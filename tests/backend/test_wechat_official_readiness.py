from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.main import app
from backend.app.models import (
    AiDraft,
    FeishuIntegrationConfig,
    WechatOfficialArticle,
    WechatOfficialArticleComment,
    WechatOfficialArticleMetric,
    WechatOfficialArticleSnapshot,
    WechatOfficialBackendSession,
    WechatOfficialCrawlAccount,
    WechatOfficialRedfoxConfig,
)

client = TestClient(app)


def _override_database(tmp_path):
    from backend.app.core.database import Base, get_db

    engine = create_engine(f"sqlite:///{tmp_path / 'wechat-official-readiness-test.db'}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return get_db, TestingSessionLocal


def _register(username: str) -> dict:
    response = client.post("/api/auth/register", json={"username": username, "password": "secret123"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _user_id(db, username: str) -> int:
    from backend.app.models import User

    user = db.query(User).filter(User.username == username).one()
    return user.id


def _check_map(payload: dict) -> dict[str, dict]:
    return {check["key"]: check for check in payload["checks"]}


def test_wechat_official_readiness_empty_workspace_returns_actionable_missing_checks(tmp_path):
    get_db, _ = _override_database(tmp_path)
    try:
        headers = _register("readiness-empty-user")

        response = client.get("/api/wechat-official/readiness", headers=headers)

        assert response.status_code == 200
        payload = response.json()
        checks = _check_map(payload)
        assert payload["summary"]["overall_status"] == "blocked"
        assert any("Redfox" in action for action in payload["summary"]["next_actions"])
        assert checks["redfox.config"]["status"] == "missing"
        assert checks["content.library"]["status"] == "missing"
        assert checks["safety.publish"]["status"] == "blocked"
        assert payload["redfox"]["configured"] is False
        assert payload["feishu"]["configured"] is False
        assert payload["sessions"]["valid"] == 0
        assert payload["content"]["total"] == 0
        assert payload["image_studio"]["available"] is True
        assert payload["image_studio"]["material_upload_blocked"] is True
        assert payload["safety"]["publish_blocked"] is True
        assert payload["safety"]["sendall_blocked"] is True
        assert payload["safety"]["preview_blocked"] is True
        assert payload["safety"]["material_upload_blocked"] is True
        assert "保持阻断" in payload["safety"]["message"]
        assert "可发布" not in payload["safety"]["message"]
        assert checks["safety.publish"]["message"] == "真实发布、预览发送、群发和素材上传均保持阻断。"
        assert "风险和 QA 设计" in checks["safety.publish"]["action"]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_wechat_official_browser_fallback_plan_is_manual_safe_and_actionable(tmp_path):
    get_db, _ = _override_database(tmp_path)
    try:
        headers = _register("browser-fallback-user")

        response = client.post(
            "/api/wechat-official/browser-fallback/plan",
            headers=headers,
            json={"url": "https://mp.weixin.qq.com/s/browser-fallback", "reason": "verification_required"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["mode"] == "manual_browser_verification"
        assert payload["url"] == "https://mp.weixin.qq.com/s/browser-fallback"
        assert payload["safe_to_automate"] is False
        assert payload["retry_policy"] == "do_not_auto_retry"
        assert payload["blocked_actions"] == ["captcha_bypass", "risk_control_evasion", "high_frequency_retry"]
        assert any("浏览器" in step["label"] for step in payload["steps"])
        assert any("完成人工验证" in step["instruction"] for step in payload["steps"])
        assert "cookie" not in str(payload).lower()
        assert "token" not in str(payload).lower()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_wechat_official_readiness_counts_config_sessions_content_and_drafts_without_network(tmp_path, monkeypatch):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        headers = _register("readiness-ready-user")
        with TestingSessionLocal() as db:
            user_id = _user_id(db, "readiness-ready-user")
            account = WechatOfficialCrawlAccount(user_id=user_id, name="Ready Account", biz="MzReady", status="active")
            db.add(account)
            db.flush()
            db.add(WechatOfficialRedfoxConfig(user_id=user_id, encrypted_api_key="encrypted-redfox", status="valid", last_error=""))
            db.add(FeishuIntegrationConfig(user_id=user_id, app_id="cli_x", encrypted_app_secret="encrypted-secret", table_id="tbl", enabled=True, last_test_status="succeeded", last_test_message="ok"))
            db.add(WechatOfficialBackendSession(account_id=account.id, status="valid"))
            db.add(WechatOfficialBackendSession(account_id=account.id, status="expired"))
            article = WechatOfficialArticle(
                account_id=account.id,
                title="Ready Article",
                digest="digest",
                article_url="https://mp.weixin.qq.com/s/ready",
                cover_url="https://img.example.com/cover.jpg",
                raw_json={"analysis": {"pool_status": "draft_ready"}},
            )
            candidate = WechatOfficialArticle(
                account_id=account.id,
                title="Candidate Article",
                digest="digest",
                article_url="https://mp.weixin.qq.com/s/candidate",
                raw_json={"analysis": {"pool_status": "candidate"}},
            )
            db.add_all([article, candidate])
            db.flush()
            db.add(WechatOfficialArticleSnapshot(article_id=article.id, text="正文", images_json=[{"url": "https://img.example.com/a.jpg"}]))
            db.add(WechatOfficialArticleMetric(article_id=article.id, read_count=120000, like_count=3000, wow_count=200, comment_count=12))
            db.add(WechatOfficialArticleComment(article_id=article.id, comment_id="c1", content="很有启发"))
            db.add(AiDraft(user_id=user_id, platform="wechat_official", title="公众号草稿", body="正文", tags=[]))
            db.commit()

        def fail_if_network_client_is_created(*args, **kwargs):
            raise AssertionError("readiness must not create Redfox client or call network")

        monkeypatch.setattr("backend.app.services.wechat_official_redfox_client.WechatOfficialRedfoxClient.__init__", fail_if_network_client_is_created)

        response = client.get("/api/wechat-official/readiness", headers=headers)

        assert response.status_code == 200
        payload = response.json()
        checks = _check_map(payload)
        assert payload["summary"]["overall_status"] in {"ready", "partial"}
        assert checks["redfox.config"]["status"] == "ready"
        assert checks["content.library"]["status"] == "ready"
        assert checks["feishu.analysis"]["status"] == "ready"
        assert checks["drafts.workbench"]["status"] == "ready"
        assert payload["redfox"]["configured"] is True
        assert payload["redfox"]["status"] == "valid"
        assert payload["feishu"]["enabled"] is True
        assert payload["feishu"]["last_test_status"] == "succeeded"
        assert payload["sessions"]["valid"] == 1
        assert payload["sessions"]["expired"] == 1
        assert payload["content"]["total"] == 2
        assert payload["content"]["candidate"] == 1
        assert payload["content"]["draft_ready"] == 1
        assert payload["content"]["snapshots"] == 1
        assert payload["content"]["images"] == 2
        assert payload["content"]["comments"] == 1
        assert payload["drafts"]["count"] == 1
        assert payload["drafts"]["dry_run_available"] is True
        assert payload["safety"]["publish_blocked"] is True
        assert payload["safety"]["sendall_blocked"] is True
        assert payload["safety"]["preview_blocked"] is True
        assert payload["safety"]["material_upload_blocked"] is True
        assert "保持阻断" in payload["safety"]["message"]
        assert checks["safety.publish"]["status"] == "blocked"
        assert "可发布" not in checks["safety.publish"]["message"]
        assert "风险和 QA 设计" in checks["safety.publish"]["action"]
    finally:
        app.dependency_overrides.pop(get_db, None)

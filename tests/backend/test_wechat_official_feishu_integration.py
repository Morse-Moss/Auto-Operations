from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.core.security import encrypt_text
from backend.app.main import app
from test_support.beta_invites import create_test_invite_code
from backend.app.models import FeishuIntegrationConfig, User, WechatOfficialArticle

client = TestClient(app)


def _override_database(tmp_path):
    from backend.app.core.database import Base, get_db

    engine = create_engine(f"sqlite:///{tmp_path / 'wechat-official-feishu-test.db'}", connect_args={"check_same_thread": False})
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
    response = client.post("/api/auth/register", json={"username": username, "password": "secret123", "invite_code": create_test_invite_code()})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _user_id(db, username: str) -> int:
    user = db.scalar(select(User).where(User.username == username))
    assert user is not None
    return user.id


def _create_feishu_config(db, *, user_id: int) -> None:
    db.add(
        FeishuIntegrationConfig(
            user_id=user_id,
            app_id="cli_wechat_test",
            encrypted_app_secret=encrypt_text("feishu-secret"),
            bitable_url="https://example.feishu.cn/base/app123?table=tbl123",
            bitable_app_token="app123",
            table_id="tbl123",
            enabled=True,
        )
    )
    db.commit()


def _create_article(headers: dict, *, title: str = "飞书分析文章", url: str = "https://mp.weixin.qq.com/s/feishu") -> int:
    start = client.post("/api/wechat-official/accounts/login/qrcode", headers=headers)
    assert start.status_code == 200
    session_id = start.json()["login_session_id"]
    complete = client.post(
        f"/api/wechat-official/accounts/login/{session_id}/complete",
        headers=headers,
        json={"cookie": "cookie-secret", "token": "token-secret", "auth_key": "auth-secret", "biz": "MzA-feishu", "nickname": "飞书公众号"},
    )
    assert complete.status_code == 200
    sync = client.post(
        "/api/wechat-official/crawl/articles/sync",
        headers=headers,
        json={"backend_session_id": session_id, "upstream_payload": {"publish_page": f'{{"publish_list":[{{"publish_info":{{"appmsgex":[{{"title":"{title}","digest":"原文摘要","link":"{url}"}}]}}}}]}}'}},
    )
    assert sync.status_code == 200
    article_id = sync.json()["items"][0]["id"]
    update = client.patch(
        f"/api/wechat-official/content-library/{article_id}/recommendation",
        headers=headers,
        json={
            "pool_status": "shortlisted",
            "recommendation_status": "recommended",
            "low_follower_evidence": True,
            "business_direction": "私域增长",
            "title_type": "结果导向",
            "article_type_label": "案例拆解",
            "viral_factors": ["强结果", "低门槛"],
            "core_insight": "用户关注可复制路径",
            "customer_conversion_method": "引导咨询",
            "hotspot_breakdown": {"hook": "强标题", "reuse_angle": "拆成清单"},
            "draft_template_key": "case_rewrite",
        },
    )
    assert update.status_code == 200
    return article_id


class FakeFeishuClient:
    def __init__(self) -> None:
        self.records: list[dict] = []
        self.created: list[dict] = []
        self.updated: list[tuple[str, dict]] = []

    def list_records(self) -> list[dict]:
        return self.records

    def create_record(self, fields: dict) -> dict:
        record = {"record_id": f"rec_{len(self.created) + 1}", "fields": fields}
        self.created.append(record)
        self.records.append(record)
        return record

    def update_record(self, record_id: str, fields: dict) -> dict:
        self.updated.append((record_id, fields))
        return {"record_id": record_id, "fields": fields}


def test_wechat_official_feishu_push_dry_run_maps_owned_article_without_client(tmp_path, monkeypatch):
    get_db, _ = _override_database(tmp_path)
    try:
        headers = _register("wechat-feishu-dry-run-user")
        article_id = _create_article(headers)

        def forbidden_client(_config):
            raise AssertionError("dry-run must not create a real Feishu client")

        monkeypatch.setattr("backend.app.api.feishu_integration.create_feishu_client_from_config", forbidden_client)
        response = client.post(
            "/api/integrations/feishu/wechat-official/articles/push",
            headers=headers,
            json={"article_ids": [article_id], "dry_run": True},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["dry_run"] is True
        assert payload["updated_count"] == 1
        assert payload["failed_count"] == 0
        fields = payload["records"][0]["fields"]
        assert fields["系统文章ID"] == str(article_id)
        assert fields["平台"] == "公众号"
        assert fields["标题"] == "飞书分析文章"
        assert fields["公众号/作者"] == "飞书公众号"
        assert fields["核心洞察"] == "用户关注可复制路径"
        assert fields["爆点拆解"]
        assert "cookie-secret" not in str(fields)
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_wechat_official_feishu_push_uses_fake_client_and_records_sync_metadata(tmp_path, monkeypatch):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    fake_client = FakeFeishuClient()
    try:
        username = "wechat-feishu-push-user"
        headers = _register(username)
        article_id = _create_article(headers)
        with TestingSessionLocal() as db:
            _create_feishu_config(db, user_id=_user_id(db, username))

        monkeypatch.setattr("backend.app.api.feishu_integration.create_feishu_client_from_config", lambda _config: fake_client)
        response = client.post(
            "/api/integrations/feishu/wechat-official/articles/push",
            headers=headers,
            json={"article_ids": [article_id], "dry_run": False},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["dry_run"] is False
        assert payload["created_count"] == 1
        assert payload["updated_count"] == 0
        assert payload["failed_count"] == 0
        assert fake_client.created[0]["fields"]["系统文章ID"] == str(article_id)
        with TestingSessionLocal() as db:
            article = db.get(WechatOfficialArticle, article_id)
            assert article is not None
            assert article.raw_json["feishu"]["record_id"] == "rec_1"
            assert article.raw_json["feishu"]["push_status"] == "synced"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_wechat_official_feishu_pull_updates_analysis_for_owned_article(tmp_path):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        headers = _register("wechat-feishu-pull-user")
        article_id = _create_article(headers)
        response = client.post(
            "/api/integrations/feishu/wechat-official/articles/pull",
            headers=headers,
            json={
                "dry_run": True,
                "records": [
                    {
                        "record_id": "rec_pull_1",
                        "fields": {
                            "系统文章ID": str(article_id),
                            "分析状态": "已完成",
                            "入库状态": "draft_ready",
                            "推荐状态": "recommended",
                            "核心洞察": "飞书回拉后的核心洞察",
                            "业务方向": "企业服务",
                            "爆点因子": "强结果、强对比",
                            "爆点拆解": "hook: 新标题\nreuse_angle: 新角度",
                            "草稿模板": "insight_commentary",
                        },
                    }
                ],
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["updated_count"] == 1
        assert payload["unmatched_count"] == 0
        with TestingSessionLocal() as db:
            article = db.get(WechatOfficialArticle, article_id)
            assert article is not None
            analysis = article.raw_json["analysis"]
            assert analysis["analysis_status"] == "已完成"
            assert analysis["pool_status"] == "draft_ready"
            assert analysis["core_insight"] == "飞书回拉后的核心洞察"
            assert analysis["business_direction"] == "企业服务"
            assert analysis["viral_factors"] == ["强结果", "强对比"]
            assert analysis["hotspot_breakdown"]["hook"] == "新标题"
            assert article.raw_json["feishu"]["record_id"] == "rec_pull_1"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_wechat_official_feishu_pull_is_scoped_to_current_user(tmp_path):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        owner_headers = _register("wechat-feishu-owner")
        other_headers = _register("wechat-feishu-other")
        article_id = _create_article(owner_headers, title="他人的文章", url="https://mp.weixin.qq.com/s/other-owned")
        response = client.post(
            "/api/integrations/feishu/wechat-official/articles/pull",
            headers=other_headers,
            json={"dry_run": True, "records": [{"record_id": "rec_other", "fields": {"系统文章ID": str(article_id), "核心洞察": "不应写入"}}]},
        )

        assert response.status_code == 200
        assert response.json()["updated_count"] == 0
        assert response.json()["unmatched_count"] == 1
        with TestingSessionLocal() as db:
            article = db.get(WechatOfficialArticle, article_id)
            assert article is not None
            assert article.raw_json["analysis"]["core_insight"] == "用户关注可复制路径"
    finally:
        app.dependency_overrides.pop(get_db, None)

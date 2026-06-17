from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.main import app
from backend.app.models import AiDraft, PublishJob, WechatOfficialDraftSource

client = TestClient(app)


def _override_database(tmp_path):
    from backend.app.core.database import Base, get_db

    engine = create_engine(f"sqlite:///{tmp_path / 'wechat-official-drafts-test.db'}", connect_args={"check_same_thread": False})
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


def _create_article_with_snapshot(headers: dict) -> int:
    start = client.post("/api/wechat-official/accounts/login/qrcode", headers=headers)
    assert start.status_code == 200
    session_id = start.json()["login_session_id"]
    complete = client.post(
        f"/api/wechat-official/accounts/login/{session_id}/complete",
        headers=headers,
        json={"cookie": "cookie-secret", "token": "token-secret", "auth_key": "auth-secret", "biz": "MzA-draft", "nickname": "Draft Account"},
    )
    assert complete.status_code == 200
    sync = client.post(
        "/api/wechat-official/crawl/articles/sync",
        headers=headers,
        json={"backend_session_id": session_id, "upstream_payload": {"publish_page": '{"publish_list":[{"publish_info":{"appmsgex":[{"title":"原文标题","digest":"原文摘要","link":"https://mp.weixin.qq.com/s/draft"}]}}]}'}},
    )
    assert sync.status_code == 200
    article_id = sync.json()["items"][0]["id"]
    snapshot = client.post(
        f"/api/wechat-official/crawl/articles/{article_id}/snapshot",
        headers=headers,
        json={"html": '<div id="js_article"><div id="js_content">原文正文第一段。原文正文第二段。</div></div>'},
    )
    assert snapshot.status_code == 200
    return article_id


def test_create_draft_from_content_library_creates_wechat_official_ai_draft_and_source(tmp_path):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        headers = _register("draft-user")
        article_id = _create_article_with_snapshot(headers)

        response = client.post(
            f"/api/wechat-official/content-library/{article_id}/create-draft",
            headers=headers,
            json={"rewrite_style": "专业克制", "target_audience": "企业主", "call_to_action": "预约咨询"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["platform"] == "wechat_official"
        assert payload["title"] == "原文标题"
        assert "专业克制" in payload["body"]
        assert "企业主" in payload["body"]
        assert "预约咨询" in payload["body"]
        assert "原文正文第一段" in payload["body"]

        with TestingSessionLocal() as db:
            draft = db.get(AiDraft, payload["id"])
            source = db.scalar(select(WechatOfficialDraftSource).where(WechatOfficialDraftSource.draft_id == payload["id"]))
            assert draft is not None
            assert draft.platform == "wechat_official"
            assert source is not None
            assert source.article_id == article_id
            assert source.source_type == "rewrite"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_generic_send_to_publish_blocks_wechat_official_draft_without_creating_job(tmp_path):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        headers = _register("send-to-publish-block-user")
        article_id = _create_article_with_snapshot(headers)
        create = client.post(
            f"/api/wechat-official/content-library/{article_id}/create-draft",
            headers=headers,
            json={"rewrite_style": "简洁", "target_audience": "运营", "call_to_action": "联系我"},
        )
        assert create.status_code == 200
        draft_id = create.json()["id"]

        response = client.post(
            f"/api/drafts/{draft_id}/send-to-publish",
            headers=headers,
            json={"publish_mode": "immediate"},
        )

        assert response.status_code in {400, 403, 422}
        assert response.json()["detail"] == "微信公众号发布/群发本阶段保持阻断，请使用 dry-run/草稿工作台"
        with TestingSessionLocal() as db:
            assert db.scalar(select(PublishJob).where(PublishJob.source_draft_id == draft_id)) is None
    finally:
        app.dependency_overrides.pop(get_db, None)



def test_draft_dry_run_blocks_publish_and_reports_content_checks(tmp_path):
    get_db, _ = _override_database(tmp_path)
    try:
        headers = _register("dry-run-user")
        article_id = _create_article_with_snapshot(headers)
        create = client.post(
            f"/api/wechat-official/content-library/{article_id}/create-draft",
            headers=headers,
            json={"rewrite_style": "简洁", "target_audience": "运营", "call_to_action": "联系我"},
        )
        draft_id = create.json()["id"]

        response = client.post(f"/api/wechat-official/drafts/{draft_id}/dry-run", headers=headers)

        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        assert payload["publish_blocked"] is True
        assert payload["sendall_blocked"] is True
        assert payload["checks"]["title"] == "ok"
        assert payload["checks"]["body"] == "ok"
        assert payload["checks"]["external_images"] == "ok"

        empty = client.post(f"/api/wechat-official/drafts/{draft_id}/dry-run", headers=headers, json={"title": "", "body": "![x](https://example.com/a.png)"})
        assert empty.status_code == 200
        empty_payload = empty.json()
        assert empty_payload["ok"] is False
        assert empty_payload["checks"]["title"] == "missing"
        assert empty_payload["checks"]["external_images"] == "warning"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_draft_dry_run_is_scoped_to_current_user(tmp_path):
    get_db, _ = _override_database(tmp_path)
    try:
        owner_headers = _register("dry-run-owner")
        other_headers = _register("dry-run-other")
        article_id = _create_article_with_snapshot(owner_headers)
        create = client.post(f"/api/wechat-official/content-library/{article_id}/create-draft", headers=owner_headers, json={})
        assert create.status_code == 200

        response = client.post(f"/api/wechat-official/drafts/{create.json()['id']}/dry-run", headers=other_headers)
        assert response.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)

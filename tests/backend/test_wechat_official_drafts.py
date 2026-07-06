from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.main import app
from test_support.beta_invites import create_test_invite_code
from backend.app.models import AiDraft, PublishJob, WechatOfficialArticle, WechatOfficialArticleSnapshot, WechatOfficialDraftSource

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
    response = client.post("/api/auth/register", json={"username": username, "password": "secret123", "invite_code": create_test_invite_code()})
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


def test_create_draft_from_content_library_returns_traceable_wechat_official_draft(tmp_path):
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
        assert "source_note_id" not in payload
        assert payload["source_article_id"] == article_id
        assert "专业克制" in payload["body"]
        assert "企业主" in payload["body"]
        assert "预约咨询" in payload["body"]
        assert "原文正文第一段" in payload["body"]

        list_response = client.get("/api/drafts", headers=headers, params={"platform": "wechat_official"})
        assert list_response.status_code == 200
        listed = list_response.json()["items"][0]
        assert listed["id"] == payload["id"]
        assert listed["source_article_id"] == article_id

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


def test_create_draft_with_template_updates_article_analysis_and_source_row(tmp_path):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        headers = _register("draft-template-user")
        article_id = _create_article_with_snapshot(headers)

        response = client.post(
            f"/api/wechat-official/content-library/{article_id}/create-draft",
            headers=headers,
            json={
                "rewrite_style": "提炼案例价值",
                "target_audience": "内容运营",
                "call_to_action": "收藏并复盘",
                "template_key": "case_rewrite",
                "template_name": "案例拆解",
                "template_instruction": "按 背景-冲突-方法-结果-启发 组织二创草稿。",
                "opening_angle": "从爆文结构拆解可复用方法",
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert "source_note_id" not in payload
        assert "案例拆解" in payload["body"]
        assert "按 背景-冲突-方法-结果-启发 组织二创草稿。" in payload["body"]
        assert "从爆文结构拆解可复用方法" in payload["body"]

        with TestingSessionLocal() as db:
            source = db.scalar(select(WechatOfficialDraftSource).where(WechatOfficialDraftSource.draft_id == payload["id"]))
            assert source is not None
            assert source.article_id == article_id
            article = db.get(WechatOfficialArticle, article_id)
            assert article is not None
            assert article.raw_json["analysis"]["pool_status"] == "draft_ready"
            assert article.raw_json["analysis"]["draft_template_key"] == "case_rewrite"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_deleted_content_article_does_not_remove_existing_wechat_official_draft(tmp_path):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        headers = _register("draft-delete-source-user")
        article_id = _create_article_with_snapshot(headers)
        create = client.post(
            f"/api/wechat-official/content-library/{article_id}/create-draft",
            headers=headers,
            json={"rewrite_style": "简洁", "target_audience": "运营", "call_to_action": "联系我"},
        )
        assert create.status_code == 200
        draft_id = create.json()["id"]

        delete = client.delete(f"/api/wechat-official/content-library/{article_id}", headers=headers)
        assert delete.status_code == 200

        with TestingSessionLocal() as db:
            assert db.get(AiDraft, draft_id) is not None
            assert db.scalar(select(WechatOfficialDraftSource).where(WechatOfficialDraftSource.draft_id == draft_id)) is None

        with TestingSessionLocal() as db:
            draft = db.get(AiDraft, draft_id)
            assert draft is not None
            assert draft.platform == "wechat_official"
            assert draft.title == "原文标题"
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



def test_create_draft_from_analyzed_article_uses_analysis_fields(tmp_path):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        headers = _register("draft-analysis-user")
        article_id = _create_article_with_snapshot(headers)
        with TestingSessionLocal() as db:
            article = db.get(WechatOfficialArticle, article_id)
            assert article is not None
            article.raw_json = {
                **(article.raw_json or {}),
                "analysis": {
                    "core_insight": "飞书回拉的核心洞察",
                    "viral_factors": ["强结果", "强对比"],
                    "title_type": "结果导向",
                    "article_type_label": "案例拆解",
                    "business_direction": "企业服务",
                    "customer_conversion_method": "引导预约咨询",
                    "draft_template_key": "case_rewrite",
                    "hotspot_breakdown": {"hook": "强标题钩子", "reuse_angle": "拆成实操清单"},
                },
            }
            db.commit()

        response = client.post(
            f"/api/wechat-official/content-library/{article_id}/create-draft",
            headers=headers,
            json={"template_name": "案例拆解", "template_instruction": "按 背景-冲突-方法-结果-启发 组织。"},
        )

        assert response.status_code == 200
        body = response.json()["body"]
        assert "飞书回拉的核心洞察" in body
        assert "强结果、强对比" in body
        assert "结果导向" in body
        assert "案例拆解" in body
        assert "企业服务" in body
        assert "引导预约咨询" in body
        assert "强标题钩子" in body
        assert "case_rewrite" in body
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_draft_dry_run_blocks_publish_preview_and_reports_content_checks(tmp_path):
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
        assert payload["preview_blocked"] is True
        assert payload["material_upload_blocked"] is True
        assert payload["checks"]["title"] == "ok"
        assert payload["checks"]["body"] == "ok"
        assert payload["checks"]["external_images"] == "ok"
        assert payload["checks"]["source_article"] == "ok"
        assert payload["checks"]["material_upload"] == "blocked"
        assert "本地草稿检查" in payload["message"]
        assert "不代表可以发布" in payload["message"]
        assert any("图片工坊" in action for action in payload["next_actions"])

        empty = client.post(f"/api/wechat-official/drafts/{draft_id}/dry-run", headers=headers, json={"title": "", "body": "![x](https://example.com/a.png)"})
        assert empty.status_code == 200
        empty_payload = empty.json()
        assert empty_payload["ok"] is False
        assert empty_payload["material_upload_blocked"] is True
        assert empty_payload["checks"]["title"] == "missing"
        assert empty_payload["checks"]["body"] == "ok"
        assert empty_payload["checks"]["external_images"] == "warning"
        assert empty_payload["checks"]["material_upload"] == "blocked"
        assert any("补标题" in action for action in empty_payload["next_actions"])
        assert any("外链图片" in action for action in empty_payload["next_actions"])
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

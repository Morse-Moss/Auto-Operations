from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.main import app
from backend.app.core.security import encrypt_text
from backend.app.models import ModelConfig, WechatOfficialArticle, WechatOfficialArticleSnapshot, WechatOfficialCrawlAccount
from backend.app.services import wechat_official_content_service

client = TestClient(app)


def _override_database(tmp_path):
    from backend.app.core.database import Base, get_db

    engine = create_engine(f"sqlite:///{tmp_path / 'wechat-official-content-test.db'}", connect_args={"check_same_thread": False})
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


def _create_session(headers: dict) -> int:
    start = client.post("/api/wechat-official/accounts/login/qrcode", headers=headers)
    assert start.status_code == 200
    session_id = start.json()["login_session_id"]
    complete = client.post(
        f"/api/wechat-official/accounts/login/{session_id}/complete",
        headers=headers,
        json={"cookie": "cookie-secret", "token": "token-secret", "auth_key": "auth-secret", "biz": "MzA-library", "nickname": "Library Account"},
    )
    assert complete.status_code == 200
    return session_id


def _create_article(headers: dict, *, title: str, url: str, read_count: int = 0) -> int:
    session_id = _create_session(headers)
    sync = client.post(
        "/api/wechat-official/crawl/articles/sync",
        headers=headers,
        json={"backend_session_id": session_id, "upstream_payload": {"publish_page": f'{{"publish_list":[{{"publish_info":{{"appmsgex":[{{"title":"{title}","digest":"摘要{title}","link":"{url}"}}]}}}}]}}'}},
    )
    assert sync.status_code == 200
    article_id = sync.json()["items"][0]["id"]
    if read_count:
        credential_payload = {
            "biz": "MzA-library",
            "uin": "123456",
            "key": "article-key-secret",
            "pass_ticket": "pass-ticket-secret",
            "wap_sid2": "wap-sid2-secret",
            "appmsg_token": "appmsg-token-secret",
            "cookie": "credential-cookie-secret",
            "timestamp": 1780000000,
            "nickname": "Library Account",
        }
        credential = client.post("/api/wechat-official/credentials/import", headers=headers, json=credential_payload)
        assert credential.status_code == 200
        metric = client.post(
            f"/api/wechat-official/crawl/articles/{article_id}/metrics",
            headers=headers,
            json={"credential_id": credential.json()["id"], "cgi_data": {"read_num": read_count, "like_count": 99}},
        )
        assert metric.status_code == 200
    return article_id


def test_content_library_filters_viral_keyword_and_recommendation_status(tmp_path):
    get_db, _ = _override_database(tmp_path)
    try:
        headers = _register("content-library-user")
        viral_id = _create_article(headers, title="AI爆款案例", url="https://mp.weixin.qq.com/s/viral", read_count=100000)
        normal_id = _create_article(headers, title="普通案例", url="https://mp.weixin.qq.com/s/normal", read_count=99999)

        update = client.patch(
            f"/api/wechat-official/content-library/{viral_id}/recommendation",
            headers=headers,
            json={"recommendation_status": "recommended", "low_follower_evidence": True, "business_direction": "B2B", "core_insight": "低粉高赞"},
        )
        assert update.status_code == 200

        viral_response = client.get("/api/wechat-official/content-library?viral_only=true&keyword=AI&recommendation_status=recommended", headers=headers)
        assert viral_response.status_code == 200
        payload = viral_response.json()
        assert payload["total"] == 1
        assert payload["items"][0]["id"] == viral_id
        assert payload["items"][0]["is_candidate"] is True
        assert payload["items"][0]["latest_metric"]["read_count"] == 100000
        assert payload["items"][0]["analysis"]["business_direction"] == "B2B"

        min_read_response = client.get("/api/wechat-official/content-library?min_read_count=100000", headers=headers)
        assert [item["id"] for item in min_read_response.json()["items"]] == [viral_id]

        all_response = client.get("/api/wechat-official/content-library", headers=headers)
        all_ids = {item["id"] for item in all_response.json()["items"]}
        assert all_ids == {viral_id, normal_id}
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_content_library_recommendation_patch_stores_analysis_fields_in_raw_json(tmp_path):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        headers = _register("content-update-user")
        article_id = _create_article(headers, title="分析案例", url="https://mp.weixin.qq.com/s/analysis", read_count=120000)

        response = client.patch(
            f"/api/wechat-official/content-library/{article_id}/recommendation",
            headers=headers,
            json={
                "recommendation_status": "shortlisted",
                "pool_status": "shortlisted",
                "low_follower_evidence": True,
                "low_follower_note": "账号粉丝少但阅读高",
                "business_direction": "私域增长",
                "title_type": "结果导向",
                "article_type_label": "案例拆解",
                "viral_factors": ["强结果", "低门槛"],
                "core_insight": "用户关注可复制路径",
                "case_info": {"brand": "Example"},
                "customer_conversion_method": "引导咨询",
                "hotspot_breakdown": {"hook": "强标题", "pain_point": "获客焦虑"},
                "analysis_mode": "manual",
            },
        )

        assert response.status_code == 200
        analysis = response.json()["analysis"]
        assert analysis["recommendation_status"] == "shortlisted"
        assert analysis["pool_status"] == "shortlisted"
        assert analysis["viral_factors"] == ["强结果", "低门槛"]
        assert analysis["case_info"] == {"brand": "Example"}
        assert analysis["hotspot_breakdown"]["hook"] == "强标题"
        assert analysis["analysis_mode"] == "manual"

        with TestingSessionLocal() as db:
            article = db.get(WechatOfficialArticle, article_id)
            assert article is not None
            assert article.raw_json["analysis"]["customer_conversion_method"] == "引导咨询"
            assert article.raw_json["analysis"]["pool_status"] == "shortlisted"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_content_library_rejects_invalid_pool_status_without_mutating_analysis(tmp_path):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        headers = _register("invalid-pool-status-user")
        article_id = _create_article(headers, title="状态案例", url="https://mp.weixin.qq.com/s/status", read_count=120000)
        ok = client.patch(
            f"/api/wechat-official/content-library/{article_id}/recommendation",
            headers=headers,
            json={"pool_status": "shortlisted"},
        )
        assert ok.status_code == 200

        response = client.patch(
            f"/api/wechat-official/content-library/{article_id}/recommendation",
            headers=headers,
            json={"pool_status": "published"},
        )

        assert response.status_code in {400, 422}
        with TestingSessionLocal() as db:
            article = db.get(WechatOfficialArticle, article_id)
            assert article is not None
            assert article.raw_json["analysis"]["pool_status"] == "shortlisted"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_content_library_detail_returns_snapshot_and_sanitized_raw_json(tmp_path):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        owner_headers = _register("detail-owner")
        other_headers = _register("detail-other")
        article_id = _create_article(owner_headers, title="详情案例", url="https://mp.weixin.qq.com/s/detail", read_count=130000)
        client.patch(
            f"/api/wechat-official/content-library/{article_id}/recommendation",
            headers=owner_headers,
            json={"pool_status": "shortlisted", "hotspot_breakdown": {"hook": "详情钩子"}},
        )
        with TestingSessionLocal() as db:
            article = db.get(WechatOfficialArticle, article_id)
            assert article is not None
            article.raw_json = {
                **(article.raw_json or {}),
                "redfox": {"external_id": "wx-1", "work_uuid": "wx-1", "api_key": "leaked-key", "token": "leaked-token"},
            }
            db.add(WechatOfficialArticleSnapshot(article_id=article_id, status="captured", text="详情正文快照", raw_json={"api_key": "snapshot-secret"}))
            db.commit()

        response = client.get(f"/api/wechat-official/content-library/{article_id}", headers=owner_headers)
        assert response.status_code == 200
        payload = response.json()
        assert payload["article"]["id"] == article_id
        assert payload["analysis"]["pool_status"] == "shortlisted"
        assert payload["latest_snapshot"]["text"] == "详情正文快照"
        assert payload["raw_json"]["redfox"]["external_id"] == "wx-1"
        serialized = response.text
        assert "leaked-key" not in serialized
        assert "leaked-token" not in serialized
        assert "snapshot-secret" not in serialized
        assert "api_key" not in serialized.lower()
        assert "token" not in serialized.lower()

        other = client.get(f"/api/wechat-official/content-library/{article_id}", headers=other_headers)
        assert other.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_analyze_hotspots_falls_back_to_template_without_default_model(tmp_path):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        headers = _register("hotspot-template-user")
        article_id = _create_article(headers, title="爆点案例", url="https://mp.weixin.qq.com/s/hotspot-template", read_count=150000)

        response = client.post(f"/api/wechat-official/content-library/{article_id}/analyze-hotspots", headers=headers, json={})

        assert response.status_code == 200
        payload = response.json()
        assert payload["analysis_mode"] == "template"
        assert payload["analysis"]["hotspot_breakdown"]["hook"]
        assert payload["analysis"]["pool_status"] == "shortlisted"
        with TestingSessionLocal() as db:
            article = db.get(WechatOfficialArticle, article_id)
            assert article is not None
            assert article.raw_json["analysis"]["analysis_mode"] == "template"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_analyze_hotspots_uses_fake_ai_json_and_degrades_on_invalid_json(tmp_path, monkeypatch):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        headers = _register("hotspot-ai-user")
        article_id = _create_article(headers, title="AI拆解案例", url="https://mp.weixin.qq.com/s/hotspot-ai", read_count=160000)
        bad_article_id = _create_article(headers, title="AI异常案例", url="https://mp.weixin.qq.com/s/hotspot-bad", read_count=160000)
        with TestingSessionLocal() as db:
            article = db.get(WechatOfficialArticle, article_id)
            assert article is not None
            account = db.get(WechatOfficialCrawlAccount, article.account_id)
            assert account is not None
            db.add(ModelConfig(user_id=account.user_id, name="Fake Text", model_type="text", provider="openai", model_name="fake", base_url="https://example.test", encrypted_api_key=encrypt_text("fake-key"), is_default=True))
            db.commit()

        class FakeClient:
            def __init__(self) -> None:
                self.calls = 0

            def polish_text(self, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    return '{"hotspot_breakdown":{"hook":"AI钩子","pain_point":"AI痛点","promise":"AI承诺","credibility":"AI证据","structure":"AI结构","reuse_angle":"AI角度"},"viral_factors":["强冲突"],"core_insight":"AI洞察","title_type":"冲突型","article_type_label":"案例拆解"}'
                return "not json"

        fake_client = FakeClient()
        monkeypatch.setattr(wechat_official_content_service, "OpenAICompatibleTextClient", lambda: fake_client)

        response = client.post(f"/api/wechat-official/content-library/{article_id}/analyze-hotspots", headers=headers, json={})
        assert response.status_code == 200
        analysis = response.json()["analysis"]
        assert response.json()["analysis_mode"] == "ai"
        assert analysis["hotspot_breakdown"]["hook"] == "AI钩子"
        assert analysis["viral_factors"] == ["强冲突"]
        assert analysis["core_insight"] == "AI洞察"

        degraded = client.post(f"/api/wechat-official/content-library/{bad_article_id}/analyze-hotspots", headers=headers, json={})
        assert degraded.status_code == 200
        assert degraded.json()["analysis_mode"] == "template_ai_parse_failed"
        assert degraded.json()["analysis"]["hotspot_breakdown"]["hook"]
    finally:
        app.dependency_overrides.pop(get_db, None)

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.main import app
from test_support.beta_invites import create_test_invite_code
from test_support.model_capabilities import bind_test_model_capability
from backend.app.core.security import encrypt_text
from backend.app.models import (
    ModelConfig,
    Notification,
    User,
    WechatOfficialArticle,
    WechatOfficialArticleComment,
    WechatOfficialArticleCommentReply,
    WechatOfficialArticleMetric,
    WechatOfficialArticleSnapshot,
    WechatOfficialCrawlAccount,
    WechatOfficialCrawlJob,
)
from backend.app.services import wechat_official_content_service
from backend.app.services import wechat_official_redfox_service as redfox_service
from backend.app.services.wechat_official_content_tombstone_service import WechatOfficialContentTombstoneService

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
    response = client.post("/api/auth/register", json={"username": username, "password": "secret123", "invite_code": create_test_invite_code()})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _register_admin(username: str, TestingSessionLocal) -> dict:
    headers = _register(username)
    with TestingSessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))
        assert user is not None
        user.role = "admin"
        db.commit()
    return headers


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


def test_content_library_pool_status_filter_keeps_candidates_out_of_library_view(tmp_path):
    get_db, _ = _override_database(tmp_path)
    try:
        headers = _register("pool-filter-user")
        candidate_id = _create_article(headers, title="候选文章", url="https://mp.weixin.qq.com/s/candidate", read_count=120000)
        library_id = _create_article(headers, title="入库文章", url="https://mp.weixin.qq.com/s/library", read_count=90000)

        update = client.patch(
            f"/api/wechat-official/content-library/{library_id}/recommendation",
            headers=headers,
            json={"pool_status": "shortlisted"},
        )
        assert update.status_code == 200

        candidate_response = client.get("/api/wechat-official/content-library?pool_status=candidate", headers=headers)
        assert candidate_response.status_code == 200
        assert {item["id"] for item in candidate_response.json()["items"]} == {candidate_id}

        library_response = client.get("/api/wechat-official/content-library?pool_status=shortlisted", headers=headers)
        assert library_response.status_code == 200
        assert {item["id"] for item in library_response.json()["items"]} == {library_id}
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_content_library_list_paginates_searches_author_and_validates_pool_status(tmp_path):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        headers = _register("content-library-pagination-user")
        article_ids = [
            _create_article(headers, title=f"入库文章 {index}", url=f"https://mp.weixin.qq.com/s/page-{index}", read_count=100000 + index)
            for index in range(3)
        ]
        for article_id in article_ids:
            update = client.patch(
                f"/api/wechat-official/content-library/{article_id}/recommendation",
                headers=headers,
                json={"pool_status": "shortlisted"},
            )
            assert update.status_code == 200

        with TestingSessionLocal() as db:
            article = db.get(WechatOfficialArticle, article_ids[1])
            assert article is not None
            article.author_name = "目标公众号"
            db.commit()

        page_response = client.get("/api/wechat-official/content-library?pool_status=shortlisted&page=2&page_size=1", headers=headers)
        assert page_response.status_code == 200
        page_payload = page_response.json()
        assert page_payload["total"] == 3
        assert page_payload["page"] == 2
        assert page_payload["page_size"] == 1
        assert len(page_payload["items"]) == 1

        author_response = client.get("/api/wechat-official/content-library?pool_status=shortlisted&keyword=目标公众号", headers=headers)
        assert author_response.status_code == 200
        author_payload = author_response.json()
        assert author_payload["total"] == 1
        assert author_payload["items"][0]["id"] == article_ids[1]

        invalid = client.get("/api/wechat-official/content-library?pool_status=published", headers=headers)
        assert invalid.status_code == 400
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_hotspot_analysis_uses_admin_default_doubao_for_regular_user(tmp_path, monkeypatch):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        headers = _register("content-library-doubao-user")
        article_id = _create_article(headers, title="AI早餐案例", url="https://mp.weixin.qq.com/s/doubao-admin-default", read_count=120000)

        with TestingSessionLocal() as db:
            owner = db.scalar(select(User).where(User.username == "content-library-doubao-user"))
            admin = User(username="content-library-doubao-admin", password_hash="hashed", role="admin", status="active")
            db.add(admin)
            db.flush()
            config = ModelConfig(
                user_id=admin.id,
                name="Doubao Text",
                model_type="text",
                provider="volcengine-ark",
                model_name="doubao-seed-2-0-mini-260428",
                base_url="https://ark.cn-beijing.volces.com/api/v3",
                encrypted_api_key=encrypt_text("sk-doubao-text"),
                is_default=True,
            )
            bind_test_model_capability(db, config=config, capability="text")
            db.add(
                WechatOfficialArticleSnapshot(
                    article_id=article_id,
                    status="captured",
                    text="这是一篇关于低成本早餐内容运营的公众号文章。",
                    html="<p>这是一篇关于低成本早餐内容运营的公众号文章。</p>",
                    images_json=[],
                )
            )
            db.commit()

        calls: list[dict] = []

        class FakeTextClient:
            def polish_text(self, *, model_config, api_key, text, instruction):
                calls.append({"model_name": model_config.model_name, "api_key": api_key, "instruction": instruction})
                return (
                    '{"hotspot_breakdown":{"hook":"hook","pain_point":"pain","promise":"promise",'
                    '"credibility":"credibility","structure":"structure","reuse_angle":"reuse"},'
                    '"viral_factors":["factor"],"core_insight":"insight",'
                    '"title_type":"list","article_type_label":"case"}'
                )

        monkeypatch.setattr(wechat_official_content_service, "OpenAICompatibleTextClient", FakeTextClient)

        response = client.post(
            f"/api/wechat-official/content-library/{article_id}/analyze-hotspots",
            headers=headers,
            json={"instruction": "从低成本获客角度分析"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["analysis_mode"] == "ai"
        assert calls == [{"model_name": "doubao-seed-2-0-mini-260428", "api_key": "sk-doubao-text", "instruction": "只输出 JSON"}]
        assert payload["analysis"]["core_insight"] == "insight"
        assert payload["analysis"]["article_type_label"] == "case"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_content_library_filters_by_job_id_for_owned_articles(tmp_path):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        headers = _register("content-library-job-filter-user")
        first_id = _create_article(headers, title="第一批文章", url="https://mp.weixin.qq.com/s/job-filter-1", read_count=120000)
        second_id = _create_article(headers, title="第二批文章", url="https://mp.weixin.qq.com/s/job-filter-2", read_count=130000)

        with TestingSessionLocal() as db:
            first = db.get(WechatOfficialArticle, first_id)
            second = db.get(WechatOfficialArticle, second_id)
            assert first is not None
            assert second is not None

            first_job = WechatOfficialCrawlJob(
                account_id=first.account_id,
                keyword="第一批",
                status="succeeded",
                source="redfox",
                requested_limit=1,
                fetched_count=1,
                saved_count=1,
                params_json={"source": "redfox_keyword", "api_calls": 1},
            )
            second_job = WechatOfficialCrawlJob(
                account_id=second.account_id,
                keyword="第二批",
                status="succeeded",
                source="redfox",
                requested_limit=1,
                fetched_count=1,
                saved_count=1,
                params_json={"source": "redfox_keyword", "api_calls": 1},
            )
            db.add(first_job)
            db.add(second_job)
            db.flush()
            first.job_id = first_job.id
            second.job_id = second_job.id
            db.commit()
            first_job_id = first_job.id
            second_job_id = second_job.id

        first_response = client.get(f"/api/wechat-official/content-library?job_id={first_job_id}", headers=headers)
        assert first_response.status_code == 200
        assert first_response.json()["total"] == 1
        assert first_response.json()["items"][0]["id"] == first_id
        assert first_response.json()["items"][0]["job_id"] == first_job_id

        second_response = client.get(f"/api/wechat-official/content-library?job_id={second_job_id}", headers=headers)
        assert second_response.status_code == 200
        assert second_response.json()["total"] == 1
        assert second_response.json()["items"][0]["id"] == second_id

        invalid = client.get("/api/wechat-official/content-library?job_id=0", headers=headers)
        assert invalid.status_code == 422
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_content_library_curates_tags_favorite_read_status_and_completeness_filters(tmp_path):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        headers = _register("content-library-curation-user")
        complete_id = _create_article(headers, title="完整私域案例", url="https://mp.weixin.qq.com/s/curation-complete", read_count=130000)
        incomplete_id = _create_article(headers, title="未读行业观察", url="https://mp.weixin.qq.com/s/curation-incomplete", read_count=90000)

        with TestingSessionLocal() as db:
            db.add(
                WechatOfficialArticleSnapshot(
                    article_id=complete_id,
                    status="captured",
                    text="完整正文",
                    html="<p>完整正文</p>",
                    images_json=[{"url": "https://img.example/curation.jpg", "type": "content"}],
                )
            )
            db.commit()

        update = client.patch(
            f"/api/wechat-official/content-library/{complete_id}/recommendation",
            headers=headers,
            json={
                "pool_status": "shortlisted",
                "category": "私域增长",
                "tags": ["案例", "转化"],
                "is_favorite": True,
                "read_status": "read",
            },
        )
        assert update.status_code == 200
        analysis = update.json()["analysis"]
        assert analysis["category"] == "私域增长"
        assert analysis["tags"] == ["案例", "转化"]
        assert analysis["is_favorite"] is True
        assert analysis["read_status"] == "read"
        assert update.json()["detail_status"]["completeness"] == "complete"

        client.patch(
            f"/api/wechat-official/content-library/{incomplete_id}/recommendation",
            headers=headers,
            json={"pool_status": "shortlisted", "category": "行业观察", "tags": ["趋势"], "read_status": "unread"},
        )

        favorite_response = client.get("/api/wechat-official/content-library?pool_status=shortlisted&category=私域增长&tag=转化&is_favorite=true&read_status=read&detail_complete=true", headers=headers)
        assert favorite_response.status_code == 200
        assert favorite_response.json()["total"] == 1
        assert favorite_response.json()["items"][0]["id"] == complete_id
        assert favorite_response.json()["items"][0]["detail_status"]["has_text"] is True

        incomplete_response = client.get("/api/wechat-official/content-library?pool_status=shortlisted&detail_complete=false", headers=headers)
        assert incomplete_response.status_code == 200
        assert {item["id"] for item in incomplete_response.json()["items"]} == {incomplete_id}
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_content_library_exports_json_csv_and_rss_feed(tmp_path):
    get_db, _ = _override_database(tmp_path)
    try:
        headers = _register("content-library-export-user")
        article_id = _create_article(headers, title="导出案例", url="https://mp.weixin.qq.com/s/export-target", read_count=150000)
        client.patch(
            f"/api/wechat-official/content-library/{article_id}/recommendation",
            headers=headers,
            json={"pool_status": "shortlisted", "category": "私域增长", "tags": ["案例", "转化"], "is_favorite": True, "read_status": "read"},
        )

        json_export = client.post("/api/wechat-official/content-library/export", headers=headers, json={"article_ids": [article_id], "format": "json"})
        assert json_export.status_code == 200
        assert json_export.json()["exported_count"] == 1
        assert json_export.json()["file_name"].startswith("wechat_official-articles-u1-")
        assert json_export.json()["download_url"].startswith("/api/files/exports/")

        csv_export = client.post("/api/wechat-official/content-library/export", headers=headers, json={"article_ids": [article_id], "format": "csv"})
        assert csv_export.status_code == 200
        assert csv_export.json()["file_name"].endswith(".csv")

        rss = client.get("/api/wechat-official/content-library/feed.rss?pool_status=shortlisted", headers=headers)
        assert rss.status_code == 200
        assert "application/rss+xml" in rss.headers["content-type"]
        assert "导出案例" in rss.text
        assert "https://mp.weixin.qq.com/s/export-target" in rss.text
        assert "私域增长" in rss.text
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_content_library_auto_refreshes_incomplete_articles_and_notifies(tmp_path, monkeypatch):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    monkeypatch.setattr(redfox_service, "WechatOfficialRedfoxClient", FakeRedfoxDetailClient, raising=False)
    try:
        headers = _register("content-library-auto-refresh-user")
        article_id = _create_article(headers, title="待自动补全", url="https://mp.weixin.qq.com/s/auto-refresh", read_count=0)
        admin_headers = _register_admin("content-library-auto-refresh-admin", TestingSessionLocal)
        config = client.post("/api/wechat-official/redfox/config", headers=admin_headers, json={"api_key": "refresh-secret"})
        assert config.status_code == 200

        response = client.post("/api/wechat-official/content-library/auto-refresh", headers=headers, json={"article_ids": [article_id]})
        assert response.status_code == 200
        assert response.json()["refreshed_count"] == 1
        assert response.json()["failed_count"] == 0

        with TestingSessionLocal() as db:
            assert db.scalar(select(WechatOfficialArticleSnapshot).where(WechatOfficialArticleSnapshot.article_id == article_id)) is not None
            notification = db.scalar(select(Notification).where(Notification.source_type == "wechat_official_content_auto_refresh"))
            assert notification is not None
            assert notification.user_id == 1
            assert notification.level == "info"
            assert "已自动补全" in notification.title
    finally:
        app.dependency_overrides.pop(get_db, None)


class FakeRedfoxDetailClient:
    def __init__(self, *, base_url: str, api_key: str) -> None:
        assert api_key == "refresh-secret"

    def query_article_detail(self, *, url: str) -> dict:
        return {
            "code": 2000,
            "data": {
                "workUuid": "refresh-work-1",
                "title": "补全后标题",
                "summary": "补全摘要",
                "workUrl": url,
                "author": "补全公众号",
                "coverUrl": "https://example.com/refresh-cover.jpg",
                "content": "补全后的正文内容",
                "html": '<p>补全后的正文内容</p><img src="https://example.com/refresh-html.jpg" />',
                "contentImages": ["https://example.com/refresh-body.jpg"],
                "comments": [
                    {
                        "commentId": "refresh-c1",
                        "nickName": "读者",
                        "content": "补全评论",
                        "likeCount": 7,
                        "replies": [{"replyId": "reply-1", "nickName": "作者", "content": "谢谢", "likeCount": 2}],
                    }
                ],
                "readCount": 88888,
                "commentCount": 1,
                "api_key": "refresh-leak",
            },
        }


class FakeRedfoxNoCoverDetailClient:
    def __init__(self, *, base_url: str, api_key: str) -> None:
        assert api_key == "refresh-secret"

    def query_article_detail(self, *, url: str) -> dict:
        return {
            "code": 2000,
            "data": {
                "workUuid": "refresh-no-cover-1",
                "title": "无封面补全标题",
                "summary": "无封面补全摘要",
                "workUrl": url,
                "author": "补全公众号",
                "content": "无封面时正文内容",
                "html": '<p>无封面时正文内容</p><img src="https://example.com/no-cover-html.jpg" />',
                "contentImages": ["https://example.com/no-cover-body.jpg"],
                "readCount": 77777,
            },
        }


def test_content_library_delete_removes_article_descendants_and_blocks_resave(tmp_path, monkeypatch):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    monkeypatch.setattr(redfox_service, "WechatOfficialRedfoxClient", FakeRedfoxDetailClient, raising=False)
    try:
        headers = _register("delete-owner")
        article_id = _create_article(headers, title="删除案例", url="https://mp.weixin.qq.com/s/delete-target", read_count=120000)
        admin_headers = _register_admin("delete-redfox-admin", TestingSessionLocal)
        config = client.post("/api/wechat-official/redfox/config", headers=admin_headers, json={"api_key": "refresh-secret"})
        assert config.status_code == 200
        refreshed = client.post(f"/api/wechat-official/content-library/{article_id}/refresh-detail", headers=headers)
        assert refreshed.status_code == 200

        with TestingSessionLocal() as db:
            article = db.get(WechatOfficialArticle, article_id)
            assert article is not None
            account = db.get(WechatOfficialCrawlAccount, article.account_id)
            assert account is not None
            owner_user_id = account.user_id
            assert db.scalar(select(WechatOfficialArticleSnapshot).where(WechatOfficialArticleSnapshot.article_id == article_id)) is not None
            assert db.scalar(select(WechatOfficialArticleComment).where(WechatOfficialArticleComment.article_id == article_id)) is not None
            assert db.scalar(
                select(WechatOfficialArticleCommentReply)
                .join(WechatOfficialArticleComment, WechatOfficialArticleCommentReply.comment_id == WechatOfficialArticleComment.id)
                .where(WechatOfficialArticleComment.article_id == article_id)
            ) is not None

        deleted = client.delete(f"/api/wechat-official/content-library/{article_id}", headers=headers)
        assert deleted.status_code == 200
        assert deleted.json() == {"id": article_id, "status": "deleted"}

        detail = client.get(f"/api/wechat-official/content-library/{article_id}", headers=headers)
        assert detail.status_code == 404

        with TestingSessionLocal() as db:
            assert db.get(WechatOfficialArticle, article_id) is None
            assert db.scalar(select(WechatOfficialArticleMetric).where(WechatOfficialArticleMetric.article_id == article_id)) is None
            assert db.scalar(select(WechatOfficialArticleSnapshot).where(WechatOfficialArticleSnapshot.article_id == article_id)) is None
            assert db.scalar(select(WechatOfficialArticleComment).where(WechatOfficialArticleComment.article_id == article_id)) is None
            assert db.scalars(
                select(WechatOfficialArticleCommentReply)
                .join(WechatOfficialArticleComment, WechatOfficialArticleCommentReply.comment_id == WechatOfficialArticleComment.id)
                .where(WechatOfficialArticleComment.article_id == article_id)
            ).all() == []
            assert db.scalar(select(WechatOfficialArticleCommentReply).where(WechatOfficialArticleCommentReply.reply_id == "reply-1")) is None
            tombstone_model = db.get_bind().metadata.tables.get("wechat_official_content_library_tombstones")
            assert tombstone_model is not None
            assert (
                db.execute(
                    select(tombstone_model).where(
                        tombstone_model.c.user_id == owner_user_id,
                        tombstone_model.c.article_url == "https://mp.weixin.qq.com/s/delete-target",
                    )
                ).first()
                is not None
            )

        with TestingSessionLocal() as db:
            tombstone_model = db.get_bind().metadata.tables.get("wechat_official_content_library_tombstones")
            assert tombstone_model is not None
            tombstones = WechatOfficialContentTombstoneService(db)
            tombstones.tombstone(owner_user_id, "https://mp.weixin.qq.com/s/duplicate-delete-target", "重复删除标题")
            tombstones.tombstone(owner_user_id, "https://mp.weixin.qq.com/s/duplicate-delete-target", "重复删除标题 2")
            db.commit()
            repeated_rows = db.execute(
                select(tombstone_model).where(
                    tombstone_model.c.user_id == owner_user_id,
                    tombstone_model.c.article_url == "https://mp.weixin.qq.com/s/duplicate-delete-target",
                )
            ).all()
            assert len(repeated_rows) == 1
            assert repeated_rows[0]._mapping["article_title"] == "重复删除标题 2"

        session_id = _create_session(headers)
        relaunch = client.post(
            "/api/wechat-official/crawl/articles/sync",
            headers=headers,
            json={
                "backend_session_id": session_id,
                "upstream_payload": {
                    "publish_page": '{"publish_list":[{"publish_info":{"appmsgex":[{"title":"删除案例","digest":"摘要删除案例","link":"https://mp.weixin.qq.com/s/delete-target"}]}}]}'
                },
            },
        )
        assert relaunch.status_code == 200
        assert relaunch.json()["items"] == []
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


def test_refresh_detail_enriches_existing_article_without_auto_refreshing_get(tmp_path, monkeypatch):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    monkeypatch.setattr(redfox_service, "WechatOfficialRedfoxClient", FakeRedfoxDetailClient, raising=False)
    try:
        headers = _register("refresh-detail-owner")
        article_id = _create_article(headers, title="待补全文章", url="https://mp.weixin.qq.com/s/refresh-detail", read_count=0)
        admin_headers = _register_admin("refresh-detail-redfox-admin", TestingSessionLocal)
        config = client.post("/api/wechat-official/redfox/config", headers=admin_headers, json={"api_key": "refresh-secret"})
        assert config.status_code == 200

        before = client.get(f"/api/wechat-official/content-library/{article_id}", headers=headers)
        assert before.status_code == 200
        assert before.json()["latest_snapshot"] is None
        assert before.json()["detail_status"]["has_snapshot"] is False

        response = client.post(f"/api/wechat-official/content-library/{article_id}/refresh-detail", headers=headers)
        assert response.status_code == 200
        payload = response.json()
        assert payload["article"]["title"] == "补全后标题"
        assert payload["latest_snapshot"]["text"] == "补全后的正文内容"
        assert {image["url"] for image in payload["images"]} >= {"https://example.com/refresh-cover.jpg", "https://example.com/refresh-html.jpg", "https://example.com/refresh-body.jpg"}
        assert payload["comments"]["total"] == 1
        assert payload["comments"]["items"][0]["content"] == "补全评论"
        assert "refresh-leak" not in response.text

        after = client.get(f"/api/wechat-official/content-library/{article_id}", headers=headers)
        assert after.status_code == 200
        assert after.json()["detail_status"]["has_snapshot"] is True
        assert after.json()["comments"]["total"] == 1

        duplicate = client.post(f"/api/wechat-official/content-library/{article_id}/refresh-detail", headers=headers)
        assert duplicate.status_code == 200
        assert duplicate.json()["comments"]["total"] == 1

        other_headers = _register("refresh-detail-other")
        other = client.post(f"/api/wechat-official/content-library/{article_id}/refresh-detail", headers=other_headers)
        assert other.status_code == 404

        with TestingSessionLocal() as db:
            article = db.get(WechatOfficialArticle, article_id)
            assert article is not None
            assert article.title == "补全后标题"
            assert len(db.scalars(select(WechatOfficialArticleSnapshot).where(WechatOfficialArticleSnapshot.article_id == article_id)).all()) == 2
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_refresh_detail_requires_redfox_config_but_plain_detail_still_works(tmp_path):
    get_db, _ = _override_database(tmp_path)
    try:
        headers = _register("refresh-no-config-owner")
        article_id = _create_article(headers, title="无配置文章", url="https://mp.weixin.qq.com/s/no-config", read_count=0)

        detail = client.get(f"/api/wechat-official/content-library/{article_id}", headers=headers)
        assert detail.status_code == 200

        refresh = client.post(f"/api/wechat-official/content-library/{article_id}/refresh-detail", headers=headers)
        assert refresh.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_refresh_detail_uses_first_detail_image_as_cover_when_redfox_has_no_cover(tmp_path, monkeypatch):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    monkeypatch.setattr(redfox_service, "WechatOfficialRedfoxClient", FakeRedfoxNoCoverDetailClient, raising=False)
    try:
        headers = _register("refresh-no-cover-owner")
        article_id = _create_article(headers, title="无封面文章", url="https://mp.weixin.qq.com/s/no-cover", read_count=0)
        admin_headers = _register_admin("refresh-no-cover-redfox-admin", TestingSessionLocal)
        config = client.post("/api/wechat-official/redfox/config", headers=admin_headers, json={"api_key": "refresh-secret"})
        assert config.status_code == 200

        response = client.post(f"/api/wechat-official/content-library/{article_id}/refresh-detail", headers=headers)

        assert response.status_code == 200
        payload = response.json()
        assert payload["article"]["cover_url"] == "https://example.com/no-cover-html.jpg"
        assert payload["detail_status"]["has_cover"] is True
        assert payload["images"][0]["url"] == "https://example.com/no-cover-html.jpg"
        with TestingSessionLocal() as db:
            article = db.get(WechatOfficialArticle, article_id)
            assert article is not None
            assert article.cover_url == "https://example.com/no-cover-html.jpg"
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
            config = ModelConfig(user_id=account.user_id, name="Fake Text", model_type="text", provider="openai", model_name="fake", base_url="https://example.test", encrypted_api_key=encrypt_text("fake-key"), is_default=True)
            bind_test_model_capability(db, config=config, capability="text")
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

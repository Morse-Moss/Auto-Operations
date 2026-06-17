from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.main import app
from backend.app.models import WechatOfficialArticle, WechatOfficialArticleSnapshot, WechatOfficialCrawlAccount, WechatOfficialCrawlJob

client = TestClient(app)


def _override_database(tmp_path):
    from backend.app.core.database import Base, get_db

    engine = create_engine(f"sqlite:///{tmp_path / 'wechat-official-crawl-test.db'}", connect_args={"check_same_thread": False})
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


def _create_backend_session(headers: dict) -> int:
    start_response = client.post("/api/wechat-official/accounts/login/qrcode", headers=headers)
    assert start_response.status_code == 200
    login_session_id = start_response.json()["login_session_id"]
    complete_response = client.post(
        f"/api/wechat-official/accounts/login/{login_session_id}/complete",
        headers=headers,
        json={"cookie": "cookie-secret", "token": "token-secret", "auth_key": "auth-secret", "biz": "MzA-session", "nickname": "Session Account"},
    )
    assert complete_response.status_code == 200
    assert complete_response.json()["status"] == "valid"
    return login_session_id


def test_search_accounts_normalizes_searchbiz_payload_and_upserts_accounts(tmp_path):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        headers = _register("crawl-search-user")
        backend_session_id = _create_backend_session(headers)

        response = client.post(
            "/api/wechat-official/crawl/accounts/search",
            headers=headers,
            json={
                "backend_session_id": backend_session_id,
                "keyword": "AI增长",
                "upstream_payload": {
                    "list": [
                        {
                            "fakeid": "fakeid-001",
                            "nickname": "增长研究所",
                            "alias": "growth_lab",
                            "round_head_img": "https://img.example/avatar.png",
                            "signature": "研究增长",
                            "service_type": 1,
                        }
                    ]
                },
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 1
        assert payload["items"][0]["fake_id"] == "fakeid-001"
        assert payload["items"][0]["name"] == "增长研究所"
        assert payload["items"][0]["alias"] == "growth_lab"
        assert payload["items"][0]["raw"]["signature"] == "研究增长"

        repeat = client.post(
            "/api/wechat-official/crawl/accounts/search",
            headers=headers,
            json={
                "backend_session_id": backend_session_id,
                "keyword": "AI增长",
                "upstream_payload": {"list": [{"fakeid": "fakeid-001", "nickname": "增长研究所新版", "alias": "growth_lab"}]},
            },
        )
        assert repeat.status_code == 200
        assert repeat.json()["items"][0]["name"] == "增长研究所新版"

        with TestingSessionLocal() as db:
            accounts = db.scalars(select(WechatOfficialCrawlAccount).where(WechatOfficialCrawlAccount.fake_id == "fakeid-001")).all()
            assert len(accounts) == 1
            assert accounts[0].user_id == 1
            assert accounts[0].name == "增长研究所新版"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_articles_sync_parses_appmsgpublish_payload_and_creates_job_and_articles(tmp_path):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        headers = _register("crawl-article-user")
        backend_session_id = _create_backend_session(headers)
        search_response = client.post(
            "/api/wechat-official/crawl/accounts/search",
            headers=headers,
            json={"backend_session_id": backend_session_id, "keyword": "AI", "upstream_payload": {"list": [{"fakeid": "fakeid-article", "nickname": "Article Account"}]}},
        )
        account_id = search_response.json()["items"][0]["id"]

        response = client.post(
            "/api/wechat-official/crawl/articles/sync",
            headers=headers,
            json={
                "backend_session_id": backend_session_id,
                "account_id": account_id,
                "limit": 10,
                "upstream_payload": {
                    "publish_page": '{"publish_list":[{"publish_info":{"appmsgex":[{"aid":"2247481_1","title":"爆款文章","digest":"摘要","link":"https://mp.weixin.qq.com/s/article-1","cover":"https://img.example/cover.jpg","update_time":1780000000}]}}]}'
                },
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["job"]["status"] == "succeeded"
        assert payload["job"]["saved_count"] == 1
        assert payload["items"][0]["title"] == "爆款文章"
        assert payload["items"][0]["article_url"] == "https://mp.weixin.qq.com/s/article-1"
        assert payload["items"][0]["digest"] == "摘要"

        with TestingSessionLocal() as db:
            job = db.scalar(select(WechatOfficialCrawlJob))
            article = db.scalar(select(WechatOfficialArticle))
            assert job is not None
            assert article is not None
            assert article.job_id == job.id
            assert article.account_id == account_id
            assert article.raw_json["aid"] == "2247481_1"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_article_snapshot_stores_html_text_status_and_comment_id(tmp_path):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        headers = _register("crawl-snapshot-user")
        backend_session_id = _create_backend_session(headers)
        sync_response = client.post(
            "/api/wechat-official/crawl/articles/sync",
            headers=headers,
            json={
                "backend_session_id": backend_session_id,
                "limit": 1,
                "upstream_payload": {"publish_page": '{"publish_list":[{"publish_info":{"appmsgex":[{"title":"快照文章","link":"https://mp.weixin.qq.com/s/snapshot"}]}}]}'},
            },
        )
        article_id = sync_response.json()["items"][0]["id"]
        html = """
        <html><body><div id="js_article"><h1>快照文章</h1><div id="js_content">这里是正文内容</div></div>
        <script>var comment_id = \"comment-123\";</script></body></html>
        """

        response = client.post(
            f"/api/wechat-official/crawl/articles/{article_id}/snapshot",
            headers=headers,
            json={"html": html},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["comment_id"] == "comment-123"
        assert "这里是正文内容" in payload["text"]

        deleted_response = client.post(
            f"/api/wechat-official/crawl/articles/{article_id}/snapshot",
            headers=headers,
            json={"html": "该内容已被发布者删除"},
        )
        assert deleted_response.status_code == 200
        assert deleted_response.json()["status"] == "deleted"

        with TestingSessionLocal() as db:
            snapshots = db.scalars(select(WechatOfficialArticleSnapshot).where(WechatOfficialArticleSnapshot.article_id == article_id)).all()
            assert len(snapshots) == 2
            assert snapshots[0].html == html
            assert snapshots[0].raw_json["comment_id"] == "comment-123"
    finally:
        app.dependency_overrides.pop(get_db, None)

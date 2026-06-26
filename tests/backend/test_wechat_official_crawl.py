from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.main import app
from backend.app.models import WechatOfficialArticle, WechatOfficialArticleSnapshot, WechatOfficialCrawlAccount, WechatOfficialCrawlJob
from backend.app.services import wechat_official_crawl_service as crawl_service

client = TestClient(app)


class FakeHistoryMaterializeArticlePageProvider:
    def fetch_article(self, *, url: str) -> dict:
        assert url == "https://mp.weixin.qq.com/s/provider-history-1"
        return {
            "external_id": "article_page:provider-history-1",
            "article_url": url,
            "content_url": url,
            "title": "Provider 历史文章",
            "digest": "公开页历史摘要",
            "author_name": "Provider 作者",
            "account_name": "Provider 公众号",
            "account": "provider-fakeid-001",
            "publish_time_remote": "1710000000",
            "cover_url": "https://img.example/provider-materialized-cover.jpg",
            "content_text": "Provider 历史文章公开页正文",
            "content_html": '<div id="js_content"><p>Provider 历史文章公开页正文</p></div>',
            "images": [{"url": "https://img.example/provider-materialized-cover.jpg", "type": "cover", "source": "article_page"}],
            "raw": {"source": "article_page"},
        }


class FakeBackendProvider:
    def __init__(self, *, transport=None) -> None:
        self.transport = transport

    def search_accounts(self, keyword: str, cookie: str, token: str, user_agent: str) -> list[dict]:
        assert keyword == "真实搜索"
        assert cookie == "cookie-secret"
        assert token == "token-secret"
        return [
            {
                "fake_id": "provider-fakeid-001",
                "name": "Provider 公众号",
                "alias": "provider_alias",
                "avatar_url": "https://img.example/provider-avatar.jpg",
                "raw": {"from": "provider"},
            }
        ]

    def sync_account_articles(self, fake_id: str, cookie: str, token: str, user_agent: str, begin: int = 0, count: int = 5) -> list[dict]:
        assert fake_id == "provider-fakeid-001"
        assert cookie == "cookie-secret"
        assert token == "token-secret"
        assert begin == 0
        assert count == 2
        return [
            {
                "article_url": "https://mp.weixin.qq.com/s/provider-history-1",
                "title": "Provider 历史文章",
                "digest": "Provider 摘要",
                "author_name": "Provider 作者",
                "cover_url": "https://img.example/provider-cover.jpg",
                "publish_time_remote": "1710000000",
                "raw": {"aid": "provider-aid-1"},
            }
        ]


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


def test_search_accounts_uses_backend_provider_when_upstream_payload_missing(tmp_path, monkeypatch):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    monkeypatch.setattr(crawl_service, "WechatOfficialBackendProvider", FakeBackendProvider, raising=False)
    try:
        headers = _register("crawl-provider-search-user")
        backend_session_id = _create_backend_session(headers)

        response = client.post(
            "/api/wechat-official/crawl/accounts/search",
            headers=headers,
            json={"backend_session_id": backend_session_id, "keyword": "真实搜索"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 1
        assert payload["items"][0]["fake_id"] == "provider-fakeid-001"
        assert payload["items"][0]["name"] == "Provider 公众号"
        assert payload["items"][0]["alias"] == "provider_alias"

        with TestingSessionLocal() as db:
            account = db.scalar(select(WechatOfficialCrawlAccount).where(WechatOfficialCrawlAccount.fake_id == "provider-fakeid-001"))
            assert account is not None
            assert account.name == "Provider 公众号"
            assert account.raw_json["raw"] == {"from": "provider"}
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_articles_sync_uses_backend_provider_when_upstream_payload_missing(tmp_path, monkeypatch):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    monkeypatch.setattr(crawl_service, "WechatOfficialBackendProvider", FakeBackendProvider, raising=False)
    monkeypatch.setattr(crawl_service, "WechatOfficialArticlePageProvider", FakeHistoryMaterializeArticlePageProvider, raising=False)
    try:
        headers = _register("crawl-provider-article-user")
        backend_session_id = _create_backend_session(headers)
        search_response = client.post(
            "/api/wechat-official/crawl/accounts/search",
            headers=headers,
            json={"backend_session_id": backend_session_id, "keyword": "真实搜索"},
        )
        account_id = search_response.json()["items"][0]["id"]

        response = client.post(
            "/api/wechat-official/crawl/articles/sync",
            headers=headers,
            json={"backend_session_id": backend_session_id, "account_id": account_id, "limit": 2},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["job"]["source"] == "backend"
        assert payload["job"]["requested_limit"] == 2
        assert payload["job"]["saved_count"] == 1
        assert payload["items"][0]["title"] == "Provider 历史文章"
        assert payload["items"][0]["article_url"] == "https://mp.weixin.qq.com/s/provider-history-1"

        with TestingSessionLocal() as db:
            job = db.scalar(select(WechatOfficialCrawlJob).order_by(WechatOfficialCrawlJob.id.desc()))
            assert job is not None
            assert job.params_json["backend_session_id"] == backend_session_id
            assert "cookie-secret" not in str(job.params_json)
            assert "token-secret" not in str(job.params_json)
            article = db.scalar(select(WechatOfficialArticle).where(WechatOfficialArticle.article_url == "https://mp.weixin.qq.com/s/provider-history-1"))
            assert article is not None
            assert article.account_id == account_id
            assert article.cover_url == "https://img.example/provider-materialized-cover.jpg"
            assert article.raw_json["raw"] == {"aid": "provider-aid-1"}
            assert article.raw_json["article_page_materialized"]["source"] == "article_page"
            snapshot = db.scalar(select(WechatOfficialArticleSnapshot).where(WechatOfficialArticleSnapshot.article_id == article.id))
            assert snapshot is not None
            assert snapshot.text == "Provider 历史文章公开页正文"
            assert snapshot.images_json == [{"url": "https://img.example/provider-materialized-cover.jpg", "type": "cover", "source": "article_page"}]
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

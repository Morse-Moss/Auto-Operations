from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.main import app
from test_support.beta_invites import create_test_invite_code
from backend.app.models import WechatOfficialArticle, WechatOfficialArticleSnapshot, WechatOfficialCrawlJob, WechatOfficialRedfoxConfig

client = TestClient(app)


class FakeArticlePageProvider:
    def fetch_article(self, *, url: str) -> dict:
        assert url == "https://mp.weixin.qq.com/s/direct-import-url"
        return {
            "external_id": "article_page:direct-import-url",
            "article_url": url,
            "content_url": url,
            "title": "公开页直接导入标题",
            "digest": "公开页摘要",
            "author_name": "公开页公众号",
            "account_name": "公开页公众号",
            "account": "公开页公众号",
            "publish_time_remote": "2026-06-25 09:30",
            "cover_url": "https://mmbiz.qpic.cn/direct-cover.jpg",
            "content_text": "公开页直接导入正文",
            "content_html": '<div id="js_content"><p>公开页直接导入正文</p></div>',
            "images": [{"url": "https://mmbiz.qpic.cn/direct-cover.jpg", "type": "cover", "source": "article_page"}],
            "comments": [],
            "detail_completeness": {"has_text": True, "has_html": True, "image_count": 1},
            "metrics": {"read_count": 0, "like_count": 0, "wow_count": 0, "share_count": 0, "comment_count": 0},
            "raw": {"source": "article_page"},
        }


def _override_database(tmp_path):
    from backend.app.core.database import Base, get_db

    engine = create_engine(f"sqlite:///{tmp_path / 'wechat-official-article-import-test.db'}", connect_args={"check_same_thread": False})
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


def test_article_import_url_uses_public_article_page_without_redfox_config(tmp_path, monkeypatch):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        headers = _register("article-import-direct-user")
        monkeypatch.setattr("backend.app.services.wechat_official_article_import_service.WechatOfficialArticlePageProvider", FakeArticlePageProvider)

        response = client.post(
            "/api/wechat-official/articles/import-url",
            headers=headers,
            json={"url": "https://mp.weixin.qq.com/s/direct-import-url", "save_snapshot": True},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["summary"]["saved"] == 1
        assert payload["summary"]["provider"] == "article_page"
        assert payload["job"]["source"] == "article_page"
        assert payload["job"]["params"]["source"] == "article_page_url"
        assert payload["items"][0]["title"] == "公开页直接导入标题"
        assert payload["items"][0]["article_url"] == "https://mp.weixin.qq.com/s/direct-import-url"

        with TestingSessionLocal() as db:
            assert db.scalar(select(WechatOfficialRedfoxConfig)) is None
            job = db.scalar(select(WechatOfficialCrawlJob))
            assert job is not None
            assert job.source == "article_page"
            assert job.keyword == "https://mp.weixin.qq.com/s/direct-import-url"
            article = db.scalar(select(WechatOfficialArticle).where(WechatOfficialArticle.article_url == "https://mp.weixin.qq.com/s/direct-import-url"))
            assert article is not None
            assert article.source == "article_page"
            snapshot = db.scalar(select(WechatOfficialArticleSnapshot).where(WechatOfficialArticleSnapshot.article_id == article.id))
            assert snapshot is not None
            assert snapshot.text == "公开页直接导入正文"
            assert snapshot.raw_json["source"] == "article_page"
    finally:
        app.dependency_overrides.pop(get_db, None)

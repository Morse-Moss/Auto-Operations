from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.main import app
from backend.app.models import AiDraft, PublishJob, WechatOfficialArticle, WechatOfficialArticleMetric, WechatOfficialArticleSnapshot, WechatOfficialCrawlJob, WechatOfficialDraftSource
from backend.app.services import wechat_official_redfox_service as redfox_service

client = TestClient(app)


class FakeRedfoxClient:
    def __init__(self, *, base_url: str, api_key: str) -> None:
        self.base_url = base_url
        self.api_key = api_key
        assert api_key == "redfox-collect-secret"

    def search_articles(self, *, keyword: str, offset: int, sort_type: str) -> dict:
        assert keyword == "私域增长"
        assert offset == 0
        assert sort_type == "_4"
        return {
            "code": 2000,
            "data": {
                "list": [
                    {
                        "workUuid": "viral-work-1",
                        "title": "10万+私域案例",
                        "summary": "私域增长摘要",
                        "workUrl": "https://mp.weixin.qq.com/s/redfox-viral",
                        "publishTime": "2026-06-16 10:00:00",
                        "author": "增长研究所",
                        "coverUrl": "https://example.com/cover.jpg",
                        "content": "正文：可复制的私域增长路径。",
                        "readCount": 120000,
                        "likeCount": 3500,
                        "watchCount": 1200,
                        "commentCount": 280,
                        "shareCount": 150,
                    },
                    {
                        "workUuid": "normal-work-1",
                        "title": "普通私域案例",
                        "summary": "普通摘要",
                        "workUrl": "https://mp.weixin.qq.com/s/redfox-normal",
                        "publishTime": "2026-06-16 11:00:00",
                        "author": "增长研究所",
                        "content": "正文：普通文章。",
                        "readCount": 50000,
                        "likeCount": 30,
                    },
                ]
            },
        }

    def query_work_list(self, *, account: str, account_name: str, offset: int, sort_type: str, publish_time_start: str | None, publish_time_end: str | None) -> dict:
        assert account == "rmrbwx"
        return {
            "code": 2000,
            "data": {
                "list": [
                    {
                        "workUuid": "account-work-1",
                        "title": "公众号热文",
                        "summary": "公众号热文摘要",
                        "workUrl": "https://mp.weixin.qq.com/s/redfox-account-viral",
                        "author": account_name,
                        "readCount": 150000,
                    }
                ]
            },
        }

    def query_article_detail(self, *, url: str) -> dict:
        assert url == "https://mp.weixin.qq.com/s/redfox-url"
        return {
            "code": 2000,
            "data": {
                "workUuid": "url-work-1",
                "title": "URL补全爆文",
                "summary": "URL补全摘要",
                "workUrl": url,
                "author": "URL公众号",
                "content": "URL 详情正文。",
                "readCount": 130000,
                "shareCount": 66,
            },
        }

    def validate_key(self) -> dict:
        return {"code": 2000, "data": {"ok": True}}


def _override_database(tmp_path):
    from backend.app.core.database import Base, get_db

    engine = create_engine(f"sqlite:///{tmp_path / 'wechat-official-redfox-collect-test.db'}", connect_args={"check_same_thread": False})
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


def _save_config(headers: dict) -> None:
    response = client.post("/api/wechat-official/redfox/config", headers=headers, json={"api_key": "redfox-collect-secret"})
    assert response.status_code == 200


def test_redfox_keyword_collect_saves_articles_metrics_snapshots_and_candidates(tmp_path, monkeypatch):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    monkeypatch.setattr(redfox_service, "WechatOfficialRedfoxClient", FakeRedfoxClient, raising=False)
    try:
        headers = _register("redfox-keyword-user")
        _save_config(headers)

        response = client.post(
            "/api/wechat-official/redfox/collect/articles",
            headers=headers,
            json={"keyword": "私域增长", "pages": 1, "sort_type": "_4", "min_read_count": 100000, "save_snapshot": True},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["summary"] == {"fetched": 2, "saved": 2, "deduped": 0, "viral_candidates": 1, "failed": 0, "api_calls": 1, "estimated_credit_cost": None}
        assert len(payload["items"]) == 2
        viral = next(item for item in payload["items"] if item["title"] == "10万+私域案例")
        normal = next(item for item in payload["items"] if item["title"] == "普通私域案例")
        assert viral["is_candidate"] is True
        assert viral["latest_metric"]["read_count"] == 120000
        assert viral["analysis"]["recommendation_status"] == "candidate"
        assert viral["analysis"]["low_follower_evidence"] == "unknown"
        assert normal["is_candidate"] is False

        library = client.get("/api/wechat-official/content-library?viral_only=true&min_read_count=100000", headers=headers)
        assert library.status_code == 200
        assert library.json()["total"] == 1
        assert library.json()["items"][0]["title"] == "10万+私域案例"

        unknown_library = client.get("/api/wechat-official/content-library?low_follower_evidence=unknown", headers=headers)
        assert unknown_library.status_code == 200
        assert unknown_library.json()["total"] == 2

        draft_response = client.post(
            f"/api/wechat-official/content-library/{viral['id']}/create-draft",
            headers=headers,
            json={"rewrite_style": "专业克制", "target_audience": "私域运营", "call_to_action": "预约咨询"},
        )
        assert draft_response.status_code == 200
        draft_payload = draft_response.json()
        assert draft_payload["platform"] == "wechat_official"
        assert "正文：可复制的私域增长路径" in draft_payload["body"]

        dry_run = client.post(f"/api/wechat-official/drafts/{draft_payload['id']}/dry-run", headers=headers)
        assert dry_run.status_code == 200
        assert dry_run.json()["publish_blocked"] is True
        assert dry_run.json()["sendall_blocked"] is True

        send_to_publish = client.post(f"/api/drafts/{draft_payload['id']}/send-to-publish", headers=headers, json={"publish_mode": "immediate"})
        assert send_to_publish.status_code in {400, 403, 422}

        with TestingSessionLocal() as db:
            job = db.scalar(select(WechatOfficialCrawlJob))
            assert job is not None
            assert job.source == "redfox"
            serialized_job = str(job.params_json) + job.error_message
            assert "redfox-collect-secret" not in serialized_job
            assert db.scalars(select(WechatOfficialArticle)).all()
            assert len(db.scalars(select(WechatOfficialArticleMetric)).all()) == 2
            assert len(db.scalars(select(WechatOfficialArticleSnapshot)).all()) == 2
            draft = db.get(AiDraft, draft_payload["id"])
            assert draft is not None
            assert draft.platform == "wechat_official"
            source = db.scalar(select(WechatOfficialDraftSource).where(WechatOfficialDraftSource.draft_id == draft_payload["id"]))
            assert source is not None
            assert db.scalar(select(PublishJob).where(PublishJob.source_draft_id == draft_payload["id"])) is None
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_redfox_account_collect_and_url_import_use_same_library_path(tmp_path, monkeypatch):
    get_db, _ = _override_database(tmp_path)
    monkeypatch.setattr(redfox_service, "WechatOfficialRedfoxClient", FakeRedfoxClient, raising=False)
    try:
        headers = _register("redfox-account-url-user")
        _save_config(headers)

        account_response = client.post(
            "/api/wechat-official/redfox/collect/account",
            headers=headers,
            json={"account": "rmrbwx", "account_name": "人民日报", "pages": 1, "sort_type": "_4", "min_read_count": 100000},
        )
        assert account_response.status_code == 200
        assert account_response.json()["summary"]["viral_candidates"] == 1

        url_response = client.post(
            "/api/wechat-official/redfox/import-url",
            headers=headers,
            json={"url": "https://mp.weixin.qq.com/s/redfox-url", "min_read_count": 100000},
        )
        assert url_response.status_code == 200
        assert url_response.json()["summary"]["viral_candidates"] == 1

        library = client.get("/api/wechat-official/content-library?viral_only=true", headers=headers)
        assert library.status_code == 200
        titles = {item["title"] for item in library.json()["items"]}
        assert {"公众号热文", "URL补全爆文"}.issubset(titles)
    finally:
        app.dependency_overrides.pop(get_db, None)

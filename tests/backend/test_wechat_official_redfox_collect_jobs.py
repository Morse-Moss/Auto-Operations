from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.main import app
from test_support.beta_invites import create_test_invite_code
from backend.app.models import WechatOfficialCrawlJob
from backend.app.services import wechat_official_redfox_service as redfox_service

client = TestClient(app)


class FakeRedfoxCollectJobsClient:
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
            "data": [
                {
                    "workUuid": "traceable-work-1",
                    "title": "10万+私域案例",
                    "summary": "私域增长摘要",
                    "workUrl": "https://mp.weixin.qq.com/s/traceable-1",
                    "publishTime": "2026-06-16 10:00:00",
                    "author": "增长研究所",
                    "coverUrl": "https://example.com/traceable-cover-1.jpg",
                    "readCount": 120000,
                    "likeCount": 3000,
                    "commentCount": 120,
                    "content": "正文：可复制的私域增长路径。",
                },
                {
                    "workUuid": "traceable-work-2",
                    "title": "普通私域案例",
                    "summary": "普通摘要",
                    "workUrl": "https://mp.weixin.qq.com/s/traceable-2",
                    "publishTime": "2026-06-16 11:00:00",
                    "author": "增长研究所",
                    "readCount": 80000,
                    "likeCount": 100,
                    "commentCount": 5,
                    "content": "正文：普通私域增长文章。",
                },
            ],
        }

    def query_work_list(self, **_: object) -> dict:
        raise AssertionError("query_work_list should not be called")

    def query_article_detail(self, **_: object) -> dict:
        raise AssertionError("query_article_detail should not be called")


def _override_database(tmp_path):
    from backend.app.core.database import Base, get_db

    engine = create_engine(f"sqlite:///{tmp_path / 'wechat-official-redfox-collect-jobs-test.db'}", connect_args={"check_same_thread": False})
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


def _save_config(headers: dict) -> None:
    response = client.post("/api/wechat-official/redfox/config", headers=headers, json={"api_key": "redfox-collect-secret"})
    assert response.status_code == 200


def _collect_keyword(headers: dict) -> dict:
    response = client.post(
        "/api/wechat-official/redfox/collect/articles",
        headers=headers,
        json={"keyword": "私域增长", "target_count": 2, "max_pages": 1, "sort_type": "_4", "min_read_count": 100000, "save_snapshot": True},
    )
    assert response.status_code == 200
    return response.json()


def test_redfox_collect_jobs_api_lists_owned_collection_jobs_with_traceable_params(tmp_path, monkeypatch):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    monkeypatch.setattr(redfox_service, "WechatOfficialRedfoxClient", FakeRedfoxCollectJobsClient, raising=False)
    try:
        headers = _register("redfox-jobs-owner")
        _save_config(headers)

        collect_payload = _collect_keyword(headers)
        job = collect_payload["job"]
        assert job["id"]
        assert job["source"] == "redfox"
        assert job["keyword"] == "私域增长"
        assert job["requested_limit"] == 2
        assert job["fetched_count"] == 2
        assert job["saved_count"] == 2
        assert job["params"]["source"] == "redfox_keyword"
        assert job["params"]["api_calls"] == 1
        assert job["params"]["target_count"] == 2
        assert "created_at" in job
        assert "started_at" in job
        assert "finished_at" in job

        jobs_response = client.get("/api/wechat-official/redfox/collect/jobs", headers=headers)
        assert jobs_response.status_code == 200
        jobs_payload = jobs_response.json()
        assert jobs_payload["total"] == 1
        assert jobs_payload["page"] == 1
        assert jobs_payload["page_size"] == 20
        assert jobs_payload["items"][0]["id"] == job["id"]
        assert jobs_payload["items"][0]["params"]["source"] == "redfox_keyword"

        detail = client.get(f"/api/wechat-official/redfox/collect/jobs/{job['id']}", headers=headers)
        assert detail.status_code == 200
        detail_payload = detail.json()
        assert detail_payload["job"]["id"] == job["id"]
        assert detail_payload["total"] == 2
        assert {item["job_id"] for item in detail_payload["items"]} == {job["id"]}

        with TestingSessionLocal() as db:
            stored_job = db.get(WechatOfficialCrawlJob, job["id"])
            assert stored_job is not None
            serialized_job = str(stored_job.params_json) + stored_job.error_message
            assert "redfox-collect-secret" not in serialized_job
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_redfox_collect_jobs_are_isolated_by_user(tmp_path, monkeypatch):
    get_db, _ = _override_database(tmp_path)
    monkeypatch.setattr(redfox_service, "WechatOfficialRedfoxClient", FakeRedfoxCollectJobsClient, raising=False)
    try:
        owner_headers = _register("redfox-jobs-owner-isolated")
        other_headers = _register("redfox-jobs-other-isolated")
        _save_config(owner_headers)

        collect_payload = _collect_keyword(owner_headers)
        job_id = collect_payload["job"]["id"]

        other_list = client.get("/api/wechat-official/redfox/collect/jobs", headers=other_headers)
        assert other_list.status_code == 200
        assert other_list.json()["total"] == 0
        assert other_list.json()["items"] == []

        other_detail = client.get(f"/api/wechat-official/redfox/collect/jobs/{job_id}", headers=other_headers)
        assert other_detail.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)

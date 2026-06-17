from __future__ import annotations

from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.main import app
from backend.app.models import WechatOfficialArticleMetric

client = TestClient(app)


def _override_database(tmp_path):
    from backend.app.core.database import Base, get_db

    engine = create_engine(f"sqlite:///{tmp_path / 'wechat-official-metrics-test.db'}", connect_args={"check_same_thread": False})
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
        json={"cookie": "cookie-secret", "token": "token-secret", "auth_key": "auth-secret", "biz": "MzA-metric", "nickname": "Metric Account"},
    )
    assert complete.status_code == 200
    return session_id


def _create_article(headers: dict) -> int:
    session_id = _create_session(headers)
    sync = client.post(
        "/api/wechat-official/crawl/articles/sync",
        headers=headers,
        json={
            "backend_session_id": session_id,
            "upstream_payload": {"publish_page": '{"publish_list":[{"publish_info":{"appmsgex":[{"title":"指标文章","link":"https://mp.weixin.qq.com/s/metrics"}]}}]}'},
        },
    )
    assert sync.status_code == 200
    return sync.json()["items"][0]["id"]


def _import_credential(headers: dict, **overrides) -> int:
    payload = {
        "biz": "MzA-metric",
        "uin": "123456",
        "key": "article-key-secret",
        "pass_ticket": "pass-ticket-secret",
        "wap_sid2": "wap-sid2-secret",
        "appmsg_token": "appmsg-token-secret",
        "cookie": "credential-cookie-secret",
        "timestamp": 1780000000,
        "nickname": "Metric Account",
        "captured_at": datetime.now().replace(microsecond=0).isoformat(),
    }
    payload.update(overrides)
    response = client.post("/api/wechat-official/credentials/import", headers=headers, json=payload)
    assert response.status_code == 200
    return response.json()["id"]


def test_article_metrics_parses_cgi_data_and_stores_snapshot_with_owned_credential(tmp_path):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        headers = _register("metrics-user")
        article_id = _create_article(headers)
        credential_id = _import_credential(headers)

        response = client.post(
            f"/api/wechat-official/crawl/articles/{article_id}/metrics",
            headers=headers,
            json={
                "credential_id": credential_id,
                "cgi_data": {"read_num": 120001, "old_like_count": 321, "share_count": 45, "like_count": 88, "comment_count": 6},
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["read_count"] == 120001
        assert payload["wow_count"] == 321
        assert payload["share_count"] == 45
        assert payload["like_count"] == 88
        assert payload["comment_count"] == 6

        with TestingSessionLocal() as db:
            metric = db.scalar(select(WechatOfficialArticleMetric).where(WechatOfficialArticleMetric.article_id == article_id))
            assert metric is not None
            assert metric.read_count == 120001
            assert metric.raw_json["source"] == "cgi_data"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_article_metrics_parses_window_cgi_data_new_from_html(tmp_path):
    get_db, _ = _override_database(tmp_path)
    try:
        headers = _register("metrics-html-user")
        article_id = _create_article(headers)
        credential_id = _import_credential(headers)
        html = '<script>window.cgiDataNew = {"appmsgstat": {"read_count": 100000, "like_count": 12, "old_like_count": 34, "share_count": 5, "comment_count": 2}}</script>'

        response = client.post(
            f"/api/wechat-official/crawl/articles/{article_id}/metrics",
            headers=headers,
            json={"credential_id": credential_id, "html": html},
        )

        assert response.status_code == 200
        assert response.json()["read_count"] == 100000
        assert response.json()["wow_count"] == 34
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_article_metrics_rejects_non_owner_or_expired_credential(tmp_path):
    get_db, _ = _override_database(tmp_path)
    try:
        owner_headers = _register("metrics-owner")
        other_headers = _register("metrics-other")
        article_id = _create_article(owner_headers)
        other_credential_id = _import_credential(other_headers)

        forbidden = client.post(
            f"/api/wechat-official/crawl/articles/{article_id}/metrics",
            headers=owner_headers,
            json={"credential_id": other_credential_id, "cgi_data": {"read_num": 1}},
        )
        assert forbidden.status_code == 404

        expired_id = _import_credential(
            owner_headers,
            biz="MzA-expired",
            nickname="Expired",
            captured_at=(datetime.now() - timedelta(hours=1)).replace(microsecond=0).isoformat(),
        )
        expired = client.post(
            f"/api/wechat-official/crawl/articles/{article_id}/metrics",
            headers=owner_headers,
            json={"credential_id": expired_id, "cgi_data": {"read_num": 1}},
        )
        assert expired.status_code == 400
        assert "valid" in expired.json()["detail"] or "expired" in expired.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_db, None)

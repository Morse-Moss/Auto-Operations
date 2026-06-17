from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.main import app
from backend.app.models import WechatOfficialProxyNode

client = TestClient(app)


def _override_database(tmp_path):
    from backend.app.core.database import Base, get_db

    engine = create_engine(f"sqlite:///{tmp_path / 'wechat-official-proxy-test.db'}", connect_args={"check_same_thread": False})
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


def test_proxy_list_seeds_direct_and_safe_public_reference_nodes_per_user(tmp_path):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        owner_headers = _register("proxy-owner")
        other_headers = _register("proxy-other")

        response = client.get("/api/wechat-official/proxies", headers=owner_headers)

        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 2
        names = {item["name"] for item in payload["items"]}
        assert names == {"Direct connection", "Public proxy reference"}
        direct = next(item for item in payload["items"] if item["type"] == "direct")
        public_ref = next(item for item in payload["items"] if item["type"] == "public_reference")
        assert direct["supports_sensitive_requests"] is True
        assert public_ref["supports_sensitive_requests"] is False
        assert public_ref["endpoint"] == "https://example.com/proxy-reference"
        assert "secret" not in str(payload).lower()
        assert "encrypted" not in str(payload).lower()

        other_response = client.get("/api/wechat-official/proxies", headers=other_headers)
        assert other_response.status_code == 200
        assert other_response.json()["total"] == 2

        with TestingSessionLocal() as db:
            assert len(db.scalars(select(WechatOfficialProxyNode)).all()) == 4
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_proxy_test_marks_success_failure_and_blocks_sensitive_public_proxy(tmp_path):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        headers = _register("proxy-test-user")
        list_response = client.get("/api/wechat-official/proxies", headers=headers)
        assert list_response.status_code == 200
        items = list_response.json()["items"]
        direct = next(item for item in items if item["type"] == "direct")
        public_ref = next(item for item in items if item["type"] == "public_reference")

        blocked_response = client.post(
            f"/api/wechat-official/proxies/{public_ref['id']}/test",
            headers=headers,
            json={"request_type": "sensitive", "success": True},
        )
        assert blocked_response.status_code == 400
        assert "sensitive" in blocked_response.json()["detail"]

        success_response = client.post(
            f"/api/wechat-official/proxies/{direct['id']}/test",
            headers=headers,
            json={"request_type": "sensitive", "success": True},
        )
        assert success_response.status_code == 200
        assert success_response.json()["status"] == "active"
        assert success_response.json()["last_error"] == ""

        failure_response = client.post(
            f"/api/wechat-official/proxies/{direct['id']}/test",
            headers=headers,
            json={"request_type": "public", "success": False, "error_message": "timeout"},
        )
        assert failure_response.status_code == 200
        assert failure_response.json()["status"] == "cooldown"
        assert failure_response.json()["last_error"] == "timeout"

        with TestingSessionLocal() as db:
            node = db.get(WechatOfficialProxyNode, direct["id"])
            assert node is not None
            assert node.status == "cooldown"
            assert node.last_error == "timeout"
            assert node.raw_json["failure_count"] == 1
    finally:
        app.dependency_overrides.pop(get_db, None)

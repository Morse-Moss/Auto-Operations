from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.core.security import decrypt_text
from backend.app.main import app
from backend.app.models import WechatOfficialRedfoxConfig
from backend.app.services import wechat_official_redfox_service as redfox_service

client = TestClient(app)


def _override_database(tmp_path):
    from backend.app.core.database import Base, get_db

    engine = create_engine(f"sqlite:///{tmp_path / 'wechat-official-redfox-config-test.db'}", connect_args={"check_same_thread": False})
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


def test_redfox_config_save_encrypts_api_key_and_response_is_sanitized(tmp_path):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        headers = _register("redfox-config-user")

        response = client.post(
            "/api/wechat-official/redfox/config",
            headers=headers,
            json={"name": "RedFoxHub", "base_url": "https://redfox.hk", "api_key": "redfox-secret-key"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["configured"] is True
        config_payload = payload["config"]
        assert config_payload["name"] == "RedFoxHub"
        assert config_payload["base_url"] == "https://redfox.hk"
        assert config_payload["has_api_key"] is True
        assert config_payload["masked_api_key"].endswith("-key")
        serialized = str(payload)
        assert "redfox-secret-key" not in serialized
        assert "encrypted_api_key" not in serialized

        with TestingSessionLocal() as db:
            config = db.scalar(select(WechatOfficialRedfoxConfig))
            assert config is not None
            assert config.encrypted_api_key != "redfox-secret-key"
            assert decrypt_text(config.encrypted_api_key) == "redfox-secret-key"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_redfox_config_update_without_api_key_preserves_existing_secret(tmp_path):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        headers = _register("redfox-config-update-user")
        created = client.post(
            "/api/wechat-official/redfox/config",
            headers=headers,
            json={"name": "RedFoxHub", "base_url": "https://redfox.hk", "api_key": "redfox-original-key"},
        )
        assert created.status_code == 200

        updated = client.post(
            "/api/wechat-official/redfox/config",
            headers=headers,
            json={"name": "RedFoxHub CN", "base_url": "https://redfox.hk"},
        )

        assert updated.status_code == 200
        payload = updated.json()["config"]
        assert payload["name"] == "RedFoxHub CN"
        assert payload["has_api_key"] is True
        assert "redfox-original-key" not in str(updated.json())

        with TestingSessionLocal() as db:
            config = db.scalar(select(WechatOfficialRedfoxConfig))
            assert config is not None
            assert decrypt_text(config.encrypted_api_key) == "redfox-original-key"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_redfox_config_is_scoped_to_current_user(tmp_path):
    get_db, _ = _override_database(tmp_path)
    try:
        owner_headers = _register("redfox-owner")
        other_headers = _register("redfox-other")
        response = client.post(
            "/api/wechat-official/redfox/config",
            headers=owner_headers,
            json={"api_key": "owner-redfox-key"},
        )
        assert response.status_code == 200

        owner_config = client.get("/api/wechat-official/redfox/config", headers=owner_headers)
        assert owner_config.status_code == 200
        assert owner_config.json()["configured"] is True

        other_config = client.get("/api/wechat-official/redfox/config", headers=other_headers)
        assert other_config.status_code == 200
        assert other_config.json()["configured"] is False
        assert "owner-redfox-key" not in str(other_config.json())
    finally:
        app.dependency_overrides.pop(get_db, None)


class FakeValidRedfoxClient:
    called = False

    def __init__(self, *, base_url: str, api_key: str) -> None:
        assert base_url == "https://redfox.hk"
        assert api_key == "redfox-valid-key"

    def validate_key(self) -> dict:
        FakeValidRedfoxClient.called = True
        return {"code": 2000, "data": {"list": []}}


class FakeInvalidRedfoxClient:
    called = False

    def __init__(self, *, base_url: str, api_key: str) -> None:
        assert base_url == "https://redfox.hk"
        assert api_key == "redfox-invalid-key"

    def validate_key(self) -> dict:
        FakeInvalidRedfoxClient.called = True
        raise redfox_service.RedfoxApiError("invalid key")


def test_redfox_config_rejects_untrusted_base_url(tmp_path):
    get_db, _ = _override_database(tmp_path)
    try:
        headers = _register("redfox-bad-base-url")
        response = client.post(
            "/api/wechat-official/redfox/config",
            headers=headers,
            json={"name": "Bad", "base_url": "http://127.0.0.1:8000", "api_key": "redfox-secret-key"},
        )

        assert response.status_code == 422
        assert "Redfox base_url" in response.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_redfox_config_normalizes_allowed_base_url(tmp_path):
    get_db, _ = _override_database(tmp_path)
    try:
        headers = _register("redfox-normalize-base-url")
        response = client.post(
            "/api/wechat-official/redfox/config",
            headers=headers,
            json={"name": "RedFoxHub", "base_url": "https://redfox.hk/", "api_key": "redfox-secret-key"},
        )

        assert response.status_code == 200
        assert response.json()["config"]["base_url"] == "https://redfox.hk"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_redfox_validate_config_calls_upstream_validation(tmp_path, monkeypatch):
    get_db, _ = _override_database(tmp_path)
    monkeypatch.setattr(redfox_service, "WechatOfficialRedfoxClient", FakeValidRedfoxClient, raising=False)
    FakeValidRedfoxClient.called = False
    try:
        headers = _register("redfox-validate-valid")
        created = client.post(
            "/api/wechat-official/redfox/config",
            headers=headers,
            json={"name": "RedFoxHub", "base_url": "https://redfox.hk", "api_key": "redfox-valid-key"},
        )
        assert created.status_code == 200

        response = client.post("/api/wechat-official/redfox/config/validate", headers=headers)

        assert response.status_code == 200
        assert response.json()["ok"] is True
        assert response.json()["config"]["status"] == "valid"
        assert FakeValidRedfoxClient.called is True
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_redfox_validate_config_marks_invalid_without_leaking_key(tmp_path, monkeypatch):
    get_db, _ = _override_database(tmp_path)
    monkeypatch.setattr(redfox_service, "WechatOfficialRedfoxClient", FakeInvalidRedfoxClient, raising=False)
    FakeInvalidRedfoxClient.called = False
    try:
        headers = _register("redfox-validate-invalid")
        created = client.post(
            "/api/wechat-official/redfox/config",
            headers=headers,
            json={"name": "RedFoxHub", "base_url": "https://redfox.hk", "api_key": "redfox-invalid-key"},
        )
        assert created.status_code == 200

        response = client.post("/api/wechat-official/redfox/config/validate", headers=headers)

        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is False
        assert payload["config"]["status"] == "invalid"
        assert FakeInvalidRedfoxClient.called is True
        assert "redfox-invalid-key" not in str(payload)
    finally:
        app.dependency_overrides.pop(get_db, None)

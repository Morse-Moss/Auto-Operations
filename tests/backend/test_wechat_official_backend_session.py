from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.core.security import decrypt_text
from backend.app.main import app
from test_support.beta_invites import create_test_invite_code
from backend.app.models import WechatOfficialBackendSession
from backend.app.services.wechat_official_backend_session_service import get_valid_session


client = TestClient(app)


def _override_database(tmp_path):
    from backend.app.core.database import Base, get_db

    engine = create_engine(f"sqlite:///{tmp_path / 'wechat-official-session-test.db'}", connect_args={"check_same_thread": False})
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
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_complete_backend_login_encrypts_cookie_and_token_and_api_hides_plaintext(tmp_path):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        headers = _register("operator-session")

        start_response = client.post("/api/wechat-official/accounts/login/qrcode", headers=headers)
        assert start_response.status_code == 200
        start_payload = start_response.json()
        assert start_payload["login_session_id"]
        assert start_payload["qrcode_url"].startswith("wechat-official://login/pending/")
        assert "mp.weixin.qq.com" not in start_payload["qrcode_url"]

        complete_response = client.post(
            f"/api/wechat-official/accounts/login/{start_payload['login_session_id']}/complete",
            headers=headers,
            json={
                "cookie": "wx-cookie-secret",
                "token": "wx-token-secret",
                "auth_key": "auth-key-secret",
                "biz": "MzA-session",
                "nickname": "测试公众号",
                "user_agent": "Mozilla/5.0 test",
            },
        )
        assert complete_response.status_code == 200
        api_payload = complete_response.json()
        assert api_payload["id"] == start_payload["login_session_id"]
        assert api_payload["status"] == "valid"
        serialized = str(api_payload)
        assert "wx-cookie-secret" not in serialized
        assert "wx-token-secret" not in serialized
        assert "auth-key-secret" not in serialized
        assert "encrypted_cookie" not in api_payload
        assert "encrypted_token" not in api_payload

        with TestingSessionLocal() as db:
            session = db.scalar(select(WechatOfficialBackendSession))
            assert session is not None
            assert session.encrypted_cookie != "wx-cookie-secret"
            assert session.encrypted_token != "wx-token-secret"
            assert decrypt_text(session.encrypted_cookie) == "wx-cookie-secret"
            assert decrypt_text(session.encrypted_token) == "wx-token-secret"
            assert session.status == "valid"
            assert session.raw_json["auth_key_hash"]
            assert session.raw_json["auth_key_hash"] != "auth-key-secret"
            assert "auth-key-secret" not in str(session.raw_json)
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_session_list_is_desensitized_and_scoped_to_current_user(tmp_path):
    get_db, _ = _override_database(tmp_path)
    try:
        owner_headers = _register("session-owner")
        other_headers = _register("session-other")

        start_response = client.post("/api/wechat-official/accounts/login/qrcode", headers=owner_headers)
        assert start_response.status_code == 200
        login_session_id = start_response.json()["login_session_id"]
        complete_response = client.post(
            f"/api/wechat-official/accounts/login/{login_session_id}/complete",
            headers=owner_headers,
            json={
                "cookie": "owner-cookie-secret",
                "token": "owner-token-secret",
                "auth_key": "owner-auth-key",
                "biz": "MzA-owner",
                "nickname": "Owner Account",
            },
        )
        assert complete_response.status_code == 200

        owner_list_response = client.get("/api/wechat-official/accounts/sessions", headers=owner_headers)
        assert owner_list_response.status_code == 200
        owner_payload = owner_list_response.json()
        assert owner_payload["total"] == 1
        assert owner_payload["items"][0]["id"] == login_session_id
        assert owner_payload["items"][0]["status"] == "valid"
        owner_serialized = str(owner_payload)
        assert "owner-cookie-secret" not in owner_serialized
        assert "owner-token-secret" not in owner_serialized
        assert "encrypted_cookie" not in owner_serialized
        assert "encrypted_token" not in owner_serialized

        other_list_response = client.get("/api/wechat-official/accounts/sessions", headers=other_headers)
        assert other_list_response.status_code == 200
        assert other_list_response.json()["items"] == []
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_complete_backend_login_saves_expired_status_when_expires_at_is_past(tmp_path):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        headers = _register("session-expiry-user")
        start_response = client.post("/api/wechat-official/accounts/login/qrcode", headers=headers)
        assert start_response.status_code == 200
        login_session_id = start_response.json()["login_session_id"]
        expires_at = (datetime.now() - timedelta(minutes=1)).replace(microsecond=0)

        complete_response = client.post(
            f"/api/wechat-official/accounts/login/{login_session_id}/complete",
            headers=headers,
            json={
                "cookie": "expired-cookie-secret",
                "token": "expired-token-secret",
                "auth_key": "expired-auth-key",
                "biz": "MzA-expired",
                "nickname": "Expired Account",
                "expires_at": expires_at.isoformat(),
            },
        )

        assert complete_response.status_code == 200
        complete_payload = complete_response.json()
        assert complete_payload["status"] == "expired"
        assert complete_payload["expires_at"] == expires_at.isoformat()

        list_response = client.get("/api/wechat-official/accounts/sessions", headers=headers)
        assert list_response.status_code == 200
        list_item = list_response.json()["items"][0]
        assert list_item["id"] == login_session_id
        assert list_item["status"] == "expired"

        with TestingSessionLocal() as db:
            login_session = db.scalar(select(WechatOfficialBackendSession))
            assert login_session is not None
            assert login_session.expires_at == expires_at
            assert login_session.status == "expired"
            try:
                get_valid_session(db, user_id=1, session_id=login_session_id)
                assert False, "expected expired session to be rejected"
            except HTTPException as exc:
                assert exc.status_code == 400
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_complete_backend_login_normalizes_aware_expires_at_to_shanghai_time(tmp_path):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        headers = _register("session-aware-normalize-user")
        start_response = client.post("/api/wechat-official/accounts/login/qrcode", headers=headers)
        assert start_response.status_code == 200
        login_session_id = start_response.json()["login_session_id"]

        aware_utc_expires_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).replace(microsecond=0)
        expected_shanghai_naive = aware_utc_expires_at.astimezone(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
        complete_response = client.post(
            f"/api/wechat-official/accounts/login/{login_session_id}/complete",
            headers=headers,
            json={
                "cookie": "aware-valid-cookie-secret",
                "token": "aware-valid-token-secret",
                "auth_key": "aware-valid-auth-key",
                "biz": "MzA-aware-valid",
                "nickname": "Aware Valid Account",
                "expires_at": aware_utc_expires_at.isoformat(),
            },
        )
        assert complete_response.status_code == 200
        complete_payload = complete_response.json()
        assert complete_payload["status"] == "valid"
        assert complete_payload["expires_at"] == expected_shanghai_naive.isoformat()

        with TestingSessionLocal() as db:
            login_session = db.scalar(select(WechatOfficialBackendSession))
            assert login_session is not None
            assert login_session.expires_at == expected_shanghai_naive
            assert login_session.status == "valid"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_session_list_downgrades_valid_session_to_expired_when_expires_at_passes(tmp_path):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        headers = _register("session-list-expiry-user")
        start_response = client.post("/api/wechat-official/accounts/login/qrcode", headers=headers)
        assert start_response.status_code == 200
        login_session_id = start_response.json()["login_session_id"]
        future_expires_at = (datetime.now() + timedelta(minutes=10)).replace(microsecond=0)

        complete_response = client.post(
            f"/api/wechat-official/accounts/login/{login_session_id}/complete",
            headers=headers,
            json={
                "cookie": "list-expiry-cookie-secret",
                "token": "list-expiry-token-secret",
                "auth_key": "list-expiry-auth-key",
                "biz": "MzA-list-expiry",
                "nickname": "List Expiry Account",
                "expires_at": future_expires_at.isoformat(),
            },
        )
        assert complete_response.status_code == 200
        assert complete_response.json()["status"] == "valid"

        past_expires_at = (datetime.now() - timedelta(minutes=1)).replace(microsecond=0)
        with TestingSessionLocal() as db:
            login_session = db.scalar(select(WechatOfficialBackendSession))
            assert login_session is not None
            login_session.expires_at = past_expires_at
            login_session.status = "valid"
            db.commit()

        list_response = client.get("/api/wechat-official/accounts/sessions", headers=headers)
        assert list_response.status_code == 200
        list_item = list_response.json()["items"][0]
        assert list_item["id"] == login_session_id
        assert list_item["status"] == "expired"

        with TestingSessionLocal() as db:
            login_session = db.scalar(select(WechatOfficialBackendSession))
            assert login_session is not None
            assert login_session.status == "expired"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_complete_backend_login_missing_required_secret_fields_returns_validation_error(tmp_path):
    get_db, _ = _override_database(tmp_path)
    try:
        headers = _register("session-missing-fields-user")
        start_response = client.post("/api/wechat-official/accounts/login/qrcode", headers=headers)
        assert start_response.status_code == 200
        login_session_id = start_response.json()["login_session_id"]

        for missing_field in ["cookie", "token", "auth_key"]:
            payload = {
                "cookie": "cookie-secret",
                "token": "token-secret",
                "auth_key": "auth-key-secret",
            }
            payload.pop(missing_field)
            response = client.post(
                f"/api/wechat-official/accounts/login/{login_session_id}/complete",
                headers=headers,
                json=payload,
            )
            assert response.status_code in {400, 422}
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_non_owner_cannot_complete_backend_login_session(tmp_path):
    get_db, _ = _override_database(tmp_path)
    try:
        owner_headers = _register("session-private-owner")
        other_headers = _register("session-private-other")
        start_response = client.post("/api/wechat-official/accounts/login/qrcode", headers=owner_headers)
        assert start_response.status_code == 200
        login_session_id = start_response.json()["login_session_id"]

        response = client.post(
            f"/api/wechat-official/accounts/login/{login_session_id}/complete",
            headers=other_headers,
            json={"cookie": "x", "token": "y", "auth_key": "z"},
        )

        assert response.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_get_valid_session_rejects_invalid_status(tmp_path):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        headers = _register("session-invalid-user")
        start_response = client.post("/api/wechat-official/accounts/login/qrcode", headers=headers)
        assert start_response.status_code == 200
        login_session_id = start_response.json()["login_session_id"]

        with TestingSessionLocal() as db:
            login_session = db.scalar(select(WechatOfficialBackendSession))
            assert login_session is not None
            try:
                get_valid_session(db, user_id=1, session_id=login_session_id)
                assert False, "expected pending session to be rejected"
            except HTTPException as exc:
                assert exc.status_code == 400
            assert login_session.status == "pending"
    finally:
        app.dependency_overrides.pop(get_db, None)

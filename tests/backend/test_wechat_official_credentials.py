from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.core.security import decrypt_text
from backend.app.core.time import shanghai_now
from backend.app.main import app
from test_support.beta_invites import create_test_invite_code
from backend.app.models import WechatOfficialArticleCredential


client = TestClient(app)


def _override_database(tmp_path):
    from backend.app.core.database import Base, get_db

    engine = create_engine(f"sqlite:///{tmp_path / 'wechat-official-credential-test.db'}", connect_args={"check_same_thread": False})
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


def _credential_payload(**overrides):
    captured_at = (shanghai_now() + timedelta(minutes=5)).replace(microsecond=0)
    payload = {
        "biz": "MzA-credential",
        "uin": "123456",
        "key": "article-key-secret",
        "pass_ticket": "pass-ticket-secret",
        "wap_sid2": "wap-sid2-secret",
        "appmsg_token": "appmsg-token-secret",
        "cookie": "credential-cookie-secret",
        "timestamp": 1780000000,
        "nickname": "Credential Account",
        "article_url": "https://mp.weixin.qq.com/s/test",
        "captured_at": captured_at.isoformat(),
    }
    payload.update(overrides)
    return payload


def test_credential_guide_contains_expected_fields_and_risk_warnings(tmp_path):
    get_db, _ = _override_database(tmp_path)
    try:
        headers = _register("guide-user")
        response = client.get("/api/wechat-official/credentials/guide", headers=headers)
        assert response.status_code == 200
        payload = response.json()
        assert payload["expected_fields"] == [
            "biz",
            "uin",
            "key",
            "pass_ticket",
            "wap_sid2",
            "appmsg_token",
            "cookie",
            "timestamp",
        ]
        warnings = " ".join(payload["risk_warnings"])
        assert "用户授权环境" in warnings
        assert "短有效期" in warnings
        assert "不做验证码绕过" in warnings
        assert payload["steps"]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_credential_validate_reports_missing_fields_without_saving(tmp_path):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        headers = _register("validate-user")
        payload = _credential_payload()
        payload.pop("key")
        payload.pop("cookie")

        response = client.post("/api/wechat-official/credentials/validate", headers=headers, json=payload)
        assert response.status_code == 200
        result = response.json()
        assert result["valid"] is False
        assert result["missing_fields"] == ["key", "cookie"]

        with TestingSessionLocal() as db:
            assert db.scalar(select(WechatOfficialArticleCredential)) is None
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_credential_import_encrypts_sensitive_fields_sets_expiry_valid_and_capabilities(tmp_path):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        headers = _register("import-user")
        response = client.post("/api/wechat-official/credentials/import", headers=headers, json=_credential_payload())
        assert response.status_code == 200
        api_payload = response.json()
        assert api_payload["biz"] == "MzA-credential"
        assert api_payload["nickname"] == "Credential Account"
        assert api_payload["status"] == "valid"
        assert api_payload["valid"] is True
        assert api_payload["capabilities"] == ["article.read", "article.metrics", "article.comments"]
        assert datetime.fromisoformat(api_payload["expires_at"]) > shanghai_now()
        serialized = str(api_payload)
        for secret in [
            "article-key-secret",
            "pass-ticket-secret",
            "wap-sid2-secret",
            "appmsg-token-secret",
            "credential-cookie-secret",
        ]:
            assert secret not in serialized
        assert "encrypted" not in serialized

        with TestingSessionLocal() as db:
            credential = db.scalar(select(WechatOfficialArticleCredential))
            assert credential is not None
            assert credential.valid is True
            assert credential.expires_at > shanghai_now()
            assert credential.encrypted_cookie != "credential-cookie-secret"
            assert decrypt_text(credential.encrypted_cookie) == "credential-cookie-secret"
            assert decrypt_text(credential.encrypted_token) == "appmsg-token-secret"
            assert decrypt_text(credential.encrypted_key) == "article-key-secret"
            assert credential.raw_json["pass_ticket_encrypted"] != "pass-ticket-secret"
            assert decrypt_text(credential.raw_json["pass_ticket_encrypted"]) == "pass-ticket-secret"
            assert decrypt_text(credential.raw_json["wap_sid2_encrypted"]) == "wap-sid2-secret"
            assert credential.raw_json["capabilities"] == ["article.read", "article.metrics", "article.comments"]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_credential_list_hides_sensitive_fields_and_is_scoped_to_current_user(tmp_path):
    get_db, _ = _override_database(tmp_path)
    try:
        owner_headers = _register("credential-owner")
        other_headers = _register("credential-other")

        import_response = client.post("/api/wechat-official/credentials/import", headers=owner_headers, json=_credential_payload())
        assert import_response.status_code == 200

        owner_list_response = client.get("/api/wechat-official/credentials", headers=owner_headers)
        assert owner_list_response.status_code == 200
        owner_payload = owner_list_response.json()
        assert owner_payload["total"] == 1
        item = owner_payload["items"][0]
        assert item["biz"] == "MzA-credential"
        assert item["nickname"] == "Credential Account"
        assert item["status"] == "valid"
        assert item["capabilities"] == ["article.read", "article.metrics", "article.comments"]
        serialized = str(owner_payload)
        for forbidden in [
            "article-key-secret",
            "pass-ticket-secret",
            "wap-sid2-secret",
            "appmsg-token-secret",
            "credential-cookie-secret",
            "encrypted_cookie",
            "encrypted_token",
            "encrypted_key",
        ]:
            assert forbidden not in serialized

        other_list_response = client.get("/api/wechat-official/credentials", headers=other_headers)
        assert other_list_response.status_code == 200
        assert other_list_response.json()["items"] == []
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_credential_import_sanitizes_sensitive_article_url_query_in_response_and_storage(tmp_path):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        headers = _register("credential-url-user")
        raw_url = (
            "https://mp.weixin.qq.com/s/test?__biz=MzA-credential&mid=1&idx=1&"
            "key=article-key-secret&pass_ticket=pass-ticket-secret&"
            "appmsg_token=appmsg-token-secret&token=backend-token-secret&"
            "wap_sid2=wap-sid2-query-secret&cookie=credential-cookie-query-secret&scene=1"
        )

        response = client.post(
            "/api/wechat-official/credentials/import",
            headers=headers,
            json=_credential_payload(article_url=raw_url),
        )

        assert response.status_code == 200
        api_payload = response.json()
        assert api_payload["article_url"] == "https://mp.weixin.qq.com/s/test?__biz=MzA-credential&mid=1&idx=1&scene=1"
        serialized = str(api_payload)
        for secret_fragment in [
            "article-key-secret",
            "pass-ticket-secret",
            "appmsg-token-secret",
            "backend-token-secret",
            "wap-sid2-query-secret",
            "credential-cookie-query-secret",
        ]:
            assert secret_fragment not in serialized

        with TestingSessionLocal() as db:
            credential = db.scalar(select(WechatOfficialArticleCredential))
            assert credential is not None
            assert credential.article_url == api_payload["article_url"]
            assert "key=" not in credential.article_url
            assert "pass_ticket=" not in credential.article_url
            assert "appmsg_token=" not in credential.article_url
            assert "token=" not in credential.article_url
            assert "wap_sid2=" not in credential.article_url
            assert "cookie=" not in credential.article_url
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_credential_import_normalizes_utc_captured_at_to_shanghai_expiry(tmp_path):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        headers = _register("credential-utc-captured-user")
        captured_at_utc = (datetime.now(timezone.utc) + timedelta(minutes=1)).replace(microsecond=0)
        expected_expires_at = captured_at_utc.astimezone(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None) + timedelta(minutes=25)

        response = client.post(
            "/api/wechat-official/credentials/import",
            headers=headers,
            json=_credential_payload(captured_at=captured_at_utc.isoformat()),
        )

        assert response.status_code == 200
        api_payload = response.json()
        assert api_payload["status"] == "valid"
        assert api_payload["valid"] is True
        assert datetime.fromisoformat(api_payload["expires_at"]) == expected_expires_at
        assert expected_expires_at > shanghai_now()

        with TestingSessionLocal() as db:
            credential = db.scalar(select(WechatOfficialArticleCredential))
            assert credential is not None
            assert credential.valid is True
            assert credential.expires_at == expected_expires_at
    finally:
        app.dependency_overrides.pop(get_db, None)



def test_credential_import_saves_expired_credential_as_expired_for_diagnostics(tmp_path):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        headers = _register("credential-expired-user")
        captured_at = (shanghai_now() - timedelta(hours=1)).replace(microsecond=0).isoformat()

        response = client.post(
            "/api/wechat-official/credentials/import",
            headers=headers,
            json=_credential_payload(captured_at=captured_at),
        )

        assert response.status_code == 200
        api_payload = response.json()
        assert api_payload["status"] == "expired"
        assert api_payload["valid"] is False

        list_response = client.get("/api/wechat-official/credentials", headers=headers)
        assert list_response.status_code == 200
        item = list_response.json()["items"][0]
        assert item["status"] == "expired"
        assert item["valid"] is False

        with TestingSessionLocal() as db:
            credential = db.scalar(select(WechatOfficialArticleCredential))
            assert credential is not None
            assert credential.valid is False
            assert credential.expires_at < shanghai_now()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_credential_import_rejects_invalid_captured_at_with_400(tmp_path):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        headers = _register("credential-invalid-date-user")

        response = client.post(
            "/api/wechat-official/credentials/import",
            headers=headers,
            json=_credential_payload(captured_at="not-a-date"),
        )

        assert response.status_code == 400
        assert "captured_at" in str(response.json()["detail"])
        with TestingSessionLocal() as db:
            assert db.scalar(select(WechatOfficialArticleCredential)) is None
    finally:
        app.dependency_overrides.pop(get_db, None)

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.core.config import get_settings
from backend.app.core.database import Base, get_db
from backend.app.core.security import create_access_token, create_refresh_token, hash_password
from backend.app.main import app
from backend.app.models import (
    InviteCode,
    InviteCodeUse,
    TenantMember,
    UsageLedger,
    User,
)
from backend.app.services.usage_quota_service import get_or_create_default_tenant_context


client = TestClient(app)


def _override_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'beta-admission-test.db'}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    override_get_db.sessionmaker = TestingSessionLocal
    app.dependency_overrides[get_db] = override_get_db
    return get_db


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_invite(db, code: str = "BETA-JOIN", max_uses: int = 1, created_by_user_id: int | None = None) -> InviteCode:
    invite = InviteCode(code=code, max_uses=max_uses, used_count=0, status="active", created_by_user_id=created_by_user_id)
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return invite


def _create_user(db, username: str, *, role: str = "user", status: str = "active") -> User:
    user = User(username=username, password_hash=hash_password("secret123"), role=role, status=status)
    db.add(user)
    db.commit()
    db.refresh(user)
    get_or_create_default_tenant_context(db, user.id)
    db.commit()
    db.refresh(user)
    return user


def _register(username: str, invite_code: str | None = None):
    payload = {"username": username, "password": "secret123"}
    if invite_code is not None:
        payload["invite_code"] = invite_code
    return client.post("/api/auth/register", json=payload)


def test_register_requires_invite_code_and_records_usage(tmp_path):
    db_dependency = _override_database(tmp_path)
    try:
        missing = _register("no-invite-user")
        assert missing.status_code == 400
        assert missing.json()["detail"] == "Invitation code is required"

        db = next(app.dependency_overrides[get_db]())
        try:
            invite = _create_invite(db, code="BETA-JOIN", max_uses=2)
        finally:
            db.close()

        response = _register("invited-user", invite_code=" beta-join ")

        assert response.status_code == 200
        payload = response.json()
        assert payload["user"]["username"] == "invited-user"
        assert payload["user"]["role"] == "user"
        assert payload["user"]["status"] == "active"

        db = next(app.dependency_overrides[get_db]())
        try:
            invite = db.get(InviteCode, invite.id)
            assert invite is not None
            usage = db.scalar(select(InviteCodeUse).where(InviteCodeUse.used_by_user_id == payload["user"]["id"]))
            assert invite.used_count == 1
            assert usage is not None
            assert usage.invite_code_id == invite.id
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_invite_code_enforces_max_uses(tmp_path):
    db_dependency = _override_database(tmp_path)
    try:
        db = next(app.dependency_overrides[get_db]())
        try:
            _create_invite(db, code="ONE-SEAT", max_uses=1)
        finally:
            db.close()

        first = _register("first-seat", invite_code="ONE-SEAT")
        second = _register("second-seat", invite_code="ONE-SEAT")

        assert first.status_code == 200
        assert second.status_code == 400
        assert second.json()["detail"] == "Invitation code has no remaining uses"

        db = next(app.dependency_overrides[get_db]())
        try:
            assert db.scalar(select(User).where(User.username == "second-seat")) is None
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_disabled_user_and_suspended_tenant_are_rejected(tmp_path):
    db_dependency = _override_database(tmp_path)
    try:
        db = next(app.dependency_overrides[get_db]())
        try:
            _create_invite(db, code="STATUS-CHECK", max_uses=1)
        finally:
            db.close()

        registered = _register("status-user", invite_code="STATUS-CHECK").json()
        token = registered["access_token"]

        db = next(app.dependency_overrides[get_db]())
        try:
            user = db.get(User, registered["user"]["id"])
            assert user is not None
            user.status = "disabled"
            db.commit()
        finally:
            db.close()

        disabled = client.get("/api/auth/me", headers=_auth_headers(token))
        assert disabled.status_code == 403
        assert disabled.json()["detail"] == "User is disabled"

        db = next(app.dependency_overrides[get_db]())
        try:
            user = db.get(User, registered["user"]["id"])
            assert user is not None
            user.status = "active"
            membership = db.scalar(select(TenantMember).where(TenantMember.user_id == user.id))
            assert membership is not None
            context = get_or_create_default_tenant_context(db, user.id)
            context.tenant.status = "suspended"
            db.commit()
        finally:
            db.close()

        suspended = client.get("/api/usage/balance", headers=_auth_headers(token))
        assert suspended.status_code == 403
        assert suspended.json()["detail"] == "Tenant is suspended"
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_suspended_tenant_is_rejected_by_all_authenticated_routes(tmp_path):
    db_dependency = _override_database(tmp_path)
    try:
        db = next(app.dependency_overrides[get_db]())
        try:
            user = _create_user(db, "suspended-global-user")
            token = create_access_token(user.id)
            context = get_or_create_default_tenant_context(db, user.id)
            context.tenant.status = "suspended"
            db.commit()
        finally:
            db.close()

        tasks = client.get("/api/tasks", headers=_auth_headers(token))
        assert tasks.status_code == 403
        assert tasks.json()["detail"] == "Tenant is suspended"
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_suspended_tenant_cannot_login_or_refresh_token(tmp_path):
    db_dependency = _override_database(tmp_path)
    try:
        db = next(app.dependency_overrides[get_db]())
        try:
            user = _create_user(db, "suspended-auth-user")
            context = get_or_create_default_tenant_context(db, user.id)
            context.tenant.status = "suspended"
            refresh_token = create_refresh_token(user.id)
            db.commit()
        finally:
            db.close()

        login = client.post("/api/auth/login", json={"username": "suspended-auth-user", "password": "secret123"})
        assert login.status_code == 403
        assert login.json()["detail"] == "Tenant is suspended"

        refresh = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
        assert refresh.status_code == 403
        assert refresh.json()["detail"] == "Tenant is suspended"
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_first_admin_bootstrap_requires_configured_token_and_creates_admin(tmp_path, monkeypatch):
    db_dependency = _override_database(tmp_path)
    monkeypatch.setenv("BETA_ADMIN_BOOTSTRAP_TOKEN", "bootstrap-secret")
    get_settings.cache_clear()
    try:
        wrong = client.post(
            "/api/admin/bootstrap",
            json={"username": "first-admin", "password": "secret123", "bootstrap_token": "wrong"},
        )
        assert wrong.status_code == 403

        created = client.post(
            "/api/admin/bootstrap",
            json={"username": "first-admin", "password": "secret123", "bootstrap_token": "bootstrap-secret"},
        )
        assert created.status_code == 200
        assert created.json()["username"] == "first-admin"
        assert created.json()["role"] == "admin"
        assert created.json()["status"] == "active"

        login = client.post("/api/auth/login", json={"username": "first-admin", "password": "secret123"})
        assert login.status_code == 200
        assert login.json()["user"]["role"] == "admin"
    finally:
        get_settings.cache_clear()
        app.dependency_overrides.pop(db_dependency, None)


def test_first_admin_bootstrap_refuses_after_admin_exists(tmp_path, monkeypatch):
    db_dependency = _override_database(tmp_path)
    monkeypatch.setenv("BETA_ADMIN_BOOTSTRAP_TOKEN", "bootstrap-secret")
    get_settings.cache_clear()
    try:
        db = next(app.dependency_overrides[get_db]())
        try:
            _create_user(db, "existing-admin", role="admin")
        finally:
            db.close()

        response = client.post(
            "/api/admin/bootstrap",
            json={"username": "late-admin", "password": "secret123", "bootstrap_token": "bootstrap-secret"},
        )
        assert response.status_code == 409
        assert response.json()["detail"] == "Admin bootstrap is already completed"
    finally:
        get_settings.cache_clear()
        app.dependency_overrides.pop(db_dependency, None)


def test_admin_api_controls_users_tenants_and_credit_balance(tmp_path):
    db_dependency = _override_database(tmp_path)
    try:
        db = next(app.dependency_overrides[get_db]())
        try:
            admin = _create_user(db, "beta-admin", role="admin")
            target = _create_user(db, "beta-member", role="user")
            target_context = get_or_create_default_tenant_context(db, target.id)
            admin_token = create_access_token(admin.id)
            target_token = create_access_token(target.id)
            target_tenant_id = target_context.tenant.id
            target_user_id = target.id
        finally:
            db.close()

        non_admin = client.get("/api/admin/users", headers=_auth_headers(target_token))
        assert non_admin.status_code == 403

        users = client.get("/api/admin/users", headers=_auth_headers(admin_token))
        assert users.status_code == 200
        assert {item["username"]: item["role"] for item in users.json()["items"]}["beta-admin"] == "admin"

        tenants = client.get("/api/admin/tenants", headers=_auth_headers(admin_token))
        assert tenants.status_code == 200
        assert any(item["id"] == target_tenant_id for item in tenants.json()["items"])

        adjusted = client.post(
            f"/api/admin/tenants/{target_tenant_id}/credits/adjust",
            headers=_auth_headers(admin_token),
            json={"bucket": "credits", "total": 700, "reason": "beta grant"},
        )
        assert adjusted.status_code == 200
        assert adjusted.json()["bucket"] == "credits"
        assert adjusted.json()["total"] == 700
        assert adjusted.json()["remaining"] == 700

        db = next(app.dependency_overrides[get_db]())
        try:
            ledger = db.scalar(
                select(UsageLedger).where(
                    UsageLedger.tenant_id == target_tenant_id,
                    UsageLedger.bucket == "credits",
                    UsageLedger.operation == "adjust",
                )
            )
            assert ledger is not None
            assert ledger.failure_reason == "beta grant"
        finally:
            db.close()

        suspended = client.post(f"/api/admin/tenants/{target_tenant_id}/suspend", headers=_auth_headers(admin_token))
        assert suspended.status_code == 200
        assert suspended.json()["status"] == "suspended"
        assert client.get("/api/usage/balance", headers=_auth_headers(target_token)).status_code == 403

        activated = client.post(f"/api/admin/tenants/{target_tenant_id}/activate", headers=_auth_headers(admin_token))
        assert activated.status_code == 200
        assert activated.json()["status"] == "active"
        assert client.get("/api/usage/balance", headers=_auth_headers(target_token)).status_code == 200

        disabled = client.post(f"/api/admin/users/{target_user_id}/disable", headers=_auth_headers(admin_token))
        assert disabled.status_code == 200
        assert disabled.json()["status"] == "disabled"
        assert client.get("/api/auth/me", headers=_auth_headers(target_token)).status_code == 403

        enabled = client.post(f"/api/admin/users/{target_user_id}/activate", headers=_auth_headers(admin_token))
        assert enabled.status_code == 200
        assert enabled.json()["status"] == "active"
        assert client.get("/api/auth/me", headers=_auth_headers(target_token)).status_code == 200
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_admin_invite_code_management_lists_usage(tmp_path):
    db_dependency = _override_database(tmp_path)
    try:
        db = next(app.dependency_overrides[get_db]())
        try:
            admin = _create_user(db, "invite-admin", role="admin")
            admin_token = create_access_token(admin.id)
        finally:
            db.close()

        created = client.post(
            "/api/admin/invite-codes",
            headers=_auth_headers(admin_token),
            json={"code": "BETA-ADMIN-CODE", "max_uses": 3},
        )
        assert created.status_code == 200
        assert created.json()["code"] == "BETA-ADMIN-CODE"
        assert created.json()["max_uses"] == 3

        registered = _register("invite-recipient", invite_code="BETA-ADMIN-CODE")
        assert registered.status_code == 200

        listed = client.get("/api/admin/invite-codes", headers=_auth_headers(admin_token))
        assert listed.status_code == 200
        invite = next(item for item in listed.json()["items"] if item["code"] == "BETA-ADMIN-CODE")
        assert invite["used_count"] == 1
        assert invite["uses"][0]["username"] == "invite-recipient"
    finally:
        app.dependency_overrides.pop(db_dependency, None)

from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.database import Base, get_db
from backend.app.core.security import encrypt_text
from backend.app.core.time import shanghai_now
from backend.app.main import app
from backend.app.models import BetaConcurrencyLease, ModelConfig, Task, UsageLedger, User
from backend.app.services.usage_quota_service import get_or_create_default_tenant_context
from test_support.beta_invites import create_test_invite_code

client = TestClient(app)


def _override_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'beta-concurrency-test.db'}", connect_args={"check_same_thread": False})
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


def _register(username: str) -> dict:
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": "secret123", "invite_code": create_test_invite_code()},
    )
    assert response.status_code == 200
    return response.json()


def _with_db(action):
    db = next(app.dependency_overrides[get_db]())
    try:
        return action(db)
    finally:
        db.close()


def _create_image_model(db: Session, user_id: int) -> None:
    db.add(
        ModelConfig(
            user_id=user_id,
            name="Default Image",
            model_type="image",
            provider="openai-compatible",
            model_name="gpt-image-concurrency-test",
            base_url="https://api.example.test/v1",
            encrypted_api_key=encrypt_text("sk-image-secret"),
            is_default=True,
        )
    )
    db.commit()


def _create_text_model(db: Session, user_id: int) -> None:
    db.add(
        ModelConfig(
            user_id=user_id,
            name="Default Text",
            model_type="text",
            provider="openai-compatible",
            model_name="gpt-analysis-concurrency-test",
            base_url="https://api.example.test/v1",
            encrypted_api_key=encrypt_text("sk-analysis-secret"),
            is_default=True,
        )
    )
    db.commit()


def _seed_active_lease(db: Session, *, user_id: int, bucket: str, scope: str, slot_number: int = 1, expires_in_minutes: int = 30):
    from backend.app.services.beta_concurrency_service import BetaConcurrencyService

    tenant_id = get_or_create_default_tenant_context(db, user_id).tenant.id
    return BetaConcurrencyService(db).acquire(
        tenant_id=tenant_id,
        user_id=user_id,
        bucket=bucket,
        scope=scope,
        slot_number=slot_number,
        expires_at=shanghai_now() + timedelta(minutes=expires_in_minutes),
    )


def test_concurrency_service_blocks_second_user_image_slot_and_releases_for_reuse(tmp_path):
    db_dependency = _override_database(tmp_path)
    try:
        registered = _register("concurrency-service-user")

        def scenario(db: Session):
            from backend.app.services.beta_concurrency_service import BetaConcurrencyLimitExceeded, BetaConcurrencyService

            tenant_id = get_or_create_default_tenant_context(db, registered["user"]["id"]).tenant.id
            service = BetaConcurrencyService(db)

            first = service.acquire(
                tenant_id=tenant_id,
                user_id=registered["user"]["id"],
                bucket="image_generation",
                scope="user",
                slot_number=1,
                expires_at=shanghai_now() + timedelta(minutes=30),
            )
            try:
                service.acquire(
                    tenant_id=tenant_id,
                    user_id=registered["user"]["id"],
                    bucket="image_generation",
                    scope="user",
                    slot_number=1,
                    expires_at=shanghai_now() + timedelta(minutes=30),
                )
            except BetaConcurrencyLimitExceeded as exc:
                assert exc.status_code == 429
                assert exc.payload["bucket"] == "image_generation"
                assert exc.payload["scope"] == "user"
                assert exc.payload["limit"] == 1
            else:  # pragma: no cover - the assertion above is the contract.
                raise AssertionError("second active user image lease must be rejected")

            service.release(first.id, reason="test finished")
            second = service.acquire(
                tenant_id=tenant_id,
                user_id=registered["user"]["id"],
                bucket="image_generation",
                scope="user",
                slot_number=1,
                expires_at=shanghai_now() + timedelta(minutes=30),
            )
            assert second.id != first.id
            assert second.status == "active"

        _with_db(scenario)
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_concurrency_service_ignores_expired_tenant_slots(tmp_path):
    db_dependency = _override_database(tmp_path)
    try:
        registered = _register("concurrency-expired-user")

        def scenario(db: Session):
            from backend.app.services.beta_concurrency_service import BetaConcurrencyService

            tenant_id = get_or_create_default_tenant_context(db, registered["user"]["id"]).tenant.id
            service = BetaConcurrencyService(db)
            stale = service.acquire(
                tenant_id=tenant_id,
                user_id=registered["user"]["id"],
                bucket="analysis_report",
                scope="tenant",
                slot_number=1,
                expires_at=shanghai_now() - timedelta(minutes=1),
            )
            fresh = service.acquire(
                tenant_id=tenant_id,
                user_id=registered["user"]["id"],
                bucket="analysis_report",
                scope="tenant",
                slot_number=1,
                expires_at=shanghai_now() + timedelta(minutes=30),
            )

            db.refresh(stale)
            assert stale.status == "expired"
            assert fresh.status == "active"

        _with_db(scenario)
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_image_generate_user_concurrency_limit_returns_429_before_quota_or_provider_call(tmp_path):
    from backend.app.api.ai import get_image_ai_client

    class TrapImageClient:
        called = False

        def generate_image(self, **kwargs):
            self.called = True
            raise AssertionError("provider must not be called when image concurrency is exhausted")

    db_dependency = _override_database(tmp_path)
    trap_client = TrapImageClient()
    try:
        registered = _register("image-user-limit")

        def seed(db: Session):
            user_id = registered["user"]["id"]
            _create_image_model(db, user_id)
            _seed_active_lease(db, user_id=user_id, bucket="image_generation", scope="user")

        _with_db(seed)
        app.dependency_overrides[get_image_ai_client] = lambda: trap_client
        response = client.post(
            "/api/ai/images/generate",
            headers={**_auth_headers(registered["access_token"]), "Idempotency-Key": "image-user-concurrency"},
            json={"prompt": "blocked image", "save_to_assets": False, "aspect_ratio": "1:1"},
        )

        assert response.status_code == 429
        assert response.json()["code"] == "beta_concurrency_limit_exceeded"
        assert response.json()["bucket"] == "image_generation"
        assert response.json()["scope"] == "user"
        assert trap_client.called is False

        ledger_count = _with_db(
            lambda db: db.scalar(select(func.count(UsageLedger.id)).where(UsageLedger.bucket == "image_generation"))
        )
        assert ledger_count == 0
    finally:
        app.dependency_overrides.pop(get_image_ai_client, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_image_generate_tenant_concurrency_limit_counts_two_users_and_spares_other_tenants(tmp_path):
    from backend.app.api.ai import get_image_ai_client

    class TrapImageClient:
        called = False

        def generate_image(self, **kwargs):
            self.called = True
            raise AssertionError("provider must not be called for blocked tenant image slot")

    class FakeImageClient:
        def generate_image(self, **kwargs):
            return {"url": "data:image/png;base64,aGVsbG8=", "raw": {"ok": True}}

    db_dependency = _override_database(tmp_path)
    try:
        owner = _register("image-tenant-owner")
        peer = _register("image-tenant-peer")
        outside = _register("image-tenant-outside")

        def seed(db: Session):
            owner_context = get_or_create_default_tenant_context(db, owner["user"]["id"])
            peer_context = get_or_create_default_tenant_context(db, peer["user"]["id"])
            peer_context.membership.tenant_id = owner_context.tenant.id
            peer_context.membership.role = "member"
            _create_image_model(db, owner["user"]["id"])
            _create_image_model(db, peer["user"]["id"])
            _create_image_model(db, outside["user"]["id"])
            _seed_active_lease(db, user_id=owner["user"]["id"], bucket="image_generation", scope="tenant", slot_number=1)
            _seed_active_lease(db, user_id=peer["user"]["id"], bucket="image_generation", scope="tenant", slot_number=2)
            db.commit()

        _with_db(seed)

        app.dependency_overrides[get_image_ai_client] = lambda: TrapImageClient()
        blocked = client.post(
            "/api/ai/images/generate",
            headers={**_auth_headers(owner["access_token"]), "Idempotency-Key": "image-tenant-blocked"},
            json={"prompt": "blocked tenant image", "save_to_assets": False, "aspect_ratio": "1:1"},
        )
        assert blocked.status_code == 429
        assert blocked.json()["scope"] == "tenant"

        app.dependency_overrides[get_image_ai_client] = lambda: FakeImageClient()
        allowed = client.post(
            "/api/ai/images/generate",
            headers={**_auth_headers(outside["access_token"]), "Idempotency-Key": "image-other-tenant"},
            json={"prompt": "outside tenant image", "save_to_assets": False, "aspect_ratio": "1:1"},
        )
        assert allowed.status_code == 200
        assert allowed.json()["url"].startswith("data:image/png")
    finally:
        app.dependency_overrides.pop(get_image_ai_client, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_analysis_report_tenant_concurrency_limit_returns_429_before_quota_or_provider_call(tmp_path):
    from backend.app.api.platforms.xhs import analysis_center

    class TrapTextClient:
        called = False

        def complete_json_prompt(self, **kwargs):
            self.called = True
            raise AssertionError("provider must not be called when analysis concurrency is exhausted")

    db_dependency = _override_database(tmp_path)
    trap_client = TrapTextClient()
    try:
        registered = _register("analysis-tenant-limit")

        def seed(db: Session):
            user_id = registered["user"]["id"]
            _create_text_model(db, user_id)
            _seed_active_lease(db, user_id=user_id, bucket="analysis_report", scope="tenant")

        _with_db(seed)
        app.dependency_overrides[analysis_center.get_text_ai_client] = lambda: trap_client
        response = client.post(
            "/api/xhs/analytics/analysis/reports",
            headers={**_auth_headers(registered["access_token"]), "Idempotency-Key": "analysis-concurrency"},
            json={"keyword_group_id": 1, "title": "blocked report", "excluded_note_ids": []},
        )

        assert response.status_code == 429
        assert response.json()["code"] == "beta_concurrency_limit_exceeded"
        assert response.json()["bucket"] == "analysis_report"
        assert response.json()["scope"] == "tenant"
        assert trap_client.called is False

        ledger_count = _with_db(
            lambda db: db.scalar(select(func.count(UsageLedger.id)).where(UsageLedger.bucket == "analysis_report"))
        )
        assert ledger_count == 0
    finally:
        app.dependency_overrides.pop(analysis_center.get_text_ai_client, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_async_image_generation_releases_concurrency_leases_after_success(tmp_path, monkeypatch):
    from backend.app.api import ai as ai_module
    from backend.app.api.ai import get_image_ai_client

    class FakeImageClient:
        def generate_image(self, **kwargs):
            return {"url": "data:image/png;base64,aGVsbG8=", "raw": {"ok": True}}

    db_dependency = _override_database(tmp_path)
    try:
        registered = _register("async-concurrency-success")

        def seed(db: Session):
            _create_image_model(db, registered["user"]["id"])

        _with_db(seed)
        monkeypatch.setattr(ai_module, "SessionLocal", app.dependency_overrides[get_db].sessionmaker)
        app.dependency_overrides[get_image_ai_client] = lambda: FakeImageClient()
        response = client.post(
            "/api/ai/images/generate-async",
            headers={**_auth_headers(registered["access_token"]), "Idempotency-Key": "async-concurrency-success"},
            json={"prompt": "async slot success", "save_to_assets": False, "aspect_ratio": "1:1"},
        )

        assert response.status_code == 200
        task_id = response.json()["task_id"]

        def assert_released(db: Session):
            task = db.get(Task, task_id)
            assert task is not None
            assert task.status == "completed"
            lease_ids = task.payload["concurrency_lease_ids"]
            assert len(lease_ids) == 2
            leases = db.scalars(select(BetaConcurrencyLease).where(BetaConcurrencyLease.id.in_(lease_ids))).all()
            assert sorted(lease.status for lease in leases) == ["released", "released"]
            assert all(lease.active_key is None for lease in leases)

        _with_db(assert_released)
    finally:
        app.dependency_overrides.pop(get_image_ai_client, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_async_image_generation_releases_concurrency_leases_after_failure(tmp_path, monkeypatch):
    from backend.app.api import ai as ai_module
    from backend.app.api.ai import get_image_ai_client

    class FailingImageClient:
        def generate_image(self, **kwargs):
            raise RuntimeError("async provider failed")

    db_dependency = _override_database(tmp_path)
    try:
        registered = _register("async-concurrency-failure")

        def seed(db: Session):
            _create_image_model(db, registered["user"]["id"])

        _with_db(seed)
        monkeypatch.setattr(ai_module, "SessionLocal", app.dependency_overrides[get_db].sessionmaker)
        app.dependency_overrides[get_image_ai_client] = lambda: FailingImageClient()
        response = client.post(
            "/api/ai/images/generate-async",
            headers={**_auth_headers(registered["access_token"]), "Idempotency-Key": "async-concurrency-failure"},
            json={"prompt": "async slot failure", "save_to_assets": False, "aspect_ratio": "1:1"},
        )

        assert response.status_code == 200
        task_id = response.json()["task_id"]

        def assert_released(db: Session):
            task = db.get(Task, task_id)
            assert task is not None
            assert task.status == "failed"
            lease_ids = task.payload["concurrency_lease_ids"]
            leases = db.scalars(select(BetaConcurrencyLease).where(BetaConcurrencyLease.id.in_(lease_ids))).all()
            assert sorted(lease.status for lease in leases) == ["released", "released"]
            assert all(lease.active_key is None for lease in leases)

        _with_db(assert_released)
    finally:
        app.dependency_overrides.pop(get_image_ai_client, None)
        app.dependency_overrides.pop(db_dependency, None)

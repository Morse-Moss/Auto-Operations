from __future__ import annotations

import importlib
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import Base, get_db
from backend.app.core.security import encrypt_text
from backend.app.main import app
from backend.app.models import AiDraft, ApiLog, ModelConfig, Task, UsageLedger
from test_support.beta_invites import create_test_invite_code

client = TestClient(app)


def _override_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'usage-quota-test.db'}", connect_args={"check_same_thread": False})
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


def _register(username: str = "quota-owner") -> dict:
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": "secret123", "invite_code": create_test_invite_code()},
    )
    assert response.status_code == 200
    return response.json()


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _usage_contract():
    try:
        models = importlib.import_module("backend.app.models.usage_quota")
        service_module = importlib.import_module("backend.app.services.usage_quota_service")
    except ModuleNotFoundError as exc:
        raise AssertionError("usage quota models and service must exist") from exc
    return models, service_module


def test_register_creates_default_tenant_membership_and_beta_credit_balance(tmp_path):
    db_dependency = _override_database(tmp_path)
    try:
        registered = _register("tenant-beta-owner")

        models, _ = _usage_contract()
        db = next(app.dependency_overrides[get_db]())
        try:
            tenant = db.scalar(select(models.Tenant).where(models.Tenant.slug == "tenant-beta-owner"))
            assert tenant is not None
            membership = db.scalar(
                select(models.TenantMember).where(
                    models.TenantMember.tenant_id == tenant.id,
                    models.TenantMember.user_id == registered["user"]["id"],
                )
            )
            assert membership is not None
            assert membership.role == "owner"
        finally:
            db.close()

        balance_response = client.get("/api/usage/balance", headers=_auth_headers(registered["access_token"]))

        assert balance_response.status_code == 200
        balance = balance_response.json()
        assert balance["tenant"]["name"] == "tenant-beta-owner 的工作空间"
        assert balance["membership"]["role"] == "owner"
        assert balance["buckets"]["credits"]["remaining"] == 100
        assert set(balance["buckets"]) == {"credits"}
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_usage_balance_hides_legacy_feature_buckets(tmp_path):
    db_dependency = _override_database(tmp_path)
    try:
        registered = _register("legacy-bucket-owner")
        models, service_module = _usage_contract()
        db = next(app.dependency_overrides[get_db]())
        try:
            context = service_module.get_or_create_default_tenant_context(db, registered["user"]["id"])
            db.add(models.BetaCreditAccount(tenant_id=context.tenant.id, bucket="image_generation", total=20, remaining=20, status="active"))
            db.commit()
        finally:
            db.close()

        balance_response = client.get("/api/usage/balance", headers=_auth_headers(registered["access_token"]))

        assert balance_response.status_code == 200
        assert set(balance_response.json()["buckets"]) == {"credits"}
        assert balance_response.json()["buckets"]["credits"]["remaining"] == 100
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_usage_quota_reserve_commit_refund_and_idempotency_are_ledgered(tmp_path):
    db_dependency = _override_database(tmp_path)
    try:
        registered = _register("ledger-owner")
        models, service_module = _usage_contract()
        db = next(app.dependency_overrides[get_db]())
        try:
            context = service_module.get_or_create_default_tenant_context(db, registered["user"]["id"])
            service = service_module.UsageQuotaService(db)

            reservation = service.reserve(
                tenant_id=context.tenant.id,
                user_id=registered["user"]["id"],
                feature_key="ai.rewrite_note",
                bucket="credits",
                amount=2,
                idempotency_key="rewrite-once",
                request_summary={"body_length": 128},
            )
            assert reservation.status == "reserved"
            assert reservation.balance_after == 98

            duplicate_reservation = service.reserve(
                tenant_id=context.tenant.id,
                user_id=registered["user"]["id"],
                feature_key="ai.rewrite_note",
                bucket="credits",
                amount=2,
                idempotency_key="rewrite-once",
                request_summary={"body_length": 128},
            )
            assert duplicate_reservation.id == reservation.id
            assert service.get_balance(context.tenant.id)["credits"].remaining == 98

            committed = service.commit(reservation.id)
            assert committed.status == "committed"
            assert service.get_balance(context.tenant.id)["credits"].remaining == 98

            try:
                service.refund(reservation.id, failure_reason="provider failed after reservation")
            except ValueError as exc:
                assert "committed" in str(exc)
            else:  # pragma: no cover - the assertion above is the contract.
                raise AssertionError("committed reservations must not be refunded")
            assert service.get_balance(context.tenant.id)["credits"].remaining == 98

            ledger_rows = db.scalars(
                select(models.UsageLedger)
                .where(models.UsageLedger.tenant_id == context.tenant.id)
                .order_by(models.UsageLedger.id)
            ).all()
            assert [row.operation for row in ledger_rows] == ["reserve", "commit"]
            assert all("secret" not in str(row.request_summary).lower() for row in ledger_rows)
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_usage_quota_insufficient_balance_raises_structured_error(tmp_path):
    db_dependency = _override_database(tmp_path)
    try:
        registered = _register("insufficient-owner")
        _, service_module = _usage_contract()
        db = next(app.dependency_overrides[get_db]())
        try:
            context = service_module.get_or_create_default_tenant_context(db, registered["user"]["id"])
            service = service_module.UsageQuotaService(db)
            service.adjust_bucket(context.tenant.id, "credits", total=0, reason="test exhausts credits")

            try:
                service.reserve(
                    tenant_id=context.tenant.id,
                    user_id=registered["user"]["id"],
                    feature_key="ai.image_generate",
                    bucket="credits",
                    amount=5,
                    idempotency_key="image-over-limit",
                )
            except service_module.UsageQuotaInsufficientError as exc:
                assert exc.status_code == 402
                assert exc.payload == {
                    "code": "usage_quota_insufficient",
                    "message": "积分不足，本次需要 5 积分，当前剩余 0 积分。",
                    "feature_key": "ai.image_generate",
                    "bucket": "credits",
                    "required": 5,
                    "remaining": 0,
                }
            else:  # pragma: no cover - the assertion above is the contract.
                raise AssertionError("reserve must fail when balance is insufficient")
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_ai_rewrite_credit_shortage_returns_402_without_calling_provider(tmp_path):
    from backend.app.api.ai import get_text_ai_client

    class TrapTextAiClient:
        called = False

        def rewrite_note(self, **kwargs):
            self.called = True
            raise AssertionError("provider must not be called when credits are exhausted")

    db_dependency = _override_database(tmp_path)
    trap_client = TrapTextAiClient()
    try:
        registered = _register("rewrite-limit-owner")
        _, service_module = _usage_contract()
        db = next(app.dependency_overrides[get_db]())
        try:
            context = service_module.get_or_create_default_tenant_context(db, registered["user"]["id"])
            service_module.UsageQuotaService(db).adjust_bucket(
                context.tenant.id,
                "credits",
                total=0,
                reason="test exhausts credits",
            )
            draft = AiDraft(user_id=registered["user"]["id"], platform="xhs", title="原标题", body="原正文")
            db.add(draft)
            db.add(
                ModelConfig(
                    user_id=registered["user"]["id"],
                    name="Default Text",
                    model_type="text",
                    provider="openai-compatible",
                    model_name="gpt-quota-test",
                    base_url="https://api.example.test/v1",
                    encrypted_api_key=encrypt_text("sk-test-secret"),
                    is_default=True,
                )
            )
            db.commit()
            draft_id = draft.id
        finally:
            db.close()

        app.dependency_overrides[get_text_ai_client] = lambda: trap_client
        response = client.post(
            "/api/ai/rewrite-note",
            headers={**_auth_headers(registered["access_token"]), "Idempotency-Key": "rewrite-over-limit"},
            json={"draft_id": draft_id, "instruction": "更口语化"},
        )

        assert response.status_code == 402
        assert response.json()["code"] == "usage_quota_insufficient"
        assert response.json()["bucket"] == "credits"
        assert response.json()["required"] == 2
        assert trap_client.called is False
    finally:
        app.dependency_overrides.pop(get_text_ai_client, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_text_generation_endpoints_reserve_and_commit_credits(tmp_path):
    from backend.app.api.ai import get_text_ai_client

    class FakeTextClient:
        def generate_note(self, **kwargs):
            return {"title": "生成标题", "body": "生成正文"}

        def generate_titles(self, **kwargs):
            return ["标题 A", "标题 B"]

        def generate_tags(self, **kwargs):
            return ["低卡", "早餐"]

    db_dependency = _override_database(tmp_path)
    fake_client = FakeTextClient()
    try:
        registered = _register("text-action-owner")
        _, service_module = _usage_contract()
        db = next(app.dependency_overrides[get_db]())
        try:
            context = service_module.get_or_create_default_tenant_context(db, registered["user"]["id"])
            db.add(
                ModelConfig(
                    user_id=registered["user"]["id"],
                    name="Default Text",
                    model_type="text",
                    provider="openai-compatible",
                    model_name="gpt-quota-test",
                    base_url="https://api.example.test/v1",
                    encrypted_api_key=encrypt_text("sk-test-secret"),
                    is_default=True,
                )
            )
            db.commit()
            tenant_id = context.tenant.id
        finally:
            db.close()

        app.dependency_overrides[get_text_ai_client] = lambda: fake_client
        headers = _auth_headers(registered["access_token"])
        assert client.post(
            "/api/ai/generate-note",
            headers={**headers, "Idempotency-Key": "generate-note-1"},
            json={"platform": "xhs", "topic": "低卡早餐", "reference": "参考", "instruction": "具体"},
        ).status_code == 200
        assert client.post(
            "/api/ai/generate-title",
            headers={**headers, "Idempotency-Key": "generate-title-1"},
            json={"title": "旧标题", "body": "正文", "count": 2},
        ).status_code == 200
        assert client.post(
            "/api/ai/generate-tags",
            headers={**headers, "Idempotency-Key": "generate-tags-1"},
            json={"title": "早餐", "body": "正文", "count": 2},
        ).status_code == 200

        balance_response = client.get("/api/usage/balance", headers=headers)
        assert balance_response.status_code == 200
        assert balance_response.json()["buckets"]["credits"]["remaining"] == 94

        db = next(app.dependency_overrides[get_db]())
        try:
            rows = db.scalars(select(UsageLedger).where(UsageLedger.tenant_id == tenant_id).order_by(UsageLedger.id)).all()
            text_ops = [(row.feature_key, row.operation, row.bucket, row.amount) for row in rows if row.bucket == "credits"]
            assert text_ops == [
                ("ai.generate_note", "reserve", "credits", 2),
                ("ai.generate_note.commit", "commit", "credits", 2),
                ("ai.generate_title", "reserve", "credits", 2),
                ("ai.generate_title.commit", "commit", "credits", 2),
                ("ai.generate_tags", "reserve", "credits", 2),
                ("ai.generate_tags.commit", "commit", "credits", 2),
            ]
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_text_ai_client, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_polish_provider_failure_refunds_credits(tmp_path):
    from backend.app.api.ai import get_text_ai_client

    class FailingPolishClient:
        def polish_text(self, **kwargs):
            raise RuntimeError("provider unavailable")

    db_dependency = _override_database(tmp_path)
    try:
        registered = _register("polish-refund-owner")
        db = next(app.dependency_overrides[get_db]())
        try:
            db.add(
                ModelConfig(
                    user_id=registered["user"]["id"],
                    name="Default Text",
                    model_type="text",
                    provider="openai-compatible",
                    model_name="gpt-quota-test",
                    base_url="https://api.example.test/v1",
                    encrypted_api_key=encrypt_text("sk-test-secret"),
                    is_default=True,
                )
            )
            db.commit()
        finally:
            db.close()

        app.dependency_overrides[get_text_ai_client] = lambda: FailingPolishClient()
        response = client.post(
            "/api/ai/polish-text",
            headers={**_auth_headers(registered["access_token"]), "Idempotency-Key": "polish-fails-once"},
            json={"text": "原文", "instruction": "更自然"},
        )

        assert response.status_code == 502
        balance_response = client.get("/api/usage/balance", headers=_auth_headers(registered["access_token"]))
        assert balance_response.status_code == 200
        assert balance_response.json()["buckets"]["credits"]["remaining"] == 100

        db = next(app.dependency_overrides[get_db]())
        try:
            rows = db.scalars(
                select(UsageLedger)
                .where(UsageLedger.user_id == registered["user"]["id"], UsageLedger.bucket == "credits")
                .order_by(UsageLedger.id)
            ).all()
            assert [(row.feature_key, row.operation) for row in rows] == [
                ("ai.polish_text", "reserve"),
                ("ai.polish_text.refund", "refund"),
            ]
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_text_ai_client, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_generate_cover_credit_shortage_returns_402_without_calling_provider(tmp_path):
    from backend.app.api.ai import get_image_ai_client

    class TrapImageClient:
        called = False

        def generate_cover(self, **kwargs):
            self.called = True
            raise AssertionError("provider must not be called when credits are exhausted")

    db_dependency = _override_database(tmp_path)
    trap_client = TrapImageClient()
    try:
        registered = _register("image-limit-owner")
        _, service_module = _usage_contract()
        db = next(app.dependency_overrides[get_db]())
        try:
            context = service_module.get_or_create_default_tenant_context(db, registered["user"]["id"])
            service_module.UsageQuotaService(db).adjust_bucket(
                context.tenant.id,
                "credits",
                total=0,
                reason="test exhausts credits",
            )
            db.add(
                ModelConfig(
                    user_id=registered["user"]["id"],
                    name="Default Image",
                    model_type="image",
                    provider="openai-compatible",
                    model_name="gpt-image-quota-test",
                    base_url="https://api.example.test/v1",
                    encrypted_api_key=encrypt_text("sk-image-secret"),
                    is_default=True,
                )
            )
            db.commit()
        finally:
            db.close()

        app.dependency_overrides[get_image_ai_client] = lambda: trap_client
        response = client.post(
            "/api/ai/images/generate-cover",
            headers={**_auth_headers(registered["access_token"]), "Idempotency-Key": "cover-over-limit"},
            json={"prompt": "做一张封面图", "size": "1024x1024", "style": "clean"},
        )

        assert response.status_code == 402
        assert response.json()["code"] == "usage_quota_insufficient"
        assert response.json()["bucket"] == "credits"
        assert response.json()["required"] == 5
        assert trap_client.called is False
    finally:
        app.dependency_overrides.pop(get_image_ai_client, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_generate_image_success_commits_credits(tmp_path):
    from backend.app.api.ai import get_image_ai_client

    class FakeImageClient:
        def generate_image(self, **kwargs):
            return {"url": "https://example.test/generated.png", "raw": {"ok": True}}

    db_dependency = _override_database(tmp_path)
    try:
        registered = _register("image-success-owner")
        _, service_module = _usage_contract()
        db = next(app.dependency_overrides[get_db]())
        try:
            context = service_module.get_or_create_default_tenant_context(db, registered["user"]["id"])
            db.add(
                ModelConfig(
                    user_id=registered["user"]["id"],
                    name="Default Image",
                    model_type="image",
                    provider="openai-compatible",
                    model_name="gpt-image-quota-test",
                    base_url="https://api.example.test/v1",
                    encrypted_api_key=encrypt_text("sk-image-secret"),
                    is_default=True,
                )
            )
            db.commit()
            tenant_id = context.tenant.id
        finally:
            db.close()

        app.dependency_overrides[get_image_ai_client] = lambda: FakeImageClient()
        response = client.post(
            "/api/ai/images/generate",
            headers={**_auth_headers(registered["access_token"]), "Idempotency-Key": "image-generate-success"},
            json={"prompt": "生成一张配图", "save_to_assets": False, "aspect_ratio": "1:1"},
        )

        assert response.status_code == 200
        assert response.json()["url"] == "https://example.test/generated.png"
        balance_response = client.get("/api/usage/balance", headers=_auth_headers(registered["access_token"]))
        assert balance_response.status_code == 200
        assert balance_response.json()["buckets"]["credits"]["remaining"] == 95

        db = next(app.dependency_overrides[get_db]())
        try:
            rows = db.scalars(
                select(UsageLedger)
                .where(UsageLedger.tenant_id == tenant_id, UsageLedger.bucket == "credits")
                .order_by(UsageLedger.id)
            ).all()
            assert [(row.feature_key, row.operation, row.amount) for row in rows] == [
                ("ai.image_generate", "reserve", 5),
                ("ai.image_generate.commit", "commit", 5),
            ]
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_image_ai_client, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_describe_image_failure_refunds_credits(tmp_path):
    from backend.app.api.ai import get_image_ai_client

    class FailingDescribeClient:
        def describe_image(self, **kwargs):
            raise RuntimeError("vision provider unavailable")

    db_dependency = _override_database(tmp_path)
    try:
        registered = _register("describe-refund-owner")
        db = next(app.dependency_overrides[get_db]())
        try:
            db.add(
                ModelConfig(
                    user_id=registered["user"]["id"],
                    name="Default Image",
                    model_type="image",
                    provider="openai-compatible",
                    model_name="gpt-image-quota-test",
                    base_url="https://api.example.test/v1",
                    encrypted_api_key=encrypt_text("sk-image-secret"),
                    is_default=True,
                )
            )
            db.commit()
        finally:
            db.close()

        app.dependency_overrides[get_image_ai_client] = lambda: FailingDescribeClient()
        response = client.post(
            "/api/ai/images/describe",
            headers={**_auth_headers(registered["access_token"]), "Idempotency-Key": "describe-fails-once"},
            json={"image_url": "https://example.test/image.png", "instruction": "描述卖点"},
        )

        assert response.status_code == 502
        balance_response = client.get("/api/usage/balance", headers=_auth_headers(registered["access_token"]))
        assert balance_response.status_code == 200
        assert balance_response.json()["buckets"]["credits"]["remaining"] == 100

        db = next(app.dependency_overrides[get_db]())
        try:
            rows = db.scalars(
                select(UsageLedger)
                .where(UsageLedger.user_id == registered["user"]["id"], UsageLedger.bucket == "credits")
                .order_by(UsageLedger.id)
            ).all()
            assert [(row.feature_key, row.operation) for row in rows] == [
                ("ai.describe_image", "reserve"),
                ("ai.describe_image.refund", "refund"),
            ]
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_image_ai_client, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_async_image_create_reserves_credits_and_worker_success_commits(tmp_path, monkeypatch):
    from backend.app.api import ai as ai_module
    from backend.app.api.ai import _run_async_image_generate_task, get_image_ai_client

    class FakeImageClient:
        def generate_image(self, **kwargs):
            return {"url": "https://example.test/async-generated.png", "raw": {"ok": True}}

    db_dependency = _override_database(tmp_path)
    fake_client = FakeImageClient()
    try:
        registered = _register("async-image-owner")
        _, service_module = _usage_contract()
        db = next(app.dependency_overrides[get_db]())
        try:
            context = service_module.get_or_create_default_tenant_context(db, registered["user"]["id"])
            model = ModelConfig(
                user_id=registered["user"]["id"],
                name="Default Image",
                model_type="image",
                provider="openai-compatible",
                model_name="gpt-image-quota-test",
                base_url="https://api.example.test/v1",
                encrypted_api_key=encrypt_text("sk-image-secret"),
                is_default=True,
            )
            db.add(model)
            db.commit()
            tenant_id = context.tenant.id
            model_id = model.id
        finally:
            db.close()

        monkeypatch.setattr(ai_module, "SessionLocal", app.dependency_overrides[get_db].sessionmaker)
        app.dependency_overrides[get_image_ai_client] = lambda: fake_client
        response = client.post(
            "/api/ai/images/generate-async",
            headers={**_auth_headers(registered["access_token"]), "Idempotency-Key": "async-image-success"},
            json={"prompt": "异步生成配图", "save_to_assets": False, "aspect_ratio": "1:1"},
        )

        assert response.status_code == 200
        db = next(app.dependency_overrides[get_db]())
        try:
            task = db.get(Task, response.json()["task_id"])
            assert task.status == "completed"
            task_payload = task.payload or {}
            assert task_payload["usage_reservation_id"]
            assert task_payload["feature_key"] == "ai.image_generate_async"
            assert task_payload["usage_bucket"] == "credits"
            rows = db.scalars(
                select(UsageLedger)
                .where(UsageLedger.tenant_id == tenant_id, UsageLedger.bucket == "credits")
                .order_by(UsageLedger.id)
            ).all()
            assert [(row.feature_key, row.operation, row.amount) for row in rows] == [
                ("ai.image_generate_async", "reserve", 5),
                ("ai.image_generate_async.commit", "commit", 5),
            ]
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_image_ai_client, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_async_image_worker_failure_refunds_reserved_quota(tmp_path, monkeypatch):
    from backend.app.api import ai as ai_module
    from backend.app.api.ai import _run_async_image_generate_task, get_image_ai_client

    class FailingImageClient:
        def generate_image(self, **kwargs):
            raise RuntimeError("async provider unavailable")

    db_dependency = _override_database(tmp_path)
    failing_client = FailingImageClient()
    try:
        registered = _register("async-image-refund-owner")
        db = next(app.dependency_overrides[get_db]())
        try:
            model = ModelConfig(
                user_id=registered["user"]["id"],
                name="Default Image",
                model_type="image",
                provider="openai-compatible",
                model_name="gpt-image-quota-test",
                base_url="https://api.example.test/v1",
                encrypted_api_key=encrypt_text("sk-image-secret"),
                is_default=True,
            )
            db.add(model)
            db.commit()
            model_id = model.id
        finally:
            db.close()

        monkeypatch.setattr(ai_module, "SessionLocal", app.dependency_overrides[get_db].sessionmaker)
        app.dependency_overrides[get_image_ai_client] = lambda: failing_client
        response = client.post(
            "/api/ai/images/generate-async",
            headers={**_auth_headers(registered["access_token"]), "Idempotency-Key": "async-image-fails"},
            json={"prompt": "异步失败配图", "save_to_assets": False, "aspect_ratio": "1:1"},
        )
        assert response.status_code == 200
        balance_response = client.get("/api/usage/balance", headers=_auth_headers(registered["access_token"]))
        assert balance_response.status_code == 200
        assert balance_response.json()["buckets"]["credits"]["remaining"] == 100

        db = next(app.dependency_overrides[get_db]())
        try:
            task = db.get(Task, response.json()["task_id"])
            assert task.status == "failed"
            rows = db.scalars(
                select(UsageLedger)
                .where(UsageLedger.user_id == registered["user"]["id"], UsageLedger.bucket == "credits")
                .order_by(UsageLedger.id)
            ).all()
            assert [(row.feature_key, row.operation) for row in rows] == [
                ("ai.image_generate_async", "reserve"),
                ("ai.image_generate_async.refund", "refund"),
            ]
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_image_ai_client, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_async_image_credit_shortage_returns_402_without_creating_task(tmp_path):
    from backend.app.api.ai import get_image_ai_client

    class TrapImageClient:
        called = False

        def generate_image(self, **kwargs):
            self.called = True
            raise AssertionError("provider must not be called when async credits are exhausted")

    db_dependency = _override_database(tmp_path)
    trap_client = TrapImageClient()
    try:
        registered = _register("async-image-limit-owner")
        _, service_module = _usage_contract()
        db = next(app.dependency_overrides[get_db]())
        try:
            context = service_module.get_or_create_default_tenant_context(db, registered["user"]["id"])
            service_module.UsageQuotaService(db).adjust_bucket(context.tenant.id, "credits", total=0, reason="test exhausts async image credits")
            db.add(
                ModelConfig(
                    user_id=registered["user"]["id"],
                    name="Default Image",
                    model_type="image",
                    provider="openai-compatible",
                    model_name="gpt-image-quota-test",
                    base_url="https://api.example.test/v1",
                    encrypted_api_key=encrypt_text("sk-image-secret"),
                    is_default=True,
                )
            )
            db.commit()
        finally:
            db.close()

        app.dependency_overrides[get_image_ai_client] = lambda: trap_client
        response = client.post(
            "/api/ai/images/generate-async",
            headers={**_auth_headers(registered["access_token"]), "Idempotency-Key": "async-image-over-limit"},
            json={"prompt": "异步超额配图", "save_to_assets": False, "aspect_ratio": "1:1"},
        )

        assert response.status_code == 402
        assert response.json()["bucket"] == "credits"
        assert trap_client.called is False
        db = next(app.dependency_overrides[get_db]())
        try:
            assert db.scalars(select(Task).where(Task.user_id == registered["user"]["id"], Task.task_type == "ai_image_generate")).all() == []
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_image_ai_client, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_draft_ai_score_success_commits_credits(tmp_path):
    from backend.app.api.ai import get_text_ai_client

    class FakeDraftScoreClient:
        def complete_json_prompt(self, **kwargs):
            return '{"overall_score":88,"potential_level":"high","summary":"结构清晰。"}'

    db_dependency = _override_database(tmp_path)
    try:
        registered = _register("draft-score-credit-owner")
        _, service_module = _usage_contract()
        db = next(app.dependency_overrides[get_db]())
        try:
            context = service_module.get_or_create_default_tenant_context(db, registered["user"]["id"])
            model = ModelConfig(
                user_id=registered["user"]["id"],
                name="Default Text",
                model_type="text",
                provider="openai-compatible",
                model_name="gpt-score-quota-test",
                base_url="https://api.example.test/v1",
                encrypted_api_key=encrypt_text("sk-score-secret"),
                is_default=True,
            )
            draft = AiDraft(
                user_id=registered["user"]["id"],
                platform="xhs",
                title="低卡早餐怎么搭",
                body="低卡早餐步骤和避坑建议，适合通勤党收藏。" * 8,
            )
            db.add_all([model, draft])
            db.commit()
            tenant_id = context.tenant.id
            draft_id = draft.id
        finally:
            db.close()

        app.dependency_overrides[get_text_ai_client] = lambda: FakeDraftScoreClient()
        response = client.post(
            f"/api/drafts/{draft_id}/ai-score",
            headers={**_auth_headers(registered["access_token"]), "Idempotency-Key": "draft-score-success"},
            json={},
        )

        assert response.status_code == 200
        assert response.json()["overall_score"] == 88
        balance_response = client.get("/api/usage/balance", headers=_auth_headers(registered["access_token"]))
        assert balance_response.status_code == 200
        assert balance_response.json()["buckets"]["credits"]["remaining"] == 98

        db = next(app.dependency_overrides[get_db]())
        try:
            rows = db.scalars(
                select(UsageLedger)
                .where(UsageLedger.tenant_id == tenant_id, UsageLedger.bucket == "credits")
                .order_by(UsageLedger.id)
            ).all()
            assert [(row.feature_key, row.operation, row.amount) for row in rows] == [
                ("draft.ai_score", "reserve", 2),
                ("draft.ai_score.commit", "commit", 2),
            ]
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_text_ai_client, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_model_config_test_allows_three_free_daily_attempts_then_returns_429_without_provider_call(tmp_path, monkeypatch):
    import backend.app.api.model_configs as model_configs_api
    from backend.app.core.time import shanghai_now

    calls = 0

    class FakeResponse:
        status_code = 200
        text = '{"choices":[{"message":{"content":"ok"}}]}'

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    def fake_post(*args, **kwargs):
        nonlocal calls
        calls += 1
        return FakeResponse()

    db_dependency = _override_database(tmp_path)
    try:
        registered = _register("model-test-limit-owner")
        db = next(app.dependency_overrides[get_db]())
        try:
            model = ModelConfig(
                user_id=registered["user"]["id"],
                name="Default Text",
                model_type="text",
                provider="openai-compatible",
                model_name="gpt-model-test-limit",
                base_url="https://api.example.test/v1",
                encrypted_api_key=encrypt_text("sk-model-test-secret"),
                is_default=True,
            )
            db.add(model)
            db.commit()
            config_id = model.id
        finally:
            db.close()

        monkeypatch.setattr(model_configs_api.http_requests, "post", fake_post, raising=False)
        responses = [
            client.post(f"/api/model-configs/{config_id}/test", headers=_auth_headers(registered["access_token"]))
            for _ in range(4)
        ]

        assert [response.status_code for response in responses] == [200, 200, 200, 429]
        assert responses[-1].json()["code"] == "model_test_daily_limit_exceeded"
        assert calls == 3

        db = next(app.dependency_overrides[get_db]())
        try:
            logs = db.scalars(
                select(ApiLog)
                .where(ApiLog.user_id == registered["user"]["id"], ApiLog.endpoint == "model_config.test")
                .order_by(ApiLog.id)
            ).all()
            assert len(logs) == 3
            assert all(log.meta["feature_key"] == "model_test" for log in logs)
            assert db.scalars(select(UsageLedger).where(UsageLedger.bucket == "model_test")).all() == []
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_model_config_test_ignores_previous_day_attempts(tmp_path, monkeypatch):
    import backend.app.api.model_configs as model_configs_api
    from backend.app.core.time import shanghai_now

    calls = 0

    class FakeResponse:
        status_code = 200
        text = '{"choices":[{"message":{"content":"ok"}}]}'

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    def fake_post(*args, **kwargs):
        nonlocal calls
        calls += 1
        return FakeResponse()

    db_dependency = _override_database(tmp_path)
    try:
        registered = _register("model-test-next-day-owner")
        db = next(app.dependency_overrides[get_db]())
        try:
            model = ModelConfig(
                user_id=registered["user"]["id"],
                name="Default Text",
                model_type="text",
                provider="openai-compatible",
                model_name="gpt-model-test-next-day",
                base_url="https://api.example.test/v1",
                encrypted_api_key=encrypt_text("sk-model-test-secret"),
                is_default=True,
            )
            db.add(model)
            db.flush()
            for index in range(3):
                db.add(
                    ApiLog(
                        user_id=registered["user"]["id"],
                        platform="ai",
                        endpoint="model_config.test",
                        status="success",
                        meta={"feature_key": "model_test", "model_config_id": model.id, "attempt": index + 1},
                        created_at=shanghai_now() - timedelta(days=1),
                    )
                )
            db.commit()
            config_id = model.id
        finally:
            db.close()

        monkeypatch.setattr(model_configs_api.http_requests, "post", fake_post, raising=False)
        response = client.post(f"/api/model-configs/{config_id}/test", headers=_auth_headers(registered["access_token"]))

        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert calls == 1
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_draft_ai_score_credit_shortage_returns_402_without_calling_provider(tmp_path):
    from backend.app.api.ai import get_text_ai_client

    class TrapDraftScoreClient:
        called = False

        def complete_json_prompt(self, **kwargs):
            self.called = True
            raise AssertionError("provider must not be called when credits are exhausted")

    db_dependency = _override_database(tmp_path)
    trap_client = TrapDraftScoreClient()
    try:
        registered = _register("draft-score-limit-owner")
        _, service_module = _usage_contract()
        db = next(app.dependency_overrides[get_db]())
        try:
            context = service_module.get_or_create_default_tenant_context(db, registered["user"]["id"])
            service_module.UsageQuotaService(db).adjust_bucket(
                context.tenant.id,
                "credits",
                total=0,
                reason="test exhausts credits",
            )
            model = ModelConfig(
                user_id=registered["user"]["id"],
                name="Default Text",
                model_type="text",
                provider="openai-compatible",
                model_name="gpt-score-quota-test",
                base_url="https://api.example.test/v1",
                encrypted_api_key=encrypt_text("sk-score-secret"),
                is_default=True,
            )
            draft = AiDraft(user_id=registered["user"]["id"], platform="xhs", title="草稿标题", body="草稿正文" * 50)
            db.add_all([model, draft])
            db.commit()
            draft_id = draft.id
        finally:
            db.close()

        app.dependency_overrides[get_text_ai_client] = lambda: trap_client
        response = client.post(
            f"/api/drafts/{draft_id}/ai-score",
            headers={**_auth_headers(registered["access_token"]), "Idempotency-Key": "draft-score-over-limit"},
            json={},
        )

        assert response.status_code == 402
        assert response.json()["bucket"] == "credits"
        assert response.json()["required"] == 2
        assert trap_client.called is False
    finally:
        app.dependency_overrides.pop(get_text_ai_client, None)
        app.dependency_overrides.pop(db_dependency, None)

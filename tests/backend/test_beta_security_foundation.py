from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

from backend.app.api import files as files_api
from backend.app.core.database import Base, get_db
from backend.app.core.security import encrypt_text
from backend.app.main import app
from backend.app.models import (
    AccountCookieVersion,
    Note,
    PlatformAccount,
    PublishJob,
    UsageLedger,
)
from test_support.beta_invites import create_test_invite_code
from test_support.model_capabilities import bind_test_model_capability

client = TestClient(app)


def _override_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'beta-security-test.db'}", connect_args={"check_same_thread": False})
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


def _register(username: str) -> dict:
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": "secret123", "invite_code": create_test_invite_code()},
    )
    assert response.status_code == 200
    return response.json()


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _use_temp_media_dir(tmp_path, monkeypatch):
    storage_dir = tmp_path / "storage"
    monkeypatch.setattr(files_api, "get_settings", lambda: SimpleNamespace(storage_dir=storage_dir))
    return storage_dir


def _upload_png(token: str) -> dict:
    response = client.post(
        "/api/files/upload",
        headers=_auth_headers(token),
        files={"file": ("sample.png", b"\x89PNG\r\n\x1a\n" + b"0" * 128, "image/png")},
    )
    assert response.status_code == 200
    return response.json()


def test_media_download_urls_are_signed_and_required(tmp_path, monkeypatch):
    db_dependency = _override_database(tmp_path)
    _use_temp_media_dir(tmp_path, monkeypatch)
    try:
        owner = _register("media-owner")
        uploaded = _upload_png(owner["access_token"])

        assert "token=" in uploaded["download_url"]
        bare_url = f"/api/files/media/{uploaded['file_name']}"

        no_token_response = client.get(bare_url)
        assert no_token_response.status_code in {403, 404}

        signed_response = client.get(uploaded["download_url"])
        assert signed_response.status_code == 200
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_signed_media_token_cannot_be_reused_for_another_file(tmp_path, monkeypatch):
    db_dependency = _override_database(tmp_path)
    _use_temp_media_dir(tmp_path, monkeypatch)
    try:
        owner = _register("token-owner")
        first = _upload_png(owner["access_token"])
        second = _upload_png(owner["access_token"])
        first_token = first["download_url"].split("token=", 1)[1]

        swapped_response = client.get(f"/api/files/media/{second['file_name']}?token={first_token}")
        assert swapped_response.status_code in {403, 404}
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_other_user_cannot_reference_owner_media_in_publish_note_or_creator_upload(tmp_path, monkeypatch):
    from backend.app.api.platforms.xhs import creator as creator_api

    db_dependency = _override_database(tmp_path)
    _use_temp_media_dir(tmp_path, monkeypatch)
    try:
        owner = _register("media-reference-owner")
        intruder = _register("media-reference-intruder")
        uploaded = _upload_png(owner["access_token"])
        owner_media_path = f"/api/files/media/{uploaded['file_name']}"

        db = next(app.dependency_overrides[get_db]())
        try:
            intruder_id = intruder["user"]["id"]
            account = PlatformAccount(user_id=intruder_id, platform="xhs", sub_type="creator", nickname="creator", status="active")
            db.add(account)
            db.flush()
            db.add(AccountCookieVersion(platform_account_id=account.id, encrypted_cookies=encrypt_text("a1=test")))
            note = Note(
                user_id=intruder_id,
                platform_account_id=account.id,
                platform="xhs",
                note_id="intruder-note",
                title="intruder",
                content="body",
                author_name="author",
            )
            job = PublishJob(
                user_id=intruder_id,
                platform_account_id=account.id,
                platform="xhs",
                title="publish",
                body="body",
                publish_mode="immediate",
                status="pending",
            )
            db.add_all([note, job])
            db.commit()
            account_id = account.id
            note_id = note.id
            job_id = job.id
        finally:
            db.close()

        headers = _auth_headers(intruder["access_token"])
        publish_response = client.post(
            f"/api/publish/jobs/{job_id}/assets",
            headers=headers,
            json={"asset_type": "image", "file_path": owner_media_path},
        )
        assert publish_response.status_code in {400, 403, 404}

        note_response = client.post(
            f"/api/notes/{note_id}/assets",
            headers=headers,
            json={"asset_type": "image", "local_path": uploaded["file_name"]},
        )
        assert note_response.status_code in {400, 403, 404}

        class TrapCreatorAdapter:
            called = False

            def __init__(self, cookies: str):
                self.cookies = cookies

            def upload_media(self, file_path: str, media_type: str):
                self.called = True
                raise AssertionError("creator upload adapter must not receive another user's media path")

        app.dependency_overrides[creator_api.get_creator_api_adapter_factory] = lambda: TrapCreatorAdapter
        creator_response = client.post(
            "/api/xhs/creator/assets/upload",
            headers=headers,
            json={"account_id": account_id, "file_path": owner_media_path, "media_type": "image"},
        )
        assert creator_response.status_code in {400, 403, 404}
        assert TrapCreatorAdapter.called is False
    finally:
        app.dependency_overrides.pop(creator_api.get_creator_api_adapter_factory, None)
        app.dependency_overrides.pop(db_dependency, None)


def test_usage_reservation_commit_and_refund_are_terminal(tmp_path):
    from backend.app.services.usage_quota_service import UsageQuotaService, get_or_create_default_tenant_context

    db_dependency = _override_database(tmp_path)
    try:
        registered = _register("terminal-ledger-owner")
        db = next(app.dependency_overrides[get_db]())
        try:
            context = get_or_create_default_tenant_context(db, registered["user"]["id"])
            service = UsageQuotaService(db)
            reservation = service.reserve(
                tenant_id=context.tenant.id,
                user_id=registered["user"]["id"],
                feature_key="ai.rewrite_note",
                bucket="credits",
                amount=2,
                idempotency_key="terminal-reservation",
            )

            committed = service.commit(reservation.id)
            assert committed.status == "committed"
            with pytest.raises(ValueError):
                service.refund(reservation.id, failure_reason="must not refund after commit")
            assert service.get_balance(context.tenant.id)["credits"].remaining == 98
            rows = db.scalars(select(UsageLedger).where(UsageLedger.reservation_id == reservation.id).order_by(UsageLedger.id)).all()
            assert [row.operation for row in rows] == ["commit"]
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_usage_reserve_hashes_long_idempotency_keys_and_does_not_store_prompt_text(tmp_path):
    from backend.app.services.usage_quota_service import UsageQuotaService, get_or_create_default_tenant_context

    db_dependency = _override_database(tmp_path)
    try:
        registered = _register("hash-ledger-owner")
        db = next(app.dependency_overrides[get_db]())
        try:
            context = get_or_create_default_tenant_context(db, registered["user"]["id"])
            service = UsageQuotaService(db)
            long_prompt = "敏感提示词" * 80
            reservation = service.reserve(
                tenant_id=context.tenant.id,
                user_id=registered["user"]["id"],
                feature_key="ai.generate_title",
                bucket="credits",
                amount=2,
                idempotency_key=f"ai.generate_title:{registered['user']['id']}:{long_prompt}",
                request_summary={"body_length": len(long_prompt)},
            )

            assert len(reservation.idempotency_key) <= 160
            assert "敏感提示词" not in reservation.idempotency_key
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_inactive_usage_bucket_cannot_reserve(tmp_path):
    from backend.app.services.usage_quota_service import UsageQuotaService, get_or_create_default_tenant_context

    db_dependency = _override_database(tmp_path)
    try:
        registered = _register("inactive-bucket-owner")
        db = next(app.dependency_overrides[get_db]())
        try:
            context = get_or_create_default_tenant_context(db, registered["user"]["id"])
            service = UsageQuotaService(db)
            account = service._get_account(context.tenant.id, "credits")
            account.status = "inactive"
            db.commit()

            with pytest.raises(ValueError):
                service.reserve(
                    tenant_id=context.tenant.id,
                    user_id=registered["user"]["id"],
                    feature_key="ai.image_generate",
                    bucket="credits",
                    amount=5,
                    idempotency_key="inactive-bucket",
                )
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_async_image_asset_save_failure_refunds_reserved_quota(tmp_path, monkeypatch):
    from backend.app.api import ai as ai_module
    from backend.app.api.ai import get_image_ai_client

    class FakeImageClient:
        def generate_image(self, **kwargs):
            return {"url": "https://example.test/generated.png", "raw": {"ok": True}}

    def failing_create_generated_image_asset(**kwargs):
        raise ValueError("asset import failed")

    db_dependency = _override_database(tmp_path)
    try:
        registered = _register("async-asset-failure-owner")
        db = next(app.dependency_overrides[get_db]())
        try:
            config = __import__("backend.app.models", fromlist=["ModelConfig"]).ModelConfig(
                user_id=registered["user"]["id"],
                name="Default Image",
                model_type="image",
                provider="openai-compatible",
                model_name="gpt-image-quota-test",
                base_url="https://api.example.test/v1",
                encrypted_api_key=encrypt_text("sk-image-secret"),
                is_default=True,
            )
            bind_test_model_capability(db, config=config, capability="image_generation")
            db.commit()
        finally:
            db.close()

        monkeypatch.setattr(ai_module, "SessionLocal", app.dependency_overrides[get_db].sessionmaker)
        monkeypatch.setattr(ai_module, "_create_generated_image_asset", failing_create_generated_image_asset)
        app.dependency_overrides[get_image_ai_client] = lambda: FakeImageClient()
        response = client.post(
            "/api/ai/images/generate-async",
            headers={**_auth_headers(registered["access_token"]), "Idempotency-Key": "async-asset-save-fails"},
            json={"prompt": "异步保存失败配图", "save_to_assets": True, "aspect_ratio": "1:1"},
        )
        assert response.status_code == 200

        balance_response = client.get("/api/usage/balance", headers=_auth_headers(registered["access_token"]))
        assert balance_response.status_code == 200
        assert balance_response.json()["buckets"]["credits"]["remaining"] == 100

        db = next(app.dependency_overrides[get_db]())
        try:
            rows = db.scalars(select(UsageLedger).where(UsageLedger.user_id == registered["user"]["id"], UsageLedger.bucket == "credits").order_by(UsageLedger.id)).all()
            assert [(row.feature_key, row.operation) for row in rows] == [
                ("ai.image_generate_async", "reserve"),
                ("ai.image_generate_async.refund", "refund"),
            ]
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_image_ai_client, None)
        app.dependency_overrides.pop(db_dependency, None)

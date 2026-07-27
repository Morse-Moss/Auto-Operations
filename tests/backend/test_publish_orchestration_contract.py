from __future__ import annotations

import json
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.api import publish as publish_api
from backend.app.core.database import Base, get_db
from backend.app.core.security import create_access_token, encrypt_text, hash_password
from backend.app.core.time import shanghai_now
from backend.app.main import app
from backend.app.models import AccountCookieVersion, PlatformAccount, PublishAsset, PublishJob, User
from backend.app.services.publish_orchestration_service import PublishOrchestrationService
from backend.app.services.scheduler_service import run_due_publish_jobs

client = TestClient(app)


class TrapCreatorAdapter:
    init_called = False
    upload_called = False
    post_called = False

    def __init__(self, cookies: str) -> None:
        TrapCreatorAdapter.init_called = True
        self.cookies = cookies

    def upload_media(self, file_path: str, media_type: str) -> dict:
        TrapCreatorAdapter.upload_called = True
        raise AssertionError("dry-run must not upload media")

    def post_note(self, note_info: dict) -> dict:
        TrapCreatorAdapter.post_called = True
        raise AssertionError("dry-run or unconfirmed publish must not post notes")


class CallableTrapAdapterFactory:
    called = False

    def __call__(self):
        CallableTrapAdapterFactory.called = True
        return TrapCreatorAdapter


def _reset_traps() -> None:
    TrapCreatorAdapter.init_called = False
    TrapCreatorAdapter.upload_called = False
    TrapCreatorAdapter.post_called = False
    CallableTrapAdapterFactory.called = False


def _override_database(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'publish-orchestration-contract.db'}",
        connect_args={"check_same_thread": False},
    )
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


def _override_adapter():
    _reset_traps()
    factory = CallableTrapAdapterFactory()
    app.dependency_overrides[publish_api.get_creator_publish_adapter_factory] = factory
    return publish_api.get_creator_publish_adapter_factory


def _create_user(db, username: str = "publish-orchestration-user") -> User:
    user = User(username=username, password_hash=hash_password("secret123"))
    db.add(user)
    db.flush()
    return user


def _auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def _create_account(db, user: User, *, platform: str = "xhs", sub_type: str | None = "creator") -> PlatformAccount:
    account = PlatformAccount(
        user_id=user.id,
        platform=platform,
        sub_type=sub_type,
        external_user_id=f"{platform}-{user.id}",
        nickname=f"{platform} Account",
        status="active",
    )
    db.add(account)
    db.flush()
    db.add(
        AccountCookieVersion(
            platform_account_id=account.id,
            encrypted_cookies=encrypt_text(json.dumps({"a1": "a1", "web_session": "session"})),
        )
    )
    db.flush()
    return account


def _create_job(
    db,
    user: User,
    account: PlatformAccount | None,
    *,
    platform: str = "xhs",
    title: str = "Dry-run title",
    body: str = "Dry-run body",
    publish_mode: str = "immediate",
    scheduled_at=None,
    status: str = "pending",
) -> PublishJob:
    job = PublishJob(
        user_id=user.id,
        platform_account_id=account.id if account else None,
        platform=platform,
        title=title,
        body=body,
        publish_mode=publish_mode,
        scheduled_at=scheduled_at,
        status=status,
    )
    db.add(job)
    db.flush()
    return job


def _add_asset(
    db,
    job: PublishJob,
    *,
    asset_type: str = "image",
    upload_status: str = "pending",
    file_path: str | None = None,
) -> PublishAsset:
    asset = PublishAsset(
        publish_job_id=job.id,
        asset_type=asset_type,
        file_path=file_path or f"/api/files/media/{asset_type}-{job.id}.jpg",
        upload_status=upload_status,
        creator_media_id="",
        creator_upload_info="{}",
    )
    db.add(asset)
    db.flush()
    return asset


def _check_codes(result: dict) -> set[str]:
    return {check["code"] for check in result["checks"]}


def _checks_by_code(result: dict) -> dict[str, dict]:
    return {check["code"]: check for check in result["checks"]}


def test_xhs_dry_run_validates_local_state_without_upload_or_post(tmp_path):
    _reset_traps()
    _, TestingSessionLocal = _override_database(tmp_path)
    try:
        with TestingSessionLocal() as db:
            user = _create_user(db)
            account = _create_account(db, user)
            job = _create_job(db, user, account)
            asset = _add_asset(db, job, upload_status="pending")
            db.commit()
            job_id = job.id
            asset_id = asset.id

            result = PublishOrchestrationService(db).dry_run(job_id=job_id, current_user=user)

            assert result["job_id"] == job_id
            assert result["ok"] is True
            assert result["publish_blocked"] is True
            assert result["policy"]["allowed"] is True
            assert _checks_by_code(result)["policy"]["status"] == "passed"
            assert _checks_by_code(result)["title_required"]["status"] == "passed"
            assert _checks_by_code(result)["asset_required"]["status"] == "passed"
            assert result["diagnostics"] == []

            persisted_job = db.get(PublishJob, job_id)
            persisted_asset = db.get(PublishAsset, asset_id)
            assert persisted_job.status == "pending"
            assert persisted_asset.upload_status == "pending"
            assert TrapCreatorAdapter.init_called is False
            assert TrapCreatorAdapter.upload_called is False
            assert TrapCreatorAdapter.post_called is False
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_xhs_dry_run_reports_blocking_checks_without_mutating_job_or_assets(tmp_path):
    _, TestingSessionLocal = _override_database(tmp_path)
    try:
        with TestingSessionLocal() as db:
            user = _create_user(db, "publish-orchestration-invalid-user")
            account = _create_account(db, user)
            missing_asset_job = _create_job(
                db,
                user,
                account,
                title="   ",
                body="",
                publish_mode="scheduled",
                scheduled_at=shanghai_now() - timedelta(minutes=5),
                status="failed",
            )
            video_job = _create_job(db, user, account, title="Video job")
            video_asset = _add_asset(db, video_job, asset_type="video", upload_status="pending")
            db.commit()
            missing_asset_job_id = missing_asset_job.id
            video_job_id = video_job.id
            video_asset_id = video_asset.id

            missing_asset_result = PublishOrchestrationService(db).dry_run(
                job_id=missing_asset_job_id,
                current_user=user,
            )
            video_result = PublishOrchestrationService(db).dry_run(job_id=video_job_id, current_user=user)

            missing_checks = _checks_by_code(missing_asset_result)
            assert missing_asset_result["ok"] is False
            assert missing_checks["title_required"]["status"] == "blocked"
            assert missing_checks["asset_required"]["status"] == "blocked"
            assert missing_checks["body"]["status"] == "warning"
            assert missing_checks["scheduled_at_future"]["status"] == "blocked"

            video_checks = _checks_by_code(video_result)
            assert video_result["ok"] is False
            assert video_checks["video_unsupported"]["status"] == "blocked"
            assert video_checks["asset_required"]["status"] == "blocked"

            persisted_missing_job = db.get(PublishJob, missing_asset_job_id)
            persisted_video_asset = db.get(PublishAsset, video_asset_id)
            assert persisted_missing_job.status == "failed"
            assert persisted_video_asset.upload_status == "pending"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_planned_platform_dry_run_fails_closed_before_adapter_use(tmp_path):
    _reset_traps()
    _, TestingSessionLocal = _override_database(tmp_path)
    try:
        with TestingSessionLocal() as db:
            user = _create_user(db, "publish-orchestration-wechat-user")
            account = _create_account(db, user, platform="wechat_official", sub_type=None)
            job = _create_job(db, user, account, platform="wechat_official")
            _add_asset(db, job, upload_status="pending")
            db.commit()
            job_id = job.id

            result = PublishOrchestrationService(db).dry_run(job_id=job_id, current_user=user)

            assert result["ok"] is False
            assert result["publish_blocked"] is True
            assert result["policy"]["allowed"] is False
            assert result["policy"]["blocked_reason"] == "platform_planned"
            assert _checks_by_code(result)["policy"]["status"] == "blocked"
            assert TrapCreatorAdapter.init_called is False
            assert TrapCreatorAdapter.upload_called is False
            assert TrapCreatorAdapter.post_called is False
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_dry_run_endpoint_returns_contract_without_adapter_side_effects(tmp_path):
    get_db_override, TestingSessionLocal = _override_database(tmp_path)
    adapter_override = _override_adapter()
    try:
        with TestingSessionLocal() as db:
            user = _create_user(db, "publish-orchestration-endpoint-user")
            account = _create_account(db, user)
            job = _create_job(db, user, account)
            asset = _add_asset(db, job, upload_status="pending")
            db.commit()
            job_id = job.id
            asset_id = asset.id
            headers = _auth_headers(user)

        response = client.post(f"/api/publish/jobs/{job_id}/dry-run", headers=headers)

        assert response.status_code == 200
        payload = response.json()
        assert payload["job_id"] == job_id
        assert payload["ok"] is True
        assert payload["publish_blocked"] is True
        assert CallableTrapAdapterFactory.called is False
        assert TrapCreatorAdapter.init_called is False
        assert TrapCreatorAdapter.upload_called is False
        assert TrapCreatorAdapter.post_called is False
        with TestingSessionLocal() as db:
            persisted_job = db.get(PublishJob, job_id)
            persisted_asset = db.get(PublishAsset, asset_id)
            assert persisted_job.status == "pending"
            assert persisted_asset.upload_status == "pending"
    finally:
        app.dependency_overrides.pop(get_db_override, None)
        app.dependency_overrides.pop(adapter_override, None)


def test_app_draft_handoff_requires_mobile_confirmation_without_adapter_side_effects(tmp_path):
    get_db_override, TestingSessionLocal = _override_database(tmp_path)
    adapter_override = _override_adapter()
    try:
        with TestingSessionLocal() as db:
            user = _create_user(db, "publish-app-draft-handoff-user")
            account = _create_account(db, user)
            job = _create_job(db, user, account, title="App draft handoff title", body="Draft body")
            asset = _add_asset(
                db,
                job,
                upload_status="pending",
                file_path=f"/api/files/media/xhs-upload-u{user.id}-draft.jpg",
            )
            db.commit()
            job_id = job.id
            asset_id = asset.id
            headers = _auth_headers(user)

        response = client.post(f"/api/publish/jobs/{job_id}/app-draft-handoff", headers=headers)

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "requires_mobile_app_handoff"
        assert payload["draft_saved"] is False
        assert payload["real_publish_blocked"] is True
        assert payload["handoff"]["title"] == "App draft handoff title"
        assert payload["handoff"]["body"] == "Draft body"
        assert payload["handoff"]["assets"][0]["file_path"] == f"/api/files/media/xhs-upload-u{user.id}-draft.jpg"
        assert payload["verification"]["requires_user_app_check"] is True
        assert "App" in payload["verification"]["acceptance"]
        assert payload["verification"]["verification_code"] in payload["handoff"]["suggested_test_title"]
        assert CallableTrapAdapterFactory.called is False
        assert TrapCreatorAdapter.init_called is False
        assert TrapCreatorAdapter.upload_called is False
        assert TrapCreatorAdapter.post_called is False
        with TestingSessionLocal() as db:
            persisted_job = db.get(PublishJob, job_id)
            persisted_asset = db.get(PublishAsset, asset_id)
            assert persisted_job.status == "pending"
            assert persisted_job.external_note_id == ""
            assert persisted_asset.upload_status == "pending"
    finally:
        app.dependency_overrides.pop(get_db_override, None)
        app.dependency_overrides.pop(adapter_override, None)


def test_real_publish_without_confirmation_returns_403_before_adapter_instantiation(tmp_path):
    get_db_override, TestingSessionLocal = _override_database(tmp_path)
    adapter_override = _override_adapter()
    try:
        with TestingSessionLocal() as db:
            user = _create_user(db, "publish-orchestration-unconfirmed-user")
            account = _create_account(db, user)
            job = _create_job(db, user, account)
            _add_asset(db, job, upload_status="uploaded")
            db.commit()
            job_id = job.id
            headers = _auth_headers(user)

        response = client.post(f"/api/publish/jobs/{job_id}/publish", headers=headers)

        assert response.status_code == 403
        assert response.json()["detail"] == "真实小红书发布需要显式确认"
        assert TrapCreatorAdapter.init_called is False
        assert TrapCreatorAdapter.upload_called is False
        assert TrapCreatorAdapter.post_called is False
        with TestingSessionLocal() as db:
            job = db.get(PublishJob, job_id)
            assert job.status == "pending"
            assert job.external_note_id == ""
    finally:
        app.dependency_overrides.pop(get_db_override, None)
        app.dependency_overrides.pop(adapter_override, None)


def test_asset_upload_refuses_already_claimed_asset_before_adapter_instantiation(tmp_path):
    get_db_override, TestingSessionLocal = _override_database(tmp_path)
    adapter_override = _override_adapter()
    try:
        with TestingSessionLocal() as db:
            user = _create_user(db, "publish-orchestration-uploading-asset-user")
            account = _create_account(db, user)
            job = _create_job(db, user, account)
            asset = _add_asset(
                db,
                job,
                upload_status="uploading",
                file_path=f"/api/files/media/xhs-upload-u{user.id}-already-uploading.jpg",
            )
            db.commit()
            asset_id = asset.id
            headers = _auth_headers(user)

        response = client.post(f"/api/publish/assets/{asset_id}/upload", headers=headers)

        assert response.status_code == 409
        assert response.json()["detail"] == "Publish asset is already being uploaded"
        assert TrapCreatorAdapter.init_called is False
        assert TrapCreatorAdapter.upload_called is False
        assert TrapCreatorAdapter.post_called is False
        with TestingSessionLocal() as db:
            asset = db.get(PublishAsset, asset_id)
            assert asset.upload_status == "uploading"
            assert asset.creator_media_id == ""
    finally:
        app.dependency_overrides.pop(get_db_override, None)
        app.dependency_overrides.pop(adapter_override, None)


def test_scheduler_refuses_already_claimed_due_job_before_adapter_instantiation(tmp_path):
    _reset_traps()
    _, TestingSessionLocal = _override_database(tmp_path)
    try:
        with TestingSessionLocal() as db:
            user = _create_user(db, "publish-orchestration-scheduler-claimed-user")
            account = _create_account(db, user)
            job = _create_job(
                db,
                user,
                account,
                publish_mode="scheduled",
                scheduled_at=shanghai_now() - timedelta(minutes=1),
                status="publishing",
            )
            _add_asset(db, job, upload_status="uploaded", file_path="/api/files/media/already-uploaded.jpg")
            db.commit()
            job_id = job.id

            result = run_due_publish_jobs(
                db=db,
                current_user=user,
                now=shanghai_now(),
                platform="xhs",
                adapter_factory=TrapCreatorAdapter,
            )

            assert result["executed_count"] == 0
            assert result["failed_count"] == 0
            assert result["items"] == []
            assert TrapCreatorAdapter.init_called is False
            assert TrapCreatorAdapter.upload_called is False
            assert TrapCreatorAdapter.post_called is False
            job = db.get(PublishJob, job_id)
            assert job.status == "publishing"
            assert job.external_note_id == ""
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_scheduler_claims_due_job_before_adapter_instantiation(tmp_path):
    _reset_traps()
    _, TestingSessionLocal = _override_database(tmp_path)
    try:
        with TestingSessionLocal() as db:
            user = _create_user(db, "publish-orchestration-scheduler-claim-user")
            account = _create_account(db, user)
            job = _create_job(
                db,
                user,
                account,
                publish_mode="scheduled",
                scheduled_at=shanghai_now() - timedelta(minutes=1),
                status="pending",
            )
            _add_asset(
                db,
                job,
                upload_status="uploaded",
                file_path=f"/api/files/media/xhs-upload-u{user.id}-uploaded.jpg",
            ).creator_upload_info = json.dumps({"fileIds": ["file-id"], "height": 100, "width": 100})
            db.commit()
            job_id = job.id

            def adapter_factory(_cookies: str):
                claimed_job = db.get(PublishJob, job_id)
                assert claimed_job.status == "publishing"
                return TrapCreatorAdapter(_cookies)

            result = run_due_publish_jobs(
                db=db,
                current_user=user,
                now=shanghai_now(),
                platform="xhs",
                adapter_factory=adapter_factory,
            )

            assert result["executed_count"] == 1
            assert result["failed_count"] == 1
            assert TrapCreatorAdapter.init_called is True
            assert TrapCreatorAdapter.post_called is True
            job = db.get(PublishJob, job_id)
            assert job.status == "failed"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_real_publish_refuses_already_claimed_job_before_adapter_instantiation(tmp_path):
    get_db_override, TestingSessionLocal = _override_database(tmp_path)
    adapter_override = _override_adapter()
    try:
        with TestingSessionLocal() as db:
            user = _create_user(db, "publish-orchestration-claimed-user")
            account = _create_account(db, user)
            job = _create_job(db, user, account, status="publishing")
            _add_asset(db, job, upload_status="uploaded")
            db.commit()
            job_id = job.id
            headers = _auth_headers(user)

        response = client.post(f"/api/publish/jobs/{job_id}/publish?confirm_real_publish=true", headers=headers)

        assert response.status_code == 409
        assert response.json()["detail"] == "Publish job is already being processed"
        assert TrapCreatorAdapter.init_called is False
        assert TrapCreatorAdapter.upload_called is False
        assert TrapCreatorAdapter.post_called is False
        with TestingSessionLocal() as db:
            job = db.get(PublishJob, job_id)
            assert job.status == "publishing"
            assert job.external_note_id == ""
    finally:
        app.dependency_overrides.pop(get_db_override, None)
        app.dependency_overrides.pop(adapter_override, None)

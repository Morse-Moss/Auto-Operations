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

client = TestClient(app)


class FakeCreatorPublishAdapter:
    post_note_called = False

    def __init__(self, cookies: str) -> None:
        self.cookies = cookies

    def upload_media(self, file_path: str, media_type: str) -> dict:
        raise AssertionError("upload_media should not be called for pre-uploaded assets")

    def post_note(self, note_info: dict) -> dict:
        FakeCreatorPublishAdapter.post_note_called = True
        return {"success": True, "data": {"note_id": "fake-note-id"}}


def _override_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'publish-confirmation-test.db'}", connect_args={"check_same_thread": False})
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
    FakeCreatorPublishAdapter.post_note_called = False
    app.dependency_overrides[publish_api.get_creator_publish_adapter_factory] = lambda: FakeCreatorPublishAdapter
    return publish_api.get_creator_publish_adapter_factory


def _create_user(db, username: str) -> User:
    user = User(username=username, password_hash=hash_password("secret123"))
    db.add(user)
    db.flush()
    return user


def _auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def _create_creator_account(db, user: User) -> PlatformAccount:
    account = PlatformAccount(
        user_id=user.id,
        platform="xhs",
        sub_type="creator",
        external_user_id=f"creator-{user.id}",
        nickname="Creator Account",
        status="active",
    )
    db.add(account)
    db.flush()
    db.add(AccountCookieVersion(platform_account_id=account.id, encrypted_cookies=encrypt_text(json.dumps({"a1": "a1", "web_session": "session"}))))
    db.flush()
    return account


def _create_uploaded_publish_job(db, user: User, account: PlatformAccount, *, scheduled: bool = False) -> PublishJob:
    job = PublishJob(
        user_id=user.id,
        platform_account_id=account.id,
        platform="xhs",
        title="真实发布确认测试",
        body="发布正文",
        publish_mode="scheduled" if scheduled else "immediate",
        scheduled_at=shanghai_now() - timedelta(minutes=1) if scheduled else None,
        status="pending",
    )
    db.add(job)
    db.flush()
    db.add(
        PublishAsset(
            publish_job_id=job.id,
            asset_type="image",
            file_path="/api/files/media/already-uploaded.jpg",
            upload_status="uploaded",
            creator_media_id="file-1",
            creator_upload_info=json.dumps({"fileIds": "file-1", "width": 800, "height": 600}, ensure_ascii=False),
        )
    )
    db.commit()
    db.refresh(job)
    return job


def test_publish_job_requires_explicit_real_publish_confirmation(tmp_path):
    get_db_override, TestingSessionLocal = _override_database(tmp_path)
    adapter_override = _override_adapter()
    try:
        with TestingSessionLocal() as db:
            user = _create_user(db, "publish-confirmation-user")
            account = _create_creator_account(db, user)
            job = _create_uploaded_publish_job(db, user, account)
            job_id = job.id
            headers = _auth_headers(user)

        response = client.post(f"/api/publish/jobs/{job_id}/publish", headers=headers)

        assert response.status_code == 403
        assert response.json()["detail"] == "真实小红书发布需要显式确认"
        assert FakeCreatorPublishAdapter.post_note_called is False
        with TestingSessionLocal() as db:
            job = db.get(PublishJob, job_id)
            assert job is not None
            assert job.status == "pending"
            assert job.external_note_id == ""
    finally:
        app.dependency_overrides.pop(get_db_override, None)
        app.dependency_overrides.pop(adapter_override, None)


def test_run_due_tasks_requires_explicit_real_publish_confirmation(tmp_path):
    get_db_override, TestingSessionLocal = _override_database(tmp_path)
    adapter_override = _override_adapter()
    try:
        with TestingSessionLocal() as db:
            user = _create_user(db, "run-due-confirmation-user")
            account = _create_creator_account(db, user)
            job = _create_uploaded_publish_job(db, user, account, scheduled=True)
            job_id = job.id
            headers = _auth_headers(user)

        response = client.post("/api/tasks/run-due?platform=xhs", headers=headers)

        assert response.status_code == 403
        assert response.json()["detail"] == "真实小红书发布需要显式确认"
        assert FakeCreatorPublishAdapter.post_note_called is False
        with TestingSessionLocal() as db:
            job = db.get(PublishJob, job_id)
            assert job is not None
            assert job.status == "pending"
            assert job.external_note_id == ""
    finally:
        app.dependency_overrides.pop(get_db_override, None)
        app.dependency_overrides.pop(adapter_override, None)


def test_publish_job_with_confirmation_can_call_creator_adapter(tmp_path):
    get_db_override, TestingSessionLocal = _override_database(tmp_path)
    adapter_override = _override_adapter()
    try:
        with TestingSessionLocal() as db:
            user = _create_user(db, "publish-confirmed-user")
            account = _create_creator_account(db, user)
            job = _create_uploaded_publish_job(db, user, account)
            job_id = job.id
            headers = _auth_headers(user)

        response = client.post(f"/api/publish/jobs/{job_id}/publish?confirm_real_publish=true", headers=headers)

        assert response.status_code == 200
        assert response.json()["status"] == "published"
        assert FakeCreatorPublishAdapter.post_note_called is True
    finally:
        app.dependency_overrides.pop(get_db_override, None)
        app.dependency_overrides.pop(adapter_override, None)

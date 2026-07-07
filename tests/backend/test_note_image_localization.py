from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import Base, get_db
from backend.app.core.security import create_access_token, hash_password
from backend.app.main import app
from backend.app.models import Note, NoteAsset, PlatformAccount, User


client = TestClient(app)


def override_database(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'note-image-localization-test.db'}",
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
    return TestingSessionLocal


def create_user_headers(SessionLocal, username: str = "image-localizer"):
    db = SessionLocal()
    try:
        user = User(username=username, password_hash=hash_password("secret123"))
        db.add(user)
        db.flush()
        account = PlatformAccount(
            user_id=user.id,
            platform="xhs",
            sub_type="page_import",
            external_user_id=f"account-{user.id}",
            nickname="Image localizer",
            status="active",
        )
        db.add(account)
        db.flush()
        note = Note(
            user_id=user.id,
            platform_account_id=account.id,
            platform="xhs",
            note_id=f"note-{user.id}",
            title="Image note",
            content="Body",
            author_name="Author",
        )
        db.add(note)
        db.flush()
        db.commit()
        return user.id, note.id, {"Authorization": f"Bearer {create_access_token(user.id)}"}
    finally:
        db.close()


def assert_signed_media_url(url: str, file_name: str) -> None:
    assert url.startswith(f"/api/files/media/{file_name}?")
    assert "token=" in url


def test_localize_note_image_assets_downloads_missing_images_and_ignores_video(tmp_path, monkeypatch):
    SessionLocal = override_database(tmp_path)
    download_calls: list[tuple[str, int, str]] = []
    try:
        user_id, note_id, headers = create_user_headers(SessionLocal)
        existing_file = f"xhs-asset-u{user_id}-existing.jpg"
        new_file = f"xhs-asset-u{user_id}-new.jpg"
        db = SessionLocal()
        try:
            db.add_all(
                [
                    NoteAsset(note_id=note_id, asset_type="image", url="https://cdn.example.test/a.jpg", local_path="", sort_order=0),
                    NoteAsset(note_id=note_id, asset_type="image", url="https://cdn.example.test/b.jpg", local_path=existing_file, sort_order=1),
                    NoteAsset(note_id=note_id, asset_type="video", url="https://cdn.example.test/v.mp4", local_path="", sort_order=2),
                ]
            )
            db.commit()
        finally:
            db.close()

        def fake_download(url: str, owner_id: int, asset_type: str) -> str | None:
            download_calls.append((url, owner_id, asset_type))
            return new_file

        monkeypatch.setattr("backend.app.api.notes._download_asset", fake_download, raising=False)

        response = client.post(f"/api/notes/{note_id}/assets/localize-images", headers=headers)

        assert response.status_code == 200
        payload = response.json()
        assert payload["total_image_count"] == 2
        assert payload["downloaded_count"] == 1
        assert payload["skipped_count"] == 1
        assert payload["failed_count"] == 0
        assert [(item["asset_id"], item["status"]) for item in payload["items"]] == [
            (payload["items"][0]["asset_id"], "downloaded"),
            (payload["items"][1]["asset_id"], "skipped"),
        ]
        assert download_calls == [("https://cdn.example.test/a.jpg", user_id, "image")]

        db = SessionLocal()
        try:
            assets = db.scalars(select(NoteAsset).where(NoteAsset.note_id == note_id).order_by(NoteAsset.sort_order)).all()
            assert [(asset.asset_type, asset.local_path) for asset in assets] == [
                ("image", new_file),
                ("image", existing_file),
                ("video", ""),
            ]
        finally:
            db.close()

        assets_response = client.get(f"/api/notes/{note_id}/assets", headers=headers)
        assert assets_response.status_code == 200
        items = assets_response.json()["items"]
        assert_signed_media_url(items[0]["url"], new_file)
        assert_signed_media_url(items[1]["url"], existing_file)
        assert items[2]["url"] == "https://cdn.example.test/v.mp4"
        assert items[2]["local_path"] == ""
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_localize_note_image_assets_reports_failures_without_touching_video(tmp_path, monkeypatch):
    SessionLocal = override_database(tmp_path)
    download_calls: list[tuple[str, int, str]] = []
    try:
        user_id, note_id, headers = create_user_headers(SessionLocal, username="image-localizer-failure")
        db = SessionLocal()
        try:
            db.add_all(
                [
                    NoteAsset(note_id=note_id, asset_type="image", url="https://cdn.example.test/fail.jpg", local_path="", sort_order=0),
                    NoteAsset(note_id=note_id, asset_type="video", url="https://cdn.example.test/v.mp4", local_path="", sort_order=1),
                ]
            )
            db.commit()
        finally:
            db.close()

        def fake_download(url: str, owner_id: int, asset_type: str) -> str | None:
            download_calls.append((url, owner_id, asset_type))
            return None

        monkeypatch.setattr("backend.app.api.notes._download_asset", fake_download, raising=False)

        response = client.post(f"/api/notes/{note_id}/assets/localize-images", headers=headers)

        assert response.status_code == 200
        payload = response.json()
        assert payload["downloaded_count"] == 0
        assert payload["skipped_count"] == 0
        assert payload["failed_count"] == 1
        assert payload["items"] == [
            {
                "asset_id": payload["items"][0]["asset_id"],
                "status": "failed",
                "local_path": "",
                "error": "download_failed",
            }
        ]
        assert download_calls == [("https://cdn.example.test/fail.jpg", user_id, "image")]

        db = SessionLocal()
        try:
            assets = db.scalars(select(NoteAsset).where(NoteAsset.note_id == note_id).order_by(NoteAsset.sort_order)).all()
            assert [(asset.asset_type, asset.local_path) for asset in assets] == [("image", ""), ("video", "")]
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


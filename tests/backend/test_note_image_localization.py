from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.database import Base, get_db
from backend.app.core.security import create_access_token, encrypt_text, hash_password
from backend.app.api.platforms.xhs.pc import get_xhs_pc_api_adapter_factory
from backend.app.main import app
from backend.app.models import AccountCookieVersion, Note, NoteAsset, PlatformAccount, User
import backend.app.services.xhs_source_image_import_service as source_image_import_service
from backend.app.services.xhs_source_image_import_service import (
    SourceImageDetailError,
    fetch_authenticated_source_images,
)


client = TestClient(app)


def override_database():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
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


def add_source_import_account(
    db,
    *,
    user_id: int,
    nickname: str,
    sub_type: str = "pc",
    status: str = "active",
    platform: str = "xhs",
    cookie_text: str | None = None,
    updated_at: datetime | None = None,
) -> PlatformAccount:
    account = PlatformAccount(
        user_id=user_id,
        platform=platform,
        sub_type=sub_type,
        external_user_id=f"source-import-{nickname}",
        nickname=nickname,
        status=status,
        updated_at=updated_at or datetime(2026, 7, 12, 12, 0),
    )
    db.add(account)
    db.flush()
    if cookie_text is not None:
        db.add(
            AccountCookieVersion(
                platform_account_id=account.id,
                encrypted_cookies=encrypt_text(cookie_text),
            )
        )
        db.flush()
    return account


def test_localize_note_image_assets_downloads_missing_images_and_ignores_video(monkeypatch):
    SessionLocal = override_database()
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


def test_localize_note_image_assets_reports_failures_without_touching_video(monkeypatch):
    SessionLocal = override_database()
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


def test_import_source_images_does_not_persist_xsec_token(monkeypatch):
    SessionLocal = override_database()
    try:
        user_id, note_id, headers = create_user_headers(SessionLocal, username="source-image-import-sanitized")
        db = SessionLocal()
        try:
            add_source_import_account(db, user_id=user_id, nickname="sanitized", cookie_text="a1=sanitized")
            db.commit()
        finally:
            db.close()

        class FakeAdapter:
            def __init__(self, _cookies: str):
                pass

            def get_note_info(self, source_url: str):
                assert source_url == "https://www.xiaohongshu.com/explore/note-1"
                return True, "ok", source_image_payload("new-image")

        app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: FakeAdapter
        monkeypatch.setattr("backend.app.api.notes._download_asset", lambda *_args: "downloaded.jpg", raising=False)

        response = client.post(
            f"/api/notes/{note_id}/assets/import-source-images",
            headers=headers,
            json={"source_url": "https://www.xiaohongshu.com/explore/note-1?xsec_token=secret-token&xsec_source=pc_feed"},
        )

        assert response.status_code == 200
        db = SessionLocal()
        try:
            note = db.get(Note, note_id)
            assert note is not None
            raw_text = str(note.raw_json)
            assert "secret-token" not in raw_text
            assert note.raw_json["source_image_import"]["source_url"] == "https://www.xiaohongshu.com/explore/note-1"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)
        app.dependency_overrides.pop(get_db, None)


def test_import_source_images_adds_missing_images_and_downloads_without_touching_video(monkeypatch):
    SessionLocal = override_database()
    download_calls: list[tuple[str, int, str]] = []
    try:
        user_id, note_id, headers = create_user_headers(SessionLocal, username="source-image-importer")
        existing_url = "https://sns-img-hw.xhscdn.com/notes_pre_post/existing-image"
        db = SessionLocal()
        try:
            db.add_all(
                [
                    NoteAsset(note_id=note_id, asset_type="image", url=existing_url, local_path="existing.jpg", sort_order=0),
                    NoteAsset(note_id=note_id, asset_type="video", url="https://cdn.example.test/v.mp4", local_path="", sort_order=1),
                ]
            )
            add_source_import_account(db, user_id=user_id, nickname="importer", cookie_text="a1=importer")
            db.commit()
        finally:
            db.close()

        source_urls = [
            existing_url + "?imageView2/2/w/360/format/webp",
            "https://sns-img-bd.xhscdn.com/notes_pre_post/new-image-a",
            "https://sns-img-bd.xhscdn.com/notes_pre_post/new-image-b",
        ]

        class FakeAdapter:
            def __init__(self, _cookies: str):
                pass

            def get_note_info(self, _source_url: str):
                return True, "ok", {"image_list": [{"url": url} for url in source_urls]}

        def fake_download(url: str, owner_id: int, asset_type: str) -> str | None:
            download_calls.append((url, owner_id, asset_type))
            return f"downloaded-{len(download_calls)}.jpg"

        app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: FakeAdapter
        monkeypatch.setattr("backend.app.api.notes._download_asset", fake_download, raising=False)

        response = client.post(
            f"/api/notes/{note_id}/assets/import-source-images",
            headers=headers,
            json={"source_url": "https://www.xiaohongshu.com/explore/note-1?xsec_token=secret"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["total_source_image_count"] == 3
        assert payload["imported_count"] == 2
        assert payload["skipped_count"] == 1
        assert payload["downloaded_count"] == 2
        assert payload["failed_count"] == 0
        assert download_calls == [
            ("https://sns-img-bd.xhscdn.com/notes_pre_post/new-image-a", user_id, "image"),
            ("https://sns-img-bd.xhscdn.com/notes_pre_post/new-image-b", user_id, "image"),
        ]

        db = SessionLocal()
        try:
            assets = db.scalars(select(NoteAsset).where(NoteAsset.note_id == note_id).order_by(NoteAsset.sort_order.asc(), NoteAsset.id.asc())).all()
            assert [(asset.asset_type, asset.url, asset.local_path) for asset in assets] == [
                ("image", existing_url, "existing.jpg"),
                ("video", "https://cdn.example.test/v.mp4", ""),
                ("image", "https://sns-img-bd.xhscdn.com/notes_pre_post/new-image-a", "downloaded-1.jpg"),
                ("image", "https://sns-img-bd.xhscdn.com/notes_pre_post/new-image-b", "downloaded-2.jpg"),
            ]
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)
        app.dependency_overrides.pop(get_db, None)


def test_import_source_images_downloads_existing_remote_images_without_duplicating(monkeypatch):
    SessionLocal = override_database()
    download_calls: list[tuple[str, int, str]] = []
    try:
        user_id, note_id, headers = create_user_headers(SessionLocal, username="source-image-existing-localizer")
        existing_url = "https://sns-webpic-qc.xhscdn.com/202607071002/a/notes_pre_post/existing!nd_dft_wlteh_webp_3"
        normalized_existing_url = "https://sns-webpic-qc.xhscdn.com/202607071002/a/notes_pre_post/existing"
        db = SessionLocal()
        try:
            db.add_all(
                [
                    NoteAsset(note_id=note_id, asset_type="image", url=existing_url, local_path="", sort_order=0),
                    NoteAsset(note_id=note_id, asset_type="video", url="https://cdn.example.test/v.mp4", local_path="", sort_order=1),
                ]
            )
            add_source_import_account(db, user_id=user_id, nickname="existing", cookie_text="a1=existing")
            db.commit()
        finally:
            db.close()

        class FakeAdapter:
            def __init__(self, _cookies: str):
                pass

            def get_note_info(self, _source_url: str):
                return True, "ok", {
                    "image_list": [{"url": existing_url + "?imageView2/2/w/360/format/webp"}]
                }

        def fake_download(url: str, owner_id: int, asset_type: str) -> str | None:
            download_calls.append((url, owner_id, asset_type))
            return "downloaded-existing.jpg"

        app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: FakeAdapter
        monkeypatch.setattr("backend.app.api.notes._download_asset", fake_download, raising=False)

        response = client.post(
            f"/api/notes/{note_id}/assets/import-source-images",
            headers=headers,
            json={"source_url": "https://www.xiaohongshu.com/explore/note-1"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["total_source_image_count"] == 1
        assert payload["imported_count"] == 0
        assert payload["skipped_count"] == 1
        assert payload["downloaded_count"] == 1
        assert payload["failed_count"] == 0
        assert payload["items"] == [
            {
                "url": normalized_existing_url,
                "status": "downloaded",
                "asset_id": payload["items"][0]["asset_id"],
                "local_path": "downloaded-existing.jpg",
                "error": "",
            }
        ]
        assert download_calls == [(normalized_existing_url, user_id, "image")]

        db = SessionLocal()
        try:
            assets = db.scalars(select(NoteAsset).where(NoteAsset.note_id == note_id).order_by(NoteAsset.sort_order.asc(), NoteAsset.id.asc())).all()
            assert [(asset.asset_type, asset.url, asset.local_path) for asset in assets] == [
                ("image", existing_url, "downloaded-existing.jpg"),
                ("video", "https://cdn.example.test/v.mp4", ""),
            ]
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)
        app.dependency_overrides.pop(get_db, None)


def test_import_source_images_accepts_page_payload_token_and_downloads(monkeypatch):
    SessionLocal = override_database()
    download_calls: list[tuple[str, int, str]] = []
    try:
        user_id, note_id, headers = create_user_headers(SessionLocal, username="source-image-page-payload")

        def fake_download(url: str, owner_id: int, asset_type: str) -> str | None:
            download_calls.append((url, owner_id, asset_type))
            return f"page-payload-{len(download_calls)}.jpg"

        monkeypatch.setattr("backend.app.api.notes._download_asset", fake_download, raising=False)

        script_response = client.post(f"/api/notes/{note_id}/assets/import-source-images/page-script", headers=headers)
        assert script_response.status_code == 200
        script_payload = script_response.json()
        assert "localStorage" not in script_payload["script"]
        assert "cookie" not in script_payload["script"].lower()
        assert "__INITIAL_STATE__" in script_payload["script"]
        assert "imageList" in script_payload["script"]
        assert "if(!urls.length)" not in script_payload["script"]
        assert "walk(window.__INITIAL_STATE__" in script_payload["script"]
        assert "document.querySelectorAll('img,source')" in script_payload["script"]
        assert "const keyOf=(u)=>" in script_payload["script"]
        assert "note_pre_post_uhdr" in script_payload["script"]
        assert "await fetch(target" not in script_payload["script"]
        assert "navigator.sendBeacon" in script_payload["script"]
        assert "status:'sent'" in script_payload["script"]
        assert "keepalive:true" in script_payload["script"]
        assert "__xhsSourceImageImportStatus" in script_payload["script"]
        token = script_payload["script"].split("token=")[1].split(";", 1)[0].strip("'\"")

        response = client.post(
            f"/api/notes/{note_id}/assets/import-source-images/page-payload",
            content=json.dumps(
                {
                    "token": token,
                    "source_url": "https://www.xiaohongshu.com/explore/note-1?xsec_token=secret-token",
                    "image_urls": [
                        "https://sns-webpic-qc.xhscdn.com/202607071002/a/notes_pre_post/one!nd_dft_wlteh_webp_3",
                        "https://sns-webpic-qc.xhscdn.com/202607071002/b/notes_pre_post/two!nd_dft_wlteh_webp_3",
                        "https://sns-webpic-qc.xhscdn.com/202607071002/a/notes_pre_post/one!nd_dft_wlteh_webp_3",
                        "https://sns-avatar-qc.xhscdn.com/avatar/not-a-note-image.jpg",
                    ],
                    "download": True,
                }
            ),
            headers={"Content-Type": "text/plain;charset=UTF-8"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["total_source_image_count"] == 2
        assert payload["imported_count"] == 2
        assert payload["downloaded_count"] == 2
        assert download_calls == [
            ("https://sns-webpic-qc.xhscdn.com/202607071002/a/notes_pre_post/one!nd_dft_wlteh_webp_3", user_id, "image"),
            ("https://sns-webpic-qc.xhscdn.com/202607071002/b/notes_pre_post/two!nd_dft_wlteh_webp_3", user_id, "image"),
        ]

        db = SessionLocal()
        try:
            note = db.get(Note, note_id)
            assert note is not None
            assert "secret-token" not in str(note.raw_json)
            assets = db.scalars(select(NoteAsset).where(NoteAsset.note_id == note_id).order_by(NoteAsset.sort_order.asc())).all()
            assert [asset.local_path for asset in assets] == ["page-payload-1.jpg", "page-payload-2.jpg"]
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_localize_images_refreshes_source_import_failure_summary(monkeypatch):
    SessionLocal = override_database()
    download_calls: list[tuple[str, int, str]] = []
    try:
        user_id, note_id, headers = create_user_headers(SessionLocal, username="source-image-refresh-summary")
        first_url = "https://sns-webpic-qc.xhscdn.com/202607071002/a/notes_pre_post/one"
        second_url = "https://sns-webpic-qc.xhscdn.com/202607071002/b/notes_pre_post/two"

        def fail_download(url: str, owner_id: int, asset_type: str) -> str | None:
            download_calls.append((url, owner_id, asset_type))
            return None

        monkeypatch.setattr("backend.app.api.notes._download_asset", fail_download, raising=False)

        script_response = client.post(f"/api/notes/{note_id}/assets/import-source-images/page-script", headers=headers)
        assert script_response.status_code == 200
        token = script_response.json()["script"].split("token=")[1].split(";", 1)[0].strip("'\"")
        import_response = client.post(
            f"/api/notes/{note_id}/assets/import-source-images/page-payload",
            content=json.dumps(
                {
                    "token": token,
                    "source_url": "https://www.xiaohongshu.com/explore/note-1?xsec_token=secret-token",
                    "image_urls": [first_url, second_url],
                    "download": True,
                }
            ),
            headers={"Content-Type": "text/plain;charset=UTF-8"},
        )
        assert import_response.status_code == 200
        assert import_response.json()["failed_count"] == 2

        db = SessionLocal()
        try:
            note = db.get(Note, note_id)
            assert note is not None
            summary = note.raw_json["source_image_import"]
            assert summary["source_image_keys"] == ["notes_pre_post/one", "notes_pre_post/two"]
            db.add(
                NoteAsset(
                    note_id=note_id,
                    asset_type="image",
                    url="https://sns-img-hw.xhscdn.com/notes_pre_post/unrelated",
                    local_path="unrelated.jpg",
                    sort_order=99,
                )
            )
            db.commit()
        finally:
            db.close()

        def recover_download(url: str, owner_id: int, asset_type: str) -> str | None:
            download_calls.append((url, owner_id, asset_type))
            return f"recovered-{len(download_calls)}.webp"

        monkeypatch.setattr("backend.app.api.notes._download_asset", recover_download, raising=False)

        response = client.post(f"/api/notes/{note_id}/assets/localize-images", headers=headers)

        assert response.status_code == 200
        payload = response.json()
        assert payload["downloaded_count"] == 2
        assert payload["failed_count"] == 0

        db = SessionLocal()
        try:
            note = db.get(Note, note_id)
            assert note is not None
            summary = note.raw_json["source_image_import"]
            assert summary["status"] == "completed"
            assert summary["total_source_image_count"] == 2
            assert summary["downloaded_count"] == 2
            assert summary["failed_count"] == 0
            assert summary["downloaded_count"] + summary["failed_count"] <= summary["total_source_image_count"]
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_localize_images_leaves_ambiguous_legacy_source_import_summary_unchanged(monkeypatch):
    SessionLocal = override_database()
    try:
        user_id, note_id, headers = create_user_headers(SessionLocal, username="source-image-legacy-summary")
        urls = {
            name: f"https://sns-img-hw.xhscdn.com/notes_pre_post/{name}"
            for name in ("a", "b", "unrelated", "c")
        }
        legacy_summary = {
            "status": "partial",
            "source_url": "https://www.xiaohongshu.com/explore/legacy-note",
            "total_source_image_count": 2,
            "imported_count": 2,
            "skipped_count": 0,
            "downloaded_count": 0,
            "failed_count": 2,
        }
        db = SessionLocal()
        try:
            note = db.get(Note, note_id)
            assert note is not None
            note.raw_json = {
                **(note.raw_json or {}),
                "image_urls": [urls["a"], urls["b"], urls["unrelated"], urls["c"]],
                "source_image_import": legacy_summary,
            }
            db.add_all(
                [
                    NoteAsset(
                        note_id=note_id,
                        asset_type="image",
                        url=url,
                        local_path="",
                        sort_order=index,
                    )
                    for index, url in enumerate(urls.values())
                ]
            )
            db.commit()
        finally:
            db.close()

        monkeypatch.setattr(
            "backend.app.api.notes._download_asset",
            lambda url, _owner_id, _asset_type: f"{url.rsplit('/', 1)[-1]}.jpg",
            raising=False,
        )

        response = client.post(f"/api/notes/{note_id}/assets/localize-images", headers=headers)

        assert response.status_code == 200
        assert response.json()["downloaded_count"] == 4
        db = SessionLocal()
        try:
            note = db.get(Note, note_id)
            assert note is not None
            assert note.raw_json["source_image_import"] == legacy_summary
            assert "source_image_keys" not in note.raw_json["source_image_import"]
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_source_image_page_script_uses_backend_port_from_frontend_origin():
    SessionLocal = override_database()
    try:
        _user_id, note_id, headers = create_user_headers(SessionLocal, username="source-image-frontend-origin")

        response = client.post(
            f"/api/notes/{note_id}/assets/import-source-images/page-script",
            headers={**headers, "Origin": "http://127.0.0.1:18080"},
        )

        assert response.status_code == 200
        assert "http://127.0.0.1:18081/api/notes/" in response.json()["script"]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_import_source_images_page_payload_allows_original_page_preflight():
    SessionLocal = override_database()
    try:
        _user_id, note_id, _headers = create_user_headers(SessionLocal, username="source-image-preflight")

        response = client.options(
            f"/api/notes/{note_id}/assets/import-source-images/page-payload",
            headers={
                "Origin": "https://www.xiaohongshu.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Private-Network": "true",
            },
        )

        assert response.status_code == 204
        assert response.headers["access-control-allow-origin"] == "https://www.xiaohongshu.com"
        assert response.headers["access-control-allow-methods"] == "POST, OPTIONS"
        assert response.headers["access-control-allow-private-network"] == "true"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_import_source_images_rejects_bad_page_payload_token_without_importing(monkeypatch):
    SessionLocal = override_database()
    download_calls: list[tuple[str, int, str]] = []
    try:
        _user_id, note_id, _headers = create_user_headers(SessionLocal, username="source-image-bad-token")

        def fake_download(url: str, owner_id: int, asset_type: str) -> str | None:
            download_calls.append((url, owner_id, asset_type))
            return "bad-token-should-not-download.jpg"

        monkeypatch.setattr("backend.app.api.notes._download_asset", fake_download, raising=False)

        response = client.post(
            f"/api/notes/{note_id}/assets/import-source-images/page-payload",
            content=json.dumps(
                {
                    "token": "bad.token",
                    "source_url": "https://www.xiaohongshu.com/explore/note-1?xsec_token=secret-token",
                    "image_urls": ["https://sns-webpic-qc.xhscdn.com/202607071002/a/notes_pre_post/one"],
                    "download": True,
                }
            ),
            headers={"Content-Type": "text/plain;charset=UTF-8"},
        )

        assert response.status_code == 401
        assert download_calls == []

        db = SessionLocal()
        try:
            assets = db.scalars(select(NoteAsset).where(NoteAsset.note_id == note_id)).all()
            assert assets == []
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_import_source_images_reports_all_existing_authenticated_images_and_updates_summary(monkeypatch):
    SessionLocal = override_database()
    try:
        user_id, note_id, headers = create_user_headers(SessionLocal, username="source-image-existing-raw")
        existing_url = "https://sns-img-hw.xhscdn.com/notes_pre_post/existing-image"
        db = SessionLocal()
        try:
            note = db.get(Note, note_id)
            assert note is not None
            note.raw_json = {
                "source": "data_acquisition",
                "note_url": "https://www.xiaohongshu.com/explore/note-1?xsec_token=token",
                "asset_urls": [existing_url],
            }
            db.add(NoteAsset(note_id=note_id, asset_type="image", url=existing_url, local_path="existing.jpg", sort_order=0))
            account = add_source_import_account(
                db,
                user_id=user_id,
                nickname="existing-raw",
                cookie_text="a1=existing-raw",
            )
            db.commit()
            account_id = account.id
        finally:
            db.close()

        class FakeAdapter:
            def __init__(self, _cookies: str):
                pass

            def get_note_info(self, _source_url: str):
                return True, "ok", source_image_payload("existing-image")

        app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: FakeAdapter
        monkeypatch.setattr(
            "backend.app.api.notes._download_asset",
            lambda *_args: (_ for _ in ()).throw(AssertionError("existing image should not be downloaded again")),
            raising=False,
        )

        response = client.post(
            f"/api/notes/{note_id}/assets/import-source-images",
            headers=headers,
            json={"source_url": "https://www.xiaohongshu.com/explore/note-1?xsec_token=token", "download": True},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["total_source_image_count"] == 1
        assert payload["imported_count"] == 0
        assert payload["skipped_count"] == 1
        assert payload["downloaded_count"] == 0
        assert payload["failed_count"] == 0
        assert payload["items"] == [
            {
                "url": existing_url,
                "status": "skipped",
                "asset_id": payload["items"][0]["asset_id"],
                "local_path": "existing.jpg",
                "error": "",
            }
        ]
        db = SessionLocal()
        try:
            note = db.get(Note, note_id)
            assert note is not None
            summary = note.raw_json["source_image_import"]
            assert summary["status"] == "completed"
            assert summary["account_id"] == account_id
            assert summary["source_url"] == "https://www.xiaohongshu.com/explore/note-1"
            assert "token" not in str(summary)
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)
        app.dependency_overrides.pop(get_db, None)


def create_source_import_note(db, *, username: str, bound_sub_type: str = "page_import"):
    user = User(username=username, password_hash=hash_password("secret123"))
    db.add(user)
    db.flush()
    bound = add_source_import_account(
        db,
        user_id=user.id,
        nickname=f"{username}-bound",
        sub_type=bound_sub_type,
    )
    note = Note(
        user_id=user.id,
        platform_account_id=bound.id,
        platform="xhs",
        note_id=f"{username}-note",
        title="Source import",
    )
    db.add(note)
    db.flush()
    return user, note, bound


def source_image_payload(marker: str = "one") -> dict:
    return {
        "success": True,
        "data": {
            "items": [
                {
                    "note_card": {
                        "image_list": [
                            {"url_default": f"https://sns-img-hw.xhscdn.com/notes_pre_post/{marker}"}
                        ]
                    }
                }
            ]
        },
    }


def test_import_source_images_uses_authenticated_pc_detail_and_persists_safe_summary(monkeypatch):
    SessionLocal = override_database()
    adapter_calls: list[tuple[str, str]] = []
    try:
        user_id, note_id, headers = create_user_headers(SessionLocal, username="authenticated-api-import")
        db = SessionLocal()
        try:
            note = db.get(Note, note_id)
            assert note is not None
            account = add_source_import_account(
                db,
                user_id=user_id,
                nickname="usable-pc",
                cookie_text="a1=usable-secret; web_session=usable-session",
            )
            note.platform_account_id = account.id
            note.note_id = "real-note-id"
            note.raw_json = {
                "note_url": "https://www.xiaohongshu.com/explore/real-note-id?xsec_token=stored-secret"
            }
            db.commit()
            account_id = account.id
        finally:
            db.close()

        class FakeAdapter:
            def __init__(self, cookies: str):
                self.cookies = cookies

            def get_note_info(self, url: str):
                adapter_calls.append((self.cookies, url))
                return True, "ok", {
                    "data": {
                        "items": [
                            {
                                "note_card": {
                                    "image_list": [
                                        {
                                            "info_list": [
                                                {
                                                    "url": "https://sns-img-hw.xhscdn.com/notes_pre_post/snake-nested"
                                                }
                                            ]
                                        },
                                        {
                                            "infoList": [
                                                {
                                                    "urlDefault": "https://sns-img-hw.xhscdn.com/notes_pre_post/camel-nested"
                                                }
                                            ]
                                        },
                                    ]
                                }
                            }
                        ]
                    }
                }

        app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: FakeAdapter
        monkeypatch.setattr(
            "backend.app.api.notes._download_asset",
            lambda url, *_args: url.rsplit("/", 1)[-1] + ".jpg",
            raising=False,
        )

        response = client.post(
            f"/api/notes/{note_id}/assets/import-source-images",
            headers=headers,
            json={
                "source_url": (
                    "https://www.xiaohongshu.com/explore/real-note-id"
                    "?xsec_token=request-secret&xsec_source=pc_feed"
                ),
                "download": True,
            },
        )

        assert response.status_code == 200
        assert response.json()["downloaded_count"] == 2
        assert adapter_calls == [
            (
                "a1=usable-secret; web_session=usable-session",
                "https://www.xiaohongshu.com/explore/real-note-id",
            )
        ]
        db = SessionLocal()
        try:
            note = db.get(Note, note_id)
            assert note is not None
            summary = note.raw_json["source_image_import"]
            assert summary["status"] == "completed"
            assert summary["account_id"] == account_id
            assert summary["source_url"] == "https://www.xiaohongshu.com/explore/real-note-id"
            assert "request-secret" not in str(summary)
            assert "stored-secret" not in str(summary)
            assets = db.scalars(
                select(NoteAsset).where(NoteAsset.note_id == note_id).order_by(NoteAsset.sort_order.asc())
            ).all()
            assert [(asset.url, asset.local_path) for asset in assets] == [
                (
                    "https://sns-img-hw.xhscdn.com/notes_pre_post/snake-nested",
                    "snake-nested.jpg",
                ),
                (
                    "https://sns-img-hw.xhscdn.com/notes_pre_post/camel-nested",
                    "camel-nested.jpg",
                ),
            ]
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)
        app.dependency_overrides.pop(get_db, None)


def test_import_source_images_returns_structured_login_required_without_provider_call():
    SessionLocal = override_database()
    adapter_calls: list[str] = []
    try:
        _user_id, note_id, headers = create_user_headers(SessionLocal, username="automatic-import-login-required")

        class UnexpectedAdapter:
            def __init__(self, _cookies: str):
                adapter_calls.append("constructed")

        app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: UnexpectedAdapter
        response = client.post(
            f"/api/notes/{note_id}/assets/import-source-images",
            headers=headers,
            json={
                "source_url": "https://www.xiaohongshu.com/explore/real-note-id?xsec_token=secret",
                "download": True,
            },
        )

        assert response.status_code == 409
        assert response.json()["detail"] == {
            "code": "xhs_login_required",
            "message": "自动补全原文图片需要先登录小红书 PC 账号，请前往账号矩阵登录后重试。",
        }
        assert adapter_calls == []
        db = SessionLocal()
        try:
            note = db.get(Note, note_id)
            assert note is not None
            summary = note.raw_json["source_image_import"]
            assert summary["status"] == "login_required"
            assert summary["error_code"] == "xhs_login_required"
            assert summary["account_id"] is None
            assert "secret" not in str(summary)
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)
        app.dependency_overrides.pop(get_db, None)


def test_import_source_images_returns_structured_not_found_without_creating_assets():
    SessionLocal = override_database()
    try:
        user_id, note_id, headers = create_user_headers(SessionLocal, username="automatic-import-no-images")
        db = SessionLocal()
        try:
            usable_account = add_source_import_account(
                db,
                user_id=user_id,
                nickname="usable",
                cookie_text="a1=usable",
            )
            db.commit()
            usable_account_id = usable_account.id
        finally:
            db.close()

        class EmptyDetailAdapter:
            def __init__(self, _cookies: str):
                pass

            def get_note_info(self, _url: str):
                return True, "ok", {"data": {"items": [{"note_card": {"image_list": []}}]}}

        app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: EmptyDetailAdapter
        response = client.post(
            f"/api/notes/{note_id}/assets/import-source-images",
            headers=headers,
            json={"source_url": "https://www.xiaohongshu.com/explore/real-note-id", "download": True},
        )

        assert response.status_code == 422
        assert response.json()["detail"] == {
            "code": "source_images_not_found",
            "message": "原文详情未返回可补全的图片。",
        }
        db = SessionLocal()
        try:
            assert db.scalars(select(NoteAsset).where(NoteAsset.note_id == note_id)).all() == []
            note = db.get(Note, note_id)
            assert note is not None
            summary = note.raw_json["source_image_import"]
            assert summary["status"] == "not_found"
            assert summary["account_id"] == usable_account_id
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)
        app.dependency_overrides.pop(get_db, None)


def test_explicit_page_image_urls_still_import_without_pc_account(monkeypatch):
    SessionLocal = override_database()
    adapter_calls: list[str] = []
    try:
        _user_id, note_id, headers = create_user_headers(SessionLocal, username="explicit-image-urls-no-pc")

        class UnexpectedAdapter:
            def __init__(self, _cookies: str):
                adapter_calls.append("constructed")

        app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: UnexpectedAdapter
        monkeypatch.setattr("backend.app.api.notes._download_asset", lambda *_args: "explicit.jpg", raising=False)
        response = client.post(
            f"/api/notes/{note_id}/assets/import-source-images",
            headers=headers,
            json={
                "source_url": "https://www.xiaohongshu.com/explore/real-note-id?xsec_token=secret",
                "image_urls": ["https://sns-img-hw.xhscdn.com/notes_pre_post/explicit"],
                "download": True,
            },
        )

        assert response.status_code == 200
        assert response.json()["imported_count"] == 1
        assert adapter_calls == []
        db = SessionLocal()
        try:
            note = db.get(Note, note_id)
            assert note is not None
            summary = note.raw_json["source_image_import"]
            assert summary["status"] == "completed"
            assert summary["account_id"] is None
            assert "secret" not in str(summary)
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)
        app.dependency_overrides.pop(get_db, None)


def test_explicit_source_image_import_summary_strips_url_userinfo(monkeypatch):
    SessionLocal = override_database()
    try:
        _user_id, note_id, headers = create_user_headers(SessionLocal, username="explicit-userinfo")
        monkeypatch.setattr("backend.app.api.notes._download_asset", lambda *_args: "explicit.jpg", raising=False)

        response = client.post(
            f"/api/notes/{note_id}/assets/import-source-images",
            headers=headers,
            json={
                "source_url": "https://source-user:source-password@www.xiaohongshu.com:443/explore/real-note-id?xsec_token=secret",
                "image_urls": ["https://sns-img-hw.xhscdn.com/notes_pre_post/explicit-userinfo"],
                "download": True,
            },
        )

        assert response.status_code == 200
        db = SessionLocal()
        try:
            note = db.get(Note, note_id)
            assert note is not None
            summary = note.raw_json["source_image_import"]
            assert summary["source_url"] == "https://www.xiaohongshu.com:443/explore/real-note-id"
            assert "source-user" not in str(summary)
            assert "source-password" not in str(summary)
            assert "secret" not in str(summary)
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize(
    ("adapter_response", "expected_status", "expected_code", "expected_summary_status"),
    [
        ((False, "访问频繁，请稍后再试", {"code": 300013}), 429, "xhs_rate_limited", "failed"),
        ((False, "provider unavailable", {"code": 500}), 502, "source_detail_failed", "failed"),
    ],
)
def test_import_source_images_persists_safe_structured_provider_errors(
    adapter_response,
    expected_status,
    expected_code,
    expected_summary_status,
):
    SessionLocal = override_database()
    try:
        user_id, note_id, headers = create_user_headers(
            SessionLocal,
            username=f"automatic-import-{expected_code}",
        )
        db = SessionLocal()
        try:
            usable_account = add_source_import_account(
                db,
                user_id=user_id,
                nickname="usable",
                cookie_text="a1=private-cookie",
            )
            db.commit()
            usable_account_id = usable_account.id
        finally:
            db.close()

        class FailedAdapter:
            def __init__(self, _cookies: str):
                pass

            def get_note_info(self, _url: str):
                return adapter_response

        app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: FailedAdapter
        response = client.post(
            f"/api/notes/{note_id}/assets/import-source-images",
            headers=headers,
            json={
                "source_url": "https://www.xiaohongshu.com/explore/real-note-id?xsec_token=secret-query",
                "download": True,
            },
        )

        assert response.status_code == expected_status
        assert response.json()["detail"]["code"] == expected_code
        db = SessionLocal()
        try:
            note = db.get(Note, note_id)
            assert note is not None
            summary = note.raw_json["source_image_import"]
            assert summary["status"] == expected_summary_status
            assert summary["error_code"] == expected_code
            assert summary["account_id"] == usable_account_id
            assert summary["source_url"] == "https://www.xiaohongshu.com/explore/real-note-id"
            assert "secret-query" not in str(summary)
            assert "private-cookie" not in str(summary)
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)
        app.dependency_overrides.pop(get_db, None)


def test_import_source_images_persists_safe_structured_source_url_error():
    SessionLocal = override_database()
    adapter_calls: list[str] = []
    try:
        user_id, note_id, headers = create_user_headers(SessionLocal, username="automatic-import-bad-url")
        db = SessionLocal()
        try:
            add_source_import_account(db, user_id=user_id, nickname="usable", cookie_text="a1=private-cookie")
            db.commit()
        finally:
            db.close()

        class UnexpectedAdapter:
            def __init__(self, _cookies: str):
                adapter_calls.append("constructed")

        app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: UnexpectedAdapter
        response = client.post(
            f"/api/notes/{note_id}/assets/import-source-images",
            headers=headers,
            json={"source_url": "https://error-user:error-password@example.test/explore/real-note-id?xsec_token=secret-query"},
        )

        assert response.status_code == 422
        assert response.json()["detail"] == {
            "code": "source_url_unavailable",
            "message": "原文链接不可用，请检查笔记来源后重试。",
        }
        assert adapter_calls == []
        db = SessionLocal()
        try:
            note = db.get(Note, note_id)
            assert note is not None
            summary = note.raw_json["source_image_import"]
            assert summary["status"] == "failed"
            assert summary["error_code"] == "source_url_unavailable"
            assert summary["source_url"] == "https://example.test/explore/real-note-id"
            assert "error-user" not in str(summary)
            assert "error-password" not in str(summary)
            assert "secret-query" not in str(summary)
            assert "private-cookie" not in str(summary)
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)
        app.dependency_overrides.pop(get_db, None)


def test_authenticated_source_import_prefers_bound_pc_account_and_strips_query_token():
    SessionLocal = override_database()
    db = SessionLocal()
    try:
        user, note, bound = create_source_import_note(db, username="source-bound", bound_sub_type="pc")
        bound_cookie = "a1=bound-secret; web_session=bound-session"
        db.add(
            AccountCookieVersion(
                platform_account_id=bound.id,
                encrypted_cookies=encrypt_text(bound_cookie),
            )
        )
        add_source_import_account(
            db,
            user_id=user.id,
            nickname="newer-fallback",
            cookie_text="a1=fallback-secret; web_session=fallback-session",
            updated_at=datetime(2026, 7, 12, 15, 0),
        )
        db.commit()
        calls: list[tuple[str, str]] = []

        class FakeAdapter:
            def __init__(self, cookies: str):
                self.account_marker = "bound" if cookies == bound_cookie else "unexpected"

            def get_note_info(self, url: str):
                calls.append((self.account_marker, url))
                return True, "ok", source_image_payload()

        result = fetch_authenticated_source_images(
            db=db,
            user_id=user.id,
            note=note,
            source_url=(
                "https://www.xiaohongshu.com/explore/source-bound-note"
                "?xsec_token=expired-token&xsec_source=pc_feed"
            ),
            adapter_factory=FakeAdapter,
        )

        assert result.account_id == bound.id
        assert result.source_url == "https://www.xiaohongshu.com/explore/source-bound-note"
        assert result.image_urls == ["https://sns-img-hw.xhscdn.com/notes_pre_post/one"]
        assert calls == [("bound", result.source_url)]
        assert "bound-secret" not in repr(result)
        assert "expired-token" not in repr(result)
    finally:
        db.close()


def test_authenticated_source_import_uses_newest_eligible_fallback_account():
    SessionLocal = override_database()
    db = SessionLocal()
    try:
        user, note, _bound = create_source_import_note(db, username="source-fallback")
        add_source_import_account(
            db,
            user_id=user.id,
            nickname="older-pc",
            cookie_text="a1=older-secret",
            updated_at=datetime(2026, 7, 12, 10, 0),
        )
        newest = add_source_import_account(
            db,
            user_id=user.id,
            nickname="newest-pc",
            cookie_text="a1=newest-secret",
            updated_at=datetime(2026, 7, 12, 11, 0),
        )
        db.commit()
        calls: list[str] = []

        class FakeAdapter:
            def __init__(self, cookies: str):
                self.marker = "newest" if cookies == "a1=newest-secret" else "other"

            def get_note_info(self, url: str):
                calls.append(f"{self.marker}:{url}")
                return True, "ok", source_image_payload("fallback")

        result = fetch_authenticated_source_images(
            db=db,
            user_id=user.id,
            note=note,
            source_url="https://www.xiaohongshu.com/discovery/item/source-fallback-note?xsec_token=stale",
            adapter_factory=FakeAdapter,
        )

        assert result.account_id == newest.id
        assert calls == ["newest:https://www.xiaohongshu.com/explore/source-fallback-note"]
    finally:
        db.close()


def test_authenticated_source_import_loads_candidates_in_one_query_and_decrypts_only_attempted_account(monkeypatch):
    SessionLocal = override_database()
    db = SessionLocal()
    query_count = 0
    listener_registered = False
    try:
        user, note, _bound = create_source_import_note(db, username="source-bounded-query")
        for index in range(8):
            add_source_import_account(
                db,
                user_id=user.id,
                nickname=f"candidate-{index}",
                cookie_text=f"a1=candidate-{index}-secret",
                updated_at=datetime(2026, 7, 12, 10, index),
            )
        db.commit()
        db.refresh(note)
        user_id = user.id
        real_decrypt = source_image_import_service.decrypt_text
        decrypt_calls: list[str] = []

        def counting_decrypt(encrypted_value: str) -> str:
            decrypt_calls.append(encrypted_value)
            return real_decrypt(encrypted_value)

        monkeypatch.setattr(source_image_import_service, "decrypt_text", counting_decrypt)

        def count_query(*_args):
            nonlocal query_count
            query_count += 1

        engine = db.get_bind()
        event.listen(engine, "before_cursor_execute", count_query)
        listener_registered = True

        class SuccessfulAdapter:
            def __init__(self, _cookies: str):
                pass

            def get_note_info(self, _url: str):
                return True, "ok", source_image_payload("bounded-query")

        result = fetch_authenticated_source_images(
            db=db,
            user_id=user_id,
            note=note,
            source_url="https://www.xiaohongshu.com/explore/source-bounded-query-note",
            adapter_factory=SuccessfulAdapter,
        )

        assert result.image_urls == ["https://sns-img-hw.xhscdn.com/notes_pre_post/bounded-query"]
        assert query_count == 1
        assert len(decrypt_calls) == 1
    finally:
        if listener_registered:
            event.remove(db.get_bind(), "before_cursor_execute", count_query)
        db.close()


def test_authenticated_source_import_skips_ineligible_accounts():
    SessionLocal = override_database()
    db = SessionLocal()
    try:
        user, note, _bound = create_source_import_note(db, username="source-ineligible")
        intruder = User(username="source-ineligible-intruder", password_hash=hash_password("secret123"))
        db.add(intruder)
        db.flush()
        base_time = datetime(2026, 7, 12, 16, 0)
        add_source_import_account(db, user_id=user.id, nickname="expired", status="expired", cookie_text="a1=expired", updated_at=base_time)
        add_source_import_account(db, user_id=user.id, nickname="deleted", status="deleted", cookie_text="a1=deleted", updated_at=base_time)
        add_source_import_account(db, user_id=user.id, nickname="creator", sub_type="creator", cookie_text="a1=creator", updated_at=base_time)
        add_source_import_account(db, user_id=user.id, nickname="other-platform", platform="wechat_official", cookie_text="a1=other", updated_at=base_time)
        add_source_import_account(db, user_id=intruder.id, nickname="cross-user", cookie_text="a1=cross", updated_at=base_time)
        add_source_import_account(db, user_id=user.id, nickname="cookieless", cookie_text=None, updated_at=base_time)
        eligible = add_source_import_account(
            db,
            user_id=user.id,
            nickname="eligible",
            cookie_text="a1=eligible-secret",
            updated_at=base_time - timedelta(hours=1),
        )
        db.commit()
        constructed: list[str] = []

        class FakeAdapter:
            def __init__(self, cookies: str):
                constructed.append("eligible" if cookies == "a1=eligible-secret" else "ineligible")

            def get_note_info(self, _url: str):
                return True, "ok", source_image_payload("eligible")

        result = fetch_authenticated_source_images(
            db=db,
            user_id=user.id,
            note=note,
            source_url="https://www.xiaohongshu.com/explore/source-ineligible-note",
            adapter_factory=FakeAdapter,
        )

        assert result.account_id == eligible.id
        assert constructed == ["eligible"]
    finally:
        db.close()


def test_authenticated_source_import_advances_only_after_login_failure():
    SessionLocal = override_database()
    db = SessionLocal()
    try:
        user, note, _bound = create_source_import_note(db, username="source-login-rotation")
        second = add_source_import_account(
            db,
            user_id=user.id,
            nickname="second",
            cookie_text="a1=second-secret",
            updated_at=datetime(2026, 7, 12, 10, 0),
        )
        add_source_import_account(
            db,
            user_id=user.id,
            nickname="first",
            cookie_text="a1=first-secret",
            updated_at=datetime(2026, 7, 12, 11, 0),
        )
        db.commit()
        call_count = 0

        class FakeAdapter:
            def __init__(self, _cookies: str):
                pass

            def get_note_info(self, _url: str):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return False, "无登录信息，或登录信息为空", {"success": False}
                return True, "ok", source_image_payload("after-login")

        result = fetch_authenticated_source_images(
            db=db,
            user_id=user.id,
            note=note,
            source_url="https://www.xiaohongshu.com/explore/source-login-rotation-note",
            adapter_factory=FakeAdapter,
        )

        assert result.account_id == second.id
        assert call_count == 2
    finally:
        db.close()


def test_authenticated_source_import_requires_login_after_all_candidates_expire_without_account_writes():
    SessionLocal = override_database()
    db = SessionLocal()
    try:
        user, note, _bound = create_source_import_note(db, username="source-all-logins-expired")
        older_updated_at = datetime(2026, 7, 12, 10, 0)
        newer_updated_at = datetime(2026, 7, 12, 11, 0)
        older = add_source_import_account(
            db,
            user_id=user.id,
            nickname="older",
            cookie_text="a1=older-expired-secret",
            updated_at=older_updated_at,
        )
        newer = add_source_import_account(
            db,
            user_id=user.id,
            nickname="newer",
            cookie_text="a1=newer-expired-secret",
            updated_at=newer_updated_at,
        )
        db.commit()
        calls: list[str] = []

        class ExpiredAdapter:
            def __init__(self, cookies: str):
                self.marker = "newer" if cookies == "a1=newer-expired-secret" else "older"

            def get_note_info(self, _url: str):
                calls.append(self.marker)
                return False, "无登录信息，或登录信息为空", {"success": False}

        with pytest.raises(SourceImageDetailError) as exc_info:
            fetch_authenticated_source_images(
                db=db,
                user_id=user.id,
                note=note,
                source_url="https://www.xiaohongshu.com/explore/source-all-logins-expired-note",
                adapter_factory=ExpiredAdapter,
            )

        assert exc_info.value.code == "xhs_login_required"
        assert exc_info.value.status_code == 409
        assert exc_info.value.account_id is None
        assert calls == ["newer", "older"]
        db.refresh(older)
        db.refresh(newer)
        assert (older.status, older.updated_at) == ("active", older_updated_at)
        assert (newer.status, newer.updated_at) == ("active", newer_updated_at)
    finally:
        db.close()


def test_authenticated_source_import_does_not_rotate_after_rate_limit():
    SessionLocal = override_database()
    db = SessionLocal()
    try:
        user, note, _bound = create_source_import_note(db, username="source-rate-limit")
        add_source_import_account(db, user_id=user.id, nickname="older", cookie_text="a1=older", updated_at=datetime(2026, 7, 12, 10, 0))
        add_source_import_account(db, user_id=user.id, nickname="newer", cookie_text="a1=newer", updated_at=datetime(2026, 7, 12, 11, 0))
        db.commit()
        call_count = 0

        class FakeAdapter:
            def __init__(self, _cookies: str):
                pass

            def get_note_info(self, _url: str):
                nonlocal call_count
                call_count += 1
                return False, "访问频繁，请稍后再试", {"code": 300013}

        with pytest.raises(SourceImageDetailError) as exc_info:
            fetch_authenticated_source_images(
                db=db,
                user_id=user.id,
                note=note,
                source_url="https://www.xiaohongshu.com/explore/source-rate-limit-note",
                adapter_factory=FakeAdapter,
            )

        assert exc_info.value.code == "xhs_rate_limited"
        assert exc_info.value.status_code == 429
        assert exc_info.value.account_id is not None
        assert call_count == 1
    finally:
        db.close()


def test_authenticated_source_import_requires_login_when_no_candidate_exists():
    SessionLocal = override_database()
    db = SessionLocal()
    try:
        user, note, _bound = create_source_import_note(db, username="source-no-login")
        db.commit()
        adapter_calls: list[str] = []

        class UnexpectedAdapter:
            def __init__(self, _cookies: str):
                adapter_calls.append("constructed")

        with pytest.raises(SourceImageDetailError) as exc_info:
            fetch_authenticated_source_images(
                db=db,
                user_id=user.id,
                note=note,
                source_url="https://www.xiaohongshu.com/explore/source-no-login-note",
                adapter_factory=UnexpectedAdapter,
            )

        assert exc_info.value.code == "xhs_login_required"
        assert exc_info.value.status_code == 409
        assert exc_info.value.account_id is None
        assert exc_info.value.message == "自动补全原文图片需要先登录小红书 PC 账号，请前往账号矩阵登录后重试。"
        assert adapter_calls == []
    finally:
        db.close()


@pytest.mark.parametrize(
    "malformed_cookie",
    [
        "a1=crlf-secret\r\nInjected: value",
        "a1=trailing-crlf-secret\r\n",
        "a1=nul-secret\x00tail",
        '{"a1":"json-secret; injected=value","web_session":"session"}',
        '{"bad name":"invalid-name-secret","web_session":"session"}',
    ],
)
def test_authenticated_source_import_skips_malformed_cookie_candidates_without_secret_leak(
    malformed_cookie,
    caplog,
):
    SessionLocal = override_database()
    db = SessionLocal()
    try:
        user, note, _bound = create_source_import_note(db, username=f"source-malformed-cookie-{len(malformed_cookie)}")
        add_source_import_account(
            db,
            user_id=user.id,
            nickname="malformed",
            cookie_text=malformed_cookie,
        )
        db.commit()
        adapter_calls: list[str] = []

        class UnexpectedAdapter:
            def __init__(self, _cookies: str):
                adapter_calls.append("constructed")

        with caplog.at_level("WARNING", logger="backend.app.services.xhs_source_image_import_service"):
            with pytest.raises(SourceImageDetailError) as exc_info:
                fetch_authenticated_source_images(
                    db=db,
                    user_id=user.id,
                    note=note,
                    source_url="https://www.xiaohongshu.com/explore/source-malformed-cookie-note",
                    adapter_factory=UnexpectedAdapter,
                )

        assert exc_info.value.code == "xhs_login_required"
        assert exc_info.value.status_code == 409
        assert adapter_calls == []
        assert malformed_cookie not in repr(exc_info.value)
        assert malformed_cookie not in caplog.text
    finally:
        db.close()


def test_authenticated_source_import_rejects_unsupported_source_url():
    SessionLocal = override_database()
    db = SessionLocal()
    try:
        user, note, _bound = create_source_import_note(db, username="source-bad-url")
        add_source_import_account(db, user_id=user.id, nickname="eligible", cookie_text="a1=secret")
        db.commit()

        with pytest.raises(SourceImageDetailError) as exc_info:
            fetch_authenticated_source_images(
                db=db,
                user_id=user.id,
                note=note,
                source_url="https://example.test/explore/source-bad-url-note?xsec_token=secret-token",
                adapter_factory=lambda _cookies: pytest.fail("unsupported URL must not construct an adapter"),
            )

        assert exc_info.value.code == "source_url_unavailable"
        assert exc_info.value.status_code == 422
        assert exc_info.value.account_id is None
        assert "secret-token" not in repr(exc_info.value)
    finally:
        db.close()


def test_authenticated_source_import_rejects_unsupported_xhs_path_without_constructing_adapter():
    SessionLocal = override_database()
    db = SessionLocal()
    try:
        user, note, _bound = create_source_import_note(db, username="source-bad-xhs-path")
        add_source_import_account(db, user_id=user.id, nickname="eligible", cookie_text="a1=secret")
        db.commit()
        adapter_calls: list[str] = []

        class UnexpectedAdapter:
            def __init__(self, _cookies: str):
                adapter_calls.append("constructed")

        with pytest.raises(SourceImageDetailError) as exc_info:
            fetch_authenticated_source_images(
                db=db,
                user_id=user.id,
                note=note,
                source_url="https://www.xiaohongshu.com/foo/source-bad-xhs-path-note",
                adapter_factory=UnexpectedAdapter,
            )

        assert exc_info.value.code == "source_url_unavailable"
        assert exc_info.value.status_code == 422
        assert adapter_calls == []
    finally:
        db.close()


def test_authenticated_source_import_reports_success_without_images():
    SessionLocal = override_database()
    db = SessionLocal()
    try:
        user, note, _bound = create_source_import_note(db, username="source-no-images")
        add_source_import_account(db, user_id=user.id, nickname="eligible", cookie_text="a1=secret")
        db.commit()

        class EmptyAdapter:
            def __init__(self, _cookies: str):
                pass

            def get_note_info(self, _url: str):
                return True, "ok", {"success": True, "data": {"items": []}}

        with pytest.raises(SourceImageDetailError) as exc_info:
            fetch_authenticated_source_images(
                db=db,
                user_id=user.id,
                note=note,
                source_url="https://www.xiaohongshu.com/explore/source-no-images-note",
                adapter_factory=EmptyAdapter,
            )

        assert exc_info.value.code == "source_images_not_found"
        assert exc_info.value.status_code == 422
        assert exc_info.value.account_id is not None
    finally:
        db.close()


def test_authenticated_source_import_stops_after_general_provider_failure():
    SessionLocal = override_database()
    db = SessionLocal()
    try:
        user, note, _bound = create_source_import_note(db, username="source-provider-failure")
        add_source_import_account(db, user_id=user.id, nickname="older", cookie_text="a1=older", updated_at=datetime(2026, 7, 12, 10, 0))
        add_source_import_account(db, user_id=user.id, nickname="newer", cookie_text="a1=newer", updated_at=datetime(2026, 7, 12, 11, 0))
        db.commit()
        call_count = 0

        class FailedAdapter:
            def __init__(self, _cookies: str):
                pass

            def get_note_info(self, _url: str):
                nonlocal call_count
                call_count += 1
                return False, "provider unavailable", {"code": 500}

        with pytest.raises(SourceImageDetailError) as exc_info:
            fetch_authenticated_source_images(
                db=db,
                user_id=user.id,
                note=note,
                source_url="https://www.xiaohongshu.com/explore/source-provider-failure-note",
                adapter_factory=FailedAdapter,
            )

        assert exc_info.value.code == "source_detail_failed"
        assert exc_info.value.status_code == 502
        assert exc_info.value.account_id is not None
        assert call_count == 1
    finally:
        db.close()


def test_authenticated_source_import_does_not_chain_provider_exception_with_cookie_secret(caplog):
    SessionLocal = override_database()
    db = SessionLocal()
    try:
        user, note, _bound = create_source_import_note(db, username="source-secret-exception")
        secret = "a1=exception-secret; web_session=exception-session"
        add_source_import_account(db, user_id=user.id, nickname="eligible", cookie_text=secret)
        db.commit()

        class RaisingAdapter:
            def __init__(self, _cookies: str):
                pass

            def get_note_info(self, _url: str):
                raise RuntimeError(f"provider failed with {secret}")

        with caplog.at_level("WARNING", logger="backend.app.services.xhs_source_image_import_service"):
            with pytest.raises(SourceImageDetailError) as exc_info:
                fetch_authenticated_source_images(
                    db=db,
                    user_id=user.id,
                    note=note,
                    source_url="https://www.xiaohongshu.com/explore/source-secret-exception-note",
                    adapter_factory=RaisingAdapter,
                )

        assert exc_info.value.code == "source_detail_failed"
        assert exc_info.value.account_id is not None
        assert exc_info.value.__cause__ is None
        assert secret not in repr(exc_info.value)
        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert record.account_id > 0
        assert record.exception_type == "RuntimeError"
        assert record.stage == "provider_request"
        assert secret not in caplog.text
        assert "provider failed with" not in caplog.text
    finally:
        db.close()


def test_authenticated_source_import_accepts_latest_json_and_string_cookies_without_exposing_secrets():
    SessionLocal = override_database()
    db = SessionLocal()
    try:
        user, note, _bound = create_source_import_note(db, username="source-cookie-formats")
        raw_account = add_source_import_account(
            db,
            user_id=user.id,
            nickname="raw",
            cookie_text="a1=raw-secret; web_session=raw-session",
            updated_at=datetime(2026, 7, 12, 10, 0),
        )
        json_account = add_source_import_account(
            db,
            user_id=user.id,
            nickname="json",
            cookie_text=None,
            updated_at=datetime(2026, 7, 12, 11, 0),
        )
        db.add_all(
            [
                AccountCookieVersion(
                    platform_account_id=json_account.id,
                    encrypted_cookies=encrypt_text("a1=obsolete-secret"),
                    created_at=datetime(2026, 7, 12, 9, 0),
                ),
                AccountCookieVersion(
                    platform_account_id=json_account.id,
                    encrypted_cookies=encrypt_text('{"a1":"json-secret","web_session":"json-session"}'),
                    created_at=datetime(2026, 7, 12, 12, 0),
                ),
            ]
        )
        db.commit()
        normalized_formats: list[str] = []

        class FormatAdapter:
            def __init__(self, cookies: str):
                if cookies == "a1=json-secret; web_session=json-session":
                    self.kind = "json"
                elif cookies == "a1=raw-secret; web_session=raw-session":
                    self.kind = "string"
                else:
                    self.kind = "invalid"
                normalized_formats.append(self.kind)

            def get_note_info(self, _url: str):
                if self.kind == "json":
                    return False, "登录已过期", {"code": -100}
                return True, "ok", source_image_payload("cookie-formats")

        result = fetch_authenticated_source_images(
            db=db,
            user_id=user.id,
            note=note,
            source_url="https://www.xiaohongshu.com/explore/source-cookie-formats-note",
            adapter_factory=FormatAdapter,
        )

        assert result.account_id == raw_account.id
        assert normalized_formats == ["json", "string"]
        result_repr = repr(result)
        assert "json-secret" not in result_repr
        assert "raw-secret" not in result_repr
        assert "obsolete-secret" not in result_repr
    finally:
        db.close()

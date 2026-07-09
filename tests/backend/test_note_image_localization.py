from __future__ import annotations

import json

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.database import Base, get_db
from backend.app.core.security import create_access_token, hash_password
from backend.app.main import app
from backend.app.models import Note, NoteAsset, PlatformAccount, User


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
        _user_id, note_id, headers = create_user_headers(SessionLocal, username="source-image-import-sanitized")

        def fake_fetch(source_url: str) -> list[str]:
            assert source_url == "https://www.xiaohongshu.com/explore/note-1?xsec_token=secret-token&xsec_source=pc_feed"
            return ["https://sns-img-bd.xhscdn.com/notes_pre_post/new-image"]

        monkeypatch.setattr("backend.app.api.notes.fetch_xhs_note_image_urls", fake_fetch, raising=False)
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
            db.commit()
        finally:
            db.close()

        source_urls = [
            existing_url + "?imageView2/2/w/360/format/webp",
            "https://sns-img-bd.xhscdn.com/notes_pre_post/new-image-a",
            "https://sns-img-bd.xhscdn.com/notes_pre_post/new-image-b",
        ]

        def fake_fetch(_source_url: str) -> list[str]:
            return source_urls

        def fake_download(url: str, owner_id: int, asset_type: str) -> str | None:
            download_calls.append((url, owner_id, asset_type))
            return f"downloaded-{len(download_calls)}.jpg"

        monkeypatch.setattr("backend.app.api.notes.fetch_xhs_note_image_urls", fake_fetch, raising=False)
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
        app.dependency_overrides.pop(get_db, None)


def test_import_source_images_downloads_existing_remote_images_without_duplicating(monkeypatch):
    SessionLocal = override_database()
    download_calls: list[tuple[str, int, str]] = []
    try:
        user_id, note_id, headers = create_user_headers(SessionLocal, username="source-image-existing-localizer")
        existing_url = "https://sns-webpic-qc.xhscdn.com/202607071002/a/notes_pre_post/existing!nd_dft_wlteh_webp_3"
        db = SessionLocal()
        try:
            db.add_all(
                [
                    NoteAsset(note_id=note_id, asset_type="image", url=existing_url, local_path="", sort_order=0),
                    NoteAsset(note_id=note_id, asset_type="video", url="https://cdn.example.test/v.mp4", local_path="", sort_order=1),
                ]
            )
            db.commit()
        finally:
            db.close()

        def fake_fetch(_source_url: str) -> list[str]:
            return [existing_url + "?imageView2/2/w/360/format/webp"]

        def fake_download(url: str, owner_id: int, asset_type: str) -> str | None:
            download_calls.append((url, owner_id, asset_type))
            return "downloaded-existing.jpg"

        monkeypatch.setattr("backend.app.api.notes.fetch_xhs_note_image_urls", fake_fetch, raising=False)
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
                "url": existing_url + "?imageView2/2/w/360/format/webp",
                "status": "downloaded",
                "asset_id": payload["items"][0]["asset_id"],
                "local_path": "downloaded-existing.jpg",
                "error": "",
            }
        ]
        assert download_calls == [(existing_url + "?imageView2/2/w/360/format/webp", user_id, "image")]

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
            assert note.raw_json["source_image_import"]["total_source_image_count"] == 2
            assert note.raw_json["source_image_import"]["downloaded_count"] == 2
            assert note.raw_json["source_image_import"]["failed_count"] == 0
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


def test_import_source_images_reports_existing_raw_images_when_page_fetch_returns_empty(monkeypatch):
    SessionLocal = override_database()
    try:
        _user_id, note_id, headers = create_user_headers(SessionLocal, username="source-image-existing-raw")
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
            db.commit()
        finally:
            db.close()

        monkeypatch.setattr("backend.app.api.notes.fetch_xhs_note_image_urls", lambda _source_url: [], raising=False)
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
    finally:
        app.dependency_overrides.pop(get_db, None)

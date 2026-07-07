from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import Base, get_db
from backend.app.core.security import create_access_token, hash_password
from backend.app.main import app
from backend.app.models import Note, NoteAsset, NoteComment, PlatformAccount, User


client = TestClient(app)


SAMPLE_NOTE_URL = (
    "https://www.xiaohongshu.com/explore/6a45e1250000000022014470"
    "?xsec_token=FBttxOcAnoV_1mPPAfhqpCaAS8_GCdUkcCV20uklQwiHw=&xsec_source=pc_feed"
)
SAMPLE_CLEAN_NOTE_URL = "https://www.xiaohongshu.com/explore/6a45e1250000000022014470"


def override_database(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'xhs-page-import-test.db'}",
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


def create_user_headers(SessionLocal):
    db = SessionLocal()
    try:
        user = User(username="page-importer", password_hash=hash_password("secret123"))
        db.add(user)
        db.flush()
        account = PlatformAccount(
            user_id=user.id,
            platform="xhs",
            sub_type="page_import",
            external_user_id="current-page",
            nickname="Current page import",
            status="active",
        )
        db.add(account)
        db.commit()
        return user.id, {"Authorization": f"Bearer {create_access_token(user.id)}"}
    finally:
        db.close()


def sample_payload() -> dict:
    image_keys = [
        "notes_pre_post/1040g3k03223tv026na2g5nv0648g80tctrfrc9o",
        "notes_pre_post/1040g3k03223tv026na005nv0648g80tc8psra6o",
        "notes_pre_post/1040g3k03223tv026na0g5nv0648g80tc7qmsgn0",
        "notes_pre_post/1040g3k03223tv026na105nv0648g80tcfj7g5v0",
        "notes_pre_post/1040g3k03223tv026na1g5nv0648g80tc3peehd8",
        "notes_pre_post/1040g3k03223tv026na205nv0648g80tcg1smcto",
    ]
    return {
        "note_id": "6a45e1250000000022014470",
        "note_url": SAMPLE_NOTE_URL,
        "title": "6-image sample note",
        "content": "Body copied from the currently open note page.",
        "author_name": "sample author",
        "tags": ["tag-a", "tag-b", "tag-a"],
        "image_urls": [f"https://sns-webpic-qc.xhscdn.com/202407/{key}!nd_whgt34_webp_3" for key in image_keys],
        "visible_comments": [
            {
                "comment_id": "comment-1",
                "user_name": "commenter",
                "user_id": "user-1",
                "content": "visible comment only",
                "like_count": 3,
                "created_at_remote": "2026-07-07",
                "raw": {"visible": True},
            }
        ],
        "raw": {"note_type": "normal", "source": "current_page", "source_url": SAMPLE_NOTE_URL},
    }


def patch_page_import_downloader(monkeypatch):
    calls: list[tuple[str, int, str]] = []

    def fake_download(url: str, user_id: int, asset_type: str) -> str | None:
        calls.append((url, user_id, asset_type))
        return f"xhs-asset-u{user_id}-{len(calls)}.jpg"

    monkeypatch.setattr("backend.app.api.platforms.xhs.page_import._download_asset", fake_download, raising=False)
    return calls


def test_current_note_import_saves_six_images_and_visible_comments_with_local_images(tmp_path, monkeypatch):
    SessionLocal = override_database(tmp_path)
    try:
        user_id, headers = create_user_headers(SessionLocal)
        download_calls = patch_page_import_downloader(monkeypatch)
        payload = sample_payload()

        response = client.post("/api/xhs/page-import/current-note", headers=headers, json=payload)

        assert response.status_code == 200
        body = response.json()
        assert body["imported"] is True
        assert body["asset_count"] == 6
        assert body["comment_count"] == 1
        assert body["item"]["note_id"] == "6a45e1250000000022014470"

        db = SessionLocal()
        try:
            note = db.scalars(select(Note).where(Note.user_id == user_id)).one()
            assert note.platform == "xhs"
            assert note.title == "6-image sample note"
            assert note.content == "Body copied from the currently open note page."
            assert note.raw_json["note_url"] == SAMPLE_CLEAN_NOTE_URL
            assert note.raw_json["tags"] == ["tag-a", "tag-b"]
            assert note.raw_json["page_import"]["mode"] == "manual_current_page"

            assets = db.scalars(select(NoteAsset).where(NoteAsset.note_id == note.id).order_by(NoteAsset.sort_order)).all()
            assert [asset.asset_type for asset in assets] == ["image"] * 6
            assert [asset.sort_order for asset in assets] == list(range(6))
            assert [asset.local_path for asset in assets] == [f"xhs-asset-u{user_id}-{index}.jpg" for index in range(1, 7)]
            assert "1040g3k03223tv026na2g5nv0648g80tctrfrc9o" in assets[0].url
            assert download_calls == [(url, user_id, "image") for url in payload["image_urls"]]

            comments = db.scalars(select(NoteComment).where(NoteComment.note_id == note.id)).all()
            assert len(comments) == 1
            assert comments[0].comment_id == "comment-1"
            assert comments[0].content == "visible comment only"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_current_note_import_replaces_assets_on_repeat_import(tmp_path, monkeypatch):
    SessionLocal = override_database(tmp_path)
    try:
        _user_id, headers = create_user_headers(SessionLocal)
        patch_page_import_downloader(monkeypatch)
        first = sample_payload()
        second = sample_payload()
        second["title"] = "updated title"
        second["image_urls"] = [
            "https://sns-webpic-qc.xhscdn.com/202407/notes_pre_post/updated-a!nd_whgt34_webp_3",
            "https://sns-webpic-qc.xhscdn.com/202407/notes_pre_post/updated-b!nd_whgt34_webp_3",
        ]

        assert client.post("/api/xhs/page-import/current-note", headers=headers, json=first).status_code == 200
        response = client.post("/api/xhs/page-import/current-note", headers=headers, json=second)

        assert response.status_code == 200
        body = response.json()
        assert body["imported"] is False
        assert body["asset_count"] == 2
        assert body["item"]["title"] == "updated title"

        db = SessionLocal()
        try:
            note = db.scalars(select(Note)).one()
            assets = db.scalars(select(NoteAsset).where(NoteAsset.note_id == note.id).order_by(NoteAsset.sort_order)).all()
            assert len(assets) == 2
            assert assets[0].url.endswith("updated-a!nd_whgt34_webp_3")
            assert assets[1].url.endswith("updated-b!nd_whgt34_webp_3")
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_current_note_import_rejects_empty_media_payload(tmp_path):
    SessionLocal = override_database(tmp_path)
    try:
        _user_id, headers = create_user_headers(SessionLocal)
        payload = sample_payload()
        payload["image_urls"] = []
        payload["video_url"] = ""

        response = client.post("/api/xhs/page-import/current-note", headers=headers, json=payload)

        assert response.status_code == 422
        assert response.json()["detail"] == "No media URLs found on the current note page"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_current_note_import_sanitizes_note_url_and_comment_user_ids(tmp_path, monkeypatch):
    SessionLocal = override_database(tmp_path)
    try:
        user_id, headers = create_user_headers(SessionLocal)
        patch_page_import_downloader(monkeypatch)
        payload = sample_payload()
        payload["visible_comments"] = [
            {
                "comment_id": "comment-with-token",
                "user_name": "commenter",
                "user_id": (
                    "5efb4b8b00000000010068f6?channel_type=web_note_detail_r10"
                    f"&xsec_token={'secret' * 30}"
                ),
                "content": "visible comment only",
            }
        ]

        response = client.post("/api/xhs/page-import/current-note", headers=headers, json=payload)

        assert response.status_code == 200
        db = SessionLocal()
        try:
            note = db.scalars(select(Note).where(Note.user_id == user_id)).one()
            assert note.raw_json["note_url"] == SAMPLE_CLEAN_NOTE_URL
            assert note.raw_json["source_url"] == SAMPLE_CLEAN_NOTE_URL
            comment = db.scalars(select(NoteComment).where(NoteComment.note_id == note.id)).one()
            assert comment.user_id == "5efb4b8b00000000010068f6"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.api.platforms.xhs.data_acquisition import get_data_acquisition_note_source
from backend.app.core.database import Base, get_db
from backend.app.core.security import create_access_token, encrypt_text, hash_password
from backend.app.main import app
from backend.app.models import (
    AccountCookieVersion,
    DataAcquisitionCandidate,
    DataAcquisitionRun,
    Note,
    NoteAsset,
    NoteSourceSnapshot,
    PlatformAccount,
    Task,
    User,
)

client = TestClient(app)


class FakeNoteSource:
    def __init__(self, rows: list[dict[str, Any]] | None = None, error: str | None = None) -> None:
        self.rows = rows or []
        self.error = error
        self.calls: list[tuple[str, str, int, dict[str, Any]]] = []

    def search_notes(self, cookie_text: str, keyword: str, limit: int, **params: Any) -> list[dict[str, Any]]:
        self.calls.append((cookie_text, keyword, limit, params))
        if self.error is not None:
            raise RuntimeError(self.error)
        return self.rows[:limit]


def override_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'xhs-data-acquisition-test.db'}", connect_args={"check_same_thread": False})
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


def create_user_account_and_headers(SessionLocal):
    db = SessionLocal()
    try:
        user = User(username="operator", password_hash=hash_password("secret123"))
        db.add(user)
        db.flush()
        account = PlatformAccount(
            user_id=user.id,
            platform="huitun",
            sub_type="main",
            external_user_id="huitun-1",
            nickname="data account",
            status="active",
        )
        db.add(account)
        db.flush()
        db.add(AccountCookieVersion(platform_account_id=account.id, encrypted_cookies=encrypt_text("session=ok")))
        db.commit()
        return user.id, account.id, {"Authorization": f"Bearer {create_access_token(user.id)}"}
    finally:
        db.close()


def test_note_search_run_creates_candidates_without_exposing_internal_source(tmp_path):
    SessionLocal = override_database(tmp_path)
    fake = FakeNoteSource(
        [
            {
                "platform_note_id": "note-1",
                "external_id": "note-1",
                "original_url": "https://www.xiaohongshu.com/explore/note-1",
                "title": "浴缸收纳",
                "content_excerpt": "浴缸收纳方案",
                "author_name": "家居作者",
                "cover_url": "https://sns-img-hw.xhscdn.com/cover.jpg",
                "asset_urls": ["https://sns-img-hw.xhscdn.com/cover.jpg"],
                "metrics": {"like_count": 10, "collect_count": 5, "comment_count": 2, "share_count": 1},
                "raw": {"noteId": "note-1", "title": "浴缸收纳"},
            }
        ]
    )
    app.dependency_overrides[get_data_acquisition_note_source] = lambda: fake
    try:
        _user_id, account_id, headers = create_user_account_and_headers(SessionLocal)

        response = client.post(
            "/api/xhs/data-acquisition/runs",
            headers=headers,
            json={
                "acquisition_type": "note_search",
                "account_id": account_id,
                "params": {"keyword": "浴缸", "limit": 50, "sort": "interaction", "note_type": "all"},
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "completed"
        assert payload["acquisition_type"] == "note_search"
        assert payload["effective_limit"] == 50
        assert payload["candidate_count"] == 1
        assert "source" not in payload
        assert "admin_debug" not in payload
        assert "huitun" not in str(payload).lower()
        assert "extData" not in str(payload)
        assert fake.calls == [("session=ok", "浴缸", 50, {"sort": "interaction", "note_type": "all"})]

        candidates_response = client.get("/api/xhs/data-acquisition/candidates", headers=headers)
        assert candidates_response.status_code == 200
        candidates = candidates_response.json()["items"]
        assert candidates[0]["title"] == "浴缸收纳"
        assert candidates[0]["status"] == "pending"
        assert candidates[0]["metrics"]["like_count"] == 10
        assert "source" not in candidates[0]
        assert "raw_json" not in candidates[0]
    finally:
        app.dependency_overrides.pop(get_data_acquisition_note_source, None)
        app.dependency_overrides.pop(get_db, None)


def test_admin_debug_query_does_not_expose_internal_source_to_ordinary_user(tmp_path):
    SessionLocal = override_database(tmp_path)
    fake = FakeNoteSource(
        [
            {
                "platform_note_id": "note-1",
                "external_id": "note-1",
                "title": "浴缸收纳",
                "content_excerpt": "浴缸收纳方案",
                "metrics": {"like_count": 10},
                "raw": {"noteId": "note-1"},
            }
        ]
    )
    app.dependency_overrides[get_data_acquisition_note_source] = lambda: fake
    try:
        _user_id, account_id, headers = create_user_account_and_headers(SessionLocal)

        create_response = client.post(
            "/api/xhs/data-acquisition/runs",
            headers=headers,
            json={
                "acquisition_type": "note_search",
                "account_id": account_id,
                "params": {"keyword": "浴缸", "limit": 10},
            },
        )
        run_id = create_response.json()["id"]

        run_response = client.get(
            f"/api/xhs/data-acquisition/runs/{run_id}?include_admin_debug=true",
            headers=headers,
        )
        candidates_response = client.get(
            "/api/xhs/data-acquisition/candidates?include_admin_debug=true",
            headers=headers,
        )

        assert run_response.status_code == 200
        assert candidates_response.status_code == 200
        combined = str({"run": run_response.json(), "candidates": candidates_response.json()})
        assert "admin_debug" not in combined
        assert "raw_json" not in combined
        assert "source_mode" not in combined
        assert "huitun" not in combined.lower()
        assert "extData" not in combined
    finally:
        app.dependency_overrides.pop(get_data_acquisition_note_source, None)
        app.dependency_overrides.pop(get_db, None)


def test_note_search_failure_records_failed_run_without_fallback_candidates(tmp_path):
    SessionLocal = override_database(tmp_path)
    fake = FakeNoteSource(error="search structure changed")
    app.dependency_overrides[get_data_acquisition_note_source] = lambda: fake
    try:
        _user_id, account_id, headers = create_user_account_and_headers(SessionLocal)

        response = client.post(
            "/api/xhs/data-acquisition/runs",
            headers=headers,
            json={
                "acquisition_type": "note_search",
                "account_id": account_id,
                "params": {"keyword": "浴缸", "limit": 10},
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "failed"
        assert payload["user_message"] == "本次数据获取失败，任务已停止。"
        assert payload["candidate_count"] == 0

        db = SessionLocal()
        try:
            run = db.scalars(select(DataAcquisitionRun)).one()
            task = db.scalars(select(Task)).one()
            assert run.status == "failed"
            assert run.error_code == "note_search_failed"
            assert task.status == "failed"
            assert db.scalars(select(DataAcquisitionCandidate)).all() == []
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_data_acquisition_note_source, None)
        app.dependency_overrides.pop(get_db, None)


def test_unverified_acquisition_types_are_rejected_without_creating_task(tmp_path):
    SessionLocal = override_database(tmp_path)
    try:
        _user_id, account_id, headers = create_user_account_and_headers(SessionLocal)

        response = client.post(
            "/api/xhs/data-acquisition/runs",
            headers=headers,
            json={
                "acquisition_type": "note_rank",
                "account_id": account_id,
                "params": {"rank_type": "hot_notes", "limit": 10},
            },
        )

        assert response.status_code == 422
        assert "仍在验证中" in response.json()["detail"]
        db = SessionLocal()
        try:
            assert db.scalars(select(Task)).all() == []
            assert db.scalars(select(DataAcquisitionRun)).all() == []
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_import_candidates_reuses_existing_note_and_creates_snapshot_without_downloading_assets(tmp_path):
    SessionLocal = override_database(tmp_path)
    fake = FakeNoteSource(
        [
            {
                "platform_note_id": "note-1",
                "external_id": "note-1",
                "original_url": "https://www.xiaohongshu.com/explore/note-1",
                "title": "浴缸收纳",
                "content_excerpt": "浴缸收纳方案",
                "author_name": "家居作者",
                "cover_url": "https://sns-img-hw.xhscdn.com/cover.jpg",
                "asset_urls": [
                    "https://sns-img-hw.xhscdn.com/cover.jpg",
                    "https://sns-img-hw.xhscdn.com/detail.jpg",
                ],
                "metrics": {"like_count": 10, "collect_count": 5, "comment_count": 2, "share_count": 1},
                "raw": {"noteId": "note-1", "videoUrl": "https://sns-video-v6.xhscdn.com/video.mp4"},
            }
        ]
    )
    app.dependency_overrides[get_data_acquisition_note_source] = lambda: fake
    try:
        user_id, account_id, headers = create_user_account_and_headers(SessionLocal)
        db = SessionLocal()
        try:
            existing = Note(
                user_id=user_id,
                platform_account_id=account_id,
                platform="xhs",
                note_id="note-1",
                title="旧标题",
                content="旧内容",
                author_name="旧作者",
                raw_json={"existing": True},
            )
            db.add(existing)
            db.commit()
            existing_id = existing.id
        finally:
            db.close()

        run_response = client.post(
            "/api/xhs/data-acquisition/runs",
            headers=headers,
            json={
                "acquisition_type": "note_search",
                "account_id": account_id,
                "params": {"keyword": "浴缸", "limit": 10},
            },
        )
        candidate_id = run_response.json()["candidates"][0]["id"]

        import_response = client.post(
            "/api/xhs/data-acquisition/candidates/import",
            headers=headers,
            json={"candidate_ids": [candidate_id]},
        )

        assert import_response.status_code == 200
        payload = import_response.json()
        assert payload["imported_count"] == 1
        assert payload["items"][0]["id"] == existing_id
        assert payload["message"] == "已入库 1 条笔记，可前往分析中心生成洞察。"

        db = SessionLocal()
        try:
            notes = db.scalars(select(Note)).all()
            assert len(notes) == 1
            note = notes[0]
            assert note.id == existing_id
            assert note.title == "浴缸收纳"
            assert note.raw_json["data_acquisition"]["original_url"].endswith("/note-1")
            assets = db.scalars(select(NoteAsset).where(NoteAsset.note_id == note.id).order_by(NoteAsset.sort_order.asc())).all()
            assert [asset.url for asset in assets] == [
                "https://sns-img-hw.xhscdn.com/cover.jpg",
                "https://sns-img-hw.xhscdn.com/detail.jpg",
            ]
            assert all(asset.local_path == "" for asset in assets)
            snapshot = db.scalars(select(NoteSourceSnapshot)).one()
            assert snapshot.note_id == note.id
            assert snapshot.snapshot_type == "search_result"
            assert snapshot.metrics_json["like_count"] == 10
            candidate = db.get(DataAcquisitionCandidate, candidate_id)
            assert candidate is not None
            assert candidate.status == "imported"
            assert candidate.imported_note_id == note.id
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_data_acquisition_note_source, None)
        app.dependency_overrides.pop(get_db, None)

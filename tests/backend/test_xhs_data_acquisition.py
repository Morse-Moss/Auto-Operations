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
    UsageLedger,
    User,
)
from backend.app.core.time import shanghai_now

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


def sample_note_row(note_id: str = "note-1", title: str = "浴缸收纳") -> dict[str, Any]:
    return {
        "platform_note_id": note_id,
        "external_id": note_id,
        "original_url": f"https://www.xiaohongshu.com/explore/{note_id}",
        "title": title,
        "content_excerpt": f"{title}方案",
        "author_name": "家居作者",
        "cover_url": f"https://sns-img-hw.xhscdn.com/{note_id}.jpg",
        "asset_urls": [f"https://sns-img-hw.xhscdn.com/{note_id}.jpg"],
        "metrics": {"like_count": 10, "collect_count": 5, "comment_count": 2, "share_count": 1},
        "raw": {"noteId": note_id, "title": title},
    }


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
        admin = User(username="data-admin", password_hash=hash_password("secret123"), role="admin")
        db.add(user)
        db.add(admin)
        db.flush()
        account = PlatformAccount(
            user_id=admin.id,
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


def create_successful_run(
    *,
    SessionLocal,
    headers: dict[str, str],
    account_id: int,
    rows: list[dict[str, Any]] | None = None,
    keyword: str = "浴缸",
    limit: int = 10,
):
    fake = FakeNoteSource(rows or [sample_note_row()])
    app.dependency_overrides[get_data_acquisition_note_source] = lambda: fake
    response = client.post(
        "/api/xhs/data-acquisition/runs",
        headers=headers,
        json={
            "acquisition_type": "note_search",
            "account_id": account_id,
            "params": {"keyword": keyword, "limit": limit, "sort": "interaction", "note_type": "all"},
        },
    )
    assert response.status_code == 200
    return response.json(), fake


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


def test_note_search_uses_platform_data_account_without_user_account_id(tmp_path):
    SessionLocal = override_database(tmp_path)
    fake = FakeNoteSource([sample_note_row("note-platform", "Platform account result")])
    app.dependency_overrides[get_data_acquisition_note_source] = lambda: fake
    try:
        _user_id, account_id, headers = create_user_account_and_headers(SessionLocal)

        response = client.post(
            "/api/xhs/data-acquisition/runs",
            headers=headers,
            json={
                "acquisition_type": "note_search",
                "params": {"keyword": "platform keyword", "limit": 5, "sort": "interaction", "note_type": "all"},
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "completed"
        assert payload["candidate_count"] == 1
        assert fake.calls == [("session=ok", "platform keyword", 5, {"sort": "interaction", "note_type": "all"})]

        db = SessionLocal()
        try:
            run = db.scalars(select(DataAcquisitionRun)).one()
            assert run.account_id == account_id
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_data_acquisition_note_source, None)
        app.dependency_overrides.pop(get_db, None)


def test_note_search_daily_user_limit_returns_429_without_calling_source(tmp_path):
    SessionLocal = override_database(tmp_path)
    fake = FakeNoteSource([sample_note_row()])
    app.dependency_overrides[get_data_acquisition_note_source] = lambda: fake
    try:
        user_id, _account_id, headers = create_user_account_and_headers(SessionLocal)
        db = SessionLocal()
        try:
            for index in range(20):
                db.add(
                    UsageLedger(
                        tenant_id=1,
                        user_id=user_id,
                        feature_key="xhs.data_acquisition.note_search",
                        bucket="data_acquisition_note_search",
                        operation="commit",
                        amount=1,
                        balance_after=20 - index,
                        status="completed",
                        idempotency_key=f"seed:{index}",
                        created_at=shanghai_now(),
                    )
                )
            db.commit()
        finally:
            db.close()

        response = client.post(
            "/api/xhs/data-acquisition/runs",
            headers=headers,
            json={
                "acquisition_type": "note_search",
                "params": {"keyword": "rate limit", "limit": 5},
            },
        )

        assert response.status_code == 429
        assert response.json()["detail"]["code"] == "data_acquisition_daily_limit_exceeded"
        assert fake.calls == []
        db = SessionLocal()
        try:
            assert db.scalars(select(DataAcquisitionRun)).all() == []
            assert db.scalars(select(Task)).all() == []
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_data_acquisition_note_source, None)
        app.dependency_overrides.pop(get_db, None)


def test_rerun_creates_new_run_without_overwriting_failed_original(tmp_path):
    SessionLocal = override_database(tmp_path)
    failing = FakeNoteSource(error="temporary upstream failure")
    app.dependency_overrides[get_data_acquisition_note_source] = lambda: failing
    try:
        _user_id, account_id, headers = create_user_account_and_headers(SessionLocal)
        failed_response = client.post(
            "/api/xhs/data-acquisition/runs",
            headers=headers,
            json={
                "acquisition_type": "note_search",
                "account_id": account_id,
                "params": {"keyword": "浴缸", "limit": 10, "sort": "interaction", "note_type": "all"},
            },
        )
        failed_payload = failed_response.json()
        assert failed_payload["status"] == "failed"

        succeeding = FakeNoteSource([sample_note_row("note-rerun", "重跑结果")])
        app.dependency_overrides[get_data_acquisition_note_source] = lambda: succeeding
        rerun_response = client.post(
            f"/api/xhs/data-acquisition/runs/{failed_payload['id']}/rerun",
            headers=headers,
        )

        assert rerun_response.status_code == 200
        rerun_payload = rerun_response.json()
        assert rerun_payload["id"] != failed_payload["id"]
        assert rerun_payload["status"] == "completed"
        assert rerun_payload["params"] == failed_payload["params"]
        assert rerun_payload["candidate_count"] == 1
        assert "huitun" not in str(rerun_payload).lower()

        db = SessionLocal()
        try:
            original = db.get(DataAcquisitionRun, failed_payload["id"])
            new_run = db.get(DataAcquisitionRun, rerun_payload["id"])
            assert original is not None
            assert original.status == "failed"
            assert original.error_code == "note_search_failed"
            assert new_run is not None
            assert new_run.rerun_of_run_id == original.id
            assert new_run.params_json == original.params_json
            assert new_run.account_id == original.account_id
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_data_acquisition_note_source, None)
        app.dependency_overrides.pop(get_db, None)


def test_cancel_pending_and_running_runs_keep_task_state_consistent(tmp_path):
    SessionLocal = override_database(tmp_path)
    try:
        user_id, account_id, headers = create_user_account_and_headers(SessionLocal)
        db = SessionLocal()
        try:
            pending_task = Task(user_id=user_id, platform="xhs", task_type="data_acquisition_note_search", status="pending", progress=0)
            running_task = Task(user_id=user_id, platform="xhs", task_type="data_acquisition_note_search", status="running", progress=25)
            db.add_all([pending_task, running_task])
            db.flush()
            pending_run = DataAcquisitionRun(
                task_id=pending_task.id,
                user_id=user_id,
                account_id=account_id,
                platform="xhs",
                acquisition_type="note_search",
                source="huitun",
                source_mode="live_account",
                status="pending",
                requested_limit=10,
                effective_limit=10,
                params_json={"keyword": "浴缸", "limit": 10},
            )
            running_run = DataAcquisitionRun(
                task_id=running_task.id,
                user_id=user_id,
                account_id=account_id,
                platform="xhs",
                acquisition_type="note_search",
                source="huitun",
                source_mode="live_account",
                status="running",
                requested_limit=10,
                effective_limit=10,
                params_json={"keyword": "浴缸", "limit": 10},
            )
            db.add_all([pending_run, running_run])
            db.commit()
            pending_run_id = pending_run.id
            running_run_id = running_run.id
            pending_task_id = pending_task.id
            running_task_id = running_task.id
        finally:
            db.close()

        pending_response = client.post(f"/api/xhs/data-acquisition/runs/{pending_run_id}/cancel", headers=headers)
        running_response = client.post(f"/api/xhs/data-acquisition/runs/{running_run_id}/cancel", headers=headers)

        assert pending_response.status_code == 200
        assert running_response.status_code == 200
        assert pending_response.json()["status"] == "cancelled"
        assert running_response.json()["status"] == "running"
        assert running_response.json()["cancellation_requested"] is True

        db = SessionLocal()
        try:
            pending_run_after = db.get(DataAcquisitionRun, pending_run_id)
            running_run_after = db.get(DataAcquisitionRun, running_run_id)
            pending_task_after = db.get(Task, pending_task_id)
            running_task_after = db.get(Task, running_task_id)
            assert pending_run_after is not None
            assert pending_run_after.status == "cancelled"
            assert pending_run_after.finished_at is not None
            assert pending_task_after is not None
            assert pending_task_after.status == "cancelled"
            assert pending_task_after.finished_at is not None
            assert running_run_after is not None
            assert running_run_after.status == "running"
            assert running_run_after.cancellation_requested is True
            assert running_task_after is not None
            assert running_task_after.status == "running"
            assert running_task_after.finished_at is None
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_exclude_and_restore_candidates_update_filters_and_decision_reason(tmp_path):
    SessionLocal = override_database(tmp_path)
    try:
        _user_id, account_id, headers = create_user_account_and_headers(SessionLocal)
        run_payload, _fake = create_successful_run(
            SessionLocal=SessionLocal,
            headers=headers,
            account_id=account_id,
            rows=[sample_note_row("note-a", "A"), sample_note_row("note-b", "B")],
        )
        first_id = run_payload["candidates"][0]["id"]
        second_id = run_payload["candidates"][1]["id"]

        exclude_response = client.post(
            "/api/xhs/data-acquisition/candidates/exclude",
            headers=headers,
            json={"candidate_ids": [first_id], "reason_code": "irrelevant", "reason_text": "不相关"},
        )
        pending_after_exclude = client.get(
            f"/api/xhs/data-acquisition/candidates?run_id={run_payload['id']}&status=pending",
            headers=headers,
        )
        excluded_after_exclude = client.get(
            f"/api/xhs/data-acquisition/candidates?run_id={run_payload['id']}&status=excluded",
            headers=headers,
        )

        assert exclude_response.status_code == 200
        excluded_item = exclude_response.json()["items"][0]
        assert excluded_item["id"] == first_id
        assert excluded_item["status"] == "excluded"
        assert excluded_item["decision_reason_code"] == "irrelevant"
        assert [item["id"] for item in pending_after_exclude.json()["items"]] == [second_id]
        assert [item["id"] for item in excluded_after_exclude.json()["items"]] == [first_id]

        restore_response = client.post(
            "/api/xhs/data-acquisition/candidates/restore",
            headers=headers,
            json={"candidate_ids": [first_id]},
        )
        pending_after_restore = client.get(
            f"/api/xhs/data-acquisition/candidates?run_id={run_payload['id']}&status=pending",
            headers=headers,
        )

        assert restore_response.status_code == 200
        restored_item = restore_response.json()["items"][0]
        assert restored_item["status"] == "pending"
        assert restored_item["decision_reason_code"] == ""
        assert {item["id"] for item in pending_after_restore.json()["items"]} == {first_id, second_id}
    finally:
        app.dependency_overrides.pop(get_data_acquisition_note_source, None)
        app.dependency_overrides.pop(get_db, None)


def test_list_runs_reports_candidate_count_and_task_center_links_to_run(tmp_path):
    SessionLocal = override_database(tmp_path)
    try:
        _user_id, account_id, headers = create_user_account_and_headers(SessionLocal)
        run_payload, _fake = create_successful_run(
            SessionLocal=SessionLocal,
            headers=headers,
            account_id=account_id,
            rows=[sample_note_row("note-a", "A"), sample_note_row("note-b", "B")],
        )

        runs_response = client.get("/api/xhs/data-acquisition/runs", headers=headers)
        tasks_response = client.get("/api/tasks?platform=xhs", headers=headers)
        task_response = client.get(f"/api/tasks/{run_payload['task_id']}", headers=headers)

        assert runs_response.status_code == 200
        listed_run = runs_response.json()["items"][0]
        assert listed_run["id"] == run_payload["id"]
        assert listed_run["candidate_count"] == 2
        assert "huitun" not in str(listed_run).lower()

        assert tasks_response.status_code == 200
        listed_task = tasks_response.json()["items"][0]
        assert listed_task["id"] == run_payload["task_id"]
        assert listed_task["payload"]["data_acquisition_run_id"] == run_payload["id"]
        assert listed_task["payload"]["data_acquisition_url"] == f"/platforms/xhs/crawler?run_id={run_payload['id']}"
        assert "huitun" not in str(listed_task).lower()

        assert task_response.status_code == 200
        assert task_response.json()["payload"]["data_acquisition_run_id"] == run_payload["id"]
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


def test_note_search_does_not_call_source_when_data_account_is_expired(tmp_path):
    SessionLocal = override_database(tmp_path)
    fake = FakeNoteSource([sample_note_row()])
    app.dependency_overrides[get_data_acquisition_note_source] = lambda: fake
    try:
        _user_id, account_id, headers = create_user_account_and_headers(SessionLocal)
        db = SessionLocal()
        try:
            account = db.get(PlatformAccount, account_id)
            account.status = "expired"
            db.commit()
        finally:
            db.close()

        response = client.post(
            "/api/xhs/data-acquisition/runs",
            headers=headers,
            json={
                "acquisition_type": "note_search",
                "account_id": account_id,
                "params": {"keyword": "浴缸", "limit": 3, "sort": "interaction", "note_type": "all"},
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "failed"
        assert payload["candidate_count"] == 0
        assert fake.calls == []
        assert payload["user_message"] == "本次数据获取失败，任务已停止。"

        db = SessionLocal()
        try:
            run = db.scalars(select(DataAcquisitionRun)).one()
            assert "数据账号登录状态已过期" in run.error_message
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


def test_import_excluded_candidate_requires_restore_first(tmp_path):
    SessionLocal = override_database(tmp_path)
    try:
        _user_id, account_id, headers = create_user_account_and_headers(SessionLocal)
        run_payload, _fake = create_successful_run(
            SessionLocal=SessionLocal,
            headers=headers,
            account_id=account_id,
            rows=[sample_note_row("note-excluded", "Excluded")],
        )
        candidate_id = run_payload["candidates"][0]["id"]

        exclude_response = client.post(
            "/api/xhs/data-acquisition/candidates/exclude",
            headers=headers,
            json={"candidate_ids": [candidate_id], "reason_code": "manual_exclude"},
        )
        import_response = client.post(
            "/api/xhs/data-acquisition/candidates/import",
            headers=headers,
            json={"candidate_ids": [candidate_id]},
        )

        assert exclude_response.status_code == 200
        assert import_response.status_code == 422
        assert import_response.json()["detail"] == "请先恢复已排除候选，再执行入库。"

        db = SessionLocal()
        try:
            candidate = db.get(DataAcquisitionCandidate, candidate_id)
            assert candidate is not None
            assert candidate.status == "excluded"
            assert db.scalars(select(Note)).all() == []
            assert db.scalars(select(NoteSourceSnapshot)).all() == []
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_data_acquisition_note_source, None)
        app.dependency_overrides.pop(get_db, None)


def test_task_center_cancel_coordinates_with_data_acquisition_runs(tmp_path):
    SessionLocal = override_database(tmp_path)
    try:
        user_id, account_id, headers = create_user_account_and_headers(SessionLocal)
        db = SessionLocal()
        try:
            pending_task = Task(
                user_id=user_id,
                platform="xhs",
                task_type="data_acquisition_note_search",
                status="pending",
                progress=0,
                payload={},
            )
            running_task = Task(
                user_id=user_id,
                platform="xhs",
                task_type="data_acquisition_note_search",
                status="running",
                progress=20,
                payload={},
            )
            db.add_all([pending_task, running_task])
            db.flush()
            pending_run = DataAcquisitionRun(
                task_id=pending_task.id,
                user_id=user_id,
                account_id=account_id,
                platform="xhs",
                acquisition_type="note_search",
                source="huitun",
                source_mode="live_account",
                status="pending",
                requested_limit=10,
                effective_limit=10,
                params_json={"keyword": "pending"},
            )
            running_run = DataAcquisitionRun(
                task_id=running_task.id,
                user_id=user_id,
                account_id=account_id,
                platform="xhs",
                acquisition_type="note_search",
                source="huitun",
                source_mode="live_account",
                status="running",
                requested_limit=10,
                effective_limit=10,
                params_json={"keyword": "running"},
            )
            db.add_all([pending_run, running_run])
            db.flush()
            pending_task.payload = {
                "data_acquisition_run_id": pending_run.id,
                "data_acquisition_url": f"/platforms/xhs/crawler?run_id={pending_run.id}",
            }
            running_task.payload = {
                "data_acquisition_run_id": running_run.id,
                "data_acquisition_url": f"/platforms/xhs/crawler?run_id={running_run.id}",
            }
            db.commit()
            pending_task_id = pending_task.id
            running_task_id = running_task.id
            pending_run_id = pending_run.id
            running_run_id = running_run.id
        finally:
            db.close()

        pending_response = client.post(f"/api/tasks/{pending_task_id}/cancel", headers=headers)
        running_response = client.post(f"/api/tasks/{running_task_id}/cancel", headers=headers)

        assert pending_response.status_code == 200
        assert running_response.status_code == 200

        db = SessionLocal()
        try:
            pending_task_after = db.get(Task, pending_task_id)
            running_task_after = db.get(Task, running_task_id)
            pending_run_after = db.get(DataAcquisitionRun, pending_run_id)
            running_run_after = db.get(DataAcquisitionRun, running_run_id)
            assert pending_task_after is not None
            assert pending_task_after.status == "cancelled"
            assert pending_task_after.finished_at is not None
            assert pending_run_after is not None
            assert pending_run_after.status == "cancelled"
            assert pending_run_after.finished_at is not None
            assert running_task_after is not None
            assert running_task_after.status == "running"
            assert running_task_after.finished_at is None
            assert running_run_after is not None
            assert running_run_after.status == "running"
            assert running_run_after.cancellation_requested is True
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)

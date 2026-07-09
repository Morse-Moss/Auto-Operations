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
    NoteComment,
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
        self.comment_calls: list[tuple[str, str, dict[str, Any]]] = []

    def search_notes(self, cookie_text: str, keyword: str, limit: int, **params: Any) -> list[dict[str, Any]]:
        self.calls.append((cookie_text, keyword, limit, params))
        if self.error is not None:
            raise RuntimeError(self.error)
        return self.rows[:limit]

    def resolve_note_url(self, cookie_text: str, note_id: str) -> str:
        return ""

    def fetch_note_comments(self, cookie_text: str, note_id: str, **params: Any) -> list[dict[str, Any]]:
        self.comment_calls.append((cookie_text, note_id, params))
        return []


class CommentingFakeNoteSource(FakeNoteSource):
    def __init__(
        self,
        rows: list[dict[str, Any]],
        comments_by_note_id: dict[str, list[dict[str, Any]]] | None = None,
        comment_error: str | None = None,
    ) -> None:
        super().__init__(rows)
        self.comments_by_note_id = comments_by_note_id or {}
        self.comment_error = comment_error

    def fetch_note_comments(self, cookie_text: str, note_id: str, **params: Any) -> list[dict[str, Any]]:
        self.comment_calls.append((cookie_text, note_id, params))
        if self.comment_error is not None:
            raise RuntimeError(self.comment_error)
        return self.comments_by_note_id.get(note_id, [])


class ResolvingFakeNoteSource(FakeNoteSource):
    def __init__(self, rows: list[dict[str, Any]], resolved_urls: dict[str, str]) -> None:
        super().__init__(rows)
        self.resolved_urls = resolved_urls
        self.resolve_calls: list[tuple[str, str]] = []

    def resolve_note_url(self, cookie_text: str, note_id: str) -> str:
        self.resolve_calls.append((cookie_text, note_id))
        return self.resolved_urls.get(note_id, "")


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


def sample_unresolved_note_row(note_id: str = "11548571364", title: str = "浴缸收纳") -> dict[str, Any]:
    row = sample_note_row(note_id, title)
    row["original_url"] = ""
    return row


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


def create_user_headers_without_data_account(SessionLocal):
    db = SessionLocal()
    try:
        user = User(username="operator-no-data-account", password_hash=hash_password("secret123"))
        db.add(user)
        db.commit()
        return user.id, {"Authorization": f"Bearer {create_access_token(user.id)}"}
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
        user_id, account_id, headers = create_user_account_and_headers(SessionLocal)

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


def test_note_search_caps_single_run_at_fifty_candidates(tmp_path):
    SessionLocal = override_database(tmp_path)
    fake = FakeNoteSource([sample_note_row("note-cap", "浴缸收纳")])
    app.dependency_overrides[get_data_acquisition_note_source] = lambda: fake
    try:
        _user_id, account_id, headers = create_user_account_and_headers(SessionLocal)

        response = client.post(
            "/api/xhs/data-acquisition/runs",
            headers=headers,
            json={
                "acquisition_type": "note_search",
                "account_id": account_id,
                "params": {"keyword": "浴缸", "limit": 100, "sort": "interaction", "note_type": "all"},
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["requested_limit"] == 100
        assert payload["effective_limit"] == 50
        assert fake.calls == [("session=ok", "浴缸", 50, {"sort": "interaction", "note_type": "all"})]
    finally:
        app.dependency_overrides.pop(get_data_acquisition_note_source, None)
        app.dependency_overrides.pop(get_db, None)


def test_note_search_keeps_source_rows_without_local_relevance_filtering(tmp_path):
    SessionLocal = override_database(tmp_path)

    upstream_rows = [
        sample_note_row("note-weak", "投影仪家电清单"),
        sample_note_row("note-topic", "卫生间装修避坑"),
        sample_note_row("note-title", "浴缸尺寸怎么选"),
    ]
    upstream_rows[0]["content_excerpt"] = "客厅大屏和音响搭配"
    upstream_rows[0]["tags"] = ["浴缸"]
    upstream_rows[0]["raw"] = {
        "noteId": "note-weak",
        "title": "投影仪家电清单",
        "desc": "客厅大屏和音响搭配",
        "participles": ["浴缸"],
    }

    try:
        _user_id, account_id, headers = create_user_account_and_headers(SessionLocal)
        run_payload, _fake = create_successful_run(
            SessionLocal=SessionLocal,
            headers=headers,
            account_id=account_id,
            rows=upstream_rows,
            keyword="浴缸",
            limit=10,
        )

        assert run_payload["candidate_count"] == 3
        assert [candidate["title"] for candidate in run_payload["candidates"]] == [
            "投影仪家电清单",
            "卫生间装修避坑",
            "浴缸尺寸怎么选",
        ]
    finally:
        app.dependency_overrides.pop(get_data_acquisition_note_source, None)
        app.dependency_overrides.pop(get_db, None)


def test_note_search_uses_platform_data_account_without_user_account_id(tmp_path):
    SessionLocal = override_database(tmp_path)
    fake = FakeNoteSource([sample_note_row("note-platform", "Platform account result")])
    app.dependency_overrides[get_data_acquisition_note_source] = lambda: fake
    try:
        user_id, account_id, headers = create_user_account_and_headers(SessionLocal)

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


def test_note_search_ignores_legacy_daily_count_and_charges_credits(tmp_path):
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

        assert response.status_code == 200
        assert response.json()["status"] == "completed"
        assert fake.calls == [("session=ok", "rate limit", 5, {"sort": "interaction", "note_type": "all"})]
        db = SessionLocal()
        try:
            rows = db.scalars(
                select(UsageLedger)
                .where(UsageLedger.user_id == user_id, UsageLedger.bucket == "credits")
                .order_by(UsageLedger.id)
            ).all()
            assert [(row.feature_key, row.operation, row.amount) for row in rows] == [
                ("xhs.data_acquisition.note_search", "reserve", 2),
                ("xhs.data_acquisition.note_search.commit", "commit", 2),
            ]
            assert rows[-1].balance_after == 98
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_data_acquisition_note_source, None)
        app.dependency_overrides.pop(get_db, None)


def test_note_search_credit_shortage_returns_402_without_calling_source(tmp_path):
    from backend.app.services.usage_quota_service import UsageQuotaService, get_or_create_default_tenant_context

    SessionLocal = override_database(tmp_path)
    fake = FakeNoteSource([sample_note_row()])
    app.dependency_overrides[get_data_acquisition_note_source] = lambda: fake
    try:
        user_id, _account_id, headers = create_user_account_and_headers(SessionLocal)
        db = SessionLocal()
        try:
            context = get_or_create_default_tenant_context(db, user_id)
            UsageQuotaService(db).adjust_bucket(context.tenant.id, "credits", total=1, reason="test insufficient note search credits")
        finally:
            db.close()

        response = client.post(
            "/api/xhs/data-acquisition/runs",
            headers=headers,
            json={
                "acquisition_type": "note_search",
                "params": {"keyword": "credits low", "limit": 5},
            },
        )

        assert response.status_code == 402
        assert response.json()["code"] == "usage_quota_insufficient"
        assert response.json()["bucket"] == "credits"
        assert response.json()["required"] == 2
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
        user_id, account_id, headers = create_user_account_and_headers(SessionLocal)
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
        user_id, account_id, headers = create_user_account_and_headers(SessionLocal)
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
        user_id, account_id, headers = create_user_account_and_headers(SessionLocal)
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


def test_list_runs_redacts_legacy_data_account_error_from_ordinary_user(tmp_path):
    SessionLocal = override_database(tmp_path)
    try:
        user_id, headers = create_user_headers_without_data_account(SessionLocal)
        db = SessionLocal()
        try:
            task = Task(
                user_id=user_id,
                platform="xhs",
                task_type="data_acquisition_note_search",
                status="failed",
                progress=100,
            )
            db.add(task)
            db.flush()
            db.add(
                DataAcquisitionRun(
                    task_id=task.id,
                    user_id=user_id,
                    platform="xhs",
                    acquisition_type="note_search",
                    source="huitun",
                    source_mode="live_account",
                    status="failed",
                    requested_limit=1,
                    effective_limit=1,
                    params_json={"keyword": "露营"},
                    error_code="note_search_failed",
                    error_message="数据账号未配置，请联系管理员。",
                )
            )
            db.commit()
        finally:
            db.close()

        response = client.get("/api/xhs/data-acquisition/runs", headers=headers)

        assert response.status_code == 200
        payload = response.json()
        assert payload["items"][0]["user_message"] == "本次数据获取失败，任务已停止。"
        assert "数据账号" not in str(payload)
        assert "huitun" not in str(payload).lower()
        assert "灰豚" not in str(payload)
    finally:
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
        user_id, account_id, headers = create_user_account_and_headers(SessionLocal)

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
        assert payload["user_message"] == "笔记数据结构变化，任务已停止，请联系管理员检查采集配置。"
        assert payload["candidate_count"] == 0

        db = SessionLocal()
        try:
            run = db.scalars(select(DataAcquisitionRun)).one()
            task = db.scalars(select(Task)).one()
            assert run.status == "failed"
            assert run.error_code == "note_search_failed"
            assert task.status == "failed"
            assert db.scalars(select(DataAcquisitionCandidate)).all() == []
            ledgers = db.scalars(
                select(UsageLedger)
                .where(UsageLedger.user_id == user_id, UsageLedger.bucket == "credits")
                .order_by(UsageLedger.id)
            ).all()
            assert [(row.feature_key, row.operation, row.amount) for row in ledgers] == [
                ("xhs.data_acquisition.note_search", "reserve", 2),
                ("xhs.data_acquisition.note_search.refund", "refund", 2),
            ]
            assert ledgers[-1].balance_after == 100
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

        assert response.status_code == 409
        payload = response.json()
        assert payload["detail"]["code"] == "data_account_not_ready"
        assert payload["detail"]["status"] == "expired"
        assert payload["detail"]["message"] == "数据获取服务未就绪，请联系管理员处理后再重试。"
        assert fake.calls == []
        assert "数据账号" not in str(payload)
        assert "huitun" not in str(payload).lower()
        assert "灰豚" not in str(payload)

        db = SessionLocal()
        try:
            assert db.scalars(select(DataAcquisitionRun)).all() == []
            assert db.scalars(select(Task)).all() == []
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_data_acquisition_note_source, None)
        app.dependency_overrides.pop(get_db, None)


def test_note_search_failure_reports_missing_data_account_without_internal_source(tmp_path):
    SessionLocal = override_database(tmp_path)
    fake = FakeNoteSource([sample_note_row()])
    app.dependency_overrides[get_data_acquisition_note_source] = lambda: fake
    try:
        _user_id, headers = create_user_headers_without_data_account(SessionLocal)

        response = client.post(
            "/api/xhs/data-acquisition/runs",
            headers=headers,
            json={
                "acquisition_type": "note_search",
                "params": {"keyword": "露营", "limit": 1, "sort": "interaction", "note_type": "all"},
            },
        )

        assert response.status_code == 409
        payload = response.json()
        assert payload["detail"]["code"] == "data_account_not_ready"
        assert payload["detail"]["status"] == "missing"
        assert payload["detail"]["message"] == "数据获取服务未就绪，请联系管理员处理后再重试。"
        assert fake.calls == []
        assert "数据账号" not in str(payload)
        assert "huitun" not in str(payload).lower()
        assert "灰豚" not in str(payload)
        db = SessionLocal()
        try:
            assert db.scalars(select(DataAcquisitionRun)).all() == []
            assert db.scalars(select(Task)).all() == []
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_data_acquisition_note_source, None)
        app.dependency_overrides.pop(get_db, None)


def test_data_acquisition_readiness_reports_ready_missing_and_expired_states(tmp_path):
    SessionLocal = override_database(tmp_path)
    try:
        _user_id, headers = create_user_headers_without_data_account(SessionLocal)

        missing_response = client.get("/api/xhs/data-acquisition/readiness", headers=headers)

        assert missing_response.status_code == 200
        assert missing_response.json() == {
            "available": False,
            "status": "missing",
            "message": "数据获取服务未就绪，请联系管理员处理后再重试。",
            "next_action": "联系管理员处理。",
        }
        assert "数据账号" not in str(missing_response.json())

        db = SessionLocal()
        try:
            admin = User(username="expired-data-admin", password_hash=hash_password("secret123"), role="admin")
            db.add(admin)
            db.flush()
            admin_id = admin.id
            expired_account = PlatformAccount(
                user_id=admin.id,
                platform="huitun",
                sub_type="main",
                external_user_id="expired-data-account",
                nickname="expired data account",
                status="expired",
            )
            db.add(expired_account)
            db.commit()
        finally:
            db.close()

        expired_response = client.get("/api/xhs/data-acquisition/readiness", headers=headers)

        assert expired_response.status_code == 200
        assert expired_response.json()["available"] is False
        assert expired_response.json()["status"] == "expired"
        assert expired_response.json()["message"] == "数据获取服务未就绪，请联系管理员处理后再重试。"
        assert "数据账号" not in str(expired_response.json())
        assert "huitun" not in str(expired_response.json()).lower()
        assert "灰豚" not in str(expired_response.json())

        admin_expired_response = client.get(
            "/api/xhs/data-acquisition/readiness",
            headers={"Authorization": f"Bearer {create_access_token(admin_id)}"},
        )

        assert admin_expired_response.status_code == 200
        assert admin_expired_response.json()["available"] is False
        assert admin_expired_response.json()["status"] == "expired"
        assert admin_expired_response.json()["message"] == "数据账号登录状态已过期，请让管理员重新登录后再重试。"

        db = SessionLocal()
        try:
            expired_account = db.scalars(select(PlatformAccount).where(PlatformAccount.platform == "huitun")).one()
            expired_account.status = "active"
            db.add(AccountCookieVersion(platform_account_id=expired_account.id, encrypted_cookies=encrypt_text("session=ok")))
            db.commit()
        finally:
            db.close()

        ready_response = client.get("/api/xhs/data-acquisition/readiness", headers=headers)

        assert ready_response.status_code == 200
        assert ready_response.json() == {
            "available": True,
            "status": "ready",
            "message": "数据获取服务已就绪。",
            "next_action": "",
        }
    finally:
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


def test_import_candidates_reuses_existing_note_downloads_images_and_creates_snapshot(tmp_path, monkeypatch):
    SessionLocal = override_database(tmp_path)
    download_calls: list[tuple[str, int, str]] = []
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

        def fake_download(url: str, owner_id: int, asset_type: str) -> str | None:
            download_calls.append((url, owner_id, asset_type))
            return f"xhs-asset-u{owner_id}-{len(download_calls)}.jpg"

        monkeypatch.setattr("backend.app.services.data_acquisition_service.download_asset_to_local", fake_download)

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
            assert [asset.local_path for asset in assets] == [
                f"xhs-asset-u{user_id}-1.jpg",
                f"xhs-asset-u{user_id}-2.jpg",
            ]
            assert download_calls == [
                ("https://sns-img-hw.xhscdn.com/cover.jpg", user_id, "image"),
                ("https://sns-img-hw.xhscdn.com/detail.jpg", user_id, "image"),
            ]
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


def test_import_candidates_fetches_comments_from_data_account(tmp_path, monkeypatch):
    SessionLocal = override_database(tmp_path)
    fake = CommentingFakeNoteSource(
        [sample_note_row("note-with-comments", "浴缸评论笔记")],
        {
            "note-with-comments": [
                {
                    "comment_id": "comment-1",
                    "user_name": "用户A",
                    "user_id": "user-a",
                    "content": "想看更多尺寸",
                    "like_count": 12,
                    "parent_comment_id": None,
                    "created_at_remote": "2026-07-09",
                    "raw_json": {"commentId": "comment-1"},
                },
                {
                    "comment_id": "comment-2",
                    "user_name": "用户B",
                    "content": "收藏了",
                    "like_count": 3,
                    "raw_json": {"commentId": "comment-2"},
                },
            ]
        },
    )
    app.dependency_overrides[get_data_acquisition_note_source] = lambda: fake
    monkeypatch.setattr("backend.app.services.data_acquisition_service.download_asset_to_local", lambda *_args: "")
    try:
        _user_id, account_id, headers = create_user_account_and_headers(SessionLocal)

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
        assert fake.comment_calls == [
            ("session=ok", "note-with-comments", {"limit": 200})
        ]
        db = SessionLocal()
        try:
            note = db.scalars(select(Note)).one()
            comments = db.scalars(select(NoteComment).where(NoteComment.note_id == note.id).order_by(NoteComment.id.asc())).all()
            assert [(comment.comment_id, comment.user_name, comment.content, comment.like_count) for comment in comments] == [
                ("comment-1", "用户A", "想看更多尺寸", 12),
                ("comment-2", "用户B", "收藏了", 3),
            ]
            assert comments[0].raw_json == {"commentId": "comment-1"}
            assert note.raw_json["data_acquisition"]["comments_status"] == "completed"
            assert note.raw_json["data_acquisition"]["comments_count"] == 2
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_data_acquisition_note_source, None)
        app.dependency_overrides.pop(get_db, None)


def test_import_candidates_keeps_note_when_data_account_comments_fail(tmp_path, monkeypatch):
    SessionLocal = override_database(tmp_path)
    fake = CommentingFakeNoteSource(
        [sample_note_row("note-comment-denied", "浴缸评论失败笔记")],
        comment_error="当前版本无请求权限，请升级会员版本查看更多~",
    )
    app.dependency_overrides[get_data_acquisition_note_source] = lambda: fake
    monkeypatch.setattr("backend.app.services.data_acquisition_service.download_asset_to_local", lambda *_args: "")
    try:
        _user_id, account_id, headers = create_user_account_and_headers(SessionLocal)

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
        assert fake.comment_calls == [
            ("session=ok", "note-comment-denied", {"limit": 200})
        ]
        db = SessionLocal()
        try:
            note = db.scalars(select(Note)).one()
            assert note.title == "浴缸评论失败笔记"
            assert db.scalars(select(NoteComment)).all() == []
            assert note.raw_json["data_acquisition"]["comments_status"] == "failed"
            assert "当前版本无请求权限" in note.raw_json["data_acquisition"]["comments_error"]
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_data_acquisition_note_source, None)
        app.dependency_overrides.pop(get_db, None)


def test_import_candidates_resolves_original_url_from_data_account_when_missing(tmp_path, monkeypatch):
    SessionLocal = override_database(tmp_path)
    resolved_url = (
        "https://www.xiaohongshu.com/discovery/item/6a4a223c0000000006022abe"
        "?xsec_token=token&xsec_source=pc_feed"
    )
    fake = ResolvingFakeNoteSource(
        [sample_unresolved_note_row("11548571364", "浴缸多图笔记")],
        {"11548571364": resolved_url},
    )
    app.dependency_overrides[get_data_acquisition_note_source] = lambda: fake
    monkeypatch.setattr("backend.app.services.data_acquisition_service.download_asset_to_local", lambda *_args: "")
    try:
        _user_id, account_id, headers = create_user_account_and_headers(SessionLocal)

        run_response = client.post(
            "/api/xhs/data-acquisition/runs",
            headers=headers,
            json={
                "acquisition_type": "note_search",
                "account_id": account_id,
                "params": {"keyword": "浴缸", "limit": 10},
            },
        )
        candidate_payload = run_response.json()["candidates"][0]
        assert candidate_payload["original_url"] == ""

        import_response = client.post(
            "/api/xhs/data-acquisition/candidates/import",
            headers=headers,
            json={"candidate_ids": [candidate_payload["id"]]},
        )

        assert import_response.status_code == 200
        imported = import_response.json()["items"][0]
        assert imported["source_url"] == resolved_url
        assert fake.resolve_calls == [("session=ok", "11548571364")]

        db = SessionLocal()
        try:
            note = db.scalars(select(Note)).one()
            assert note.raw_json["note_url"] == resolved_url
            assert note.raw_json["data_acquisition"]["original_url"] == resolved_url
            snapshot = db.scalars(select(NoteSourceSnapshot)).one()
            assert snapshot.source_url == resolved_url
            candidate = db.get(DataAcquisitionCandidate, candidate_payload["id"])
            assert candidate is not None
            assert candidate.original_url == resolved_url
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_data_acquisition_note_source, None)
        app.dependency_overrides.pop(get_db, None)


def test_import_source_images_resolves_legacy_data_acquisition_short_link(tmp_path, monkeypatch):
    SessionLocal = override_database(tmp_path)
    bad_url = "https://www.xiaohongshu.com/explore/11548571364"
    resolved_url = (
        "https://www.xiaohongshu.com/discovery/item/6a4a223c0000000006022abe"
        "?xsec_token=token&xsec_source=pc_feed"
    )
    resolve_calls: list[tuple[str, str]] = []
    fetch_calls: list[str] = []
    monkeypatch.setattr(
        "backend.app.services.huitun_live_note_source.resolve_note_url",
        lambda cookie_text, note_id: resolve_calls.append((cookie_text, note_id)) or resolved_url,
    )
    monkeypatch.setattr(
        "backend.app.api.notes.fetch_xhs_note_image_urls",
        lambda source_url: fetch_calls.append(source_url) or ["https://sns-img-hw.xhscdn.com/notes_pre_post/image-1"],
    )
    monkeypatch.setattr("backend.app.api.notes._download_asset", lambda *_args: "")
    try:
        user_id, _account_id, headers = create_user_account_and_headers(SessionLocal)
        db = SessionLocal()
        try:
            note = Note(
                user_id=user_id,
                platform_account_id=0,
                platform="xhs",
                note_id="11548571364",
                title="legacy data acquisition note",
                content="",
                author_name="",
                raw_json={
                    "source": "data_acquisition",
                    "note_url": bad_url,
                    "data_acquisition": {"original_url": bad_url},
                },
            )
            db.add(note)
            db.commit()
            note_id = note.id
        finally:
            db.close()

        response = client.post(
            f"/api/notes/{note_id}/assets/import-source-images",
            headers=headers,
            json={"source_url": bad_url, "download": True},
        )

        assert response.status_code == 200
        assert response.json()["imported_count"] == 1
        assert resolve_calls == [("session=ok", "11548571364")]
        assert fetch_calls == [resolved_url]
        db = SessionLocal()
        try:
            note = db.get(Note, note_id)
            assert note is not None
            assert note.raw_json["note_url"] == resolved_url
            assert note.raw_json["data_acquisition"]["original_url"] == resolved_url
            asset = db.scalars(select(NoteAsset).where(NoteAsset.note_id == note_id)).one()
            assert asset.url == "https://sns-img-hw.xhscdn.com/notes_pre_post/image-1"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_import_source_images_fails_closed_when_legacy_short_link_cannot_resolve(tmp_path, monkeypatch):
    SessionLocal = override_database(tmp_path)
    bad_url = "https://www.xiaohongshu.com/explore/11548571364"
    fetch_calls: list[str] = []
    monkeypatch.setattr("backend.app.services.huitun_live_note_source.resolve_note_url", lambda _cookie_text, _note_id: "")
    monkeypatch.setattr(
        "backend.app.api.notes.fetch_xhs_note_image_urls",
        lambda source_url: fetch_calls.append(source_url) or ["https://sns-img-hw.xhscdn.com/notes_pre_post/image-1"],
    )
    try:
        user_id, _account_id, headers = create_user_account_and_headers(SessionLocal)
        db = SessionLocal()
        try:
            note = Note(
                user_id=user_id,
                platform_account_id=0,
                platform="xhs",
                note_id="11548571364",
                title="legacy data acquisition note",
                content="",
                author_name="",
                raw_json={
                    "source": "data_acquisition",
                    "note_url": bad_url,
                    "data_acquisition": {"original_url": bad_url},
                },
            )
            db.add(note)
            db.commit()
            note_id = note.id
        finally:
            db.close()

        response = client.post(
            f"/api/notes/{note_id}/assets/import-source-images",
            headers=headers,
            json={"source_url": bad_url, "download": True},
        )

        assert response.status_code == 422
        assert response.json()["detail"] == "source_url_unavailable"
        assert fetch_calls == []
    finally:
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

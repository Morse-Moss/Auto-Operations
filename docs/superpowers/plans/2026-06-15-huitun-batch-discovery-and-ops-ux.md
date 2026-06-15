# Huitun Batch Discovery and Ops UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reliable batch Huitun keyword discovery workflow with per-seed diagnostics, in-system run history, and the related operator UX fixes found in testing.

**Architecture:** Reuse existing `KeywordDiscoveryRun` / `KeywordDiscoveryItem` tables and add structured run metadata in `error_message` to avoid a migration. Keep Huitun as an integration source for XHS keyword discovery, not a top-level platform workspace. Fix adjacent UX with narrow API/UI changes: draft duplicate endpoint, publish visibility labels, and split AI generate reference inputs.

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy, Pytest, React, TypeScript, Vite, Ant Design.

**Hard constraints from project rules:** Do not modify `apis/`, `xhs_utils/`, or `static/`. Do not run real publish. Do not use high-frequency/concurrent Huitun requests. Do not commit unless the user explicitly asks.

---

## File Structure

- Modify: `backend/app/api/keyword_groups.py`
  - Adds per-seed metadata helpers, partial-failure live Huitun execution, run list endpoint, and extended serialization.
- Modify: `backend/app/services/huitun_live_keyword_source.py`
  - Makes Huitun response parsing more resilient and error messages more actionable without changing request frequency.
- Create: `tests/backend/test_huitun_keyword_discovery.py`
  - TDD coverage for batch success, partial failure, all failure, run history, import compatibility, and Huitun parser diagnostics.
- Modify: `backend/app/api/drafts.py`
  - Adds `POST /drafts/{draft_id}/duplicate`.
- Create: `tests/backend/test_drafts_duplicate.py`
  - TDD coverage for draft content/assets copy and ownership checks.
- Modify: `frontend/src/types/index.ts`
  - Adds Huitun seed result and summary types.
- Modify: `frontend/src/lib/api.ts`
  - Adds `fetchHuitunKeywordDiscoveryRuns()` and `duplicateDraft()` clients.
- Modify: `frontend/src/pages/platforms/xhs/keywords-page.tsx`
  - Adds batch seed input, per-seed summary/errors, run history, and source seed filtering.
- Modify: `frontend/src/pages/platforms/xhs/drafts-page.tsx`
  - Adds copy draft action.
- Modify: `frontend/src/pages/platforms/xhs/publish-page.tsx`
  - Aligns visibility labels with XHS and shows disabled mutual-friends option.
- Modify: `frontend/src/pages/platforms/xhs/rewrite-page.tsx`
  - Splits generate-mode reference input into links and supplemental info.
- Create: `tests/backend/test_frontend_ops_ux_sources.py`
  - Static source checks for frontend UX/API/type wiring.

## Task 1: Backend Huitun Batch Discovery Tests

**Files:**
- Create: `tests/backend/test_huitun_keyword_discovery.py`

- [ ] **Step 1: Write failing backend tests for partial-success batch discovery**

Create `tests/backend/test_huitun_keyword_discovery.py` with this initial content:

```python
from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.api.keyword_groups import get_huitun_live_keyword_client
from backend.app.core.database import Base, get_db
from backend.app.core.security import create_access_token, encrypt_text, hash_password
from backend.app.main import app
from backend.app.models import AccountCookieVersion, KeywordDiscoveryItem, KeywordDiscoveryRun, PlatformAccount, User

client = TestClient(app)


class FakeHuitunClient:
    def __init__(self, results: dict[str, list[dict[str, Any]]], failures: dict[str, str] | None = None) -> None:
        self.results = results
        self.failures = failures or {}
        self.calls: list[tuple[str, str, int]] = []

    def fetch_huitun_hotwords(self, cookie_text: str, seed_keyword: str, limit: int) -> list[dict[str, Any]]:
        self.calls.append((cookie_text, seed_keyword, limit))
        if seed_keyword in self.failures:
            raise RuntimeError(self.failures[seed_keyword])
        return self.results.get(seed_keyword, [])[:limit]


def override_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'huitun-discovery-test.db'}", connect_args={"check_same_thread": False})
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
            nickname="灰豚测试账号",
            status="active",
        )
        db.add(account)
        db.flush()
        db.add(AccountCookieVersion(platform_account_id=account.id, encrypted_cookies=encrypt_text("session=ok")))
        db.commit()
        return account.id, {"Authorization": f"Bearer {create_access_token(user.id)}"}
    finally:
        db.close()


def test_live_huitun_batch_discovery_keeps_successful_seed_items_when_one_seed_fails(tmp_path):
    SessionLocal = override_database(tmp_path)
    account_id, headers = create_user_account_and_headers(SessionLocal)
    fake = FakeHuitunClient(
        results={
            "低卡早餐": [
                {
                    "source_keyword": "低卡早餐",
                    "keyword": "低卡早餐食谱",
                    "hot_value_text": "1.2w",
                    "hot_value_number": 12000,
                    "note_count": 300,
                    "interaction_text": "900",
                    "interaction_number": 900,
                    "categories": [{"label": "美食", "rate": "80"}],
                    "rank_index": 1,
                }
            ]
        },
        failures={"通勤穿搭": "灰豚候选词返回结构已变化，请先使用手工导入并等待适配。"},
    )
    app.dependency_overrides[get_huitun_live_keyword_client] = lambda: fake
    try:
        response = client.post(
            "/api/keyword-groups/huitun/discovery-runs",
            headers=headers,
            json={
                "source_mode": "live_account",
                "account_id": account_id,
                "limit_per_seed": 50,
                "inputs": [
                    {"source_keyword": "低卡早餐"},
                    {"source_keyword": "通勤穿搭"},
                ],
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "partial_failed"
        assert payload["summary"] == {
            "success_seed_count": 1,
            "failed_seed_count": 1,
            "total_item_count": 1,
        }
        assert payload["seed_results"] == [
            {"source_keyword": "低卡早餐", "status": "success", "item_count": 1, "error_message": ""},
            {
                "source_keyword": "通勤穿搭",
                "status": "failed",
                "item_count": 0,
                "error_message": "灰豚候选词返回结构已变化，请先使用手工导入并等待适配。",
            },
        ]
        assert [item["keyword"] for item in payload["items"]] == ["低卡早餐食谱"]
        assert fake.calls == [("session=ok", "低卡早餐", 50), ("session=ok", "通勤穿搭", 50)]
    finally:
        app.dependency_overrides.pop(get_huitun_live_keyword_client, None)
        app.dependency_overrides.pop(get_db, None)
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
py -3 -m pytest tests/backend/test_huitun_keyword_discovery.py::test_live_huitun_batch_discovery_keeps_successful_seed_items_when_one_seed_fails -q
```

Expected: FAIL. Current backend raises HTTP 400 on the failed second seed or lacks `summary` / `seed_results`.

## Task 2: Implement Per-Seed Metadata and Partial Failure Semantics

**Files:**
- Modify: `backend/app/api/keyword_groups.py`

- [ ] **Step 1: Add metadata helpers above `_serialize_discovery_run`**

In `backend/app/api/keyword_groups.py`, add these helpers after `_serialize_discovery_item`:

```python
RUN_METADATA_VERSION = 1


def _run_metadata(seed_results: list[dict[str, Any]], total_item_count: int) -> dict[str, Any]:
    success_count = len([item for item in seed_results if item.get("status") == "success"])
    failed_count = len([item for item in seed_results if item.get("status") == "failed"])
    return {
        "version": RUN_METADATA_VERSION,
        "seed_results": seed_results,
        "summary": {
            "success_seed_count": success_count,
            "failed_seed_count": failed_count,
            "total_item_count": total_item_count,
        },
    }


def _metadata_text(seed_results: list[dict[str, Any]], total_item_count: int) -> str:
    return json.dumps(_run_metadata(seed_results, total_item_count), ensure_ascii=False, separators=(",", ":"))


def _parse_run_metadata(error_message: str | None, items: list[KeywordDiscoveryItem]) -> dict[str, Any]:
    fallback = {
        "seed_results": [],
        "summary": {
            "success_seed_count": 0,
            "failed_seed_count": 0,
            "total_item_count": len(items),
        },
    }
    if not error_message:
        return fallback
    try:
        parsed = json.loads(error_message)
    except json.JSONDecodeError:
        return fallback
    if not isinstance(parsed, dict):
        return fallback
    seed_results = parsed.get("seed_results")
    summary = parsed.get("summary")
    if not isinstance(seed_results, list) or not isinstance(summary, dict):
        return fallback
    return {"seed_results": seed_results, "summary": summary}


def _seed_success(source_keyword: str, item_count: int) -> dict[str, Any]:
    return {
        "source_keyword": source_keyword,
        "status": "success",
        "item_count": item_count,
        "error_message": "",
    }


def _seed_failure(source_keyword: str, error_message: str) -> dict[str, Any]:
    return {
        "source_keyword": source_keyword,
        "status": "failed",
        "item_count": 0,
        "error_message": error_message,
    }


def _status_from_seed_results(seed_results: list[dict[str, Any]]) -> str:
    success_count = len([item for item in seed_results if item.get("status") == "success"])
    failed_count = len([item for item in seed_results if item.get("status") == "failed"])
    if success_count and failed_count:
        return "partial_failed"
    if failed_count and not success_count:
        return "failed"
    return "completed"
```

- [ ] **Step 2: Extend run serialization**

Change `_serialize_discovery_run` to parse metadata and include it:

```python
def _serialize_discovery_run(run: KeywordDiscoveryRun, items: list[KeywordDiscoveryItem]) -> dict[str, Any]:
    metadata = _parse_run_metadata(run.error_message, items)
    return {
        "id": run.id,
        "platform": run.platform,
        "source": run.source,
        "seed_keywords": run.seed_keywords or [],
        "limit_per_seed": run.limit_per_seed,
        "source_mode": run.source_mode,
        "status": run.status,
        "error_message": run.error_message,
        "seed_results": metadata["seed_results"],
        "summary": metadata["summary"],
        "created_at": run.created_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "items": [_serialize_discovery_item(item) for item in items],
    }
```

- [ ] **Step 3: Change live_account loop to partial failure semantics**

In `create_huitun_discovery_run`, replace the existing `if payload.source_mode == "live_account":` block with:

```python
    seed_results: list[dict[str, Any]] = []
    if payload.source_mode == "live_account":
        cookies_text = _latest_huitun_cookie_text(db, current_user, payload.account_id)
        for input_item in payload.inputs:
            source_keyword = input_item.source_keyword.strip()
            try:
                seed_rows = live_keyword_client.fetch_huitun_hotwords(cookies_text, source_keyword, payload.limit_per_seed)
            except RuntimeError as exc:
                seed_results.append(_seed_failure(source_keyword, str(exc)))
                continue
            rows.extend(seed_rows)
            seed_results.append(_seed_success(source_keyword, len(seed_rows)))
    else:
        for input_item in payload.inputs:
            seed_rows = _rows_from_huitun_input(input_item, payload.source_mode)[: payload.limit_per_seed]
            rows.extend(seed_rows)
            seed_results.append(_seed_success(input_item.source_keyword.strip(), len(seed_rows)))
```

Then replace the run status assignment near the end:

```python
    run.status = "completed"
    run.finished_at = shanghai_now()
```

with:

```python
    run.status = _status_from_seed_results(seed_results)
    run.error_message = _metadata_text(seed_results, len(items))
    run.finished_at = shanghai_now()
```

- [ ] **Step 4: Run the partial failure test again**

Run:

```bash
py -3 -m pytest tests/backend/test_huitun_keyword_discovery.py::test_live_huitun_batch_discovery_keeps_successful_seed_items_when_one_seed_fails -q
```

Expected: PASS.

## Task 3: Add All-Failed, Run History, and Import Compatibility Tests

**Files:**
- Modify: `tests/backend/test_huitun_keyword_discovery.py`

- [ ] **Step 1: Add all-failed run test**

Append:

```python
def test_live_huitun_batch_discovery_returns_failed_run_instead_of_http_400_when_all_seeds_fail(tmp_path):
    SessionLocal = override_database(tmp_path)
    account_id, headers = create_user_account_and_headers(SessionLocal)
    fake = FakeHuitunClient(results={}, failures={"低卡早餐": "灰豚登录态已过期，请到账号矩阵重新登录。"})
    app.dependency_overrides[get_huitun_live_keyword_client] = lambda: fake
    try:
        response = client.post(
            "/api/keyword-groups/huitun/discovery-runs",
            headers=headers,
            json={
                "source_mode": "live_account",
                "account_id": account_id,
                "limit_per_seed": 50,
                "inputs": [{"source_keyword": "低卡早餐"}],
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "failed"
        assert payload["items"] == []
        assert payload["summary"] == {
            "success_seed_count": 0,
            "failed_seed_count": 1,
            "total_item_count": 0,
        }
        assert payload["seed_results"][0]["error_message"] == "灰豚登录态已过期，请到账号矩阵重新登录。"
    finally:
        app.dependency_overrides.pop(get_huitun_live_keyword_client, None)
        app.dependency_overrides.pop(get_db, None)
```

- [ ] **Step 2: Add run history list test**

Append:

```python
def test_huitun_discovery_run_history_lists_current_user_runs_without_items(tmp_path):
    SessionLocal = override_database(tmp_path)
    account_id, headers = create_user_account_and_headers(SessionLocal)
    fake = FakeHuitunClient(
        results={
            "低卡早餐": [
                {"source_keyword": "低卡早餐", "keyword": "低卡早餐食谱", "rank_index": 1, "categories": []}
            ]
        }
    )
    app.dependency_overrides[get_huitun_live_keyword_client] = lambda: fake
    try:
        create_response = client.post(
            "/api/keyword-groups/huitun/discovery-runs",
            headers=headers,
            json={
                "source_mode": "live_account",
                "account_id": account_id,
                "limit_per_seed": 20,
                "inputs": [{"source_keyword": "低卡早餐"}],
            },
        )
        assert create_response.status_code == 200

        list_response = client.get("/api/keyword-groups/huitun/discovery-runs", headers=headers)

        assert list_response.status_code == 200
        payload = list_response.json()
        assert payload["total"] == 1
        assert payload["items"][0]["seed_keywords"] == ["低卡早餐"]
        assert payload["items"][0]["summary"]["total_item_count"] == 1
        assert payload["items"][0]["items"] == []
    finally:
        app.dependency_overrides.pop(get_huitun_live_keyword_client, None)
        app.dependency_overrides.pop(get_db, None)
```

- [ ] **Step 3: Add import compatibility test**

Append:

```python
def test_successful_huitun_candidates_can_still_import_to_new_keyword_group(tmp_path):
    SessionLocal = override_database(tmp_path)
    account_id, headers = create_user_account_and_headers(SessionLocal)
    fake = FakeHuitunClient(
        results={
            "低卡早餐": [
                {"source_keyword": "低卡早餐", "keyword": "低卡早餐食谱", "rank_index": 1, "categories": []},
                {"source_keyword": "低卡早餐", "keyword": "低卡早餐空气炸锅", "rank_index": 2, "categories": []},
            ]
        }
    )
    app.dependency_overrides[get_huitun_live_keyword_client] = lambda: fake
    try:
        create_response = client.post(
            "/api/keyword-groups/huitun/discovery-runs",
            headers=headers,
            json={
                "source_mode": "live_account",
                "account_id": account_id,
                "limit_per_seed": 20,
                "inputs": [{"source_keyword": "低卡早餐"}],
            },
        )
        assert create_response.status_code == 200
        candidate_ids = [item["id"] for item in create_response.json()["items"]]

        import_response = client.post(
            "/api/keyword-groups/import-keyword-candidates",
            headers=headers,
            json={
                "candidate_ids": candidate_ids,
                "merge_mode": "append_dedupe",
                "target": {"mode": "create", "name": "低卡早餐热词", "platform": "xhs"},
            },
        )

        assert import_response.status_code == 200
        payload = import_response.json()
        assert payload["group"]["name"] == "低卡早餐热词"
        assert payload["imported_keywords"] == ["低卡早餐食谱", "低卡早餐空气炸锅"]
    finally:
        app.dependency_overrides.pop(get_huitun_live_keyword_client, None)
        app.dependency_overrides.pop(get_db, None)
```

- [ ] **Step 4: Run tests and verify they fail before endpoint exists**

Run:

```bash
py -3 -m pytest tests/backend/test_huitun_keyword_discovery.py -q
```

Expected: partial failure test should pass after Task 2; history test fails with 405/404 until the list endpoint is added.

## Task 4: Add Huitun Run History Endpoint

**Files:**
- Modify: `backend/app/api/keyword_groups.py`

- [ ] **Step 1: Add list endpoint before `get_huitun_discovery_run`**

Insert after `create_huitun_discovery_run` and before `@router.get("/huitun/discovery-runs/{run_id}")`:

```python
@router.get("/huitun/discovery-runs")
def list_huitun_discovery_runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    runs = db.scalars(
        select(KeywordDiscoveryRun)
        .where(
            KeywordDiscoveryRun.user_id == current_user.id,
            KeywordDiscoveryRun.platform == "xhs",
            KeywordDiscoveryRun.source == "huitun",
        )
        .order_by(KeywordDiscoveryRun.created_at.desc(), KeywordDiscoveryRun.id.desc())
    ).all()
    return paginated([_serialize_discovery_run(run, []) for run in runs], page, page_size)
```

- [ ] **Step 2: Run Huitun discovery tests**

Run:

```bash
py -3 -m pytest tests/backend/test_huitun_keyword_discovery.py -q
```

Expected: PASS for the tests added so far.

## Task 5: Huitun Response Parser Diagnostics Tests

**Files:**
- Modify: `tests/backend/test_huitun_keyword_discovery.py`

- [ ] **Step 1: Add parser tests**

Append:

```python
def test_huitun_rows_from_response_finds_nested_lists_under_data_records():
    from backend.app.services.huitun_live_keyword_source import _rows_from_response

    rows = _rows_from_response(
        "低卡早餐",
        {
            "status": 0,
            "data": {
                "result": {
                    "records": [
                        {"word": "低卡早餐食谱", "searchIndex": "1.2w", "noteNum": 200, "rankIndex": 1}
                    ]
                }
            },
        },
        10,
    )

    assert rows[0]["keyword"] == "低卡早餐食谱"
    assert rows[0]["hot_value_text"] == "1.2w"
    assert rows[0]["note_count"] == 200


def test_huitun_rows_from_response_reports_structure_change_when_no_list_exists():
    import pytest
    from backend.app.services.huitun_live_keyword_source import HUITUN_STRUCTURE_CHANGED_MESSAGE, _rows_from_response

    with pytest.raises(RuntimeError) as exc_info:
        _rows_from_response("低卡早餐", {"status": 0, "extData": {"unexpected": {"value": 1}}}, 10)

    assert str(exc_info.value) == HUITUN_STRUCTURE_CHANGED_MESSAGE


def test_huitun_rows_from_response_reports_empty_result_when_list_is_present_but_has_no_rows():
    import pytest
    from backend.app.services.huitun_live_keyword_source import HUITUN_EMPTY_RESULT_MESSAGE, _rows_from_response

    with pytest.raises(RuntimeError) as exc_info:
        _rows_from_response("低卡早餐", {"status": 0, "data": {"records": []}}, 10)

    assert str(exc_info.value) == HUITUN_EMPTY_RESULT_MESSAGE


def test_huitun_rows_from_response_reports_decrypt_failure_for_invalid_ext_data():
    import pytest
    from backend.app.services.huitun_crypto import HUITUN_EXT_DATA_DECRYPT_FAILED_MESSAGE
    from backend.app.services.huitun_live_keyword_source import _rows_from_response

    with pytest.raises(RuntimeError) as exc_info:
        _rows_from_response("低卡早餐", {"status": 0, "extData": "not-valid-encrypted-payload"}, 10)

    assert str(exc_info.value) == HUITUN_EXT_DATA_DECRYPT_FAILED_MESSAGE
```

- [ ] **Step 2: Run parser tests to verify failure**

Run:

```bash
py -3 -m pytest tests/backend/test_huitun_keyword_discovery.py::test_huitun_rows_from_response_finds_nested_lists_under_data_records tests/backend/test_huitun_keyword_discovery.py::test_huitun_rows_from_response_reports_structure_change_when_no_list_exists tests/backend/test_huitun_keyword_discovery.py::test_huitun_rows_from_response_reports_empty_result_when_list_is_present_but_has_no_rows tests/backend/test_huitun_keyword_discovery.py::test_huitun_rows_from_response_reports_decrypt_failure_for_invalid_ext_data -q
```

Expected: FAIL. Current `_first_list()` does not recursively search `data.result.records`, and no structure-change message exists.

## Task 6: Implement Huitun Parser Diagnostics

**Files:**
- Modify: `backend/app/services/huitun_live_keyword_source.py`

- [ ] **Step 1: Add messages**

Near existing constants, change/add:

```python
HUITUN_LIVE_FAILED_MESSAGE = "灰豚候选词获取失败，请稍后重试或使用手工导入。"
HUITUN_LOGIN_EXPIRED_MESSAGE = "灰豚登录态已过期，请到账号矩阵重新登录。"
HUITUN_STRUCTURE_CHANGED_MESSAGE = "灰豚候选词返回结构已变化，请先使用手工导入并等待适配。"
HUITUN_EMPTY_RESULT_MESSAGE = "没有获取到候选词，可换种子词或使用手工导入。"
```

- [ ] **Step 2: Replace `_first_list` with recursive search**

Replace current `_first_list` with:

```python
def _first_list(value: Any, depth: int = 0) -> list[Any] | None:
    if depth > 4:
        return None
    if isinstance(value, list):
        return value
    if not isinstance(value, dict):
        return None

    for key in ("list", "items", "records", "rows", "data", "result", "extData"):
        nested = value.get(key)
        if isinstance(nested, list):
            return nested

    for key in ("list", "items", "records", "rows", "data", "result", "extData"):
        nested = value.get(key)
        found = _first_list(nested, depth + 1)
        if found is not None:
            return found
    return None
```

- [ ] **Step 3: Update `_rows_from_response` to inspect `extData` or whole payload**

Replace `_rows_from_response` with:

```python
def _rows_from_response(source_keyword: str, payload: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    ext_data = payload.get("extData")
    if isinstance(ext_data, str):
        try:
            ext_data = decrypt_huitun_ext_data(ext_data)
        except ValueError as exc:
            raise RuntimeError(HUITUN_EXT_DATA_DECRYPT_FAILED_MESSAGE) from exc

    search_root: Any = ext_data if ext_data is not None else payload
    raw_items = _first_list(search_root)
    if raw_items is None and isinstance(payload, dict):
        raw_items = _first_list(payload)
    if raw_items is None:
        raise RuntimeError(HUITUN_STRUCTURE_CHANGED_MESSAGE)
    if not raw_items:
        raise RuntimeError(HUITUN_EMPTY_RESULT_MESSAGE)

    rows: list[dict[str, Any]] = []
    for index, item in enumerate(raw_items):
        if not isinstance(item, dict):
            continue
        row = _row_from_item(source_keyword, index, item)
        if row:
            rows.append(row)
    if not rows:
        raise RuntimeError(HUITUN_EMPTY_RESULT_MESSAGE)
    return dedupe_keyword_candidates(prioritize_exact_hotword_rows(source_keyword, rows))[:limit]
```

- [ ] **Step 4: Run parser tests**

Run:

```bash
py -3 -m pytest tests/backend/test_huitun_keyword_discovery.py::test_huitun_rows_from_response_finds_nested_lists_under_data_records tests/backend/test_huitun_keyword_discovery.py::test_huitun_rows_from_response_reports_structure_change_when_no_list_exists tests/backend/test_huitun_keyword_discovery.py::test_huitun_rows_from_response_reports_empty_result_when_list_is_present_but_has_no_rows tests/backend/test_huitun_keyword_discovery.py::test_huitun_rows_from_response_reports_decrypt_failure_for_invalid_ext_data -q
```

Expected: PASS.

- [ ] **Step 5: Run all Huitun discovery tests**

Run:

```bash
py -3 -m pytest tests/backend/test_huitun_keyword_discovery.py -q
```

Expected: PASS.

## Task 7: Draft Duplicate Backend Tests

**Files:**
- Create: `tests/backend/test_drafts_duplicate.py`

- [ ] **Step 1: Write failing tests**

Create `tests/backend/test_drafts_duplicate.py`:

```python
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import Base, get_db
from backend.app.core.security import create_access_token, hash_password
from backend.app.main import app
from backend.app.models import AiDraft, DraftAsset, User

client = TestClient(app)


def override_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'draft-duplicate-test.db'}", connect_args={"check_same_thread": False})
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


def create_user(SessionLocal, username: str = "operator"):
    db = SessionLocal()
    try:
        user = User(username=username, password_hash=hash_password("secret123"))
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id, {"Authorization": f"Bearer {create_access_token(user.id)}"}
    finally:
        db.close()


def test_duplicate_draft_copies_content_tags_source_and_assets(tmp_path):
    SessionLocal = override_database(tmp_path)
    user_id, headers = create_user(SessionLocal)
    db = SessionLocal()
    try:
        draft = AiDraft(
            user_id=user_id,
            platform="xhs",
            title="长文改写",
            body="第一段\n第二段",
            tags=[{"id": "tag-1", "name": "职场"}],
            source_note_id=None,
        )
        db.add(draft)
        db.flush()
        db.add(DraftAsset(draft_id=draft.id, asset_type="image", url="https://example.test/a.jpg", local_path="", sort_order=0))
        db.add(DraftAsset(draft_id=draft.id, asset_type="image", url="", local_path="local/b.jpg", sort_order=1))
        db.commit()
        draft_id = draft.id
    finally:
        db.close()

    try:
        response = client.post(f"/api/drafts/{draft_id}/duplicate", headers=headers)

        assert response.status_code == 200
        payload = response.json()
        assert payload["id"] != draft_id
        assert payload["title"] == "长文改写 - 副本"
        assert payload["body"] == "第一段\n第二段"
        assert payload["tags"] == [{"id": "tag-1", "name": "职场"}]

        db = SessionLocal()
        try:
            copied_assets = db.scalars(select(DraftAsset).where(DraftAsset.draft_id == payload["id"]).order_by(DraftAsset.sort_order.asc())).all()
            assert [(asset.asset_type, asset.url, asset.local_path, asset.sort_order) for asset in copied_assets] == [
                ("image", "https://example.test/a.jpg", "", 0),
                ("image", "", "local/b.jpg", 1),
            ]
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_duplicate_draft_rejects_other_users_draft(tmp_path):
    SessionLocal = override_database(tmp_path)
    owner_id, _ = create_user(SessionLocal, "owner")
    _, other_headers = create_user(SessionLocal, "other")
    db = SessionLocal()
    try:
        draft = AiDraft(user_id=owner_id, platform="xhs", title="Owner", body="secret")
        db.add(draft)
        db.commit()
        draft_id = draft.id
    finally:
        db.close()

    try:
        response = client.post(f"/api/drafts/{draft_id}/duplicate", headers=other_headers)

        assert response.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
py -3 -m pytest tests/backend/test_drafts_duplicate.py -q
```

Expected: FAIL with 405/404 because duplicate endpoint does not exist.

## Task 8: Implement Draft Duplicate Endpoint

**Files:**
- Modify: `backend/app/api/drafts.py`

- [ ] **Step 1: Add copy helper imports**

At top of `drafts.py`, add `copy` import:

```python
from copy import deepcopy
```

- [ ] **Step 2: Add duplicate endpoint before `send_draft_to_publish`**

Insert after `create_draft`:

```python
@router.post("/{draft_id}/duplicate")
def duplicate_draft(
    draft_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    draft = db.get(AiDraft, draft_id)
    if draft is None or draft.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")

    copied = AiDraft(
        user_id=current_user.id,
        platform=draft.platform,
        title=f"{(draft.title or '未命名草稿').strip()} - 副本",
        body=draft.body,
        tags=deepcopy(draft.tags or []),
        source_note_id=draft.source_note_id,
    )
    db.add(copied)
    db.flush()

    assets = db.scalars(
        select(DraftAsset).where(DraftAsset.draft_id == draft.id).order_by(DraftAsset.sort_order.asc(), DraftAsset.id.asc())
    ).all()
    for asset in assets:
        db.add(
            DraftAsset(
                draft_id=copied.id,
                asset_type=asset.asset_type,
                url=asset.url,
                local_path=asset.local_path,
                sort_order=asset.sort_order,
            )
        )

    db.commit()
    db.refresh(copied)
    return _serialize_draft(copied)
```

- [ ] **Step 3: Run draft duplicate tests**

Run:

```bash
py -3 -m pytest tests/backend/test_drafts_duplicate.py -q
```

Expected: PASS.

## Task 9: Frontend Static Source Tests

**Files:**
- Create: `tests/backend/test_frontend_ops_ux_sources.py`

- [ ] **Step 1: Write failing static tests**

Create `tests/backend/test_frontend_ops_ux_sources.py`:

```python
from __future__ import annotations


def read(path: str) -> str:
    return open(path, encoding="utf-8").read()


def test_frontend_exposes_huitun_batch_run_history_and_seed_diagnostics():
    api_source = read("frontend/src/lib/api.ts")
    types_source = read("frontend/src/types/index.ts")
    keywords_source = read("frontend/src/pages/platforms/xhs/keywords-page.tsx")

    assert "fetchHuitunKeywordDiscoveryRuns" in api_source
    assert '"/keyword-groups/huitun/discovery-runs"' in api_source
    assert "HuitunSeedResult" in types_source
    assert "HuitunDiscoverySummary" in types_source
    assert "seed_results" in types_source
    assert "summary" in types_source
    assert "splitSeedKeywords" in keywords_source
    assert "最近灰豚批次" in keywords_source
    assert "失败种子" in keywords_source
    assert "批量获取灰豚候选词" in keywords_source


def test_frontend_exposes_draft_duplicate_action():
    api_source = read("frontend/src/lib/api.ts")
    drafts_source = read("frontend/src/pages/platforms/xhs/drafts-page.tsx")

    assert "duplicateDraft" in api_source
    assert '/duplicate' in api_source
    assert "复制草稿" in drafts_source
    assert "handleDuplicateDraft" in drafts_source


def test_publish_visibility_labels_match_xhs_without_enabling_unknown_privacy_value():
    publish_source = read("frontend/src/pages/platforms/xhs/publish-page.tsx")

    assert "公开可见" in publish_source
    assert "仅自己可见" in publish_source
    assert "仅互关好友可见" in publish_source
    assert "待确认发布接口支持" in publish_source
    assert "disabled: true" in publish_source


def test_generate_note_reference_inputs_are_split():
    rewrite_source = read("frontend/src/pages/platforms/xhs/rewrite-page.tsx")

    assert "referenceLinks" in rewrite_source
    assert "referenceContext" in rewrite_source
    assert "参考链接" in rewrite_source
    assert "补充信息" in rewrite_source
    assert "buildGenerateReference" in rewrite_source
```

- [ ] **Step 2: Run static tests to verify failure**

Run:

```bash
py -3 -m pytest tests/backend/test_frontend_ops_ux_sources.py -q
```

Expected: FAIL because frontend wiring has not been added yet.

## Task 10: Frontend Types and API Clients

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Extend Huitun discovery types**

In `frontend/src/types/index.ts`, locate `KeywordDiscoveryRun`. Add these types near keyword discovery types:

```ts
export type HuitunSeedResult = {
  source_keyword: string;
  status: "success" | "failed" | string;
  item_count: number;
  error_message: string;
};

export type HuitunDiscoverySummary = {
  success_seed_count: number;
  failed_seed_count: number;
  total_item_count: number;
};
```

Extend `KeywordDiscoveryRun` with:

```ts
  seed_results?: HuitunSeedResult[];
  summary?: HuitunDiscoverySummary;
```

- [ ] **Step 2: Add API clients**

In `frontend/src/lib/api.ts`, add after `fetchHuitunKeywordDiscoveryRun`:

```ts
export async function fetchHuitunKeywordDiscoveryRuns(params?: {
  page?: number;
  page_size?: number;
}): Promise<Paginated<KeywordDiscoveryRun>> {
  const response = await http.get<Paginated<KeywordDiscoveryRun>>("/keyword-groups/huitun/discovery-runs", { params });
  return response.data;
}
```

Add after `deleteDraft`:

```ts
export async function duplicateDraft(draftId: number): Promise<Draft> {
  const response = await http.post<Draft>(`/drafts/${draftId}/duplicate`);
  return response.data;
}
```

- [ ] **Step 3: Run frontend static tests**

Run:

```bash
py -3 -m pytest tests/backend/test_frontend_ops_ux_sources.py::test_frontend_exposes_huitun_batch_run_history_and_seed_diagnostics tests/backend/test_frontend_ops_ux_sources.py::test_frontend_exposes_draft_duplicate_action -q
```

Expected: still FAIL because pages are not wired yet, but API/type assertions should now pass.

## Task 11: Keywords Page Batch Huitun UX

**Files:**
- Modify: `frontend/src/pages/platforms/xhs/keywords-page.tsx`

- [ ] **Step 1: Update imports**

Add `fetchHuitunKeywordDiscoveryRuns` to API imports:

```ts
  fetchHuitunKeywordDiscoveryRuns,
```

Add `Alert`, `Divider` if not already imported; `Alert` already exists. Add `Divider` to Ant imports if missing:

```ts
  Divider,
```

- [ ] **Step 2: Add seed parsing helper**

Replace or supplement `splitKeywords` with a dedicated helper near existing helpers:

```ts
function splitSeedKeywords(value: string): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  value
    .split(/[,，\n]/)
    .map((keyword) => keyword.trim())
    .filter(Boolean)
    .forEach((keyword) => {
      const key = keyword.toLowerCase();
      if (!seen.has(key)) {
        seen.add(key);
        result.push(keyword);
      }
    });
  return result.slice(0, 50);
}
```

- [ ] **Step 3: Add state**

Inside `XhsKeywordsPage`, add:

```ts
  const [huitunRuns, setHuitunRuns] = useState<KeywordDiscoveryRun[]>([]);
  const [limitPerSeed, setLimitPerSeed] = useState(50);
  const [sourceKeywordFilter, setSourceKeywordFilter] = useState<string | null>(null);
```

- [ ] **Step 4: Load recent Huitun runs**

Add function:

```ts
  async function loadHuitunRuns() {
    try {
      const result = await fetchHuitunKeywordDiscoveryRuns({ page: 1, page_size: 10 });
      setHuitunRuns(result.items);
    } catch {
      // Keep keyword groups usable even if history fails.
    }
  }
```

Update `loadGroups()` finally or success path to call it after groups/accounts load:

```ts
      await loadHuitunRuns();
```

If that creates duplicate requests in `useEffect`, acceptable for first pass; otherwise call `void loadHuitunRuns()` in `useEffect` beside `loadGroups()`.

- [ ] **Step 5: Update live Huitun fetch function**

Replace `fetchHuitunHotwordsFromAccount()` body with batch behavior:

```ts
  async function fetchHuitunHotwordsFromAccount() {
    const seeds = splitSeedKeywords(huitunSeed);
    if (!seeds.length) {
      setMessage("请输入至少一个种子关键词。");
      return;
    }
    if (!selectedHuitunAccountId) {
      setMessage("请先到账号矩阵绑定灰豚账号。");
      return;
    }
    setIsHuitunWorking(true);
    setMessage(null);
    setError(null);
    setSourceKeywordFilter(null);
    try {
      const run = await createHuitunKeywordDiscoveryRun({
        source_mode: "live_account",
        account_id: selectedHuitunAccountId,
        limit_per_seed: limitPerSeed,
        inputs: seeds.map((source_keyword) => ({ source_keyword })),
      });
      setHuitunRun(run);
      setSelectedCandidateIds(run.items.map((item) => item.id));
      setTargetGroupName(seeds.length === 1 ? `${seeds[0]} 热词` : `${seeds[0]}等${seeds.length}词热词`);
      await loadHuitunRuns();
      const summary = run.summary;
      setMessage(
        run.items.length
          ? `已获取 ${run.items.length} 个灰豚候选词，成功种子 ${summary?.success_seed_count ?? 0} 个，失败种子 ${summary?.failed_seed_count ?? 0} 个。`
          : "没有获取到候选词，可展开手工导入灰豚热词临时处理。"
      );
    } catch {
      setMessage("灰豚候选词获取失败，请检查账号登录态，或使用手工导入灰豚热词。");
    } finally {
      setIsHuitunWorking(false);
    }
  }
```

- [ ] **Step 6: Replace seed input UI with batch TextArea and limit input**

In the Huitun card row, replace the single seed `<Input>` column with:

```tsx
          <Col xs={24} md={10}>
            <Form.Item label="种子关键词（批量）">
              <Input.TextArea
                value={huitunSeed}
                onChange={(e) => setHuitunSeed(e.target.value)}
                placeholder="每行一个，例如：\n低卡早餐\n通勤穿搭\n小个子穿搭"
                autoSize={{ minRows: 3, maxRows: 6 }}
              />
              <Text type="secondary" style={{ fontSize: 12 }}>
                支持换行、中文逗号、英文逗号分隔，最多 50 个种子词。
              </Text>
            </Form.Item>
          </Col>
          <Col xs={24} md={3}>
            <Form.Item label="每词数量">
              <Input
                value={limitPerSeed}
                onChange={(e) => setLimitPerSeed(Math.max(1, Math.min(100, Number(e.target.value) || 50)))}
              />
            </Form.Item>
          </Col>
```

Update the button label:

```tsx
批量获取灰豚候选词
```

- [ ] **Step 7: Add current run summary and failures**

Before candidate import controls, add:

```tsx
        {huitunRun?.summary ? (
          <Alert
            type={huitunRun.summary.failed_seed_count ? "warning" : "success"}
            showIcon
            message={`当前批次：成功种子 ${huitunRun.summary.success_seed_count} 个，失败种子 ${huitunRun.summary.failed_seed_count} 个，候选词 ${huitunRun.summary.total_item_count} 个。`}
            style={{ marginBottom: 16 }}
          />
        ) : null}
        {huitunRun?.seed_results?.some((item) => item.status === "failed") ? (
          <Alert
            type="warning"
            showIcon
            message="失败种子"
            description={
              <Space direction="vertical" size={4}>
                {huitunRun.seed_results.filter((item) => item.status === "failed").map((item) => (
                  <Text key={item.source_keyword} type="secondary">
                    {item.source_keyword}：{item.error_message}
                  </Text>
                ))}
              </Space>
            }
            style={{ marginBottom: 16 }}
          />
        ) : null}
```

- [ ] **Step 8: Add source seed filter and filtered data**

Before `return`, add:

```ts
  const sourceKeywordOptions = Array.from(new Set((huitunRun?.items ?? []).map((item) => item.source_keyword).filter(Boolean)));
  const filteredHuitunItems = huitunRun?.items.filter((item) => !sourceKeywordFilter || item.source_keyword === sourceKeywordFilter) ?? [];
```

Add a filter Select near import controls:

```tsx
            <Select
              allowClear
              value={sourceKeywordFilter ?? undefined}
              onChange={(value) => setSourceKeywordFilter(value ?? null)}
              placeholder="按来源种子筛选"
              style={{ width: 180 }}
              options={sourceKeywordOptions.map((keyword) => ({ value: keyword, label: keyword }))}
            />
```

Change table `dataSource`:

```tsx
            dataSource={filteredHuitunItems}
```

- [ ] **Step 9: Add recent run history Collapse**

After manual import collapse and before current run table, add:

```tsx
        <Divider />
        <Collapse
          ghost
          items={[
            {
              key: "history",
              label: "最近灰豚批次",
              children: huitunRuns.length ? (
                <List
                  size="small"
                  dataSource={huitunRuns}
                  renderItem={(run) => (
                    <List.Item
                      actions={[
                        <Button
                          key="view"
                          size="small"
                          onClick={async () => {
                            const detail = await fetchHuitunKeywordDiscoveryRun(run.id);
                            setHuitunRun(detail);
                            setSelectedCandidateIds(detail.items.filter((item) => !item.imported_group_id).map((item) => item.id));
                            setSourceKeywordFilter(null);
                          }}
                        >
                          查看
                        </Button>,
                      ]}
                    >
                      <List.Item.Meta
                        title={<Space><Text>{run.seed_keywords.join("，") || `批次 #${run.id}`}</Text><Tag>{run.status}</Tag></Space>}
                        description={`候选词 ${run.summary?.total_item_count ?? 0} 个 · 成功种子 ${run.summary?.success_seed_count ?? 0} · 失败种子 ${run.summary?.failed_seed_count ?? 0}`}
                      />
                    </List.Item>
                  )}
                />
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无灰豚批次" />
              ),
            },
          ]}
        />
```

- [ ] **Step 10: Run frontend static test for keywords wiring**

Run:

```bash
py -3 -m pytest tests/backend/test_frontend_ops_ux_sources.py::test_frontend_exposes_huitun_batch_run_history_and_seed_diagnostics -q
```

Expected: PASS.

## Task 12: Draft Duplicate Frontend Wiring

**Files:**
- Modify: `frontend/src/pages/platforms/xhs/drafts-page.tsx`

- [ ] **Step 1: Import Copy icon and duplicate API**

Add `CopyOutlined` to icon imports:

```ts
  CopyOutlined,
```

Add `duplicateDraft` to API imports:

```ts
  duplicateDraft,
```

- [ ] **Step 2: Add handler**

Inside component near `handleSave` / delete handlers, add:

```ts
  async function handleDuplicateDraft(draftId: number) {
    clearStatus();
    try {
      const copied = await duplicateDraft(draftId);
      upsertDraft(copied);
      setSelectedDraftId(copied.id);
      setMessage("已复制草稿，可拆分成多篇继续编辑。");
    } catch {
      setError("复制草稿失败。");
    }
  }
```

- [ ] **Step 3: Add copy button beside delete action in draft list**

In each draft `List.Item` action area, before the delete `Popconfirm`, add:

```tsx
                        <Button
                          type="text"
                          size="small"
                          icon={<CopyOutlined />}
                          title="复制草稿"
                          onClick={(e) => {
                            e.stopPropagation();
                            void handleDuplicateDraft(draft.id);
                          }}
                          style={{ flexShrink: 0 }}
                        >
                          复制草稿
                        </Button>
```

If the visual layout becomes crowded, keep text on desktop and use only icon on narrow layout in a later UI pass. Do not remove the accessible title.

- [ ] **Step 4: Run static test for draft duplicate**

Run:

```bash
py -3 -m pytest tests/backend/test_frontend_ops_ux_sources.py::test_frontend_exposes_draft_duplicate_action -q
```

Expected: PASS.

## Task 13: Publish Visibility Labels

**Files:**
- Modify: `frontend/src/pages/platforms/xhs/publish-page.tsx`

- [ ] **Step 1: Replace visibility options only**

Find the visibility Select options and replace with:

```tsx
options={[
  { value: "public", label: "公开可见" },
  { value: "mutual", label: "仅互关好友可见（待确认发布接口支持）", disabled: true },
  { value: "private", label: "仅自己可见" },
]}
```

Do not change the submit mapping yet. Existing submit logic should continue mapping public/private to backend 0/1. The disabled `mutual` option cannot be selected by the user.

- [ ] **Step 2: Run static visibility test**

Run:

```bash
py -3 -m pytest tests/backend/test_frontend_ops_ux_sources.py::test_publish_visibility_labels_match_xhs_without_enabling_unknown_privacy_value -q
```

Expected: PASS.

## Task 14: Split AI Generate Reference Inputs

**Files:**
- Modify: `frontend/src/pages/platforms/xhs/rewrite-page.tsx`

- [ ] **Step 1: Add state**

Find generate mode state:

```ts
  const [reference, setReference] = useState("");
```

Replace with:

```ts
  const [referenceLinks, setReferenceLinks] = useState("");
  const [referenceContext, setReferenceContext] = useState("");
```

- [ ] **Step 2: Add reference builder helper inside component**

Add near `handleGenerateNote`:

```ts
  function buildGenerateReference(): string {
    const sections: string[] = [];
    if (referenceLinks.trim()) {
      sections.push(`【参考链接】\n${referenceLinks.trim()}`);
    }
    if (referenceContext.trim()) {
      sections.push(`【补充信息】\n${referenceContext.trim()}`);
    }
    return sections.join("\n\n");
  }
```

- [ ] **Step 3: Update generate payload**

In `handleGenerateNote`, replace:

```ts
        reference,
```

with:

```ts
        reference: buildGenerateReference(),
```

- [ ] **Step 4: Replace generate form reference field**

In `renderGenerateMode()`, replace `Form.Item label="参考材料"` with two fields:

```tsx
            <Form.Item label="参考链接">
              <TextArea
                value={referenceLinks}
                onChange={(e) => setReferenceLinks(e.target.value)}
                placeholder="每行一个竞品笔记/网页链接，可不填"
                rows={3}
              />
            </Form.Item>
            <Form.Item label="补充信息">
              <TextArea
                value={referenceContext}
                onChange={(e) => setReferenceContext(e.target.value)}
                placeholder="卖点、评论洞察、人群信息、要强调/避免的内容"
                rows={5}
              />
            </Form.Item>
```

- [ ] **Step 5: Run static generate reference test**

Run:

```bash
py -3 -m pytest tests/backend/test_frontend_ops_ux_sources.py::test_generate_note_reference_inputs_are_split -q
```

Expected: PASS.

## Task 15: Backend and Frontend Verification

**Files:**
- No new files; run verification.

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
py -3 -m pytest tests/backend/test_huitun_keyword_discovery.py tests/backend/test_drafts_duplicate.py tests/backend/test_frontend_ops_ux_sources.py -q
```

Expected: PASS.

- [ ] **Step 2: Run existing API regression tests related to touched areas**

Run:

```bash
py -3 -m pytest tests/backend/test_api.py -q
```

Expected: PASS. If unrelated existing tests fail, capture the exact failing output and do not claim completion.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 4: Optional manual smoke test without real publish**

Start the app using the project’s normal local commands only if needed. Do not execute real XHS publish. Verify visually:

1. Keyword page shows batch seed TextArea and recent Huitun runs.
2. A fake/backend-tested run can be viewed from history when data exists.
3. Draft page has a copy action.
4. Publish page shows `公开可见 / 仅互关好友可见（待确认发布接口支持） / 仅自己可见`.
5. Generate mode shows `参考链接` and `补充信息`.

## Self-Review

- Spec coverage: This plan covers batch Huitun input, partial failure, run history, diagnostics, import compatibility, draft duplicate, publish visibility labels, and split AI generate references.
- Placeholder scan: No `TBD`, `TODO`, `implement later`, or unspecified “add tests” steps remain. Each code behavior has test-first steps.
- Type consistency: `HuitunSeedResult`, `HuitunDiscoverySummary`, `seed_results`, `summary`, `fetchHuitunKeywordDiscoveryRuns`, `duplicateDraft`, `referenceLinks`, and `referenceContext` are used consistently.
- Risk gate: The plan does not require database migrations, real publish, concurrent Huitun requests, or edits to `apis/`, `xhs_utils/`, `static/`.
- Project instruction override: No commit step is included because project rules say commits only when explicitly requested.

## Execution Notes

Recommended execution mode: subagent-driven implementation task by task, with review after each task group. If running inline, keep the TDD order: write the failing test, verify RED, implement minimal GREEN, then verify.

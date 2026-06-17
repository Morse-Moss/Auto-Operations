# XHS Crawler Save To Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the XHS data crawler save valid manual keyword and note URL crawl results into the system content library, including comments captured in the same crawl.

**Architecture:** Reuse the crawler module's existing `_save_normalized_notes` and `_save_note_comments` helpers inside the `/api/xhs/crawl/data` SSE flow. Add a `save_to_library` request flag and surface save counts/status in the frontend while preserving Excel export.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, React, Vite, TypeScript, Ant Design.

---

## File Structure

- Modify `backend/app/api/platforms/xhs/crawl.py`: add `save_to_library` to `DataCrawlRequest`; save valid notes/comments in `note_urls` and `search` modes; include save summary in `done` events.
- Modify `tests/backend/test_api.py`: add regression tests for data crawl save behavior, comments persistence, comment rate-limit resilience, and `save_to_library=false`.
- Modify `frontend/src/types/index.ts`: add `save_to_library` to `XhsDataCrawlPayload`; extend data crawl summary shape if needed.
- Modify `frontend/src/lib/api.ts`: parse save summary fields from `crawlXhsDataStream` done events.
- Modify `frontend/src/pages/platforms/xhs/crawler-page.tsx`: add save-to-library checkbox, pass flag to data crawl, and show saved/skipped summary.

## Task 1: Backend RED Tests For Data Crawl Persistence

**Files:**
- Modify: `tests/backend/test_api.py`

- [ ] **Step 1: Add a failing test for note URL crawl saving comments already fetched in the stream**

Add this test near the existing `test_xhs_data_crawl_marks_partial_failures_and_fetches_comments` tests:

```python
def test_xhs_data_crawl_note_urls_saves_notes_and_fetched_comments(tmp_path):
    from backend.app.api.platforms.xhs.pc import get_xhs_pc_api_adapter_factory
    from backend.app.core.database import get_db
    from backend.app.models import Note, NoteComment

    class FakeDataCrawlSaveAdapter:
        comment_calls = []

        def __init__(self, cookies):
            self.cookies = cookies

        def get_note_info(self, url):
            return True, "ok", {
                "data": {
                    "items": [
                        {
                            "note_card": {
                                "note_id": "data-save-url-001",
                                "display_title": "saved data crawl detail",
                                "desc": "saved detail body",
                                "user": {"nickname": "saved detail author"},
                                "interact_info": {"liked_count": 8, "comment_count": 1},
                                "image_list": [{"url": "https://img.example/data-save-url.png"}],
                            }
                        }
                    ]
                }
            }

        def get_note_comments(self, url):
            self.__class__.comment_calls.append(url)
            return True, "ok", {
                "data": {
                    "comments": [
                        {
                            "id": "data-save-comment-001",
                            "content": "保存后的评论",
                            "user_info": {"nickname": "comment author", "user_id": "comment-user"},
                            "like_count": "3",
                        }
                    ]
                }
            }

    db_dependency, owner_token, owner_account_id = _create_pc_account_with_cookie(tmp_path, "data-crawl-save-url-owner")
    FakeDataCrawlSaveAdapter.comment_calls = []
    app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: FakeDataCrawlSaveAdapter
    try:
        response = client.post(
            "/api/xhs/crawl/data",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "account_id": owner_account_id,
                "mode": "note_urls",
                "urls": ["https://www.xiaohongshu.com/explore/data-save-url-001?xsec_token=data-token"],
                "fetch_comments": True,
                "comment_sleep": 0,
                "save_to_library": True,
            },
        )

        assert response.status_code == 200
        payload = _parse_sse_response(response)
        assert payload["success_count"] == 1
        assert payload["saved_count"] == 1
        assert payload["skipped_count"] == 0
        assert payload["items"][0]["saved"] is True
        assert payload["items"][0]["comment_count"] == 1

        db = next(app.dependency_overrides[get_db]())
        try:
            note = db.query(Note).filter(Note.note_id == "data-save-url-001").one()
            assert note.title == "saved data crawl detail"
            assert note.content == "saved detail body"
            comments = db.query(NoteComment).filter(NoteComment.note_id == note.id).all()
            assert len(comments) == 1
            assert comments[0].comment_id == "data-save-comment-001"
            assert comments[0].content == "保存后的评论"
        finally:
            db.close()
        assert FakeDataCrawlSaveAdapter.comment_calls == ["https://www.xiaohongshu.com/explore/data-save-url-001?xsec_token=data-token"]
    finally:
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)
        app.dependency_overrides.pop(db_dependency, None)
```

- [ ] **Step 2: Add a failing test for search crawl saving a valid detail note**

```python
def test_xhs_data_crawl_search_saves_valid_detail_note(tmp_path):
    from backend.app.api.platforms.xhs.pc import get_xhs_pc_api_adapter_factory
    from backend.app.core.database import get_db
    from backend.app.models import Note

    class FakeSearchSaveAdapter:
        def __init__(self, cookies):
            self.cookies = cookies

        def search_note(self, keyword, page=1, **kwargs):
            return True, "ok", {
                "data": {
                    "has_more": False,
                    "items": [
                        {
                            "xsec_token": "xsec-data-save-search",
                            "note_card": {
                                "note_id": "data-save-search-001",
                                "display_title": "search source title",
                                "desc": "search source body",
                                "user": {"nickname": "search author"},
                            },
                        }
                    ],
                }
            }

        def get_note_info(self, url):
            return True, "ok", {
                "data": {
                    "items": [
                        {
                            "note_card": {
                                "note_id": "data-save-search-001",
                                "display_title": "saved search detail",
                                "desc": "saved search detail body",
                                "user": {"nickname": "saved search author"},
                                "image_list": [{"url": "https://img.example/data-save-search.png"}],
                            }
                        }
                    ]
                }
            }

    db_dependency, owner_token, owner_account_id = _create_pc_account_with_cookie(tmp_path, "data-crawl-save-search-owner")
    app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: FakeSearchSaveAdapter
    try:
        response = client.post(
            "/api/xhs/crawl/data",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "account_id": owner_account_id,
                "mode": "search",
                "keyword": "保存测试",
                "pages": 1,
                "max_notes": 1,
                "save_to_library": True,
            },
        )

        assert response.status_code == 200
        payload = _parse_sse_response(response)
        assert payload["success_count"] == 1
        assert payload["saved_count"] == 1
        assert payload["items"][0]["saved"] is True

        db = next(app.dependency_overrides[get_db]())
        try:
            note = db.query(Note).filter(Note.note_id == "data-save-search-001").one()
            assert note.title == "saved search detail"
            assert note.author_name == "saved search author"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)
        app.dependency_overrides.pop(db_dependency, None)
```

- [ ] **Step 3: Add a failing test for `save_to_library=false`**

```python
def test_xhs_data_crawl_does_not_save_when_save_to_library_is_false(tmp_path):
    from backend.app.api.platforms.xhs.pc import get_xhs_pc_api_adapter_factory
    from backend.app.core.database import get_db
    from backend.app.models import Note

    class FakeNoSaveAdapter:
        def __init__(self, cookies):
            self.cookies = cookies

        def get_note_info(self, url):
            return True, "ok", {
                "data": {
                    "items": [
                        {
                            "note_card": {
                                "note_id": "data-no-save-001",
                                "display_title": "not saved title",
                                "desc": "not saved body",
                                "user": {"nickname": "not saved author"},
                                "image_list": [{"url": "https://img.example/no-save.png"}],
                            }
                        }
                    ]
                }
            }

        def get_note_comments(self, url):
            return True, "ok", {"data": {"comments": [{"id": "no-save-comment", "content": "not saved"}]}}

    db_dependency, owner_token, owner_account_id = _create_pc_account_with_cookie(tmp_path, "data-crawl-no-save-owner")
    app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: FakeNoSaveAdapter
    try:
        response = client.post(
            "/api/xhs/crawl/data",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "account_id": owner_account_id,
                "mode": "note_urls",
                "urls": ["https://www.xiaohongshu.com/explore/data-no-save-001?xsec_token=data-token"],
                "fetch_comments": True,
                "comment_sleep": 0,
                "save_to_library": False,
            },
        )

        assert response.status_code == 200
        payload = _parse_sse_response(response)
        assert payload["success_count"] == 1
        assert payload["saved_count"] == 0
        assert payload["items"][0]["saved"] is False
        assert payload["items"][0]["comment_count"] == 1

        db = next(app.dependency_overrides[get_db]())
        try:
            assert db.query(Note).filter(Note.note_id == "data-no-save-001").count() == 0
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)
        app.dependency_overrides.pop(db_dependency, None)
```

- [ ] **Step 4: Run RED tests**

Run:

```bash
pytest tests/backend/test_api.py::test_xhs_data_crawl_note_urls_saves_notes_and_fetched_comments tests/backend/test_api.py::test_xhs_data_crawl_search_saves_valid_detail_note tests/backend/test_api.py::test_xhs_data_crawl_does_not_save_when_save_to_library_is_false -q
```

Expected: at least the first two tests fail because `saved_count` is missing/0 and no notes/comments are persisted.

## Task 2: Backend GREEN Implementation

**Files:**
- Modify: `backend/app/api/platforms/xhs/crawl.py`

- [ ] **Step 1: Add `save_to_library` to the request model**

Change `DataCrawlRequest` to include:

```python
save_to_library: bool = True
```

- [ ] **Step 2: Track save counts in `crawl_data.generate`**

At the start of `generate`, add:

```python
saved_count = 0
skipped_count = 0
```

- [ ] **Step 3: Save note URL mode results after comments are fetched**

In the `note_urls` success path, after optional comment fetch and before `_crawl_data_item`, insert:

```python
saved = False
if payload.save_to_library and quality["can_save"]:
    saved_notes = _save_normalized_notes(db, account, [note])
    saved = bool(saved_notes)
    if saved and comments_list:
        _save_note_comments(db, saved_notes[0], comments_list)
    saved_count += 1 if saved else 0
elif payload.save_to_library and not quality["can_save"]:
    skipped_count += 1
```

Then pass `saved=saved` to `_quality_item_fields`:

```python
**_quality_item_fields(quality, saved=saved),
```

- [ ] **Step 4: Save search mode results after comments are fetched**

In the `search` success path, after optional comment fetch and before `_crawl_data_item`, insert:

```python
saved = False
if payload.save_to_library and quality["can_save"]:
    saved_notes = _save_normalized_notes(db, account, [detail_note])
    saved = bool(saved_notes)
    if saved and comments_list:
        _save_note_comments(db, saved_notes[0], comments_list)
    saved_count += 1 if saved else 0
elif payload.save_to_library and not quality["can_save"]:
    skipped_count += 1
```

Then pass `saved=saved` to `_quality_item_fields`:

```python
**_quality_item_fields(quality, saved=saved),
```

- [ ] **Step 5: Include save fields in task completion and done event**

Extend `_complete_task` payload with:

```python
"saved_count": saved_count,
"skipped_count": skipped_count,
```

Extend the `done` SSE event with:

```python
"saved_count": saved_count,
"skipped_count": skipped_count,
"summary_message": f"采集完成：保存 {saved_count} 条，跳过 {skipped_count} 条。",
```

- [ ] **Step 6: Run GREEN backend tests**

Run:

```bash
pytest tests/backend/test_api.py::test_xhs_data_crawl_note_urls_saves_notes_and_fetched_comments tests/backend/test_api.py::test_xhs_data_crawl_search_saves_valid_detail_note tests/backend/test_api.py::test_xhs_data_crawl_does_not_save_when_save_to_library_is_false -q
```

Expected: all three pass.

## Task 3: Preserve Existing Crawler Behavior

**Files:**
- Modify: `tests/backend/test_api.py` if existing tests need expected summary fields only.
- Modify: `backend/app/api/platforms/xhs/crawl.py` if existing behavior regresses.

- [ ] **Step 1: Run existing data crawl tests**

Run:

```bash
pytest tests/backend/test_api.py::test_xhs_data_crawl_marks_partial_failures_and_fetches_comments tests/backend/test_api.py::test_xhs_data_crawl_search_comment_rate_limit_keeps_notes_successful tests/backend/test_api.py::test_xhs_data_crawl_search_expands_filters_and_fetches_details -q
```

Expected: all pass. Comment rate-limit test should still show `success_count == 2`, `comment_rate_limited_count == 1`, and `comment_skipped_count == 1`.

- [ ] **Step 2: If comment rate-limit test fails because save state changed**

Do not change the intended comment behavior. Keep detail fetch and note saving independent from comment failures.

## Task 4: Frontend Types And API Summary

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Add `save_to_library` to `XhsDataCrawlPayload`**

In `frontend/src/types/index.ts`, change the payload type to include:

```ts
save_to_library?: boolean;
```

- [ ] **Step 2: Add summary fields to `crawlXhsDataStream` return type**

In `frontend/src/lib/api.ts`, update the return type:

```ts
Promise<{
  total: number;
  success_count: number;
  failed_count: number;
  saved_count: number;
  skipped_count: number;
  comment_rate_limited_count?: number;
  comment_skipped_count?: number;
  summary_message?: string;
}>
```

Update the initial result:

```ts
{ total: 0, success_count: 0, failed_count: 0, saved_count: 0, skipped_count: 0, comment_rate_limited_count: 0, comment_skipped_count: 0, summary_message: "" }
```

Update `mapDone`:

```ts
(event) => ({
  total: Number(event.total || 0),
  success_count: Number(event.success_count || 0),
  failed_count: Number(event.failed_count || 0),
  saved_count: Number(event.saved_count || 0),
  skipped_count: Number(event.skipped_count || 0),
  comment_rate_limited_count: Number(event.comment_rate_limited_count || 0),
  comment_skipped_count: Number(event.comment_skipped_count || 0),
  summary_message: String(event.summary_message || ""),
})
```

## Task 5: Frontend Save Option And Summary

**Files:**
- Modify: `frontend/src/pages/platforms/xhs/crawler-page.tsx`

- [ ] **Step 1: Add local state**

Near the existing `fetchCommentsChecked` state, add:

```tsx
const [saveToLibraryChecked, setSaveToLibraryChecked] = useState(true);
const [dataSavedCount, setDataSavedCount] = useState(0);
const [dataSkippedCount, setDataSkippedCount] = useState(0);
```

- [ ] **Step 2: Reset save counts before runs**

In both run reset sections before data crawl, set:

```tsx
setDataSavedCount(0);
setDataSkippedCount(0);
```

- [ ] **Step 3: Send `save_to_library` in manual data crawl**

In the `crawlXhsDataStream` payload, add:

```tsx
save_to_library: mode === "comments" ? false : saveToLibraryChecked,
```

- [ ] **Step 4: Capture summary after manual data crawl**

After `setFailedCount(summary.failed_count);`, add:

```tsx
setDataSavedCount(summary.saved_count);
setDataSkippedCount(summary.skipped_count);
setSummaryMessage(summary.summary_message || `采集完成：保存 ${summary.saved_count} 条，跳过 ${summary.skipped_count} 条。`);
```

- [ ] **Step 5: Add checkbox UI**

In the row that currently contains `同时抓取评论`, add another `Col`:

```tsx
<Col span={8} style={{ display: "flex", alignItems: "center", paddingTop: 8 }}>
  <Checkbox
    checked={saveToLibraryChecked}
    onChange={(e) => setSaveToLibraryChecked(e.target.checked)}
    disabled={isKeywordGroupMode || mode === "comments"}
  >
    保存到系统内容库
  </Checkbox>
</Col>
```

Below the row, show a small hint for manual modes:

```tsx
{!isKeywordGroupMode && mode !== "comments" && saveToLibraryChecked ? (
  <Text type="secondary" style={{ display: "block", marginTop: 4, fontSize: 12 }}>
    有效详情会自动入库；同时抓取评论时，评论会随笔记一起保存。
  </Text>
) : null}
{!isKeywordGroupMode && mode === "comments" ? (
  <Text type="secondary" style={{ display: "block", marginTop: 4, fontSize: 12 }}>
    只爬评论模式不会创建新笔记，结果可在本页查看或导出 Excel。
  </Text>
) : null}
```

- [ ] **Step 6: Include save summary in results title**

In the results card title text, include saved/skipped counts:

```tsx
{dataSavedCount ? ` · 已保存 ${dataSavedCount}` : ""}{dataSkippedCount ? ` · 跳过入库 ${dataSkippedCount}` : ""}
```

## Task 6: Verification

**Files:**
- No new files.

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
pytest tests/backend/test_api.py::test_xhs_data_crawl_note_urls_saves_notes_and_fetched_comments tests/backend/test_api.py::test_xhs_data_crawl_search_saves_valid_detail_note tests/backend/test_api.py::test_xhs_data_crawl_does_not_save_when_save_to_library_is_false tests/backend/test_api.py::test_xhs_data_crawl_marks_partial_failures_and_fetches_comments tests/backend/test_api.py::test_xhs_data_crawl_search_comment_rate_limit_keeps_notes_successful tests/backend/test_api.py::test_xhs_data_crawl_search_expands_filters_and_fetches_details -q
```

Expected: all pass.

- [ ] **Step 2: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: build succeeds without TypeScript errors.

- [ ] **Step 3: Check git diff manually**

Run:

```bash
git diff -- backend/app/api/platforms/xhs/crawl.py tests/backend/test_api.py frontend/src/types/index.ts frontend/src/lib/api.ts frontend/src/pages/platforms/xhs/crawler-page.tsx docs/superpowers/specs/2026-06-17-xhs-crawler-save-to-library-design.md docs/superpowers/plans/2026-06-17-xhs-crawler-save-to-library.md
```

Expected: diff only contains the scoped crawler save-to-library changes and the design/plan docs. Do not commit unless the user explicitly asks.

## Self-Review

- Spec coverage: manual keyword and note URL save paths are covered by Tasks 1-5; comments persistence is covered by Task 1; `save_to_library=false` is covered by Task 1; frontend checkbox and summary are covered by Tasks 4-5; verification is covered by Task 6.
- Placeholder scan: no TBD/TODO placeholders are present.
- Type consistency: backend field is `save_to_library`; frontend payload uses `save_to_library`; response fields use `saved_count`, `skipped_count`, and `summary_message` consistently.

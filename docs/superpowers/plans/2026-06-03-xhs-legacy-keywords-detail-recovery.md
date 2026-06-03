# XHS Legacy Keywords + Detail Recovery Implementation Plan

> **For agentic workers:** implement task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not commit unless the user explicitly asks.

**Goal:** Implement the first legacy capability integration batch for the `XHS_ALL_IN_ONE` baseline: Huitun keyword candidate import, XHS detail quality gates, short-link diagnostics, rate-limit recognition, and user-visible crawl diagnostics.

**Architecture:** Keep the root FastAPI / React / SQLAlchemy system authoritative. Port legacy parsing and safety logic into Python services and current Web workflows. Do not run the legacy TypeScript CLI as a product dependency. Do not modify `apis/`, `xhs_utils/`, or `static/`.

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy, Alembic, React, Vite, Ant Design, SQLite-compatible JSON fields, current XHS PC adapter boundary.

---

## Commit Policy Note

This plan intentionally omits commit steps. The active project rules say to commit only when the user explicitly asks. If the user later asks to commit, use a concise English commit message and include the required Claude co-author trailer.

## Source of Truth

Approved design spec:

```text
docs/superpowers/specs/2026-06-02-xhs-legacy-keywords-detail-recovery-design.md
```

Relevant current files:

```text
backend/app/models/keyword_group.py
backend/app/api/keyword_groups.py
backend/app/api/platforms/xhs/pc.py
backend/app/api/platforms/xhs/crawl.py
backend/app/models/note.py
backend/app/models/task.py
backend/app/models/__init__.py
backend/alembic/versions/
frontend/src/pages/platforms/xhs/keywords-page.tsx
frontend/src/pages/platforms/xhs/crawler-page.tsx
frontend/src/lib/api.ts
frontend/src/types/index.ts
tests/backend/test_api.py
```

Relevant legacy references:

```text
legacy/xhs-ops-collector/src/browser/hotword-search.ts
legacy/xhs-ops-collector/src/utils/number.ts
legacy/xhs-ops-collector/src/browser/xhs-note-detail.ts
legacy/xhs-ops-collector/src/xhs-search-collector.ts
legacy/xhs-ops-collector/src/xhs-types.ts
```

## Safety Boundaries

- Do not execute real publish, Creator publish, Provider/API publish, or automatic publish.
- Do not store plaintext Cookie, token, API key, password, full `xsec_token`, request headers, or full HTML in diagnostics.
- Do not implement CAPTCHA bypass, risk-control bypass, account pools, detection evasion, or high-frequency retry.
- XHS real-account verification is optional and must be low-frequency, serial, and explicitly authorized for that specific run.
- Huitun first batch supports manual table/JSON/local connector output only; the backend must not persist or manage Huitun login state.

---

## Task 1: Add pure services and tests for legacy parsing/safety logic

**Files:**
- Create: `backend/app/services/huitun_keyword_source.py`
- Create: `backend/app/services/xhs_detail_recovery.py`
- Create: `backend/app/services/crawl_diagnostics.py`
- Create: `tests/backend/test_legacy_keyword_detail_recovery.py`

- [ ] **Step 1: Write failing tests for Huitun hotword parsing**

Create `tests/backend/test_legacy_keyword_detail_recovery.py` with tests that cover:

- `parse_huitun_number(None) -> None`
- `parse_huitun_number("") -> None`
- `parse_huitun_number("12.3万") -> 123000`
- `parse_huitun_number("8.6w") -> 86000`
- `parse_huitun_number("3,400") -> 3400`
- `parse_huitun_categories("户外 42.5%\n穿搭 18%")`
- `parse_hotword_rows_from_cells("露营", rows)` skips rows with fewer than 5 cells and empty words.
- `prioritize_exact_hotword_rows("露营", rows)` puts exact word match before non-exact rows while preserving rank order otherwise.

Expected before implementation: tests fail because the service module/functions do not exist.

- [ ] **Step 2: Implement `huitun_keyword_source.py` pure functions**

Implement these functions without browser automation:

```python
def parse_huitun_number(value: str | None) -> int | None: ...
def parse_huitun_categories(value: str) -> list[dict[str, str | None]]: ...
def parse_hotword_rows_from_cells(source_keyword: str, table_rows: list[list[str]]) -> list[dict]: ...
def prioritize_exact_hotword_rows(keyword: str, rows: list[dict]) -> list[dict]: ...
def dedupe_keyword_candidates(rows: list[dict]) -> list[dict]: ...
```

Rules:

- Match legacy semantics from `hotword-search.ts` and `utils/number.ts` where practical.
- Output field names should be backend/API friendly:
  - `source_keyword`
  - `keyword`
  - `hot_value_text`
  - `hot_value_number`
  - `note_count`
  - `interaction_text`
  - `interaction_number`
  - `categories`
  - `rank_index`
- Keep functions pure and deterministic.
- Do not introduce Playwright or browser dependencies.

- [ ] **Step 3: Write failing tests for XHS URL/rate-limit/detail-quality logic**

Add tests for:

- `should_reject_short_explore_url("https://www.xiaohongshu.com/explore/abc") is True`
- `should_reject_short_explore_url("https://www.xiaohongshu.com/explore/abc?xsec_token=t") is False`
- `should_reject_short_explore_url("https://www.xiaohongshu.com/search_result/abc?xsec_token=t") is False`
- `is_xhs_rate_limit_signal(url="https://www.xiaohongshu.com/website-login/error?error_code=300013") is True`
- `is_xhs_rate_limit_signal(text="访问频繁，请稍后再试") is True`
- `is_xhs_rate_limit_signal(message="普通详情失败") is False`
- `mask_xsec_token("abcdefghijk")` does not return the full token.
- `evaluate_detail_quality()` returns valid for strong signals: content, media, tags, or recognizable detail structure.
- `evaluate_detail_quality()` returns `search_card_only` for title/URL/interaction-only payloads.
- `evaluate_detail_quality()` returns invalid for empty details.

Expected before implementation: tests fail.

- [ ] **Step 4: Implement `xhs_detail_recovery.py` pure functions**

Implement:

```python
def should_reject_short_explore_url(url: str) -> bool: ...
def is_xhs_rate_limit_signal(url: str | None = None, text: str | None = None, message: str | None = None) -> bool: ...
def mask_xsec_token(token: str | None) -> str | None: ...
def classify_source_url(url: str) -> str: ...
def summarize_payload(raw_payload: object, source_url: str = "") -> dict: ...
def evaluate_detail_quality(normalized: dict, raw_payload: object | None = None) -> dict: ...
def build_user_message(diagnostic_kind: str | None, quality_status: str) -> str: ...
```

Expected `evaluate_detail_quality()` result shape:

```python
{
    "quality_status": "valid_detail" | "search_card_only" | "invalid_source_url" | "empty_detail_payload" | "detail_api_failed" | "rate_limited",
    "diagnostic_kind": "missing_xsec_token_short_explore" | "xhs_rate_limited" | "empty_detail_payload" | "detail_api_failed" | "invalid_note_identity" | None,
    "recoverable": True | False,
    "user_message": "...",
    "can_save": True | False,
}
```

Quality gate rules:

- Strong detail signals: non-empty content/detail text, media URLs, tags, recognizable detail payload structure.
- Weak signals: note id, URL, title, cover URL, likes/collects/comments/shares.
- Weak signals alone must not pass the detail quality gate.

- [ ] **Step 5: Implement `crawl_diagnostics.py` redaction helpers**

Implement pure helper functions first:

```python
SENSITIVE_KEYS = {...}
ALLOWED_SUMMARY_KEYS = {...}

def redact_diagnostic_raw(value: object) -> dict: ...
def diagnostic_payload_summary(raw_payload: object, source_url: str = "") -> dict: ...
```

Rules:

- Never keep Cookie, Authorization, access token, refresh token, API key, full `xsec_token`, request headers, or full HTML.
- Store only whitelisted summary fields such as `error_code`, `message`, `note_id`, `source_url_kind`, `has_xsec_token`, `payload_keys`, `has_data`, `item_count`, `has_content`, `has_media`, `has_tags`, `has_interaction`.
- If token presence is useful, use `has_xsec_token` or a masked token only.

- [ ] **Step 6: Run focused pure logic tests**

Run:

```bash
py -3 -m pytest tests/backend/test_legacy_keyword_detail_recovery.py
```

Expected: PASS.

---

## Task 2: Add SQLAlchemy models and Alembic migration

**Files:**
- Create: `backend/app/models/keyword_discovery.py`
- Create: `backend/app/models/crawl_diagnostic.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/<revision>_add_keyword_discovery_and_crawl_diagnostics.py`
- Modify: `tests/backend/test_api.py`

- [ ] **Step 1: Create keyword discovery models**

Create `backend/app/models/keyword_discovery.py`:

```python
class KeywordDiscoveryRun(Base):
    __tablename__ = "keyword_discovery_runs"

class KeywordDiscoveryItem(Base):
    __tablename__ = "keyword_discovery_items"
```

Required columns for `keyword_discovery_runs`:

- `id`
- `user_id` indexed FK to `users.id`
- `platform` indexed, default/expected `xhs`
- `source` indexed, first batch `huitun`
- `seed_keywords` JSON nullable
- `limit_per_seed` integer
- `source_mode` string
- `status` string
- `error_message` text nullable
- `created_at`
- `finished_at` nullable

Required columns for `keyword_discovery_items`:

- `id`
- `run_id` indexed FK to `keyword_discovery_runs.id`
- `user_id` indexed FK to `users.id`
- `platform` indexed
- `source` indexed
- `source_keyword` string
- `keyword` indexed string
- `hot_value_text` nullable string
- `hot_value_number` nullable integer
- `note_count` nullable integer
- `interaction_text` nullable string
- `interaction_number` nullable integer
- `categories` JSON nullable
- `rank_index` integer
- `selected` boolean default false
- `imported_group_id` nullable FK to `keyword_groups.id`
- `raw_json` JSON nullable, redacted/summary only
- `created_at`

- [ ] **Step 2: Create crawl diagnostic model**

Create `backend/app/models/crawl_diagnostic.py`:

```python
class CrawlDiagnostic(Base):
    __tablename__ = "crawl_diagnostics"
```

Required columns:

- `id`
- `user_id` indexed FK to `users.id`
- `task_id` nullable indexed FK to `tasks.id`
- `platform_account_id` nullable indexed FK to `platform_accounts.id`
- `platform` indexed
- `source` text
- `note_id` nullable indexed string
- `note_url` nullable text
- `stage` indexed string: `search`, `detail`, `comments`, `save`
- `kind` indexed string
- `severity` string: `info`, `warning`, `error`, `blocked`
- `recoverable` boolean
- `message` text
- `user_message` text
- `raw_json` JSON nullable, redacted summary only
- `created_at`

- [ ] **Step 3: Register models in `backend/app/models/__init__.py`**

Add imports and `__all__` entries:

```python
from backend.app.models.keyword_discovery import KeywordDiscoveryRun, KeywordDiscoveryItem
from backend.app.models.crawl_diagnostic import CrawlDiagnostic
```

Expected: `Base.metadata.create_all()` and Alembic env can see the models.

- [ ] **Step 4: Create Alembic migration**

Create a new migration under `backend/alembic/versions/`.

Use current head as `down_revision`:

```text
60cd5c95fde1
```

Migration must create:

```text
keyword_discovery_runs
keyword_discovery_items
crawl_diagnostics
```

Use `sa.JSON()` consistently with existing schema. Use nullable `task_id` for `crawl_diagnostics`.

Do not add these new datetime columns to the old SQLite datetime normalization compatibility migration; new tables start with current time handling.

- [ ] **Step 5: Update database schema tests**

In `tests/backend/test_api.py`, update `test_alembic_initial_migration_creates_all_product_tables` expected set to include:

```python
"keyword_discovery_runs",
"keyword_discovery_items",
"crawl_diagnostics",
```

Add a focused test that runs Alembic to head on a temp SQLite DB and inspects key columns/indexed tables.

- [ ] **Step 6: Run migration tests**

Run:

```bash
py -3 -m pytest tests/backend/test_api.py -k "alembic or database_initialization"
```

Expected: PASS.

---

## Task 3: Implement Huitun keyword discovery APIs

**Files:**
- Modify: `backend/app/api/keyword_groups.py`
- Modify/create tests: `tests/backend/test_api.py` or `tests/backend/test_keyword_groups.py`

- [ ] **Step 1: Add API schemas before route functions**

Add Pydantic request/response models in `backend/app/api/keyword_groups.py`:

```python
class HuitunDiscoveryInput(BaseModel): ...
class HuitunDiscoveryRunRequest(BaseModel): ...
class KeywordCandidateImportTarget(BaseModel): ...
class KeywordCandidateImportRequest(BaseModel): ...
```

Recommended request shape:

```json
{
  "source_mode": "manual_table",
  "limit_per_seed": 20,
  "inputs": [
    {
      "source_keyword": "露营",
      "table_rows": [["露营装备", "12.3万", "3400", "8.6万", "户外 42.5%"]],
      "items": []
    }
  ]
}
```

Supported `source_mode` values:

- `manual_table`
- `manual_json`
- `local_connector_output`

Reject any mode that implies backend-managed Huitun login or browser session.

- [ ] **Step 2: Add tests for discovery run creation**

Test flow:

1. Register/login a user through existing auth helper.
2. POST `/api/keyword-groups/huitun/discovery-runs` with manual table rows.
3. Assert response contains:
   - `status == "completed"`
   - parsed item keyword
   - hot value number
   - note count
   - interaction number
   - categories
4. Query temp DB and assert run/items were persisted.

Expected before implementation: endpoint 404.

- [ ] **Step 3: Implement discovery run endpoint**

Add static routes **before** dynamic `/{group_id}` routes to avoid route conflicts:

```python
@router.post("/huitun/discovery-runs")
def create_huitun_discovery_run(...): ...

@router.get("/huitun/discovery-runs/{run_id}")
def get_huitun_discovery_run(...): ...
```

Implementation rules:

- Use `get_current_user` and `get_db`.
- Create a `KeywordDiscoveryRun` with `source="huitun"`.
- Parse each input through `huitun_keyword_source.py`.
- Apply limit per seed and dedupe.
- Store `KeywordDiscoveryItem` rows.
- Keep `raw_json` to a safe candidate summary only.
- Return serialized run and items.

- [ ] **Step 4: Add tests for importing candidates into an existing group**

Test flow:

1. Create a keyword group with `keywords=["露营"]`.
2. Create discovery run items: `露营`, `露营装备`, `户外帐篷`.
3. POST `/api/keyword-groups/{group_id}/import-keyword-candidates`.
4. Assert keyword group becomes deduped list preserving existing keyword and appending new candidates.
5. Assert imported items have `selected=True` and `imported_group_id=group_id`.

- [ ] **Step 5: Add tests for creating a new group from candidates**

Test POST `/api/keyword-groups/import-keyword-candidates` with:

```json
{
  "candidate_ids": [1, 2],
  "merge_mode": "append_dedupe",
  "target": { "mode": "create", "name": "露营热词" }
}
```

Assert a new `KeywordGroup` is created with selected candidate keywords.

- [ ] **Step 6: Implement candidate import endpoints**

Add routes before `/{group_id}`:

```python
@router.post("/{group_id}/import-keyword-candidates")
def import_keyword_candidates_to_group(...): ...

@router.post("/import-keyword-candidates")
def import_keyword_candidates(...): ...
```

Important route order:

- `/huitun/discovery-runs` routes first.
- `/import-keyword-candidates` route before `/{group_id}`.
- `/{group_id}/import-keyword-candidates` is acceptable because `group_id` is an int path parameter, but keep static routes above dynamic routes.

Implementation rules:

- User can import only their own candidate items.
- Merge mode first batch: `append_dedupe` only.
- Do not mutate candidate hot metrics into `KeywordGroup.keywords`.
- Update `KeywordGroup.updated_at`.

- [ ] **Step 7: Run keyword API tests**

Run:

```bash
py -3 -m pytest tests/backend/test_api.py -k "keyword or huitun"
```

Expected: PASS.

---

## Task 4: Implement crawl diagnostics persistence and query API

**Files:**
- Modify: `backend/app/services/crawl_diagnostics.py`
- Modify: `backend/app/api/platforms/xhs/crawl.py`
- Modify/create tests: `tests/backend/test_api.py` or `tests/backend/test_crawl_diagnostics.py`

- [ ] **Step 1: Add persistence helpers**

Extend `crawl_diagnostics.py` with:

```python
def create_crawl_diagnostic(
    db: Session,
    *,
    user_id: int,
    task_id: int | None,
    platform_account_id: int | None,
    platform: str,
    source: str,
    note_id: str | None,
    note_url: str | None,
    stage: str,
    kind: str,
    severity: str,
    recoverable: bool,
    message: str,
    user_message: str,
    raw_payload: object | None = None,
) -> CrawlDiagnostic: ...

def serialize_crawl_diagnostic(diagnostic: CrawlDiagnostic) -> dict: ...
def quality_summary_from_items(items: list[dict]) -> dict: ...
```

Use `diagnostic_payload_summary()` for `raw_json`.

- [ ] **Step 2: Add tests for redaction and persistence**

Test that persisted `raw_json` does not contain:

- `Cookie`
- `Authorization`
- `web_session`
- full `xsec_token`
- request headers
- full HTML

Expected: diagnostics persist only safe summary keys.

- [ ] **Step 3: Add query endpoint**

In `backend/app/api/platforms/xhs/crawl.py`, add:

```python
@router.get("/diagnostics")
def list_crawl_diagnostics(task_id: int | None = None, ...): ...
```

Behavior:

- Requires authentication.
- Filters by current user.
- Optional `task_id` filter.
- Returns paginated or simple `{ "items": [...] }` response. Prefer simple response for first batch unless existing pagination helper is easy.

- [ ] **Step 4: Add tests for diagnostics ownership**

Test:

- User A can see their diagnostics.
- User B cannot see User A diagnostics.
- `task_id` filter works.

- [ ] **Step 5: Run diagnostics tests**

Run:

```bash
py -3 -m pytest tests/backend/test_api.py -k "diagnostic or crawl"
```

Expected: PASS.

---

## Task 5: Integrate detail recovery into PC detail and crawl flows

**Files:**
- Modify: `backend/app/api/platforms/xhs/pc.py`
- Modify: `backend/app/api/platforms/xhs/crawl.py`
- Modify/create tests: `tests/backend/test_api.py` or `tests/backend/test_xhs_detail_recovery.py`

- [ ] **Step 1: Add tests for `/xhs/pc/notes/detail` inline diagnostics**

Use adapter dependency override to avoid real XHS calls.

Test cases:

1. Short explore URL without `xsec_token`:
   - POST `/api/xhs/pc/notes/detail`
   - Expected status can be `422` or `400`; choose one and keep consistent.
   - Response detail includes `missing_xsec_token_short_explore` and user guidance.
   - Adapter is not called.

2. Adapter returns success with empty detail payload:
   - Response includes `quality_status="empty_detail_payload"` or equivalent.
   - `can_save` false or `quality_status` marks it invalid.

3. Adapter returns success with content/media/tags:
   - Response includes normalized note fields and `quality_status="valid_detail"`.

- [ ] **Step 2: Implement PC detail precheck and quality result**

In `pc.py`:

- Import `should_reject_short_explore_url`, `evaluate_detail_quality`, `build_user_message`, `is_xhs_rate_limit_signal`.
- Before decrypting/calling adapter, reject short explore URLs missing `xsec_token`.
- After adapter success, normalize payload, evaluate quality, and merge diagnostic fields into response:

```python
{
    **normalized,
    "quality_status": quality["quality_status"],
    "diagnostic_kind": quality["diagnostic_kind"],
    "recoverable": quality["recoverable"],
    "user_message": quality["user_message"],
    "can_save": quality["can_save"],
}
```

If adapter fails and message indicates rate limit, return structured rate-limit diagnostic with no retry.

- [ ] **Step 3: Add tests for `_crawl_data_item` diagnostic fields**

Expected item shape must include:

```python
{
    "source": "...",
    "status": "success" | "partial" | "failed" | "skipped",
    "quality_status": "...",
    "recoverable": True | False,
    "diagnostic_kind": "..." | None,
    "save_diagnostic_kind": "..." | None,
    "user_message": "...",
    "saved": True | False,
    "note": ...,
    "comments": [...],
    "comment_count": 0,
}
```

- [ ] **Step 4: Update `_crawl_data_item()`**

Modify helper in `crawl.py` to accept optional diagnostic fields and default to backward-compatible values:

```python
def _crawl_data_item(
    *,
    source: str,
    status: str,
    note: dict[str, Any] | None = None,
    comments: list[dict[str, Any]] | None = None,
    error: str = "",
    quality_status: str = "unknown",
    recoverable: bool = False,
    diagnostic_kind: str | None = None,
    save_diagnostic_kind: str | None = None,
    user_message: str = "",
    saved: bool = False,
) -> dict[str, Any]: ...
```

- [ ] **Step 5: Add tests for save quality gate**

Test `_save_normalized_notes()` or a new wrapper only saves valid details.

Cases:

- Valid detail with content/media saves.
- Search-card-only item is skipped.
- Empty detail is skipped.
- Skipped item gets diagnostic `save_skipped_low_quality`.

If testing private helpers becomes too brittle, use an API test with fake adapter and temp DB.

- [ ] **Step 6: Implement save filtering helper**

Add helper in `crawl.py` or service:

```python
def _filter_saveable_notes(normalized_items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]: ...
```

Rules:

- Only save `evaluate_detail_quality(...)["can_save"] is True`.
- Skipped low-quality entries should generate diagnostics when task context exists.
- Keep existing `Task.status` values compatible (`completed` or `failed`). Put partial counts in payload.

- [ ] **Step 7: Apply quality gate to saving endpoints**

Update these endpoints:

```text
POST /api/xhs/crawl/note-urls
POST /api/xhs/crawl/search-notes
POST /api/xhs/crawl/user-notes
POST /api/xhs/crawl/data
```

Important behavior by endpoint:

- `note-urls`: reject/diagnose short explore URL before adapter call; save only valid detail.
- `search-notes`: search card results are not valid detail by default. Either fetch details before saving or skip saving and report `search_card_only`. Prefer skip in first batch unless a specific detail fetch budget is added.
- `user-notes`: same rule as `search-notes`; do not silently save card-only data as full detail.
- `data`: do not add implicit content-library saving unless `DataCrawlRequest` is explicitly extended. First batch should improve stream diagnostics and quality status without surprising persistence.

- [ ] **Step 8: Add rate-limit circuit behavior**

When adapter failure message or payload indicates XHS rate limit:

- Create `xhs_rate_limited` diagnostic.
- Stop current detail loop.
- Mark remaining not-yet-processed items as `skipped` if they are already known.
- Put summary into `Task.payload`:

```python
{
    "result_count": success_count,
    "failed_count": failed_count,
    "skipped_count": skipped_count,
    "saved_count": saved_count,
    "quality_summary": {...},
}
```

Do not do aggressive retry.

- [ ] **Step 9: Run detail/crawl tests**

Run:

```bash
py -3 -m pytest tests/backend/test_api.py -k "xhs or crawl or detail or diagnostic"
```

Expected: PASS.

---

## Task 6: Update frontend types and API clients

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Add frontend types**

Add types:

```ts
export type HuitunDiscoverySourceMode = "manual_table" | "manual_json" | "local_connector_output";

export type KeywordDiscoveryItem = { ... };
export type KeywordDiscoveryRun = { ... };
export type HuitunDiscoveryRunPayload = { ... };
export type KeywordCandidateImportPayload = { ... };
export type CrawlDiagnostic = { ... };
```

Extend `XhsSearchNote` with optional fields:

```ts
quality_status?: string;
diagnostic_kind?: string | null;
recoverable?: boolean;
user_message?: string;
can_save?: boolean;
```

Extend `XhsDataCrawlItem` with optional/required diagnostic fields matching backend response:

```ts
quality_status?: string;
recoverable?: boolean;
diagnostic_kind?: string | null;
save_diagnostic_kind?: string | null;
user_message?: string;
saved?: boolean;
```

- [ ] **Step 2: Add API client functions**

In `frontend/src/lib/api.ts`, add:

```ts
export async function createHuitunKeywordDiscoveryRun(payload: HuitunDiscoveryRunPayload): Promise<KeywordDiscoveryRun> { ... }
export async function fetchHuitunKeywordDiscoveryRun(runId: number): Promise<KeywordDiscoveryRun> { ... }
export async function importKeywordCandidatesToGroup(groupId: number, payload: KeywordCandidateImportPayload): Promise<KeywordGroupDetail> { ... }
export async function importKeywordCandidates(payload: KeywordCandidateImportPayload): Promise<KeywordGroupDetail> { ... }
export async function fetchXhsCrawlDiagnostics(taskId?: number): Promise<{ items: CrawlDiagnostic[] }> { ... }
```

- [ ] **Step 3: Add static source tests if current suite uses source assertions**

Existing tests inspect frontend source strings. Add or update tests to ensure:

- API client includes `/keyword-groups/huitun/discovery-runs`.
- Types include `KeywordDiscoveryItem`.
- Crawler item type includes `quality_status` and `diagnostic_kind`.

- [ ] **Step 4: Run frontend type/build later in Task 8**

No standalone frontend build yet if pages are not updated. Continue to Task 7.

---

## Task 7: Update Keywords and Crawler pages

**Files:**
- Modify: `frontend/src/pages/platforms/xhs/keywords-page.tsx`
- Modify: `frontend/src/pages/platforms/xhs/crawler-page.tsx`

- [ ] **Step 1: Add Huitun import UI to Keywords page**

In `keywords-page.tsx`, add a card above or beside the manual group form:

- Seed keyword input.
- TextArea for pasted Huitun table rows.
- Button: `解析灰豚热词`.
- Candidate table/list showing:
  - keyword
  - hot value
  - note count
  - interaction
  - categories
  - source seed
  - rank
- Selection state for candidate IDs.
- Action:
  - import into selected existing group
  - create new group from selected candidates

UX rules:

- Do not mention Cookie/token.
- If parsing fails, show next action: “请粘贴灰豚热词表格或 JSON 导出”。
- Default dedupe.
- Refresh keyword groups after import.

- [ ] **Step 2: Add Crawler diagnostics columns**

In `crawler-page.tsx`, update table columns:

- status
- quality status
- diagnostic kind
- user message
- saved
- existing title/author/interaction/comment/error columns

Suggested labels:

```text
质量
诊断
提示
入库
```

Map statuses:

- `valid_detail` -> success tag
- `search_card_only` -> warning tag
- `missing_xsec_token_short_explore` -> error tag
- `xhs_rate_limited` -> warning/error tag with cooldown guidance

- [ ] **Step 3: Update Excel export**

Add export headers before note fields:

```text
质量状态
诊断类型
保存诊断
用户提示
是否可恢复
是否已入库
```

Keep existing spider-style note headers unchanged after the new diagnostic prefix.

- [ ] **Step 4: Add source assertion tests**

Add/update tests in `tests/backend/test_api.py` if current project continues source-level frontend checks:

- `keywords-page.tsx` contains `灰豚热词` and candidate import function references.
- `crawler-page.tsx` contains `quality_status`, `diagnostic_kind`, and `是否已入库`.
- `api.ts` contains new API endpoints.

- [ ] **Step 5: Run source assertion tests**

Run:

```bash
py -3 -m pytest tests/backend/test_api.py -k "crawler_page or keyword or frontend"
```

Expected: PASS.

---

## Task 8: Full verification without real platform actions

**Files:**
- No source changes unless verification reveals defects.

- [ ] **Step 1: Run backend tests**

Run:

```bash
py -3 -m pytest tests
```

Expected: PASS. If failures occur, report exact failing tests and fix only defects caused by this implementation.

- [ ] **Step 2: Run frontend build**

Run:

```bash
npm --prefix frontend run build
```

Expected: PASS. Existing chunk-size warnings are acceptable; TypeScript or build errors are not.

- [ ] **Step 3: Run backend health smoke**

Run backend without frontend:

```bash
py -3 main.py --host 127.0.0.1 --port 8000
```

Then check:

```text
http://127.0.0.1:8000/api/health
```

Expected response:

```json
{"status":"ok","service":"spider-xhs"}
```

Stop the local backend after the check.

- [ ] **Step 4: Run local UI smoke if backend/frontend are available**

Start:

```bash
py -3 main.py --with-frontend --host 127.0.0.1 --port 8000 --frontend-port 18080
```

Check:

```text
http://127.0.0.1:18080
```

Smoke targets:

- Keywords page loads.
- Huitun import card is visible.
- Crawler page loads.
- Crawler table includes diagnostic columns.
- No page error.
- No API 5xx.

- [ ] **Step 5: Do not run real XHS or publish actions in this task**

This verification phase must not:

- Publish notes.
- Call Creator publish.
- Run Provider/API publishing.
- Trigger automatic operations.
- Run high-frequency XHS crawling.

---

## Task 9: Optional authorized low-frequency XHS QA

**Files:**
- No source changes unless QA finds defects.

Only run this task if the user explicitly authorizes this specific real-account QA run.

- [ ] **Step 1: Confirm PC account status without exposing cookies**

Use existing account health endpoint/UI. Do not print or store Cookie values.

Expected: one XHS PC account is active/healthy enough for read-only tests.

- [ ] **Step 2: Run low-frequency read-only chain**

Use one harmless keyword and serial calls:

1. Search one page.
2. Pick one result with full `xsec_token` URL.
3. Fetch one detail.
4. Fetch a small number of comments.
5. Save one valid detail only if it passes quality gate.
6. Query content library to confirm it exists.

- [ ] **Step 3: Verify negative diagnostic**

Use a deliberately short explore URL without `xsec_token`:

```text
https://www.xiaohongshu.com/explore/<note_id>
```

Expected:

- Adapter is not called.
- Response/diagnostic says `missing_xsec_token_short_explore`.
- The item is not saved to content library.

- [ ] **Step 4: Report QA result**

Report:

```text
Real XHS QA: pass | partial | failed | skipped
Account action scope: read-only PC search/detail/comments only
Published anything: no
Saved valid note: yes | no
Short-link diagnostic: pass | fail
Rate limit encountered: yes | no
Logs/errors: <summary>
```

---

## Self-Review Checklist

- Spec coverage:
  - Huitun parsing and import: Tasks 1, 2, 3, 6, 7.
  - Detail URL/rate-limit/quality gate: Tasks 1, 4, 5.
  - Diagnostics persistence and UI display: Tasks 2, 4, 6, 7.
  - Verification: Tasks 8 and 9.

- Placeholder scan:
  - No unresolved `TODO`, `TBD`, or unnamed files should remain in implementation files.
  - New functions and endpoints have explicit tests.

- Compatibility:
  - `KeywordGroup.keywords` remains `list[str]`.
  - `Task.status` remains compatible with existing `completed` / `failed` values.
  - `crawl_diagnostics.task_id` is nullable for non-task diagnostics.
  - No legacy SQLite import.
  - No root dependency on legacy TypeScript CLI.

- Safety:
  - No plaintext Cookie/token/API key persistence.
  - No full `xsec_token` persistence.
  - No full HTML diagnostics in first batch.
  - No bottom-layer SDK/signature changes.
  - No real publish or publish-adjacent action.

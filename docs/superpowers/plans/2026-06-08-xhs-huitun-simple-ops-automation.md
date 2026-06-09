# XHS Huitun Simple Ops Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a simple frontend flow where an operator imports Huitun hotwords, creates/updates a keyword group, then starts one low-frequency XHS keyword crawl from that group and sees a human-readable result summary.

**Architecture:** Huitun now has an account-matrix path with QR login and encrypted server-side login persistence, plus manual table / JSON fallback. The keyword-group crawl SSE endpoint reuses the existing XHS PC adapter, detail quality gate, save gate, diagnostics, and task model. The frontend keeps a simple path from the keyword group card to the crawler page, with advanced crawl parameters hidden behind a progressive-disclosure area.

**Tech Stack:** FastAPI, SQLAlchemy, existing XHS PC adapter, Server-Sent Events, React, Vite, Ant Design, pytest, frontend production build, browser UI smoke.

---

## File Map

- Modify `backend/app/api/platforms/xhs/crawl.py`
  - Add `KeywordGroupCrawlRequest`.
  - Add `POST /api/xhs/crawl/keyword-group` SSE endpoint.
  - Reuse existing helpers: `_owned_pc_account`, `_create_crawl_task`, `_normalize_search_item`, `_normalize_detail_payload`, `evaluate_detail_quality`, `_save_normalized_notes`, `_record_crawl_diagnostic`, `_crawl_data_item`.
  - Return item events and a final done event with `saved_count`, `skipped_count`, `rate_limited_count`, `missing_detail_count`, and `summary_message`.

- Modify `frontend/src/types/index.ts`
  - Add `XhsKeywordGroupCrawlPayload`.
  - Add `XhsKeywordGroupCrawlSummary`.
  - Add optional `keyword` on `XhsDataCrawlItem` so grouped results can show which keyword produced each note.

- Modify `frontend/src/lib/api.ts`
  - Add `crawlXhsKeywordGroupStream()`.
  - Keep it consistent with `crawlXhsDataStream()`.

- Modify `frontend/src/pages/platforms/xhs/keywords-page.tsx`
  - Add a primary `开始采集` button on each keyword group card.
  - Navigate to `/platforms/xhs/crawler?keyword_group_id=<id>`.
  - Keep edit/delete secondary.

- Modify `frontend/src/pages/platforms/xhs/crawler-page.tsx`
  - Read `keyword_group_id` from query string.
  - Load keyword groups and show simple mode if a group is selected.
  - Simple mode fields: PC account, keyword group, keyword count, per-keyword note count, comments toggle.
  - Hide advanced sleep/filter options unless the user expands `高级设置`.
  - Run keyword-group crawl through the new SSE client.
  - Show result summary in human words: saved, skipped, rate-limited, missing-detail/low-quality.

- Modify `tests/backend/test_api.py`
  - Add backend API test for keyword-group crawl using a fake adapter.
  - Add frontend source assertions for simple Huitun ops flow.

## Constraints

- Do not modify `apis/`, `xhs_utils/`, or `static/`.
- Do not store Huitun passwords or expose plaintext Cookie/token in code, docs, logs, frontend storage, or API responses; Huitun login state must stay encrypted server-side.
- Do not real-publish anything.
- XHS crawling must remain low-frequency and serial.
- Save only `valid_detail` notes; low-quality detail stays visible as skipped/diagnosed.
- Frontend acceptance must be done through visible UI interaction, not only API calls.

---

### Task 1: Backend keyword-group crawl endpoint

**Files:**
- Modify: `backend/app/api/platforms/xhs/crawl.py`
- Test: `tests/backend/test_api.py`

- [ ] **Step 1: Add a failing backend test**

Add a test that creates a user, a PC account, a keyword group, overrides the XHS adapter, calls `/api/xhs/crawl/keyword-group`, parses SSE, and asserts:

```python
assert response.status_code == 200
parsed = _parse_sse_response(response)
assert parsed["saved_count"] == 1
assert parsed["skipped_count"] >= 1
assert parsed["summary_message"].startswith("采集完成")
assert any(item.get("keyword") == "低卡早餐" for item in parsed["items"])
```

The fake adapter should return one search item with a usable `note_url`, then a detail payload with title/content/media so quality becomes `valid_detail`.

- [ ] **Step 2: Run the focused failing test**

Run:

```bash
py -3 -m pytest tests/backend/test_api.py -k "keyword_group_crawl" -q
```

Expected: FAIL because `/api/xhs/crawl/keyword-group` does not exist.

- [ ] **Step 3: Implement minimal backend endpoint**

Add:

```python
class KeywordGroupCrawlRequest(BaseModel):
    account_id: int
    keyword_group_id: int
    keyword_limit: int = Field(default=5, ge=1, le=20)
    max_notes_per_keyword: int = Field(default=5, ge=1, le=50)
    time_sleep: float = Field(default=1, ge=0, le=60)
    fetch_comments: bool = False
    sort_type_choice: int = Field(default=0, ge=0, le=4)
    note_type: int = Field(default=0, ge=0, le=2)
    note_time: int = Field(default=0, ge=0, le=3)
```

Endpoint behavior:

```text
POST /api/xhs/crawl/keyword-group
1. Verify owned PC account.
2. Verify owned XHS keyword group.
3. Take first N normalized keywords from group.
4. For each keyword serially:
   - search page 1
   - detail each result until max_notes_per_keyword
   - apply detail quality gate
   - record diagnostics for skipped/failed details
   - save only can_save=true notes
   - emit SSE item events immediately
5. Emit done event with human summary.
```

Done event shape:

```json
{
  "type": "done",
  "task_id": 123,
  "total": 8,
  "success_count": 3,
  "failed_count": 5,
  "saved_count": 3,
  "skipped_count": 5,
  "rate_limited_count": 0,
  "missing_detail_count": 2,
  "summary_message": "采集完成：保存 3 条，跳过 5 条，访问频繁 0 条，详情缺失 2 条。"
}
```

- [ ] **Step 4: Run backend test again**

Run:

```bash
py -3 -m pytest tests/backend/test_api.py -k "keyword_group_crawl" -q
```

Expected: PASS.

---

### Task 2: Frontend API contract and keyword entry

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/pages/platforms/xhs/keywords-page.tsx`
- Test: `tests/backend/test_api.py`

- [ ] **Step 1: Add frontend source assertions**

Assert these strings exist:

```python
assert "crawlXhsKeywordGroupStream" in api_source
assert "XhsKeywordGroupCrawlPayload" in types_source
assert "keyword_group_id" in keywords_page_source
assert "开始采集" in keywords_page_source
```

- [ ] **Step 2: Add frontend types and client**

Add payload/summary types and a streaming client mirroring `crawlXhsDataStream()` but posting to:

```text
/api/xhs/crawl/keyword-group
```

- [ ] **Step 3: Add keyword group card CTA**

In each keyword group card, add a primary button:

```tsx
<Button type="primary" onClick={() => navigate(`/platforms/xhs/crawler?keyword_group_id=${group.id}`)}>
  开始采集
</Button>
```

Keep edit/delete as secondary actions.

- [ ] **Step 4: Run frontend source test**

Run:

```bash
py -3 -m pytest tests/backend/test_api.py -k "frontend_exposes_huitun" -q
```

Expected: PASS.

---

### Task 3: Simple crawler UI

**Files:**
- Modify: `frontend/src/pages/platforms/xhs/crawler-page.tsx`
- Test: `tests/backend/test_api.py`

- [ ] **Step 1: Add source assertions for simple mode**

Assert these strings exist:

```python
assert "关键词组一键采集" in crawler_page_source
assert "傻瓜模式" not in crawler_page_source
assert "高级设置" in crawler_page_source
assert "crawlXhsKeywordGroupStream" in crawler_page_source
assert "summary_message" in crawler_page_source
assert "采集完成" in crawler_page_source
```

- [ ] **Step 2: Implement simple mode state**

Add state for:

```tsx
const [keywordGroups, setKeywordGroups] = useState<KeywordGroup[]>([]);
const [selectedKeywordGroupId, setSelectedKeywordGroupId] = useState<number | null>(null);
const [keywordLimit, setKeywordLimit] = useState(5);
const [maxNotesPerKeyword, setMaxNotesPerKeyword] = useState(5);
const [showAdvanced, setShowAdvanced] = useState(false);
const [summaryMessage, setSummaryMessage] = useState<string | null>(null);
```

Read `keyword_group_id` from the URL and preselect it.

- [ ] **Step 3: Implement one-click run**

When a keyword group is selected, the primary action should call `crawlXhsKeywordGroupStream()` and show:

```text
将采集 X 个关键词，每个关键词最多 Y 条，系统会低频串行执行，只保存有效详情。
```

- [ ] **Step 4: Show human-readable summary**

After done event, show an Ant Design success Alert:

```text
采集完成：保存 N 条，跳过 M 条，访问频繁 K 条，详情缺失 L 条。
```

- [ ] **Step 5: Run frontend build**

Run:

```bash
npm --prefix frontend run build
```

Expected: PASS. Existing chunk-size warning is acceptable.

---

### Task 4: Full verification and UI acceptance

**Files:**
- No code changes unless verification exposes a defect.

- [ ] **Step 1: Run backend focused tests**

```bash
py -3 -m pytest tests/backend/test_api.py -k "keyword_group_crawl or frontend_exposes_huitun" -q
```

Expected: PASS.

- [ ] **Step 2: Run full backend tests**

```bash
py -3 -m pytest tests -q
```

Expected: PASS.

- [ ] **Step 3: Build frontend**

```bash
npm --prefix frontend run build
```

Expected: PASS.

- [ ] **Step 4: Start local app for UI smoke**

Run the project server with the fixed frontend port 18080 and backend port 18081.

- [ ] **Step 5: Simulate real operator frontend flow**

Using browser automation against the visible frontend:

```text
1. Login as operator.
2. Open XHS → 关键词组.
3. Paste one Huitun hotword table sample into the Huitun import box.
4. Click 解析灰豚热词.
5. Select candidates.
6. Import into a keyword group.
7. Click 开始采集 on that group.
8. Verify crawler page opens with the group preselected.
9. Click 开始采集.
10. Verify the page shows item rows and human summary.
```

If real XHS account/cookies are not available in the local DB, use a mocked/local test path only for UI acceptance and report that real XHS external calls were not performed. Do not ask for or store Huitun credentials.

## Self-Review

- Scope is one product loop: Huitun hotwords → keyword group → one-click XHS crawl → valid details saved → human summary.
- It does not touch XHS SDK/signature files.
- It now includes Huitun account-matrix login persistence, but only via encrypted server-side account/cookie storage and non-sensitive API responses.
- It keeps advanced crawl parameters out of the operator's default path.
- Verification includes both tests/build and frontend/UI or real low-frequency API operation.

## 2026-06-09 Closeout Status

Implemented in code commit `b09cdc1 feat: add Huitun account keyword discovery flow`:

- Huitun accounts are managed in the account matrix as `platform="huitun"`, `sub_type="main"`.
- Huitun QR login and Cookie fallback persist login state through encrypted server-side account cookie versions.
- Huitun encrypted `extData` is decrypted server-side with the web-client-compatible AES-ECB/PKCS7 path.
- Keyword groups can fetch Huitun candidates with `source_mode="live_account"` and import them into XHS keyword groups.
- XHS keyword-group crawl runs low-frequency and serial, applies detail quality gates, and saves only valid details.

Verified before commit:

- `py -3 -m pytest tests -q` → `159 passed, 6 warnings`.
- `npm --prefix frontend run build` → build completed, only existing chunk-size warning.
- Real low-frequency chain for seed `浴缸`: Huitun API live discovery returned candidates, keyword group imported, XHS PC crawl saved 6 valid notes, and content library query confirmed入库.

# Wechat Official Redfox Target Count Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not create commits unless the user explicitly authorizes commits; use the checkpoint steps instead.

**Goal:** Let users request a target number of keyword-relevant Redfox articles, automatically fetch more pages within a safe limit, filter unrelated results before saving, and report filtering statistics.

**Architecture:** Keep Redfox as the upstream retrieval source, but make `WechatOfficialRedfoxService.collect_articles` responsible for deterministic relevance filtering before persistence. The backend returns richer summary statistics; the frontend sends `target_count` and `max_pages` instead of making users think in Redfox pages.

**Tech Stack:** Python 3.10+/FastAPI/SQLAlchemy backend, pytest backend tests, React/Vite/TypeScript/Ant Design frontend.

---

## File Structure

- Modify `tests/backend/test_wechat_official_redfox_collect.py`
  - Add failing tests for target related count, auto-pagination, relevance filtering, and `target_reached=false`.
  - Update existing keyword fake data so the old smoke test remains meaningful after stricter filtering.
- Modify `backend/app/services/wechat_official_redfox_service.py`
  - Add bounded helpers for `target_count` and `max_pages`.
  - Add keyword tokenization and relevance matching helpers.
  - Change `collect_articles` to fetch pages until target is reached or max pages is exhausted.
  - Change `_save_collection` to accept raw fetched count and summary extras without changing account/url behavior.
- Modify `frontend/src/types/index.ts`
  - Add `target_count`, `max_pages`, and new summary fields.
- Modify `frontend/src/pages/wechat-official/wechat-official-dashboard.tsx`
  - Replace keyword/batch “页数” primary control with “目标相关篇数” and “最多翻页”.
  - Pass new payload fields.
  - Show filtered/relevance/target feedback in the last collection summary.

No database migration is required. No Redfox client endpoint change is required.

---

### Task 1: Add Backend Failing Tests for Target Count and Relevance Filtering

**Files:**
- Modify: `tests/backend/test_wechat_official_redfox_collect.py`

- [ ] **Step 1: Update existing fake keyword data so the current smoke test still has 2 relevant keyword results**

In `FakeRedfoxClient.search_articles`, change the second article content at `tests/backend/test_wechat_official_redfox_collect.py:61` from:

```python
"content": "正文：普通文章。",
```

to:

```python
"content": "正文：普通文章，也讨论私域增长。",
```

This keeps `test_redfox_keyword_collect_saves_articles_metrics_snapshots_and_candidates` focused on persistence, metrics, snapshots, candidates, and draft safety after relevance filtering exists.

- [ ] **Step 2: Append a fake client for auto-pagination tests**

Add this class after `FakeRedfoxClient` and before `_override_database`:

```python
class FakeTargetCountRedfoxClient:
    calls: list[tuple[str, int, str]] = []

    def __init__(self, *, base_url: str, api_key: str) -> None:
        self.base_url = base_url
        self.api_key = api_key
        assert api_key == "redfox-collect-secret"

    def search_articles(self, *, keyword: str, offset: int, sort_type: str) -> dict:
        assert keyword == "浴缸"
        assert sort_type == "_4"
        self.__class__.calls.append((keyword, offset, sort_type))
        pages = {
            0: [
                {
                    "workUuid": "bathtub-page-1-relevant",
                    "title": "阳台上的浴缸改造",
                    "summary": "浴缸装修案例",
                    "workUrl": "https://mp.weixin.qq.com/s/bathtub-1",
                    "author": "家居研究所",
                    "content": "正文：浴缸空间改造。",
                    "readCount": 120000,
                    "likeCount": 300,
                },
                {
                    "workUuid": "bathtub-page-1-irrelevant",
                    "title": "防范儿童溺水，这6大高危场景千万要警惕！",
                    "summary": "安全教育提醒",
                    "workUrl": "https://mp.weixin.qq.com/s/safety-1",
                    "author": "教育号",
                    "content": "正文：户外水域安全。",
                    "readCount": 100001,
                    "likeCount": 200,
                },
            ],
            20: [
                {
                    "workUuid": "bathtub-page-2-relevant",
                    "title": "小户型浴缸怎么选",
                    "summary": "选浴缸避坑指南",
                    "workUrl": "https://mp.weixin.qq.com/s/bathtub-2",
                    "author": "装修编辑部",
                    "content": "正文：浴缸尺寸和材质。",
                    "readCount": 99000,
                    "likeCount": 88,
                },
                {
                    "workUuid": "bathtub-page-2-irrelevant",
                    "title": "新证据显示：火星曾有海洋",
                    "summary": "科学新闻",
                    "workUrl": "https://mp.weixin.qq.com/s/mars-1",
                    "author": "参考消息",
                    "content": "正文：行星科学。",
                    "readCount": 88000,
                    "likeCount": 66,
                },
            ],
            40: [
                {
                    "workUuid": "bathtub-page-3-relevant",
                    "title": "浴缸清洁保养清单",
                    "summary": "卫生间维护",
                    "workUrl": "https://mp.weixin.qq.com/s/bathtub-3",
                    "author": "生活方式",
                    "content": "正文：浴缸清洁。",
                    "readCount": 76000,
                    "likeCount": 55,
                },
            ],
        }
        return {"code": 2000, "data": {"list": pages.get(offset, [])}}

    def query_work_list(self, *, account: str, account_name: str, offset: int, sort_type: str, publish_time_start: str | None, publish_time_end: str | None) -> dict:
        raise AssertionError("query_work_list should not be called by keyword target-count tests")

    def query_article_detail(self, *, url: str) -> dict:
        raise AssertionError("query_article_detail should not be called by keyword target-count tests")

    def validate_key(self) -> dict:
        return {"code": 2000, "data": {"ok": True}}
```

- [ ] **Step 3: Add a test for auto-pagination stopping once target relevant count is reached**

Append this test after `test_redfox_keyword_collect_saves_articles_metrics_snapshots_and_candidates`:

```python
def test_redfox_keyword_collect_filters_unrelated_articles_and_stops_at_target_count(tmp_path, monkeypatch):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    FakeTargetCountRedfoxClient.calls = []
    monkeypatch.setattr(redfox_service, "WechatOfficialRedfoxClient", FakeTargetCountRedfoxClient, raising=False)
    try:
        headers = _register("redfox-target-count-user")
        _save_config(headers)

        response = client.post(
            "/api/wechat-official/redfox/collect/articles",
            headers=headers,
            json={
                "keyword": "浴缸",
                "target_count": 2,
                "max_pages": 3,
                "sort_type": "_4",
                "min_read_count": 100000,
                "save_snapshot": True,
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["summary"]["fetched"] == 4
        assert payload["summary"]["saved"] == 2
        assert payload["summary"]["filtered"] == 2
        assert payload["summary"]["relevance_matched"] == 2
        assert payload["summary"]["requested_target_count"] == 2
        assert payload["summary"]["max_pages"] == 3
        assert payload["summary"]["target_reached"] is True
        assert payload["summary"]["api_calls"] == 2
        assert FakeTargetCountRedfoxClient.calls == [("浴缸", 0, "_4"), ("浴缸", 20, "_4")]
        assert {item["title"] for item in payload["items"]} == {"阳台上的浴缸改造", "小户型浴缸怎么选"}

        with TestingSessionLocal() as db:
            articles = db.scalars(select(WechatOfficialArticle)).all()
            assert {article.title for article in articles} == {"阳台上的浴缸改造", "小户型浴缸怎么选"}
            job = db.scalar(select(WechatOfficialCrawlJob))
            assert job is not None
            assert job.keyword == "浴缸"
            assert job.requested_limit == 2
            assert job.fetched_count == 4
            assert job.saved_count == 2
            assert job.params_json["target_count"] == 2
            assert job.params_json["max_pages"] == 3
            assert job.params_json["filtered"] == 2
            assert job.params_json["target_reached"] is True
    finally:
        app.dependency_overrides.pop(get_db, None)
```

- [ ] **Step 4: Add a test for target not reached after max pages**

Append this test after the previous test:

```python
def test_redfox_keyword_collect_reports_target_not_reached_when_relevant_results_are_insufficient(tmp_path, monkeypatch):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    FakeTargetCountRedfoxClient.calls = []
    monkeypatch.setattr(redfox_service, "WechatOfficialRedfoxClient", FakeTargetCountRedfoxClient, raising=False)
    try:
        headers = _register("redfox-target-not-reached-user")
        _save_config(headers)

        response = client.post(
            "/api/wechat-official/redfox/collect/articles",
            headers=headers,
            json={
                "keyword": "浴缸",
                "target_count": 4,
                "max_pages": 2,
                "sort_type": "_4",
                "min_read_count": 0,
                "save_snapshot": True,
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["summary"]["fetched"] == 4
        assert payload["summary"]["saved"] == 2
        assert payload["summary"]["filtered"] == 2
        assert payload["summary"]["relevance_matched"] == 2
        assert payload["summary"]["requested_target_count"] == 4
        assert payload["summary"]["max_pages"] == 2
        assert payload["summary"]["target_reached"] is False
        assert payload["summary"]["api_calls"] == 2
        assert FakeTargetCountRedfoxClient.calls == [("浴缸", 0, "_4"), ("浴缸", 20, "_4")]

        with TestingSessionLocal() as db:
            job = db.scalar(select(WechatOfficialCrawlJob))
            assert job is not None
            assert job.requested_limit == 4
            assert job.fetched_count == 4
            assert job.saved_count == 2
            assert job.params_json["target_reached"] is False
    finally:
        app.dependency_overrides.pop(get_db, None)
```

- [ ] **Step 5: Run the new tests and verify they fail before implementation**

Run:

```bash
py -3 -m pytest tests/backend/test_wechat_official_redfox_collect.py::test_redfox_keyword_collect_filters_unrelated_articles_and_stops_at_target_count tests/backend/test_wechat_official_redfox_collect.py::test_redfox_keyword_collect_reports_target_not_reached_when_relevant_results_are_insufficient -q
```

Expected before implementation: FAIL. The current service ignores `target_count`/`max_pages`, fetches only one page when `pages` is absent, saves unfiltered results, and does not include `filtered`, `relevance_matched`, `requested_target_count`, `max_pages`, or `target_reached` in the summary.

- [ ] **Step 6: Checkpoint**

Run:

```bash
git diff -- tests/backend/test_wechat_official_redfox_collect.py
```

Expected: diff only contains the fake data adjustment and the two new tests. Do not commit unless the user explicitly authorizes commits.

---

### Task 2: Implement Backend Target Count, Auto-Pagination, and Relevance Filtering

**Files:**
- Modify: `backend/app/services/wechat_official_redfox_service.py`
- Test: `tests/backend/test_wechat_official_redfox_collect.py`

- [ ] **Step 1: Add constants near existing Redfox constants**

At the top of `backend/app/services/wechat_official_redfox_service.py`, replace:

```python
DEFAULT_PAGE_SIZE = 20
MAX_PAGES = 3
```

with:

```python
DEFAULT_PAGE_SIZE = 20
DEFAULT_TARGET_COUNT = 10
MAX_TARGET_COUNT = 50
MAX_PAGES = 3
MAX_KEYWORD_AUTO_PAGES = 5
```

`MAX_PAGES` remains the legacy cap for account collection and old `pages` callers. `MAX_KEYWORD_AUTO_PAGES` is the new cap for keyword auto-pagination.

- [ ] **Step 2: Replace `collect_articles` with target-count logic**

Replace the entire `collect_articles` method with:

```python
    def collect_articles(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        keyword = str(payload.get("keyword") or "").strip()
        if not keyword:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="keyword is required")
        target_count = _bounded_int(payload.get("target_count"), default=_legacy_target_count(payload.get("pages")), minimum=1, maximum=MAX_TARGET_COUNT)
        max_pages = _bounded_int(payload.get("max_pages"), default=_bounded_pages(payload.get("pages")), minimum=1, maximum=MAX_KEYWORD_AUTO_PAGES)
        sort_type = str(payload.get("sort_type") or "_4")
        client = self._client(user_id)
        matched: list[dict[str, Any]] = []
        fetched_count = 0
        filtered_count = 0
        api_calls = 0
        for page_index in range(max_pages):
            response = client.search_articles(keyword=keyword, offset=page_index * DEFAULT_PAGE_SIZE, sort_type=sort_type)
            api_calls += 1
            page_items = self.adapter.normalize_article_list(response)
            fetched_count += len(page_items)
            for item in page_items:
                if _matches_keyword(item, keyword):
                    matched.append(item)
                    if len(matched) >= target_count:
                        break
                else:
                    filtered_count += 1
            if len(matched) >= target_count:
                break
        matched = matched[:target_count]
        target_reached = len(matched) >= target_count
        return self._save_collection(
            user_id,
            matched,
            source_label="redfox_keyword",
            keyword=keyword,
            requested_limit=target_count,
            min_read_count=int(payload.get("min_read_count") or 100000),
            save_snapshot=bool(payload.get("save_snapshot", True)),
            api_calls=api_calls,
            params={
                "keyword": keyword,
                "target_count": target_count,
                "max_pages": max_pages,
                "sort_type": sort_type,
                "filtered": filtered_count,
                "relevance_matched": len(matched),
                "target_reached": target_reached,
            },
            fetched_count=fetched_count,
            summary_extra={
                "requested_target_count": target_count,
                "max_pages": max_pages,
                "filtered": filtered_count,
                "relevance_matched": len(matched),
                "target_reached": target_reached,
            },
        )
```

- [ ] **Step 3: Extend `_save_collection` signature and summary**

Change `_save_collection` signature from:

```python
    def _save_collection(
        self,
        user_id: int,
        articles_payload: list[dict[str, Any]],
        *,
        source_label: str,
        keyword: str,
        requested_limit: int,
        min_read_count: int,
        save_snapshot: bool,
        api_calls: int,
        params: dict[str, Any],
    ) -> dict[str, Any]:
```

to:

```python
    def _save_collection(
        self,
        user_id: int,
        articles_payload: list[dict[str, Any]],
        *,
        source_label: str,
        keyword: str,
        requested_limit: int,
        min_read_count: int,
        save_snapshot: bool,
        api_calls: int,
        params: dict[str, Any],
        fetched_count: int | None = None,
        summary_extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
```

Inside the job creation, replace:

```python
            fetched_count=len(articles_payload),
```

with:

```python
            fetched_count=fetched_count if fetched_count is not None else len(articles_payload),
```

Before the `return` at the end of `_save_collection`, replace the inline summary with a local variable:

```python
        summary = {
            "fetched": fetched_count if fetched_count is not None else len(articles_payload),
            "saved": len(saved_articles),
            "deduped": deduped,
            "viral_candidates": viral_candidates,
            "failed": 0,
            "api_calls": api_calls,
            "estimated_credit_cost": None,
        }
        if summary_extra:
            summary.update(summary_extra)
        return {
            "summary": summary,
            "job": {"id": job.id, "source": job.source, "status": job.status},
            "items": items,
        }
```

The account and URL paths do not pass `fetched_count` or `summary_extra`, so their response shape remains backward-compatible.

- [ ] **Step 4: Add bounded and relevance helper functions near `_bounded_pages`**

Insert these helpers above `_bounded_pages`:

```python
def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value if value is not None else default)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def _legacy_target_count(pages_value: Any) -> int:
    return _bounded_pages(pages_value) * DEFAULT_PAGE_SIZE


def _keyword_tokens(keyword: str) -> list[str]:
    separators = [",", "，", "、", "\n", "\t"]
    normalized = keyword.strip()
    for separator in separators:
        normalized = normalized.replace(separator, " ")
    tokens = [token.strip().lower() for token in normalized.split(" ") if token.strip()]
    return tokens or [keyword.strip().lower()]


def _matches_keyword(item: dict[str, Any], keyword: str) -> bool:
    tokens = _keyword_tokens(keyword)
    raw = item.get("raw") if isinstance(item.get("raw"), dict) else {}
    fields = [
        item.get("title"),
        item.get("digest"),
        item.get("content_text"),
        raw.get("title"),
        raw.get("summary"),
        raw.get("memo"),
    ]
    haystack = " ".join(str(value or "") for value in fields).lower()
    return any(token in haystack for token in tokens)
```

Leave existing `_bounded_pages` in place for account collection and legacy compatibility.

- [ ] **Step 5: Run target-count tests**

Run:

```bash
py -3 -m pytest tests/backend/test_wechat_official_redfox_collect.py::test_redfox_keyword_collect_filters_unrelated_articles_and_stops_at_target_count tests/backend/test_wechat_official_redfox_collect.py::test_redfox_keyword_collect_reports_target_not_reached_when_relevant_results_are_insufficient -q
```

Expected: PASS.

- [ ] **Step 6: Run the full Redfox collect test file**

Run:

```bash
py -3 -m pytest tests/backend/test_wechat_official_redfox_collect.py -q
```

Expected: all tests in the file pass. If the first existing keyword test fails because the second fake article is filtered, confirm Task 1 Step 1 changed its content to include `私域增长`.

- [ ] **Step 7: Checkpoint**

Run:

```bash
git diff -- backend/app/services/wechat_official_redfox_service.py tests/backend/test_wechat_official_redfox_collect.py
```

Expected: backend diff is limited to target-count collection, relevance helpers, summary extras, and tests. Do not commit unless the user explicitly authorizes commits.

---

### Task 3: Update Frontend Types and API Contract

**Files:**
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Add new payload fields**

In `WechatOfficialRedfoxKeywordCollectPayload`, replace:

```typescript
export type WechatOfficialRedfoxKeywordCollectPayload = {
  keyword: string;
  pages?: number;
  sort_type?: "_0" | "_2" | "_4" | string;
  min_read_count?: number;
  save_snapshot?: boolean;
};
```

with:

```typescript
export type WechatOfficialRedfoxKeywordCollectPayload = {
  keyword: string;
  pages?: number;
  target_count?: number;
  max_pages?: number;
  sort_type?: "_0" | "_2" | "_4" | string;
  min_read_count?: number;
  save_snapshot?: boolean;
};
```

Keep `pages?: number` temporarily for backward compatibility.

- [ ] **Step 2: Add new summary fields as optional fields**

In `WechatOfficialRedfoxCollectSummary`, replace:

```typescript
export type WechatOfficialRedfoxCollectSummary = {
  fetched: number;
  saved: number;
  deduped: number;
  viral_candidates: number;
  failed: number;
  api_calls: number;
  estimated_credit_cost?: number | null;
};
```

with:

```typescript
export type WechatOfficialRedfoxCollectSummary = {
  fetched: number;
  saved: number;
  deduped: number;
  viral_candidates: number;
  failed: number;
  api_calls: number;
  estimated_credit_cost?: number | null;
  requested_target_count?: number;
  max_pages?: number;
  filtered?: number;
  relevance_matched?: number;
  target_reached?: boolean;
};
```

The new fields are optional because account collection and URL import reuse the same response type but do not need keyword relevance statistics.

- [ ] **Step 3: Run TypeScript build after frontend task, not yet**

Do not run build yet if Task 4 has not updated usages. Proceed to Task 4.

- [ ] **Step 4: Checkpoint**

Run:

```bash
git diff -- frontend/src/types/index.ts
```

Expected: only payload and summary type changes. Do not commit unless the user explicitly authorizes commits.

---

### Task 4: Update Frontend Forms, Payloads, and Result Copy

**Files:**
- Modify: `frontend/src/pages/wechat-official/wechat-official-dashboard.tsx`

- [ ] **Step 1: Add frontend defaults**

Near existing constants:

```typescript
const DEFAULT_MIN_READ = 100000;
const MAX_BATCH_KEYWORDS = 5;
```

replace with:

```typescript
const DEFAULT_MIN_READ = 100000;
const DEFAULT_TARGET_COUNT = 10;
const DEFAULT_MAX_PAGES = 3;
const MAX_BATCH_KEYWORDS = 5;
```

- [ ] **Step 2: Update form types**

Replace `KeywordForm` and `BatchKeywordsForm` definitions:

```typescript
type KeywordForm = {
  keyword: string;
  pages: number;
  min_read_count: number;
};

type BatchKeywordsForm = {
  keywords: string;
  pages: number;
  min_read_count: number;
};
```

with:

```typescript
type KeywordForm = {
  keyword: string;
  target_count: number;
  max_pages: number;
  min_read_count: number;
};

type BatchKeywordsForm = {
  keywords: string;
  target_count: number;
  max_pages: number;
  min_read_count: number;
};
```

Leave `AccountForm.pages` unchanged because account collection still works by page.

- [ ] **Step 3: Replace batch watched values**

Replace:

```typescript
  const batchKeywords = splitKeywords(String(Form.useWatch("keywords", batchForm) || ""));
  const batchPages = Number(Form.useWatch("pages", batchForm) || 1);
```

with:

```typescript
  const batchKeywords = splitKeywords(String(Form.useWatch("keywords", batchForm) || ""));
  const batchTargetCount = Number(Form.useWatch("target_count", batchForm) || DEFAULT_TARGET_COUNT);
  const batchMaxPages = Number(Form.useWatch("max_pages", batchForm) || DEFAULT_MAX_PAGES);
```

- [ ] **Step 4: Update single keyword payload**

In `handleKeywordCollect`, replace:

```typescript
    const response = await collectWechatOfficialRedfoxArticles({
      keyword: values.keyword,
      pages: values.pages ?? 1,
      sort_type: "_4",
      min_read_count: values.min_read_count ?? DEFAULT_MIN_READ,
      save_snapshot: true,
    });
```

with:

```typescript
    const response = await collectWechatOfficialRedfoxArticles({
      keyword: values.keyword,
      target_count: values.target_count ?? DEFAULT_TARGET_COUNT,
      max_pages: values.max_pages ?? DEFAULT_MAX_PAGES,
      sort_type: "_4",
      min_read_count: values.min_read_count ?? DEFAULT_MIN_READ,
      save_snapshot: true,
    });
```

- [ ] **Step 5: Update batch keyword payload**

In `handleBatchCollect`, replace:

```typescript
        const response = await collectWechatOfficialRedfoxArticles({
          keyword,
          pages: values.pages ?? 1,
          sort_type: "_4",
          min_read_count: values.min_read_count ?? DEFAULT_MIN_READ,
          save_snapshot: true,
        });
```

with:

```typescript
        const response = await collectWechatOfficialRedfoxArticles({
          keyword,
          target_count: values.target_count ?? DEFAULT_TARGET_COUNT,
          max_pages: values.max_pages ?? DEFAULT_MAX_PAGES,
          sort_type: "_4",
          min_read_count: values.min_read_count ?? DEFAULT_MIN_READ,
          save_snapshot: true,
        });
```

- [ ] **Step 6: Update summary copy**

Replace `collectSummaryText`:

```typescript
function collectSummaryText(result: WechatOfficialRedfoxCollectResponse | null): string {
  if (!result) return "尚未执行收集";
  const { summary } = result;
  return `拉取 ${summary.fetched}，保存 ${summary.saved}，10万+候选 ${summary.viral_candidates}，重复 ${summary.deduped}，API 调用 ${summary.api_calls}`;
}
```

with:

```typescript
function collectSummaryText(result: WechatOfficialRedfoxCollectResponse | null): string {
  if (!result) return "尚未执行收集";
  const { summary } = result;
  const base = `拉取 ${summary.fetched}，保存 ${summary.saved}，10万+候选 ${summary.viral_candidates}，重复 ${summary.deduped}，API 调用 ${summary.api_calls}`;
  if (summary.filtered === undefined || summary.relevance_matched === undefined) return base;
  const targetText = summary.requested_target_count ? `目标 ${summary.requested_target_count} 篇，` : "";
  const reachedText = summary.target_reached === false ? "未达目标，建议换关键词或提高最多翻页" : "已达目标";
  return `${targetText}相关命中 ${summary.relevance_matched}，过滤 ${summary.filtered}；${base}；${reachedText}`;
}
```

- [ ] **Step 7: Update single keyword form controls**

Replace the single keyword form block:

```tsx
              <Form form={keywordForm} layout="inline" initialValues={{ pages: 1, min_read_count: DEFAULT_MIN_READ }}>
                <Form.Item name="keyword" rules={[{ required: true, message: "请输入关键词" }]}><Input placeholder="关键词，如 私域增长" /></Form.Item>
                <Form.Item name="pages" label="页数"><InputNumber min={1} max={3} /></Form.Item>
                <Form.Item name="min_read_count" label="最低阅读"><InputNumber min={0} step={10000} /></Form.Item>
                <Form.Item><Button type="primary" loading={busyAction === "collect-keyword"} onClick={handleKeywordCollect}>开始收集爆文</Button></Form.Item>
              </Form>
```

with:

```tsx
              <Form form={keywordForm} layout="inline" initialValues={{ target_count: DEFAULT_TARGET_COUNT, max_pages: DEFAULT_MAX_PAGES, min_read_count: DEFAULT_MIN_READ }}>
                <Form.Item name="keyword" rules={[{ required: true, message: "请输入关键词" }]}><Input placeholder="关键词，如 浴缸" /></Form.Item>
                <Form.Item name="target_count" label="目标相关篇数"><InputNumber min={1} max={50} /></Form.Item>
                <Form.Item name="max_pages" label="最多翻页"><InputNumber min={1} max={5} /></Form.Item>
                <Form.Item name="min_read_count" label="最低阅读"><InputNumber min={0} step={10000} /></Form.Item>
                <Form.Item><Button type="primary" loading={busyAction === "collect-keyword"} onClick={handleKeywordCollect}>开始收集爆文</Button></Form.Item>
              </Form>
```

- [ ] **Step 8: Update batch keyword form controls and API estimate**

Replace the batch form opening and controls:

```tsx
              <Form form={batchForm} layout="vertical" initialValues={{ pages: 1, min_read_count: DEFAULT_MIN_READ }}>
```

with:

```tsx
              <Form form={batchForm} layout="vertical" initialValues={{ target_count: DEFAULT_TARGET_COUNT, max_pages: DEFAULT_MAX_PAGES, min_read_count: DEFAULT_MIN_READ }}>
```

Then replace this `Space` block content:

```tsx
                  <Form.Item name="pages" label="页数"><InputNumber min={1} max={3} /></Form.Item>
                  <Form.Item name="min_read_count" label="最低阅读"><InputNumber min={0} step={10000} /></Form.Item>
                  <Button type="primary" loading={busyAction === "collect-batch"} onClick={handleBatchCollect}>执行批量收集</Button>
                  <Tag color="gold">预计 API 调用 {batchKeywords.length * batchPages}</Tag>
```

with:

```tsx
                  <Form.Item name="target_count" label="目标相关篇数"><InputNumber min={1} max={50} /></Form.Item>
                  <Form.Item name="max_pages" label="最多翻页"><InputNumber min={1} max={5} /></Form.Item>
                  <Form.Item name="min_read_count" label="最低阅读"><InputNumber min={0} step={10000} /></Form.Item>
                  <Button type="primary" loading={busyAction === "collect-batch"} onClick={handleBatchCollect}>执行批量收集</Button>
                  <Tag color="gold">最多 API 调用 {batchKeywords.length * batchMaxPages}</Tag>
                  <Tag color="blue">每词目标 {batchTargetCount} 篇</Tag>
```

- [ ] **Step 9: Update batch result text**

Replace:

```tsx
{item.summary ? `拉取 ${item.summary.fetched} / 保存 ${item.summary.saved} / 候选 ${item.summary.viral_candidates} / API ${item.summary.api_calls}` : item.error}
```

with:

```tsx
{item.summary ? `拉取 ${item.summary.fetched} / 命中 ${item.summary.relevance_matched ?? item.summary.saved} / 过滤 ${item.summary.filtered ?? 0} / 保存 ${item.summary.saved} / API ${item.summary.api_calls}` : item.error}
```

- [ ] **Step 10: Update explanatory paragraph**

Replace:

```tsx
            <Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>默认 1 页，最多 3 页；批量关键词会串行执行，避免并发消耗 Redfox API。</Paragraph>
```

with:

```tsx
            <Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>系统会过滤标题、摘要或正文不命中关键词的结果，并在最多翻页范围内尽量补足目标相关篇数；批量关键词会串行执行，避免并发消耗 Redfox API。</Paragraph>
```

- [ ] **Step 11: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: TypeScript and Vite build pass.

- [ ] **Step 12: Checkpoint**

Run:

```bash
git diff -- frontend/src/types/index.ts frontend/src/pages/wechat-official/wechat-official-dashboard.tsx
```

Expected: only Redfox keyword collection type/form/summary changes. Do not commit unless the user explicitly authorizes commits.

---

### Task 5: Full Verification and Final Diff Review

**Files:**
- Verify: `backend/app/services/wechat_official_redfox_service.py`
- Verify: `tests/backend/test_wechat_official_redfox_collect.py`
- Verify: `frontend/src/types/index.ts`
- Verify: `frontend/src/pages/wechat-official/wechat-official-dashboard.tsx`

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
py -3 -m pytest tests/backend/test_wechat_official_redfox_collect.py -q
```

Expected: all tests in the file pass.

- [ ] **Step 2: Run related content library tests because candidate/library behavior depends on saved articles**

Run:

```bash
py -3 -m pytest tests/backend/test_wechat_official_content_library.py -q
```

Expected: all tests in the file pass.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: TypeScript and Vite build pass.

- [ ] **Step 4: Inspect final diff**

Run:

```bash
git diff -- backend/app/services/wechat_official_redfox_service.py tests/backend/test_wechat_official_redfox_collect.py frontend/src/types/index.ts frontend/src/pages/wechat-official/wechat-official-dashboard.tsx docs/superpowers/specs/2026-06-18-wechat-official-redfox-target-count-design.md docs/superpowers/plans/2026-06-18-wechat-official-redfox-target-count.md
```

Expected: diff includes only the Redfox target related count feature, its tests, the design spec, and this plan.

- [ ] **Step 5: Report verification honestly**

Report:

- Backend test command and result.
- Content library test command and result.
- Frontend build command and result.
- Whether commits were skipped because the project requires explicit user authorization.
- Whether root `master` contains the changes. If no commit was made, say changes are uncommitted in root workspace.

Do not say “complete” unless the verification commands passed. If any command fails, include the failing output and stop for investigation.

---

## Plan Self-Review

- **Spec coverage:** The plan covers target related count, auto-pagination, deterministic relevance filtering, richer summary statistics, frontend controls, and backend/frontend verification. Account and URL collection remain out of scope except for preserving existing behavior.
- **Placeholder scan:** No TBD/TODO/later placeholders are present. Each code change step includes exact code or exact replacement instructions.
- **Type consistency:** Backend fields are `target_count`, `max_pages`, `filtered`, `relevance_matched`, `requested_target_count`, and `target_reached`; frontend payload and summary types use the same field names.
- **Project rule check:** Commit steps are replaced by checkpoints because this repository requires explicit user authorization before committing.

# XHS Feishu Analysis Filters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Feishu-returned analysis fields appear as dynamic, grouped content-library filters with multi-select OR behavior.

**Architecture:** Store the only missing returned field (`search_attribute`) on `note_analysis_results`, keep existing compatible fields for core product/service (`subject_object`), content type (`content_type`), reusable model (`reusable_models`), and content usage (`reuse_value`). The `/api/notes` backend owns true filtering and dynamic option aggregation; the React content-library shell only renders a clean two-card filter layout and sends selected values.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, pytest, React, TypeScript, Vite, Ant Design.

**Project constraints:** Work in root workspace `E:/小红书` on `master`. Do not modify XHS SDK/signature files. Do not commit unless the user explicitly asks; each task ends with `git diff --check` and targeted verification instead of a commit.

---

## File Structure

- Modify `backend/app/models/feishu.py`
  - Add `NoteAnalysisResult.search_attribute`.
- Create `backend/alembic/versions/20260624_add_note_analysis_search_attribute.py`
  - Add/drop the `search_attribute` column.
- Modify `backend/app/services/feishu_bitable_service.py`
  - Persist returned Feishu `搜索属性` into `search_attribute` without fabricating a value when Feishu clears it.
  - Include `search_attribute` in preanalysis state when available.
- Modify `backend/app/api/notes.py`
  - Add list-normalization helpers.
  - Add true multi-select OR filtering for analysis fields.
  - Add `GET /api/notes/filter-options` for dynamic options.
  - Serialize compatible frontend fields.
- Modify `frontend/src/types/index.ts`
  - Add `search_attribute` and alias fields to `NoteAnalysisResult`.
  - Add `SavedNoteFilterOptions` type.
- Modify `frontend/src/lib/api.ts`
  - Add multi-select filter params and `fetchSavedNoteFilterOptions()`.
- Modify `frontend/src/components/content-library/content-library-types.ts`
  - Change analysis filter state to arrays for multi-select fields.
  - Add dynamic filter options and loader contract.
- Modify `frontend/src/components/content-library/use-content-library.ts`
  - Manage dynamic filter options and new selected arrays.
- Modify `frontend/src/components/content-library/content-library-shell.tsx`
  - Split basic filters and Feishu analysis filters into separate cards.
  - Render five business dimensions as multi-select controls.
- Modify `frontend/src/pages/platforms/xhs/xhs-content-library-adapter.ts`
  - Remove hard-coded XHS business options.
  - Load dynamic options from the backend.
  - Refresh options after Feishu pull/push operations.
- Modify tests:
  - `tests/backend/test_feishu_integration.py`
  - `tests/backend/test_api.py`

---

### Task 1: Add backend tests for Feishu pull persistence and dynamic filter options

**Files:**
- Modify: `tests/backend/test_feishu_integration.py`
- Modify: `tests/backend/test_api.py`

- [ ] **Step 1: Add failing test for returned `搜索属性` persistence**

Append this test to `tests/backend/test_feishu_integration.py`:

```python
def test_pull_feishu_analysis_records_persists_search_attribute_and_clears_blank(tmp_path):
    SessionLocal = _override_database(tmp_path, "feishu-search-attribute.db")
    try:
        user_id = _create_user(SessionLocal)
        db = SessionLocal()
        try:
            note = Note(user_id=user_id, platform_account_id=1, platform="xhs", note_id="xhs-search", title="AI 搜索教程", content="强搜索选题", author_name="作者")
            db.add(note)
            db.commit()
            db.refresh(note)
            note_id = note.id
        finally:
            db.close()

        headers = _auth_headers(user_id)
        response = client.post(
            "/api/integrations/feishu/xhs-notes/pull",
            headers=headers,
            json={
                "dry_run": True,
                "records": [
                    {
                        "record_id": "rec_search_1",
                        "fields": {
                            "系统笔记ID": str(note_id),
                            "分析状态": "已完成",
                            "核心产品/服务": "AI 工具",
                            "内容类型": "教程",
                            "可复用模型": ["教程方法模型"],
                            "内容利用方式": ["正文结构参考"],
                            "搜索属性": "强搜索",
                        },
                    }
                ],
            },
        )

        assert response.status_code == 200
        assert response.json()["updated_count"] == 1
        db = SessionLocal()
        try:
            result = db.scalar(select(NoteAnalysisResult).where(NoteAnalysisResult.note_id == note_id))
            assert result is not None
            assert result.search_attribute == "强搜索"
        finally:
            db.close()

        clear_response = client.post(
            "/api/integrations/feishu/xhs-notes/pull",
            headers=headers,
            json={
                "dry_run": True,
                "records": [
                    {
                        "record_id": "rec_search_1",
                        "fields": {
                            "系统笔记ID": str(note_id),
                            "分析状态": "已完成",
                            "搜索属性": "",
                        },
                    }
                ],
            },
        )

        assert clear_response.status_code == 200
        db = SessionLocal()
        try:
            result = db.scalar(select(NoteAnalysisResult).where(NoteAnalysisResult.note_id == note_id))
            assert result is not None
            assert result.search_attribute is None
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)
```

- [ ] **Step 2: Add failing API test for multi-select OR, cross-field AND, and options**

Append this test to `tests/backend/test_api.py` near other content-library/Feishu tests:

```python
def test_xhs_notes_feishu_analysis_filters_are_dynamic_and_multi_select(tmp_path):
    db_dependency, access_token, account_id = _create_pc_account_with_cookie(tmp_path, "analysis-filter-owner")
    try:
        db = next(db_dependency())
        try:
            first = Note(user_id=1, platform_account_id=account_id, platform="xhs", note_id="filter-1", title="AI 教程", content="正文", author_name="作者A")
            second = Note(user_id=1, platform_account_id=account_id, platform="xhs", note_id="filter-2", title="知识管理测评", content="正文", author_name="作者B")
            third = Note(user_id=1, platform_account_id=account_id, platform="xhs", note_id="filter-3", title="AI 避坑", content="正文", author_name="作者C")
            db.add_all([first, second, third])
            db.flush()
            db.add_all([
                NoteAnalysisResult(
                    user_id=1,
                    note_id=first.id,
                    source="feishu",
                    analysis_status="已完成",
                    subject_object="AI 工具",
                    content_type="教程",
                    reusable_models=["教程方法模型", "问题驱动模型"],
                    reuse_value="正文结构参考",
                    search_attribute="强搜索",
                    push_status="synced",
                ),
                NoteAnalysisResult(
                    user_id=1,
                    note_id=second.id,
                    source="feishu",
                    analysis_status="已完成",
                    subject_object="知识管理",
                    content_type="测评",
                    reusable_models=["测评背书模型"],
                    reuse_value="选题参考",
                    search_attribute="弱搜索",
                    push_status="synced",
                ),
                NoteAnalysisResult(
                    user_id=1,
                    note_id=third.id,
                    source="feishu",
                    analysis_status="分析中",
                    subject_object="AI 工具",
                    content_type="避坑",
                    reusable_models=["问题驱动模型"],
                    reuse_value="废弃",
                    search_attribute=None,
                    push_status="synced",
                ),
            ])
            db.commit()
        finally:
            db.close()

        options_response = client.get(
            "/api/notes/filter-options?platform=xhs",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert options_response.status_code == 200
        options = options_response.json()
        assert {item["value"] for item in options["coreProductService"]} >= {"AI 工具", "知识管理"}
        assert {item["value"] for item in options["contentType"]} >= {"教程", "测评", "避坑"}
        assert {item["value"] for item in options["reusableModel"]} >= {"教程方法模型", "问题驱动模型", "测评背书模型"}
        assert {item["value"] for item in options["contentUsage"]} >= {"正文结构参考", "选题参考", "废弃"}
        assert {item["value"] for item in options["searchAttribute"]} >= {"强搜索", "弱搜索"}

        or_response = client.get(
            "/api/notes?platform=xhs&core_product_service=AI 工具,知识管理",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert or_response.status_code == 200
        assert {item["note_id"] for item in or_response.json()["items"]} == {"filter-1", "filter-2", "filter-3"}

        and_response = client.get(
            "/api/notes?platform=xhs&core_product_service=AI 工具,知识管理&content_type=教程",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert and_response.status_code == 200
        assert [item["note_id"] for item in and_response.json()["items"]] == ["filter-1"]

        model_response = client.get(
            "/api/notes?platform=xhs&reusable_model=问题驱动模型&search_attribute=强搜索",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert model_response.status_code == 200
        assert [item["note_id"] for item in model_response.json()["items"]] == ["filter-1"]
    finally:
        app.dependency_overrides.pop(get_db, None)
```

- [ ] **Step 3: Run tests and verify RED**

Run:

```bash
pytest tests/backend/test_feishu_integration.py::test_pull_feishu_analysis_records_persists_search_attribute_and_clears_blank tests/backend/test_api.py::test_xhs_notes_feishu_analysis_filters_are_dynamic_and_multi_select -q
```

Expected:

```text
FAILED ... AttributeError: 'NoteAnalysisResult' object has no attribute 'search_attribute'
```

or failure because `/api/notes/filter-options` does not exist yet. This is the correct RED state.

---

### Task 2: Persist Feishu `搜索属性` in the analysis result model

**Files:**
- Modify: `backend/app/models/feishu.py`
- Create: `backend/alembic/versions/20260624_add_note_analysis_search_attribute.py`
- Modify: `backend/app/services/feishu_bitable_service.py`
- Modify: `backend/app/api/notes.py`
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Add model field**

In `backend/app/models/feishu.py`, add the column after `reuse_value`:

```python
    search_attribute: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
```

The surrounding block becomes:

```python
    reusable_models: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    reuse_value: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    search_attribute: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    analysis_note: Mapped[str] = mapped_column(Text, default="")
```

- [ ] **Step 2: Add Alembic migration**

Create `backend/alembic/versions/20260624_add_note_analysis_search_attribute.py`:

```python
"""add note analysis search attribute

Revision ID: 20260624_analysis_search_attr
Revises: 20260623_feishu_collab
Create Date: 2026-06-24
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260624_analysis_search_attr"
down_revision: Union[str, Sequence[str], None] = "20260623_feishu_collab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("note_analysis_results", sa.Column("search_attribute", sa.String(length=64), nullable=True))
    op.create_index("ix_note_analysis_results_search_attribute", "note_analysis_results", ["search_attribute"])


def downgrade() -> None:
    op.drop_index("ix_note_analysis_results_search_attribute", table_name="note_analysis_results")
    op.drop_column("note_analysis_results", "search_attribute")
```

- [ ] **Step 3: Update Feishu pull persistence**

In `backend/app/services/feishu_bitable_service.py`, inside `pull_feishu_analysis_records()`, replace the current content usage/search area:

```python
        result.reusable_models = normalize_multi_select(_field_value(fields, "可复用模型"), REUSABLE_MODEL_OPTIONS, fallback=[])
        result.reuse_value = _as_text(_field_value(fields, "内容利用方式")) or None
        result.analysis_note = _as_text(_field_value(fields, "分析备注"))
```

with:

```python
        result.reusable_models = normalize_multi_select(_field_value(fields, "可复用模型"), REUSABLE_MODEL_OPTIONS, fallback=[])
        result.reuse_value = "、".join(normalize_multi_select(_field_value(fields, "内容利用方式"), REUSE_VALUE_OPTIONS, fallback=[])) or None
        raw_search_attribute = _as_text(_field_value(fields, "搜索属性"))
        result.search_attribute = normalize_search_attribute(raw_search_attribute, note) if raw_search_attribute else None
        result.analysis_note = _as_text(_field_value(fields, "分析备注"))
```

- [ ] **Step 4: Store preanalysis search attribute when pushing**

In `apply_preanalysis_to_result()`, after the `reuse_value` assignment block, add:

```python
    search_attribute = normalize_search_attribute(analysis.get("search_attribute"), None)
    if force_update or not result.search_attribute:
        result.search_attribute = search_attribute or None
```

If `normalize_search_attribute()` currently requires a `Note`, adjust its signature to accept `note: Note | None` and return `""` when both input and note are empty:

```python
def normalize_search_attribute(value: Any, note: Note | None = None) -> str:
    text = _as_text(value)
    if text in ["强搜索", "弱搜索", "泛流量"]:
        return text
    if text:
        if "强" in text:
            return "强搜索"
        if "弱" in text:
            return "弱搜索"
        if "泛" in text:
            return "泛流量"
    if note is None:
        return ""
    source = f"{note.title}\n{note.content}"
    if any(word in source for word in ["怎么", "如何", "教程", "避坑", "攻略", "步骤"]):
        return "强搜索"
    if any(word in source for word in ["体验", "测评", "对比", "推荐"]):
        return "弱搜索"
    return "泛流量"
```

Preserve any existing equivalent rules if the function already has more cases.

- [ ] **Step 5: Serialize search attribute and aliases**

In `backend/app/api/notes.py`, update `_serialize_analysis_result()` to include compatible fields:

```python
        "core_product_service": result.subject_object,
        "subject_object": result.subject_object,
        "content_type": result.content_type,
        "reusable_model": result.reusable_models or [],
        "reusable_models": result.reusable_models or [],
        "content_usage": result.reuse_value,
        "reuse_value": result.reuse_value,
        "search_attribute": result.search_attribute,
```

Keep existing fields like `core_points`, `target_audience`, and timestamps unchanged.

- [ ] **Step 6: Update frontend type**

In `frontend/src/types/index.ts`, update `NoteAnalysisResult` to include aliases:

```typescript
export type NoteAnalysisResult = {
  analysis_status?: string | null;
  core_product_service?: string | null;
  subject_object: string;
  content_type?: string | null;
  core_points: string;
  target_audience: string;
  title_hook: string;
  content_structure: string;
  reusable_model?: string[];
  reusable_models: string[];
  content_usage?: string | null;
  reuse_value?: string | null;
  search_attribute?: string | null;
  analysis_note: string;
  last_pushed_at?: string | null;
  last_pulled_at?: string | null;
};
```

- [ ] **Step 7: Run targeted RED/GREEN check**

Run:

```bash
pytest tests/backend/test_feishu_integration.py::test_pull_feishu_analysis_records_persists_search_attribute_and_clears_blank -q
```

Expected: PASS.

---

### Task 3: Add backend dynamic options and multi-select filtering

**Files:**
- Modify: `backend/app/api/notes.py`

- [ ] **Step 1: Add helper functions**

In `backend/app/api/notes.py`, after `_get_feishu_analysis_result()`, add:

```python
def _split_filter_values(value: Optional[str]) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in str(value).replace("；", ",").replace(";", ",").split(",") if item.strip()]


def _split_analysis_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).replace("；", ",").replace(";", ",").replace("\n", ",").split(",") if item.strip()]


def _has_any_text(actual: Any, selected: list[str]) -> bool:
    if not selected:
        return True
    actual_values = set(_split_analysis_values(actual))
    return any(item in actual_values for item in selected)


def _option_list(counter: dict[str, int]) -> list[dict[str, str]]:
    values = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    return [{"value": value, "label": value} for value, _count in values]


def _add_option(counter: dict[str, int], value: Any) -> None:
    for item in _split_analysis_values(value):
        counter[item] = counter.get(item, 0) + 1
```

- [ ] **Step 2: Extend `get_notes()` query parameters**

Update `get_notes()` parameters:

```python
    feishu_push_status: Optional[str] = None,
    analysis_status: Optional[str] = None,
    core_product_service: Optional[str] = None,
    content_type: Optional[str] = None,
    reusable_model: Optional[str] = None,
    content_usage: Optional[str] = None,
    search_attribute: Optional[str] = None,
    reuse_value: Optional[str] = None,
```

Keep `reuse_value` as backward-compatible alias.

- [ ] **Step 3: Replace `_matches_analysis_filters()` with OR/AND logic**

Inside `get_notes()`, before `_matches_analysis_filters`, normalize selected values:

```python
    selected_analysis_status = _split_filter_values(analysis_status)
    selected_core_product_service = _split_filter_values(core_product_service)
    selected_content_type = _split_filter_values(content_type)
    selected_reusable_model = _split_filter_values(reusable_model)
    selected_content_usage = _split_filter_values(content_usage or reuse_value)
    selected_search_attribute = _split_filter_values(search_attribute)
```

Replace the function body with:

```python
    def _matches_analysis_filters(note: Note) -> bool:
        result = _get_feishu_analysis_result(db, note.id)
        if feishu_push_status and (result.push_status if result else "not_synced") != feishu_push_status:
            return False
        if result is None:
            return False
        if not _has_any_text(result.analysis_status, selected_analysis_status):
            return False
        if not _has_any_text(result.subject_object, selected_core_product_service):
            return False
        if not _has_any_text(result.content_type, selected_content_type):
            return False
        if not _has_any_text(result.reusable_models or [], selected_reusable_model):
            return False
        if not _has_any_text(result.reuse_value, selected_content_usage):
            return False
        if not _has_any_text(result.search_attribute, selected_search_attribute):
            return False
        return True
```

Update the condition that applies filtering:

```python
    if any([
        feishu_push_status,
        selected_analysis_status,
        selected_core_product_service,
        selected_content_type,
        selected_reusable_model,
        selected_content_usage,
        selected_search_attribute,
    ]):
        notes = [note for note in notes if _matches_analysis_filters(note)]
```

- [ ] **Step 4: Add `GET /notes/filter-options` before `GET /notes/{note_id}`**

Add this route after `get_notes()` and before `@router.post("/batch-create-drafts")` or before `@router.get("/{note_id}")`:

```python
@router.get("/filter-options")
def get_note_filter_options(
    platform: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note_statement = select(Note.id).where(Note.user_id == current_user.id)
    if platform:
        note_statement = note_statement.where(Note.platform == platform)
    note_ids = list(db.scalars(note_statement).all())

    counters: dict[str, dict[str, int]] = {
        "analysisStatus": {},
        "coreProductService": {},
        "contentType": {},
        "reusableModel": {},
        "contentUsage": {},
        "searchAttribute": {},
    }
    if note_ids:
        results = db.scalars(
            select(NoteAnalysisResult).where(
                NoteAnalysisResult.user_id == current_user.id,
                NoteAnalysisResult.source == "feishu",
                NoteAnalysisResult.note_id.in_(note_ids),
            )
        ).all()
        for result in results:
            _add_option(counters["analysisStatus"], result.analysis_status)
            _add_option(counters["coreProductService"], result.subject_object)
            _add_option(counters["contentType"], result.content_type)
            _add_option(counters["reusableModel"], result.reusable_models or [])
            _add_option(counters["contentUsage"], result.reuse_value)
            _add_option(counters["searchAttribute"], result.search_attribute)

    return {key: _option_list(counter) for key, counter in counters.items()}
```

- [ ] **Step 5: Run backend filter tests**

Run:

```bash
pytest tests/backend/test_api.py::test_xhs_notes_feishu_analysis_filters_are_dynamic_and_multi_select -q
```

Expected: PASS.

---

### Task 4: Add frontend API/types contract for dynamic multi-select filters

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/components/content-library/content-library-types.ts`

- [ ] **Step 1: Update `SavedNoteFilters` and add options type**

In `frontend/src/lib/api.ts`, update `SavedNoteFilters`:

```typescript
export type SavedNoteFilters = {
  platform?: string;
  q?: string;
  tag_id?: number;
  has_assets?: boolean;
  has_comments?: boolean;
  feishu_push_status?: string;
  analysis_status?: string | string[];
  core_product_service?: string[];
  content_type?: string | string[];
  reusable_model?: string | string[];
  content_usage?: string[];
  search_attribute?: string[];
  reuse_value?: string | string[];
  sort_by?: "latest" | "engagement" | "likes" | "comments" | "collects";
  page?: number;
  page_size?: number;
};

export type SavedNoteFilterOptions = {
  analysisStatus: Array<{ value: string; label: string }>;
  coreProductService: Array<{ value: string; label: string }>;
  contentType: Array<{ value: string; label: string }>;
  reusableModel: Array<{ value: string; label: string }>;
  contentUsage: Array<{ value: string; label: string }>;
  searchAttribute: Array<{ value: string; label: string }>;
};
```

- [ ] **Step 2: Add array serializer**

In `frontend/src/lib/api.ts`, before `fetchSavedNotes()`, add:

```typescript
function csvParam(value?: string | string[]): string | undefined {
  if (Array.isArray(value)) return value.length ? value.join(",") : undefined;
  return value || undefined;
}
```

- [ ] **Step 3: Serialize multi-select filters in `fetchSavedNotes()`**

Replace the analysis params block with:

```typescript
          feishu_push_status: platformOrFilters.feishu_push_status,
          analysis_status: csvParam(platformOrFilters.analysis_status),
          core_product_service: csvParam(platformOrFilters.core_product_service),
          content_type: csvParam(platformOrFilters.content_type),
          reusable_model: csvParam(platformOrFilters.reusable_model),
          content_usage: csvParam(platformOrFilters.content_usage ?? platformOrFilters.reuse_value),
          search_attribute: csvParam(platformOrFilters.search_attribute),
```

- [ ] **Step 4: Add options API function**

After `fetchSavedNotes()`, add:

```typescript
export async function fetchSavedNoteFilterOptions(platform = "xhs"): Promise<SavedNoteFilterOptions> {
  const response = await http.get<SavedNoteFilterOptions>("/notes/filter-options", { params: { platform } });
  return response.data;
}
```

- [ ] **Step 5: Update content-library types**

In `frontend/src/components/content-library/content-library-types.ts`, update filters/options/controller shape:

```typescript
export type ContentLibraryFilters = {
  q?: string;
  tag_id?: number;
  has_assets?: boolean;
  has_comments?: boolean;
  feishu_push_status?: string;
  analysis_status?: string | string[];
  core_product_service?: string[];
  content_type?: string[];
  reusable_model?: string[];
  content_usage?: string[];
  search_attribute?: string[];
  sort_by?: ContentLibrarySortBy;
  page?: number;
  page_size?: number;
};
```

Update `ContentLibraryFilterOptions`:

```typescript
export type ContentLibraryFilterOptions = {
  analysisStatus?: ContentLibrarySelectOption[];
  coreProductService?: ContentLibrarySelectOption[];
  contentType?: ContentLibrarySelectOption[];
  reusableModel?: ContentLibrarySelectOption[];
  contentUsage?: ContentLibrarySelectOption[];
  searchAttribute?: ContentLibrarySelectOption[];
};
```

Add to `ContentLibraryAdapter`:

```typescript
  loadFilterOptions?(): Promise<ContentLibraryFilterOptions>;
```

Update controller fields and setters:

```typescript
  filterOptions: ContentLibraryFilterOptions;
  coreProductServiceFilter: string[];
  contentTypeFilter: string[];
  reusableModelFilter: string[];
  contentUsageFilter: string[];
  searchAttributeFilter: string[];
  setCoreProductServiceFilter(value: string[]): void;
  setContentTypeFilter(value: string[]): void;
  setReusableModelFilter(value: string[]): void;
  setContentUsageFilter(value: string[]): void;
  setSearchAttributeFilter(value: string[]): void;
  refreshFilterOptions(): Promise<void>;
```

Remove or keep legacy `reuseValueFilter` only if TypeScript call sites still need it. New UI should use `contentUsageFilter`.

- [ ] **Step 6: Run frontend typecheck to see expected failures**

Run:

```bash
cd frontend && npm run build
```

Expected: TypeScript failures in `use-content-library.ts`, `content-library-shell.tsx`, and `xhs-content-library-adapter.ts` because the new contract is not implemented yet.

---

### Task 5: Implement frontend controller state and dynamic option loading

**Files:**
- Modify: `frontend/src/components/content-library/use-content-library.ts`

- [ ] **Step 1: Replace single-value analysis states with arrays**

In `useContentLibrary()`, replace:

```typescript
  const [contentTypeFilter, setContentTypeFilter] = useState("");
  const [reuseValueFilter, setReuseValueFilter] = useState("");
  const [reusableModelFilter, setReusableModelFilter] = useState("");
```

with:

```typescript
  const [filterOptions, setFilterOptions] = useState(adapter.filterOptions ?? {});
  const [coreProductServiceFilter, setCoreProductServiceFilter] = useState<string[]>([]);
  const [contentTypeFilter, setContentTypeFilter] = useState<string[]>([]);
  const [reusableModelFilter, setReusableModelFilter] = useState<string[]>([]);
  const [contentUsageFilter, setContentUsageFilter] = useState<string[]>([]);
  const [searchAttributeFilter, setSearchAttributeFilter] = useState<string[]>([]);
```

Keep `feishuPushStatusFilter` and `analysisStatusFilter` as strings.

- [ ] **Step 2: Add `refreshFilterOptions()`**

After `refreshTags`, add:

```typescript
  const refreshFilterOptions = useCallback(async () => {
    if (!adapter.loadFilterOptions) {
      setFilterOptions(adapter.filterOptions ?? {});
      return;
    }
    try {
      const result = await adapter.loadFilterOptions();
      setFilterOptions(result);
    } catch {
      setFilterOptions(adapter.filterOptions ?? {});
    }
  }, [adapter]);
```

Update the initial `useEffect()`:

```typescript
  useEffect(() => {
    void refreshItems();
    void refreshTags();
    void refreshFilterOptions();
  }, []);
```

- [ ] **Step 3: Send array filters in `refreshItems()`**

In `refreshItems()`, replace the old analysis filter fields with:

```typescript
      analysis_status: analysisStatusFilter || undefined,
      core_product_service: coreProductServiceFilter.length ? coreProductServiceFilter : undefined,
      content_type: contentTypeFilter.length ? contentTypeFilter : undefined,
      reusable_model: reusableModelFilter.length ? reusableModelFilter : undefined,
      content_usage: contentUsageFilter.length ? contentUsageFilter : undefined,
      search_attribute: searchAttributeFilter.length ? searchAttributeFilter : undefined,
```

Update the dependency list to include `coreProductServiceFilter`, `contentUsageFilter`, and `searchAttributeFilter`, and remove `reuseValueFilter`.

- [ ] **Step 4: Clear all new filters**

In `clearFilters()`, replace old analysis clears with:

```typescript
    setAnalysisStatusFilter("");
    setCoreProductServiceFilter([]);
    setContentTypeFilter([]);
    setReusableModelFilter([]);
    setContentUsageFilter([]);
    setSearchAttributeFilter([]);
```

Update `refreshItems()` override:

```typescript
    void refreshItems({
      q: undefined,
      tag_id: undefined,
      has_assets: undefined,
      has_comments: undefined,
      feishu_push_status: undefined,
      analysis_status: undefined,
      core_product_service: undefined,
      content_type: undefined,
      reusable_model: undefined,
      content_usage: undefined,
      search_attribute: undefined,
      page: 1,
    });
```

- [ ] **Step 5: Return new controller fields**

In the returned controller object, include:

```typescript
    filterOptions,
    coreProductServiceFilter,
    contentTypeFilter,
    reusableModelFilter,
    contentUsageFilter,
    searchAttributeFilter,
    setCoreProductServiceFilter,
    setContentTypeFilter,
    setReusableModelFilter,
    setContentUsageFilter,
    setSearchAttributeFilter,
    refreshFilterOptions,
```

Remove returned `reuseValueFilter` and `setReuseValueFilter` if there are no remaining call sites.

- [ ] **Step 6: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: remaining TypeScript failures only in shell/adapter call sites, not in the hook contract itself.

---

### Task 6: Split filter UI into Basic Filters and Feishu Analysis Filters

**Files:**
- Modify: `frontend/src/components/content-library/content-library-shell.tsx`

- [ ] **Step 1: Replace static default options**

Update `DEFAULT_FILTER_OPTIONS` to avoid hard-coded business dimensions except analysis status fallback:

```typescript
const DEFAULT_FILTER_OPTIONS = {
  analysisStatus: ["待分析", "分析中", "已完成", "废弃"].map((value) => ({ value, label: value })),
  coreProductService: [],
  contentType: [],
  reusableModel: [],
  contentUsage: [],
  searchAttribute: [],
};
```

- [ ] **Step 2: Read options from controller first**

Inside `ContentLibraryShell`, replace `filterOptions` construction with:

```typescript
  const filterOptions = {
    analysisStatus: controller.filterOptions.analysisStatus ?? adapter.filterOptions?.analysisStatus ?? DEFAULT_FILTER_OPTIONS.analysisStatus,
    coreProductService: controller.filterOptions.coreProductService ?? adapter.filterOptions?.coreProductService ?? DEFAULT_FILTER_OPTIONS.coreProductService,
    contentType: controller.filterOptions.contentType ?? adapter.filterOptions?.contentType ?? DEFAULT_FILTER_OPTIONS.contentType,
    reusableModel: controller.filterOptions.reusableModel ?? adapter.filterOptions?.reusableModel ?? DEFAULT_FILTER_OPTIONS.reusableModel,
    contentUsage: controller.filterOptions.contentUsage ?? adapter.filterOptions?.contentUsage ?? DEFAULT_FILTER_OPTIONS.contentUsage,
    searchAttribute: controller.filterOptions.searchAttribute ?? adapter.filterOptions?.searchAttribute ?? DEFAULT_FILTER_OPTIONS.searchAttribute,
  };
```

- [ ] **Step 3: Add helper for multi-select controls**

Before `return`, add:

```typescript
  const renderMultiSelect = (
    placeholder: string,
    value: string[],
    onChange: (value: string[]) => void,
    options: Array<{ value: string; label: string }> = [],
  ) => (
    <Select
      mode="multiple"
      allowClear
      maxTagCount="responsive"
      placeholder={options.length ? placeholder : `${placeholder}（暂无可选项）`}
      value={value}
      onChange={onChange}
      style={{ width: "100%" }}
      options={options}
    />
  );
```

- [ ] **Step 4: Keep first card for basic filters only**

In the first filter `Card`, keep:

```text
Input, tag select, sort select, 有素材, 有评论, Segmented, 重置, 筛选
```

Remove the Feishu status/analysis/content/reuse/model controls from this first card.

- [ ] **Step 5: Add second Feishu analysis card**

Immediately after the first filter `Card`, add:

```tsx
      {adapter.capabilities.canFilterFeishuAnalysis ? (
        <Card size="small" title="飞书分析筛选" style={{ marginBottom: 16 }}>
          <Row gutter={[12, 12]} align="middle">
            <Col xs={24} sm={12} md={6} lg={4}>
              <Select
                allowClear
                placeholder="飞书同步状态"
                value={controller.feishuPushStatusFilter || undefined}
                onChange={(value) => controller.setFeishuPushStatusFilter(value ?? "")}
                style={{ width: "100%" }}
                options={[
                  { value: "not_synced", label: "未同步" },
                  { value: "dry_run", label: "Dry-run" },
                  { value: "synced", label: "已同步" },
                  { value: "failed", label: "同步失败" },
                ]}
              />
            </Col>
            <Col xs={24} sm={12} md={6} lg={4}>
              <Select
                allowClear
                placeholder="分析状态"
                value={controller.analysisStatusFilter || undefined}
                onChange={(value) => controller.setAnalysisStatusFilter(value ?? "")}
                style={{ width: "100%" }}
                options={filterOptions.analysisStatus}
              />
            </Col>
            <Col xs={24} sm={12} md={6} lg={5}>{renderMultiSelect("核心产品/服务", controller.coreProductServiceFilter, controller.setCoreProductServiceFilter, filterOptions.coreProductService)}</Col>
            <Col xs={24} sm={12} md={6} lg={4}>{renderMultiSelect("内容类型", controller.contentTypeFilter, controller.setContentTypeFilter, filterOptions.contentType)}</Col>
            <Col xs={24} sm={12} md={6} lg={5}>{renderMultiSelect("可复用模型", controller.reusableModelFilter, controller.setReusableModelFilter, filterOptions.reusableModel)}</Col>
            <Col xs={24} sm={12} md={6} lg={5}>{renderMultiSelect("内容利用方式", controller.contentUsageFilter, controller.setContentUsageFilter, filterOptions.contentUsage)}</Col>
            <Col xs={24} sm={12} md={6} lg={4}>{renderMultiSelect("搜索属性", controller.searchAttributeFilter, controller.setSearchAttributeFilter, filterOptions.searchAttribute)}</Col>
          </Row>
        </Card>
      ) : null}
```

- [ ] **Step 6: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: shell-related TypeScript errors are resolved; adapter errors may remain until Task 7.

---

### Task 7: Wire XHS adapter to backend dynamic options

**Files:**
- Modify: `frontend/src/pages/platforms/xhs/xhs-content-library-adapter.ts`

- [ ] **Step 1: Import options API**

Add `fetchSavedNoteFilterOptions` to the existing API imports from `../../../lib/api`.

- [ ] **Step 2: Remove hard-coded XHS business filter options**

In `createXhsContentLibraryAdapter()`, replace the current `filterOptions` block with:

```typescript
    filterOptions: {
      analysisStatus: ["待分析", "分析中", "已完成", "废弃"].map((value) => ({ value, label: value })),
      coreProductService: [],
      contentType: [],
      reusableModel: [],
      contentUsage: [],
      searchAttribute: [],
    },
    loadFilterOptions: () => fetchSavedNoteFilterOptions("xhs"),
```

- [ ] **Step 3: Refresh options after Feishu pull and bulk sync**

After existing `await context.controller.refreshItems();` calls in Feishu actions, add:

```typescript
      await context.controller.refreshFilterOptions();
```

Do this in:

- `syncSelectedToFeishu()`
- `syncAllToFeishu()`
- `pullSelectedFromFeishu()`

- [ ] **Step 4: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

---

### Task 8: Update source-inspection tests for the new UI contract

**Files:**
- Modify: `tests/backend/test_api.py`

- [ ] **Step 1: Update `test_xhs_content_library_exposes_feishu_filters_and_actions()` expectations**

Replace assertions for old labels with new labels:

```python
    assert "飞书分析筛选" in shell_source
    assert "飞书同步状态" in shell_source
    assert "分析状态" in shell_source
    assert "核心产品/服务" in shell_source
    assert "内容类型" in shell_source
    assert "可复用模型" in shell_source
    assert "内容利用方式" in shell_source
    assert "搜索属性" in shell_source
    assert "mode=\"multiple\"" in shell_source
```

Keep the action assertions:

```python
    assert "canFilterFeishuAnalysis" in types_source
    assert "pushXhsNotesToFeishu" in adapter_source
    assert "pullXhsNotesFromFeishu" in adapter_source
    assert "同步到飞书" in adapter_source
    assert "从飞书回传" in adapter_source
```

- [ ] **Step 2: Update `test_content_library_filter_options_are_platform_adapter_owned()`**

Change expectations so XHS no longer owns hard-coded business options:

```python
    assert "loadFilterOptions" in types_source
    assert "controller.filterOptions" in shell_source
    assert "fetchSavedNoteFilterOptions" in xhs_adapter_source
    assert "核心产品/服务" in shell_source
    assert "搜索属性" in shell_source
    assert "观点评论" in wechat_adapter_source
    assert "案例拆解" in wechat_adapter_source
```

Remove the assertions that require `场景种草模型` or `测评背书模型` in the XHS adapter or shell, because those should now come from backend data.

- [ ] **Step 3: Run updated inspection tests**

Run:

```bash
pytest tests/backend/test_api.py::test_xhs_content_library_exposes_feishu_filters_and_actions tests/backend/test_api.py::test_content_library_filter_options_are_platform_adapter_owned -q
```

Expected: PASS.

---

### Task 9: Full targeted verification

**Files:**
- No code changes unless verification finds a real issue.

- [ ] **Step 1: Run Feishu/backend targeted tests**

Run:

```bash
pytest tests/backend/test_feishu_integration.py tests/backend/test_api.py::test_xhs_notes_feishu_analysis_filters_are_dynamic_and_multi_select tests/backend/test_api.py::test_xhs_content_library_exposes_feishu_filters_and_actions tests/backend/test_api.py::test_content_library_filter_options_are_platform_adapter_owned -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 3: Check diff hygiene**

Run:

```bash
git diff --check
git status --short
```

Expected:

```text
git diff --check produces no output.
git status shows only intended files changed plus existing unrelated workspace changes.
```

- [ ] **Step 4: Manual acceptance path**

Use the running app or start it through the project’s normal command if needed, then verify:

1. Open XHS content library.
2. Confirm basic filters and “飞书分析筛选” are separate cards.
3. Confirm the five business fields are visible:
   - 核心产品/服务
   - 内容类型
   - 可复用模型
   - 内容利用方式
   - 搜索属性
4. Pull Feishu analysis for selected notes.
5. Confirm options appear in the relevant controls.
6. Select two values in one field and confirm OR behavior.
7. Select another field and confirm cross-field AND behavior.
8. Click reset and confirm all filters clear.

---

## Self-Review

- Spec coverage: The plan covers dynamic options, five business fields, multi-select OR within fields, AND across fields, grouped UI, backend-owned filtering, reset behavior, and verification.
- Placeholder scan: No `TBD`, `TODO`, `implement later`, or vague “add appropriate handling” steps remain.
- Type consistency: Backend wire names use `core_product_service`, `content_type`, `reusable_model`, `content_usage`, `search_attribute`; frontend option keys use `coreProductService`, `contentType`, `reusableModel`, `contentUsage`, `searchAttribute`.
- Scope check: This stays inside the Feishu analysis filter loop and does not introduce product management, AI classification, SDK edits, or publishing behavior.

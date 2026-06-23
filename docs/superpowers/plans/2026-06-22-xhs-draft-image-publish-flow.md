# XHS 草稿-图片工坊-发布链路优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a smooth XHS production path where drafts have internal names, AI-generated copy is normalized, drafts can enter Image Studio with context and reference images, and generated image results can be sent to Publish Center.

**Architecture:** Add a backend XHS content normalizer and `draft_name` persistence, then wire frontend draft state through Draft Workbench, Image Studio, and Publish Center using a lightweight sessionStorage context. Reuse the existing image-to-image workflow and publish job/assets APIs instead of introducing a new pipeline engine or image model integration.

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy, Alembic, pytest, React, TypeScript, Vite, Ant Design, react-router-dom.

---

## Current Constraints and Safety Notes

- Work in `e:\小红书` on branch `master` unless the user explicitly asks for a worktree.
- Current workspace already has unrelated uncommitted changes. Keep edits surgical and do not overwrite unrelated changes.
- Do not modify `apis/`, `xhs_utils/`, or `static/` because XHS SDK/signature layers are fragile and not part of this feature.
- Do not execute real XHS publishing during verification. Only create pending publish jobs and inspect local UI/API state.
- Project rules say commits require explicit user approval. This plan uses checkpoint steps instead of `git commit` commands.

## File Structure and Responsibilities

### Backend

- Create `backend/app/services/xhs_content_normalizer.py`
  - Pure functions for normalizing XHS generated title/body/tags.
  - No database dependency.
- Modify `backend/app/models/ai.py`
  - Add `AiDraft.draft_name` SQLAlchemy column.
- Create `backend/alembic/versions/20260622_add_draft_name_to_ai_drafts.py`
  - Add/drop `ai_drafts.draft_name`.
- Modify `backend/app/api/drafts.py`
  - Accept, persist, serialize, duplicate, normalize, and publish draft content.
- Modify `backend/app/api/ai.py`
  - Normalize AI rewrite output before saving draft.
- Modify `backend/app/services/scheduler_service.py`
  - Normalize automatic operation generated draft content before creating publish jobs.
- Modify `backend/app/services/xhs_analysis_center_service.py`
  - Normalize analysis-generated XHS drafts before saving them.
- Modify `backend/app/api/notes.py` and `backend/app/api/platforms/xhs/analytics.py`
  - Include `draft_name` in draft serializers used by note/content-library flows.

### Frontend

- Modify `frontend/src/types/index.ts`
  - Add `draft_name` to `Draft`, create/update payloads, and add Image Studio context types.
- Modify `frontend/src/lib/api.ts`
  - Allow draft create/update payloads to include `draft_name`.
  - Reuse existing publish asset API for Image Studio → Publish Center handoff.
- Modify `frontend/src/components/draft-workbench/draft-workbench-types.ts`
  - Add `draftName` field to draft patches and controller.
- Modify `frontend/src/components/draft-workbench/use-draft-workbench.ts`
  - Track `draftName` state and save it.
- Modify `frontend/src/components/draft-workbench/draft-workbench-shell.tsx`
  - Render internal draft name and publish title separately.
  - Show `draft_name || title || 未命名草稿` in the list.
- Modify `frontend/src/pages/platforms/xhs/xhs-draft-workbench-adapter.ts`
  - Pass `draft_name` through update calls and improve list subtitles.
- Modify `frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx`
  - Add “送入图片工坊”.
  - Save current draft before navigation.
  - Build Image Studio draft context from draft assets and source-note images.
- Create `frontend/src/pages/platforms/xhs/xhs-image-studio-context.ts`
  - Constants and helpers for sessionStorage draft context.
- Modify `frontend/src/pages/platforms/xhs/image-studio-page.tsx`
  - Read context, show “来自草稿” card, preload reference images, prefill prompt, and send generated image to Publish Center.
- Modify `frontend/src/pages/platforms/xhs/publish-page.tsx`
  - Honor `?jobId=` so Image Studio can open the newly created publish job.

### Tests

- Create `tests/backend/test_xhs_content_normalizer.py`
  - Unit tests for title duplication, Markdown cleanup, prefix cleanup, and tag dedupe.
- Modify `tests/backend/test_drafts.py`
  - Cover `draft_name` create/update/duplicate/serialize.
  - Cover send-to-publish normalized title/body and draft tags.
- Modify `tests/backend/test_api.py`
  - Update AI rewrite expectations if existing tests assert raw rewritten body.

---

## Task 1: Backend XHS Content Normalizer

**Files:**
- Create: `backend/app/services/xhs_content_normalizer.py`
- Create: `tests/backend/test_xhs_content_normalizer.py`

- [ ] **Step 1: Write failing normalizer tests**

Create `tests/backend/test_xhs_content_normalizer.py`:

```python
from backend.app.services.xhs_content_normalizer import normalize_xhs_generated_content


def test_removes_repeated_title_from_body_start():
    result = normalize_xhs_generated_content(
        title="SaaS 工具怎么选？",
        body="SaaS 工具怎么选？\n\n正文第一段...",
        tags=[],
    )

    assert result.title == "SaaS 工具怎么选？"
    assert result.body == "正文第一段..."
    assert "removed_repeated_title" in result.warnings


def test_removes_markdown_title_and_bold_symbols():
    result = normalize_xhs_generated_content(
        title="浴缸怎么选",
        body="# 浴缸怎么选\n\n**重点**\n- 尺寸\n* 材质",
        tags=[],
    )

    assert result.body == "重点\n尺寸\n材质"
    assert "#" not in result.body
    assert "**" not in result.body


def test_removes_introductory_content_prefixes():
    result = normalize_xhs_generated_content(
        title="标题",
        body="以下是适合小红书发布的内容：\n正文：\n第一段内容",
        tags=[],
    )

    assert result.body == "第一段内容"


def test_deduplicates_tags_without_fabricating_new_tags():
    result = normalize_xhs_generated_content(
        title="标题",
        body="正文",
        tags=[{"name": "浴缸"}, {"id": "1", "name": "浴缸"}, {"name": "装修"}, {"name": ""}],
    )

    assert result.tags == [{"name": "浴缸"}, {"name": "装修"}]
```

- [ ] **Step 2: Run normalizer tests to verify failure**

Run:

```bash
pytest tests/backend/test_xhs_content_normalizer.py -q
```

Expected: FAIL because `backend.app.services.xhs_content_normalizer` does not exist.

- [ ] **Step 3: Implement the normalizer**

Create `backend/app/services/xhs_content_normalizer.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any


@dataclass(frozen=True)
class NormalizedContent:
    title: str
    body: str
    tags: list[dict[str, Any]]
    warnings: list[str] = field(default_factory=list)


_PREFIX_PATTERNS = [
    re.compile(r"^\s*(正文|内容|小红书文案)\s*[:：]\s*"),
    re.compile(r"^\s*以下是(?:适合)?小红书发布的内容\s*[:：]?\s*"),
]


def _plain_compare(value: str) -> str:
    value = value.strip()
    value = re.sub(r"^[#\s]+", "", value)
    value = re.sub(r"^标题\s*[:：]\s*", "", value)
    value = value.strip("《》\"'“”‘’ ")
    value = re.sub(r"\s+", "", value)
    return value.lower()


def _strip_markdown_line(line: str) -> str:
    line = re.sub(r"^\s{0,3}#{1,6}\s*", "", line)
    line = re.sub(r"^\s*[-*]\s+", "", line)
    line = re.sub(r"\*\*(.*?)\*\*", r"\1", line)
    line = re.sub(r"__(.*?)__", r"\1", line)
    return line.strip()


def _strip_prefixes(lines: list[str], warnings: list[str]) -> list[str]:
    changed = True
    while lines and changed:
        changed = False
        first = lines[0]
        for pattern in _PREFIX_PATTERNS:
            next_first = pattern.sub("", first).strip()
            if next_first != first.strip():
                warnings.append("removed_intro_prefix")
                changed = True
                if next_first:
                    lines[0] = next_first
                else:
                    lines = lines[1:]
                break
    return lines


def _normalize_body(title: str, body: str, warnings: list[str]) -> str:
    raw_lines = [line.rstrip() for line in body.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    lines = [_strip_markdown_line(line) for line in raw_lines]
    while lines and not lines[0].strip():
        lines.pop(0)
    lines = _strip_prefixes(lines, warnings)
    title_key = _plain_compare(title)
    if lines and title_key and _plain_compare(lines[0]) == title_key:
        lines.pop(0)
        warnings.append("removed_repeated_title")
    lines = _strip_prefixes(lines, warnings)
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    collapsed: list[str] = []
    previous_blank = False
    for line in lines:
        is_blank = not line.strip()
        if is_blank and previous_blank:
            continue
        collapsed.append(line.strip() if not is_blank else "")
        previous_blank = is_blank
    return "\n".join(collapsed).strip()


def _normalize_tags(tags: list[Any] | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in tags or []:
        if isinstance(item, str):
            name = item.strip().lstrip("#")
            tag: dict[str, Any] = {"name": name}
        elif isinstance(item, dict):
            name = str(item.get("name", "")).strip().lstrip("#")
            tag = {key: value for key, value in item.items() if key in {"id", "name"}}
            tag["name"] = name
        else:
            continue
        if not name or name in seen:
            continue
        seen.add(name)
        normalized.append(tag)
    return normalized


def normalize_xhs_generated_content(title: str, body: str, tags: list[Any] | None) -> NormalizedContent:
    warnings: list[str] = []
    normalized_title = _strip_markdown_line(str(title or "")).strip()
    normalized_body = _normalize_body(normalized_title, str(body or ""), warnings)
    normalized_tags = _normalize_tags(tags)
    return NormalizedContent(
        title=normalized_title,
        body=normalized_body,
        tags=normalized_tags,
        warnings=list(dict.fromkeys(warnings)),
    )
```

- [ ] **Step 4: Run normalizer tests to verify pass**

Run:

```bash
pytest tests/backend/test_xhs_content_normalizer.py -q
```

Expected: PASS.

- [ ] **Step 5: Checkpoint**

Do not commit unless the user explicitly asks. Record changed files for final summary.

---

## Task 2: Persist and Serialize `draft_name`

**Files:**
- Modify: `backend/app/models/ai.py`
- Create: `backend/alembic/versions/20260622_add_draft_name_to_ai_drafts.py`
- Modify: `backend/app/api/drafts.py`
- Modify: `backend/app/api/notes.py`
- Modify: `backend/app/api/platforms/xhs/analytics.py`
- Modify: `backend/app/services/wechat_official_draft_service.py`
- Modify: `tests/backend/test_drafts.py`

- [ ] **Step 1: Add failing draft_name API tests**

Append to `tests/backend/test_drafts.py`:

```python

def test_create_update_and_list_draft_uses_internal_draft_name(tmp_path):
    SessionLocal = override_database(tmp_path)
    try:
        db = SessionLocal()
        try:
            owner = create_user(db, "draft-name-owner")
            headers = auth_headers(owner)
            db.commit()
        finally:
            db.close()

        create_response = client.post(
            "/api/drafts",
            headers=headers,
            json={
                "platform": "xhs",
                "draft_name": "浴缸案例图替换 - A版",
                "title": "卫生间浴缸怎么选？",
                "body": "正文",
            },
        )
        assert create_response.status_code == 200
        created = create_response.json()
        assert created["draft_name"] == "浴缸案例图替换 - A版"
        assert created["title"] == "卫生间浴缸怎么选？"

        update_response = client.patch(
            f"/api/drafts/{created['id']}",
            headers=headers,
            json={"draft_name": "浴缸案例图替换 - B版"},
        )
        assert update_response.status_code == 200
        assert update_response.json()["draft_name"] == "浴缸案例图替换 - B版"
        assert update_response.json()["title"] == "卫生间浴缸怎么选？"

        list_response = client.get("/api/drafts", headers=headers, params={"platform": "xhs"})
        assert list_response.status_code == 200
        assert list_response.json()["items"][0]["draft_name"] == "浴缸案例图替换 - B版"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_duplicate_draft_copies_internal_name_with_copy_suffix(tmp_path):
    SessionLocal = override_database(tmp_path)
    try:
        db = SessionLocal()
        try:
            owner = create_user(db, "draft-name-duplicate-owner")
            original = create_original_draft_with_assets(db, owner)
            original.draft_name = "浴缸案例图替换"
            db.commit()
            original_id = original.id
            headers = auth_headers(owner)
        finally:
            db.close()

        response = client.post(f"/api/drafts/{original_id}/duplicate", headers=headers)

        assert response.status_code == 200
        payload = response.json()
        assert payload["draft_name"] == "浴缸案例图替换 副本"
        assert payload["title"] == "原始草稿 - 副本"
    finally:
        app.dependency_overrides.pop(get_db, None)
```

- [ ] **Step 2: Run draft tests to verify failure**

Run:

```bash
pytest tests/backend/test_drafts.py -q
```

Expected: FAIL because `draft_name` is not on the model/API response.

- [ ] **Step 3: Add model column**

Modify `backend/app/models/ai.py` inside `AiDraft`:

```python
class AiDraft(Base):
    __tablename__ = "ai_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    platform: Mapped[str] = mapped_column(String(32), index=True)
    draft_name: Mapped[str] = mapped_column(String(256), default="")
    title: Mapped[str] = mapped_column(String(256), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    source_note_id: Mapped[Optional[int]] = mapped_column(ForeignKey("notes.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now)
```

- [ ] **Step 4: Add Alembic migration**

Create `backend/alembic/versions/20260622_add_draft_name_to_ai_drafts.py`:

```python
"""add draft_name to ai_drafts

Revision ID: 20260622draftname
Revises: 20260618woclt
Create Date: 2026-06-22 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260622draftname"
down_revision: Union[str, Sequence[str], None] = "20260618woclt"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("ai_drafts", schema=None) as batch_op:
        batch_op.add_column(sa.Column("draft_name", sa.String(length=256), server_default="", nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("ai_drafts", schema=None) as batch_op:
        batch_op.drop_column("draft_name")
```

- [ ] **Step 5: Extend draft API request models and serializer**

Modify `backend/app/api/drafts.py` request models:

```python
class DraftCreateRequest(BaseModel):
    platform: str = Field(pattern="^xhs$")
    source_note_id: Optional[int] = None
    draft_name: str = Field(default="", max_length=256)
    title: str = ""
    body: str = ""
    intent: str = Field(default="publish", max_length=32)


class DraftUpdateRequest(BaseModel):
    draft_name: Optional[str] = Field(default=None, max_length=256)
    title: Optional[str] = None
    body: Optional[str] = None
    tags: Optional[list[dict]] = None
```

Modify `_serialize_draft`:

```python
def _serialize_draft(draft: AiDraft) -> dict:
    return {
        "id": draft.id,
        "platform": draft.platform,
        "draft_name": draft.draft_name or "",
        "title": draft.title,
        "body": draft.body,
        "tags": draft.tags or [],
        "source_note_id": draft.source_note_id,
        "created_at": draft.created_at.isoformat(),
    }
```

Modify `create_draft` instantiation:

```python
draft = AiDraft(
    user_id=current_user.id,
    platform=payload.platform,
    draft_name=(payload.draft_name or "").strip(),
    title=payload.title or (source_note.title if source_note else ""),
    body=payload.body or (source_note.content if source_note else ""),
    tags=tags,
    source_note_id=source_note.id if source_note else None,
)
```

Modify `duplicate_draft` instantiation:

```python
duplicated = AiDraft(
    user_id=current_user.id,
    platform=draft.platform,
    draft_name=f"{draft.draft_name} 副本" if draft.draft_name else "",
    title=f"{draft.title} - 副本",
    body=draft.body,
    tags=json.loads(json.dumps(draft.tags, ensure_ascii=False)) if draft.tags is not None else None,
    source_note_id=draft.source_note_id,
)
```

Modify `update_draft` before title/body updates:

```python
if payload.draft_name is not None:
    draft.draft_name = payload.draft_name.strip()
```

- [ ] **Step 6: Update other backend serializers**

In `backend/app/api/notes.py`, update its `_serialize_draft` return dict to include:

```python
"draft_name": draft.draft_name or "",
```

In `backend/app/api/platforms/xhs/analytics.py`, update draft serialization to include:

```python
"draft_name": draft.draft_name or "",
```

In `backend/app/services/wechat_official_draft_service.py`, update `serialize_draft` return dict to include:

```python
"draft_name": draft.draft_name or "",
```

- [ ] **Step 7: Run draft tests to verify pass**

Run:

```bash
pytest tests/backend/test_drafts.py -q
```

Expected: PASS.

- [ ] **Step 8: Checkpoint**

Do not commit unless the user explicitly asks. Record changed files for final summary.

---

## Task 3: Apply Content Normalization to Draft, AI Rewrite, and Auto Operations

**Files:**
- Modify: `backend/app/api/drafts.py`
- Modify: `backend/app/api/ai.py`
- Modify: `backend/app/services/scheduler_service.py`
- Modify: `backend/app/services/xhs_analysis_center_service.py`
- Modify: `tests/backend/test_drafts.py`
- Modify: `tests/backend/test_api.py`

- [ ] **Step 1: Add failing draft normalization tests**

Append to `tests/backend/test_drafts.py`:

```python

def test_update_draft_normalizes_repeated_title_and_markdown_symbols(tmp_path):
    SessionLocal = override_database(tmp_path)
    try:
        db = SessionLocal()
        try:
            owner = create_user(db, "draft-normalize-owner")
            draft = AiDraft(user_id=owner.id, platform="xhs", title="旧标题", body="旧正文", tags=[])
            db.add(draft)
            db.commit()
            draft_id = draft.id
            headers = auth_headers(owner)
        finally:
            db.close()

        response = client.patch(
            f"/api/drafts/{draft_id}",
            headers=headers,
            json={
                "title": "SaaS 工具怎么选？",
                "body": "# SaaS 工具怎么选？\n\n**重点**\n- 第一条",
                "tags": [{"name": "工具"}, {"name": "工具"}],
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["title"] == "SaaS 工具怎么选？"
        assert payload["body"] == "重点\n第一条"
        assert payload["tags"] == [{"name": "工具"}]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_send_draft_to_publish_uses_normalized_content(tmp_path):
    SessionLocal = override_database(tmp_path)
    try:
        db = SessionLocal()
        try:
            owner = create_user(db, "draft-publish-normalize-owner")
            draft = AiDraft(
                user_id=owner.id,
                platform="xhs",
                title="SaaS 工具怎么选？",
                body="SaaS 工具怎么选？\n\n正文第一段",
                tags=[{"name": "SaaS"}, {"name": "SaaS"}],
            )
            db.add(draft)
            db.commit()
            draft_id = draft.id
            headers = auth_headers(owner)
        finally:
            db.close()

        response = client.post(f"/api/drafts/{draft_id}/send-to-publish", headers=headers, json={"publish_mode": "immediate"})

        assert response.status_code == 200
        payload = response.json()
        assert payload["title"] == "SaaS 工具怎么选？"
        assert payload["body"] == "正文第一段"
        assert payload["publish_options"]["draft_tags"] == [{"name": "SaaS"}]
    finally:
        app.dependency_overrides.pop(get_db, None)
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/backend/test_drafts.py -q
```

Expected: FAIL because draft update and send-to-publish do not normalize content yet.

- [ ] **Step 3: Add draft API normalization helper**

In `backend/app/api/drafts.py`, import:

```python
from backend.app.services.xhs_content_normalizer import normalize_xhs_generated_content
```

Add helper near `_serialize_draft`:

```python
def _apply_normalized_content(draft: AiDraft) -> None:
    normalized = normalize_xhs_generated_content(draft.title, draft.body, draft.tags or [])
    draft.title = normalized.title
    draft.body = normalized.body
    draft.tags = normalized.tags
    flag_modified(draft, "tags")
```

- [ ] **Step 4: Normalize create/update/send-to-publish**

In `create_draft`, after `draft = AiDraft(...)` and before `db.add(draft)`, add:

```python
_apply_normalized_content(draft)
```

In `update_draft`, after applying payload fields and before `db.commit()`, add:

```python
if {"title", "body", "tags"} & payload.model_fields_set:
    _apply_normalized_content(draft)
```

In `send_draft_to_publish`, after ownership checks and before building `options`, add:

```python
_apply_normalized_content(draft)
```

- [ ] **Step 5: Normalize AI rewrite output**

In `backend/app/api/ai.py`, import:

```python
from backend.app.services.xhs_content_normalizer import normalize_xhs_generated_content
```

Replace the current rewrite save block:

```python
draft.body = rewritten_body
task.payload = {**(task.payload or {}), "result_draft_id": draft.id, "result_length": len(rewritten_body)}
```

with:

```python
normalized = normalize_xhs_generated_content(draft.title, rewritten_body, draft.tags or [])
draft.title = normalized.title
draft.body = normalized.body
draft.tags = normalized.tags
task.payload = {
    **(task.payload or {}),
    "result_draft_id": draft.id,
    "result_length": len(normalized.body),
    "normalization_warnings": normalized.warnings,
}
```

- [ ] **Step 6: Normalize scheduler-generated auto-operation drafts**

In `backend/app/services/scheduler_service.py`, import:

```python
from backend.app.services.xhs_content_normalizer import normalize_xhs_generated_content
```

Near the auto-operation flow where `draft.title`, `draft.body`, and optional generated title are finalized before `PublishJob(...)`, add:

```python
normalized = normalize_xhs_generated_content(draft.title, draft.body, draft.tags or [])
draft.title = normalized.title
draft.body = normalized.body
draft.tags = normalized.tags
```

Place it immediately before the comment or code that creates the publish job, so the pending publish job receives clean content.

- [ ] **Step 7: Normalize analysis-generated topic drafts**

In `backend/app/services/xhs_analysis_center_service.py`, import:

```python
from backend.app.services.xhs_content_normalizer import normalize_xhs_generated_content
```

Where `draft = AiDraft(user_id=user_id, platform="xhs", title=title, body=body, tags=tags, source_note_id=None)` is created, replace with:

```python
normalized = normalize_xhs_generated_content(title, body, tags)
draft = AiDraft(
    user_id=user_id,
    platform="xhs",
    title=normalized.title,
    body=normalized.body,
    tags=normalized.tags,
    source_note_id=None,
)
```

- [ ] **Step 8: Update AI rewrite tests if raw body expectations fail**

Run:

```bash
pytest tests/backend/test_api.py::test_ai_rewrite_note_uses_default_text_model_and_updates_owned_draft -q
```

If the existing fake rewrite body contains no Markdown/repeated title, expected output remains unchanged. If it contains a repeated title, update the expected assertion to the normalized body exactly as produced by `normalize_xhs_generated_content`.

- [ ] **Step 9: Run backend normalization-related tests**

Run:

```bash
pytest tests/backend/test_xhs_content_normalizer.py tests/backend/test_drafts.py tests/backend/test_api.py::test_ai_rewrite_note_uses_default_text_model_and_updates_owned_draft -q
```

Expected: PASS.

- [ ] **Step 10: Checkpoint**

Do not commit unless the user explicitly asks. Record changed files for final summary.

---

## Task 4: Frontend Draft Name Support in Shared Draft Workbench

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/components/draft-workbench/draft-workbench-types.ts`
- Modify: `frontend/src/components/draft-workbench/use-draft-workbench.ts`
- Modify: `frontend/src/components/draft-workbench/draft-workbench-shell.tsx`
- Modify: `frontend/src/pages/platforms/xhs/xhs-draft-workbench-adapter.ts`

- [ ] **Step 1: Extend shared frontend types**

In `frontend/src/types/index.ts`, update `Draft`:

```ts
export type Draft = {
  id: number;
  platform: PlatformId;
  draft_name?: string;
  title: string;
  body: string;
  tags?: { id?: string; name: string }[];
  source_note_id?: number | null;
  created_at: string;
};
```

Update `CreateDraftPayload` to include:

```ts
draft_name?: string;
```

If `CreateDraftPayload` currently has only `platform`, `source_note_id`, and `intent`, make it:

```ts
export type CreateDraftPayload = {
  platform: "xhs";
  source_note_id?: number | null;
  draft_name?: string;
  title?: string;
  body?: string;
  intent?: "rewrite" | "publish" | string;
};
```

- [ ] **Step 2: Extend API update payload**

In `frontend/src/lib/api.ts`, replace `updateDraft` signature with:

```ts
export async function updateDraft(
  draftId: number,
  payload: { draft_name?: string; title?: string; body?: string; tags?: { id?: string; name: string }[] },
): Promise<Draft> {
  const response = await http.patch<Draft>(`/drafts/${draftId}`, payload);
  return response.data;
}
```

- [ ] **Step 3: Extend Draft Workbench types**

In `frontend/src/components/draft-workbench/draft-workbench-types.ts`, change `DraftWorkbenchDraft`:

```ts
export type DraftWorkbenchDraft = Pick<Draft, "id" | "draft_name" | "title" | "body" | "tags" | "created_at">;
```

Change `DraftWorkbenchDraftPatch`:

```ts
export type DraftWorkbenchDraftPatch = {
  draft_name?: string;
  title: string;
  body: string;
  tags: Draft["tags"];
};
```

Add to `DraftWorkbenchController`:

```ts
draftName: string;
setDraftName(draftName: string): void;
```

- [ ] **Step 4: Track draftName in useDraftWorkbench**

In `frontend/src/components/draft-workbench/use-draft-workbench.ts`, add state after title:

```ts
const [draftName, setDraftName] = useState("");
```

In `syncDraftState`, set it:

```ts
setDraftName(draft.draft_name ?? "");
```

In the null branch, reset it:

```ts
setDraftName("");
```

In `saveSelectedDraft`, include it:

```ts
const updated = await adapter.saveDraft(selectedDraft.id, { draft_name: draftName, title, body, tags });
```

In hook dependencies for `saveSelectedDraft`, add `draftName`.

In returned controller, add:

```ts
draftName,
setDraftName,
```

- [ ] **Step 5: Render internal name and publish title separately**

In `frontend/src/components/draft-workbench/draft-workbench-shell.tsx`, change list title from:

```tsx
{draft.title || "未命名草稿"}
```

to:

```tsx
{draft.draft_name || draft.title || "未命名草稿"}
```

Change the title label block from “标题” to two inputs:

```tsx
<div>
  <Text type="secondary" style={{ display: "block", marginBottom: 8 }}>
    内部草稿名
  </Text>
  <Input
    value={controller.draftName}
    onChange={(event) => controller.setDraftName(event.target.value)}
    placeholder="例如：浴缸案例图替换 - 0622 A版"
  />
</div>

<div>
  <Text type="secondary" style={{ display: "block", marginBottom: 8 }}>
    发布标题
  </Text>
  <Input
    value={controller.title}
    onChange={(event) => controller.setTitle(event.target.value)}
    placeholder="输入小红书发布标题"
  />
</div>
```

- [ ] **Step 6: Improve XHS list subtitle**

In `frontend/src/pages/platforms/xhs/xhs-draft-workbench-adapter.ts`, change `getListSubtitle`:

```ts
getListSubtitle: (draft) => {
  const time = formatDraftTime(draft.created_at);
  return draft.draft_name && draft.title ? `发布标题：${draft.title} · ${time}` : time;
},
```

- [ ] **Step 7: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS. If TypeScript reports additional places where `DraftWorkbenchController` is constructed or used, update them to include `draftName` and `setDraftName`.

- [ ] **Step 8: Checkpoint**

Do not commit unless the user explicitly asks. Record changed files for final summary.

---

## Task 5: Draft Workbench → Image Studio Context Handoff

**Files:**
- Create: `frontend/src/pages/platforms/xhs/xhs-image-studio-context.ts`
- Modify: `frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx`

- [ ] **Step 1: Create Image Studio context helpers**

Create `frontend/src/pages/platforms/xhs/xhs-image-studio-context.ts`:

```ts
import type { Draft } from "../../../types";
import type { DraftAsset } from "../../../lib/api";

export const XHS_IMAGE_STUDIO_DRAFT_CONTEXT_KEY = "xhs:image-studio:draft-context";

export type XhsImageStudioCandidateImage = {
  id?: number;
  url: string;
  local_path?: string;
  source: "draft_asset" | "source_note" | "manual";
};

export type XhsImageStudioDraftContext = {
  source: "draft";
  draft_id: number;
  draft_name?: string | null;
  title: string;
  body: string;
  tags: NonNullable<Draft["tags"]>;
  source_note_id?: number | null;
  candidate_images: XhsImageStudioCandidateImage[];
};

export function saveImageStudioDraftContext(context: XhsImageStudioDraftContext): void {
  window.sessionStorage.setItem(XHS_IMAGE_STUDIO_DRAFT_CONTEXT_KEY, JSON.stringify(context));
}

export function loadImageStudioDraftContext(): XhsImageStudioDraftContext | null {
  const raw = window.sessionStorage.getItem(XHS_IMAGE_STUDIO_DRAFT_CONTEXT_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as XhsImageStudioDraftContext;
    return parsed?.source === "draft" && typeof parsed.draft_id === "number" ? parsed : null;
  } catch {
    return null;
  }
}

export function clearImageStudioDraftContext(): void {
  window.sessionStorage.removeItem(XHS_IMAGE_STUDIO_DRAFT_CONTEXT_KEY);
}

export function draftAssetToCandidate(asset: DraftAsset): XhsImageStudioCandidateImage | null {
  if (asset.asset_type !== "image" || !asset.url) return null;
  return {
    id: asset.id,
    url: asset.url,
    local_path: asset.local_path,
    source: "draft_asset",
  };
}
```

- [ ] **Step 2: Wire navigate and context save in XHS draft workbench**

In `frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx`, add imports:

```ts
import { useNavigate } from "react-router-dom";
import { PictureOutlined } from "@ant-design/icons";
import { draftAssetToCandidate, saveImageStudioDraftContext } from "./xhs-image-studio-context";
```

If `PictureOutlined` conflicts with the existing icon import line, merge it into the existing `@ant-design/icons` import.

Inside `XhsDraftsPage`, add:

```ts
const navigate = useNavigate();
const [isSendingImageStudio, setIsSendingImageStudio] = useState(false);
```

Add helper function near `handleSendToPublish`:

```ts
function sourceNoteImageCandidates(note: SavedNote | null) {
  const urls = new Set<string>();
  if (note?.cover_url) urls.add(note.cover_url);
  for (const url of note?.asset_urls ?? []) {
    if (url) urls.add(url);
  }
  return Array.from(urls).map((url) => ({ url, source: "source_note" as const }));
}

async function handleSendToImageStudio() {
  if (!selectedDraft) return;
  setIsSendingImageStudio(true);
  try {
    const saved = await updateDraft(selectedDraft.id, {
      draft_name: controller.draftName,
      title: controller.title,
      body: controller.body,
      tags: controller.tags,
    });
    const draftAssets = await fetchDraftAssets(saved.id);
    const candidateImages = [
      ...draftAssets.items.map(draftAssetToCandidate).filter((item): item is NonNullable<typeof item> => Boolean(item)),
      ...sourceNoteImageCandidates(sourceNote),
    ];
    saveImageStudioDraftContext({
      source: "draft",
      draft_id: saved.id,
      draft_name: saved.draft_name ?? "",
      title: saved.title,
      body: saved.body,
      tags: Array.isArray(saved.tags) ? saved.tags : [],
      source_note_id: saved.source_note_id ?? null,
      candidate_images: candidateImages,
    });
    antMessage.success("已带着草稿内容进入图片工坊。");
    navigate("/platforms/xhs/image-studio?from=draft");
  } catch (error) {
    antMessage.error(error instanceof Error ? error.message : "送入图片工坊失败");
  } finally {
    setIsSendingImageStudio(false);
  }
}
```

- [ ] **Step 3: Add button next to publish button**

In `renderAssistantExtras`, inside the `<Space wrap>` that currently contains “送发布中心”, add before the publish button:

```tsx
<Button onClick={() => void handleSendToImageStudio()} loading={isSendingImageStudio} icon={<PictureOutlined />}>
  送入图片工坊
</Button>
```

- [ ] **Step 4: Ensure publish save includes draft_name**

In existing `handleSendToPublish`, change update payload to:

```ts
await updateDraft(selectedDraft.id, {
  draft_name: controller.draftName,
  title: controller.title,
  body: controller.body,
  tags: controller.tags,
});
```

- [ ] **Step 5: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 6: Checkpoint**

Do not commit unless the user explicitly asks. Record changed files for final summary.

---

## Task 6: Image Studio Consumes Draft Context and Sends Generated Image to Publish Center

**Files:**
- Modify: `frontend/src/pages/platforms/xhs/image-studio-page.tsx`
- Modify: `frontend/src/lib/api.ts` if `addPublishAsset` is not already exported

- [ ] **Step 1: Add imports to Image Studio**

In `frontend/src/pages/platforms/xhs/image-studio-page.tsx`, update imports:

```ts
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
```

Add API imports:

```ts
addPublishAsset,
sendDraftToPublish,
```

Add context imports:

```ts
import {
  clearImageStudioDraftContext,
  loadImageStudioDraftContext,
  type XhsImageStudioDraftContext,
} from "./xhs-image-studio-context";
```

- [ ] **Step 2: Add state for draft context and publishing handoff**

Inside `XhsImageStudioPage`, add:

```ts
const navigate = useNavigate();
const [draftContext, setDraftContext] = useState<XhsImageStudioDraftContext | null>(null);
const [isSendingPublish, setIsSendingPublish] = useState(false);
```

Add derived values:

```ts
const draftContextTitle = draftContext?.draft_name || draftContext?.title || "未命名草稿";
const candidateReferenceImages = useMemo(
  () => draftContext?.candidate_images.map((item) => item.url).filter(Boolean) ?? [],
  [draftContext],
);
```

- [ ] **Step 3: Load context on mount and prefill reference images/prompt**

Replace the existing mount effect:

```ts
useEffect(() => {
  void loadAssets();
}, []);
```

with:

```ts
useEffect(() => {
  void loadAssets();
  const context = loadImageStudioDraftContext();
  if (!context) return;
  setDraftContext(context);
  setReferenceImages(context.candidate_images.slice(0, RUNNINGHUB_CURRENT_REFERENCE_IMAGE_LIMIT).map((item) => item.url));
  setPrompt((current) => current || `参考草稿《${context.title || context.draft_name || "未命名"}》的内容和案例图，生成适合小红书发布的产品替换图。\n\n正文摘要：${context.body.slice(0, 300)}`);
  setMessage("已载入草稿文案和案例图候选。请上传或选择产品图后生成替换图。");
}, []);
```

- [ ] **Step 4: Render draft context card above generation tools**

After success/error alerts and before the top row, add:

```tsx
{draftContext ? (
  <Card style={{ marginBottom: 16 }}>
    <Space direction="vertical" size={8} style={{ width: "100%" }}>
      <Space wrap>
        <Tag color="blue">来自草稿</Tag>
        <Text strong>{draftContextTitle}</Text>
        {draftContext.candidate_images.length > 0 ? (
          <Text type="secondary">已带入 {draftContext.candidate_images.length} 张案例图候选</Text>
        ) : (
          <Text type="secondary">这个草稿还没有案例图，请手动上传或选择参考图</Text>
        )}
      </Space>
      <Paragraph ellipsis={{ rows: 2, expandable: true, symbol: "展开正文" }} style={{ marginBottom: 0, whiteSpace: "pre-wrap" }}>
        {draftContext.body || "暂无正文"}
      </Paragraph>
      <Space wrap>
        <Button size="small" onClick={() => navigate("/platforms/xhs/drafts")}>回到草稿</Button>
        <Button size="small" onClick={() => { clearImageStudioDraftContext(); setDraftContext(null); }}>清除草稿上下文</Button>
      </Space>
    </Space>
  </Card>
) : null}
```

- [ ] **Step 5: Show candidate reference images when context has more than two images**

Under the existing reference image selector, add:

```tsx
{candidateReferenceImages.length > RUNNINGHUB_CURRENT_REFERENCE_IMAGE_LIMIT ? (
  <div style={{ marginTop: 8 }}>
    <Text type="secondary" style={{ fontSize: 12, display: "block", marginBottom: 6 }}>
      更多案例图候选
    </Text>
    <Space size={8} wrap>
      {candidateReferenceImages.slice(RUNNINGHUB_CURRENT_REFERENCE_IMAGE_LIMIT).map((url) => (
        <Button key={url} size="small" onClick={() => handlePickerSelect(url)}>
          加入参考图
        </Button>
      ))}
    </Space>
  </div>
) : null}
```

This reuses `handlePickerSelect` and the existing two-reference-image limit.

- [ ] **Step 6: Add Image Studio → Publish Center handoff**

Add function near `handleGenerate`:

```ts
async function handleSendGeneratedToPublish() {
  if (!draftContext) {
    setError("没有草稿上下文，无法送入发布中心。");
    return;
  }
  if (!generatedPreview) {
    setError("请先生成图片，再送入发布中心。");
    return;
  }
  setIsSendingPublish(true);
  setError(null);
  setMessage(null);
  try {
    const job = await sendDraftToPublish(draftContext.draft_id, { publish_mode: "immediate" });
    await addPublishAsset(job.id, { asset_type: "image", file_path: generatedPreview });
    clearImageStudioDraftContext();
    setMessage(`已送入发布中心，发布任务 #${job.id}。`);
    navigate(`/platforms/xhs/publish?jobId=${job.id}`);
  } catch (err) {
    const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
    setError(detail || "送入发布中心失败，草稿内容和生成图已保留。");
  } finally {
    setIsSendingPublish(false);
  }
}
```

- [ ] **Step 7: Render handoff button in generated result**

Inside the generated result block after the image, add:

```tsx
{draftContext ? (
  <Button
    type="primary"
    size="small"
    onClick={() => void handleSendGeneratedToPublish()}
    loading={isSendingPublish}
    style={{ marginTop: 8 }}
  >
    送入发布中心
  </Button>
) : null}
```

- [ ] **Step 8: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 9: Checkpoint**

Do not commit unless the user explicitly asks. Record changed files for final summary.

---

## Task 7: Publish Center Selects Newly Created Job from Query String

**Files:**
- Modify: `frontend/src/pages/platforms/xhs/publish-page.tsx`

- [ ] **Step 1: Add search params import and state use**

Modify import:

```ts
import { useNavigate, useSearchParams } from "react-router-dom";
```

Inside `XhsPublishPage`, add:

```ts
const [searchParams, setSearchParams] = useSearchParams();
const requestedJobId = Number(searchParams.get("jobId") || 0) || null;
```

- [ ] **Step 2: Make loadJobs select requested job**

In `loadJobs`, replace the selection block:

```ts
const current = selectedJobId ? result.items.find((job) => job.id === selectedJobId) : null;
const nextJob = current ?? result.items[0];
```

with:

```ts
const requested = requestedJobId ? result.items.find((job) => job.id === requestedJobId) : null;
const current = selectedJobId ? result.items.find((job) => job.id === selectedJobId) : null;
const nextJob = requested ?? current ?? result.items[0];
```

After `await loadAssets(nextJob.id);`, add:

```ts
if (requestedJobId && requestedJobId === nextJob.id) {
  setSearchParams({}, { replace: true });
}
```

Update `loadJobs` dependencies if lint/type checking complains. Because `loadJobs` is a function declared inside the component and called manually, no hook dependency array needs updating beyond the existing mount effect.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 4: Checkpoint**

Do not commit unless the user explicitly asks. Record changed files for final summary.

---

## Task 8: Full Verification and Manual Smoke Checklist

**Files:**
- No code changes expected.

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
pytest tests/backend/test_xhs_content_normalizer.py tests/backend/test_drafts.py tests/backend/test_api.py::test_ai_rewrite_note_uses_default_text_model_and_updates_owned_draft -q
```

Expected: PASS.

- [ ] **Step 2: Run broader backend API tests if time permits**

Run:

```bash
pytest tests/backend/test_api.py -q
```

Expected: PASS or report exact pre-existing failures if unrelated. Do not claim completion if this fails without explanation.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 4: Manual smoke test draft name**

Use the local app without real publishing:

1. Open `/platforms/xhs/drafts`.
2. Select or create a draft.
3. Fill internal draft name: `浴缸案例图替换 - 0622 A版`.
4. Fill publish title: `卫生间浴缸怎么选？看完少踩 3 个坑`.
5. Save and refresh.

Expected:

- Draft list main title shows `浴缸案例图替换 - 0622 A版`.
- Editor publish title remains `卫生间浴缸怎么选？看完少踩 3 个坑`.
- Publish title is not overwritten by internal draft name.

- [ ] **Step 5: Manual smoke test draft → image studio**

1. Select a draft that has image assets or a source note with `asset_urls`.
2. Click `送入图片工坊`.

Expected:

- Image Studio opens.
- It shows `来自草稿` card.
- Prompt contains draft context.
- Reference image slots are preloaded with up to two candidate images.
- If no images exist, Image Studio stays usable and asks the user to upload/select a reference image.

- [ ] **Step 6: Manual smoke test image studio → publish center without real publish**

1. In Image Studio, generate or simulate a generated preview using the existing image generation flow.
2. Click `送入发布中心`.

Expected:

- A pending publish job is created.
- Publish Center opens with `?jobId=` selection applied.
- The selected job contains normalized title/body/tags from the source draft.
- The generated image appears as a publish asset.
- Do not click the real `发布` confirmation.

- [ ] **Step 7: Final status report**

Report:

- Current branch and workspace path.
- Files changed.
- Verification commands run and exact pass/fail outcome.
- Whether root `master` contains the changes.
- Whether local standard services on ports `18080/18081` need restart to see frontend/backend changes.

Do not claim “done and verified” unless the focused backend tests and frontend build pass, or unless failures are clearly reported with output.

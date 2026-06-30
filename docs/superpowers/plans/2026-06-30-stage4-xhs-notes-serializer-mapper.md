# Stage 4 XHS Notes Serializer Mapper Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the XHS notes API serializer use `backend/app/adapters/xhs/mappers.py::map_xhs_content` for XHS raw payload display fields and engagement metrics without changing the response shape.

**Architecture:** Keep `map_xhs_content` as the pure adapter mapper. Add a tiny serializer boundary in `backend/app/api/notes.py` that calls the mapper only for `note.platform == "xhs"`; non-XHS notes keep the existing defensive behavior. Preserve database asset priority, existing field names, batch-save behavior, and ownership checks.

**Tech Stack:** Python 3.12 via `py -3.12`, FastAPI route helpers, SQLAlchemy models, pytest.

---

## Scope Firewall

### In scope

- Modify `backend/app/api/notes.py` only for XHS serializer/metric mapper usage.
- Create `tests/backend/test_notes_xhs_serializer.py` for focused serializer tests.
- Reuse existing `backend/app/adapters/xhs/mappers.py` unchanged unless a test proves a mapper bug.

### Out of scope

- No database model changes.
- No Alembic migration.
- No `POST /api/notes/batch-save` save behavior changes.
- No `_get_owned_account` ownership change.
- No `apis/`, `xhs_utils/`, or `static/` changes.
- No Feishu analysis/score/rating changes.
- No XHS auto-ops, publish page, or creator pending-login/user-message changes.
- No real provider call, real XHS request, deploy, service restart, push, or broad staging.

### Dirty workspace warning

At plan time, `backend/app/api/notes.py` already contains unrelated Feishu/score/rating dirty hunks:

```diff
+        "cover_type": result.raw_payload.get("封面类型") if isinstance(result.raw_payload, dict) else None,
+        "title_type": result.raw_payload.get("标题类型") if isinstance(result.raw_payload, dict) else None,
+        "score": result.score,
+        "rating": result.rating,
```

Do not revert these hunks. Do not include them in the Stage 4 commit. If committing, stage only the serializer hunks in `backend/app/api/notes.py` plus the new focused test file.

---

## File Structure

- Modify: `backend/app/api/notes.py`
  - Responsibility: serialize stored `Note` rows into API response dictionaries.
  - New boundary: XHS-only serializer helper calls `map_xhs_content` and keeps fallback behavior local to serialization.

- Create: `tests/backend/test_notes_xhs_serializer.py`
  - Responsibility: focused tests for notes serializer mapper usage without exercising unrelated Feishu or full API flows.
  - Tests call private serializer helpers directly because this is a serializer contract, not route/auth behavior.

---

## Task 1: Add failing serializer tests

**Files:**

- Create: `tests/backend/test_notes_xhs_serializer.py`
- Read-only reference: `backend/app/models/note.py`
- Read-only reference: `backend/app/api/notes.py`

- [ ] **Step 1: Create focused test file**

Create `tests/backend/test_notes_xhs_serializer.py` with this content:

```python
from __future__ import annotations

from datetime import datetime

from backend.app.api.notes import _note_engagement_metrics, _serialize_note
from backend.app.models import Note, NoteAsset


class _FakeDb:
    def scalars(self, statement):
        return _FakeScalarResult([])

    def scalar(self, statement):
        return None


class _FakeAssetDb(_FakeDb):
    def __init__(self, assets: list[NoteAsset]) -> None:
        self.assets = assets

    def scalars(self, statement):
        return _FakeScalarResult(self.assets)


class _FakeScalarResult:
    def __init__(self, items: list) -> None:
        self.items = items

    def all(self):
        return self.items


def _note(*, platform: str = "xhs", raw_json: dict | None = None) -> Note:
    note = Note(
        id=101,
        user_id=1,
        platform_account_id=10,
        platform=platform,
        note_id="serializer-note-001",
        title="Serializer note",
        content="Body",
        author_name="Author",
        raw_json=raw_json,
        created_at=datetime(2026, 6, 30, 9, 0, 0),
    )
    return note


def test_xhs_note_engagement_metrics_use_mapper_for_nested_note_card_shape():
    note = _note(raw_json={
        "data": {
            "items": [
                {
                    "note_card": {
                        "interact_info": {
                            "liked_count": "3,000",
                            "comment_count": "12",
                            "collected_count": "1.2w",
                            "share_count": "7",
                        }
                    }
                }
            ]
        }
    })

    assert _note_engagement_metrics(note) == {
        "likes": 3000,
        "comments": 12,
        "collects": 12000,
        "shares": 7,
    }


def test_xhs_note_serializer_uses_mapper_asset_fallback_when_db_assets_are_missing():
    note = _note(raw_json={
        "cover_url": "https://images.example/raw-cover.jpg",
        "image_url": "https://images.example/raw-image.jpg",
        "video_url": "https://videos.example/raw-video.mp4",
    })

    payload = _serialize_note(_FakeDb(), note)

    assert payload["cover_url"] == "https://images.example/raw-cover.jpg"
    assert payload["video_url"] == "https://videos.example/raw-video.mp4"
    assert payload["video_addr"] == "https://videos.example/raw-video.mp4"
    assert payload["asset_urls"] == [
        "https://images.example/raw-cover.jpg",
        "https://images.example/raw-image.jpg",
        "https://videos.example/raw-video.mp4",
    ]
    assert set(payload.keys()) == {
        "id",
        "platform",
        "platform_account_id",
        "note_id",
        "title",
        "content",
        "author_name",
        "raw_json",
        "asset_urls",
        "cover_url",
        "video_url",
        "video_addr",
        "created_at",
        "engagement_metrics",
        "analysis_marks",
        "is_analysis_focus",
        "feishu_sync",
        "analysis_result",
    }


def test_xhs_note_serializer_preserves_db_asset_priority_over_mapper_fallback():
    note = _note(raw_json={
        "cover_url": "https://images.example/raw-cover.jpg",
        "image_url": "https://images.example/raw-image.jpg",
        "video_url": "https://videos.example/raw-video.mp4",
    })
    image = NoteAsset(
        id=201,
        note_id=note.id,
        asset_type="image",
        url="https://images.example/db-image.jpg",
        local_path="xhs-asset-u1-local-image.jpg",
        sort_order=0,
    )
    video = NoteAsset(
        id=202,
        note_id=note.id,
        asset_type="video",
        url="https://videos.example/db-video.mp4",
        local_path="xhs-asset-u1-local-video.mp4",
        sort_order=1,
    )

    payload = _serialize_note(_FakeAssetDb([image, video]), note)

    assert payload["cover_url"] == "/api/files/media/xhs-asset-u1-local-image.jpg"
    assert payload["video_url"] == "/api/files/media/xhs-asset-u1-local-video.mp4"
    assert payload["video_addr"] == "/api/files/media/xhs-asset-u1-local-video.mp4"
    assert payload["asset_urls"] == [
        "/api/files/media/xhs-asset-u1-local-image.jpg",
        "/api/files/media/xhs-asset-u1-local-video.mp4",
    ]


def test_non_xhs_note_serializer_does_not_require_xhs_raw_shape():
    note = _note(platform="wechat_official", raw_json={"unexpected": {"shape": True}})

    payload = _serialize_note(_FakeDb(), note)

    assert payload["platform"] == "wechat_official"
    assert payload["cover_url"] == ""
    assert payload["video_url"] == ""
    assert payload["video_addr"] == ""
    assert payload["asset_urls"] == []
    assert payload["engagement_metrics"] == {
        "likes": 0,
        "collects": 0,
        "comments": 0,
        "shares": 0,
    }
```

- [ ] **Step 2: Run the focused tests to verify RED**

Run:

```bash
py -3.12 -m pytest tests/backend/test_notes_xhs_serializer.py -q
```

Expected: at least these tests fail before implementation:

```text
FAILED tests/backend/test_notes_xhs_serializer.py::test_xhs_note_serializer_uses_mapper_asset_fallback_when_db_assets_are_missing
```

The current serializer does not use mapper `video_url`/`asset_urls` fallback and may keep only direct raw cover fallback.

---

## Task 2: Wire XHS mapper into notes serializer

**Files:**

- Modify: `backend/app/api/notes.py`

- [ ] **Step 1: Import mapper types and function**

In `backend/app/api/notes.py`, add this import after the existing XHS route imports and before core imports:

```python
from backend.app.adapters.xhs.mappers import XhsContentMapping, map_xhs_content
```

Do not remove the existing `backend.app.api.platforms.xhs.pc` imports in this task.

- [ ] **Step 2: Add helper functions after `_as_int`**

Insert this block immediately after `_as_int`:

```python
def _xhs_content_mapping(note: Note) -> XhsContentMapping | None:
    if note.platform != "xhs":
        return None
    raw = note.raw_json if isinstance(note.raw_json, dict) else {}
    return map_xhs_content(note.note_id, raw)


def _legacy_note_engagement_metrics(note: Note) -> dict[str, int]:
    raw = note.raw_json if isinstance(note.raw_json, dict) else {}
    likes = _as_int(raw.get("liked_count") or raw.get("likes") or raw.get("like_count"))
    collects = _as_int(raw.get("collected_count") or raw.get("collects") or raw.get("collect_count"))
    comments = _as_int(raw.get("comment_count") or raw.get("comments"))
    shares = _as_int(raw.get("share_count") or raw.get("shares"))
    if likes or collects or comments or shares:
        return {"likes": likes, "collects": collects, "comments": comments, "shares": shares}

    data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
    items = data.get("items") if isinstance(data.get("items"), list) else []
    item = items[0] if items and isinstance(items[0], dict) else {}
    card = item.get("note_card") if isinstance(item.get("note_card"), dict) else {}
    info = card.get("interact_info") if isinstance(card.get("interact_info"), dict) else {}
    return {
        "likes": _as_int(info.get("liked_count")),
        "collects": _as_int(info.get("collected_count")),
        "comments": _as_int(info.get("comment_count")),
        "shares": _as_int(info.get("share_count")),
    }
```

This preserves the old parsing as fallback and for non-XHS notes.

- [ ] **Step 3: Replace `_note_engagement_metrics` body**

Replace the existing `_note_engagement_metrics` function body with:

```python
def _note_engagement_metrics(note: Note) -> dict[str, int]:
    mapping = _xhs_content_mapping(note)
    if mapping is not None:
        return {
            "likes": mapping.engagement_metrics["likes"],
            "collects": mapping.engagement_metrics["collects"],
            "comments": mapping.engagement_metrics["comments"],
            "shares": mapping.engagement_metrics["shares"],
        }
    return _legacy_note_engagement_metrics(note)
```

The key order intentionally matches the existing API response order: `likes`, `collects`, `comments`, `shares`.

- [ ] **Step 4: Update `_serialize_note` fallback logic only**

Inside `_serialize_note`, replace the local variables at the start with this block:

```python
    assets = _get_note_assets(db, note)
    image_assets = [asset for asset in assets if asset.asset_type == "image"]
    video_assets = [asset for asset in assets if asset.asset_type == "video"]
    asset_urls = [_asset_display_url(asset) for asset in assets if asset.url or asset.local_path]
    raw = note.raw_json if isinstance(note.raw_json, dict) else {}
    raw_cover = raw.get("cover_url") if isinstance(raw.get("cover_url"), str) else ""
    mapping = _xhs_content_mapping(note)
    mapped_cover_url = mapping.cover_url if mapping else ""
    mapped_video_url = mapping.video_url if mapping else ""
    mapped_asset_urls = mapping.asset_urls if mapping else []
    response_asset_urls = asset_urls or mapped_asset_urls
    response_cover_url = _asset_display_url(image_assets[0]) if image_assets else (mapped_cover_url or raw_cover)
    response_video_url = _asset_display_url(video_assets[0]) if video_assets else mapped_video_url
    marks = (top20_marks or {}).get(note.id, [])
    analysis = _get_feishu_analysis_result(db, note.id)
```

Then in the returned dict, replace only these three fields:

```python
        "asset_urls": response_asset_urls,
        "cover_url": response_cover_url,
        "video_url": response_video_url,
        "video_addr": response_video_url,
```

Do not alter the Feishu analysis fields in `_serialize_analysis_result`; they are unrelated dirty work.

- [ ] **Step 5: Run focused serializer tests to verify GREEN**

Run:

```bash
py -3.12 -m pytest tests/backend/test_notes_xhs_serializer.py -q
```

Expected:

```text
4 passed
```

---

## Task 3: Run mapper and adjacent regression tests

**Files:**

- No code edits unless tests reveal a Stage 4 serializer issue.

- [ ] **Step 1: Run mapper + serializer tests together**

Run:

```bash
py -3.12 -m pytest tests/backend/test_xhs_content_mappers.py tests/backend/test_notes_xhs_serializer.py -q
```

Expected:

```text
11 passed
```

The exact runtime may vary, but both files must pass.

- [ ] **Step 2: Run focused existing API tests for notes/library behavior**

Run:

```bash
py -3.12 -m pytest tests/backend/test_api.py -q -k "notes or library_page_preserves_delete_and_media_logic"
```

Expected: PASS for selected tests. If this fails because of unrelated pre-existing dirty frontend or Feishu assertions, stop and report the exact failing test names and whether the failure is outside Stage 4.

- [ ] **Step 3: Run diff whitespace check**

Run:

```bash
git diff --check -- backend/app/api/notes.py tests/backend/test_notes_xhs_serializer.py
```

Expected: no output.

---

## Task 4: Stage and commit only Stage 4 hunks if authorized

**Files:**

- Stage: `tests/backend/test_notes_xhs_serializer.py`
- Partially stage: `backend/app/api/notes.py` serializer mapper hunks only
- Do not stage unrelated Feishu/score/rating hunks in `backend/app/api/notes.py`.

- [ ] **Step 1: Inspect mixed file diff**

Run:

```bash
git diff -- backend/app/api/notes.py
```

Expected: the diff contains both:

- unrelated Feishu/score/rating hunks already present before this task
- new Stage 4 serializer mapper hunks

- [ ] **Step 2: Stage the new test file**

Run:

```bash
git add -- tests/backend/test_notes_xhs_serializer.py
```

- [ ] **Step 3: Stage only serializer hunks in notes.py**

Use interactive patch staging:

```bash
git add -p -- backend/app/api/notes.py
```

Stage these hunks only:

- import `XhsContentMapping, map_xhs_content`
- `_xhs_content_mapping`
- `_legacy_note_engagement_metrics`
- `_note_engagement_metrics` replacement
- `_serialize_note` mapper fallback variables and returned `asset_urls` / `cover_url` / `video_url` / `video_addr`

Do not stage these existing unrelated lines:

```python
"cover_type": result.raw_payload.get("封面类型") if isinstance(result.raw_payload, dict) else None,
"title_type": result.raw_payload.get("标题类型") if isinstance(result.raw_payload, dict) else None,
"score": result.score,
"rating": result.rating,
```

If interactive patch staging is unavailable in the current harness, do not improvise with broad staging. Instead, stop and report that partial staging needs either user-assisted `git add -p` or a temporary index-only staging procedure.

- [ ] **Step 4: Verify staged diff**

Run:

```bash
git diff --staged --name-only
git diff --staged -- backend/app/api/notes.py tests/backend/test_notes_xhs_serializer.py
git diff --staged --check
```

Expected staged files:

```text
backend/app/api/notes.py
tests/backend/test_notes_xhs_serializer.py
```

Expected staged diff: no Feishu/score/rating hunks.

- [ ] **Step 5: Commit only after explicit user authorization**

This project requires explicit user authorization before commits. If authorized, run:

```bash
git commit -m "refactor: route xhs note serialization through mapper"
```

If commit attribution is required by the runtime, use:

```text
refactor: route xhs note serialization through mapper

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
```

Do not push.

---

## Self-Review

### Spec coverage

- Mapper is used in real notes serialization path: Task 2.
- Response shape unchanged: Task 1 asserts exact serializer keys; Task 2 only changes existing values/fallbacks.
- No DB/Alembic/batch-save/ownership changes: Scope firewall and Task 2 file list restrict this.
- Existing dirty Feishu hunks protected: Dirty workspace warning and Task 4 partial staging rules.
- Focused verification defined: Task 3.

### Placeholder scan

- No `TBD`, `TODO`, `implement later`, or vague placeholder instructions remain.
- Code blocks are complete for test and implementation steps.

### Type consistency

- `XhsContentMapping` and `map_xhs_content` match `backend/app/adapters/xhs/mappers.py`.
- Test fake DB methods match `_get_note_assets()` and `_get_feishu_analysis_result()` usage: `scalars(...).all()` and `scalar(...)`.
- Serializer response keys match current `_serialize_note` output.

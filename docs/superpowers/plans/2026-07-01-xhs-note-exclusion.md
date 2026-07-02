# XHS Note Exclusion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a negative-sample exclusion layer so low-value/GEO/unwanted XHS notes are hidden, remembered, skipped on future imports, and marked `已废弃` in Feishu instead of physically deleted.

**Architecture:** Add a `note_exclusions` table keyed by `(user_id, platform, platform_note_id)`, route note listing/import through that table, and keep Feishu simple by extending the existing `分析状态` select options with `已废弃`. Centralize exclusion matching/marking in a focused service so API handlers and one-off cleanup use the same behavior.

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy ORM, Alembic, pytest/TestClient, existing Feishu Bitable integration.

---

## File Map

- Create: `backend/app/models/note_exclusion.py` — SQLAlchemy model for remembered excluded notes.
- Modify: `backend/app/models/__init__.py` — export `NoteExclusion`.
- Create: `backend/alembic/versions/20260701_add_note_exclusions.py` — migration for the table and indexes.
- Create: `backend/app/services/note_exclusion_service.py` — exclusion checks, candidate building, marking notes excluded, and Feishu field payload construction.
- Modify: `backend/app/services/feishu_bitable_service.py` — add `已废弃` analysis status, ensure existing Feishu select options include it, and expose a record update helper used by exclusion service.
- Modify: `backend/app/api/notes.py` — default-hide excluded notes, skip excluded notes during `/batch-save`, and add `POST /api/notes/exclusions/mark`.
- Modify: `tests/backend/test_feishu_integration.py` — verify Feishu field definitions/options include `已废弃` and existing field options are updated.
- Create: `tests/backend/test_note_exclusions.py` — verify exclusion marking, default hiding, import skipping, and current cleanup candidate rules.

---

### Task 1: Add the `NoteExclusion` model and migration

**Files:**
- Create: `backend/app/models/note_exclusion.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/20260701_add_note_exclusions.py`
- Test: `tests/backend/test_note_exclusions.py`

- [ ] **Step 1: Write the failing model metadata test**

Create `tests/backend/test_note_exclusions.py` with this initial content:

```python
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import Base, get_db
from backend.app.core.security import create_access_token, hash_password
from backend.app.main import app
from backend.app.models import Note, NoteExclusion, User

client = TestClient(app)


def _override_database(tmp_path, name="note-exclusions.db"):
    engine = create_engine(f"sqlite:///{tmp_path / name}", connect_args={"check_same_thread": False})
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


def _create_user(SessionLocal, username="exclusion-owner"):
    db = SessionLocal()
    try:
        user = User(username=username, password_hash=hash_password("secret123"))
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id
    finally:
        db.close()


def _auth_headers(user_id: int):
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


def test_note_exclusion_model_is_registered_in_metadata():
    assert NoteExclusion.__tablename__ == "note_exclusions"
    assert "note_exclusions" in Base.metadata.tables
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
pytest tests/backend/test_note_exclusions.py::test_note_exclusion_model_is_registered_in_metadata -v
```

Expected: FAIL with an import error like `cannot import name 'NoteExclusion'`.

- [ ] **Step 3: Add the model**

Create `backend/app/models/note_exclusion.py`:

```python
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base
from backend.app.core.time import shanghai_now


class NoteExclusion(Base):
    __tablename__ = "note_exclusions"
    __table_args__ = (UniqueConstraint("user_id", "platform", "platform_note_id", name="uq_note_exclusions_user_platform_note"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    note_id: Mapped[Optional[int]] = mapped_column(ForeignKey("notes.id"), nullable=True, index=True)
    platform: Mapped[str] = mapped_column(String(32), index=True)
    platform_note_id: Mapped[str] = mapped_column(String(128), index=True)
    source_url: Mapped[str] = mapped_column(Text, default="")
    title: Mapped[str] = mapped_column(Text, default="")
    author_name: Mapped[str] = mapped_column(Text, default="")
    reason_code: Mapped[str] = mapped_column(String(64), index=True)
    reason_text: Mapped[str] = mapped_column(Text, default="")
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rating: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    external_record_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now)
```

Modify `backend/app/models/__init__.py`:

```python
from backend.app.models.note_exclusion import NoteExclusion
```

Add `"NoteExclusion"` to `__all__` near `"NoteComment"`.

- [ ] **Step 4: Add the Alembic migration**

Create `backend/alembic/versions/20260701_add_note_exclusions.py`:

```python
"""add note exclusions

Revision ID: 20260701_note_exclusions
Revises: 20260625_analysis_score_rating
Create Date: 2026-07-01
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260701_note_exclusions"
down_revision: Union[str, Sequence[str], None] = "20260625_analysis_score_rating"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "note_exclusions" not in tables:
        op.create_table(
            "note_exclusions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("note_id", sa.Integer(), sa.ForeignKey("notes.id"), nullable=True),
            sa.Column("platform", sa.String(length=32), nullable=False),
            sa.Column("platform_note_id", sa.String(length=128), nullable=False),
            sa.Column("source_url", sa.Text(), nullable=False, server_default=""),
            sa.Column("title", sa.Text(), nullable=False, server_default=""),
            sa.Column("author_name", sa.Text(), nullable=False, server_default=""),
            sa.Column("reason_code", sa.String(length=64), nullable=False),
            sa.Column("reason_text", sa.Text(), nullable=False, server_default=""),
            sa.Column("score", sa.Float(), nullable=True),
            sa.Column("rating", sa.String(length=32), nullable=True),
            sa.Column("external_record_id", sa.String(length=128), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("user_id", "platform", "platform_note_id", name="uq_note_exclusions_user_platform_note"),
        )

    indexes = {index["name"] for index in inspector.get_indexes("note_exclusions")}
    if "ix_note_exclusions_user_id" not in indexes:
        op.create_index("ix_note_exclusions_user_id", "note_exclusions", ["user_id"])
    if "ix_note_exclusions_note_id" not in indexes:
        op.create_index("ix_note_exclusions_note_id", "note_exclusions", ["note_id"])
    if "ix_note_exclusions_platform" not in indexes:
        op.create_index("ix_note_exclusions_platform", "note_exclusions", ["platform"])
    if "ix_note_exclusions_platform_note_id" not in indexes:
        op.create_index("ix_note_exclusions_platform_note_id", "note_exclusions", ["platform_note_id"])
    if "ix_note_exclusions_reason_code" not in indexes:
        op.create_index("ix_note_exclusions_reason_code", "note_exclusions", ["reason_code"])
    if "ix_note_exclusions_external_record_id" not in indexes:
        op.create_index("ix_note_exclusions_external_record_id", "note_exclusions", ["external_record_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "note_exclusions" in set(inspector.get_table_names()):
        op.drop_table("note_exclusions")
```

- [ ] **Step 5: Run the model test to verify it passes**

Run:

```bash
pytest tests/backend/test_note_exclusions.py::test_note_exclusion_model_is_registered_in_metadata -v
```

Expected: PASS.

- [ ] **Step 6: Check Alembic heads**

Run from repository root:

```bash
python -m alembic -c backend/alembic.ini heads
```

Expected: exactly one head, `20260701_note_exclusions`.

---

### Task 2: Extend Feishu `分析状态` with `已废弃`

**Files:**
- Modify: `backend/app/services/feishu_bitable_service.py`
- Modify: `tests/backend/test_feishu_integration.py`

- [ ] **Step 1: Write failing tests for Feishu status option support**

In `tests/backend/test_feishu_integration.py`, update `FakeFeishuClient.create_field` to preserve options:

```python
    def create_field(self, definition):
        field = {"field_name": definition["field_name"], "type": definition["type"]}
        if definition.get("options"):
            field["property"] = {"options": [{"name": option} for option in definition["options"]]}
        self.fields.append(field)
        self.created_fields.append(field)
        return field
```

Add this method to `FakeFeishuClient`:

```python
    def update_field(self, field_id, definition):
        updated = {"field_id": field_id, "field_name": definition["field_name"], "type": definition["type"]}
        if definition.get("options"):
            updated["property"] = {"options": [{"name": option} for option in definition["options"]]}
        self.updated_fields = getattr(self, "updated_fields", [])
        self.updated_fields.append(updated)
        for field in self.fields:
            if field.get("field_id") == field_id:
                field.update(updated)
        return updated
```

Add tests:

```python
def test_feishu_analysis_status_definition_includes_discarded():
    analysis_status = next(item for item in feishu_bitable_service.FEISHU_FIELD_DEFINITIONS if item["field_name"] == "分析状态")

    assert "已废弃" in analysis_status["options"]


def test_ensure_feishu_fields_updates_existing_analysis_status_options():
    fake = FakeFeishuClient()
    fake.fields = [
        {
            "field_id": "fld_analysis_status",
            "field_name": "分析状态",
            "type": 3,
            "property": {"options": [{"name": "待分析"}, {"name": "分析中"}, {"name": "已完成"}]},
        }
    ]

    result = feishu_bitable_service.ensure_feishu_fields(fake)

    assert result["status"] == "ok"
    assert getattr(fake, "updated_fields", [])[0]["field_id"] == "fld_analysis_status"
    updated_options = [item["name"] for item in fake.updated_fields[0]["property"]["options"]]
    assert "已废弃" in updated_options
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/backend/test_feishu_integration.py::test_feishu_analysis_status_definition_includes_discarded tests/backend/test_feishu_integration.py::test_ensure_feishu_fields_updates_existing_analysis_status_options -v
```

Expected: first test FAILS because `已废弃` is missing; second test FAILS because existing field options are skipped, not updated.

- [ ] **Step 3: Implement Feishu option support**

Modify `backend/app/services/feishu_bitable_service.py`:

```python
ANALYSIS_STATUS_OPTIONS = ["待分析", "分析中", "已完成", "已废弃"]
```

Add a client method after `create_field`:

```python
    def update_field(self, field_id: str, definition: dict[str, Any]) -> dict[str, Any]:
        body: dict[str, Any] = {
            "field_name": definition["field_name"],
            "type": FEISHU_FIELD_TYPE_MAP.get(str(definition.get("type")), 1),
        }
        options = definition.get("options") or []
        if options:
            body["property"] = {"options": [{"name": str(option)} for option in options]}
        payload = self._request("PUT", f"/bitable/v1/apps/{self.bitable_app_token}/tables/{self.table_id}/fields/{field_id}", json=body)
        return dict(payload.get("data", {}).get("field", payload.get("data", {})))
```

Add helper functions near `ensure_feishu_fields`:

```python
def _field_option_names(field: dict[str, Any]) -> set[str]:
    property_value = field.get("property") if isinstance(field.get("property"), dict) else {}
    options = property_value.get("options") if isinstance(property_value, dict) else []
    names: set[str] = set()
    if isinstance(options, list):
        for option in options:
            if isinstance(option, dict) and option.get("name"):
                names.add(str(option["name"]))
            elif isinstance(option, str):
                names.add(option)
    return names


def _field_id(field: dict[str, Any]) -> str:
    return str(field.get("field_id") or field.get("fieldId") or "")
```

Replace `ensure_feishu_fields` with:

```python
def ensure_feishu_fields(client: Any) -> dict[str, Any]:
    existing = client.list_fields()
    existing_by_name = {str(field.get("field_name")): field for field in existing if field.get("field_name")}
    existing_names = set(existing_by_name)
    created: list[dict[str, Any]] = []
    updated: list[dict[str, Any]] = []
    skipped: list[str] = []
    for definition in FEISHU_FIELD_DEFINITIONS:
        field_name = definition["field_name"]
        aliases = FIELD_ALIASES.get(field_name, [])
        existing_name = field_name if field_name in existing_names else next((alias for alias in aliases if alias in existing_names), "")
        if existing_name:
            field = existing_by_name[existing_name]
            options = definition.get("options") or []
            missing_options = [option for option in options if option not in _field_option_names(field)]
            field_id = _field_id(field)
            if missing_options and field_id and hasattr(client, "update_field"):
                update_definition = dict(definition)
                update_definition["field_name"] = existing_name
                existing_options = list(_field_option_names(field))
                merged_options = [*existing_options]
                for option in options:
                    if option not in merged_options:
                        merged_options.append(option)
                update_definition["options"] = merged_options
                updated.append(client.update_field(field_id, update_definition))
            skipped.append(field_name)
            continue
        created.append(client.create_field(definition))
        existing_names.add(field_name)
    return {
        "dry_run": False,
        "status": "ok",
        "created_count": len(created),
        "updated_count": len(updated),
        "skipped_count": len(skipped),
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "fields": FEISHU_FIELD_DEFINITIONS,
    }
```

- [ ] **Step 4: Run Feishu tests**

Run:

```bash
pytest tests/backend/test_feishu_integration.py::test_feishu_analysis_status_definition_includes_discarded tests/backend/test_feishu_integration.py::test_ensure_feishu_fields_updates_existing_analysis_status_options tests/backend/test_feishu_integration.py::test_feishu_ensure_fields_dry_run_returns_expected_template -v
```

Expected: PASS.

---

### Task 3: Implement exclusion service and cleanup candidate rules

**Files:**
- Create: `backend/app/services/note_exclusion_service.py`
- Test: `tests/backend/test_note_exclusions.py`

- [ ] **Step 1: Write failing service tests**

Append to `tests/backend/test_note_exclusions.py`:

```python
from backend.app.models import NoteAnalysisResult
from backend.app.services.note_exclusion_service import build_current_cleanup_candidates, is_note_excluded, mark_notes_excluded


def _create_note_with_analysis(SessionLocal, user_id: int, *, note_id: str, title: str, content: str = "", score=None, rating=None, subject="", status="分析完成"):
    db = SessionLocal()
    try:
        note = Note(user_id=user_id, platform_account_id=1, platform="xhs", note_id=note_id, title=title, content=content, author_name="作者")
        db.add(note)
        db.flush()
        analysis = NoteAnalysisResult(
            user_id=user_id,
            note_id=note.id,
            source="feishu",
            analysis_status=status,
            score=score,
            rating=rating,
            subject_object=subject,
            external_record_id=f"rec_{note_id}",
        )
        db.add(analysis)
        db.commit()
        db.refresh(note)
        return note.id
    finally:
        db.close()


def test_mark_notes_excluded_creates_memory_and_is_idempotent(tmp_path):
    SessionLocal = _override_database(tmp_path, "mark-excluded.db")
    try:
        user_id = _create_user(SessionLocal)
        note_id = _create_note_with_analysis(SessionLocal, user_id, note_id="xhs-low", title="低分素材", score=2.0, rating="低表现内容", subject="浴缸")
        db = SessionLocal()
        try:
            first = mark_notes_excluded(db, user_id=user_id, note_ids=[note_id], reason_code="low_score_bathtub", reason_text="浴缸低分", client=None)
            second = mark_notes_excluded(db, user_id=user_id, note_ids=[note_id], reason_code="low_score_bathtub", reason_text="浴缸低分", client=None)
            exclusion = db.scalar(select(NoteExclusion).where(NoteExclusion.platform_note_id == "xhs-low"))

            assert first["excluded_count"] == 1
            assert second["excluded_count"] == 1
            assert db.query(NoteExclusion).count() == 1
            assert exclusion.reason_code == "low_score_bathtub"
            assert exclusion.score == 2.0
            assert is_note_excluded(db, user_id=user_id, platform="xhs", platform_note_id="xhs-low") is True
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_build_current_cleanup_candidates_matches_strict_rules(tmp_path):
    SessionLocal = _override_database(tmp_path, "cleanup-candidates.db")
    try:
        user_id = _create_user(SessionLocal)
        geo_id = _create_note_with_analysis(SessionLocal, user_id, note_id="geo-1", title="GEO 可以做什么", score=None, subject="")
        square_id = _create_note_with_analysis(SessionLocal, user_id, note_id="bath-square", title="粉色方形浴缸", score=9.0, subject="浴缸")
        low_bath_id = _create_note_with_analysis(SessionLocal, user_id, note_id="bath-low", title="小户型浴缸", score=6.5, subject="浴缸")
        high_bath_id = _create_note_with_analysis(SessionLocal, user_id, note_id="bath-high", title="浴缸避坑指南", score=9.0, subject="浴缸")
        low_other_id = _create_note_with_analysis(SessionLocal, user_id, note_id="other-low", title="飞书教程", score=3.0, subject="安装服务")
        db = SessionLocal()
        try:
            candidates = build_current_cleanup_candidates(db, user_id=user_id, strict=True)
            by_note_id = {item["note_id"]: item for item in candidates}

            assert geo_id in by_note_id
            assert by_note_id[geo_id]["reason_code"] == "geo"
            assert square_id in by_note_id
            assert by_note_id[square_id]["reason_code"] == "square_wall_bathtub"
            assert low_bath_id in by_note_id
            assert by_note_id[low_bath_id]["reason_code"] == "low_score_bathtub"
            assert low_other_id in by_note_id
            assert by_note_id[low_other_id]["reason_code"] == "low_score_non_bathtub"
            assert high_bath_id not in by_note_id
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/backend/test_note_exclusions.py::test_mark_notes_excluded_creates_memory_and_is_idempotent tests/backend/test_note_exclusions.py::test_build_current_cleanup_candidates_matches_strict_rules -v
```

Expected: FAIL because `backend.app.services.note_exclusion_service` does not exist.

- [ ] **Step 3: Implement the service**

Create `backend/app/services/note_exclusion_service.py`:

```python
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.time import shanghai_now
from backend.app.models import Note, NoteAnalysisResult, NoteExclusion

BATH_WORDS = ["浴缸", "泡澡", "泡澡池", "浴室", "卫生间", "主卫", "洗澡", "澡池", "自砌浴缸"]
SQUARE_WALL_BATHTUB_WORDS = ["方形贴墙浴缸", "贴墙浴缸", "方形浴缸"]
GEO_WORDS = ["geo", "seo/geo", "seo geo", "ai搜索", "ai 搜索", "生成式引擎优化"]
LOW_SCORE_THRESHOLD = 7.0

REASON_TEXT = {
    "geo": "GEO相关，当前清理规则排除",
    "square_wall_bathtub": "方形/贴墙浴缸相关，当前清理规则排除",
    "low_score_non_bathtub": "非浴缸相关且评分低于7，按严格清理规则废弃",
    "low_score_bathtub": "浴缸相关但评分低于7，按严格清理规则废弃",
    "manual_excluded": "人工标记废弃",
}


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n".join(_as_text(item) for item in value)
    if isinstance(value, dict):
        return "\n".join(_as_text(item) for item in value.values())
    return str(value)


def _note_text(note: Note, analysis: NoteAnalysisResult | None) -> str:
    chunks = [note.title, note.content, note.author_name, note.note_id]
    if analysis is not None:
        chunks.extend([
            analysis.analysis_status,
            analysis.subject_object,
            analysis.content_type,
            analysis.core_points,
            analysis.target_audience,
            analysis.title_hook,
            analysis.content_structure,
            analysis.reuse_value,
            analysis.search_attribute,
            analysis.rating,
            analysis.analysis_note,
            analysis.reusable_models,
            analysis.raw_payload,
        ])
    return "\n".join(_as_text(chunk) for chunk in chunks if chunk is not None).lower()


def _contains_any(text: str, words: list[str]) -> bool:
    return any(word.lower() in text for word in words)


def is_note_excluded(db: Session, *, user_id: int, platform: str, platform_note_id: str) -> bool:
    if not platform_note_id:
        return False
    return db.scalar(
        select(NoteExclusion.id).where(
            NoteExclusion.user_id == user_id,
            NoteExclusion.platform == platform,
            NoteExclusion.platform_note_id == platform_note_id,
        )
    ) is not None


def _analysis_for_note(db: Session, note_id: int) -> NoteAnalysisResult | None:
    return db.scalar(select(NoteAnalysisResult).where(NoteAnalysisResult.note_id == note_id, NoteAnalysisResult.source == "feishu"))


def _note_url(note: Note) -> str:
    raw = note.raw_json if isinstance(note.raw_json, dict) else {}
    return str(raw.get("note_url") or raw.get("url") or raw.get("share_url") or f"https://www.xiaohongshu.com/explore/{note.note_id}")


def _reason_for_note(note: Note, analysis: NoteAnalysisResult | None, *, strict: bool) -> str | None:
    text = _note_text(note, analysis)
    if _contains_any(text, GEO_WORDS):
        return "geo"
    if _contains_any(text, SQUARE_WALL_BATHTUB_WORDS):
        return "square_wall_bathtub"
    score = analysis.score if analysis is not None else None
    if score is None or score >= LOW_SCORE_THRESHOLD:
        return None
    is_bath = _contains_any(text, BATH_WORDS)
    if is_bath and strict:
        return "low_score_bathtub"
    if not is_bath:
        return "low_score_non_bathtub"
    return None


def build_current_cleanup_candidates(db: Session, *, user_id: int, strict: bool = True) -> list[dict[str, Any]]:
    notes = db.scalars(select(Note).where(Note.user_id == user_id, Note.platform == "xhs").order_by(Note.id.asc())).all()
    candidates: list[dict[str, Any]] = []
    for note in notes:
        analysis = _analysis_for_note(db, note.id)
        reason_code = _reason_for_note(note, analysis, strict=strict)
        if reason_code is None:
            continue
        candidates.append({
            "note_id": note.id,
            "platform_note_id": note.note_id,
            "title": note.title,
            "score": analysis.score if analysis else None,
            "rating": analysis.rating if analysis else None,
            "external_record_id": analysis.external_record_id if analysis else None,
            "reason_code": reason_code,
            "reason_text": REASON_TEXT[reason_code],
        })
    return candidates


def _append_note(existing: str | None, reason_text: str) -> str:
    message = f"系统已废弃：{reason_text}"
    current = (existing or "").strip()
    if message in current:
        return current
    return f"{current}\n{message}".strip() if current else message


def _feishu_exclusion_fields(reason_text: str, existing_note: str | None = None) -> dict[str, Any]:
    return {
        "分析状态": "已废弃",
        "内容利用方式": ["废弃"],
        "分析备注": _append_note(existing_note, reason_text),
    }


def mark_notes_excluded(db: Session, *, user_id: int, note_ids: list[int], reason_code: str, reason_text: str = "", client: Any | None = None) -> dict[str, Any]:
    unique_ids = list(dict.fromkeys(note_ids))
    notes = db.scalars(select(Note).where(Note.user_id == user_id, Note.id.in_(unique_ids))).all()
    by_id = {note.id: note for note in notes}
    now = shanghai_now()
    excluded_count = 0
    skipped_count = 0
    feishu_updated_count = 0
    errors: list[dict[str, Any]] = []
    final_reason_text = reason_text or REASON_TEXT.get(reason_code, reason_code)

    for note_id in unique_ids:
        note = by_id.get(note_id)
        if note is None:
            skipped_count += 1
            errors.append({"note_id": note_id, "error": "Note not found"})
            continue
        analysis = _analysis_for_note(db, note.id)
        exclusion = db.scalar(
            select(NoteExclusion).where(
                NoteExclusion.user_id == user_id,
                NoteExclusion.platform == note.platform,
                NoteExclusion.platform_note_id == note.note_id,
            )
        )
        if exclusion is None:
            exclusion = NoteExclusion(user_id=user_id, platform=note.platform, platform_note_id=note.note_id)
            db.add(exclusion)
        exclusion.note_id = note.id
        exclusion.source_url = _note_url(note)
        exclusion.title = note.title or ""
        exclusion.author_name = note.author_name or ""
        exclusion.reason_code = reason_code
        exclusion.reason_text = final_reason_text
        exclusion.score = analysis.score if analysis else None
        exclusion.rating = analysis.rating if analysis else None
        exclusion.external_record_id = analysis.external_record_id if analysis else None
        exclusion.updated_at = now
        if analysis is not None:
            analysis.analysis_status = "已废弃"
            analysis.reuse_value = "废弃"
            analysis.analysis_note = _append_note(analysis.analysis_note, final_reason_text)
            analysis.updated_at = now
        if client is not None and analysis is not None and analysis.external_record_id:
            try:
                client.update_record(analysis.external_record_id, _feishu_exclusion_fields(final_reason_text, analysis.analysis_note))
                feishu_updated_count += 1
            except Exception as exc:
                errors.append({"note_id": note.id, "record_id": analysis.external_record_id, "error": str(exc)})
        excluded_count += 1
    db.commit()
    return {
        "excluded_count": excluded_count,
        "skipped_count": skipped_count,
        "feishu_updated_count": feishu_updated_count,
        "feishu_failed_count": len([error for error in errors if error.get("record_id")]),
        "errors": errors,
    }
```

- [ ] **Step 4: Run service tests**

Run:

```bash
pytest tests/backend/test_note_exclusions.py::test_mark_notes_excluded_creates_memory_and_is_idempotent tests/backend/test_note_exclusions.py::test_build_current_cleanup_candidates_matches_strict_rules -v
```

Expected: PASS.

---

### Task 4: Hide excluded notes and skip excluded imports

**Files:**
- Modify: `backend/app/api/notes.py`
- Test: `tests/backend/test_note_exclusions.py`

- [ ] **Step 1: Write failing API tests**

Append to `tests/backend/test_note_exclusions.py`:

```python
def test_notes_list_hides_excluded_notes_by_default(tmp_path):
    SessionLocal = _override_database(tmp_path, "hide-excluded.db")
    try:
        user_id = _create_user(SessionLocal)
        hidden_id = _create_note_with_analysis(SessionLocal, user_id, note_id="hidden-xhs", title="GEO 可以做什么", score=2.0, subject="")
        visible_id = _create_note_with_analysis(SessionLocal, user_id, note_id="visible-xhs", title="浴缸避坑指南", score=9.0, subject="浴缸")
        db = SessionLocal()
        try:
            mark_notes_excluded(db, user_id=user_id, note_ids=[hidden_id], reason_code="geo", reason_text="GEO相关", client=None)
        finally:
            db.close()

        response = client.get("/api/notes", headers=_auth_headers(user_id), params={"platform": "xhs", "page_size": 100})

        assert response.status_code == 200
        ids = [item["id"] for item in response.json()["items"]]
        assert visible_id in ids
        assert hidden_id not in ids
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_batch_save_skips_excluded_note_ids(tmp_path):
    SessionLocal = _override_database(tmp_path, "skip-import.db")
    try:
        user_id = _create_user(SessionLocal)
        db = SessionLocal()
        try:
            user = db.get(User, user_id)
            account = __import__("backend.app.models", fromlist=["PlatformAccount"]).PlatformAccount(user_id=user.id, platform="xhs", name="pc", sub_type="pc")
            db.add(account)
            db.flush()
            note = Note(user_id=user_id, platform_account_id=account.id, platform="xhs", note_id="excluded-import", title="旧标题", content="旧内容", author_name="作者")
            db.add(note)
            db.flush()
            note_id = note.id
            db.add(NoteExclusion(user_id=user_id, note_id=note.id, platform="xhs", platform_note_id="excluded-import", reason_code="geo", reason_text="GEO相关"))
            db.commit()
            account_id = account.id
        finally:
            db.close()

        response = client.post(
            "/api/notes/batch-save",
            headers=_auth_headers(user_id),
            json={
                "account_id": account_id,
                "notes": [
                    {"note_id": "excluded-import", "title": "新标题不应写入", "content": "新内容", "author_name": "作者"},
                    {"note_id": "fresh-import", "title": "新素材", "content": "正文", "author_name": "作者"},
                ],
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["saved_count"] == 1
        assert body["skipped_count"] == 1
        assert body["skipped_items"][0]["note_id"] == "excluded-import"
        db = SessionLocal()
        try:
            old_note = db.get(Note, note_id)
            fresh_note = db.scalar(select(Note).where(Note.note_id == "fresh-import"))
            assert old_note.title == "旧标题"
            assert fresh_note is not None
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/backend/test_note_exclusions.py::test_notes_list_hides_excluded_notes_by_default tests/backend/test_note_exclusions.py::test_batch_save_skips_excluded_note_ids -v
```

Expected: first FAILS because excluded notes still appear; second FAILS because `/batch-save` overwrites excluded notes and lacks `skipped_count`.

- [ ] **Step 3: Modify imports in `backend/app/api/notes.py`**

Update model imports:

```python
from backend.app.models import AccountCookieVersion, AiDraft, Note, NoteAnalysisResult, NoteAsset, NoteComment, NoteExclusion, PlatformAccount, Tag, User, note_tags
```

Add service import:

```python
from backend.app.services.note_exclusion_service import is_note_excluded
```

- [ ] **Step 4: Exclude notes in list/filter/ids queries**

In `get_note_filter_options`, add this condition inside the `.where(...)` block:

```python
~Note.id.in_(select(NoteExclusion.note_id).where(NoteExclusion.user_id == current_user.id, NoteExclusion.note_id.is_not(None)))
```

In `get_note_ids`, add before platform filtering:

```python
statement = statement.where(
    ~Note.id.in_(select(NoteExclusion.note_id).where(NoteExclusion.user_id == current_user.id, NoteExclusion.note_id.is_not(None)))
)
```

In `get_notes`, add after the initial statement creation:

```python
statement = statement.where(
    ~Note.id.in_(select(NoteExclusion.note_id).where(NoteExclusion.user_id == current_user.id, NoteExclusion.note_id.is_not(None)))
)
```

- [ ] **Step 5: Skip excluded notes in `/batch-save`**

In `batch_save_notes`, initialize skipped tracking after `saved_notes`:

```python
    skipped_items: list[dict[str, str]] = []
```

At the top of the `for note_payload in payload.notes:` loop, before looking up `existing`, add:

```python
        if is_note_excluded(db, user_id=current_user.id, platform=account.platform, platform_note_id=note_payload.note_id):
            skipped_items.append({"note_id": note_payload.note_id, "reason": "excluded"})
            continue
```

Update the return payload:

```python
    return {
        "saved_count": len(saved_notes),
        "skipped_count": len(skipped_items),
        "skipped_items": skipped_items,
        "items": [_serialize_note_with_tags(db, note) for note in saved_notes],
    }
```

- [ ] **Step 6: Run API tests**

Run:

```bash
pytest tests/backend/test_note_exclusions.py::test_notes_list_hides_excluded_notes_by_default tests/backend/test_note_exclusions.py::test_batch_save_skips_excluded_note_ids -v
```

Expected: PASS.

---

### Task 5: Add the exclusion mark API

**Files:**
- Modify: `backend/app/api/notes.py`
- Test: `tests/backend/test_note_exclusions.py`

- [ ] **Step 1: Write failing endpoint test**

Append to `tests/backend/test_note_exclusions.py`:

```python
def test_mark_exclusions_endpoint_marks_notes_and_hides_them(tmp_path):
    SessionLocal = _override_database(tmp_path, "endpoint-mark.db")
    try:
        user_id = _create_user(SessionLocal)
        note_id = _create_note_with_analysis(SessionLocal, user_id, note_id="endpoint-xhs", title="小户型浴缸低分", score=2.0, rating="低表现内容", subject="浴缸")

        response = client.post(
            "/api/notes/exclusions/mark",
            headers=_auth_headers(user_id),
            json={"note_ids": [note_id], "reason_code": "low_score_bathtub", "reason_text": "浴缸低分", "sync_feishu": False},
        )

        assert response.status_code == 200
        assert response.json()["excluded_count"] == 1
        db = SessionLocal()
        try:
            exclusion = db.scalar(select(NoteExclusion).where(NoteExclusion.note_id == note_id))
            analysis = db.scalar(select(NoteAnalysisResult).where(NoteAnalysisResult.note_id == note_id))
            assert exclusion.reason_code == "low_score_bathtub"
            assert analysis.analysis_status == "已废弃"
            assert analysis.reuse_value == "废弃"
        finally:
            db.close()

        list_response = client.get("/api/notes", headers=_auth_headers(user_id), params={"platform": "xhs", "page_size": 100})
        assert note_id not in [item["id"] for item in list_response.json()["items"]]
    finally:
        app.dependency_overrides.pop(get_db, None)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/backend/test_note_exclusions.py::test_mark_exclusions_endpoint_marks_notes_and_hides_them -v
```

Expected: FAIL with HTTP 404 for `/api/notes/exclusions/mark`.

- [ ] **Step 3: Add request model and route**

In `backend/app/api/notes.py`, add service import:

```python
from backend.app.services.note_exclusion_service import build_current_cleanup_candidates, is_note_excluded, mark_notes_excluded
```

Add request model near other request models:

```python
class MarkNoteExclusionsRequest(BaseModel):
    note_ids: list[int] = Field(min_length=1)
    reason_code: str = Field(min_length=1, max_length=64)
    reason_text: str = ""
    sync_feishu: bool = False
```

Add route before `@router.get("/{note_id}")` so it does not conflict with path params:

```python
@router.post("/exclusions/mark")
def mark_note_exclusions(
    payload: MarkNoteExclusionsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    client = None
    if payload.sync_feishu:
        from backend.app.api.feishu_integration import _client_or_error, _get_config

        client = _client_or_error(_get_config(db, current_user.id))
    return mark_notes_excluded(
        db,
        user_id=current_user.id,
        note_ids=payload.note_ids,
        reason_code=payload.reason_code,
        reason_text=payload.reason_text,
        client=client,
    )


@router.get("/exclusions/current-cleanup-candidates")
def get_current_cleanup_candidates(
    strict: bool = True,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {"items": build_current_cleanup_candidates(db, user_id=current_user.id, strict=strict)}
```

- [ ] **Step 4: Run endpoint test**

Run:

```bash
pytest tests/backend/test_note_exclusions.py::test_mark_exclusions_endpoint_marks_notes_and_hides_them -v
```

Expected: PASS.

---

### Task 6: Apply the current cleanup safely

**Files:**
- No source changes if previous tasks are complete.
- Uses API/service behavior already tested.

- [ ] **Step 1: Preview candidates through the API**

Run the backend or use a test/auth context only if already running. If using direct database inspection, run this read-only command from repository root:

```bash
python - <<'PY'
from backend.app.core.database import SessionLocal
from backend.app.services.note_exclusion_service import build_current_cleanup_candidates

with SessionLocal() as db:
    # Replace 1 only if the active user id differs in the local database.
    candidates = build_current_cleanup_candidates(db, user_id=1, strict=True)
    print(len(candidates))
    for item in candidates:
        print(item["note_id"], item["platform_note_id"], item["reason_code"], item["score"], item["title"])
PY
```

Expected: prints the current strict cleanup candidates, including GEO and square/贴墙浴缸 records. If user id `1` is not the active user, query `select id, username from users` first and rerun with the correct id.

- [ ] **Step 2: Mark candidates excluded locally first**

Run after visually checking the candidate list:

```bash
python - <<'PY'
from collections import defaultdict
from backend.app.core.database import SessionLocal
from backend.app.services.note_exclusion_service import build_current_cleanup_candidates, mark_notes_excluded, REASON_TEXT

USER_ID = 1
with SessionLocal() as db:
    candidates = build_current_cleanup_candidates(db, user_id=USER_ID, strict=True)
    grouped = defaultdict(list)
    for item in candidates:
        grouped[item["reason_code"]].append(item["note_id"])
    for reason_code, note_ids in grouped.items():
        result = mark_notes_excluded(db, user_id=USER_ID, note_ids=note_ids, reason_code=reason_code, reason_text=REASON_TEXT[reason_code], client=None)
        print(reason_code, result)
PY
```

Expected: each group reports `excluded_count` equal to its note count and no unexpected `Note not found` errors.

- [ ] **Step 3: Sync Feishu status if credentials are available**

If Feishu config is enabled and credentials are available, run the API with `sync_feishu=true` or use the endpoint from the UI/backend auth context. Expected Feishu updates per record:

```json
{
  "分析状态": "已废弃",
  "内容利用方式": ["废弃"],
  "分析备注": "系统已废弃：<reason>"
}
```

If Feishu API fails, do not roll back local exclusions. Record the failed records and report them as deferred Feishu sync.

- [ ] **Step 4: Verify content library is clean**

Run:

```bash
pytest tests/backend/test_note_exclusions.py -v
```

Expected: all note exclusion tests pass. Then open the content library or call `/api/notes?platform=xhs&page_size=100`; excluded note IDs should not appear.

---

### Task 7: Full verification

**Files:**
- No new files.

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
pytest tests/backend/test_note_exclusions.py tests/backend/test_feishu_integration.py -v
```

Expected: PASS.

- [ ] **Step 2: Run existing broad backend smoke tests**

Run:

```bash
pytest tests/backend/test_api.py -v
```

Expected: PASS. If failures mention expected source strings, update tests only if the behavior changed intentionally and the assertion is stale.

- [ ] **Step 3: Check Alembic heads gate**

Run:

```bash
python -m alembic -c backend/alembic.ini heads
```

Expected: exactly one head, `20260701_note_exclusions`. If more than one head appears, stop and create a merge migration before reporting completion.

- [ ] **Step 4: Report state**

Report:

```text
工作区: E:/小红书
分支: master
已实现: note_exclusions 废弃库、内容库默认隐藏、batch-save 跳过、飞书 已废弃 状态支持
已验证: <commands and pass/fail>
已清理数据: <excluded_count by reason>
飞书同步: <updated/failed/deferred>
未自动 git push，未自动 commit
```

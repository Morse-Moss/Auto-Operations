# XHS Analysis Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first usable 小红书分析中心 flow: keyword group / note range → data health check → sample exclusion → evidence-backed structured AI analysis → report snapshot → static HTML export → editable topic cards → draft skeletons.

**Architecture:** Add a focused analysis-center backend next to the existing XHS analytics API instead of expanding the current dashboard endpoint file. The backend owns all truth gates: real-data health checks, evidence pool construction, JSON validation, evidence ID validation, confidence caps, report persistence, HTML rendering, and draft skeleton creation. The frontend upgrades the existing 数据洞察 route into 小红书分析中心 while preserving the old lightweight metrics as supporting context.

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy 2, Alembic, Pydantic-style validation with standard library JSON, existing OpenAI-compatible text model client, React 19, Vite, Ant Design 6, TypeScript.

---

## Non-Negotiable Product Rules

- Do not fabricate data, metrics, evidence, comments, insight cards, topic cards, HTML reports, or draft evidence.
- No default text model means report creation must fail before model invocation.
- Below minimum data threshold means report creation must fail before model invocation.
- AI output must be JSON, must pass backend validation, and must reference only backend-generated `evidence_id` values.
- Failed model/schema/evidence validation saves a `failed` report snapshot with `error_message`; it must not show partial AI text as a report.
- Product UI must not include demo mode, fake data mode, or fake report generation.
- Test fixtures are allowed only in automated tests.
- Do not integrate external XHS tools (`redbook`, `xhs-toolkit`, TikHub, Selenium/ChromeDriver) in this version.
- Do not commit during execution unless the user explicitly authorizes commits; this project rule overrides generic frequent-commit advice.

## Existing Integration Points

- Existing route remains [frontend/src/app/router.tsx](../../../frontend/src/app/router.tsx): `/platforms/xhs/analytics` → `XhsAnalyticsPage`.
- Existing analytics API stays in [backend/app/api/platforms/xhs/analytics.py](../../../backend/app/api/platforms/xhs/analytics.py). New analysis-center API goes in a separate file.
- Existing models used as input:
  - [backend/app/models/keyword_group.py](../../../backend/app/models/keyword_group.py): `KeywordGroup`.
  - [backend/app/models/note.py](../../../backend/app/models/note.py): `Note`, `NoteComment`.
  - [backend/app/models/monitoring.py](../../../backend/app/models/monitoring.py): `MonitoringTarget`.
  - [backend/app/models/ai.py](../../../backend/app/models/ai.py): `ModelConfig`, `AiDraft`.
- Existing model client is in [backend/app/services/ai_service.py](../../../backend/app/services/ai_service.py).
- Existing model-config dependency patterns are in [backend/app/api/ai.py](../../../backend/app/api/ai.py).
- Existing frontend API helpers live in [frontend/src/lib/api.ts](../../../frontend/src/lib/api.ts).
- Existing frontend types live in [frontend/src/types/index.ts](../../../frontend/src/types/index.ts).

## File Map

### Backend files to create

- `backend/app/models/analysis_report.py` — SQLAlchemy report snapshot model.
- `backend/app/api/platforms/xhs/analysis_center.py` — FastAPI routes under `/xhs/analytics/analysis`.
- `backend/app/services/xhs_analysis_center_service.py` — health checks, note/comment selection, evidence pool, model invocation, validation, persistence, draft skeletons.
- `backend/app/services/xhs_analysis_report_renderer.py` — static HTML renderer from validated report data.
- `backend/alembic/versions/9f4c2b7e1a0d_add_analysis_reports_table.py` — migration.
- `tests/backend/test_xhs_analysis_center.py` — backend test coverage.

### Backend files to modify

- `backend/app/models/__init__.py` — export `AnalysisReport`.
- `backend/app/main.py` — include the new analysis-center router with `prefix="/api"`.
- `backend/app/services/ai_service.py` — add a structured prompt helper that returns raw JSON text from the existing OpenAI-compatible completion path.
- `backend/app/core/database.py` — add `analysis_reports` datetime columns to SQLite datetime normalization if the file contains a table-to-columns map in the current branch.

### Frontend files to modify

- `frontend/src/types/index.ts` — add analysis-center request/response types.
- `frontend/src/lib/api.ts` — add analysis-center API helpers.
- `frontend/src/pages/platforms/xhs/analytics-page.tsx` — upgrade the existing page into 小红书分析中心.
- `frontend/src/pages/platforms/xhs/keywords-page.tsx` — add analysis entry per keyword group.

---

## Task 1: Add `analysis_reports` model and migration

**Files:**
- Create: `backend/app/models/analysis_report.py`
- Create: `backend/alembic/versions/9f4c2b7e1a0d_add_analysis_reports_table.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/core/database.py` only if it currently normalizes SQLite datetimes through a table map
- Test: `tests/backend/test_xhs_analysis_center.py`

- [ ] **Step 1: Write model persistence tests**

Add the first tests to `tests/backend/test_xhs_analysis_center.py`:

```python
from __future__ import annotations

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from backend.app.core.database import Base
from backend.app.models.analysis_report import AnalysisReport
from backend.app.models.user import User


def _create_user(db: Session, username: str = "analysis-user") -> User:
    user = User(username=username, hashed_password="hashed")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_analysis_report_model_persists_json(db_session: Session):
    user = _create_user(db_session)
    report = AnalysisReport(
        user_id=user.id,
        platform="xhs",
        report_type="content_analysis",
        status="completed",
        title="AI 编程 - 小红书分析报告 - 2026-06-16",
        input_config={"keyword_group_id": 1, "excluded_note_ids": []},
        data_health={"status": "minimum", "can_generate": True},
        evidence_pool={"notes": [], "comments": [], "keywords": [], "metrics": [], "benchmarks": []},
        result_json={"summary": {"facts": [], "inferences": [], "recommendations": []}, "insight_cards": [], "topic_cards": [], "report_warnings": []},
        html_file_path="exports/xhs-analysis-report-u1-test.html",
    )
    db_session.add(report)
    db_session.commit()
    db_session.refresh(report)

    assert report.id > 0
    assert report.platform == "xhs"
    assert report.input_config["keyword_group_id"] == 1
    assert report.data_health["status"] == "minimum"
    assert report.evidence_pool["notes"] == []
    assert report.error_message is None


def test_analysis_reports_table_has_required_columns(db_session: Session):
    columns = {column["name"] for column in inspect(db_session.bind).get_columns("analysis_reports")}

    assert {
        "id",
        "user_id",
        "platform",
        "report_type",
        "status",
        "title",
        "input_config",
        "data_health",
        "evidence_pool",
        "result_json",
        "html_file_path",
        "source_task_id",
        "rerun_from_report_id",
        "error_message",
        "created_at",
        "started_at",
        "finished_at",
    }.issubset(columns)
```

If the current test suite does not already provide a `db_session` fixture, create one in this test file by following the existing `_override_database(tmp_path)` pattern in `tests/backend/test_api.py` and yielding a session after `Base.metadata.create_all(bind=engine)`.

- [ ] **Step 2: Run the new tests and verify the model does not exist yet**

Run:

```bash
pytest tests/backend/test_xhs_analysis_center.py::test_analysis_report_model_persists_json -v
```

Expected: fail with `ModuleNotFoundError` or import error for `backend.app.models.analysis_report`.

- [ ] **Step 3: Create the model**

Create `backend/app/models/analysis_report.py`:

```python
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base
from backend.app.core.time import shanghai_now


class AnalysisReport(Base):
    __tablename__ = "analysis_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    platform: Mapped[str] = mapped_column(String(32), index=True, default="xhs")
    report_type: Mapped[str] = mapped_column(String(64), index=True, default="content_analysis")
    status: Mapped[str] = mapped_column(String(32), index=True, default="pending")
    title: Mapped[str] = mapped_column(String(256), default="")
    input_config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    data_health: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    evidence_pool: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    result_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    html_file_path: Mapped[str] = mapped_column(Text, default="")
    source_task_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rerun_from_report_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
```

- [ ] **Step 4: Export the model**

Modify `backend/app/models/__init__.py` to import `AnalysisReport` and add it to `__all__` using the file's existing style:

```python
from backend.app.models.analysis_report import AnalysisReport
```

Add the string:

```python
"AnalysisReport",
```

- [ ] **Step 5: Create Alembic migration**

Create `backend/alembic/versions/9f4c2b7e1a0d_add_analysis_reports_table.py`:

```python
"""add analysis reports table

Revision ID: 9f4c2b7e1a0d
Revises: 7b2d4a9c1f03
Create Date: 2026-06-16 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "9f4c2b7e1a0d"
down_revision = "7b2d4a9c1f03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analysis_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("report_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("input_config", sa.JSON(), nullable=True),
        sa.Column("data_health", sa.JSON(), nullable=True),
        sa.Column("evidence_pool", sa.JSON(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("html_file_path", sa.Text(), nullable=False),
        sa.Column("source_task_id", sa.Integer(), nullable=True),
        sa.Column("rerun_from_report_id", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analysis_reports_user_id", "analysis_reports", ["user_id"])
    op.create_index("ix_analysis_reports_platform", "analysis_reports", ["platform"])
    op.create_index("ix_analysis_reports_report_type", "analysis_reports", ["report_type"])
    op.create_index("ix_analysis_reports_status", "analysis_reports", ["status"])


def downgrade() -> None:
    op.drop_index("ix_analysis_reports_status", table_name="analysis_reports")
    op.drop_index("ix_analysis_reports_report_type", table_name="analysis_reports")
    op.drop_index("ix_analysis_reports_platform", table_name="analysis_reports")
    op.drop_index("ix_analysis_reports_user_id", table_name="analysis_reports")
    op.drop_table("analysis_reports")
```

Before committing this file to the branch, verify the current Alembic head. If `7b2d4a9c1f03` is no longer the current head, set `down_revision` to the actual current head and keep the revision id `9f4c2b7e1a0d` unless it conflicts.

- [ ] **Step 6: Update SQLite datetime normalization if applicable**

If `backend/app/core/database.py` contains a table-to-datetime-column normalization map, add:

```python
"analysis_reports": ["created_at", "started_at", "finished_at"],
```

If the current file has no such map, do not add new normalization code.

- [ ] **Step 7: Run model tests**

Run:

```bash
pytest tests/backend/test_xhs_analysis_center.py::test_analysis_report_model_persists_json tests/backend/test_xhs_analysis_center.py::test_analysis_reports_table_has_required_columns -v
```

Expected: both tests pass.

---

## Task 2: Add deterministic health check and collection plan service

**Files:**
- Create: `backend/app/services/xhs_analysis_center_service.py`
- Test: `tests/backend/test_xhs_analysis_center.py`

- [ ] **Step 1: Add health-check tests**

Add tests that create real `KeywordGroup`, `Note`, and `NoteComment` rows. Use real rows only; no product fake data.

```python
def test_analysis_health_below_minimum_blocks_generation(db_session: Session):
    user = _create_user(db_session, "below-minimum")
    group = _create_keyword_group(db_session, user.id, ["Claude Code", "AI编程"])
    _create_note_with_comments(db_session, user.id, title="少量样本", content="Claude Code 入门", comments=["怎么配置？"])

    service = XhsAnalysisCenterService(db_session)
    health = service.check_health(user_id=user.id, keyword_group_id=group.id, excluded_note_ids=[])

    assert health["status"] == "insufficient"
    assert health["can_generate"] is False
    assert health["metrics"]["valid_note_count"] < 10
    assert health["collection_plan"]["needed"] is True


def test_analysis_health_minimum_caps_confidence_to_medium(db_session: Session):
    user = _create_user(db_session, "minimum")
    group = _create_keyword_group(db_session, user.id, ["Claude Code", "AI编程", "Cursor"])
    for index in range(10):
        _create_note_with_comments(
            db_session,
            user.id,
            title=f"Claude Code 入门 {index}",
            content="Claude Code Cursor AI编程 新手配置",
            comments=[f"新手怎么配置 {index}-{item}？" for item in range(3)],
            raw_json={"liked_count": 20 + index, "collected_count": 10, "comment_count": 3, "share_count": 1},
        )

    service = XhsAnalysisCenterService(db_session)
    health = service.check_health(user_id=user.id, keyword_group_id=group.id, excluded_note_ids=[])

    assert health["status"] == "minimum"
    assert health["can_generate"] is True
    assert health["confidence_cap"] == "medium"


def test_analysis_health_standard_allows_high_confidence(db_session: Session):
    user = _create_user(db_session, "standard")
    group = _create_keyword_group(db_session, user.id, ["Claude Code", "AI编程", "Cursor", "AI工具", "效率工具"])
    for index in range(30):
        _create_note_with_comments(
            db_session,
            user.id,
            title=f"Claude Code 效率工具 {index}",
            content="Claude Code Cursor AI编程 AI工具 效率工具 配置教程",
            comments=[f"怎么买课程 {index}-{item}？" for item in range(4)],
            raw_json={"liked_count": 80 + index, "collected_count": 40, "comment_count": 4, "share_count": 10},
        )

    service = XhsAnalysisCenterService(db_session)
    health = service.check_health(user_id=user.id, keyword_group_id=group.id, excluded_note_ids=[])

    assert health["status"] == "standard"
    assert health["can_generate"] is True
    assert health["confidence_cap"] == "high"
```

Add helpers in the same test file:

```python
def _create_keyword_group(db: Session, user_id: int, keywords: list[str]):
    from backend.app.models.keyword_group import KeywordGroup

    group = KeywordGroup(user_id=user_id, platform="xhs", name="AI 编程", keywords=keywords)
    db.add(group)
    db.commit()
    db.refresh(group)
    return group


def _create_note_with_comments(
    db: Session,
    user_id: int,
    title: str,
    content: str,
    comments: list[str],
    raw_json: dict | None = None,
):
    from backend.app.models.note import Note, NoteComment

    note = Note(
        user_id=user_id,
        platform_account_id=1,
        platform="xhs",
        note_id=f"note-{user_id}-{title}",
        title=title,
        content=content,
        author_name="测试作者",
        raw_json=raw_json or {"liked_count": 1, "collected_count": 1, "comment_count": len(comments), "share_count": 0},
    )
    db.add(note)
    db.commit()
    db.refresh(note)

    for index, text in enumerate(comments):
        db.add(
            NoteComment(
                note_id=note.id,
                comment_id=f"comment-{note.id}-{index}",
                user_name="测试用户",
                content=text,
                like_count=index,
            )
        )
    db.commit()
    return note
```

- [ ] **Step 2: Run health tests and verify the service does not exist yet**

Run:

```bash
pytest tests/backend/test_xhs_analysis_center.py::test_analysis_health_below_minimum_blocks_generation -v
```

Expected: fail with import error for `XhsAnalysisCenterService`.

- [ ] **Step 3: Implement health constants and service skeleton**

Create `backend/app/services/xhs_analysis_center_service.py` with the service class, thresholds, and health check:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.time import shanghai_now
from backend.app.models.keyword_group import KeywordGroup
from backend.app.models.note import Note, NoteComment

MINIMUM_THRESHOLDS = {
    "valid_notes": 10,
    "comments": 30,
    "keyword_coverage": 3,
    "representative_notes": 1,
}

STANDARD_THRESHOLDS = {
    "valid_notes": 30,
    "comments": 100,
    "keyword_coverage": 5,
    "high_engagement_notes": 3,
}


@dataclass(frozen=True)
class AnalysisScope:
    keyword_group: KeywordGroup
    notes: list[Note]
    comments_by_note_id: dict[int, list[NoteComment]]
    excluded_note_ids: set[int]


class AnalysisValidationError(ValueError):
    pass


class XhsAnalysisCenterService:
    def __init__(self, db: Session):
        self.db = db

    def check_health(self, *, user_id: int, keyword_group_id: int, excluded_note_ids: list[int] | None = None) -> dict[str, Any]:
        scope = self._resolve_scope(user_id=user_id, keyword_group_id=keyword_group_id, excluded_note_ids=excluded_note_ids or [])
        covered_keywords = self._covered_keywords(scope.keyword_group.keywords or [], scope.notes, scope.comments_by_note_id)
        engagements = [self._note_engagement(note) for note in scope.notes]
        high_engagement_note_ids = self._high_engagement_note_ids(scope.notes)
        representative_count = len(high_engagement_note_ids) if high_engagement_note_ids else min(len(scope.notes), 3)
        comment_count = sum(len(items) for items in scope.comments_by_note_id.values())

        metrics = {
            "valid_note_count": len(scope.notes),
            "comment_count": comment_count,
            "covered_keyword_count": len(covered_keywords),
            "representative_note_count": representative_count,
            "high_engagement_note_count": len(high_engagement_note_ids),
            "total_engagement": sum(engagements),
        }
        missing = self._missing_health_items(metrics)
        if missing:
            status = "insufficient"
            can_generate = False
            confidence_cap = "none"
        elif self._meets_standard(metrics):
            status = "standard"
            can_generate = True
            confidence_cap = "high"
        else:
            status = "minimum"
            can_generate = True
            confidence_cap = "medium"

        warnings = []
        if status == "minimum":
            warnings.append("样本未达标准阈值，结论仅供初筛")
        if len(high_engagement_note_ids) < STANDARD_THRESHOLDS["high_engagement_notes"]:
            warnings.append("整体互动样本偏少，高互动结论置信度有限")

        return {
            "status": status,
            "can_generate": can_generate,
            "confidence_cap": confidence_cap,
            "metrics": metrics,
            "missing": missing,
            "warnings": warnings,
            "collection_plan": self.create_collection_plan(metrics=metrics, keywords=scope.keyword_group.keywords or []),
        }
```

- [ ] **Step 4: Implement scope resolution and metrics helpers**

Add these methods inside `XhsAnalysisCenterService`:

```python
    def _resolve_scope(self, *, user_id: int, keyword_group_id: int, excluded_note_ids: list[int]) -> AnalysisScope:
        keyword_group = self.db.scalar(
            select(KeywordGroup).where(
                KeywordGroup.id == keyword_group_id,
                KeywordGroup.user_id == user_id,
                KeywordGroup.platform == "xhs",
            )
        )
        if keyword_group is None:
            raise AnalysisValidationError("Keyword group not found")

        keywords = [str(item).strip() for item in (keyword_group.keywords or []) if str(item).strip()]
        excluded = {int(item) for item in excluded_note_ids}
        note_stmt = select(Note).where(Note.user_id == user_id, Note.platform == "xhs")
        notes = [note for note in self.db.scalars(note_stmt).all() if note.id not in excluded and self._note_matches_keywords(note, keywords)]
        note_ids = [note.id for note in notes]
        comments_by_note_id: dict[int, list[NoteComment]] = {note_id: [] for note_id in note_ids}
        if note_ids:
            comments = self.db.scalars(select(NoteComment).where(NoteComment.note_id.in_(note_ids))).all()
            for comment in comments:
                comments_by_note_id.setdefault(comment.note_id, []).append(comment)
        return AnalysisScope(keyword_group=keyword_group, notes=notes, comments_by_note_id=comments_by_note_id, excluded_note_ids=excluded)

    def _note_matches_keywords(self, note: Note, keywords: list[str]) -> bool:
        if not keywords:
            return False
        haystack = f"{note.title}\n{note.content}".lower()
        return any(keyword.lower() in haystack for keyword in keywords)

    def _covered_keywords(self, keywords: list[str], notes: list[Note], comments_by_note_id: dict[int, list[NoteComment]]) -> set[str]:
        covered: set[str] = set()
        for keyword in keywords:
            needle = keyword.lower()
            for note in notes:
                note_text = f"{note.title}\n{note.content}".lower()
                comment_text = "\n".join(comment.content for comment in comments_by_note_id.get(note.id, [])).lower()
                if needle in note_text or needle in comment_text:
                    covered.add(keyword)
                    break
        return covered

    def _note_engagement(self, note: Note) -> int:
        raw = note.raw_json or {}
        keys = ["liked_count", "like_count", "likes", "collected_count", "collect_count", "collects", "comment_count", "comments", "share_count", "shares"]
        total = 0
        for key in keys:
            value = raw.get(key)
            if isinstance(value, int):
                total += value
            elif isinstance(value, str) and value.isdigit():
                total += int(value)
        return total

    def _high_engagement_note_ids(self, notes: list[Note]) -> set[int]:
        if not notes:
            return set()
        scored = sorted(((note.id, self._note_engagement(note)) for note in notes), key=lambda item: item[1], reverse=True)
        top_count = max(1, int(len(scored) * 0.1))
        return {note_id for note_id, engagement in scored[:top_count] if engagement >= 50}

    def _missing_health_items(self, metrics: dict[str, int]) -> list[dict[str, int | str]]:
        checks = [
            ("valid_notes", "有效笔记不足", metrics["valid_note_count"], MINIMUM_THRESHOLDS["valid_notes"]),
            ("comments", "评论不足", metrics["comment_count"], MINIMUM_THRESHOLDS["comments"]),
            ("keyword_coverage", "覆盖关键词不足", metrics["covered_keyword_count"], MINIMUM_THRESHOLDS["keyword_coverage"]),
            ("representative_notes", "代表性样本不足", metrics["representative_note_count"], MINIMUM_THRESHOLDS["representative_notes"]),
        ]
        return [{"key": key, "message": message, "current": current, "required": required} for key, message, current, required in checks if current < required]

    def _meets_standard(self, metrics: dict[str, int]) -> bool:
        return (
            metrics["valid_note_count"] >= STANDARD_THRESHOLDS["valid_notes"]
            and metrics["comment_count"] >= STANDARD_THRESHOLDS["comments"]
            and metrics["covered_keyword_count"] >= STANDARD_THRESHOLDS["keyword_coverage"]
            and metrics["high_engagement_note_count"] >= STANDARD_THRESHOLDS["high_engagement_notes"]
        )

    def create_collection_plan(self, *, metrics: dict[str, int], keywords: list[str]) -> dict[str, Any]:
        needed = bool(self._missing_health_items(metrics))
        missing_notes = max(0, MINIMUM_THRESHOLDS["valid_notes"] - metrics["valid_note_count"])
        missing_comments = max(0, MINIMUM_THRESHOLDS["comments"] - metrics["comment_count"])
        recommended_keywords = keywords[: max(1, MINIMUM_THRESHOLDS["keyword_coverage"] - metrics["covered_keyword_count"])] if needed else []
        return {
            "needed": needed,
            "recommended_keywords": recommended_keywords,
            "recommended_notes_per_keyword": max(0, (missing_notes + max(1, len(recommended_keywords)) - 1) // max(1, len(recommended_keywords))) if needed else 0,
            "should_collect_comments": missing_comments > 0,
        }
```

- [ ] **Step 5: Run health tests**

Run:

```bash
pytest tests/backend/test_xhs_analysis_center.py::test_analysis_health_below_minimum_blocks_generation tests/backend/test_xhs_analysis_center.py::test_analysis_health_minimum_caps_confidence_to_medium tests/backend/test_xhs_analysis_center.py::test_analysis_health_standard_allows_high_confidence -v
```

Expected: all pass.

---

## Task 3: Build evidence pool and deterministic signal extraction

**Files:**
- Modify: `backend/app/services/xhs_analysis_center_service.py`
- Test: `tests/backend/test_xhs_analysis_center.py`

- [ ] **Step 1: Add evidence-pool tests**

```python
def test_evidence_pool_contains_only_real_notes_comments_keywords_and_metrics(db_session: Session):
    user = _create_user(db_session, "evidence")
    group = _create_keyword_group(db_session, user.id, ["Claude Code", "AI编程", "Cursor"])
    note = _create_note_with_comments(
        db_session,
        user.id,
        title="Claude Code 新手配置",
        content="Claude Code Cursor AI编程 入门教程",
        comments=["新手完全不会配置，有没有保姆级教程？", "多少钱可以买课程？"],
        raw_json={"liked_count": 100, "collected_count": 60, "comment_count": 2, "share_count": 5},
    )

    service = XhsAnalysisCenterService(db_session)
    pool = service.build_evidence_pool(user_id=user.id, keyword_group_id=group.id, excluded_note_ids=[])

    assert pool["notes"][0]["evidence_id"] == f"note:{note.id}"
    assert pool["comments"][0]["evidence_id"].startswith("comment:")
    assert {item["keyword"] for item in pool["keywords"]} == {"Claude Code", "AI编程", "Cursor"}
    assert any(metric["evidence_id"] == "metric:question_rate" for metric in pool["metrics"])
    assert "beginner_need" in pool["comments"][0]["signals"]
    assert "price_intent" in pool["comments"][1]["signals"]
```

- [ ] **Step 2: Implement evidence pool**

Add public method:

```python
    def build_evidence_pool(self, *, user_id: int, keyword_group_id: int, excluded_note_ids: list[int] | None = None) -> dict[str, Any]:
        scope = self._resolve_scope(user_id=user_id, keyword_group_id=keyword_group_id, excluded_note_ids=excluded_note_ids or [])
        keywords = [str(item).strip() for item in (scope.keyword_group.keywords or []) if str(item).strip()]
        note_items = []
        comment_items = []
        for note in scope.notes:
            matched_keywords = self._matched_keywords_for_text(f"{note.title}\n{note.content}", keywords)
            note_items.append(
                {
                    "evidence_id": f"note:{note.id}",
                    "note_id": note.id,
                    "title": note.title,
                    "author_name": note.author_name,
                    "likes": self._raw_int(note.raw_json or {}, ["liked_count", "like_count", "likes"]),
                    "collects": self._raw_int(note.raw_json or {}, ["collected_count", "collect_count", "collects"]),
                    "comments": self._raw_int(note.raw_json or {}, ["comment_count", "comments"]),
                    "shares": self._raw_int(note.raw_json or {}, ["share_count", "shares"]),
                    "engagement": self._note_engagement(note),
                    "matched_keywords": matched_keywords,
                    "excerpt": self._excerpt(note.content or note.title),
                }
            )
            for comment in scope.comments_by_note_id.get(note.id, []):
                comment_items.append(
                    {
                        "evidence_id": f"comment:{comment.id}",
                        "comment_id": comment.id,
                        "note_id": note.id,
                        "content": comment.content,
                        "like_count": comment.like_count,
                        "signals": self._comment_signals(comment.content),
                    }
                )

        keyword_items = []
        for keyword in keywords:
            matched_notes = [note for note in scope.notes if keyword.lower() in f"{note.title}\n{note.content}".lower()]
            matched_comments = [item for item in comment_items if keyword.lower() in str(item["content"]).lower()]
            keyword_items.append({"evidence_id": f"keyword:{keyword}", "keyword": keyword, "matched_notes": len(matched_notes), "matched_comments": len(matched_comments)})

        metrics = self._metric_evidence(scope, comment_items)
        return {"notes": note_items, "comments": comment_items, "keywords": keyword_items, "metrics": metrics, "benchmarks": []}
```

Add helpers:

```python
    def _raw_int(self, raw: dict[str, Any], keys: list[str]) -> int:
        for key in keys:
            value = raw.get(key)
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
        return 0

    def _matched_keywords_for_text(self, text: str, keywords: list[str]) -> list[str]:
        lower = text.lower()
        return [keyword for keyword in keywords if keyword.lower() in lower]

    def _excerpt(self, text: str, limit: int = 120) -> str:
        normalized = " ".join(text.split())
        return normalized[:limit]

    def _comment_signals(self, content: str) -> list[str]:
        text = content.lower()
        rules = [
            ("question", ["?", "？", "怎么", "如何", "有没有", "能不能", "吗"]),
            ("price_intent", ["多少钱", "价格", "贵", "便宜"]),
            ("purchase_intent", ["怎么买", "链接", "店铺", "下单", "购买"]),
            ("suitability", ["适合", "能不能用", "可以用"]),
            ("comparison", ["哪个好", "对比", "还是", "区别"]),
            ("complaint", ["踩坑", "不好用", "失败", "报错", "吐槽"]),
            ("beginner_need", ["新手", "小白", "入门", "保姆级"]),
            ("scenario", ["上班", "副业", "学生", "宝妈", "程序员", "团队"]),
        ]
        return [signal for signal, needles in rules if any(needle in text for needle in needles)]

    def _metric_evidence(self, scope: AnalysisScope, comment_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        total_comments = len(comment_items)
        question_count = sum(1 for item in comment_items if "question" in item["signals"])
        beginner_count = sum(1 for item in comment_items if "beginner_need" in item["signals"])
        purchase_count = sum(1 for item in comment_items if "purchase_intent" in item["signals"] or "price_intent" in item["signals"])
        return [
            {"evidence_id": "metric:valid_note_count", "name": "valid_note_count", "value": len(scope.notes), "description": "参与分析的有效笔记数"},
            {"evidence_id": "metric:comment_count", "name": "comment_count", "value": total_comments, "description": "参与分析的评论数"},
            {"evidence_id": "metric:question_rate", "name": "question_rate", "value": round(question_count / total_comments, 4) if total_comments else 0, "description": "评论中提问评论占比"},
            {"evidence_id": "metric:beginner_need_rate", "name": "beginner_need_rate", "value": round(beginner_count / total_comments, 4) if total_comments else 0, "description": "评论中新手需求占比"},
            {"evidence_id": "metric:purchase_intent_rate", "name": "purchase_intent_rate", "value": round(purchase_count / total_comments, 4) if total_comments else 0, "description": "评论中购买或价格意图占比"},
        ]
```

- [ ] **Step 3: Run evidence test**

Run:

```bash
pytest tests/backend/test_xhs_analysis_center.py::test_evidence_pool_contains_only_real_notes_comments_keywords_and_metrics -v
```

Expected: pass.

---

## Task 4: Add structured AI helper and report validation gates

**Files:**
- Modify: `backend/app/services/ai_service.py`
- Modify: `backend/app/services/xhs_analysis_center_service.py`
- Test: `tests/backend/test_xhs_analysis_center.py`

- [ ] **Step 1: Add validation tests**

```python
def test_validate_result_rejects_nonexistent_evidence_id(db_session: Session):
    service = XhsAnalysisCenterService(db_session)
    evidence_pool = {"notes": [], "comments": [], "keywords": [], "metrics": [{"evidence_id": "metric:question_rate"}], "benchmarks": []}
    result = _valid_ai_result(evidence_ids=["metric:not_exists"])

    with pytest.raises(AnalysisValidationError, match="Unknown evidence_id"):
        service.validate_ai_result(result, evidence_pool=evidence_pool, confidence_cap="high")


def test_validate_result_rejects_high_confidence_when_cap_is_medium(db_session: Session):
    service = XhsAnalysisCenterService(db_session)
    evidence_pool = {"notes": [], "comments": [], "keywords": [], "metrics": [{"evidence_id": "metric:question_rate"}], "benchmarks": []}
    result = _valid_ai_result(evidence_ids=["metric:question_rate"], confidence="high")

    with pytest.raises(AnalysisValidationError, match="exceeds confidence cap"):
        service.validate_ai_result(result, evidence_pool=evidence_pool, confidence_cap="medium")


def _valid_ai_result(evidence_ids: list[str], confidence: str = "medium") -> dict:
    return {
        "summary": {
            "facts": [{"id": "fact_1", "text": "评论中提问占比较高。", "evidence_ids": evidence_ids}],
            "inferences": [{"id": "inference_1", "text": "用户需要更清晰的配置教程。", "evidence_ids": evidence_ids}],
            "recommendations": [{"id": "recommendation_1", "text": "优先制作保姆级教程。", "evidence_ids": evidence_ids}],
        },
        "insight_cards": [
            {
                "id": "insight_1",
                "title": "新手配置门槛是高频痛点",
                "score": 80,
                "sub_scores": {"traffic_potential": 70, "demand_strength": 90, "competition_pressure": 60, "actionability": 85},
                "confidence": confidence,
                "confidence_reason": "基于评论信号和指标。",
                "facts": [],
                "inferences": [],
                "recommendations": [],
                "evidence_ids": evidence_ids,
                "topic_card_ids": ["topic_1"],
            }
        ],
        "topic_cards": [
            {
                "id": "topic_1",
                "insight_id": "insight_1",
                "title_direction": "Claude Code 新手配置清单",
                "target_pain": "新手不会配置。",
                "content_angle": "保姆级教程。",
                "recommended_structure": ["适合谁", "配置步骤", "常见坑"],
                "recommended_content_form": ["教程型"],
                "tags": ["ClaudeCode"],
                "cover_suggestion": "第一次用 Claude Code，照着做就能跑",
                "expected_advantage": "新手问题明确。",
                "risk_warning": "不要写泛泛介绍。",
                "evidence_ids": evidence_ids,
            }
        ],
        "report_warnings": [],
    }
```

- [ ] **Step 2: Add raw structured prompt method to AI service**

In `backend/app/services/ai_service.py`, extend the `TextAiClient` protocol with:

```python
    def complete_json_prompt(self, *, model_config: ModelConfig, api_key: str, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
        ...
```

Add implementation to `OpenAICompatibleTextClient`:

```python
    def complete_json_prompt(self, *, model_config: ModelConfig, api_key: str, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
        return self._complete(
            model_config=model_config,
            api_key=api_key,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
        )
```

- [ ] **Step 3: Implement AI result validation**

Add to `XhsAnalysisCenterService`:

```python
    def validate_ai_result(self, result: dict[str, Any], *, evidence_pool: dict[str, Any], confidence_cap: str) -> dict[str, Any]:
        if not isinstance(result, dict):
            raise AnalysisValidationError("AI result must be an object")
        for key in ["summary", "insight_cards", "topic_cards", "report_warnings"]:
            if key not in result:
                raise AnalysisValidationError(f"Missing result field: {key}")
        summary = result["summary"]
        if not isinstance(summary, dict):
            raise AnalysisValidationError("summary must be an object")
        for key in ["facts", "inferences", "recommendations"]:
            if not isinstance(summary.get(key), list):
                raise AnalysisValidationError(f"summary.{key} must be a list")
        insight_cards = result["insight_cards"]
        topic_cards = result["topic_cards"]
        if not isinstance(insight_cards, list) or len(insight_cards) > 5:
            raise AnalysisValidationError("insight_cards must be a list with at most 5 items")
        if not isinstance(topic_cards, list) or len(topic_cards) > 15:
            raise AnalysisValidationError("topic_cards must be a list with at most 15 items")

        known_ids = self._known_evidence_ids(evidence_pool)
        for item in summary["facts"]:
            self._require_evidence(item, known_ids, "summary facts")
        for item in summary["inferences"]:
            self._require_evidence(item, known_ids, "summary inferences")
        for item in summary["recommendations"]:
            self._require_evidence(item, known_ids, "summary recommendations")
        for card in insight_cards:
            self._validate_insight_card(card, known_ids, confidence_cap)
        topic_ids = {card.get("id") for card in topic_cards}
        for card in topic_cards:
            self._validate_topic_card(card, known_ids)
        for card in insight_cards:
            for topic_id in card.get("topic_card_ids", []):
                if topic_id not in topic_ids:
                    raise AnalysisValidationError(f"Unknown topic_card_id: {topic_id}")
        return result
```

Add helper methods:

```python
    def _known_evidence_ids(self, evidence_pool: dict[str, Any]) -> set[str]:
        ids: set[str] = set()
        for key in ["notes", "comments", "keywords", "metrics", "benchmarks"]:
            for item in evidence_pool.get(key, []):
                evidence_id = item.get("evidence_id")
                if isinstance(evidence_id, str):
                    ids.add(evidence_id)
        return ids

    def _require_evidence(self, item: dict[str, Any], known_ids: set[str], label: str) -> None:
        evidence_ids = item.get("evidence_ids")
        if not isinstance(evidence_ids, list) or not evidence_ids:
            raise AnalysisValidationError(f"{label} must include evidence_ids")
        for evidence_id in evidence_ids:
            if evidence_id not in known_ids:
                raise AnalysisValidationError(f"Unknown evidence_id: {evidence_id}")

    def _validate_score(self, value: Any, label: str) -> None:
        if not isinstance(value, int) or value < 0 or value > 100:
            raise AnalysisValidationError(f"{label} must be an integer from 0 to 100")

    def _validate_insight_card(self, card: dict[str, Any], known_ids: set[str], confidence_cap: str) -> None:
        for key in ["id", "title", "confidence", "confidence_reason", "evidence_ids", "topic_card_ids"]:
            if key not in card:
                raise AnalysisValidationError(f"Missing insight card field: {key}")
        self._validate_score(card.get("score"), "insight score")
        sub_scores = card.get("sub_scores")
        if not isinstance(sub_scores, dict):
            raise AnalysisValidationError("sub_scores must be an object")
        for key in ["traffic_potential", "demand_strength", "competition_pressure", "actionability"]:
            self._validate_score(sub_scores.get(key), f"sub_scores.{key}")
        confidence = card.get("confidence")
        if confidence not in ["low", "medium", "high"]:
            raise AnalysisValidationError("Invalid confidence")
        if confidence_cap == "medium" and confidence == "high":
            raise AnalysisValidationError("Insight confidence exceeds confidence cap")
        self._require_evidence(card, known_ids, "insight card")

    def _validate_topic_card(self, card: dict[str, Any], known_ids: set[str]) -> None:
        required = ["id", "insight_id", "title_direction", "target_pain", "content_angle", "recommended_structure", "recommended_content_form", "tags", "cover_suggestion", "expected_advantage", "risk_warning", "evidence_ids"]
        for key in required:
            if key not in card:
                raise AnalysisValidationError(f"Missing topic card field: {key}")
        if not isinstance(card["recommended_structure"], list) or not card["recommended_structure"]:
            raise AnalysisValidationError("recommended_structure must be a non-empty list")
        if not isinstance(card["tags"], list):
            raise AnalysisValidationError("tags must be a list")
        self._require_evidence(card, known_ids, "topic card")
```

- [ ] **Step 4: Run validation tests**

Run:

```bash
pytest tests/backend/test_xhs_analysis_center.py::test_validate_result_rejects_nonexistent_evidence_id tests/backend/test_xhs_analysis_center.py::test_validate_result_rejects_high_confidence_when_cap_is_medium -v
```

Expected: both pass.

---

## Task 5: Create reports with model gate, health gate, JSON gate, and failed snapshots

**Files:**
- Modify: `backend/app/services/xhs_analysis_center_service.py`
- Test: `tests/backend/test_xhs_analysis_center.py`

- [ ] **Step 1: Add report-creation tests using a fake client**

```python
class FakeJsonAiClient:
    def __init__(self, response: str):
        self.response = response
        self.calls = 0

    def complete_json_prompt(self, **kwargs):
        self.calls += 1
        return self.response


def test_create_report_below_minimum_does_not_call_model(db_session: Session):
    user = _create_user(db_session, "no-model-call")
    group = _create_keyword_group(db_session, user.id, ["Claude Code", "AI编程"])
    _create_note_with_comments(db_session, user.id, "少量 Claude Code", "Claude Code", ["怎么配置？"])
    client = FakeJsonAiClient(response="{}")

    service = XhsAnalysisCenterService(db_session)
    report = service.create_report(
        user_id=user.id,
        payload={"keyword_group_id": group.id, "title": "数据不足报告", "excluded_note_ids": []},
        model_config=None,
        api_key="",
        ai_client=client,
    )

    assert report.status == "failed"
    assert "数据低于最低门槛" in report.error_message
    assert client.calls == 0


def test_create_report_invalid_json_saves_failed_snapshot(db_session: Session):
    user = _seed_minimum_dataset(db_session, "invalid-json")
    group = db_session.scalar(select(KeywordGroup).where(KeywordGroup.user_id == user.id))
    client = FakeJsonAiClient(response="not json")
    model_config = _create_model_config(db_session, user.id)

    service = XhsAnalysisCenterService(db_session)
    report = service.create_report(
        user_id=user.id,
        payload={"keyword_group_id": group.id, "title": "非法 JSON", "excluded_note_ids": []},
        model_config=model_config,
        api_key="test-key",
        ai_client=client,
    )

    assert report.status == "failed"
    assert "模型输出不是合法 JSON" in report.error_message
    assert report.evidence_pool["notes"]
    assert report.html_file_path == ""
```

Add helpers:

```python
def _seed_minimum_dataset(db: Session, username: str) -> User:
    user = _create_user(db, username)
    _create_keyword_group(db, user.id, ["Claude Code", "AI编程", "Cursor"])
    for index in range(10):
        _create_note_with_comments(
            db,
            user.id,
            title=f"Claude Code 入门 {index}",
            content="Claude Code Cursor AI编程 入门配置",
            comments=[f"新手怎么配置 {index}-{item}？" for item in range(3)],
            raw_json={"liked_count": 70, "collected_count": 30, "comment_count": 3, "share_count": 5},
        )
    return user


def _create_model_config(db: Session, user_id: int):
    from backend.app.models.ai import ModelConfig

    config = ModelConfig(
        user_id=user_id,
        name="测试文本模型",
        model_type="text",
        provider="openai-compatible",
        model_name="test-model",
        base_url="https://example.invalid/v1",
        encrypted_api_key="encrypted",
        is_default=True,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return config
```

- [ ] **Step 2: Implement `create_report`**

Add method:

```python
    def create_report(self, *, user_id: int, payload: dict[str, Any], model_config: Any | None, api_key: str, ai_client: Any) -> Any:
        from backend.app.models.analysis_report import AnalysisReport

        keyword_group_id = int(payload["keyword_group_id"])
        excluded_note_ids = [int(item) for item in payload.get("excluded_note_ids", [])]
        title = str(payload.get("title") or "小红书分析报告")
        report = AnalysisReport(
            user_id=user_id,
            platform="xhs",
            report_type="content_analysis",
            status="running",
            title=title,
            input_config=self._input_config(keyword_group_id=keyword_group_id, excluded_note_ids=excluded_note_ids, payload=payload),
            started_at=shanghai_now(),
            html_file_path="",
        )
        self.db.add(report)
        self.db.commit()
        self.db.refresh(report)

        health = self.check_health(user_id=user_id, keyword_group_id=keyword_group_id, excluded_note_ids=excluded_note_ids)
        evidence_pool = self.build_evidence_pool(user_id=user_id, keyword_group_id=keyword_group_id, excluded_note_ids=excluded_note_ids)
        report.data_health = health
        report.evidence_pool = evidence_pool

        try:
            if not health["can_generate"]:
                raise AnalysisValidationError("数据低于最低门槛，未调用模型")
            if model_config is None:
                raise AnalysisValidationError("Default text model is not configured")
            raw_text = ai_client.complete_json_prompt(
                model_config=model_config,
                api_key=api_key,
                system_prompt=self._analysis_system_prompt(),
                user_prompt=self._analysis_user_prompt(health=health, evidence_pool=evidence_pool, input_config=report.input_config or {}),
                temperature=0.2,
            )
            result = self._parse_json_result(raw_text)
            report.result_json = self.validate_ai_result(result, evidence_pool=evidence_pool, confidence_cap=health["confidence_cap"])
            report.status = "completed"
            report.error_message = None
        except Exception as exc:
            report.status = "failed"
            report.error_message = str(exc)
            report.result_json = None
        finally:
            report.finished_at = shanghai_now()
            self.db.add(report)
            self.db.commit()
            self.db.refresh(report)
        return report
```

Add helpers:

```python
    def _input_config(self, *, keyword_group_id: int, excluded_note_ids: list[int], payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "keyword_group_id": keyword_group_id,
            "excluded_note_ids": excluded_note_ids,
            "source_note_ids": payload.get("source_note_ids", []),
            "benchmark_target_ids": payload.get("benchmark_target_ids", []),
            "thresholds": {"minimum": MINIMUM_THRESHOLDS, "standard": STANDARD_THRESHOLDS},
            "topic_cards_per_insight": 3,
            "max_insight_cards": 5,
        }

    def _parse_json_result(self, raw_text: str) -> dict[str, Any]:
        import json

        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise AnalysisValidationError("模型输出不是合法 JSON") from exc
        if not isinstance(parsed, dict):
            raise AnalysisValidationError("模型输出 JSON 必须是对象")
        return parsed

    def _analysis_system_prompt(self) -> str:
        return "\n".join(
            [
                "你是小红书内容分析助手。你只能基于输入 evidence_pool 中的证据做分析。",
                "任何事实结论都必须引用 evidence_id。",
                "不要编造数据、评论、笔记、用户反馈、行业基准或报告结论。",
                "如果证据不足，少输出或降低置信度，不要补全。",
                "输出必须是符合 JSON Schema 的 JSON，不要 Markdown。",
                "必须区分 facts、inferences、recommendations。",
            ]
        )

    def _analysis_user_prompt(self, *, health: dict[str, Any], evidence_pool: dict[str, Any], input_config: dict[str, Any]) -> str:
        import json

        schema_hint = {
            "summary": {"facts": [], "inferences": [], "recommendations": []},
            "insight_cards": "最多 5 个，每个包含 score/sub_scores/confidence/evidence_ids/topic_card_ids",
            "topic_cards": "每个洞察最多 3 个，总数最多 15 个",
            "report_warnings": [],
        }
        payload = {"data_health": health, "input_config": input_config, "evidence_pool": evidence_pool, "required_shape": schema_hint}
        return json.dumps(payload, ensure_ascii=False)
```

- [ ] **Step 3: Run report-creation tests**

Run:

```bash
pytest tests/backend/test_xhs_analysis_center.py::test_create_report_below_minimum_does_not_call_model tests/backend/test_xhs_analysis_center.py::test_create_report_invalid_json_saves_failed_snapshot -v
```

Expected: both pass.

---

## Task 6: Add static HTML renderer and attach it only to completed reports

**Files:**
- Create: `backend/app/services/xhs_analysis_report_renderer.py`
- Modify: `backend/app/services/xhs_analysis_center_service.py`
- Test: `tests/backend/test_xhs_analysis_center.py`

- [ ] **Step 1: Add HTML tests**

```python
def test_renderer_outputs_static_html_with_disclaimer(tmp_path):
    from backend.app.services.xhs_analysis_report_renderer import render_xhs_analysis_report_html

    html = render_xhs_analysis_report_html(
        title="AI 编程 - 小红书分析报告",
        data_health={"status": "minimum", "warnings": ["样本未达标准阈值，结论仅供初筛"]},
        evidence_pool={"notes": [{"evidence_id": "note:1", "title": "真实笔记", "engagement": 100}], "comments": [], "keywords": [], "metrics": [], "benchmarks": []},
        result_json=_valid_ai_result(["note:1"]),
    )

    assert "AI 编程 - 小红书分析报告" in html
    assert "样本未达标准阈值" in html
    assert "报告基于当前已采集数据生成" in html
    assert "<script" not in html.lower()
```

- [ ] **Step 2: Implement static renderer**

Create `backend/app/services/xhs_analysis_report_renderer.py`:

```python
from __future__ import annotations

from html import escape
from typing import Any


def render_xhs_analysis_report_html(*, title: str, data_health: dict[str, Any], evidence_pool: dict[str, Any], result_json: dict[str, Any]) -> str:
    summary = result_json.get("summary", {})
    insight_cards = result_json.get("insight_cards", [])
    topic_cards = result_json.get("topic_cards", [])
    warnings = list(data_health.get("warnings", [])) + list(result_json.get("report_warnings", []))
    return "\n".join(
        [
            "<!doctype html>",
            "<html lang=\"zh-CN\">",
            "<head>",
            "<meta charset=\"utf-8\" />",
            f"<title>{escape(title)}</title>",
            "<style>body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:1080px;margin:0 auto;padding:32px;color:#1f1f1f;}section{margin:24px 0;padding:20px;border:1px solid #eee;border-radius:12px;}h1,h2,h3{margin-top:0}.card{margin:12px 0;padding:14px;background:#fafafa;border-radius:10px}.muted{color:#666}.warning{color:#ad6800;background:#fff7e6;padding:10px;border-radius:8px}</style>",
            "</head>",
            "<body>",
            f"<h1>{escape(title)}</h1>",
            f"<p class=\"muted\">数据健康状态：{escape(str(data_health.get('status', 'unknown')))}</p>",
            _render_warnings(warnings),
            _render_summary(summary),
            _render_insights(insight_cards),
            _render_topics(topic_cards),
            _render_evidence(evidence_pool),
            "<section><h2>免责声明</h2><p>报告基于当前已采集数据生成，未采集到的数据不会被推断为事实，样本不足时结论仅供初筛。</p></section>",
            "</body></html>",
        ]
    )


def _render_warnings(warnings: list[Any]) -> str:
    if not warnings:
        return ""
    items = "".join(f"<li>{escape(str(item))}</li>" for item in warnings)
    return f"<section class=\"warning\"><h2>样本限制与风险提醒</h2><ul>{items}</ul></section>"


def _render_summary(summary: dict[str, Any]) -> str:
    blocks = []
    for key, label in [("facts", "事实"), ("inferences", "推断"), ("recommendations", "建议")]:
        items = "".join(f"<li>{escape(str(item.get('text', '')))} <span class=\"muted\">{escape(', '.join(item.get('evidence_ids', [])))}</span></li>" for item in summary.get(key, []))
        blocks.append(f"<h3>{label}</h3><ul>{items}</ul>")
    return f"<section><h2>核心总结</h2>{''.join(blocks)}</section>"


def _render_insights(cards: list[dict[str, Any]]) -> str:
    body = "".join(
        f"<div class=\"card\"><h3>{escape(str(card.get('title', '')))}</h3><p>综合分：{escape(str(card.get('score', '')))} / 置信度：{escape(str(card.get('confidence', '')))}</p><p>{escape(str(card.get('confidence_reason', '')))}</p><p class=\"muted\">证据：{escape(', '.join(card.get('evidence_ids', [])))}</p></div>"
        for card in cards
    )
    return f"<section><h2>洞察卡</h2>{body}</section>"


def _render_topics(cards: list[dict[str, Any]]) -> str:
    body = "".join(
        f"<div class=\"card\"><h3>{escape(str(card.get('title_direction', '')))}</h3><p><strong>痛点：</strong>{escape(str(card.get('target_pain', '')))}</p><p><strong>角度：</strong>{escape(str(card.get('content_angle', '')))}</p><p><strong>风险：</strong>{escape(str(card.get('risk_warning', '')))}</p></div>"
        for card in cards
    )
    return f"<section><h2>选题卡</h2>{body}</section>"


def _render_evidence(pool: dict[str, Any]) -> str:
    notes = "".join(f"<li>{escape(str(note.get('evidence_id', '')))}：{escape(str(note.get('title', '')))}</li>" for note in pool.get("notes", [])[:10])
    return f"<section><h2>代表性证据</h2><ul>{notes}</ul></section>"
```

- [ ] **Step 3: Attach renderer in completed report path**

In `create_report`, after validation and before setting `status = "completed"`, call a new helper:

```python
            report.result_json = self.validate_ai_result(result, evidence_pool=evidence_pool, confidence_cap=health["confidence_cap"])
            report.html_file_path = self._write_report_html(user_id=user_id, report_id=report.id, title=report.title, data_health=health, evidence_pool=evidence_pool, result_json=report.result_json)
            report.status = "completed"
```

Add helper:

```python
    def _write_report_html(self, *, user_id: int, report_id: int, title: str, data_health: dict[str, Any], evidence_pool: dict[str, Any], result_json: dict[str, Any]) -> str:
        from pathlib import Path
        from backend.app.core.config import get_settings
        from backend.app.services.xhs_analysis_report_renderer import render_xhs_analysis_report_html

        settings = get_settings()
        export_dir = Path(settings.storage_dir) / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        file_path = export_dir / f"xhs-analysis-report-u{user_id}-{report_id}.html"
        html = render_xhs_analysis_report_html(title=title, data_health=data_health, evidence_pool=evidence_pool, result_json=result_json)
        file_path.write_text(html, encoding="utf-8")
        return str(file_path)
```

- [ ] **Step 4: Run HTML tests**

Run:

```bash
pytest tests/backend/test_xhs_analysis_center.py::test_renderer_outputs_static_html_with_disclaimer -v
```

Expected: pass.

---

## Task 7: Add analysis-center API routes

**Files:**
- Create: `backend/app/api/platforms/xhs/analysis_center.py`
- Modify: `backend/app/main.py`
- Test: `tests/backend/test_xhs_analysis_center.py`

- [ ] **Step 1: Add API tests for health, create, list, detail, permission**

Use the existing authenticated-client helpers from `tests/backend/test_api.py` style. Add tests that verify:

```python
def test_health_api_returns_can_generate_false_for_insufficient_data(client):
    token = _register_and_get_access_token(client, username="health-api")
    group_id = _seed_keyword_group_via_db("health-api")

    response = client.post(
        "/api/xhs/analytics/analysis/health",
        headers={"Authorization": f"Bearer {token}"},
        json={"keyword_group_id": group_id, "excluded_note_ids": []},
    )

    assert response.status_code == 200
    assert response.json()["can_generate"] is False


def test_reports_api_rejects_other_user_report(client):
    token_a = _register_and_get_access_token(client, username="owner")
    token_b = _register_and_get_access_token(client, username="intruder")
    report_id = _seed_failed_report_via_db(username="owner")

    response = client.get(
        f"/api/xhs/analytics/analysis/reports/{report_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )

    assert response.status_code == 404
```

When implementing these tests, reuse the project's real auth helpers and DB override pattern. Keep all seeded rows inside the test database.

- [ ] **Step 2: Implement request schemas and routes**

Create `backend/app/api/platforms/xhs/analysis_center.py`:

```python
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.ai import _text_model_context, get_text_ai_client
from backend.app.core.database import get_db
from backend.app.models.analysis_report import AnalysisReport
from backend.app.models.user import User
from backend.app.services.auth_service import get_current_user
from backend.app.services.xhs_analysis_center_service import AnalysisValidationError, XhsAnalysisCenterService

router = APIRouter(prefix="/xhs/analytics/analysis", tags=["xhs-analysis-center"])


class AnalysisHealthPayload(BaseModel):
    keyword_group_id: int
    excluded_note_ids: list[int] = Field(default_factory=list)
    source_note_ids: list[int] = Field(default_factory=list)
    benchmark_target_ids: list[int] = Field(default_factory=list)


class CreateAnalysisReportPayload(AnalysisHealthPayload):
    title: str = "小红书分析报告"


class CreateDraftFromTopicCardsPayload(BaseModel):
    topic_cards: list[dict[str, Any]]


def _serialize_report(report: AnalysisReport) -> dict[str, Any]:
    return {
        "id": report.id,
        "platform": report.platform,
        "report_type": report.report_type,
        "status": report.status,
        "title": report.title,
        "input_config": report.input_config or {},
        "data_health": report.data_health or {},
        "evidence_pool": report.evidence_pool or {},
        "result_json": report.result_json,
        "html_file_path": report.html_file_path,
        "error_message": report.error_message,
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "started_at": report.started_at.isoformat() if report.started_at else None,
        "finished_at": report.finished_at.isoformat() if report.finished_at else None,
    }


@router.post("/health")
def check_analysis_health(payload: AnalysisHealthPayload, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    service = XhsAnalysisCenterService(db)
    try:
        return service.check_health(user_id=current_user.id, keyword_group_id=payload.keyword_group_id, excluded_note_ids=payload.excluded_note_ids)
    except AnalysisValidationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/collection-plan")
def create_collection_plan(payload: AnalysisHealthPayload, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    service = XhsAnalysisCenterService(db)
    health = service.check_health(user_id=current_user.id, keyword_group_id=payload.keyword_group_id, excluded_note_ids=payload.excluded_note_ids)
    return health["collection_plan"]


@router.get("/reports")
def list_reports(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    reports = db.scalars(select(AnalysisReport).where(AnalysisReport.user_id == current_user.id, AnalysisReport.platform == "xhs").order_by(AnalysisReport.created_at.desc())).all()
    return [_serialize_report(report) for report in reports]


@router.get("/reports/{report_id}")
def get_report(report_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    report = db.scalar(select(AnalysisReport).where(AnalysisReport.id == report_id, AnalysisReport.user_id == current_user.id))
    if report is None:
        raise HTTPException(status_code=404, detail="Analysis report not found")
    return _serialize_report(report)


@router.post("/reports")
def create_report(payload: CreateAnalysisReportPayload, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    service = XhsAnalysisCenterService(db)
    model_config = None
    api_key = ""
    try:
        model_config, api_key = _text_model_context(db, current_user)
    except HTTPException:
        model_config = None
        api_key = ""
    report = service.create_report(user_id=current_user.id, payload=payload.model_dump(), model_config=model_config, api_key=api_key, ai_client=get_text_ai_client())
    return _serialize_report(report)


@router.post("/reports/{report_id}/rerun")
def rerun_report(report_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    original = db.scalar(select(AnalysisReport).where(AnalysisReport.id == report_id, AnalysisReport.user_id == current_user.id))
    if original is None:
        raise HTTPException(status_code=404, detail="Analysis report not found")
    payload = dict(original.input_config or {})
    payload["title"] = f"{original.title} - 重跑"
    payload["rerun_from_report_id"] = original.id
    model_config, api_key = _text_model_context(db, current_user)
    report = XhsAnalysisCenterService(db).create_report(user_id=current_user.id, payload=payload, model_config=model_config, api_key=api_key, ai_client=get_text_ai_client())
    report.rerun_from_report_id = original.id
    db.add(report)
    db.commit()
    db.refresh(report)
    return _serialize_report(report)
```

- [ ] **Step 3: Include router in main app**

Modify `backend/app/main.py`:

```python
from backend.app.api.platforms.xhs import analysis_center, analytics, crawl, creator, monitoring, pc
```

Add include near the existing XHS analytics include:

```python
app.include_router(analysis_center.router, prefix="/api")
```

- [ ] **Step 4: Run API tests**

Run:

```bash
pytest tests/backend/test_xhs_analysis_center.py -v
```

Expected: current backend analysis-center tests pass.

---

## Task 8: Add draft skeleton generation from edited topic cards

**Files:**
- Modify: `backend/app/services/xhs_analysis_center_service.py`
- Modify: `backend/app/api/platforms/xhs/analysis_center.py`
- Test: `tests/backend/test_xhs_analysis_center.py`

- [ ] **Step 1: Add draft tests**

```python
def test_create_drafts_from_topic_cards_saves_skeleton_only(db_session: Session):
    user = _create_user(db_session, "drafts")
    service = XhsAnalysisCenterService(db_session)
    cards = [_valid_ai_result(["metric:question_rate"])["topic_cards"][0]]

    drafts = service.create_drafts_from_topic_cards(user_id=user.id, topic_cards=cards)

    assert len(drafts) == 1
    assert drafts[0].platform == "xhs"
    assert "正文结构大纲" in drafts[0].body
    assert "风险提醒" in drafts[0].body
    assert "完整正文" not in drafts[0].body
```

- [ ] **Step 2: Implement draft skeleton method**

Add method:

```python
    def create_drafts_from_topic_cards(self, *, user_id: int, topic_cards: list[dict[str, Any]]) -> list[Any]:
        from backend.app.models.ai import AiDraft

        drafts = []
        for card in topic_cards:
            title = str(card.get("title_direction", "小红书选题草稿骨架"))[:256]
            tags = [{"name": str(tag)} for tag in card.get("tags", []) if str(tag).strip()]
            body = "\n".join(
                [
                    f"标题方向：{title}",
                    f"目标用户痛点：{card.get('target_pain', '')}",
                    f"内容角度：{card.get('content_angle', '')}",
                    "正文结构大纲：",
                    *[f"- {item}" for item in card.get("recommended_structure", [])],
                    f"推荐内容形态：{', '.join(card.get('recommended_content_form', []))}",
                    f"封面建议：{card.get('cover_suggestion', '')}",
                    f"预期优势：{card.get('expected_advantage', '')}",
                    f"参考证据：{', '.join(card.get('evidence_ids', []))}",
                    f"风险提醒：{card.get('risk_warning', '')}",
                ]
            )
            draft = AiDraft(user_id=user_id, platform="xhs", title=title, body=body, tags=tags, source_note_id=None)
            self.db.add(draft)
            drafts.append(draft)
        self.db.commit()
        for draft in drafts:
            self.db.refresh(draft)
        return drafts
```

- [ ] **Step 3: Add API route for drafts**

Add route to `analysis_center.py`:

```python
@router.post("/reports/{report_id}/topic-cards/{card_id}/drafts")
def create_drafts_from_topic_card(report_id: int, card_id: str, payload: CreateDraftFromTopicCardsPayload, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    report = db.scalar(select(AnalysisReport).where(AnalysisReport.id == report_id, AnalysisReport.user_id == current_user.id))
    if report is None:
        raise HTTPException(status_code=404, detail="Analysis report not found")
    drafts = XhsAnalysisCenterService(db).create_drafts_from_topic_cards(user_id=current_user.id, topic_cards=payload.topic_cards)
    return [{"id": draft.id, "platform": draft.platform, "title": draft.title, "body": draft.body, "tags": draft.tags or [], "source_note_id": draft.source_note_id, "created_at": draft.created_at.isoformat()} for draft in drafts]
```

The `card_id` path parameter is used for route readability and future audit trails; the payload carries the edited topic cards because the user can modify a card before creating the draft skeleton.

- [ ] **Step 4: Run draft tests**

Run:

```bash
pytest tests/backend/test_xhs_analysis_center.py::test_create_drafts_from_topic_cards_saves_skeleton_only -v
```

Expected: pass.

---

## Task 9: Add frontend types and API client helpers

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Add TypeScript types**

Append to `frontend/src/types/index.ts` near existing analytics and keyword group types:

```typescript
export type AnalysisReportStatus = "pending" | "running" | "completed" | "failed";

export type AnalysisDataHealth = {
  status: "insufficient" | "minimum" | "standard";
  can_generate: boolean;
  confidence_cap: "none" | "low" | "medium" | "high";
  metrics: {
    valid_note_count: number;
    comment_count: number;
    covered_keyword_count: number;
    representative_note_count: number;
    high_engagement_note_count: number;
    total_engagement?: number;
  };
  missing: Array<{ key: string; message: string; current: number; required: number }>;
  warnings: string[];
  collection_plan: {
    needed: boolean;
    recommended_keywords: string[];
    recommended_notes_per_keyword: number;
    should_collect_comments: boolean;
  };
};

export type AnalysisEvidencePool = {
  notes: Array<{ evidence_id: string; note_id: number; title: string; author_name: string; likes: number; collects: number; comments: number; shares: number; engagement: number; matched_keywords: string[]; excerpt: string }>;
  comments: Array<{ evidence_id: string; comment_id: number; note_id: number; content: string; like_count: number; signals: string[] }>;
  keywords: Array<{ evidence_id: string; keyword: string; matched_notes: number; matched_comments: number }>;
  metrics: Array<{ evidence_id: string; name: string; value: number; description: string }>;
  benchmarks: Array<Record<string, unknown>>;
};

export type InsightCard = {
  id: string;
  title: string;
  score: number;
  sub_scores: { traffic_potential: number; demand_strength: number; competition_pressure: number; actionability: number };
  confidence: "low" | "medium" | "high";
  confidence_reason: string;
  facts: Array<Record<string, unknown>>;
  inferences: Array<Record<string, unknown>>;
  recommendations: Array<Record<string, unknown>>;
  evidence_ids: string[];
  topic_card_ids: string[];
};

export type TopicCard = {
  id: string;
  insight_id: string;
  title_direction: string;
  target_pain: string;
  content_angle: string;
  recommended_structure: string[];
  recommended_content_form: string[];
  tags: string[];
  cover_suggestion: string;
  expected_advantage: string;
  risk_warning: string;
  evidence_ids: string[];
};

export type AnalysisResultJson = {
  summary: {
    facts: Array<{ id: string; text: string; evidence_ids: string[] }>;
    inferences: Array<{ id: string; text: string; evidence_ids: string[] }>;
    recommendations: Array<{ id: string; text: string; evidence_ids: string[] }>;
  };
  insight_cards: InsightCard[];
  topic_cards: TopicCard[];
  report_warnings: string[];
};

export type AnalysisReport = {
  id: number;
  platform: PlatformId;
  report_type: string;
  status: AnalysisReportStatus;
  title: string;
  input_config: Record<string, unknown>;
  data_health: AnalysisDataHealth;
  evidence_pool: AnalysisEvidencePool;
  result_json?: AnalysisResultJson | null;
  html_file_path: string;
  error_message?: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
};

export type AnalysisHealthPayload = {
  keyword_group_id: number;
  excluded_note_ids?: number[];
  source_note_ids?: number[];
  benchmark_target_ids?: number[];
};

export type CreateAnalysisReportPayload = AnalysisHealthPayload & {
  title: string;
};

export type CreateDraftFromTopicCardsPayload = {
  topic_cards: TopicCard[];
};
```

- [ ] **Step 2: Add API helper functions**

Add imports for the new types in `frontend/src/lib/api.ts`, then add functions following the existing axios helper style:

```typescript
export async function fetchXhsAnalysisReports(): Promise<AnalysisReport[]> {
  const { data } = await api.get<AnalysisReport[]>("/xhs/analytics/analysis/reports");
  return data;
}

export async function fetchXhsAnalysisReport(reportId: number): Promise<AnalysisReport> {
  const { data } = await api.get<AnalysisReport>(`/xhs/analytics/analysis/reports/${reportId}`);
  return data;
}

export async function checkXhsAnalysisHealth(payload: AnalysisHealthPayload): Promise<AnalysisDataHealth> {
  const { data } = await api.post<AnalysisDataHealth>("/xhs/analytics/analysis/health", payload);
  return data;
}

export async function createXhsAnalysisCollectionPlan(payload: AnalysisHealthPayload): Promise<AnalysisDataHealth["collection_plan"]> {
  const { data } = await api.post<AnalysisDataHealth["collection_plan"]>("/xhs/analytics/analysis/collection-plan", payload);
  return data;
}

export async function createXhsAnalysisReport(payload: CreateAnalysisReportPayload): Promise<AnalysisReport> {
  const { data } = await api.post<AnalysisReport>("/xhs/analytics/analysis/reports", payload);
  return data;
}

export async function rerunXhsAnalysisReport(reportId: number): Promise<AnalysisReport> {
  const { data } = await api.post<AnalysisReport>(`/xhs/analytics/analysis/reports/${reportId}/rerun`);
  return data;
}

export async function createXhsAnalysisDrafts(reportId: number, cardId: string, payload: CreateDraftFromTopicCardsPayload): Promise<Draft[]> {
  const { data } = await api.post<Draft[]>(`/xhs/analytics/analysis/reports/${reportId}/topic-cards/${cardId}/drafts`, payload);
  return data;
}
```

- [ ] **Step 3: Type-check frontend**

Run:

```bash
cd frontend && npm run build
```

Expected: if the page is not yet changed, build should either pass or fail only on unused imports introduced in this step. Remove unused imports before continuing.

---

## Task 10: Upgrade analytics page into 小红书分析中心

**Files:**
- Modify: `frontend/src/pages/platforms/xhs/analytics-page.tsx`

- [ ] **Step 1: Replace the old development banner with target-oriented title and actions**

Use the existing page as the base and keep the old overview cards. Add these state fields:

```typescript
const [analysisReports, setAnalysisReports] = useState<AnalysisReport[]>([]);
const [selectedReport, setSelectedReport] = useState<AnalysisReport | null>(null);
const [wizardOpen, setWizardOpen] = useState(false);
const [keywordGroupId, setKeywordGroupId] = useState<number | undefined>();
const [excludedNoteIds, setExcludedNoteIds] = useState<number[]>([]);
const [analysisHealth, setAnalysisHealth] = useState<AnalysisDataHealth | null>(null);
const [reportTitle, setReportTitle] = useState("小红书分析报告");
const [creatingReport, setCreatingReport] = useState(false);
```

Top-level title should read:

```tsx
<Title level={2}>小红书分析中心</Title>
<Text type="secondary">从真实关键词组、笔记和评论生成有证据的洞察卡、选题卡和草稿骨架。</Text>
```

- [ ] **Step 2: Load report history**

Add loader:

```typescript
const loadAnalysisReports = async () => {
  const reports = await fetchXhsAnalysisReports();
  setAnalysisReports(reports);
  setSelectedReport((current) => current ?? reports[0] ?? null);
};
```

Call it in the page's existing `useEffect` next to the old overview loaders.

- [ ] **Step 3: Add create-report drawer with three steps**

Use Ant Design `Drawer`, `Steps`, `Form`, `Select`, `Input`, `Button`, `Alert`, `Table`, and `List`.

Step labels:

```typescript
const wizardSteps = [
  { title: "选择范围" },
  { title: "数据健康与样本预览" },
  { title: "生成确认" },
];
```

Step 1 must require `keyword_group_id` and `title`. If the page has URL search param `keyword_group_id`, initialize it and open the drawer.

Step 2 must call:

```typescript
const health = await checkXhsAnalysisHealth({ keyword_group_id: keywordGroupId, excluded_note_ids: excludedNoteIds });
setAnalysisHealth(health);
```

Step 3 must disable the generate button when:

```typescript
!analysisHealth?.can_generate
```

- [ ] **Step 4: Create report from drawer**

Add handler:

```typescript
const handleCreateAnalysisReport = async () => {
  if (!keywordGroupId || !analysisHealth?.can_generate) return;
  setCreatingReport(true);
  try {
    const report = await createXhsAnalysisReport({
      keyword_group_id: keywordGroupId,
      excluded_note_ids: excludedNoteIds,
      title: reportTitle,
    });
    setSelectedReport(report);
    await loadAnalysisReports();
    setWizardOpen(false);
    message.success(report.status === "completed" ? "分析报告已生成" : "分析报告生成失败，请查看原因");
  } finally {
    setCreatingReport(false);
  }
};
```

- [ ] **Step 5: Show report list and report detail states**

Report list must show title, status, created time, and health status. Detail area must show:

- `failed`: `Alert` with `error_message` and no partial AI text.
- `completed`: summary facts/inferences/recommendations, insight cards, topic cards, evidence collapse, HTML path/download entry.
- empty: guide the user to choose a keyword group and create a report.

- [ ] **Step 6: Add topic-card edit and draft button**

For each `TopicCard`, render editable fields for `title_direction`, `target_pain`, `content_angle`, `recommended_structure`, `tags`, `cover_suggestion`, and `risk_warning`. On draft creation call:

```typescript
await createXhsAnalysisDrafts(selectedReport.id, card.id, { topic_cards: [editedCard] });
message.success("草稿骨架已保存到草稿工坊");
```

Do not generate full body copy on this page.

- [ ] **Step 7: Build frontend**

Run:

```bash
cd frontend && npm run build
```

Expected: TypeScript and Vite build pass.

---

## Task 11: Add keyword group entry into analysis center

**Files:**
- Modify: `frontend/src/pages/platforms/xhs/keywords-page.tsx`

- [ ] **Step 1: Add navigation import**

Use the existing router style in the file. Add:

```typescript
import { useNavigate } from "react-router-dom";
```

Inside component:

```typescript
const navigate = useNavigate();
```

- [ ] **Step 2: Add analysis action to each keyword group row/card**

Where the row actions are rendered, add:

```tsx
<Button
  size="small"
  onClick={() => navigate(`/platforms/xhs/analytics?keyword_group_id=${record.id}`)}
>
  分析
</Button>
```

If the page uses cards instead of table records in the current branch, use the keyword group variable available in that render scope instead of `record`.

- [ ] **Step 3: Verify URL prefill in analytics page**

In `analytics-page.tsx`, read URL params:

```typescript
const [searchParams] = useSearchParams();
useEffect(() => {
  const groupId = Number(searchParams.get("keyword_group_id"));
  if (groupId > 0) {
    setKeywordGroupId(groupId);
    setReportTitle(`小红书分析报告 - 关键词组 ${groupId}`);
    setWizardOpen(true);
  }
}, [searchParams]);
```

If keyword group names are already loaded on the page, replace the generic title with the actual group name.

- [ ] **Step 4: Build frontend**

Run:

```bash
cd frontend && npm run build
```

Expected: build passes.

---

## Task 12: Final backend and frontend verification

**Files:**
- All files touched by the previous tasks

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
pytest tests/backend/test_xhs_analysis_center.py -v
```

Expected: all tests pass.

- [ ] **Step 2: Run existing backend API regression tests**

Run:

```bash
pytest tests/backend/test_api.py -v
```

Expected: pass. If unrelated existing tests fail because of local environment data, report exact failures and do not hide them.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: pass.

- [ ] **Step 4: Manual smoke test with real existing data**

Start backend on project port `18081` and frontend on `18080` using existing project commands. Then verify:

1. Open `/platforms/xhs/keywords`.
2. Click one keyword group's “分析”.
3. Confirm `/platforms/xhs/analytics?keyword_group_id=<id>` opens 小红书分析中心 drawer.
4. Run health check.
5. If insufficient, verify no model call is made and collection plan is shown.
6. If sufficient and model is configured, generate report.
7. Verify completed report shows facts, inferences, recommendations, insight cards, topic cards, evidence IDs, and HTML export path.
8. Verify failed report shows error message and no partial AI output.
9. Edit one topic card and create a draft skeleton.
10. Confirm draft appears in 草稿工坊 and contains outline, tags, cover suggestion, evidence summary, and risk warning, not a full fabricated article.

- [ ] **Step 5: Report verification outcome**

Final implementation report must state:

- Files changed.
- Tests run and exact pass/fail result.
- Whether a real report was generated or blocked by health/model gates.
- Any skipped verification and the reason.
- Any existing unrelated failures.

---

## Self-Review Checklist

### Spec coverage

- Keyword group / note range input: Task 2, Task 10, Task 11.
- Data health gate: Task 2, Task 7, Task 10.
- Sample exclusion: Task 2 and Task 10 through `excluded_note_ids`.
- Minimum and standard thresholds: Task 2.
- No model when insufficient: Task 5.
- No report when no model: Task 5 and Task 7 through `_text_model_context` fallback to failed report.
- Evidence pool: Task 3.
- Structured AI JSON: Task 4 and Task 5.
- Schema/evidence/confidence validation: Task 4.
- Report snapshot: Task 1 and Task 5.
- Failed snapshot: Task 5.
- Static HTML: Task 6.
- Draft skeleton: Task 8.
- Frontend analysis center: Task 9 and Task 10.
- Keyword group entry: Task 11.
- Tests and verification: Task 12.

### Placeholder scan

The plan intentionally avoids undefined implementation blanks. Branch-specific instructions are limited to verifiable conditions, such as checking the current Alembic head and using the current file's existing style.

### Type consistency

- Backend report field names match the spec: `input_config`, `data_health`, `evidence_pool`, `result_json`, `html_file_path`, `error_message`.
- API helper names match the spec: `fetchXhsAnalysisReports`, `createXhsAnalysisReport`, `fetchXhsAnalysisReport`, `rerunXhsAnalysisReport`, `checkXhsAnalysisHealth`, `createXhsAnalysisDrafts`, `createXhsAnalysisCollectionPlan`.
- Frontend types match backend JSON keys and keep snake_case for API payload fields.

## Done Definition

The first version is done only when all of these are true:

- A user can enter from a real keyword group.
- The system checks real stored notes/comments before model use.
- Below minimum data does not call the model and does not generate a report.
- Missing model does not generate a fake report.
- AI output is JSON and passes backend validation.
- Every displayed fact, insight, and topic card has valid evidence IDs.
- A completed report is saved and can be reopened from history.
- A failed report shows a clear reason and no partial AI text.
- Static HTML is generated only for completed reports.
- Edited topic cards can create draft skeletons in the existing draft table.
- Product UI contains no demo/fake data/report mode.
- Focused backend tests and frontend build have been run and reported honestly.

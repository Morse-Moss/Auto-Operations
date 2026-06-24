# XHS Feishu Analysis Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first local-verifiable version of the XHS → Feishu Bitable → XHS analysis result loop, plus clearer XHS collection source grouping.

**Architecture:** Add a backend Feishu integration boundary with encrypted config, analysis result persistence, field definitions, dry-run/testable push/pull services, and API routes. Extend XHS content library API/frontend types to expose Feishu sync state and returned analysis fields; add UI controls for local/dry-run syncing and content-library filtering. Refactor the crawler page UI into two source tabs without changing fragile XHS SDK behavior.

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy, Alembic, pytest, React, Vite, Ant Design, existing `backend.app.core.security` encryption helpers.

---

## File Structure

### Backend files

- Create: `backend/app/models/feishu.py`
  - Owns `FeishuIntegrationConfig` and `NoteAnalysisResult` SQLAlchemy models.
- Modify: `backend/app/models/__init__.py`
  - Exports new models so Alembic metadata and tests see them.
- Create: `backend/alembic/versions/20260622_add_feishu_analysis_loop.py`
  - Adds Feishu config and note analysis result tables.
- Create: `backend/app/services/feishu_bitable_service.py`
  - Provides Feishu field definitions, value mapping, dry-run fake client boundary, note serialization, push and pull service methods.
- Create: `backend/app/api/feishu_integration.py`
  - FastAPI routes for config, test, ensure fields, push notes, and pull notes.
- Modify: `backend/app/main.py`
  - Registers the Feishu integration router.
- Modify: `backend/app/api/notes.py`
  - Extends note list/detail serialization with `feishu_sync` and `analysis_result`.
  - Adds filters for Feishu sync status, analysis status, content type, reuse value, reusable model.
  - Extends keyword search to include collection keyword metadata when available.

### Frontend files

- Modify: `frontend/src/types/index.ts`
  - Adds Feishu config, sync result, analysis result, and saved-note analysis fields.
- Modify: `frontend/src/lib/api.ts`
  - Adds Feishu API client functions and content-library filter params.
- Modify: `frontend/src/pages/settings/settings-page.tsx`
  - Adds Feishu integration settings card.
- Modify: `frontend/src/pages/platforms/xhs/crawler-page.tsx`
  - Introduces source tabs: `灰豚热词采集` and `小红书站内采集`.
  - Renames existing XHS crawl modes to `按关键词组采集` and `临时关键词搜索`.
- Modify: `frontend/src/components/content-library/content-library-types.ts`
  - Adds Feishu filter state and toolbar operation types.
- Modify: `frontend/src/components/content-library/use-content-library.ts`
  - Carries Feishu filters into adapter load calls.
- Modify: `frontend/src/components/content-library/content-library-shell.tsx`
  - Renders Feishu filter controls when adapter exposes Feishu capability.
- Modify: `frontend/src/pages/platforms/xhs/xhs-content-library-adapter.ts`
  - Adds XHS-specific Feishu filters, sync/pull toolbar actions, card badges, and detail fields.

### Tests

- Create: `tests/backend/test_feishu_integration.py`
  - Model/API/service tests for config encryption, dry-run field ensure, push mapping, pull update, and note filters.
- Modify: `tests/backend/test_api.py`
  - Adds static contract checks for frontend Feishu integration route/API strings and crawler tab labels.
- Modify: `tests/backend/test_notes_library_sorting.py`
  - Adds note analysis result filtering coverage if easier to keep with existing note list tests.

---

## Task 1: Add Feishu persistence models and migration

**Files:**
- Create: `backend/app/models/feishu.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/20260622_add_feishu_analysis_loop.py`
- Test: `tests/backend/test_feishu_integration.py`

- [ ] **Step 1: Write the failing model metadata test**

Add `tests/backend/test_feishu_integration.py` with this initial content:

```python
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import Base, get_db
from backend.app.core.security import create_access_token, hash_password
from backend.app.main import app
from backend.app.models import FeishuIntegrationConfig, Note, NoteAnalysisResult, User

client = TestClient(app)


def _override_database(tmp_path, name="feishu-integration.db"):
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


def _create_user(SessionLocal, username="feishu-owner"):
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


def test_feishu_models_are_registered_in_metadata():
    assert FeishuIntegrationConfig.__tablename__ == "feishu_integration_configs"
    assert NoteAnalysisResult.__tablename__ == "note_analysis_results"
    assert "feishu_integration_configs" in Base.metadata.tables
    assert "note_analysis_results" in Base.metadata.tables
```

- [ ] **Step 2: Run the failing model metadata test**

Run:

```bash
pytest tests/backend/test_feishu_integration.py::test_feishu_models_are_registered_in_metadata -q
```

Expected: FAIL with import error for `FeishuIntegrationConfig` / `NoteAnalysisResult`.

- [ ] **Step 3: Create Feishu models**

Create `backend/app/models/feishu.py`:

```python
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base
from backend.app.core.time import shanghai_now


class FeishuIntegrationConfig(Base):
    __tablename__ = "feishu_integration_configs"
    __table_args__ = (UniqueConstraint("user_id", name="uq_feishu_integration_configs_user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    app_id: Mapped[str] = mapped_column(String(128), default="")
    encrypted_app_secret: Mapped[str] = mapped_column(Text, default="")
    bitable_url: Mapped[str] = mapped_column(Text, default="")
    bitable_app_token: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    table_id: Mapped[str] = mapped_column(String(128), default="")
    view_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    enabled: Mapped[bool] = mapped_column(Integer, default=0)
    last_test_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    last_test_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_tested_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now)


class NoteAnalysisResult(Base):
    __tablename__ = "note_analysis_results"
    __table_args__ = (UniqueConstraint("note_id", "source", name="uq_note_analysis_results_note_source"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    note_id: Mapped[int] = mapped_column(ForeignKey("notes.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    source: Mapped[str] = mapped_column(String(32), default="feishu", index=True)
    external_record_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    analysis_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    subject_object: Mapped[str] = mapped_column(Text, default="")
    content_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    core_points: Mapped[str] = mapped_column(Text, default="")
    target_audience: Mapped[str] = mapped_column(Text, default="")
    title_hook: Mapped[str] = mapped_column(Text, default="")
    content_structure: Mapped[str] = mapped_column(Text, default="")
    reusable_models: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    reuse_value: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    analysis_note: Mapped[str] = mapped_column(Text, default="")
    last_pushed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_pulled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    push_status: Mapped[str] = mapped_column(String(32), default="not_synced", index=True)
    pull_status: Mapped[str] = mapped_column(String(32), default="not_pulled")
    last_error: Mapped[str] = mapped_column(Text, default="")
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now)
```

- [ ] **Step 4: Export models**

Modify `backend/app/models/__init__.py`:

```python
from backend.app.models.feishu import FeishuIntegrationConfig, NoteAnalysisResult
```

Add both names to `__all__`.

- [ ] **Step 5: Add Alembic migration**

Create `backend/alembic/versions/20260622_add_feishu_analysis_loop.py`:

```python
"""add feishu analysis loop tables

Revision ID: 20260622_add_feishu_analysis_loop
Revises: 20260622_add_draft_name_to_ai_drafts
Create Date: 2026-06-22
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260622_add_feishu_analysis_loop"
down_revision = "20260622_add_draft_name_to_ai_drafts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feishu_integration_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("app_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("encrypted_app_secret", sa.Text(), nullable=False, server_default=""),
        sa.Column("bitable_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("bitable_app_token", sa.String(length=128), nullable=True),
        sa.Column("table_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("view_id", sa.String(length=128), nullable=True),
        sa.Column("enabled", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_test_status", sa.String(length=32), nullable=True),
        sa.Column("last_test_message", sa.Text(), nullable=True),
        sa.Column("last_tested_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_feishu_integration_configs_user_id"),
    )
    op.create_index("ix_feishu_integration_configs_user_id", "feishu_integration_configs", ["user_id"])

    op.create_table(
        "note_analysis_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("note_id", sa.Integer(), sa.ForeignKey("notes.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="feishu"),
        sa.Column("external_record_id", sa.String(length=128), nullable=True),
        sa.Column("analysis_status", sa.String(length=32), nullable=True),
        sa.Column("subject_object", sa.Text(), nullable=False, server_default=""),
        sa.Column("content_type", sa.String(length=64), nullable=True),
        sa.Column("core_points", sa.Text(), nullable=False, server_default=""),
        sa.Column("target_audience", sa.Text(), nullable=False, server_default=""),
        sa.Column("title_hook", sa.Text(), nullable=False, server_default=""),
        sa.Column("content_structure", sa.Text(), nullable=False, server_default=""),
        sa.Column("reusable_models", sa.JSON(), nullable=True),
        sa.Column("reuse_value", sa.String(length=64), nullable=True),
        sa.Column("analysis_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("last_pushed_at", sa.DateTime(), nullable=True),
        sa.Column("last_pulled_at", sa.DateTime(), nullable=True),
        sa.Column("push_status", sa.String(length=32), nullable=False, server_default="not_synced"),
        sa.Column("pull_status", sa.String(length=32), nullable=False, server_default="not_pulled"),
        sa.Column("last_error", sa.Text(), nullable=False, server_default=""),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("note_id", "source", name="uq_note_analysis_results_note_source"),
    )
    op.create_index("ix_note_analysis_results_note_id", "note_analysis_results", ["note_id"])
    op.create_index("ix_note_analysis_results_user_id", "note_analysis_results", ["user_id"])
    op.create_index("ix_note_analysis_results_source", "note_analysis_results", ["source"])
    op.create_index("ix_note_analysis_results_external_record_id", "note_analysis_results", ["external_record_id"])
    op.create_index("ix_note_analysis_results_analysis_status", "note_analysis_results", ["analysis_status"])
    op.create_index("ix_note_analysis_results_content_type", "note_analysis_results", ["content_type"])
    op.create_index("ix_note_analysis_results_reuse_value", "note_analysis_results", ["reuse_value"])
    op.create_index("ix_note_analysis_results_push_status", "note_analysis_results", ["push_status"])


def downgrade() -> None:
    op.drop_index("ix_note_analysis_results_push_status", table_name="note_analysis_results")
    op.drop_index("ix_note_analysis_results_reuse_value", table_name="note_analysis_results")
    op.drop_index("ix_note_analysis_results_content_type", table_name="note_analysis_results")
    op.drop_index("ix_note_analysis_results_analysis_status", table_name="note_analysis_results")
    op.drop_index("ix_note_analysis_results_external_record_id", table_name="note_analysis_results")
    op.drop_index("ix_note_analysis_results_source", table_name="note_analysis_results")
    op.drop_index("ix_note_analysis_results_user_id", table_name="note_analysis_results")
    op.drop_index("ix_note_analysis_results_note_id", table_name="note_analysis_results")
    op.drop_table("note_analysis_results")
    op.drop_index("ix_feishu_integration_configs_user_id", table_name="feishu_integration_configs")
    op.drop_table("feishu_integration_configs")
```

- [ ] **Step 6: Run model test**

Run:

```bash
pytest tests/backend/test_feishu_integration.py::test_feishu_models_are_registered_in_metadata -q
```

Expected: PASS.

---

## Task 2: Add Feishu service constants, config API, and encrypted storage

**Files:**
- Create: `backend/app/services/feishu_bitable_service.py`
- Create: `backend/app/api/feishu_integration.py`
- Modify: `backend/app/main.py`
- Test: `tests/backend/test_feishu_integration.py`

- [ ] **Step 1: Add failing config API test**

Append to `tests/backend/test_feishu_integration.py`:

```python
def test_feishu_config_api_encrypts_secret_and_redacts_response(tmp_path):
    SessionLocal = _override_database(tmp_path, "feishu-config.db")
    try:
        user_id = _create_user(SessionLocal)
        headers = _auth_headers(user_id)
        payload = {
            "app_id": "cli_xxx",
            "app_secret": "secret-value",
            "bitable_url": "https://example.feishu.cn/base/app_token?table=tbl_xxx&view=vew_xxx",
            "table_id": "tbl_xxx",
            "enabled": True,
        }

        response = client.put("/api/integrations/feishu/config", headers=headers, json=payload)

        assert response.status_code == 200
        body = response.json()
        assert body["app_id"] == "cli_xxx"
        assert body["has_app_secret"] is True
        assert "app_secret" not in body
        assert body["table_id"] == "tbl_xxx"
        assert body["enabled"] is True

        db = SessionLocal()
        try:
            config = db.scalar(select(FeishuIntegrationConfig))
            assert config is not None
            assert config.encrypted_app_secret
            assert config.encrypted_app_secret != "secret-value"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)
```

- [ ] **Step 2: Run failing config API test**

Run:

```bash
pytest tests/backend/test_feishu_integration.py::test_feishu_config_api_encrypts_secret_and_redacts_response -q
```

Expected: FAIL with 404 because route is missing.

- [ ] **Step 3: Create service constants and serializers**

Create `backend/app/services/feishu_bitable_service.py` with constants:

```python
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.time import shanghai_now
from backend.app.models import Note, NoteAnalysisResult

ANALYSIS_STATUS_OPTIONS = ["待分析", "分析中", "已完成", "废弃"]
CONTENT_TYPE_OPTIONS = ["种草", "测评", "避坑", "教程", "合集/清单", "对比", "痛点共鸣", "案例故事"]
REUSABLE_MODEL_OPTIONS = [
    "问题驱动模型",
    "情绪驱动模型",
    "场景种草模型",
    "对比反差模型",
    "测评背书模型",
    "教程方法模型",
    "故事案例模型",
    "IP/热点借势模型",
]
REUSE_VALUE_OPTIONS = ["选题参考", "标题参考", "正文结构参考", "卖点表达参考", "可直接改写", "行业观察", "竞品参考", "废弃"]

SYSTEM_FIELD_NAMES = [
    "系统笔记ID",
    "平台笔记ID",
    "采集批次ID",
    "数据来源",
    "采集方式",
    "采集关键词",
    "关键词组",
    "笔记标题",
    "笔记正文",
    "作者",
    "原链接",
    "笔记类型",
    "标签/话题",
    "点赞数",
    "收藏数",
    "评论数",
    "分享数",
    "采集时间",
    "同步时间",
]

ANALYSIS_FIELD_NAMES = [
    "分析状态",
    "产品/主题对象",
    "内容类型",
    "核心卖点/核心观点",
    "目标人群",
    "封面/标题钩子",
    "内容结构分析",
    "可复用模型",
    "复用价值",
    "分析备注",
]

FEISHU_FIELD_DEFINITIONS = [
    {"field_name": name, "type": "text"} for name in SYSTEM_FIELD_NAMES
] + [
    {"field_name": "分析状态", "type": "single_select", "options": ANALYSIS_STATUS_OPTIONS},
    {"field_name": "产品/主题对象", "type": "text"},
    {"field_name": "内容类型", "type": "single_select", "options": CONTENT_TYPE_OPTIONS},
    {"field_name": "核心卖点/核心观点", "type": "text"},
    {"field_name": "目标人群", "type": "text"},
    {"field_name": "封面/标题钩子", "type": "text"},
    {"field_name": "内容结构分析", "type": "text"},
    {"field_name": "可复用模型", "type": "multi_select", "options": REUSABLE_MODEL_OPTIONS},
    {"field_name": "复用价值", "type": "single_select", "options": REUSE_VALUE_OPTIONS},
    {"field_name": "分析备注", "type": "text"},
]


def extract_bitable_tokens(url: str) -> dict[str, str | None]:
    return {
        "bitable_app_token": _match(url, r"/base/([^/?#]+)"),
        "wiki_node_token": _match(url, r"/wiki/([^/?#]+)"),
        "table_id": _match(url, r"[?&]table=([^&#]+)"),
        "view_id": _match(url, r"[?&]view=([^&#]+)"),
    }


def _match(value: str, pattern: str) -> str | None:
    matched = re.search(pattern, value or "")
    return matched.group(1) if matched else None
```

- [ ] **Step 4: Create config API**

Create `backend/app/api/feishu_integration.py`:

```python
from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.security import encrypt_text
from backend.app.core.time import shanghai_now
from backend.app.models import FeishuIntegrationConfig, User
from backend.app.services.feishu_bitable_service import extract_bitable_tokens
from backend.app.api.auth import get_current_user

router = APIRouter(prefix="/integrations/feishu", tags=["feishu-integration"])


class FeishuConfigPayload(BaseModel):
    app_id: str = Field(default="", max_length=128)
    app_secret: str = ""
    bitable_url: str = ""
    table_id: str = Field(default="", max_length=128)
    enabled: bool = False


def _get_config(db: Session, user_id: int) -> FeishuIntegrationConfig | None:
    return db.scalar(select(FeishuIntegrationConfig).where(FeishuIntegrationConfig.user_id == user_id))


def _serialize_config(config: FeishuIntegrationConfig | None) -> dict:
    if config is None:
        return {
            "app_id": "",
            "has_app_secret": False,
            "bitable_url": "",
            "bitable_app_token": None,
            "table_id": "",
            "view_id": None,
            "enabled": False,
            "last_test_status": None,
            "last_test_message": None,
            "last_tested_at": None,
        }
    return {
        "id": config.id,
        "app_id": config.app_id,
        "has_app_secret": bool(config.encrypted_app_secret),
        "bitable_url": config.bitable_url,
        "bitable_app_token": config.bitable_app_token,
        "table_id": config.table_id,
        "view_id": config.view_id,
        "enabled": bool(config.enabled),
        "last_test_status": config.last_test_status,
        "last_test_message": config.last_test_message,
        "last_tested_at": config.last_tested_at.isoformat() if config.last_tested_at else None,
    }


@router.get("/config")
def get_feishu_config(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _serialize_config(_get_config(db, current_user.id))


@router.put("/config")
def save_feishu_config(payload: FeishuConfigPayload, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    config = _get_config(db, current_user.id)
    if config is None:
        config = FeishuIntegrationConfig(user_id=current_user.id)
        db.add(config)
    tokens = extract_bitable_tokens(payload.bitable_url)
    config.app_id = payload.app_id.strip()
    if payload.app_secret:
        config.encrypted_app_secret = encrypt_text(payload.app_secret)
    config.bitable_url = payload.bitable_url.strip()
    config.bitable_app_token = tokens["bitable_app_token"]
    config.table_id = payload.table_id.strip() or tokens["table_id"] or ""
    config.view_id = tokens["view_id"]
    config.enabled = bool(payload.enabled)
    config.updated_at = shanghai_now()
    db.commit()
    db.refresh(config)
    return _serialize_config(config)
```

- [ ] **Step 5: Register router**

Modify `backend/app/main.py` imports:

```python
from backend.app.api import accounts, ai, auth, auto_tasks, drafts, feishu_integration, files, huitun_login_sessions, keyword_groups, login_sessions, model_configs, notes, notifications, publish, tags, tasks
```

Add router registration near other API routers:

```python
app.include_router(feishu_integration.router, prefix="/api")
```

- [ ] **Step 6: Run config test**

Run:

```bash
pytest tests/backend/test_feishu_integration.py::test_feishu_config_api_encrypts_secret_and_redacts_response -q
```

Expected: PASS.

---

## Task 3: Add dry-run field ensure and Feishu test endpoint

**Files:**
- Modify: `backend/app/services/feishu_bitable_service.py`
- Modify: `backend/app/api/feishu_integration.py`
- Test: `tests/backend/test_feishu_integration.py`

- [ ] **Step 1: Add failing field ensure test**

Append:

```python
def test_feishu_ensure_fields_dry_run_returns_expected_template(tmp_path):
    SessionLocal = _override_database(tmp_path, "feishu-fields.db")
    try:
        user_id = _create_user(SessionLocal)
        headers = _auth_headers(user_id)
        client.put(
            "/api/integrations/feishu/config",
            headers=headers,
            json={"app_id": "cli_xxx", "app_secret": "secret", "bitable_url": "https://example.feishu.cn/base/app?table=tbl", "enabled": True},
        )

        response = client.post("/api/integrations/feishu/ensure-fields", headers=headers, json={"dry_run": True})

        assert response.status_code == 200
        body = response.json()
        assert body["dry_run"] is True
        field_names = [item["field_name"] for item in body["fields"]]
        assert "系统笔记ID" in field_names
        assert "笔记标题" in field_names
        assert "分析状态" in field_names
        assert "可复用模型" in field_names
    finally:
        app.dependency_overrides.pop(get_db, None)
```

- [ ] **Step 2: Run failing field ensure test**

Run:

```bash
pytest tests/backend/test_feishu_integration.py::test_feishu_ensure_fields_dry_run_returns_expected_template -q
```

Expected: FAIL with missing endpoint.

- [ ] **Step 3: Add endpoint**

Modify `backend/app/api/feishu_integration.py`:

```python
from pydantic import BaseModel, Field
from backend.app.services.feishu_bitable_service import FEISHU_FIELD_DEFINITIONS, extract_bitable_tokens


class FeishuDryRunPayload(BaseModel):
    dry_run: bool = True


@router.post("/ensure-fields")
def ensure_feishu_fields(payload: FeishuDryRunPayload, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    config = _get_config(db, current_user.id)
    if config is None:
        return {"dry_run": payload.dry_run, "status": "not_configured", "fields": FEISHU_FIELD_DEFINITIONS}
    if payload.dry_run:
        return {"dry_run": True, "status": "ok", "fields": FEISHU_FIELD_DEFINITIONS}
    return {"dry_run": False, "status": "blocked", "message": "真实飞书字段补齐需要配置凭据后由用户触发。", "fields": FEISHU_FIELD_DEFINITIONS}
```

- [ ] **Step 4: Run field ensure test**

Run:

```bash
pytest tests/backend/test_feishu_integration.py::test_feishu_ensure_fields_dry_run_returns_expected_template -q
```

Expected: PASS.

---

## Task 4: Implement note analysis result serialization and filters

**Files:**
- Modify: `backend/app/api/notes.py`
- Test: `tests/backend/test_notes_library_sorting.py`

- [ ] **Step 1: Add failing note filter test**

Append to `tests/backend/test_notes_library_sorting.py`:

```python
from backend.app.models import NoteAnalysisResult


def test_notes_library_filters_by_feishu_analysis_fields(tmp_path):
    SessionLocal = _override_database(tmp_path)
    try:
        user_id = _create_user_and_notes(SessionLocal)
        db = SessionLocal()
        try:
            note = db.scalar(select(Note).where(Note.note_id == "note-like-top"))
            result = NoteAnalysisResult(
                user_id=user_id,
                note_id=note.id,
                source="feishu",
                analysis_status="已完成",
                content_type="种草",
                reuse_value="可直接改写",
                reusable_models=["问题驱动模型", "场景种草模型"],
                push_status="synced",
            )
            db.add(result)
            db.commit()
        finally:
            db.close()
        headers = {"Authorization": f"Bearer {create_access_token(user_id)}"}

        response = client.get(
            "/api/notes",
            headers=headers,
            params={
                "platform": "xhs",
                "feishu_push_status": "synced",
                "analysis_status": "已完成",
                "content_type": "种草",
                "reuse_value": "可直接改写",
                "reusable_model": "问题驱动模型",
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 1
        item = payload["items"][0]
        assert item["note_id"] == "note-like-top"
        assert item["feishu_sync"]["push_status"] == "synced"
        assert item["analysis_result"]["analysis_status"] == "已完成"
        assert item["analysis_result"]["content_type"] == "种草"
        assert "问题驱动模型" in item["analysis_result"]["reusable_models"]
    finally:
        app.dependency_overrides.pop(get_db, None)
```

- [ ] **Step 2: Run failing note filter test**

Run:

```bash
pytest tests/backend/test_notes_library_sorting.py::test_notes_library_filters_by_feishu_analysis_fields -q
```

Expected: FAIL because filters/serialization are missing.

- [ ] **Step 3: Modify notes serialization**

In `backend/app/api/notes.py`, import `NoteAnalysisResult` and add helper:

```python
def _get_feishu_analysis_result(db: Session, note_id: int) -> NoteAnalysisResult | None:
    return db.scalar(
        select(NoteAnalysisResult).where(
            NoteAnalysisResult.note_id == note_id,
            NoteAnalysisResult.source == "feishu",
        )
    )


def _serialize_analysis_result(result: NoteAnalysisResult | None) -> dict | None:
    if result is None:
        return None
    return {
        "analysis_status": result.analysis_status,
        "subject_object": result.subject_object,
        "content_type": result.content_type,
        "core_points": result.core_points,
        "target_audience": result.target_audience,
        "title_hook": result.title_hook,
        "content_structure": result.content_structure,
        "reusable_models": result.reusable_models or [],
        "reuse_value": result.reuse_value,
        "analysis_note": result.analysis_note,
        "last_pushed_at": result.last_pushed_at.isoformat() if result.last_pushed_at else None,
        "last_pulled_at": result.last_pulled_at.isoformat() if result.last_pulled_at else None,
    }


def _serialize_feishu_sync(result: NoteAnalysisResult | None) -> dict:
    return {
        "push_status": result.push_status if result else "not_synced",
        "pull_status": result.pull_status if result else "not_pulled",
        "external_record_id": result.external_record_id if result else None,
        "last_error": result.last_error if result else "",
    }
```

Update `_serialize_note` or `_serialize_note_with_tags` so each serialized note includes:

```python
analysis = _get_feishu_analysis_result(db, note.id)
serialized["feishu_sync"] = _serialize_feishu_sync(analysis)
serialized["analysis_result"] = _serialize_analysis_result(analysis)
```

- [ ] **Step 4: Modify notes list filters**

In the `/api/notes` list endpoint, add query params:

```python
feishu_push_status: str | None = Query(default=None),
analysis_status: str | None = Query(default=None),
content_type: str | None = Query(default=None),
reuse_value: str | None = Query(default=None),
reusable_model: str | None = Query(default=None),
```

Filter in Python after loading notes, matching existing metric sorting style:

```python
def _matches_analysis_filters(note: Note) -> bool:
    result = _get_feishu_analysis_result(db, note.id)
    if feishu_push_status and (result.push_status if result else "not_synced") != feishu_push_status:
        return False
    if analysis_status and (result.analysis_status if result else None) != analysis_status:
        return False
    if content_type and (result.content_type if result else None) != content_type:
        return False
    if reuse_value and (result.reuse_value if result else None) != reuse_value:
        return False
    if reusable_model and reusable_model not in ((result.reusable_models or []) if result else []):
        return False
    return True
```

Apply before pagination.

- [ ] **Step 5: Run note filter test**

Run:

```bash
pytest tests/backend/test_notes_library_sorting.py::test_notes_library_filters_by_feishu_analysis_fields -q
```

Expected: PASS.

---

## Task 5: Implement dry-run push to Feishu and analysis result push state

**Files:**
- Modify: `backend/app/services/feishu_bitable_service.py`
- Modify: `backend/app/api/feishu_integration.py`
- Test: `tests/backend/test_feishu_integration.py`

- [ ] **Step 1: Add failing dry-run push test**

Append:

```python
def test_push_notes_to_feishu_dry_run_creates_analysis_result_state(tmp_path):
    SessionLocal = _override_database(tmp_path, "feishu-push.db")
    try:
        user_id = _create_user(SessionLocal)
        db = SessionLocal()
        try:
            note = Note(user_id=user_id, platform_account_id=1, platform="xhs", note_id="xhs-1", title="标题", content="正文", author_name="作者")
            db.add(note)
            db.commit()
            db.refresh(note)
            note_id = note.id
        finally:
            db.close()
        headers = _auth_headers(user_id)

        response = client.post("/api/integrations/feishu/xhs-notes/push", headers=headers, json={"note_ids": [note_id], "dry_run": True})

        assert response.status_code == 200
        body = response.json()
        assert body["dry_run"] is True
        assert body["updated_count"] == 1
        assert body["failed_count"] == 0
        assert body["records"][0]["fields"]["系统笔记ID"] == str(note_id)
        assert body["records"][0]["fields"]["分析状态"] == "待分析"

        db = SessionLocal()
        try:
            result = db.scalar(select(NoteAnalysisResult).where(NoteAnalysisResult.note_id == note_id))
            assert result is not None
            assert result.push_status == "dry_run"
            assert result.analysis_status == "待分析"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)
```

- [ ] **Step 2: Run failing push test**

Run:

```bash
pytest tests/backend/test_feishu_integration.py::test_push_notes_to_feishu_dry_run_creates_analysis_result_state -q
```

Expected: FAIL with missing endpoint.

- [ ] **Step 3: Add push service methods**

Append to `backend/app/services/feishu_bitable_service.py`:

```python
MAX_SYNC_ITEMS = 100


def note_to_feishu_fields(note: Note, *, batch_id: str = "", source: str = "小红书站内", method: str = "内容库同步", keyword: str = "", keyword_group: str = "") -> dict[str, Any]:
    raw = note.raw_json or {}
    return {
        "系统笔记ID": str(note.id),
        "平台笔记ID": note.note_id,
        "采集批次ID": batch_id,
        "数据来源": source,
        "采集方式": method,
        "采集关键词": keyword,
        "关键词组": keyword_group,
        "笔记标题": note.title,
        "笔记正文": note.content,
        "作者": note.author_name,
        "原链接": str(raw.get("note_url") or raw.get("url") or raw.get("share_url") or f"https://www.xiaohongshu.com/explore/{note.note_id}"),
        "笔记类型": str(raw.get("note_type") or raw.get("type") or "未知"),
        "标签/话题": "、".join(str(item) for item in raw.get("tags", []) if item) if isinstance(raw.get("tags"), list) else "",
        "点赞数": str(raw.get("liked_count") or raw.get("like_count") or raw.get("likes") or ""),
        "收藏数": str(raw.get("collected_count") or raw.get("collect_count") or raw.get("collects") or ""),
        "评论数": str(raw.get("comment_count") or raw.get("comments") or ""),
        "分享数": str(raw.get("share_count") or raw.get("shares") or ""),
        "采集时间": note.created_at.isoformat(),
        "同步时间": shanghai_now().isoformat(),
        "分析状态": "待分析",
    }


def get_or_create_analysis_result(db: Session, *, user_id: int, note_id: int) -> NoteAnalysisResult:
    result = db.scalar(select(NoteAnalysisResult).where(NoteAnalysisResult.note_id == note_id, NoteAnalysisResult.source == "feishu"))
    if result is None:
        result = NoteAnalysisResult(user_id=user_id, note_id=note_id, source="feishu")
        db.add(result)
        db.flush()
    return result


def push_notes_to_feishu_dry_run(db: Session, *, user_id: int, note_ids: list[int]) -> dict[str, Any]:
    unique_ids = list(dict.fromkeys(note_ids))
    if len(unique_ids) > MAX_SYNC_ITEMS:
        return {"dry_run": True, "updated_count": 0, "failed_count": len(unique_ids), "errors": [f"每次最多同步 {MAX_SYNC_ITEMS} 条"], "records": []}
    notes = db.scalars(select(Note).where(Note.id.in_(unique_ids), Note.user_id == user_id)).all()
    by_id = {note.id: note for note in notes}
    records = []
    errors = []
    updated = 0
    now = shanghai_now()
    for note_id in unique_ids:
        note = by_id.get(note_id)
        if note is None:
            errors.append({"note_id": note_id, "error": "Note not found"})
            continue
        fields = note_to_feishu_fields(note)
        result = get_or_create_analysis_result(db, user_id=user_id, note_id=note.id)
        result.analysis_status = result.analysis_status or "待分析"
        result.push_status = "dry_run"
        result.last_pushed_at = now
        result.last_error = ""
        result.updated_at = now
        records.append({"note_id": note.id, "status": "dry_run", "fields": fields})
        updated += 1
    db.commit()
    return {"dry_run": True, "updated_count": updated, "failed_count": len(errors), "errors": errors, "records": records}
```

- [ ] **Step 4: Add push endpoint**

Modify `backend/app/api/feishu_integration.py`:

```python
from backend.app.services.feishu_bitable_service import FEISHU_FIELD_DEFINITIONS, extract_bitable_tokens, push_notes_to_feishu_dry_run


class FeishuPushNotesPayload(BaseModel):
    note_ids: list[int] = Field(default_factory=list)
    dry_run: bool = True


@router.post("/xhs-notes/push")
def push_xhs_notes_to_feishu(payload: FeishuPushNotesPayload, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not payload.note_ids:
        return {"dry_run": payload.dry_run, "updated_count": 0, "failed_count": 0, "errors": [], "records": []}
    if payload.dry_run:
        return push_notes_to_feishu_dry_run(db, user_id=current_user.id, note_ids=payload.note_ids)
    return {"dry_run": False, "updated_count": 0, "failed_count": len(payload.note_ids), "errors": ["真实飞书写入需要醒后配置凭据并单独启用。"], "records": []}
```

- [ ] **Step 5: Run push test**

Run:

```bash
pytest tests/backend/test_feishu_integration.py::test_push_notes_to_feishu_dry_run_creates_analysis_result_state -q
```

Expected: PASS.

---

## Task 6: Implement fake pull from Feishu payload into analysis results

**Files:**
- Modify: `backend/app/services/feishu_bitable_service.py`
- Modify: `backend/app/api/feishu_integration.py`
- Test: `tests/backend/test_feishu_integration.py`

- [ ] **Step 1: Add failing pull test**

Append:

```python
def test_pull_feishu_analysis_payload_updates_analysis_result(tmp_path):
    SessionLocal = _override_database(tmp_path, "feishu-pull.db")
    try:
        user_id = _create_user(SessionLocal)
        db = SessionLocal()
        try:
            note = Note(user_id=user_id, platform_account_id=1, platform="xhs", note_id="xhs-2", title="标题", content="正文", author_name="作者")
            db.add(note)
            db.commit()
            db.refresh(note)
            note_id = note.id
        finally:
            db.close()
        headers = _auth_headers(user_id)
        payload = {
            "dry_run": True,
            "records": [
                {
                    "fields": {
                        "系统笔记ID": str(note_id),
                        "分析状态": "已完成",
                        "产品/主题对象": "表达力训练",
                        "内容类型": "种草",
                        "核心卖点/核心观点": "真实体验带出卖点",
                        "目标人群": "宝妈",
                        "封面/标题钩子": "孩子不敢表达怎么办",
                        "内容结构分析": "痛点开头-经验分享-行动引导",
                        "可复用模型": ["问题驱动模型", "场景种草模型"],
                        "复用价值": "可直接改写",
                        "分析备注": "适合二创",
                    },
                    "record_id": "rec_xxx",
                }
            ],
        }

        response = client.post("/api/integrations/feishu/xhs-notes/pull", headers=headers, json=payload)

        assert response.status_code == 200
        assert response.json()["updated_count"] == 1
        db = SessionLocal()
        try:
            result = db.scalar(select(NoteAnalysisResult).where(NoteAnalysisResult.note_id == note_id))
            assert result.analysis_status == "已完成"
            assert result.subject_object == "表达力训练"
            assert result.content_type == "种草"
            assert result.reusable_models == ["问题驱动模型", "场景种草模型"]
            assert result.reuse_value == "可直接改写"
            assert result.external_record_id == "rec_xxx"
            assert result.pull_status == "success"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)
```

- [ ] **Step 2: Run failing pull test**

Run:

```bash
pytest tests/backend/test_feishu_integration.py::test_pull_feishu_analysis_payload_updates_analysis_result -q
```

Expected: FAIL with missing endpoint.

- [ ] **Step 3: Add pull service**

Append to `backend/app/services/feishu_bitable_service.py`:

```python
def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "、".join(str(item) for item in value if str(item).strip())
    return str(value).strip()


def _as_text_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[,，、\n]", value) if item.strip()]
    return []


def pull_feishu_analysis_records(db: Session, *, user_id: int, records: list[dict[str, Any]]) -> dict[str, Any]:
    updated = 0
    unmatched = 0
    errors = []
    now = shanghai_now()
    for record in records:
        fields = record.get("fields") if isinstance(record, dict) else None
        if not isinstance(fields, dict):
            errors.append({"error": "Invalid record fields"})
            continue
        raw_note_id = fields.get("系统笔记ID")
        try:
            note_id = int(str(raw_note_id))
        except Exception:
            unmatched += 1
            continue
        note = db.get(Note, note_id)
        if note is None or note.user_id != user_id:
            unmatched += 1
            continue
        result = get_or_create_analysis_result(db, user_id=user_id, note_id=note.id)
        result.external_record_id = _as_text(record.get("record_id") or result.external_record_id)
        result.analysis_status = _as_text(fields.get("分析状态")) or None
        result.subject_object = _as_text(fields.get("产品/主题对象"))
        result.content_type = _as_text(fields.get("内容类型")) or None
        result.core_points = _as_text(fields.get("核心卖点/核心观点"))
        result.target_audience = _as_text(fields.get("目标人群"))
        result.title_hook = _as_text(fields.get("封面/标题钩子"))
        result.content_structure = _as_text(fields.get("内容结构分析"))
        result.reusable_models = _as_text_list(fields.get("可复用模型"))
        result.reuse_value = _as_text(fields.get("复用价值")) or None
        result.analysis_note = _as_text(fields.get("分析备注"))
        result.pull_status = "success"
        result.last_pulled_at = now
        result.last_error = ""
        result.raw_payload = fields
        result.updated_at = now
        updated += 1
    db.commit()
    return {"updated_count": updated, "unmatched_count": unmatched, "failed_count": len(errors), "errors": errors}
```

- [ ] **Step 4: Add pull endpoint**

Modify `backend/app/api/feishu_integration.py`:

```python
from backend.app.services.feishu_bitable_service import FEISHU_FIELD_DEFINITIONS, extract_bitable_tokens, pull_feishu_analysis_records, push_notes_to_feishu_dry_run


class FeishuPullNotesPayload(BaseModel):
    dry_run: bool = True
    records: list[dict] = Field(default_factory=list)


@router.post("/xhs-notes/pull")
def pull_xhs_notes_from_feishu(payload: FeishuPullNotesPayload, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if payload.dry_run:
        return pull_feishu_analysis_records(db, user_id=current_user.id, records=payload.records)
    return {"updated_count": 0, "unmatched_count": 0, "failed_count": 1, "errors": ["真实飞书读取需要醒后配置凭据并单独启用。"]}
```

- [ ] **Step 5: Run pull test**

Run:

```bash
pytest tests/backend/test_feishu_integration.py::test_pull_feishu_analysis_payload_updates_analysis_result -q
```

Expected: PASS.

---

## Task 7: Add frontend API types and static contract checks

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/api.ts`
- Modify: `tests/backend/test_api.py`

- [ ] **Step 1: Add failing static contract test**

Append to `tests/backend/test_api.py`:

```python
def test_frontend_exposes_feishu_integration_contracts():
    api_source = open("frontend/src/lib/api.ts", encoding="utf-8").read()
    types_source = open("frontend/src/types/index.ts", encoding="utf-8").read()

    assert "FeishuIntegrationConfig" in types_source
    assert "NoteAnalysisResult" in types_source
    assert "FeishuPushNotesPayload" in types_source
    assert "FeishuPullNotesPayload" in types_source
    assert "fetchFeishuConfig" in api_source
    assert "saveFeishuConfig" in api_source
    assert "ensureFeishuFields" in api_source
    assert "pushXhsNotesToFeishu" in api_source
    assert "pullXhsNotesFromFeishu" in api_source
    assert '"/integrations/feishu/config"' in api_source
    assert '"/integrations/feishu/xhs-notes/push"' in api_source
    assert '"/integrations/feishu/xhs-notes/pull"' in api_source
```

- [ ] **Step 2: Run failing static contract test**

Run:

```bash
pytest tests/backend/test_api.py::test_frontend_exposes_feishu_integration_contracts -q
```

Expected: FAIL.

- [ ] **Step 3: Add frontend types**

Add to `frontend/src/types/index.ts`:

```typescript
export type FeishuIntegrationConfig = {
  id?: number;
  app_id: string;
  has_app_secret: boolean;
  bitable_url: string;
  bitable_app_token?: string | null;
  table_id: string;
  view_id?: string | null;
  enabled: boolean;
  last_test_status?: string | null;
  last_test_message?: string | null;
  last_tested_at?: string | null;
};

export type FeishuIntegrationConfigPayload = {
  app_id: string;
  app_secret: string;
  bitable_url: string;
  table_id: string;
  enabled: boolean;
};

export type NoteAnalysisResult = {
  analysis_status?: string | null;
  subject_object: string;
  content_type?: string | null;
  core_points: string;
  target_audience: string;
  title_hook: string;
  content_structure: string;
  reusable_models: string[];
  reuse_value?: string | null;
  analysis_note: string;
  last_pushed_at?: string | null;
  last_pulled_at?: string | null;
};

export type FeishuSyncState = {
  push_status: "not_synced" | "dry_run" | "synced" | "failed" | string;
  pull_status: "not_pulled" | "success" | "failed" | string;
  external_record_id?: string | null;
  last_error: string;
};

export type FeishuPushNotesPayload = {
  note_ids: number[];
  dry_run?: boolean;
};

export type FeishuPullNotesPayload = {
  dry_run?: boolean;
  records?: Array<Record<string, unknown>>;
};

export type FeishuSyncResponse = {
  dry_run?: boolean;
  updated_count: number;
  failed_count: number;
  unmatched_count?: number;
  errors: unknown[];
  records?: Array<Record<string, unknown>>;
};
```

Extend `SavedNote`:

```typescript
feishu_sync?: FeishuSyncState;
analysis_result?: NoteAnalysisResult | null;
```

- [ ] **Step 4: Add frontend API functions**

Modify `frontend/src/lib/api.ts` imports/types and add:

```typescript
export async function fetchFeishuConfig(): Promise<FeishuIntegrationConfig> {
  const response = await http.get<FeishuIntegrationConfig>("/integrations/feishu/config");
  return response.data;
}

export async function saveFeishuConfig(payload: FeishuIntegrationConfigPayload): Promise<FeishuIntegrationConfig> {
  const response = await http.put<FeishuIntegrationConfig>("/integrations/feishu/config", payload);
  return response.data;
}

export async function ensureFeishuFields(payload: { dry_run?: boolean } = { dry_run: true }): Promise<{ dry_run: boolean; status: string; fields: Array<Record<string, unknown>> }> {
  const response = await http.post<{ dry_run: boolean; status: string; fields: Array<Record<string, unknown>> }>("/integrations/feishu/ensure-fields", payload);
  return response.data;
}

export async function pushXhsNotesToFeishu(payload: FeishuPushNotesPayload): Promise<FeishuSyncResponse> {
  const response = await http.post<FeishuSyncResponse>("/integrations/feishu/xhs-notes/push", payload);
  return response.data;
}

export async function pullXhsNotesFromFeishu(payload: FeishuPullNotesPayload): Promise<FeishuSyncResponse> {
  const response = await http.post<FeishuSyncResponse>("/integrations/feishu/xhs-notes/pull", payload);
  return response.data;
}
```

Extend `SavedNoteFilters`:

```typescript
feishu_push_status?: string;
analysis_status?: string;
content_type?: string;
reuse_value?: string;
reusable_model?: string;
```

Pass these params in `fetchSavedNotes`.

- [ ] **Step 5: Run static contract test**

Run:

```bash
pytest tests/backend/test_api.py::test_frontend_exposes_feishu_integration_contracts -q
```

Expected: PASS.

---

## Task 8: Add Feishu settings UI

**Files:**
- Modify: `frontend/src/pages/settings/settings-page.tsx`
- Test: `tests/backend/test_api.py`

- [ ] **Step 1: Add failing settings static test**

Append:

```python
def test_settings_page_exposes_feishu_integration_card():
    source = open("frontend/src/pages/settings/settings-page.tsx", encoding="utf-8").read()

    assert "飞书集成" in source
    assert "飞书 App ID" in source
    assert "飞书多维表格地址" in source
    assert "测试连接" in source
    assert "自动补字段" in source
    assert "saveFeishuConfig" in source
    assert "ensureFeishuFields" in source
```

- [ ] **Step 2: Run failing settings test**

Run:

```bash
pytest tests/backend/test_api.py::test_settings_page_exposes_feishu_integration_card -q
```

Expected: FAIL.

- [ ] **Step 3: Implement settings card**

Modify `frontend/src/pages/settings/settings-page.tsx`:

- Import `Button`, `Form`, `Input`, `Switch`, `message` from Ant Design as needed.
- Import `useEffect`, `useState`.
- Import `ensureFeishuFields`, `fetchFeishuConfig`, `saveFeishuConfig`.

Add component-local state and handlers:

```tsx
const [form] = Form.useForm();
const [isLoadingFeishu, setIsLoadingFeishu] = useState(false);
const [isSavingFeishu, setIsSavingFeishu] = useState(false);
const [isEnsuringFields, setIsEnsuringFields] = useState(false);

useEffect(() => {
  setIsLoadingFeishu(true);
  fetchFeishuConfig()
    .then((config) => form.setFieldsValue({ ...config, app_secret: "" }))
    .catch(() => message.error("飞书配置加载失败"))
    .finally(() => setIsLoadingFeishu(false));
}, [form]);

async function handleSaveFeishu(values: { app_id: string; app_secret: string; bitable_url: string; table_id: string; enabled: boolean }) {
  setIsSavingFeishu(true);
  try {
    await saveFeishuConfig(values);
    message.success("飞书配置已保存");
  } catch (error) {
    message.error(error instanceof Error ? error.message : "飞书配置保存失败");
  } finally {
    setIsSavingFeishu(false);
  }
}

async function handleEnsureFeishuFields() {
  setIsEnsuringFields(true);
  try {
    const result = await ensureFeishuFields({ dry_run: true });
    message.success(`字段模板已生成：${result.fields.length} 个字段`);
  } catch (error) {
    message.error(error instanceof Error ? error.message : "自动补字段失败");
  } finally {
    setIsEnsuringFields(false);
  }
}
```

Add a card:

```tsx
<Card title="飞书集成">
  <Alert type="info" showIcon style={{ marginBottom: 16 }} message="第一版先使用 dry-run 字段检查；真实飞书写入需配置凭据后单独启用。" />
  <Form form={form} layout="vertical" onFinish={handleSaveFeishu} disabled={isLoadingFeishu}>
    <Form.Item label="飞书 App ID" name="app_id"><Input placeholder="cli_xxx" /></Form.Item>
    <Form.Item label="飞书 App Secret" name="app_secret"><Input.Password placeholder="留空表示不更新密钥" /></Form.Item>
    <Form.Item label="飞书多维表格地址" name="bitable_url"><Input placeholder="https://.../base/...?...table=..." /></Form.Item>
    <Form.Item label="目标数据表" name="table_id"><Input placeholder="可从多维表格地址自动识别" /></Form.Item>
    <Form.Item label="启用状态" name="enabled" valuePropName="checked"><Switch /></Form.Item>
    <Space wrap>
      <Button type="primary" htmlType="submit" loading={isSavingFeishu}>保存飞书配置</Button>
      <Button onClick={handleEnsureFeishuFields} loading={isEnsuringFields}>自动补字段</Button>
      <Button onClick={() => message.info("测试连接将在真实凭据启用后执行")}>测试连接</Button>
    </Space>
  </Form>
</Card>
```

- [ ] **Step 4: Run settings static test**

Run:

```bash
pytest tests/backend/test_api.py::test_settings_page_exposes_feishu_integration_card -q
```

Expected: PASS.

---

## Task 9: Update content library filters and XHS adapter display/actions

**Files:**
- Modify: `frontend/src/components/content-library/content-library-types.ts`
- Modify: `frontend/src/components/content-library/use-content-library.ts`
- Modify: `frontend/src/components/content-library/content-library-shell.tsx`
- Modify: `frontend/src/pages/platforms/xhs/xhs-content-library-adapter.ts`
- Test: `tests/backend/test_api.py`

- [ ] **Step 1: Add failing content library static test**

Append:

```python
def test_xhs_content_library_exposes_feishu_filters_and_actions():
    adapter_source = open("frontend/src/pages/platforms/xhs/xhs-content-library-adapter.ts", encoding="utf-8").read()
    shell_source = open("frontend/src/components/content-library/content-library-shell.tsx", encoding="utf-8").read()
    types_source = open("frontend/src/components/content-library/content-library-types.ts", encoding="utf-8").read()

    assert "飞书同步状态" in shell_source or "feishuPushStatusFilter" in shell_source
    assert "分析状态" in shell_source
    assert "内容类型" in shell_source
    assert "复用价值" in shell_source
    assert "可复用模型" in shell_source
    assert "pushXhsNotesToFeishu" in adapter_source
    assert "pullXhsNotesFromFeishu" in adapter_source
    assert "同步到飞书" in adapter_source
    assert "从飞书回传" in adapter_source
    assert "analysis_result" in adapter_source
    assert "feishuPushStatusFilter" in types_source
```

- [ ] **Step 2: Run failing content library static test**

Run:

```bash
pytest tests/backend/test_api.py::test_xhs_content_library_exposes_feishu_filters_and_actions -q
```

Expected: FAIL.

- [ ] **Step 3: Extend content library types/controller**

Add optional filters to `ContentLibraryFilters`:

```typescript
feishu_push_status?: string;
analysis_status?: string;
content_type?: string;
reuse_value?: string;
reusable_model?: string;
```

Add controller fields:

```typescript
feishuPushStatusFilter: string;
analysisStatusFilter: string;
contentTypeFilter: string;
reuseValueFilter: string;
reusableModelFilter: string;
setFeishuPushStatusFilter(value: string): void;
setAnalysisStatusFilter(value: string): void;
setContentTypeFilter(value: string): void;
setReuseValueFilter(value: string): void;
setReusableModelFilter(value: string): void;
```

- [ ] **Step 4: Extend hook state**

Modify `frontend/src/components/content-library/use-content-library.ts` to add state:

```typescript
const [feishuPushStatusFilter, setFeishuPushStatusFilter] = useState("");
const [analysisStatusFilter, setAnalysisStatusFilter] = useState("");
const [contentTypeFilter, setContentTypeFilter] = useState("");
const [reuseValueFilter, setReuseValueFilter] = useState("");
const [reusableModelFilter, setReusableModelFilter] = useState("");
```

Include in filters:

```typescript
feishu_push_status: feishuPushStatusFilter || undefined,
analysis_status: analysisStatusFilter || undefined,
content_type: contentTypeFilter || undefined,
reuse_value: reuseValueFilter || undefined,
reusable_model: reusableModelFilter || undefined,
```

Clear in `clearFilters()` and expose in returned controller.

- [ ] **Step 5: Add shell filter controls**

In `content-library-shell.tsx`, add Select controls near existing filters:

```tsx
<Select allowClear placeholder="飞书同步状态" value={controller.feishuPushStatusFilter || undefined} onChange={(value) => controller.setFeishuPushStatusFilter(value ?? "")} style={{ minWidth: 140 }} options={[{ value: "not_synced", label: "未同步" }, { value: "synced", label: "已同步" }, { value: "dry_run", label: "Dry-run" }, { value: "failed", label: "同步失败" }]} />
<Select allowClear placeholder="分析状态" value={controller.analysisStatusFilter || undefined} onChange={(value) => controller.setAnalysisStatusFilter(value ?? "")} style={{ minWidth: 120 }} options={["待分析", "分析中", "已完成", "废弃"].map((value) => ({ value, label: value }))} />
<Select allowClear placeholder="内容类型" value={controller.contentTypeFilter || undefined} onChange={(value) => controller.setContentTypeFilter(value ?? "")} style={{ minWidth: 120 }} options={["种草", "测评", "避坑", "教程", "合集/清单", "对比", "痛点共鸣", "案例故事"].map((value) => ({ value, label: value }))} />
<Select allowClear placeholder="复用价值" value={controller.reuseValueFilter || undefined} onChange={(value) => controller.setReuseValueFilter(value ?? "")} style={{ minWidth: 140 }} options={["选题参考", "标题参考", "正文结构参考", "卖点表达参考", "可直接改写", "行业观察", "竞品参考", "废弃"].map((value) => ({ value, label: value }))} />
<Select allowClear placeholder="可复用模型" value={controller.reusableModelFilter || undefined} onChange={(value) => controller.setReusableModelFilter(value ?? "")} style={{ minWidth: 160 }} options={["问题驱动模型", "情绪驱动模型", "场景种草模型", "对比反差模型", "测评背书模型", "教程方法模型", "故事案例模型", "IP/热点借势模型"].map((value) => ({ value, label: value }))} />
```

- [ ] **Step 6: Add XHS adapter toolbar actions**

In `xhs-content-library-adapter.ts`, import `pushXhsNotesToFeishu` and `pullXhsNotesFromFeishu`.

Add toolbar buttons inside `renderToolbarExtras` or equivalent XHS adapter area:

```tsx
<Button disabled={context.controller.selectedItemIds.length === 0} onClick={async () => {
  const result = await pushXhsNotesToFeishu({ note_ids: context.controller.selectedItemIds, dry_run: true });
  context.controller.setBatchActionMessage(`同步到飞书 dry-run：更新 ${result.updated_count} 条，失败 ${result.failed_count} 条`);
  await context.controller.refreshItems();
}}>同步到飞书</Button>
<Button disabled={context.controller.selectedItemIds.length === 0} onClick={async () => {
  const result = await pullXhsNotesFromFeishu({ dry_run: true, records: [] });
  context.controller.setBatchActionMessage(`从飞书回传：更新 ${result.updated_count} 条，失败 ${result.failed_count} 条`);
  await context.controller.refreshItems();
}}>从飞书回传</Button>
```

- [ ] **Step 7: Add XHS card/detail analysis display**

In card render, show weak tags if present:

```tsx
{item.analysis_result?.analysis_status ? <Tag color="blue">{item.analysis_result.analysis_status}</Tag> : null}
{item.analysis_result?.content_type ? <Tag>{item.analysis_result.content_type}</Tag> : null}
{item.analysis_result?.reuse_value ? <Tag color="green">{item.analysis_result.reuse_value}</Tag> : null}
```

In detail render, add a section:

```tsx
<Card size="small" title="飞书分析结果">
  <Descriptions size="small" column={1}>
    <Descriptions.Item label="分析状态">{item.analysis_result?.analysis_status || "未回传"}</Descriptions.Item>
    <Descriptions.Item label="产品/主题对象">{item.analysis_result?.subject_object || "-"}</Descriptions.Item>
    <Descriptions.Item label="核心卖点/核心观点">{item.analysis_result?.core_points || "-"}</Descriptions.Item>
    <Descriptions.Item label="目标人群">{item.analysis_result?.target_audience || "-"}</Descriptions.Item>
    <Descriptions.Item label="封面/标题钩子">{item.analysis_result?.title_hook || "-"}</Descriptions.Item>
    <Descriptions.Item label="内容结构分析">{item.analysis_result?.content_structure || "-"}</Descriptions.Item>
    <Descriptions.Item label="可复用模型">{item.analysis_result?.reusable_models?.join("、") || "-"}</Descriptions.Item>
    <Descriptions.Item label="复用价值">{item.analysis_result?.reuse_value || "-"}</Descriptions.Item>
    <Descriptions.Item label="分析备注">{item.analysis_result?.analysis_note || "-"}</Descriptions.Item>
  </Descriptions>
</Card>
```

- [ ] **Step 8: Run content library static test**

Run:

```bash
pytest tests/backend/test_api.py::test_xhs_content_library_exposes_feishu_filters_and_actions -q
```

Expected: PASS.

---

## Task 10: Refactor crawler page into source tabs and update copy

**Files:**
- Modify: `frontend/src/pages/platforms/xhs/crawler-page.tsx`
- Test: `tests/backend/test_api.py`

- [ ] **Step 1: Add failing crawler tab static test**

Append:

```python
def test_crawler_page_groups_sources_by_huitun_and_xhs_tabs():
    source = open("frontend/src/pages/platforms/xhs/crawler-page.tsx", encoding="utf-8").read()

    assert "灰豚热词采集" in source
    assert "小红书站内采集" in source
    assert "按关键词组采集" in source
    assert "临时关键词搜索" in source
    assert "关键词组采集" not in source or "按关键词组采集" in source
    assert "手动关键词" not in source or "临时关键词搜索" in source
    assert "Tabs" in source
```

- [ ] **Step 2: Run failing crawler tab test**

Run:

```bash
pytest tests/backend/test_api.py::test_crawler_page_groups_sources_by_huitun_and_xhs_tabs -q
```

Expected: FAIL.

- [ ] **Step 3: Add Ant Design Tabs import**

In `crawler-page.tsx`, add `Tabs` to the Ant Design import.

- [ ] **Step 4: Wrap existing page sections in Tabs**

Use this structure around the existing gray/huitun keyword discovery block and XHS crawl form/results block:

```tsx
<Tabs
  defaultActiveKey="xhs"
  items={[
    {
      key: "huitun",
      label: "灰豚热词采集",
      children: (
        <Space direction="vertical" size={16} style={{ width: "100%" }}>
          <Alert showIcon type="info" message="灰豚热词采集" description="灰豚用于发现热词和候选关键词，结果会导入关键词组，不直接进入内容库。" />
          {/* move existing huitun keyword discovery / import UI here if currently present on this page; otherwise add a Link to /platforms/xhs/keywords */}
        </Space>
      ),
    },
    {
      key: "xhs",
      label: "小红书站内采集",
      children: (
        <Space direction="vertical" size={16} style={{ width: "100%" }}>
          <Alert showIcon type="info" message="小红书站内采集" description="小红书站内采集用于按关键词组或临时关键词抓取笔记内容，结果可保存到内容库。" />
          {/* existing crawler form, results, diagnostics and export UI */}
        </Space>
      ),
    },
  ]}
/>
```

If the current crawler page does not contain gray/huitun UI, the gray tab should contain a concise bridge:

```tsx
<Link to="/platforms/xhs/keywords"><Button type="primary">去导入灰豚热词</Button></Link>
```

- [ ] **Step 5: Rename radio labels**

Replace:

```tsx
<Radio.Button value="keyword_group">关键词组采集</Radio.Button>
<Radio.Button value="manual_keyword">手动关键词</Radio.Button>
```

with:

```tsx
<Radio.Button value="keyword_group">按关键词组采集</Radio.Button>
<Radio.Button value="manual_keyword">临时关键词搜索</Radio.Button>
```

- [ ] **Step 6: Run crawler tab static test**

Run:

```bash
pytest tests/backend/test_api.py::test_crawler_page_groups_sources_by_huitun_and_xhs_tabs -q
```

Expected: PASS.

---

## Task 11: Run focused backend and static verification

**Files:**
- No code changes unless failures identify a direct issue.

- [ ] **Step 1: Run Feishu backend tests**

Run:

```bash
pytest tests/backend/test_feishu_integration.py -q
```

Expected: PASS.

- [ ] **Step 2: Run content library sorting/filter tests**

Run:

```bash
pytest tests/backend/test_notes_library_sorting.py -q
```

Expected: PASS.

- [ ] **Step 3: Run frontend static contract tests added in this plan**

Run:

```bash
pytest tests/backend/test_api.py::test_frontend_exposes_feishu_integration_contracts tests/backend/test_api.py::test_settings_page_exposes_feishu_integration_card tests/backend/test_api.py::test_xhs_content_library_exposes_feishu_filters_and_actions tests/backend/test_api.py::test_crawler_page_groups_sources_by_huitun_and_xhs_tabs -q
```

Expected: PASS.

- [ ] **Step 4: Run broader backend smoke tests likely affected by imports/routes**

Run:

```bash
pytest tests/backend/test_api.py::test_backend_foundation_modules_import tests/backend/test_api.py::test_health_endpoint_returns_ok -q
```

Expected: PASS.

---

## Task 12: Run frontend build/type verification

**Files:**
- No code changes unless failures identify a direct issue.

- [ ] **Step 1: Install check only if dependencies are already present**

Run:

```bash
test -d frontend/node_modules && echo "frontend deps present" || echo "frontend deps missing"
```

Expected: If dependencies are missing, stop frontend build verification and report it. Do not install dependencies while user sleeps unless already authorized.

- [ ] **Step 2: Run frontend build if dependencies are present**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS. If FAIL, capture the exact TypeScript/build errors and fix only direct errors introduced by this work.

---

## Task 13: Final report without commit/push

**Files:**
- No code changes.

- [ ] **Step 1: Check git diff summary**

Run:

```bash
git status --short
git diff --stat
```

Expected: Shows changed files. Do not commit unless user explicitly asks.

- [ ] **Step 2: Prepare handoff summary**

Report:

- What was implemented.
- What was verified and exact commands run.
- What failed, if anything.
- What remains blocked by real Feishu credentials / external write authorization.
- Confirm no real Feishu write was performed.
- Confirm no commit/push was performed.

---

## Self-Review

Spec coverage:

-采集页来源拆分 → Task 10.
-采集记录追溯 → partially represented through existing task payload; full dedicated history UI/API is intentionally not in this first night run because the code exploration shows existing `Task` payloads need more investigation. Report as remaining phase if not implemented.
-飞书配置 → Tasks 2, 3, 8.
-系统到飞书 dry-run and state → Task 5.
-飞书到系统 dry-run payload回传 → Task 6.
-分析结果表 → Task 1.
-内容库筛选/展示 → Tasks 4, 7, 9.
-真实飞书写入/读取 → explicitly blocked for wake-up because it requires credentials and external side effects.

Placeholder scan:

- No `TBD` / `TODO` plan steps.
- All code-changing tasks provide concrete code snippets or exact UI snippets.

Type consistency:

- Backend `NoteAnalysisResult` maps to frontend `NoteAnalysisResult` fields.
- Backend endpoints `/api/integrations/feishu/...` match frontend client paths with Axios base `/api` behavior.
- `push_status` uses `not_synced`, `dry_run`, `synced`, `failed` consistently.

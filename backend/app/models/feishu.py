from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
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
    collaborator_member_type: Mapped[str] = mapped_column(String(32), default="")
    collaborator_member_id: Mapped[str] = mapped_column(String(256), default="")
    collaborator_perm: Mapped[str] = mapped_column(String(32), default="edit")
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
    cover_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    title_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    content_structure: Mapped[str] = mapped_column(Text, default="")
    reusable_models: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    reuse_value: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    search_attribute: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True, index=True)
    rating: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    analysis_note: Mapped[str] = mapped_column(Text, default="")
    last_pushed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_pulled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    push_status: Mapped[str] = mapped_column(String(32), default="not_synced", index=True)
    pull_status: Mapped[str] = mapped_column(String(32), default="not_pulled")
    last_error: Mapped[str] = mapped_column(Text, default="")
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now)

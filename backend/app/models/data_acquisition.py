from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base
from backend.app.core.time import shanghai_now


def default_candidate_expiry() -> datetime:
    return shanghai_now() + timedelta(days=30)


class DataAcquisitionRun(Base):
    __tablename__ = "data_acquisition_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tasks.id"), index=True, nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("platform_accounts.id"), index=True, nullable=True)
    platform: Mapped[str] = mapped_column(String(32), index=True, default="xhs")
    acquisition_type: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    source_mode: Mapped[str] = mapped_column(String(32), default="live_account")
    status: Mapped[str] = mapped_column(String(32), index=True, default="pending")
    requested_limit: Mapped[int] = mapped_column(Integer, default=0)
    effective_limit: Mapped[int] = mapped_column(Integer, default=0)
    params_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    admin_debug_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str] = mapped_column(String(64), default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    rerun_of_run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("data_acquisition_runs.id"), nullable=True)
    cancellation_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class DataAcquisitionCandidate(Base):
    __tablename__ = "data_acquisition_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("data_acquisition_runs.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    platform: Mapped[str] = mapped_column(String(32), index=True, default="xhs")
    candidate_type: Mapped[str] = mapped_column(String(32), index=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    external_id: Mapped[str] = mapped_column(String(128), default="")
    platform_note_id: Mapped[str] = mapped_column(String(128), index=True, default="")
    original_url: Mapped[str] = mapped_column(Text, default="")
    title: Mapped[str] = mapped_column(String(512), default="")
    content_excerpt: Mapped[str] = mapped_column(Text, default="")
    author_name: Mapped[str] = mapped_column(String(128), default="")
    cover_url: Mapped[str] = mapped_column(Text, default="")
    asset_urls_json: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    publish_time: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    update_time: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    rank_index: Mapped[int] = mapped_column(Integer, default=0)
    category: Mapped[str] = mapped_column(String(128), default="")
    tags_json: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    metrics_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    raw_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=True, default="pending")
    imported_note_id: Mapped[Optional[int]] = mapped_column(ForeignKey("notes.id"), index=True, nullable=True)
    decision_reason_code: Mapped[str] = mapped_column(String(64), default="")
    decision_reason_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now, onupdate=shanghai_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime, default=default_candidate_expiry)


class NoteSourceSnapshot(Base):
    __tablename__ = "note_source_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    note_id: Mapped[int] = mapped_column(ForeignKey("notes.id"), index=True)
    run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("data_acquisition_runs.id"), index=True, nullable=True)
    candidate_id: Mapped[Optional[int]] = mapped_column(ForeignKey("data_acquisition_candidates.id"), index=True, nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    platform: Mapped[str] = mapped_column(String(32), index=True, default="xhs")
    source: Mapped[str] = mapped_column(String(32), index=True)
    snapshot_type: Mapped[str] = mapped_column(String(32), index=True)
    source_url: Mapped[str] = mapped_column(Text, default="")
    source_record_id: Mapped[str] = mapped_column(String(128), default="")
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now)
    rank_index: Mapped[int] = mapped_column(Integer, default=0)
    keyword: Mapped[str] = mapped_column(String(128), default="")
    rank_type: Mapped[str] = mapped_column(String(64), default="")
    category: Mapped[str] = mapped_column(String(128), default="")
    tags_json: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    metrics_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    analysis_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    raw_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now)

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

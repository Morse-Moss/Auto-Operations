from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base
from backend.app.core.time import shanghai_now


class KeywordDiscoveryRun(Base):
    __tablename__ = "keyword_discovery_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    platform: Mapped[str] = mapped_column(String(32), index=True, default="xhs")
    source: Mapped[str] = mapped_column(String(32), index=True, default="huitun")
    seed_keywords: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    limit_per_seed: Mapped[int] = mapped_column(Integer, default=20)
    source_mode: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="running")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class KeywordDiscoveryItem(Base):
    __tablename__ = "keyword_discovery_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("keyword_discovery_runs.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    platform: Mapped[str] = mapped_column(String(32), index=True, default="xhs")
    source: Mapped[str] = mapped_column(String(32), index=True, default="huitun")
    source_keyword: Mapped[str] = mapped_column(String(128))
    keyword: Mapped[str] = mapped_column(String(128), index=True)
    hot_value_text: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    hot_value_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    note_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    interaction_text: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    interaction_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    categories: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    rank_index: Mapped[int] = mapped_column(Integer, default=0)
    selected: Mapped[bool] = mapped_column(Boolean, default=False)
    imported_group_id: Mapped[Optional[int]] = mapped_column(ForeignKey("keyword_groups.id"), nullable=True)
    raw_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now)

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
    note_id: Mapped[Optional[int]] = mapped_column(ForeignKey("notes.id", ondelete="SET NULL"), nullable=True, index=True)
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
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now, onupdate=shanghai_now)

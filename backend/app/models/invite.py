from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base
from backend.app.core.time import shanghai_now


class InviteCode(Base):
    __tablename__ = "invite_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now, onupdate=shanghai_now)


class InviteCodeUse(Base):
    __tablename__ = "invite_code_uses"
    __table_args__ = (
        UniqueConstraint("invite_code_id", "used_by_user_id", name="uq_invite_code_uses_code_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invite_code_id: Mapped[int] = mapped_column(ForeignKey("invite_codes.id"), index=True)
    used_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    used_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now)

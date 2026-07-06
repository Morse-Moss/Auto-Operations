from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base
from backend.app.core.time import shanghai_now


class BetaConcurrencyLease(Base):
    __tablename__ = "beta_concurrency_leases"
    __table_args__ = (UniqueConstraint("active_key", name="uq_beta_concurrency_leases_active_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    bucket: Mapped[str] = mapped_column(String(64), index=True)
    scope: Mapped[str] = mapped_column(String(32), index=True)
    slot_number: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    active_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    feature_key: Mapped[str] = mapped_column(String(128), default="")
    idempotency_key: Mapped[str] = mapped_column(String(160), default="")
    task_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tasks.id"), nullable=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    released_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    release_reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now)

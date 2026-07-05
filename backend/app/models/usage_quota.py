from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base
from backend.app.core.time import shanghai_now
from backend.app.models.tenant import Tenant, TenantMember


class BetaCreditAccount(Base):
    __tablename__ = "beta_credit_accounts"
    __table_args__ = (UniqueConstraint("tenant_id", "bucket", name="uq_beta_credit_accounts_tenant_bucket"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    bucket: Mapped[str] = mapped_column(String(64), index=True)
    total: Mapped[int] = mapped_column(Integer, default=0)
    remaining: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now, onupdate=shanghai_now)


class UsageLedger(Base):
    __tablename__ = "usage_ledgers"
    __table_args__ = (UniqueConstraint("tenant_id", "feature_key", "idempotency_key", name="uq_usage_ledgers_tenant_feature_idempotency"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    feature_key: Mapped[str] = mapped_column(String(128), index=True)
    bucket: Mapped[str] = mapped_column(String(64), index=True)
    operation: Mapped[str] = mapped_column(String(32), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    balance_after: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="completed")
    idempotency_key: Mapped[str] = mapped_column(String(160), default="")
    reservation_id: Mapped[Optional[int]] = mapped_column(ForeignKey("usage_ledgers.id"), nullable=True, index=True)
    task_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tasks.id"), nullable=True, index=True)
    resource_type: Mapped[str] = mapped_column(String(64), default="")
    resource_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    provider: Mapped[str] = mapped_column(String(64), default="")
    model_config_id: Mapped[Optional[int]] = mapped_column(ForeignKey("model_configs.id"), nullable=True, index=True)
    external_request_id: Mapped[str] = mapped_column(String(128), default="")
    request_summary: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    failure_reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now)

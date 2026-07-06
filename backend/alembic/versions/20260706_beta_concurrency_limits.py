"""add beta concurrency leases

Revision ID: 20260706_beta_concurrency_limits
Revises: 20260706_beta_admission_admin
Create Date: 2026-07-06
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260706_beta_concurrency_limits"
down_revision: Union[str, Sequence[str], None] = "20260706_beta_admission_admin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "beta_concurrency_leases" not in tables:
        op.create_table(
            "beta_concurrency_leases",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("bucket", sa.String(length=64), nullable=False),
            sa.Column("scope", sa.String(length=32), nullable=False),
            sa.Column("slot_number", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
            sa.Column("active_key", sa.String(length=255), nullable=True),
            sa.Column("feature_key", sa.String(length=128), nullable=False, server_default=""),
            sa.Column("idempotency_key", sa.String(length=160), nullable=False, server_default=""),
            sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id"), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("released_at", sa.DateTime(), nullable=True),
            sa.Column("release_reason", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("active_key", name="uq_beta_concurrency_leases_active_key"),
        )
        op.create_index("ix_beta_concurrency_leases_tenant_id", "beta_concurrency_leases", ["tenant_id"])
        op.create_index("ix_beta_concurrency_leases_user_id", "beta_concurrency_leases", ["user_id"])
        op.create_index("ix_beta_concurrency_leases_bucket", "beta_concurrency_leases", ["bucket"])
        op.create_index("ix_beta_concurrency_leases_scope", "beta_concurrency_leases", ["scope"])
        op.create_index("ix_beta_concurrency_leases_status", "beta_concurrency_leases", ["status"])
        op.create_index("ix_beta_concurrency_leases_task_id", "beta_concurrency_leases", ["task_id"])
        op.create_index("ix_beta_concurrency_leases_expires_at", "beta_concurrency_leases", ["expires_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "beta_concurrency_leases" in tables:
        op.drop_table("beta_concurrency_leases")

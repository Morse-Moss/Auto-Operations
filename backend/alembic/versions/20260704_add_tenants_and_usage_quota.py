"""add tenants and usage quota

Revision ID: 20260704_tenants_usage_quota
Revises: 20260701_note_exclusions
Create Date: 2026-07-04
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260704_tenants_usage_quota"
down_revision: Union[str, Sequence[str], None] = "20260701_note_exclusions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "tenants" not in tables:
        op.create_table(
            "tenants",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("slug", sa.String(length=128), nullable=False),
            sa.Column("kind", sa.String(length=32), nullable=False, server_default="beta"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("slug", name="uq_tenants_slug"),
        )
        op.create_index("ix_tenants_slug", "tenants", ["slug"])

    if "tenant_members" not in tables:
        op.create_table(
            "tenant_members",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("role", sa.String(length=32), nullable=False, server_default="owner"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("tenant_id", "user_id", name="uq_tenant_members_tenant_user"),
        )
        op.create_index("ix_tenant_members_tenant_id", "tenant_members", ["tenant_id"])
        op.create_index("ix_tenant_members_user_id", "tenant_members", ["user_id"])

    if "beta_credit_accounts" not in tables:
        op.create_table(
            "beta_credit_accounts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("bucket", sa.String(length=64), nullable=False),
            sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("remaining", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("tenant_id", "bucket", name="uq_beta_credit_accounts_tenant_bucket"),
        )
        op.create_index("ix_beta_credit_accounts_tenant_id", "beta_credit_accounts", ["tenant_id"])
        op.create_index("ix_beta_credit_accounts_bucket", "beta_credit_accounts", ["bucket"])

    if "usage_ledgers" not in tables:
        op.create_table(
            "usage_ledgers",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("feature_key", sa.String(length=128), nullable=False),
            sa.Column("bucket", sa.String(length=64), nullable=False),
            sa.Column("operation", sa.String(length=32), nullable=False),
            sa.Column("amount", sa.Integer(), nullable=False),
            sa.Column("balance_after", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="completed"),
            sa.Column("idempotency_key", sa.String(length=160), nullable=False, server_default=""),
            sa.Column("reservation_id", sa.Integer(), sa.ForeignKey("usage_ledgers.id"), nullable=True),
            sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id"), nullable=True),
            sa.Column("resource_type", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("resource_id", sa.Integer(), nullable=True),
            sa.Column("provider", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("model_config_id", sa.Integer(), sa.ForeignKey("model_configs.id"), nullable=True),
            sa.Column("external_request_id", sa.String(length=128), nullable=False, server_default=""),
            sa.Column("request_summary", sa.JSON(), nullable=True),
            sa.Column("failure_reason", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("tenant_id", "feature_key", "idempotency_key", name="uq_usage_ledgers_tenant_feature_idempotency"),
        )
        for index_name, columns in (
            ("ix_usage_ledgers_tenant_id", ["tenant_id"]),
            ("ix_usage_ledgers_user_id", ["user_id"]),
            ("ix_usage_ledgers_feature_key", ["feature_key"]),
            ("ix_usage_ledgers_bucket", ["bucket"]),
            ("ix_usage_ledgers_operation", ["operation"]),
            ("ix_usage_ledgers_reservation_id", ["reservation_id"]),
            ("ix_usage_ledgers_task_id", ["task_id"]),
            ("ix_usage_ledgers_model_config_id", ["model_config_id"]),
        ):
            op.create_index(index_name, "usage_ledgers", columns)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    for table_name in ("usage_ledgers", "beta_credit_accounts", "tenant_members", "tenants"):
        if table_name in tables:
            op.drop_table(table_name)

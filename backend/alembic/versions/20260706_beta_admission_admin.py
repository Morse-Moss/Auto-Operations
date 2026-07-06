"""add beta admission admin controls

Revision ID: 20260706_beta_admission_admin
Revises: 20260706_data_acquisition
Create Date: 2026-07-06
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260706_beta_admission_admin"
down_revision: Union[str, Sequence[str], None] = "20260706_data_acquisition"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "users" in tables:
        user_columns = _column_names(inspector, "users")
        if "role" not in user_columns:
            op.add_column("users", sa.Column("role", sa.String(length=32), nullable=False, server_default="user"))
        if "status" not in user_columns:
            op.add_column("users", sa.Column("status", sa.String(length=32), nullable=False, server_default="active"))

    if "invite_codes" not in tables:
        op.create_table(
            "invite_codes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("code", sa.String(length=80), nullable=False),
            sa.Column("max_uses", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
            sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("code", name="uq_invite_codes_code"),
        )
        op.create_index("ix_invite_codes_code", "invite_codes", ["code"])
        op.create_index("ix_invite_codes_created_by_user_id", "invite_codes", ["created_by_user_id"])

    if "invite_code_uses" not in tables:
        op.create_table(
            "invite_code_uses",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("invite_code_id", sa.Integer(), sa.ForeignKey("invite_codes.id"), nullable=False),
            sa.Column("used_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("used_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("invite_code_id", "used_by_user_id", name="uq_invite_code_uses_code_user"),
        )
        op.create_index("ix_invite_code_uses_invite_code_id", "invite_code_uses", ["invite_code_id"])
        op.create_index("ix_invite_code_uses_used_by_user_id", "invite_code_uses", ["used_by_user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "invite_code_uses" in tables:
        op.drop_table("invite_code_uses")
    if "invite_codes" in tables:
        op.drop_table("invite_codes")
    if "users" in tables:
        user_columns = _column_names(inspector, "users")
        if "status" in user_columns:
            op.drop_column("users", "status")
        if "role" in user_columns:
            op.drop_column("users", "role")

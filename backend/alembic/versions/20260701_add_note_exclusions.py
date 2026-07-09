"""add note exclusions

Revision ID: 20260701_note_exclusions
Revises: 20260701_merge_analysis_draft_score_heads
Create Date: 2026-07-01
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260701_note_exclusions"
down_revision: Union[str, Sequence[str], None] = "20260701_merge_analysis_draft_score_heads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "note_exclusions" not in tables:
        op.create_table(
            "note_exclusions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("note_id", sa.Integer(), sa.ForeignKey("notes.id", ondelete="SET NULL"), nullable=True),
            sa.Column("platform", sa.String(length=32), nullable=False),
            sa.Column("platform_note_id", sa.String(length=128), nullable=False),
            sa.Column("source_url", sa.Text(), nullable=False),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("author_name", sa.Text(), nullable=False),
            sa.Column("reason_code", sa.String(length=64), nullable=False),
            sa.Column("reason_text", sa.Text(), nullable=False),
            sa.Column("score", sa.Float(), nullable=True),
            sa.Column("rating", sa.String(length=32), nullable=True),
            sa.Column("external_record_id", sa.String(length=128), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("user_id", "platform", "platform_note_id", name="uq_note_exclusions_user_platform_note"),
        )

    indexes = {index["name"] for index in inspector.get_indexes("note_exclusions")}
    if "ix_note_exclusions_user_id" not in indexes:
        op.create_index("ix_note_exclusions_user_id", "note_exclusions", ["user_id"])
    if "ix_note_exclusions_note_id" not in indexes:
        op.create_index("ix_note_exclusions_note_id", "note_exclusions", ["note_id"])
    if "ix_note_exclusions_platform" not in indexes:
        op.create_index("ix_note_exclusions_platform", "note_exclusions", ["platform"])
    if "ix_note_exclusions_platform_note_id" not in indexes:
        op.create_index("ix_note_exclusions_platform_note_id", "note_exclusions", ["platform_note_id"])
    if "ix_note_exclusions_reason_code" not in indexes:
        op.create_index("ix_note_exclusions_reason_code", "note_exclusions", ["reason_code"])
    if "ix_note_exclusions_external_record_id" not in indexes:
        op.create_index("ix_note_exclusions_external_record_id", "note_exclusions", ["external_record_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "note_exclusions" in set(inspector.get_table_names()):
        op.drop_table("note_exclusions")

"""add persisted draft rewrite candidates

Revision ID: 20260722_draft_rewrite_state
Revises: 20260712_xhs_login_idempotency
Create Date: 2026-07-22
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260722_draft_rewrite_state"
down_revision: Union[str, Sequence[str], None] = "20260712_xhs_login_idempotency"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_rewrite_candidates_column() -> bool:
    columns = sa.inspect(op.get_bind()).get_columns("ai_drafts")
    return any(column["name"] == "rewrite_candidates" for column in columns)


def upgrade() -> None:
    if _has_rewrite_candidates_column():
        return
    with op.batch_alter_table("ai_drafts", schema=None) as batch_op:
        batch_op.add_column(sa.Column("rewrite_candidates", sa.JSON(), nullable=True))


def downgrade() -> None:
    if not _has_rewrite_candidates_column():
        return
    with op.batch_alter_table("ai_drafts", schema=None) as batch_op:
        batch_op.drop_column("rewrite_candidates")

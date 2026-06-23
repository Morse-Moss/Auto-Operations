"""add draft_name to ai_drafts

Revision ID: 20260622draftname
Revises: 20260618woclt
Create Date: 2026-06-22 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260622draftname"
down_revision: Union[str, Sequence[str], None] = "20260618woclt"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("ai_drafts", schema=None) as batch_op:
        batch_op.add_column(sa.Column("draft_name", sa.String(length=256), server_default="", nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("ai_drafts", schema=None) as batch_op:
        batch_op.drop_column("draft_name")

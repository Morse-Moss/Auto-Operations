"""add usage ledger followup uniqueness

Revision ID: 20260708_usage_ledger_followup_unique
Revises: 20260708_note_analysis_cover_title
Create Date: 2026-07-08
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260708_usage_ledger_followup_unique"
down_revision: Union[str, Sequence[str], None] = "20260708_note_analysis_cover_title"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


INDEX_NAME = "uq_usage_ledgers_reservation_operation"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "usage_ledgers" not in tables:
        return
    existing = {index["name"] for index in inspector.get_indexes("usage_ledgers")}
    if INDEX_NAME not in existing:
        op.create_index(INDEX_NAME, "usage_ledgers", ["reservation_id", "operation"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "usage_ledgers" not in tables:
        return
    existing = {index["name"] for index in inspector.get_indexes("usage_ledgers")}
    if INDEX_NAME in existing:
        op.drop_index(INDEX_NAME, table_name="usage_ledgers")

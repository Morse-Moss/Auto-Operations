"""add scheduler status indexes

Revision ID: 20260726_scheduler_indexes
Revises: 20260722_draft_rewrite_state
Create Date: 2026-07-26
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260726_scheduler_indexes"
down_revision: Union[str, Sequence[str], None] = "20260722_draft_rewrite_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


INDEXES = (
    ("publish_jobs", "ix_publish_jobs_status_scheduled_at", ["status", "scheduled_at"]),
    ("auto_tasks", "ix_auto_tasks_status_next_run_at", ["status", "next_run_at"]),
    ("tasks", "ix_tasks_status", ["status"]),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    for table_name, index_name, columns in INDEXES:
        if table_name not in tables:
            continue
        existing = {index["name"] for index in inspector.get_indexes(table_name)}
        if index_name not in existing:
            op.create_index(index_name, table_name, columns)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    for table_name, index_name, _columns in INDEXES:
        if table_name not in tables:
            continue
        existing = {index["name"] for index in inspector.get_indexes(table_name)}
        if index_name in existing:
            op.drop_index(index_name, table_name=table_name)

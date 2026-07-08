"""add note analysis cover and title type columns

Revision ID: 20260708_note_analysis_cover_title
Revises: 20260706_beta_concurrency_limits
Create Date: 2026-07-08
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260708_note_analysis_cover_title"
down_revision: Union[str, Sequence[str], None] = "20260706_beta_concurrency_limits"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "note_analysis_results" not in tables:
        return

    columns = {column["name"] for column in inspector.get_columns("note_analysis_results")}
    if "cover_type" not in columns:
        op.add_column("note_analysis_results", sa.Column("cover_type", sa.String(length=64), nullable=True))
        op.create_index("ix_note_analysis_results_cover_type", "note_analysis_results", ["cover_type"])
    if "title_type" not in columns:
        op.add_column("note_analysis_results", sa.Column("title_type", sa.String(length=64), nullable=True))
        op.create_index("ix_note_analysis_results_title_type", "note_analysis_results", ["title_type"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "note_analysis_results" not in tables:
        return

    indexes = {index["name"] for index in inspector.get_indexes("note_analysis_results")}
    if "ix_note_analysis_results_title_type" in indexes:
        op.drop_index("ix_note_analysis_results_title_type", table_name="note_analysis_results")
    if "ix_note_analysis_results_cover_type" in indexes:
        op.drop_index("ix_note_analysis_results_cover_type", table_name="note_analysis_results")

    columns = {column["name"] for column in inspector.get_columns("note_analysis_results")}
    if "title_type" in columns:
        op.drop_column("note_analysis_results", "title_type")
    if "cover_type" in columns:
        op.drop_column("note_analysis_results", "cover_type")

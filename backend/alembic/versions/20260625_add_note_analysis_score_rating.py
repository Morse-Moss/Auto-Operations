"""add note analysis score rating

Revision ID: 20260625_analysis_score_rating
Revises: 20260624_analysis_search_attr
Create Date: 2026-06-25
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260625_analysis_score_rating"
down_revision: Union[str, Sequence[str], None] = "20260624_analysis_search_attr"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("note_analysis_results")}
    if "score" not in columns:
        op.add_column("note_analysis_results", sa.Column("score", sa.Float(), nullable=True))
    if "rating" not in columns:
        op.add_column("note_analysis_results", sa.Column("rating", sa.String(length=32), nullable=True))

    indexes = {index["name"] for index in inspector.get_indexes("note_analysis_results")}
    if "ix_note_analysis_results_score" not in indexes:
        op.create_index("ix_note_analysis_results_score", "note_analysis_results", ["score"])
    if "ix_note_analysis_results_rating" not in indexes:
        op.create_index("ix_note_analysis_results_rating", "note_analysis_results", ["rating"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes("note_analysis_results")}
    if "ix_note_analysis_results_rating" in indexes:
        op.drop_index("ix_note_analysis_results_rating", table_name="note_analysis_results")
    if "ix_note_analysis_results_score" in indexes:
        op.drop_index("ix_note_analysis_results_score", table_name="note_analysis_results")

    columns = {column["name"] for column in inspector.get_columns("note_analysis_results")}
    if "rating" in columns:
        op.drop_column("note_analysis_results", "rating")
    if "score" in columns:
        op.drop_column("note_analysis_results", "score")

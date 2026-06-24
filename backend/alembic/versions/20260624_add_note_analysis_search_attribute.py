"""add note analysis search attribute

Revision ID: 20260624_analysis_search_attr
Revises: 20260623_feishu_collab
Create Date: 2026-06-24
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260624_analysis_search_attr"
down_revision: Union[str, Sequence[str], None] = "20260623_feishu_collab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("note_analysis_results")}
    if "search_attribute" not in columns:
        op.add_column("note_analysis_results", sa.Column("search_attribute", sa.String(length=64), nullable=True))

    indexes = {index["name"] for index in inspector.get_indexes("note_analysis_results")}
    if "ix_note_analysis_results_search_attribute" not in indexes:
        op.create_index("ix_note_analysis_results_search_attribute", "note_analysis_results", ["search_attribute"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes("note_analysis_results")}
    if "ix_note_analysis_results_search_attribute" in indexes:
        op.drop_index("ix_note_analysis_results_search_attribute", table_name="note_analysis_results")

    columns = {column["name"] for column in inspector.get_columns("note_analysis_results")}
    if "search_attribute" in columns:
        op.drop_column("note_analysis_results", "search_attribute")

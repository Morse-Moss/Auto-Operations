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
    op.add_column("note_analysis_results", sa.Column("search_attribute", sa.String(length=64), nullable=True))
    op.create_index("ix_note_analysis_results_search_attribute", "note_analysis_results", ["search_attribute"])


def downgrade() -> None:
    op.drop_index("ix_note_analysis_results_search_attribute", table_name="note_analysis_results")
    op.drop_column("note_analysis_results", "search_attribute")

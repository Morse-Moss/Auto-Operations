"""add draft ai score results

Revision ID: 20260630_draft_ai_score_results
Revises: 20260624_analysis_search_attr
Create Date: 2026-06-30
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260630_draft_ai_score_results"
down_revision: Union[str, Sequence[str], None] = "20260624_analysis_search_attr"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "draft_ai_score_results" in inspector.get_table_names():
        return

    op.create_table(
        "draft_ai_score_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("draft_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("overall_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("potential_level", sa.String(length=32), nullable=False, server_default="medium"),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("rule_snapshot", sa.JSON(), nullable=True),
        sa.Column("opportunity_snapshot", sa.JSON(), nullable=True),
        sa.Column("model_name", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["draft_id"], ["ai_drafts.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_draft_ai_score_results_draft_id", "draft_ai_score_results", ["draft_id"])
    op.create_index("ix_draft_ai_score_results_user_id", "draft_ai_score_results", ["user_id"])
    op.create_index("ix_draft_ai_score_results_platform", "draft_ai_score_results", ["platform"])
    op.create_index("ix_draft_ai_score_results_task_id", "draft_ai_score_results", ["task_id"])
    op.create_index(
        "ix_draft_ai_score_results_draft_created",
        "draft_ai_score_results",
        ["draft_id", "created_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "draft_ai_score_results" not in inspector.get_table_names():
        return

    indexes = {index["name"] for index in inspector.get_indexes("draft_ai_score_results")}
    for index_name in (
        "ix_draft_ai_score_results_draft_created",
        "ix_draft_ai_score_results_task_id",
        "ix_draft_ai_score_results_platform",
        "ix_draft_ai_score_results_user_id",
        "ix_draft_ai_score_results_draft_id",
    ):
        if index_name in indexes:
            op.drop_index(index_name, table_name="draft_ai_score_results")
    op.drop_table("draft_ai_score_results")

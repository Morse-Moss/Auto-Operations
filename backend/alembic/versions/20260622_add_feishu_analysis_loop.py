"""add feishu analysis loop tables

Revision ID: 20260622_feishu_loop
Revises: 20260618woclt
Create Date: 2026-06-22
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260622_feishu_loop"
down_revision: Union[str, None] = "20260618woclt"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "feishu_integration_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("app_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("encrypted_app_secret", sa.Text(), nullable=False),
        sa.Column("bitable_url", sa.Text(), nullable=False),
        sa.Column("bitable_app_token", sa.String(length=128), nullable=True),
        sa.Column("table_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("view_id", sa.String(length=128), nullable=True),
        sa.Column("enabled", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_test_status", sa.String(length=32), nullable=True),
        sa.Column("last_test_message", sa.Text(), nullable=True),
        sa.Column("last_tested_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_feishu_integration_configs_user_id"),
    )
    op.create_index("ix_feishu_integration_configs_user_id", "feishu_integration_configs", ["user_id"])

    op.create_table(
        "note_analysis_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("note_id", sa.Integer(), sa.ForeignKey("notes.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="feishu"),
        sa.Column("external_record_id", sa.String(length=128), nullable=True),
        sa.Column("analysis_status", sa.String(length=32), nullable=True),
        sa.Column("subject_object", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(length=64), nullable=True),
        sa.Column("core_points", sa.Text(), nullable=False),
        sa.Column("target_audience", sa.Text(), nullable=False),
        sa.Column("title_hook", sa.Text(), nullable=False),
        sa.Column("content_structure", sa.Text(), nullable=False),
        sa.Column("reusable_models", sa.JSON(), nullable=True),
        sa.Column("reuse_value", sa.String(length=64), nullable=True),
        sa.Column("analysis_note", sa.Text(), nullable=False),
        sa.Column("last_pushed_at", sa.DateTime(), nullable=True),
        sa.Column("last_pulled_at", sa.DateTime(), nullable=True),
        sa.Column("push_status", sa.String(length=32), nullable=False, server_default="not_synced"),
        sa.Column("pull_status", sa.String(length=32), nullable=False, server_default="not_pulled"),
        sa.Column("last_error", sa.Text(), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("note_id", "source", name="uq_note_analysis_results_note_source"),
    )
    op.create_index("ix_note_analysis_results_note_id", "note_analysis_results", ["note_id"])
    op.create_index("ix_note_analysis_results_user_id", "note_analysis_results", ["user_id"])
    op.create_index("ix_note_analysis_results_source", "note_analysis_results", ["source"])
    op.create_index("ix_note_analysis_results_external_record_id", "note_analysis_results", ["external_record_id"])
    op.create_index("ix_note_analysis_results_analysis_status", "note_analysis_results", ["analysis_status"])
    op.create_index("ix_note_analysis_results_content_type", "note_analysis_results", ["content_type"])
    op.create_index("ix_note_analysis_results_reuse_value", "note_analysis_results", ["reuse_value"])
    op.create_index("ix_note_analysis_results_push_status", "note_analysis_results", ["push_status"])


def downgrade() -> None:
    op.drop_index("ix_note_analysis_results_push_status", table_name="note_analysis_results")
    op.drop_index("ix_note_analysis_results_reuse_value", table_name="note_analysis_results")
    op.drop_index("ix_note_analysis_results_content_type", table_name="note_analysis_results")
    op.drop_index("ix_note_analysis_results_analysis_status", table_name="note_analysis_results")
    op.drop_index("ix_note_analysis_results_external_record_id", table_name="note_analysis_results")
    op.drop_index("ix_note_analysis_results_source", table_name="note_analysis_results")
    op.drop_index("ix_note_analysis_results_user_id", table_name="note_analysis_results")
    op.drop_index("ix_note_analysis_results_note_id", table_name="note_analysis_results")
    op.drop_table("note_analysis_results")
    op.drop_index("ix_feishu_integration_configs_user_id", table_name="feishu_integration_configs")
    op.drop_table("feishu_integration_configs")

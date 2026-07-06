"""add data acquisition tables

Revision ID: 20260706_data_acquisition
Revises: 20260704_tenants_usage_quota
Create Date: 2026-07-06
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260706_data_acquisition"
down_revision: Union[str, Sequence[str], None] = "20260704_tenants_usage_quota"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "data_acquisition_runs" not in tables:
        op.create_table(
            "data_acquisition_runs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id"), nullable=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("account_id", sa.Integer(), sa.ForeignKey("platform_accounts.id"), nullable=True),
            sa.Column("platform", sa.String(length=32), nullable=False),
            sa.Column("acquisition_type", sa.String(length=64), nullable=False),
            sa.Column("source", sa.String(length=32), nullable=False),
            sa.Column("source_mode", sa.String(length=32), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("requested_limit", sa.Integer(), nullable=False),
            sa.Column("effective_limit", sa.Integer(), nullable=False),
            sa.Column("params_json", sa.JSON(), nullable=True),
            sa.Column("admin_debug_json", sa.JSON(), nullable=True),
            sa.Column("error_code", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("error_message", sa.Text(), nullable=False, server_default=""),
            sa.Column("rerun_of_run_id", sa.Integer(), sa.ForeignKey("data_acquisition_runs.id"), nullable=True),
            sa.Column("cancellation_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
        )
        for index_name, columns in (
            ("ix_data_acquisition_runs_task_id", ["task_id"]),
            ("ix_data_acquisition_runs_user_id", ["user_id"]),
            ("ix_data_acquisition_runs_account_id", ["account_id"]),
            ("ix_data_acquisition_runs_platform", ["platform"]),
            ("ix_data_acquisition_runs_acquisition_type", ["acquisition_type"]),
            ("ix_data_acquisition_runs_source", ["source"]),
            ("ix_data_acquisition_runs_status", ["status"]),
        ):
            op.create_index(index_name, "data_acquisition_runs", columns)

    if "data_acquisition_candidates" not in tables:
        op.create_table(
            "data_acquisition_candidates",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("run_id", sa.Integer(), sa.ForeignKey("data_acquisition_runs.id"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("platform", sa.String(length=32), nullable=False),
            sa.Column("candidate_type", sa.String(length=32), nullable=False),
            sa.Column("source", sa.String(length=32), nullable=False),
            sa.Column("external_id", sa.String(length=128), nullable=False, server_default=""),
            sa.Column("platform_note_id", sa.String(length=128), nullable=False, server_default=""),
            sa.Column("original_url", sa.Text(), nullable=False, server_default=""),
            sa.Column("title", sa.String(length=512), nullable=False, server_default=""),
            sa.Column("content_excerpt", sa.Text(), nullable=False, server_default=""),
            sa.Column("author_name", sa.String(length=128), nullable=False, server_default=""),
            sa.Column("cover_url", sa.Text(), nullable=False, server_default=""),
            sa.Column("asset_urls_json", sa.JSON(), nullable=True),
            sa.Column("publish_time", sa.String(length=64), nullable=True),
            sa.Column("update_time", sa.String(length=64), nullable=True),
            sa.Column("rank_index", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("category", sa.String(length=128), nullable=False, server_default=""),
            sa.Column("tags_json", sa.JSON(), nullable=True),
            sa.Column("metrics_json", sa.JSON(), nullable=True),
            sa.Column("raw_json", sa.JSON(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("imported_note_id", sa.Integer(), sa.ForeignKey("notes.id"), nullable=True),
            sa.Column("decision_reason_code", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("decision_reason_text", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
        )
        for index_name, columns in (
            ("ix_data_acquisition_candidates_run_id", ["run_id"]),
            ("ix_data_acquisition_candidates_user_id", ["user_id"]),
            ("ix_data_acquisition_candidates_platform", ["platform"]),
            ("ix_data_acquisition_candidates_candidate_type", ["candidate_type"]),
            ("ix_data_acquisition_candidates_source", ["source"]),
            ("ix_data_acquisition_candidates_platform_note_id", ["platform_note_id"]),
            ("ix_data_acquisition_candidates_status", ["status"]),
            ("ix_data_acquisition_candidates_imported_note_id", ["imported_note_id"]),
        ):
            op.create_index(index_name, "data_acquisition_candidates", columns)

    if "note_source_snapshots" not in tables:
        op.create_table(
            "note_source_snapshots",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("note_id", sa.Integer(), sa.ForeignKey("notes.id"), nullable=False),
            sa.Column("run_id", sa.Integer(), sa.ForeignKey("data_acquisition_runs.id"), nullable=True),
            sa.Column("candidate_id", sa.Integer(), sa.ForeignKey("data_acquisition_candidates.id"), nullable=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("platform", sa.String(length=32), nullable=False),
            sa.Column("source", sa.String(length=32), nullable=False),
            sa.Column("snapshot_type", sa.String(length=32), nullable=False),
            sa.Column("source_url", sa.Text(), nullable=False, server_default=""),
            sa.Column("source_record_id", sa.String(length=128), nullable=False, server_default=""),
            sa.Column("fetched_at", sa.DateTime(), nullable=False),
            sa.Column("rank_index", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("keyword", sa.String(length=128), nullable=False, server_default=""),
            sa.Column("rank_type", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("category", sa.String(length=128), nullable=False, server_default=""),
            sa.Column("tags_json", sa.JSON(), nullable=True),
            sa.Column("metrics_json", sa.JSON(), nullable=True),
            sa.Column("analysis_json", sa.JSON(), nullable=True),
            sa.Column("raw_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        for index_name, columns in (
            ("ix_note_source_snapshots_note_id", ["note_id"]),
            ("ix_note_source_snapshots_run_id", ["run_id"]),
            ("ix_note_source_snapshots_candidate_id", ["candidate_id"]),
            ("ix_note_source_snapshots_user_id", ["user_id"]),
            ("ix_note_source_snapshots_platform", ["platform"]),
            ("ix_note_source_snapshots_source", ["source"]),
            ("ix_note_source_snapshots_snapshot_type", ["snapshot_type"]),
        ):
            op.create_index(index_name, "note_source_snapshots", columns)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    for table_name in ("note_source_snapshots", "data_acquisition_candidates", "data_acquisition_runs"):
        if table_name in tables:
            op.drop_table(table_name)

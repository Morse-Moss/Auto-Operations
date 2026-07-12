"""make XHS login confirmation idempotent

Revision ID: 20260712_xhs_login_idempotency
Revises: 20260710_model_capability_defaults
Create Date: 2026-07-12
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260712_xhs_login_idempotency"
down_revision: Union[str, Sequence[str], None] = "20260710_model_capability_defaults"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ACCOUNT_REFERENCES = {
    "account_cookie_versions": ("platform_account_id",),
    "notes": ("platform_account_id",),
    "publish_jobs": ("platform_account_id",),
    "monitoring_targets": ("platform_account_id",),
    "auto_tasks": ("pc_account_id", "creator_account_id"),
    "data_acquisition_runs": ("account_id",),
    "crawl_diagnostics": ("platform_account_id",),
}


def _merge_duplicate_accounts(bind) -> None:
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())
    groups = bind.execute(
        sa.text(
            "SELECT user_id, platform, sub_type, external_user_id, COUNT(*) AS duplicate_count "
            "FROM platform_accounts "
            "WHERE external_user_id IS NOT NULL AND TRIM(external_user_id) <> '' "
            "GROUP BY user_id, platform, sub_type, external_user_id "
            "HAVING COUNT(*) > 1"
        )
    ).mappings()

    for group in groups:
        rows = list(
            bind.execute(
                sa.text(
                    "SELECT id, status, nickname, avatar_url, profile_json, updated_at "
                    "FROM platform_accounts WHERE user_id = :user_id AND platform = :platform "
                    "AND sub_type = :sub_type AND external_user_id = :external_user_id"
                ),
                dict(group),
            ).mappings()
        )
        canonical = max(
            rows,
            key=lambda row: (
                2 if row["status"] == "active" else 1 if row["status"] != "deleted" else 0,
                bool(row["nickname"]),
                bool(row["avatar_url"]),
                len(str(row["profile_json"] or "")),
                str(row["updated_at"] or ""),
                -int(row["id"]),
            ),
        )
        canonical_id = int(canonical["id"])
        duplicate_ids = [int(row["id"]) for row in rows if int(row["id"]) != canonical_id]

        for duplicate_id in duplicate_ids:
            for table_name, column_names in ACCOUNT_REFERENCES.items():
                if table_name not in table_names:
                    continue
                existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
                for column_name in column_names:
                    if column_name not in existing_columns:
                        continue
                    bind.execute(
                        sa.text(
                            f"UPDATE {table_name} SET {column_name} = :canonical_id "
                            f"WHERE {column_name} = :duplicate_id"
                        ),
                        {"canonical_id": canonical_id, "duplicate_id": duplicate_id},
                    )
            bind.execute(
                sa.text("DELETE FROM platform_accounts WHERE id = :duplicate_id"),
                {"duplicate_id": duplicate_id},
            )


def upgrade() -> None:
    with op.batch_alter_table("login_sessions") as batch_op:
        batch_op.add_column(sa.Column("platform_account_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("poll_in_progress", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(sa.Column("poll_started_at", sa.DateTime(), nullable=True))
        batch_op.create_foreign_key(
            "fk_login_sessions_platform_account_id",
            "platform_accounts",
            ["platform_account_id"],
            ["id"],
        )
        batch_op.create_index(
            "ix_login_sessions_platform_account_id",
            ["platform_account_id"],
            unique=False,
        )

    bind = op.get_bind()
    _merge_duplicate_accounts(bind)
    bind.execute(
        sa.text(
            "UPDATE platform_accounts SET external_user_id = NULL "
            "WHERE external_user_id IS NOT NULL AND TRIM(external_user_id) = ''"
        )
    )
    with op.batch_alter_table("platform_accounts") as batch_op:
        batch_op.create_unique_constraint(
            "uq_platform_accounts_owned_identity",
            ["user_id", "platform", "sub_type", "external_user_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("platform_accounts") as batch_op:
        batch_op.drop_constraint("uq_platform_accounts_owned_identity", type_="unique")

    with op.batch_alter_table("login_sessions") as batch_op:
        batch_op.drop_index("ix_login_sessions_platform_account_id")
        batch_op.drop_constraint("fk_login_sessions_platform_account_id", type_="foreignkey")
        batch_op.drop_column("poll_started_at")
        batch_op.drop_column("poll_in_progress")
        batch_op.drop_column("platform_account_id")

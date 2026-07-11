"""add model capability defaults

Revision ID: 20260710_model_capability_defaults
Revises: 20260708_usage_ledger_followup_unique
Create Date: 2026-07-10
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260710_model_capability_defaults"
down_revision: Union[str, Sequence[str], None] = "20260708_usage_ledger_followup_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CAPABILITIES = {
    "text": ("text", None, True),
    "vision": ("image", {"openai-compatible", "volcengine-ark"}, True),
    "image_generation": ("image", {"openai-compatible", "runninghub-ai-app"}, False),
}


def _candidate_rows(
    bind,
    *,
    model_type: str,
    providers: set[str] | None,
    require_default: bool,
):
    conditions = [
        "u.role = 'admin'",
        "u.status = 'active'",
        "mc.model_type = :model_type",
        "TRIM(COALESCE(mc.model_name, '')) <> ''",
        "TRIM(COALESCE(mc.base_url, '')) <> ''",
        "TRIM(COALESCE(mc.encrypted_api_key, '')) <> ''",
    ]
    params = {"model_type": model_type}
    if require_default:
        conditions.append("mc.is_default = 1")
    if providers:
        placeholders = []
        for index, provider in enumerate(sorted(providers)):
            key = f"provider_{index}"
            params[key] = provider
            placeholders.append(f":{key}")
        conditions.append(f"mc.provider IN ({','.join(placeholders)})")
    query = sa.text(
        "SELECT mc.id AS model_config_id, mc.user_id AS updated_by_user_id "
        "FROM model_configs mc JOIN users u ON u.id = mc.user_id WHERE "
        + " AND ".join(conditions)
    )
    return list(bind.execute(query, params).mappings())


def upgrade() -> None:
    op.create_table(
        "model_capability_defaults",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("capability", sa.String(length=64), nullable=False),
        sa.Column("model_config_id", sa.Integer(), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["model_config_id"], ["model_configs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("capability", name="uq_model_capability_defaults_capability"),
    )
    op.create_index(
        "ix_model_capability_defaults_model_config_id",
        "model_capability_defaults",
        ["model_config_id"],
        unique=False,
    )

    bind = op.get_bind()
    for capability, (model_type, providers, require_default) in CAPABILITIES.items():
        candidates = _candidate_rows(
            bind,
            model_type=model_type,
            providers=providers,
            require_default=require_default,
        )
        if len(candidates) != 1:
            continue
        candidate = candidates[0]
        bind.execute(
            sa.text(
                "INSERT INTO model_capability_defaults "
                "(capability, model_config_id, updated_by_user_id, created_at, updated_at) "
                "VALUES (:capability, :model_config_id, :updated_by_user_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {
                "capability": capability,
                "model_config_id": candidate["model_config_id"],
                "updated_by_user_id": candidate["updated_by_user_id"],
            },
        )


def downgrade() -> None:
    op.drop_index(
        "ix_model_capability_defaults_model_config_id",
        table_name="model_capability_defaults",
    )
    op.drop_table("model_capability_defaults")

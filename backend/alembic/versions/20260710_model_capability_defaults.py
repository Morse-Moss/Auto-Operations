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
TABLE_NAME = "model_capability_defaults"
CAPABILITY_INDEX = "ix_model_capability_defaults_model_config_id"
REQUIRED_COLUMNS = {
    "id",
    "capability",
    "model_config_id",
    "updated_by_user_id",
    "created_at",
    "updated_at",
}
REQUIRED_COLUMN_SHAPES = {
    "id": (sa.Integer, None, False),
    "capability": (sa.String, 64, False),
    "model_config_id": (sa.Integer, None, False),
    "updated_by_user_id": (sa.Integer, None, False),
    "created_at": (sa.DateTime, None, False),
    "updated_at": (sa.DateTime, None, False),
}
REQUIRED_FOREIGN_KEYS = {
    ("model_config_id",): ("model_configs", ("id",)),
    ("updated_by_user_id",): ("users", ("id",)),
}


def _validate_existing_table(bind) -> None:
    inspector = sa.inspect(bind)
    problems = []

    columns = {
        column["name"]: column
        for column in inspector.get_columns(TABLE_NAME)
    }
    missing_columns = sorted(REQUIRED_COLUMNS - columns.keys())
    if missing_columns:
        problems.append(f"missing columns: {', '.join(missing_columns)}")

    for name, (expected_type, expected_length, expected_nullable) in REQUIRED_COLUMN_SHAPES.items():
        column = columns.get(name)
        if column is None:
            continue
        actual_type = column.get("type")
        if not isinstance(actual_type, expected_type):
            problems.append(f"invalid type for column {name}: {actual_type}")
        elif expected_length is not None and getattr(actual_type, "length", None) != expected_length:
            problems.append(
                f"invalid length for column {name}: {getattr(actual_type, 'length', None)}"
            )
        if bool(column.get("nullable")) != expected_nullable:
            problems.append(f"invalid nullability for column {name}")

    primary_key = tuple(
        inspector.get_pk_constraint(TABLE_NAME).get("constrained_columns") or ()
    )
    if primary_key != ("id",):
        problems.append("invalid primary key; expected id")

    unique_constraints = {
        tuple(constraint.get("column_names") or ())
        for constraint in inspector.get_unique_constraints(TABLE_NAME)
    }
    if ("capability",) not in unique_constraints:
        problems.append("missing unique constraint on capability")

    foreign_keys = {
        tuple(foreign_key.get("constrained_columns") or ()): (
            foreign_key.get("referred_table"),
            tuple(foreign_key.get("referred_columns") or ()),
            str((foreign_key.get("options") or {}).get("ondelete") or "").upper(),
        )
        for foreign_key in inspector.get_foreign_keys(TABLE_NAME)
    }
    for constrained_columns, (target_table, target_columns) in REQUIRED_FOREIGN_KEYS.items():
        expected_target = (target_table, target_columns, "RESTRICT")
        if foreign_keys.get(constrained_columns) != expected_target:
            source = ", ".join(constrained_columns)
            target = f"{target_table}.{'.'.join(target_columns)}"
            problems.append(f"missing foreign key {source} -> {target}")

    indexes = {
        str(index.get("name") or ""): tuple(index.get("column_names") or ())
        for index in inspector.get_indexes(TABLE_NAME)
    }
    capability_index_columns = indexes.get(CAPABILITY_INDEX)
    if capability_index_columns is not None and capability_index_columns != ("model_config_id",):
        problems.append(
            f"invalid index {CAPABILITY_INDEX}: {capability_index_columns}"
        )

    if problems:
        raise RuntimeError(
            f"incompatible {TABLE_NAME}: {'; '.join(problems)}"
        )

    if capability_index_columns is None:
        op.create_index(
            CAPABILITY_INDEX,
            TABLE_NAME,
            ["model_config_id"],
            unique=False,
        )


def _ensure_capability_table(bind) -> None:
    if TABLE_NAME in sa.inspect(bind).get_table_names():
        _validate_existing_table(bind)
        return

    op.create_table(
        TABLE_NAME,
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
        CAPABILITY_INDEX,
        TABLE_NAME,
        ["model_config_id"],
        unique=False,
    )


def _has_binding(bind, capability: str) -> bool:
    return (
        bind.execute(
            sa.text(
                f"SELECT 1 FROM {TABLE_NAME} "
                "WHERE capability = :capability LIMIT 1"
            ),
            {"capability": capability},
        ).first()
        is not None
    )


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
    bind = op.get_bind()
    _ensure_capability_table(bind)
    for capability, (model_type, providers, require_default) in CAPABILITIES.items():
        if _has_binding(bind, capability):
            continue
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

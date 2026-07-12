from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
import pytest
import sqlalchemy as sa


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PREVIOUS_REVISION = "20260708_usage_ledger_followup_unique"
HEAD_REVISION = "20260710_model_capability_defaults"
TABLE_NAME = "model_capability_defaults"
CAPABILITY_INDEX = "ix_model_capability_defaults_model_config_id"
ALTERNATE_CAPABILITY_INDEX = "ix_capability_defaults_model_config_alternate"
SENTINEL_BINDING = {
    "id": 77,
    "capability": "text",
    "model_config_id": 15,
    "updated_by_user_id": 1,
    "created_at": "2026-01-02 03:04:05",
    "updated_at": "2026-01-03 04:05:06",
}


def _alembic_config(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    config = Config(str(PROJECT_ROOT / "backend" / "alembic.ini"))
    config.set_main_option(
        "script_location",
        str(PROJECT_ROOT / "backend" / "alembic"),
    )
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    return config


def _engine(db_path: Path) -> sa.Engine:
    return sa.create_engine(f"sqlite:///{db_path.as_posix()}")


def _upgrade_to_previous_revision(config: Config) -> None:
    command.upgrade(config, PREVIOUS_REVISION)


def _seed_admin_and_model_configs(engine: sa.Engine) -> dict[str, int]:
    config_ids = {
        "text": 11,
        "vision": 12,
        "image_openai": 13,
        "image_runninghub": 14,
        "text_alternate": 15,
    }
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO users "
                "(id, username, password_hash, created_at, role, status) "
                "VALUES (1, 'migration-admin', 'test-hash', CURRENT_TIMESTAMP, 'admin', 'active')"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO model_configs "
                "(id, user_id, name, model_type, provider, model_name, base_url, "
                "encrypted_api_key, is_default) VALUES "
                "(:text_id, 1, 'Text Default', 'text', 'volcengine-ark', "
                "'text-model', 'https://text.example.test', 'encrypted-text-key', 1), "
                "(:vision_id, 1, 'Vision Default', 'image', 'volcengine-ark', "
                "'vision-model', 'https://vision.example.test', 'encrypted-vision-key', 1), "
                "(:image_openai_id, 1, 'OpenAI Image', 'image', 'openai-compatible', "
                "'image-openai-model', 'https://openai.example.test', 'encrypted-openai-key', 0), "
                "(:image_runninghub_id, 1, 'RunningHub Image', 'image', 'runninghub-ai-app', "
                "'image-runninghub-model', 'https://runninghub.example.test', "
                "'encrypted-runninghub-key', 0), "
                "(:text_alternate_id, 1, 'Text Alternate', 'text', 'volcengine-ark', "
                "'text-alternate-model', 'https://text-alt.example.test', "
                "'encrypted-text-alt-key', 0)"
            ),
            {
                "text_id": config_ids["text"],
                "vision_id": config_ids["vision"],
                "image_openai_id": config_ids["image_openai"],
                "image_runninghub_id": config_ids["image_runninghub"],
                "text_alternate_id": config_ids["text_alternate"],
            },
        )
    return config_ids


def _create_capability_table(
    engine: sa.Engine,
    *,
    index_name: str = CAPABILITY_INDEX,
    index_column: str = "model_config_id",
    model_config_nullable: bool = False,
    created_at_type: sa.types.TypeEngine | None = None,
) -> None:
    metadata = sa.MetaData()
    metadata.reflect(engine, only=["model_configs", "users"])
    table = sa.Table(
        TABLE_NAME,
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("capability", sa.String(length=64), nullable=False),
        sa.Column("model_config_id", sa.Integer(), nullable=model_config_nullable),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            created_at_type or sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["model_config_id"],
            ["model_configs.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "capability",
            name="uq_model_capability_defaults_capability",
        ),
    )
    sa.Index(
        index_name,
        table.c[index_column],
    )
    metadata.create_all(engine)


def _revision(engine: sa.Engine) -> str:
    with engine.connect() as connection:
        return connection.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).scalar_one()


def _bindings(engine: sa.Engine) -> dict[str, int]:
    with engine.connect() as connection:
        rows = connection.execute(
            sa.text(
                "SELECT capability, model_config_id "
                "FROM model_capability_defaults ORDER BY capability"
            )
        ).mappings()
        return {row["capability"]: row["model_config_id"] for row in rows}


def _binding_row(engine: sa.Engine, capability: str) -> dict:
    with engine.connect() as connection:
        row = connection.execute(
            sa.text(
                "SELECT id, capability, model_config_id, updated_by_user_id, "
                "created_at, updated_at FROM model_capability_defaults "
                "WHERE capability = :capability"
            ),
            {"capability": capability},
        ).mappings().one()
        return dict(row)


@pytest.mark.parametrize("existing_text_binding", [False, True])
def test_half_applied_migration_reuses_table_and_preserves_bindings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    existing_text_binding: bool,
):
    db_path = tmp_path / f"half-applied-{existing_text_binding}.db"
    config = _alembic_config(db_path, monkeypatch)
    _upgrade_to_previous_revision(config)
    engine = _engine(db_path)
    try:
        config_ids = _seed_admin_and_model_configs(engine)
        _create_capability_table(engine)
        if existing_text_binding:
            with engine.begin() as connection:
                connection.execute(
                    sa.text(
                        "INSERT INTO model_capability_defaults "
                        "(id, capability, model_config_id, updated_by_user_id, "
                        "created_at, updated_at) VALUES "
                        "(:id, :capability, :model_config_id, :updated_by_user_id, "
                        ":created_at, :updated_at)"
                    ),
                    SENTINEL_BINDING,
                )

        command.upgrade(config, "head")

        assert _revision(engine) == HEAD_REVISION
        assert _bindings(engine) == {
            "text": (
                config_ids["text_alternate"]
                if existing_text_binding
                else config_ids["text"]
            ),
            "vision": config_ids["vision"],
        }
        if existing_text_binding:
            assert _binding_row(engine, "text") == SENTINEL_BINDING
    finally:
        engine.dispose()


def test_fresh_upgrade_creates_table_and_backfills_only_unique_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    db_path = tmp_path / "fresh-upgrade.db"
    config = _alembic_config(db_path, monkeypatch)
    _upgrade_to_previous_revision(config)
    engine = _engine(db_path)
    try:
        config_ids = _seed_admin_and_model_configs(engine)

        command.upgrade(config, "head")

        assert _revision(engine) == HEAD_REVISION
        assert _bindings(engine) == {
            "text": config_ids["text"],
            "vision": config_ids["vision"],
        }
    finally:
        engine.dispose()


def test_upgrade_rejects_incompatible_existing_capability_table(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    db_path = tmp_path / "incompatible-table.db"
    config = _alembic_config(db_path, monkeypatch)
    _upgrade_to_previous_revision(config)
    engine = _engine(db_path)
    try:
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "CREATE TABLE model_capability_defaults "
                    "(id INTEGER PRIMARY KEY, capability VARCHAR(64) NOT NULL)"
                )
            )

        with pytest.raises(
            RuntimeError,
            match="incompatible model_capability_defaults",
        ):
            command.upgrade(config, "head")
    finally:
        engine.dispose()


def test_upgrade_creates_exact_named_index_before_downgrade(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    db_path = tmp_path / "alternate-index.db"
    config = _alembic_config(db_path, monkeypatch)
    _upgrade_to_previous_revision(config)
    engine = _engine(db_path)
    try:
        _create_capability_table(engine, index_name=ALTERNATE_CAPABILITY_INDEX)

        command.upgrade(config, "head")

        index_names = {
            index["name"]
            for index in sa.inspect(engine).get_indexes(TABLE_NAME)
        }
        assert CAPABILITY_INDEX in index_names

        command.downgrade(config, PREVIOUS_REVISION)

        assert _revision(engine) == PREVIOUS_REVISION
        assert TABLE_NAME not in sa.inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_upgrade_rejects_incompatible_column_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    db_path = tmp_path / "incompatible-column-shape.db"
    config = _alembic_config(db_path, monkeypatch)
    _upgrade_to_previous_revision(config)
    engine = _engine(db_path)
    try:
        _create_capability_table(
            engine,
            model_config_nullable=True,
            created_at_type=sa.String(length=64),
        )

        with pytest.raises(
            RuntimeError,
            match="incompatible model_capability_defaults",
        ):
            command.upgrade(config, "head")
    finally:
        engine.dispose()


def test_upgrade_rejects_named_index_on_wrong_column(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    db_path = tmp_path / "wrong-named-index.db"
    config = _alembic_config(db_path, monkeypatch)
    _upgrade_to_previous_revision(config)
    engine = _engine(db_path)
    try:
        _create_capability_table(
            engine,
            index_name=CAPABILITY_INDEX,
            index_column="updated_by_user_id",
        )

        with pytest.raises(
            RuntimeError,
            match="incompatible model_capability_defaults",
        ):
            command.upgrade(config, "head")
    finally:
        engine.dispose()

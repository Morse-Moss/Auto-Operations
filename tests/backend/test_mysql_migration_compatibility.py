from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import sqlalchemy as sa


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_migration(filename: str) -> ModuleType:
    path = PROJECT_ROOT / "backend" / "alembic" / "versions" / filename
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_draft_assets_mysql_migration_does_not_set_defaults_on_text_columns():
    migration = _load_migration("31c257707df9_add_draft_assets_table.py")
    captured: dict[str, tuple[sa.Column, ...]] = {}

    def fake_create_table(table_name: str, *columns: sa.Column, **_kwargs) -> None:
        captured[table_name] = columns

    with patch.object(migration.op, "create_table", fake_create_table):
        migration.upgrade()

    draft_assets_columns = captured["draft_assets"]
    text_columns = {
        column.name: column
        for column in draft_assets_columns
        if isinstance(column.type, sa.Text)
    }

    assert set(text_columns) == {"url", "local_path"}
    assert text_columns["url"].server_default is None
    assert text_columns["local_path"].server_default is None


def test_wechat_official_tombstones_uses_mysql_safe_url_index_column():
    migration = _load_migration("20260618_add_wechat_official_content_library_tombstones.py")
    captured: dict[str, tuple[sa.Column, ...]] = {}

    def fake_create_table(table_name: str, *columns: sa.Column, **_kwargs) -> None:
        captured[table_name] = columns

    with (
        patch.object(migration.op, "create_table", fake_create_table),
        patch.object(migration.op, "create_index"),
        patch.object(migration.op, "f", lambda name: name),
    ):
        migration.upgrade()

    tombstone_columns = captured["wechat_official_content_library_tombstones"]
    article_url = next(column for column in tombstone_columns if column.name == "article_url")

    assert isinstance(article_url.type, sa.String)
    assert not isinstance(article_url.type, sa.Text)
    assert article_url.type.length is not None
    assert article_url.type.length <= 512

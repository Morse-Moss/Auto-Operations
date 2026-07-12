from __future__ import annotations

import ast
import importlib.util
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from types import ModuleType
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import mysql, sqlite


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = PROJECT_ROOT / "backend" / "alembic" / "versions"


def _load_migration(filename: str) -> ModuleType:
    path = MIGRATIONS_DIR / filename
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _is_sa_text_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "Text"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "sa"
    )


def _is_sa_column_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "Column"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "sa"
    )


def _column_name(node: ast.Call) -> str:
    if node.args and isinstance(node.args[0], ast.Constant):
        return str(node.args[0].value)
    return "<unknown>"


def _text_columns_with_server_default() -> list[str]:
    offenders: list[str] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not _is_sa_column_call(node):
                continue
            if not any(_is_sa_text_call(arg) for arg in node.args[1:]):
                continue
            if any(keyword.arg == "server_default" for keyword in node.keywords):
                offenders.append(f"{path.name}:{node.lineno}:{_column_name(node)}")
    return offenders


def _revision_ids() -> list[str]:
    revision_ids: list[str] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.target.id == "revision"
                and isinstance(node.value, ast.Constant)
            ):
                revision_ids.append(str(node.value.value))
    return revision_ids


class _FakeInspector:
    def __init__(self, columns: list[dict] | None = None) -> None:
        self.columns = columns

    def get_table_names(self) -> list[str]:
        return ["alembic_version"] if self.columns is not None else []

    def get_columns(self, table_name: str) -> list[dict]:
        assert table_name == "alembic_version"
        return self.columns or []


class _FakeConnection:
    def __init__(self, dialect=None, in_transaction: bool = False) -> None:
        self.dialect = dialect or mysql.dialect()
        self._in_transaction = in_transaction
        self.commit_count = 0
        self.statements: list[str] = []

    def execute(self, statement) -> None:
        self.statements.append(str(statement))

    def in_transaction(self) -> bool:
        return self._in_transaction

    def commit(self) -> None:
        self.commit_count += 1
        self._in_transaction = False


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


def test_mysql_migrations_do_not_set_server_defaults_on_text_columns():
    assert _text_columns_with_server_default() == []


def test_mysql_alembic_version_length_covers_all_revision_ids():
    from backend.app.core.alembic_compat import ALEMBIC_VERSION_NUM_LENGTH

    max_revision_length = max(len(revision_id) for revision_id in _revision_ids())

    assert max_revision_length > 32
    assert ALEMBIC_VERSION_NUM_LENGTH >= max_revision_length


def test_mysql_alembic_version_table_is_created_with_wide_revision_column(monkeypatch):
    from backend.app.core import alembic_compat

    connection = _FakeConnection()
    monkeypatch.setattr(alembic_compat, "inspect", lambda _connection: _FakeInspector())

    alembic_compat.ensure_mysql_alembic_version_table(connection)

    assert connection.statements == [
        "CREATE TABLE alembic_version (version_num VARCHAR(128) NOT NULL, CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
    ]


def test_mysql_alembic_version_table_is_widened_when_existing_column_is_short(monkeypatch):
    from backend.app.core import alembic_compat

    connection = _FakeConnection()
    monkeypatch.setattr(
        alembic_compat,
        "inspect",
        lambda _connection: _FakeInspector([{"name": "version_num", "type": sa.String(length=32)}]),
    )

    alembic_compat.ensure_mysql_alembic_version_table(connection)

    assert connection.statements == [
        "ALTER TABLE alembic_version MODIFY version_num VARCHAR(128) NOT NULL"
    ]


def test_prepare_mysql_alembic_connection_commits_preflight_autobegin(monkeypatch):
    from backend.app.core import alembic_compat

    connection = _FakeConnection()

    def inspect_with_autobegin(_connection):
        connection._in_transaction = True
        return _FakeInspector([{"name": "version_num", "type": sa.String(length=128)}])

    monkeypatch.setattr(
        alembic_compat,
        "inspect",
        inspect_with_autobegin,
    )

    alembic_compat.prepare_mysql_alembic_connection(connection)

    assert connection.statements == []
    assert connection.commit_count == 1
    assert connection.in_transaction() is False


def test_mysql_preflight_commits_before_alembic_context_configure(monkeypatch):
    from alembic import context as alembic_context
    from backend.app.core import alembic_compat

    connection = _FakeConnection()
    events: list[str] = []

    def inspect_with_autobegin(_connection):
        connection._in_transaction = True
        events.append("inspect")
        return _FakeInspector([{"name": "version_num", "type": sa.String(length=128)}])

    original_commit = connection.commit

    def record_commit() -> None:
        original_commit()
        events.append("commit")

    @contextmanager
    def connect():
        yield connection

    @contextmanager
    def begin_transaction():
        yield

    def configure(**_kwargs) -> None:
        assert connection.commit_count == 1
        assert connection.in_transaction() is False
        events.append("configure")

    fake_config = SimpleNamespace(
        config_file_name=None,
        config_ini_section="alembic",
        get_main_option=lambda _name: "mysql+pymysql://",
        get_section=lambda _name, _default: {},
    )
    fake_engine = SimpleNamespace(connect=connect)

    monkeypatch.setenv("DATABASE_URL", "mysql+pymysql://")
    monkeypatch.setattr(connection, "commit", record_commit)
    monkeypatch.setattr(alembic_compat, "inspect", inspect_with_autobegin)
    monkeypatch.setattr(sa, "engine_from_config", lambda *_args, **_kwargs: fake_engine)
    monkeypatch.setattr(alembic_context, "config", fake_config, raising=False)
    monkeypatch.setattr(alembic_context, "is_offline_mode", lambda: False)
    monkeypatch.setattr(alembic_context, "configure", configure)
    monkeypatch.setattr(alembic_context, "begin_transaction", begin_transaction)
    monkeypatch.setattr(alembic_context, "run_migrations", lambda: events.append("migrate"))

    path = PROJECT_ROOT / "backend" / "alembic" / "env.py"
    spec = importlib.util.spec_from_file_location("test_alembic_env", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    assert events == ["inspect", "commit", "configure", "migrate"]


def test_prepare_mysql_alembic_connection_rejects_existing_transaction(monkeypatch):
    from backend.app.core import alembic_compat

    connection = _FakeConnection(in_transaction=True)
    inspect_count = 0

    def record_inspect(_connection):
        nonlocal inspect_count
        inspect_count += 1
        return _FakeInspector([{"name": "version_num", "type": sa.String(length=128)}])

    monkeypatch.setattr(
        alembic_compat,
        "inspect",
        record_inspect,
    )

    with pytest.raises(RuntimeError, match="transaction-free"):
        alembic_compat.prepare_mysql_alembic_connection(connection)

    assert connection.commit_count == 0
    assert inspect_count == 0


def test_prepare_mysql_alembic_connection_does_not_commit_sqlite():
    from backend.app.core import alembic_compat

    connection = _FakeConnection(dialect=sqlite.dialect(), in_transaction=True)

    alembic_compat.prepare_mysql_alembic_connection(connection)

    assert connection.commit_count == 0


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

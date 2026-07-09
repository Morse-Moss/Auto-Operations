from __future__ import annotations

from sqlalchemy import inspect, text


ALEMBIC_VERSION_NUM_LENGTH = 128


def _quote_identifier(connection, name: str) -> str:
    return connection.dialect.identifier_preparer.quote(name)


def ensure_mysql_alembic_version_table(connection) -> None:
    if connection.dialect.name not in {"mysql", "mariadb"}:
        return

    inspector = inspect(connection)
    table_name = "alembic_version"
    version_column = "version_num"
    quoted_table = _quote_identifier(connection, table_name)
    quoted_column = _quote_identifier(connection, version_column)

    if table_name not in inspector.get_table_names():
        connection.execute(
            text(
                f"CREATE TABLE {quoted_table} ("
                f"{quoted_column} VARCHAR({ALEMBIC_VERSION_NUM_LENGTH}) NOT NULL, "
                f"CONSTRAINT {_quote_identifier(connection, table_name + '_pkc')} PRIMARY KEY ({quoted_column})"
                ")"
            )
        )
        return

    columns = {column["name"]: column for column in inspector.get_columns(table_name)}
    version_type = columns.get(version_column, {}).get("type")
    current_length = getattr(version_type, "length", None)
    if current_length is None or int(current_length) < ALEMBIC_VERSION_NUM_LENGTH:
        connection.execute(
            text(
                f"ALTER TABLE {quoted_table} MODIFY {quoted_column} "
                f"VARCHAR({ALEMBIC_VERSION_NUM_LENGTH}) NOT NULL"
            )
        )

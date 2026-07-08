from __future__ import annotations

from pathlib import Path

import pytest


def _write_config(path: Path) -> None:
    path.write_text(
        "\n".join([
            "security:",
            "  secret_key: yaml-secret",
            "  fernet_key: yaml-fernet",
            "database:",
            "  type: sqlite",
            "  sqlite_path: ./data/test-config.db",
        ]),
        encoding="utf-8",
    )


def test_environment_secret_key_overrides_yaml(monkeypatch, tmp_path):
    from backend.app.core.config import get_settings

    config_path = tmp_path / "config.yaml"
    _write_config(config_path)
    monkeypatch.setenv("CONFIG_FILE", str(config_path))
    monkeypatch.setenv("SECRET_KEY", "env-secret-for-test")
    get_settings.cache_clear()

    try:
        assert get_settings().secret_key == "env-secret-for-test"
    finally:
        get_settings.cache_clear()


def test_production_settings_reject_placeholder_secret(monkeypatch, tmp_path):
    from backend.app.core.config import get_settings

    config_path = tmp_path / "production.yaml"
    config_path.write_text(
        "\n".join([
            "server:",
            "  cors_origins: https://ops.example.com",
            "database:",
            "  type: mysql",
            "  mysql_host: mysql",
            "  mysql_user: spider_xhs",
            "  mysql_password: strong-db-password",
            "  mysql_database: spider_xhs",
            "security:",
            "  secret_key: dev-only-change-me",
        ]),
        encoding="utf-8",
    )
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("CONFIG_FILE", str(config_path))
    get_settings.cache_clear()

    try:
        with pytest.raises(ValueError, match="SECRET_KEY"):
            get_settings()
    finally:
        get_settings.cache_clear()


def test_production_settings_reject_sqlite(monkeypatch, tmp_path):
    from backend.app.core.config import get_settings

    config_path = tmp_path / "production.yaml"
    config_path.write_text(
        "\n".join([
            "server:",
            "  cors_origins: https://ops.example.com",
            "database:",
            "  type: sqlite",
            "  sqlite_path: ./data/prod.db",
            "security:",
            "  secret_key: production-secret-with-enough-length",
        ]),
        encoding="utf-8",
    )
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("CONFIG_FILE", str(config_path))
    get_settings.cache_clear()

    try:
        with pytest.raises(ValueError, match="SQLite"):
            get_settings()
    finally:
        get_settings.cache_clear()


def test_production_settings_reject_placeholder_cors_origin(monkeypatch, tmp_path):
    from backend.app.core.config import get_settings

    config_path = tmp_path / "production.yaml"
    config_path.write_text(
        "\n".join([
            "server:",
            "  cors_origins: https://your-domain.com",
            "database:",
            "  type: mysql",
            "  mysql_host: mysql",
            "  mysql_user: spider_xhs",
            "  mysql_password: strong-db-password",
            "  mysql_database: spider_xhs",
            "security:",
            "  secret_key: production-secret-with-enough-length",
        ]),
        encoding="utf-8",
    )
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("CONFIG_FILE", str(config_path))
    get_settings.cache_clear()

    try:
        with pytest.raises(ValueError, match="CORS"):
            get_settings()
    finally:
        get_settings.cache_clear()


def test_production_scheduler_requires_explicit_external_actions_opt_in(monkeypatch, tmp_path):
    from backend.app.core.config import get_settings

    config_path = tmp_path / "production.yaml"
    config_path.write_text(
        "\n".join([
            "server:",
            "  cors_origins: https://ops.example.com",
            "database:",
            "  type: mysql",
            "  mysql_host: mysql",
            "  mysql_user: spider_xhs",
            "  mysql_password: strong-db-password",
            "  mysql_database: spider_xhs",
            "security:",
            "  secret_key: production-secret-with-enough-length",
            "scheduler:",
            "  enabled: true",
        ]),
        encoding="utf-8",
    )
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("CONFIG_FILE", str(config_path))
    monkeypatch.delenv("ALLOW_PRODUCTION_EXTERNAL_ACTIONS", raising=False)
    get_settings.cache_clear()

    try:
        with pytest.raises(ValueError, match="ALLOW_PRODUCTION_EXTERNAL_ACTIONS"):
            get_settings()
    finally:
        get_settings.cache_clear()


def test_production_settings_accept_hardened_values(monkeypatch, tmp_path):
    from backend.app.core.config import get_settings

    config_path = tmp_path / "production.yaml"
    config_path.write_text(
        "\n".join([
            "server:",
            "  cors_origins: https://ops.example.com",
            "database:",
            "  type: mysql",
            "  mysql_host: mysql",
            "  mysql_user: spider_xhs",
            "  mysql_password: strong-db-password",
            "  mysql_database: spider_xhs",
            "security:",
            "  secret_key: production-secret-with-enough-length",
            "  fernet_key: stable-fernet-key-material",
            "scheduler:",
            "  enabled: false",
        ]),
        encoding="utf-8",
    )
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("CONFIG_FILE", str(config_path))
    get_settings.cache_clear()

    try:
        settings = get_settings()
        assert settings.environment == "production"
        assert settings.database_type == "mysql"
        assert settings.scheduler_enabled is False
    finally:
        get_settings.cache_clear()


def test_environment_fernet_key_overrides_yaml(monkeypatch, tmp_path):
    from backend.app.core.config import get_settings

    config_path = tmp_path / "config.yaml"
    _write_config(config_path)
    monkeypatch.setenv("CONFIG_FILE", str(config_path))
    monkeypatch.setenv("FERNET_KEY", "env-fernet-for-test")
    get_settings.cache_clear()

    try:
        assert get_settings().fernet_key == "env-fernet-for-test"
    finally:
        get_settings.cache_clear()


def test_yaml_config_applies_when_environment_is_absent(monkeypatch, tmp_path):
    from backend.app.core.config import get_settings

    config_path = tmp_path / "config.yaml"
    _write_config(config_path)
    monkeypatch.setenv("CONFIG_FILE", str(config_path))
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("FERNET_KEY", raising=False)
    get_settings.cache_clear()

    try:
        settings = get_settings()
        assert settings.secret_key == "yaml-secret"
        assert settings.fernet_key == "yaml-fernet"
    finally:
        get_settings.cache_clear()

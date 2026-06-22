from __future__ import annotations

from pathlib import Path


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

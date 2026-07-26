from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ImportError:  # pragma: no cover - handled by dependency installation
    BaseSettings = object
    SettingsConfigDict = dict


def _load_yaml_config() -> Dict[str, Any]:
    """Load YAML configuration files and flatten into env-var-style keys.

    Loading order (later values override earlier ones):
      1. config/default.yaml (always loaded if it exists)
      2. File specified by CONFIG_FILE environment variable
    """
    try:
        import yaml
    except ImportError:
        return {}

    project_root = Path(__file__).resolve().parent.parent.parent.parent
    flat: Dict[str, Any] = {}

    # Mapping from nested YAML paths to Settings field names
    yaml_key_map = {
        "server.host": "server_host",
        "server.port": "server_port",
        "server.cors_origins": "backend_cors_origins",
        "database.type": "database_type",
        "database.sqlite_path": "database_sqlite_path",
        "database.mysql_host": "database_mysql_host",
        "database.mysql_port": "database_mysql_port",
        "database.mysql_user": "database_mysql_user",
        "database.mysql_password": "database_mysql_password",
        "database.mysql_database": "database_mysql_database",
        "security.secret_key": "secret_key",
        "security.fernet_key": "fernet_key",
        "auth.allow_public_registration": "allow_public_registration",
        "scheduler.enabled": "scheduler_enabled",
        "scheduler.interval_seconds": "scheduler_interval_seconds",
        "scheduler.crawl_rate_limit_per_minute": "crawl_rate_limit_per_minute",
        "frontend.serve_static": "frontend_serve_static",
        "frontend.build_dir": "frontend_build_dir",
    }

    def _flatten(data: Any, prefix: str = "") -> None:
        if isinstance(data, dict):
            for key, value in data.items():
                full_key = f"{prefix}.{key}" if prefix else key
                if full_key in yaml_key_map:
                    flat[yaml_key_map[full_key]] = value
                _flatten(value, full_key)

    # 1. Load config/default.yaml
    default_yaml = project_root / "config" / "default.yaml"
    if default_yaml.exists():
        with open(default_yaml, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            if data:
                _flatten(data)

    # 2. Load CONFIG_FILE override
    config_file = os.environ.get("CONFIG_FILE")
    if config_file:
        config_path = Path(config_file)
        if not config_path.is_absolute():
            config_path = project_root / config_path
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data:
                    _flatten(data)

    return flat


# Known placeholder secret keys that must never protect a network-reachable deployment.
PLACEHOLDER_SECRET_KEYS = {"", "dev-only-change-me", "change-me", "secret", "change_me_via_env_var"}
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def is_placeholder_secret_key(secret_key: str) -> bool:
    return (secret_key or "").strip().lower() in PLACEHOLDER_SECRET_KEYS


def validate_secret_key_for_host(settings: "Settings", listen_host: str | None = None) -> None:
    """Unconditional startup hard gate, independent of ENVIRONMENT.

    A placeholder SECRET_KEY lets anyone on the network forge login tokens and
    signed media URLs. Loopback-only development keeps working; any server that
    listens beyond loopback must configure a real secret before it can start.
    """
    if not is_placeholder_secret_key(settings.secret_key):
        return
    effective_host = (listen_host if listen_host is not None else settings.server_host or "").strip()
    if effective_host.lower() in LOOPBACK_HOSTS:
        return
    raise RuntimeError(
        f"SECRET_KEY 仍是占位值，而服务监听地址是 {effective_host or '(未知)'}（非本机回环），已拒绝启动，"
        "否则局域网内任何人都能伪造登录令牌。请设置环境变量 SECRET_KEY=<足够长的随机字符串>"
        "（例如用 openssl rand -hex 32 生成），或在 config/*.yaml 的 security.secret_key 填入真实密钥；"
        "如果只在本机使用，也可以把 server.host 改为 127.0.0.1。"
    )


class Settings(BaseSettings):
    app_name: str = "Spider_XHS"
    api_title: str = "Spider_XHS Operations Platform"
    environment: str = "development"

    # Database
    database_url: str = ""
    database_type: str = "sqlite"
    database_sqlite_path: str = "./data/spider_xhs.db"
    database_mysql_host: str = "localhost"
    database_mysql_port: int = 3306
    database_mysql_user: str = "spider_xhs"
    database_mysql_password: str = "change_me"
    database_mysql_database: str = "spider_xhs"

    # Security
    secret_key: str = "dev-only-change-me"
    fernet_key: str = ""
    beta_admin_bootstrap_token: str = ""
    allow_public_registration: bool = False

    # Server
    server_host: str = "0.0.0.0"
    server_port: int = 18081

    # CORS
    backend_cors_origins: str = "http://127.0.0.1:18080,http://localhost:18080"

    # Scheduler
    scheduler_enabled: bool = False
    scheduler_interval_seconds: int = 60
    crawl_rate_limit_per_minute: int = 5
    allow_production_external_actions: bool = False

    # Asset storage
    asset_storage_type: str = "local"

    # Frontend static serving
    frontend_serve_static: bool = False
    frontend_build_dir: str = "./frontend/dist"

    if hasattr(BaseSettings, "model_config"):
        model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    def model_post_init(self, __context: Any) -> None:
        # Build database_url from component fields if not explicitly set
        if not self.database_url:
            if self.database_type == "mysql":
                mysql_host = os.environ.get("MYSQLHOST")
                mysql_port = os.environ.get("MYSQLPORT")
                mysql_user = os.environ.get("MYSQLUSER")
                mysql_password = os.environ.get("MYSQLPASSWORD")
                mysql_database = os.environ.get("MYSQLDATABASE")
                if mysql_host and self.database_mysql_host in {"localhost", "mysql"}:
                    object.__setattr__(self, "database_mysql_host", mysql_host)
                if mysql_port and self.database_mysql_port == 3306:
                    object.__setattr__(self, "database_mysql_port", int(mysql_port))
                if mysql_user and self.database_mysql_user == "spider_xhs":
                    object.__setattr__(self, "database_mysql_user", mysql_user)
                if mysql_password and self.database_mysql_password in {"", "change_me", "CHANGE_ME_VIA_ENV_VAR"}:
                    object.__setattr__(self, "database_mysql_password", mysql_password)
                if mysql_database and self.database_mysql_database == "spider_xhs":
                    object.__setattr__(self, "database_mysql_database", mysql_database)
                object.__setattr__(
                    self,
                    "database_url",
                    f"mysql+pymysql://{self.database_mysql_user}:{self.database_mysql_password}"
                    f"@{self.database_mysql_host}:{self.database_mysql_port}/{self.database_mysql_database}"
                    "?charset=utf8mb4",
                )
            else:
                # Backward compatibility: if the old default DB path exists but the
                # new YAML-configured path does not, use the old path so existing
                # installations keep their data without manual migration.
                sqlite_path = self.database_sqlite_path
                old_default = "./backend/app/storage/spider_xhs.db"
                if sqlite_path != old_default:
                    new_db = Path(sqlite_path)
                    old_db = Path(old_default)
                    if not new_db.exists() and old_db.exists():
                        sqlite_path = old_default
                object.__setattr__(
                    self,
                    "database_url",
                    f"sqlite:///{sqlite_path}",
                )
        self._validate_production_settings()

    @property
    def storage_dir(self) -> Path:
        return Path("backend/app/storage")

    def _validate_production_settings(self) -> None:
        if self.environment.lower() != "production":
            return

        secret = self.secret_key.strip()
        if secret in {"", "dev-only-change-me", "CHANGE_ME_VIA_ENV_VAR"} or len(secret) < 24:
            raise ValueError("SECRET_KEY must be set to a non-placeholder value in production")

        if self.database_type.lower() == "sqlite" or self.database_url.startswith("sqlite:"):
            raise ValueError("SQLite is not allowed in production; configure MySQL or another server database")
        if self.database_mysql_password in {"", "change_me", "CHANGE_ME_VIA_ENV_VAR"}:
            raise ValueError("DATABASE_MYSQL_PASSWORD must be set to a non-placeholder value in production")

        origins = [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]
        if not origins:
            raise ValueError("CORS origins must be explicitly configured in production")
        for origin in origins:
            parsed = urlparse(origin)
            host = parsed.netloc.lower()
            if origin == "*" or parsed.scheme != "https" or host in {"", "localhost", "127.0.0.1", "your-domain.com"}:
                raise ValueError("CORS origins must be real HTTPS domains in production")

        if self.scheduler_enabled and not self.allow_production_external_actions:
            raise ValueError("ALLOW_PRODUCTION_EXTERNAL_ACTIONS must be true before enabling the scheduler in production")


def _load_dotenv_overrides() -> Dict[str, str]:
    """Read project-root .env so its values override YAML defaults.

    Needed because get_settings passes YAML values as constructor kwargs,
    which outrank pydantic-settings' own env_file loading.
    """
    if os.environ.get("XHS_DISABLE_DOTENV") == "1":
        return {}
    env_path = Path(__file__).resolve().parent.parent.parent.parent / ".env"
    if not env_path.exists():
        return {}
    fields = getattr(Settings, "model_fields", None) or getattr(Settings, "__fields__", {})
    field_by_env = {str(name).upper(): str(name) for name in fields}
    overrides: Dict[str, str] = {}
    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            field_name = field_by_env.get(key.strip().upper())
            if field_name:
                overrides[field_name] = value.strip().strip('"').strip("'")
    except OSError:
        return {}
    return overrides


def _load_environment_overrides() -> Dict[str, str]:
    fields = getattr(Settings, "model_fields", None) or getattr(Settings, "__fields__", {})
    overrides: Dict[str, str] = {}
    for field_name in fields:
        env_name = str(field_name).upper()
        if env_name in os.environ:
            overrides[str(field_name)] = os.environ[env_name]
    return overrides


@lru_cache
def get_settings() -> Settings:
    values = _load_yaml_config()
    values.update(_load_dotenv_overrides())
    values.update(_load_environment_overrides())
    return Settings(**values)

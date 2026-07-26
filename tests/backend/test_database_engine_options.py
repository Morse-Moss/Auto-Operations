from backend.app.core.database import _database_engine_options


def test_sqlite_engine_options_preserve_thread_configuration_only():
    assert _database_engine_options("sqlite:///data/local.db") == {
        "connect_args": {"check_same_thread": False},
    }


def test_server_database_engine_options_probe_and_recycle_connections():
    assert _database_engine_options("mysql+pymysql://user:password@db/app") == {
        "pool_pre_ping": True,
        "pool_recycle": 3600,
    }

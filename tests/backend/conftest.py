import pytest


@pytest.fixture(autouse=True)
def _isolate_local_dotenv(monkeypatch):
    """Keep tests hermetic: never let the developer's real .env leak into
    test-constructed settings (secret keys, fernet keys, etc.)."""
    monkeypatch.setenv("XHS_DISABLE_DOTENV", "1")

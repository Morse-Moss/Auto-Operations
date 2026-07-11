import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.rate_limit_service import clear_rate_limit_state


client = TestClient(app)
PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def reset_runtime_diagnostics_rate_limits():
    clear_rate_limit_state()
    yield
    clear_rate_limit_state()


def test_version_endpoint_exposes_runtime_identity():
    response = client.get("/api/version")

    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "spider-xhs"
    assert isinstance(payload["version"], str)
    assert payload["version"]


def test_request_id_middleware_returns_or_preserves_request_id():
    generated = client.get("/api/health")
    preserved = client.get("/api/health", headers={"X-Request-ID": "support-ticket-123"})

    assert generated.status_code == 200
    assert generated.headers["X-Request-ID"]
    assert preserved.headers["X-Request-ID"] == "support-ticket-123"


def test_alembic_logging_config_preserves_application_loggers(tmp_path):
    from alembic import command
    from alembic.config import Config

    runtime_logger = logging.getLogger("spider_xhs.runtime")
    runtime_logger.disabled = False
    config = Config(str(PROJECT_ROOT / "backend" / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{tmp_path / 'logging-state.db'}")

    command.upgrade(config, "head")

    assert runtime_logger.disabled is False


def test_client_error_endpoint_accepts_sanitized_diagnostics(caplog):
    caplog.set_level(logging.WARNING, logger="spider_xhs.runtime")
    response = client.post(
        "/api/client-errors",
        headers={"X-Request-ID": "frontend-error-1"},
        json={
            "event_type": "react_error_boundary",
            "message": "useLocation() may be used only in the context of a Router",
            "stack": "Error: useLocation() may be used only in the context of a Router",
            "url": "https://example.test/platform-select",
            "app_version": "test-version",
            "request_id": "frontend-error-1",
            "user_agent": "Test Browser",
            "extra": {"component_stack": "AppShell"},
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["accepted"] is True
    assert payload["request_id"] == "frontend-error-1"
    assert "client_error" in caplog.text
    assert "useLocation()" in caplog.text


def test_client_error_endpoint_rate_limits_repeated_reports():
    clear_rate_limit_state()
    try:
        responses = [
            client.post(
                "/api/client-errors",
                json={"event_type": "window_error", "message": f"browser failure {index}"},
            )
            for index in range(8)
        ]

        assert [response.status_code for response in responses] == [202] * 7 + [429]
        assert responses[-1].json()["detail"] == "Too many requests"
    finally:
        clear_rate_limit_state()


def test_client_error_endpoint_rejects_excess_metadata():
    response = client.post(
        "/api/client-errors",
        json={
            "event_type": "window_error",
            "message": "browser failure",
            "extra": {f"field_{index}": index for index in range(21)},
        },
    )

    assert response.status_code == 422


def test_client_error_endpoint_keeps_log_record_single_line(caplog):
    caplog.set_level(logging.WARNING, logger="spider_xhs.runtime")
    response = client.post(
        "/api/client-errors",
        json={
            "event_type": "window_error\nforged_event",
            "message": "first line\nforged message",
            "stack": "stack line one\r\nstack line two",
            "url": "https://example.test/path\nforged_url",
        },
    )

    assert response.status_code == 202
    record = next(record for record in caplog.records if record.name == "spider_xhs.runtime")
    rendered = record.getMessage()
    assert "\n" not in rendered
    assert "\r" not in rendered
    assert "first line forged message" in rendered

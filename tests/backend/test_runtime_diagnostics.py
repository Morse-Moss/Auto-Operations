from fastapi.testclient import TestClient

from backend.app.main import app


client = TestClient(app)


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


def test_client_error_endpoint_accepts_sanitized_diagnostics(caplog):
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

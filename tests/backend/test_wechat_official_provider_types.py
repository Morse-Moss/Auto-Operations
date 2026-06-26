from __future__ import annotations

import json

from backend.app.services.wechat_official_provider_types import WechatOfficialProviderDiagnostic, WechatOfficialProviderError


def test_provider_diagnostic_to_dict_is_json_serializable_and_redacts_sensitive_fields() -> None:
    diagnostic = WechatOfficialProviderDiagnostic(
        provider="redfox",
        stage="fetch_detail",
        severity="error",
        message="provider rejected the request",
        details={
            "api_key": "redfox-secret-key",
            "token": "provider-token",
            "cookie": "session=provider-cookie",
            "nested": {
                "Authorization": "Bearer provider-auth",
                "safe": "visible",
                "items": [{"password": "provider-password"}, {"url": "https://mp.weixin.qq.com/s/demo"}],
            },
        },
    )

    serialized = diagnostic.to_dict()
    json.dumps(serialized, ensure_ascii=False)
    serialized_text = json.dumps(serialized, ensure_ascii=False)

    assert serialized["provider"] == "redfox"
    assert serialized["stage"] == "fetch_detail"
    assert serialized["severity"] == "error"
    assert serialized["message"] == "provider rejected the request"
    assert "visible" in serialized_text
    assert "redfox-secret-key" not in serialized_text
    assert "provider-token" not in serialized_text
    assert "provider-cookie" not in serialized_text
    assert "provider-auth" not in serialized_text
    assert "provider-password" not in serialized_text
    assert serialized["details"]["api_key"] == "[REDACTED]"
    assert serialized["details"]["nested"]["Authorization"] == "[REDACTED]"


def test_provider_error_exposes_sanitized_diagnostic_payload() -> None:
    error = WechatOfficialProviderError(
        provider="redfox",
        stage="search",
        message="upstream failed",
        details={"secret": "do-not-leak", "request_id": "safe-id"},
    )

    payload = error.to_dict()
    payload_text = json.dumps(payload, ensure_ascii=False)

    assert str(error) == "upstream failed"
    assert payload["stage"] == "search"
    assert payload["details"]["request_id"] == "safe-id"
    assert payload["details"]["secret"] == "[REDACTED]"
    assert "do-not-leak" not in payload_text

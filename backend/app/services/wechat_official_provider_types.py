from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SENSITIVE_FIELD_NAMES = {
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "password",
    "secret",
    "token",
}
REDACTED_VALUE = "[REDACTED]"


def sanitize_provider_payload(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            text_key = str(key)
            if _is_sensitive_key(text_key):
                sanitized[text_key] = REDACTED_VALUE
            else:
                sanitized[text_key] = sanitize_provider_payload(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_provider_payload(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_provider_payload(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


@dataclass(frozen=True)
class WechatOfficialProviderDiagnostic:
    provider: str
    stage: str
    severity: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "stage": self.stage,
            "severity": self.severity,
            "message": self.message,
            "details": sanitize_provider_payload(self.details),
        }


class WechatOfficialProviderError(Exception):
    def __init__(self, *, provider: str, stage: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.diagnostic = WechatOfficialProviderDiagnostic(
            provider=provider,
            stage=stage,
            severity="error",
            message=message,
            details=details or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return self.diagnostic.to_dict()


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return normalized in SENSITIVE_FIELD_NAMES or any(part in SENSITIVE_FIELD_NAMES for part in normalized.split("_"))

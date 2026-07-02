from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from backend.app.platforms.contracts import (
    AdapterError,
    AdapterErrorCategory,
    CapabilityDecision,
    CapabilityRequestContext,
)

_SECRET_MARKERS = (
    "api_key",
    "api-key",
    "api/key",
    "apikey",
    "access-token",
    "authorization",
    "bearer",
    "cookie",
    "password",
    "secret",
    "session",
    "token",
    "web_session",
    "xsec_token",
)

_REFERENCE_PREFIXES = ("api_log:", "audit:", "task:", "diagnostic:")

_RAW_PAYLOAD_MARKERS = (
    "raw_json",
    "platform_message",
)


@dataclass(frozen=True)
class StandardDiagnostic:
    platform_id: str
    capability_key: str
    stage: str
    severity: str
    recoverable: bool
    category: str
    user_message: str
    next_action: str
    raw_reference: str | None
    correlation_id: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "platform_id": self.platform_id,
            "capability_key": self.capability_key,
            "stage": self.stage,
            "severity": self.severity,
            "recoverable": self.recoverable,
            "category": self.category,
            "user_message": self.user_message,
            "next_action": self.next_action,
            "raw_reference": self.raw_reference,
            "correlation_id": self.correlation_id,
        }


_CATEGORY_DEFAULTS: dict[str, dict[str, Any]] = {
    "auth_expired": {
        "severity": "blocked",
        "recoverable": True,
        "user_message": "账号凭证已过期，动作未执行。",
        "next_action": "重新登录或更新 Cookie 后再重试。",
    },
    "rate_limited": {
        "severity": "warning",
        "recoverable": True,
        "user_message": "平台访问频率受限，动作已暂停。",
        "next_action": "稍后重试，或降低任务频率。",
    },
    "signature_failed": {
        "severity": "error",
        "recoverable": False,
        "user_message": "平台签名或接口可能已变化，动作未执行。",
        "next_action": "暂停自动动作，检查平台适配器或签名能力。",
    },
    "risk_blocked": {
        "severity": "blocked",
        "recoverable": True,
        "user_message": "动作被安全策略阻断，未执行真实平台操作。",
        "next_action": "确认平台能力和动作级授权后再重试。",
    },
    "validation": {
        "severity": "warning",
        "recoverable": True,
        "user_message": "输入未通过校验，动作未执行。",
        "next_action": "修正输入后重新执行。",
    },
    "unknown": {
        "severity": "error",
        "recoverable": False,
        "user_message": "动作执行失败，原因未知。",
        "next_action": "查看任务详情或联系维护者排查。",
    },
}


_ADAPTER_CATEGORY_MAP: dict[str, str] = {
    "auth_expired": "auth_expired",
    "credential_invalid": "auth_expired",
    "rate_limited": "rate_limited",
    "signature_failed": "signature_failed",
    "invalid_request": "validation",
    "risk_blocked": "risk_blocked",
    "blocked_capability": "risk_blocked",
    "validation": "validation",
}


def sanitize_raw_reference(raw_reference: Any) -> str | None:
    if raw_reference is None:
        return None
    if not isinstance(raw_reference, str):
        return None

    value = raw_reference.strip()
    if not value:
        return None

    lowered = value.lower()
    if any(marker in lowered for marker in _RAW_PAYLOAD_MARKERS):
        return None
    if value.startswith(("{", "[")):
        return None

    parsed = urlsplit(value)
    if parsed.scheme and parsed.netloc:
        if parsed.scheme not in {"http", "https"}:
            return None
        if parsed.username or parsed.password:
            return None
        path_lower = parsed.path.lower()
        if any(marker in path_lower for marker in _SECRET_MARKERS):
            return None
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))

    if any(marker in lowered for marker in _SECRET_MARKERS):
        return None
    if value.startswith(_REFERENCE_PREFIXES):
        return value[:256]
    return None


def standard_diagnostic(
    category: AdapterErrorCategory | str,
    *,
    platform_id: str,
    capability_key: str,
    stage: str,
    correlation_id: str,
    user_message: str | None = None,
    raw_reference: Any = None,
    severity: str | None = None,
    recoverable: bool | None = None,
) -> StandardDiagnostic:
    normalized_category = str(category) if str(category) in _CATEGORY_DEFAULTS else "unknown"
    defaults = _CATEGORY_DEFAULTS[normalized_category]
    return StandardDiagnostic(
        platform_id=platform_id,
        capability_key=capability_key,
        stage=stage,
        severity=severity or str(defaults["severity"]),
        recoverable=bool(defaults["recoverable"] if recoverable is None else recoverable),
        category=normalized_category,
        user_message=user_message or str(defaults["user_message"]),
        next_action=str(defaults["next_action"]),
        raw_reference=sanitize_raw_reference(raw_reference),
        correlation_id=correlation_id,
    )


def diagnostic_from_adapter_error(
    error: AdapterError,
    *,
    platform_id: str,
    capability_key: str,
    stage: str,
    correlation_id: str,
) -> StandardDiagnostic:
    category = _ADAPTER_CATEGORY_MAP.get(error.category, "unknown")
    return standard_diagnostic(
        category,
        platform_id=platform_id,
        capability_key=capability_key,
        stage=stage,
        correlation_id=correlation_id,
        user_message=error.user_message,
        raw_reference=error.raw_reference,
    )


def diagnostic_from_capability_decision(
    decision: CapabilityDecision,
    *,
    context: CapabilityRequestContext,
    stage: str,
) -> StandardDiagnostic:
    if decision.allowed:
        return standard_diagnostic(
            "unknown",
            platform_id=context.platform_id,
            capability_key=context.capability_key,
            stage=stage,
            correlation_id=context.correlation_id,
            user_message=decision.user_message,
            raw_reference=decision.audit_reference,
        )

    reason = decision.blocked_reason or ""
    category = "risk_blocked"
    if reason in {"account_required", "account_sub_type_mismatch", "account_platform_mismatch"}:
        category = "auth_expired"
    elif reason in {"request_context_mismatch", "capability_not_found"}:
        category = "validation"

    return standard_diagnostic(
        category,
        platform_id=context.platform_id,
        capability_key=context.capability_key,
        stage=stage,
        correlation_id=context.correlation_id,
        user_message=decision.user_message,
        raw_reference=decision.audit_reference,
    )


def validation_diagnostic(
    *,
    platform_id: str,
    capability_key: str,
    stage: str,
    correlation_id: str,
    user_message: str,
    raw_reference: Any = None,
) -> StandardDiagnostic:
    return standard_diagnostic(
        "validation",
        platform_id=platform_id,
        capability_key=capability_key,
        stage=stage,
        correlation_id=correlation_id,
        user_message=user_message,
        raw_reference=raw_reference,
    )


def readiness_diagnostic(
    *,
    platform_id: str,
    check_key: str,
    user_message: str,
    stage: str = "readiness",
    check_severity: str = "follow_up",
) -> StandardDiagnostic:
    is_blocker = check_severity == "blocker"
    return standard_diagnostic(
        "validation",
        platform_id=platform_id,
        capability_key="readiness.second_platform",
        stage=stage,
        correlation_id=check_key,
        user_message=user_message,
        raw_reference=f"diagnostic:{check_key}",
        severity=("blocked" if is_blocker else "warning"),
        recoverable=not is_blocker,
    )


def skipped_save_diagnostic(
    *,
    platform_id: str,
    skipped_item: dict[str, Any],
    correlation_id: str,
) -> StandardDiagnostic:
    kind = str(skipped_item.get("save_diagnostic_kind") or "save_skipped_low_quality")
    category = "rate_limited" if skipped_item.get("quality_status") == "rate_limited" or skipped_item.get("diagnostic_kind") == "xhs_rate_limited" else "validation"
    return standard_diagnostic(
        category,
        platform_id=platform_id,
        capability_key="content.save",
        stage="save",
        correlation_id=correlation_id,
        user_message=str(skipped_item.get("user_message") or "内容质量不足，已跳过入库。"),
        raw_reference=f"diagnostic:{kind}",
        recoverable=bool(skipped_item.get("recoverable", False)),
    )

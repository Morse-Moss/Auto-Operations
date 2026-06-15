from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Generic, Literal, Protocol, TypeVar, runtime_checkable

from backend.app.core.platforms import PlatformCapability, PlatformMeta


RequestSource = Literal["manual", "scheduler", "auto_task", "api", "retry"]
AdapterErrorCategory = Literal[
    "auth_expired",
    "credential_invalid",
    "rate_limited",
    "network",
    "signature_failed",
    "invalid_request",
    "upstream_changed",
    "not_found",
    "risk_blocked",
    "blocked_capability",
    "validation",
    "unknown",
]

T = TypeVar("T")


@dataclass(frozen=True)
class AccountSafetyResult:
    passed: bool
    reason: str | None = None
    user_message: str | None = None


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int | None = None
    cooldown_until: datetime | None = None
    should_skip_current_item: bool = False
    should_pause_target: bool = False
    user_message: str | None = None


@dataclass(frozen=True)
class DiagnosticEvent:
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PlatformAccountRef:
    account_id: int
    platform_id: str
    account_kind: str | None = None
    sub_type: str | None = None
    display_role: str | None = None
    auth_mode: str = "cookie"
    status: str = "active"
    credential_status: str = "valid"
    health_status: str = "healthy"
    profile_summary: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConfirmationToken:
    capability_key: str
    platform_id: str
    account_id: int
    action_hash: str
    payload_summary_hash: str
    expires_at: datetime
    issued_by: int
    single_use: bool
    confirmed_risk_level: str
    request_source: RequestSource | None = None


@dataclass(frozen=True)
class CapabilityRequestContext:
    user_id: int
    platform_id: str
    capability_key: str
    account_ref: PlatformAccountRef | None
    dry_run: bool
    confirmation_token: ConfirmationToken | None
    request_source: RequestSource
    correlation_id: str
    task_id: int | None = None
    idempotency_key: str | None = None
    action_hash: str | None = None
    payload_summary_hash: str | None = None
    required_account_sub_type: str | None = None
    allow_partial: bool = False


@dataclass(frozen=True)
class CapabilityDecision:
    allowed: bool
    blocked_reason: str | None
    risk_level: str
    requires_confirmation: bool
    confirmation_required_fields: list[str]
    effective_dry_run: bool
    account_safety_result: AccountSafetyResult | None
    rate_limit_result: RateLimitDecision | None
    user_message: str
    audit_reference: str | None = None


@dataclass(frozen=True)
class AdapterError:
    category: AdapterErrorCategory
    user_message: str
    platform_message: str | None
    retryable: bool
    rate_limited: bool
    credential_invalid: bool
    raw_reference: str | None
    next_action: str | None


@dataclass(frozen=True)
class AdapterResultEnvelope(Generic[T]):
    success: bool
    data: T | None
    message: str
    diagnostics: list[DiagnosticEvent]
    raw_reference: str | None
    retry_after_seconds: int | None
    rate_limit: RateLimitDecision | None
    error: AdapterError | None
    correlation_id: str


class RegistryProvider(Protocol):
    def get_meta(self, platform_id: str) -> PlatformMeta: ...

    def get_capability(self, platform_id: str, capability_key: str) -> PlatformCapability: ...

    def list_platforms(self) -> list[PlatformMeta]: ...

    def assert_enabled(self, platform_id: str) -> None: ...


@runtime_checkable
class PlatformAdapter(Protocol):
    supported_capabilities: set[str]


class CapabilityPolicyError(RuntimeError):
    def __init__(self, decision: CapabilityDecision) -> None:
        super().__init__(decision.user_message)
        self.decision = decision

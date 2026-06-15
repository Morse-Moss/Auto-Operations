# Platform Adapter Contract Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Stage A backend-only Platform Adapter Contract skeleton with fail-closed CapabilityGate and adapter resolver tests, without touching existing XHS execution paths.

**Architecture:** Keep `E:/小红书/backend/app/core/platforms.py` as the registry fact source and add a pure `backend.app.platforms` contract/policy/resolver layer. The policy reads `release_stage`, `enabled`, `adapter_key`, `capability.status`, `capability.risk`, and `capability.requires_confirmation`; the resolver enforces policy before returning any fake adapter and never lets adapter support upgrade registry policy.

**Tech Stack:** Python 3.10+, dataclasses, Protocol types, pytest. No FastAPI route changes, no database, no frontend, no XHS SDK/signature imports.

---

## Scope Firewall

Allowed implementation files for this plan:
- `E:/小红书/backend/app/platforms/contracts.py`
- `E:/小红书/backend/app/platforms/policy.py`
- `E:/小红书/backend/app/platforms/resolver.py`
- `E:/小红书/tests/backend/test_platform_capability_gate.py`
- `E:/小红书/tests/backend/test_platform_adapter_resolver.py`

Allowed existing regression file to run, not edit:
- `E:/小红书/tests/backend/test_platforms.py`

Allowed implementation directory operation:
- Create directory `E:/小红书/backend/app/platforms/` if it does not exist.
- Do not create `E:/小红书/backend/app/platforms/__init__.py` unless imports fail on the target Python runtime; Python namespace package import should be sufficient.

Forbidden:
- No edits under `E:/小红书/apis/`, `E:/小红书/xhs_utils/`, or `E:/小红书/static/`.
- No edits to `E:/小红书/backend/app/adapters/xhs/`.
- No edits to existing XHS routes under `E:/小红书/backend/app/api/platforms/xhs/`.
- No edits to `E:/小红书/backend/app/api/publish.py`, scheduler, auto-task, Huitun, database model, Alembic, or frontend files.
- No real platform calls, real cookies, real tokens, real publish, real reply execution, browser automation, or network calls.
- No `git add`, `git commit`, `git push`, `git checkout`, `git restore`, broad formatting, or cleanup of unrelated dirty files.

Current workspace caveat from research:
- Treat existing dirty files as unrelated upstream/user work: `E:/小红书/CLAUDE.md`, `E:/小红书/frontend/src/components/layout/platform-selector.tsx`, `E:/小红书/frontend/src/lib/platforms.ts`, `E:/小红书/frontend/src/types/index.ts`, and untracked spec `E:/小红书/docs/superpowers/specs/2026-06-09-platform-adapter-contract-design.md`.
- Do not stage, revert, format, or modify them during Stage A.

## Definitions This Plan Locks In

Stable blocked reasons to use in tests and implementation:
- `platform_not_found`
- `platform_planned`
- `platform_unavailable`
- `platform_disabled`
- `adapter_key_missing`
- `capability_not_found`
- `capability_planned`
- `capability_unavailable`
- `capability_blocked`
- `capability_partial_requires_explicit_path`
- `account_platform_mismatch`
- `account_required`
- `account_sub_type_mismatch`
- `confirmation_required`
- `confirmation_platform_mismatch`
- `confirmation_capability_mismatch`
- `confirmation_user_mismatch`
- `confirmation_account_required`
- `confirmation_account_mismatch`
- `confirmation_action_mismatch`
- `confirmation_payload_mismatch`
- `confirmation_source_mismatch`
- `confirmation_expired`
- `confirmation_single_use_required`
- `confirmation_risk_mismatch`
- `request_context_mismatch`
- `adapter_not_registered`
- `adapter_capability_unsupported`

Stage A partial-capability rule:
- `capability.status == "partial"` is blocked by default.
- It is only allowed when `CapabilityRequestContext.allow_partial is True`, and then it still must pass account and confirmation checks.
- This is a skeleton representation of future explicit partial-path rules; it must not imply production-grade publish authorization.

Stage A confirmation rule:
- A capability requires confirmation when `capability.requires_confirmation is True` or `capability.risk == "high"`.
- A matching `ConfirmationToken` must bind `platform_id`, `capability_key`, `issued_by/user_id`, `account_id`, `action_hash`, `payload_summary_hash`, unexpired `expires_at`, exact `request_source`, `single_use=True`, and exact `confirmed_risk_level`.
- `single_use=False` must block with stable reason `confirmation_single_use_required`, not the broader `confirmation_risk_mismatch`.
- ConfirmationToken is request-level skeleton only in Stage A; it is not sufficient for real publish authorization.

Post-review safety amendment:
- The stable rules above and the current source files supersede any earlier scaffold snippets in this plan. Do not re-apply stale snippets that allow unknown `release_stage`, unknown capability `status`/`risk`, missing or invalid `request_source`, or `single_use=False` confirmation tokens.

## Task 0: Preflight and Existing Registry Regression

**Files:**
- Read only: `E:/小红书/backend/app/core/platforms.py`
- Read only: `E:/小红书/tests/backend/test_platforms.py`
- Read only: `E:/小红书/docs/superpowers/specs/2026-06-09-platform-adapter-contract-design.md`

- [ ] **Step 1: Confirm workspace state without modifying anything**

Run:

```bash
git -C E:/小红书 status --short
```

Expected:
- May show existing unrelated dirty files from the research output.
- Do not run `git add`, `git checkout`, `git restore`, or formatting commands.

- [ ] **Step 2: Run existing platform registry regression before Stage A edits**

Run:

```bash
cd E:/小红书 && py -3 -m pytest tests/backend/test_platforms.py -q
```

Expected:
- PASS.
- If this fails before Stage A edits, stop and report the pre-existing failure. Do not fix unrelated registry/API behavior as part of Stage A.

## Task 1: CapabilityGate Contract DTOs and Fail-Closed Policy

**Files:**
- Create: `E:/小红书/tests/backend/test_platform_capability_gate.py`
- Create: `E:/小红书/backend/app/platforms/contracts.py`
- Create: `E:/小红书/backend/app/platforms/policy.py`

- [ ] **Step 1: Write the failing CapabilityGate tests**

Create `E:/小红书/tests/backend/test_platform_capability_gate.py` with this exact content:

```python
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone

from backend.app.core.platforms import get_platform
from backend.app.platforms.contracts import (
    CapabilityRequestContext,
    ConfirmationToken,
    PlatformAccountRef,
)
from backend.app.platforms.policy import PlatformPolicyService


NOW = datetime(2026, 6, 9, 12, 0, 0, tzinfo=timezone.utc)


@dataclass(frozen=True)
class FakeCapability:
    key: str
    status: str = "available"
    risk: str = "medium"
    requires_confirmation: bool = False
    notes: str = "fake capability"


@dataclass(frozen=True)
class FakeMeta:
    id: str
    enabled: bool = True
    release_stage: str = "enabled"
    adapter_key: str | None = "fake"
    capabilities: list[FakeCapability] = field(default_factory=list)


class FakeRegistryProvider:
    def __init__(self, platforms: list[FakeMeta]) -> None:
        self._platforms = {platform.id: platform for platform in platforms}

    def get_meta(self, platform_id: str):
        try:
            return self._platforms[platform_id]
        except KeyError:
            raise KeyError(platform_id)

    def get_capability(self, platform_id: str, capability_key: str):
        platform = self.get_meta(platform_id)
        for capability in platform.capabilities:
            if capability.key == capability_key:
                return capability
        raise KeyError(capability_key)

    def list_platforms(self):
        return list(self._platforms.values())

    def assert_enabled(self, platform_id: str) -> None:
        platform = self.get_meta(platform_id)
        if not platform.enabled:
            raise KeyError(platform_id)


def make_service(platforms: list[FakeMeta] | None = None) -> PlatformPolicyService:
    registry = FakeRegistryProvider(platforms or []) if platforms is not None else None
    return PlatformPolicyService(registry_provider=registry, now_provider=lambda: NOW)


def make_account(
    platform_id: str = "xhs",
    sub_type: str | None = "main",
    account_id: int = 101,
) -> PlatformAccountRef:
    return PlatformAccountRef(
        account_id=account_id,
        platform_id=platform_id,
        account_kind="content_account",
        sub_type=sub_type,
        display_role="测试账号",
        auth_mode="cookie",
        status="active",
        credential_status="valid",
        health_status="healthy",
        profile_summary={"nickname": "fake"},
    )


def make_token(
    *,
    platform_id: str = "xhs",
    capability_key: str = "account.login_cookie",
    account_id: int = 101,
    action_hash: str = "action-1",
    payload_summary_hash: str = "payload-1",
    expires_at: datetime = NOW + timedelta(minutes=10),
    issued_by: int = 7,
    confirmed_risk_level: str = "high",
    request_source: str | None = "manual",
) -> ConfirmationToken:
    return ConfirmationToken(
        capability_key=capability_key,
        platform_id=platform_id,
        account_id=account_id,
        action_hash=action_hash,
        payload_summary_hash=payload_summary_hash,
        expires_at=expires_at,
        issued_by=issued_by,
        single_use=True,
        confirmed_risk_level=confirmed_risk_level,
        request_source=request_source,
    )


def make_context(
    *,
    platform_id: str = "xhs",
    capability_key: str = "content.discover",
    account_ref: PlatformAccountRef | None = None,
    confirmation_token: ConfirmationToken | None = None,
    request_source: str = "manual",
    action_hash: str | None = "action-1",
    payload_summary_hash: str | None = "payload-1",
    required_account_sub_type: str | None = None,
    allow_partial: bool = False,
) -> CapabilityRequestContext:
    return CapabilityRequestContext(
        user_id=7,
        platform_id=platform_id,
        capability_key=capability_key,
        account_ref=account_ref,
        dry_run=True,
        confirmation_token=confirmation_token,
        request_source=request_source,
        correlation_id="corr-test",
        task_id=None,
        idempotency_key="idem-test",
        action_hash=action_hash,
        payload_summary_hash=payload_summary_hash,
        required_account_sub_type=required_account_sub_type,
        allow_partial=allow_partial,
    )


def fake_platform(
    *,
    platform_id: str = "fake",
    enabled: bool = True,
    release_stage: str = "enabled",
    adapter_key: str | None = "fake",
    capabilities: list[FakeCapability] | None = None,
) -> FakeMeta:
    return FakeMeta(
        id=platform_id,
        enabled=enabled,
        release_stage=release_stage,
        adapter_key=adapter_key,
        capabilities=capabilities or [FakeCapability("content.discover")],
    )


def test_capability_gate_blocks_unknown_platform_with_user_readable_reason():
    decision = make_service([]).evaluate(make_context(platform_id="unknown"))

    assert decision.allowed is False
    assert decision.blocked_reason == "platform_not_found"
    assert decision.user_message == "平台不存在或尚未接入，动作未执行。"


def test_capability_gate_blocks_planned_platform_before_other_checks():
    decision = make_service().evaluate(
        make_context(platform_id="douyin", capability_key="content.discover")
    )

    assert decision.allowed is False
    assert decision.blocked_reason == "platform_planned"
    assert "Coming Soon" in decision.user_message


def test_capability_gate_blocks_disabled_non_planned_platform():
    platform = fake_platform(platform_id="disabled_fake", enabled=False, release_stage="enabled")
    decision = make_service([platform]).evaluate(
        make_context(platform_id="disabled_fake", capability_key="content.discover")
    )

    assert decision.allowed is False
    assert decision.blocked_reason == "platform_disabled"


def test_capability_gate_blocks_platform_missing_adapter_key():
    platform = fake_platform(platform_id="no_adapter_key", adapter_key=None)
    decision = make_service([platform]).evaluate(
        make_context(platform_id="no_adapter_key", capability_key="content.discover")
    )

    assert decision.allowed is False
    assert decision.blocked_reason == "adapter_key_missing"


def test_capability_gate_blocks_missing_capability():
    platform = fake_platform(platform_id="fake", capabilities=[])
    decision = make_service([platform]).evaluate(
        make_context(platform_id="fake", capability_key="content.unknown")
    )

    assert decision.allowed is False
    assert decision.blocked_reason == "capability_not_found"


def test_capability_gate_blocks_planned_blocked_and_unavailable_capabilities():
    cases = [
        ("planned", "capability_planned"),
        ("blocked", "capability_blocked"),
        ("unavailable", "capability_unavailable"),
    ]

    for status, expected_reason in cases:
        platform = fake_platform(
            platform_id=f"fake_{status}",
            capabilities=[FakeCapability("content.discover", status=status)],
        )
        decision = make_service([platform]).evaluate(
            make_context(platform_id=f"fake_{status}", capability_key="content.discover")
        )

        assert decision.allowed is False
        assert decision.blocked_reason == expected_reason


def test_xhs_reply_execute_stays_blocked_high_risk_and_requires_confirmation():
    xhs = get_platform("xhs")
    reply_execute = next(
        capability
        for capability in xhs.capabilities
        if capability.key.value == "engagement.reply_execute"
    )

    decision = make_service().evaluate(
        make_context(
            platform_id="xhs",
            capability_key="engagement.reply_execute",
            account_ref=make_account(),
        )
    )

    assert reply_execute.status.value == "blocked"
    assert reply_execute.risk.value == "high"
    assert reply_execute.requires_confirmation is True
    assert decision.allowed is False
    assert decision.blocked_reason == "capability_blocked"


def test_partial_capability_is_blocked_by_default_and_allowed_only_for_explicit_partial_path():
    blocked = make_service().evaluate(
        make_context(
            platform_id="xhs",
            capability_key="engagement.comment_read",
            account_ref=make_account(),
        )
    )
    allowed = make_service().evaluate(
        make_context(
            platform_id="xhs",
            capability_key="engagement.comment_read",
            account_ref=make_account(),
            allow_partial=True,
        )
    )

    assert blocked.allowed is False
    assert blocked.blocked_reason == "capability_partial_requires_explicit_path"
    assert allowed.allowed is True
    assert allowed.blocked_reason is None


def test_high_risk_capability_requiring_confirmation_is_blocked_when_token_is_missing():
    decision = make_service().evaluate(
        make_context(
            platform_id="xhs",
            capability_key="account.login_cookie",
            account_ref=make_account(),
            confirmation_token=None,
        )
    )

    assert decision.allowed is False
    assert decision.blocked_reason == "confirmation_required"
    assert decision.requires_confirmation is True
    assert decision.confirmation_required_fields == [
        "platform_id",
        "capability_key",
        "account_id",
        "action_hash",
        "payload_summary_hash",
        "expires_at",
        "confirmed_risk_level",
    ]


def test_high_risk_capability_with_matching_confirmation_token_is_allowed():
    account_ref = make_account()
    token = make_token(account_id=account_ref.account_id)

    decision = make_service().evaluate(
        make_context(
            platform_id="xhs",
            capability_key="account.login_cookie",
            account_ref=account_ref,
            confirmation_token=token,
            action_hash="action-1",
            payload_summary_hash="payload-1",
        )
    )

    assert decision.allowed is True
    assert decision.blocked_reason is None
    assert decision.requires_confirmation is True
    assert decision.risk_level == "high"


def test_high_risk_confirmation_token_must_match_request_binding_and_not_be_expired():
    account_ref = make_account()
    base_token = make_token(account_id=account_ref.account_id)
    cases = [
        (replace(base_token, platform_id="douyin"), "confirmation_platform_mismatch"),
        (replace(base_token, capability_key="publish.real_publish"), "confirmation_capability_mismatch"),
        (replace(base_token, issued_by=8), "confirmation_user_mismatch"),
        (replace(base_token, account_id=202), "confirmation_account_mismatch"),
        (replace(base_token, action_hash="other-action"), "confirmation_action_mismatch"),
        (replace(base_token, payload_summary_hash="other-payload"), "confirmation_payload_mismatch"),
        (replace(base_token, request_source="scheduler"), "confirmation_source_mismatch"),
        (replace(base_token, expires_at=NOW - timedelta(seconds=1)), "confirmation_expired"),
        (replace(base_token, confirmed_risk_level="medium"), "confirmation_risk_mismatch"),
    ]

    for token, expected_reason in cases:
        decision = make_service().evaluate(
            make_context(
                platform_id="xhs",
                capability_key="account.login_cookie",
                account_ref=account_ref,
                confirmation_token=token,
                request_source="manual",
                action_hash="action-1",
                payload_summary_hash="payload-1",
            )
        )

        assert decision.allowed is False
        assert decision.blocked_reason == expected_reason


def test_account_ref_platform_id_mismatch_is_blocked():
    decision = make_service().evaluate(
        make_context(
            platform_id="xhs",
            capability_key="content.discover",
            account_ref=make_account(platform_id="douyin"),
        )
    )

    assert decision.allowed is False
    assert decision.blocked_reason == "account_platform_mismatch"


def test_account_ref_sub_type_mismatch_is_blocked_when_context_requires_sub_type():
    decision = make_service().evaluate(
        make_context(
            platform_id="xhs",
            capability_key="content.discover",
            account_ref=make_account(platform_id="xhs", sub_type="main"),
            required_account_sub_type="creator",
        )
    )

    assert decision.allowed is False
    assert decision.blocked_reason == "account_sub_type_mismatch"
```

- [ ] **Step 2: Run the CapabilityGate test file and verify RED**

Run:

```bash
cd E:/小红书 && py -3 -m pytest tests/backend/test_platform_capability_gate.py -q
```

Expected:
- FAIL before implementation.
- Expected import failure is acceptable: `ModuleNotFoundError: No module named 'backend.app.platforms'` or `No module named 'backend.app.platforms.contracts'`.
- If it passes before implementation, stop: another worker already implemented this scope, so review instead of duplicating.

- [ ] **Step 3: Create the platform contract directory**

Run:

```bash
mkdir -p E:/小红书/backend/app/platforms
```

Expected:
- Directory exists.
- Do not add `__init__.py` unless the RED test proves namespace-package import fails after files exist.

- [ ] **Step 4: Implement `contracts.py`**

Create `E:/小红书/backend/app/platforms/contracts.py` with this exact content:

```python
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
```

- [ ] **Step 5: Implement `policy.py`**

Create `E:/小红书/backend/app/platforms/policy.py` with this exact content:

```python
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from backend.app.core.platforms import get_platform, get_platforms
from backend.app.platforms.contracts import (
    AccountSafetyResult,
    CapabilityDecision,
    CapabilityPolicyError,
    CapabilityRequestContext,
    RegistryProvider,
)


CONFIRMATION_REQUIRED_FIELDS = [
    "platform_id",
    "capability_key",
    "account_id",
    "action_hash",
    "payload_summary_hash",
    "expires_at",
    "confirmed_risk_level",
]


def _value(item: Any) -> str:
    if hasattr(item, "value"):
        return str(item.value)
    return str(item)


def _capability_key(capability: Any) -> str:
    return _value(getattr(capability, "key"))


class CoreRegistryProvider:
    def get_meta(self, platform_id: str):
        return get_platform(platform_id)

    def get_capability(self, platform_id: str, capability_key: str):
        platform = self.get_meta(platform_id)
        for capability in platform.capabilities:
            if _capability_key(capability) == capability_key:
                return capability
        raise KeyError(capability_key)

    def list_platforms(self):
        return get_platforms()

    def assert_enabled(self, platform_id: str) -> None:
        platform = self.get_meta(platform_id)
        if not platform.enabled:
            raise KeyError(platform_id)


class PlatformPolicyService:
    def __init__(
        self,
        registry_provider: RegistryProvider | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.registry_provider = registry_provider or CoreRegistryProvider()
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def evaluate(self, context: CapabilityRequestContext) -> CapabilityDecision:
        try:
            meta = self.registry_provider.get_meta(context.platform_id)
        except KeyError:
            return self._blocked(
                context,
                reason="platform_not_found",
                message="平台不存在或尚未接入，动作未执行。",
            )

        release_stage = _value(getattr(meta, "release_stage", "unknown"))
        if release_stage == "planned":
            return self._blocked(
                context,
                reason="platform_planned",
                message="平台仍处于 Coming Soon 状态，动作未执行。",
            )
        if release_stage == "unavailable":
            return self._blocked(
                context,
                reason="platform_unavailable",
                message="平台当前不可用，动作未执行。",
            )
        if not bool(getattr(meta, "enabled", False)):
            return self._blocked(
                context,
                reason="platform_disabled",
                message="平台未启用，动作未执行。",
            )
        if not getattr(meta, "adapter_key", None):
            return self._blocked(
                context,
                reason="adapter_key_missing",
                message="平台缺少适配器配置，动作未执行。",
            )

        try:
            capability = self.registry_provider.get_capability(
                context.platform_id, context.capability_key
            )
        except KeyError:
            return self._blocked(
                context,
                reason="capability_not_found",
                message="平台未声明该能力，动作未执行。",
            )

        status = _value(getattr(capability, "status", "unknown"))
        risk_level = _value(getattr(capability, "risk", "unknown"))
        requires_confirmation = bool(
            getattr(capability, "requires_confirmation", False)
        ) or risk_level == "high"

        if status == "planned":
            return self._blocked(
                context,
                reason="capability_planned",
                message="该能力尚未开放，动作未执行。",
                risk_level=risk_level,
                requires_confirmation=requires_confirmation,
            )
        if status == "unavailable":
            return self._blocked(
                context,
                reason="capability_unavailable",
                message="该能力当前不可用，动作未执行。",
                risk_level=risk_level,
                requires_confirmation=requires_confirmation,
            )
        if status == "blocked":
            return self._blocked(
                context,
                reason="capability_blocked",
                message="该能力已被安全策略阻断，动作未执行。",
                risk_level=risk_level,
                requires_confirmation=requires_confirmation,
            )
        if status == "partial" and not context.allow_partial:
            return self._blocked(
                context,
                reason="capability_partial_requires_explicit_path",
                message="该能力只允许明确的受限路径，当前请求未声明 partial path，动作未执行。",
                risk_level=risk_level,
                requires_confirmation=requires_confirmation,
            )

        account_decision = self._evaluate_account(
            context,
            risk_level=risk_level,
            requires_confirmation=requires_confirmation,
        )
        if account_decision is not None:
            return account_decision

        if requires_confirmation:
            confirmation_decision = self._evaluate_confirmation(
                context,
                risk_level=risk_level,
                requires_confirmation=requires_confirmation,
            )
            if confirmation_decision is not None:
                return confirmation_decision

        return CapabilityDecision(
            allowed=True,
            blocked_reason=None,
            risk_level=risk_level,
            requires_confirmation=requires_confirmation,
            confirmation_required_fields=[],
            effective_dry_run=context.dry_run,
            account_safety_result=(
                AccountSafetyResult(passed=True, user_message="账号检查通过。")
                if context.account_ref is not None
                else None
            ),
            rate_limit_result=None,
            user_message="能力门禁已放行。",
            audit_reference=context.correlation_id,
        )

    def enforce(self, context: CapabilityRequestContext) -> CapabilityDecision:
        decision = self.evaluate(context)
        if not decision.allowed:
            raise CapabilityPolicyError(decision)
        return decision

    def _evaluate_account(
        self,
        context: CapabilityRequestContext,
        *,
        risk_level: str,
        requires_confirmation: bool,
    ) -> CapabilityDecision | None:
        account_ref = context.account_ref
        if account_ref is not None and account_ref.platform_id != context.platform_id:
            return self._blocked(
                context,
                reason="account_platform_mismatch",
                message="账号归属平台与请求平台不一致，动作未执行。",
                risk_level=risk_level,
                requires_confirmation=requires_confirmation,
            )

        if context.required_account_sub_type is None:
            return None
        if account_ref is None:
            return self._blocked(
                context,
                reason="account_required",
                message="该能力需要绑定账号后才能执行，动作未执行。",
                risk_level=risk_level,
                requires_confirmation=requires_confirmation,
            )
        if account_ref.sub_type != context.required_account_sub_type:
            return self._blocked(
                context,
                reason="account_sub_type_mismatch",
                message="账号类型不满足该能力要求，动作未执行。",
                risk_level=risk_level,
                requires_confirmation=requires_confirmation,
            )
        return None

    def _evaluate_confirmation(
        self,
        context: CapabilityRequestContext,
        *,
        risk_level: str,
        requires_confirmation: bool,
    ) -> CapabilityDecision | None:
        token = context.confirmation_token
        if token is None:
            return self._blocked(
                context,
                reason="confirmation_required",
                message="该高风险能力需要动作级确认，动作未执行。",
                risk_level=risk_level,
                requires_confirmation=requires_confirmation,
                confirmation_required_fields=CONFIRMATION_REQUIRED_FIELDS,
            )
        if token.platform_id != context.platform_id:
            return self._confirmation_blocked(
                context, "confirmation_platform_mismatch", risk_level, requires_confirmation
            )
        if token.capability_key != context.capability_key:
            return self._confirmation_blocked(
                context, "confirmation_capability_mismatch", risk_level, requires_confirmation
            )
        if token.issued_by != context.user_id:
            return self._confirmation_blocked(
                context, "confirmation_user_mismatch", risk_level, requires_confirmation
            )
        if context.account_ref is None:
            return self._confirmation_blocked(
                context, "confirmation_account_required", risk_level, requires_confirmation
            )
        if token.account_id != context.account_ref.account_id:
            return self._confirmation_blocked(
                context, "confirmation_account_mismatch", risk_level, requires_confirmation
            )
        if not context.action_hash or token.action_hash != context.action_hash:
            return self._confirmation_blocked(
                context, "confirmation_action_mismatch", risk_level, requires_confirmation
            )
        if (
            not context.payload_summary_hash
            or token.payload_summary_hash != context.payload_summary_hash
        ):
            return self._confirmation_blocked(
                context, "confirmation_payload_mismatch", risk_level, requires_confirmation
            )
        if token.request_source is not None and token.request_source != context.request_source:
            return self._confirmation_blocked(
                context, "confirmation_source_mismatch", risk_level, requires_confirmation
            )
        if self._is_expired(token.expires_at):
            return self._confirmation_blocked(
                context, "confirmation_expired", risk_level, requires_confirmation
            )
        if token.confirmed_risk_level != risk_level:
            return self._confirmation_blocked(
                context, "confirmation_risk_mismatch", risk_level, requires_confirmation
            )
        return None

    def _is_expired(self, expires_at: datetime) -> bool:
        now = self._now_provider()
        if expires_at.tzinfo is None and now.tzinfo is not None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if now.tzinfo is None and expires_at.tzinfo is not None:
            now = now.replace(tzinfo=timezone.utc)
        return expires_at <= now

    def _confirmation_blocked(
        self,
        context: CapabilityRequestContext,
        reason: str,
        risk_level: str,
        requires_confirmation: bool,
    ) -> CapabilityDecision:
        return self._blocked(
            context,
            reason=reason,
            message="确认令牌与本次高风险动作不匹配，动作未执行。",
            risk_level=risk_level,
            requires_confirmation=requires_confirmation,
            confirmation_required_fields=CONFIRMATION_REQUIRED_FIELDS,
        )

    def _blocked(
        self,
        context: CapabilityRequestContext,
        *,
        reason: str,
        message: str,
        risk_level: str = "unknown",
        requires_confirmation: bool = False,
        confirmation_required_fields: list[str] | None = None,
    ) -> CapabilityDecision:
        return CapabilityDecision(
            allowed=False,
            blocked_reason=reason,
            risk_level=risk_level,
            requires_confirmation=requires_confirmation,
            confirmation_required_fields=confirmation_required_fields or [],
            effective_dry_run=context.dry_run,
            account_safety_result=None,
            rate_limit_result=None,
            user_message=message,
            audit_reference=context.correlation_id,
        )
```

- [ ] **Step 6: Run CapabilityGate tests and verify GREEN**

Run:

```bash
cd E:/小红书 && py -3 -m pytest tests/backend/test_platform_capability_gate.py -q
```

Expected:
- PASS.
- No network, no database, no platform calls.

## Task 2: PlatformAdapterResolver Fail-Closed Fake Adapter Tests

**Files:**
- Create: `E:/小红书/tests/backend/test_platform_adapter_resolver.py`
- Create: `E:/小红书/backend/app/platforms/resolver.py`
- Read only: `E:/小红书/backend/app/platforms/contracts.py`
- Read only: `E:/小红书/backend/app/platforms/policy.py`

- [ ] **Step 1: Write the failing resolver tests**

Create `E:/小红书/tests/backend/test_platform_adapter_resolver.py` with this exact content:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.platforms.contracts import (
    CapabilityPolicyError,
    CapabilityRequestContext,
    ConfirmationToken,
    PlatformAccountRef,
)
from backend.app.platforms.policy import PlatformPolicyService
from backend.app.platforms.resolver import PlatformAdapterResolver


NOW = datetime(2026, 6, 9, 12, 0, 0, tzinfo=timezone.utc)


@dataclass(frozen=True)
class FakeCapability:
    key: str
    status: str = "available"
    risk: str = "medium"
    requires_confirmation: bool = False
    notes: str = "fake capability"


@dataclass(frozen=True)
class FakeMeta:
    id: str
    enabled: bool = True
    release_stage: str = "enabled"
    adapter_key: str | None = "fake"
    capabilities: list[FakeCapability] = field(default_factory=list)


class FakeRegistryProvider:
    def __init__(self, platforms: list[FakeMeta]) -> None:
        self._platforms = {platform.id: platform for platform in platforms}

    def get_meta(self, platform_id: str):
        try:
            return self._platforms[platform_id]
        except KeyError:
            raise KeyError(platform_id)

    def get_capability(self, platform_id: str, capability_key: str):
        platform = self.get_meta(platform_id)
        for capability in platform.capabilities:
            if capability.key == capability_key:
                return capability
        raise KeyError(capability_key)

    def list_platforms(self):
        return list(self._platforms.values())

    def assert_enabled(self, platform_id: str) -> None:
        platform = self.get_meta(platform_id)
        if not platform.enabled:
            raise KeyError(platform_id)


class FakeAdapter:
    def __init__(self, supported_capabilities: set[str]) -> None:
        self.supported_capabilities = supported_capabilities
        self.calls = 0

    def execute(self, context: CapabilityRequestContext) -> dict[str, str]:
        self.calls += 1
        return {
            "platform_id": context.platform_id,
            "capability_key": context.capability_key,
        }


def fake_platform(
    *,
    platform_id: str = "fake",
    enabled: bool = True,
    release_stage: str = "enabled",
    adapter_key: str | None = "fake",
    capabilities: list[FakeCapability] | None = None,
) -> FakeMeta:
    return FakeMeta(
        id=platform_id,
        enabled=enabled,
        release_stage=release_stage,
        adapter_key=adapter_key,
        capabilities=capabilities or [FakeCapability("content.discover")],
    )


def make_policy(platforms: list[FakeMeta]) -> PlatformPolicyService:
    return PlatformPolicyService(
        registry_provider=FakeRegistryProvider(platforms),
        now_provider=lambda: NOW,
    )


def make_resolver(
    *,
    platforms: list[FakeMeta],
    adapters: dict[str, FakeAdapter],
) -> PlatformAdapterResolver:
    return PlatformAdapterResolver(
        policy_service=make_policy(platforms),
        adapters=adapters,
    )


def make_account(account_id: int = 101, sub_type: str | None = "creator") -> PlatformAccountRef:
    return PlatformAccountRef(
        account_id=account_id,
        platform_id="fake",
        account_kind="content_account",
        sub_type=sub_type,
        display_role="测试账号",
        auth_mode="cookie",
        status="active",
        credential_status="valid",
        health_status="healthy",
        profile_summary={"nickname": "fake"},
    )


def make_token(
    *,
    capability_key: str = "publish.real_publish",
    account_id: int = 101,
    action_hash: str = "action-1",
    payload_summary_hash: str = "payload-1",
) -> ConfirmationToken:
    return ConfirmationToken(
        capability_key=capability_key,
        platform_id="fake",
        account_id=account_id,
        action_hash=action_hash,
        payload_summary_hash=payload_summary_hash,
        expires_at=NOW + timedelta(minutes=10),
        issued_by=7,
        single_use=True,
        confirmed_risk_level="high",
        request_source="manual",
    )


def make_context(
    *,
    platform_id: str = "fake",
    capability_key: str = "content.discover",
    account_ref: PlatformAccountRef | None = None,
    confirmation_token: ConfirmationToken | None = None,
    action_hash: str | None = "action-1",
    payload_summary_hash: str | None = "payload-1",
    required_account_sub_type: str | None = None,
    allow_partial: bool = False,
) -> CapabilityRequestContext:
    return CapabilityRequestContext(
        user_id=7,
        platform_id=platform_id,
        capability_key=capability_key,
        account_ref=account_ref,
        dry_run=True,
        confirmation_token=confirmation_token,
        request_source="manual",
        correlation_id="corr-resolver-test",
        task_id=None,
        idempotency_key="idem-resolver-test",
        action_hash=action_hash,
        payload_summary_hash=payload_summary_hash,
        required_account_sub_type=required_account_sub_type,
        allow_partial=allow_partial,
    )


def test_resolver_blocks_planned_platform_without_calling_adapter():
    adapter = FakeAdapter({"content.discover"})
    resolver = make_resolver(
        platforms=[
            fake_platform(
                platform_id="fake",
                release_stage="planned",
                adapter_key="fake",
                capabilities=[FakeCapability("content.discover")],
            )
        ],
        adapters={"fake": adapter},
    )

    with pytest.raises(CapabilityPolicyError) as exc_info:
        resolver.resolve("fake", "content.discover", make_context())

    assert exc_info.value.decision.blocked_reason == "platform_planned"
    assert adapter.calls == 0


def test_resolver_blocks_when_adapter_supports_but_registry_marks_capability_blocked():
    adapter = FakeAdapter({"engagement.reply_execute"})
    resolver = make_resolver(
        platforms=[
            fake_platform(
                capabilities=[
                    FakeCapability(
                        "engagement.reply_execute",
                        status="blocked",
                        risk="high",
                        requires_confirmation=True,
                    )
                ]
            )
        ],
        adapters={"fake": adapter},
    )

    with pytest.raises(CapabilityPolicyError) as exc_info:
        resolver.resolve(
            "fake",
            "engagement.reply_execute",
            make_context(capability_key="engagement.reply_execute"),
        )

    assert exc_info.value.decision.blocked_reason == "capability_blocked"
    assert adapter.calls == 0


def test_resolver_blocks_when_registry_allows_but_adapter_does_not_support_capability():
    adapter = FakeAdapter({"content.crawl_detail"})
    resolver = make_resolver(
        platforms=[fake_platform(capabilities=[FakeCapability("content.discover")])],
        adapters={"fake": adapter},
    )

    with pytest.raises(CapabilityPolicyError) as exc_info:
        resolver.resolve("fake", "content.discover", make_context())

    assert exc_info.value.decision.blocked_reason == "adapter_capability_unsupported"
    assert adapter.calls == 0


def test_resolver_blocks_unknown_adapter_key_without_calling_other_adapter():
    registered_adapter = FakeAdapter({"content.discover"})
    resolver = make_resolver(
        platforms=[fake_platform(adapter_key="unknown_adapter")],
        adapters={"fake": registered_adapter},
    )

    with pytest.raises(CapabilityPolicyError) as exc_info:
        resolver.resolve("fake", "content.discover", make_context())

    assert exc_info.value.decision.blocked_reason == "adapter_not_registered"
    assert registered_adapter.calls == 0


def test_resolver_blocks_missing_adapter_implementation():
    orphan_adapter = FakeAdapter({"content.discover"})
    resolver = make_resolver(
        platforms=[fake_platform(adapter_key="fake")],
        adapters={},
    )

    with pytest.raises(CapabilityPolicyError) as exc_info:
        resolver.resolve("fake", "content.discover", make_context())

    assert exc_info.value.decision.blocked_reason == "adapter_not_registered"
    assert orphan_adapter.calls == 0


def test_resolver_blocks_missing_adapter_key_before_adapter_lookup():
    adapter = FakeAdapter({"content.discover"})
    resolver = make_resolver(
        platforms=[fake_platform(adapter_key=None)],
        adapters={"fake": adapter},
    )

    with pytest.raises(CapabilityPolicyError) as exc_info:
        resolver.resolve("fake", "content.discover", make_context())

    assert exc_info.value.decision.blocked_reason == "adapter_key_missing"
    assert adapter.calls == 0


def test_resolver_blocks_context_platform_or_capability_mismatch_before_adapter_lookup():
    adapter = FakeAdapter({"content.discover"})
    resolver = make_resolver(
        platforms=[fake_platform()],
        adapters={"fake": adapter},
    )

    with pytest.raises(CapabilityPolicyError) as exc_info:
        resolver.resolve(
            "fake",
            "content.discover",
            make_context(platform_id="other", capability_key="content.discover"),
        )

    assert exc_info.value.decision.blocked_reason == "request_context_mismatch"
    assert adapter.calls == 0


def test_resolver_returns_fake_adapter_only_when_registry_policy_and_adapter_support_match():
    adapter = FakeAdapter({"publish.real_publish"})
    platform = fake_platform(
        capabilities=[
            FakeCapability(
                "publish.real_publish",
                status="available",
                risk="high",
                requires_confirmation=True,
            )
        ]
    )
    account_ref = make_account(account_id=101, sub_type="creator")
    context = make_context(
        capability_key="publish.real_publish",
        account_ref=account_ref,
        confirmation_token=make_token(account_id=account_ref.account_id),
        required_account_sub_type="creator",
        action_hash="action-1",
        payload_summary_hash="payload-1",
    )
    resolver = make_resolver(platforms=[platform], adapters={"fake": adapter})

    resolved = resolver.resolve("fake", "publish.real_publish", context)
    result = resolved.execute(context)

    assert resolved is adapter
    assert result == {
        "platform_id": "fake",
        "capability_key": "publish.real_publish",
    }
    assert adapter.calls == 1
```

- [ ] **Step 2: Run resolver tests and verify RED**

Run:

```bash
cd E:/小红书 && py -3 -m pytest tests/backend/test_platform_adapter_resolver.py -q
```

Expected:
- FAIL before `resolver.py` exists.
- Expected import failure: `ModuleNotFoundError: No module named 'backend.app.platforms.resolver'`.

- [ ] **Step 3: Implement `resolver.py`**

Create `E:/小红书/backend/app/platforms/resolver.py` with this exact content:

```python
from __future__ import annotations

from collections.abc import Mapping

from backend.app.platforms.contracts import (
    CapabilityDecision,
    CapabilityPolicyError,
    CapabilityRequestContext,
    PlatformAdapter,
)
from backend.app.platforms.policy import PlatformPolicyService


class PlatformAdapterResolver:
    def __init__(
        self,
        policy_service: PlatformPolicyService | None = None,
        adapters: Mapping[str, PlatformAdapter] | None = None,
    ) -> None:
        self.policy_service = policy_service or PlatformPolicyService()
        self._adapters = dict(adapters or {})

    def resolve(
        self,
        platform_id: str,
        capability_key: str,
        context: CapabilityRequestContext,
    ) -> PlatformAdapter:
        if context.platform_id != platform_id or context.capability_key != capability_key:
            raise CapabilityPolicyError(
                self._blocked(
                    context,
                    reason="request_context_mismatch",
                    message="请求上下文与 resolver 参数不一致，动作未执行。",
                )
            )

        decision = self.policy_service.enforce(context)
        meta = self.policy_service.registry_provider.get_meta(platform_id)
        adapter_key = getattr(meta, "adapter_key", None)

        adapter = self._adapters.get(adapter_key)
        if adapter is None:
            raise CapabilityPolicyError(
                self._blocked(
                    context,
                    reason="adapter_not_registered",
                    message="平台适配器尚未注册，动作未执行。",
                    risk_level=decision.risk_level,
                    requires_confirmation=decision.requires_confirmation,
                )
            )

        supported_capabilities = set(getattr(adapter, "supported_capabilities", set()))
        if capability_key not in supported_capabilities:
            raise CapabilityPolicyError(
                self._blocked(
                    context,
                    reason="adapter_capability_unsupported",
                    message="适配器未声明支持该能力，动作未执行。",
                    risk_level=decision.risk_level,
                    requires_confirmation=decision.requires_confirmation,
                )
            )

        return adapter

    def _blocked(
        self,
        context: CapabilityRequestContext,
        *,
        reason: str,
        message: str,
        risk_level: str = "unknown",
        requires_confirmation: bool = False,
    ) -> CapabilityDecision:
        return CapabilityDecision(
            allowed=False,
            blocked_reason=reason,
            risk_level=risk_level,
            requires_confirmation=requires_confirmation,
            confirmation_required_fields=[],
            effective_dry_run=context.dry_run,
            account_safety_result=None,
            rate_limit_result=None,
            user_message=message,
            audit_reference=context.correlation_id,
        )
```

- [ ] **Step 4: Run resolver tests and verify GREEN**

Run:

```bash
cd E:/小红书 && py -3 -m pytest tests/backend/test_platform_adapter_resolver.py -q
```

Expected:
- PASS.
- Fake adapters are the only adapters used.
- All blocked resolver scenarios keep `FakeAdapter.calls == 0`.

## Task 3: Aggregate Verification and Scope Audit

**Files:**
- Verify only: `E:/小红书/tests/backend/test_platforms.py`
- Verify only: `E:/小红书/tests/backend/test_platform_capability_gate.py`
- Verify only: `E:/小红书/tests/backend/test_platform_adapter_resolver.py`
- Inspect only: Stage A diff

- [ ] **Step 1: Run Stage A aggregate backend tests**

Run:

```bash
cd E:/小红书 && py -3 -m pytest tests/backend/test_platforms.py tests/backend/test_platform_capability_gate.py tests/backend/test_platform_adapter_resolver.py -q
```

Expected:
- PASS.
- Existing `/api/platforms` registry behavior remains unchanged.

- [ ] **Step 2: Run whitespace/conflict sanity check**

Run:

```bash
git -C E:/小红书 diff --check -- backend/app/platforms/contracts.py backend/app/platforms/policy.py backend/app/platforms/resolver.py tests/backend/test_platform_capability_gate.py tests/backend/test_platform_adapter_resolver.py docs/superpowers/plans/2026-06-09-platform-adapter-contract-skeleton.md
```

Expected:
- No trailing whitespace or conflict markers.

- [ ] **Step 3: Inspect changed file list for scope compliance**

Run:

```bash
git -C E:/小红书 status --short
```

Expected Stage A additions:
- `?? backend/app/platforms/contracts.py`
- `?? backend/app/platforms/policy.py`
- `?? backend/app/platforms/resolver.py`
- `?? tests/backend/test_platform_capability_gate.py`
- `?? tests/backend/test_platform_adapter_resolver.py`
- `?? docs/superpowers/plans/2026-06-09-platform-adapter-contract-skeleton.md`

Existing unrelated dirty files may still appear. Do not touch them.

- [ ] **Step 4: Confirm forbidden layers were not touched**

Run:

```bash
git -C E:/小红书 diff --name-only -- apis xhs_utils static backend/app/adapters/xhs backend/app/api/platforms/xhs backend/app/api/publish.py frontend
```

Expected:
- No Stage A changes in forbidden paths.
- If existing unrelated frontend diffs appear, confirm they pre-existed and were not modified by this task.

- [ ] **Step 5: Stop without committing**

Do not run:

```bash
git add
git commit
git push
```

Expected:
- Implementation remains uncommitted until the user explicitly requests commit/push.

## Self-Review Checklist

Before reporting Stage A done, verify:
- [ ] Only the five Stage A implementation/test files plus this requested plan file were created or modified by this work.
- [ ] `E:/小红书/backend/app/core/platforms.py` remains the registry fact source and was not edited.
- [ ] Policy logic keys off `release_stage`, `enabled`, `adapter_key`, `capability.status`, `capability.risk`, and `capability.requires_confirmation`; it does not use legacy `PlatformMeta.status`.
- [ ] `CapabilityStatus` enum in `core/platforms.py` was not extended just to add `unavailable`; fake tests cover the string path without changing registry API semantics.
- [ ] Planned platforms fail before adapter lookup.
- [ ] Disabled non-planned fake platform is tested separately from `douyin`.
- [ ] Missing adapter key, missing adapter implementation, unknown adapter key, and adapter unsupported capability all fail closed.
- [ ] `engagement.reply_execute` remains `blocked/high/requires_confirmation` and policy blocks it.
- [ ] Partial capability is blocked by default and allowed only with explicit `allow_partial=True` skeleton context.
- [ ] High-risk confirmation requires action-level binding and expiry checks.
- [ ] Account platform and subtype mismatches are blocked.
- [ ] Resolver calls/enforces policy before returning an adapter.
- [ ] Fake adapters are never called in blocked paths.
- [ ] No imports from `apis`, `xhs_utils`, `static`, or `backend.app.adapters.xhs` were introduced in `backend/app/platforms/`.
- [ ] No API responses, XHS routes, Huitun logic, database schema, frontend behavior, real publish, or real platform calls changed.
- [ ] Aggregate command passes: `cd E:/小红书 && py -3 -m pytest tests/backend/test_platforms.py tests/backend/test_platform_capability_gate.py tests/backend/test_platform_adapter_resolver.py -q`.

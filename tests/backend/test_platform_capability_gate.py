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


@dataclass(frozen=True)
class FakeMetaWithoutReleaseStage:
    id: str
    enabled: bool = True
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
    request_source: str | None = "manual",
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


def test_capability_gate_blocks_unknown_platform_release_stage_even_when_enabled():
    platform = fake_platform(platform_id="mystery_stage", enabled=True, release_stage="mystery")
    decision = make_service([platform]).evaluate(
        make_context(platform_id="mystery_stage", capability_key="content.discover")
    )

    assert decision.allowed is False
    assert decision.blocked_reason == "platform_unavailable"


def test_capability_gate_blocks_platform_missing_release_stage_even_when_enabled():
    platform = FakeMetaWithoutReleaseStage(
        id="missing_stage",
        enabled=True,
        adapter_key="fake",
        capabilities=[FakeCapability("content.discover")],
    )
    decision = make_service([platform]).evaluate(
        make_context(platform_id="missing_stage", capability_key="content.discover")
    )

    assert decision.allowed is False
    assert decision.blocked_reason == "platform_unavailable"


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


def test_capability_gate_blocks_planned_blocked_unavailable_and_unknown_status_capabilities():
    cases = [
        ("planned", "capability_planned"),
        ("blocked", "capability_blocked"),
        ("unavailable", "capability_unavailable"),
        ("mystery", "capability_unavailable"),
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


def test_capability_gate_blocks_unknown_capability_risk_with_capability_unavailable():
    platform = fake_platform(
        platform_id="unknown_risk",
        capabilities=[FakeCapability("content.discover", status="available", risk="mystery")],
    )
    decision = make_service([platform]).evaluate(
        make_context(platform_id="unknown_risk", capability_key="content.discover")
    )

    assert decision.allowed is False
    assert decision.blocked_reason == "capability_unavailable"
    assert decision.risk_level == "mystery"


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


def test_capability_gate_blocks_missing_or_invalid_request_source_before_allowing_capability():
    account_ref = make_account()
    cases = [
        (None, "request_context_mismatch"),
        ("console", "request_context_mismatch"),
    ]

    for request_source, expected_reason in cases:
        decision = make_service().evaluate(
            make_context(
                platform_id="xhs",
                capability_key="content.discover",
                account_ref=account_ref,
                request_source=request_source,
            )
        )

        assert decision.allowed is False
        assert decision.blocked_reason == expected_reason


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
        (replace(base_token, request_source="console"), "confirmation_source_mismatch"),
        (replace(base_token, request_source=None), "confirmation_source_mismatch"),
        (replace(base_token, single_use=False), "confirmation_single_use_required"),
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

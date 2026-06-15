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


def test_resolver_blocks_disabled_platform_without_calling_adapter():
    adapter = FakeAdapter({"content.discover"})
    resolver = make_resolver(
        platforms=[fake_platform(enabled=False, capabilities=[FakeCapability("content.discover")])],
        adapters={"fake": adapter},
    )

    with pytest.raises(CapabilityPolicyError) as exc_info:
        resolver.resolve("fake", "content.discover", make_context())

    assert exc_info.value.decision.blocked_reason == "platform_disabled"
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


def test_resolver_blocks_high_risk_missing_confirmation_without_calling_adapter():
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
    resolver = make_resolver(platforms=[platform], adapters={"fake": adapter})

    with pytest.raises(CapabilityPolicyError) as exc_info:
        resolver.resolve(
            "fake",
            "publish.real_publish",
            make_context(
                capability_key="publish.real_publish",
                account_ref=account_ref,
                confirmation_token=None,
                required_account_sub_type="creator",
                action_hash="action-1",
                payload_summary_hash="payload-1",
            ),
        )

    assert exc_info.value.decision.blocked_reason == "confirmation_required"
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

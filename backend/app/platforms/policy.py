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
VALID_RELEASE_STAGES = {"enabled", "beta"}
VALID_CAPABILITY_RISKS = {"low", "medium", "high"}
VALID_REQUEST_SOURCES = {"manual", "scheduler", "auto_task", "api", "retry"}


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
        if context.request_source not in VALID_REQUEST_SOURCES:
            return self._blocked(
                context,
                reason="request_context_mismatch",
                message="请求上下文与允许的来源不匹配，动作未执行。",
            )

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
        if release_stage == "unavailable" or release_stage not in VALID_RELEASE_STAGES:
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

        if risk_level not in VALID_CAPABILITY_RISKS:
            return self._blocked(
                context,
                reason="capability_unavailable",
                message="该能力当前不可用，动作未执行。",
                risk_level=risk_level,
                requires_confirmation=requires_confirmation,
            )

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
        if status not in {"available", "partial"}:
            return self._blocked(
                context,
                reason="capability_unavailable",
                message="该能力当前不可用，动作未执行。",
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
        if (
            token.request_source not in VALID_REQUEST_SOURCES
            or token.request_source != context.request_source
        ):
            return self._confirmation_blocked(
                context, "confirmation_source_mismatch", risk_level, requires_confirmation
            )
        if self._is_expired(token.expires_at):
            return self._confirmation_blocked(
                context, "confirmation_expired", risk_level, requires_confirmation
            )
        if not token.single_use:
            return self._confirmation_blocked(
                context,
                "confirmation_single_use_required",
                risk_level,
                requires_confirmation,
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

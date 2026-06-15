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

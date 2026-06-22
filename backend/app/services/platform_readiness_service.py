from __future__ import annotations

from dataclasses import dataclass


CORE_READINESS_CHECKS = (
    "platform_registered",
    "read_only_adapter_path",
    "shared_content_library_or_deferral",
    "capability_policy_gate",
    "publish_dry_run_no_side_effect",
    "scheduler_no_bypass",
    "diagnostics_no_secret_leak",
    "credential_logging_safe",
    "real_publish_confirmation_gate",
    "disable_or_rollback_path",
)

_BLOCKER_CHECKS = {
    "capability_policy_gate",
    "publish_dry_run_no_side_effect",
    "scheduler_no_bypass",
    "diagnostics_no_secret_leak",
    "credential_logging_safe",
    "real_publish_confirmation_gate",
}

_CHECK_DESCRIPTIONS = {
    "platform_registered": "平台已先进入 registry，而不是先复制页面。",
    "read_only_adapter_path": "新平台能通过 registry + adapter + normalizer 接入最小只读能力。",
    "shared_content_library_or_deferral": "内容库可走共享 shell/adapter，或已有明确延期边界。",
    "capability_policy_gate": "真实平台动作必须经过 Capability Policy。",
    "publish_dry_run_no_side_effect": "发布 dry-run 已证明不上传、不发布、不改发布状态。",
    "scheduler_no_bypass": "scheduler/auto task/retry 不绕过真实动作门禁。",
    "diagnostics_no_secret_leak": "诊断只暴露用户可读恢复信息，不泄露凭据或平台私有 token。",
    "credential_logging_safe": "凭据不会进入日志、前端、通知、诊断或任务 payload。",
    "real_publish_confirmation_gate": "真实发布仍需要动作级确认。",
    "disable_or_rollback_path": "平台能力可以禁用或回滚到安全状态。",
}

_USER_IMPACT = {
    "platform_registered": "用户能在统一平台入口理解该平台状态。",
    "read_only_adapter_path": "用户可以先获得低风险只读价值，而不等待完整闭环。",
    "shared_content_library_or_deferral": "用户不会被迫学习每个平台一套内容库操作。",
    "capability_policy_gate": "用户不会误触未开放或高风险动作。",
    "publish_dry_run_no_side_effect": "用户可以安全预检发布任务，不影响真实账号。",
    "scheduler_no_bypass": "用户不会因为后台任务而被静默真实发布。",
    "diagnostics_no_secret_leak": "用户能看到下一步恢复建议，同时凭据不外泄。",
    "credential_logging_safe": "用户账号凭据不会被调试链路复制扩散。",
    "real_publish_confirmation_gate": "用户对每次真实发布保持最终控制权。",
    "disable_or_rollback_path": "用户遇到平台异常时可以快速禁用或回滚。",
}

_NEXT_ACTION = {
    "platform_registered": "先补 registry 元数据和 capability matrix。",
    "read_only_adapter_path": "先实现 fake/read-only adapter pilot，不接真实写动作。",
    "shared_content_library_or_deferral": "接入 ContentLibraryAdapter，或记录只读阶段延期原因。",
    "capability_policy_gate": "先把该能力接入 PlatformPolicyService，再允许 adapter 调用。",
    "publish_dry_run_no_side_effect": "先补 dry-run no-side-effect 测试，再开放发布入口。",
    "scheduler_no_bypass": "先补 scheduler no-bypass gate，再启用自动化。",
    "diagnostics_no_secret_leak": "先接入标准 diagnostics，并验证 raw_reference 不泄密。",
    "credential_logging_safe": "先审查日志、通知、任务 payload 和前端响应。",
    "real_publish_confirmation_gate": "先补动作级 confirmation token 或显式确认路径。",
    "disable_or_rollback_path": "先提供能力禁用或回滚开关。",
}


@dataclass(frozen=True)
class CoreReadinessSnapshot:
    platform_registered: bool
    read_only_adapter_path: bool
    shared_content_library_or_deferral: bool
    capability_policy_gate: bool
    publish_dry_run_no_side_effect: bool
    scheduler_no_bypass: bool
    diagnostics_no_secret_leak: bool
    credential_logging_safe: bool
    real_publish_confirmation_gate: bool
    disable_or_rollback_path: bool


@dataclass(frozen=True)
class ReadinessCheck:
    key: str
    passed: bool
    severity: str
    description: str
    user_impact: str
    next_action: str


@dataclass(frozen=True)
class ReadinessReport:
    platform_id: str
    verdict: str
    allowed_outcome: str
    checks: tuple[ReadinessCheck, ...]
    blockers: list[str]
    follow_ups: list[str]

    def to_payload(self) -> dict:
        return {
            "platform_id": self.platform_id,
            "verdict": self.verdict,
            "allowed_outcome": self.allowed_outcome,
            "checks": [
                {
                    "key": check.key,
                    "passed": check.passed,
                    "severity": check.severity,
                    "description": check.description,
                    "user_impact": check.user_impact,
                    "next_action": check.next_action,
                }
                for check in self.checks
            ],
            "blockers": self.blockers,
            "follow_ups": self.follow_ups,
        }


def evaluate_second_platform_readiness(platform_id: str, snapshot: CoreReadinessSnapshot) -> ReadinessReport:
    checks = tuple(
        _build_check(key, getattr(snapshot, key))
        for key in CORE_READINESS_CHECKS
    )
    blockers = [check.key for check in checks if not check.passed and check.key in _BLOCKER_CHECKS]
    follow_ups = [check.key for check in checks if not check.passed and check.key not in _BLOCKER_CHECKS]

    if blockers:
        verdict = "BLOCKER"
        allowed_outcome = "do_not_connect_real_platform"
    elif follow_ups:
        verdict = "FOLLOW_UP"
        allowed_outcome = "docs_or_fake_adapter_only"
    else:
        verdict = "PASS"
        allowed_outcome = "start_read_only_adapter_pilot"

    return ReadinessReport(
        platform_id=platform_id,
        verdict=verdict,
        allowed_outcome=allowed_outcome,
        checks=checks,
        blockers=blockers,
        follow_ups=follow_ups,
    )


def _build_check(key: str, passed: bool) -> ReadinessCheck:
    return ReadinessCheck(
        key=key,
        passed=passed,
        severity=("passed" if passed else "blocker" if key in _BLOCKER_CHECKS else "follow_up"),
        description=_CHECK_DESCRIPTIONS[key],
        user_impact=_USER_IMPACT[key],
        next_action=("无需处理。" if passed else _NEXT_ACTION[key]),
    )

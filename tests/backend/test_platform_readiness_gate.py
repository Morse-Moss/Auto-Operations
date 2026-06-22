from __future__ import annotations

from backend.app.services.platform_readiness_service import (
    CORE_READINESS_CHECKS,
    CoreReadinessSnapshot,
    evaluate_second_platform_readiness,
)


def _ready_snapshot(**overrides) -> CoreReadinessSnapshot:
    values = {
        "platform_registered": True,
        "read_only_adapter_path": True,
        "shared_content_library_or_deferral": True,
        "capability_policy_gate": True,
        "publish_dry_run_no_side_effect": True,
        "scheduler_no_bypass": True,
        "diagnostics_no_secret_leak": True,
        "credential_logging_safe": True,
        "real_publish_confirmation_gate": True,
        "disable_or_rollback_path": True,
    }
    values.update(overrides)
    return CoreReadinessSnapshot(**values)


def test_readiness_gate_passes_only_when_every_core_check_is_ready() -> None:
    report = evaluate_second_platform_readiness("wechat_official", _ready_snapshot())

    assert report.verdict == "PASS"
    assert report.allowed_outcome == "start_read_only_adapter_pilot"
    assert {check.key for check in report.checks} == set(CORE_READINESS_CHECKS)
    assert all(check.passed for check in report.checks)
    assert report.blockers == []
    assert report.follow_ups == []


def test_readiness_gate_returns_follow_up_for_missing_read_only_adapter_path() -> None:
    report = evaluate_second_platform_readiness(
        "douyin",
        _ready_snapshot(read_only_adapter_path=False, shared_content_library_or_deferral=False),
    )

    assert report.verdict == "FOLLOW_UP"
    assert report.allowed_outcome == "docs_or_fake_adapter_only"
    assert "read_only_adapter_path" in report.follow_ups
    assert "shared_content_library_or_deferral" in report.follow_ups
    assert report.blockers == []


def test_readiness_gate_blocks_when_high_risk_gates_are_missing() -> None:
    report = evaluate_second_platform_readiness(
        "douyin",
        _ready_snapshot(
            capability_policy_gate=False,
            publish_dry_run_no_side_effect=False,
            scheduler_no_bypass=False,
            diagnostics_no_secret_leak=False,
            credential_logging_safe=False,
            real_publish_confirmation_gate=False,
        ),
    )

    assert report.verdict == "BLOCKER"
    assert report.allowed_outcome == "do_not_connect_real_platform"
    assert set(report.blockers) == {
        "capability_policy_gate",
        "publish_dry_run_no_side_effect",
        "scheduler_no_bypass",
        "diagnostics_no_secret_leak",
        "credential_logging_safe",
        "real_publish_confirmation_gate",
    }
    assert report.follow_ups == []


def test_readiness_report_explains_user_impact_and_next_action() -> None:
    report = evaluate_second_platform_readiness(
        "wechat_channels",
        _ready_snapshot(disable_or_rollback_path=False),
    )

    check = next(item for item in report.checks if item.key == "disable_or_rollback_path")
    assert report.verdict == "FOLLOW_UP"
    assert check.passed is False
    assert "用户" in check.user_impact
    assert check.next_action
    assert "回滚" in check.next_action or "禁用" in check.next_action


def test_readiness_gate_rejects_unknown_snapshot_fields_by_contract() -> None:
    assert set(CORE_READINESS_CHECKS) == {
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
    }

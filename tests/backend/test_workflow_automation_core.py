from __future__ import annotations

from datetime import datetime

from backend.app.services.workflow_automation_service import (
    WORKFLOW_DEFINITIONS,
    build_legacy_xhs_auto_task_workflow,
    build_scheduled_publish_step,
    calculate_next_run_at,
)


def test_workflow_definitions_include_safe_core_types_without_reply_execute() -> None:
    expected = {
        "discover_to_library",
        "library_to_draft",
        "draft_to_publish_job",
        "scheduled_publish",
        "monitor_keywords",
        "engagement_reply_suggest",
    }

    assert set(WORKFLOW_DEFINITIONS) == expected
    assert "engagement_reply_execute" not in WORKFLOW_DEFINITIONS
    assert "reply_execute" not in WORKFLOW_DEFINITIONS

    for workflow_type, definition in WORKFLOW_DEFINITIONS.items():
        assert definition.workflow_type == workflow_type
        assert definition.payload_skeleton
        assert definition.steps
        assert all(step.capability_key for step in definition.steps)


def test_legacy_xhs_auto_task_maps_to_non_authorized_workflow_plan() -> None:
    plan = build_legacy_xhs_auto_task_workflow(
        task_id=42,
        name="Daily discovery",
        keywords=["coffee", "bakery"],
        pc_account_id=1001,
        creator_account_id=2002,
        ai_instruction="Rewrite in a warm tone",
        schedule_type="daily",
        schedule_time="09:30",
        schedule_days="",
        schedule_interval_hours=24,
    )

    assert plan.platform_id == "xhs"
    assert plan.workflow_type in {"discover_to_publish_job", "auto_ops_legacy_skeleton"}
    assert plan.account_refs == {"pc": 1001, "creator": 2002}
    assert plan.payload["legacy_auto_task_id"] == 42
    assert plan.payload["keywords"] == ["coffee", "bakery"]
    assert plan.payload["ai_instruction"] == "Rewrite in a warm tone"
    assert plan.real_publish_authorized is False
    assert plan.risk_policy.authorization_ref is None
    assert "authorization_ref" not in plan.risk_policy.to_payload()
    assert all(not step.is_executable_real_publish for step in plan.steps)


def test_scheduled_publish_without_authorization_is_blocked_fail_closed() -> None:
    step = build_scheduled_publish_step("xhs")

    assert step.capability_key == "publish.real_publish"
    assert step.requires_authorization is True
    assert step.blocked_reason == "authorization_ref_required"
    assert step.is_executable_real_publish is False


def test_scheduled_publish_with_authorization_can_be_executable() -> None:
    step = build_scheduled_publish_step("xhs", authorization_ref="auth-123")

    assert step.requires_authorization is True
    assert step.authorization_ref == "auth-123"
    assert step.blocked_reason is None
    assert step.is_executable_real_publish is True


def test_calculate_next_run_at_preserves_manual_daily_weekly_interval_semantics() -> None:
    now = datetime(2026, 6, 22, 10, 15, 30)  # Monday

    assert calculate_next_run_at("manual", "09:00", "", 24, now) is None

    assert calculate_next_run_at("daily", "11:00", "", 24, now) == datetime(2026, 6, 22, 11, 0)
    assert calculate_next_run_at("daily", "09:00", "", 24, now) == datetime(2026, 6, 23, 9, 0)

    assert calculate_next_run_at("weekly", "08:30", "1,3", 24, now) == datetime(2026, 6, 24, 8, 30)
    assert calculate_next_run_at("weekly", "08:30", "", 24, now) is None

    assert calculate_next_run_at("interval", "09:00", "", 6, now) == datetime(2026, 6, 22, 16, 15, 30)


def test_background_auto_task_scheduler_does_not_silently_upload_or_publish() -> None:
    source = open("backend/app/services/scheduler_service.py", encoding="utf-8").read()
    start = source.index("def _execute_auto_task_background")
    end = source.index("def run_due_auto_tasks", start)
    body = source[start:end]

    assert "creator_adapter.upload_media" not in body
    assert "creator_adapter.post_note" not in body
    assert "AutoCreatorAdapter" not in body
    assert 'status="publishing"' not in body
    assert "task.total_published" not in body
    assert 'status="pending"' in body

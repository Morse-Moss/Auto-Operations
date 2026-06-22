from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Mapping


@dataclass(frozen=True)
class WorkflowStep:
    key: str
    capability_key: str
    risk_level: str = "low"
    requires_authorization: bool = False
    authorization_ref: str | None = None
    blocked_reason: str | None = None

    @property
    def is_executable_real_publish(self) -> bool:
        return (
            self.capability_key == "publish.real_publish"
            and self.requires_authorization
            and self.authorization_ref is not None
            and self.blocked_reason is None
        )


@dataclass(frozen=True)
class WorkflowDefinition:
    workflow_type: str
    payload_skeleton: Mapping[str, Any]
    steps: tuple[WorkflowStep, ...]


@dataclass(frozen=True)
class WorkflowSchedule:
    schedule_type: str
    schedule_time: str = "09:00"
    schedule_days: str = ""
    schedule_interval_hours: int = 24


@dataclass(frozen=True)
class RiskPolicy:
    real_publish_authorized: bool = False
    authorization_ref: str | None = None
    blocked_capabilities: tuple[str, ...] = field(default_factory=tuple)

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "real_publish_authorized": self.real_publish_authorized,
            "blocked_capabilities": list(self.blocked_capabilities),
        }
        if self.authorization_ref is not None:
            payload["authorization_ref"] = self.authorization_ref
        return payload


@dataclass(frozen=True)
class WorkflowPlan:
    platform_id: str
    workflow_type: str
    account_refs: Mapping[str, int]
    schedule: WorkflowSchedule
    payload: Mapping[str, Any]
    risk_policy: RiskPolicy
    steps: tuple[WorkflowStep, ...]

    @property
    def real_publish_authorized(self) -> bool:
        return self.risk_policy.real_publish_authorized


WORKFLOW_DEFINITIONS: Mapping[str, WorkflowDefinition] = {
    "discover_to_library": WorkflowDefinition(
        workflow_type="discover_to_library",
        payload_skeleton={"keywords": [], "source": None, "limit": None},
        steps=(
            WorkflowStep("discover", "content.discover", "medium"),
            WorkflowStep("save_to_library", "content.library", "low"),
        ),
    ),
    "library_to_draft": WorkflowDefinition(
        workflow_type="library_to_draft",
        payload_skeleton={"content_refs": [], "ai_instruction": ""},
        steps=(
            WorkflowStep("load_library_item", "content.library", "low"),
            WorkflowStep("create_draft", "content.rewrite", "medium"),
        ),
    ),
    "draft_to_publish_job": WorkflowDefinition(
        workflow_type="draft_to_publish_job",
        payload_skeleton={"draft_ref": None, "publish_mode": "draft_job_only"},
        steps=(
            WorkflowStep("validate_draft", "publish.dry_run", "medium"),
            WorkflowStep("create_publish_job", "publish.create_job", "medium"),
        ),
    ),
    "scheduled_publish": WorkflowDefinition(
        workflow_type="scheduled_publish",
        payload_skeleton={"publish_job_ref": None, "scheduled_at": None, "authorization_ref": None},
        steps=(
            WorkflowStep("schedule_publish", "publish.schedule", "high"),
            WorkflowStep(
                "generic.real_publish",
                "publish.real_publish",
                "high",
                requires_authorization=True,
                blocked_reason="authorization_ref_required",
            ),
        ),
    ),
    "monitor_keywords": WorkflowDefinition(
        workflow_type="monitor_keywords",
        payload_skeleton={"keywords": [], "interval_hours": None},
        steps=(WorkflowStep("monitor_keywords", "monitoring.keyword", "low"),),
    ),
    "engagement_reply_suggest": WorkflowDefinition(
        workflow_type="engagement_reply_suggest",
        payload_skeleton={"content_refs": [], "comment_refs": [], "tone": None},
        steps=(
            WorkflowStep("read_comments", "engagement.comment_read", "medium"),
            WorkflowStep("suggest_reply", "engagement.reply_suggest", "medium"),
        ),
    ),
}


def build_scheduled_publish_step(platform_id: str, authorization_ref: str | None = None) -> WorkflowStep:
    blocked_reason = None if authorization_ref else "authorization_ref_required"
    return WorkflowStep(
        key=f"{platform_id}.real_publish",
        capability_key="publish.real_publish",
        risk_level="high",
        requires_authorization=True,
        authorization_ref=authorization_ref,
        blocked_reason=blocked_reason,
    )


def build_legacy_xhs_auto_task_workflow(
    *,
    task_id: int,
    name: str,
    keywords: list[str],
    pc_account_id: int,
    creator_account_id: int,
    ai_instruction: str,
    schedule_type: str,
    schedule_time: str,
    schedule_days: str,
    schedule_interval_hours: int,
) -> WorkflowPlan:
    del name
    risk_policy = RiskPolicy(
        real_publish_authorized=False,
        blocked_capabilities=("publish.real_publish",),
    )
    return WorkflowPlan(
        platform_id="xhs",
        workflow_type="auto_ops_legacy_skeleton",
        account_refs={"pc": pc_account_id, "creator": creator_account_id},
        schedule=WorkflowSchedule(
            schedule_type=schedule_type,
            schedule_time=schedule_time,
            schedule_days=schedule_days,
            schedule_interval_hours=schedule_interval_hours,
        ),
        payload={
            "legacy_auto_task_id": task_id,
            "keywords": list(keywords),
            "ai_instruction": ai_instruction,
            "output": "publish_job_only",
        },
        risk_policy=risk_policy,
        steps=(
            WorkflowStep("search_note", "content.discover", "medium"),
            WorkflowStep("create_draft", "content.rewrite", "medium"),
            WorkflowStep("create_publish_job", "publish.create_job", "medium"),
            build_scheduled_publish_step("xhs"),
        ),
    )


def calculate_next_run_at(
    schedule_type: str,
    schedule_time: str | None,
    schedule_days: str | None,
    schedule_interval_hours: int | None,
    now: datetime,
) -> datetime | None:
    if schedule_type == "manual":
        return None
    if schedule_type == "daily":
        hour, minute = _parse_schedule_time(schedule_time)
        next_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_time <= now:
            next_time += timedelta(days=1)
        return next_time
    if schedule_type == "weekly":
        hour, minute = _parse_schedule_time(schedule_time)
        days = [int(day) for day in (schedule_days or "").split(",") if day.strip().isdigit()]
        if not days:
            return None
        for offset in range(1, 8):
            candidate = now + timedelta(days=offset)
            if candidate.isoweekday() in days:
                return candidate.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return None
    if schedule_type == "interval":
        return now + timedelta(hours=schedule_interval_hours or 24)
    return None


def _parse_schedule_time(schedule_time: str | None) -> tuple[int, int]:
    hour, minute = (schedule_time or "09:00").split(":")
    return int(hour), int(minute)

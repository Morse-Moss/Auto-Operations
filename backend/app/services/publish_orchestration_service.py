from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import PlatformAccount, PublishAsset, PublishJob, User
from backend.app.platforms.contracts import CapabilityRequestContext, PlatformAccountRef
from backend.app.platforms.policy import PlatformPolicyService
from backend.app.services.diagnostic_service import (
    diagnostic_from_capability_decision,
    validation_diagnostic,
)


class PublishOrchestrationService:
    def __init__(
        self,
        db: Session,
        policy_service: PlatformPolicyService | None = None,
    ) -> None:
        self.db = db
        self.policy_service = policy_service or PlatformPolicyService()

    def dry_run(self, *, job_id: int, current_user: User) -> dict[str, Any]:
        job = self._get_owned_job(job_id=job_id, current_user=current_user)
        account = self._get_account(job=job, current_user=current_user)
        assets = self._get_assets(job)
        context = CapabilityRequestContext(
            user_id=current_user.id,
            platform_id=job.platform,
            capability_key="publish.dry_run",
            account_ref=self._account_ref(account),
            dry_run=True,
            confirmation_token=None,
            request_source="manual",
            correlation_id=f"publish-dry-run:{job.id}",
            required_account_sub_type="creator" if job.platform == "xhs" else None,
        )
        decision = self.policy_service.evaluate(context)

        checks: list[dict[str, Any]] = [
            self._check(
                code="policy",
                status="passed" if decision.allowed else "blocked",
                message=decision.user_message,
            )
        ]
        checks.extend(self._local_checks(job=job, account=account, assets=assets))
        diagnostics = []
        if not decision.allowed:
            diagnostics.append(
                diagnostic_from_capability_decision(
                    decision,
                    context=context,
                    stage="policy",
                ).to_payload()
            )
        diagnostics.extend(
            validation_diagnostic(
                platform_id=job.platform,
                capability_key="publish.dry_run",
                stage="local_validation",
                correlation_id=context.correlation_id,
                user_message=check["message"],
            ).to_payload()
            for check in checks
            if check["status"] in {"blocked", "warning"} and check["code"] != "policy"
        )

        ok = decision.allowed and not any(check["status"] == "blocked" for check in checks)
        return {
            "job_id": job.id,
            "ok": ok,
            "publish_blocked": True,
            "checks": checks,
            "diagnostics": diagnostics,
            "policy": {
                "allowed": decision.allowed,
                "blocked_reason": decision.blocked_reason,
                "risk_level": decision.risk_level,
                "requires_confirmation": decision.requires_confirmation,
                "effective_dry_run": decision.effective_dry_run,
                "user_message": decision.user_message,
            },
        }

    def _get_owned_job(self, *, job_id: int, current_user: User) -> PublishJob:
        job = self.db.scalars(
            select(PublishJob).where(PublishJob.id == job_id, PublishJob.user_id == current_user.id)
        ).first()
        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Publish job not found")
        return job

    def _get_account(self, *, job: PublishJob, current_user: User) -> PlatformAccount | None:
        if not job.platform_account_id:
            return None
        account = self.db.get(PlatformAccount, job.platform_account_id)
        if account is None or account.user_id != current_user.id:
            return None
        return account

    def _get_assets(self, job: PublishJob) -> list[PublishAsset]:
        return list(
            self.db.scalars(
                select(PublishAsset)
                .where(PublishAsset.publish_job_id == job.id)
                .order_by(PublishAsset.id.asc())
            ).all()
        )

    def _account_ref(self, account: PlatformAccount | None) -> PlatformAccountRef | None:
        if account is None:
            return None
        return PlatformAccountRef(
            account_id=account.id,
            platform_id=account.platform,
            account_kind=account.sub_type,
            sub_type=account.sub_type,
            status=account.status,
        )

    def _local_checks(
        self,
        *,
        job: PublishJob,
        account: PlatformAccount | None,
        assets: list[PublishAsset],
    ) -> list[dict[str, Any]]:
        image_assets = [asset for asset in assets if asset.asset_type == "image"]
        video_assets = [asset for asset in assets if asset.asset_type == "video"]
        checks = [
            self._check(
                code="title_required",
                status="passed" if job.title.strip() else "blocked",
                message="标题已填写。" if job.title.strip() else "发布标题不能为空。",
            ),
            self._check(
                code="body",
                status="passed" if job.body.strip() else "warning",
                message="正文已填写。" if job.body.strip() else "正文为空，发布前建议补充正文。",
            ),
            self._check(
                code="asset_required",
                status="passed" if image_assets else "blocked",
                message="已选择图片素材。" if image_assets else "至少需要一个图片素材。",
            ),
        ]

        if job.platform == "xhs":
            checks.append(
                self._check(
                    code="creator_account_required",
                    status=("passed" if account is not None and account.sub_type == "creator" else "blocked"),
                    message="已选择小红书 Creator 账号。" if account is not None and account.sub_type == "creator" else "请选择小红书 Creator 账号。",
                )
            )

        if video_assets:
            checks.append(
                self._check(
                    code="video_unsupported",
                    status="blocked",
                    message="视频发布功能即将上线，目前仅支持图片发布。",
                )
            )

        if job.publish_mode == "scheduled":
            checks.append(
                self._check(
                    code="scheduled_at_future",
                    status="passed" if job.scheduled_at is not None and job.scheduled_at > self._now() else "blocked",
                    message=(
                        "排期时间有效。"
                        if job.scheduled_at is not None and job.scheduled_at > self._now()
                        else "排期发布时间必须晚于当前时间。"
                    ),
                )
            )

        return checks

    def _now(self):
        from backend.app.core.time import shanghai_now

        return shanghai_now()

    @staticmethod
    def _check(*, code: str, status: str, message: str) -> dict[str, str]:
        return {"code": code, "status": status, "message": message}

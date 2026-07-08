from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.app.models import BetaCreditAccount, Tenant, TenantMember, UsageLedger

CREDITS_BUCKET = "credits"

BETA_DEFAULT_BUCKETS: dict[str, int] = {
    CREDITS_BUCKET: 100,
}

CREDIT_COSTS: dict[str, int] = {
    "note_search": 2,
    "ai_text": 2,
    "image_generation": 5,
    "analysis_report": 10,
}

BUCKET_LABELS: dict[str, str] = {
    CREDITS_BUCKET: "积分",
    "image_generation": "图片生成",
    "ai_rewrite": "AI 改写",
    "text_action": "文本 AI",
    "draft_score": "草稿评分",
    "analysis_report": "分析报告",
}


FEATURE_CREDIT_ACTIONS: dict[str, str] = {
    "ai.rewrite_note": "ai_text",
    "ai.generate_note": "ai_text",
    "ai.generate_title": "ai_text",
    "ai.generate_tags": "ai_text",
    "ai.polish_text": "ai_text",
    "ai.describe_image": "ai_text",
    "draft.ai_score": "ai_text",
    "ai.image_generate_cover": "image_generation",
    "ai.image_generate": "image_generation",
    "ai.image_generate_async": "image_generation",
    "analysis.report_create": "analysis_report",
    "analysis.report_rerun": "analysis_report",
    "xhs.data_acquisition.note_search": "note_search",
}


def credit_cost(action_key: str) -> int:
    if action_key not in CREDIT_COSTS:
        raise ValueError(f"Unknown credit action: {action_key}")
    return CREDIT_COSTS[action_key]


def credit_action_for_feature(feature_key: str) -> str:
    if feature_key not in FEATURE_CREDIT_ACTIONS:
        raise ValueError(f"Unknown credit feature: {feature_key}")
    return FEATURE_CREDIT_ACTIONS[feature_key]


def credit_cost_for_feature(feature_key: str) -> int:
    return credit_cost(credit_action_for_feature(feature_key))


@dataclass(frozen=True)
class TenantContext:
    tenant: Tenant
    membership: TenantMember


@dataclass(frozen=True)
class UsageBucketBalance:
    bucket: str
    total: int
    remaining: int
    status: str


class UsageQuotaInsufficientError(HTTPException):
    def __init__(self, *, feature_key: str, bucket: str, required: int, remaining: int) -> None:
        label = BUCKET_LABELS.get(bucket, bucket)
        unit = "积分" if bucket == CREDITS_BUCKET else "次"
        payload = {
            "code": "usage_quota_insufficient",
            "message": f"{label}不足，本次需要 {required} {unit}，当前剩余 {remaining} {unit}。",
            "feature_key": feature_key,
            "bucket": bucket,
            "required": required,
            "remaining": remaining,
        }
        self.payload = payload
        super().__init__(status_code=402, detail=payload)


def _tenant_slug(username: str, user_id: int) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", username.strip().lower()).strip("-")
    return slug or f"user-{user_id}"


def _create_tenant_slug(db: Session, username: str, user_id: int) -> str:
    base = _tenant_slug(username, user_id)
    slug = base
    suffix = 2
    while db.scalar(select(Tenant).where(Tenant.slug == slug)) is not None:
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


def _safe_idempotency_key(value: str) -> str:
    text = (value or "").strip()
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    prefix = re.sub(r"[^a-zA-Z0-9_.:-]+", "-", text[:48]).strip("-._:") or "usage"
    return f"{prefix}:sha256:{digest}"


def get_or_create_default_tenant_context(db: Session, user_id: int, *, commit: bool = True) -> TenantContext:
    membership = db.scalar(
        select(TenantMember)
        .where(TenantMember.user_id == user_id, TenantMember.status == "active")
        .order_by(TenantMember.id)
    )
    if membership is not None:
        tenant = db.get(Tenant, membership.tenant_id)
        if tenant is not None:
            _ensure_beta_credit_accounts(db, tenant.id)
            return TenantContext(tenant=tenant, membership=membership)

    from backend.app.models import User

    user = db.get(User, user_id)
    if user is None:
        raise ValueError("User not found")

    tenant = Tenant(name=f"{user.username} 的工作空间", slug=_create_tenant_slug(db, user.username, user.id), kind="beta", status="active")
    db.add(tenant)
    db.flush()
    membership = TenantMember(tenant_id=tenant.id, user_id=user.id, role="owner", status="active")
    db.add(membership)
    db.flush()
    _ensure_beta_credit_accounts(db, tenant.id)
    if commit:
        db.commit()
        db.refresh(tenant)
        db.refresh(membership)
    return TenantContext(tenant=tenant, membership=membership)


def _ensure_beta_credit_accounts(db: Session, tenant_id: int) -> None:
    existing = set(db.scalars(select(BetaCreditAccount.bucket).where(BetaCreditAccount.tenant_id == tenant_id)).all())
    for bucket, total in BETA_DEFAULT_BUCKETS.items():
        if bucket not in existing:
            db.add(BetaCreditAccount(tenant_id=tenant_id, bucket=bucket, total=total, remaining=total, status="active"))
    db.flush()


class UsageQuotaService:
    def __init__(self, db: Session):
        self.db = db

    def get_balance(self, tenant_id: int) -> dict[str, UsageBucketBalance]:
        _ensure_beta_credit_accounts(self.db, tenant_id)
        accounts = self.db.scalars(
            select(BetaCreditAccount).where(
                BetaCreditAccount.tenant_id == tenant_id,
                BetaCreditAccount.bucket.in_(BETA_DEFAULT_BUCKETS.keys()),
            )
        ).all()
        return {
            account.bucket: UsageBucketBalance(
                bucket=account.bucket,
                total=account.total,
                remaining=account.remaining,
                status=account.status,
            )
            for account in accounts
        }

    def adjust_bucket(self, tenant_id: int, bucket: str, *, total: int, reason: str = "") -> BetaCreditAccount:
        account = self._get_account(tenant_id, bucket)
        account.total = total
        account.remaining = total
        self.db.add(
            UsageLedger(
                tenant_id=tenant_id,
                user_id=None,
                feature_key=f"usage.adjust.{bucket}",
                bucket=bucket,
                operation="adjust",
                amount=total,
                balance_after=account.remaining,
                status="completed",
                idempotency_key=f"adjust:{bucket}:{account.id}:{total}",
                failure_reason=reason,
            )
        )
        self.db.commit()
        self.db.refresh(account)
        return account

    def reserve(
        self,
        *,
        tenant_id: int,
        user_id: int,
        feature_key: str,
        bucket: str,
        amount: int,
        idempotency_key: str,
        request_summary: dict | None = None,
        task_id: int | None = None,
        resource_type: str = "",
        resource_id: int | None = None,
        provider: str = "",
        model_config_id: int | None = None,
        external_request_id: str = "",
    ) -> UsageLedger:
        safe_idempotency_key = _safe_idempotency_key(idempotency_key)
        existing = self._find_reservation(tenant_id, feature_key, safe_idempotency_key)
        if existing is not None:
            return existing

        account = self._get_account(tenant_id, bucket)
        if account.status != "active":
            raise ValueError(f"Usage bucket is not active: {bucket}")
        if account.remaining < amount:
            raise UsageQuotaInsufficientError(feature_key=feature_key, bucket=bucket, required=amount, remaining=account.remaining)

        updated = self.db.execute(
            update(BetaCreditAccount)
            .where(
                BetaCreditAccount.id == account.id,
                BetaCreditAccount.status == "active",
                BetaCreditAccount.remaining >= amount,
            )
            .values(remaining=BetaCreditAccount.remaining - amount)
        )
        if updated.rowcount != 1:
            self.db.refresh(account)
            if account.status != "active":
                raise ValueError(f"Usage bucket is not active: {bucket}")
            raise UsageQuotaInsufficientError(feature_key=feature_key, bucket=bucket, required=amount, remaining=account.remaining)
        self.db.refresh(account)
        ledger = UsageLedger(
            tenant_id=tenant_id,
            user_id=user_id,
            feature_key=feature_key,
            bucket=bucket,
            operation="reserve",
            amount=amount,
            balance_after=account.remaining,
            status="reserved",
            idempotency_key=safe_idempotency_key,
            task_id=task_id,
            resource_type=resource_type,
            resource_id=resource_id,
            provider=provider,
            model_config_id=model_config_id,
            external_request_id=external_request_id,
            request_summary=request_summary,
        )
        self.db.add(ledger)
        self.db.commit()
        self.db.refresh(ledger)
        return ledger

    def commit(self, reservation_id: int) -> UsageLedger:
        reservation = self.db.get(UsageLedger, reservation_id)
        if reservation is None or reservation.operation != "reserve":
            raise ValueError("Usage reservation not found")
        existing = self._find_followup(reservation.id, "commit")
        if existing is not None:
            return existing
        if self._find_followup(reservation.id, "refund") is not None or reservation.status == "refunded":
            raise ValueError("Usage reservation has already been refunded")
        if reservation.status not in {"reserved", "committed"}:
            raise ValueError("Usage reservation is not active")
        reservation.status = "committed"
        ledger = UsageLedger(
            tenant_id=reservation.tenant_id,
            user_id=reservation.user_id,
            feature_key=f"{reservation.feature_key}.commit",
            bucket=reservation.bucket,
            operation="commit",
            amount=reservation.amount,
            balance_after=reservation.balance_after,
            status="committed",
            idempotency_key=f"commit:{reservation.id}",
            reservation_id=reservation.id,
            task_id=reservation.task_id,
            resource_type=reservation.resource_type,
            resource_id=reservation.resource_id,
            provider=reservation.provider,
            model_config_id=reservation.model_config_id,
            external_request_id=reservation.external_request_id,
            request_summary=reservation.request_summary,
        )
        self.db.add(ledger)
        self.db.commit()
        self.db.refresh(ledger)
        return ledger

    def refund(self, reservation_id: int, failure_reason: str = "") -> UsageLedger:
        reservation = self.db.get(UsageLedger, reservation_id)
        if reservation is None or reservation.operation != "reserve":
            raise ValueError("Usage reservation not found")
        existing = self._find_followup(reservation.id, "refund")
        if existing is not None:
            return existing
        if self._find_followup(reservation.id, "commit") is not None or reservation.status == "committed":
            raise ValueError("Usage reservation has already been committed")
        if reservation.status not in {"reserved", "refunded"}:
            raise ValueError("Usage reservation is not active")

        account = self._get_account(reservation.tenant_id, reservation.bucket)
        account.remaining += reservation.amount
        reservation.status = "refunded"
        ledger = UsageLedger(
            tenant_id=reservation.tenant_id,
            user_id=reservation.user_id,
            feature_key=f"{reservation.feature_key}.refund",
            bucket=reservation.bucket,
            operation="refund",
            amount=reservation.amount,
            balance_after=account.remaining,
            status="refunded",
            idempotency_key=f"refund:{reservation.id}",
            reservation_id=reservation.id,
            task_id=reservation.task_id,
            resource_type=reservation.resource_type,
            resource_id=reservation.resource_id,
            provider=reservation.provider,
            model_config_id=reservation.model_config_id,
            external_request_id=reservation.external_request_id,
            request_summary=reservation.request_summary,
            failure_reason=failure_reason,
        )
        self.db.add(ledger)
        self.db.commit()
        self.db.refresh(ledger)
        return ledger

    def _get_account(self, tenant_id: int, bucket: str) -> BetaCreditAccount:
        _ensure_beta_credit_accounts(self.db, tenant_id)
        account = self.db.scalar(
            select(BetaCreditAccount).where(BetaCreditAccount.tenant_id == tenant_id, BetaCreditAccount.bucket == bucket)
        )
        if account is None:
            raise ValueError(f"Unknown usage bucket: {bucket}")
        return account

    def _find_reservation(self, tenant_id: int, feature_key: str, idempotency_key: str) -> UsageLedger | None:
        return self.db.scalar(
            select(UsageLedger).where(
                UsageLedger.tenant_id == tenant_id,
                UsageLedger.feature_key == feature_key,
                UsageLedger.idempotency_key == idempotency_key,
                UsageLedger.operation == "reserve",
            )
        )

    def _find_followup(self, reservation_id: int, operation: str) -> UsageLedger | None:
        return self.db.scalar(
            select(UsageLedger).where(UsageLedger.reservation_id == reservation_id, UsageLedger.operation == operation)
        )

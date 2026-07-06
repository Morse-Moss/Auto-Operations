from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.time import shanghai_now
from backend.app.models import BetaConcurrencyLease


IMAGE_GENERATION_USER_LIMIT = 1
IMAGE_GENERATION_TENANT_LIMIT = 2
ANALYSIS_REPORT_TENANT_LIMIT = 1
DEFAULT_LEASE_TTL = timedelta(minutes=30)


class BetaConcurrencyLimitExceeded(HTTPException):
    def __init__(self, *, bucket: str, scope: str, limit: int) -> None:
        payload = {
            "code": "beta_concurrency_limit_exceeded",
            "message": "Too many concurrent beta tasks",
            "bucket": bucket,
            "scope": scope,
            "limit": limit,
        }
        self.payload = payload
        super().__init__(status_code=429, detail=payload)


class BetaConcurrencyService:
    def __init__(self, db: Session):
        self.db = db

    def acquire(
        self,
        *,
        tenant_id: int,
        user_id: int,
        bucket: str,
        scope: str,
        slot_number: int,
        expires_at: datetime,
        feature_key: str = "",
        idempotency_key: str = "",
        task_id: int | None = None,
    ) -> BetaConcurrencyLease:
        self.expire_stale(now=shanghai_now())
        limit = self._limit_for(bucket=bucket, scope=scope)
        active_key = self._active_key(
            tenant_id=tenant_id,
            user_id=user_id,
            bucket=bucket,
            scope=scope,
            slot_number=slot_number,
        )
        lease = BetaConcurrencyLease(
            tenant_id=tenant_id,
            user_id=user_id,
            bucket=bucket,
            scope=scope,
            slot_number=slot_number,
            status="active",
            active_key=active_key,
            feature_key=feature_key,
            idempotency_key=idempotency_key,
            task_id=task_id,
            expires_at=expires_at,
        )
        self.db.add(lease)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise BetaConcurrencyLimitExceeded(bucket=bucket, scope=scope, limit=limit) from exc
        self.db.refresh(lease)
        return lease

    def acquire_first_available(
        self,
        *,
        tenant_id: int,
        user_id: int,
        bucket: str,
        scope: str,
        limit: int,
        ttl: timedelta = DEFAULT_LEASE_TTL,
        feature_key: str = "",
        idempotency_key: str = "",
        task_id: int | None = None,
    ) -> BetaConcurrencyLease:
        self.expire_stale(now=shanghai_now())
        expires_at = shanghai_now() + ttl
        last_error: BetaConcurrencyLimitExceeded | None = None
        for slot_number in range(1, limit + 1):
            try:
                return self.acquire(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    bucket=bucket,
                    scope=scope,
                    slot_number=slot_number,
                    expires_at=expires_at,
                    feature_key=feature_key,
                    idempotency_key=idempotency_key,
                    task_id=task_id,
                )
            except BetaConcurrencyLimitExceeded as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise BetaConcurrencyLimitExceeded(bucket=bucket, scope=scope, limit=limit)

    def release(self, lease_id: int | None, *, reason: str = "") -> BetaConcurrencyLease | None:
        if lease_id is None:
            return None
        lease = self.db.get(BetaConcurrencyLease, lease_id)
        if lease is None:
            return None
        if lease.status != "active":
            return lease
        lease.status = "released"
        lease.active_key = None
        lease.released_at = shanghai_now()
        lease.release_reason = reason
        self.db.commit()
        self.db.refresh(lease)
        return lease

    def expire_stale(self, *, now: datetime | None = None) -> int:
        current = now or shanghai_now()
        leases = self.db.scalars(
            select(BetaConcurrencyLease).where(
                BetaConcurrencyLease.status == "active",
                BetaConcurrencyLease.expires_at <= current,
            )
        ).all()
        for lease in leases:
            lease.status = "expired"
            lease.active_key = None
            lease.released_at = current
            lease.release_reason = "expired"
        if leases:
            self.db.commit()
        return len(leases)

    @staticmethod
    def _active_key(*, tenant_id: int, user_id: int, bucket: str, scope: str, slot_number: int) -> str:
        owner_id = user_id if scope == "user" else tenant_id
        return f"{scope}:{owner_id}:{bucket}:{slot_number}"

    @staticmethod
    def _limit_for(*, bucket: str, scope: str) -> int:
        if bucket == "image_generation" and scope == "user":
            return IMAGE_GENERATION_USER_LIMIT
        if bucket == "image_generation" and scope == "tenant":
            return IMAGE_GENERATION_TENANT_LIMIT
        if bucket == "analysis_report" and scope == "tenant":
            return ANALYSIS_REPORT_TENANT_LIMIT
        return 1


class BetaConcurrencyLeaseGuard:
    def __init__(self, db: Session, lease_ids: list[int]):
        self.db = db
        self.lease_ids = lease_ids

    def release(self, *, reason: str = "") -> None:
        service = BetaConcurrencyService(self.db)
        for lease_id in self.lease_ids:
            service.release(lease_id, reason=reason)


def acquire_image_generation_leases(
    *,
    db: Session,
    tenant_id: int,
    user_id: int,
    feature_key: str,
    idempotency_key: str,
    task_id: int | None = None,
) -> BetaConcurrencyLeaseGuard:
    service = BetaConcurrencyService(db)
    user_lease = service.acquire_first_available(
        tenant_id=tenant_id,
        user_id=user_id,
        bucket="image_generation",
        scope="user",
        limit=IMAGE_GENERATION_USER_LIMIT,
        feature_key=feature_key,
        idempotency_key=idempotency_key,
        task_id=task_id,
    )
    try:
        tenant_lease = service.acquire_first_available(
            tenant_id=tenant_id,
            user_id=user_id,
            bucket="image_generation",
            scope="tenant",
            limit=IMAGE_GENERATION_TENANT_LIMIT,
            feature_key=feature_key,
            idempotency_key=idempotency_key,
            task_id=task_id,
        )
    except Exception:
        service.release(user_lease.id, reason="tenant slot acquisition failed")
        raise
    return BetaConcurrencyLeaseGuard(db, [user_lease.id, tenant_lease.id])


def acquire_analysis_report_lease(
    *,
    db: Session,
    tenant_id: int,
    user_id: int,
    feature_key: str,
    idempotency_key: str,
    task_id: int | None = None,
) -> BetaConcurrencyLeaseGuard:
    lease = BetaConcurrencyService(db).acquire_first_available(
        tenant_id=tenant_id,
        user_id=user_id,
        bucket="analysis_report",
        scope="tenant",
        limit=ANALYSIS_REPORT_TENANT_LIMIT,
        feature_key=feature_key,
        idempotency_key=idempotency_key,
        task_id=task_id,
    )
    return BetaConcurrencyLeaseGuard(db, [lease.id])

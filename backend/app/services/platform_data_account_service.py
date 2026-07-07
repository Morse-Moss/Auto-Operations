from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.security import decrypt_text
from backend.app.core.time import shanghai_now
from backend.app.models import AccountCookieVersion, PlatformAccount, UsageLedger, User

DATA_ACCOUNT_PLATFORM = "huitun"
DATA_ACCOUNT_SUB_TYPE = "main"
NOTE_SEARCH_FEATURE_KEY = "xhs.data_acquisition.note_search"
NOTE_SEARCH_BUCKET = "data_acquisition_note_search"
NOTE_SEARCH_DAILY_USER_LIMIT = 20
NOTE_SEARCH_DAILY_PLATFORM_LIMIT = 200


def _today_start() -> datetime:
    now = shanghai_now()
    return datetime(now.year, now.month, now.day)


def resolve_platform_data_account(
    db: Session,
    account_id: int | None = None,
    *,
    allow_explicit_account: bool = False,
) -> PlatformAccount | None:
    statement = (
        select(PlatformAccount)
        .join(User, User.id == PlatformAccount.user_id)
        .where(
            PlatformAccount.platform == DATA_ACCOUNT_PLATFORM,
            PlatformAccount.sub_type == DATA_ACCOUNT_SUB_TYPE,
            PlatformAccount.status != "deleted",
            User.role == "admin",
        )
    )
    if account_id is not None and allow_explicit_account:
        statement = statement.where(PlatformAccount.id == account_id)
    else:
        statement = statement.where(PlatformAccount.status == "active")
    return db.scalars(statement.order_by(PlatformAccount.updated_at.desc(), PlatformAccount.id.desc())).first()


def get_platform_data_account_cookie_text(
    db: Session,
    account_id: int | None = None,
    *,
    allow_explicit_account: bool = False,
) -> tuple[PlatformAccount, str]:
    account = resolve_platform_data_account(db, account_id, allow_explicit_account=allow_explicit_account)
    if account is None and not allow_explicit_account:
        account = db.scalars(
            select(PlatformAccount)
            .join(User, User.id == PlatformAccount.user_id)
            .where(
                PlatformAccount.platform == DATA_ACCOUNT_PLATFORM,
                PlatformAccount.sub_type == DATA_ACCOUNT_SUB_TYPE,
                PlatformAccount.status != "deleted",
                User.role == "admin",
            )
            .order_by(PlatformAccount.updated_at.desc(), PlatformAccount.id.desc())
        ).first()
    if account is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="数据账号未配置，请联系管理员。")
    if account.status != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="数据账号登录状态已过期，请联系管理员更新。")
    cookie_version = db.scalars(
        select(AccountCookieVersion)
        .where(AccountCookieVersion.platform_account_id == account.id)
        .order_by(AccountCookieVersion.created_at.desc())
    ).first()
    if cookie_version is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="数据账号登录状态已过期，请联系管理员更新。")
    return account, decrypt_text(cookie_version.encrypted_cookies)


def _note_search_count(db: Session, *, user_id: int | None = None) -> int:
    statement = select(func.count(UsageLedger.id)).where(
        UsageLedger.feature_key == NOTE_SEARCH_FEATURE_KEY,
        UsageLedger.status == "completed",
        UsageLedger.created_at >= _today_start(),
    )
    if user_id is not None:
        statement = statement.where(UsageLedger.user_id == user_id)
    return int(db.scalar(statement) or 0)


def enforce_note_search_daily_limit(db: Session, *, user_id: int) -> None:
    user_count = _note_search_count(db, user_id=user_id)
    if user_count >= NOTE_SEARCH_DAILY_USER_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "data_acquisition_daily_limit_exceeded",
                "scope": "user",
                "limit": NOTE_SEARCH_DAILY_USER_LIMIT,
                "used": user_count,
                "message": "今日数据获取次数已用完，请明天再试。",
            },
        )
    platform_count = _note_search_count(db)
    if platform_count >= NOTE_SEARCH_DAILY_PLATFORM_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "data_acquisition_daily_limit_exceeded",
                "scope": "platform",
                "limit": NOTE_SEARCH_DAILY_PLATFORM_LIMIT,
                "used": platform_count,
                "message": "今日平台数据获取额度已用完，请明天再试。",
            },
        )


def record_note_search_usage(
    db: Session,
    *,
    tenant_id: int,
    user_id: int,
    task_id: int,
    run_id: int,
    keyword: str,
    limit: int,
) -> UsageLedger:
    used_after = _note_search_count(db, user_id=user_id) + 1
    ledger = UsageLedger(
        tenant_id=tenant_id,
        user_id=user_id,
        feature_key=NOTE_SEARCH_FEATURE_KEY,
        bucket=NOTE_SEARCH_BUCKET,
        operation="commit",
        amount=1,
        balance_after=max(0, NOTE_SEARCH_DAILY_USER_LIMIT - used_after),
        status="completed",
        idempotency_key=f"data-acquisition-run:{run_id}",
        task_id=task_id,
        resource_type="data_acquisition_run",
        resource_id=run_id,
        provider=DATA_ACCOUNT_PLATFORM,
        request_summary={"keyword": keyword, "limit": limit},
    )
    db.add(ledger)
    db.flush()
    return ledger

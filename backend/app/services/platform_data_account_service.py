from __future__ import annotations

from dataclasses import asdict, dataclass

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.security import decrypt_text
from backend.app.models import AccountCookieVersion, PlatformAccount, User

DATA_ACCOUNT_PLATFORM = "huitun"
DATA_ACCOUNT_SUB_TYPE = "main"
DATA_ACCOUNT_NOT_READY_CODE = "data_account_not_ready"
DATA_ACCOUNT_READY_MESSAGE = "数据获取服务已就绪。"
DATA_ACCOUNT_MISSING_MESSAGE = "数据账号未配置，请让管理员完成登录后再重试。"
DATA_ACCOUNT_EXPIRED_MESSAGE = "数据账号登录状态已过期，请让管理员重新登录后再重试。"
PUBLIC_DATA_ACCOUNT_NOT_READY_MESSAGE = "数据获取服务未就绪，请联系管理员处理后再重试。"
PUBLIC_DATA_ACCOUNT_NEXT_ACTION = "联系管理员处理。"


@dataclass(frozen=True)
class DataAccountReadiness:
    available: bool
    status: str
    message: str
    next_action: str = ""

    def to_dict(self) -> dict[str, str | bool]:
        return asdict(self)

    def for_user(self, user: User) -> "DataAccountReadiness":
        if self.available or user.role == "admin":
            return self
        return DataAccountReadiness(
            available=False,
            status=self.status,
            message=PUBLIC_DATA_ACCOUNT_NOT_READY_MESSAGE,
            next_action=PUBLIC_DATA_ACCOUNT_NEXT_ACTION,
        )


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


def _latest_non_deleted_data_account(db: Session) -> PlatformAccount | None:
    return db.scalars(
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


def get_data_account_readiness(
    db: Session,
    account_id: int | None = None,
    *,
    current_user: User | None = None,
) -> DataAccountReadiness:
    account = resolve_platform_data_account(db, account_id)
    if account is None:
        latest_account = _latest_non_deleted_data_account(db)
        if latest_account is None:
            readiness = DataAccountReadiness(
                available=False,
                status="missing",
                message=DATA_ACCOUNT_MISSING_MESSAGE,
                next_action="联系管理员完成登录。",
            )
            return readiness.for_user(current_user) if current_user is not None else readiness
        readiness = DataAccountReadiness(
            available=False,
            status="expired",
            message=DATA_ACCOUNT_EXPIRED_MESSAGE,
            next_action="联系管理员重新登录。",
        )
        return readiness.for_user(current_user) if current_user is not None else readiness
    cookie_version = db.scalars(
        select(AccountCookieVersion)
        .where(AccountCookieVersion.platform_account_id == account.id)
        .order_by(AccountCookieVersion.created_at.desc())
    ).first()
    if cookie_version is None:
        readiness = DataAccountReadiness(
            available=False,
            status="expired",
            message=DATA_ACCOUNT_EXPIRED_MESSAGE,
            next_action="联系管理员重新登录。",
        )
        return readiness.for_user(current_user) if current_user is not None else readiness
    readiness = DataAccountReadiness(
        available=True,
        status="ready",
        message=DATA_ACCOUNT_READY_MESSAGE,
        next_action="",
    )
    return readiness.for_user(current_user) if current_user is not None else readiness


def ensure_data_account_ready(
    db: Session,
    account_id: int | None = None,
    *,
    current_user: User | None = None,
) -> DataAccountReadiness:
    readiness = get_data_account_readiness(db, account_id, current_user=current_user)
    if readiness.available:
        return readiness
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": DATA_ACCOUNT_NOT_READY_CODE,
            "status": readiness.status,
            "message": readiness.message,
            "next_action": readiness.next_action,
        },
    )


def get_platform_data_account_cookie_text(
    db: Session,
    account_id: int | None = None,
    *,
    allow_explicit_account: bool = False,
) -> tuple[PlatformAccount, str]:
    account = resolve_platform_data_account(db, account_id, allow_explicit_account=allow_explicit_account)
    if account is None and not allow_explicit_account:
        account = _latest_non_deleted_data_account(db)
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

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.auto_tasks import _resolve_auto_task_account
from backend.app.core.database import Base
from backend.app.core.security import encrypt_text, hash_password
from backend.app.models import AccountCookieVersion, AutoTask, PlatformAccount, User


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def _user(db, username="owner"):
    user = User(username=username, password_hash=hash_password("secret123"))
    db.add(user)
    db.flush()
    return user


def _account(
    db,
    user_id: int,
    *,
    sub_type: str,
    status: str = "active",
    with_cookie: bool = True,
    external_user_id: str | None = None,
) -> PlatformAccount:
    account = PlatformAccount(
        user_id=user_id,
        platform="xhs",
        sub_type=sub_type,
        external_user_id=external_user_id or f"{sub_type}-{status}-{with_cookie}",
        nickname=f"{sub_type} account",
        status=status,
    )
    db.add(account)
    db.flush()
    if with_cookie:
        db.add(AccountCookieVersion(platform_account_id=account.id, encrypted_cookies=encrypt_text("a1=test; web_session=test")))
        db.flush()
    return account


def test_resolve_auto_task_account_rebinds_deleted_creator_to_active_creator_with_cookie():
    db = _session()
    user = _user(db)
    stale_creator = _account(db, user.id, sub_type="creator", status="deleted", with_cookie=False)
    active_creator = _account(db, user.id, sub_type="creator", status="active", with_cookie=True)
    pc = _account(db, user.id, sub_type="pc", status="active", with_cookie=True)
    task = AutoTask(
        user_id=user.id,
        name="auto",
        keywords=["ai"],
        pc_account_id=pc.id,
        creator_account_id=stale_creator.id,
    )
    db.add(task)
    db.flush()

    resolved = _resolve_auto_task_account(db, user, task, "creator")

    assert resolved.id == active_creator.id
    assert task.creator_account_id == active_creator.id


def test_resolve_auto_task_account_keeps_active_bound_account_with_cookie():
    db = _session()
    user = _user(db)
    bound_creator = _account(
        db,
        user.id,
        sub_type="creator",
        status="active",
        with_cookie=True,
        external_user_id="creator-bound",
    )
    other_creator = _account(
        db,
        user.id,
        sub_type="creator",
        status="active",
        with_cookie=True,
        external_user_id="creator-other",
    )
    pc = _account(db, user.id, sub_type="pc", status="active", with_cookie=True)
    task = AutoTask(
        user_id=user.id,
        name="auto",
        keywords=["ai"],
        pc_account_id=pc.id,
        creator_account_id=bound_creator.id,
    )
    db.add(task)
    db.flush()

    resolved = _resolve_auto_task_account(db, user, task, "creator")

    assert resolved.id == bound_creator.id
    assert task.creator_account_id == bound_creator.id
    assert resolved.id != other_creator.id

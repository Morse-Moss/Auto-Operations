from __future__ import annotations

import json
from datetime import datetime

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import Base
from backend.app.core.security import encrypt_text
from backend.app.models import AccountCookieVersion, PlatformAccount, User
from backend.app.services.account_service import (
    XHS_PC_RELOGIN_MESSAGE,
    get_xhs_pc_login_readiness,
    get_xhs_pc_login_readiness_map,
)


def _session(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'account-login-readiness.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    return engine, sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def _account(db, *, status: str = "active", nickname: str = "PC account") -> PlatformAccount:
    user = db.scalar(select(User).where(User.username == "readiness-owner"))
    if user is None:
        user = User(username="readiness-owner", password_hash="test")
        db.add(user)
        db.flush()
    account = PlatformAccount(
        user_id=user.id,
        platform="xhs",
        sub_type="pc",
        external_user_id=f"pc-{nickname}",
        nickname=nickname,
        status=status,
    )
    db.add(account)
    db.flush()
    return account


def _cookie(db, account: PlatformAccount, value: str, *, encrypted: bool = True, created_at: datetime | None = None):
    version = AccountCookieVersion(
        platform_account_id=account.id,
        encrypted_cookies=encrypt_text(value) if encrypted else value,
    )
    if created_at is not None:
        version.created_at = created_at
    db.add(version)
    db.flush()
    return version


@pytest.mark.parametrize(
    "cookie_value",
    [
        "{",
        json.dumps({"a1": "only-a1"}),
        json.dumps({"web_session": "   "}),
        json.dumps({"web_session": 123}),
    ],
)
def test_xhs_pc_readiness_rejects_malformed_or_missing_session_values(tmp_path, cookie_value):
    _engine, db = _session(tmp_path)
    try:
        account = _account(db)
        _cookie(db, account, cookie_value)
        db.commit()

        readiness = get_xhs_pc_login_readiness(db, account)

        assert readiness.login_ready is False
        assert readiness.login_readiness_message == XHS_PC_RELOGIN_MESSAGE
        assert readiness.cookie_text is None
    finally:
        db.close()


def test_xhs_pc_readiness_requires_cookie_active_status_and_decryptable_value(tmp_path):
    _engine, db = _session(tmp_path)
    try:
        missing = _account(db, nickname="missing")
        decrypt_failure = _account(db, nickname="decrypt-failure")
        inactive = _account(db, status="expired", nickname="inactive")
        ready = _account(db, nickname="ready")
        _cookie(db, decrypt_failure, "not-a-fernet-token", encrypted=False)
        _cookie(db, inactive, json.dumps({"web_session": "valid-but-inactive"}))
        _cookie(db, ready, json.dumps({"a1": "a1", "web_session": "  session-123  "}))
        db.commit()

        readiness = get_xhs_pc_login_readiness_map(db, [missing, decrypt_failure, inactive, ready])

        assert readiness[missing.id].login_ready is False
        assert readiness[decrypt_failure.id].login_ready is False
        assert readiness[inactive.id].login_ready is False
        assert readiness[ready.id].login_ready is True
        assert readiness[ready.id].login_readiness_message == ""
        assert readiness[ready.id].cookie_text == "a1=a1; web_session=  session-123  "
    finally:
        db.close()


def test_xhs_pc_readiness_uses_id_as_tie_breaker_for_latest_cookie(tmp_path):
    _engine, db = _session(tmp_path)
    try:
        account = _account(db)
        same_time = datetime(2026, 7, 19, 9, 0, 0)
        older_id = _cookie(db, account, json.dumps({"web_session": "older-valid"}), created_at=same_time)
        newer_id = _cookie(db, account, json.dumps({"a1": "newer-without-session"}), created_at=same_time)
        assert newer_id.id > older_id.id
        db.commit()

        readiness = get_xhs_pc_login_readiness(db, account)

        assert readiness.login_ready is False
        assert readiness.cookie_text is None
    finally:
        db.close()


def test_xhs_pc_readiness_batch_query_is_read_only_and_avoids_n_plus_one(tmp_path):
    engine, db = _session(tmp_path)
    try:
        accounts = [_account(db, nickname=f"account-{index}") for index in range(3)]
        for account in accounts:
            _cookie(db, account, json.dumps({"web_session": f"session-{account.id}"}))
        db.commit()
        before_accounts = db.execute(
            select(PlatformAccount.id, PlatformAccount.status, PlatformAccount.status_message, PlatformAccount.updated_at)
            .order_by(PlatformAccount.id)
        ).all()
        before_cookies = db.execute(
            select(AccountCookieVersion.id, AccountCookieVersion.encrypted_cookies, AccountCookieVersion.created_at)
            .order_by(AccountCookieVersion.id)
        ).all()
        cookie_selects = 0

        def count_cookie_selects(_conn, _cursor, statement, _parameters, _context, _executemany):
            nonlocal cookie_selects
            if statement.lstrip().upper().startswith("SELECT") and "account_cookie_versions" in statement:
                cookie_selects += 1

        event.listen(engine, "before_cursor_execute", count_cookie_selects)
        try:
            readiness = get_xhs_pc_login_readiness_map(db, accounts)
        finally:
            event.remove(engine, "before_cursor_execute", count_cookie_selects)

        assert all(readiness[account.id].login_ready for account in accounts)
        assert cookie_selects == 1
        assert db.execute(
            select(PlatformAccount.id, PlatformAccount.status, PlatformAccount.status_message, PlatformAccount.updated_at)
            .order_by(PlatformAccount.id)
        ).all() == before_accounts
        assert db.execute(
            select(AccountCookieVersion.id, AccountCookieVersion.encrypted_cookies, AccountCookieVersion.created_at)
            .order_by(AccountCookieVersion.id)
        ).all() == before_cookies
    finally:
        db.close()

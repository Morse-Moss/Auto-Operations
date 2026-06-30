from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend.app.api.notes import _get_owned_account
from backend.app.models import PlatformAccount, User


class _FakeDb:
    def __init__(self, account: PlatformAccount | None) -> None:
        self.account = account
        self.calls: list[tuple[type, int]] = []

    def get(self, model, identity):
        self.calls.append((model, identity))
        return self.account


def _user(user_id: int = 1) -> User:
    return User(id=user_id, username=f"user-{user_id}", password_hash="hash")


def _account(*, user_id: int = 1, platform: str = "xhs") -> PlatformAccount:
    return PlatformAccount(
        id=10,
        user_id=user_id,
        platform=platform,
        sub_type="pc",
        nickname="Account",
        status="active",
    )


def test_get_owned_account_accepts_account_for_expected_platform():
    account = _account(platform="xhs")
    db = _FakeDb(account)

    assert _get_owned_account(db, _user(), 10, expected_platform="xhs") is account
    assert db.calls == [(PlatformAccount, 10)]


def test_get_owned_account_rejects_account_from_other_user():
    db = _FakeDb(_account(user_id=2, platform="xhs"))

    with pytest.raises(HTTPException) as exc:
        _get_owned_account(db, _user(1), 10, expected_platform="xhs")

    assert exc.value.status_code == 404
    assert exc.value.detail == "Account not found"


def test_get_owned_account_rejects_account_for_unexpected_platform():
    db = _FakeDb(_account(user_id=1, platform="wechat_official"))

    with pytest.raises(HTTPException) as exc:
        _get_owned_account(db, _user(1), 10, expected_platform="xhs")

    assert exc.value.status_code == 404
    assert exc.value.detail == "Account not found"

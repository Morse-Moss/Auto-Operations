from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.security import decrypt_text, encrypt_text
from backend.app.core.time import shanghai_now
from backend.app.models import AccountCookieVersion, PlatformAccount
from xhs_utils.cookie_util import trans_cookies

DATA_ACCOUNT_DISPLAY_NAME = "数据账号"
PROFILE_SYNC_PENDING = "pending"
PROFILE_SYNC_PENDING_MESSAGE = "账号已登录，完整资料待同步。"
XHS_PC_RELOGIN_MESSAGE = "账号登录信息不可用，请重新登录"
DATA_ACCOUNT_INTERNAL_TEXT_REPLACEMENTS = (
    ("第三方数据源", DATA_ACCOUNT_DISPLAY_NAME),
    ("灰豚", DATA_ACCOUNT_DISPLAY_NAME),
    ("Huitun", DATA_ACCOUNT_DISPLAY_NAME),
    ("huitun", DATA_ACCOUNT_DISPLAY_NAME),
    ("extData", ""),
    ("connector", ""),
    ("supplier", ""),
    ("internal API", ""),
    ("Cookie", "登录凭证"),
    ("cookie", "登录凭证"),
)


def account_profile_from_user_info(user_info: dict[str, Any]) -> dict[str, Any]:
    profile = user_info.get("profile")
    if isinstance(profile, dict):
        return profile
    return {}


def _account_profile(account: PlatformAccount) -> dict[str, Any]:
    try:
        profile = json.loads(account.profile_json or "{}")
    except json.JSONDecodeError:
        return {}
    return profile if isinstance(profile, dict) else {}


def _has_value(value: Any) -> bool:
    return value not in (None, "", [], {})


def _account_profile_score(account: PlatformAccount) -> int:
    profile = _account_profile(account)
    profile_values = [
        value
        for key, value in profile.items()
        if key != "profile_sync_status" and _has_value(value)
    ]
    return (
        (4 if _has_value(account.nickname) else 0)
        + (2 if _has_value(account.avatar_url) else 0)
        + len(profile_values)
    )


def _merge_profile_values(
    source_profile: dict[str, Any],
    incoming_profile: dict[str, Any],
) -> dict[str, Any]:
    merged = {
        key: value
        for key, value in source_profile.items()
        if key != "profile_sync_status" and _has_value(value)
    }
    merged.update(
        {
            key: value
            for key, value in incoming_profile.items()
            if key != "profile_sync_status" and _has_value(value)
        }
    )
    if incoming_profile.get("profile_sync_status") == PROFILE_SYNC_PENDING:
        merged["profile_sync_status"] = PROFILE_SYNC_PENDING
    return merged


def _merge_user_info_with_account(
    user_info: dict[str, Any],
    source: PlatformAccount | None,
) -> dict[str, Any]:
    if source is None:
        return user_info
    return {
        **user_info,
        "nickname": user_info.get("nickname") or source.nickname or "",
        "avatar_url": user_info.get("avatar_url") or source.avatar_url or "",
        "profile": _merge_profile_values(
            _account_profile(source),
            account_profile_from_user_info(user_info),
        ),
    }


def _profile_sync_is_pending(profile: dict[str, Any]) -> bool:
    return profile.get("profile_sync_status") == PROFILE_SYNC_PENDING


def _best_identity_profile_source(
    accounts: list[PlatformAccount],
    *,
    exclude_account_id: int | None = None,
) -> PlatformAccount | None:
    candidates = [
        account
        for account in accounts
        if account.id != exclude_account_id
        and account.status != "deleted"
        and _account_profile_score(account) > 0
    ]
    return max(candidates, key=_account_profile_score, default=None)


def decode_cookie_text(value: str) -> dict[str, Any]:
    stripped = value.strip()
    if not stripped:
        return {}
    if stripped.startswith("{"):
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    return trans_cookies(stripped)


def cookie_header_from_text(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return ""
    if not stripped.startswith("{"):
        return stripped
    cookies = decode_cookie_text(stripped)
    return "; ".join(f"{key}={cookie_value}" for key, cookie_value in cookies.items())


def latest_cookie_version(db: Session, account_id: int) -> AccountCookieVersion | None:
    return db.scalars(
        select(AccountCookieVersion)
        .where(AccountCookieVersion.platform_account_id == account_id)
        .order_by(AccountCookieVersion.created_at.desc(), AccountCookieVersion.id.desc())
    ).first()


def latest_cookie_header(db: Session, account_id: int) -> str | None:
    cookie_version = latest_cookie_version(db, account_id)
    if cookie_version is None:
        return None
    return cookie_header_from_text(decrypt_text(cookie_version.encrypted_cookies))


@dataclass(frozen=True)
class XhsPcLoginReadiness:
    login_ready: bool
    login_readiness_message: str
    cookie_text: str | None = None


def _unready_xhs_pc_login() -> XhsPcLoginReadiness:
    return XhsPcLoginReadiness(
        login_ready=False,
        login_readiness_message=XHS_PC_RELOGIN_MESSAGE,
    )


def _evaluate_xhs_pc_login_readiness(
    account: PlatformAccount,
    cookie_version: AccountCookieVersion | None,
) -> XhsPcLoginReadiness:
    if account.status != "active" or cookie_version is None:
        return _unready_xhs_pc_login()
    try:
        decrypted_cookie_text = decrypt_text(cookie_version.encrypted_cookies)
        cookies = decode_cookie_text(decrypted_cookie_text)
        web_session = cookies.get("web_session")
        if not isinstance(web_session, str) or not web_session.strip():
            return _unready_xhs_pc_login()
        cookie_text = cookie_header_from_text(decrypted_cookie_text)
    except Exception:
        return _unready_xhs_pc_login()
    return XhsPcLoginReadiness(
        login_ready=True,
        login_readiness_message="",
        cookie_text=cookie_text,
    )


def get_xhs_pc_login_readiness_map(
    db: Session,
    accounts: list[PlatformAccount],
) -> dict[int, XhsPcLoginReadiness]:
    pc_accounts = [
        account
        for account in accounts
        if account.id is not None and account.platform == "xhs" and account.sub_type == "pc"
    ]
    if not pc_accounts:
        return {}

    account_ids = [account.id for account in pc_accounts]
    cookie_versions = db.scalars(
        select(AccountCookieVersion)
        .where(AccountCookieVersion.platform_account_id.in_(account_ids))
        .order_by(
            AccountCookieVersion.platform_account_id.asc(),
            AccountCookieVersion.created_at.desc(),
            AccountCookieVersion.id.desc(),
        )
    ).all()
    latest_cookie_by_account_id: dict[int, AccountCookieVersion] = {}
    for cookie_version in cookie_versions:
        latest_cookie_by_account_id.setdefault(cookie_version.platform_account_id, cookie_version)

    return {
        account.id: _evaluate_xhs_pc_login_readiness(
            account,
            latest_cookie_by_account_id.get(account.id),
        )
        for account in pc_accounts
    }


def get_xhs_pc_login_readiness(
    db: Session,
    account: PlatformAccount,
) -> XhsPcLoginReadiness:
    return get_xhs_pc_login_readiness_map(db, [account]).get(
        account.id,
        _unready_xhs_pc_login(),
    )


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def enrich_user_info_with_xhs_self_profile(user_info: dict[str, Any], response: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(response, dict) or response.get("success") is False:
        return user_info
    data = response.get("data")
    if not isinstance(data, dict):
        return user_info
    basic_info = data.get("basic_info")
    if not isinstance(basic_info, dict):
        basic_info = {}

    interaction_counts: dict[str, Any] = {}
    interactions = data.get("interactions")
    if isinstance(interactions, list):
        for item in interactions:
            if not isinstance(item, dict):
                continue
            interaction_type = item.get("type")
            if interaction_type:
                interaction_counts[str(interaction_type)] = _first_present(item.get("i18n_count"), item.get("count"))

    existing_profile = {
        key: value
        for key, value in account_profile_from_user_info(user_info).items()
        if key != "profile_sync_status"
    }
    profile = {
        **existing_profile,
        "red_id": _first_present(basic_info.get("red_id"), existing_profile.get("red_id"), ""),
        "description": _first_present(basic_info.get("desc"), existing_profile.get("description"), ""),
        "ip_location": _first_present(basic_info.get("ip_location"), existing_profile.get("ip_location"), ""),
        "gender": _first_present(basic_info.get("gender"), existing_profile.get("gender")),
        "followers": _first_present(interaction_counts.get("fans"), existing_profile.get("followers")),
        "following": _first_present(interaction_counts.get("follows"), existing_profile.get("following")),
        "likes": _first_present(interaction_counts.get("interaction"), existing_profile.get("likes")),
        "raw": response,
    }
    return {
        **user_info,
        "nickname": _first_present(basic_info.get("nickname"), user_info.get("nickname"), ""),
        "avatar_url": _first_present(basic_info.get("images"), basic_info.get("imageb"), user_info.get("avatar_url"), ""),
        "profile": profile,
    }


def _public_data_account_text(value: Any, fallback: str = DATA_ACCOUNT_DISPLAY_NAME) -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    for source, replacement in DATA_ACCOUNT_INTERNAL_TEXT_REPLACEMENTS:
        text = text.replace(source, replacement)
    text = text.replace(f"{DATA_ACCOUNT_DISPLAY_NAME}账号", DATA_ACCOUNT_DISPLAY_NAME)
    text = text.replace(f"{DATA_ACCOUNT_DISPLAY_NAME}帐号", DATA_ACCOUNT_DISPLAY_NAME)
    while f"{DATA_ACCOUNT_DISPLAY_NAME}{DATA_ACCOUNT_DISPLAY_NAME}" in text:
        text = text.replace(f"{DATA_ACCOUNT_DISPLAY_NAME}{DATA_ACCOUNT_DISPLAY_NAME}", DATA_ACCOUNT_DISPLAY_NAME)
    text = " ".join(text.split())
    return text or fallback


def _public_data_account_external_id(value: Any, account_id: int | None) -> str:
    text = str(value or "").strip()
    lowered = text.lower()
    if not text or "huitun" in lowered or "灰豚" in text:
        return f"{DATA_ACCOUNT_DISPLAY_NAME} {account_id}" if account_id else DATA_ACCOUNT_DISPLAY_NAME
    return _public_data_account_text(text, fallback=f"{DATA_ACCOUNT_DISPLAY_NAME} {account_id}" if account_id else DATA_ACCOUNT_DISPLAY_NAME)


def serialize_account(account: PlatformAccount, action: str | None = None) -> dict[str, Any]:
    profile = _account_profile(account)

    nickname = account.nickname
    external_user_id = account.external_user_id
    status_message = account.status_message
    if account.platform == "huitun":
        nickname = _public_data_account_text(account.nickname)
        external_user_id = _public_data_account_external_id(account.external_user_id, account.id)
        status_message = _public_data_account_text(account.status_message, fallback="")

    payload = {
        "id": account.id,
        "platform": account.platform,
        "sub_type": account.sub_type,
        "external_user_id": external_user_id,
        "nickname": nickname,
        "avatar_url": account.avatar_url,
        "status": account.status,
        "status_message": status_message,
        "profile": profile,
        "created_at": account.created_at.isoformat() if account.created_at else None,
        "updated_at": (account.updated_at or account.created_at).isoformat() if (account.updated_at or account.created_at) else None,
    }
    if action:
        payload["action"] = action
    return payload


def serialize_accounts(
    accounts: list[PlatformAccount],
    login_readiness_by_account_id: dict[int, XhsPcLoginReadiness] | None = None,
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for account in accounts:
        payload = serialize_account(account)
        readiness = (login_readiness_by_account_id or {}).get(account.id)
        if readiness is not None:
            payload["login_ready"] = readiness.login_ready
            payload["login_readiness_message"] = readiness.login_readiness_message
        profile = payload["profile"]
        has_profile_details = bool(
            payload["nickname"]
            or payload["avatar_url"]
            or any(
                _has_value(value)
                for key, value in profile.items()
                if key != "profile_sync_status"
            )
        )
        used_identity_profile_fallback = False
        if account.platform == "xhs" and account.external_user_id:
            identity_accounts = [
                candidate
                for candidate in accounts
                if candidate.user_id == account.user_id
                and candidate.platform == account.platform
                and candidate.external_user_id == account.external_user_id
            ]
            source = _best_identity_profile_source(
                identity_accounts,
                exclude_account_id=account.id,
            )
            if source is not None:
                source_payload = serialize_account(source)
                used_identity_profile_fallback = bool(
                    (not _has_value(payload["nickname"]) and _has_value(source_payload["nickname"]))
                    or (not _has_value(payload["avatar_url"]) and _has_value(source_payload["avatar_url"]))
                    or any(
                        key != "profile_sync_status"
                        and _has_value(value)
                        and not _has_value(profile.get(key))
                        for key, value in source_payload["profile"].items()
                    )
                )
                payload["nickname"] = payload["nickname"] or source_payload["nickname"]
                payload["avatar_url"] = payload["avatar_url"] or source_payload["avatar_url"]
                payload["profile"] = _merge_profile_values(
                    source_payload["profile"],
                    profile,
                )
        profile_sync_pending = account.platform == "xhs" and (
            _profile_sync_is_pending(profile)
            or (bool(account.external_user_id) and not has_profile_details)
            or used_identity_profile_fallback
        )
        if profile_sync_pending:
            payload["profile"]["profile_sync_status"] = PROFILE_SYNC_PENDING
            if account.status == "active" and not payload["status_message"]:
                payload["status_message"] = PROFILE_SYNC_PENDING_MESSAGE
        payloads.append(payload)
    return payloads


def upsert_platform_account_from_login(
    *,
    db: Session,
    user_id: int,
    platform: str,
    sub_type: str,
    user_info: dict[str, Any],
    cookies_text: str,
) -> tuple[PlatformAccount, str]:
    external_user_id = user_info.get("external_user_id", "") or ""
    account = None
    if external_user_id:
        account = db.scalar(
            select(PlatformAccount).where(
                PlatformAccount.user_id == user_id,
                PlatformAccount.platform == platform,
                PlatformAccount.sub_type == sub_type,
                PlatformAccount.external_user_id == external_user_id,
            )
        )

    if platform == "xhs" and external_user_id:
        identity_accounts = list(
            db.scalars(
                select(PlatformAccount).where(
                    PlatformAccount.user_id == user_id,
                    PlatformAccount.platform == platform,
                    PlatformAccount.external_user_id == external_user_id,
                    PlatformAccount.status != "deleted",
                )
            ).all()
        )
        user_info = _merge_user_info_with_account(
            user_info,
            _best_identity_profile_source(identity_accounts),
        )

    action = "updated" if account is not None else "created"
    now = shanghai_now()
    created = account is None
    if created:
        account = PlatformAccount(
            user_id=user_id,
            platform=platform,
            sub_type=sub_type,
            external_user_id=external_user_id,
            created_at=now,
        )

    account.nickname = user_info.get("nickname", "") or account.nickname or ""
    account.avatar_url = user_info.get("avatar_url", "") or account.avatar_url or ""
    account.external_user_id = external_user_id or account.external_user_id
    account.status = "active"
    profile = account_profile_from_user_info(user_info)
    account.status_message = (
        PROFILE_SYNC_PENDING_MESSAGE
        if _profile_sync_is_pending(profile)
        else ""
    )
    account.profile_json = json.dumps(profile, ensure_ascii=False, separators=(",", ":"))
    account.updated_at = now
    if created:
        try:
            with db.begin_nested():
                db.add(account)
                db.flush()
        except IntegrityError:
            if not external_user_id:
                raise
            return upsert_platform_account_from_login(
                db=db,
                user_id=user_id,
                platform=platform,
                sub_type=sub_type,
                user_info=user_info,
                cookies_text=cookies_text,
            )
    else:
        db.flush()
    db.add(
        AccountCookieVersion(
            platform_account_id=account.id,
            encrypted_cookies=encrypt_text(cookies_text),
        )
    )
    return account, action

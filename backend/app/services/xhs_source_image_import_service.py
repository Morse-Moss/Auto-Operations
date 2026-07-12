from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import re
from urllib.parse import quote, urlparse

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.adapters.xhs.pc_api_adapter import XhsPcApiAdapter
from backend.app.core.security import decrypt_text
from backend.app.models import AccountCookieVersion, Note, PlatformAccount
from backend.app.services.xhs_crawl_quality_service import search_failure_kind
from backend.app.services.xhs_source_image_extractor import extract_xhs_note_image_urls_from_payload


LOGIN_REQUIRED_MESSAGE = "自动补全原文图片需要先登录小红书 PC 账号，请前往账号矩阵登录后重试。"
SOURCE_URL_UNAVAILABLE_MESSAGE = "原文链接不可用，请检查笔记来源后重试。"
SOURCE_IMAGES_NOT_FOUND_MESSAGE = "原文详情未返回可补全的图片。"
RATE_LIMITED_MESSAGE = "小红书请求频率受限，请稍后重试。"
SOURCE_DETAIL_FAILED_MESSAGE = "原文详情获取失败，请稍后重试。"
COOKIE_NAME_PATTERN = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
COOKIE_CONTROL_PATTERN = re.compile(r"[\x00-\x1f\x7f]")
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthenticatedSourceImages:
    account_id: int
    source_url: str
    image_urls: list[str]


@dataclass(frozen=True)
class _EncryptedAccountCandidate:
    account: PlatformAccount
    encrypted_cookies: str


class SourceImageDetailError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int,
        *,
        account_id: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.account_id = account_id


def fetch_authenticated_source_images(
    *,
    db: Session,
    user_id: int,
    note: Note,
    source_url: str,
    adapter_factory=XhsPcApiAdapter,
) -> AuthenticatedSourceImages:
    clean_url = _clean_note_detail_url(source_url, note.note_id)
    candidates = _eligible_pc_accounts(
        db,
        user_id=user_id,
        preferred_account_id=note.platform_account_id,
    )
    if not candidates:
        raise SourceImageDetailError("xhs_login_required", LOGIN_REQUIRED_MESSAGE, 409)

    for candidate in candidates:
        account = candidate.account
        try:
            cookies = _cookies_to_string(decrypt_text(candidate.encrypted_cookies))
        except Exception as exc:
            _log_safe_failure(
                account_id=account.id,
                exception_type=type(exc).__name__,
                stage="cookie_decode",
            )
            continue
        if not cookies:
            continue
        try:
            response = adapter_factory(cookies).get_note_info(clean_url)
        except Exception as exc:
            _log_safe_failure(
                account_id=account.id,
                exception_type=type(exc).__name__,
                stage="provider_request",
            )
            response = None
        if not isinstance(response, tuple) or len(response) != 3:
            raise SourceImageDetailError(
                "source_detail_failed",
                SOURCE_DETAIL_FAILED_MESSAGE,
                502,
                account_id=account.id,
            )
        success, message, raw_payload = response

        if success:
            image_urls = extract_xhs_note_image_urls_from_payload(raw_payload or {})
            if not image_urls:
                raise SourceImageDetailError(
                    "source_images_not_found",
                    SOURCE_IMAGES_NOT_FOUND_MESSAGE,
                    422,
                    account_id=account.id,
                )
            return AuthenticatedSourceImages(
                account_id=account.id,
                source_url=clean_url,
                image_urls=image_urls,
            )

        failure_kind = search_failure_kind(str(message or ""), raw_payload)
        if failure_kind == "xhs_account_expired" or _has_missing_login_signal(message, raw_payload):
            continue
        if failure_kind == "xhs_rate_limited":
            raise SourceImageDetailError(
                "xhs_rate_limited",
                RATE_LIMITED_MESSAGE,
                429,
                account_id=account.id,
            )
        raise SourceImageDetailError(
            "source_detail_failed",
            SOURCE_DETAIL_FAILED_MESSAGE,
            502,
            account_id=account.id,
        )

    raise SourceImageDetailError("xhs_login_required", LOGIN_REQUIRED_MESSAGE, 409)


def _clean_note_detail_url(source_url: str, fallback_note_id: str) -> str:
    raw_url = str(source_url or "").strip()
    if raw_url:
        parsed = urlparse(raw_url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or not (
            host == "xiaohongshu.com" or host.endswith(".xiaohongshu.com")
        ):
            raise SourceImageDetailError(
                "source_url_unavailable",
                SOURCE_URL_UNAVAILABLE_MESSAGE,
                422,
            )
        path_parts = [part for part in parsed.path.split("/") if part]
        if len(path_parts) == 2 and path_parts[0] == "explore":
            note_id = path_parts[1]
        elif len(path_parts) == 3 and path_parts[:2] == ["discovery", "item"]:
            note_id = path_parts[2]
        else:
            raise SourceImageDetailError(
                "source_url_unavailable",
                SOURCE_URL_UNAVAILABLE_MESSAGE,
                422,
            )
    else:
        note_id = str(fallback_note_id or "").strip()

    if not note_id or note_id in {".", ".."} or "/" in note_id or "\\" in note_id:
        raise SourceImageDetailError(
            "source_url_unavailable",
            SOURCE_URL_UNAVAILABLE_MESSAGE,
            422,
        )
    return f"https://www.xiaohongshu.com/explore/{quote(note_id, safe='-_')}"


def _eligible_pc_accounts(
    db: Session,
    *,
    user_id: int,
    preferred_account_id: int | None,
) -> list[_EncryptedAccountCandidate]:
    latest_cookie_versions = (
        select(
            AccountCookieVersion.platform_account_id.label("account_id"),
            AccountCookieVersion.encrypted_cookies.label("encrypted_cookies"),
            func.row_number()
            .over(
                partition_by=AccountCookieVersion.platform_account_id,
                order_by=(
                    AccountCookieVersion.created_at.desc(),
                    AccountCookieVersion.id.desc(),
                ),
            )
            .label("version_rank"),
        )
        .subquery()
    )
    rows = db.execute(
        select(PlatformAccount, latest_cookie_versions.c.encrypted_cookies)
        .join(
            latest_cookie_versions,
            latest_cookie_versions.c.account_id == PlatformAccount.id,
        )
        .where(
            latest_cookie_versions.c.version_rank == 1,
            PlatformAccount.user_id == user_id,
            PlatformAccount.platform == "xhs",
            PlatformAccount.sub_type == "pc",
            PlatformAccount.status == "active",
        )
        .order_by(PlatformAccount.updated_at.desc(), PlatformAccount.id.desc())
    ).all()
    candidates = [
        _EncryptedAccountCandidate(
            account=account,
            encrypted_cookies=encrypted_cookies,
        )
        for account, encrypted_cookies in rows
        if encrypted_cookies
    ]
    if preferred_account_id is not None:
        candidates.sort(key=lambda candidate: candidate.account.id != preferred_account_id)
    return candidates


def _cookies_to_string(value: str) -> str:
    raw = str(value or "")
    if COOKIE_CONTROL_PATTERN.search(raw):
        raise ValueError("Cookie contains unsafe control characters")
    stripped = raw.strip()
    if not stripped:
        return ""

    if stripped.startswith("{"):
        decoded = json.loads(stripped)
        if not isinstance(decoded, dict):
            raise ValueError("Cookie JSON must be an object")
        cookie_items = list(decoded.items())
        reject_separator = True
    else:
        cookie_items = []
        for segment in stripped.split(";"):
            segment = segment.strip()
            if not segment:
                continue
            if "=" not in segment:
                raise ValueError("Cookie segment is malformed")
            name, cookie_value = segment.split("=", 1)
            cookie_items.append((name.strip(), cookie_value.strip()))
        reject_separator = False

    normalized: list[str] = []
    seen_names: set[str] = set()
    for raw_name, raw_value in cookie_items:
        name = str(raw_name).strip()
        if not COOKIE_NAME_PATTERN.fullmatch(name) or name in seen_names:
            raise ValueError("Cookie name is invalid or duplicated")
        if not isinstance(raw_value, (str, int, float, bool)):
            raise ValueError("Cookie value must be scalar")
        cookie_value = str(raw_value).strip()
        if COOKIE_CONTROL_PATTERN.search(cookie_value) or (reject_separator and ";" in cookie_value):
            raise ValueError("Cookie value contains unsafe characters")
        seen_names.add(name)
        normalized.append(f"{name}={cookie_value}")
    return "; ".join(normalized)


def _log_safe_failure(*, account_id: int, exception_type: str, stage: str) -> None:
    logger.warning(
        "XHS source image import dependency failed",
        extra={
            "account_id": account_id,
            "exception_type": exception_type,
            "stage": stage,
        },
    )


def _has_missing_login_signal(message: object, raw_payload: object | None) -> bool:
    messages = [str(message or "")]
    if isinstance(raw_payload, dict):
        messages.append(str(raw_payload.get("message") or raw_payload.get("msg") or ""))
    combined = " ".join(messages)
    return "无登录信息" in combined or "登录信息为空" in combined

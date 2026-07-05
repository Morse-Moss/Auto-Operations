from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from pathlib import PureWindowsPath
from typing import Iterable
from urllib.parse import quote, urlsplit

from backend.app.core.config import get_settings
from backend.app.core.platforms import PlatformId

MEDIA_OWNER_KINDS = {"upload", "asset", "image"}
EXPORT_OWNER_KINDS = {"notes", "report", "articles"}
_DEFAULT_PLATFORM = PlatformId.XHS.value
_ALLOWED_PLATFORMS = {platform.value for platform in PlatformId}


def _validate_platform(platform: str) -> str:
    value = (platform or "").strip()
    if value not in _ALLOWED_PLATFORMS:
        raise ValueError("Invalid platform")
    return value


def _validate_kind(kind: str, allowed_kinds: set[str]) -> str:
    value = (kind or "").strip()
    if value not in allowed_kinds:
        raise ValueError("Invalid owner kind")
    return value


def _validate_user_id(user_id: int) -> int:
    if not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("Invalid user id")
    return user_id


def _safe_basename(file_name: str) -> str:
    value = (file_name or "").strip()
    if not value or ".." in value or PureWindowsPath(value).name != value:
        raise ValueError("Invalid file name")
    return value


def asset_owner_prefix(platform: str, kind: str, user_id: int) -> str:
    platform_value = _validate_platform(platform)
    kind_value = _validate_kind(kind, MEDIA_OWNER_KINDS)
    user_id_value = _validate_user_id(user_id)
    return f"{platform_value}-{kind_value}-u{user_id_value}-"


def export_owner_prefix(platform: str, kind: str, user_id: int) -> str:
    platform_value = _validate_platform(platform)
    kind_value = _validate_kind(kind, EXPORT_OWNER_KINDS)
    user_id_value = _validate_user_id(user_id)
    return f"{platform_value}-{kind_value}-u{user_id_value}-"


def _platform_values(platforms: Iterable[str] | None) -> tuple[str, ...]:
    if platforms is None:
        return tuple(sorted(_ALLOWED_PLATFORMS))
    return tuple(_validate_platform(platform) for platform in platforms)


def valid_media_owner_prefixes(
    user_id: int,
    platforms: Iterable[str] | None = None,
    kinds: Iterable[str] | None = None,
) -> tuple[str, ...]:
    user_id_value = _validate_user_id(user_id)
    owner_kinds = tuple(sorted(MEDIA_OWNER_KINDS)) if kinds is None else tuple(_validate_kind(kind, MEDIA_OWNER_KINDS) for kind in kinds)
    return tuple(
        asset_owner_prefix(platform, kind, user_id_value)
        for platform in _platform_values(platforms)
        for kind in owner_kinds
    )


def valid_export_owner_prefixes(
    user_id: int,
    platforms: Iterable[str] | None = None,
    kinds: Iterable[str] | None = None,
) -> tuple[str, ...]:
    user_id_value = _validate_user_id(user_id)
    owner_kinds = tuple(sorted(EXPORT_OWNER_KINDS)) if kinds is None else tuple(_validate_kind(kind, EXPORT_OWNER_KINDS) for kind in kinds)
    return tuple(
        export_owner_prefix(platform, kind, user_id_value)
        for platform in _platform_values(platforms)
        for kind in owner_kinds
    )


def validate_owned_media_file_name(file_name: str, user_id: int) -> str:
    safe_name = _safe_basename(file_name)
    if not safe_name.startswith(valid_media_owner_prefixes(user_id)):
        raise ValueError("Media file not found")
    return safe_name


def media_file_name_from_reference(value: str) -> str:
    text = (value or "").strip()
    if not text:
        raise ValueError("Media file not found")
    media_prefix = "/api/files/media/"
    path = urlsplit(text).path
    if path.startswith(media_prefix):
        text = path[len(media_prefix):]
    elif text.startswith(media_prefix):
        text = text[len(media_prefix):]
    return _safe_basename(text)


def validate_owned_media_reference(value: str, user_id: int) -> str:
    return validate_owned_media_file_name(media_file_name_from_reference(value), user_id)


def owned_media_api_path(value: str, user_id: int) -> str:
    return f"/api/files/media/{validate_owned_media_reference(value, user_id)}"


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("utf-8").rstrip("=")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("utf-8"))


def _sign_media_payload(payload: dict) -> str:
    body = _base64url_encode(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(get_settings().secret_key.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).digest()
    return f"{body}.{_base64url_encode(signature)}"


def create_signed_media_token(file_name: str, user_id: int, *, expires_delta: timedelta = timedelta(minutes=30)) -> str:
    safe_name = validate_owned_media_file_name(file_name, user_id)
    expires_at = datetime.now(timezone.utc) + expires_delta
    return _sign_media_payload({"file_name": safe_name, "user_id": user_id, "exp": int(expires_at.timestamp())})


def create_signed_media_url(file_name: str, user_id: int, *, expires_delta: timedelta = timedelta(minutes=30)) -> str:
    safe_name = validate_owned_media_file_name(file_name, user_id)
    token = create_signed_media_token(safe_name, user_id, expires_delta=expires_delta)
    return f"/api/files/media/{quote(safe_name)}?token={quote(token)}"


def verify_signed_media_token(file_name: str, token: str) -> str:
    safe_name = _safe_basename(file_name)
    if not token:
        raise ValueError("Invalid media token")
    try:
        body, signature = token.split(".", 1)
        expected = hmac.new(get_settings().secret_key.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).digest()
        actual = _base64url_decode(signature)
        payload = json.loads(_base64url_decode(body))
    except Exception as exc:
        raise ValueError("Invalid media token") from exc
    if not hmac.compare_digest(actual, expected):
        raise ValueError("Invalid media token")
    if payload.get("file_name") != safe_name:
        raise ValueError("Invalid media token")
    expires_at = payload.get("exp")
    if not isinstance(expires_at, int) or expires_at < int(datetime.now(timezone.utc).timestamp()):
        raise ValueError("Invalid media token")
    user_id = payload.get("user_id")
    if not isinstance(user_id, int):
        raise ValueError("Invalid media token")
    return validate_owned_media_file_name(safe_name, user_id)


def validate_owned_export_file_name(file_name: str, user_id: int) -> str:
    safe_name = _safe_basename(file_name)
    if not safe_name.startswith(valid_export_owner_prefixes(user_id)):
        raise ValueError("Export file not found")
    return safe_name


def default_asset_owner_prefix(kind: str, user_id: int) -> str:
    return asset_owner_prefix(_DEFAULT_PLATFORM, kind, user_id)

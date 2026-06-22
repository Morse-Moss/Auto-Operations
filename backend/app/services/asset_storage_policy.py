from __future__ import annotations

from pathlib import PureWindowsPath
from typing import Iterable

from backend.app.core.platforms import PlatformId

MEDIA_OWNER_KINDS = {"upload", "asset", "image"}
EXPORT_OWNER_KINDS = {"notes", "report"}
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


def validate_owned_export_file_name(file_name: str, user_id: int) -> str:
    safe_name = _safe_basename(file_name)
    if not safe_name.startswith(valid_export_owner_prefixes(user_id)):
        raise ValueError("Export file not found")
    return safe_name


def default_asset_owner_prefix(kind: str, user_id: int) -> str:
    return asset_owner_prefix(_DEFAULT_PLATFORM, kind, user_id)

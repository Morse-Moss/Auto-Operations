from __future__ import annotations

from backend.app.core.platforms import get_platform, get_platforms


def list_platforms() -> list[dict]:
    return [platform.to_dict() for platform in get_platforms()]


def get_platform_detail(platform_id: str) -> dict:
    return get_platform(platform_id).to_dict()

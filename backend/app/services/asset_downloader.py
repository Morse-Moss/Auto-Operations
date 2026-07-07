from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from loguru import logger

from backend.app.core.config import get_settings
from backend.app.services.asset_storage_policy import asset_owner_prefix


DEFAULT_DOWNLOAD_TIMEOUT = (5, 15)
DEFAULT_MAX_BYTES = 20 * 1024 * 1024
MIN_ASSET_BYTES = 100


def download_asset_to_local(
    url: str,
    user_id: int,
    asset_type: str,
    platform: str = "xhs",
    *,
    timeout: tuple[int, int] = DEFAULT_DOWNLOAD_TIMEOUT,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> str | None:
    if not url or not url.startswith(("http://", "https://")):
        return None
    media_dir = Path(get_settings().storage_dir) / "media"
    file_path: Path | None = None
    try:
        import requests
        with requests.get(url, timeout=timeout, headers={"Referer": ""}, stream=True) as resp:
            resp.raise_for_status()
            content_length = _content_length(resp.headers.get("content-length"))
            if content_length is not None and content_length > max_bytes:
                return None
            ext = _guess_extension(url, resp.headers.get("content-type", ""), asset_type)
            file_name = f"{asset_owner_prefix(platform, 'asset', user_id)}{uuid4().hex}{ext}"
            media_dir.mkdir(parents=True, exist_ok=True)
            file_path = media_dir / file_name
            written = 0
            with file_path.open("wb") as handle:
                for chunk in resp.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    written += len(chunk)
                    if written > max_bytes:
                        raise ValueError("asset exceeds size limit")
                    handle.write(chunk)
            if written < MIN_ASSET_BYTES:
                file_path.unlink(missing_ok=True)
                return None
            return file_name
    except Exception as exc:
        if file_path is not None:
            file_path.unlink(missing_ok=True)
        logger.warning(f"Asset download failed for {url[:80]}: {exc}")
        return None


def _content_length(value: str | None) -> int | None:
    if not value:
        return None
    try:
        length = int(value)
        if length < 0:
            return None
        return length
    except ValueError:
        return None


def _guess_extension(url: str, content_type: str, asset_type: str) -> str:
    ct = content_type.lower()
    if "jpeg" in ct or "jpg" in ct:
        return ".jpg"
    if "png" in ct:
        return ".png"
    if "gif" in ct:
        return ".gif"
    if "webp" in ct:
        return ".webp"
    if "mp4" in ct:
        return ".mp4"
    if "quicktime" in ct or "mov" in ct:
        return ".mov"
    lower_url = url.lower().split("?")[0]
    for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4", ".mov"):
        if lower_url.endswith(ext):
            return ext
    return ".mp4" if asset_type == "video" else ".jpg"

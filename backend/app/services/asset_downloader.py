from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from loguru import logger

from backend.app.core.config import get_settings
from backend.app.services.asset_storage_policy import asset_owner_prefix
from backend.app.services.public_url_guard import (
    PublicUrlBlockedError,
    PublicUrlUnresolvedError,
    assert_public_http_url,
)


DEFAULT_DOWNLOAD_TIMEOUT = (5, 15)
DEFAULT_MAX_BYTES = 20 * 1024 * 1024
MIN_ASSET_BYTES = 100
MAX_DOWNLOAD_REDIRECTS = 3
DOWNLOAD_HEADERS = {
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "Referer": "",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
}


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
    # SSRF hard gate: refuse to fetch anything that is not a public network
    # address (private/loopback/link-local/metadata ranges). Raises
    # PublicUrlBlockedError with a user-readable Chinese message.
    try:
        assert_public_http_url(url, label="图片下载地址")
    except PublicUrlUnresolvedError as exc:
        # DNS failure is a normal download failure (same as before), not an attack.
        logger.warning(f"Asset download skipped, host unresolved for {url[:80]}: {exc}")
        return None
    candidates = _download_url_candidates(url, asset_type)
    for candidate_url in candidates:
        file_name = _download_single_asset_to_local(
            candidate_url,
            user_id,
            asset_type,
            platform=platform,
            timeout=timeout,
            max_bytes=max_bytes,
            log_failure=False,
        )
        if file_name:
            return file_name
    logger.warning(f"Asset download failed for all candidates from {url[:80]}")
    return None


def _download_single_asset_to_local(
    url: str,
    user_id: int,
    asset_type: str,
    platform: str,
    *,
    timeout: tuple[int, int],
    max_bytes: int,
    log_failure: bool = True,
) -> str | None:
    media_dir = Path(get_settings().storage_dir) / "media"
    file_path: Path | None = None
    try:
        import requests
        with _open_checked_response(requests, url, timeout=timeout) as resp:
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
        if log_failure:
            logger.warning(f"Asset download failed for {url[:80]}: {exc}")
        else:
            logger.debug(f"Asset download candidate failed for {url[:80]}: {exc}")
        return None


def _open_checked_response(requests_module, url: str, *, timeout: tuple[int, int]):
    """GET with per-hop SSRF validation: redirects are followed manually and
    every redirect target is re-validated against the public-address guard."""
    current_url = url
    for _ in range(MAX_DOWNLOAD_REDIRECTS + 1):
        assert_public_http_url(current_url, label="图片下载地址")
        resp = requests_module.get(
            current_url,
            timeout=timeout,
            headers=DOWNLOAD_HEADERS,
            stream=True,
            allow_redirects=False,
        )
        if resp.is_redirect or resp.is_permanent_redirect:
            location = resp.headers.get("location", "")
            resp.close()
            if not location:
                raise PublicUrlBlockedError("图片下载地址重定向缺少目标")
            current_url = requests_module.compat.urljoin(current_url, location)
            continue
        return resp
    raise PublicUrlBlockedError("图片下载地址重定向次数过多")


def _download_url_candidates(url: str, asset_type: str) -> list[str]:
    candidates = [url]
    if asset_type == "image":
        candidates.extend(_stable_xhs_note_image_urls(url))
    result: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        result.append(candidate)
    return result


def _stable_xhs_note_image_urls(url: str) -> list[str]:
    parsed = urlparse(str(url or "").strip().replace("\\u002F", "/").replace("\\/", "/").split("!", 1)[0])
    host = parsed.netloc.lower()
    if not ((host.startswith("sns-") and host.endswith(".xhscdn.com")) or host == "ci.xiaohongshu.com"):
        return []
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    for marker in ("notes_pre_post", "notes_uhdr"):
        if marker in parts:
            index = parts.index(marker)
            if index + 1 < len(parts):
                token = parts[index + 1]
                if token:
                    stable_url = f"https://sns-img-hw.xhscdn.com/{marker}/{token}"
                    return [
                        f"{stable_url}?imageView2/2/w/1080/format/webp",
                        stable_url,
                    ]
    for index, part in enumerate(parts):
        if part.startswith("note_pre_post_") and index + 1 < len(parts):
            token = parts[index + 1]
            if token:
                stable_url = f"https://sns-img-hw.xhscdn.com/{part}/{token}"
                return [
                    f"{stable_url}?imageView2/2/w/1080/format/webp",
                    stable_url,
                ]
    return []


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
    if "heic" in ct or "heif" in ct:
        return ".heic"
    if "mp4" in ct:
        return ".mp4"
    if "quicktime" in ct or "mov" in ct:
        return ".mov"
    lower_url = url.lower().split("?")[0]
    for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4", ".mov"):
        if lower_url.endswith(ext):
            return ext
    return ".mp4" if asset_type == "video" else ".jpg"

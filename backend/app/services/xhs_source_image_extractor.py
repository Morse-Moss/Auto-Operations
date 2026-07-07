from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse, urlunparse


MAX_SOURCE_IMAGES = 50
DEFAULT_TIMEOUT = 15
XHS_SOURCE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"
    ),
    "Referer": "https://www.xiaohongshu.com/",
}


class XhsSourceImageExtractionError(RuntimeError):
    pass


def fetch_xhs_note_image_urls(source_url: str, *, timeout: int = DEFAULT_TIMEOUT) -> list[str]:
    clean_url = _clean_source_url(source_url)
    if not clean_url:
        raise XhsSourceImageExtractionError("source_url_required")
    try:
        import requests

        response = requests.get(clean_url, headers=XHS_SOURCE_HEADERS, timeout=timeout)
        response.raise_for_status()
    except Exception as exc:
        raise XhsSourceImageExtractionError("source_page_unavailable") from exc
    return extract_xhs_note_image_urls_from_html(response.text)


def extract_xhs_note_image_urls_from_html(html: str) -> list[str]:
    state = _extract_initial_state(html)
    if not isinstance(state, dict):
        return _unique_image_urls(_find_xhs_image_urls(html))

    note = _find_note_payload(state)
    image_items = note.get("imageList") if isinstance(note, dict) else None
    urls: list[str] = []
    if isinstance(image_items, list):
        for item in image_items:
            for value in _candidate_image_values(item):
                token_url = _image_url_from_value(value)
                if token_url:
                    urls.append(token_url)
                    break
    if not urls:
        urls.extend(_find_xhs_image_urls(json.dumps(note, ensure_ascii=False) if note else html))
    return _unique_image_urls(urls)


def _clean_source_url(source_url: str) -> str:
    raw = str(source_url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        return ""
    host = parsed.netloc.lower()
    if not (host.endswith("xiaohongshu.com") or host.endswith("xhslink.com")):
        return ""
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", parsed.query, ""))[:2048]


def _extract_initial_state(html: str) -> dict[str, Any] | None:
    if not html:
        return None
    match = re.search(r"window\.__INITIAL_STATE__\s*=\s*", html)
    if not match:
        return None
    start = match.end()
    end = html.find("</script>", start)
    raw = html[start:end if end >= 0 else len(html)].strip().rstrip(";")
    raw = raw.replace("undefined", "null")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        try:
            import yaml

            loaded = yaml.safe_load(raw)
            return loaded if isinstance(loaded, dict) else None
        except Exception:
            return None


def _find_note_payload(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    phone = _deep_get(data, ("noteData", "data", "noteData"))
    if isinstance(phone, dict):
        return phone
    detail_map = _deep_get(data, ("note", "noteDetailMap"))
    if isinstance(detail_map, dict):
        for value in detail_map.values():
            note = value.get("note") if isinstance(value, dict) else None
            if isinstance(note, dict):
                return note
    found = _find_first_dict_with_key(data, "imageList")
    return found if isinstance(found, dict) else {}


def _deep_get(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _find_first_dict_with_key(value: Any, key: str) -> dict[str, Any] | None:
    if isinstance(value, dict):
        if key in value:
            return value
        for child in value.values():
            found = _find_first_dict_with_key(child, key)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_first_dict_with_key(child, key)
            if found:
                return found
    return None


def _candidate_image_values(item: Any) -> list[str]:
    if not isinstance(item, dict):
        return []
    keys = ("urlDefault", "url", "traceId", "fileId", "id")
    values = [str(item.get(key) or "").strip() for key in keys if item.get(key)]
    url_list = item.get("urlList")
    if isinstance(url_list, list):
        for value in url_list:
            if isinstance(value, str):
                values.append(value.strip())
            elif isinstance(value, dict):
                values.extend(_candidate_image_values(value))
    return values


def _image_url_from_value(value: str) -> str:
    if not value:
        return ""
    if value.startswith(("http://", "https://")):
        return _normalize_image_url(value)
    if "/" in value or re.fullmatch(r"[A-Za-z0-9_-]{12,}", value):
        return f"https://sns-img-bd.xhscdn.com/{value.lstrip('/')}"
    return ""


def _find_xhs_image_urls(text: str) -> list[str]:
    if not text:
        return []
    pattern = re.compile(r"https?://(?:sns-[^\\\"'\\s<>]+?\\.xhscdn\\.com|ci\\.xiaohongshu\\.com)/[^\\\"'\\s<>]+")
    return [_normalize_image_url(match.group(0)) for match in pattern.finditer(text)]


def _normalize_image_url(url: str) -> str:
    cleaned = str(url or "").strip().replace("\\u002F", "/").replace("\\/", "/")
    if "!" in cleaned:
        cleaned = cleaned.split("!", 1)[0]
    parsed = urlparse(cleaned)
    if not parsed.scheme or not parsed.netloc:
        return cleaned
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", parsed.query, ""))


def _canonical_image_key(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.netloc.lower()}{parsed.path}".rstrip("/")


def _unique_image_urls(urls: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for url in urls:
        normalized = _normalize_image_url(url)
        if not normalized.startswith(("http://", "https://")):
            continue
        if not is_xhs_note_image_url(normalized):
            continue
        key = _canonical_image_key(normalized)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(normalized)
        if len(result) >= MAX_SOURCE_IMAGES:
            break
    return result


def canonical_xhs_image_key(url: str) -> str:
    return _canonical_image_key(_normalize_image_url(url))


def is_xhs_note_image_url(url: str) -> bool:
    parsed = urlparse(_normalize_image_url(url))
    if not parsed.scheme or not parsed.netloc:
        return False
    host = parsed.netloc.lower()
    if not ((host.startswith("sns-") and host.endswith(".xhscdn.com")) or host == "ci.xiaohongshu.com"):
        return False
    path = parsed.path.lower()
    if any(segment in path for segment in ("/notes_pre_post/", "/note_pre_post_", "/notes_uhdr/")):
        return True
    return bool(re.fullmatch(r"/[a-z0-9_-]{20,}", path))

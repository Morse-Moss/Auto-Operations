from __future__ import annotations

from typing import Any

import requests

from backend.app.services.huitun_crypto import HUITUN_EXT_DATA_DECRYPT_FAILED_MESSAGE, decrypt_huitun_ext_data
from backend.app.services.huitun_live_keyword_source import _now_ms, _session_from_cookie_text

HUITUN_NOTE_SEARCH_URL = "https://xhsapi.huitun.com/note/searchV2"
NOTE_SEARCH_MAX_LIMIT = 100

NOTE_SEARCH_FAILED_MESSAGE = "本次数据获取失败，任务已停止。"
NOTE_SEARCH_STRUCTURE_CHANGED_MESSAGE = "笔记数据返回结构已变化，任务已停止。"
NOTE_SEARCH_LOGIN_EXPIRED_MESSAGE = "数据账号登录状态已过期，请重新登录后再试。"


def _first_list(value: Any) -> list[Any] | None:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("list", "items", "records", "rows", "data", "result"):
            nested = value.get(key)
            candidate = _first_list(nested)
            if candidate is not None:
                return candidate
        for nested in value.values():
            candidate = _first_list(nested)
            if candidate is not None:
                return candidate
    return None


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _int_value(value: Any) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        cleaned = value.strip().lower().replace(",", "")
        multiplier = 1
        if cleaned.endswith("w") or cleaned.endswith("万"):
            multiplier = 10000
            cleaned = cleaned[:-1]
        try:
            return int(float(cleaned) * multiplier)
        except ValueError:
            return 0
    return 0


def _dedupe_texts(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = value.strip()
        if cleaned and cleaned not in seen:
            result.append(cleaned)
            seen.add(cleaned)
    return result


def _tags_from_item(item: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    for key in ("topic", "keyw", "participles"):
        value = item.get(key)
        if isinstance(value, list):
            tags.extend(_text(part).lstrip("#") for part in value)
        elif isinstance(value, str):
            tags.extend(part.strip().lstrip("#") for part in value.replace("，", ",").split(","))
    return _dedupe_texts(tags)


def _candidate_from_item(item: dict[str, Any], index: int) -> dict[str, Any] | None:
    note_id = _text(item.get("noteId") or item.get("note_id") or item.get("id"))
    title = _text(item.get("title") or item.get("displayTitle"))
    content = _text(item.get("desc") or item.get("content"))
    if not note_id and not title:
        return None
    image_url = _text(item.get("imageUrl") or item.get("coverUrl") or item.get("cover"))
    video_url = _text(item.get("videoUrl") or item.get("video_url"))
    asset_urls = _dedupe_texts([image_url])
    metrics = {
        "like_count": _int_value(item.get("like")),
        "collect_count": _int_value(item.get("coll")),
        "comment_count": _int_value(item.get("comm")),
        "share_count": _int_value(item.get("share") or item.get("sharedCount")),
        "estimated_read_count": _int_value(item.get("read")),
    }
    metrics["interaction_count"] = (
        metrics["like_count"] + metrics["collect_count"] + metrics["comment_count"] + metrics["share_count"]
    )
    return {
        "external_id": note_id or _text(item.get("tid") or item.get("bbid")),
        "platform_note_id": note_id,
        "original_url": f"https://www.xiaohongshu.com/explore/{note_id}" if note_id else "",
        "title": title,
        "content_excerpt": content,
        "author_name": _text(item.get("nick") or item.get("author")),
        "cover_url": image_url,
        "asset_urls": asset_urls,
        "video_url": video_url,
        "publish_time": _text(item.get("ts")),
        "update_time": _text(item.get("updateTime")),
        "rank_index": int(item.get("rank_index") or item.get("rankIndex") or index + 1),
        "category": _text(item.get("category") or item.get("cidP")),
        "tags": _tags_from_item(item),
        "metrics": metrics,
        "raw": item,
    }


def _rows_from_response(payload: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    ext_data = payload.get("extData")
    if isinstance(ext_data, str):
        try:
            ext_data = decrypt_huitun_ext_data(ext_data)
        except ValueError as exc:
            raise RuntimeError(HUITUN_EXT_DATA_DECRYPT_FAILED_MESSAGE) from exc

    candidate_list = _first_list(ext_data) if isinstance(ext_data, (dict, list)) else None
    if candidate_list is None:
        candidate_list = _first_list(payload)
    if candidate_list is None:
        raise RuntimeError(NOTE_SEARCH_STRUCTURE_CHANGED_MESSAGE)

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(candidate_list):
        if not isinstance(item, dict):
            continue
        candidate = _candidate_from_item(item, index)
        if candidate is None:
            continue
        dedupe_key = candidate["platform_note_id"] or f"{candidate['title']}::{candidate['author_name']}"
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        rows.append(candidate)
        if len(rows) >= limit:
            break
    return rows


def search_notes(
    cookie_text: str,
    keyword: str,
    limit: int,
    *,
    sort: str = "interaction",
    note_type: str = "all",
) -> list[dict[str, Any]]:
    keyword = keyword.strip()
    if not keyword:
        return []
    effective_limit = max(1, min(limit, NOTE_SEARCH_MAX_LIMIT))
    session = _session_from_cookie_text(cookie_text)
    try:
        response = session.get(
            HUITUN_NOTE_SEARCH_URL,
            params={
                "_t": _now_ms(),
                "keyword": keyword,
                "page": 1,
                "pageSize": effective_limit,
                "sort": sort,
                "noteType": note_type,
            },
            timeout=20,
        )
    except requests.Timeout as exc:
        raise RuntimeError("笔记数据获取超时，任务已停止。") from exc
    except requests.RequestException as exc:
        raise RuntimeError("笔记数据网络请求失败，任务已停止。") from exc

    if response.status_code in {401, 403}:
        raise RuntimeError(NOTE_SEARCH_LOGIN_EXPIRED_MESSAGE)
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(f"笔记数据获取失败：HTTP {response.status_code}") from exc
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(NOTE_SEARCH_STRUCTURE_CHANGED_MESSAGE) from exc
    if not isinstance(payload, dict):
        raise RuntimeError(NOTE_SEARCH_STRUCTURE_CHANGED_MESSAGE)
    status_code = payload.get("status") or payload.get("code")
    if status_code in {1001, 401, 403}:
        raise RuntimeError(NOTE_SEARCH_LOGIN_EXPIRED_MESSAGE)
    if status_code not in {0, 200, None}:
        message = _text(payload.get("message") or payload.get("msg"))
        raise RuntimeError(message or NOTE_SEARCH_FAILED_MESSAGE)
    return _rows_from_response(payload, effective_limit)

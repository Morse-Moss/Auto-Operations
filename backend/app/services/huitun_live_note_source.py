from __future__ import annotations

from datetime import timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests

from backend.app.core.time import shanghai_now
from backend.app.services.huitun_crypto import HUITUN_EXT_DATA_DECRYPT_FAILED_MESSAGE, decrypt_huitun_ext_data
from backend.app.services.huitun_live_keyword_source import _now_ms, _session_from_cookie_text

HUITUN_NOTE_SEARCH_URL = "https://xhsapi.huitun.com/note/searchV2"
HUITUN_NOTE_URL_URL = "https://xhsapi.huitun.com/note/noteUrl"
HUITUN_NOTE_COMMENT_URL = "https://xhsapi.huitun.com/note/detail/noteComment"
HUITUN_WEB_VERSION = "16101520.52.102"
NOTE_SEARCH_MAX_LIMIT = 50
NOTE_SEARCH_LIVE_PAGE_SIZE_MAX = 20
NOTE_SEARCH_DEFAULT_DAYS = 30
NOTE_COMMENT_DEFAULT_LIMIT = 200
NOTE_COMMENT_PAGE_SIZE_MAX = 20
# Verified from the web search UI: 1 = note title, 3 = note tag.
NOTE_SEARCH_TITLE_TAG_RANGE_LIST = "1,3"
NOTE_SEARCH_SORT_MAP = {
    "time": 0,
    "latest": 0,
    "publish_time": 0,
    "like": 1,
    "collect": 2,
    "collection": 2,
    "comment": 3,
    "share": 4,
    "interaction": 5,
    "stat": 5,
    "read": 6,
}
NOTE_SEARCH_TYPE_MAP = {
    "": "",
    "0": "",
    "all": "",
    "1": "video",
    "video": "video",
    "2": "normal",
    "normal": "normal",
    "image": "normal",
    "picture": "normal",
    "note": "normal",
}

NOTE_SEARCH_FAILED_MESSAGE = "本次数据获取失败，任务已停止。"
NOTE_SEARCH_STRUCTURE_CHANGED_MESSAGE = "笔记数据返回结构已变化，任务已停止。"
NOTE_SEARCH_LOGIN_EXPIRED_MESSAGE = "数据账号登录状态已过期，请重新登录后再试。"


def _first_list(value: Any) -> list[Any] | None:
    if isinstance(value, list):
        if not value or _looks_like_note_list(value):
            return value
        empty_candidate: list[Any] | None = None
        for nested in value:
            candidate = _first_list(nested)
            if candidate:
                return candidate
            if candidate is not None and empty_candidate is None:
                empty_candidate = candidate
        if empty_candidate is not None:
            return empty_candidate
        return value
    if isinstance(value, dict):
        empty_candidate: list[Any] | None = None
        for key in ("list", "items", "records", "rows", "data", "result"):
            nested = value.get(key)
            candidate = _first_list(nested)
            if candidate:
                return candidate
            if candidate is not None and empty_candidate is None:
                empty_candidate = candidate
        for nested in value.values():
            candidate = _first_list(nested)
            if candidate:
                return candidate
            if candidate is not None and empty_candidate is None:
                empty_candidate = candidate
        if empty_candidate is not None:
            return empty_candidate
    return None


def _looks_like_note_list(value: list[Any]) -> bool:
    note_keys = {"noteId", "note_id", "id", "title", "displayTitle"}
    return any(isinstance(item, dict) and any(key in item for key in note_keys) for item in value)


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


def _normalize_sort(sort: Any) -> int:
    if isinstance(sort, bool) or sort is None:
        return NOTE_SEARCH_SORT_MAP["interaction"]
    try:
        return int(sort)
    except (TypeError, ValueError):
        pass
    return NOTE_SEARCH_SORT_MAP.get(str(sort).strip().lower(), NOTE_SEARCH_SORT_MAP["interaction"])


def _note_type_param(note_type: Any) -> str:
    value = _text(note_type).lower()
    return NOTE_SEARCH_TYPE_MAP.get(value, value)


def _date_range_params(days: int = NOTE_SEARCH_DEFAULT_DAYS) -> dict[str, Any]:
    end_date = shanghai_now().date()
    start_date = end_date - timedelta(days=days - 1)
    return {
        "dateStart": start_date.isoformat(),
        "dateEnd": end_date.isoformat(),
        "days": days,
    }


def _common_params() -> dict[str, Any]:
    return {
        "_t": _now_ms(),
        "vs": HUITUN_WEB_VERSION,
        "Source": "web",
    }


def _search_params(keyword: str, limit: int, *, sort: Any, note_type: Any, page: int = 1) -> dict[str, Any]:
    params: dict[str, Any] = {
        **_common_params(),
        "keyword": keyword,
        "page": page,
        "pageSize": limit,
        "sort": _normalize_sort(sort),
        "rangeList": NOTE_SEARCH_TITLE_TAG_RANGE_LIST,
        **_date_range_params(),
        "del": True,
    }
    normalized_note_type = _note_type_param(note_type)
    if normalized_note_type:
        params["noteType"] = normalized_note_type
    return params


def _huitun_headers() -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Origin": "https://xhs.huitun.com",
        "Referer": "https://xhs.huitun.com/",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        ),
    }


def _is_supported_original_url(value: str) -> bool:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    host = parsed.netloc.lower()
    if host.endswith("xhslink.com"):
        return True
    if not host.endswith("xiaohongshu.com"):
        return False
    path_segments = [segment for segment in parsed.path.split("/") if segment]
    if len(path_segments) >= 2 and path_segments[0] in {"explore", "discovery"}:
        return "xsec_token" in parse_qs(parsed.query)
    return False


def _original_url_from_item(item: dict[str, Any]) -> str:
    for key in ("noteUrl", "note_url", "shareUrl", "share_url", "url", "link", "noteLink"):
        value = _text(item.get(key))
        if value.startswith(("http://", "https://")) and _is_supported_original_url(value):
            return value
    return ""


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
        "original_url": _original_url_from_item(item),
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


def _ext_data_from_payload(payload: dict[str, Any]) -> Any:
    ext_data = payload.get("extData")
    if isinstance(ext_data, str):
        try:
            return decrypt_huitun_ext_data(ext_data)
        except ValueError as exc:
            raise RuntimeError(HUITUN_EXT_DATA_DECRYPT_FAILED_MESSAGE) from exc
    return ext_data


def _comment_id(item: dict[str, Any]) -> str:
    return _text(item.get("commentId") or item.get("comment_id") or item.get("id"))


def _comment_from_item(item: dict[str, Any]) -> dict[str, Any] | None:
    comment_id = _comment_id(item)
    content = _text(item.get("content") or item.get("commentContent") or item.get("text"))
    if not comment_id or not content:
        return None
    return {
        "comment_id": comment_id,
        "user_name": _text(item.get("nick") or item.get("nickname") or item.get("userName") or item.get("user_name")),
        "user_id": _text(item.get("anchorId") or item.get("userId") or item.get("user_id")) or None,
        "content": content,
        "like_count": _int_value(item.get("likeCount") or item.get("like_count") or item.get("likedCount")),
        "parent_comment_id": _text(item.get("parentCommentId") or item.get("parent_comment_id")) or None,
        "created_at_remote": _text(item.get("postTime") or item.get("createTime") or item.get("created_at")) or None,
        "raw_json": item,
    }


def _comment_rows_from_payload(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ext_data = _ext_data_from_payload(payload)
    if not isinstance(ext_data, dict):
        return [], {"has_next": False, "total": 0, "pages": 0}
    raw_list = ext_data.get("list")
    if not isinstance(raw_list, list):
        raw_list = []
    rows: list[dict[str, Any]] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        comment = _comment_from_item(item)
        if comment is not None:
            rows.append(comment)
    page_info = {
        "has_next": bool(ext_data.get("hasNextPage")),
        "total": _int_value(ext_data.get("total")),
        "pages": _int_value(ext_data.get("pages")),
    }
    return rows, page_info


def _payload_from_response(response: requests.Response) -> dict[str, Any]:
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
    if status_code in {1000, 1001, 401, 403}:
        raise RuntimeError(NOTE_SEARCH_LOGIN_EXPIRED_MESSAGE)
    if status_code not in {0, 200, None}:
        message = _text(payload.get("message") or payload.get("msg"))
        raise RuntimeError(message or NOTE_SEARCH_FAILED_MESSAGE)
    return payload


def _resolved_url_from_payload(payload: dict[str, Any]) -> str:
    ext_data = payload.get("extData")
    if isinstance(ext_data, str):
        try:
            ext_data = decrypt_huitun_ext_data(ext_data)
        except ValueError as exc:
            raise RuntimeError(HUITUN_EXT_DATA_DECRYPT_FAILED_MESSAGE) from exc
    if isinstance(ext_data, str):
        candidate = ext_data.strip().strip('"')
        return candidate if _is_supported_original_url(candidate) else ""
    if isinstance(ext_data, dict):
        return _original_url_from_item(ext_data)
    return ""


def resolve_note_url(cookie_text: str, note_id: str) -> str:
    note_id = note_id.strip()
    if not note_id:
        return ""
    session = _session_from_cookie_text(cookie_text)
    try:
        response = session.get(
            HUITUN_NOTE_URL_URL,
            params={**_common_params(), "noteId": note_id},
            headers=_huitun_headers(),
            timeout=20,
        )
    except requests.Timeout as exc:
        raise RuntimeError("note_url_request_timeout") from exc
    except requests.RequestException as exc:
        raise RuntimeError("note_url_request_failed") from exc
    return _resolved_url_from_payload(_payload_from_response(response))


def fetch_note_comments(
    cookie_text: str,
    note_id: str,
    *,
    limit: int = NOTE_COMMENT_DEFAULT_LIMIT,
    page_size: int = NOTE_COMMENT_PAGE_SIZE_MAX,
) -> list[dict[str, Any]]:
    note_id = note_id.strip()
    if not note_id:
        return []
    effective_limit = max(1, int(limit or NOTE_COMMENT_DEFAULT_LIMIT))
    effective_page_size = max(1, min(int(page_size or NOTE_COMMENT_PAGE_SIZE_MAX), NOTE_COMMENT_PAGE_SIZE_MAX))
    session = _session_from_cookie_text(cookie_text)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    page = 1
    while len(rows) < effective_limit:
        current_page_size = min(effective_page_size, effective_limit - len(rows))
        try:
            response = session.get(
                HUITUN_NOTE_COMMENT_URL,
                params={
                    **_common_params(),
                    "noteId": note_id,
                    "keyword": "",
                    "emotion": "",
                    "pageSize": current_page_size,
                    "page": page,
                },
                headers=_huitun_headers(),
                timeout=20,
            )
        except requests.Timeout as exc:
            raise RuntimeError("评论数据获取超时，已跳过本篇评论补全。") from exc
        except requests.RequestException as exc:
            raise RuntimeError("评论数据网络请求失败，已跳过本篇评论补全。") from exc

        page_rows, page_info = _comment_rows_from_payload(_payload_from_response(response))
        for row in page_rows:
            dedupe_key = row["comment_id"]
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            rows.append(row)
            if len(rows) >= effective_limit:
                break
        if not page_info["has_next"] or len(page_rows) < current_page_size:
            break
        page += 1
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
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    page = 1
    while len(rows) < effective_limit:
        page_size = min(NOTE_SEARCH_LIVE_PAGE_SIZE_MAX, effective_limit - len(rows))
        try:
            response = session.get(
                HUITUN_NOTE_SEARCH_URL,
                params=_search_params(keyword, page_size, sort=sort, note_type=note_type, page=page),
                timeout=20,
            )
        except requests.Timeout as exc:
            raise RuntimeError("笔记数据获取超时，任务已停止。") from exc
        except requests.RequestException as exc:
            raise RuntimeError("笔记数据网络请求失败，任务已停止。") from exc

        page_rows = _rows_from_response(_payload_from_response(response), page_size)
        for row in page_rows:
            dedupe_key = row["platform_note_id"] or f"{row['title']}::{row['author_name']}"
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            rows.append(row)
            if len(rows) >= effective_limit:
                break
        if len(page_rows) < page_size:
            break
        page += 1
    return rows

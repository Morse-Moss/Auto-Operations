from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

XHS_NOTE_URL_BASE = "https://www.xiaohongshu.com"


def should_reject_short_explore_url(url: str) -> bool:
    parsed = urlparse(url if re.match(r"^https?://", url) else f"{XHS_NOTE_URL_BASE}{url if url.startswith('/') else '/' + url}")
    path_segments = [segment for segment in parsed.path.split("/") if segment]
    if len(path_segments) != 2:
        return False
    section, feed_id = path_segments
    return section == "explore" and bool(feed_id.strip()) and "xsec_token" not in parse_qs(parsed.query)


def _has_rate_limit_error_code(value: str) -> bool:
    return re.search(r"(?:^|[^\w])error_code\s*=\s*300013(?!\d)", value) is not None


def is_xhs_rate_limit_signal(
    *,
    url: str | None = None,
    text: str | None = None,
    message: str | None = None,
) -> bool:
    raw_url = url or ""
    decoded_url = unquote(raw_url)
    combined = "\n".join([raw_url, decoded_url, text or "", message or ""])

    parsed = urlparse(raw_url)
    is_xhs_host = parsed.hostname in {"xiaohongshu.com", "www.xiaohongshu.com"}
    if is_xhs_host and parsed.path == "/website-login/error" and _has_rate_limit_error_code(combined):
        return True
    if _has_rate_limit_error_code(combined):
        return True
    if "访问频繁" in combined:
        return True
    return is_xhs_host and "请稍后再试" in combined


def mask_xsec_token(token: str | None) -> str | None:
    if token is None:
        return None
    if len(token) <= 8:
        return "***"
    return f"{token[:4]}***{token[-4:]}"


def classify_source_url(url: str) -> str:
    if not url:
        return "empty"
    parsed = urlparse(url if re.match(r"^https?://", url) else f"{XHS_NOTE_URL_BASE}{url if url.startswith('/') else '/' + url}")
    path_segments = [segment for segment in parsed.path.split("/") if segment]
    if len(path_segments) >= 1 and path_segments[0] == "explore":
        return "explore_with_xsec_token" if "xsec_token" in parse_qs(parsed.query) else "short_explore_without_xsec_token"
    if len(path_segments) >= 1 and path_segments[0] == "search_result":
        return "search_result"
    return "other"


def _is_record(value: Any) -> bool:
    return isinstance(value, dict)


def _data_payload(raw_payload: object | None) -> dict[str, Any]:
    if not isinstance(raw_payload, dict):
        return {}
    data = raw_payload.get("data")
    return data if isinstance(data, dict) else raw_payload


def _payload_items(raw_payload: object | None) -> list[Any]:
    data = _data_payload(raw_payload)
    for key in ("items", "notes", "list"):
        value = data.get(key)
        if isinstance(value, list):
            return value
    return []


def _first_note_card(raw_payload: object | None) -> dict[str, Any]:
    items = _payload_items(raw_payload)
    item = items[0] if items and isinstance(items[0], dict) else _data_payload(raw_payload)
    if not isinstance(item, dict):
        return {}
    for key in ("note_card", "note", "noteDetail", "currentNote"):
        value = item.get(key)
        if isinstance(value, dict):
            return value
    return item


def _extract_note_id(raw_payload: object | None) -> str | None:
    card = _first_note_card(raw_payload)
    for key in ("note_id", "id", "feed_id", "feedId"):
        value = card.get(key)
        if value:
            return str(value)
    if isinstance(raw_payload, dict):
        for key in ("note_id", "id", "feed_id", "feedId"):
            value = raw_payload.get(key)
            if value:
                return str(value)
    return None


def _has_recognized_detail_structure(raw_payload: object | None) -> bool:
    if not isinstance(raw_payload, dict):
        return False
    data = _data_payload(raw_payload)
    state_note = data.get("note") if isinstance(data.get("note"), dict) else None
    if isinstance(state_note, dict) and isinstance(state_note.get("noteDetailMap"), dict) and state_note["noteDetailMap"]:
        return True
    if isinstance(data.get("noteDetailMap"), dict) and data["noteDetailMap"]:
        return True
    if isinstance(data.get("noteDetail"), dict):
        return True
    card = _first_note_card(raw_payload)
    return any(key in card for key in ("desc", "description", "content", "tag_list", "tags", "topics", "image_list", "images", "video"))


def summarize_payload(raw_payload: object, source_url: str = "") -> dict:
    data = _data_payload(raw_payload)
    items = _payload_items(raw_payload)
    card = _first_note_card(raw_payload)
    url_query = parse_qs(urlparse(source_url).query)
    xsec_token = None
    if isinstance(raw_payload, dict):
        xsec_token = raw_payload.get("xsec_token")
    xsec_token = xsec_token or card.get("xsec_token") or (url_query.get("xsec_token") or [None])[0]

    return {
        "error_code": data.get("error_code") if isinstance(data, dict) else None,
        "message": data.get("message") or data.get("msg") if isinstance(data, dict) else None,
        "note_id": _extract_note_id(raw_payload),
        "source_url_kind": classify_source_url(source_url),
        "has_xsec_token": bool(xsec_token),
        "masked_xsec_token": mask_xsec_token(str(xsec_token)) if xsec_token else None,
        "payload_keys": sorted([str(key) for key in data.keys()]) if isinstance(data, dict) else [],
        "has_data": bool(data),
        "item_count": len(items),
        "has_content": bool(card.get("desc") or card.get("description") or card.get("content")),
        "has_media": bool(card.get("image_list") or card.get("images") or card.get("video") or card.get("video_url") or card.get("video_addr")),
        "has_tags": bool(card.get("tag_list") or card.get("tags") or card.get("topics")),
        "has_interaction": bool(card.get("interact_info") or card.get("interaction")),
    }


def _has_non_empty_list(value: Any) -> bool:
    return isinstance(value, list) and any(item for item in value)


def _has_content(normalized: dict[str, Any]) -> bool:
    for key in ("content", "desc", "description", "detailText", "detail_text", "rawDetailText", "raw_detail_text"):
        value = normalized.get(key)
        if isinstance(value, str) and value.strip():
            return True
    return False


def _has_media(normalized: dict[str, Any]) -> bool:
    return _has_non_empty_list(normalized.get("image_urls")) or bool(normalized.get("video_url") or normalized.get("video_addr"))


def _has_tags(normalized: dict[str, Any]) -> bool:
    return _has_non_empty_list(normalized.get("tags")) or _has_non_empty_list(normalized.get("detailTags"))


def _has_weak_search_card_signal(normalized: dict[str, Any]) -> bool:
    weak_keys = ("note_id", "note_url", "title", "cover_url", "likes", "collects", "comments", "shares")
    return any(normalized.get(key) not in (None, "", [], {}) for key in weak_keys)


def build_user_message(diagnostic_kind: str | None, quality_status: str) -> str:
    if diagnostic_kind == "missing_xsec_token_short_explore":
        return "这个链接缺少 xsec_token，无法稳定获取详情。请从搜索结果重新采集，或提供带 xsec_token 的完整链接。"
    if diagnostic_kind == "xhs_rate_limited":
        return "小红书提示访问频繁，已停止本轮详情抓取。请稍后低频重试。"
    if diagnostic_kind == "detail_api_failed":
        return "详情接口返回失败。请稍后重试，或换用搜索结果中的完整链接。"
    if diagnostic_kind == "invalid_note_identity":
        return "无法识别笔记 ID，请检查链接格式。"
    if quality_status == "search_card_only":
        return "已拿到搜索卡片，但详情为空，本条不会自动入库。可稍后低频重试。"
    if quality_status == "empty_detail_payload":
        return "详情为空，本条不会自动入库。请稍后重试或换来源链接。"
    if quality_status == "valid_detail":
        return "详情已通过质量检查。"
    return "采集结果需要人工确认。"


def _quality_result(quality_status: str, diagnostic_kind: str | None, recoverable: bool, can_save: bool) -> dict[str, Any]:
    return {
        "quality_status": quality_status,
        "diagnostic_kind": diagnostic_kind,
        "recoverable": recoverable,
        "user_message": build_user_message(diagnostic_kind, quality_status),
        "can_save": can_save,
    }


def evaluate_detail_quality(normalized: dict, raw_payload: object | None = None) -> dict[str, Any]:
    note_url = str(normalized.get("note_url") or "")
    if note_url and should_reject_short_explore_url(note_url):
        return _quality_result("invalid_source_url", "missing_xsec_token_short_explore", False, False)

    raw_text = ""
    if isinstance(raw_payload, dict):
        message = raw_payload.get("message") or raw_payload.get("msg") or ""
        raw_text = str(message)
    if is_xhs_rate_limit_signal(url=note_url, text=raw_text):
        return _quality_result("rate_limited", "xhs_rate_limited", True, False)

    has_strong_signal = _has_content(normalized) or _has_media(normalized) or _has_tags(normalized) or _has_recognized_detail_structure(raw_payload)
    if has_strong_signal:
        return _quality_result("valid_detail", None, False, True)

    if _has_weak_search_card_signal(normalized):
        return _quality_result("search_card_only", "empty_detail_payload", True, False)

    return _quality_result("empty_detail_payload", "empty_detail_payload", True, False)

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class XhsContentMapping:
    note_type: str
    note_url: str
    author_profile_url: str
    tags: list[str]
    engagement_metrics: dict[str, int]
    cover_url: str
    video_url: str
    asset_urls: list[str]
    publish_timestamp_ms: int | None


def map_xhs_content(
    note_id: str,
    raw: Mapping[str, Any] | None,
    *,
    cover_url: str | None = None,
    video_url: str | None = None,
    video_addr: str | None = None,
    image_urls: Sequence[str] | None = None,
    asset_urls: Sequence[str] | None = None,
) -> XhsContentMapping:
    payload: Mapping[str, Any] = raw if isinstance(raw, Mapping) else {}
    note_card = _first_note_card(payload)

    resolved_cover_url = _first_text(
        cover_url,
        payload.get("cover_url"),
        payload.get("cover"),
        _nested_get(note_card, "cover", "url"),
        _nested_get(note_card, "cover", "info_list", 0, "url"),
    )
    resolved_video_url = _first_text(
        video_url,
        video_addr,
        payload.get("video_url"),
        payload.get("video_addr"),
        _nested_get(note_card, "video", "url"),
        _nested_get(note_card, "video", "media", "stream", "h264", 0, "master_url"),
    )

    return XhsContentMapping(
        note_type=_first_note_type(
            payload.get("model_type"),
            payload.get("type"),
            payload.get("note_type"),
            payload.get("noteType"),
            note_card.get("type"),
            note_card.get("note_type"),
            note_card.get("noteType"),
            "note",
        ),
        note_url=_build_note_url(note_id, payload, note_card),
        author_profile_url=_build_author_profile_url(payload, note_card),
        tags=_extract_tags(payload, note_card),
        engagement_metrics=_extract_engagement_metrics(payload, note_card),
        cover_url=resolved_cover_url,
        video_url=resolved_video_url,
        asset_urls=_extract_asset_urls(
            payload,
            note_card,
            cover_url=resolved_cover_url,
            video_url=resolved_video_url,
            image_urls=image_urls,
            asset_urls=asset_urls,
        ),
        publish_timestamp_ms=_extract_publish_timestamp_ms(payload, note_card),
    )


def normalize_xhs_comment_payload(raw_payload: Any) -> list[dict[str, Any]]:
    return _flatten_comments(_extract_comment_list(raw_payload))


def _first_note_card(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    direct = payload.get("note_card")
    if isinstance(direct, Mapping):
        return direct
    card = _nested_get(payload, "data", "items", 0, "note_card")
    return card if isinstance(card, Mapping) else {}


def _first_item(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    item = _nested_get(payload, "data", "items", 0)
    return item if isinstance(item, Mapping) else {}


def _nested_get(value: Any, *path: str | int) -> Any:
    current = value
    for part in path:
        if isinstance(part, int):
            if not isinstance(current, Sequence) or isinstance(current, (str, bytes)) or len(current) <= part:
                return None
            current = current[part]
            continue
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return current


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _first_note_type(*values: Any) -> str:
    for value in values:
        normalized = _normalize_note_type(value)
        if normalized:
            return normalized
    return "note"


def _normalize_note_type(value: Any) -> str:
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, (int, float)):
        numeric = int(value)
        if numeric == 1:
            return "video"
        if numeric == 2:
            return "normal"
        return ""
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not text:
        return ""
    lowered = text.lower()
    if lowered == "1" or "video" in lowered or "视频" in text:
        return "video"
    if lowered == "2" or "normal" in lowered or "image" in lowered or "图文" in text:
        return "normal"
    return text


def _as_int(value: Any) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        cleaned = value.strip().lower().replace(",", "")
        multiplier = 1
        if cleaned.endswith("w"):
            multiplier = 10000
            cleaned = cleaned[:-1]
        try:
            return int(float(cleaned) * multiplier)
        except ValueError:
            return 0
    return 0


def _extract_engagement_metrics(payload: Mapping[str, Any], note_card: Mapping[str, Any]) -> dict[str, int]:
    direct = {
        "likes": _as_int(payload.get("liked_count") or payload.get("likes") or payload.get("like_count")),
        "comments": _as_int(payload.get("comment_count") or payload.get("comments")),
        "collects": _as_int(payload.get("collected_count") or payload.get("collects") or payload.get("collect_count")),
        "shares": _as_int(payload.get("share_count") or payload.get("shares")),
    }
    if any(direct.values()):
        return direct

    info = note_card.get("interact_info") if isinstance(note_card.get("interact_info"), Mapping) else {}
    return {
        "likes": _as_int(info.get("liked_count") or info.get("likes") or info.get("like_count")),
        "comments": _as_int(info.get("comment_count") or info.get("comments")),
        "collects": _as_int(info.get("collected_count") or info.get("collects") or info.get("collect_count")),
        "shares": _as_int(info.get("share_count") or info.get("shares")),
    }


def _build_note_url(note_id: str, payload: Mapping[str, Any], note_card: Mapping[str, Any]) -> str:
    direct = _first_text(payload.get("note_url"), payload.get("url"), payload.get("share_url"))
    if direct:
        return direct

    base_url = f"https://www.xiaohongshu.com/explore/{note_id}"
    for source in (note_card, _first_item(payload), payload):
        if not isinstance(source, Mapping):
            continue
        xsec_token = _first_text(source.get("xsec_token"))
        if xsec_token:
            xsec_source = _first_text(source.get("xsec_source"), "pc_feed")
            return f"{base_url}?xsec_token={xsec_token}&xsec_source={xsec_source}"
        direct_nested = _first_text(source.get("note_url"), source.get("url"), source.get("share_url"))
        if direct_nested:
            return direct_nested
    return base_url


def _build_author_profile_url(payload: Mapping[str, Any], note_card: Mapping[str, Any]) -> str:
    user = note_card.get("user") if isinstance(note_card.get("user"), Mapping) else {}
    author_id = _first_text(payload.get("author_id"), user.get("user_id"), user.get("id"))
    if not author_id:
        return ""
    return f"https://www.xiaohongshu.com/user/profile/{author_id}"


def _extract_tags(payload: Mapping[str, Any], note_card: Mapping[str, Any]) -> list[str]:
    tag_values = payload.get("tag_list")
    if not isinstance(tag_values, Sequence) or isinstance(tag_values, (str, bytes)):
        tag_values = payload.get("tags")
    if not isinstance(tag_values, Sequence) or isinstance(tag_values, (str, bytes)):
        tag_values = note_card.get("tag_list")
    if not isinstance(tag_values, Sequence) or isinstance(tag_values, (str, bytes)):
        return []
    return [_tag_name(tag) for tag in tag_values if _tag_name(tag)]


def _tag_name(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        return _first_text(value.get("name"), value.get("tag_name"), value.get("title"))
    return ""


def _extract_asset_urls(
    payload: Mapping[str, Any],
    note_card: Mapping[str, Any],
    *,
    cover_url: str,
    video_url: str,
    image_urls: Sequence[str] | None,
    asset_urls: Sequence[str] | None,
) -> list[str]:
    urls: list[str] = []
    _append_unique(urls, cover_url)
    _append_unique(urls, payload.get("image_url"))
    _append_texts(urls, image_urls)
    _append_texts(urls, asset_urls)
    _append_texts(urls, payload.get("asset_urls"))
    _append_note_card_image_urls(urls, note_card)
    _append_unique(urls, video_url)
    return urls


def _append_texts(target: list[str], values: Any) -> None:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return
    for value in values:
        _append_unique(target, value)


def _append_unique(target: list[str], value: Any) -> None:
    text = value.strip() if isinstance(value, str) else ""
    if text and text not in target:
        target.append(text)


def _append_note_card_image_urls(target: list[str], note_card: Mapping[str, Any]) -> None:
    images = note_card.get("image_list")
    if not isinstance(images, Sequence) or isinstance(images, (str, bytes)):
        return
    for image in images:
        if isinstance(image, str):
            _append_unique(target, image)
        elif isinstance(image, Mapping):
            _append_unique(target, image.get("url"))
            _append_unique(target, _nested_get(image, "info_list", 0, "url"))


def _comment_metric(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return 0
    multiplier = 1
    if text.endswith("万"):
        multiplier = 10000
        text = text[:-1]
    elif text.lower().endswith("w"):
        multiplier = 10000
        text = text[:-1]
    number_match = re.search(r"\d+(?:\.\d+)?", text)
    if not number_match:
        return 0
    return int(float(number_match.group(0)) * multiplier)


def _comment_id(comment: Mapping[str, Any]) -> str:
    return str(comment.get("comment_id") or comment.get("id") or comment.get("commentId") or "")


def _comment_user(comment: Mapping[str, Any]) -> Mapping[str, Any]:
    user = comment.get("user_info") or comment.get("user") or comment.get("author") or {}
    return user if isinstance(user, Mapping) else {}


def _comment_children(comment: Mapping[str, Any]) -> list[dict[str, Any]]:
    for key in ("sub_comments", "sub_comment", "comments", "replies", "children"):
        value = comment.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            return [item for item in value if isinstance(item, dict)]
    sub_comment_payload = comment.get("sub_comment_info")
    if isinstance(sub_comment_payload, Mapping):
        value = sub_comment_payload.get("comments")
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            return [item for item in value if isinstance(item, dict)]
    return []


def _normalize_comment(comment: Mapping[str, Any], parent_comment_id: str | None = None) -> dict[str, Any]:
    user = _comment_user(comment)
    return {
        "comment_id": _comment_id(comment),
        "user_name": str(user.get("nickname") or user.get("name") or comment.get("user_name") or ""),
        "user_id": str(user.get("user_id") or user.get("id") or comment.get("user_id") or "") or None,
        "content": str(comment.get("content") or comment.get("text") or comment.get("desc") or ""),
        "like_count": _comment_metric(comment.get("like_count") or comment.get("liked_count") or comment.get("likes")),
        "parent_comment_id": parent_comment_id,
        "created_at_remote": comment.get("create_time") or comment.get("created_at") or comment.get("time"),
        "raw_json": comment,
    }


def _flatten_comments(comments: list[dict[str, Any]], parent_comment_id: str | None = None) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for comment in comments:
        normalized = _normalize_comment(comment, parent_comment_id=parent_comment_id)
        if normalized["comment_id"]:
            flattened.append(normalized)
            child_parent_id = normalized["comment_id"]
        else:
            child_parent_id = parent_comment_id
        flattened.extend(_flatten_comments(_comment_children(comment), parent_comment_id=child_parent_id))
    return flattened


def _extract_comment_list(raw_payload: Any) -> list[dict[str, Any]]:
    if isinstance(raw_payload, Sequence) and not isinstance(raw_payload, (str, bytes)):
        return [item for item in raw_payload if isinstance(item, dict)]
    if not isinstance(raw_payload, Mapping):
        return []
    data = raw_payload.get("data") if isinstance(raw_payload.get("data"), Mapping) else raw_payload
    for key in ("comments", "items", "list"):
        value = data.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            return [item for item in value if isinstance(item, dict)]
    return []


def _extract_publish_timestamp_ms(payload: Mapping[str, Any], note_card: Mapping[str, Any]) -> int | None:
    for value in (
        payload.get("publish_timestamp_ms"),
        payload.get("publish_time"),
        payload.get("time"),
        payload.get("timestamp"),
        payload.get("create_time"),
        note_card.get("publish_time"),
        note_card.get("time"),
        note_card.get("last_update_time"),
    ):
        parsed = _parse_optional_int(value)
        if parsed is not None:
            return parsed
    return None


def _parse_optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(float(stripped))
        except ValueError:
            return None
    return None

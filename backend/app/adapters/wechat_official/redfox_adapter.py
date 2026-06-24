from __future__ import annotations

import re
from typing import Any

SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "api-key",
    "redfox_api_key",
    "redfox-api-key",
    "x-api-key",
    "authorization",
    "auth",
    "auth_key",
    "authkey",
    "cookie",
    "cookies",
    "set-cookie",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "key",
    "pass_ticket",
    "wap_sid2",
    "appmsg_token",
    "session",
    "sessionid",
    "sid",
    "uin",
}

DETAIL_OBJECT_KEYS = (
    "article",
    "detail",
    "work",
    "info",
    "articleInfo",
    "workInfo",
    "article_info",
    "work_info",
    "data",
)

ARTICLE_HINT_KEYS = (
    "title",
    "appmsg_title",
    "msg_title",
    "article_title",
    "nickname",
    "nick_name",
    "accountName",
    "account_name",
    "author",
    "readCount",
    "read_count",
    "read_num",
    "readNum",
    "content_url",
    "contentUrl",
    "workUrl",
    "workUuid",
    "article_url",
    "url",
)


class WechatOfficialRedfoxAdapter:
    def normalize_article_list(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        data = payload.get("data") if isinstance(payload, dict) else payload
        if isinstance(data, dict):
            for key in ("list", "items", "records", "data"):
                value = data.get(key)
                if isinstance(value, list):
                    return [self.normalize_article_detail(item) for item in value if isinstance(item, dict)]
            if self._looks_like_article(data):
                return [self.normalize_article_detail(data)]
        if isinstance(data, list):
            return [self.normalize_article_detail(item) for item in data if isinstance(item, dict)]
        return []

    def normalize_article_detail(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = _extract_article_detail_data(payload)
        raw = sanitize_payload(data)
        read_count = _int_value(data, "readCount", "read_count", "read_num", "readNum", "read", "readcnt", "read_cnt")
        follower_count = _optional_int(data.get("followerCount") or data.get("follower_count") or data.get("fansCount") or data.get("fans_count"))
        cover_url = _text_value(data.get("coverUrl") or data.get("cover_url") or data.get("cover"))
        content_html = _text_value(data.get("html") or data.get("contentHtml") or data.get("content_html") or data.get("articleHtml") or data.get("bodyHtml"))
        content_text = _text_value(data.get("content") or data.get("text") or data.get("body") or data.get("contentText") or data.get("content_text"))
        images = _normalize_images(data, cover_url=cover_url, content_html=content_html)
        comments = _normalize_comments(data)
        article_url = _text_value(
            data.get("workUrl")
            or data.get("work_url")
            or data.get("article_url")
            or data.get("contentUrl")
            or data.get("content_url")
            or data.get("url")
            or data.get("link")
            or data.get("source_url")
        )
        author_name = _text_value(
            data.get("author")
            or data.get("author_name")
            or data.get("accountName")
            or data.get("account_name")
            or data.get("nickname")
            or data.get("nick_name")
            or data.get("biz_name")
            or data.get("source_name")
        )
        return {
            "external_id": _text_value(data.get("workUuid") or data.get("work_uuid") or data.get("id")),
            "article_url": article_url,
            "title": _text_value(data.get("title") or data.get("appmsg_title") or data.get("msg_title") or data.get("article_title") or data.get("name")),
            "digest": _text_value(data.get("summary") or data.get("digest") or data.get("memo") or data.get("appmsg_digest") or data.get("abstract") or data.get("desc") or data.get("description")),
            "author_name": author_name,
            "account_name": author_name,
            "account": _text_value(data.get("account") or data.get("biz") or data.get("__biz") or data.get("fakeid") or data.get("fake_id") or data.get("accountId") or data.get("account_id")),
            "publish_time_remote": _text_value(data.get("publishTime") or data.get("publish_time")),
            "cover_url": cover_url,
            "content_url": article_url,
            "content_text": content_text,
            "content_html": content_html,
            "images": images,
            "comments": comments,
            "detail_completeness": {
                "has_cover": bool(cover_url),
                "has_text": bool(content_text),
                "has_html": bool(content_html),
                "image_count": len(images),
                "comment_count": len(comments),
            },
            "metrics": {
                "read_count": read_count,
                "like_count": _int_value(data, "likeCount", "like_count", "old_like_count", "like_num", "likeNum"),
                "wow_count": _int_value(data, "watchCount", "watch_count", "wow_count", "like_num2", "old_like_count_2"),
                "share_count": _int_value(data, "shareCount", "share_count", "share_num", "shareNum"),
                "comment_count": _int_value(data, "commentCount", "comment_count", "comment_num", "commentNum"),
            },
            "follower_count": follower_count,
            "low_follower_label": data.get("lowFollowerLabel") or data.get("low_follower_label"),
            "raw": raw,
        }

    def _looks_like_article(self, data: dict[str, Any]) -> bool:
        return _looks_like_article(data)


def _extract_article_detail_data(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if _looks_like_article(data):
        return data

    for key in DETAIL_OBJECT_KEYS:
        value = data.get(key)
        if isinstance(value, dict) and _looks_like_article(value):
            return value

    for key in DETAIL_OBJECT_KEYS:
        value = data.get(key)
        if not isinstance(value, dict):
            continue
        for nested_key in DETAIL_OBJECT_KEYS:
            nested = value.get(nested_key)
            if isinstance(nested, dict) and _looks_like_article(nested):
                return nested

    return data


def _looks_like_article(data: dict[str, Any]) -> bool:
    return isinstance(data, dict) and any(data.get(key) not in (None, "") for key in ARTICLE_HINT_KEYS)


def sanitize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).lower() in SENSITIVE_KEYS:
                cleaned[key] = "***redacted***"
            else:
                cleaned[key] = sanitize_payload(item)
        return cleaned
    if isinstance(value, list):
        return [sanitize_payload(item) for item in value]
    return value


def _normalize_images(data: dict[str, Any], *, cover_url: str, content_html: str) -> list[dict[str, Any]]:
    images: list[dict[str, Any]] = []
    if cover_url:
        images.append({"url": cover_url, "type": "cover", "alt": "", "width": None, "height": None, "source": "redfox_detail"})

    for key in ("images", "imageList", "image_list", "contentImages", "content_images", "mediaList", "media_list", "pics", "picList"):
        value = data.get(key)
        if isinstance(value, list):
            for item in value:
                image = _normalize_image_item(item)
                if image:
                    images.append(image)
        elif isinstance(value, dict):
            image = _normalize_image_item(value)
            if image:
                images.append(image)

    for url in _extract_html_images(content_html):
        images.append({"url": url, "type": "content", "alt": "", "width": None, "height": None, "source": "redfox_detail_html"})

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for image in images:
        url = _text_value(image.get("url"))
        if not _is_public_url(url) or url in seen:
            continue
        seen.add(url)
        image["url"] = url
        deduped.append(image)
    return deduped


def _normalize_image_item(item: Any) -> dict[str, Any] | None:
    if isinstance(item, str):
        url = _text_value(item)
        return {"url": url, "type": "content", "alt": "", "width": None, "height": None, "source": "redfox_detail"}
    if not isinstance(item, dict):
        return None
    url = _text_value(item.get("url") or item.get("src") or item.get("imageUrl") or item.get("image_url") or item.get("cdnUrl") or item.get("coverUrl"))
    if not url:
        return None
    return {
        "url": url,
        "type": _text_value(item.get("type") or item.get("asset_type") or "content") or "content",
        "alt": _text_value(item.get("alt") or item.get("title")),
        "width": _optional_int(item.get("width")),
        "height": _optional_int(item.get("height")),
        "source": "redfox_detail",
    }


def _extract_html_images(content_html: str) -> list[str]:
    if not content_html:
        return []
    pattern = re.compile(r"<img\b[^>]*?\bsrc=[\"']([^\"']+)[\"']", re.IGNORECASE)
    return [_text_value(match.group(1)) for match in pattern.finditer(content_html)]


def _is_public_url(url: str) -> bool:
    lowered = url.lower()
    return lowered.startswith("http://") or lowered.startswith("https://")


def _normalize_comments(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw_comments = None
    for key in ("comments", "commentList", "comment_list", "elected_comment", "electedComment", "hotComments", "hot_comments"):
        value = data.get(key)
        if value:
            raw_comments = value
            break
    if isinstance(raw_comments, dict):
        raw_comments = raw_comments.get("list") or raw_comments.get("items") or raw_comments.get("comments") or []
    if not isinstance(raw_comments, list):
        return []
    return [_normalize_comment(comment) for comment in raw_comments if isinstance(comment, dict)]


def _normalize_comment(comment: dict[str, Any]) -> dict[str, Any]:
    replies = comment.get("replies") or comment.get("reply") or comment.get("replyList") or comment.get("reply_list") or []
    if isinstance(replies, dict):
        replies = replies.get("list") or replies.get("items") or replies.get("reply_list") or []
    if not isinstance(replies, list):
        replies = []
    return {
        "comment_id": _text_value(comment.get("commentId") or comment.get("comment_id") or comment.get("content_id") or comment.get("id")),
        "user_name": _text_value(comment.get("nickName") or comment.get("nick_name") or comment.get("nickname") or comment.get("user_name")),
        "user_id": _text_value(comment.get("userId") or comment.get("user_id") or comment.get("openid")) or None,
        "content": _text_value(comment.get("content") or comment.get("text")),
        "like_count": _int_value(comment, "likeCount", "like_count", "likeNum", "like_num"),
        "created_at_remote": _text_value(comment.get("createTime") or comment.get("create_time") or comment.get("created_at")),
        "replies": [_normalize_reply(reply) for reply in replies if isinstance(reply, dict)],
        "raw": sanitize_payload(comment),
    }


def _normalize_reply(reply: dict[str, Any]) -> dict[str, Any]:
    return {
        "reply_id": _text_value(reply.get("replyId") or reply.get("reply_id") or reply.get("content_id") or reply.get("id")),
        "user_name": _text_value(reply.get("nickName") or reply.get("nick_name") or reply.get("nickname") or reply.get("user_name")),
        "user_id": _text_value(reply.get("userId") or reply.get("user_id") or reply.get("openid")) or None,
        "content": _text_value(reply.get("content") or reply.get("text")),
        "like_count": _int_value(reply, "likeCount", "like_count", "likeNum", "like_num"),
        "created_at_remote": _text_value(reply.get("createTime") or reply.get("create_time") or reply.get("created_at")),
        "raw": sanitize_payload(reply),
    }


def _text_value(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "none" else text


def _int_value(data: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = data.get(key)
        parsed = _optional_int(value)
        if parsed is not None:
            return parsed
    return 0


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None

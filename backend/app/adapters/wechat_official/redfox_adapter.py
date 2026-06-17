from __future__ import annotations

from typing import Any

SENSITIVE_KEYS = {"api_key", "apikey", "redfox_api_key", "redfox-api-key", "x-api-key", "authorization", "token", "key"}


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
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        raw = sanitize_payload(data)
        read_count = _int_value(data, "readCount", "read_count", "read_num")
        follower_count = _optional_int(data.get("followerCount") or data.get("follower_count") or data.get("fansCount") or data.get("fans_count"))
        return {
            "external_id": str(data.get("workUuid") or data.get("work_uuid") or data.get("id") or ""),
            "article_url": str(data.get("workUrl") or data.get("article_url") or data.get("url") or data.get("contentUrl") or ""),
            "title": str(data.get("title") or ""),
            "digest": str(data.get("summary") or data.get("digest") or data.get("memo") or ""),
            "author_name": str(data.get("author") or data.get("accountName") or data.get("account_name") or ""),
            "account_name": str(data.get("accountName") or data.get("account_name") or data.get("author") or ""),
            "account": str(data.get("account") or data.get("biz") or data.get("accountId") or ""),
            "publish_time_remote": str(data.get("publishTime") or data.get("publish_time") or ""),
            "cover_url": str(data.get("coverUrl") or data.get("cover_url") or ""),
            "content_url": str(data.get("workUrl") or data.get("contentUrl") or data.get("url") or ""),
            "content_text": str(data.get("content") or data.get("text") or ""),
            "content_html": str(data.get("html") or data.get("contentHtml") or ""),
            "metrics": {
                "read_count": read_count,
                "like_count": _int_value(data, "likeCount", "like_count", "old_like_count"),
                "wow_count": _int_value(data, "watchCount", "watch_count", "wow_count"),
                "share_count": _int_value(data, "shareCount", "share_count"),
                "comment_count": _int_value(data, "commentCount", "comment_count"),
            },
            "follower_count": follower_count,
            "low_follower_label": data.get("lowFollowerLabel") or data.get("low_follower_label"),
            "raw": raw,
        }

    def _looks_like_article(self, data: dict[str, Any]) -> bool:
        return bool(data.get("title") or data.get("workUrl") or data.get("workUuid"))


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

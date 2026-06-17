from __future__ import annotations

import json
import re
from html import unescape
from typing import Any


class WechatOfficialResearchAdapter:
    """Offline parser/normalizer for WeChat Official research payloads.

    This adapter intentionally performs no network I/O. Tests and API callers pass
    captured/upstream payloads for this phase.
    """

    def normalize_searchbiz_accounts(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        rows = payload.get("list") or payload.get("items") or payload.get("data", {}).get("list") or []
        accounts: list[dict[str, Any]] = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            nickname = str(row.get("nickname") or row.get("name") or "").strip()
            fake_id = str(row.get("fakeid") or row.get("fake_id") or row.get("fakeId") or "").strip()
            accounts.append(
                {
                    "fake_id": fake_id,
                    "name": nickname,
                    "alias": str(row.get("alias") or "").strip(),
                    "avatar": str(row.get("round_head_img") or row.get("avatar") or row.get("head_img") or "").strip(),
                    "signature": str(row.get("signature") or "").strip(),
                    "service_type": row.get("service_type"),
                    "raw": row,
                }
            )
        return accounts

    def normalize_appmsgpublish_articles(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        publish_page = payload.get("publish_page")
        if isinstance(publish_page, str):
            try:
                page = json.loads(publish_page)
            except json.JSONDecodeError:
                page = {}
        elif isinstance(publish_page, dict):
            page = publish_page
        else:
            page = payload

        appmsg_entries: list[dict[str, Any]] = []
        publish_list = page.get("publish_list") or page.get("list") or []
        if isinstance(publish_list, list):
            for publish in publish_list:
                if not isinstance(publish, dict):
                    continue
                publish_info = publish.get("publish_info") or publish
                if isinstance(publish_info, str):
                    try:
                        publish_info = json.loads(publish_info)
                    except json.JSONDecodeError:
                        publish_info = {}
                appmsgex = publish_info.get("appmsgex") if isinstance(publish_info, dict) else None
                if isinstance(appmsgex, list):
                    appmsg_entries.extend([entry for entry in appmsgex if isinstance(entry, dict)])
        if not appmsg_entries and isinstance(page.get("appmsgex"), list):
            appmsg_entries = [entry for entry in page["appmsgex"] if isinstance(entry, dict)]

        articles: list[dict[str, Any]] = []
        for entry in appmsg_entries:
            articles.append(
                {
                    "aid": str(entry.get("aid") or entry.get("appmsgid") or ""),
                    "title": str(entry.get("title") or "").strip(),
                    "digest": str(entry.get("digest") or "").strip(),
                    "article_url": str(entry.get("link") or entry.get("content_url") or "").strip(),
                    "cover_url": str(entry.get("cover") or entry.get("cover_url") or "").strip(),
                    "publish_time_remote": str(entry.get("update_time") or entry.get("create_time") or "") or None,
                    "author_name": str(entry.get("author") or "").strip(),
                    "raw": entry,
                }
            )
        return articles

    def parse_html_snapshot(self, html: str) -> dict[str, Any]:
        if not html or not html.strip():
            return {"status": "parse_failed", "text": "", "comment_id": ""}
        lowered = html.lower()
        if "已被发布者删除" in html or "content has been deleted" in lowered:
            status = "deleted"
        elif "违规" in html or "违反" in html or "violation" in lowered:
            status = "violation"
        elif "风险" in html or "环境异常" in html or "risk" in lowered:
            status = "risk"
        elif 'id="js_article"' in html or "id='js_article'" in html or "id=js_article" in html:
            status = "ok"
        else:
            status = "parse_failed"

        content_match = re.search(r"<[^>]+id=[\"']js_content[\"'][^>]*>(.*?)</[^>]+>", html, flags=re.I | re.S)
        source = content_match.group(1) if content_match else html
        text = _html_to_text(source)
        comment_id = _first_match(html, [r"comment_id\s*[=:]\s*[\"']([^\"']+)", r"comment_id\s*[=:]\s*(\d+)"])
        return {"status": status, "text": text, "comment_id": comment_id}

    def parse_metrics(self, *, html: str | None = None, cgi_data: dict[str, Any] | None = None) -> dict[str, Any]:
        source = "cgi_data"
        data = cgi_data if isinstance(cgi_data, dict) else None
        if data is None:
            data = self._extract_metrics_json(html or "")
            source = "html"
        stat = data.get("appmsgstat") if isinstance(data.get("appmsgstat"), dict) else data
        return {
            "read_count": _to_int(stat.get("read_count", stat.get("read_num", 0))),
            "wow_count": _to_int(stat.get("old_like_count", stat.get("wow_count", 0))),
            "share_count": _to_int(stat.get("share_count", 0)),
            "like_count": _to_int(stat.get("like_count", 0)),
            "comment_count": _to_int(stat.get("comment_count", 0)),
            "raw": data,
            "source": source,
        }

    def normalize_comments(self, payload: dict[str, Any], limit: int = 50) -> list[dict[str, Any]]:
        rows = payload.get("elected_comment") or payload.get("comments") or payload.get("comment") or []
        if isinstance(rows, dict):
            rows = rows.get("list") or []
        comments: list[dict[str, Any]] = []
        for row in rows[: max(0, limit)] if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            replies_payload = row.get("reply") or row.get("reply_list") or {}
            replies = replies_payload.get("reply_list") if isinstance(replies_payload, dict) else replies_payload
            normalized_replies = []
            for reply in replies if isinstance(replies, list) else []:
                if not isinstance(reply, dict):
                    continue
                normalized_replies.append(_normalize_comment_like(reply, id_key="reply_id"))
            comment = _normalize_comment_like(row, id_key="comment_id")
            comment["replies"] = normalized_replies
            comments.append(comment)
        return comments

    def _extract_metrics_json(self, html: str) -> dict[str, Any]:
        for name in ["window.cgiDataNew", "cgiDataNew", "appmsg_bar_data"]:
            match = re.search(re.escape(name) + r"\s*=\s*(\{.*?\})\s*(?:;|</script>)", html, flags=re.S)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
        return {}


def _normalize_comment_like(row: dict[str, Any], *, id_key: str) -> dict[str, Any]:
    normalized_id = str(row.get("content_id") or row.get(id_key) or row.get("id") or "").strip()
    return {
        id_key: normalized_id,
        "user_name": str(row.get("nick_name") or row.get("nickname") or row.get("user_name") or "").strip(),
        "user_id": str(row.get("user_id") or row.get("openid") or "").strip() or None,
        "content": str(row.get("content") or "").strip(),
        "like_count": _to_int(row.get("like_num", row.get("like_count", 0))),
        "created_at_remote": str(row.get("create_time") or row.get("created_at") or "") or None,
        "raw": row,
    }


def _html_to_text(html: str) -> str:
    text = re.sub(r"<script.*?</script>", " ", html, flags=re.I | re.S)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _first_match(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return ""


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0

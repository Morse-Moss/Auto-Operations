from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import urlparse

import requests

from backend.app.services.wechat_official_provider_types import WechatOfficialProviderError, sanitize_provider_payload

WECHAT_ARTICLE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.43",
    "Referer": "https://mp.weixin.qq.com/",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


class WechatOfficialArticlePageProvider:
    def __init__(self, *, timeout: float = 30.0) -> None:
        self.timeout = timeout

    def fetch_article(self, *, url: str) -> dict[str, Any]:
        if not _is_wechat_article_url(url):
            raise WechatOfficialProviderError(
                provider="article_page",
                stage="fetch",
                message="只支持公开微信公众号文章 URL",
                details={"url": url, "reason": "unsupported_url", "next_action": "请粘贴 mp.weixin.qq.com/s/ 开头的公开文章 URL"},
            )
        try:
            response = requests.get(url, headers=WECHAT_ARTICLE_HEADERS, timeout=self.timeout)
            response.raise_for_status()
        except requests.Timeout as exc:
            raise WechatOfficialProviderError(
                provider="article_page",
                stage="fetch",
                message="公开文章页请求超时",
                details={"url": url, "reason": "timeout", "next_action": "请稍后重试，或降低采集频率"},
            ) from exc
        except requests.RequestException as exc:
            raise WechatOfficialProviderError(
                provider="article_page",
                stage="fetch",
                message="公开文章页请求失败",
                details={"url": url, "reason": "network_error", "error": str(exc), "next_action": "请检查网络或稍后重试"},
            ) from exc
        return parse_article_page(url=url, html_text=response.text)


def parse_article_page(*, url: str, html_text: str) -> dict[str, Any]:
    _raise_for_failure_page(url=url, html_text=html_text)
    title = _first_text(
        html_text,
        [
            r'<h1[^>]*(?:id=["\']activity-name["\']|class=["\'][^"\']*rich_media_title[^"\']*["\'])[^>]*>([\s\S]*?)</h1>',
            r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
            r'<title[^>]*>([\s\S]*?)</title>',
        ],
    )
    account_name = _first_text(
        html_text,
        [
            r'<span[^>]*id=["\']js_name["\'][^>]*>([\s\S]*?)</span>',
            r'<a[^>]*id=["\']js_name["\'][^>]*>([\s\S]*?)</a>',
            r'var\s+nickname\s*=\s*["\']([^"\']+)["\']',
        ],
    )
    publish_time = _first_text(html_text, [r'<em[^>]*id=["\']publish_time["\'][^>]*>([\s\S]*?)</em>'])
    digest = _first_attr(html_text, [r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']*)["\']'])
    content_html = _extract_content_html(html_text)
    content_text = _html_to_text(content_html)
    images = _extract_images(html_text=html_text, content_html=content_html)

    if not title or not content_text:
        raise WechatOfficialProviderError(
            provider="article_page",
            stage="parse",
            message="未能从公开文章页解析出标题和正文；请确认 URL 是公开微信公众号文章，或稍后重试 Redfox",
            details={"url": url, "reason": "parse_failed", "next_action": "请换一个公开文章 URL，或稍后重试 Redfox 详情接口"},
        )

    return {
        "external_id": f"article_page:{_article_slug(url)}",
        "article_url": url,
        "content_url": url,
        "title": title,
        "digest": digest,
        "author_name": account_name,
        "account_name": account_name,
        "account": account_name,
        "publish_time_remote": publish_time,
        "cover_url": _first_image_url(images),
        "content_text": content_text,
        "content_html": content_html,
        "images": images,
        "comments": [],
        "detail_completeness": {"has_text": bool(content_text), "has_html": bool(content_html), "image_count": len(images)},
        "metrics": {"read_count": 0, "like_count": 0, "wow_count": 0, "share_count": 0, "comment_count": 0},
        "raw": sanitize_provider_payload({"source": "article_page", "url": url}),
    }


def _is_wechat_article_url(url: str) -> bool:
    parsed = urlparse(str(url or ""))
    return parsed.scheme in {"http", "https"} and parsed.netloc.lower() == "mp.weixin.qq.com" and parsed.path.startswith("/s")


def _raise_for_failure_page(*, url: str, html_text: str) -> None:
    text = _html_to_text(html_text)
    if "环境异常" in text or "完成验证" in text:
        raise WechatOfficialProviderError(
            provider="article_page",
            stage="fetch",
            message="需要完成微信验证后才能访问该文章",
            details={
                "url": url,
                "reason": "verification_required",
                "browser_fallback": "manual_verification_required",
                "retry_policy": "do_not_auto_retry",
                "next_action": "请在浏览器打开文章完成人工验证后重试；系统不会自动绕过验证码或风控验证",
            },
        )
    if "已被发布者删除" in text or "内容已被删除" in text or "无法查看" in text:
        raise WechatOfficialProviderError(
            provider="article_page",
            stage="fetch",
            message="文章已删除或不可访问",
            details={"url": url, "reason": "deleted_or_unavailable", "next_action": "请更换公开文章 URL"},
        )


def _extract_content_html(html_text: str) -> str:
    match = re.search(r'<div[^>]*id=["\']js_content["\'][^>]*>[\s\S]*?</div>', html_text, flags=re.IGNORECASE)
    if match:
        return _clean_html(match.group(0))
    match = re.search(r'<div[^>]*class=["\'][^"\']*rich_media_content[^"\']*["\'][^>]*>[\s\S]*?</div>', html_text, flags=re.IGNORECASE)
    if match:
        return _clean_html(match.group(0))
    return ""


def _clean_html(value: str) -> str:
    value = re.sub(r'<script[^>]*>[\s\S]*?</script>', "", value, flags=re.IGNORECASE)
    return value.strip()


def _extract_images(*, html_text: str, content_html: str) -> list[dict[str, Any]]:
    images: list[dict[str, Any]] = []
    seen: set[str] = set()
    cover_url = _first_attr(html_text, [r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']'])
    if cover_url:
        seen.add(cover_url)
        images.append({"url": cover_url, "type": "cover", "alt": "", "width": None, "height": None, "source": "article_page"})
    for tag in re.findall(r'<img[^>]*>', content_html, flags=re.IGNORECASE):
        url = _attr(tag, "data-src") or _attr(tag, "src")
        if not url or url.startswith("data:") or url in seen:
            continue
        seen.add(url)
        images.append({"url": url, "type": "content", "alt": _attr(tag, "alt"), "width": None, "height": None, "source": "article_page"})
    return images


def _first_image_url(images: list[dict[str, Any]]) -> str:
    for image in images:
        url = str(image.get("url") or "").strip()
        if url:
            return url
    return ""


def _first_text(html_text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, html_text, flags=re.IGNORECASE)
        if match:
            return _normalize_text(match.group(1))
    return ""


def _first_attr(html_text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, html_text, flags=re.IGNORECASE)
        if match:
            return html.unescape(match.group(1)).strip()
    return ""


def _attr(tag: str, name: str) -> str:
    match = re.search(rf'{name}=["\']([^"\']*)["\']', tag, flags=re.IGNORECASE)
    return html.unescape(match.group(1)).strip() if match else ""


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", _html_to_text(value)).strip()


def _html_to_text(value: str) -> str:
    text = re.sub(r'<br\s*/?>', "\n", value, flags=re.IGNORECASE)
    text = re.sub(r'</(?:p|div|section|h[1-6]|li)>', "\n", text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', "", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _article_slug(url: str) -> str:
    parsed = urlparse(url)
    return parsed.path.rsplit("/", 1)[-1] or parsed.netloc

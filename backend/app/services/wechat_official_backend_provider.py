from __future__ import annotations

from typing import Any, Protocol

import requests

from backend.app.services.wechat_official_provider_types import WechatOfficialProviderError, sanitize_provider_payload

PROVIDER_NAME = "wechat_backend"
ENDPOINTS = {
    "searchbiz": "https://mp.weixin.qq.com/cgi-bin/searchbiz",
    "appmsgpublish": "https://mp.weixin.qq.com/cgi-bin/appmsgpublish",
}


class WechatOfficialBackendTransport(Protocol):
    def get_json(self, endpoint: str, *, params: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]: ...


class RequestsWechatOfficialBackendTransport:
    def __init__(self, *, timeout: float = 30.0) -> None:
        self.timeout = timeout

    def get_json(self, endpoint: str, *, params: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        url = ENDPOINTS.get(endpoint)
        if not url:
            raise WechatOfficialProviderError(
                provider=PROVIDER_NAME,
                stage=endpoint,
                message="不支持的微信公众号后台接口",
                details={"reason": "unsupported_endpoint"},
            )
        request_headers = {
            **headers,
            "Referer": "https://mp.weixin.qq.com/",
            "Origin": "https://mp.weixin.qq.com",
        }
        try:
            response = requests.get(url, params=params, headers=request_headers, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
        except requests.Timeout as exc:
            raise WechatOfficialProviderError(
                provider=PROVIDER_NAME,
                stage=endpoint,
                message="微信公众号后台请求超时",
                details={"reason": "timeout"},
            ) from exc
        except requests.RequestException as exc:
            raise WechatOfficialProviderError(
                provider=PROVIDER_NAME,
                stage=endpoint,
                message="微信公众号后台请求失败",
                details={"reason": "network_error", "error": str(exc)},
            ) from exc
        except ValueError as exc:
            raise WechatOfficialProviderError(
                provider=PROVIDER_NAME,
                stage=endpoint,
                message="微信公众号后台返回不是有效 JSON",
                details={"reason": "invalid_json"},
            ) from exc
        if not isinstance(payload, dict):
            raise WechatOfficialProviderError(
                provider=PROVIDER_NAME,
                stage=endpoint,
                message="微信公众号后台返回格式异常",
                details={"reason": "invalid_payload", "payload_type": type(payload).__name__},
            )
        return payload


class WechatOfficialBackendProvider:
    def __init__(self, *, transport: WechatOfficialBackendTransport | None = None) -> None:
        self.transport = transport or RequestsWechatOfficialBackendTransport()

    def search_accounts(self, keyword: str, cookie: str, token: str, user_agent: str) -> list[dict[str, Any]]:
        stage = "searchbiz"
        payload = self._get_json(
            stage,
            params={"action": "search_biz", "query": keyword, "token": token, "lang": "zh_CN", "f": "json"},
            headers=_headers(cookie=cookie, user_agent=user_agent),
            secrets=(cookie, token),
        )
        _raise_for_base_resp_error(payload, stage=stage)
        items = payload.get("list") if isinstance(payload, dict) else []
        if not isinstance(items, list):
            return []
        return [_normalize_account(item) for item in items if isinstance(item, dict)]

    def sync_account_articles(
        self,
        fake_id: str,
        cookie: str,
        token: str,
        user_agent: str,
        begin: int = 0,
        count: int = 5,
    ) -> list[dict[str, Any]]:
        stage = "appmsgpublish"
        payload = self._get_json(
            stage,
            params={
                "sub": "list",
                "search_field": "null",
                "begin": begin,
                "count": count,
                "fakeid": fake_id,
                "type": "101_1",
                "token": token,
                "lang": "zh_CN",
                "f": "json",
            },
            headers=_headers(cookie=cookie, user_agent=user_agent),
            secrets=(cookie, token),
        )
        _raise_for_base_resp_error(payload, stage=stage)
        articles: list[dict[str, Any]] = []
        for publish_item in _publish_list(payload):
            publish_info = publish_item.get("publish_info") if isinstance(publish_item, dict) else None
            appmsgex = publish_info.get("appmsgex") if isinstance(publish_info, dict) else None
            if not isinstance(appmsgex, list):
                continue
            articles.extend(_normalize_article(item) for item in appmsgex if isinstance(item, dict))
        return articles

    def _get_json(
        self,
        endpoint: str,
        *,
        params: dict[str, Any],
        headers: dict[str, str],
        secrets: tuple[str, ...],
    ) -> dict[str, Any]:
        try:
            payload = self.transport.get_json(endpoint, params=params, headers=headers)
        except WechatOfficialProviderError:
            raise
        except Exception as exc:
            raise WechatOfficialProviderError(
                provider=PROVIDER_NAME,
                stage=endpoint,
                message="微信公众号后台请求失败",
                details={"reason": "transport_error", "error": _redact_secret_values(str(exc), secrets)},
            ) from exc
        if not isinstance(payload, dict):
            raise WechatOfficialProviderError(
                provider=PROVIDER_NAME,
                stage=endpoint,
                message="微信公众号后台返回格式异常",
                details={"reason": "invalid_payload", "payload_type": type(payload).__name__},
            )
        return payload


def _headers(*, cookie: str, user_agent: str) -> dict[str, str]:
    return {"Cookie": cookie, "User-Agent": user_agent}


def _raise_for_base_resp_error(payload: dict[str, Any], *, stage: str) -> None:
    base_resp = payload.get("base_resp")
    if not isinstance(base_resp, dict):
        return
    ret = base_resp.get("ret")
    if ret in (None, 0, "0"):
        return
    raise WechatOfficialProviderError(
        provider=PROVIDER_NAME,
        stage=stage,
        message="微信公众号后台返回错误",
        details={"ret": ret, "base_resp": sanitize_provider_payload(base_resp)},
    )


def _normalize_account(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "fake_id": _text(item.get("fakeid") or item.get("fake_id")),
        "name": _text(item.get("nickname") or item.get("name")),
        "alias": _text(item.get("alias")),
        "avatar_url": _text(item.get("round_head_img") or item.get("avatar_url") or item.get("head_img")),
        "raw": sanitize_provider_payload(item),
    }


def _publish_list(payload: dict[str, Any]) -> list[Any]:
    publish_page = payload.get("publish_page")
    if not isinstance(publish_page, dict):
        return []
    publish_list = publish_page.get("publish_list")
    if not isinstance(publish_list, list):
        return []
    return publish_list


def _normalize_article(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "article_url": _text(item.get("link") or item.get("article_url")),
        "title": _text(item.get("title")),
        "digest": _text(item.get("digest")),
        "author_name": _text(item.get("author") or item.get("author_name")),
        "cover_url": _text(item.get("cover") or item.get("cover_url")),
        "publish_time_remote": _text(item.get("update_time") or item.get("publish_time") or item.get("create_time")),
        "raw": sanitize_provider_payload(item),
    }


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _redact_secret_values(value: str, secrets: tuple[str, ...]) -> str:
    redacted = value
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    return redacted

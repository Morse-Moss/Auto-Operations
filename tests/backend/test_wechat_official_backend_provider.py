from __future__ import annotations

import pytest

from backend.app.services.wechat_official_backend_provider import RequestsWechatOfficialBackendTransport, WechatOfficialBackendProvider
from backend.app.services.wechat_official_provider_types import WechatOfficialProviderError


class FakeTransport:
    def __init__(self, responses: dict[str, dict] | None = None, error: Exception | None = None) -> None:
        self.responses = responses or {}
        self.error = error
        self.calls: list[dict] = []

    def get_json(self, endpoint: str, *, params: dict, headers: dict) -> dict:
        self.calls.append({"endpoint": endpoint, "params": params, "headers": headers})
        if self.error:
            raise self.error
        return self.responses[endpoint]


def test_requests_transport_calls_mp_endpoint_with_safe_headers(monkeypatch) -> None:
    calls = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"base_resp": {"ret": 0}, "list": []}

    def fake_get(url: str, **kwargs):
        calls.append({"url": url, "kwargs": kwargs})
        return FakeResponse()

    monkeypatch.setattr("backend.app.services.wechat_official_backend_provider.requests.get", fake_get)

    payload = RequestsWechatOfficialBackendTransport().get_json(
        "searchbiz",
        params={"action": "search_biz", "query": "摩斯", "token": "secret-token", "lang": "zh_CN", "f": "json"},
        headers={"Cookie": "secret-cookie", "User-Agent": "UA"},
    )

    assert payload == {"base_resp": {"ret": 0}, "list": []}
    assert calls == [
        {
            "url": "https://mp.weixin.qq.com/cgi-bin/searchbiz",
            "kwargs": {
                "params": {"action": "search_biz", "query": "摩斯", "token": "secret-token", "lang": "zh_CN", "f": "json"},
                "headers": {"Cookie": "secret-cookie", "User-Agent": "UA", "Referer": "https://mp.weixin.qq.com/", "Origin": "https://mp.weixin.qq.com"},
                "timeout": 30,
            },
        }
    ]


def test_requests_transport_rejects_unknown_endpoint() -> None:
    with pytest.raises(WechatOfficialProviderError) as exc_info:
        RequestsWechatOfficialBackendTransport().get_json("unknown", params={}, headers={})

    error_dict = exc_info.value.to_dict()
    assert error_dict["provider"] == "wechat_backend"
    assert error_dict["stage"] == "unknown"
    assert error_dict["details"]["reason"] == "unsupported_endpoint"


def test_search_accounts_calls_searchbiz_and_normalizes_accounts() -> None:
    transport = FakeTransport(
        {
            "searchbiz": {
                "base_resp": {"ret": 0},
                "list": [
                    {
                        "fakeid": "MzFakeId",
                        "nickname": "摩斯增长实验室",
                        "alias": "morse-lab",
                        "round_head_img": "https://example.com/avatar.jpg",
                        "extra": "kept",
                    }
                ],
            }
        }
    )
    provider = WechatOfficialBackendProvider(transport=transport)

    accounts = provider.search_accounts("摩斯", cookie="secret-cookie", token="secret-token", user_agent="UA")

    assert accounts == [
        {
            "fake_id": "MzFakeId",
            "name": "摩斯增长实验室",
            "alias": "morse-lab",
            "avatar_url": "https://example.com/avatar.jpg",
            "raw": {
                "fakeid": "MzFakeId",
                "nickname": "摩斯增长实验室",
                "alias": "morse-lab",
                "round_head_img": "https://example.com/avatar.jpg",
                "extra": "kept",
            },
        }
    ]
    assert transport.calls == [
        {
            "endpoint": "searchbiz",
            "params": {"action": "search_biz", "query": "摩斯", "token": "secret-token", "lang": "zh_CN", "f": "json"},
            "headers": {"Cookie": "secret-cookie", "User-Agent": "UA"},
        }
    ]


def test_sync_account_articles_calls_appmsgpublish_and_normalizes_publish_list() -> None:
    transport = FakeTransport(
        {
            "appmsgpublish": {
                "base_resp": {"ret": 0},
                "publish_page": {
                    "publish_list": [
                        {
                            "publish_info": {
                                "appmsgex": [
                                    {
                                        "link": "https://mp.weixin.qq.com/s/article-a",
                                        "title": "第一篇",
                                        "digest": "摘要",
                                        "author": "作者",
                                        "cover": "https://example.com/cover.jpg",
                                        "update_time": 1710000000,
                                    }
                                ]
                            }
                        }
                    ]
                },
            }
        }
    )
    provider = WechatOfficialBackendProvider(transport=transport)

    articles = provider.sync_account_articles("MzFakeId", cookie="secret-cookie", token="secret-token", user_agent="UA", begin=10, count=3)

    assert articles == [
        {
            "article_url": "https://mp.weixin.qq.com/s/article-a",
            "title": "第一篇",
            "digest": "摘要",
            "author_name": "作者",
            "cover_url": "https://example.com/cover.jpg",
            "publish_time_remote": "1710000000",
            "raw": {
                "link": "https://mp.weixin.qq.com/s/article-a",
                "title": "第一篇",
                "digest": "摘要",
                "author": "作者",
                "cover": "https://example.com/cover.jpg",
                "update_time": 1710000000,
            },
        }
    ]
    assert transport.calls == [
        {
            "endpoint": "appmsgpublish",
            "params": {
                "sub": "list",
                "search_field": "null",
                "begin": 10,
                "count": 3,
                "fakeid": "MzFakeId",
                "type": "101_1",
                "token": "secret-token",
                "lang": "zh_CN",
                "f": "json",
            },
            "headers": {"Cookie": "secret-cookie", "User-Agent": "UA"},
        }
    ]


@pytest.mark.parametrize(
    ("method_name", "kwargs", "stage"),
    [
        ("search_accounts", {"keyword": "摩斯", "cookie": "secret-cookie", "token": "secret-token", "user_agent": "UA"}, "searchbiz"),
        (
            "sync_account_articles",
            {"fake_id": "MzFakeId", "cookie": "secret-cookie", "token": "secret-token", "user_agent": "UA"},
            "appmsgpublish",
        ),
    ],
)
def test_base_resp_error_raises_provider_error_without_leaking_credentials(method_name: str, kwargs: dict, stage: str) -> None:
    transport = FakeTransport({stage: {"base_resp": {"ret": 200003, "err_msg": "invalid csrf token"}}})
    provider = WechatOfficialBackendProvider(transport=transport)

    with pytest.raises(WechatOfficialProviderError) as exc_info:
        getattr(provider, method_name)(**kwargs)

    error_dict = exc_info.value.to_dict()
    assert error_dict["provider"] == "wechat_backend"
    assert error_dict["stage"] == stage
    assert error_dict["details"]["ret"] == 200003
    assert "secret-cookie" not in str(error_dict)
    assert "secret-token" not in str(error_dict)


def test_transport_errors_are_wrapped_as_provider_error_without_leaking_credentials() -> None:
    transport = FakeTransport(error=RuntimeError("socket closed with secret-cookie secret-token"))
    provider = WechatOfficialBackendProvider(transport=transport)

    with pytest.raises(WechatOfficialProviderError) as exc_info:
        provider.search_accounts("摩斯", cookie="secret-cookie", token="secret-token", user_agent="UA")

    error_dict = exc_info.value.to_dict()
    assert error_dict["provider"] == "wechat_backend"
    assert error_dict["stage"] == "searchbiz"
    assert error_dict["details"]["reason"] == "transport_error"
    assert "secret-cookie" not in str(error_dict)
    assert "secret-token" not in str(error_dict)

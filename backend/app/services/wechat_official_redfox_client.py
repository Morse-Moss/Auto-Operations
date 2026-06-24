from __future__ import annotations

from typing import Any

import requests


class WechatOfficialRedfoxClient:
    def __init__(self, *, base_url: str, api_key: str, timeout: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def search_articles(self, *, keyword: str, offset: int = 0, sort_type: str = "_4") -> dict[str, Any]:
        return self._post("/story/api/gzhData/searchArticle", {"keyword": keyword, "offset": offset, "sortType": sort_type})

    def query_work_list(
        self,
        *,
        account: str,
        account_name: str = "",
        offset: int = 0,
        sort_type: str = "_4",
        publish_time_start: str | None = None,
        publish_time_end: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"account": account, "offset": offset, "sortType": sort_type}
        if account_name:
            payload["accountName"] = account_name
        if publish_time_start:
            payload["publishTimeStart"] = publish_time_start
        if publish_time_end:
            payload["publishTimeEnd"] = publish_time_end
        return self._post("/story/api/gzhData/queryWorkList", payload)

    def query_article_detail(self, *, url: str) -> dict[str, Any]:
        return self._post("/story/api/gzhData/queryArticleDetail", {"url": url}, timeout=max(self.timeout, 60.0))

    def validate_key(self) -> dict[str, Any]:
        return self._post("/story/api/gzhData/searchArticle", {"keyword": "test", "offset": 0, "sortType": "_0"})

    def _post(self, path: str, payload: dict[str, Any], *, timeout: float | None = None) -> dict[str, Any]:
        response = requests.post(
            f"{self.base_url}{path}",
            headers={"REDFOX_API_KEY": self.api_key, "Content-Type": "application/json"},
            json=payload,
            timeout=timeout or self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise RedfoxApiError("Redfox response is not a JSON object")
        code = data.get("code")
        if code not in (None, 0, 200, 2000, "0", "200", "2000"):
            raise RedfoxApiError(str(data.get("msg") or data.get("message") or f"Redfox API error: {code}"))
        return data


class RedfoxApiError(RuntimeError):
    pass

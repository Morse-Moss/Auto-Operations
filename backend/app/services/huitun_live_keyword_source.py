from __future__ import annotations

from typing import Any

import requests

from backend.app.services.account_service import decode_cookie_text
from backend.app.services.huitun_account_service import validate_huitun_login_state
from backend.app.services.huitun_crypto import HUITUN_EXT_DATA_DECRYPT_FAILED_MESSAGE, decrypt_huitun_ext_data
from backend.app.services.huitun_keyword_source import dedupe_keyword_candidates, prioritize_exact_hotword_rows

HUITUN_HOTWORD_SEARCH_URL = "https://xhsapi.huitun.com/hotword/search/v2"
HUITUN_LIVE_FAILED_MESSAGE = "灰豚候选词获取失败，请先使用手工导入。"
HUITUN_LOGIN_EXPIRED_MESSAGE = "灰豚登录态已过期，请到账号矩阵重新登录。"
HUITUN_STRUCTURE_CHANGED_MESSAGE = "灰豚候选词返回结构已变化，请先使用手工导入并等待适配。"
HUITUN_EMPTY_RESULT_MESSAGE = "灰豚没有返回候选词，请换一个种子词或稍后重试。"
HUITUN_HOTWORD_MAX_PAGE_SIZE = 20


def _safe_huitun_message(payload: dict[str, Any]) -> str:
    for key in ("message", "msg", "errorMessage", "error_message", "desc"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    ext_data = payload.get("extData")
    if isinstance(ext_data, dict):
        for key in ("message", "msg", "errorMessage", "error_message", "desc"):
            value = ext_data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _huitun_failure_message(payload: dict[str, Any]) -> str:
    status_code = payload.get("status") or payload.get("code")
    message = _safe_huitun_message(payload)
    if message:
        return f"灰豚候选词获取失败：{message}"
    if status_code is not None:
        return f"灰豚候选词获取失败：灰豚接口返回状态 {status_code}，请重新登录灰豚或稍后重试。"
    return HUITUN_LIVE_FAILED_MESSAGE


def _now_ms() -> int:
    import time

    return int(time.time() * 1000)


def _session_from_cookie_text(cookie_text: str) -> requests.Session:
    session = requests.Session()
    for key, value in decode_cookie_text(cookie_text).items():
        session.cookies.set(key, str(value), domain=".huitun.com", path="/")
    return session


def _first_list(value: Any) -> list[Any] | None:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("list", "items", "records", "rows", "data", "result"):
            nested = value.get(key)
            candidate = _first_list(nested)
            if candidate is not None:
                return candidate
        for nested in value.values():
            candidate = _first_list(nested)
            if candidate is not None:
                return candidate
    return None


def _row_from_item(source_keyword: str, index: int, item: dict[str, Any]) -> dict[str, Any] | None:
    keyword = (
        item.get("keyword")
        or item.get("word")
        or item.get("hotword")
        or item.get("hotWord")
        or item.get("name")
        or item.get("title")
        or ""
    )
    keyword = str(keyword).strip().lstrip("#")
    if not keyword:
        return None
    hot_value_text = item.get("hot_value_text") or item.get("hotValueText") or item.get("searchIndex") or item.get("hotValue") or item.get("score")
    note_count = item.get("note_count") or item.get("noteCount") or item.get("notes") or item.get("noteNum")
    interaction_text = item.get("interaction_text") or item.get("interactionText") or item.get("interaction") or item.get("engagement")
    categories = item.get("categories") or item.get("category") or item.get("categoryNames") or []
    if isinstance(categories, str):
        categories = [{"label": categories, "rate": None}]
    if not isinstance(categories, list):
        categories = []
    return {
        "source_keyword": source_keyword,
        "keyword": keyword,
        "hot_value_text": str(hot_value_text).strip() if hot_value_text is not None else None,
        "hot_value_number": item.get("hot_value_number") or item.get("hotValueNumber"),
        "note_count": note_count if isinstance(note_count, int) else None,
        "interaction_text": str(interaction_text).strip() if interaction_text is not None else None,
        "interaction_number": item.get("interaction_number") or item.get("interactionNumber"),
        "categories": categories,
        "rank_index": int(item.get("rank_index") or item.get("rankIndex") or index + 1),
    }


def _rows_from_response(source_keyword: str, payload: dict[str, Any], limit: int) -> list[dict[str, Any]]:
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
        raise RuntimeError(HUITUN_STRUCTURE_CHANGED_MESSAGE)

    rows: list[dict[str, Any]] = []
    for index, item in enumerate(candidate_list):
        if not isinstance(item, dict):
            continue
        row = _row_from_item(source_keyword, index, item)
        if row:
            rows.append(row)
    rows = dedupe_keyword_candidates(prioritize_exact_hotword_rows(source_keyword, rows))[:limit]
    if not rows:
        raise RuntimeError(HUITUN_EMPTY_RESULT_MESSAGE)
    return rows


def fetch_huitun_hotwords(cookie_text: str, seed_keyword: str, limit: int) -> list[dict[str, Any]]:
    seed = seed_keyword.strip()
    if not seed:
        return []
    try:
        validate_huitun_login_state(cookie_text)
    except Exception as exc:
        raise RuntimeError(HUITUN_LOGIN_EXPIRED_MESSAGE) from exc

    session = _session_from_cookie_text(cookie_text)
    try:
        response = session.post(
            HUITUN_HOTWORD_SEARCH_URL,
            params={"_t": _now_ms()},
            json={"keyword": seed, "page": 1, "pageSize": max(1, min(limit, HUITUN_HOTWORD_MAX_PAGE_SIZE)), "type": 0},
            timeout=20,
        )
    except requests.Timeout as exc:
        raise RuntimeError("灰豚候选词获取超时，请稍后重试；如果连续失败，请重新登录灰豚。") from exc
    except requests.RequestException as exc:
        raise RuntimeError("灰豚候选词网络请求失败，请检查网络或稍后重试。") from exc

    if response.status_code in {401, 403}:
        raise RuntimeError(HUITUN_LOGIN_EXPIRED_MESSAGE)
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(f"灰豚候选词获取失败：HTTP {response.status_code}，请稍后重试。") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("灰豚候选词接口返回非 JSON 内容，请稍后重试或重新登录灰豚。") from exc

    if not isinstance(payload, dict):
        raise RuntimeError(HUITUN_STRUCTURE_CHANGED_MESSAGE)
    status_code = payload.get("status") or payload.get("code")
    if status_code in {1001, 401, 403}:
        raise RuntimeError(HUITUN_LOGIN_EXPIRED_MESSAGE)
    if status_code not in {0, 200, None}:
        raise RuntimeError(_huitun_failure_message(payload))
    return _rows_from_response(seed, payload, limit)

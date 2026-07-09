from __future__ import annotations

import base64
import hashlib
import io
import json
import time
from typing import Any

import qrcode
import requests

from backend.app.services.account_service import cookie_header_from_text, decode_cookie_text

HUITUN_QR_TICKET_URL = "https://login.huitun.com/weChat/getTicket"
HUITUN_QR_CHECK_URL = "https://xhsapi.huitun.com/user/checkHuiTunLogin"
HUITUN_CURRENT_USER_URL = "https://xhsapi.huitun.com/user/currentUser"
HUITUN_PHONE_LOGIN_URL = "https://xhsapi.huitun.com/user/phoneLogin"
HUITUN_DEVICE_PHONE_LOGIN_URL = "https://xhsapi.huitun.com/user/v2/phoneLoginChange"
HUITUN_QR_TAG = "XiaoHongShu"
HUITUN_WEB_VERSION = "16101520.52.102"
HUITUN_INVALID_LOGIN_MESSAGE = "数据账号登录态无效或已过期。"
HUITUN_QR_FAILED_MESSAGE = "数据账号二维码生成失败，请稍后重试。"
HUITUN_PASSWORD_LOGIN_FAILED_MESSAGE = "数据账号登录失败，请检查账号密码或重新完成验证。"
HUITUN_PASSWORD_SMS_REQUIRED_MESSAGE = "当前设备需要短信验证，请输入短信验证码后继续。"
HUITUN_PASSWORD_SMS_KEYWORDS = (
    "短信",
    "验证码",
    "设备",
    "安全验证",
    "二次验证",
    "手机验证",
    "企业版",
)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _safe_message(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text if text else ""


def _json_dumps(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _qr_data_url(qr_url: str) -> str:
    image = qrcode.make(qr_url)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _session_from_cookie_text(cookie_text: str) -> requests.Session:
    session = requests.Session()
    cookies = decode_cookie_text(cookie_text)
    for key, value in cookies.items():
        session.cookies.set(key, str(value), domain=".huitun.com", path="/")
    return session


def _cookies_text_from_session(session: requests.Session) -> str:
    cookies = {cookie.name: cookie.value for cookie in session.cookies}
    return _json_dumps(cookies)


def _normalize_user_info(payload: dict[str, Any], cookies_text: str) -> dict[str, Any]:
    data = payload.get("extData") or payload.get("data") or payload.get("user") or payload
    if not isinstance(data, dict):
        data = {}

    user_id = (
        data.get("userId")
        or data.get("id")
        or data.get("uid")
        or data.get("accountId")
        or data.get("phone")
        or data.get("mobile")
        or ""
    )
    nickname = (
        data.get("nickName")
        or data.get("nickname")
        or data.get("name")
        or data.get("userName")
        or data.get("companyName")
        or "数据账号"
    )
    avatar_url = data.get("avatar") or data.get("avatarUrl") or data.get("headImgUrl") or ""
    external_user_id = str(user_id or "").strip()
    if not external_user_id:
        external_user_id = "huitun-" + hashlib.sha256(cookie_header_from_text(cookies_text).encode("utf-8")).hexdigest()[:16]

    return {
        "external_user_id": external_user_id,
        "nickname": str(nickname or "数据账号"),
        "avatar_url": str(avatar_url or ""),
        "profile": {
            "source": "huitun",
            "raw": data,
        },
    }


def create_huitun_qrcode() -> dict[str, Any]:
    session = requests.Session()
    try:
        response = session.get(
            HUITUN_QR_TICKET_URL,
            params={"_t": _now_ms(), "tag": HUITUN_QR_TAG},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise RuntimeError(HUITUN_QR_FAILED_MESSAGE) from exc

    ext_data = payload.get("extData") if isinstance(payload, dict) else None
    if not isinstance(ext_data, dict) or not ext_data.get("ticket") or not ext_data.get("url"):
        raise RuntimeError(HUITUN_QR_FAILED_MESSAGE)

    qr_url = str(ext_data["url"])
    ticket = str(ext_data["ticket"])
    state = {
        "ticket": ticket,
        "cookies": {cookie.name: cookie.value for cookie in session.cookies},
        "expire_seconds": ext_data.get("expireSeconds") or 300,
    }
    return {
        "ticket": ticket,
        "qr_url": qr_url,
        "qr_image_data_url": _qr_data_url(qr_url),
        "state": state,
    }


def check_huitun_qrcode_status(state: dict[str, Any]) -> dict[str, Any]:
    ticket = str(state.get("ticket") or "")
    if not ticket:
        return {"status": "expired", "cookies_text": "", "user_info": None}

    session = requests.Session()
    for key, value in (state.get("cookies") or {}).items():
        session.cookies.set(str(key), str(value), domain=".huitun.com", path="/")

    try:
        response = session.get(
            HUITUN_QR_CHECK_URL,
            params={"_t": _now_ms(), "ticket": ticket, "referee": ""},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return {"status": "pending", "cookies_text": _cookies_text_from_session(session), "user_info": None}

    status_code = payload.get("status")
    message = _safe_message(payload.get("message"))
    ext_data = payload.get("extData")

    if status_code == 1002 or "等待" in message:
        return {"status": "pending", "cookies_text": _cookies_text_from_session(session), "user_info": None}
    if "扫码" in message and ("确认" in message or "已扫码" in message):
        return {"status": "scanned", "cookies_text": _cookies_text_from_session(session), "user_info": None}
    if status_code in {1003, 1004} or "过期" in message or "失效" in message:
        return {"status": "expired", "cookies_text": _cookies_text_from_session(session), "user_info": None}

    cookies_text = _cookies_text_from_session(session)
    if status_code in {0, 200} or ext_data:
        try:
            user_info = validate_huitun_login_state(cookies_text)
        except Exception:
            return {"status": "pending", "cookies_text": cookies_text, "user_info": None}
        return {"status": "confirmed", "cookies_text": cookies_text, "user_info": user_info}

    return {"status": "pending", "cookies_text": cookies_text, "user_info": None}


def _huitun_form_headers() -> dict[str, str]:
    return {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://xhs.huitun.com",
        "Referer": "https://xhs.huitun.com/",
        "Source": "web",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        ),
    }


def _is_sms_required_payload(payload: dict[str, Any]) -> bool:
    message = _safe_message(payload.get("message") or payload.get("msg"))
    status_code = str(payload.get("status") or payload.get("code") or "").strip()
    return status_code in {"1006", "1010", "2006", "3006"} or any(word in message for word in HUITUN_PASSWORD_SMS_KEYWORDS)


def _password_login_diagnostics(payload: dict[str, Any], http_status: int | None = None) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {}
    if http_status is not None:
        diagnostics["http_status"] = http_status
    for key in ("status", "code", "message", "msg"):
        value = payload.get(key)
        if value is not None:
            diagnostics[key] = str(value)[:200]
    return diagnostics


def _post_huitun_password_login(
    session: requests.Session,
    *,
    mobile: str,
    password: str,
    ticket: str,
    rand_str: str,
    captcha: str | None = None,
) -> dict[str, Any]:
    login_url = HUITUN_DEVICE_PHONE_LOGIN_URL if captcha else HUITUN_PHONE_LOGIN_URL
    form_data = {
        "mobile": mobile,
        "password": password,
        "ticket": ticket,
        "randStr": rand_str,
        "vs": HUITUN_WEB_VERSION,
        "Source": "web",
    }
    if captcha:
        form_data["captcha"] = captcha

    response = session.post(
        login_url,
        params={"_t": _now_ms()},
        data=form_data,
        headers=_huitun_form_headers(),
        timeout=20,
    )
    try:
        payload = response.json()
    except Exception:
        response.raise_for_status()
        raise RuntimeError(HUITUN_PASSWORD_LOGIN_FAILED_MESSAGE)
    if not isinstance(payload, dict):
        raise RuntimeError(HUITUN_PASSWORD_LOGIN_FAILED_MESSAGE)
    if response.status_code >= 400 and not _is_sms_required_payload(payload):
        response.raise_for_status()
    return payload


def login_huitun_with_password(
    mobile: str,
    password: str,
    ticket: str,
    rand_str: str,
    captcha: str | None = None,
    initial_cookies_text: str | None = None,
) -> dict[str, Any]:
    session = requests.Session()
    if initial_cookies_text:
        for key, value in decode_cookie_text(initial_cookies_text).items():
            session.cookies.set(str(key), str(value), domain=".huitun.com", path="/")
    try:
        payload = _post_huitun_password_login(
            session,
            mobile=mobile,
            password=password,
            ticket=ticket,
            rand_str=rand_str,
            captcha=captcha,
        )
    except Exception as exc:
        raise RuntimeError(HUITUN_PASSWORD_LOGIN_FAILED_MESSAGE) from exc

    if _is_sms_required_payload(payload):
        return {
            "status": "verification_required",
            "cookies_text": _cookies_text_from_session(session),
            "user_info": None,
            "message": HUITUN_PASSWORD_SMS_REQUIRED_MESSAGE,
            "diagnostics": _password_login_diagnostics(payload),
        }

    status_code = str(payload.get("status") or payload.get("code") or "").strip()
    if status_code in {"1000", "1001", "401", "403"}:
        raise RuntimeError(HUITUN_PASSWORD_LOGIN_FAILED_MESSAGE)

    cookies_text = _cookies_text_from_session(session)
    try:
        user_info = validate_huitun_login_state(cookies_text)
    except Exception as exc:
        raise RuntimeError(HUITUN_PASSWORD_LOGIN_FAILED_MESSAGE) from exc

    return {
        "status": "confirmed",
        "cookies_text": cookies_text,
        "user_info": user_info,
        "message": "",
    }


def validate_huitun_login_state(cookie_text: str) -> dict[str, Any]:
    session = _session_from_cookie_text(cookie_text)
    try:
        response = session.get(HUITUN_CURRENT_USER_URL, params={"_t": _now_ms()}, timeout=20)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise RuntimeError(HUITUN_INVALID_LOGIN_MESSAGE) from exc

    status_code = payload.get("status")
    if status_code in {1000, 1001, 401, 403}:
        raise RuntimeError(HUITUN_INVALID_LOGIN_MESSAGE)
    if status_code not in {0, 200} and not payload.get("extData"):
        raise RuntimeError(HUITUN_INVALID_LOGIN_MESSAGE)
    return _normalize_user_info(payload, _cookies_text_from_session(session) or cookie_text)

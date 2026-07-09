from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.deps import get_current_user, require_admin_user
from backend.app.core.security import decrypt_text, encrypt_text
from backend.app.models import LoginSession, User
from backend.app.services import huitun_account_service
from backend.app.services.account_service import serialize_account, upsert_platform_account_from_login

router = APIRouter(prefix="/huitun/login-sessions", tags=["huitun-login-sessions"])

HUITUN_LOGIN_STATUS_CHECK_FAILED_MESSAGE = "数据账号登录状态检查失败，请稍后重试。"
HUITUN_ACCOUNT_INFO_FAILED_MESSAGE = "数据账号信息获取失败，请刷新二维码重试。"
HUITUN_PASSWORD_LOGIN_FAILED_MESSAGE = "数据账号登录失败，请检查账号密码或重新完成验证。"


def _dump_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _load_json(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    parsed = json.loads(value)
    return parsed if isinstance(parsed, dict) else {}


def get_huitun_account_client():
    return huitun_account_service


class HuitunPasswordLoginRequest(BaseModel):
    mobile: str = Field(min_length=5, max_length=32)
    password: str = Field(min_length=1, max_length=128)
    ticket: str = Field(min_length=1, max_length=512)
    randStr: str = Field(min_length=1, max_length=512)
    captcha: str | None = Field(default=None, max_length=16)
    session_id: int | None = Field(default=None, ge=1)


def _mask_mobile(mobile: str) -> str:
    digits = "".join(char for char in mobile if char.isdigit())
    if len(digits) >= 7:
        return f"{digits[:3]}****{digits[-4:]}"
    return "已填写"


@router.post("/qrcode")
def huitun_qrcode(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    client=Depends(get_huitun_account_client),
):
    require_admin_user(current_user)
    try:
        qr_payload = client.create_huitun_qrcode()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=huitun_account_service.HUITUN_QR_FAILED_MESSAGE,
        ) from exc

    session = LoginSession(
        user_id=current_user.id,
        platform="huitun",
        sub_type="main",
        status="pending",
        login_method="qr",
        qr_id=qr_payload["ticket"],
        qr_url=qr_payload["qr_url"],
        encrypted_temp_cookies=encrypt_text(_dump_json(qr_payload.get("state") or {})),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return {
        "session_id": session.id,
        "status": session.status,
        "qr_url": session.qr_url,
        "qr_image_data_url": qr_payload["qr_image_data_url"],
    }


@router.get("/{session_id}")
def huitun_login_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    client=Depends(get_huitun_account_client),
):
    require_admin_user(current_user)
    session = db.get(LoginSession, session_id)
    if session is None or session.user_id != current_user.id or session.platform != "huitun":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Login session not found")
    if session.sub_type != "main" or session.login_method != "qr":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported login session")
    if session.status in {"confirmed", "expired"}:
        return {"session_id": session.id, "status": session.status, "qr_url": session.qr_url}

    try:
        state = _load_json(decrypt_text(session.encrypted_temp_cookies))
        result = client.check_huitun_qrcode_status(state)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=HUITUN_LOGIN_STATUS_CHECK_FAILED_MESSAGE) from exc

    session.status = result.get("status") or "pending"
    if result.get("cookies_text"):
        try:
            state["cookies"] = _load_json(result["cookies_text"])
        except Exception:
            state["cookies"] = {}
    session.encrypted_temp_cookies = encrypt_text(_dump_json(state))

    account_payload = None
    if session.status == "confirmed":
        cookies_text = result.get("cookies_text") or _dump_json(state.get("cookies") or {})
        user_info = result.get("user_info")
        if not isinstance(user_info, dict):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=HUITUN_ACCOUNT_INFO_FAILED_MESSAGE)
        account, action = upsert_platform_account_from_login(
            db=db,
            user_id=current_user.id,
            platform="huitun",
            sub_type="main",
            user_info=user_info,
            cookies_text=cookies_text,
        )
        account_payload = serialize_account(account, action)

    db.commit()
    return {
        "session_id": session.id,
        "status": session.status,
        "qr_url": session.qr_url,
        "account": account_payload,
    }


@router.post("/password/confirm")
def huitun_password_login_confirm(
    payload: HuitunPasswordLoginRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    client=Depends(get_huitun_account_client),
):
    require_admin_user(current_user)
    session = None
    initial_cookies_text = None
    if payload.session_id is not None:
        session = db.get(LoginSession, payload.session_id)
        if (
            session is None
            or session.user_id != current_user.id
            or session.platform != "huitun"
            or session.sub_type != "main"
            or session.login_method != "password"
            or session.status != "verification_required"
        ):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Login session not found")
        if session.encrypted_temp_cookies:
            initial_cookies_text = decrypt_text(session.encrypted_temp_cookies)
    if session is None:
        session = LoginSession(
            user_id=current_user.id,
            platform="huitun",
            sub_type="main",
            status="pending",
            login_method="password",
            phone_mask=_mask_mobile(payload.mobile),
            encrypted_temp_cookies=None,
        )
        db.add(session)
        db.flush()

    try:
        result = client.login_huitun_with_password(
            payload.mobile.strip(),
            payload.password,
            payload.ticket.strip(),
            payload.randStr.strip(),
            payload.captcha.strip() if payload.captcha else None,
            initial_cookies_text=initial_cookies_text,
        )
    except Exception as exc:
        session.status = "failed"
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=HUITUN_PASSWORD_LOGIN_FAILED_MESSAGE) from exc

    result_status = result.get("status") or "pending"
    if result_status == "verification_required":
        session.status = "verification_required"
        if result.get("cookies_text"):
            session.encrypted_temp_cookies = encrypt_text(result["cookies_text"])
        db.commit()
        return {
            "session_id": session.id,
            "status": session.status,
            "qr_url": "",
            "message": result.get("message") or huitun_account_service.HUITUN_PASSWORD_SMS_REQUIRED_MESSAGE,
            "account": None,
        }

    if result_status != "confirmed":
        session.status = str(result_status)
        session.encrypted_temp_cookies = None
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=HUITUN_PASSWORD_LOGIN_FAILED_MESSAGE)

    cookies_text = result.get("cookies_text") or ""
    user_info = result.get("user_info")
    if not cookies_text or not isinstance(user_info, dict):
        session.status = "failed"
        db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=HUITUN_ACCOUNT_INFO_FAILED_MESSAGE)

    account, action = upsert_platform_account_from_login(
        db=db,
        user_id=current_user.id,
        platform="huitun",
        sub_type="main",
        user_info=user_info,
        cookies_text=cookies_text,
    )
    session.status = "confirmed"
    session.encrypted_temp_cookies = None
    db.commit()
    db.refresh(session)
    db.refresh(account)
    return {
        "session_id": session.id,
        "status": session.status,
        "qr_url": "",
        "account": serialize_account(account, action),
    }

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Protocol

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.security import encrypt_text
from backend.app.core.time import SHANGHAI_TZ, shanghai_now
from backend.app.models import WechatOfficialBackendSession, WechatOfficialCrawlAccount


class WechatOfficialQrLoginClient(Protocol):
    def create_qrcode(self) -> dict[str, Any]: ...


class PlaceholderWechatOfficialQrLoginClient:
    def create_qrcode(self) -> dict[str, Any]:
        return {"qrcode_url": "wechat-official://login/pending/placeholder"}


class WechatOfficialBackendSessionService:
    def __init__(self, db: Session, client: WechatOfficialQrLoginClient | None = None) -> None:
        self.db = db
        self.client = client or PlaceholderWechatOfficialQrLoginClient()

    def start_qr_login(self, user_id: int) -> dict[str, Any]:
        upstream = self.client.create_qrcode()
        qrcode_url = upstream.get("qrcode_url") or upstream.get("qr_url") or ""
        account = WechatOfficialCrawlAccount(user_id=user_id, name="", status="login_pending", raw_json={"source": "backend_qr_login"})
        self.db.add(account)
        self.db.flush()
        login_session = WechatOfficialBackendSession(
            account_id=account.id,
            status="pending",
            raw_json={"qrcode_url": qrcode_url, "upstream": _safe_qr_upstream(upstream)},
        )
        self.db.add(login_session)
        self.db.flush()
        qrcode_url = qrcode_url.replace("/placeholder", f"/{login_session.id}")
        login_session.raw_json = {"qrcode_url": qrcode_url, "upstream": _safe_qr_upstream(upstream)}
        self.db.commit()
        self.db.refresh(login_session)
        return {"login_session_id": login_session.id, "qrcode_url": qrcode_url, "status": login_session.status}

    def complete_qr_login(self, user_id: int, login_session_id: int, upstream_payload: dict[str, Any]) -> dict[str, Any]:
        login_session = self._get_owned_session(user_id, login_session_id)
        cookie = _required_text(upstream_payload, "cookie")
        token = _required_text(upstream_payload, "token")
        auth_key = _required_text(upstream_payload, "auth_key")

        account = self.db.get(WechatOfficialCrawlAccount, login_session.account_id)
        if account is None or account.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Login session not found")

        account.biz = str(upstream_payload.get("biz") or account.biz or "")
        account.name = str(upstream_payload.get("nickname") or account.name or "")
        account.status = "active"
        account.updated_at = shanghai_now()

        login_session.encrypted_cookie = encrypt_text(cookie)
        login_session.encrypted_token = encrypt_text(token)
        login_session.user_agent = str(upstream_payload.get("user_agent") or "")
        expires_at = upstream_payload.get("expires_at")
        if isinstance(expires_at, datetime):
            login_session.expires_at = _normalize_datetime_for_storage(expires_at)
        login_session.status = "expired" if _is_expired_at(login_session.expires_at) else "valid"
        login_session.raw_json = {
            "auth_key_hash": hashlib.sha256(auth_key.encode("utf-8")).hexdigest(),
            "biz": account.biz,
            "nickname": account.name,
            "completed_at": shanghai_now().isoformat(),
        }
        login_session.updated_at = shanghai_now()
        self.db.commit()
        self.db.refresh(login_session)
        return serialize_backend_session(login_session, account=account)

    def list_sessions(self, user_id: int) -> list[dict[str, Any]]:
        rows = self.db.execute(
            select(WechatOfficialBackendSession, WechatOfficialCrawlAccount)
            .join(WechatOfficialCrawlAccount, WechatOfficialBackendSession.account_id == WechatOfficialCrawlAccount.id)
            .where(WechatOfficialCrawlAccount.user_id == user_id)
            .order_by(WechatOfficialBackendSession.updated_at.desc(), WechatOfficialBackendSession.id.desc())
        ).all()
        changed = False
        for login_session, _account in rows:
            if _is_expired_at(login_session.expires_at) and login_session.status == "valid":
                login_session.status = "expired"
                login_session.updated_at = shanghai_now()
                changed = True
        if changed:
            self.db.commit()
        return [serialize_backend_session(login_session, account=account) for login_session, account in rows]

    def _get_owned_session(self, user_id: int, session_id: int) -> WechatOfficialBackendSession:
        login_session = self.db.get(WechatOfficialBackendSession, session_id)
        if login_session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Login session not found")
        account = self.db.get(WechatOfficialCrawlAccount, login_session.account_id)
        if account is None or account.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Login session not found")
        return login_session


def get_valid_session(db: Session, user_id: int, session_id: int) -> WechatOfficialBackendSession:
    service = WechatOfficialBackendSessionService(db)
    login_session = service._get_owned_session(user_id, session_id)
    if _is_expired_at(login_session.expires_at):
        login_session.status = "expired"
        login_session.updated_at = shanghai_now()
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Login session is expired")
    if login_session.status != "valid":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Login session is not valid")
    return login_session


def _normalize_datetime_for_storage(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(SHANGHAI_TZ).replace(tzinfo=None)


def _is_expired_at(value: datetime | None) -> bool:
    return bool(value and _normalize_datetime_for_storage(value) <= shanghai_now())


def serialize_backend_session(login_session: WechatOfficialBackendSession, *, account: WechatOfficialCrawlAccount | None = None) -> dict[str, Any]:
    status_text = "expired" if login_session.status == "valid" and _is_expired_at(login_session.expires_at) else login_session.status
    return {
        "id": login_session.id,
        "account_id": login_session.account_id,
        "biz": account.biz if account else "",
        "nickname": account.name if account else "",
        "status": status_text,
        "expires_at": login_session.expires_at.isoformat() if login_session.expires_at else None,
        "created_at": login_session.created_at.isoformat() if login_session.created_at else None,
        "updated_at": login_session.updated_at.isoformat() if login_session.updated_at else None,
    }


def _required_text(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Missing required field: {field}")
    return value.strip()


def _safe_qr_upstream(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key not in {"cookie", "token", "auth_key"}}

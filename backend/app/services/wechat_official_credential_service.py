from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.security import encrypt_text
from backend.app.core.time import SHANGHAI_TZ, shanghai_now
from backend.app.models import WechatOfficialArticleCredential, WechatOfficialCrawlAccount

EXPECTED_CREDENTIAL_FIELDS = [
    "biz",
    "uin",
    "key",
    "pass_ticket",
    "wap_sid2",
    "appmsg_token",
    "cookie",
    "timestamp",
]
DEFAULT_CAPABILITIES = ["article.read", "article.metrics", "article.comments"]
SENSITIVE_ARTICLE_URL_QUERY_KEYS = {"key", "pass_ticket", "appmsg_token", "token", "wap_sid2", "cookie"}


class WechatOfficialCredentialService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_credential_guide(self) -> dict[str, Any]:
        return {
            "title": "微信公众号文章 credential.py 导入引导",
            "expected_fields": EXPECTED_CREDENTIAL_FIELDS,
            "steps": [
                "在用户明确授权的浏览器环境中打开目标公众号文章。",
                "按项目提供的 credential.py 提示采集字段。",
                "将 biz、uin、key、pass_ticket、wap_sid2、appmsg_token、cookie、timestamp 导入本系统。",
            ],
            "risk_warnings": [
                "仅允许在用户授权环境中采集和导入 credential。",
                "credential 有短有效期，默认按采集时间后 25 分钟过期。",
                "不做验证码绕过，不实现代理池，不绕过微信安全机制。",
            ],
        }

    def validate_credential_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        missing_fields = [field for field in EXPECTED_CREDENTIAL_FIELDS if not _has_text(payload.get(field))]
        return {"valid": not missing_fields, "missing_fields": missing_fields, "expected_fields": EXPECTED_CREDENTIAL_FIELDS}

    def import_credential(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        validation = self.validate_credential_payload(payload)
        if not validation["valid"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=validation)

        captured_at = _parse_captured_at(payload.get("captured_at"))
        expires_at = captured_at + timedelta(minutes=25)
        is_expired = expires_at <= shanghai_now()
        biz = str(payload["biz"]).strip()
        nickname = str(payload.get("nickname") or "").strip()

        account = WechatOfficialCrawlAccount(
            user_id=user_id,
            biz=biz,
            name=nickname,
            status="active",
            raw_json={"uin": str(payload["uin"]).strip()},
        )
        self.db.add(account)
        self.db.flush()

        credential = WechatOfficialArticleCredential(
            account_id=account.id,
            article_url=_sanitize_article_url(payload.get("article_url")),
            encrypted_cookie=encrypt_text(str(payload["cookie"]).strip()),
            encrypted_token=encrypt_text(str(payload["appmsg_token"]).strip()),
            encrypted_key=encrypt_text(str(payload["key"]).strip()),
            valid=not is_expired,
            expires_at=expires_at,
            raw_json={
                "uin": str(payload["uin"]).strip(),
                "timestamp": str(payload["timestamp"]).strip(),
                "captured_at": captured_at.isoformat(),
                "pass_ticket_encrypted": encrypt_text(str(payload["pass_ticket"]).strip()),
                "wap_sid2_encrypted": encrypt_text(str(payload["wap_sid2"]).strip()),
                "capabilities": DEFAULT_CAPABILITIES,
            },
        )
        self.db.add(credential)
        self.db.commit()
        self.db.refresh(credential)
        return serialize_credential(credential, account=account)

    def list_credentials(self, user_id: int) -> list[dict[str, Any]]:
        rows = self.db.execute(
            select(WechatOfficialArticleCredential, WechatOfficialCrawlAccount)
            .join(WechatOfficialCrawlAccount, WechatOfficialArticleCredential.account_id == WechatOfficialCrawlAccount.id)
            .where(WechatOfficialCrawlAccount.user_id == user_id)
            .order_by(WechatOfficialArticleCredential.updated_at.desc(), WechatOfficialArticleCredential.id.desc())
        ).all()
        changed = False
        for credential, _account in rows:
            if _is_expired(credential):
                credential.valid = False
                changed = True
        if changed:
            self.db.commit()
        return [serialize_credential(credential, account=account) for credential, account in rows]


def serialize_credential(
    credential: WechatOfficialArticleCredential,
    *,
    account: WechatOfficialCrawlAccount | None = None,
) -> dict[str, Any]:
    capabilities = []
    if isinstance(credential.raw_json, dict):
        raw_capabilities = credential.raw_json.get("capabilities")
        if isinstance(raw_capabilities, list):
            capabilities = raw_capabilities
    status_text = "expired" if _is_expired(credential) else "valid" if credential.valid else "invalid"
    return {
        "id": credential.id,
        "account_id": credential.account_id,
        "biz": account.biz if account else "",
        "nickname": account.name if account else "",
        "status": status_text,
        "valid": False if status_text == "expired" else credential.valid,
        "expires_at": credential.expires_at.isoformat() if credential.expires_at else None,
        "capabilities": capabilities,
        "article_url": credential.article_url,
        "created_at": credential.created_at.isoformat() if credential.created_at else None,
        "updated_at": credential.updated_at.isoformat() if credential.updated_at else None,
    }


def get_credential_guide() -> dict[str, Any]:
    return WechatOfficialCredentialService(None).get_credential_guide()  # type: ignore[arg-type]


def validate_credential_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return WechatOfficialCredentialService(None).validate_credential_payload(payload)  # type: ignore[arg-type]


def _has_text(value: Any) -> bool:
    return isinstance(value, (str, int)) and str(value).strip() != ""


def _parse_captured_at(value: Any) -> datetime:
    if isinstance(value, datetime):
        return _normalize_datetime_for_storage(value)
    if isinstance(value, str) and value.strip():
        try:
            return _normalize_datetime_for_storage(datetime.fromisoformat(value.strip()))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid captured_at ISO datetime") from exc
    return shanghai_now()


def _normalize_datetime_for_storage(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(SHANGHAI_TZ).replace(tzinfo=None)


def _sanitize_article_url(value: Any) -> str:
    raw_url = str(value or "").strip()
    if not raw_url:
        return ""
    parts = urlsplit(raw_url)
    safe_query = urlencode(
        [(key, query_value) for key, query_value in parse_qsl(parts.query, keep_blank_values=True) if key not in SENSITIVE_ARTICLE_URL_QUERY_KEYS]
    )
    return urlunsplit((parts.scheme, parts.netloc, parts.path, safe_query, parts.fragment))


def _is_expired(credential: WechatOfficialArticleCredential) -> bool:
    return bool(credential.expires_at and _normalize_datetime_for_storage(credential.expires_at) <= shanghai_now())

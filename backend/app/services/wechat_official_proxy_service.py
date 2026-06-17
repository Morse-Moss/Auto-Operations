from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from backend.app.core.time import shanghai_now
from backend.app.models import WechatOfficialProxyNode


class WechatOfficialProxyService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_proxies(self, user_id: int) -> list[dict[str, Any]]:
        self._seed_defaults_if_empty(user_id)
        nodes = self.db.scalars(
            select(WechatOfficialProxyNode)
            .where(WechatOfficialProxyNode.raw_json["user_id"].as_integer() == user_id)
            .order_by(WechatOfficialProxyNode.id.asc())
        ).all()
        return [serialize_proxy_node(node) for node in nodes]

    def test_proxy(self, user_id: int, proxy_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        node = self._get_owned_proxy(user_id, proxy_id)
        raw = _raw(node)
        request_type = str(payload.get("request_type") or "public")
        if request_type == "sensitive" and not bool(raw.get("supports_sensitive_requests")):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Proxy does not support sensitive requests")
        success = bool(payload.get("success", True))
        if success:
            node.status = "active"
            node.last_error = ""
            raw["success_count"] = int(raw.get("success_count") or 0) + 1
            raw["last_success_at"] = shanghai_now().isoformat()
        else:
            node.status = "cooldown"
            node.last_error = str(payload.get("error_message") or "proxy test failed")
            raw["failure_count"] = int(raw.get("failure_count") or 0) + 1
            raw["last_failure_at"] = shanghai_now().isoformat()
        node.raw_json = raw
        node.updated_at = shanghai_now()
        flag_modified(node, "raw_json")
        self.db.commit()
        self.db.refresh(node)
        return serialize_proxy_node(node)

    def _seed_defaults_if_empty(self, user_id: int) -> None:
        existing = self.db.scalar(
            select(WechatOfficialProxyNode.id).where(WechatOfficialProxyNode.raw_json["user_id"].as_integer() == user_id).limit(1)
        )
        if existing is not None:
            return
        defaults = [
            WechatOfficialProxyNode(
                name="Direct connection",
                endpoint="direct://local",
                enabled=True,
                status="active",
                raw_json={"user_id": user_id, "type": "direct", "supports_sensitive_requests": True, "success_count": 0, "failure_count": 0},
            ),
            WechatOfficialProxyNode(
                name="Public proxy reference",
                endpoint="https://example.com/proxy-reference",
                enabled=True,
                status="active",
                raw_json={"user_id": user_id, "type": "public_reference", "supports_sensitive_requests": False, "success_count": 0, "failure_count": 0},
            ),
        ]
        self.db.add_all(defaults)
        self.db.commit()

    def _get_owned_proxy(self, user_id: int, proxy_id: int) -> WechatOfficialProxyNode:
        node = self.db.get(WechatOfficialProxyNode, proxy_id)
        if node is None or _raw(node).get("user_id") != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proxy node not found")
        return node


def serialize_proxy_node(node: WechatOfficialProxyNode) -> dict[str, Any]:
    raw = _raw(node)
    return {
        "id": node.id,
        "name": node.name,
        "endpoint": node.endpoint,
        "enabled": node.enabled,
        "status": node.status,
        "last_error": node.last_error,
        "type": raw.get("type", "custom"),
        "supports_sensitive_requests": bool(raw.get("supports_sensitive_requests")),
        "success_count": int(raw.get("success_count") or 0),
        "failure_count": int(raw.get("failure_count") or 0),
        "created_at": node.created_at.isoformat() if node.created_at else None,
        "updated_at": node.updated_at.isoformat() if node.updated_at else None,
    }


def _raw(node: WechatOfficialProxyNode) -> dict[str, Any]:
    return dict(node.raw_json or {})

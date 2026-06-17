from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import AiDraft, WechatOfficialArticleSnapshot, WechatOfficialDraftSource
from backend.app.services.wechat_official_content_service import get_owned_content_article


class WechatOfficialDraftService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_draft_from_article(self, user_id: int, article_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        article = get_owned_content_article(self.db, user_id, article_id)
        snapshot = self.db.scalar(
            select(WechatOfficialArticleSnapshot)
            .where(WechatOfficialArticleSnapshot.article_id == article.id)
            .order_by(WechatOfficialArticleSnapshot.captured_at.desc(), WechatOfficialArticleSnapshot.id.desc())
        )
        source_text = snapshot.text if snapshot and snapshot.text else article.digest
        rewrite_style = str(payload.get("rewrite_style") or "保持原文结构").strip()
        target_audience = str(payload.get("target_audience") or "公众号读者").strip()
        call_to_action = str(payload.get("call_to_action") or "关注后续更新").strip()
        body = (
            f"改写风格：{rewrite_style}\n"
            f"目标读者：{target_audience}\n"
            f"行动引导：{call_to_action}\n\n"
            f"原文摘要：{article.digest}\n\n"
            f"改写参考：\n{source_text}"
        )
        draft = AiDraft(user_id=user_id, platform="wechat_official", title=article.title, body=body, tags=[])
        self.db.add(draft)
        self.db.flush()
        source = WechatOfficialDraftSource(draft_id=draft.id, article_id=article.id, source_type="rewrite", raw_json={"rewrite_params": payload})
        self.db.add(source)
        self.db.commit()
        self.db.refresh(draft)
        return serialize_draft(draft)

    def dry_run(self, user_id: int, draft_id: int, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        draft = self.db.get(AiDraft, draft_id)
        if draft is None or draft.user_id != user_id or draft.platform != "wechat_official":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")
        payload = payload or {}
        title = str(payload.get("title") if "title" in payload else draft.title)
        body = str(payload.get("body") if "body" in payload else draft.body)
        checks = {
            "title": "ok" if title.strip() else "missing",
            "body": "ok" if body.strip() else "missing",
            "publish": "blocked",
            "sendall": "blocked",
            "external_images": "warning" if _has_external_images(body) else "ok",
        }
        ok = checks["title"] == "ok" and checks["body"] == "ok"
        return {"draft_id": draft.id, "ok": ok, "publish_blocked": True, "sendall_blocked": True, "checks": checks}


def serialize_draft(draft: AiDraft) -> dict[str, Any]:
    return {
        "id": draft.id,
        "platform": draft.platform,
        "title": draft.title,
        "body": draft.body,
        "tags": draft.tags or [],
        "source_note_id": draft.source_note_id,
        "created_at": draft.created_at.isoformat() if draft.created_at else None,
    }


def _has_external_images(body: str) -> bool:
    return bool(re.search(r"!\[[^\]]*\]\(https?://", body) or re.search(r"<img[^>]+src=[\"']https?://", body, flags=re.I))

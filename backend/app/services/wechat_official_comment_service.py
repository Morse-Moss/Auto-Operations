from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from backend.app.adapters.wechat_official.research_adapter import WechatOfficialResearchAdapter
from backend.app.models import WechatOfficialArticleComment, WechatOfficialArticleCommentReply
from backend.app.services.wechat_official_crawl_service import WechatOfficialCrawlService


class WechatOfficialCommentService:
    def __init__(self, db: Session, adapter: WechatOfficialResearchAdapter | None = None) -> None:
        self.db = db
        self.adapter = adapter or WechatOfficialResearchAdapter()

    def store_comments(self, user_id: int, article_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        crawl_service = WechatOfficialCrawlService(self.db, self.adapter)
        article = crawl_service._get_owned_article(user_id, article_id)
        crawl_service._get_owned_valid_credential(user_id, int(payload["credential_id"]))
        limit = int(payload.get("limit") or 50)
        comments = self.adapter.normalize_comments(payload.get("comments_payload") or {}, limit=limit)
        for comment_payload in comments:
            comment = WechatOfficialArticleComment(
                article_id=article.id,
                comment_id=comment_payload["comment_id"],
                user_name=comment_payload["user_name"],
                user_id=comment_payload["user_id"],
                content=comment_payload["content"],
                like_count=comment_payload["like_count"],
                created_at_remote=comment_payload["created_at_remote"],
                raw_json=comment_payload["raw"],
            )
            self.db.add(comment)
            self.db.flush()
            comment_payload["db_id"] = comment.id
            for reply_payload in comment_payload["replies"]:
                reply = WechatOfficialArticleCommentReply(
                    comment_id=comment.id,
                    reply_id=reply_payload["reply_id"],
                    user_name=reply_payload["user_name"],
                    user_id=reply_payload["user_id"],
                    content=reply_payload["content"],
                    like_count=reply_payload["like_count"],
                    created_at_remote=reply_payload["created_at_remote"],
                    raw_json=reply_payload["raw"],
                )
                self.db.add(reply)
        self.db.commit()
        return {"items": comments, "total": len(comments)}

from __future__ import annotations

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.time import shanghai_now
from backend.app.models import WechatOfficialContentLibraryTombstone


class WechatOfficialContentTombstoneService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def is_tombstoned(self, user_id: int, article_url: str) -> bool:
        article_url = str(article_url or "").strip()
        if not article_url:
            return False
        return (
            self.db.scalar(
                select(WechatOfficialContentLibraryTombstone.id).where(
                    WechatOfficialContentLibraryTombstone.user_id == user_id,
                    WechatOfficialContentLibraryTombstone.article_url == article_url,
                )
            )
            is not None
        )

    def tombstone(self, user_id: int, article_url: str, article_title: str = "") -> None:
        article_url = str(article_url or "").strip()
        if not article_url:
            return
        title = str(article_title or "")
        now = shanghai_now()
        if self._update_existing(user_id, article_url, title, now):
            return
        try:
            with self.db.begin_nested():
                self.db.execute(
                    insert(WechatOfficialContentLibraryTombstone).values(
                        user_id=user_id,
                        article_url=article_url,
                        article_title=title,
                        deleted_at=now,
                    )
                )
        except IntegrityError:
            if not self._update_existing(user_id, article_url, title, shanghai_now()):
                raise

    def _update_existing(self, user_id: int, article_url: str, article_title: str, deleted_at) -> bool:
        values = {"deleted_at": deleted_at}
        if article_title:
            values["article_title"] = article_title
        result = self.db.execute(
            update(WechatOfficialContentLibraryTombstone)
            .where(
                WechatOfficialContentLibraryTombstone.user_id == user_id,
                WechatOfficialContentLibraryTombstone.article_url == article_url,
            )
            .values(**values)
        )
        return bool(result.rowcount)

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from backend.app.core.time import shanghai_now
from backend.app.models import WechatOfficialArticle, WechatOfficialArticleSnapshot, WechatOfficialCrawlAccount, WechatOfficialCrawlJob
from backend.app.services.wechat_official_content_tombstone_service import WechatOfficialContentTombstoneService
from backend.app.services.wechat_official_provider_types import sanitize_provider_payload


class WechatOfficialIngestionService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def ingest_articles(
        self,
        *,
        user_id: int,
        provider: str,
        source_label: str,
        keyword: str,
        requested_limit: int,
        fetched_count: int,
        articles: list[dict[str, Any]],
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        job = WechatOfficialCrawlJob(
            keyword=keyword,
            status="running",
            source=provider,
            requested_limit=requested_limit,
            fetched_count=fetched_count,
            params_json={"source": source_label, **sanitize_provider_payload(params or {})},
            started_at=shanghai_now(),
        )
        self.db.add(job)
        self.db.flush()

        tombstones = WechatOfficialContentTombstoneService(self.db)
        saved_articles: list[WechatOfficialArticle] = []
        skipped = 0
        for payload in articles:
            article_url = str(payload.get("article_url") or payload.get("content_url") or "").strip()
            title = str(payload.get("title") or "").strip()
            if not article_url or not title:
                skipped += 1
                continue
            if tombstones.is_tombstoned(user_id, article_url):
                skipped += 1
                continue

            account = self._upsert_account(user_id=user_id, provider=provider, payload=payload)
            article = self._upsert_article(account_id=account.id, job_id=job.id, provider=provider, payload=payload, article_url=article_url, title=title)
            if payload.get("content_text") or payload.get("content_html") or payload.get("images"):
                self._create_snapshot(article.id, provider=provider, payload=payload)
            saved_articles.append(article)

        job.status = "succeeded"
        job.saved_count = len(saved_articles)
        job.finished_at = shanghai_now()
        self.db.commit()
        self.db.refresh(job)

        return {
            "summary": {"fetched": fetched_count, "saved": len(saved_articles), "skipped": skipped},
            "job_id": job.id,
            "article_ids": [article.id for article in saved_articles],
        }

    def _upsert_account(self, *, user_id: int, provider: str, payload: dict[str, Any]) -> WechatOfficialCrawlAccount:
        account_name = str(payload.get("account_name") or payload.get("author_name") or f"{provider}公众号").strip()
        account_key = str(payload.get("account") or payload.get("biz") or account_name or provider).strip()
        fake_id = f"{provider}:{account_key}"
        account = self.db.scalar(select(WechatOfficialCrawlAccount).where(WechatOfficialCrawlAccount.user_id == user_id, WechatOfficialCrawlAccount.fake_id == fake_id))
        if account is None:
            account = WechatOfficialCrawlAccount(user_id=user_id, fake_id=fake_id, status="active")
            self.db.add(account)
        account.name = account_name
        account.alias = str(payload.get("account") or account.alias or "")
        account.biz = str(payload.get("biz") or account.biz or "")
        account.raw_json = {"source": provider, "raw": sanitize_provider_payload(payload.get("raw") or {})}
        account.updated_at = shanghai_now()
        self.db.flush()
        return account

    def _upsert_article(
        self,
        *,
        account_id: int,
        job_id: int,
        provider: str,
        payload: dict[str, Any],
        article_url: str,
        title: str,
    ) -> WechatOfficialArticle:
        article = self.db.scalar(select(WechatOfficialArticle).where(WechatOfficialArticle.article_url == article_url, WechatOfficialArticle.account_id == account_id))
        if article is None:
            article = WechatOfficialArticle(account_id=account_id, article_url=article_url)
            self.db.add(article)
        article.job_id = job_id
        article.title = title
        article.digest = str(payload.get("digest") or article.digest or "")
        article.author_name = str(payload.get("author_name") or article.author_name or "")
        article.source = provider
        article.publish_time_remote = payload.get("publish_time_remote") or article.publish_time_remote
        article.cover_url = str(payload.get("cover_url") or article.cover_url or "")
        article.content_url = str(payload.get("content_url") or article_url)
        article.raw_json = {
            "source": provider,
            "external_id": payload.get("external_id"),
            "raw": sanitize_provider_payload(payload.get("raw") or {}),
        }
        flag_modified(article, "raw_json")
        article.updated_at = shanghai_now()
        self.db.flush()
        return article

    def _create_snapshot(self, article_id: int, *, provider: str, payload: dict[str, Any]) -> WechatOfficialArticleSnapshot:
        snapshot = WechatOfficialArticleSnapshot(
            article_id=article_id,
            status="captured",
            html=str(payload.get("content_html") or ""),
            text=str(payload.get("content_text") or payload.get("digest") or ""),
            images_json=sanitize_provider_payload(payload.get("images") or []),
            raw_json={"source": provider, "external_id": payload.get("external_id")},
        )
        self.db.add(snapshot)
        self.db.flush()
        return snapshot

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.models import WechatOfficialArticle, WechatOfficialCrawlJob
from backend.app.services.wechat_official_article_page_provider import WechatOfficialArticlePageProvider
from backend.app.services.wechat_official_crawl_service import serialize_article, serialize_crawl_job
from backend.app.services.wechat_official_ingestion_service import WechatOfficialIngestionService
from backend.app.services.wechat_official_provider_types import WechatOfficialProviderError


class WechatOfficialArticleImportService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def import_url(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        url = str(payload.get("url") or "").strip()
        if not url:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="url is required")
        try:
            article_payload = WechatOfficialArticlePageProvider().fetch_article(url=url)
        except WechatOfficialProviderError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": "公众号公开文章页抓取失败；未保存空壳文章",
                    "provider": exc.to_dict(),
                    "next_action": "请确认 URL 是公开微信公众号文章，或稍后重试",
                },
            ) from exc

        result = WechatOfficialIngestionService(self.db).ingest_articles(
            user_id=user_id,
            provider="article_page",
            source_label="article_page_url",
            keyword=url,
            requested_limit=1,
            fetched_count=1,
            articles=[article_payload],
            params={"url": url, "save_snapshot": bool(payload.get("save_snapshot", True))},
        )
        articles = []
        for article_id in result["article_ids"]:
            article = self.db.get(WechatOfficialArticle, article_id)
            if article is not None:
                articles.append(serialize_article(article, latest_metric=None, analysis=dict((article.raw_json or {}).get("analysis") or {})))
        job = self.db.get(WechatOfficialCrawlJob, result["job_id"])
        return {
            "summary": {**result["summary"], "provider": "article_page", "api_calls": 1, "failed": 0, "deduped": 0, "viral_candidates": 0},
            "job": serialize_crawl_job(job) if job else None,
            "items": articles,
        }

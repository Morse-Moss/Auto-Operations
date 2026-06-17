from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from backend.app.models import WechatOfficialArticle, WechatOfficialArticleMetric
from backend.app.services.wechat_official_crawl_service import WechatOfficialCrawlService, serialize_article, serialize_metric

ANALYSIS_FIELDS = {
    "recommendation_status",
    "low_follower_evidence",
    "low_follower_note",
    "business_direction",
    "title_type",
    "article_type_label",
    "viral_factors",
    "core_insight",
    "case_info",
    "customer_conversion_method",
}


class WechatOfficialContentService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_content(self, user_id: int, filters: dict[str, Any]) -> dict[str, Any]:
        articles = self.db.scalars(select(WechatOfficialArticle).order_by(WechatOfficialArticle.updated_at.desc(), WechatOfficialArticle.id.desc())).all()
        items = []
        for article in articles:
            if not self._is_owned(user_id, article):
                continue
            latest_metric = self._latest_metric(article.id)
            metric_payload = serialize_metric(latest_metric) if latest_metric else None
            analysis = _analysis(article)
            read_count = int(metric_payload.get("read_count") or 0) if metric_payload else 0
            if filters.get("viral_only") and read_count < 100000:
                continue
            if filters.get("min_read_count") is not None and read_count < int(filters["min_read_count"]):
                continue
            if filters.get("low_follower_evidence") is not None and not _matches_low_follower_evidence(analysis.get("low_follower_evidence"), filters["low_follower_evidence"]):
                continue
            if filters.get("recommendation_status") and analysis.get("recommendation_status") != filters["recommendation_status"]:
                continue
            keyword = str(filters.get("keyword") or "").strip()
            if keyword and keyword not in article.title and keyword not in article.digest:
                continue
            items.append(serialize_article(article, latest_metric=metric_payload, analysis=analysis))
        return {"items": items, "total": len(items)}

    def update_recommendation(self, user_id: int, article_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        article = WechatOfficialCrawlService(self.db)._get_owned_article(user_id, article_id)
        raw = dict(article.raw_json or {})
        analysis = dict(raw.get("analysis") or {})
        for field in ANALYSIS_FIELDS:
            if field in payload:
                analysis[field] = payload[field]
        raw["analysis"] = analysis
        article.raw_json = raw
        flag_modified(article, "raw_json")
        self.db.commit()
        self.db.refresh(article)
        latest_metric = self._latest_metric(article.id)
        return serialize_article(article, latest_metric=serialize_metric(latest_metric) if latest_metric else None, analysis=analysis)

    def _latest_metric(self, article_id: int) -> WechatOfficialArticleMetric | None:
        return self.db.scalar(
            select(WechatOfficialArticleMetric)
            .where(WechatOfficialArticleMetric.article_id == article_id)
            .order_by(WechatOfficialArticleMetric.captured_at.desc(), WechatOfficialArticleMetric.id.desc())
        )

    def _is_owned(self, user_id: int, article: WechatOfficialArticle) -> bool:
        try:
            WechatOfficialCrawlService(self.db)._get_owned_article(user_id, article.id)
            return True
        except HTTPException:
            return False


def get_owned_content_article(db: Session, user_id: int, article_id: int) -> WechatOfficialArticle:
    article = WechatOfficialCrawlService(db)._get_owned_article(user_id, article_id)
    if article is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    return article


def _analysis(article: WechatOfficialArticle) -> dict[str, Any]:
    raw = article.raw_json or {}
    analysis = raw.get("analysis")
    return dict(analysis) if isinstance(analysis, dict) else {}


def _matches_low_follower_evidence(value: Any, expected: Any) -> bool:
    expected_text = str(expected).strip().lower()
    if expected_text in {"unknown", "manual", "inferred"}:
        return str(value or "unknown").strip().lower() == expected_text
    if expected_text in {"true", "1", "yes"}:
        return bool(value) is True
    if expected_text in {"false", "0", "no"}:
        return bool(value) is False
    return str(value or "").strip().lower() == expected_text

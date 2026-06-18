from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from backend.app.core.security import decrypt_text
from backend.app.core.time import shanghai_now
from backend.app.models import ModelConfig, WechatOfficialArticle, WechatOfficialArticleComment, WechatOfficialArticleCommentReply, WechatOfficialArticleMetric, WechatOfficialArticleSnapshot
from backend.app.services.ai_service import OpenAICompatibleTextClient
from backend.app.services.wechat_official_crawl_service import WechatOfficialCrawlService, serialize_article, serialize_metric

POOL_STATUSES = {"candidate", "shortlisted", "analyzing", "draft_ready", "rejected", "archived"}
SENSITIVE_KEYS = {"api_key", "apikey", "encrypted_api_key", "cookie", "token", "authorization", "auth_key", "key", "pass_ticket", "wap_sid2", "appmsg_token"}

ANALYSIS_FIELDS = {
    "recommendation_status",
    "pool_status",
    "low_follower_evidence",
    "low_follower_note",
    "business_direction",
    "title_type",
    "article_type_label",
    "viral_factors",
    "core_insight",
    "case_info",
    "customer_conversion_method",
    "hotspot_breakdown",
    "draft_template_key",
    "analysis_mode",
    "analysis_updated_at",
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
            if filters.get("pool_status") and _pool_status(analysis) != filters["pool_status"]:
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
        _validate_analysis_payload(payload)
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

    def get_detail(self, user_id: int, article_id: int) -> dict[str, Any]:
        article = get_owned_content_article(self.db, user_id, article_id)
        latest_metric = self._latest_metric(article.id)
        metric_payload = serialize_metric(latest_metric) if latest_metric else None
        analysis = _analysis(article)
        latest_snapshot = self._latest_snapshot(article.id)
        return {
            "article": serialize_article(article, latest_metric=metric_payload, analysis=analysis),
            "latest_metric": metric_payload,
            "analysis": analysis,
            "latest_snapshot": _serialize_snapshot_detail(latest_snapshot) if latest_snapshot else None,
            "images": _detail_images(article, latest_snapshot),
            "comments": _comments(self.db, article.id),
            "detail_status": _detail_status(article, latest_snapshot, _detail_images(article, latest_snapshot), _comments(self.db, article.id)),
            "raw_json": _safe_raw_json(article.raw_json or {}),
        }

    def analyze_hotspots(self, user_id: int, article_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        article = get_owned_content_article(self.db, user_id, article_id)
        snapshot = self._latest_snapshot(article.id)
        source_text = snapshot.text if snapshot and snapshot.text else article.digest
        analysis = _analysis(article)
        raw = dict(article.raw_json or {})
        instruction = str(payload.get("instruction") or "").strip()
        mode = "template"
        try:
            ai_payload = self._analyze_with_ai(user_id, article, source_text, instruction)
            analysis.update(_normalize_ai_analysis(ai_payload))
            mode = "ai"
        except _NoTextModel:
            analysis.update(_template_hotspot_analysis(article, source_text))
            mode = "template"
        except Exception:
            analysis.update(_template_hotspot_analysis(article, source_text))
            mode = "template_ai_parse_failed"
        analysis["analysis_mode"] = mode
        analysis["pool_status"] = "shortlisted"
        analysis["analysis_updated_at"] = shanghai_now().isoformat()
        raw["analysis"] = analysis
        article.raw_json = raw
        flag_modified(article, "raw_json")
        self.db.commit()
        self.db.refresh(article)
        return {"article_id": article.id, "analysis_mode": mode, "analysis": analysis}

    def _analyze_with_ai(self, user_id: int, article: WechatOfficialArticle, source_text: str, instruction: str) -> dict[str, Any]:
        model_config = self.db.scalar(
            select(ModelConfig).where(ModelConfig.user_id == user_id, ModelConfig.model_type == "text", ModelConfig.is_default.is_(True))
        )
        if model_config is None:
            raise _NoTextModel()
        api_key = decrypt_text(model_config.encrypted_api_key) if model_config.encrypted_api_key else ""
        prompt = (
            "请把下面微信公众号文章拆解为 JSON，字段包括 hotspot_breakdown、viral_factors、core_insight、title_type、article_type_label。"
            "hotspot_breakdown 必须包含 hook、pain_point、promise、credibility、structure、reuse_angle。只输出 JSON。\n\n"
            f"补充要求：{instruction or '从公众号运营二创角度分析'}\n"
            f"标题：{article.title}\n摘要：{article.digest}\n正文：{source_text[:5000]}"
        )
        content = OpenAICompatibleTextClient().polish_text(model_config=model_config, api_key=api_key, text=prompt, instruction="只输出 JSON")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError("AI hotspot analysis is not valid JSON") from exc
        if not isinstance(parsed, dict):
            raise ValueError("AI hotspot analysis must be a JSON object")
        return parsed

    def _latest_metric(self, article_id: int) -> WechatOfficialArticleMetric | None:
        return self.db.scalar(
            select(WechatOfficialArticleMetric)
            .where(WechatOfficialArticleMetric.article_id == article_id)
            .order_by(WechatOfficialArticleMetric.captured_at.desc(), WechatOfficialArticleMetric.id.desc())
        )

    def _latest_snapshot(self, article_id: int) -> WechatOfficialArticleSnapshot | None:
        return self.db.scalar(
            select(WechatOfficialArticleSnapshot)
            .where(WechatOfficialArticleSnapshot.article_id == article_id)
            .order_by(WechatOfficialArticleSnapshot.captured_at.desc(), WechatOfficialArticleSnapshot.id.desc())
        )

    def _is_owned(self, user_id: int, article: WechatOfficialArticle) -> bool:
        try:
            WechatOfficialCrawlService(self.db)._get_owned_article(user_id, article.id)
            return True
        except HTTPException:
            return False


class _NoTextModel(Exception):
    pass


def get_owned_content_article(db: Session, user_id: int, article_id: int) -> WechatOfficialArticle:
    article = WechatOfficialCrawlService(db)._get_owned_article(user_id, article_id)
    if article is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    return article


def _analysis(article: WechatOfficialArticle) -> dict[str, Any]:
    raw = article.raw_json or {}
    analysis = raw.get("analysis")
    return dict(analysis) if isinstance(analysis, dict) else {}


def _validate_analysis_payload(payload: dict[str, Any]) -> None:
    pool_status = payload.get("pool_status")
    if pool_status is not None and pool_status not in POOL_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid pool_status")


def _pool_status(analysis: dict[str, Any]) -> str:
    return str(analysis.get("pool_status") or analysis.get("recommendation_status") or "candidate")


def _serialize_snapshot_detail(snapshot: WechatOfficialArticleSnapshot) -> dict[str, Any]:
    return {
        "id": snapshot.id,
        "article_id": snapshot.article_id,
        "status": snapshot.status,
        "text": snapshot.text,
        "html": snapshot.html,
        "images_json": snapshot.images_json or [],
        "captured_at": snapshot.captured_at.isoformat() if snapshot.captured_at else None,
    }


def _safe_raw_json(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).lower() in SENSITIVE_KEYS:
                continue
            cleaned[key] = _safe_raw_json(item)
        return cleaned
    if isinstance(value, list):
        return [_safe_raw_json(item) for item in value]
    return value


def _detail_images(article: WechatOfficialArticle, snapshot: WechatOfficialArticleSnapshot | None) -> list[dict[str, Any]]:
    images: list[dict[str, Any]] = []
    if snapshot and isinstance(snapshot.images_json, list):
        for item in snapshot.images_json:
            if isinstance(item, dict) and item.get("url"):
                images.append(_safe_raw_json(item))
            elif isinstance(item, str) and item:
                images.append({"url": item, "type": "content", "source": "snapshot"})
    if article.cover_url:
        images.insert(0, {"url": article.cover_url, "type": "cover", "alt": "", "width": None, "height": None, "source": "article"})
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for image in images:
        url = str(image.get("url") or "")
        if not url or url in seen:
            continue
        seen.add(url)
        deduped.append(image)
    return deduped


def _comments(db: Session, article_id: int, limit: int = 50) -> dict[str, Any]:
    rows = db.scalars(
        select(WechatOfficialArticleComment)
        .where(WechatOfficialArticleComment.article_id == article_id)
        .order_by(WechatOfficialArticleComment.like_count.desc(), WechatOfficialArticleComment.id.asc())
        .limit(limit)
    ).all()
    items = []
    for comment in rows:
        replies = db.scalars(
            select(WechatOfficialArticleCommentReply)
            .where(WechatOfficialArticleCommentReply.comment_id == comment.id)
            .order_by(WechatOfficialArticleCommentReply.id.asc())
        ).all()
        items.append(
            {
                "id": comment.id,
                "article_id": comment.article_id,
                "comment_id": comment.comment_id,
                "user_name": comment.user_name,
                "user_id": comment.user_id,
                "content": comment.content,
                "like_count": comment.like_count,
                "created_at_remote": comment.created_at_remote,
                "raw_json": _safe_raw_json(comment.raw_json or {}),
                "replies": [
                    {
                        "id": reply.id,
                        "reply_id": reply.reply_id,
                        "user_name": reply.user_name,
                        "user_id": reply.user_id,
                        "content": reply.content,
                        "like_count": reply.like_count,
                        "created_at_remote": reply.created_at_remote,
                        "raw_json": _safe_raw_json(reply.raw_json or {}),
                    }
                    for reply in replies
                ],
            }
        )
    return {"items": items, "total": len(items), "available": bool(items), "source": "stored" if items else "none"}


def _detail_status(article: WechatOfficialArticle, snapshot: WechatOfficialArticleSnapshot | None, images: list[dict[str, Any]], comments: dict[str, Any]) -> dict[str, Any]:
    return {
        "has_cover": bool(article.cover_url),
        "has_snapshot": snapshot is not None,
        "has_text": bool(snapshot and snapshot.text),
        "has_html": bool(snapshot and snapshot.html),
        "image_count": len(images),
        "comment_count": int(comments.get("total") or 0),
        "can_refresh_from_redfox": bool(article.article_url or article.content_url),
    }


def _template_hotspot_analysis(article: WechatOfficialArticle, source_text: str) -> dict[str, Any]:
    digest = article.digest or source_text[:120]
    return {
        "hotspot_breakdown": {
            "hook": article.title or "待补充标题钩子",
            "pain_point": digest[:80] or "待人工补充读者痛点",
            "promise": "待人工补充可交付收益",
            "credibility": "待人工补充案例或数据证据",
            "structure": "标题-痛点-案例-方法-转化",
            "reuse_angle": "可作为公众号二创选题参考",
        },
        "viral_factors": ["强标题", "可复用结构"],
        "core_insight": digest[:160] or "待人工补充核心洞察",
        "title_type": "待确认",
        "article_type_label": "待拆解",
    }


def _normalize_ai_analysis(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = _template_hotspot_analysis(WechatOfficialArticle(title=""), "")
    hotspot = payload.get("hotspot_breakdown") if isinstance(payload.get("hotspot_breakdown"), dict) else {}
    normalized["hotspot_breakdown"] = {**normalized["hotspot_breakdown"], **hotspot}
    for key in ("viral_factors", "core_insight", "title_type", "article_type_label"):
        if key in payload:
            normalized[key] = payload[key]
    return normalized


def _matches_low_follower_evidence(value: Any, expected: Any) -> bool:
    expected_text = str(expected).strip().lower()
    if expected_text in {"unknown", "manual", "inferred"}:
        return str(value or "unknown").strip().lower() == expected_text
    if expected_text in {"true", "1", "yes"}:
        return bool(value) is True
    if expected_text in {"false", "0", "no"}:
        return bool(value) is False
    return str(value or "").strip().lower() == expected_text

from __future__ import annotations

import csv
import io
import json
from html import escape
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from backend.app.core.config import get_settings
from backend.app.core.database import Base
from backend.app.core.security import decrypt_text
from backend.app.core.time import shanghai_now
from backend.app.models import (
    Notification,
    WechatOfficialArticle,
    WechatOfficialArticleComment,
    WechatOfficialArticleCommentReply,
    WechatOfficialArticleMetric,
    WechatOfficialArticleSnapshot,
    WechatOfficialDraftSource,
    WechatOfficialIngestError,
)
from backend.app.services.ai_service import OpenAICompatibleTextClient
from backend.app.services.asset_storage_policy import export_owner_prefix
from backend.app.services.model_config_service import get_default_model_config
from backend.app.services.wechat_official_content_tombstone_service import WechatOfficialContentTombstoneService
from backend.app.services.wechat_official_crawl_service import WechatOfficialCrawlService, serialize_article, serialize_metric

POOL_STATUSES = {"candidate", "shortlisted", "analyzing", "draft_ready", "rejected", "archived"}
SENSITIVE_KEYS = {"api_key", "apikey", "encrypted_api_key", "cookie", "token", "authorization", "auth_key", "key", "pass_ticket", "wap_sid2", "appmsg_token"}

ANALYSIS_FIELDS = {
    "recommendation_status",
    "pool_status",
    "category",
    "tags",
    "is_favorite",
    "read_status",
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

READ_STATUSES = {"unread", "read", "reading"}
EXPORT_FORMATS = {"json", "csv"}


class WechatOfficialContentService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_content(self, user_id: int, filters: dict[str, Any]) -> dict[str, Any]:
        pool_status = filters.get("pool_status")
        if pool_status is not None and pool_status not in POOL_STATUSES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid pool_status")

        page = max(1, int(filters.get("page") or 1))
        page_size = max(1, min(100, int(filters.get("page_size") or 20)))
        job_id = filters.get("job_id")
        articles = self.db.scalars(select(WechatOfficialArticle).order_by(WechatOfficialArticle.updated_at.desc(), WechatOfficialArticle.id.desc())).all()
        items = []
        for article in articles:
            if job_id is not None and article.job_id != int(job_id):
                continue
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
            if pool_status and _pool_status(analysis) != pool_status:
                continue
            if filters.get("category") and str(analysis.get("category") or "") != str(filters["category"]):
                continue
            if filters.get("tag") and str(filters["tag"]) not in [str(tag) for tag in analysis.get("tags") or []]:
                continue
            if filters.get("is_favorite") is not None and bool(analysis.get("is_favorite")) is not bool(filters["is_favorite"]):
                continue
            if filters.get("read_status") and str(analysis.get("read_status") or "unread") != str(filters["read_status"]):
                continue
            detail_status = self._article_detail_status(article)
            if filters.get("detail_complete") is not None and bool(detail_status.get("is_complete")) is not bool(filters["detail_complete"]):
                continue
            keyword = str(filters.get("keyword") or "").strip()
            if keyword and not _matches_keyword(article, keyword):
                continue
            items.append(_with_detail_status(serialize_article(article, latest_metric=metric_payload, analysis=analysis), detail_status))
        total = len(items)
        start = (page - 1) * page_size
        return {"items": items[start : start + page_size], "total": total, "page": page, "page_size": page_size}

    def export_articles(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        article_ids = [int(article_id) for article_id in dict.fromkeys(payload.get("article_ids") or [])]
        if not article_ids:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="article_ids is required")
        export_format = str(payload.get("format") or "json").lower()
        if export_format not in EXPORT_FORMATS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid export format")
        articles = [get_owned_content_article(self.db, user_id, article_id) for article_id in article_ids]
        export_dir = Path(get_settings().storage_dir) / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        exported_at = shanghai_now()
        file_name = f"{export_owner_prefix('wechat_official', 'articles', user_id)}{exported_at.strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}.{export_format}"
        file_path = export_dir / file_name
        if export_format == "csv":
            file_path.write_text("﻿" + self._build_articles_csv(articles), encoding="utf-8")
        else:
            export_payload = {
                "platform": "wechat_official",
                "format": export_format,
                "exported_at": exported_at.isoformat(),
                "total": len(articles),
                "items": [self._serialize_export_article(article) for article in articles],
            }
            file_path.write_text(json.dumps(export_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"exported_count": len(articles), "file_name": file_name, "file_path": str(file_path.resolve()), "download_url": f"/api/files/exports/{file_name}"}

    def rss_feed(self, user_id: int, filters: dict[str, Any]) -> Response:
        payload = self.list_content(user_id, {**filters, "page": 1, "page_size": 100})
        items = payload.get("items") or []
        feed_items = []
        for item in items:
            article_url = escape(str(item.get("article_url") or item.get("content_url") or ""))
            title = escape(str(item.get("title") or "未命名公众号文章"))
            digest = escape(str(item.get("digest") or ""))
            category = escape(str((item.get("analysis") or {}).get("category") or ""))
            feed_items.append(
                "<item>"
                f"<title>{title}</title>"
                f"<link>{article_url}</link>"
                f"<guid>{article_url}</guid>"
                f"<description>{digest}</description>"
                f"<category>{category}</category>"
                "</item>"
            )
        body = (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
            "<rss version=\"2.0\"><channel>"
            "<title>公众号内容库</title>"
            "<description>本地公众号文章内容库 RSS</description>"
            "<link>https://localhost/wechat-official/content-library</link>"
            + "".join(feed_items)
            + "</channel></rss>"
        )
        return Response(content=body, media_type="application/rss+xml; charset=utf-8")

    def auto_refresh(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        article_ids = [int(article_id) for article_id in dict.fromkeys(payload.get("article_ids") or [])]
        if not article_ids:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="article_ids is required")
        refreshed_count = 0
        failed: list[dict[str, Any]] = []
        from backend.app.services.wechat_official_redfox_service import WechatOfficialRedfoxService

        redfox_service = WechatOfficialRedfoxService(self.db)
        for article_id in article_ids:
            article = get_owned_content_article(self.db, user_id, article_id)
            if self._article_detail_status(article).get("is_complete"):
                continue
            try:
                redfox_service.refresh_article_detail(user_id, article.id)
                refreshed_count += 1
            except Exception as exc:
                failed.append({"article_id": article.id, "message": str(exc)})
        level = "info" if not failed else "warning"
        title = f"已自动补全 {refreshed_count} 篇公众号文章" if not failed else f"公众号自动补全完成：成功 {refreshed_count} 篇，失败 {len(failed)} 篇"
        self.db.add(
            Notification(
                user_id=user_id,
                title=title,
                body="自动补全只写入本地正文、图片、评论和指标；不会上传素材、发布或群发。",
                level=level,
                source_type="wechat_official_content_auto_refresh",
            )
        )
        self.db.commit()
        return {"requested_count": len(article_ids), "refreshed_count": refreshed_count, "failed_count": len(failed), "failed": failed}

    def _serialize_export_article(self, article: WechatOfficialArticle) -> dict[str, Any]:
        latest_metric = self._latest_metric(article.id)
        snapshot = self._latest_snapshot(article.id)
        analysis = _analysis(article)
        return {
            **serialize_article(article, latest_metric=serialize_metric(latest_metric) if latest_metric else None, analysis=analysis),
            "detail_status": _detail_status(article, snapshot, _detail_images(article, snapshot), _comments(self.db, article.id)),
            "latest_snapshot": _serialize_snapshot_detail(snapshot) if snapshot else None,
        }

    def _build_articles_csv(self, articles: list[WechatOfficialArticle]) -> str:
        output = io.StringIO()
        fieldnames = ["id", "title", "author_name", "article_url", "read_count", "category", "tags", "is_favorite", "read_status", "created_at"]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for article in articles:
            metric = self._latest_metric(article.id)
            analysis = _analysis(article)
            writer.writerow(
                {
                    "id": article.id,
                    "title": article.title,
                    "author_name": article.author_name,
                    "article_url": article.article_url,
                    "read_count": metric.read_count if metric else 0,
                    "category": analysis.get("category") or "",
                    "tags": ",".join(str(tag) for tag in analysis.get("tags") or []),
                    "is_favorite": bool(analysis.get("is_favorite")),
                    "read_status": analysis.get("read_status") or "unread",
                    "created_at": article.created_at.isoformat() if article.created_at else "",
                }
            )
        return output.getvalue()

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
        return _with_detail_status(
            serialize_article(article, latest_metric=serialize_metric(latest_metric) if latest_metric else None, analysis=analysis),
            self._article_detail_status(article),
        )

    def get_detail(self, user_id: int, article_id: int) -> dict[str, Any]:
        article = get_owned_content_article(self.db, user_id, article_id)
        latest_metric = self._latest_metric(article.id)
        metric_payload = serialize_metric(latest_metric) if latest_metric else None
        analysis = _analysis(article)
        latest_snapshot = self._latest_snapshot(article.id)
        images = _detail_images(article, latest_snapshot)
        comments = _comments(self.db, article.id)
        detail_status = _detail_status(article, latest_snapshot, images, comments)
        return {
            "article": _with_detail_status(serialize_article(article, latest_metric=metric_payload, analysis=analysis), detail_status),
            "latest_metric": metric_payload,
            "analysis": analysis,
            "latest_snapshot": _serialize_snapshot_detail(latest_snapshot) if latest_snapshot else None,
            "images": images,
            "comments": comments,
            "detail_status": detail_status,
            "raw_json": _safe_raw_json(article.raw_json or {}),
        }

    def delete_article(self, user_id: int, article_id: int) -> dict[str, Any]:
        bind = self.db.get_bind()
        if not hasattr(bind, "metadata"):
            bind.metadata = Base.metadata
        article = get_owned_content_article(self.db, user_id, article_id)
        article_url = str(article.article_url or article.content_url or "").strip()
        if article_url:
            WechatOfficialContentTombstoneService(self.db).tombstone(user_id, article_url, article.title)

        comment_ids = select(WechatOfficialArticleComment.id).where(WechatOfficialArticleComment.article_id == article.id)
        self.db.execute(delete(WechatOfficialArticleCommentReply).where(WechatOfficialArticleCommentReply.comment_id.in_(comment_ids)))
        self.db.execute(delete(WechatOfficialArticleComment).where(WechatOfficialArticleComment.article_id == article.id))
        self.db.execute(delete(WechatOfficialArticleMetric).where(WechatOfficialArticleMetric.article_id == article.id))
        self.db.execute(delete(WechatOfficialArticleSnapshot).where(WechatOfficialArticleSnapshot.article_id == article.id))
        self.db.execute(delete(WechatOfficialIngestError).where(WechatOfficialIngestError.article_id == article.id))
        self.db.execute(delete(WechatOfficialDraftSource).where(WechatOfficialDraftSource.article_id == article.id))
        self.db.delete(article)
        self.db.commit()
        return {"id": article_id, "status": "deleted"}

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
        model_config = get_default_model_config(self.db, user_id=user_id, model_type="text", capability="text")
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

    def _article_detail_status(self, article: WechatOfficialArticle) -> dict[str, Any]:
        latest_snapshot = self._latest_snapshot(article.id)
        comments = _comments(self.db, article.id)
        return _detail_status(article, latest_snapshot, _detail_images(article, latest_snapshot), comments)

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
    read_status = payload.get("read_status")
    if read_status is not None and read_status not in READ_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid read_status")
    tags = payload.get("tags")
    if tags is not None and not isinstance(tags, list):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tags")


def _pool_status(analysis: dict[str, Any]) -> str:
    return str(analysis.get("pool_status") or analysis.get("recommendation_status") or "candidate")


def _matches_keyword(article: WechatOfficialArticle, keyword: str) -> bool:
    normalized = keyword.casefold()
    fields = [article.title, article.digest, article.author_name]
    return any(normalized in str(value or "").casefold() for value in fields)


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
    has_text = bool(snapshot and snapshot.text)
    has_html = bool(snapshot and snapshot.html)
    image_count = len(images)
    is_complete = has_text and has_html and image_count > 0
    return {
        "has_cover": bool(article.cover_url),
        "has_snapshot": snapshot is not None,
        "has_text": has_text,
        "has_html": has_html,
        "image_count": image_count,
        "comment_count": int(comments.get("total") or 0),
        "completeness": "complete" if is_complete else "partial" if snapshot is not None else "missing",
        "is_complete": is_complete,
        "can_refresh_from_redfox": bool(article.article_url or article.content_url),
    }


def _with_detail_status(article_payload: dict[str, Any], detail_status: dict[str, Any]) -> dict[str, Any]:
    return {**article_payload, "detail_status": detail_status}


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

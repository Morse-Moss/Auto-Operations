from __future__ import annotations

from typing import Any

import re
from urllib.parse import urlparse

import requests
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from backend.app.adapters.wechat_official.redfox_adapter import WechatOfficialRedfoxAdapter, sanitize_payload
from backend.app.core.security import decrypt_text, encrypt_text
from backend.app.core.time import shanghai_now
from backend.app.models import (
    WechatOfficialArticle,
    WechatOfficialArticleComment,
    WechatOfficialArticleCommentReply,
    WechatOfficialArticleMetric,
    WechatOfficialArticleSnapshot,
    WechatOfficialCrawlAccount,
    WechatOfficialCrawlJob,
    WechatOfficialRedfoxConfig,
)
from backend.app.services.wechat_official_content_tombstone_service import WechatOfficialContentTombstoneService
from backend.app.services.wechat_official_crawl_service import WechatOfficialCrawlService, serialize_article, serialize_crawl_job, serialize_metric
from backend.app.services.wechat_official_redfox_client import RedfoxApiError, WechatOfficialRedfoxClient

DEFAULT_REDFOX_BASE_URL = "https://redfox.hk"
DEFAULT_PAGE_SIZE = 20
DEFAULT_TARGET_COUNT = 10
MAX_TARGET_COUNT = 50
MAX_PAGES = 3
MAX_KEYWORD_AUTO_PAGES = 5
COLLECT_SOURCE_LABELS = {"redfox_keyword", "redfox_account", "redfox_url"}


class WechatOfficialRedfoxService:
    def __init__(self, db: Session, adapter: WechatOfficialRedfoxAdapter | None = None) -> None:
        self.db = db
        self.adapter = adapter or WechatOfficialRedfoxAdapter()

    def get_config(self, user_id: int) -> dict[str, Any]:
        config = self._find_config(user_id)
        return {"configured": config is not None and bool(config.encrypted_api_key), "config": serialize_redfox_config(config) if config else None}

    def save_config(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        config = self._find_config(user_id)
        if config is None:
            config = WechatOfficialRedfoxConfig(user_id=user_id)
            self.db.add(config)

        if payload.get("name") is not None:
            config.name = str(payload.get("name") or "RedFoxHub").strip() or "RedFoxHub"
        if payload.get("base_url") is not None:
            config.base_url = _normalize_base_url(str(payload.get("base_url") or DEFAULT_REDFOX_BASE_URL))
        elif not config.base_url:
            config.base_url = DEFAULT_REDFOX_BASE_URL

        api_key = payload.get("api_key")
        if isinstance(api_key, str) and api_key.strip():
            config.encrypted_api_key = encrypt_text(api_key.strip())
            config.status = "unknown"
            config.last_error = ""

        config.updated_at = shanghai_now()
        self.db.commit()
        self.db.refresh(config)
        return {"configured": bool(config.encrypted_api_key), "config": serialize_redfox_config(config)}

    def validate_config(self, user_id: int) -> dict[str, Any]:
        config = self._require_config(user_id)
        if not config.encrypted_api_key:
            config.status = "invalid"
            config.last_checked_at = shanghai_now()
            config.last_error = "未配置 Redfox API Key"
            self.db.commit()
            self.db.refresh(config)
            return {"ok": False, "config": serialize_redfox_config(config), "message": config.last_error}

        try:
            client = WechatOfficialRedfoxClient(base_url=config.base_url or DEFAULT_REDFOX_BASE_URL, api_key=decrypt_text(config.encrypted_api_key))
            client.validate_key()
        except requests.Timeout:
            config.status = "invalid"
            config.last_error = "Redfox 校验超时，请稍后重试"
        except requests.RequestException:
            config.status = "invalid"
            config.last_error = "Redfox 网络请求失败，请检查网络或稍后重试"
        except (RedfoxApiError, ValueError):
            config.status = "invalid"
            config.last_error = "Redfox API Key 无效或服务返回异常"
        else:
            config.status = "valid"
            config.last_error = ""
        config.last_checked_at = shanghai_now()
        self.db.commit()
        self.db.refresh(config)
        if config.status == "valid":
            return {"ok": True, "config": serialize_redfox_config(config), "message": "Redfox 配置可用"}
        return {"ok": False, "config": serialize_redfox_config(config), "message": config.last_error}

    def list_collect_jobs(self, user_id: int, filters: dict[str, Any]) -> dict[str, Any]:
        page = max(1, int(filters.get("page") or 1))
        page_size = max(1, min(100, int(filters.get("page_size") or 20)))
        source_label = str(filters.get("source_label") or "").strip()
        owned_job_ids = (
            select(WechatOfficialArticle.job_id)
            .join(WechatOfficialCrawlAccount, WechatOfficialArticle.account_id == WechatOfficialCrawlAccount.id)
            .where(WechatOfficialCrawlAccount.user_id == user_id, WechatOfficialArticle.job_id.is_not(None))
            .distinct()
        )
        jobs = self.db.scalars(
            select(WechatOfficialCrawlJob)
            .where(WechatOfficialCrawlJob.source == "redfox", WechatOfficialCrawlJob.id.in_(owned_job_ids))
            .order_by(WechatOfficialCrawlJob.created_at.desc(), WechatOfficialCrawlJob.id.desc())
        ).all()
        items = []
        for job in jobs:
            params = job.params_json if isinstance(job.params_json, dict) else {}
            label = str(params.get("source") or "")
            if label not in COLLECT_SOURCE_LABELS:
                continue
            if source_label and label != source_label:
                continue
            items.append(serialize_crawl_job(job))
        total = len(items)
        start = (page - 1) * page_size
        return {"items": items[start : start + page_size], "total": total, "page": page, "page_size": page_size}

    def get_collect_job(self, user_id: int, job_id: int) -> dict[str, Any]:
        job = self.db.get(WechatOfficialCrawlJob, job_id)
        if job is None or job.source != "redfox":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Redfox collect job not found")
        params = job.params_json if isinstance(job.params_json, dict) else {}
        if str(params.get("source") or "") not in COLLECT_SOURCE_LABELS:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Redfox collect job not found")
        articles = self.db.scalars(
            select(WechatOfficialArticle)
            .join(WechatOfficialCrawlAccount, WechatOfficialArticle.account_id == WechatOfficialCrawlAccount.id)
            .where(
                WechatOfficialArticle.job_id == job_id,
                WechatOfficialCrawlAccount.user_id == user_id,
            )
            .order_by(WechatOfficialArticle.updated_at.desc(), WechatOfficialArticle.id.desc())
        ).all()
        if not articles:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Redfox collect job not found")
        items = []
        for article in articles:
            latest_metric = self._latest_metric(article.id)
            analysis = dict((article.raw_json or {}).get("analysis") or {})
            items.append(serialize_article(article, latest_metric=serialize_metric(latest_metric) if latest_metric else None, analysis=analysis))
        return {"job": serialize_crawl_job(job), "items": items, "total": len(items)}

    def collect_articles(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        keyword = str(payload.get("keyword") or "").strip()
        if not keyword:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="keyword is required")

        sort_type = str(payload.get("sort_type") or "_4")
        target_count = _resolve_keyword_target_count(payload.get("target_count"), legacy_pages_value=payload.get("pages"))
        max_pages = _bounded_keyword_pages(payload.get("max_pages"), fallback=_legacy_pages(payload.get("pages")))
        min_read_count = _int_or_default(payload.get("min_read_count"), default=100000)
        save_snapshot = bool(payload.get("save_snapshot", True))

        client = self._client(user_id)
        fetched: list[dict[str, Any]] = []
        matched: list[dict[str, Any]] = []
        api_calls = 0
        filtered = 0
        relevance_matched = 0
        search_tokens = _keyword_tokens(keyword)
        target_reached = False

        for page_index in range(max_pages):
            response = client.search_articles(keyword=keyword, offset=page_index * DEFAULT_PAGE_SIZE, sort_type=sort_type)
            api_calls += 1
            page_items = self.adapter.normalize_article_list(response)
            fetched.extend(page_items)
            for item in page_items:
                is_match = _article_matches_keyword(item, search_tokens)
                if is_match:
                    relevance_matched += 1
                    if len(matched) < target_count:
                        matched.append(item)
                        if len(matched) >= target_count:
                            target_reached = True
                else:
                    filtered += 1
            if target_reached:
                break

        params: dict[str, Any] = {"keyword": keyword, "sort_type": sort_type, "target_count": target_count, "max_pages": max_pages}
        summary_extra = {
            "requested_target_count": target_count,
            "max_pages": max_pages,
            "filtered": filtered,
            "relevance_matched": relevance_matched,
            "target_reached": target_reached,
        }

        return self._save_collection(
            user_id,
            matched,
            source_label="redfox_keyword",
            keyword=keyword,
            requested_limit=target_count,
            min_read_count=min_read_count,
            save_snapshot=save_snapshot,
            api_calls=api_calls,
            fetched_count=len(fetched),
            params=params,
            summary_extra=summary_extra,
        )

    def collect_account(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        account = str(payload.get("account") or "").strip()
        if not account:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="account is required")
        account_name = str(payload.get("account_name") or "")
        pages = _bounded_pages(payload.get("pages"))
        sort_type = str(payload.get("sort_type") or "_4")
        client = self._client(user_id)
        normalized: list[dict[str, Any]] = []
        api_calls = 0
        for page_index in range(pages):
            response = client.query_work_list(
                account=account,
                account_name=account_name,
                offset=page_index * DEFAULT_PAGE_SIZE,
                sort_type=sort_type,
                publish_time_start=payload.get("publish_time_start"),
                publish_time_end=payload.get("publish_time_end"),
            )
            api_calls += 1
            normalized.extend(self.adapter.normalize_article_list(response))
        return self._save_collection(
            user_id,
            normalized,
            source_label="redfox_account",
            keyword=account_name or account,
            requested_limit=pages * DEFAULT_PAGE_SIZE,
            min_read_count=_int_or_default(payload.get("min_read_count"), default=100000),
            save_snapshot=bool(payload.get("save_snapshot", True)),
            api_calls=api_calls,
            params={
                "account": account,
                "account_name": account_name,
                "pages": pages,
                "sort_type": sort_type,
                "publish_time_start": payload.get("publish_time_start"),
                "publish_time_end": payload.get("publish_time_end"),
            },
        )

    def import_url(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        url = str(payload.get("url") or "").strip()
        if not url:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="url is required")
        client = self._client(user_id)
        response = self._query_article_detail_or_raise(client, url=url)
        normalized = [self.adapter.normalize_article_detail(response)]
        return self._save_collection(
            user_id,
            normalized,
            source_label="redfox_url",
            keyword=url,
            requested_limit=1,
            min_read_count=_int_or_default(payload.get("min_read_count"), default=100000),
            save_snapshot=bool(payload.get("save_snapshot", True)),
            api_calls=1,
            params={"url": url},
        )

    def refresh_article_detail(self, user_id: int, article_id: int) -> dict[str, Any]:
        article = WechatOfficialCrawlService(self.db)._get_owned_article(user_id, article_id)
        url = str(article.article_url or article.content_url or "").strip()
        if not url:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Article URL is required to refresh detail")

        client = self._client(user_id)
        response = self._query_article_detail_or_raise(client, url=url)
        payload = self.adapter.normalize_article_detail(response)
        payload["article_url"] = payload.get("article_url") or article.article_url or article.content_url
        payload["content_url"] = payload.get("content_url") or article.content_url or article.article_url
        payload["title"] = payload.get("title") or article.title
        payload["digest"] = payload.get("digest") or article.digest
        payload["author_name"] = payload.get("author_name") or article.author_name
        payload["cover_url"] = payload.get("cover_url") or article.cover_url or _first_image_url(payload.get("images"))

        job = WechatOfficialCrawlJob(
            account_id=article.account_id,
            keyword=url,
            status="running",
            source="redfox",
            requested_limit=1,
            fetched_count=1,
            params_json={"source": "redfox_detail_refresh", "api_calls": 1, "article_id": article.id, **sanitize_payload({"url": url})},
            started_at=shanghai_now(),
        )
        self.db.add(job)
        self.db.flush()

        self._upsert_redfox_article(article.account_id, job.id, payload, min_read_count=0)
        self._create_metric(article.id, payload)
        if payload.get("content_text") or payload.get("content_html") or payload.get("images"):
            self._create_snapshot(article.id, payload)
        self._store_redfox_comments(article.id, payload)
        job.status = "succeeded"
        job.saved_count = 1
        job.finished_at = shanghai_now()
        self.db.commit()

        from backend.app.services.wechat_official_content_service import WechatOfficialContentService

        return WechatOfficialContentService(self.db).get_detail(user_id, article_id)

    def _query_article_detail_or_raise(self, client: WechatOfficialRedfoxClient, *, url: str) -> dict[str, Any]:
        try:
            return client.query_article_detail(url=url)
        except requests.Timeout as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Redfox detail request timed out; please retry later") from exc
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else status.HTTP_502_BAD_GATEWAY
            message = f"Redfox detail request failed with HTTP {status_code}"
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=message) from exc
        except requests.RequestException as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Redfox detail request failed: {exc}") from exc
        except RedfoxApiError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Redfox detail API rejected the request: {exc}") from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Redfox detail response is not valid JSON") from exc

    def _save_collection(
        self,
        user_id: int,
        articles_payload: list[dict[str, Any]],
        *,
        source_label: str,
        keyword: str,
        requested_limit: int,
        min_read_count: int,
        save_snapshot: bool,
        api_calls: int,
        params: dict[str, Any],
        fetched_count: int | None = None,
        summary_extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        job = WechatOfficialCrawlJob(
            keyword=keyword,
            status="running",
            source="redfox",
            requested_limit=requested_limit,
            fetched_count=fetched_count if fetched_count is not None else len(articles_payload),
            params_json={"source": source_label, "api_calls": api_calls, **sanitize_payload(params), **sanitize_payload(summary_extra or {})},
            started_at=shanghai_now(),
        )
        self.db.add(job)
        self.db.flush()

        tombstones = WechatOfficialContentTombstoneService(self.db)
        saved_articles: list[WechatOfficialArticle] = []
        deduped = 0
        viral_candidates = 0
        for item in articles_payload:
            article_url = str(item.get("article_url") or item.get("content_url") or "").strip()
            if article_url and tombstones.is_tombstoned(user_id, article_url):
                continue
            account = self._upsert_redfox_account(user_id, item)
            article, created = self._upsert_redfox_article(account.id, job.id, item, min_read_count=min_read_count)
            if not created:
                deduped += 1
            metric = self._create_metric(article.id, item)
            if save_snapshot and (item.get("content_text") or item.get("content_html") or item.get("images")):
                self._create_snapshot(article.id, item)
            self._store_redfox_comments(article.id, item)
            if metric.read_count >= min_read_count:
                viral_candidates += 1
            saved_articles.append(article)

        job.status = "succeeded"
        job.saved_count = len(saved_articles)
        job.finished_at = shanghai_now()
        self.db.commit()
        self.db.refresh(job)

        items = []
        for article in saved_articles:
            latest_metric = self._latest_metric(article.id)
            analysis = dict((article.raw_json or {}).get("analysis") or {})
            items.append(serialize_article(article, latest_metric=serialize_metric(latest_metric) if latest_metric else None, analysis=analysis))
        summary = {
            "fetched": fetched_count if fetched_count is not None else len(articles_payload),
            "saved": len(saved_articles),
            "deduped": deduped,
            "viral_candidates": viral_candidates,
            "failed": 0,
            "api_calls": api_calls,
            "estimated_credit_cost": None,
        }
        if summary_extra:
            summary.update(summary_extra)
        return {
            "summary": summary,
            "job": serialize_crawl_job(job),
            "items": items,
        }

    def _upsert_redfox_account(self, user_id: int, payload: dict[str, Any]) -> WechatOfficialCrawlAccount:
        account_name = payload.get("account_name") or payload.get("author_name") or "Redfox公众号"
        account_key = payload.get("account") or account_name or "redfox"
        fake_id = f"redfox:{account_key}"
        account = self.db.scalar(select(WechatOfficialCrawlAccount).where(WechatOfficialCrawlAccount.user_id == user_id, WechatOfficialCrawlAccount.fake_id == fake_id))
        if account is None:
            account = WechatOfficialCrawlAccount(user_id=user_id, fake_id=fake_id, status="active")
            self.db.add(account)
        account.name = str(account_name)
        account.alias = str(payload.get("account") or account.alias or "")
        account.raw_json = {"source": "redfox", "raw": sanitize_payload(payload.get("raw") or {})}
        account.updated_at = shanghai_now()
        self.db.flush()
        return account

    def _upsert_redfox_article(self, account_id: int, job_id: int, payload: dict[str, Any], *, min_read_count: int) -> tuple[WechatOfficialArticle, bool]:
        article_url = str(payload.get("article_url") or "")
        article = None
        if article_url:
            article = self.db.scalar(select(WechatOfficialArticle).where(WechatOfficialArticle.article_url == article_url, WechatOfficialArticle.account_id == account_id))
        created = article is None
        if article is None:
            article = WechatOfficialArticle(account_id=account_id, article_url=article_url)
            self.db.add(article)
        article.job_id = job_id
        article.title = str(payload.get("title") or article.title)
        article.digest = str(payload.get("digest") or article.digest)
        article.author_name = str(payload.get("author_name") or article.author_name)
        article.source = "redfox"
        article.publish_time_remote = str(payload.get("publish_time_remote") or "") or article.publish_time_remote
        article.cover_url = str(payload.get("cover_url") or article.cover_url or _first_image_url(payload.get("images")))
        article.content_url = str(payload.get("content_url") or article.article_url)
        raw = dict(article.raw_json or {})
        analysis = dict(raw.get("analysis") or {})
        analysis.setdefault("low_follower_evidence", "unknown")
        read_count = int((payload.get("metrics") or {}).get("read_count") or 0)
        if read_count >= min_read_count:
            analysis.setdefault("recommendation_status", "candidate")
        raw["analysis"] = analysis
        raw["redfox"] = {
            "external_id": payload.get("external_id"),
            "work_uuid": payload.get("external_id"),
            "raw": sanitize_payload(payload.get("raw") or {}),
        }
        article.raw_json = raw
        flag_modified(article, "raw_json")
        article.updated_at = shanghai_now()
        self.db.flush()
        return article, created

    def _create_metric(self, article_id: int, payload: dict[str, Any]) -> WechatOfficialArticleMetric:
        metrics = payload.get("metrics") or {}
        metric = WechatOfficialArticleMetric(
            article_id=article_id,
            read_count=int(metrics.get("read_count") or 0),
            like_count=int(metrics.get("like_count") or 0),
            wow_count=int(metrics.get("wow_count") or 0),
            share_count=int(metrics.get("share_count") or 0),
            comment_count=int(metrics.get("comment_count") or 0),
            raw_json={"source": "redfox", "payload": sanitize_payload(payload.get("raw") or {})},
        )
        self.db.add(metric)
        self.db.flush()
        return metric

    def _create_snapshot(self, article_id: int, payload: dict[str, Any]) -> WechatOfficialArticleSnapshot:
        snapshot = WechatOfficialArticleSnapshot(
            article_id=article_id,
            status="captured",
            html=str(payload.get("content_html") or ""),
            text=str(payload.get("content_text") or payload.get("digest") or ""),
            images_json=sanitize_payload(payload.get("images") or []),
            raw_json={"source": "redfox", "external_id": payload.get("external_id"), "detail_completeness": payload.get("detail_completeness") or {}},
        )
        self.db.add(snapshot)
        self.db.flush()
        return snapshot

    def _store_redfox_comments(self, article_id: int, payload: dict[str, Any]) -> int:
        comments = payload.get("comments") or []
        if not isinstance(comments, list):
            return 0
        stored = 0
        for item in comments:
            if not isinstance(item, dict):
                continue
            comment_id = str(item.get("comment_id") or "").strip()
            if not comment_id:
                continue
            comment = self.db.scalar(select(WechatOfficialArticleComment).where(WechatOfficialArticleComment.article_id == article_id, WechatOfficialArticleComment.comment_id == comment_id))
            if comment is None:
                comment = WechatOfficialArticleComment(article_id=article_id, comment_id=comment_id)
                self.db.add(comment)
                stored += 1
            comment.user_name = str(item.get("user_name") or "")
            comment.user_id = item.get("user_id") or None
            comment.content = str(item.get("content") or "")
            comment.like_count = int(item.get("like_count") or 0)
            comment.created_at_remote = item.get("created_at_remote") or None
            comment.raw_json = sanitize_payload(item.get("raw") or item)
            self.db.flush()
            replies = item.get("replies") or []
            if not isinstance(replies, list):
                continue
            for reply_item in replies:
                if not isinstance(reply_item, dict):
                    continue
                reply_id = str(reply_item.get("reply_id") or "").strip()
                if not reply_id:
                    continue
                reply = self.db.scalar(select(WechatOfficialArticleCommentReply).where(WechatOfficialArticleCommentReply.comment_id == comment.id, WechatOfficialArticleCommentReply.reply_id == reply_id))
                if reply is None:
                    reply = WechatOfficialArticleCommentReply(comment_id=comment.id, reply_id=reply_id)
                    self.db.add(reply)
                reply.user_name = str(reply_item.get("user_name") or "")
                reply.user_id = reply_item.get("user_id") or None
                reply.content = str(reply_item.get("content") or "")
                reply.like_count = int(reply_item.get("like_count") or 0)
                reply.created_at_remote = reply_item.get("created_at_remote") or None
                reply.raw_json = sanitize_payload(reply_item.get("raw") or reply_item)
                self.db.flush()
        return stored

    def _latest_metric(self, article_id: int) -> WechatOfficialArticleMetric | None:
        return self.db.scalar(
            select(WechatOfficialArticleMetric)
            .where(WechatOfficialArticleMetric.article_id == article_id)
            .order_by(WechatOfficialArticleMetric.captured_at.desc(), WechatOfficialArticleMetric.id.desc())
        )

    def _client(self, user_id: int) -> WechatOfficialRedfoxClient:
        config = self._require_config(user_id)
        if not config.encrypted_api_key:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Redfox API Key is not configured")
        return WechatOfficialRedfoxClient(base_url=config.base_url or DEFAULT_REDFOX_BASE_URL, api_key=decrypt_text(config.encrypted_api_key))

    def _find_config(self, user_id: int) -> WechatOfficialRedfoxConfig | None:
        return self.db.scalar(select(WechatOfficialRedfoxConfig).where(WechatOfficialRedfoxConfig.user_id == user_id).order_by(WechatOfficialRedfoxConfig.id.desc()))

    def _require_config(self, user_id: int) -> WechatOfficialRedfoxConfig:
        config = self._find_config(user_id)
        if config is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Redfox config not found")
        return config


def _bounded_pages(value: Any) -> int:
    try:
        pages = int(value or 1)
    except (TypeError, ValueError):
        pages = 1
    return max(1, min(MAX_PAGES, pages))


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value if value is not None and value != "" else default)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def _int_or_default(value: Any, *, default: int) -> int:
    try:
        return int(value if value is not None and value != "" else default)
    except (TypeError, ValueError):
        return default


def _legacy_pages(value: Any) -> int:
    return _bounded_int(value, default=1, minimum=1, maximum=MAX_KEYWORD_AUTO_PAGES)


def _legacy_target_count(value: Any) -> int:
    if value is None or value == "":
        return DEFAULT_TARGET_COUNT
    return max(1, _legacy_pages(value) * DEFAULT_PAGE_SIZE)


def _resolve_keyword_target_count(value: Any, *, legacy_pages_value: Any) -> int:
    if value is None or value == "":
        return _legacy_target_count(legacy_pages_value)
    return _bounded_int(value, default=DEFAULT_TARGET_COUNT, minimum=1, maximum=MAX_TARGET_COUNT)


def _bounded_keyword_pages(value: Any, *, fallback: int) -> int:
    return _bounded_int(value, default=fallback, minimum=1, maximum=MAX_KEYWORD_AUTO_PAGES)


def _keyword_tokens(keyword: str) -> list[str]:
    tokens = [token.strip().lower() for token in re.split(r"[\s,，、\n\t]+", keyword) if token and token.strip()]
    if tokens:
        seen: set[str] = set()
        unique: list[str] = []
        for token in tokens:
            if token in seen:
                continue
            seen.add(token)
            unique.append(token)
        return unique
    return [keyword.strip().lower()]


def _article_matches_keyword(article: dict[str, Any], tokens: list[str]) -> bool:
    haystacks: list[str] = []
    for key in ("title", "digest", "content_text"):
        value = article.get(key)
        if isinstance(value, str) and value.strip():
            haystacks.append(value.strip().lower())
    raw = article.get("raw")
    if isinstance(raw, dict):
        for key in ("title", "summary", "memo", "content", "content_text"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                haystacks.append(value.strip().lower())
    for haystack in haystacks:
        for token in tokens:
            if token and token in haystack:
                return True
    return False


def _normalize_base_url(base_url: str) -> str:
    cleaned = (base_url or DEFAULT_REDFOX_BASE_URL).strip().rstrip("/") or DEFAULT_REDFOX_BASE_URL
    parsed = urlparse(cleaned)
    if parsed.scheme != "https" or parsed.netloc != "redfox.hk" or parsed.path not in ("", "/"):
        raise HTTPException(status_code=422, detail="Redfox base_url must be https://redfox.hk")
    return DEFAULT_REDFOX_BASE_URL


def _mask_api_key(encrypted_api_key: str) -> str:
    if not encrypted_api_key:
        return ""
    try:
        api_key = decrypt_text(encrypted_api_key)
    except Exception:
        return "****"
    suffix = api_key[-4:] if len(api_key) >= 4 else api_key
    return f"****{suffix}"


def _first_image_url(images: Any) -> str:
    if not isinstance(images, list):
        return ""

    fallback = ""
    for item in images:
        if isinstance(item, dict):
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            source = str(item.get("source") or "").strip().lower()
            if source.endswith("html"):
                return url
            if not fallback:
                fallback = url
            continue
        if isinstance(item, str) and item.strip() and not fallback:
            fallback = item.strip()
    return fallback


def serialize_redfox_config(config: WechatOfficialRedfoxConfig | None) -> dict[str, Any] | None:
    if config is None:
        return None
    return {
        "id": config.id,
        "name": config.name,
        "base_url": config.base_url,
        "has_api_key": bool(config.encrypted_api_key),
        "masked_api_key": _mask_api_key(config.encrypted_api_key),
        "status": config.status,
        "last_checked_at": config.last_checked_at.isoformat() if config.last_checked_at else None,
        "last_error": config.last_error,
        "created_at": config.created_at.isoformat() if config.created_at else None,
        "updated_at": config.updated_at.isoformat() if config.updated_at else None,
    }

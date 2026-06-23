from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.adapters.wechat_official.research_adapter import WechatOfficialResearchAdapter
from backend.app.core.time import shanghai_now
from backend.app.models import (
    WechatOfficialArticle,
    WechatOfficialArticleCredential,
    WechatOfficialArticleMetric,
    WechatOfficialArticleSnapshot,
    WechatOfficialBackendSession,
    WechatOfficialCrawlAccount,
    WechatOfficialCrawlJob,
)
from backend.app.services.wechat_official_backend_session_service import get_valid_session
from backend.app.services.wechat_official_content_tombstone_service import WechatOfficialContentTombstoneService
from backend.app.services.wechat_official_credential_service import serialize_credential


class WechatOfficialCrawlService:
    def __init__(self, db: Session, adapter: WechatOfficialResearchAdapter | None = None) -> None:
        self.db = db
        self.adapter = adapter or WechatOfficialResearchAdapter()

    def search_accounts(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        get_valid_session(self.db, user_id, int(payload["backend_session_id"]))
        accounts = self.adapter.normalize_searchbiz_accounts(payload.get("upstream_payload") or {})
        items = [self._upsert_account(user_id, account) for account in accounts]
        self.db.commit()
        return {"items": [serialize_crawl_account(item) for item in items], "total": len(items)}

    def sync_articles(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        session = get_valid_session(self.db, user_id, int(payload["backend_session_id"]))
        account_id = payload.get("account_id") or session.account_id
        account = self._get_owned_account(user_id, int(account_id)) if account_id else None
        articles_payload = self.adapter.normalize_appmsgpublish_articles(payload.get("upstream_payload") or {})
        limit = int(payload.get("limit") or len(articles_payload) or 0)
        selected = articles_payload[:limit] if limit else articles_payload
        job = WechatOfficialCrawlJob(
            account_id=account.id if account else None,
            keyword=str(payload.get("keyword") or ""),
            status="running",
            source="backend",
            requested_limit=limit,
            fetched_count=len(articles_payload),
            params_json={"backend_session_id": session.id},
            started_at=shanghai_now(),
        )
        self.db.add(job)
        self.db.flush()
        tombstones = WechatOfficialContentTombstoneService(self.db)
        saved: list[WechatOfficialArticle] = []
        for article_payload in selected:
            article_url = str(article_payload.get("article_url") or article_payload.get("content_url") or "").strip()
            if article_url and tombstones.is_tombstoned(user_id, article_url):
                continue
            article = self._upsert_article(account.id if account else None, job.id, article_payload)
            saved.append(article)
        job.status = "succeeded"
        job.saved_count = len(saved)
        job.finished_at = shanghai_now()
        self.db.commit()
        self.db.refresh(job)
        return {"job": serialize_crawl_job(job), "items": [serialize_article(article, latest_metric=None, analysis={}) for article in saved]}

    def capture_snapshot(self, user_id: int, article_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        article = self._get_owned_article(user_id, article_id)
        html = str(payload.get("html") or "")
        parsed = self.adapter.parse_html_snapshot(html)
        snapshot = WechatOfficialArticleSnapshot(
            article_id=article.id,
            status=parsed["status"],
            html=html,
            text=parsed["text"],
            images_json=[],
            raw_json={"comment_id": parsed["comment_id"]},
        )
        self.db.add(snapshot)
        self.db.commit()
        self.db.refresh(snapshot)
        return serialize_snapshot(snapshot)

    def capture_metrics(self, user_id: int, article_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        article = self._get_owned_article(user_id, article_id)
        credential = self._get_owned_valid_credential(user_id, int(payload["credential_id"]))
        parsed = self.adapter.parse_metrics(html=payload.get("html"), cgi_data=payload.get("cgi_data"))
        metric = WechatOfficialArticleMetric(
            article_id=article.id,
            read_count=parsed["read_count"],
            like_count=parsed["like_count"],
            wow_count=parsed["wow_count"],
            share_count=parsed["share_count"],
            comment_count=parsed["comment_count"],
            raw_json={"source": parsed["source"], "credential_id": credential.id, "payload": parsed["raw"]},
        )
        self.db.add(metric)
        self.db.commit()
        self.db.refresh(metric)
        return serialize_metric(metric)

    def _upsert_account(self, user_id: int, payload: dict[str, Any]) -> WechatOfficialCrawlAccount:
        fake_id = payload.get("fake_id") or ""
        account = None
        if fake_id:
            account = self.db.scalar(select(WechatOfficialCrawlAccount).where(WechatOfficialCrawlAccount.user_id == user_id, WechatOfficialCrawlAccount.fake_id == fake_id))
        if account is None:
            account = WechatOfficialCrawlAccount(user_id=user_id, fake_id=fake_id, status="active")
            self.db.add(account)
        account.name = payload.get("name") or account.name
        account.alias = payload.get("alias") or account.alias
        account.raw_json = {"avatar": payload.get("avatar"), "signature": payload.get("signature"), "service_type": payload.get("service_type"), "raw": payload.get("raw")}
        account.updated_at = shanghai_now()
        self.db.flush()
        return account

    def _upsert_article(self, account_id: int | None, job_id: int, payload: dict[str, Any]) -> WechatOfficialArticle:
        article_url = payload.get("article_url") or ""
        article = None
        if article_url:
            article = self.db.scalar(select(WechatOfficialArticle).where(WechatOfficialArticle.article_url == article_url, WechatOfficialArticle.account_id == account_id))
        if article is None:
            article = WechatOfficialArticle(account_id=account_id, article_url=article_url)
            self.db.add(article)
        article.job_id = job_id
        article.title = payload.get("title") or article.title
        article.digest = payload.get("digest") or article.digest
        article.author_name = payload.get("author_name") or article.author_name
        article.cover_url = payload.get("cover_url") or article.cover_url
        article.content_url = article_url
        article.publish_time_remote = payload.get("publish_time_remote")
        article.raw_json = {"aid": payload.get("aid"), "raw": payload.get("raw")}
        article.updated_at = shanghai_now()
        self.db.flush()
        return article

    def _get_owned_account(self, user_id: int, account_id: int) -> WechatOfficialCrawlAccount:
        account = self.db.get(WechatOfficialCrawlAccount, account_id)
        if account is None or account.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wechat Official account not found")
        return account

    def _get_owned_article(self, user_id: int, article_id: int) -> WechatOfficialArticle:
        article = self.db.get(WechatOfficialArticle, article_id)
        if article is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
        if article.account_id is not None:
            account = self.db.get(WechatOfficialCrawlAccount, article.account_id)
            if account is None or account.user_id != user_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
        else:
            job = self.db.get(WechatOfficialCrawlJob, article.job_id) if article.job_id else None
            session_id = (job.params_json or {}).get("backend_session_id") if job else None
            session = self.db.get(WechatOfficialBackendSession, session_id) if session_id else None
            account = self.db.get(WechatOfficialCrawlAccount, session.account_id) if session else None
            if account is None or account.user_id != user_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
        return article

    def _get_owned_valid_credential(self, user_id: int, credential_id: int) -> WechatOfficialArticleCredential:
        credential = self.db.get(WechatOfficialArticleCredential, credential_id)
        if credential is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found")
        account = self.db.get(WechatOfficialCrawlAccount, credential.account_id)
        if account is None or account.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found")
        serialized = serialize_credential(credential, account=account)
        if not serialized["valid"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Credential is not valid or expired")
        return credential


def serialize_crawl_account(account: WechatOfficialCrawlAccount) -> dict[str, Any]:
    raw = account.raw_json or {}
    return {
        "id": account.id,
        "name": account.name,
        "biz": account.biz,
        "fake_id": account.fake_id,
        "alias": account.alias,
        "status": account.status,
        "raw": {"avatar": raw.get("avatar"), "signature": raw.get("signature"), "service_type": raw.get("service_type")},
        "created_at": account.created_at.isoformat() if account.created_at else None,
        "updated_at": account.updated_at.isoformat() if account.updated_at else None,
    }


def serialize_crawl_job(job: WechatOfficialCrawlJob) -> dict[str, Any]:
    params = job.params_json if isinstance(job.params_json, dict) else {}
    return {
        "id": job.id,
        "account_id": job.account_id,
        "proxy_node_id": job.proxy_node_id,
        "keyword": job.keyword,
        "status": job.status,
        "source": job.source,
        "requested_limit": job.requested_limit,
        "fetched_count": job.fetched_count,
        "saved_count": job.saved_count,
        "error_message": job.error_message,
        "params": params,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


def serialize_article(article: WechatOfficialArticle, *, latest_metric: dict[str, Any] | None, analysis: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": article.id,
        "account_id": article.account_id,
        "job_id": article.job_id,
        "article_url": article.article_url,
        "title": article.title,
        "digest": article.digest,
        "author_name": article.author_name,
        "cover_url": article.cover_url,
        "content_url": article.content_url,
        "publish_time_remote": article.publish_time_remote,
        "latest_metric": latest_metric,
        "analysis": analysis,
        "is_candidate": bool(latest_metric and int(latest_metric.get("read_count") or 0) >= 100000),
        "created_at": article.created_at.isoformat() if article.created_at else None,
        "updated_at": article.updated_at.isoformat() if article.updated_at else None,
    }


def serialize_snapshot(snapshot: WechatOfficialArticleSnapshot) -> dict[str, Any]:
    raw = snapshot.raw_json or {}
    return {"id": snapshot.id, "article_id": snapshot.article_id, "status": snapshot.status, "text": snapshot.text, "comment_id": raw.get("comment_id", "")}


def serialize_metric(metric: WechatOfficialArticleMetric) -> dict[str, Any]:
    return {
        "id": metric.id,
        "article_id": metric.article_id,
        "read_count": metric.read_count,
        "like_count": metric.like_count,
        "wow_count": metric.wow_count,
        "share_count": metric.share_count,
        "comment_count": metric.comment_count,
        "captured_at": metric.captured_at.isoformat() if metric.captured_at else None,
    }

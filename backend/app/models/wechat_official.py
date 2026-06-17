from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base
from backend.app.core.time import shanghai_now


class WechatOfficialCrawlAccount(Base):
    __tablename__ = "wechat_official_crawl_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    biz: Mapped[str] = mapped_column(String(128), index=True, default="")
    fake_id: Mapped[str] = mapped_column(String(128), index=True, default="")
    alias: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(32), index=True, default="active")
    raw_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now, onupdate=shanghai_now)


class WechatOfficialBackendSession(Base):
    __tablename__ = "wechat_official_backend_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("wechat_official_crawl_accounts.id"), index=True)
    encrypted_cookie: Mapped[str] = mapped_column(Text, default="")
    encrypted_token: Mapped[str] = mapped_column(Text, default="")
    user_agent: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), index=True, default="active")
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    raw_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now, onupdate=shanghai_now)


class WechatOfficialArticleCredential(Base):
    __tablename__ = "wechat_official_article_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("wechat_official_crawl_accounts.id"), index=True)
    article_url: Mapped[str] = mapped_column(Text, default="")
    encrypted_cookie: Mapped[str] = mapped_column(Text, default="")
    encrypted_token: Mapped[str] = mapped_column(Text, default="")
    encrypted_key: Mapped[str] = mapped_column(Text, default="")
    valid: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    raw_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now, onupdate=shanghai_now)


class WechatOfficialProxyNode(Base):
    __tablename__ = "wechat_official_proxy_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    endpoint: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(32), index=True, default="active")
    last_error: Mapped[str] = mapped_column(Text, default="")
    raw_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now, onupdate=shanghai_now)


class WechatOfficialCrawlJob(Base):
    __tablename__ = "wechat_official_crawl_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("wechat_official_crawl_accounts.id"), nullable=True, index=True)
    proxy_node_id: Mapped[Optional[int]] = mapped_column(ForeignKey("wechat_official_proxy_nodes.id"), nullable=True, index=True)
    keyword: Mapped[str] = mapped_column(String(256), default="")
    status: Mapped[str] = mapped_column(String(32), index=True, default="pending")
    source: Mapped[str] = mapped_column(String(32), index=True, default="backend")
    requested_limit: Mapped[int] = mapped_column(Integer, default=0)
    fetched_count: Mapped[int] = mapped_column(Integer, default=0)
    saved_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, default="")
    params_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now, onupdate=shanghai_now)


class WechatOfficialArticle(Base):
    __tablename__ = "wechat_official_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("wechat_official_crawl_accounts.id"), nullable=True, index=True)
    job_id: Mapped[Optional[int]] = mapped_column(ForeignKey("wechat_official_crawl_jobs.id"), nullable=True, index=True)
    article_url: Mapped[str] = mapped_column(Text, default="")
    title: Mapped[str] = mapped_column(String(512), default="")
    digest: Mapped[str] = mapped_column(Text, default="")
    author_name: Mapped[str] = mapped_column(String(128), default="")
    source: Mapped[str] = mapped_column(String(32), index=True, default="crawl")
    publish_time_remote: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    cover_url: Mapped[str] = mapped_column(Text, default="")
    content_url: Mapped[str] = mapped_column(Text, default="")
    raw_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now, onupdate=shanghai_now)


class WechatOfficialArticleSnapshot(Base):
    __tablename__ = "wechat_official_article_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("wechat_official_articles.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True, default="captured")
    html: Mapped[str] = mapped_column(Text, default="")
    text: Mapped[str] = mapped_column(Text, default="")
    images_json: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    raw_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now)


class WechatOfficialArticleMetric(Base):
    __tablename__ = "wechat_official_article_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("wechat_official_articles.id"), index=True)
    read_count: Mapped[int] = mapped_column(Integer, default=0)
    like_count: Mapped[int] = mapped_column(Integer, default=0)
    wow_count: Mapped[int] = mapped_column(Integer, default=0)
    share_count: Mapped[int] = mapped_column(Integer, default=0)
    comment_count: Mapped[int] = mapped_column(Integer, default=0)
    raw_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now)


class WechatOfficialArticleComment(Base):
    __tablename__ = "wechat_official_article_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("wechat_official_articles.id"), index=True)
    comment_id: Mapped[str] = mapped_column(String(128), index=True)
    user_name: Mapped[str] = mapped_column(String(128), default="")
    user_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    content: Mapped[str] = mapped_column(Text, default="")
    like_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at_remote: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    raw_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now)


class WechatOfficialArticleCommentReply(Base):
    __tablename__ = "wechat_official_article_comment_replies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    comment_id: Mapped[int] = mapped_column(ForeignKey("wechat_official_article_comments.id"), index=True)
    reply_id: Mapped[str] = mapped_column(String(128), index=True)
    user_name: Mapped[str] = mapped_column(String(128), default="")
    user_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    content: Mapped[str] = mapped_column(Text, default="")
    like_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at_remote: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    raw_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now)


class WechatOfficialIngestError(Base):
    __tablename__ = "wechat_official_ingest_errors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[Optional[int]] = mapped_column(ForeignKey("wechat_official_crawl_jobs.id"), nullable=True, index=True)
    account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("wechat_official_crawl_accounts.id"), nullable=True, index=True)
    article_id: Mapped[Optional[int]] = mapped_column(ForeignKey("wechat_official_articles.id"), nullable=True, index=True)
    stage: Mapped[str] = mapped_column(String(64), default="")
    message: Mapped[str] = mapped_column(Text, default="")
    raw_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now)


class WechatOfficialRedfoxConfig(Base):
    __tablename__ = "wechat_official_redfox_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(128), default="RedFoxHub")
    base_url: Mapped[str] = mapped_column(Text, default="https://redfox.hk")
    encrypted_api_key: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), index=True, default="unknown")
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    raw_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now, onupdate=shanghai_now)


class WechatOfficialDraftSource(Base):
    __tablename__ = "wechat_official_draft_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("ai_drafts.id"), index=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("wechat_official_articles.id"), index=True)
    source_type: Mapped[str] = mapped_column(String(32), default="rewrite")
    raw_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now)

from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import Base
from backend.app.models import (
    WechatOfficialArticle,
    WechatOfficialArticleSnapshot,
    WechatOfficialContentLibraryTombstone,
    WechatOfficialCrawlAccount,
    WechatOfficialCrawlJob,
)
from backend.app.services.wechat_official_ingestion_service import WechatOfficialIngestionService


def _session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'wechat-official-ingestion-test.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def test_ingestion_saves_article_and_snapshot_without_sensitive_provider_payload(tmp_path) -> None:
    SessionLocal = _session_factory(tmp_path)

    with SessionLocal() as db:
        result = WechatOfficialIngestionService(db).ingest_articles(
            user_id=7,
            provider="redfox",
            source_label="redfox_keyword",
            keyword="私域增长",
            requested_limit=1,
            fetched_count=1,
            articles=[
                {
                    "article_url": "https://mp.weixin.qq.com/s/ingestion-valid",
                    "title": "统一吸收服务样例",
                    "digest": "摘要",
                    "author_name": "增长研究所",
                    "publish_time_remote": "2026-06-25 10:00:00",
                    "cover_url": "https://example.com/cover.jpg",
                    "content_text": "正文内容",
                    "content_html": "<p>正文内容</p>",
                    "images": [{"url": "https://example.com/cover.jpg", "type": "cover"}],
                    "raw": {"api_key": "redfox-secret-key", "token": "provider-token", "safe": "visible"},
                }
            ],
            params={"api_key": "redfox-secret-key", "keyword": "私域增长"},
        )

        assert result["summary"] == {"fetched": 1, "saved": 1, "skipped": 0}

        job = db.scalar(select(WechatOfficialCrawlJob))
        assert job is not None
        assert job.source == "redfox"
        assert job.keyword == "私域增长"
        assert job.requested_limit == 1
        assert job.fetched_count == 1
        assert job.saved_count == 1
        assert job.status == "succeeded"
        persisted_job_text = str(job.params_json) + job.error_message
        assert "redfox-secret-key" not in persisted_job_text
        assert job.params_json["api_key"] == "[REDACTED]"

        account = db.scalar(select(WechatOfficialCrawlAccount))
        assert account is not None
        assert account.user_id == 7
        assert account.name == "增长研究所"

        article = db.scalar(select(WechatOfficialArticle))
        assert article is not None
        assert article.account_id == account.id
        assert article.job_id == job.id
        assert article.article_url == "https://mp.weixin.qq.com/s/ingestion-valid"
        assert article.title == "统一吸收服务样例"
        assert article.source == "redfox"
        persisted_article_text = str(article.raw_json)
        assert "redfox-secret-key" not in persisted_article_text
        assert "provider-token" not in persisted_article_text
        assert "visible" in persisted_article_text

        snapshot = db.scalar(select(WechatOfficialArticleSnapshot))
        assert snapshot is not None
        assert snapshot.article_id == article.id
        assert snapshot.status == "captured"
        assert snapshot.text == "正文内容"
        assert snapshot.html == "<p>正文内容</p>"
        assert snapshot.images_json == [{"url": "https://example.com/cover.jpg", "type": "cover"}]


def test_ingestion_skips_shell_and_tombstoned_articles(tmp_path) -> None:
    SessionLocal = _session_factory(tmp_path)

    with SessionLocal() as db:
        db.add(
            WechatOfficialContentLibraryTombstone(
                user_id=9,
                article_url="https://mp.weixin.qq.com/s/deleted",
                article_title="已删除文章",
            )
        )
        db.commit()

        result = WechatOfficialIngestionService(db).ingest_articles(
            user_id=9,
            provider="redfox",
            source_label="redfox_keyword",
            keyword="浴缸",
            requested_limit=3,
            fetched_count=3,
            articles=[
                {"article_url": "", "title": "缺少 URL 的空壳", "content_text": "正文"},
                {"article_url": "https://mp.weixin.qq.com/s/no-title", "title": "", "content_text": "正文"},
                {"article_url": "https://mp.weixin.qq.com/s/deleted", "title": "已删除文章", "content_text": "正文"},
            ],
        )

        assert result["summary"] == {"fetched": 3, "saved": 0, "skipped": 3}
        job = db.scalar(select(WechatOfficialCrawlJob))
        assert job is not None
        assert job.saved_count == 0
        assert job.status == "succeeded"
        assert db.scalars(select(WechatOfficialArticle)).all() == []
        assert db.scalars(select(WechatOfficialArticleSnapshot)).all() == []

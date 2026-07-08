from __future__ import annotations

import ast
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.database import Base


EXPECTED_TABLES = {
    "wechat_official_crawl_accounts",
    "wechat_official_backend_sessions",
    "wechat_official_article_credentials",
    "wechat_official_proxy_nodes",
    "wechat_official_crawl_jobs",
    "wechat_official_articles",
    "wechat_official_article_snapshots",
    "wechat_official_article_metrics",
    "wechat_official_article_comments",
    "wechat_official_article_comment_replies",
    "wechat_official_ingest_errors",
    "wechat_official_draft_sources",
    "wechat_official_redfox_configs",
}


SENSITIVE_FIELD_EXPECTATIONS = {
    "WechatOfficialBackendSession": {"encrypted_cookie", "encrypted_token"},
    "WechatOfficialArticleCredential": {"encrypted_cookie", "encrypted_token", "encrypted_key"},
    "WechatOfficialRedfoxConfig": {"encrypted_api_key"},
}


def _wechat_models():
    from backend.app.models import (
        WechatOfficialArticle,
        WechatOfficialArticleComment,
        WechatOfficialArticleCommentReply,
        WechatOfficialArticleCredential,
        WechatOfficialArticleMetric,
        WechatOfficialArticleSnapshot,
        WechatOfficialBackendSession,
        WechatOfficialCrawlAccount,
        WechatOfficialCrawlJob,
        WechatOfficialDraftSource,
        WechatOfficialIngestError,
        WechatOfficialProxyNode,
        WechatOfficialRedfoxConfig,
    )

    return {
        "WechatOfficialArticle": WechatOfficialArticle,
        "WechatOfficialArticleComment": WechatOfficialArticleComment,
        "WechatOfficialArticleCommentReply": WechatOfficialArticleCommentReply,
        "WechatOfficialArticleCredential": WechatOfficialArticleCredential,
        "WechatOfficialArticleMetric": WechatOfficialArticleMetric,
        "WechatOfficialArticleSnapshot": WechatOfficialArticleSnapshot,
        "WechatOfficialBackendSession": WechatOfficialBackendSession,
        "WechatOfficialCrawlAccount": WechatOfficialCrawlAccount,
        "WechatOfficialCrawlJob": WechatOfficialCrawlJob,
        "WechatOfficialDraftSource": WechatOfficialDraftSource,
        "WechatOfficialIngestError": WechatOfficialIngestError,
        "WechatOfficialProxyNode": WechatOfficialProxyNode,
        "WechatOfficialRedfoxConfig": WechatOfficialRedfoxConfig,
    }


def test_wechat_official_models_register_all_tables_in_metadata():
    _wechat_models()

    assert EXPECTED_TABLES.issubset(Base.metadata.tables.keys())


def test_wechat_official_alembic_migration_creates_all_tables_and_encrypted_fields():
    versions_dir = PROJECT_ROOT / "backend" / "alembic" / "versions"
    migration_texts = [path.read_text(encoding="utf-8") for path in versions_dir.glob("*.py")]
    migration_text = "\n".join(migration_texts)

    for table_name in EXPECTED_TABLES:
        assert f"'{table_name}'" in migration_text
    for encrypted_column in {"encrypted_cookie", "encrypted_token", "encrypted_key", "encrypted_api_key"}:
        assert f"'{encrypted_column}'" in migration_text
    for plaintext_sensitive_column in {"'cookie'", "'token'", "'key'"}:
        assert plaintext_sensitive_column not in migration_text


def test_wechat_official_alembic_revision_is_single_head():
    versions_dir = PROJECT_ROOT / "backend" / "alembic" / "versions"
    revisions: dict[str, str | tuple[str, ...] | None] = {}

    for path in versions_dir.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        revision = None
        down_revision = None
        for node in tree.body:
            if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
                continue
            if node.target.id == "revision" and isinstance(node.value, ast.Constant):
                revision = node.value.value
            elif node.target.id == "down_revision":
                if isinstance(node.value, ast.Constant):
                    down_revision = node.value.value
                elif isinstance(node.value, (ast.List, ast.Tuple)):
                    down_revision = tuple(
                        element.value for element in node.value.elts if isinstance(element, ast.Constant)
                    )
        assert revision is not None, f"missing revision in {path.name}"
        revisions[revision] = down_revision

    referenced_revisions: set[str] = set()
    for down_revision in revisions.values():
        if down_revision is None:
            continue
        if isinstance(down_revision, tuple):
            referenced_revisions.update(down_revision)
        else:
            referenced_revisions.add(down_revision)

    heads = set(revisions) - referenced_revisions
    assert heads == {"20260708_note_analysis_cover_title"}


def test_wechat_official_models_insert_related_crawl_data_and_defaults():
    models = _wechat_models()
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        user = __import__("backend.app.models", fromlist=["User"]).User(
            username="wechat-operator",
            password_hash="not-a-secret-sample",
        )
        draft = __import__("backend.app.models", fromlist=["AiDraft"]).AiDraft(
            user_id=1,
            platform="wechat_official",
            title="Draft from article",
            body="Draft body",
        )
        session.add(user)
        session.flush()
        draft.user_id = user.id
        session.add(draft)
        session.flush()

        account = models["WechatOfficialCrawlAccount"](
            user_id=user.id,
            name="Official Account",
            biz="MzTestBiz",
            fake_id="fake-id-1",
        )
        proxy = models["WechatOfficialProxyNode"](
            name="local-proxy",
            endpoint="http://127.0.0.1:8080",
        )
        session.add_all([account, proxy])
        session.flush()

        backend_session = models["WechatOfficialBackendSession"](
            account_id=account.id,
            encrypted_cookie="encrypted-cookie-value",
            encrypted_token="encrypted-token-value",
        )
        credential = models["WechatOfficialArticleCredential"](
            account_id=account.id,
            article_url="https://mp.weixin.qq.com/s/test",
            encrypted_cookie="encrypted-cookie-value",
            encrypted_token="encrypted-token-value",
            encrypted_key="encrypted-key-value",
        )
        job = models["WechatOfficialCrawlJob"](
            account_id=account.id,
            proxy_node_id=proxy.id,
            keyword="运营",
        )
        article = models["WechatOfficialArticle"](
            account_id=account.id,
            job_id=job.id,
            article_url="https://mp.weixin.qq.com/s/test",
            title="Article title",
            author_name="Author",
        )
        session.add_all([backend_session, credential, job, article])
        session.flush()

        snapshot = models["WechatOfficialArticleSnapshot"](
            article_id=article.id,
            html="<p>body</p>",
            text="body",
        )
        metric = models["WechatOfficialArticleMetric"](
            article_id=article.id,
            read_count=10,
            like_count=2,
        )
        comment = models["WechatOfficialArticleComment"](
            article_id=article.id,
            comment_id="comment-1",
            user_name="reader",
            content="comment body",
        )
        ingest_error = models["WechatOfficialIngestError"](
            job_id=job.id,
            account_id=account.id,
            article_id=article.id,
            stage="snapshot",
            message="transient parse error",
        )
        draft_source = models["WechatOfficialDraftSource"](
            draft_id=draft.id,
            article_id=article.id,
            source_type="rewrite",
        )
        redfox_config = models["WechatOfficialRedfoxConfig"](
            user_id=user.id,
            encrypted_api_key="encrypted-redfox-key-value",
        )
        session.add_all([snapshot, metric, comment, ingest_error, draft_source, redfox_config])
        session.flush()

        reply = models["WechatOfficialArticleCommentReply"](
            comment_id=comment.id,
            reply_id="reply-1",
            user_name="author",
            content="reply body",
        )
        session.add(reply)
        session.commit()

        assert proxy.enabled is True
        assert proxy.status == "active"
        assert job.status == "pending"
        assert article.source == "crawl"
        assert snapshot.status == "captured"
        assert credential.valid is True


def test_wechat_official_sensitive_fields_use_encrypted_column_names_only():
    models = _wechat_models()

    for model_name, expected_columns in SENSITIVE_FIELD_EXPECTATIONS.items():
        columns = {column.key for column in inspect(models[model_name]).columns}
        assert expected_columns.issubset(columns)
        assert "cookie" not in columns
        assert "token" not in columns
        assert "key" not in columns

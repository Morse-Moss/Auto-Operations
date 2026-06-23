from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models import (
    AiDraft,
    FeishuIntegrationConfig,
    WechatOfficialArticle,
    WechatOfficialArticleComment,
    WechatOfficialArticleMetric,
    WechatOfficialArticleSnapshot,
    WechatOfficialBackendSession,
    WechatOfficialCrawlAccount,
    WechatOfficialRedfoxConfig,
)


def get_wechat_official_readiness(db: Session, *, user_id: int) -> dict[str, Any]:
    redfox = _redfox_status(db, user_id)
    sessions = _session_status(db, user_id)
    content = _content_status(db, user_id)
    feishu = _feishu_status(db, user_id)
    drafts = _draft_status(db, user_id)
    image_studio = {"available": True, "material_upload_blocked": True}
    safety = {
        "publish_blocked": True,
        "sendall_blocked": True,
        "preview_blocked": True,
        "material_upload_blocked": True,
        "message": "真实发布、预览发送、群发和公众号素材上传保持阻断。",
    }

    checks = [
        _check(
            "redfox.config",
            "Redfox 配置",
            "ready" if redfox["configured"] else "missing",
            "Redfox 已配置，可作为内容数据源。" if redfox["configured"] else "还没有配置 Redfox API Key。",
            "去 Redfox 设置配置 API Key" if not redfox["configured"] else "可继续采集公众号候选。",
        ),
        _check(
            "sessions.backend",
            "公众号后台会话",
            "ready" if sessions["valid"] > 0 else "missing",
            f"有效会话 {sessions['valid']} 个，过期/无效 {sessions['expired'] + sessions['invalid']} 个。",
            "去账号矩阵完成后台会话接入" if sessions["valid"] == 0 else "可用于需要后台会话的只读采集。",
        ),
        _check(
            "content.library",
            "公众号内容库",
            "ready" if content["total"] > 0 else "missing",
            f"内容库已有 {content['total']} 篇文章，{content['draft_ready']} 篇已进入草稿准备。",
            "先从爆文发现入库文章" if content["total"] == 0 else "可继续分析、飞书协作或生成草稿。",
        ),
        _check(
            "feishu.analysis",
            "飞书分析闭环",
            "ready" if feishu["configured"] and feishu["enabled"] else "partial" if feishu["configured"] else "missing",
            "飞书多维表格已启用。" if feishu["enabled"] else "飞书配置未启用或未完成。",
            "去设置页完成飞书配置" if not feishu["configured"] else "可从内容库推送/回拉飞书标注。",
        ),
        _check(
            "drafts.workbench",
            "草稿工坊",
            "ready" if drafts["count"] > 0 else "partial",
            f"已有 {drafts['count']} 个公众号草稿，dry-run 可用。",
            "从内容库生成公众号草稿" if drafts["count"] == 0 else "可继续编辑、复制、dry-run 和进入图片工坊。",
        ),
        _check(
            "image_studio.context",
            "图片工坊",
            "ready",
            "可从公众号草稿携带封面/正文图候选进入图片工坊。",
            "只做生成/整理/下载，不上传公众号素材。",
        ),
        _check(
            "safety.publish",
            "真实发布安全边界",
            "blocked",
            "真实发布、预览发送、群发和素材上传均保持阻断。",
            "需要真实发布能力时先做单独风险和 QA 设计。",
        ),
    ]
    next_actions = _next_actions(checks)
    overall_status = "blocked" if redfox["configured"] is False or content["total"] == 0 else "partial"
    if redfox["configured"] and content["total"] > 0 and drafts["count"] > 0 and feishu["enabled"]:
        overall_status = "ready"

    return {
        "summary": {
            "overall_status": overall_status,
            "next_actions": next_actions,
        },
        "checks": checks,
        "redfox": redfox,
        "sessions": sessions,
        "content": content,
        "feishu": feishu,
        "drafts": drafts,
        "image_studio": image_studio,
        "safety": safety,
    }


def _check(key: str, label: str, status: str, message: str, action: str) -> dict[str, str]:
    return {"key": key, "label": label, "status": status, "message": message, "action": action}


def _next_actions(checks: list[dict[str, str]]) -> list[str]:
    actions = [check["action"] for check in checks if check["status"] in {"missing", "partial"}]
    return actions[:4] if actions else ["继续内容分析、草稿生产和图片整理。"]


def _redfox_status(db: Session, user_id: int) -> dict[str, Any]:
    config = db.scalar(select(WechatOfficialRedfoxConfig).where(WechatOfficialRedfoxConfig.user_id == user_id))
    return {
        "configured": bool(config and config.encrypted_api_key),
        "status": config.status if config else "missing",
        "last_error": config.last_error if config else "",
        "last_checked_at": config.last_checked_at.isoformat() if config and config.last_checked_at else None,
    }


def _session_status(db: Session, user_id: int) -> dict[str, int]:
    rows = db.scalars(
        select(WechatOfficialBackendSession)
        .join(WechatOfficialCrawlAccount, WechatOfficialBackendSession.account_id == WechatOfficialCrawlAccount.id)
        .where(WechatOfficialCrawlAccount.user_id == user_id)
    ).all()
    counts = Counter(session.status for session in rows)
    invalid = sum(counts[status] for status in counts if status not in {"valid", "pending", "expired"})
    return {
        "valid": counts["valid"],
        "pending": counts["pending"],
        "expired": counts["expired"],
        "invalid": invalid,
        "total": len(rows),
    }


def _content_status(db: Session, user_id: int) -> dict[str, int]:
    articles = db.scalars(
        select(WechatOfficialArticle)
        .join(WechatOfficialCrawlAccount, WechatOfficialArticle.account_id == WechatOfficialCrawlAccount.id)
        .where(WechatOfficialCrawlAccount.user_id == user_id)
    ).all()
    article_ids = [article.id for article in articles]
    pool_counts: Counter[str] = Counter()
    cover_count = 0
    for article in articles:
        analysis = dict((article.raw_json or {}).get("analysis") or {})
        status = str(analysis.get("pool_status") or analysis.get("recommendation_status") or "candidate")
        pool_counts[status] += 1
        if article.cover_url:
            cover_count += 1

    snapshots = db.scalars(select(WechatOfficialArticleSnapshot).where(WechatOfficialArticleSnapshot.article_id.in_(article_ids))).all() if article_ids else []
    snapshot_image_count = 0
    for snapshot in snapshots:
        images = snapshot.images_json if isinstance(snapshot.images_json, list) else []
        snapshot_image_count += len(images)
    metrics_count = db.scalar(select(func.count(WechatOfficialArticleMetric.id)).where(WechatOfficialArticleMetric.article_id.in_(article_ids))) if article_ids else 0
    comments_count = db.scalar(select(func.count(WechatOfficialArticleComment.id)).where(WechatOfficialArticleComment.article_id.in_(article_ids))) if article_ids else 0

    return {
        "total": len(articles),
        "candidate": pool_counts["candidate"],
        "shortlisted": pool_counts["shortlisted"],
        "analyzing": pool_counts["analyzing"],
        "draft_ready": pool_counts["draft_ready"],
        "rejected": pool_counts["rejected"],
        "snapshots": len(snapshots),
        "images": cover_count + snapshot_image_count,
        "comments": comments_count,
        "metrics": metrics_count,
    }


def _feishu_status(db: Session, user_id: int) -> dict[str, Any]:
    config = db.scalar(select(FeishuIntegrationConfig).where(FeishuIntegrationConfig.user_id == user_id))
    return {
        "configured": bool(config and config.app_id and config.encrypted_app_secret and config.table_id),
        "enabled": bool(config and config.enabled),
        "last_test_status": config.last_test_status if config else None,
        "last_test_message": config.last_test_message if config else None,
    }


def _draft_status(db: Session, user_id: int) -> dict[str, Any]:
    drafts = db.scalars(select(AiDraft).where(AiDraft.user_id == user_id, AiDraft.platform == "wechat_official")).all()
    return {"count": len(drafts), "dry_run_available": True}

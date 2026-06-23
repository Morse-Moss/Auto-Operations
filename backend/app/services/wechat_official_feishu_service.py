from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from backend.app.core.time import shanghai_now
from backend.app.models import (
    WechatOfficialArticle,
    WechatOfficialArticleMetric,
    WechatOfficialCrawlAccount,
)
from backend.app.services.feishu_bitable_service import MAX_SYNC_ITEMS

WECHAT_OFFICIAL_SYSTEM_FIELD_NAMES = [
    "系统文章ID",
    "平台",
    "标题",
    "公众号/作者",
    "原文链接",
    "摘要",
    "阅读数",
    "点赞数",
    "在看数",
    "评论数",
    "入库状态",
    "推荐状态",
    "同步时间",
]

WECHAT_OFFICIAL_ANALYSIS_FIELD_NAMES = [
    "分析状态",
    "低粉证据",
    "低粉备注",
    "标题类型",
    "文章类型",
    "爆点因子",
    "核心洞察",
    "业务方向",
    "转化方法",
    "爆点拆解",
    "草稿模板",
    "分析更新时间",
]

WECHAT_OFFICIAL_FEISHU_FIELD_NAMES = WECHAT_OFFICIAL_SYSTEM_FIELD_NAMES + WECHAT_OFFICIAL_ANALYSIS_FIELD_NAMES


def push_wechat_official_articles_to_feishu_dry_run(db: Session, *, user_id: int, article_ids: list[int]) -> dict[str, Any]:
    unique_ids = _unique_ids(article_ids)
    if len(unique_ids) > MAX_SYNC_ITEMS:
        return {"dry_run": True, "updated_count": 0, "failed_count": len(unique_ids), "errors": [f"每次最多同步 {MAX_SYNC_ITEMS} 条"], "records": []}
    articles = _owned_articles_by_id(db, user_id=user_id, article_ids=unique_ids)
    records = []
    errors = []
    now = shanghai_now()
    for article_id in unique_ids:
        article = articles.get(article_id)
        if article is None:
            errors.append({"article_id": article_id, "error": "Article not found"})
            continue
        fields = article_to_feishu_fields(db, article, now=now)
        records.append({"article_id": article.id, "status": "dry_run", "fields": fields})
        _store_feishu_sync_meta(article, {"push_status": "dry_run", "last_pushed_at": now.isoformat()})
    db.commit()
    return {"dry_run": True, "updated_count": len(records), "failed_count": len(errors), "errors": errors, "records": records}


def push_wechat_official_articles_to_feishu(db: Session, *, user_id: int, article_ids: list[int], client: Any) -> dict[str, Any]:
    unique_ids = _unique_ids(article_ids)
    if len(unique_ids) > MAX_SYNC_ITEMS:
        return {"dry_run": False, "created_count": 0, "updated_count": 0, "failed_count": len(unique_ids), "errors": [f"每次最多同步 {MAX_SYNC_ITEMS} 条"], "records": []}
    articles = _owned_articles_by_id(db, user_id=user_id, article_ids=unique_ids)
    existing_records = client.list_records()
    by_system_id, by_url = _records_by_article_id_and_url(existing_records)
    created_count = 0
    updated_count = 0
    errors = []
    records = []
    now = shanghai_now()
    for article_id in unique_ids:
        article = articles.get(article_id)
        if article is None:
            errors.append({"article_id": article_id, "error": "Article not found"})
            continue
        raw = dict(article.raw_json or {})
        feishu_meta = raw.get("feishu") if isinstance(raw.get("feishu"), dict) else {}
        fields = article_to_feishu_fields(db, article, now=now)
        record_id = str(feishu_meta.get("record_id") or by_system_id.get(str(article.id)) or by_url.get(_article_url(article)) or "")
        try:
            if record_id:
                update_fields = {key: value for key, value in fields.items() if key not in WECHAT_OFFICIAL_ANALYSIS_FIELD_NAMES}
                record = client.update_record(record_id, update_fields)
                status = "updated"
                updated_count += 1
            else:
                record = client.create_record(fields)
                status = "created"
                created_count += 1
            saved_record_id = str(record.get("record_id") or record_id or "")
            _store_feishu_sync_meta(article, {"record_id": saved_record_id, "push_status": "synced", "last_pushed_at": now.isoformat(), "last_error": ""})
            records.append({"article_id": article.id, "status": status, "record_id": saved_record_id})
        except Exception as exc:
            _store_feishu_sync_meta(article, {"push_status": "failed", "last_error": str(exc)})
            errors.append({"article_id": article.id, "error": str(exc)})
    db.commit()
    return {"dry_run": False, "created_count": created_count, "updated_count": updated_count, "failed_count": len(errors), "errors": errors, "records": records}


def pull_wechat_official_feishu_analysis_records(db: Session, *, user_id: int, records: list[dict[str, Any]], article_ids: list[int] | None = None) -> dict[str, Any]:
    allowed_article_ids = set(_unique_ids(article_ids or []))
    updated = 0
    unmatched = 0
    errors = []
    now = shanghai_now()
    for record in records:
        fields = record.get("fields") if isinstance(record, dict) else None
        if not isinstance(fields, dict):
            errors.append({"error": "Invalid record fields"})
            continue
        article = _match_owned_article(db, user_id=user_id, fields=fields)
        if article is None or (allowed_article_ids and article.id not in allowed_article_ids):
            unmatched += 1
            continue
        try:
            analysis_patch = analysis_from_feishu_fields(fields, now=now)
            raw = dict(article.raw_json or {})
            analysis = dict(raw.get("analysis") or {})
            analysis.update({key: value for key, value in analysis_patch.items() if value is not None})
            raw["analysis"] = analysis
            feishu = dict(raw.get("feishu") or {})
            record_id = str(record.get("record_id") or feishu.get("record_id") or "")
            if record_id:
                feishu["record_id"] = record_id
            feishu["pull_status"] = "success"
            feishu["last_pulled_at"] = now.isoformat()
            feishu["last_error"] = ""
            raw["feishu"] = feishu
            article.raw_json = raw
            flag_modified(article, "raw_json")
            updated += 1
        except Exception as exc:
            errors.append({"article_id": article.id, "error": str(exc)})
    db.commit()
    return {"updated_count": updated, "unmatched_count": unmatched, "failed_count": len(errors), "errors": errors}


def pull_wechat_official_feishu_analysis_records_from_client(db: Session, *, user_id: int, client: Any, article_ids: list[int] | None = None) -> dict[str, Any]:
    if article_ids and len(_unique_ids(article_ids)) > MAX_SYNC_ITEMS:
        return {"updated_count": 0, "unmatched_count": 0, "failed_count": len(article_ids), "errors": [f"每次最多回传 {MAX_SYNC_ITEMS} 条"]}
    return pull_wechat_official_feishu_analysis_records(db, user_id=user_id, records=client.list_records(), article_ids=article_ids)


def article_to_feishu_fields(db: Session, article: WechatOfficialArticle, *, now=None) -> dict[str, Any]:
    now = now or shanghai_now()
    analysis = dict((article.raw_json or {}).get("analysis") or {})
    metric = _latest_metric(db, article.id)
    hotspot = analysis.get("hotspot_breakdown") if isinstance(analysis.get("hotspot_breakdown"), dict) else {}
    return {
        "系统文章ID": str(article.id),
        "平台": "公众号",
        "标题": article.title,
        "公众号/作者": _article_author(db, article),
        "原文链接": _article_url(article),
        "摘要": article.digest,
        "阅读数": str(metric.read_count if metric else 0),
        "点赞数": str(metric.like_count if metric else 0),
        "在看数": str(metric.wow_count if metric else 0),
        "评论数": str(metric.comment_count if metric else 0),
        "入库状态": str(analysis.get("pool_status") or "candidate"),
        "推荐状态": str(analysis.get("recommendation_status") or ""),
        "同步时间": now.isoformat(),
        "分析状态": str(analysis.get("analysis_status") or "待分析"),
        "低粉证据": _as_text(analysis.get("low_follower_evidence")),
        "低粉备注": _as_text(analysis.get("low_follower_note")),
        "标题类型": _as_text(analysis.get("title_type")),
        "文章类型": _as_text(analysis.get("article_type_label")),
        "爆点因子": _as_text(analysis.get("viral_factors")),
        "核心洞察": _as_text(analysis.get("core_insight")),
        "业务方向": _as_text(analysis.get("business_direction")),
        "转化方法": _as_text(analysis.get("customer_conversion_method")),
        "爆点拆解": _hotspot_to_text(hotspot),
        "草稿模板": _as_text(analysis.get("draft_template_key")),
        "分析更新时间": _as_text(analysis.get("analysis_updated_at")),
    }


def analysis_from_feishu_fields(fields: dict[str, Any], *, now=None) -> dict[str, Any]:
    now = now or shanghai_now()
    patch: dict[str, Any] = {
        "analysis_status": _as_text(fields.get("分析状态")) or None,
        "pool_status": _as_text(fields.get("入库状态")) or None,
        "recommendation_status": _as_text(fields.get("推荐状态")) or None,
        "low_follower_note": _as_text(fields.get("低粉备注")) or None,
        "title_type": _as_text(fields.get("标题类型")) or None,
        "article_type_label": _as_text(fields.get("文章类型")) or None,
        "viral_factors": _as_text_list(fields.get("爆点因子")) or None,
        "core_insight": _as_text(fields.get("核心洞察")) or None,
        "business_direction": _as_text(fields.get("业务方向")) or None,
        "customer_conversion_method": _as_text(fields.get("转化方法")) or None,
        "draft_template_key": _as_text(fields.get("草稿模板")) or None,
        "analysis_mode": "feishu",
        "analysis_updated_at": now.isoformat(),
    }
    low_follower = fields.get("低粉证据")
    if low_follower is not None:
        patch["low_follower_evidence"] = _parse_bool_or_text(low_follower)
    hotspot = _parse_hotspot(fields.get("爆点拆解"))
    if hotspot:
        patch["hotspot_breakdown"] = hotspot
    return patch


def _owned_articles_by_id(db: Session, *, user_id: int, article_ids: list[int]) -> dict[int, WechatOfficialArticle]:
    if not article_ids:
        return {}
    rows = db.scalars(
        select(WechatOfficialArticle)
        .join(WechatOfficialCrawlAccount, WechatOfficialArticle.account_id == WechatOfficialCrawlAccount.id)
        .where(WechatOfficialArticle.id.in_(article_ids), WechatOfficialCrawlAccount.user_id == user_id)
    ).all()
    return {article.id: article for article in rows}


def _match_owned_article(db: Session, *, user_id: int, fields: dict[str, Any]) -> WechatOfficialArticle | None:
    raw_article_id = fields.get("系统文章ID")
    try:
        article_id = int(str(raw_article_id))
    except Exception:
        article_id = 0
    statement = (
        select(WechatOfficialArticle)
        .join(WechatOfficialCrawlAccount, WechatOfficialArticle.account_id == WechatOfficialCrawlAccount.id)
        .where(WechatOfficialCrawlAccount.user_id == user_id)
    )
    if article_id > 0:
        return db.scalar(statement.where(WechatOfficialArticle.id == article_id))
    url = _as_text(fields.get("原文链接"))
    if url:
        return db.scalar(statement.where((WechatOfficialArticle.article_url == url) | (WechatOfficialArticle.content_url == url)))
    return None


def _latest_metric(db: Session, article_id: int) -> WechatOfficialArticleMetric | None:
    return db.scalar(
        select(WechatOfficialArticleMetric)
        .where(WechatOfficialArticleMetric.article_id == article_id)
        .order_by(WechatOfficialArticleMetric.captured_at.desc(), WechatOfficialArticleMetric.id.desc())
    )


def _records_by_article_id_and_url(records: list[dict[str, Any]]) -> tuple[dict[str, str], dict[str, str]]:
    by_system_id: dict[str, str] = {}
    by_url: dict[str, str] = {}
    for record in records:
        record_id = str(record.get("record_id") or "")
        fields = record.get("fields") if isinstance(record.get("fields"), dict) else {}
        if not record_id:
            continue
        system_id = fields.get("系统文章ID")
        url = fields.get("原文链接")
        if system_id:
            by_system_id[str(system_id)] = record_id
        if url:
            by_url[str(url)] = record_id
    return by_system_id, by_url


def _store_feishu_sync_meta(article: WechatOfficialArticle, patch: dict[str, Any]) -> None:
    raw = dict(article.raw_json or {})
    feishu = dict(raw.get("feishu") or {})
    feishu.update({key: value for key, value in patch.items() if value is not None})
    raw["feishu"] = feishu
    article.raw_json = raw
    flag_modified(article, "raw_json")


def _unique_ids(ids: list[int]) -> list[int]:
    return list(dict.fromkeys(int(item) for item in ids))


def _article_url(article: WechatOfficialArticle) -> str:
    return str(article.article_url or article.content_url or "")


def _article_author(db: Session, article: WechatOfficialArticle) -> str:
    if article.author_name:
        return article.author_name
    account = db.get(WechatOfficialCrawlAccount, article.account_id) if article.account_id else None
    return account.name if account else ""


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, list):
        return "、".join(str(item) for item in value if str(item).strip())
    if isinstance(value, dict):
        return "\n".join(f"{key}: {item}" for key, item in value.items() if str(item).strip())
    return str(value).strip()


def _as_text_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[,，、\n]", value) if item.strip()]
    return []


def _hotspot_to_text(value: dict[str, Any]) -> str:
    return "\n".join(f"{key}: {item}" for key, item in value.items() if str(item).strip())


def _parse_hotspot(value: Any) -> dict[str, str]:
    text = _as_text(value)
    if not text:
        return {}
    parsed: dict[str, str] = {}
    for line in text.splitlines():
        if ":" in line:
            key, item = line.split(":", 1)
        elif "：" in line:
            key, item = line.split("：", 1)
        else:
            continue
        key = key.strip()
        item = item.strip()
        if key and item:
            parsed[key] = item
    return parsed or {"note": text}


def _parse_bool_or_text(value: Any) -> Any:
    text = _as_text(value).lower()
    if text in {"是", "true", "1", "yes", "有", "已有证据"}:
        return True
    if text in {"否", "false", "0", "no", "无", "无证据"}:
        return False
    return _as_text(value) or None

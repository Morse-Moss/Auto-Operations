from __future__ import annotations

import base64
import csv
import hashlib
import hmac
import io
import json
import time
from pathlib import Path
from typing import Any, Literal, Optional
from urllib.parse import urlparse, urlunparse
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from backend.app.api.platforms.xhs.pc import (
    _cookies_to_string,
    get_xhs_pc_api_adapter_factory,
)
from backend.app.adapters.xhs.mappers import XhsContentMapping, map_xhs_content, normalize_xhs_comment_payload
from backend.app.core.config import get_settings
from backend.app.core.database import get_db
from backend.app.core.deps import get_current_tenant_context, get_current_user
from backend.app.core.time import shanghai_now
from backend.app.core.security import decrypt_text
from backend.app.models import AccountCookieVersion, AiDraft, Note, NoteAnalysisResult, NoteAsset, NoteComment, NoteExclusion, PlatformAccount, Tag, User, note_tags
from backend.app.schemas.common import paginated
from backend.app.services.asset_storage_policy import create_signed_media_url, export_owner_prefix, validate_owned_media_reference
from backend.app.services.feishu_bitable_service import get_or_create_analysis_result
from backend.app.services.note_analysis_service import analyze_note_system
from backend.app.services.note_exclusion_service import build_current_cleanup_candidates, mark_notes_excluded
from backend.app.services.usage_quota_service import CREDITS_BUCKET, UsageQuotaService, credit_cost_for_feature, usage_idempotency_key
from backend.app.services import huitun_live_note_source
from backend.app.services.platform_data_account_service import get_platform_data_account_cookie_text
from backend.app.services.xhs_source_image_extractor import (
    XhsSourceImageExtractionError,
    canonical_xhs_image_key,
    fetch_xhs_note_image_urls,
    is_xhs_note_image_url,
)

router = APIRouter(prefix="/notes", tags=["notes"])
SOURCE_IMAGE_IMPORT_TOKEN_TTL_SECONDS = 15 * 60
NOTE_SYSTEM_ANALYSIS_FEATURE_KEY = "note.system_analysis"


class BatchSaveNoteItem(BaseModel):
    note_id: str = Field(min_length=1, max_length=128)
    note_url: str = ""
    title: str = ""
    content: str = ""
    author_name: str = ""
    cover_url: str = ""
    video_url: str = ""
    video_addr: str = ""
    image_urls: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class BatchSaveNotesRequest(BaseModel):
    account_id: int
    fetch_comments: bool = False
    notes: list[BatchSaveNoteItem] = Field(min_length=1)


class BatchTagNotesRequest(BaseModel):
    note_ids: list[int] = Field(min_length=1)
    tag_ids: list[int] = Field(default_factory=list)
    mode: Literal["replace", "add", "remove"] = "replace"


class BatchCreateDraftsRequest(BaseModel):
    note_ids: list[int] = Field(min_length=1)
    intent: str = Field(default="rewrite", max_length=32)


class ExportNotesRequest(BaseModel):
    note_ids: list[int] = Field(min_length=1)
    format: Literal["json", "csv"] = "json"


class MarkNoteExclusionsRequest(BaseModel):
    note_ids: list[int] = Field(min_length=1)
    reason_code: str = Field(min_length=1, max_length=64)
    reason_text: str = ""
    sync_feishu: bool = False


def _serialize_tag(tag: Tag) -> dict:
    return {
        "id": tag.id,
        "name": tag.name,
        "color": tag.color,
    }


def _get_note_tags(db: Session, note_id: int) -> list[dict]:
    tags = db.scalars(
        select(Tag)
        .join(note_tags, Tag.id == note_tags.c.tag_id)
        .where(note_tags.c.note_id == note_id)
        .order_by(Tag.id.asc())
    ).all()
    return [_serialize_tag(tag) for tag in tags]


def _get_note_assets(db: Session, note: Note) -> list[NoteAsset]:
    return db.scalars(select(NoteAsset).where(NoteAsset.note_id == note.id).order_by(NoteAsset.sort_order.asc(), NoteAsset.id.asc())).all()


def _asset_display_url(asset: NoteAsset, user_id: int | None = None) -> str:
    if asset.local_path:
        if user_id is not None:
            try:
                return create_signed_media_url(asset.local_path, user_id)
            except ValueError:
                return ""
        return f"/api/files/media/{asset.local_path}"
    return asset.url


def _as_int(value: Any) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        cleaned = value.strip().lower().replace(",", "")
        multiplier = 1
        if cleaned.endswith("w"):
            multiplier = 10000
            cleaned = cleaned[:-1]
        try:
            return int(float(cleaned) * multiplier)
        except ValueError:
            return 0
    return 0


def _xhs_content_mapping(note: Note, mapping_cache: dict[int, XhsContentMapping | None] | None = None) -> XhsContentMapping | None:
    if mapping_cache is not None and note.id in mapping_cache:
        return mapping_cache[note.id]
    mapping: XhsContentMapping | None = None
    if note.platform == "xhs":
        raw = note.raw_json if isinstance(note.raw_json, dict) else {}
        mapping = map_xhs_content(note.note_id, raw)
    if mapping_cache is not None:
        mapping_cache[note.id] = mapping
    return mapping


def _legacy_note_engagement_metrics(note: Note) -> dict[str, int]:
    raw = note.raw_json if isinstance(note.raw_json, dict) else {}
    likes = _as_int(raw.get("liked_count") or raw.get("likes") or raw.get("like_count"))
    collects = _as_int(raw.get("collected_count") or raw.get("collects") or raw.get("collect_count"))
    comments = _as_int(raw.get("comment_count") or raw.get("comments"))
    shares = _as_int(raw.get("share_count") or raw.get("shares"))
    if likes or collects or comments or shares:
        return {"likes": likes, "collects": collects, "comments": comments, "shares": shares}

    data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
    items = data.get("items") if isinstance(data.get("items"), list) else []
    item = items[0] if items and isinstance(items[0], dict) else {}
    card = item.get("note_card") if isinstance(item.get("note_card"), dict) else {}
    info = card.get("interact_info") if isinstance(card.get("interact_info"), dict) else {}
    return {
        "likes": _as_int(info.get("liked_count")),
        "collects": _as_int(info.get("collected_count")),
        "comments": _as_int(info.get("comment_count")),
        "shares": _as_int(info.get("share_count")),
    }


def _note_engagement_metrics(note: Note, mapping_cache: dict[int, XhsContentMapping | None] | None = None) -> dict[str, int]:
    mapping = _xhs_content_mapping(note, mapping_cache)
    if mapping is not None:
        return {
            "likes": mapping.engagement_metrics["likes"],
            "collects": mapping.engagement_metrics["collects"],
            "comments": mapping.engagement_metrics["comments"],
            "shares": mapping.engagement_metrics["shares"],
        }
    return _legacy_note_engagement_metrics(note)


def _is_video_type(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return int(value) == 1
    text = str(value).strip().lower()
    return text == "1" or "video" in text or "视频" in text


def _note_media_type(*, mapping: XhsContentMapping | None, video_assets: list[NoteAsset], response_video_url: str) -> str:
    if video_assets or response_video_url:
        return "video"
    if mapping is not None and _is_video_type(mapping.note_type):
        return "video"
    return "image"


def _note_metric(note: Note, sort_by: str, mapping_cache: dict[int, XhsContentMapping | None] | None = None) -> int:
    metrics = _note_engagement_metrics(note, mapping_cache)
    if sort_by == "likes":
        return metrics["likes"]
    if sort_by == "comments":
        return metrics["comments"]
    if sort_by == "collects":
        return metrics["collects"]
    if sort_by == "engagement":
        return metrics["likes"] + metrics["collects"] + metrics["comments"] + metrics["shares"]
    return 0


def _top_note_ids(
    notes: list[Note],
    sort_by: str,
    limit: int = 20,
    mapping_cache: dict[int, XhsContentMapping | None] | None = None,
) -> set[int]:
    ranked = sorted(notes, key=lambda note: (_note_metric(note, sort_by, mapping_cache), note.created_at, note.id), reverse=True)
    return {note.id for note in ranked[:limit] if _note_metric(note, sort_by, mapping_cache) > 0}


def _top20_marks(notes: list[Note], mapping_cache: dict[int, XhsContentMapping | None] | None = None) -> dict[int, list[str]]:
    labels = {"likes": "点赞TOP20", "comments": "评论TOP20", "collects": "收藏TOP20"}
    marks: dict[int, list[str]] = {note.id: [] for note in notes}
    for metric, label in labels.items():
        for note_id in _top_note_ids(notes, metric, mapping_cache=mapping_cache):
            marks.setdefault(note_id, []).append(label)
    return marks


def _get_feishu_analysis_result(db: Session, note_id: int) -> NoteAnalysisResult | None:
    return db.scalar(
        select(NoteAnalysisResult).where(
            NoteAnalysisResult.note_id == note_id,
            NoteAnalysisResult.source == "feishu",
        )
    )


def _get_effective_analysis_result(db: Session, note_id: int) -> NoteAnalysisResult | None:
    return db.scalar(
        select(NoteAnalysisResult)
        .where(
            NoteAnalysisResult.note_id == note_id,
            NoteAnalysisResult.source.in_(["system", "feishu"]),
        )
        .order_by(NoteAnalysisResult.source.desc())
    )


def _payload_value(payload: Any, *keys: str) -> Any:
    if not isinstance(payload, dict):
        return None
    for key in keys:
        value = payload.get(key)
        if value:
            return value
    return None


def _serialize_analysis_result(result: NoteAnalysisResult | None) -> dict | None:
    if result is None:
        return None
    return {
        "source": result.source,
        "analysis_status": result.analysis_status,
        "core_product_service": result.subject_object,
        "subject_object": result.subject_object,
        "content_type": result.content_type,
        "core_points": result.core_points,
        "target_audience": result.target_audience,
        "title_hook": result.title_hook,
        "content_structure": result.content_structure,
        "cover_type": result.cover_type or _payload_value(result.raw_payload, "cover_type", "灏侀潰绫诲瀷", "封面类型"),
        "title_type": result.title_type or _payload_value(result.raw_payload, "title_type", "鏍囬绫诲瀷", "标题类型"),
        "reusable_model": result.reusable_models or [],
        "reusable_models": result.reusable_models or [],
        "content_usage": result.reuse_value,
        "reuse_value": result.reuse_value,
        "search_attribute": result.search_attribute,
        "score": result.score,
        "rating": result.rating,
        "analysis_note": result.analysis_note,
        "last_pushed_at": result.last_pushed_at.isoformat() if result.last_pushed_at else None,
        "last_pulled_at": result.last_pulled_at.isoformat() if result.last_pulled_at else None,
    }


def _serialize_feishu_sync(result: NoteAnalysisResult | None) -> dict:
    return {
        "push_status": result.push_status if result else "not_synced",
        "pull_status": result.pull_status if result else "not_pulled",
        "external_record_id": result.external_record_id if result else None,
        "last_error": result.last_error if result else "",
    }


def _note_source_url(raw: dict[str, Any], fallback_note_id: str) -> str:
    for key in ("note_url", "url", "share_url"):
        value = raw.get(key)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value
    acquisition = raw.get("data_acquisition")
    if isinstance(acquisition, dict):
        value = acquisition.get("original_url")
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value
    data = raw.get("data")
    items = data.get("items") if isinstance(data, dict) else None
    item = items[0] if isinstance(items, list) and items and isinstance(items[0], dict) else {}
    card = item.get("note_card") if isinstance(item.get("note_card"), dict) else {}
    for source in (card, item):
        xsec_token = source.get("xsec_token") if isinstance(source, dict) else None
        if isinstance(xsec_token, str) and xsec_token:
            xsec_source = source.get("xsec_source") if isinstance(source.get("xsec_source"), str) else "pc_feed"
            return f"https://www.xiaohongshu.com/explore/{fallback_note_id}?xsec_token={xsec_token}&xsec_source={xsec_source}"
        for key in ("note_url", "url", "share_url"):
            value = source.get(key) if isinstance(source, dict) else None
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                return value
    return ""


def _serialize_note(
    db: Session,
    note: Note,
    top20_marks: dict[int, list[str]] | None = None,
    mapping_cache: dict[int, XhsContentMapping | None] | None = None,
    include_raw: bool = False,
) -> dict:
    assets = _get_note_assets(db, note)
    image_assets = [asset for asset in assets if asset.asset_type == "image"]
    video_assets = [asset for asset in assets if asset.asset_type == "video"]
    asset_urls = [_asset_display_url(asset, note.user_id) for asset in assets if asset.url or asset.local_path]
    raw = note.raw_json if isinstance(note.raw_json, dict) else {}
    raw_cover = raw.get("cover_url") if isinstance(raw.get("cover_url"), str) else ""
    mapping = _xhs_content_mapping(note, mapping_cache)
    mapped_cover_url = mapping.cover_url if mapping else ""
    mapped_video_url = mapping.video_url if mapping else ""
    mapped_asset_urls = mapping.asset_urls if mapping else []
    response_asset_urls = asset_urls or mapped_asset_urls
    response_cover_url = _asset_display_url(image_assets[0], note.user_id) if image_assets else (mapped_cover_url or raw_cover)
    response_video_url = _asset_display_url(video_assets[0], note.user_id) if video_assets else mapped_video_url
    media_type = _note_media_type(mapping=mapping, video_assets=video_assets, response_video_url=response_video_url)
    marks = (top20_marks or {}).get(note.id, [])
    feishu_analysis = _get_feishu_analysis_result(db, note.id)
    effective_analysis = _get_effective_analysis_result(db, note.id)
    payload = {
        "id": note.id,
        "platform": note.platform,
        "platform_account_id": note.platform_account_id,
        "note_id": note.note_id,
        "title": note.title,
        "content": note.content,
        "author_name": note.author_name,
        "source_url": _note_source_url(raw, note.note_id),
        "asset_urls": response_asset_urls,
        "cover_url": response_cover_url,
        "video_url": response_video_url,
        "video_addr": response_video_url,
        "media_type": media_type,
        "note_type": "video" if media_type == "video" else "normal",
        "created_at": note.created_at.isoformat(),
        "engagement_metrics": _note_engagement_metrics(note, mapping_cache),
        "analysis_marks": marks,
        "is_analysis_focus": len(marks) >= 2,
        "feishu_sync": _serialize_feishu_sync(feishu_analysis),
        "analysis_result": _serialize_analysis_result(effective_analysis),
    }
    if include_raw:
        payload["raw_json"] = note.raw_json
    return payload


def _serialize_note_with_tags(
    db: Session,
    note: Note,
    top20_marks: dict[int, list[str]] | None = None,
    mapping_cache: dict[int, XhsContentMapping | None] | None = None,
    include_raw: bool = False,
) -> dict:
    serialized = _serialize_note(db, note, top20_marks, mapping_cache, include_raw)
    serialized["tags"] = _get_note_tags(db, note.id)
    return serialized


def _build_notes_csv(db: Session, notes: list[Note]) -> str:
    output = io.StringIO()
    fieldnames = ["note_id", "title", "author_name", "content", "tags", "created_at"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for note in notes:
        tags = ",".join(tag["name"] for tag in _get_note_tags(db, note.id))
        writer.writerow(
            {
                "note_id": note.note_id,
                "title": note.title,
                "author_name": note.author_name,
                "content": note.content,
                "tags": tags,
                "created_at": note.created_at.isoformat(),
            }
        )
    return output.getvalue()


def _serialize_asset(asset: NoteAsset, user_id: int | None = None) -> dict:
    download_url = _asset_display_url(asset, user_id) if asset.local_path else ""
    return {
        "id": asset.id,
        "note_id": asset.note_id,
        "asset_type": asset.asset_type,
        "url": _asset_display_url(asset, user_id),
        "local_path": asset.local_path,
        "download_url": download_url,
        "sort_order": asset.sort_order,
    }


def _serialize_comment(comment: NoteComment, *, include_raw: bool = False) -> dict:
    payload = {
        "id": comment.id,
        "note_id": comment.note_id,
        "comment_id": comment.comment_id,
        "user_name": comment.user_name,
        "user_id": comment.user_id,
        "content": comment.content,
        "like_count": comment.like_count,
        "parent_comment_id": comment.parent_comment_id,
        "created_at_remote": comment.created_at_remote,
    }
    if include_raw:
        payload["raw_json"] = comment.raw_json
    return payload


def _serialize_draft(draft: AiDraft) -> dict:
    return {
        "id": draft.id,
        "platform": draft.platform,
        "draft_name": draft.draft_name or "",
        "title": draft.title,
        "body": draft.body,
        "source_note_id": draft.source_note_id,
        "created_at": draft.created_at.isoformat(),
    }


def _get_owned_account(db: Session, current_user: User, account_id: int, *, expected_platform: str) -> PlatformAccount:
    account = db.get(PlatformAccount, account_id)
    if account is None or account.user_id != current_user.id or account.platform != expected_platform:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return account


def _get_latest_account_cookies(db: Session, account: PlatformAccount) -> str:
    cookie_version = db.scalars(
        select(AccountCookieVersion)
        .where(AccountCookieVersion.platform_account_id == account.id)
        .order_by(AccountCookieVersion.created_at.desc())
    ).first()
    if cookie_version is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Account has no cookies")
    return _cookies_to_string(decrypt_text(cookie_version.encrypted_cookies))


def _get_owned_note(db: Session, current_user: User, note_id: int) -> Note:
    note = db.get(Note, note_id)
    if note is None or note.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    return note


def _get_unique_owned_notes(db: Session, current_user: User, note_ids: list[int]) -> list[Note]:
    return [_get_owned_note(db, current_user, note_id) for note_id in dict.fromkeys(note_ids)]


UNANALYZED_STATUS = "未分析"


def _excluded_note_condition(user_id: int):
    return select(NoteExclusion.id).where(
        NoteExclusion.user_id == user_id,
        NoteExclusion.platform == Note.platform,
        NoteExclusion.platform_note_id == Note.note_id,
    ).exists()


def _not_excluded_note_condition(user_id: int):
    return ~_excluded_note_condition(user_id)


def _apply_note_visibility(statement, user_id: int, visibility: str):
    if visibility == "all":
        return statement
    if visibility == "excluded":
        return statement.where(_excluded_note_condition(user_id))
    return statement.where(_not_excluded_note_condition(user_id))


def _is_unanalyzed_analysis(result: NoteAnalysisResult | None) -> bool:
    if result is None:
        return True
    return not any([
        result.analysis_status,
        result.subject_object,
        result.content_type,
        result.core_points,
        result.target_audience,
        result.title_hook,
        result.content_structure,
        result.reusable_models,
        result.reuse_value,
        result.search_attribute,
        result.score is not None,
        result.rating,
        result.analysis_note,
    ])


def _split_filter_values(value: Optional[str]) -> list[str]:
    if not value:
        return []
    text = value
    for separator in ["；", ";", "\n", "、"]:
        text = text.replace(separator, ",")
    return [item.strip() for item in text.split(",") if item.strip()]


def _split_analysis_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        items: list[str] = []
        for item in value:
            items.extend(_split_analysis_values(item))
        return items
    text = str(value).strip()
    if not text:
        return []
    for separator in ["；", ";", "\n", "、"]:
        text = text.replace(separator, ",")
    return [item.strip() for item in text.split(",") if item.strip()]


def _has_any_text(actual: Any, selected: list[str]) -> bool:
    if not selected:
        return True
    actual_values = set(_split_analysis_values(actual))
    return any(value in actual_values for value in selected)


def _option_list(counter: dict[str, int]) -> list[dict[str, str]]:
    return [
        {"label": value, "value": value}
        for value, _count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def _add_option(counter: dict[str, int], value: Any) -> None:
    for item in _split_analysis_values(value):
        counter[item] = counter.get(item, 0) + 1


def _effective_analysis_results_for_notes(db: Session, *, user_id: int, note_ids: list[int]) -> list[NoteAnalysisResult]:
    if not note_ids:
        return []
    statement = (
        select(NoteAnalysisResult)
        .where(
            NoteAnalysisResult.user_id == user_id,
            NoteAnalysisResult.source.in_(["system", "feishu"]),
            NoteAnalysisResult.note_id.in_(note_ids),
        )
        .order_by(NoteAnalysisResult.note_id.asc(), NoteAnalysisResult.source.desc())
    )
    selected: dict[int, NoteAnalysisResult] = {}
    for result in db.scalars(statement):
        selected.setdefault(result.note_id, result)
    return list(selected.values())


@router.get("/filter-options")
def get_note_filter_options(
    platform: Optional[str] = None,
    visibility: Literal["active", "all", "excluded"] = "active",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note_statement = select(Note.id).where(Note.user_id == current_user.id)
    note_statement = _apply_note_visibility(note_statement, current_user.id, visibility)
    if platform:
        note_statement = note_statement.where(Note.platform == platform)
    visible_note_ids = list(db.scalars(note_statement))

    results = _effective_analysis_results_for_notes(db, user_id=current_user.id, note_ids=visible_note_ids)
    analyzed_note_ids = {result.note_id for result in results}
    has_unanalyzed_notes = any(note_id not in analyzed_note_ids for note_id in visible_note_ids)
    analysis_status: dict[str, int] = {UNANALYZED_STATUS: 1} if has_unanalyzed_notes else {}
    core_product_service: dict[str, int] = {}
    content_type: dict[str, int] = {}
    reusable_model: dict[str, int] = {}
    content_usage: dict[str, int] = {}
    search_attribute: dict[str, int] = {}
    for result in results:
        _add_option(analysis_status, result.analysis_status)
        _add_option(core_product_service, result.subject_object)
        _add_option(content_type, result.content_type)
        _add_option(reusable_model, result.reusable_models or [])
        _add_option(content_usage, result.reuse_value)
        _add_option(search_attribute, result.search_attribute)
    return {
        "analysisStatus": _option_list(analysis_status),
        "coreProductService": _option_list(core_product_service),
        "contentType": _option_list(content_type),
        "reusableModel": _option_list(reusable_model),
        "contentUsage": _option_list(content_usage),
        "searchAttribute": _option_list(search_attribute),
    }


@router.get("/ids")
def get_note_ids(
    platform: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    statement = (
        select(Note.note_id)
        .where(
            Note.user_id == current_user.id,
            _not_excluded_note_condition(current_user.id),
        )
    )
    if platform:
        statement = statement.where(Note.platform == platform)
    note_ids = db.scalars(statement).all()
    return {"items": list(note_ids)}


@router.get("")
def get_notes(
    platform: Optional[str] = None,
    q: Optional[str] = None,
    tag_id: Optional[int] = None,
    has_assets: Optional[bool] = None,
    has_comments: Optional[bool] = None,
    visibility: Literal["active", "all", "excluded"] = "active",
    sort_by: Literal["latest", "engagement", "likes", "comments", "collects"] = "latest",
    feishu_push_status: Optional[str] = None,
    analysis_status: Optional[str] = None,
    core_product_service: Optional[str] = None,
    content_type: Optional[str] = None,
    reusable_model: Optional[str] = None,
    content_usage: Optional[str] = None,
    search_attribute: Optional[str] = None,
    reuse_value: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    statement = select(Note).where(Note.user_id == current_user.id)
    statement = _apply_note_visibility(statement, current_user.id, visibility)
    if platform:
        statement = statement.where(Note.platform == platform)
    if q:
        keyword = f"%{q.strip()}%"
        statement = statement.where(
            or_(
                Note.title.ilike(keyword),
                Note.content.ilike(keyword),
                Note.author_name.ilike(keyword),
                Note.note_id.ilike(keyword),
            )
        )
    if tag_id is not None:
        tag = db.get(Tag, tag_id)
        if tag is None or tag.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
        statement = statement.where(Note.id.in_(select(note_tags.c.note_id).where(note_tags.c.tag_id == tag_id)))
    if has_assets is True:
        statement = statement.where(Note.id.in_(select(NoteAsset.note_id)))
    elif has_assets is False:
        statement = statement.where(Note.id.not_in(select(NoteAsset.note_id)))
    if has_comments is True:
        statement = statement.where(Note.id.in_(select(NoteComment.note_id)))
    elif has_comments is False:
        statement = statement.where(Note.id.not_in(select(NoteComment.note_id)))
    notes = db.scalars(statement.order_by(Note.created_at.desc())).all()

    analysis_status_values = _split_filter_values(analysis_status)
    wants_unanalyzed = UNANALYZED_STATUS in analysis_status_values
    concrete_analysis_status_values = [value for value in analysis_status_values if value != UNANALYZED_STATUS]
    core_product_service_values = _split_filter_values(core_product_service)
    content_type_values = _split_filter_values(content_type)
    reusable_model_values = _split_filter_values(reusable_model)
    content_usage_values = _split_filter_values(content_usage) + _split_filter_values(reuse_value)
    search_attribute_values = _split_filter_values(search_attribute)
    has_analysis_field_filters = any([
        analysis_status_values,
        core_product_service_values,
        content_type_values,
        reusable_model_values,
        content_usage_values,
        search_attribute_values,
    ])

    def _matches_analysis_filters(note: Note) -> bool:
        feishu_result = _get_feishu_analysis_result(db, note.id)
        result = _get_effective_analysis_result(db, note.id)
        if feishu_push_status and (feishu_result.push_status if feishu_result else "not_synced") != feishu_push_status:
            return False
        if wants_unanalyzed and _is_unanalyzed_analysis(result):
            return True
        if wants_unanalyzed and not concrete_analysis_status_values:
            return False
        if has_analysis_field_filters and result is None:
            return False
        if not _has_any_text(result.analysis_status if result else None, concrete_analysis_status_values):
            return False
        if not _has_any_text(result.subject_object if result else None, core_product_service_values):
            return False
        if not _has_any_text(result.content_type if result else None, content_type_values):
            return False
        if not _has_any_text(result.reusable_models if result else None, reusable_model_values):
            return False
        if not _has_any_text(result.reuse_value if result else None, content_usage_values):
            return False
        if not _has_any_text(result.search_attribute if result else None, search_attribute_values):
            return False
        return True

    if feishu_push_status or has_analysis_field_filters:
        notes = [note for note in notes if _matches_analysis_filters(note)]

    mapping_cache: dict[int, XhsContentMapping | None] = {}
    top20_marks = _top20_marks(notes, mapping_cache)
    if sort_by != "latest":
        notes = sorted(notes, key=lambda note: (_note_metric(note, sort_by, mapping_cache), note.created_at, note.id), reverse=True)
    include_raw = current_user.role == "admin"
    return paginated([_serialize_note_with_tags(db, note, top20_marks, mapping_cache, include_raw=include_raw) for note in notes], page, page_size)


@router.post("/{note_id}/analysis")
def analyze_note(
    note_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = _get_owned_note(db, current_user, note_id)
    tenant_context = get_current_tenant_context(current_user=current_user, db=db)
    usage_service = UsageQuotaService(db)
    reservation = usage_service.reserve(
        tenant_id=tenant_context.tenant.id,
        user_id=current_user.id,
        feature_key=NOTE_SYSTEM_ANALYSIS_FEATURE_KEY,
        bucket=CREDITS_BUCKET,
        amount=credit_cost_for_feature(NOTE_SYSTEM_ANALYSIS_FEATURE_KEY),
        idempotency_key=usage_idempotency_key(request, f"note.system_analysis:{current_user.id}:{note.id}"),
        request_summary={"note_id": note.id},
        resource_type="note",
        resource_id=note.id,
    )
    try:
        result = analyze_note_system(db, user_id=current_user.id, note=note)
    except Exception as exc:
        usage_service.refund(reservation.id, failure_reason=str(exc))
        raise
    usage_service.commit(reservation.id)
    return _serialize_analysis_result(result)


@router.post("/batch-create-drafts")
def batch_create_drafts(
    payload: BatchCreateDraftsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notes = _get_unique_owned_notes(db, current_user, payload.note_ids)
    drafts: list[AiDraft] = []
    for note in notes:
        draft = AiDraft(
            user_id=current_user.id,
            platform=note.platform,
            title=note.title,
            body=note.content,
            source_note_id=note.id,
        )
        db.add(draft)
        drafts.append(draft)

    db.commit()
    for draft in drafts:
        db.refresh(draft)

    return {
        "created_count": len(drafts),
        "items": [_serialize_draft(draft) for draft in drafts],
    }


@router.post("/exclusions/mark")
def mark_note_exclusions(
    payload: MarkNoteExclusionsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    client = None
    feishu_client_error: Exception | None = None
    if payload.sync_feishu:
        from backend.app.api.feishu_integration import _client_or_error, _get_config

        try:
            client = _client_or_error(_get_config(db, current_user.id))
        except Exception as exc:
            feishu_client_error = exc
    response = mark_notes_excluded(
        db,
        user_id=current_user.id,
        note_ids=payload.note_ids,
        reason_code=payload.reason_code,
        reason_text=payload.reason_text,
        client=client,
    )
    if feishu_client_error is not None:
        unique_note_ids = list(dict.fromkeys(payload.note_ids))
        notes = db.scalars(
            select(Note).where(
                Note.user_id == current_user.id,
                Note.platform == "xhs",
                Note.id.in_(unique_note_ids),
            )
        ).all() if unique_note_ids else []
        failed_message = f"Feishu client error: {feishu_client_error}"
        for note in notes:
            analysis = get_or_create_analysis_result(db, user_id=current_user.id, note_id=note.id)
            analysis.push_status = "failed"
            analysis.last_error = failed_message
            response["errors"].append(
                {
                    "note_id": note.id,
                    "feishu_failed": True,
                    "error": failed_message,
                }
            )
        if notes:
            db.commit()
            response["feishu_failed_count"] += len(notes)
    return response


@router.get("/exclusions/current-cleanup-candidates")
def get_current_cleanup_candidates(
    strict: bool = True,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {"items": build_current_cleanup_candidates(db, user_id=current_user.id, strict=strict)}


@router.get("/{note_id}")
def get_note(
    note_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _serialize_note_with_tags(db, _get_owned_note(db, current_user, note_id), include_raw=current_user.role == "admin")


@router.delete("/{note_id}")
def delete_note(
    note_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = _get_owned_note(db, current_user, note_id)
    db.execute(delete(note_tags).where(note_tags.c.note_id == note.id))
    db.execute(delete(NoteAsset).where(NoteAsset.note_id == note.id))
    db.execute(delete(NoteComment).where(NoteComment.note_id == note.id))
    db.query(AiDraft).filter(AiDraft.source_note_id == note.id).update({"source_note_id": None})
    db.delete(note)
    db.commit()
    return {"id": note_id, "status": "deleted"}


@router.get("/{note_id}/assets")
def get_note_assets(
    note_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = _get_owned_note(db, current_user, note_id)
    assets = db.scalars(select(NoteAsset).where(NoteAsset.note_id == note.id).order_by(NoteAsset.sort_order.asc(), NoteAsset.id.asc())).all()
    return paginated([_serialize_asset(asset, current_user.id) for asset in assets], page, page_size)


class AddNoteAssetRequest(BaseModel):
    asset_type: str = Field(pattern="^(image|video)$")
    url: str = Field(default="", max_length=2048)
    local_path: str = Field(default="", max_length=512)


class ImportSourceImagesRequest(BaseModel):
    source_url: str = Field(default="", max_length=2048)
    download: bool = True
    image_urls: list[str] = Field(default_factory=list, max_length=50)


def _safe_source_image_import_url(source_url: str) -> str:
    parsed = urlparse(str(source_url or "").strip())
    if not parsed.scheme or not parsed.netloc:
        return ""
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def _legacy_data_acquisition_note_id(source_url: str) -> str:
    parsed = urlparse(str(source_url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc.lower().endswith("xiaohongshu.com"):
        return ""
    segments = [segment for segment in parsed.path.split("/") if segment]
    if len(segments) != 2 or segments[0] != "explore" or not segments[1].isdigit():
        return ""
    if parsed.query:
        return ""
    return segments[1]


def _resolve_source_image_import_url(
    db: Session,
    note: Note,
    source_url: str,
    *,
    fail_on_unresolved: bool = False,
) -> str:
    note_id = _legacy_data_acquisition_note_id(source_url)
    if not note_id:
        return source_url
    raw_json = note.raw_json if isinstance(note.raw_json, dict) else {}
    acquisition = raw_json.get("data_acquisition")
    if raw_json.get("source") != "data_acquisition" and not isinstance(acquisition, dict):
        return source_url
    try:
        _account, cookie_text = get_platform_data_account_cookie_text(db)
        resolved_url = huitun_live_note_source.resolve_note_url(cookie_text, note_id)
    except Exception as exc:
        if fail_on_unresolved:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="source_url_unavailable") from exc
        return source_url
    if not resolved_url:
        if fail_on_unresolved:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="source_url_unavailable")
        return source_url
    next_raw = dict(raw_json)
    next_raw["note_url"] = resolved_url
    if isinstance(acquisition, dict):
        next_raw["data_acquisition"] = {**acquisition, "original_url": resolved_url}
    else:
        next_raw["data_acquisition"] = {"original_url": resolved_url}
    note.raw_json = next_raw
    return resolved_url


def _note_known_source_image_urls(db: Session, note: Note) -> list[str]:
    values: list[str] = []

    def collect(value: Any, *, depth: int = 0) -> None:
        if depth > 8 or len(values) >= 100:
            return
        if isinstance(value, str):
            if is_xhs_note_image_url(value):
                values.append(value)
            return
        if isinstance(value, list):
            for item in value:
                collect(item, depth=depth + 1)
            return
        if isinstance(value, dict):
            for item in value.values():
                collect(item, depth=depth + 1)

    raw_json = note.raw_json if isinstance(note.raw_json, dict) else {}
    collect(raw_json)
    asset_urls = db.scalars(
        select(NoteAsset.url)
        .where(NoteAsset.note_id == note.id, NoteAsset.asset_type == "image")
        .order_by(NoteAsset.sort_order.asc(), NoteAsset.id.asc())
    ).all()
    for asset_url in asset_urls:
        collect(asset_url)
    return _unique_source_image_urls(values)


def _source_import_base64_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("utf-8").rstrip("=")


def _source_import_base64_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("utf-8"))


def _create_source_image_import_token(*, user_id: int, note_id: int) -> str:
    payload = {
        "purpose": "xhs_source_image_import",
        "user_id": user_id,
        "note_id": note_id,
        "exp": int(time.time()) + SOURCE_IMAGE_IMPORT_TOKEN_TTL_SECONDS,
    }
    payload_text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    payload_part = _source_import_base64_encode(payload_text.encode("utf-8"))
    signature = hmac.new(get_settings().secret_key.encode("utf-8"), payload_part.encode("utf-8"), hashlib.sha256).digest()
    return f"{payload_part}.{_source_import_base64_encode(signature)}"


def _decode_source_image_import_token(token: str) -> dict[str, Any]:
    credentials_exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid import token")
    try:
        payload_part, signature_part = str(token or "").split(".", 1)
    except ValueError as exc:
        raise credentials_exception from exc

    expected_signature = hmac.new(
        get_settings().secret_key.encode("utf-8"),
        payload_part.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    try:
        actual_signature = _source_import_base64_decode(signature_part)
    except Exception as exc:
        raise credentials_exception from exc
    if not hmac.compare_digest(actual_signature, expected_signature):
        raise credentials_exception

    try:
        payload = json.loads(_source_import_base64_decode(payload_part))
    except Exception as exc:
        raise credentials_exception from exc
    if payload.get("purpose") != "xhs_source_image_import":
        raise credentials_exception
    if not isinstance(payload.get("user_id"), int) or not isinstance(payload.get("note_id"), int):
        raise credentials_exception
    if not isinstance(payload.get("exp"), int) or payload["exp"] < int(time.time()):
        raise credentials_exception
    return payload


def _unique_source_image_urls(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        url = str(value or "").strip()
        if not url.startswith(("http://", "https://")):
            continue
        if not is_xhs_note_image_url(url):
            continue
        key = canonical_xhs_image_key(url)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(url)
        if len(result) >= 50:
            break
    return result


def _import_source_image_urls(
    *,
    db: Session,
    note: Note,
    user_id: int,
    source_urls: list[str],
    source_url: str,
    download: bool,
) -> dict[str, Any]:
    source_urls = _unique_source_image_urls(source_urls)
    existing_assets = db.scalars(
        select(NoteAsset)
        .where(NoteAsset.note_id == note.id, NoteAsset.asset_type == "image")
        .order_by(NoteAsset.sort_order.asc(), NoteAsset.id.asc())
    ).all()
    existing_assets_by_key = {
        key: asset
        for asset in existing_assets
        if asset.url and (key := canonical_xhs_image_key(asset.url))
    }
    next_sort_order = (
        db.scalars(select(NoteAsset.sort_order).where(NoteAsset.note_id == note.id).order_by(NoteAsset.sort_order.desc())).first()
    )
    sort_order = int(next_sort_order or 0) + 1 if next_sort_order is not None else 0
    items: list[dict[str, Any]] = []
    imported_count = 0
    skipped_count = 0
    downloaded_count = 0
    failed_count = 0

    for image_url in source_urls:
        canonical_key = canonical_xhs_image_key(image_url)
        existing_asset = existing_assets_by_key.get(canonical_key)
        if existing_asset is not None:
            skipped_count += 1
            status_text = "skipped"
            local_name = existing_asset.local_path or ""
            error = ""
            if download and not existing_asset.local_path:
                local_name = _download_asset(image_url, user_id, "image") or ""
                if local_name:
                    existing_asset.local_path = local_name
                    downloaded_count += 1
                    status_text = "downloaded"
                else:
                    failed_count += 1
                    status_text = "failed"
                    error = "download_failed"
            items.append({"url": image_url, "status": status_text, "asset_id": existing_asset.id, "local_path": local_name, "error": error})
            continue

        local_name = ""
        status_text = "imported"
        error = ""
        if download:
            local_name = _download_asset(image_url, user_id, "image") or ""
            if local_name:
                downloaded_count += 1
                status_text = "downloaded"
            else:
                failed_count += 1
                status_text = "failed"
                error = "download_failed"

        asset = NoteAsset(
            note_id=note.id,
            asset_type="image",
            url=image_url,
            local_path=local_name,
            sort_order=sort_order,
        )
        db.add(asset)
        db.flush()
        imported_count += 1
        existing_assets_by_key[canonical_key] = asset
        sort_order += 1
        items.append({"url": image_url, "status": status_text, "asset_id": asset.id, "local_path": local_name, "error": error})

    if imported_count:
        raw_json = note.raw_json if isinstance(note.raw_json, dict) else {}
        source_image_urls = [item["url"] for item in items if item["status"] != "skipped"]
        note.raw_json = {
            **raw_json,
            "source_image_import": {
                "source_url": _safe_source_image_import_url(source_url),
                "total_source_image_count": len(source_urls),
                "imported_count": imported_count,
                "downloaded_count": downloaded_count,
                "failed_count": failed_count,
            },
            "image_urls": list(dict.fromkeys([*(raw_json.get("image_urls") if isinstance(raw_json.get("image_urls"), list) else []), *source_image_urls])),
        }
    db.commit()

    return {
        "total_source_image_count": len(source_urls),
        "imported_count": imported_count,
        "skipped_count": skipped_count,
        "downloaded_count": downloaded_count,
        "failed_count": failed_count,
        "items": items,
    }


def _refresh_source_image_import_summary(note: Note, image_assets: list[NoteAsset]) -> None:
    raw_json = note.raw_json if isinstance(note.raw_json, dict) else {}
    summary = raw_json.get("source_image_import")
    if not isinstance(summary, dict):
        return
    next_summary = {
        **summary,
        "total_source_image_count": int(summary.get("total_source_image_count") or len(image_assets)),
        "downloaded_count": sum(1 for asset in image_assets if asset.local_path),
        "failed_count": sum(1 for asset in image_assets if not asset.local_path),
    }
    note.raw_json = {**raw_json, "source_image_import": next_summary}


def _source_image_import_target_url(request: Request, note_id: int) -> str:
    origin = str(request.headers.get("origin") or "").rstrip("/")
    if origin.startswith(("http://127.0.0.1", "http://localhost")):
        parsed = urlparse(origin)
        host = parsed.hostname or "127.0.0.1"
        return f"{parsed.scheme or 'http'}://{host}:{get_settings().server_port}/api/notes/{note_id}/assets/import-source-images/page-payload"
    return f"{str(request.base_url).rstrip('/')}/api/notes/{note_id}/assets/import-source-images/page-payload"


def _build_source_image_import_script(*, target_url: str, token: str) -> str:
    target_json = json.dumps(target_url, ensure_ascii=False)
    token_json = json.dumps(token, ensure_ascii=False)
    return (
        "javascript:(async()=>{"
        f"const target={target_json},token={token_json};"
        "const urls=[],seen=new Set();"
        "const noteRe=/(\\/notes_pre_post\\/|\\/note_pre_post_|\\/notes_uhdr\\/)/;"
        "const keyOf=(u)=>{try{const p=new URL(u).pathname.split('!')[0].split('/').filter(Boolean);for(const m of ['notes_pre_post','notes_uhdr','note_pre_post_uhdr']){const i=p.indexOf(m);if(i>=0&&p[i+1])return m+'/'+p[i+1];}const mm=new URL(u).pathname.match(/(note_pre_post_[^/]+)\\/([^/!?]+)/);if(mm)return mm[1]+'/'+mm[2];return u.split('!')[0];}catch(e){return String(u||'').split('!')[0];}};"
        "const add=(u)=>{u=String(u||'').trim().replace(/\\\\u002F/g,'/').replace(/\\\\\\//g,'/');"
        "if(!/^https?:\\/\\//.test(u)&&noteRe.test('/'+u.replace(/^\\/+/,'')))u='https://sns-img-bd.xhscdn.com/'+u.replace(/^\\/+/, '');"
        "if(/^https?:\\/\\/(sns-[^/]+\\.xhscdn\\.com|ci\\.xiaohongshu\\.com)\\//.test(u)&&noteRe.test(new URL(u).pathname)){const k=keyOf(u);if(!seen.has(k)){seen.add(k);urls.push(u);}}};"
        "const addList=(list)=>{if(Array.isArray(list))list.forEach(i=>{if(!i)return;[i.urlDefault,i.url,i.traceId,i.fileId,i.id].forEach(add);if(Array.isArray(i.urlList))i.urlList.forEach(x=>typeof x==='string'?add(x):x&&[x.urlDefault,x.url,x.traceId,x.fileId,x.id].forEach(add));});};"
        "const walk=(v,d=0)=>{if(!v||d>8)return;if(typeof v==='string'){add(v);return;}if(Array.isArray(v)){v.forEach(x=>walk(x,d+1));return;}if(typeof v==='object'){if(Array.isArray(v.imageList))addList(v.imageList);['urlDefault','url','urlPre','url_pre','traceId','trace_id','fileId','file_id','id'].forEach(k=>add(v[k]));Object.values(v).forEach(x=>walk(x,d+1));}};"
        "try{const s=window.__INITIAL_STATE__||{},id=(location.pathname.match(/\\/(?:explore|discovery\\/item)\\/([^/?#]+)/)||[])[1]||'';addList(s.noteData&&s.noteData.data&&s.noteData.data.noteData&&s.noteData.data.noteData.imageList);const m=s.note&&s.note.noteDetailMap;if(m){addList(m[id]&&m[id].note&&m[id].note.imageList);Object.values(m).forEach(v=>addList(v&&v.note&&v.note.imageList));}walk(window.__INITIAL_STATE__);}catch(e){}"
        "const scan=(s)=>{String(s||'').replace(/https?:\\/\\/(?:sns-[^\\\"'<>\\s]+?\\.xhscdn\\.com|ci\\.xiaohongshu\\.com)\\/[^\\\"'<>\\s)]+/g,add);};"
        "document.querySelectorAll('img,source').forEach(i=>{add(i.currentSrc||i.src||i.getAttribute('src'));scan(i.getAttribute('srcset'));});"
        "document.querySelectorAll('[style],[data-src],[data-original],[data-url]').forEach(e=>{scan(e.getAttribute('style'));add(e.getAttribute('data-src'));add(e.getAttribute('data-original'));add(e.getAttribute('data-url'));});"
        "scan(document.documentElement.innerHTML.slice(0,200000));"
        "try{performance.getEntriesByType('resource').slice(-300).forEach(e=>add(e.name));}catch(e){}"
        "const body={token,source_url:location.href,image_urls:urls.slice(0,50),download:true};"
        "const payload=JSON.stringify(body);"
        "const mark=(extra)=>{window.__xhsSourceImageImportStatus={status:'sent',count:body.image_urls.length,source_url:body.source_url,...(extra||{})};};"
        "let sent=false;try{if(navigator.sendBeacon){sent=navigator.sendBeacon(target,new Blob([payload],{type:'text/plain;charset=UTF-8'}));}}catch(e){}"
        "if(sent){mark({transport:'beacon'});}"
        "else{window.__xhsSourceImageImportStatus={status:'sending',count:body.image_urls.length,source_url:body.source_url,transport:'fetch'};"
        "fetch(target,{method:'POST',headers:{'Content-Type':'text/plain;charset=UTF-8'},body:payload,keepalive:true})"
        ".then(async r=>{const t=await r.text();let data={};try{data=JSON.parse(t);}catch(e){data={text:t};}"
        "window.__xhsSourceImageImportStatus={status:r.ok?'done':'failed',http_status:r.status,count:body.image_urls.length,result:data};"
        "console.log('[xhs-image-import]',window.__xhsSourceImageImportStatus);})"
        ".catch(e=>{window.__xhsSourceImageImportStatus={status:'failed',count:body.image_urls.length,error:e&&e.message?e.message:String(e)};"
        "console.error('[xhs-image-import]',e);});}"
        "try{console.log(`[xhs-image-import] sent ${body.image_urls.length} images, return to system and refresh detail.`);}catch(e){}"
        "})()"
    )


@router.post("/{note_id}/assets")
def add_note_asset(
    note_id: int,
    payload: AddNoteAssetRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = _get_owned_note(db, current_user, note_id)
    if not payload.url and not payload.local_path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="url or local_path is required")
    local_path = payload.local_path
    if local_path:
        try:
            local_path = validate_owned_media_reference(local_path, current_user.id)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media file not found") from None
    asset = NoteAsset(
        note_id=note.id,
        asset_type=payload.asset_type,
        url=payload.url,
        local_path=local_path,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return _serialize_asset(asset, current_user.id)


@router.post("/{note_id}/assets/import-source-images")
def import_source_image_assets(
    note_id: int,
    payload: ImportSourceImagesRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = _get_owned_note(db, current_user, note_id)
    if payload.image_urls:
        source_urls = payload.image_urls
    else:
        if not payload.source_url:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="source_url_or_image_urls_required")
        source_url = _resolve_source_image_import_url(db, note, payload.source_url, fail_on_unresolved=True)
        try:
            source_urls = fetch_xhs_note_image_urls(source_url)
        except XhsSourceImageExtractionError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        if not source_urls:
            source_urls = _note_known_source_image_urls(db, note)
    source_url = _resolve_source_image_import_url(db, note, payload.source_url) if payload.image_urls else source_url

    return _import_source_image_urls(
        db=db,
        note=note,
        user_id=current_user.id,
        source_urls=source_urls,
        source_url=source_url,
        download=payload.download,
    )


@router.post("/{note_id}/assets/import-source-images/page-script")
def create_source_image_import_script(
    note_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = _get_owned_note(db, current_user, note_id)
    token = _create_source_image_import_token(user_id=current_user.id, note_id=note.id)
    target_url = _source_image_import_target_url(request, note.id)
    return {
        "script": _build_source_image_import_script(target_url=target_url, token=token),
        "expires_in_seconds": SOURCE_IMAGE_IMPORT_TOKEN_TTL_SECONDS,
    }


@router.post("/{note_id}/assets/import-source-images/page-payload")
async def import_source_image_page_payload(
    note_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    raw_body = (await request.body()).decode("utf-8", errors="ignore")
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_payload") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_payload")

    token_payload = _decode_source_image_import_token(str(payload.get("token") or ""))
    if token_payload["note_id"] != note_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    note = db.get(Note, note_id)
    if note is None or note.user_id != token_payload["user_id"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    image_urls = payload.get("image_urls")
    if not isinstance(image_urls, list):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="image_urls_required")
    result = _import_source_image_urls(
        db=db,
        note=note,
        user_id=token_payload["user_id"],
        source_urls=[str(value or "") for value in image_urls],
        source_url=str(payload.get("source_url") or ""),
        download=bool(payload.get("download", True)),
    )
    return {"status": "ok", **result}


@router.post("/{note_id}/assets/localize-images")
def localize_note_image_assets(
    note_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = _get_owned_note(db, current_user, note_id)
    assets = db.scalars(
        select(NoteAsset)
        .where(NoteAsset.note_id == note.id, NoteAsset.asset_type == "image")
        .order_by(NoteAsset.sort_order.asc(), NoteAsset.id.asc())
    ).all()
    items: list[dict[str, Any]] = []
    downloaded_count = 0
    skipped_count = 0
    failed_count = 0

    for asset in assets:
        if asset.local_path:
            skipped_count += 1
            items.append({
                "asset_id": asset.id,
                "status": "skipped",
                "local_path": asset.local_path,
                "error": "",
            })
            continue
        if not asset.url.startswith(("http://", "https://")):
            failed_count += 1
            items.append({
                "asset_id": asset.id,
                "status": "failed",
                "local_path": "",
                "error": "invalid_url",
            })
            continue

        local_name = _download_asset(asset.url, current_user.id, "image")
        if not local_name:
            failed_count += 1
            items.append({
                "asset_id": asset.id,
                "status": "failed",
                "local_path": "",
                "error": "download_failed",
            })
            continue

        asset.local_path = local_name
        downloaded_count += 1
        items.append({
            "asset_id": asset.id,
            "status": "downloaded",
            "local_path": local_name,
            "error": "",
        })

    if downloaded_count:
        _refresh_source_image_import_summary(note, assets)
        db.commit()

    return {
        "total_image_count": len(assets),
        "downloaded_count": downloaded_count,
        "skipped_count": skipped_count,
        "failed_count": failed_count,
        "items": items,
    }


@router.delete("/{note_id}/assets/{asset_id}")
def delete_note_asset(
    note_id: int,
    asset_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = _get_owned_note(db, current_user, note_id)
    asset = db.scalars(
        select(NoteAsset).where(NoteAsset.id == asset_id, NoteAsset.note_id == note.id)
    ).first()
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    db.delete(asset)
    db.commit()
    return {"id": asset_id, "status": "deleted"}


class ReorderAssetsRequest(BaseModel):
    asset_ids: list[int] = Field(min_length=1)


@router.put("/{note_id}/assets/reorder")
def reorder_note_assets(
    note_id: int,
    payload: ReorderAssetsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = _get_owned_note(db, current_user, note_id)
    assets = db.scalars(select(NoteAsset).where(NoteAsset.note_id == note.id)).all()
    asset_map = {a.id: a for a in assets}
    for idx, aid in enumerate(payload.asset_ids):
        if aid in asset_map:
            asset_map[aid].sort_order = idx
    db.commit()
    return {"ok": True}


@router.get("/{note_id}/comments")
def get_note_comments(
    note_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = _get_owned_note(db, current_user, note_id)
    comments = db.scalars(
        select(NoteComment).where(NoteComment.note_id == note.id).order_by(NoteComment.id.asc())
    ).all()
    return paginated([_serialize_comment(comment, include_raw=current_user.role == "admin") for comment in comments], page, page_size)


def _download_asset(url: str, user_id: int, asset_type: str) -> str | None:
    from backend.app.services.asset_downloader import download_asset_to_local
    return download_asset_to_local(url, user_id, asset_type)


@router.post("/batch-save")
def batch_save_notes(
    payload: BatchSaveNotesRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    adapter_factory=Depends(get_xhs_pc_api_adapter_factory),
):
    account = _get_owned_account(db, current_user, payload.account_id, expected_platform="xhs")
    saved_notes: list[Note] = []
    skipped_items: list[dict[str, str]] = []
    notes_to_save: list[BatchSaveNoteItem] = []

    payload_note_ids = list(dict.fromkeys(note.note_id for note in payload.notes))
    excluded_note_ids = set(
        db.scalars(
            select(NoteExclusion.platform_note_id).where(
                NoteExclusion.user_id == current_user.id,
                NoteExclusion.platform == account.platform,
                NoteExclusion.platform_note_id.in_(payload_note_ids),
            )
        ).all()
    )

    for note_payload in payload.notes:
        if note_payload.note_id in excluded_note_ids:
            skipped_items.append({"note_id": note_payload.note_id, "reason": "excluded"})
        else:
            notes_to_save.append(note_payload)

    if not notes_to_save:
        return {
            "saved_count": 0,
            "skipped_count": len(skipped_items),
            "skipped_items": skipped_items,
            "items": [],
        }

    comment_adapter = None
    if payload.fetch_comments:
        if account.sub_type != "pc":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="PC account is required to fetch comments")
        comment_adapter = adapter_factory(_get_latest_account_cookies(db, account))

    for note_payload in notes_to_save:
        existing = db.scalars(
            select(Note).where(
                Note.user_id == current_user.id,
                Note.platform == account.platform,
                Note.note_id == note_payload.note_id,
            )
        ).first()
        if existing is None:
            existing = Note(
                user_id=current_user.id,
                platform_account_id=account.id,
                platform=account.platform,
                note_id=note_payload.note_id,
            )
            db.add(existing)

        existing.title = note_payload.title
        existing.content = note_payload.content
        existing.author_name = note_payload.author_name
        merged_raw = dict(note_payload.raw) if note_payload.raw else {}
        if note_payload.note_url:
            merged_raw["note_url"] = note_payload.note_url
        existing.raw_json = merged_raw
        db.flush()
        db.execute(delete(NoteAsset).where(NoteAsset.note_id == existing.id))
        image_candidates = [*note_payload.image_urls] or ([note_payload.cover_url] if note_payload.cover_url else [])
        unique_image_urls = [url for index, url in enumerate(image_candidates) if url and url not in image_candidates[:index]]
        for image_url in unique_image_urls:
            local_name = _download_asset(image_url, current_user.id, "image")
            db.add(NoteAsset(note_id=existing.id, asset_type="image", url=image_url, local_path=local_name or ""))
        video_url = note_payload.video_url or note_payload.video_addr
        if video_url:
            local_name = _download_asset(video_url, current_user.id, "video")
            db.add(NoteAsset(note_id=existing.id, asset_type="video", url=video_url, local_path=local_name or ""))
        if payload.fetch_comments and note_payload.note_url and comment_adapter is not None:
            success, message, raw_payload = comment_adapter.get_note_comments(note_payload.note_url)
            if not success:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=message or "XHS note comments failed",
                )
            db.execute(delete(NoteComment).where(NoteComment.note_id == existing.id))
            for comment in normalize_xhs_comment_payload(raw_payload):
                db.add(
                    NoteComment(
                        note_id=existing.id,
                        comment_id=comment["comment_id"],
                        user_name=comment["user_name"],
                        user_id=comment["user_id"],
                        content=comment["content"],
                        like_count=comment["like_count"],
                        parent_comment_id=comment["parent_comment_id"],
                        created_at_remote=comment["created_at_remote"],
                        raw_json=comment["raw_json"],
                    )
                )
        saved_notes.append(existing)

    db.commit()
    for note in saved_notes:
        db.refresh(note)

    return {
        "saved_count": len(saved_notes),
        "skipped_count": len(skipped_items),
        "skipped_items": skipped_items,
        "items": [_serialize_note_with_tags(db, note, include_raw=current_user.role == "admin") for note in saved_notes],
    }


@router.post("/batch-tag")
def batch_tag_notes(
    payload: BatchTagNotesRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notes: list[Note] = []
    for note_id in dict.fromkeys(payload.note_ids):
        notes.append(_get_owned_note(db, current_user, note_id))

    tag_ids = list(dict.fromkeys(payload.tag_ids))
    for tag_id in tag_ids:
        tag = db.get(Tag, tag_id)
        if tag is None or tag.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")

    for note in notes:
        if payload.mode == "replace":
            db.execute(delete(note_tags).where(note_tags.c.note_id == note.id))
            for tag_id in tag_ids:
                db.execute(note_tags.insert().values(note_id=note.id, tag_id=tag_id))
            continue

        if payload.mode == "add":
            existing_tag_ids = set(
                db.scalars(select(note_tags.c.tag_id).where(note_tags.c.note_id == note.id)).all()
            )
            for tag_id in tag_ids:
                if tag_id not in existing_tag_ids:
                    db.execute(note_tags.insert().values(note_id=note.id, tag_id=tag_id))
            continue

        if tag_ids:
            db.execute(
                delete(note_tags).where(
                    note_tags.c.note_id == note.id,
                    note_tags.c.tag_id.in_(tag_ids),
                )
            )

    db.commit()
    return {
        "updated_count": len(notes),
        "items": [_serialize_note_with_tags(db, note, include_raw=current_user.role == "admin") for note in notes],
    }


@router.post("/export")
def export_notes(
    payload: ExportNotesRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notes = _get_unique_owned_notes(db, current_user, payload.note_ids)
    export_dir = Path(get_settings().storage_dir) / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    exported_at = shanghai_now()
    file_name = f"{export_owner_prefix('xhs', 'notes', current_user.id)}{exported_at.strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}.{payload.format}"
    file_path = export_dir / file_name
    if payload.format == "csv":
        file_path.write_text("\ufeff" + _build_notes_csv(db, notes), encoding="utf-8")
    else:
        export_payload = {
            "platform": "xhs",
            "format": payload.format,
            "exported_at": exported_at.isoformat(),
            "total": len(notes),
            "items": [_serialize_note_with_tags(db, note, include_raw=current_user.role == "admin") for note in notes],
        }
        file_path.write_text(json.dumps(export_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "exported_count": len(notes),
        "file_name": file_name,
        "file_path": str(file_path.resolve()),
        "download_url": f"/api/files/exports/{file_name}",
    }

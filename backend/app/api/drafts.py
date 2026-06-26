from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from backend.app.core.config import get_settings
from backend.app.core.database import get_db
from backend.app.core.deps import get_current_user
from backend.app.models import AiDraft, DraftAsset, Note, NoteAsset, PlatformAccount, PublishAsset, PublishJob, User, WechatOfficialDraftSource
from backend.app.schemas.common import paginated
from backend.app.services.asset_downloader import download_asset_to_local
from backend.app.services.asset_storage_policy import valid_media_owner_prefixes
from backend.app.services.xhs_content_normalizer import normalize_xhs_generated_content

router = APIRouter(prefix="/drafts", tags=["drafts"])

MAX_XHS_PUBLISH_IMAGES = 18
IMAGE_MEDIA_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp")
VIDEO_MEDIA_EXTENSIONS = (".mp4", ".mov", ".m4v", ".avi", ".webm")


class DraftCreateRequest(BaseModel):
    platform: str = Field(pattern="^xhs$")
    source_note_id: Optional[int] = None
    draft_name: str = Field(default="", max_length=256)
    title: str = ""
    body: str = ""
    intent: str = Field(default="publish", max_length=32)


class DraftUpdateRequest(BaseModel):
    draft_name: Optional[str] = Field(default=None, max_length=256)
    title: Optional[str] = None
    body: Optional[str] = None
    tags: Optional[list[dict]] = None


class DraftSendToPublishRequest(BaseModel):
    platform_account_id: Optional[int] = None
    publish_mode: str = Field(default="immediate", pattern="^(immediate|scheduled)$")
    scheduled_at: Optional[datetime] = None
    topics: Optional[list[str]] = None
    location: Optional[str] = None
    privacy_type: Optional[int] = Field(default=None, ge=0, le=1)
    is_private: Optional[bool] = None
    asset_file_path: Optional[str] = Field(default=None, max_length=2048)
    asset_file_paths: Optional[list[str]] = None


def _clean_topics(topics: Optional[list[str]]) -> list[str]:
    if topics is None:
        return []
    return [topic.strip() for topic in topics if topic and topic.strip()]


def _build_publish_options(payload: DraftSendToPublishRequest) -> dict[str, Any]:
    options: dict[str, Any] = {}
    topics = _clean_topics(payload.topics)
    if topics:
        options["topics"] = topics
    if payload.location and payload.location.strip():
        options["location"] = payload.location.strip()
    if payload.is_private is not None:
        options["is_private"] = payload.is_private
        options["privacy_type"] = 1 if payload.is_private else 0
    elif payload.privacy_type is not None:
        options["privacy_type"] = payload.privacy_type
        options["is_private"] = payload.privacy_type == 1
    return options


def _media_file_name_from_path(file_path: str) -> str:
    media_prefix = "/api/files/media/"
    if not file_path.startswith(media_prefix):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="asset_file_path must start with /api/files/media/")
    file_name = file_path[len(media_prefix):]
    if not file_name or file_name != PurePosixPath(file_name).name or "\\" in file_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="asset_file_path must be a server-managed media file path")
    return file_name


def _media_extension(value: str) -> str:
    return PurePosixPath(value.split("?", 1)[0].split("#", 1)[0]).suffix.lower()


def _is_image_media_file(value: str) -> bool:
    extension = _media_extension(value)
    return extension in IMAGE_MEDIA_EXTENSIONS and extension not in VIDEO_MEDIA_EXTENSIONS


def _downloaded_media_file(file_name: str) -> Path:
    return Path(get_settings().storage_dir) / "media" / file_name


def _delete_downloaded_media_files(file_names: list[str]) -> None:
    for file_name in file_names:
        try:
            _downloaded_media_file(file_name).unlink(missing_ok=True)
        except OSError:
            pass


def _validate_handoff_asset_file_path(file_path: str, current_user: User, *, require_image: bool = False) -> None:
    file_name = _media_file_name_from_path(file_path)
    try:
        expected_prefixes = valid_media_owner_prefixes(current_user.id, platforms=("xhs",), kinds=("asset", "image", "upload"))
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="asset_file_path must be a current-user managed media file") from None
    if not file_name.startswith(expected_prefixes):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="asset_file_path must be a current-user managed media file")
    media_file = _downloaded_media_file(file_name)
    if not media_file.is_file():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="asset_file_path media file not found")
    if require_image and not _is_image_media_file(file_name):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="asset_file_path must be an image media file")


def _is_external_image_url(file_path: str) -> bool:
    return file_path.startswith("http://") or file_path.startswith("https://")


def _normalize_handoff_asset_file_paths(payload: DraftSendToPublishRequest, current_user: User, downloaded_file_names: list[str]) -> list[str]:
    is_explicit_multi_path = payload.asset_file_paths is not None
    if is_explicit_multi_path:
        raw_paths = payload.asset_file_paths or []
        allow_external_urls = True
    elif payload.asset_file_path:
        raw_paths = [payload.asset_file_path]
        allow_external_urls = False
    else:
        raw_paths = []
        allow_external_urls = False

    unique_paths: list[str] = []
    seen: set[str] = set()
    for raw_path in raw_paths:
        path = (raw_path or "").strip()
        if not path or path in seen:
            continue
        seen.add(path)
        unique_paths.append(path)

    if is_explicit_multi_path and not unique_paths:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="asset_file_paths must include at least one usable image")
    if len(unique_paths) > MAX_XHS_PUBLISH_IMAGES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="asset_file_paths supports at most 18 images")

    for path in unique_paths:
        if path.startswith("/api/files/media/"):
            _validate_handoff_asset_file_path(path, current_user, require_image=True)
        elif not (allow_external_urls and _is_external_image_url(path)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="asset_file_path must start with /api/files/media/" if not allow_external_urls else "asset_file_path must start with /api/files/media/ or http(s)://",
            )

    normalized: list[str] = []
    downloaded_start_index = len(downloaded_file_names)
    try:
        for path in unique_paths:
            if path.startswith("/api/files/media/"):
                normalized_path = path
            elif allow_external_urls and _is_external_image_url(path):
                file_name = download_asset_to_local(path, current_user.id, "image", platform="xhs")
                if not file_name:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="asset_file_path external image download failed")
                downloaded_file_names.append(file_name)
                normalized_path = f"/api/files/media/{file_name}"
                _validate_handoff_asset_file_path(normalized_path, current_user, require_image=True)
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="asset_file_path must start with /api/files/media/" if not allow_external_urls else "asset_file_path must start with /api/files/media/ or http(s)://",
                )
            normalized.append(normalized_path)
    except Exception:
        _delete_downloaded_media_files(downloaded_file_names[downloaded_start_index:])
        del downloaded_file_names[downloaded_start_index:]
        raise

    return normalized


def _publish_file_path_from_draft_asset(asset: DraftAsset, current_user: User, downloaded_file_names: list[str]) -> str:
    if asset.local_path:
        if asset.asset_type == "image" and not _is_image_media_file(asset.local_path):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="asset_file_path must be an image media file")
        return f"/api/files/media/{asset.local_path}"
    if asset.url and _is_external_image_url(asset.url):
        file_name = download_asset_to_local(asset.url, current_user.id, asset.asset_type, platform="xhs")
        if not file_name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="asset_file_path external image download failed")
        downloaded_file_names.append(file_name)
        file_path = f"/api/files/media/{file_name}"
        _validate_handoff_asset_file_path(file_path, current_user, require_image=asset.asset_type == "image")
        return file_path
    if asset.asset_type == "image" and asset.url and not _is_image_media_file(asset.url):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="asset_file_path must be an image media file")
    return asset.url


def _prepare_fallback_publish_assets(db: Session, draft_id: int, current_user: User, downloaded_file_names: list[str]) -> list[tuple[str, str]]:
    draft_assets = db.scalars(
        select(DraftAsset).where(DraftAsset.draft_id == draft_id).order_by(DraftAsset.sort_order.asc(), DraftAsset.id.asc())
    ).all()
    image_count = sum(1 for asset in draft_assets if asset.asset_type == "image")
    if image_count > MAX_XHS_PUBLISH_IMAGES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="asset_file_paths supports at most 18 images")

    downloaded_start_index = len(downloaded_file_names)
    try:
        return [(asset.asset_type, _publish_file_path_from_draft_asset(asset, current_user, downloaded_file_names)) for asset in draft_assets]
    except Exception:
        _delete_downloaded_media_files(downloaded_file_names[downloaded_start_index:])
        del downloaded_file_names[downloaded_start_index:]
        raise


def _serialize_draft(draft: AiDraft, db: Session | None = None) -> dict:
    payload = {
        "id": draft.id,
        "platform": draft.platform,
        "draft_name": draft.draft_name or "",
        "title": draft.title,
        "body": draft.body,
        "tags": draft.tags or [],
        "source_note_id": draft.source_note_id,
        "created_at": draft.created_at.isoformat(),
    }
    if draft.platform == "wechat_official":
        source_article_id = None
        if db is not None:
            source_article_id = db.scalar(
                select(WechatOfficialDraftSource.article_id)
                .where(WechatOfficialDraftSource.draft_id == draft.id)
                .order_by(WechatOfficialDraftSource.id.asc())
            )
        payload["source_article_id"] = source_article_id
    return payload


def _apply_normalized_content(draft: AiDraft) -> None:
    normalized = normalize_xhs_generated_content(draft.title, draft.body, draft.tags or [])
    draft.title = normalized.title
    draft.body = normalized.body
    draft.tags = normalized.tags
    flag_modified(draft, "tags")


def _serialize_publish_job(job: PublishJob) -> dict:
    try:
        publish_options = json.loads(job.publish_options or "{}")
    except json.JSONDecodeError:
        publish_options = {}
    return {
        "id": job.id,
        "platform_account_id": job.platform_account_id,
        "source_draft_id": job.source_draft_id,
        "platform": job.platform,
        "title": job.title,
        "body": job.body,
        "publish_mode": job.publish_mode,
        "publish_options": publish_options,
        "status": job.status,
        "scheduled_at": job.scheduled_at.isoformat() if job.scheduled_at else None,
        "created_at": job.created_at.isoformat(),
    }


def _get_owned_source_note(db: Session, current_user: User, note_id: int) -> Note:
    note = db.get(Note, note_id)
    if note is None or note.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source note not found")
    return note


@router.get("")
def get_drafts(
    platform: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    statement = select(AiDraft).where(AiDraft.user_id == current_user.id)
    if platform:
        statement = statement.where(AiDraft.platform == platform)
    drafts = db.scalars(statement.order_by(AiDraft.created_at.desc())).all()
    return paginated([_serialize_draft(draft, db) for draft in drafts], page, page_size)


@router.post("")
def create_draft(
    payload: DraftCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    source_note = None
    if payload.source_note_id is not None:
        source_note = _get_owned_source_note(db, current_user, payload.source_note_id)

    # Extract tags from source note
    tags = None
    if source_note and source_note.raw_json:
        raw = source_note.raw_json if isinstance(source_note.raw_json, dict) else {}
        tag_list = raw.get("tags") or raw.get("tag_list")
        if not tag_list:
            data = raw.get("data")
            if isinstance(data, dict):
                items = data.get("items") or []
                if items and isinstance(items[0], dict):
                    card = items[0].get("note_card") or {}
                    if isinstance(card, dict):
                        tag_list = card.get("tag_list")
        if isinstance(tag_list, list):
            tags = []
            for t in tag_list:
                if isinstance(t, str):
                    tags.append({"name": t})
                elif isinstance(t, dict) and t.get("name"):
                    tags.append({"id": str(t.get("id", "")), "name": str(t["name"])})

    draft = AiDraft(
        user_id=current_user.id,
        platform=payload.platform,
        draft_name=(payload.draft_name or "").strip(),
        title=payload.title or (source_note.title if source_note else ""),
        body=payload.body or (source_note.content if source_note else ""),
        tags=tags,
        source_note_id=source_note.id if source_note else None,
    )
    if draft.platform == "xhs":
        _apply_normalized_content(draft)
    db.add(draft)
    db.flush()

    if source_note:
        source_assets = db.scalars(
            select(NoteAsset).where(NoteAsset.note_id == source_note.id).order_by(NoteAsset.sort_order.asc(), NoteAsset.id.asc())
        ).all()
        for idx, na in enumerate(source_assets):
            db.add(DraftAsset(
                draft_id=draft.id,
                asset_type=na.asset_type,
                url=na.url,
                local_path=na.local_path,
                sort_order=idx,
            ))

    db.commit()
    db.refresh(draft)
    return _serialize_draft(draft, db)


@router.post("/{draft_id}/send-to-publish")
def send_draft_to_publish(
    draft_id: int,
    payload: DraftSendToPublishRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    draft = db.get(AiDraft, draft_id)
    if draft is None or draft.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")
    if draft.platform == "wechat_official":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="微信公众号发布/群发本阶段保持阻断，请使用 dry-run/草稿工作台",
        )

    account_id: Optional[int] = None
    if payload.platform_account_id is not None:
        account = db.get(PlatformAccount, payload.platform_account_id)
        if account is None or account.user_id != current_user.id or account.platform != draft.platform:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform account not found")
        account_id = account.id

    downloaded_file_names: list[str] = []
    try:
        handoff_asset_file_paths = _normalize_handoff_asset_file_paths(payload, current_user, downloaded_file_names)
        fallback_publish_assets = [] if handoff_asset_file_paths else _prepare_fallback_publish_assets(db, draft.id, current_user, downloaded_file_names)

        if draft.platform == "xhs":
            _apply_normalized_content(draft)

        options = _build_publish_options(payload)
        if draft.tags:
            options["draft_tags"] = draft.tags

        job = PublishJob(
            user_id=current_user.id,
            platform_account_id=account_id,
            source_draft_id=draft.id,
            platform=draft.platform,
            title=draft.title,
            body=draft.body,
            publish_mode=payload.publish_mode,
            publish_options=json.dumps(options, ensure_ascii=False, separators=(",", ":")),
            scheduled_at=payload.scheduled_at,
            status="pending",
        )
        db.add(job)
        db.flush()

        if handoff_asset_file_paths:
            for handoff_asset_file_path in handoff_asset_file_paths:
                db.add(
                    PublishAsset(
                        publish_job_id=job.id,
                        asset_type="image",
                        file_path=handoff_asset_file_path,
                        upload_status="pending",
                    )
                )
        else:
            for asset_type, file_path in fallback_publish_assets:
                pa = PublishAsset(
                    publish_job_id=job.id,
                    asset_type=asset_type,
                    file_path=file_path,
                    upload_status="pending",
                )
                db.add(pa)

        db.commit()
    except Exception:
        if downloaded_file_names:
            _delete_downloaded_media_files(downloaded_file_names)
        raise
    db.refresh(job)
    return _serialize_publish_job(job)


@router.post("/{draft_id}/duplicate")
def duplicate_draft(
    draft_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    draft = db.get(AiDraft, draft_id)
    if draft is None or draft.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")

    duplicated = AiDraft(
        user_id=current_user.id,
        platform=draft.platform,
        draft_name=f"{draft.draft_name} 副本" if draft.draft_name else "",
        title=f"{draft.title} - 副本",
        body=draft.body,
        tags=json.loads(json.dumps(draft.tags, ensure_ascii=False)) if draft.tags is not None else None,
        source_note_id=draft.source_note_id,
    )
    db.add(duplicated)
    db.flush()

    source = db.scalar(select(WechatOfficialDraftSource).where(WechatOfficialDraftSource.draft_id == draft.id))
    if source is not None:
        db.add(WechatOfficialDraftSource(
            draft_id=duplicated.id,
            article_id=source.article_id,
            source_type=source.source_type,
            raw_json=source.raw_json,
        ))

    draft_assets = db.scalars(
        select(DraftAsset).where(DraftAsset.draft_id == draft.id).order_by(DraftAsset.sort_order.asc(), DraftAsset.id.asc())
    ).all()
    for asset in draft_assets:
        db.add(DraftAsset(
            draft_id=duplicated.id,
            asset_type=asset.asset_type,
            url=asset.url,
            local_path=asset.local_path,
            sort_order=asset.sort_order,
        ))

    db.commit()
    db.refresh(duplicated)
    return _serialize_draft(duplicated, db)


@router.patch("/{draft_id}")
def update_draft(
    draft_id: int,
    payload: DraftUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    draft = db.get(AiDraft, draft_id)
    if draft is None or draft.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")

    if payload.draft_name is not None:
        draft.draft_name = payload.draft_name.strip()
    if payload.title is not None:
        draft.title = payload.title
    if payload.body is not None:
        draft.body = payload.body
    if payload.tags is not None:
        draft.tags = list(payload.tags)
        flag_modified(draft, "tags")
    if draft.platform == "xhs" and {"title", "body", "tags"} & payload.model_fields_set:
        _apply_normalized_content(draft)

    db.commit()
    db.refresh(draft)
    return _serialize_draft(draft, db)


@router.delete("/{draft_id}")
def delete_draft(
    draft_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    draft = db.get(AiDraft, draft_id)
    if draft is None or draft.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")
    db.execute(select(DraftAsset).where(DraftAsset.draft_id == draft.id))
    for asset in db.scalars(select(DraftAsset).where(DraftAsset.draft_id == draft.id)).all():
        db.delete(asset)
    db.delete(draft)
    db.commit()
    return {"id": draft_id, "status": "deleted"}


# ---------------------------------------------------------------------------
# Draft assets
# ---------------------------------------------------------------------------

def _serialize_draft_asset(asset: DraftAsset) -> dict:
    display_url = f"/api/files/media/{asset.local_path}" if asset.local_path else asset.url
    return {
        "id": asset.id,
        "draft_id": asset.draft_id,
        "asset_type": asset.asset_type,
        "url": display_url,
        "local_path": asset.local_path,
        "sort_order": asset.sort_order,
    }


class DraftAssetCreateRequest(BaseModel):
    asset_type: str = Field(pattern="^(image|video)$")
    url: str = Field(default="", max_length=2048)
    local_path: str = Field(default="", max_length=512)


class DraftAssetReorderRequest(BaseModel):
    asset_ids: list[int] = Field(min_length=1)


@router.get("/{draft_id}/assets")
def get_draft_assets(
    draft_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    draft = db.get(AiDraft, draft_id)
    if draft is None or draft.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Draft not found")
    assets = db.scalars(
        select(DraftAsset).where(DraftAsset.draft_id == draft.id).order_by(DraftAsset.sort_order.asc(), DraftAsset.id.asc())
    ).all()
    return {"items": [_serialize_draft_asset(a) for a in assets]}


@router.post("/{draft_id}/assets")
def add_draft_asset(
    draft_id: int,
    payload: DraftAssetCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    draft = db.get(AiDraft, draft_id)
    if draft is None or draft.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Draft not found")
    max_order = db.scalar(select(func.max(DraftAsset.sort_order)).where(DraftAsset.draft_id == draft.id)) or 0
    asset = DraftAsset(
        draft_id=draft.id,
        asset_type=payload.asset_type,
        url=payload.url,
        local_path=payload.local_path,
        sort_order=max_order + 1,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return _serialize_draft_asset(asset)


@router.delete("/{draft_id}/assets/{asset_id}")
def delete_draft_asset(
    draft_id: int,
    asset_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    draft = db.get(AiDraft, draft_id)
    if draft is None or draft.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Draft not found")
    asset = db.scalars(select(DraftAsset).where(DraftAsset.id == asset_id, DraftAsset.draft_id == draft.id)).first()
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    db.delete(asset)
    db.commit()
    return {"id": asset_id, "status": "deleted"}


class DraftAssetUpdateRequest(BaseModel):
    url: Optional[str] = Field(default=None, max_length=2048)
    local_path: Optional[str] = Field(default=None, max_length=512)


@router.patch("/{draft_id}/assets/{asset_id}")
def update_draft_asset(
    draft_id: int,
    asset_id: int,
    payload: DraftAssetUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    draft = db.get(AiDraft, draft_id)
    if draft is None or draft.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Draft not found")
    asset = db.scalars(select(DraftAsset).where(DraftAsset.id == asset_id, DraftAsset.draft_id == draft.id)).first()
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    if payload.url is not None:
        asset.url = payload.url
    if payload.local_path is not None:
        asset.local_path = payload.local_path
    db.commit()
    db.refresh(asset)
    return _serialize_draft_asset(asset)


@router.put("/{draft_id}/assets/reorder")
def reorder_draft_assets(
    draft_id: int,
    payload: DraftAssetReorderRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    draft = db.get(AiDraft, draft_id)
    if draft is None or draft.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Draft not found")
    assets = db.scalars(select(DraftAsset).where(DraftAsset.draft_id == draft.id)).all()
    asset_map = {a.id: a for a in assets}
    for idx, aid in enumerate(payload.asset_ids):
        if aid in asset_map:
            asset_map[aid].sort_order = idx
    db.commit()
    return {"ok": True}

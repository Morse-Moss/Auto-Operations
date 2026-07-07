from __future__ import annotations

from typing import Any
from urllib.parse import urlparse, urlunparse

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.api.notes import _serialize_note_with_tags
from backend.app.core.database import get_db
from backend.app.core.deps import get_current_user
from backend.app.models import Note, NoteAsset, NoteComment, PlatformAccount, Tag, User, note_tags


router = APIRouter(prefix="/xhs/page-import", tags=["xhs-page-import"])


class VisibleCommentImport(BaseModel):
    comment_id: str = Field(default="", max_length=512)
    user_name: str = Field(default="", max_length=128)
    user_id: str = Field(default="", max_length=512)
    content: str = ""
    like_count: int = 0
    parent_comment_id: str = Field(default="", max_length=512)
    created_at_remote: str = Field(default="", max_length=64)
    raw: dict[str, Any] = Field(default_factory=dict)


class CurrentNoteImportRequest(BaseModel):
    note_id: str = Field(min_length=1, max_length=128)
    note_url: str = Field(default="", max_length=2048)
    title: str = Field(default="", max_length=512)
    content: str = ""
    author_name: str = Field(default="", max_length=128)
    author_id: str = Field(default="", max_length=128)
    tags: list[str] = Field(default_factory=list, max_length=100)
    image_urls: list[str] = Field(default_factory=list, max_length=50)
    video_url: str = Field(default="", max_length=4096)
    video_cover_url: str = Field(default="", max_length=4096)
    visible_comments: list[VisibleCommentImport] = Field(default_factory=list, max_length=50)
    raw: dict[str, Any] = Field(default_factory=dict)


def _unique_text(values: list[str], *, max_items: int | None = None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = str(value or "").strip()
        if not cleaned or cleaned in seen:
            continue
        result.append(cleaned)
        seen.add(cleaned)
        if max_items is not None and len(result) >= max_items:
            break
    return result


def _clean_note_url(note_url: str, note_id: str) -> str:
    raw_url = str(note_url or "").strip()
    if not raw_url:
        return ""
    try:
        parsed = urlparse(raw_url)
    except ValueError:
        return raw_url[:2048]
    path = parsed.path or f"/explore/{note_id}"
    if f"/explore/{note_id}" in path:
        path = f"/explore/{note_id}"
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))[:2048]


def _clean_external_id(value: str, *, max_length: int = 128) -> str:
    cleaned = str(value or "").strip().split("?", 1)[0].split("#", 1)[0].strip()
    return cleaned[:max_length]


def _get_or_create_page_import_account(db: Session, current_user: User) -> PlatformAccount:
    account = db.scalars(
        select(PlatformAccount).where(
            PlatformAccount.user_id == current_user.id,
            PlatformAccount.platform == "xhs",
            PlatformAccount.sub_type == "page_import",
        )
    ).first()
    if account is not None:
        return account
    account = PlatformAccount(
        user_id=current_user.id,
        platform="xhs",
        sub_type="page_import",
        external_user_id="current-page",
        nickname="Current page import",
        status="active",
    )
    db.add(account)
    db.flush()
    return account


def _sync_note_tags(db: Session, current_user: User, note: Note, tag_names: list[str]) -> None:
    db.execute(delete(note_tags).where(note_tags.c.note_id == note.id))
    for tag_name in _unique_text(tag_names, max_items=100):
        tag = db.scalars(
            select(Tag).where(Tag.user_id == current_user.id, Tag.name == tag_name)
        ).first()
        if tag is None:
            tag = Tag(user_id=current_user.id, name=tag_name, color="#111111")
            db.add(tag)
            db.flush()
        db.execute(note_tags.insert().values(note_id=note.id, tag_id=tag.id))


def _upsert_current_page_note(
    *,
    db: Session,
    current_user: User,
    payload: CurrentNoteImportRequest,
) -> tuple[Note, bool, int, int]:
    image_urls = _unique_text(payload.image_urls, max_items=50)
    video_url = str(payload.video_url or "").strip()
    if not image_urls and not video_url:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No media URLs found on the current note page",
        )

    account = _get_or_create_page_import_account(db, current_user)
    note = db.scalars(
        select(Note).where(
            Note.user_id == current_user.id,
            Note.platform == "xhs",
            Note.note_id == payload.note_id,
        )
    ).first()
    imported = note is None
    if note is None:
        note = Note(
            user_id=current_user.id,
            platform_account_id=account.id,
            platform="xhs",
            note_id=payload.note_id,
        )
        db.add(note)

    note.platform_account_id = account.id
    note.title = payload.title
    note.content = payload.content
    note.author_name = payload.author_name
    clean_note_url = _clean_note_url(payload.note_url, payload.note_id)
    raw_json = dict(payload.raw)
    if "source_url" in raw_json:
        raw_json["source_url"] = _clean_note_url(str(raw_json["source_url"]), payload.note_id)
    note.raw_json = {
        **raw_json,
        "note_url": clean_note_url,
        "author_id": _clean_external_id(payload.author_id),
        "tags": _unique_text(payload.tags, max_items=100),
        "image_urls": image_urls,
        "video_url": video_url,
        "video_cover_url": payload.video_cover_url,
        "page_import": {
            "mode": "manual_current_page",
            "asset_count": len(image_urls) + (1 if video_url else 0),
            "visible_comment_count": len(payload.visible_comments),
        },
    }
    db.flush()

    db.execute(delete(NoteAsset).where(NoteAsset.note_id == note.id))
    for index, image_url in enumerate(image_urls):
        db.add(NoteAsset(note_id=note.id, asset_type="image", url=image_url, local_path="", sort_order=index))
    if video_url:
        db.add(
            NoteAsset(
                note_id=note.id,
                asset_type="video",
                url=video_url,
                local_path="",
                sort_order=len(image_urls),
            )
        )

    _sync_note_tags(db, current_user, note, payload.tags)

    db.execute(delete(NoteComment).where(NoteComment.note_id == note.id))
    for comment in payload.visible_comments:
        content = str(comment.content or "").strip()
        if not content:
            continue
        db.add(
            NoteComment(
                note_id=note.id,
                comment_id=_clean_external_id(comment.comment_id) or f"visible-{len(content)}",
                user_name=comment.user_name,
                user_id=_clean_external_id(comment.user_id) or None,
                content=content,
                like_count=comment.like_count,
                parent_comment_id=_clean_external_id(comment.parent_comment_id) or None,
                created_at_remote=comment.created_at_remote or None,
                raw_json=comment.raw,
            )
        )

    db.commit()
    db.refresh(note)
    asset_count = len(image_urls) + (1 if video_url else 0)
    comment_count = len([comment for comment in payload.visible_comments if str(comment.content or "").strip()])
    return note, imported, asset_count, comment_count


@router.post("/current-note")
def import_current_note(
    payload: CurrentNoteImportRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note, imported, asset_count, comment_count = _upsert_current_page_note(
        db=db,
        current_user=current_user,
        payload=payload,
    )
    return {
        "imported": imported,
        "asset_count": asset_count,
        "comment_count": comment_count,
        "item": _serialize_note_with_tags(db, note),
    }

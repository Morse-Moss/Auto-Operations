from __future__ import annotations

from typing import Any, Callable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.models import Note, NoteAsset, NoteComment, NoteExclusion, PlatformAccount, Task, User
from backend.app.services.asset_downloader import download_asset_to_local
from backend.app.services.xhs_crawl_quality_service import (
    filter_saveable_notes,
    record_save_skipped_diagnostics,
    split_excluded_saveable_notes,
)


AssetDownloader = Callable[[str, int, str], str | None]


def raw_with_metrics(normalized: dict[str, Any]) -> dict[str, Any]:
    raw = normalized.get("raw") if isinstance(normalized.get("raw"), dict) else {}
    return {
        **raw,
        "note_url": normalized.get("note_url", ""),
        "tags": normalized.get("tags", []),
        "likes": normalized.get("likes", 0),
        "collects": normalized.get("collects", 0),
        "comments": normalized.get("comments", 0),
        "shares": normalized.get("shares", 0),
    }


def image_urls(normalized: dict[str, Any]) -> list[str]:
    urls = normalized.get("image_urls")
    if isinstance(urls, list) and urls:
        return [str(url) for url in urls if url]
    cover_url = normalized.get("cover_url")
    return [str(cover_url)] if cover_url else []


def video_url(normalized: dict[str, Any]) -> str:
    return str(normalized.get("video_url") or normalized.get("video_addr") or "")


def download_asset(url: str, user_id: int, asset_type: str) -> str | None:
    return download_asset_to_local(url, user_id, asset_type)


def save_with_quality_gate(
    db: Session,
    *,
    current_user: User,
    task: Task,
    account: PlatformAccount,
    normalized_items: list[dict[str, Any]],
    asset_downloader: AssetDownloader = download_asset,
    quality_evaluator: Callable[[dict[str, Any], object | None], dict[str, Any]] | None = None,
) -> tuple[list[Note], list[dict[str, Any]]]:
    remaining_items, excluded_items = split_excluded_saveable_notes(db, account, normalized_items)
    saveable_items, skipped_items = (
        filter_saveable_notes(remaining_items, quality_evaluator=quality_evaluator)
        if quality_evaluator is not None
        else filter_saveable_notes(remaining_items)
    )
    skipped_items.extend(excluded_items)
    if skipped_items:
        record_save_skipped_diagnostics(
            db,
            current_user=current_user,
            task=task,
            account=account,
            skipped_items=skipped_items,
        )
    saved_notes = save_normalized_notes(db, account, saveable_items, asset_downloader=asset_downloader) if saveable_items else []
    if skipped_items and not saveable_items:
        db.commit()
    return saved_notes, skipped_items


def save_normalized_notes(
    db: Session,
    account: PlatformAccount,
    normalized_items: list[dict[str, Any]],
    *,
    asset_downloader: AssetDownloader = download_asset,
) -> list[Note]:
    saved: list[Note] = []
    normalized_note_ids = [str(normalized.get("note_id") or "").strip() for normalized in normalized_items]
    unique_note_ids = [note_id for note_id in dict.fromkeys(normalized_note_ids) if note_id]
    excluded_note_ids = set(
        db.scalars(
            select(NoteExclusion.platform_note_id).where(
                NoteExclusion.user_id == account.user_id,
                NoteExclusion.platform == account.platform,
                NoteExclusion.platform_note_id.in_(unique_note_ids),
            )
        ).all()
    ) if unique_note_ids else set()
    for normalized in normalized_items:
        note_id = str(normalized.get("note_id") or "").strip()
        if not note_id or note_id in excluded_note_ids:
            continue
        note = db.scalars(
            select(Note).where(
                Note.user_id == account.user_id,
                Note.platform == account.platform,
                Note.note_id == note_id,
            )
        ).first()
        if note is None:
            note = Note(user_id=account.user_id, platform_account_id=account.id, platform=account.platform, note_id=note_id)
            db.add(note)
        note.title = str(normalized.get("title") or "")
        note.content = str(normalized.get("content") or "")
        note.author_name = str(normalized.get("author_name") or "")
        note.raw_json = raw_with_metrics(normalized)
        db.flush()
        db.execute(delete(NoteAsset).where(NoteAsset.note_id == note.id))
        for url in image_urls(normalized):
            local_name = asset_downloader(url, account.user_id, "image")
            db.add(NoteAsset(note_id=note.id, asset_type="image", url=url, local_path=local_name or ""))
        resolved_video_url = video_url(normalized)
        if resolved_video_url:
            local_name = asset_downloader(resolved_video_url, account.user_id, "video")
            db.add(NoteAsset(note_id=note.id, asset_type="video", url=resolved_video_url, local_path=local_name or ""))
        saved.append(note)

    db.commit()
    for note in saved:
        db.refresh(note)
    return saved


def save_note_comments(db: Session, note: Note, comments: list[dict[str, Any]]) -> None:
    if not comments:
        return
    db.execute(delete(NoteComment).where(NoteComment.note_id == note.id))
    for comment in comments:
        comment_id = str(comment.get("comment_id") or "").strip()
        if not comment_id:
            continue
        db.add(
            NoteComment(
                note_id=note.id,
                comment_id=comment_id,
                user_name=str(comment.get("user_name") or ""),
                user_id=comment.get("user_id"),
                content=str(comment.get("content") or ""),
                like_count=int(comment.get("like_count") or 0),
                parent_comment_id=comment.get("parent_comment_id"),
                created_at_remote=comment.get("created_at_remote"),
                raw_json=comment.get("raw_json"),
            )
        )
    db.commit()

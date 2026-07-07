from __future__ import annotations

import json
import time
from typing import Any, Generator, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.adapters.xhs.mappers import normalize_xhs_comment_payload
from backend.app.api.platforms.xhs.pc import (
    _get_owned_pc_account_cookies,
    _normalize_detail_payload,
    _normalize_search_item,
    get_xhs_pc_api_adapter_factory,
)
from backend.app.api.tasks import serialize_task
from backend.app.core.database import get_db
from backend.app.core.deps import get_current_user
from backend.app.models import CrawlDiagnostic, KeywordGroup, Note, PlatformAccount, Task, User
from backend.app.schemas.common import paginated
from backend.app.services import xhs_crawl_persistence_service as crawl_persistence
from backend.app.services import xhs_crawl_quality_service as crawl_quality
from backend.app.services.crawl_diagnostics import serialize_crawl_diagnostic
from backend.app.services.xhs_detail_recovery import (
    build_user_message,
    evaluate_detail_quality,
    is_xhs_rate_limit_signal,
    should_reject_short_explore_url,
)

router = APIRouter(prefix="/xhs/crawl", tags=["xhs-crawl"])


class CrawlSearchNotesRequest(BaseModel):
    account_id: int
    keyword: str = Field(min_length=1, max_length=120)
    page: int = Field(default=1, ge=1)
    save_to_library: bool = True
    fetch_comments: bool = False


class CrawlNoteUrlsRequest(BaseModel):
    account_id: int
    urls: list[str] = Field(min_length=1, max_length=50)
    save_to_library: bool = True
    fetch_comments: bool = False


class CrawlUserNotesRequest(BaseModel):
    account_id: int
    user_url: str = Field(min_length=1)
    save_to_library: bool = True


class DataCrawlRequest(BaseModel):
    account_id: int
    mode: Literal["note_urls", "search", "comments"]
    urls: list[str] = Field(default_factory=list, max_length=100)
    keyword: str = Field(default="", max_length=120)
    pages: int = Field(default=1, ge=1, le=20)
    max_notes: int = Field(default=20, ge=1, le=200)
    time_sleep: float = Field(default=0, ge=0, le=60)
    comment_sleep: float = Field(default=5, ge=0, le=120)
    fetch_comments: bool = False
    save_to_library: bool = True
    sort_type_choice: int = Field(default=0, ge=0, le=4)
    note_type: int = Field(default=0, ge=0, le=2)
    note_time: int = Field(default=0, ge=0, le=3)
    note_range: int = Field(default=0, ge=0, le=3)
    pos_distance: int = Field(default=0, ge=0, le=2)
    geo: str = ""


class KeywordGroupCrawlRequest(BaseModel):
    account_id: int
    keyword_group_id: int
    keyword_limit: int = Field(default=5, ge=1, le=20)
    max_notes_per_keyword: int = Field(default=5, ge=1, le=50)
    time_sleep: float = Field(default=1, ge=0, le=60)
    comment_sleep: float = Field(default=5, ge=0, le=120)
    fetch_comments: bool = False
    sort_type_choice: int = Field(default=0, ge=0, le=4)
    note_type: int = Field(default=0, ge=0, le=2)
    note_time: int = Field(default=0, ge=0, le=3)


def _serialize_note(note: Note) -> dict[str, Any]:
    return {
        "id": note.id,
        "platform": note.platform,
        "platform_account_id": note.platform_account_id,
        "note_id": note.note_id,
        "title": note.title,
        "content": note.content,
        "author_name": note.author_name,
        "raw_json": note.raw_json,
        "created_at": note.created_at.isoformat(),
    }


def _create_crawl_task(
    db: Session,
    current_user: User,
    crawl_type: str,
    payload: dict[str, Any],
) -> Task:
    task = Task(
        user_id=current_user.id,
        platform="xhs",
        task_type="crawl",
        status="running",
        progress=10,
        payload={"crawl_type": crawl_type, **payload},
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _complete_task(db: Session, task: Task, payload: dict[str, Any]) -> Task:
    task.status = "completed"
    task.progress = 100
    task.payload = {**(task.payload or {}), **payload}
    db.commit()
    db.refresh(task)
    return task


def _fail_task(db: Session, task: Task, error: str) -> None:
    task.status = "failed"
    task.progress = 100
    task.payload = {**(task.payload or {}), "error": error}
    db.commit()


def _data_items(raw_payload: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_payload, dict):
        return []
    data = raw_payload.get("data") if isinstance(raw_payload.get("data"), dict) else raw_payload
    items = data.get("items") or data.get("notes") or data.get("list") or []
    return [item for item in items if isinstance(item, dict) and item.get("model_type") not in ("rec_query", "hot_query")]


def _raw_with_metrics(normalized: dict[str, Any]) -> dict[str, Any]:
    return crawl_persistence.raw_with_metrics(normalized)


def _image_urls(normalized: dict[str, Any]) -> list[str]:
    return crawl_persistence.image_urls(normalized)


def _video_url(normalized: dict[str, Any]) -> str:
    return crawl_persistence.video_url(normalized)


def _filter_saveable_notes(normalized_items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return crawl_quality.filter_saveable_notes(normalized_items, quality_evaluator=evaluate_detail_quality)


def _split_excluded_saveable_notes(
    db: Session,
    account: PlatformAccount,
    saveable_items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return crawl_quality.split_excluded_saveable_notes(db, account, saveable_items)


def _quality_item_fields(quality: dict[str, Any], *, saved: bool = False, save_diagnostic_kind: str | None = None) -> dict[str, Any]:
    return crawl_quality.quality_item_fields(quality, saved=saved, save_diagnostic_kind=save_diagnostic_kind)


def _diagnostic_severity(kind: str | None) -> str:
    return crawl_quality.diagnostic_severity(kind)


def _search_failure_kind(message: str, raw_payload: object | None) -> str:
    return crawl_quality.search_failure_kind(message, raw_payload)


def _search_failure_user_message(kind: str) -> str:
    return crawl_quality.search_failure_user_message(kind)


def _record_crawl_diagnostic(
    db: Session,
    *,
    current_user: User,
    task: Task,
    account: PlatformAccount,
    source: str,
    note: dict[str, Any] | None,
    stage: str,
    kind: str,
    message: str,
    user_message: str,
    recoverable: bool,
    raw_payload: object | None = None,
    note_url: str | None = None,
) -> None:
    crawl_quality.record_crawl_diagnostic(
        db,
        current_user=current_user,
        task=task,
        account=account,
        source=source,
        note=note,
        stage=stage,
        kind=kind,
        message=message,
        user_message=user_message,
        recoverable=recoverable,
        raw_payload=raw_payload,
        note_url=note_url,
    )


def _quality_from_short_url(url: str) -> dict[str, Any]:
    return crawl_quality.quality_from_short_url(url)


def _record_save_skipped_diagnostics(
    db: Session,
    *,
    current_user: User,
    task: Task,
    account: PlatformAccount,
    skipped_items: list[dict[str, Any]],
) -> None:
    crawl_quality.record_save_skipped_diagnostics(
        db,
        current_user=current_user,
        task=task,
        account=account,
        skipped_items=skipped_items,
    )


def _save_with_quality_gate(
    db: Session,
    *,
    current_user: User,
    task: Task,
    account: PlatformAccount,
    normalized_items: list[dict[str, Any]],
) -> tuple[list[Note], list[dict[str, Any]]]:
    return crawl_persistence.save_with_quality_gate(
        db,
        current_user=current_user,
        task=task,
        account=account,
        normalized_items=normalized_items,
        asset_downloader=_download_asset,
        quality_evaluator=evaluate_detail_quality,
    )


def _save_normalized_notes(
    db: Session,
    account: PlatformAccount,
    normalized_items: list[dict[str, Any]],
) -> list[Note]:
    return crawl_persistence.save_normalized_notes(db, account, normalized_items, asset_downloader=_download_asset)


def _save_note_comments(db: Session, note: Note, comments: list[dict[str, Any]]) -> None:
    crawl_persistence.save_note_comments(db, note, comments)


def _download_asset(url: str, user_id: int, asset_type: str) -> str | None:
    return crawl_persistence.download_asset(url, user_id, asset_type)


def _sleep_between_requests(seconds: float) -> None:
    if seconds > 0:
        time.sleep(min(seconds, 120))


def _is_comment_rate_limited(message: str) -> bool:
    return crawl_quality.is_comment_rate_limited(message)


def _comment_failure_status(message: str) -> str:
    return crawl_quality.comment_failure_status(message)


def _comment_skip_error() -> str:
    return crawl_quality.comment_skip_error()


def _platform_note_id_from_url(url: str) -> str:
    return crawl_quality.platform_note_id_from_url(url)


def _is_platform_note_id_excluded(db: Session, account: PlatformAccount, note_id: str) -> bool:
    return crawl_quality.is_platform_note_id_excluded(db, account, note_id)


def _is_normalized_note_excluded(db: Session, account: PlatformAccount, normalized: dict[str, Any]) -> bool:
    return crawl_quality.is_normalized_note_excluded(db, account, normalized)


def _record_excluded_crawl_diagnostic(
    db: Session,
    *,
    current_user: User,
    task: Task,
    account: PlatformAccount,
    source: str,
    note: dict[str, Any],
    note_url: str | None = None,
) -> None:
    crawl_quality.record_excluded_crawl_diagnostic(
        db,
        current_user=current_user,
        task=task,
        account=account,
        source=source,
        note=note,
        note_url=note_url,
    )


def _crawl_data_item(
    *,
    source: str,
    status: str,
    note: dict[str, Any] | None = None,
    comments: list[dict[str, Any]] | None = None,
    error: str = "",
    keyword: str = "",
    quality_status: str = "unknown",
    recoverable: bool = False,
    diagnostic_kind: str | None = None,
    save_diagnostic_kind: str | None = None,
    user_message: str = "",
    saved: bool = False,
    comment_status: str = "not_requested",
    comment_error: str = "",
) -> dict[str, Any]:
    return {
        "source": source,
        "status": status,
        "error": error,
        "keyword": keyword,
        "quality_status": quality_status,
        "recoverable": recoverable,
        "diagnostic_kind": diagnostic_kind,
        "save_diagnostic_kind": save_diagnostic_kind,
        "user_message": user_message,
        "saved": saved,
        "note": note,
        "comments": comments or [],
        "comment_count": len(comments or []),
        "comment_status": comment_status,
        "comment_error": comment_error,
    }


def _owned_pc_account(db: Session, current_user: User, account_id: int) -> PlatformAccount:
    account = db.get(PlatformAccount, account_id)
    if (
        account is None
        or account.user_id != current_user.id
        or account.platform != "xhs"
        or account.sub_type != "pc"
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    if account.status == "expired":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="小红书 PC 账号登录已过期，请重新登录或更新 Cookie 后再采集")
    return account


def _owned_keyword_group(db: Session, current_user: User, group_id: int) -> KeywordGroup:
    group = db.get(KeywordGroup, group_id)
    if group is None or group.user_id != current_user.id or group.platform != "xhs":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Keyword group not found")
    return group


def _summary_message(*, saved_count: int, skipped_count: int, rate_limited_count: int, missing_detail_count: int) -> str:
    return f"采集完成：保存 {saved_count} 条，跳过 {skipped_count} 条，访问频繁 {rate_limited_count} 条，详情缺失 {missing_detail_count} 条。"


@router.get("/diagnostics")
def list_crawl_diagnostics(
    task_id: int | None = None,
    stage: str | None = None,
    kind: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    statement = select(CrawlDiagnostic).where(CrawlDiagnostic.user_id == current_user.id)
    if task_id is not None:
        statement = statement.where(CrawlDiagnostic.task_id == task_id)
    if stage:
        statement = statement.where(CrawlDiagnostic.stage == stage)
    if kind:
        statement = statement.where(CrawlDiagnostic.kind == kind)
    diagnostics = db.scalars(statement.order_by(CrawlDiagnostic.created_at.desc(), CrawlDiagnostic.id.desc())).all()
    return paginated([serialize_crawl_diagnostic(diagnostic) for diagnostic in diagnostics], page, page_size)


@router.post("/search-notes")
def crawl_search_notes(
    payload: CrawlSearchNotesRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    adapter_factory=Depends(get_xhs_pc_api_adapter_factory),
):
    account = _owned_pc_account(db, current_user, payload.account_id)
    cookies = _get_owned_pc_account_cookies(db, current_user, payload.account_id)
    task = _create_crawl_task(
        db,
        current_user,
        "search_notes",
        {"account_id": account.id, "keyword": payload.keyword, "page": payload.page},
    )
    success, message, raw_payload = adapter_factory(cookies).search_note(payload.keyword, page=payload.page)
    if not success:
        _fail_task(db, task, message or "XHS search crawl failed")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=message or "XHS search crawl failed")

    normalized_items = [_normalize_search_item(item) for item in _data_items(raw_payload)]
    saved_notes: list[Note] = []
    skipped_items: list[dict[str, Any]] = []
    if payload.save_to_library:
        saved_notes, skipped_items = _save_with_quality_gate(
            db,
            current_user=current_user,
            task=task,
            account=account,
            normalized_items=normalized_items,
        )
    task = _complete_task(
        db,
        task,
        {
            "result_count": len(normalized_items),
            "saved_count": len(saved_notes),
            "skipped_low_quality_count": len(skipped_items),
        },
    )
    return {
        "task": serialize_task(task),
        "result_count": len(normalized_items),
        "saved_count": len(saved_notes),
        "skipped_low_quality_count": len(skipped_items),
        "skipped_items": skipped_items,
        "items": [_serialize_note(note) for note in saved_notes],
        "raw": raw_payload,
    }


@router.post("/note-urls")
def crawl_note_urls(
    payload: CrawlNoteUrlsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    adapter_factory=Depends(get_xhs_pc_api_adapter_factory),
):
    account = _owned_pc_account(db, current_user, payload.account_id)
    cookies = _get_owned_pc_account_cookies(db, current_user, payload.account_id)
    task = _create_crawl_task(
        db,
        current_user,
        "note_urls",
        {"account_id": account.id, "url_count": len(payload.urls)},
    )
    adapter = adapter_factory(cookies)
    normalized_items: list[dict[str, Any]] = []
    skipped_items: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for url in payload.urls:
        if should_reject_short_explore_url(url):
            quality = _quality_from_short_url(url)
            errors.append({"url": url, "error": quality["user_message"], "diagnostic_kind": quality["diagnostic_kind"]})
            _record_crawl_diagnostic(
                db,
                current_user=current_user,
                task=task,
                account=account,
                source=url,
                note={"note_url": url},
                stage="detail",
                kind="missing_xsec_token_short_explore",
                message="Short explore URL missing xsec_token",
                user_message=quality["user_message"],
                recoverable=False,
                raw_payload={},
                note_url=url,
            )
            continue
        success, message, raw_payload = adapter.get_note_info(url)
        if success:
            normalized_items.append(_normalize_detail_payload(raw_payload or {}, source_url=url))
        else:
            kind = "xhs_rate_limited" if is_xhs_rate_limit_signal(url=url, message=message) else "detail_api_failed"
            user_message = build_user_message(kind, "rate_limited" if kind == "xhs_rate_limited" else "detail_api_failed")
            errors.append({"url": url, "error": message or "XHS note detail crawl failed", "diagnostic_kind": kind})
            _record_crawl_diagnostic(
                db,
                current_user=current_user,
                task=task,
                account=account,
                source=url,
                note={"note_url": url},
                stage="detail",
                kind=kind,
                message=message or "XHS note detail crawl failed",
                user_message=user_message,
                recoverable=True,
                raw_payload=raw_payload or {},
                note_url=url,
            )
            if kind == "xhs_rate_limited":
                break

    saved_notes: list[Note] = []
    if payload.save_to_library:
        saved_notes, skipped_items = _save_with_quality_gate(
            db,
            current_user=current_user,
            task=task,
            account=account,
            normalized_items=normalized_items,
        )
    task = _complete_task(
        db,
        task,
        {
            "result_count": len(normalized_items),
            "saved_count": len(saved_notes),
            "skipped_low_quality_count": len(skipped_items),
            "errors": errors,
        },
    )
    return {
        "task": serialize_task(task),
        "result_count": len(normalized_items),
        "saved_count": len(saved_notes),
        "skipped_low_quality_count": len(skipped_items),
        "skipped_items": skipped_items,
        "errors": errors,
        "items": [_serialize_note(note) for note in saved_notes],
    }


@router.post("/user-notes")
def crawl_user_notes(
    payload: CrawlUserNotesRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    adapter_factory=Depends(get_xhs_pc_api_adapter_factory),
):
    account = _owned_pc_account(db, current_user, payload.account_id)
    cookies = _get_owned_pc_account_cookies(db, current_user, payload.account_id)
    task = _create_crawl_task(
        db,
        current_user,
        "user_notes",
        {"account_id": account.id, "user_url": payload.user_url},
    )
    success, message, raw_payload = adapter_factory(cookies).get_user_notes(payload.user_url)
    if not success:
        _fail_task(db, task, message or "XHS user notes crawl failed")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=message or "XHS user notes crawl failed")

    normalized_items = [_normalize_search_item(item) for item in _data_items(raw_payload)]
    saved_notes: list[Note] = []
    skipped_items: list[dict[str, Any]] = []
    if payload.save_to_library:
        saved_notes, skipped_items = _save_with_quality_gate(
            db,
            current_user=current_user,
            task=task,
            account=account,
            normalized_items=normalized_items,
        )
    task = _complete_task(
        db,
        task,
        {
            "result_count": len(normalized_items),
            "saved_count": len(saved_notes),
            "skipped_low_quality_count": len(skipped_items),
        },
    )
    return {
        "task": serialize_task(task),
        "result_count": len(normalized_items),
        "saved_count": len(saved_notes),
        "skipped_low_quality_count": len(skipped_items),
        "skipped_items": skipped_items,
        "items": [_serialize_note(note) for note in saved_notes],
        "raw": raw_payload,
    }


def _sse_event(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/keyword-group")
def crawl_keyword_group(
    payload: KeywordGroupCrawlRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    adapter_factory=Depends(get_xhs_pc_api_adapter_factory),
):
    account = _owned_pc_account(db, current_user, payload.account_id)
    group = _owned_keyword_group(db, current_user, payload.keyword_group_id)
    cookies = _get_owned_pc_account_cookies(db, current_user, payload.account_id)
    keywords = [str(keyword).strip() for keyword in (group.keywords or []) if str(keyword).strip()][: payload.keyword_limit]
    if not keywords:
        raise HTTPException(status_code=422, detail="Keyword group has no keywords")

    task = _create_crawl_task(
        db,
        current_user,
        "keyword_group",
        {
            "account_id": account.id,
            "keyword_group_id": group.id,
            "keyword_group_name": group.name,
            "keywords": keywords,
            "max_notes_per_keyword": payload.max_notes_per_keyword,
            "time_sleep": payload.time_sleep,
            "fetch_comments": payload.fetch_comments,
        },
    )
    task_id = task.id
    adapter = adapter_factory(cookies)

    def generate() -> Generator[str, None, None]:
        items: list[dict[str, Any]] = []
        seen_sources: set[str] = set()
        error_occurred = False
        should_stop = False
        saved_count = 0
        skipped_count = 0
        rate_limited_count = 0
        missing_detail_count = 0
        comments_rate_limited = False

        try:
            for keyword in keywords:
                if should_stop:
                    break
                yield _sse_event({"type": "progress", "message": f"正在采集「{keyword}」..."})
                success, message, raw_payload = adapter.search_note(
                    keyword,
                    page=1,
                    sort_type_choice=payload.sort_type_choice,
                    note_type=payload.note_type,
                    note_time=payload.note_time,
                    note_range=0,
                    pos_distance=0,
                    geo="",
                )
                if not success:
                    kind = _search_failure_kind(message or "", raw_payload)
                    skipped_count += 1
                    if kind == "xhs_rate_limited":
                        rate_limited_count += 1
                        should_stop = True
                    user_message = _search_failure_user_message(kind)
                    _record_crawl_diagnostic(
                        db,
                        current_user=current_user,
                        task=task,
                        account=account,
                        source=keyword,
                        note=None,
                        stage="search",
                        kind=kind,
                        message=message or "search failed",
                        user_message=user_message,
                        recoverable=kind != "xhs_account_expired",
                        raw_payload=raw_payload or {},
                    )
                    item = _crawl_data_item(
                        source=keyword,
                        status="failed",
                        error=user_message,
                        keyword=keyword,
                        quality_status="rate_limited" if kind == "xhs_rate_limited" else "account_expired" if kind == "xhs_account_expired" else "unknown",
                        diagnostic_kind=kind,
                        recoverable=kind != "xhs_account_expired",
                        user_message=user_message,
                    )
                    items.append(item)
                    yield _sse_event({"type": "item", "index": len(items) - 1, "item": item})
                    continue

                per_keyword_count = 0
                for raw_item in _data_items(raw_payload):
                    if per_keyword_count >= payload.max_notes_per_keyword or should_stop:
                        break
                    search_note = _normalize_search_item(raw_item)
                    note_url = str(search_note.get("note_url") or "")
                    source = note_url or str(search_note.get("note_id") or keyword)
                    if source in seen_sources:
                        continue
                    seen_sources.add(source)
                    per_keyword_count += 1

                    if not note_url or should_reject_short_explore_url(note_url):
                        quality = _quality_from_short_url(note_url or source)
                        skipped_count += 1
                        missing_detail_count += 1
                        _record_crawl_diagnostic(
                            db,
                            current_user=current_user,
                            task=task,
                            account=account,
                            source=source,
                            note=search_note,
                            stage="detail",
                            kind="missing_xsec_token_short_explore",
                            message="Search result missing stable detail URL or xsec_token",
                            user_message=quality["user_message"],
                            recoverable=False,
                            raw_payload=search_note.get("raw") if isinstance(search_note.get("raw"), dict) else {},
                            note_url=note_url or None,
                        )
                        item = _crawl_data_item(source=source, status="failed", note=search_note, error=quality["user_message"], keyword=keyword, **_quality_item_fields(quality))
                        items.append(item)
                        yield _sse_event({"type": "item", "index": len(items) - 1, "item": item})
                        _sleep_between_requests(payload.time_sleep)
                        continue

                    detail_success, detail_message, detail_payload = adapter.get_note_info(note_url)
                    if not detail_success:
                        kind = "xhs_rate_limited" if is_xhs_rate_limit_signal(url=note_url, message=detail_message) else "detail_api_failed"
                        quality = {
                            "quality_status": "rate_limited" if kind == "xhs_rate_limited" else "detail_api_failed",
                            "diagnostic_kind": kind,
                            "recoverable": True,
                            "user_message": build_user_message(kind, "rate_limited" if kind == "xhs_rate_limited" else "detail_api_failed"),
                            "can_save": False,
                        }
                        skipped_count += 1
                        if kind == "xhs_rate_limited":
                            rate_limited_count += 1
                            should_stop = True
                        else:
                            missing_detail_count += 1
                        _record_crawl_diagnostic(
                            db,
                            current_user=current_user,
                            task=task,
                            account=account,
                            source=source,
                            note=search_note,
                            stage="detail",
                            kind=kind,
                            message=detail_message or "detail failed",
                            user_message=quality["user_message"],
                            recoverable=True,
                            raw_payload=detail_payload or {},
                            note_url=note_url,
                        )
                        item = _crawl_data_item(source=source, status="failed", note=search_note, error=detail_message or "detail failed", keyword=keyword, **_quality_item_fields(quality))
                        items.append(item)
                        yield _sse_event({"type": "item", "index": len(items) - 1, "item": item})
                        _sleep_between_requests(payload.time_sleep)
                        continue

                    detail_note = _normalize_detail_payload(detail_payload or {}, source_url=note_url)
                    detail_note["note_url"] = detail_note.get("note_url") or note_url
                    quality = evaluate_detail_quality(detail_note, detail_payload)
                    detail_note.update(quality)
                    excluded_note = _is_normalized_note_excluded(db, account, detail_note)
                    if excluded_note:
                        quality = {**quality, "can_save": False}
                    comments_list: list[dict[str, Any]] = []
                    comment_status = "skipped_excluded" if excluded_note else "not_requested"
                    comment_error = "该笔记已标记废弃，本轮跳过评论抓取和保存。" if excluded_note else ""
                    if payload.fetch_comments and quality["can_save"]:
                        if comments_rate_limited:
                            comment_status = "skipped_rate_limited"
                            comment_error = _comment_skip_error()
                        else:
                            comment_success, comment_message, comment_payload = adapter.get_note_comments(note_url)
                            if comment_success:
                                comments_list = normalize_xhs_comment_payload(comment_payload)
                                comment_status = "success"
                            else:
                                comment_error = comment_message or "comment failed"
                                comment_status = _comment_failure_status(comment_error)
                                if comment_status == "rate_limited":
                                    comments_rate_limited = True
                                    yield _sse_event({"type": "progress", "message": "评论接口访问频繁，本轮已停止评论抓取，继续抓笔记详情。"})
                            _sleep_between_requests(payload.comment_sleep)

                    saved = False
                    if quality["can_save"]:
                        saved_notes = _save_normalized_notes(db, account, [detail_note])
                        saved = bool(saved_notes)
                        if saved and comments_list:
                            _save_note_comments(db, saved_notes[0], comments_list)
                        saved_count += 1 if saved else 0
                    else:
                        skipped_count += 1
                        if excluded_note:
                            _record_excluded_crawl_diagnostic(
                                db,
                                current_user=current_user,
                                task=task,
                                account=account,
                                source=source,
                                note=detail_note,
                                note_url=note_url,
                            )
                        else:
                            missing_detail_count += 1
                            _record_crawl_diagnostic(
                                db,
                                current_user=current_user,
                                task=task,
                                account=account,
                                source=source,
                                note=detail_note,
                                stage="detail",
                                kind=str(quality["diagnostic_kind"] or "empty_detail_payload"),
                                message=str(quality["diagnostic_kind"] or "low quality detail"),
                                user_message=quality["user_message"],
                                recoverable=bool(quality["recoverable"]),
                                raw_payload=detail_payload or {},
                                note_url=note_url,
                            )
                    item = _crawl_data_item(
                        source=source,
                        status="success" if saved else "partial",
                        note=detail_note,
                        comments=comments_list,
                        keyword=keyword,
                        comment_status=comment_status,
                        comment_error=comment_error,
                        **_quality_item_fields(quality, saved=saved),
                    )
                    items.append(item)
                    yield _sse_event({"type": "item", "index": len(items) - 1, "item": item})
                    _sleep_between_requests(payload.time_sleep)
        except Exception as exc:
            error_occurred = True
            yield _sse_event({"type": "error", "message": str(exc)})

        success_count = len([item for item in items if item["status"] == "success"])
        failed_count = len(items) - success_count
        summary_message = _summary_message(
            saved_count=saved_count,
            skipped_count=skipped_count,
            rate_limited_count=rate_limited_count,
            missing_detail_count=missing_detail_count,
        )
        try:
            if error_occurred:
                _fail_task(db, task, "partial failure")
            else:
                _complete_task(
                    db,
                    task,
                    {
                        "result_count": len(items),
                        "saved_count": saved_count,
                        "skipped_count": skipped_count,
                        "rate_limited_count": rate_limited_count,
                        "missing_detail_count": missing_detail_count,
                        "summary_message": summary_message,
                    },
                )
        except Exception:
            pass
        yield _sse_event({
            "type": "done",
            "task_id": task_id,
            "total": len(items),
            "success_count": success_count,
            "failed_count": failed_count,
            "saved_count": saved_count,
            "skipped_count": skipped_count,
            "rate_limited_count": rate_limited_count,
            "missing_detail_count": missing_detail_count,
            "summary_message": summary_message,
        })

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/data")
def crawl_data(
    payload: DataCrawlRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    adapter_factory=Depends(get_xhs_pc_api_adapter_factory),
):
    account = _owned_pc_account(db, current_user, payload.account_id)
    cookies = _get_owned_pc_account_cookies(db, current_user, payload.account_id)
    task = _create_crawl_task(
        db,
        current_user,
        f"data_{payload.mode}",
        {
            "account_id": account.id,
            "mode": payload.mode,
            "keyword": payload.keyword,
            "url_count": len(payload.urls),
            "pages": payload.pages,
            "time_sleep": payload.time_sleep,
            "comment_sleep": payload.comment_sleep,
        },
    )
    task_id = task.id
    adapter = adapter_factory(cookies)

    def generate() -> Generator[str, None, None]:
        items: list[dict[str, Any]] = []
        normalized_for_save: list[dict[str, Any]] = []
        saved_count = 0
        skipped_count = 0
        error_occurred = False
        comments_rate_limited = False

        try:
            if payload.mode == "note_urls":
                for index, url in enumerate(payload.urls):
                    if should_reject_short_explore_url(url):
                        quality = _quality_from_short_url(url)
                        _record_crawl_diagnostic(
                            db,
                            current_user=current_user,
                            task=task,
                            account=account,
                            source=url,
                            note={"note_url": url},
                            stage="detail",
                            kind="missing_xsec_token_short_explore",
                            message="Short explore URL missing xsec_token",
                            user_message=quality["user_message"],
                            recoverable=False,
                            raw_payload={},
                            note_url=url,
                        )
                        if payload.save_to_library:
                            skipped_count += 1
                        item = _crawl_data_item(source=url, status="failed", error=quality["user_message"], **_quality_item_fields(quality))
                        items.append(item)
                        yield _sse_event({"type": "item", "index": len(items) - 1, "item": item})
                        if index < len(payload.urls) - 1:
                            _sleep_between_requests(payload.time_sleep)
                        continue

                    success, message, raw_payload = adapter.get_note_info(url)
                    if success:
                        note = _normalize_detail_payload(raw_payload or {}, source_url=url)
                        quality = evaluate_detail_quality(note, raw_payload)
                        note.update(quality)
                        normalized_for_save.append(note)
                        excluded_note = _is_normalized_note_excluded(db, account, note)
                        if excluded_note:
                            quality = {**quality, "can_save": False}
                        comments_list: list[dict[str, Any]] = []
                        comment_status = "skipped_excluded" if excluded_note else "not_requested"
                        comment_error = "该笔记已标记废弃，本轮跳过评论抓取和保存。" if excluded_note else ""
                        if payload.fetch_comments and quality["can_save"]:
                            if comments_rate_limited:
                                comment_status = "skipped_rate_limited"
                                comment_error = _comment_skip_error()
                            else:
                                cs, cm, cp = adapter.get_note_comments(url)
                                if cs:
                                    comments_list = normalize_xhs_comment_payload(cp)
                                    comment_status = "success"
                                else:
                                    comment_error = cm or "comment crawl failed"
                                    comment_status = _comment_failure_status(comment_error)
                                    if comment_status == "rate_limited":
                                        comments_rate_limited = True
                                        yield _sse_event({"type": "progress", "message": "评论接口访问频繁，本轮已停止评论抓取，继续抓笔记详情。"})
                                _sleep_between_requests(payload.comment_sleep)
                        if not quality["can_save"]:
                            if excluded_note:
                                _record_excluded_crawl_diagnostic(
                                    db,
                                    current_user=current_user,
                                    task=task,
                                    account=account,
                                    source=url,
                                    note=note,
                                    note_url=url,
                                )
                            else:
                                _record_crawl_diagnostic(
                                    db,
                                    current_user=current_user,
                                    task=task,
                                    account=account,
                                    source=url,
                                    note=note,
                                    stage="detail",
                                    kind=str(quality["diagnostic_kind"] or "empty_detail_payload"),
                                    message=str(quality["diagnostic_kind"] or "low quality detail"),
                                    user_message=quality["user_message"],
                                    recoverable=bool(quality["recoverable"]),
                                    raw_payload=raw_payload or {},
                                    note_url=url,
                                )
                        saved = False
                        if payload.save_to_library and quality["can_save"]:
                            saved_notes = _save_normalized_notes(db, account, [note])
                            saved = bool(saved_notes)
                            if saved and comments_list:
                                _save_note_comments(db, saved_notes[0], comments_list)
                            if saved:
                                saved_count += 1
                            else:
                                skipped_count += 1
                        elif payload.save_to_library and not quality["can_save"]:
                            skipped_count += 1
                        item = _crawl_data_item(
                            source=url,
                            status="success" if saved or (quality["can_save"] and not payload.save_to_library) else "partial",
                            note=note,
                            comments=comments_list,
                            comment_status=comment_status,
                            comment_error=comment_error,
                            **_quality_item_fields(quality, saved=saved),
                        )
                    else:
                        kind = "xhs_rate_limited" if is_xhs_rate_limit_signal(url=url, message=message) else "detail_api_failed"
                        quality = {
                            "quality_status": "rate_limited" if kind == "xhs_rate_limited" else "detail_api_failed",
                            "diagnostic_kind": kind,
                            "recoverable": True,
                            "user_message": build_user_message(kind, "rate_limited" if kind == "xhs_rate_limited" else "detail_api_failed"),
                            "can_save": False,
                        }
                        _record_crawl_diagnostic(
                            db,
                            current_user=current_user,
                            task=task,
                            account=account,
                            source=url,
                            note={"note_url": url},
                            stage="detail",
                            kind=kind,
                            message=message or "detail crawl failed",
                            user_message=quality["user_message"],
                            recoverable=True,
                            raw_payload=raw_payload or {},
                            note_url=url,
                        )
                        if payload.save_to_library:
                            skipped_count += 1
                        item = _crawl_data_item(source=url, status="failed", error=message or "detail crawl failed", **_quality_item_fields(quality))
                        if kind == "xhs_rate_limited":
                            items.append(item)
                            yield _sse_event({"type": "item", "index": len(items) - 1, "item": item})
                            break
                    items.append(item)
                    yield _sse_event({"type": "item", "index": len(items) - 1, "item": item})
                    if index < len(payload.urls) - 1:
                        _sleep_between_requests(payload.time_sleep)

            elif payload.mode == "comments":
                for index, url in enumerate(payload.urls):
                    platform_note_id = _platform_note_id_from_url(url)
                    if platform_note_id and _is_platform_note_id_excluded(db, account, platform_note_id):
                        skip_error = "该笔记已标记废弃，本轮跳过评论抓取和保存。"
                        item = _crawl_data_item(source=url, status="partial", error=skip_error, comment_status="skipped_excluded", comment_error=skip_error)
                        skipped_count += 1
                        _record_excluded_crawl_diagnostic(
                            db,
                            current_user=current_user,
                            task=task,
                            account=account,
                            source=url,
                            note={"note_id": platform_note_id, "note_url": url},
                            note_url=url,
                        )
                    elif comments_rate_limited:
                        skip_error = _comment_skip_error()
                        item = _crawl_data_item(source=url, status="failed", error=skip_error, comment_status="skipped_rate_limited", comment_error=skip_error)
                    else:
                        success, message, raw_payload = adapter.get_note_comments(url)
                        if success:
                            item = _crawl_data_item(source=url, status="success", comments=normalize_xhs_comment_payload(raw_payload), comment_status="success")
                        else:
                            comment_error = message or "comment crawl failed"
                            comment_status = _comment_failure_status(comment_error)
                            item = _crawl_data_item(source=url, status="failed", error=comment_error, comment_status=comment_status, comment_error=comment_error)
                            if comment_status == "rate_limited":
                                comments_rate_limited = True
                                yield _sse_event({"type": "progress", "message": "评论接口访问频繁，本轮已停止评论抓取。"})
                        _sleep_between_requests(payload.comment_sleep)
                    items.append(item)
                    yield _sse_event({"type": "item", "index": len(items) - 1, "item": item})
                    if index < len(payload.urls) - 1:
                        _sleep_between_requests(payload.time_sleep)

            else:
                if not payload.keyword.strip():
                    yield _sse_event({"type": "error", "message": "Keyword is required"})
                    return
                seen_urls: list[str] = []
                stop_search_pages = False
                for page in range(1, payload.pages + 1):
                    success, message, raw_payload = adapter.search_note(
                        payload.keyword, page=page,
                        sort_type_choice=payload.sort_type_choice,
                        note_type=payload.note_type,
                        note_time=payload.note_time,
                        note_range=payload.note_range,
                        pos_distance=payload.pos_distance,
                        geo=payload.geo,
                    )
                    if not success:
                        if payload.save_to_library:
                            skipped_count += 1
                        item = _crawl_data_item(source=f"page:{page}", status="failed", error=message or "search failed")
                        items.append(item)
                        yield _sse_event({"type": "item", "index": len(items) - 1, "item": item})
                        break
                    yield _sse_event({"type": "progress", "message": f"搜索第 {page} 页完成，开始获取详情..."})
                    for raw_item in _data_items(raw_payload):
                        if len(items) >= payload.max_notes:
                            break
                        search_note = _normalize_search_item(raw_item)
                        note_url = search_note.get("note_url") or ""
                        source = note_url or str(search_note.get("note_id") or f"page:{page}")
                        if source in seen_urls:
                            continue
                        seen_urls.append(source)
                        detail_note = search_note
                        if note_url:
                            ds, dm, dp = adapter.get_note_info(note_url)
                            if ds:
                                detail_note = _normalize_detail_payload(dp or {}, source_url=note_url)
                                detail_note["note_url"] = detail_note.get("note_url") or note_url
                            else:
                                kind = "xhs_rate_limited" if is_xhs_rate_limit_signal(url=note_url, message=dm) else "detail_api_failed"
                                quality = {
                                    "quality_status": "rate_limited" if kind == "xhs_rate_limited" else "detail_api_failed",
                                    "diagnostic_kind": kind,
                                    "recoverable": True,
                                    "user_message": build_user_message(kind, "rate_limited" if kind == "xhs_rate_limited" else "detail_api_failed"),
                                    "can_save": False,
                                }
                                _record_crawl_diagnostic(
                                    db,
                                    current_user=current_user,
                                    task=task,
                                    account=account,
                                    source=source,
                                    note=search_note,
                                    stage="detail",
                                    kind=kind,
                                    message=dm or "detail failed",
                                    user_message=quality["user_message"],
                                    recoverable=True,
                                    raw_payload=dp or {},
                                    note_url=note_url,
                                )
                                if payload.save_to_library:
                                    skipped_count += 1
                                item = _crawl_data_item(source=source, status="failed", note=search_note, error=dm or "detail failed", **_quality_item_fields(quality))
                                items.append(item)
                                yield _sse_event({"type": "item", "index": len(items) - 1, "item": item})
                                _sleep_between_requests(payload.time_sleep)
                                if kind == "xhs_rate_limited":
                                    stop_search_pages = True
                                    break
                                continue
                        quality = evaluate_detail_quality(detail_note, detail_note.get("raw") if isinstance(detail_note.get("raw"), dict) else None)
                        detail_note.update(quality)
                        excluded_note = _is_normalized_note_excluded(db, account, detail_note)
                        if excluded_note:
                            quality = {**quality, "can_save": False}
                        comments_list = []
                        comment_status = "skipped_excluded" if excluded_note else "not_requested"
                        comment_error = "该笔记已标记废弃，本轮跳过评论抓取和保存。" if excluded_note else ""
                        if payload.fetch_comments and note_url and quality["can_save"]:
                            if comments_rate_limited:
                                comment_status = "skipped_rate_limited"
                                comment_error = _comment_skip_error()
                            else:
                                cs, cm, cp = adapter.get_note_comments(note_url)
                                if cs:
                                    comments_list = normalize_xhs_comment_payload(cp)
                                    comment_status = "success"
                                else:
                                    comment_error = cm or "comment failed"
                                    comment_status = _comment_failure_status(comment_error)
                                    if comment_status == "rate_limited":
                                        comments_rate_limited = True
                                        yield _sse_event({"type": "progress", "message": "评论接口访问频繁，本轮已停止评论抓取，继续抓笔记详情。"})
                                _sleep_between_requests(payload.comment_sleep)
                        if not quality["can_save"]:
                            if excluded_note:
                                _record_excluded_crawl_diagnostic(
                                    db,
                                    current_user=current_user,
                                    task=task,
                                    account=account,
                                    source=source,
                                    note=detail_note,
                                    note_url=note_url,
                                )
                            else:
                                _record_crawl_diagnostic(
                                    db,
                                    current_user=current_user,
                                    task=task,
                                    account=account,
                                    source=source,
                                    note=detail_note,
                                    stage="detail",
                                    kind=str(quality["diagnostic_kind"] or "empty_detail_payload"),
                                    message=str(quality["diagnostic_kind"] or "low quality detail"),
                                    user_message=quality["user_message"],
                                    recoverable=bool(quality["recoverable"]),
                                    raw_payload=detail_note.get("raw") if isinstance(detail_note.get("raw"), dict) else {},
                                    note_url=note_url,
                                )
                        normalized_for_save.append(detail_note)
                        saved = False
                        if payload.save_to_library and quality["can_save"]:
                            saved_notes = _save_normalized_notes(db, account, [detail_note])
                            saved = bool(saved_notes)
                            if saved and comments_list:
                                _save_note_comments(db, saved_notes[0], comments_list)
                            if saved:
                                saved_count += 1
                            else:
                                skipped_count += 1
                        elif payload.save_to_library and not quality["can_save"]:
                            skipped_count += 1
                        item = _crawl_data_item(
                            source=source,
                            status="success" if saved or (quality["can_save"] and not payload.save_to_library) else "partial",
                            note=detail_note,
                            comments=comments_list,
                            comment_status=comment_status,
                            comment_error=comment_error,
                            **_quality_item_fields(quality, saved=saved),
                        )
                        items.append(item)
                        yield _sse_event({"type": "item", "index": len(items) - 1, "item": item})
                        _sleep_between_requests(payload.time_sleep)
                    if stop_search_pages or len(items) >= payload.max_notes:
                        break
                    data = (raw_payload or {}).get("data") or {}
                    if not data.get("has_more", False):
                        break

        except Exception as exc:
            error_occurred = True
            yield _sse_event({"type": "error", "message": str(exc)})

        success_count = len([i for i in items if i["status"] == "success"])
        failed_count = len(items) - success_count
        comment_rate_limited_count = len([i for i in items if i.get("comment_status") == "rate_limited"])
        comment_skipped_count = len([i for i in items if i.get("comment_status") == "skipped_rate_limited"])
        summary_message = f"采集完成：保存 {saved_count} 条，跳过 {skipped_count} 条。"
        try:
            if error_occurred:
                _fail_task(db, task, "partial failure")
            else:
                _complete_task(
                    db,
                    task,
                    {
                        "result_count": success_count,
                        "failed_count": failed_count,
                        "saved_count": saved_count,
                        "skipped_count": skipped_count,
                        "comment_rate_limited_count": comment_rate_limited_count,
                        "comment_skipped_count": comment_skipped_count,
                        "summary_message": summary_message,
                    },
                )
        except Exception:
            pass

        yield _sse_event({
            "type": "done",
            "task_id": task_id,
            "total": len(items),
            "success_count": success_count,
            "failed_count": failed_count,
            "saved_count": saved_count,
            "skipped_count": skipped_count,
            "comment_rate_limited_count": comment_rate_limited_count,
            "comment_skipped_count": comment_skipped_count,
            "summary_message": summary_message,
        })

    return StreamingResponse(generate(), media_type="text/event-stream")

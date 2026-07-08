from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.core.security import decrypt_text
from backend.app.core.time import shanghai_now
from backend.app.models import (
    AccountCookieVersion,
    DataAcquisitionCandidate,
    DataAcquisitionRun,
    Note,
    NoteAsset,
    NoteSourceSnapshot,
    PlatformAccount,
    Task,
    User,
)
from backend.app.services import huitun_live_note_source
from backend.app.services.platform_data_account_service import (
    get_platform_data_account_cookie_text,
    record_note_search_usage,
)
from backend.app.services.usage_quota_service import get_or_create_default_tenant_context

ACQUISITION_SOURCE = "huitun"
SOURCE_MODE = "live_account"
SUPPORTED_ACQUISITION_TYPE = "note_search"
NOTE_SEARCH_DEFAULT_LIMIT = 20
NOTE_SEARCH_MAX_LIMIT = 100
FAILURE_USER_MESSAGE = "本次数据获取失败，任务已停止。"
MISSING_DATA_ACCOUNT_MESSAGE = "数据账号未配置，请让管理员完成登录后再重试。"
EXPIRED_DATA_ACCOUNT_MESSAGE = "数据账号登录状态已过期，请让管理员重新登录后再重试。"
NETWORK_FAILURE_MESSAGE = "笔记数据网络请求失败，任务已停止，请稍后低频重试。"
STRUCTURE_CHANGED_MESSAGE = "笔记数据结构变化，任务已停止，请联系管理员检查采集配置。"


def data_acquisition_failure_user_message(error_message: str) -> str:
    message = str(error_message or "")
    if "数据账号未配置" in message:
        return MISSING_DATA_ACCOUNT_MESSAGE
    if "数据账号登录状态已过期" in message:
        return EXPIRED_DATA_ACCOUNT_MESSAGE
    if "网络请求失败" in message or "HTTP 400" in message:
        return NETWORK_FAILURE_MESSAGE
    if "structure changed" in message or "结构" in message:
        return STRUCTURE_CHANGED_MESSAGE
    return FAILURE_USER_MESSAGE


def _latest_cookie_text(db: Session, current_user: User, account_id: int | None) -> str:
    if account_id is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="请选择数据账号。")
    account = db.get(PlatformAccount, account_id)
    if account is None or account.user_id != current_user.id or account.platform != "huitun" or account.sub_type != "main":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据账号不存在。")
    if account.status != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="数据账号登录状态已过期，请重新登录。")
    cookie_version = db.scalars(
        select(AccountCookieVersion)
        .where(AccountCookieVersion.platform_account_id == account.id)
        .order_by(AccountCookieVersion.created_at.desc())
    ).first()
    if cookie_version is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="数据账号登录状态已过期，请重新登录。")
    return decrypt_text(cookie_version.encrypted_cookies)


def _int_param(params: dict[str, Any], key: str, default: int, min_value: int, max_value: int) -> int:
    value = params.get(key, default)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(min_value, min(parsed, max_value))


def _text_param(params: dict[str, Any], key: str, default: str = "") -> str:
    value = params.get(key, default)
    return str(value or "").strip()


def _candidate_expiry() -> Any:
    return shanghai_now() + timedelta(days=30)


def _create_task(db: Session, current_user: User, payload: dict[str, Any]) -> Task:
    now = shanghai_now()
    task = Task(
        user_id=current_user.id,
        platform="xhs",
        task_type="data_acquisition_note_search",
        status="running",
        progress=0,
        payload=payload,
        started_at=now,
        max_retries=0,
    )
    db.add(task)
    db.flush()
    return task


def _row_asset_urls(row: dict[str, Any]) -> list[str]:
    values = row.get("asset_urls") or []
    if not isinstance(values, list):
        values = []
    if row.get("cover_url"):
        values = [str(row["cover_url"]), *[str(value) for value in values]]
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = str(value or "").strip()
        if cleaned and cleaned not in seen:
            result.append(cleaned)
            seen.add(cleaned)
    return result


def _create_candidate(
    db: Session,
    *,
    current_user: User,
    run: DataAcquisitionRun,
    row: dict[str, Any],
    keyword: str,
) -> DataAcquisitionCandidate:
    candidate = DataAcquisitionCandidate(
        run_id=run.id,
        user_id=current_user.id,
        platform="xhs",
        candidate_type="note",
        source=ACQUISITION_SOURCE,
        external_id=str(row.get("external_id") or row.get("platform_note_id") or ""),
        platform_note_id=str(row.get("platform_note_id") or ""),
        original_url=str(row.get("original_url") or ""),
        title=str(row.get("title") or ""),
        content_excerpt=str(row.get("content_excerpt") or ""),
        author_name=str(row.get("author_name") or ""),
        cover_url=str(row.get("cover_url") or ""),
        asset_urls_json=_row_asset_urls(row),
        publish_time=str(row.get("publish_time") or "") or None,
        update_time=str(row.get("update_time") or "") or None,
        rank_index=int(row.get("rank_index") or 0),
        category=str(row.get("category") or ""),
        tags_json=row.get("tags") if isinstance(row.get("tags"), list) else [],
        metrics_json=row.get("metrics") if isinstance(row.get("metrics"), dict) else {},
        raw_json={
            "source": ACQUISITION_SOURCE,
            "keyword": keyword,
            "video_url": row.get("video_url") or "",
            "payload": row.get("raw") if isinstance(row.get("raw"), dict) else {},
        },
        status="pending",
        expires_at=_candidate_expiry(),
    )
    db.add(candidate)
    return candidate


def create_note_search_run(
    *,
    db: Session,
    current_user: User,
    account_id: int | None,
    params: dict[str, Any],
    note_source: Any = huitun_live_note_source,
    rerun_of_run_id: int | None = None,
) -> tuple[DataAcquisitionRun, list[DataAcquisitionCandidate]]:
    keyword = _text_param(params, "keyword")
    if not keyword:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="请输入关键词。")
    requested_limit = _int_param(params, "limit", NOTE_SEARCH_DEFAULT_LIMIT, 1, 500)
    effective_limit = min(requested_limit, NOTE_SEARCH_MAX_LIMIT)
    public_params = {
        "keyword": keyword,
        "limit": requested_limit,
        "sort": _text_param(params, "sort", "interaction") or "interaction",
        "note_type": _text_param(params, "note_type", "all") or "all",
    }
    task = _create_task(db, current_user, {"acquisition_type": SUPPORTED_ACQUISITION_TYPE, "params": public_params})
    now = shanghai_now()
    run = DataAcquisitionRun(
        task_id=task.id,
        user_id=current_user.id,
        account_id=account_id,
        platform="xhs",
        acquisition_type=SUPPORTED_ACQUISITION_TYPE,
        source=ACQUISITION_SOURCE,
        source_mode=SOURCE_MODE,
        status="running",
        requested_limit=requested_limit,
        effective_limit=effective_limit,
        params_json=public_params,
        admin_debug_json={"source": ACQUISITION_SOURCE, "source_mode": SOURCE_MODE, "endpoint_key": "note.searchV2"},
        rerun_of_run_id=rerun_of_run_id,
        started_at=now,
        expires_at=_candidate_expiry(),
    )
    db.add(run)
    db.flush()
    task.payload = {
        **(task.payload or {}),
        "data_acquisition_run_id": run.id,
        "data_acquisition_url": f"/platforms/xhs/crawler?run_id={run.id}",
    }

    candidates: list[DataAcquisitionCandidate] = []
    try:
        platform_account, cookie_text = get_platform_data_account_cookie_text(db, account_id)
        run.account_id = platform_account.id
        rows = note_source.search_notes(
            cookie_text,
            keyword,
            effective_limit,
            sort=public_params["sort"],
            note_type=public_params["note_type"],
        )
        for row in rows:
            candidates.append(_create_candidate(db, current_user=current_user, run=run, row=row, keyword=keyword))
        task.status = "completed"
        task.progress = 100
        task.finished_at = shanghai_now()
        run.status = "completed"
        run.finished_at = task.finished_at
        tenant_context = get_or_create_default_tenant_context(db, current_user.id, commit=False)
        record_note_search_usage(
            db,
            tenant_id=tenant_context.tenant.id,
            user_id=current_user.id,
            task_id=task.id,
            run_id=run.id,
            keyword=keyword,
            limit=effective_limit,
        )
        db.commit()
    except Exception as exc:
        task.status = "failed"
        task.progress = 100
        task.error_type = "data_acquisition_failed"
        task.finished_at = shanghai_now()
        run.status = "failed"
        run.error_code = "note_search_failed"
        run.error_message = str(exc)
        debug = dict(run.admin_debug_json or {})
        debug["stage"] = "note_search"
        debug["error_message"] = str(exc)
        run.admin_debug_json = debug
        run.finished_at = task.finished_at
        db.commit()
        candidates = []

    db.refresh(run)
    for candidate in candidates:
        db.refresh(candidate)
    return run, candidates


def serialize_run(
    run: DataAcquisitionRun,
    candidates: list[DataAcquisitionCandidate] | None = None,
    *,
    candidate_count: int | None = None,
    include_admin_debug: bool = False,
) -> dict[str, Any]:
    resolved_candidate_count = len(candidates) if candidates is not None else (candidate_count or 0)
    result: dict[str, Any] = {
        "id": run.id,
        "task_id": run.task_id,
        "platform": run.platform,
        "acquisition_type": run.acquisition_type,
        "status": run.status,
        "requested_limit": run.requested_limit,
        "effective_limit": run.effective_limit,
        "params": run.params_json or {},
        "candidate_count": resolved_candidate_count,
        "user_message": data_acquisition_failure_user_message(run.error_message) if run.status == "failed" else "",
        "created_at": run.created_at.isoformat(),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "cancellation_requested": run.cancellation_requested,
    }
    if candidates is not None:
        result["candidates"] = [serialize_candidate(candidate) for candidate in candidates]
    if include_admin_debug:
        result["source"] = run.source
        result["source_mode"] = run.source_mode
        result["admin_debug"] = run.admin_debug_json or {}
        result["error_code"] = run.error_code
        result["error_message"] = run.error_message
    return result


def serialize_candidate(candidate: DataAcquisitionCandidate, *, include_admin_debug: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": candidate.id,
        "run_id": candidate.run_id,
        "platform": candidate.platform,
        "candidate_type": candidate.candidate_type,
        "platform_note_id": candidate.platform_note_id,
        "original_url": candidate.original_url,
        "title": candidate.title,
        "content_excerpt": candidate.content_excerpt,
        "author_name": candidate.author_name,
        "cover_url": candidate.cover_url,
        "asset_urls": candidate.asset_urls_json or [],
        "publish_time": candidate.publish_time,
        "update_time": candidate.update_time,
        "rank_index": candidate.rank_index,
        "category": candidate.category,
        "tags": candidate.tags_json or [],
        "metrics": candidate.metrics_json or {},
        "status": candidate.status,
        "imported_note_id": candidate.imported_note_id,
        "decision_reason_code": candidate.decision_reason_code,
        "decision_reason_text": candidate.decision_reason_text,
        "created_at": candidate.created_at.isoformat(),
        "updated_at": candidate.updated_at.isoformat(),
        "expires_at": candidate.expires_at.isoformat(),
    }
    if include_admin_debug:
        result["source"] = candidate.source
        result["raw_json"] = candidate.raw_json or {}
    return result


def get_owned_candidates(db: Session, current_user: User, candidate_ids: list[int]) -> list[DataAcquisitionCandidate]:
    unique_ids = list(dict.fromkeys(candidate_ids))
    candidates = db.scalars(
        select(DataAcquisitionCandidate)
        .where(DataAcquisitionCandidate.id.in_(unique_ids), DataAcquisitionCandidate.user_id == current_user.id)
        .order_by(DataAcquisitionCandidate.id.asc())
    ).all()
    if len(candidates) != len(unique_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="候选不存在。")
    by_id = {candidate.id: candidate for candidate in candidates}
    return [by_id[candidate_id] for candidate_id in unique_ids]


def _find_existing_note(db: Session, current_user: User, candidate: DataAcquisitionCandidate) -> Note | None:
    if candidate.platform_note_id:
        existing = db.scalars(
            select(Note).where(
                Note.user_id == current_user.id,
                Note.platform == candidate.platform,
                Note.note_id == candidate.platform_note_id,
            )
        ).first()
        if existing is not None:
            return existing
    if candidate.title and candidate.author_name and candidate.publish_time:
        return db.scalars(
            select(Note).where(
                Note.user_id == current_user.id,
                Note.platform == candidate.platform,
                Note.title == candidate.title,
                Note.author_name == candidate.author_name,
            )
        ).first()
    return None


def _note_raw_from_candidate(candidate: DataAcquisitionCandidate) -> dict[str, Any]:
    raw = candidate.raw_json or {}
    payload = raw.get("payload") if isinstance(raw.get("payload"), dict) else {}
    result = dict(payload)
    result.update(
        {
            "source": "data_acquisition",
            "cover_url": candidate.cover_url,
            "asset_urls": candidate.asset_urls_json or [],
            "video_url": raw.get("video_url") or payload.get("videoUrl") or payload.get("video_url") or "",
            "note_url": candidate.original_url,
            "liked_count": (candidate.metrics_json or {}).get("like_count", 0),
            "collected_count": (candidate.metrics_json or {}).get("collect_count", 0),
            "comment_count": (candidate.metrics_json or {}).get("comment_count", 0),
            "share_count": (candidate.metrics_json or {}).get("share_count", 0),
            "data_acquisition": {
                "run_id": candidate.run_id,
                "candidate_id": candidate.id,
                "original_url": candidate.original_url,
                "metrics": candidate.metrics_json or {},
            },
        }
    )
    return result


def import_candidates(
    *,
    db: Session,
    current_user: User,
    candidate_ids: list[int],
) -> list[Note]:
    candidates = get_owned_candidates(db, current_user, candidate_ids)
    if any(candidate.status == "excluded" for candidate in candidates):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="请先恢复已排除候选，再执行入库。",
        )
    imported: list[Note] = []
    for candidate in candidates:
        if candidate.status == "imported" and candidate.imported_note_id:
            note = db.get(Note, candidate.imported_note_id)
            if note is not None and note.user_id == current_user.id:
                imported.append(note)
                continue
        if candidate.status != "pending":
            continue
        note = _find_existing_note(db, current_user, candidate)
        run = db.get(DataAcquisitionRun, candidate.run_id)
        if note is None:
            note = Note(
                user_id=current_user.id,
                platform_account_id=run.account_id if run and run.account_id else 0,
                platform=candidate.platform,
                note_id=candidate.platform_note_id or candidate.external_id or f"candidate-{candidate.id}",
            )
            db.add(note)
        note.title = candidate.title
        note.content = candidate.content_excerpt
        note.author_name = candidate.author_name
        note.raw_json = _note_raw_from_candidate(candidate)
        db.flush()

        db.execute(delete(NoteAsset).where(NoteAsset.note_id == note.id))
        for index, asset_url in enumerate(candidate.asset_urls_json or []):
            db.add(NoteAsset(note_id=note.id, asset_type="image", url=str(asset_url), local_path="", sort_order=index))

        snapshot = NoteSourceSnapshot(
            note_id=note.id,
            run_id=candidate.run_id,
            candidate_id=candidate.id,
            user_id=current_user.id,
            platform=candidate.platform,
            source=candidate.source,
            snapshot_type="search_result",
            source_url=candidate.original_url,
            source_record_id=candidate.platform_note_id or candidate.external_id,
            rank_index=candidate.rank_index,
            keyword=str((candidate.raw_json or {}).get("keyword") or ""),
            category=candidate.category,
            tags_json=candidate.tags_json or [],
            metrics_json=candidate.metrics_json or {},
            raw_json=candidate.raw_json or {},
        )
        db.add(snapshot)
        candidate.status = "imported"
        candidate.imported_note_id = note.id
        candidate.updated_at = shanghai_now()
        imported.append(note)

    db.commit()
    for note in imported:
        db.refresh(note)
    return imported


def mark_candidates(
    *,
    db: Session,
    current_user: User,
    candidate_ids: list[int],
    status_value: str,
    reason_code: str = "",
    reason_text: str = "",
) -> list[DataAcquisitionCandidate]:
    candidates = get_owned_candidates(db, current_user, candidate_ids)
    for candidate in candidates:
        candidate.status = status_value
        candidate.decision_reason_code = reason_code
        candidate.decision_reason_text = reason_text
        candidate.updated_at = shanghai_now()
    db.commit()
    for candidate in candidates:
        db.refresh(candidate)
    return candidates

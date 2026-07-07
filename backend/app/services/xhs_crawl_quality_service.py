from __future__ import annotations

from typing import Any, Callable
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import NoteExclusion, PlatformAccount, Task, User
from backend.app.services.crawl_diagnostics import create_crawl_diagnostic
from backend.app.services.diagnostic_service import skipped_save_diagnostic
from backend.app.services.xhs_detail_recovery import (
    build_user_message,
    evaluate_detail_quality,
    is_xhs_rate_limit_signal,
)


EXCLUDED_NOTE_USER_MESSAGE = "该笔记已标记废弃，本轮跳过评论抓取和保存。"
COMMENT_RATE_LIMIT_SKIP_MESSAGE = "评论接口访问频繁，本轮后续评论已跳过。"


def filter_saveable_notes(
    normalized_items: list[dict[str, Any]],
    *,
    quality_evaluator: Callable[[dict[str, Any], object | None], dict[str, Any]] = evaluate_detail_quality,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    saveable: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for normalized in normalized_items:
        raw_payload = normalized.get("raw") if isinstance(normalized.get("raw"), dict) else None
        quality = quality_evaluator(normalized, raw_payload)
        normalized.update(quality)
        if quality["can_save"]:
            saveable.append(normalized)
        else:
            normalized["save_diagnostic_kind"] = "save_skipped_low_quality"
            skipped.append(normalized)
    return saveable, skipped


def split_excluded_saveable_notes(
    db: Session,
    account: PlatformAccount,
    saveable_items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    note_ids = [str(item.get("note_id") or "").strip() for item in saveable_items]
    unique_note_ids = [note_id for note_id in dict.fromkeys(note_ids) if note_id]
    exclusions = (
        db.scalars(
            select(NoteExclusion).where(
                NoteExclusion.user_id == account.user_id,
                NoteExclusion.platform == account.platform,
                NoteExclusion.platform_note_id.in_(unique_note_ids),
            )
        ).all()
        if unique_note_ids
        else []
    )
    exclusion_by_note_id = {exclusion.platform_note_id: exclusion for exclusion in exclusions}
    remaining: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for item in saveable_items:
        note_id = str(item.get("note_id") or "").strip()
        exclusion = exclusion_by_note_id.get(note_id)
        if exclusion is None:
            remaining.append(item)
            continue
        item.update(
            {
                "can_save": False,
                "quality_status": "excluded",
                "diagnostic_kind": "excluded_note",
                "save_diagnostic_kind": "excluded_note",
                "user_message": EXCLUDED_NOTE_USER_MESSAGE,
                "recoverable": False,
                "reason": "excluded",
                "reason_code": exclusion.reason_code,
                "reason_text": exclusion.reason_text,
            }
        )
        skipped.append(item)
    return remaining, skipped


def quality_item_fields(
    quality: dict[str, Any],
    *,
    saved: bool = False,
    save_diagnostic_kind: str | None = None,
) -> dict[str, Any]:
    return {
        "quality_status": quality.get("quality_status", "unknown"),
        "recoverable": bool(quality.get("recoverable", False)),
        "diagnostic_kind": quality.get("diagnostic_kind"),
        "save_diagnostic_kind": save_diagnostic_kind,
        "user_message": str(quality.get("user_message") or ""),
        "saved": saved,
    }


def diagnostic_severity(kind: str | None) -> str:
    if kind in {"xhs_rate_limited", "xhs_account_expired"}:
        return "blocked"
    if kind in {"missing_xsec_token_short_explore", "detail_api_failed", "invalid_note_identity", "search_api_failed"}:
        return "error"
    return "warning"


def search_failure_kind(message: str, raw_payload: object | None) -> str:
    raw_message = ""
    raw_code: object | None = None
    if isinstance(raw_payload, dict):
        raw_message = str(raw_payload.get("msg") or raw_payload.get("message") or "")
        raw_code = raw_payload.get("code")
    combined = f"{message} {raw_message}"
    if raw_code == -100 or any(marker in combined for marker in ("登录已过期", "鐧诲綍宸茶繃鏈", "锟斤拷录锟窖癸拷锟斤拷")):
        return "xhs_account_expired"
    if is_xhs_rate_limit_signal(message=combined):
        return "xhs_rate_limited"
    return "search_api_failed"


def search_failure_user_message(kind: str) -> str:
    if kind == "xhs_account_expired":
        return "小红书账号登录已过期。请到账户矩阵重新登录或更新 PC Cookie 后再采集。"
    if kind == "xhs_rate_limited":
        return build_user_message("xhs_rate_limited", "rate_limited")
    return "搜索接口返回失败，请稍后重试；如果连续失败，请到账户矩阵检查账号登录状态。"


def record_crawl_diagnostic(
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
    create_crawl_diagnostic(
        db,
        user_id=current_user.id,
        task_id=task.id,
        platform_account_id=account.id,
        platform="xhs",
        source=source,
        note_id=str((note or {}).get("note_id") or "") or None,
        note_url=note_url or str((note or {}).get("note_url") or "") or None,
        stage=stage,
        kind=kind,
        severity=diagnostic_severity(kind),
        recoverable=recoverable,
        message=message,
        user_message=user_message,
        raw_payload=raw_payload or (note or {}).get("raw") or {},
    )


def quality_from_short_url(url: str) -> dict[str, Any]:
    return {
        "quality_status": "invalid_source_url",
        "diagnostic_kind": "missing_xsec_token_short_explore",
        "recoverable": False,
        "user_message": build_user_message("missing_xsec_token_short_explore", "invalid_source_url"),
        "can_save": False,
    }


def record_save_skipped_diagnostics(
    db: Session,
    *,
    current_user: User,
    task: Task,
    account: PlatformAccount,
    skipped_items: list[dict[str, Any]],
) -> None:
    for skipped in skipped_items:
        diagnostic = skipped_save_diagnostic(
            platform_id="xhs",
            skipped_item=skipped,
            correlation_id=f"task:{task.id}",
        ).to_payload()
        existing_diagnostics = skipped.get("diagnostics")
        skipped["diagnostics"] = [
            *(existing_diagnostics if isinstance(existing_diagnostics, list) else []),
            diagnostic,
        ]
        record_crawl_diagnostic(
            db,
            current_user=current_user,
            task=task,
            account=account,
            source=str(skipped.get("note_url") or skipped.get("note_id") or ""),
            note=skipped,
            stage="save",
            kind=str(skipped.get("save_diagnostic_kind") or "save_skipped_low_quality"),
            message=str(skipped.get("diagnostic_kind") or "low quality detail"),
            user_message=str(skipped.get("user_message") or build_user_message(None, str(skipped.get("quality_status") or "unknown"))),
            recoverable=bool(skipped.get("recoverable", False)),
            raw_payload=skipped.get("raw") if isinstance(skipped.get("raw"), dict) else {},
        )


def is_comment_rate_limited(message: str) -> bool:
    normalized = str(message or "")
    return any(marker in normalized for marker in ("300013", "访问频繁", "璁块棶棰戠箒", "请稍后再试", "璇风◢鍚庡啀璇", "'comments'"))


def comment_failure_status(message: str) -> str:
    return "rate_limited" if is_comment_rate_limited(message) else "failed"


def comment_skip_error() -> str:
    return COMMENT_RATE_LIMIT_SKIP_MESSAGE


def platform_note_id_from_url(url: str) -> str:
    try:
        parsed = urlparse(url)
    except Exception:
        return ""
    parts = [part for part in parsed.path.split("/") if part]
    if "explore" in parts:
        index = parts.index("explore")
        if index + 1 < len(parts):
            return parts[index + 1].strip()
    return ""


def is_platform_note_id_excluded(db: Session, account: PlatformAccount, note_id: str) -> bool:
    note_id = str(note_id or "").strip()
    if not note_id:
        return False
    return (
        db.scalar(
            select(NoteExclusion.id).where(
                NoteExclusion.user_id == account.user_id,
                NoteExclusion.platform == account.platform,
                NoteExclusion.platform_note_id == note_id,
            )
        )
        is not None
    )


def is_normalized_note_excluded(db: Session, account: PlatformAccount, normalized: dict[str, Any]) -> bool:
    return is_platform_note_id_excluded(db, account, str(normalized.get("note_id") or "").strip())


def record_excluded_crawl_diagnostic(
    db: Session,
    *,
    current_user: User,
    task: Task,
    account: PlatformAccount,
    source: str,
    note: dict[str, Any],
    note_url: str | None = None,
) -> None:
    record_crawl_diagnostic(
        db,
        current_user=current_user,
        task=task,
        account=account,
        source=source,
        note=note,
        stage="save",
        kind="excluded_note",
        message="Note is excluded and skipped before comments/save",
        user_message=EXCLUDED_NOTE_USER_MESSAGE,
        recoverable=False,
        raw_payload=note.get("raw") if isinstance(note.get("raw"), dict) else {},
        note_url=note_url,
    )

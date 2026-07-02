from __future__ import annotations

import re
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.time import shanghai_now
from backend.app.models import Note, NoteAnalysisResult, NoteExclusion
from backend.app.services import feishu_bitable_service

BATH_WORDS = ["浴缸", "泡澡", "泡澡池", "澡池", "自砌浴缸"]
SQUARE_WALL_BATHTUB_WORDS = ["方形贴墙浴缸", "贴墙浴缸", "方形浴缸"]
GEO_WORDS = ["seo/geo", "seo geo", "ai搜索", "ai 搜索", "生成式引擎优化"]
GEO_WORD_RE = re.compile(r"(?<![A-Za-z])geo(?![A-Za-z])", re.IGNORECASE)
LOW_SCORE_THRESHOLD = 7.0

REASON_TEXT = {
    "geo": "GEO相关，当前清理规则排除",
    "square_wall_bathtub": "方形/贴墙浴缸相关，当前清理规则排除",
    "low_score_non_bathtub": "非浴缸相关且评分低于7，按严格清理规则废弃",
    "low_score_bathtub": "浴缸相关但评分低于7，按严格清理规则废弃",
    "manual_excluded": "人工标记废弃",
}


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n".join(_as_text(item) for item in value)
    if isinstance(value, dict):
        return "\n".join(_as_text(item) for item in value.values())
    return str(value)


ANALYSIS_RAW_PAYLOAD_TEXT_FIELDS = [
    "核心产品/服务",
    "产品/主题对象",
    "核心卖点/观点",
    "核心卖点/核心观点",
    "目标人群",
    "内容钩子",
    "封面/标题钩子",
    "封面类型",
    "标题类型",
    "笔记结构分析",
    "内容结构分析",
    "分析备注",
]


def _analysis_payload_text(raw_payload: dict | None) -> list[Any]:
    if not isinstance(raw_payload, dict):
        return []
    return [raw_payload.get(field) for field in ANALYSIS_RAW_PAYLOAD_TEXT_FIELDS]


def _note_text(note: Note, analysis: NoteAnalysisResult | None) -> str:
    chunks: list[Any] = [note.title, note.content, note.author_name]
    if analysis is not None:
        chunks.extend(
            [
                analysis.analysis_status,
                analysis.subject_object,
                analysis.content_type,
                analysis.core_points,
                analysis.target_audience,
                analysis.title_hook,
                analysis.content_structure,
                analysis.reuse_value,
                analysis.search_attribute,
                analysis.rating,
                analysis.analysis_note,
                analysis.reusable_models,
                *_analysis_payload_text(analysis.raw_payload),
            ]
        )
    return "\n".join(_as_text(chunk) for chunk in chunks if chunk is not None).lower()


def _contains_any(text: str, words: list[str]) -> bool:
    return any(word.lower() in text for word in words)


def _contains_geo(text: str) -> bool:
    return _contains_any(text, GEO_WORDS) or bool(GEO_WORD_RE.search(text))


def is_note_excluded(db: Session, *, user_id: int, platform: str, platform_note_id: str) -> bool:
    if not platform_note_id:
        return False
    return (
        db.scalar(
            select(NoteExclusion.id).where(
                NoteExclusion.user_id == user_id,
                NoteExclusion.platform == platform,
                NoteExclusion.platform_note_id == platform_note_id,
            )
        )
        is not None
    )


def _analysis_for_note(db: Session, note_id: int) -> NoteAnalysisResult | None:
    return db.scalar(select(NoteAnalysisResult).where(NoteAnalysisResult.note_id == note_id, NoteAnalysisResult.source == "feishu"))


def _get_or_create_analysis_for_note(db: Session, *, user_id: int, note_id: int) -> NoteAnalysisResult:
    analysis = _analysis_for_note(db, note_id)
    if analysis is None:
        analysis = NoteAnalysisResult(user_id=user_id, note_id=note_id, source="feishu")
        db.add(analysis)
        db.flush()
    return analysis


def _note_url(note: Note) -> str:
    raw = note.raw_json if isinstance(note.raw_json, dict) else {}
    return str(raw.get("note_url") or raw.get("url") or raw.get("share_url") or f"https://www.xiaohongshu.com/explore/{note.note_id}")


def _reason_for_note(note: Note, analysis: NoteAnalysisResult | None, *, strict: bool) -> str | None:
    text = _note_text(note, analysis)
    if _contains_geo(text):
        return "geo"
    if _contains_any(text, SQUARE_WALL_BATHTUB_WORDS):
        return "square_wall_bathtub"

    score = analysis.score if analysis is not None else None
    if score is None or score >= LOW_SCORE_THRESHOLD:
        return None

    is_bath = _contains_any(text, BATH_WORDS)
    if is_bath and strict:
        return "low_score_bathtub"
    if not is_bath:
        return "low_score_non_bathtub"
    return None


def build_current_cleanup_candidates(db: Session, *, user_id: int, strict: bool = True) -> list[dict[str, Any]]:
    excluded_platform_note_ids = set(
        db.scalars(
            select(NoteExclusion.platform_note_id).where(
                NoteExclusion.user_id == user_id,
                NoteExclusion.platform == "xhs",
            )
        ).all()
    )
    note_rows = db.execute(
        select(Note, NoteAnalysisResult)
        .outerjoin(
            NoteAnalysisResult,
            and_(NoteAnalysisResult.note_id == Note.id, NoteAnalysisResult.source == "feishu"),
        )
        .where(Note.user_id == user_id, Note.platform == "xhs")
        .order_by(Note.id.asc())
    ).all()
    candidates: list[dict[str, Any]] = []
    for note, analysis in note_rows:
        if note.note_id in excluded_platform_note_ids:
            continue
        reason_code = _reason_for_note(note, analysis, strict=strict)
        if reason_code is None:
            continue
        candidates.append(
            {
                "note_id": note.id,
                "platform_note_id": note.note_id,
                "title": note.title,
                "score": analysis.score if analysis else None,
                "rating": analysis.rating if analysis else None,
                "external_record_id": analysis.external_record_id if analysis else None,
                "reason_code": reason_code,
                "reason_text": REASON_TEXT[reason_code],
            }
        )
    return candidates


def _append_note(existing: str | None, reason_text: str) -> str:
    message = f"系统已废弃：{reason_text}"
    current = (existing or "").strip()
    if message in current:
        return current
    return f"{current}\n{message}".strip() if current else message


def _feishu_exclusion_fields(reason_text: str, existing_note: str | None = None, existing_field_names: set[str] | None = None) -> dict[str, Any]:
    fields = {
        "分析状态": "已废弃",
        "内容利用方式": ["废弃"],
        "分析备注": _append_note(existing_note, reason_text),
    }
    if existing_field_names is None:
        return fields
    return feishu_bitable_service.resolve_field_aliases(fields, existing_field_names)


def _select_exclusion(db: Session, *, user_id: int, platform: str, platform_note_id: str) -> NoteExclusion | None:
    return db.scalar(
        select(NoteExclusion).where(
            NoteExclusion.user_id == user_id,
            NoteExclusion.platform == platform,
            NoteExclusion.platform_note_id == platform_note_id,
        )
    )


def _apply_exclusion_values(
    exclusion: NoteExclusion,
    *,
    note: Note,
    analysis: NoteAnalysisResult | None,
    reason_code: str,
    reason_text: str,
    now,
) -> None:
    exclusion.note_id = note.id
    exclusion.source_url = _note_url(note)
    exclusion.title = note.title or ""
    exclusion.author_name = note.author_name or ""
    exclusion.reason_code = reason_code
    exclusion.reason_text = reason_text
    exclusion.score = analysis.score if analysis else None
    exclusion.rating = analysis.rating if analysis else None
    exclusion.external_record_id = analysis.external_record_id if analysis else None
    exclusion.updated_at = now

    if analysis is not None:
        analysis.analysis_status = "已废弃"
        analysis.reuse_value = "废弃"
        analysis.analysis_note = _append_note(analysis.analysis_note, reason_text)
        analysis.updated_at = now


def mark_notes_excluded(
    db: Session,
    *,
    user_id: int,
    note_ids: list[int],
    reason_code: str,
    reason_text: str = "",
    client: Any | None = None,
) -> dict[str, Any]:
    unique_ids = list(dict.fromkeys(note_ids))
    notes = db.scalars(select(Note).where(Note.user_id == user_id, Note.id.in_(unique_ids))).all() if unique_ids else []
    by_id = {note.id: note for note in notes}
    valid_notes = [note for note in notes if note.platform == "xhs"]
    valid_note_ids = [note.id for note in valid_notes]
    now = shanghai_now()
    excluded_count = 0
    skipped_count = 0
    feishu_updated_count = 0
    errors: list[dict[str, Any]] = []
    final_reason_text = reason_text or REASON_TEXT.get(reason_code, reason_code)

    def load_related() -> tuple[dict[int, NoteAnalysisResult], dict[tuple[str, str], NoteExclusion]]:
        analyses = (
            db.scalars(
                select(NoteAnalysisResult).where(
                    NoteAnalysisResult.source == "feishu",
                    NoteAnalysisResult.note_id.in_(valid_note_ids),
                )
            ).all()
            if valid_note_ids
            else []
        )
        note_keys = [(note.platform, note.note_id) for note in valid_notes]
        exclusions = (
            db.scalars(
                select(NoteExclusion).where(
                    NoteExclusion.user_id == user_id,
                    NoteExclusion.platform == "xhs",
                    NoteExclusion.platform_note_id.in_([note_id for _, note_id in note_keys]),
                )
            ).all()
            if note_keys
            else []
        )
        return {analysis.note_id: analysis for analysis in analyses}, {(exclusion.platform, exclusion.platform_note_id): exclusion for exclusion in exclusions}

    analysis_by_note_id: dict[int, NoteAnalysisResult] = {}
    exclusion_by_key: dict[tuple[str, str], NoteExclusion] = {}

    def persist_local_changes() -> None:
        nonlocal analysis_by_note_id, exclusion_by_key
        analysis_by_note_id, exclusion_by_key = load_related()
        for note_id in unique_ids:
            note = by_id.get(note_id)
            if note is None or note.platform != "xhs":
                continue
            analysis = analysis_by_note_id.get(note.id)
            key = (note.platform, note.note_id)
            exclusion = exclusion_by_key.get(key)
            if exclusion is None:
                exclusion = NoteExclusion(user_id=user_id, platform=note.platform, platform_note_id=note.note_id)
                db.add(exclusion)
                exclusion_by_key[key] = exclusion
            _apply_exclusion_values(
                exclusion,
                note=note,
                analysis=analysis,
                reason_code=reason_code,
                reason_text=final_reason_text,
                now=now,
            )

    for note_id in unique_ids:
        note = by_id.get(note_id)
        if note is None:
            skipped_count += 1
            errors.append({"note_id": note_id, "error": "Note not found"})
            continue
        if note.platform != "xhs":
            skipped_count += 1
            errors.append({"note_id": note_id, "error": "Only xhs notes can be excluded by this endpoint"})
            continue
        excluded_count += 1

    try:
        persist_local_changes()
        db.commit()
    except IntegrityError:
        db.rollback()
        notes = db.scalars(select(Note).where(Note.user_id == user_id, Note.id.in_(unique_ids))).all() if unique_ids else []
        by_id = {note.id: note for note in notes}
        valid_notes = [note for note in notes if note.platform == "xhs"]
        valid_note_ids = [note.id for note in valid_notes]
        persist_local_changes()
        db.commit()

    if client is not None:
        sync_now = shanghai_now()
        try:
            existing_field_names = feishu_bitable_service.field_names_for_client(client, raise_errors=True)
        except Exception as exc:  # pragma: no cover - defensive for injected clients
            existing_field_names = None
            field_error = f"Feishu 字段查询失败：{exc}"
        else:
            field_error = ""
        for note_id in unique_ids:
            note = by_id.get(note_id)
            if note is None or note.platform != "xhs":
                continue
            analysis = analysis_by_note_id.get(note.id)
            if analysis is None:
                analysis = NoteAnalysisResult(user_id=user_id, note_id=note.id, source="feishu")
                db.add(analysis)
                db.flush()
                analysis_by_note_id[note.id] = analysis
            if field_error:
                analysis.push_status = "failed"
                analysis.last_error = field_error
                analysis.updated_at = sync_now
                errors.append({"note_id": note.id, "feishu_failed": True, "error": field_error})
                continue
            if not analysis.external_record_id:
                analysis.push_status = "failed"
                analysis.last_error = "Feishu 同步未完成：缺少 external_record_id"
                analysis.updated_at = sync_now
                errors.append({"note_id": note.id, "feishu_failed": True, "error": analysis.last_error})
                continue
            try:
                client.update_record(analysis.external_record_id, _feishu_exclusion_fields(final_reason_text, analysis.analysis_note, existing_field_names))
                feishu_updated_count += 1
                analysis.push_status = "synced"
                analysis.last_pushed_at = sync_now
                analysis.last_error = ""
                analysis.updated_at = sync_now
            except Exception as exc:  # pragma: no cover - exercised by integration callers
                analysis.push_status = "failed"
                analysis.last_error = str(exc)
                analysis.updated_at = sync_now
                errors.append({"note_id": note.id, "record_id": analysis.external_record_id, "feishu_failed": True, "error": str(exc)})
        db.commit()
    return {
        "excluded_count": excluded_count,
        "skipped_count": skipped_count,
        "feishu_updated_count": feishu_updated_count,
        "feishu_failed_count": len([error for error in errors if error.get("feishu_failed")]),
        "errors": errors,
    }

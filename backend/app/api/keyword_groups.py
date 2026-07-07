from __future__ import annotations

import json
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.deps import get_current_user
from backend.app.core.time import shanghai_now
from backend.app.models import KeywordDiscoveryItem, KeywordDiscoveryRun, KeywordGroup, Note, User
from backend.app.schemas.common import paginated
from backend.app.services import huitun_live_keyword_source
from backend.app.services.huitun_keyword_source import (
    dedupe_keyword_candidates,
    parse_hotword_rows_from_cells,
    parse_huitun_categories,
    parse_huitun_number,
    prioritize_exact_hotword_rows,
)
from backend.app.services.platform_data_account_service import get_platform_data_account_cookie_text

router = APIRouter(prefix="/keyword-groups", tags=["keyword-groups"])


class KeywordGroupCreateRequest(BaseModel):
    platform: Literal["xhs", "douyin", "kuaishou", "weibo", "xianyu", "taobao"] = "xhs"
    name: str = Field(min_length=1, max_length=128)
    keywords: list[str] = Field(min_length=1, max_length=50)


class KeywordGroupUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    keywords: Optional[list[str]] = Field(default=None, min_length=1, max_length=50)


class HuitunDiscoveryInput(BaseModel):
    source_keyword: str = Field(min_length=1, max_length=128)
    table_rows: list[list[str]] = Field(default_factory=list)
    items: list[dict[str, Any]] = Field(default_factory=list)


class HuitunDiscoveryRunRequest(BaseModel):
    source_mode: Literal["manual_table", "manual_json", "local_connector_output", "live_account"] = "manual_table"
    limit_per_seed: int = Field(default=20, ge=1, le=100)
    account_id: Optional[int] = None
    inputs: list[HuitunDiscoveryInput] = Field(min_length=1, max_length=50)


class KeywordCandidateImportTarget(BaseModel):
    mode: Literal["create"] = "create"
    name: str = Field(min_length=1, max_length=128)
    platform: Literal["xhs", "douyin", "kuaishou", "weibo", "xianyu", "taobao"] = "xhs"


class KeywordCandidateImportRequest(BaseModel):
    candidate_ids: list[int] = Field(min_length=1, max_length=100)
    merge_mode: Literal["append_dedupe"] = "append_dedupe"
    target: Optional[KeywordCandidateImportTarget] = None


def _normalize_keywords(keywords: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for keyword in keywords:
        value = keyword.strip()
        key = value.lower()
        if value and key not in seen:
            normalized.append(value)
            seen.add(key)
    if not normalized:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="At least one keyword is required")
    return normalized


def _serialize_group(group: KeywordGroup) -> dict[str, Any]:
    return {
        "id": group.id,
        "platform": group.platform,
        "name": group.name,
        "keywords": group.keywords or [],
        "created_at": group.created_at.isoformat(),
        "updated_at": group.updated_at.isoformat(),
    }


def _serialize_discovery_item(item: KeywordDiscoveryItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "run_id": item.run_id,
        "platform": item.platform,
        "source": item.source,
        "source_keyword": item.source_keyword,
        "keyword": item.keyword,
        "hot_value_text": item.hot_value_text,
        "hot_value_number": item.hot_value_number,
        "note_count": item.note_count,
        "interaction_text": item.interaction_text,
        "interaction_number": item.interaction_number,
        "categories": item.categories or [],
        "rank_index": item.rank_index,
        "selected": item.selected,
        "imported_group_id": item.imported_group_id,
        "created_at": item.created_at.isoformat(),
    }


RUN_METADATA_VERSION = 1


def _run_metadata(seed_results: list[dict[str, Any]], total_item_count: int) -> dict[str, Any]:
    success_seed_count = sum(1 for result in seed_results if result.get("status") == "success")
    failed_seed_count = sum(1 for result in seed_results if result.get("status") == "failed")
    return {
        "version": RUN_METADATA_VERSION,
        "seed_results": seed_results,
        "summary": {
            "success_seed_count": success_seed_count,
            "failed_seed_count": failed_seed_count,
            "total_item_count": total_item_count,
        },
    }


def _metadata_text(seed_results: list[dict[str, Any]], total_item_count: int) -> str:
    return json.dumps(_run_metadata(seed_results, total_item_count), ensure_ascii=False)


def _parse_run_metadata(error_message: str | None, items: list[KeywordDiscoveryItem]) -> dict[str, Any]:
    if error_message:
        try:
            metadata = json.loads(error_message)
        except json.JSONDecodeError:
            metadata = None
        if isinstance(metadata, dict) and metadata.get("version") == RUN_METADATA_VERSION:
            seed_results = metadata.get("seed_results")
            summary = metadata.get("summary")
            if isinstance(seed_results, list) and isinstance(summary, dict):
                return {"seed_results": seed_results, "summary": summary}

    counts_by_seed: dict[str, int] = {}
    for item in items:
        counts_by_seed[item.source_keyword] = counts_by_seed.get(item.source_keyword, 0) + 1
    seed_results = [_seed_success(source_keyword, item_count) for source_keyword, item_count in counts_by_seed.items()]
    return _run_metadata(seed_results, len(items))


def _seed_success(source_keyword: str, item_count: int) -> dict[str, Any]:
    return {
        "source_keyword": source_keyword,
        "status": "success",
        "item_count": item_count,
        "error_message": "",
    }


def _seed_failure(source_keyword: str, error_message: str) -> dict[str, Any]:
    return {
        "source_keyword": source_keyword,
        "status": "failed",
        "item_count": 0,
        "error_message": error_message,
    }


def _status_from_seed_results(seed_results: list[dict[str, Any]]) -> str:
    has_success = any(result.get("status") == "success" for result in seed_results)
    has_failure = any(result.get("status") == "failed" for result in seed_results)
    if has_success and has_failure:
        return "partial_failed"
    if has_failure:
        return "failed"
    return "completed"


def _serialize_discovery_run(run: KeywordDiscoveryRun, items: list[KeywordDiscoveryItem]) -> dict[str, Any]:
    metadata = _parse_run_metadata(run.error_message, items)
    return {
        "id": run.id,
        "platform": run.platform,
        "source": run.source,
        "seed_keywords": run.seed_keywords or [],
        "limit_per_seed": run.limit_per_seed,
        "source_mode": run.source_mode,
        "status": run.status,
        "error_message": run.error_message,
        "created_at": run.created_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "items": [_serialize_discovery_item(item) for item in items],
        "seed_results": metadata["seed_results"],
        "summary": metadata["summary"],
    }


def _get_owned_group(db: Session, current_user: User, group_id: int) -> KeywordGroup:
    group = db.get(KeywordGroup, group_id)
    if group is None or group.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Keyword group not found")
    return group


def _get_owned_candidates(db: Session, current_user: User, candidate_ids: list[int]) -> list[KeywordDiscoveryItem]:
    unique_ids = list(dict.fromkeys(candidate_ids))
    items = db.scalars(
        select(KeywordDiscoveryItem)
        .where(KeywordDiscoveryItem.id.in_(unique_ids), KeywordDiscoveryItem.user_id == current_user.id)
        .order_by(KeywordDiscoveryItem.rank_index.asc(), KeywordDiscoveryItem.id.asc())
    ).all()
    if len(items) != len(unique_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Keyword candidate not found")
    by_id = {item.id: item for item in items}
    return [by_id[candidate_id] for candidate_id in unique_ids]


def _candidate_keywords(candidates: list[KeywordDiscoveryItem]) -> list[str]:
    return _normalize_keywords([candidate.keyword for candidate in candidates])


def _append_dedupe_keywords(existing: list[str], additions: list[str]) -> list[str]:
    return _normalize_keywords([*(existing or []), *additions])


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


def _note_metrics(note: Note) -> dict[str, int]:
    raw = note.raw_json or {}
    interaction = raw.get("interact_info") if isinstance(raw.get("interact_info"), dict) else {}
    merged = {**raw, **interaction}
    likes = _as_int(merged.get("likes") or merged.get("liked_count") or merged.get("like_count"))
    collects = _as_int(merged.get("collects") or merged.get("collected_count") or merged.get("collect_count"))
    comments = _as_int(merged.get("comments") or merged.get("comment_count"))
    shares = _as_int(merged.get("shares") or merged.get("share_count"))
    return {
        "likes": likes,
        "collects": collects,
        "comments": comments,
        "shares": shares,
        "engagement": likes + collects + comments + shares,
    }


def _note_haystack(note: Note) -> str:
    raw_text = json.dumps(note.raw_json or {}, ensure_ascii=False)
    return "\n".join([note.note_id, note.title, note.content, note.author_name, raw_text]).lower()


def _owned_notes(db: Session, current_user: User, platform: str) -> list[Note]:
    return db.scalars(
        select(Note)
        .where(Note.user_id == current_user.id, Note.platform == platform)
        .order_by(Note.created_at.desc(), Note.id.desc())
    ).all()


def _trend_summary(db: Session, current_user: User, group: KeywordGroup) -> dict[str, Any]:
    notes = _owned_notes(db, current_user, group.platform)
    keyword_items: list[dict[str, Any]] = []
    matched_by_note_id: dict[int, dict[str, Any]] = {}
    for keyword in group.keywords or []:
        needle = keyword.lower()
        matched_notes = [note for note in notes if needle in _note_haystack(note)]
        engagement = sum(_note_metrics(note)["engagement"] for note in matched_notes)
        keyword_items.append({"keyword": keyword, "notes": len(matched_notes), "engagement": engagement})
        for note in matched_notes:
            metrics = _note_metrics(note)
            matched_by_note_id[note.id] = {
                "id": note.id,
                "note_id": note.note_id,
                "title": note.title,
                "author_name": note.author_name,
                "created_at": note.created_at.isoformat(),
                **metrics,
            }
    matched_notes = sorted(matched_by_note_id.values(), key=lambda item: item["engagement"], reverse=True)
    return {
        "total_matches": len(matched_notes),
        "total_engagement": sum(item["engagement"] for item in matched_notes),
        "keywords": keyword_items,
        "matched_notes": matched_notes[:10],
    }


def _safe_candidate_raw(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_keyword": row.get("source_keyword"),
        "keyword": row.get("keyword"),
        "hot_value_text": row.get("hot_value_text"),
        "hot_value_number": row.get("hot_value_number"),
        "note_count": row.get("note_count"),
        "interaction_text": row.get("interaction_text"),
        "interaction_number": row.get("interaction_number"),
        "categories": row.get("categories") or [],
        "rank_index": row.get("rank_index"),
    }


def _normalize_manual_item(source_keyword: str, index: int, item: dict[str, Any]) -> dict[str, Any] | None:
    keyword = str(item.get("keyword") or item.get("word") or "").strip()
    if not keyword:
        return None
    hot_value_text = item.get("hot_value_text")
    interaction_text = item.get("interaction_text")
    categories = item.get("categories") or []
    if isinstance(categories, str):
        categories = parse_huitun_categories(categories)
    return {
        "source_keyword": source_keyword.strip(),
        "keyword": keyword,
        "hot_value_text": str(hot_value_text).strip() if hot_value_text is not None else None,
        "hot_value_number": item.get("hot_value_number") or parse_huitun_number(str(hot_value_text) if hot_value_text is not None else None),
        "note_count": item.get("note_count") if isinstance(item.get("note_count"), int) else parse_huitun_number(str(item.get("note_count")) if item.get("note_count") is not None else None),
        "interaction_text": str(interaction_text).strip() if interaction_text is not None else None,
        "interaction_number": item.get("interaction_number") or parse_huitun_number(str(interaction_text) if interaction_text is not None else None),
        "categories": categories,
        "rank_index": int(item.get("rank_index") or index + 1),
    }


def _latest_huitun_cookie_text(db: Session, current_user: User, account_id: int | None) -> str:
    _account, cookie_text = get_platform_data_account_cookie_text(db, account_id)
    return cookie_text


def get_huitun_live_keyword_client():
    return huitun_live_keyword_source



def _rows_from_huitun_input(input_item: HuitunDiscoveryInput, source_mode: str) -> list[dict[str, Any]]:
    source_keyword = input_item.source_keyword.strip()
    rows: list[dict[str, Any]] = []
    if source_mode == "manual_table":
        rows.extend(parse_hotword_rows_from_cells(source_keyword, input_item.table_rows))
    else:
        for index, item in enumerate(input_item.items):
            normalized = _normalize_manual_item(source_keyword, index, item)
            if normalized:
                rows.append(normalized)
        if source_mode == "local_connector_output" and input_item.table_rows:
            rows.extend(parse_hotword_rows_from_cells(source_keyword, input_item.table_rows))
    return dedupe_keyword_candidates(prioritize_exact_hotword_rows(source_keyword, rows))


def _mark_candidates_imported(candidates: list[KeywordDiscoveryItem], group_id: int) -> None:
    for candidate in candidates:
        candidate.selected = True
        candidate.imported_group_id = group_id


@router.get("")
def list_keyword_groups(
    platform: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    statement = select(KeywordGroup).where(KeywordGroup.user_id == current_user.id)
    if platform:
        statement = statement.where(KeywordGroup.platform == platform)
    groups = db.scalars(statement.order_by(KeywordGroup.created_at.desc(), KeywordGroup.id.desc())).all()
    return paginated([_serialize_group(group) for group in groups], page, page_size)


@router.post("")
def create_keyword_group(
    payload: KeywordGroupCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    group = KeywordGroup(
        user_id=current_user.id,
        platform=payload.platform,
        name=payload.name.strip(),
        keywords=_normalize_keywords(payload.keywords),
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    return _serialize_group(group)


@router.post("/huitun/discovery-runs")
def create_huitun_discovery_run(
    payload: HuitunDiscoveryRunRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    live_keyword_client=Depends(get_huitun_live_keyword_client),
):
    seed_keywords = _normalize_keywords([input_item.source_keyword for input_item in payload.inputs])
    effective_limit_per_seed = (
        min(payload.limit_per_seed, huitun_live_keyword_source.HUITUN_HOTWORD_MAX_PAGE_SIZE)
        if payload.source_mode == "live_account"
        else payload.limit_per_seed
    )
    run = KeywordDiscoveryRun(
        user_id=current_user.id,
        platform="xhs",
        source="huitun",
        seed_keywords=seed_keywords,
        limit_per_seed=effective_limit_per_seed,
        source_mode=payload.source_mode,
        status="running",
    )
    db.add(run)
    db.flush()

    rows: list[dict[str, Any]] = []
    seed_results: list[dict[str, Any]] = []
    if payload.source_mode == "live_account":
        cookies_text = _latest_huitun_cookie_text(db, current_user, payload.account_id)
        for input_item in payload.inputs:
            source_keyword = input_item.source_keyword.strip()
            try:
                seed_rows = live_keyword_client.fetch_huitun_hotwords(cookies_text, source_keyword, effective_limit_per_seed)
            except RuntimeError as exc:
                seed_results.append(_seed_failure(source_keyword, str(exc)))
                continue
            rows.extend(seed_rows)
            seed_results.append(_seed_success(source_keyword, len(seed_rows)))
    else:
        for input_item in payload.inputs:
            seed_rows = _rows_from_huitun_input(input_item, payload.source_mode)[: effective_limit_per_seed]
            rows.extend(seed_rows)
            seed_results.append(_seed_success(input_item.source_keyword.strip(), len(seed_rows)))
    rows = dedupe_keyword_candidates(rows)

    items: list[KeywordDiscoveryItem] = []
    for index, row in enumerate(rows):
        item = KeywordDiscoveryItem(
            run_id=run.id,
            user_id=current_user.id,
            platform="xhs",
            source="huitun",
            source_keyword=str(row.get("source_keyword") or "").strip(),
            keyword=str(row.get("keyword") or "").strip(),
            hot_value_text=row.get("hot_value_text"),
            hot_value_number=row.get("hot_value_number"),
            note_count=row.get("note_count"),
            interaction_text=row.get("interaction_text"),
            interaction_number=row.get("interaction_number"),
            categories=row.get("categories") or [],
            rank_index=int(row.get("rank_index") or index + 1),
            selected=False,
            raw_json=_safe_candidate_raw(row),
        )
        db.add(item)
        items.append(item)

    run.status = _status_from_seed_results(seed_results)
    run.error_message = _metadata_text(seed_results, len(items))
    run.finished_at = shanghai_now()
    db.commit()
    db.refresh(run)
    for item in items:
        db.refresh(item)
    return _serialize_discovery_run(run, items)


@router.get("/huitun/discovery-runs")
def list_huitun_discovery_runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    runs = db.scalars(
        select(KeywordDiscoveryRun)
        .where(
            KeywordDiscoveryRun.user_id == current_user.id,
            KeywordDiscoveryRun.platform == "xhs",
            KeywordDiscoveryRun.source == "huitun",
        )
        .order_by(KeywordDiscoveryRun.created_at.desc(), KeywordDiscoveryRun.id.desc())
    ).all()
    return paginated([_serialize_discovery_run(run, []) for run in runs], page, page_size)


@router.get("/huitun/discovery-runs/{run_id}")
def get_huitun_discovery_run(
    run_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = db.get(KeywordDiscoveryRun, run_id)
    if run is None or run.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Keyword discovery run not found")
    items = db.scalars(
        select(KeywordDiscoveryItem)
        .where(KeywordDiscoveryItem.run_id == run.id, KeywordDiscoveryItem.user_id == current_user.id)
        .order_by(KeywordDiscoveryItem.rank_index.asc(), KeywordDiscoveryItem.id.asc())
    ).all()
    return _serialize_discovery_run(run, items)


@router.post("/import-keyword-candidates")
def import_keyword_candidates(
    payload: KeywordCandidateImportRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.target is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Import target is required")
    candidates = _get_owned_candidates(db, current_user, payload.candidate_ids)
    imported_keywords = _candidate_keywords(candidates)
    group = KeywordGroup(
        user_id=current_user.id,
        platform=payload.target.platform,
        name=payload.target.name.strip(),
        keywords=imported_keywords,
    )
    db.add(group)
    db.flush()
    _mark_candidates_imported(candidates, group.id)
    group.updated_at = shanghai_now()
    db.commit()
    db.refresh(group)
    for candidate in candidates:
        db.refresh(candidate)
    return {
        "group": _serialize_group(group),
        "imported_keywords": imported_keywords,
        "items": [_serialize_discovery_item(candidate) for candidate in candidates],
    }


@router.post("/{group_id}/import-keyword-candidates")
def import_keyword_candidates_to_group(
    group_id: int,
    payload: KeywordCandidateImportRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    group = _get_owned_group(db, current_user, group_id)
    candidates = _get_owned_candidates(db, current_user, payload.candidate_ids)
    imported_keywords = _candidate_keywords(candidates)
    group.keywords = _append_dedupe_keywords(group.keywords or [], imported_keywords)
    group.updated_at = shanghai_now()
    _mark_candidates_imported(candidates, group.id)
    db.commit()
    db.refresh(group)
    for candidate in candidates:
        db.refresh(candidate)
    return {
        "group": _serialize_group(group),
        "imported_keywords": imported_keywords,
        "items": [_serialize_discovery_item(candidate) for candidate in candidates],
    }


@router.get("/{group_id}")
def get_keyword_group(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    group = _get_owned_group(db, current_user, group_id)
    serialized = _serialize_group(group)
    serialized["trend"] = _trend_summary(db, current_user, group)
    return serialized


@router.patch("/{group_id}")
def update_keyword_group(
    group_id: int,
    payload: KeywordGroupUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    group = _get_owned_group(db, current_user, group_id)
    if payload.name is not None:
        group.name = payload.name.strip()
    if payload.keywords is not None:
        group.keywords = _normalize_keywords(payload.keywords)
    group.updated_at = shanghai_now()
    db.commit()
    db.refresh(group)
    return _serialize_group(group)


@router.delete("/{group_id}")
def delete_keyword_group(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    group = _get_owned_group(db, current_user, group_id)
    db.delete(group)
    db.commit()
    return {"id": group_id, "status": "deleted"}

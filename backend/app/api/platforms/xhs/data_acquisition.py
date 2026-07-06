from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.api.notes import _serialize_note_with_tags
from backend.app.core.database import get_db
from backend.app.core.deps import get_current_user
from backend.app.core.time import shanghai_now
from backend.app.models import DataAcquisitionCandidate, DataAcquisitionRun, Task, User
from backend.app.schemas.common import paginated
from backend.app.services import huitun_live_note_source
from backend.app.services.data_acquisition_service import (
    SUPPORTED_ACQUISITION_TYPE,
    create_note_search_run,
    import_candidates,
    mark_candidates,
    serialize_candidate,
    serialize_run,
)

router = APIRouter(prefix="/xhs/data-acquisition", tags=["xhs-data-acquisition"])


class DataAcquisitionRunRequest(BaseModel):
    acquisition_type: Literal["note_search", "note_rank", "note_detail_enrichment", "keyword_analysis", "file_import"]
    account_id: Optional[int] = None
    params: dict[str, Any] = Field(default_factory=dict)


class CandidateDecisionRequest(BaseModel):
    candidate_ids: list[int] = Field(min_length=1, max_length=100)
    reason_code: str = Field(default="", max_length=64)
    reason_text: str = ""


class CandidateImportRequest(BaseModel):
    candidate_ids: list[int] = Field(min_length=1, max_length=100)


def get_data_acquisition_note_source():
    return huitun_live_note_source


def _owned_run(db: Session, current_user: User, run_id: int) -> DataAcquisitionRun:
    run = db.get(DataAcquisitionRun, run_id)
    if run is None or run.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据获取任务不存在。")
    return run


def _run_candidates(db: Session, current_user: User, run_id: int) -> list[DataAcquisitionCandidate]:
    return db.scalars(
        select(DataAcquisitionCandidate)
        .where(DataAcquisitionCandidate.run_id == run_id, DataAcquisitionCandidate.user_id == current_user.id)
        .order_by(DataAcquisitionCandidate.rank_index.asc(), DataAcquisitionCandidate.id.asc())
    ).all()


def _candidate_counts_by_run(db: Session, current_user: User, run_ids: list[int]) -> dict[int, int]:
    if not run_ids:
        return {}
    rows = db.execute(
        select(DataAcquisitionCandidate.run_id, func.count(DataAcquisitionCandidate.id))
        .where(DataAcquisitionCandidate.run_id.in_(run_ids), DataAcquisitionCandidate.user_id == current_user.id)
        .group_by(DataAcquisitionCandidate.run_id)
    ).all()
    return {int(run_id): int(count) for run_id, count in rows}


@router.post("/runs")
def create_data_acquisition_run(
    payload: DataAcquisitionRunRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    note_source=Depends(get_data_acquisition_note_source),
):
    if payload.acquisition_type != SUPPORTED_ACQUISITION_TYPE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="该获取方式仍在验证中，暂不可创建任务。",
        )
    run, candidates = create_note_search_run(
        db=db,
        current_user=current_user,
        account_id=payload.account_id,
        params=payload.params,
        note_source=note_source,
    )
    return serialize_run(run, candidates)


@router.get("/runs")
def list_data_acquisition_runs(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    statement = select(DataAcquisitionRun).where(DataAcquisitionRun.user_id == current_user.id, DataAcquisitionRun.platform == "xhs")
    if status_filter:
        statement = statement.where(DataAcquisitionRun.status == status_filter)
    runs = db.scalars(statement.order_by(DataAcquisitionRun.created_at.desc(), DataAcquisitionRun.id.desc())).all()
    candidate_counts = _candidate_counts_by_run(db, current_user, [run.id for run in runs])
    return paginated(
        [
            serialize_run(run, candidate_count=candidate_counts.get(run.id, 0), include_admin_debug=False)
            for run in runs
        ],
        page,
        page_size,
    )


@router.get("/runs/{run_id}")
def get_data_acquisition_run(
    run_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = _owned_run(db, current_user, run_id)
    candidates = _run_candidates(db, current_user, run.id)
    return serialize_run(run, candidates, include_admin_debug=False)


@router.post("/runs/{run_id}/rerun")
def rerun_data_acquisition_run(
    run_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    note_source=Depends(get_data_acquisition_note_source),
):
    run = _owned_run(db, current_user, run_id)
    if run.acquisition_type != SUPPORTED_ACQUISITION_TYPE:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="该获取方式仍在验证中，暂不可重跑。")
    new_run, candidates = create_note_search_run(
        db=db,
        current_user=current_user,
        account_id=run.account_id,
        params=run.params_json or {},
        note_source=note_source,
        rerun_of_run_id=run.id,
    )
    return serialize_run(new_run, candidates)


@router.post("/runs/{run_id}/cancel")
def cancel_data_acquisition_run(
    run_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = _owned_run(db, current_user, run_id)
    if run.status == "pending":
        run.status = "cancelled"
        run.finished_at = shanghai_now()
    elif run.status == "running":
        run.cancellation_requested = True
    task = db.get(Task, run.task_id) if run.task_id else None
    if task is not None and task.status in {"pending", "running"}:
        task.status = "cancelled" if run.status == "cancelled" else task.status
        task.finished_at = run.finished_at if task.status == "cancelled" else task.finished_at
    db.commit()
    db.refresh(run)
    return serialize_run(run, _run_candidates(db, current_user, run.id))


@router.get("/candidates")
def list_data_acquisition_candidates(
    run_id: Optional[int] = None,
    status_filter: Optional[str] = Query(default="pending", alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    statement = select(DataAcquisitionCandidate).where(
        DataAcquisitionCandidate.user_id == current_user.id,
        DataAcquisitionCandidate.platform == "xhs",
    )
    if run_id is not None:
        statement = statement.where(DataAcquisitionCandidate.run_id == run_id)
    if status_filter:
        statement = statement.where(DataAcquisitionCandidate.status == status_filter)
    candidates = db.scalars(
        statement.order_by(DataAcquisitionCandidate.created_at.desc(), DataAcquisitionCandidate.id.desc())
    ).all()
    return paginated([serialize_candidate(candidate, include_admin_debug=False) for candidate in candidates], page, page_size)


@router.post("/candidates/import")
def import_data_acquisition_candidates(
    payload: CandidateImportRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notes = import_candidates(db=db, current_user=current_user, candidate_ids=payload.candidate_ids)
    return {
        "imported_count": len(notes),
        "message": f"已入库 {len(notes)} 条笔记，可前往分析中心生成洞察。",
        "items": [_serialize_note_with_tags(db, note) for note in notes],
    }


@router.post("/candidates/exclude")
def exclude_data_acquisition_candidates(
    payload: CandidateDecisionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    candidates = mark_candidates(
        db=db,
        current_user=current_user,
        candidate_ids=payload.candidate_ids,
        status_value="excluded",
        reason_code=payload.reason_code,
        reason_text=payload.reason_text,
    )
    return {"items": [serialize_candidate(candidate) for candidate in candidates]}


@router.post("/candidates/restore")
def restore_data_acquisition_candidates(
    payload: CandidateDecisionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    candidates = mark_candidates(
        db=db,
        current_user=current_user,
        candidate_ids=payload.candidate_ids,
        status_value="pending",
        reason_code="",
        reason_text="",
    )
    return {"items": [serialize_candidate(candidate) for candidate in candidates]}


@router.post("/notes/enrich-details")
def create_detail_enrichment_task():
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="补全笔记详情仍在验证中，暂不可创建任务。",
    )

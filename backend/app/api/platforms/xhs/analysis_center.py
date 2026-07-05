from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.ai import _text_model_context, get_text_ai_client
from backend.app.core.database import get_db
from backend.app.core.deps import get_current_user
from backend.app.models.analysis_report import AnalysisReport
from backend.app.models.user import User
from backend.app.services.ai_service import TextAiClient
from backend.app.services.usage_quota_service import UsageQuotaService, get_or_create_default_tenant_context
from backend.app.services.xhs_analysis_center_service import AnalysisValidationError, XhsAnalysisCenterService

router = APIRouter(prefix="/xhs/analytics/analysis", tags=["xhs-analysis-center"])


class AnalysisHealthPayload(BaseModel):
    keyword_group_id: int
    excluded_note_ids: list[int] = Field(default_factory=list)
    source_note_ids: list[int] = Field(default_factory=list)
    benchmark_target_ids: list[int] = Field(default_factory=list)


class CreateAnalysisReportPayload(AnalysisHealthPayload):
    title: str = Field(default="小红书分析报告", max_length=256)


class CreateDraftFromTopicCardsPayload(BaseModel):
    topic_cards: list[dict[str, Any]] = Field(default_factory=list)


def _serialize_report(report: AnalysisReport) -> dict[str, Any]:
    return {
        "id": report.id,
        "platform": report.platform,
        "report_type": report.report_type,
        "status": report.status,
        "title": report.title,
        "input_config": report.input_config or {},
        "data_health": report.data_health or {},
        "evidence_pool": report.evidence_pool or {},
        "result_json": report.result_json,
        "html_file_path": report.html_file_path,
        "source_task_id": report.source_task_id,
        "rerun_from_report_id": report.rerun_from_report_id,
        "error_message": report.error_message,
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "started_at": report.started_at.isoformat() if report.started_at else None,
        "finished_at": report.finished_at.isoformat() if report.finished_at else None,
    }


def _serialize_draft(draft: Any) -> dict[str, Any]:
    return {
        "id": draft.id,
        "platform": draft.platform,
        "title": draft.title,
        "body": draft.body,
        "tags": draft.tags or [],
        "source_note_id": draft.source_note_id,
        "created_at": draft.created_at.isoformat() if draft.created_at else None,
    }


def _report_payload(payload: CreateAnalysisReportPayload) -> dict[str, Any]:
    return payload.model_dump()


def _text_model_context_or_none(db: Session, current_user: User) -> tuple[Any | None, str]:
    try:
        return _text_model_context(db, current_user)
    except HTTPException:
        return None, ""


def _quota_idempotency_key(request: Request, fallback: str) -> str:
    return request.headers.get("Idempotency-Key") or fallback


def _analysis_request_summary(payload: CreateAnalysisReportPayload) -> dict[str, int]:
    return {
        "keyword_group_id": payload.keyword_group_id,
        "excluded_note_count": len(payload.excluded_note_ids),
        "source_note_count": len(payload.source_note_ids),
        "benchmark_target_count": len(payload.benchmark_target_ids),
    }


def _reserve_analysis_report_usage(
    *,
    request: Request,
    db: Session,
    current_user: User,
    feature_key: str,
    payload: CreateAnalysisReportPayload,
    model_config: Any | None,
):
    context = get_or_create_default_tenant_context(db, current_user.id)
    return UsageQuotaService(db).reserve(
        tenant_id=context.tenant.id,
        user_id=current_user.id,
        feature_key=feature_key,
        bucket="analysis_report",
        amount=1,
        idempotency_key=_quota_idempotency_key(request, f"{feature_key}:{current_user.id}:{payload.keyword_group_id}:{payload.title}"),
        request_summary=_analysis_request_summary(payload),
        model_config_id=model_config.id if model_config is not None else None,
        provider=model_config.provider if model_config is not None else "",
    )


@router.post("/health")
def check_analysis_health(
    payload: AnalysisHealthPayload,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = XhsAnalysisCenterService(db)
    try:
        return service.check_health(
            user_id=current_user.id,
            keyword_group_id=payload.keyword_group_id,
            excluded_note_ids=payload.excluded_note_ids,
        )
    except AnalysisValidationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/collection-plan")
def create_collection_plan(
    payload: AnalysisHealthPayload,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = XhsAnalysisCenterService(db)
    try:
        health = service.check_health(
            user_id=current_user.id,
            keyword_group_id=payload.keyword_group_id,
            excluded_note_ids=payload.excluded_note_ids,
        )
    except AnalysisValidationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return health["collection_plan"]


@router.get("/reports")
def list_reports(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    reports = db.scalars(
        select(AnalysisReport)
        .where(AnalysisReport.user_id == current_user.id, AnalysisReport.platform == "xhs")
        .order_by(AnalysisReport.created_at.desc(), AnalysisReport.id.desc())
    ).all()
    return [_serialize_report(report) for report in reports]


@router.get("/reports/{report_id}")
def get_report(
    report_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    report = db.scalar(
        select(AnalysisReport).where(
            AnalysisReport.id == report_id,
            AnalysisReport.user_id == current_user.id,
            AnalysisReport.platform == "xhs",
        )
    )
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis report not found")
    return _serialize_report(report)


@router.post("/reports")
def create_report(
    payload: CreateAnalysisReportPayload,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    text_ai_client: TextAiClient = Depends(get_text_ai_client),
):
    model_config, api_key = _text_model_context_or_none(db, current_user)
    usage_reservation = _reserve_analysis_report_usage(
        request=request,
        db=db,
        current_user=current_user,
        feature_key="analysis.report_create",
        payload=payload,
        model_config=model_config,
    )
    try:
        report = XhsAnalysisCenterService(db).create_report(
            user_id=current_user.id,
            payload=_report_payload(payload),
            model_config=model_config,
            api_key=api_key,
            ai_client=text_ai_client,
        )
    except AnalysisValidationError as exc:
        UsageQuotaService(db).refund(usage_reservation.id, failure_reason=str(exc))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        UsageQuotaService(db).refund(usage_reservation.id, failure_reason=str(exc))
        raise

    if report.status == "completed":
        UsageQuotaService(db).commit(usage_reservation.id)
    else:
        UsageQuotaService(db).refund(usage_reservation.id, failure_reason=report.error_message or "analysis report failed")
    return _serialize_report(report)


@router.post("/reports/{report_id}/topic-cards/{card_id}/drafts")
def create_drafts_from_topic_card(
    report_id: int,
    card_id: str,
    payload: CreateDraftFromTopicCardsPayload,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    report = db.scalar(
        select(AnalysisReport).where(
            AnalysisReport.id == report_id,
            AnalysisReport.user_id == current_user.id,
            AnalysisReport.platform == "xhs",
        )
    )
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis report not found")

    drafts = XhsAnalysisCenterService(db).create_drafts_from_topic_cards(
        user_id=current_user.id,
        topic_cards=payload.topic_cards,
    )
    return [_serialize_draft(draft) for draft in drafts]


@router.post("/reports/{report_id}/rerun")
def rerun_report(
    report_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    text_ai_client: TextAiClient = Depends(get_text_ai_client),
):
    original = db.scalar(
        select(AnalysisReport).where(
            AnalysisReport.id == report_id,
            AnalysisReport.user_id == current_user.id,
            AnalysisReport.platform == "xhs",
        )
    )
    if original is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis report not found")

    raw_payload = dict(original.input_config or {})
    raw_payload["title"] = f"{original.title} - 重跑"
    payload = CreateAnalysisReportPayload.model_validate(raw_payload)
    model_config, api_key = _text_model_context_or_none(db, current_user)
    usage_reservation = _reserve_analysis_report_usage(
        request=request,
        db=db,
        current_user=current_user,
        feature_key="analysis.report_rerun",
        payload=payload,
        model_config=model_config,
    )
    try:
        report = XhsAnalysisCenterService(db).create_report(
            user_id=current_user.id,
            payload=_report_payload(payload),
            model_config=model_config,
            api_key=api_key,
            ai_client=text_ai_client,
        )
    except AnalysisValidationError as exc:
        UsageQuotaService(db).refund(usage_reservation.id, failure_reason=str(exc))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        UsageQuotaService(db).refund(usage_reservation.id, failure_reason=str(exc))
        raise

    report.rerun_from_report_id = original.id
    db.add(report)
    db.commit()
    db.refresh(report)
    if report.status == "completed":
        UsageQuotaService(db).commit(usage_reservation.id)
    else:
        UsageQuotaService(db).refund(usage_reservation.id, failure_reason=report.error_message or "analysis report failed")
    return _serialize_report(report)

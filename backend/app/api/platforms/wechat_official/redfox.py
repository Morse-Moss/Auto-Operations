from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.api.platforms.wechat_official.schemas import (
    WechatOfficialRedfoxAccountCollectRequest,
    WechatOfficialRedfoxConfigRequest,
    WechatOfficialRedfoxKeywordCollectRequest,
    WechatOfficialRedfoxUrlImportRequest,
)
from backend.app.core.database import get_db
from backend.app.core.deps import get_current_user
from backend.app.models import User
from backend.app.services.wechat_official_redfox_service import WechatOfficialRedfoxService

router = APIRouter(prefix="/wechat-official/redfox", tags=["wechat-official"])


@router.get("/config")
def get_redfox_config(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return WechatOfficialRedfoxService(db).get_config(current_user.id)


@router.post("/config")
def save_redfox_config(payload: WechatOfficialRedfoxConfigRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return WechatOfficialRedfoxService(db).save_config(current_user.id, payload.model_dump(exclude_unset=True))


@router.post("/config/validate")
def validate_redfox_config(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return WechatOfficialRedfoxService(db).validate_config(current_user.id)


@router.get("/collect/jobs")
def list_redfox_collect_jobs(
    source_label: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return WechatOfficialRedfoxService(db).list_collect_jobs(current_user.id, {"source_label": source_label, "page": page, "page_size": page_size})


@router.get("/collect/jobs/{job_id}")
def get_redfox_collect_job(job_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return WechatOfficialRedfoxService(db).get_collect_job(current_user.id, job_id)


@router.post("/collect/articles")
def collect_redfox_articles(payload: WechatOfficialRedfoxKeywordCollectRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return WechatOfficialRedfoxService(db).collect_articles(current_user.id, payload.model_dump())


@router.post("/collect/account")
def collect_redfox_account(payload: WechatOfficialRedfoxAccountCollectRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return WechatOfficialRedfoxService(db).collect_account(current_user.id, payload.model_dump())


@router.post("/import-url")
def import_redfox_url(payload: WechatOfficialRedfoxUrlImportRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return WechatOfficialRedfoxService(db).import_url(current_user.id, payload.model_dump())

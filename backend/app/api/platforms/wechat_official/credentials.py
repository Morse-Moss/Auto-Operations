from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.api.platforms.wechat_official.schemas import (
    WechatOfficialCredentialImportRequest,
    WechatOfficialCredentialValidateRequest,
)
from backend.app.core.database import get_db
from backend.app.core.deps import get_current_user
from backend.app.models import User
from backend.app.services.wechat_official_credential_service import WechatOfficialCredentialService

router = APIRouter(prefix="/wechat-official/credentials", tags=["wechat-official"])


@router.get("/guide")
def get_credential_guide(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return WechatOfficialCredentialService(db).get_credential_guide()


@router.post("/import")
def import_credential(
    payload: WechatOfficialCredentialImportRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return WechatOfficialCredentialService(db).import_credential(current_user.id, payload.model_dump())


@router.post("/validate")
def validate_credential(
    payload: WechatOfficialCredentialValidateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return WechatOfficialCredentialService(db).validate_credential_payload(payload.as_payload())


@router.get("")
def list_credentials(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = WechatOfficialCredentialService(db).list_credentials(current_user.id)
    return {"items": items, "total": len(items)}

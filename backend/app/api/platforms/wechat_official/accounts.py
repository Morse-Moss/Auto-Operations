from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.api.platforms.wechat_official.schemas import WechatOfficialBackendLoginCompleteRequest
from backend.app.core.database import get_db
from backend.app.core.deps import get_current_user
from backend.app.models import User
from backend.app.services.wechat_official_backend_session_service import WechatOfficialBackendSessionService

router = APIRouter(prefix="/wechat-official/accounts", tags=["wechat-official"])


@router.post("/login/qrcode")
def start_qr_login(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return WechatOfficialBackendSessionService(db).start_qr_login(current_user.id)


@router.post("/login/{login_session_id}/complete")
def complete_qr_login(
    login_session_id: int,
    payload: WechatOfficialBackendLoginCompleteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return WechatOfficialBackendSessionService(db).complete_qr_login(
        current_user.id,
        login_session_id,
        payload.model_dump(),
    )


@router.get("/sessions")
def list_sessions(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = WechatOfficialBackendSessionService(db).list_sessions(current_user.id)
    return {"items": items, "total": len(items)}

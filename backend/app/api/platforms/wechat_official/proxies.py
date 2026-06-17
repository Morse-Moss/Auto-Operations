from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.api.platforms.wechat_official.schemas import WechatOfficialProxyTestRequest
from backend.app.core.database import get_db
from backend.app.core.deps import get_current_user
from backend.app.models import User
from backend.app.services.wechat_official_proxy_service import WechatOfficialProxyService

router = APIRouter(prefix="/wechat-official/proxies", tags=["wechat-official"])


@router.get("")
def list_proxies(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = WechatOfficialProxyService(db).list_proxies(current_user.id)
    return {"items": items, "total": len(items)}


@router.post("/{proxy_id}/test")
def test_proxy(proxy_id: int, payload: WechatOfficialProxyTestRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return WechatOfficialProxyService(db).test_proxy(current_user.id, proxy_id, payload.model_dump())

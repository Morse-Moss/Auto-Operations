from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.deps import get_current_user
from backend.app.models import User
from backend.app.services.wechat_official_readiness_service import get_wechat_official_readiness

router = APIRouter(prefix="/wechat-official", tags=["wechat-official"])


@router.get("/readiness")
def read_wechat_official_readiness(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_wechat_official_readiness(db, user_id=current_user.id)

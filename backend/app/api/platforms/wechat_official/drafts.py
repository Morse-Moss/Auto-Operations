from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.api.platforms.wechat_official.schemas import WechatOfficialDraftDryRunRequest
from backend.app.core.database import get_db
from backend.app.core.deps import get_current_user
from backend.app.models import User
from backend.app.services.wechat_official_draft_service import WechatOfficialDraftService

router = APIRouter(prefix="/wechat-official/drafts", tags=["wechat-official"])


@router.post("/{draft_id}/dry-run")
def dry_run(draft_id: int, payload: WechatOfficialDraftDryRunRequest | None = None, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return WechatOfficialDraftService(db).dry_run(current_user.id, draft_id, payload.model_dump(exclude_unset=True) if payload else {})

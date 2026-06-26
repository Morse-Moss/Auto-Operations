from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.deps import get_current_user
from backend.app.models import User
from backend.app.services.wechat_official_article_import_service import WechatOfficialArticleImportService

router = APIRouter(prefix="/wechat-official/articles", tags=["wechat-official"])


class WechatOfficialArticleUrlImportRequest(BaseModel):
    url: str = Field(min_length=1)
    save_snapshot: bool = True


@router.post("/import-url")
def import_article_url(payload: WechatOfficialArticleUrlImportRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return WechatOfficialArticleImportService(db).import_url(current_user.id, payload.model_dump())

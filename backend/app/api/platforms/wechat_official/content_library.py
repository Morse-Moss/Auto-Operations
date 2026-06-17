from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.api.platforms.wechat_official.schemas import WechatOfficialCreateDraftRequest, WechatOfficialRecommendationUpdateRequest
from backend.app.core.database import get_db
from backend.app.core.deps import get_current_user
from backend.app.models import User
from backend.app.services.wechat_official_content_service import WechatOfficialContentService
from backend.app.services.wechat_official_draft_service import WechatOfficialDraftService

router = APIRouter(prefix="/wechat-official/content-library", tags=["wechat-official"])


@router.get("")
def list_content_library(
    viral_only: bool = False,
    min_read_count: Optional[int] = Query(default=None, ge=0),
    low_follower_evidence: Optional[bool] = None,
    recommendation_status: Optional[str] = None,
    keyword: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return WechatOfficialContentService(db).list_content(
        current_user.id,
        {
            "viral_only": viral_only,
            "min_read_count": min_read_count,
            "low_follower_evidence": low_follower_evidence,
            "recommendation_status": recommendation_status,
            "keyword": keyword,
        },
    )


@router.patch("/{article_id}/recommendation")
def update_recommendation(article_id: int, payload: WechatOfficialRecommendationUpdateRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return WechatOfficialContentService(db).update_recommendation(current_user.id, article_id, payload.model_dump(exclude_unset=True))


@router.post("/{article_id}/create-draft")
def create_draft(article_id: int, payload: WechatOfficialCreateDraftRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return WechatOfficialDraftService(db).create_draft_from_article(current_user.id, article_id, payload.model_dump())

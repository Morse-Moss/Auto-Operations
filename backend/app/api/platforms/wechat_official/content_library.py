from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.api.platforms.wechat_official.schemas import WechatOfficialContentAutoRefreshRequest, WechatOfficialContentExportRequest, WechatOfficialCreateDraftRequest, WechatOfficialHotspotAnalyzeRequest, WechatOfficialRecommendationUpdateRequest
from backend.app.core.database import get_db
from backend.app.core.deps import get_current_user
from backend.app.models import User
from backend.app.services.wechat_official_content_service import WechatOfficialContentService
from backend.app.services.wechat_official_draft_service import WechatOfficialDraftService
from backend.app.services.wechat_official_redfox_service import WechatOfficialRedfoxService

router = APIRouter(prefix="/wechat-official/content-library", tags=["wechat-official"])


@router.get("")
def list_content_library(
    viral_only: bool = False,
    min_read_count: Optional[int] = Query(default=None, ge=0),
    low_follower_evidence: Optional[str] = None,
    recommendation_status: Optional[str] = None,
    pool_status: Optional[str] = None,
    category: Optional[str] = None,
    tag: Optional[str] = None,
    is_favorite: Optional[bool] = None,
    read_status: Optional[str] = None,
    detail_complete: Optional[bool] = None,
    keyword: Optional[str] = None,
    job_id: Optional[int] = Query(default=None, ge=1),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
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
            "pool_status": pool_status,
            "category": category,
            "tag": tag,
            "is_favorite": is_favorite,
            "read_status": read_status,
            "detail_complete": detail_complete,
            "keyword": keyword,
            "job_id": job_id,
            "page": page,
            "page_size": page_size,
        },
    )


@router.post("/export")
def export_content_library_articles(payload: WechatOfficialContentExportRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return WechatOfficialContentService(db).export_articles(current_user.id, payload.model_dump())


@router.get("/feed.rss")
def content_library_rss_feed(
    pool_status: Optional[str] = None,
    category: Optional[str] = None,
    tag: Optional[str] = None,
    is_favorite: Optional[bool] = None,
    read_status: Optional[str] = None,
    detail_complete: Optional[bool] = None,
    keyword: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return WechatOfficialContentService(db).rss_feed(
        current_user.id,
        {
            "pool_status": pool_status,
            "category": category,
            "tag": tag,
            "is_favorite": is_favorite,
            "read_status": read_status,
            "detail_complete": detail_complete,
            "keyword": keyword,
        },
    )


@router.post("/auto-refresh")
def auto_refresh_content_library_articles(payload: WechatOfficialContentAutoRefreshRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return WechatOfficialContentService(db).auto_refresh(current_user.id, payload.model_dump())


@router.get("/{article_id}")
def get_content_detail(article_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return WechatOfficialContentService(db).get_detail(current_user.id, article_id)


@router.delete("/{article_id}")
def delete_content_library_article(article_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return WechatOfficialContentService(db).delete_article(current_user.id, article_id)


@router.patch("/{article_id}/recommendation")
def update_recommendation(article_id: int, payload: WechatOfficialRecommendationUpdateRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return WechatOfficialContentService(db).update_recommendation(current_user.id, article_id, payload.model_dump(exclude_unset=True))


@router.post("/{article_id}/refresh-detail")
def refresh_detail(article_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return WechatOfficialRedfoxService(db).refresh_article_detail(current_user.id, article_id)


@router.post("/{article_id}/analyze-hotspots")
def analyze_hotspots(article_id: int, payload: WechatOfficialHotspotAnalyzeRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return WechatOfficialContentService(db).analyze_hotspots(current_user.id, article_id, payload.model_dump())


@router.post("/{article_id}/create-draft")
def create_draft(article_id: int, payload: WechatOfficialCreateDraftRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return WechatOfficialDraftService(db).create_draft_from_article(current_user.id, article_id, payload.model_dump())

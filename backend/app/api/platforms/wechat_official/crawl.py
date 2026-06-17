from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.api.platforms.wechat_official.schemas import (
    WechatOfficialArticleCommentsRequest,
    WechatOfficialArticleMetricsRequest,
    WechatOfficialArticleSnapshotRequest,
    WechatOfficialArticleSyncRequest,
    WechatOfficialSearchAccountsRequest,
)
from backend.app.core.database import get_db
from backend.app.core.deps import get_current_user
from backend.app.models import User
from backend.app.services.wechat_official_comment_service import WechatOfficialCommentService
from backend.app.services.wechat_official_crawl_service import WechatOfficialCrawlService

router = APIRouter(prefix="/wechat-official/crawl", tags=["wechat-official"])


@router.post("/accounts/search")
def search_accounts(payload: WechatOfficialSearchAccountsRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return WechatOfficialCrawlService(db).search_accounts(current_user.id, payload.model_dump())


@router.post("/articles/sync")
def sync_articles(payload: WechatOfficialArticleSyncRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return WechatOfficialCrawlService(db).sync_articles(current_user.id, payload.model_dump())


@router.post("/articles/{article_id}/snapshot")
def capture_snapshot(article_id: int, payload: WechatOfficialArticleSnapshotRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return WechatOfficialCrawlService(db).capture_snapshot(current_user.id, article_id, payload.model_dump())


@router.post("/articles/{article_id}/metrics")
def capture_metrics(article_id: int, payload: WechatOfficialArticleMetricsRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return WechatOfficialCrawlService(db).capture_metrics(current_user.id, article_id, payload.model_dump())


@router.post("/articles/{article_id}/comments")
def capture_comments(article_id: int, payload: WechatOfficialArticleCommentsRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return WechatOfficialCommentService(db).store_comments(current_user.id, article_id, payload.model_dump())

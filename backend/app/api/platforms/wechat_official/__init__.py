from __future__ import annotations

from fastapi import APIRouter

from backend.app.api.platforms.wechat_official import accounts, content_library, crawl, credentials, drafts, overview, proxies, redfox

router = APIRouter()
router.include_router(overview.router)
router.include_router(accounts.router)
router.include_router(credentials.router)
router.include_router(proxies.router)
router.include_router(redfox.router)
router.include_router(crawl.router)
router.include_router(content_library.router)
router.include_router(drafts.router)

__all__ = ["router"]

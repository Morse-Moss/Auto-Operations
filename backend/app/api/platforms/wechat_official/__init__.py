from __future__ import annotations

from fastapi import APIRouter

from backend.app.api.platforms.wechat_official import accounts, articles, browser_fallback, content_library, crawl, credentials, drafts, overview, proxies, readiness, redfox

router = APIRouter()
router.include_router(overview.router)
router.include_router(accounts.router)
router.include_router(credentials.router)
router.include_router(proxies.router)
router.include_router(redfox.router)
router.include_router(articles.router)
router.include_router(browser_fallback.router)
router.include_router(crawl.router)
router.include_router(content_library.router)
router.include_router(drafts.router)
router.include_router(readiness.router)

__all__ = ["router"]

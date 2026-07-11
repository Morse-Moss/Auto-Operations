from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.app.api import accounts, admin, ai, auth, auto_tasks, drafts, feishu_integration, files, huitun_login_sessions, keyword_groups, login_sessions, model_configs, notes, notifications, publish, tags, tasks, usage
from backend.app.api.platforms import registry
from backend.app.api.platforms.wechat_official import router as wechat_official_router
from backend.app.api.platforms.xhs import analysis_center, analytics, crawl, creator, data_acquisition, monitoring, page_import, pc
from backend.app.core.config import get_settings
from backend.app.core.database import init_db
from backend.app.services.beta_concurrency_service import BetaConcurrencyLimitExceeded
from backend.app.services.rate_limit_service import record_rate_limit_failure
from backend.app.services.scheduler_service import run_due_auto_tasks, shutdown_due_publish_scheduler, start_due_publish_scheduler
from backend.app.services.usage_quota_service import UsageQuotaInsufficientError


logger = logging.getLogger("spider_xhs.runtime")
REQUEST_ID_HEADER = "X-Request-ID"


class ClientErrorReport(BaseModel):
    event_type: str = Field(default="browser_error", max_length=80)
    message: str = Field(default="", max_length=2000)
    stack: str = Field(default="", max_length=12000)
    url: str = Field(default="", max_length=2048)
    app_version: str = Field(default="", max_length=120)
    request_id: str = Field(default="", max_length=120)
    user_agent: str = Field(default="", max_length=512)
    timestamp: str = Field(default="", max_length=80)
    extra: dict[str, Any] = Field(default_factory=dict, max_length=20)


def _runtime_version() -> dict[str, str]:
    commit = (
        os.environ.get("APP_COMMIT")
        or os.environ.get("RAILWAY_GIT_COMMIT_SHA")
        or os.environ.get("RENDER_GIT_COMMIT")
        or os.environ.get("VERCEL_GIT_COMMIT_SHA")
        or os.environ.get("GIT_COMMIT_SHA")
        or ""
    )
    version = os.environ.get("APP_VERSION") or (commit[:12] if commit else "dev")
    return {"service": "spider-xhs", "version": version, "commit": commit}


def _safe_request_id(value: str | None) -> str:
    request_id = "".join(ch for ch in (value or "").strip() if ch.isalnum() or ch in "-_:.")
    return request_id[:120] or uuid4().hex


def _safe_log_text(value: str, max_length: int) -> str:
    return " ".join(value.split())[:max_length]


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    settings = get_settings()
    scheduler = None
    if settings.scheduler_enabled:
        scheduler = start_due_publish_scheduler(settings.scheduler_interval_seconds)
    app.state.scheduler = scheduler
    try:
        yield
    finally:
        shutdown_due_publish_scheduler(scheduler)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.api_title, lifespan=lifespan)

    def _is_xhs_page_payload_path(path: str) -> bool:
        return path.startswith("/api/notes/") and path.endswith("/assets/import-source-images/page-payload")

    def _is_allowed_xhs_page_origin(origin: str) -> bool:
        parsed = urlparse(origin)
        host = parsed.netloc.lower()
        return parsed.scheme == "https" and (host == "xiaohongshu.com" or host.endswith(".xiaohongshu.com"))

    def _xhs_page_cors_headers(origin: str) -> dict[str, str]:
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Private-Network": "true",
            "Access-Control-Max-Age": "600",
            "Vary": "Origin",
        }

    origins = [origin.strip() for origin in settings.backend_cors_origins.split(",") if origin.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def _request_id_middleware(request: Request, call_next):
        request_id = _safe_request_id(request.headers.get(REQUEST_ID_HEADER))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response

    @app.middleware("http")
    async def _source_image_import_page_cors(request: Request, call_next):
        origin = request.headers.get("origin", "")
        if _is_xhs_page_payload_path(request.url.path) and _is_allowed_xhs_page_origin(origin):
            headers = _xhs_page_cors_headers(origin)
            if request.method == "OPTIONS":
                return Response(status_code=204, headers=headers)
            response = await call_next(request)
            for key, value in headers.items():
                response.headers[key] = value
            return response
        return await call_next(request)

    @app.exception_handler(UsageQuotaInsufficientError)
    async def _usage_quota_insufficient_handler(_request, exc: UsageQuotaInsufficientError):
        return JSONResponse(status_code=exc.status_code, content=exc.payload)

    @app.exception_handler(BetaConcurrencyLimitExceeded)
    async def _beta_concurrency_limit_handler(_request, exc: BetaConcurrencyLimitExceeded):
        return JSONResponse(status_code=exc.status_code, content=exc.payload)

    @app.get("/api/health", tags=["health"])
    def health() -> dict:
        return {"status": "ok", "service": "spider-xhs"}

    @app.get("/api/version", tags=["health"])
    def version() -> dict[str, str]:
        return _runtime_version()

    @app.post("/api/client-errors", status_code=202, tags=["diagnostics"])
    def client_errors(report: ClientErrorReport, request: Request) -> dict[str, Any]:
        record_rate_limit_failure(request, "client-errors")
        request_id = _safe_request_id(
            request.headers.get(REQUEST_ID_HEADER) or report.request_id or getattr(request.state, "request_id", "")
        )
        logger.warning(
            "client_error event_type=%s request_id=%s app_version=%s url=%s message=%s stack=%s extra_keys=%s",
            _safe_log_text(report.event_type, 80),
            request_id,
            _safe_log_text(report.app_version, 120),
            _safe_log_text(report.url, 2048),
            _safe_log_text(report.message, 2000),
            _safe_log_text(report.stack, 4000),
            sorted(report.extra.keys()),
        )
        return {"accepted": True, "request_id": request_id}

    app.include_router(registry.router, prefix="/api")
    app.include_router(wechat_official_router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    app.include_router(accounts.router, prefix="/api")
    app.include_router(login_sessions.router, prefix="/api")
    app.include_router(huitun_login_sessions.router, prefix="/api")
    app.include_router(notes.router, prefix="/api")
    app.include_router(files.router, prefix="/api")
    app.include_router(drafts.router, prefix="/api")
    app.include_router(feishu_integration.router, prefix="/api")
    app.include_router(ai.router, prefix="/api")
    app.include_router(tasks.router, prefix="/api")
    app.include_router(usage.router, prefix="/api")
    app.include_router(admin.router, prefix="/api")
    app.include_router(model_configs.router, prefix="/api")
    app.include_router(tags.router, prefix="/api")
    app.include_router(notifications.router, prefix="/api")
    app.include_router(keyword_groups.router, prefix="/api")
    app.include_router(publish.router, prefix="/api")
    app.include_router(analytics.router, prefix="/api")
    app.include_router(analysis_center.router, prefix="/api")
    app.include_router(pc.router, prefix="/api")
    app.include_router(creator.router, prefix="/api")
    app.include_router(crawl.router, prefix="/api")
    app.include_router(data_acquisition.router, prefix="/api")
    app.include_router(page_import.router, prefix="/api")
    app.include_router(monitoring.router, prefix="/api")
    app.include_router(auto_tasks.router, prefix="/api")

    # Serve pre-built frontend in production / Docker
    if settings.frontend_serve_static:
        frontend_dist = Path(settings.frontend_build_dir)
        if frontend_dist.is_dir():
            from starlette.responses import FileResponse

            # Serve index.html for SPA client-side routing (non-API, non-file paths)
            @app.middleware("http")
            async def _spa_fallback(request, call_next):
                response = await call_next(request)
                path = request.url.path
                if (
                    response.status_code == 404
                    and not path.startswith("/api")
                    and "." not in path.split("/")[-1]
                ):
                    return FileResponse(str(frontend_dist / "index.html"))
                return response

            app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")

    return app


app = create_app()

from __future__ import annotations

from fastapi import HTTPException, status

from backend.app.core.config import get_settings


def ensure_production_external_actions_allowed() -> None:
    settings = get_settings()
    if settings.environment.lower() == "production" and not settings.allow_production_external_actions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Production external actions require ALLOW_PRODUCTION_EXTERNAL_ACTIONS=true",
        )

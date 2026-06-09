from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.app.schemas.common import paginated
from backend.app.services.platform_service import get_platform_detail, list_platforms

router = APIRouter(prefix="/platforms", tags=["platforms"])


@router.get("")
def get_platform_registry(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    return paginated(list_platforms(), page, page_size)


@router.get("/{platform_id}")
def get_platform_registry_detail(platform_id: str):
    try:
        return get_platform_detail(platform_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="platform_not_found") from exc

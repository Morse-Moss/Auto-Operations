from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.deps import get_current_user
from backend.app.models import User
from backend.app.services.usage_quota_service import get_or_create_default_tenant_context, UsageQuotaService

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("/balance")
def usage_balance(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    context = get_or_create_default_tenant_context(db, current_user.id)
    buckets = UsageQuotaService(db).get_balance(context.tenant.id)
    return {
        "tenant": {
            "id": context.tenant.id,
            "name": context.tenant.name,
            "slug": context.tenant.slug,
            "kind": context.tenant.kind,
            "status": context.tenant.status,
        },
        "membership": {
            "role": context.membership.role,
            "status": context.membership.status,
        },
        "buckets": {
            bucket: {
                "total": balance.total,
                "remaining": balance.remaining,
                "status": balance.status,
            }
            for bucket, balance in buckets.items()
        },
    }

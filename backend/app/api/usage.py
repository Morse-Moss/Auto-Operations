from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.deps import get_current_tenant_context
from backend.app.services.usage_quota_service import CREDIT_COSTS, FEATURE_CREDIT_ACTIONS, TenantContext, UsageQuotaService

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("/balance")
def usage_balance(context: TenantContext = Depends(get_current_tenant_context), db: Session = Depends(get_db)):
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


@router.get("/pricing")
def usage_pricing(_context: TenantContext = Depends(get_current_tenant_context)):
    return {
        "currency": "credits",
        "actions": CREDIT_COSTS,
        "features": {
            feature_key: {
                "action": action_key,
                "cost": CREDIT_COSTS[action_key],
            }
            for feature_key, action_key in FEATURE_CREDIT_ACTIONS.items()
        },
    }

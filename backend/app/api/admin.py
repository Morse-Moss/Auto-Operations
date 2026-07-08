from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.database import get_db
from backend.app.core.deps import require_admin_user
from backend.app.core.security import hash_password
from backend.app.models import InviteCode, InviteCodeUse, Tenant, TenantMember, User
from backend.app.services.invite_service import create_invite_code, normalize_invite_code
from backend.app.services.usage_quota_service import CREDITS_BUCKET, UsageQuotaService, get_or_create_default_tenant_context

router = APIRouter(prefix="/admin", tags=["admin"])


class InviteCodeCreateRequest(BaseModel):
    code: str = Field(min_length=3, max_length=80)
    max_uses: int = Field(default=1, ge=1, le=100)


class CreditAdjustRequest(BaseModel):
    bucket: str = Field(default=CREDITS_BUCKET, min_length=1, max_length=64)
    total: int = Field(ge=0, le=100_000)
    reason: str = Field(default="", max_length=512)


class AdminBootstrapRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=6, max_length=128)
    bootstrap_token: str = Field(min_length=1, max_length=256)


def _serialize_user(user: User, tenant_count: int = 0) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "status": user.status,
        "tenant_count": tenant_count,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


def _serialize_tenant(tenant: Tenant, member_count: int = 0) -> dict:
    return {
        "id": tenant.id,
        "name": tenant.name,
        "slug": tenant.slug,
        "kind": tenant.kind,
        "status": tenant.status,
        "member_count": member_count,
        "created_at": tenant.created_at.isoformat() if tenant.created_at else None,
        "updated_at": tenant.updated_at.isoformat() if tenant.updated_at else None,
    }


def _serialize_invite(invite: InviteCode, uses: list[tuple[InviteCodeUse, User]]) -> dict:
    return {
        "id": invite.id,
        "code": invite.code,
        "max_uses": invite.max_uses,
        "used_count": invite.used_count,
        "status": invite.status,
        "created_by_user_id": invite.created_by_user_id,
        "created_at": invite.created_at.isoformat() if invite.created_at else None,
        "updated_at": invite.updated_at.isoformat() if invite.updated_at else None,
        "uses": [
            {
                "id": usage.id,
                "used_by_user_id": usage.used_by_user_id,
                "username": user.username,
                "used_at": usage.used_at.isoformat() if usage.used_at else None,
            }
            for usage, user in uses
        ],
    }


@router.post("/bootstrap")
def bootstrap_first_admin(payload: AdminBootstrapRequest, db: Session = Depends(get_db)):
    settings = get_settings()
    if not settings.beta_admin_bootstrap_token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin bootstrap is not configured")
    if payload.bootstrap_token != settings.beta_admin_bootstrap_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid admin bootstrap token")
    if db.scalar(select(User.id).where(User.role == "admin")) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Admin bootstrap is already completed")

    username = payload.username.strip()
    if db.scalar(select(User.id).where(User.username == username)) is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists")

    try:
        user = User(username=username, password_hash=hash_password(payload.password), role="admin", status="active")
        db.add(user)
        db.flush()
        get_or_create_default_tenant_context(db, user.id, commit=False)
        db.commit()
        db.refresh(user)
        return _serialize_user(user, tenant_count=1)
    except HTTPException:
        db.rollback()
        raise


@router.get("/users")
def list_users(_admin: User = Depends(require_admin_user), db: Session = Depends(get_db)):
    tenant_counts = dict(
        db.execute(select(TenantMember.user_id, func.count(TenantMember.id)).group_by(TenantMember.user_id)).all()
    )
    users = db.scalars(select(User).order_by(User.id)).all()
    return {"items": [_serialize_user(user, tenant_counts.get(user.id, 0)) for user in users], "total": len(users)}


@router.get("/tenants")
def list_tenants(_admin: User = Depends(require_admin_user), db: Session = Depends(get_db)):
    member_counts = dict(
        db.execute(select(TenantMember.tenant_id, func.count(TenantMember.id)).group_by(TenantMember.tenant_id)).all()
    )
    tenants = db.scalars(select(Tenant).order_by(Tenant.id)).all()
    return {"items": [_serialize_tenant(tenant, member_counts.get(tenant.id, 0)) for tenant in tenants], "total": len(tenants)}


@router.post("/tenants/{tenant_id}/credits/adjust")
def adjust_tenant_credit(
    tenant_id: int,
    payload: CreditAdjustRequest,
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    if payload.bucket != CREDITS_BUCKET:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Only credits can be adjusted")
    account = UsageQuotaService(db).adjust_bucket(tenant_id, payload.bucket, total=payload.total, reason=payload.reason)
    return {"bucket": account.bucket, "total": account.total, "remaining": account.remaining, "status": account.status}


@router.post("/tenants/{tenant_id}/suspend")
def suspend_tenant(tenant_id: int, _admin: User = Depends(require_admin_user), db: Session = Depends(get_db)):
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    tenant.status = "suspended"
    db.commit()
    db.refresh(tenant)
    return _serialize_tenant(tenant)


@router.post("/tenants/{tenant_id}/activate")
def activate_tenant(tenant_id: int, _admin: User = Depends(require_admin_user), db: Session = Depends(get_db)):
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    tenant.status = "active"
    db.commit()
    db.refresh(tenant)
    return _serialize_tenant(tenant)


@router.post("/users/{user_id}/disable")
def disable_user(user_id: int, _admin: User = Depends(require_admin_user), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.status = "disabled"
    db.commit()
    db.refresh(user)
    return _serialize_user(user)


@router.post("/users/{user_id}/activate")
def activate_user(user_id: int, _admin: User = Depends(require_admin_user), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.status = "active"
    db.commit()
    db.refresh(user)
    return _serialize_user(user)


@router.post("/invite-codes")
def create_admin_invite_code(
    payload: InviteCodeCreateRequest,
    admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    invite = create_invite_code(
        db,
        code=normalize_invite_code(payload.code),
        max_uses=payload.max_uses,
        created_by_user_id=admin.id,
    )
    return _serialize_invite(invite, [])


@router.get("/invite-codes")
def list_invite_codes(_admin: User = Depends(require_admin_user), db: Session = Depends(get_db)):
    invites = db.scalars(select(InviteCode).order_by(InviteCode.id)).all()
    rows = db.execute(select(InviteCodeUse, User).join(User, User.id == InviteCodeUse.used_by_user_id)).all()
    uses_by_invite: dict[int, list[tuple[InviteCodeUse, User]]] = {}
    for usage, user in rows:
        uses_by_invite.setdefault(usage.invite_code_id, []).append((usage, user))
    return {
        "items": [_serialize_invite(invite, uses_by_invite.get(invite.id, [])) for invite in invites],
        "total": len(invites),
    }

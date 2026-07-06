from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.app.models import InviteCode, InviteCodeUse


def normalize_invite_code(code: str) -> str:
    return code.strip().upper()


def create_invite_code(db: Session, *, code: str, max_uses: int, created_by_user_id: int | None = None) -> InviteCode:
    normalized = normalize_invite_code(code)
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation code is required")
    if max_uses < 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation max uses must be at least 1")
    existing = db.scalar(select(InviteCode).where(InviteCode.code == normalized))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation code already exists")

    invite = InviteCode(code=normalized, max_uses=max_uses, used_count=0, status="active", created_by_user_id=created_by_user_id)
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return invite


def consume_invite_code(db: Session, *, code: str, user_id: int) -> InviteCode:
    normalized = normalize_invite_code(code)
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation code is required")

    invite = db.scalar(select(InviteCode).where(InviteCode.code == normalized))
    if invite is None or invite.status != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation code is invalid")
    if invite.used_count >= invite.max_uses:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation code has no remaining uses")

    updated = db.execute(
        update(InviteCode)
        .where(
            InviteCode.id == invite.id,
            InviteCode.status == "active",
            InviteCode.used_count < InviteCode.max_uses,
        )
        .values(used_count=InviteCode.used_count + 1)
    )
    if updated.rowcount != 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation code has no remaining uses")

    db.refresh(invite)
    db.add(InviteCodeUse(invite_code_id=invite.id, used_by_user_id=user_id))
    db.flush()
    return invite

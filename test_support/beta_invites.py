from __future__ import annotations

from backend.app.core.database import get_db
from backend.app.main import app
from backend.app.models import InviteCode


def create_test_invite_code(prefix: str = "TEST-BETA") -> str:
    db = next(app.dependency_overrides[get_db]())
    try:
        existing_count = db.query(InviteCode).count()
        code = f"{prefix}-{existing_count + 1}"
        db.add(InviteCode(code=code, max_uses=1000, used_count=0, status="active"))
        db.commit()
        return code
    finally:
        db.close()

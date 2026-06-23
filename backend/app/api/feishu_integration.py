from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.deps import get_current_user
from backend.app.core.security import encrypt_text
from backend.app.core.time import shanghai_now
from backend.app.models import FeishuIntegrationConfig, User
from backend.app.services.feishu_bitable_service import (
    FEISHU_FIELD_DEFINITIONS,
    FeishuIntegrationError,
    create_feishu_client_from_config,
    ensure_feishu_fields as ensure_feishu_fields_service,
    extract_bitable_tokens,
    pull_feishu_analysis_records,
    pull_feishu_analysis_records_from_client,
    push_notes_to_feishu,
    push_notes_to_feishu_dry_run,
)
from backend.app.services.wechat_official_feishu_service import (
    pull_wechat_official_feishu_analysis_records,
    pull_wechat_official_feishu_analysis_records_from_client,
    push_wechat_official_articles_to_feishu,
    push_wechat_official_articles_to_feishu_dry_run,
)

router = APIRouter(prefix="/integrations/feishu", tags=["feishu-integration"])


class FeishuConfigPayload(BaseModel):
    app_id: str = Field(default="", max_length=128)
    app_secret: str = ""
    bitable_url: str = ""
    table_id: str = Field(default="", max_length=128)
    enabled: bool = False


class FeishuDryRunPayload(BaseModel):
    dry_run: bool = True


class FeishuPushNotesPayload(BaseModel):
    note_ids: list[int] = Field(default_factory=list)
    dry_run: bool = True


class FeishuPullNotesPayload(BaseModel):
    note_ids: list[int] = Field(default_factory=list)
    dry_run: bool = True
    records: list[dict] = Field(default_factory=list)


class FeishuPushWechatOfficialArticlesPayload(BaseModel):
    article_ids: list[int] = Field(default_factory=list)
    dry_run: bool = True


class FeishuPullWechatOfficialArticlesPayload(BaseModel):
    article_ids: list[int] = Field(default_factory=list)
    dry_run: bool = True
    records: list[dict] = Field(default_factory=list)


def _get_config(db: Session, user_id: int) -> FeishuIntegrationConfig | None:
    return db.scalar(select(FeishuIntegrationConfig).where(FeishuIntegrationConfig.user_id == user_id))


def _serialize_config(config: FeishuIntegrationConfig | None) -> dict:
    if config is None:
        return {
            "app_id": "",
            "has_app_secret": False,
            "bitable_url": "",
            "bitable_app_token": None,
            "table_id": "",
            "view_id": None,
            "enabled": False,
            "last_test_status": None,
            "last_test_message": None,
            "last_tested_at": None,
        }
    return {
        "id": config.id,
        "app_id": config.app_id,
        "has_app_secret": bool(config.encrypted_app_secret),
        "bitable_url": config.bitable_url,
        "bitable_app_token": config.bitable_app_token,
        "table_id": config.table_id,
        "view_id": config.view_id,
        "enabled": bool(config.enabled),
        "last_test_status": config.last_test_status,
        "last_test_message": config.last_test_message,
        "last_tested_at": config.last_tested_at.isoformat() if config.last_tested_at else None,
    }


def _client_or_error(config: FeishuIntegrationConfig | None):
    if config is None:
        raise FeishuIntegrationError("飞书集成未配置")
    return create_feishu_client_from_config(config)


@router.get("/config")
def get_feishu_config(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _serialize_config(_get_config(db, current_user.id))


@router.post("/test")
def test_feishu_connection(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    config = _get_config(db, current_user.id)
    if config is None:
        return {"status": "not_configured", "message": "飞书集成未配置"}
    try:
        client = create_feishu_client_from_config(config)
        fields = client.list_fields()
        config.last_test_status = "success"
        config.last_test_message = f"连接成功，当前表已有 {len(fields)} 个字段"
        config.last_tested_at = shanghai_now()
        db.commit()
        return {"status": "success", "message": config.last_test_message, "field_count": len(fields)}
    except Exception as exc:
        config.last_test_status = "failed"
        config.last_test_message = str(exc)
        config.last_tested_at = shanghai_now()
        db.commit()
        return {"status": "failed", "message": str(exc)}


@router.post("/ensure-fields")
def ensure_feishu_fields(payload: FeishuDryRunPayload, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    config = _get_config(db, current_user.id)
    if config is None:
        return {"dry_run": payload.dry_run, "status": "not_configured", "fields": FEISHU_FIELD_DEFINITIONS}
    if payload.dry_run:
        return {"dry_run": True, "status": "ok", "fields": FEISHU_FIELD_DEFINITIONS}
    try:
        client = create_feishu_client_from_config(config)
        result = ensure_feishu_fields_service(client)
        config.last_test_status = "success"
        config.last_test_message = f"字段补齐完成：新增 {result.get('created_count', 0)} 个，已存在 {result.get('skipped_count', 0)} 个"
        config.last_tested_at = shanghai_now()
        db.commit()
        return result
    except Exception as exc:
        config.last_test_status = "failed"
        config.last_test_message = str(exc)
        config.last_tested_at = shanghai_now()
        db.commit()
        return {"dry_run": False, "status": "failed", "message": str(exc), "fields": FEISHU_FIELD_DEFINITIONS}


@router.post("/xhs-notes/push")
def push_xhs_notes_to_feishu(payload: FeishuPushNotesPayload, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not payload.note_ids:
        return {"dry_run": payload.dry_run, "updated_count": 0, "failed_count": 0, "errors": [], "records": []}
    if payload.dry_run:
        return push_notes_to_feishu_dry_run(db, user_id=current_user.id, note_ids=payload.note_ids)
    try:
        client = _client_or_error(_get_config(db, current_user.id))
        return push_notes_to_feishu(db, user_id=current_user.id, note_ids=payload.note_ids, client=client)
    except Exception as exc:
        return {
            "dry_run": False,
            "created_count": 0,
            "updated_count": 0,
            "failed_count": len(payload.note_ids),
            "errors": [str(exc)],
            "records": [],
        }


@router.post("/xhs-notes/pull")
def pull_xhs_notes_from_feishu(payload: FeishuPullNotesPayload, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if payload.dry_run:
        return pull_feishu_analysis_records(db, user_id=current_user.id, records=payload.records, note_ids=payload.note_ids or None)
    try:
        client = _client_or_error(_get_config(db, current_user.id))
        return pull_feishu_analysis_records_from_client(db, user_id=current_user.id, client=client, note_ids=payload.note_ids or None)
    except Exception as exc:
        return {
            "updated_count": 0,
            "unmatched_count": 0,
            "failed_count": 1,
            "errors": [str(exc)],
        }


@router.post("/wechat-official/articles/push")
def push_wechat_official_articles_to_feishu_endpoint(payload: FeishuPushWechatOfficialArticlesPayload, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not payload.article_ids:
        return {"dry_run": payload.dry_run, "updated_count": 0, "failed_count": 0, "errors": [], "records": []}
    if payload.dry_run:
        return push_wechat_official_articles_to_feishu_dry_run(db, user_id=current_user.id, article_ids=payload.article_ids)
    try:
        client = _client_or_error(_get_config(db, current_user.id))
        return push_wechat_official_articles_to_feishu(db, user_id=current_user.id, article_ids=payload.article_ids, client=client)
    except Exception as exc:
        return {
            "dry_run": False,
            "created_count": 0,
            "updated_count": 0,
            "failed_count": len(payload.article_ids),
            "errors": [str(exc)],
            "records": [],
        }


@router.post("/wechat-official/articles/pull")
def pull_wechat_official_articles_from_feishu_endpoint(payload: FeishuPullWechatOfficialArticlesPayload, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if payload.dry_run:
        return pull_wechat_official_feishu_analysis_records(db, user_id=current_user.id, records=payload.records, article_ids=payload.article_ids or None)
    try:
        client = _client_or_error(_get_config(db, current_user.id))
        return pull_wechat_official_feishu_analysis_records_from_client(db, user_id=current_user.id, client=client, article_ids=payload.article_ids or None)
    except Exception as exc:
        return {
            "updated_count": 0,
            "unmatched_count": 0,
            "failed_count": 1,
            "errors": [str(exc)],
        }


@router.put("/config")
def save_feishu_config(payload: FeishuConfigPayload, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    config = _get_config(db, current_user.id)
    if config is None:
        config = FeishuIntegrationConfig(user_id=current_user.id)
        db.add(config)
    tokens = extract_bitable_tokens(payload.bitable_url)
    config.app_id = payload.app_id.strip()
    if payload.app_secret:
        config.encrypted_app_secret = encrypt_text(payload.app_secret)
    config.bitable_url = payload.bitable_url.strip()
    config.bitable_app_token = tokens["bitable_app_token"]
    config.table_id = payload.table_id.strip() or tokens["table_id"] or ""
    config.view_id = tokens["view_id"]
    config.enabled = bool(payload.enabled)
    config.updated_at = shanghai_now()
    db.commit()
    db.refresh(config)
    return _serialize_config(config)

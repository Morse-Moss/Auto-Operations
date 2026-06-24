from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.deps import get_current_user
from backend.app.core.security import encrypt_text
from backend.app.core.time import shanghai_now
from backend.app.models import FeishuIntegrationConfig, Note, NoteAnalysisResult, User
from backend.app.services.feishu_bitable_service import (
    FEISHU_FIELD_DEFINITIONS,
    FeishuIntegrationError,
    create_feishu_analysis_base,
    create_feishu_bootstrap_client_from_config,
    create_feishu_client_from_config,
    grant_feishu_bitable_permission,
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
    collaborator_member_type: str = Field(default="", max_length=32)
    collaborator_member_id: str = Field(default="", max_length=256)
    collaborator_perm: str = Field(default="edit", max_length=32)


class FeishuDryRunPayload(BaseModel):
    dry_run: bool = True


class FeishuCreateAnalysisBasePayload(BaseModel):
    base_name: str = Field(default="小红书内容分析总表", max_length=128)
    table_name: str = Field(default="小红书内容分析", max_length=128)
    folder_token: str = Field(default="", max_length=256)


class FeishuGrantPermissionPayload(BaseModel):
    member_type: str = Field(default="", max_length=32)
    member_id: str = Field(default="", max_length=256)
    perm: str = Field(default="edit", max_length=32)
    notify_lark: bool = False


class FeishuPushNotesPayload(BaseModel):
    note_ids: list[int] = Field(default_factory=list)
    dry_run: bool = True
    overwrite_existing: bool = False


class FeishuPushAllNotesPayload(BaseModel):
    dry_run: bool = False
    only_unsynced: bool = False
    batch_size: int = Field(default=10, ge=1, le=100)
    overwrite_existing: bool = False


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
            "collaborator_member_type": "",
            "collaborator_member_id": "",
            "collaborator_perm": "edit",
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
        "collaborator_member_type": config.collaborator_member_type or "",
        "collaborator_member_id": config.collaborator_member_id or "",
        "collaborator_perm": config.collaborator_perm or "edit",
        "enabled": bool(config.enabled),
        "last_test_status": config.last_test_status,
        "last_test_message": config.last_test_message,
        "last_tested_at": config.last_tested_at.isoformat() if config.last_tested_at else None,
    }


def _client_or_error(config: FeishuIntegrationConfig | None):
    if config is None:
        raise FeishuIntegrationError("飞书集成未配置")
    return create_feishu_client_from_config(config)


def _normalize_collaborator(member_type: str, member_id: str, perm: str = "edit") -> tuple[str, str, str]:
    normalized_id = (member_id or "").strip()
    normalized_type = (member_type or "").strip()
    normalized_perm = (perm or "edit").strip() or "edit"
    if normalized_id.startswith("oc_"):
        normalized_type = "openchat"
    elif "@" in normalized_id and not normalized_type:
        normalized_type = "email"
    return normalized_type, normalized_id, normalized_perm


def _configured_collaborator(config: FeishuIntegrationConfig) -> tuple[str, str, str] | None:
    member_type, member_id, perm = _normalize_collaborator(config.collaborator_member_type or "", config.collaborator_member_id or "", config.collaborator_perm or "edit")
    if not member_type or not member_id:
        return None
    return member_type, member_id, perm


def _grant_configured_collaborator(config: FeishuIntegrationConfig, client, *, notify_lark: bool = False) -> dict | None:
    collaborator = _configured_collaborator(config)
    if not collaborator:
        return None
    member_type, member_id, perm = collaborator
    return grant_feishu_bitable_permission(
        client,
        app_token=config.bitable_app_token or "",
        member_type=member_type,
        member_id=member_id,
        perm=perm,
        notify_lark=notify_lark,
    )


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


@router.post("/create-analysis-base")
def create_feishu_analysis_base_endpoint(payload: FeishuCreateAnalysisBasePayload, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    config = _get_config(db, current_user.id)
    if config is None:
        return {"status": "not_configured", "message": "请先保存飞书 App ID 和 App Secret"}
    try:
        client = create_feishu_bootstrap_client_from_config(config)
        result = create_feishu_analysis_base(
            client,
            base_name=payload.base_name.strip() or "小红书内容分析总表",
            table_name=payload.table_name.strip() or "小红书内容分析",
            folder_token=payload.folder_token.strip(),
        )
        config.bitable_app_token = result["app_token"]
        config.table_id = result["table_id"]
        config.bitable_url = result["bitable_url"]
        grant_result = None
        grant_message = ""
        try:
            grant_result = _grant_configured_collaborator(config, client)
            if grant_result:
                grant_message = "，并已授权协作者编辑"
        except Exception as grant_exc:
            grant_message = f"，但协作者授权失败：{grant_exc}"
        config.last_test_status = "success"
        config.last_test_message = f"已创建飞书分析表并补齐 {result.get('created_fields', 0)} 个字段{grant_message}"
        config.last_tested_at = shanghai_now()
        config.updated_at = shanghai_now()
        db.commit()
        db.refresh(config)
        return {**result, "grant_result": grant_result, "grant_message": grant_message, "config": _serialize_config(config)}
    except Exception as exc:
        config.last_test_status = "failed"
        config.last_test_message = str(exc)
        config.last_tested_at = shanghai_now()
        db.commit()
        return {"status": "failed", "message": str(exc)}


@router.post("/grant-permission")
def grant_feishu_permission(payload: FeishuGrantPermissionPayload, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    config = _get_config(db, current_user.id)
    if config is None:
        return {"status": "not_configured", "message": "飞书集成未配置"}
    member_type, member_id, perm = _normalize_collaborator(
        payload.member_type.strip() or (config.collaborator_member_type or "").strip(),
        payload.member_id.strip() or (config.collaborator_member_id or "").strip(),
        payload.perm.strip() or (config.collaborator_perm or "edit"),
    )
    try:
        client = create_feishu_client_from_config(config)
        result = grant_feishu_bitable_permission(
            client,
            app_token=config.bitable_app_token or "",
            member_type=member_type,
            member_id=member_id,
            perm=perm,
            notify_lark=payload.notify_lark,
        )
        config.collaborator_member_type = member_type
        config.collaborator_member_id = member_id
        config.collaborator_perm = perm
        config.last_test_status = result.get("status", "success")
        config.last_test_message = "飞书分析表协作者授权完成" if result.get("status") == "success" else "飞书分析表协作者授权部分失败"
        config.last_tested_at = shanghai_now()
        config.updated_at = shanghai_now()
        db.commit()
        db.refresh(config)
        return {**result, "message": config.last_test_message, "config": _serialize_config(config)}
    except Exception as exc:
        config.last_test_status = "failed"
        config.last_test_message = str(exc)
        config.last_tested_at = shanghai_now()
        db.commit()
        return {"status": "failed", "message": str(exc), "config": _serialize_config(config)}


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
        return push_notes_to_feishu_dry_run(db, user_id=current_user.id, note_ids=payload.note_ids, overwrite_existing=payload.overwrite_existing)
    try:
        client = _client_or_error(_get_config(db, current_user.id))
        return push_notes_to_feishu(db, user_id=current_user.id, note_ids=payload.note_ids, client=client, overwrite_existing=payload.overwrite_existing)
    except Exception as exc:
        return {
            "dry_run": False,
            "created_count": 0,
            "updated_count": 0,
            "failed_count": len(payload.note_ids),
            "errors": [str(exc)],
            "records": [],
        }


@router.post("/xhs-notes/push-all")
def push_all_xhs_notes_to_feishu(payload: FeishuPushAllNotesPayload, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    note_ids_query = select(Note.id).where(Note.user_id == current_user.id, Note.platform == "xhs").order_by(Note.id.asc())
    note_ids = list(db.scalars(note_ids_query).all())
    if payload.only_unsynced and note_ids:
        synced_ids = set(
            db.scalars(
                select(NoteAnalysisResult.note_id).where(
                    NoteAnalysisResult.user_id == current_user.id,
                    NoteAnalysisResult.source == "feishu",
                    NoteAnalysisResult.push_status == "synced",
                )
            ).all()
        )
        note_ids = [note_id for note_id in note_ids if note_id not in synced_ids]
    if not note_ids:
        return {
            "dry_run": payload.dry_run,
            "total_count": 0,
            "processed_count": 0,
            "created_count": 0,
            "updated_count": 0,
            "failed_count": 0,
            "errors": [],
            "records": [],
            "batches": [],
        }

    processed = 0
    created = 0
    updated = 0
    failed = 0
    errors = []
    records = []
    batches = []
    try:
        client = None if payload.dry_run else _client_or_error(_get_config(db, current_user.id))
        for index in range(0, len(note_ids), payload.batch_size):
            batch = note_ids[index : index + payload.batch_size]
            batch_label = f"{index + 1}-{index + len(batch)}/{len(note_ids)}"
            print(f"[feishu-push-all] start user_id={current_user.id} batch={batch_label} dry_run={payload.dry_run} overwrite_existing={payload.overwrite_existing}", flush=True)
            result = push_notes_to_feishu_dry_run(db, user_id=current_user.id, note_ids=batch, overwrite_existing=payload.overwrite_existing) if payload.dry_run else push_notes_to_feishu(db, user_id=current_user.id, note_ids=batch, client=client, overwrite_existing=payload.overwrite_existing)
            batch_created = int(result.get("created_count") or 0)
            batch_updated = int(result.get("updated_count") or 0)
            batch_failed = int(result.get("failed_count") or 0)
            batch_records = result.get("records") or []
            created += batch_created
            updated += batch_updated
            failed += batch_failed
            processed += len(batch)
            errors.extend(result.get("errors") or [])
            records.extend(batch_records)
            warning_count = sum(1 for record in batch_records if isinstance(record, dict) and record.get("warning"))
            print(
                f"[feishu-push-all] done user_id={current_user.id} batch={batch_label} created={batch_created} updated={batch_updated} failed={batch_failed} warnings={warning_count}",
                flush=True,
            )
            batches.append(
                {
                    "start": index + 1,
                    "end": index + len(batch),
                    "count": len(batch),
                    "created_count": batch_created,
                    "updated_count": batch_updated,
                    "failed_count": batch_failed,
                    "warning_count": warning_count,
                }
            )
    except Exception as exc:
        print(f"[feishu-push-all] failed user_id={current_user.id} processed={processed}/{len(note_ids)} error={exc}", flush=True)
        return {
            "dry_run": payload.dry_run,
            "total_count": len(note_ids),
            "processed_count": processed,
            "created_count": created,
            "updated_count": updated,
            "failed_count": len(note_ids) - processed + failed,
            "errors": [*errors, str(exc)],
            "records": records,
            "batches": batches,
        }

    return {
        "dry_run": payload.dry_run,
        "total_count": len(note_ids),
        "processed_count": processed,
        "created_count": created,
        "updated_count": updated,
        "failed_count": failed,
        "errors": errors,
        "records": records,
        "batches": batches,
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
    member_type, member_id, perm = _normalize_collaborator(payload.collaborator_member_type, payload.collaborator_member_id, payload.collaborator_perm)
    config.collaborator_member_type = member_type
    config.collaborator_member_id = member_id
    config.collaborator_perm = perm
    config.enabled = bool(payload.enabled)
    config.updated_at = shanghai_now()
    db.commit()
    db.refresh(config)
    return _serialize_config(config)

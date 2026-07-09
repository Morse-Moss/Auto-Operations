from __future__ import annotations

import re
from typing import Optional

import requests as http_requests
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.deps import get_current_tenant_context, require_admin_user
from backend.app.core.security import encrypt_text
from backend.app.models import DEFAULT_TEXT_MODEL_NAME, ApiLog, ModelConfig, User
from backend.app.schemas.common import paginated
from backend.app.services.ai_service import RUNNINGHUB_DEFAULT_BASE_URL
from backend.app.services.usage_quota_service import CREDITS_BUCKET, UsageQuotaService, credit_cost_for_feature, usage_idempotency_key

router = APIRouter(prefix="/model-configs", tags=["model-configs"])

MODEL_TEST_FEATURE_KEY = "model_config.test"
MODEL_TEST_IMAGE_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)
VOLCENGINE_ARK_PROVIDER = "volcengine-ark"
VOLCENGINE_ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DOUBAO_MAIN_MODEL_NAME = DEFAULT_TEXT_MODEL_NAME


class ModelConfigCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    model_type: str = Field(pattern="^(text|image)$")
    provider: str = Field(min_length=1, max_length=64)
    model_name: str = Field(default="", max_length=128)
    base_url: str = ""
    api_key: str = ""
    is_default: bool = False


class ModelConfigUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    provider: Optional[str] = Field(default=None, min_length=1, max_length=64)
    model_name: Optional[str] = Field(default=None, max_length=128)
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    is_default: Optional[bool] = None


class DoubaoMainConfigRequest(BaseModel):
    api_key: str = Field(min_length=1)


def _serialize_config(config: ModelConfig) -> dict:
    return {
        "id": config.id,
        "name": config.name,
        "model_type": config.model_type,
        "provider": config.provider,
        "model_name": config.model_name,
        "base_url": config.base_url,
        "has_api_key": bool(config.encrypted_api_key),
        "is_default": config.is_default,
    }


def _default_model_name(model_type: str) -> str:
    return DEFAULT_TEXT_MODEL_NAME if model_type in {"text", "image"} else ""


def _normalize_model_name(model_type: str, model_name: Optional[str]) -> str:
    if model_name == "gpt5.4":
        return "gpt-5.4"
    cleaned = (model_name or "").strip()
    return cleaned or _default_model_name(model_type)


def _get_owned_config(db: Session, current_user: User, config_id: int) -> ModelConfig:
    config = db.get(ModelConfig, config_id)
    if config is None or config.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model config not found")
    return config


def _clear_default_for_type(db: Session, user_id: int, model_type: str) -> None:
    configs = db.scalars(
        select(ModelConfig).where(ModelConfig.user_id == user_id, ModelConfig.model_type == model_type)
    ).all()
    for config in configs:
        config.is_default = False


def _upsert_doubao_main_config(db: Session, *, current_user: User, model_type: str, name: str, api_key: str) -> ModelConfig:
    config = db.scalars(
        select(ModelConfig)
        .where(
            ModelConfig.user_id == current_user.id,
            ModelConfig.model_type == model_type,
            ModelConfig.provider == VOLCENGINE_ARK_PROVIDER,
            ModelConfig.model_name == DOUBAO_MAIN_MODEL_NAME,
        )
        .order_by(ModelConfig.id.asc())
    ).first()
    if config is None:
        config = ModelConfig(user_id=current_user.id, model_type=model_type)
        db.add(config)

    _clear_default_for_type(db, current_user.id, model_type)
    config.name = name
    config.provider = VOLCENGINE_ARK_PROVIDER
    config.model_name = DOUBAO_MAIN_MODEL_NAME
    config.base_url = VOLCENGINE_ARK_BASE_URL
    config.encrypted_api_key = encrypt_text(api_key)
    config.is_default = True
    return config


def _redact_api_key(message: object, api_key: str) -> str:
    redacted = str(message)
    if api_key:
        redacted = redacted.replace(api_key, "[REDACTED]")
    redacted = re.sub(r"(?i)(api[_-]?key=)[^&\s\"'}]+", r"\1[REDACTED]", redacted)
    return redacted


def _record_model_test_attempt(db: Session, *, current_user: User, config: ModelConfig, result_status: str) -> None:
    db.add(
        ApiLog(
            user_id=current_user.id,
            platform="ai",
            endpoint="model_config.test",
            status=result_status,
            meta={
                "feature_key": "model_test",
                "model_config_id": config.id,
                "model_type": config.model_type,
                "provider": config.provider,
            },
        )
    )
    db.commit()


@router.get("")
def get_model_configs(
    model_type: Optional[str] = Query(default=None, pattern="^(text|image)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    statement = select(ModelConfig).where(ModelConfig.user_id == current_user.id)
    if model_type:
        statement = statement.where(ModelConfig.model_type == model_type)
    configs = db.scalars(statement.order_by(ModelConfig.id.desc())).all()
    return paginated([_serialize_config(config) for config in configs], page, page_size)


@router.post("")
def create_model_config(
    payload: ModelConfigCreateRequest,
    current_user: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    if payload.is_default:
        _clear_default_for_type(db, current_user.id, payload.model_type)

    config = ModelConfig(
        user_id=current_user.id,
        name=payload.name,
        model_type=payload.model_type,
        provider=payload.provider,
        model_name=_normalize_model_name(payload.model_type, payload.model_name),
        base_url=payload.base_url,
        encrypted_api_key=encrypt_text(payload.api_key) if payload.api_key else "",
        is_default=payload.is_default,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return _serialize_config(config)


@router.post("/doubao-main")
def configure_doubao_main_models(
    payload: DoubaoMainConfigRequest,
    current_user: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    text_config = _upsert_doubao_main_config(
        db,
        current_user=current_user,
        model_type="text",
        name="Doubao Seed 2.0 Mini Text",
        api_key=payload.api_key,
    )
    vision_config = _upsert_doubao_main_config(
        db,
        current_user=current_user,
        model_type="image",
        name="Doubao Seed 2.0 Mini Vision",
        api_key=payload.api_key,
    )
    db.commit()
    db.refresh(text_config)
    db.refresh(vision_config)
    return {
        "text": _serialize_config(text_config),
        "vision": _serialize_config(vision_config),
    }


@router.post("/{config_id}/test")
def test_model_config(
    config_id: int,
    request: Request,
    current_user: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    from backend.app.core.security import decrypt_text

    config = _get_owned_config(db, current_user, config_id)
    if not config.encrypted_api_key:
        return {"id": config.id, "status": "error", "message": "未配置 API Key"}

    if config.provider == "runninghub-ai-app" and config.model_type != "image":
        return {
            "id": config.id,
            "status": "error",
            "message": "RunningHub provider only supports image model configs",
        }

    api_key = decrypt_text(config.encrypted_api_key)
    if config.provider == "runninghub-ai-app":
        base_url = (config.base_url or RUNNINGHUB_DEFAULT_BASE_URL).rstrip("/")
    elif not config.base_url:
        return {"id": config.id, "status": "error", "message": "未配置 Base URL"}
    else:
        base_url = config.base_url.rstrip("/")

    tenant_context = get_current_tenant_context(current_user=current_user, db=db)
    usage_reservation = UsageQuotaService(db).reserve(
        tenant_id=tenant_context.tenant.id,
        user_id=current_user.id,
        feature_key=MODEL_TEST_FEATURE_KEY,
        bucket=CREDITS_BUCKET,
        amount=credit_cost_for_feature(MODEL_TEST_FEATURE_KEY),
        idempotency_key=usage_idempotency_key(request, f"{MODEL_TEST_FEATURE_KEY}:{current_user.id}:{config.id}"),
        request_summary={"model_config_id": config.id, "model_type": config.model_type, "provider": config.provider},
        model_config_id=config.id,
        provider=config.provider,
    )

    def finish(result: dict) -> dict:
        _record_model_test_attempt(db, current_user=current_user, config=config, result_status=result["status"])
        UsageQuotaService(db).commit(usage_reservation.id)
        return result

    try:
        if config.provider == "runninghub-ai-app":
            resp = http_requests.get(
                f"{base_url}/api/webapp/apiCallDemo",
                headers={"Authorization": f"Bearer {api_key}", "Host": "www.runninghub.cn"},
                params={"apiKey": api_key, "webappId": "2046760522573418497"},
                timeout=15,
            )
        elif config.model_type == "image":
            resp = http_requests.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": config.model_name,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "image_url", "image_url": {"url": MODEL_TEST_IMAGE_DATA_URL}},
                                {"type": "text", "text": "请用一句话描述这张图片。"},
                            ],
                        }
                    ],
                    "max_tokens": 32,
                },
                timeout=15,
            )
        else:
            resp = http_requests.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": config.model_name, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5},
                timeout=15,
            )

        if resp.status_code < 400:
            try:
                body = resp.json()
                if config.provider == "runninghub-ai-app":
                    if body.get("code") != 0 or not isinstance(body.get("data"), dict):
                        message = body.get("msg") or body.get("message") or body
                        return finish(
                            {
                                "id": config.id,
                                "status": "error",
                                "message": _redact_api_key(f"RunningHub 连接失败: {message}", api_key)[:200],
                            }
                        )
                    return finish({"id": config.id, "status": "ok", "message": f"连接成功 ({resp.status_code})"})
                if body.get("choices") or body.get("data") or body.get("object"):
                    return finish({"id": config.id, "status": "ok", "message": f"连接成功 ({resp.status_code})"})
                return finish(
                    {
                        "id": config.id,
                        "status": "error",
                        "message": _redact_api_key(f"响应格式异常: {resp.text[:150]}", api_key),
                    }
                )
            except Exception:
                return finish(
                    {
                        "id": config.id,
                        "status": "error",
                        "message": _redact_api_key(f"响应非 JSON: {resp.text[:150]}", api_key),
                    }
                )
        return finish(
            {
                "id": config.id,
                "status": "error",
                "message": _redact_api_key(f"HTTP {resp.status_code}: {resp.text[:150]}", api_key),
            }
        )
    except Exception as exc:
        return finish({"id": config.id, "status": "error", "message": _redact_api_key(exc, api_key)[:200]})


@router.patch("/{config_id}")
def update_model_config(
    config_id: int,
    payload: ModelConfigUpdateRequest,
    current_user: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    config = _get_owned_config(db, current_user, config_id)

    if payload.name is not None:
        config.name = payload.name
    if payload.provider is not None:
        config.provider = payload.provider
    if payload.model_name is not None:
        config.model_name = _normalize_model_name(config.model_type, payload.model_name)
    if payload.base_url is not None:
        config.base_url = payload.base_url
    if payload.api_key is not None:
        config.encrypted_api_key = encrypt_text(payload.api_key) if payload.api_key else ""
    if payload.is_default is not None:
        if payload.is_default:
            _clear_default_for_type(db, current_user.id, config.model_type)
        config.is_default = payload.is_default

    db.commit()
    db.refresh(config)
    return _serialize_config(config)


@router.delete("/{config_id}")
def delete_model_config(
    config_id: int,
    current_user: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    config = _get_owned_config(db, current_user, config_id)
    db.delete(config)
    db.commit()
    return {"id": config_id, "status": "deleted"}


@router.post("/{config_id}/set-default")
def set_default_model_config(
    config_id: int,
    current_user: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    config = _get_owned_config(db, current_user, config_id)
    _clear_default_for_type(db, current_user.id, config.model_type)
    config.is_default = True
    db.commit()
    db.refresh(config)
    return _serialize_config(config)

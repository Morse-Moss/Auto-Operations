from __future__ import annotations

import re
from typing import Optional

import requests as http_requests
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.deps import get_current_user
from backend.app.core.security import encrypt_text
from backend.app.core.time import shanghai_now
from backend.app.models import DEFAULT_TEXT_MODEL_NAME, ApiLog, ModelConfig, User
from backend.app.schemas.common import paginated
from backend.app.services.ai_service import RUNNINGHUB_DEFAULT_BASE_URL

router = APIRouter(prefix="/model-configs", tags=["model-configs"])

MODEL_TEST_DAILY_FREE_LIMIT = 3


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
    return DEFAULT_TEXT_MODEL_NAME if model_type == "text" else ""


def _normalize_model_name(model_type: str, model_name: Optional[str]) -> str:
    if model_name == "gpt5.4":
        return DEFAULT_TEXT_MODEL_NAME
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


def _redact_api_key(message: object, api_key: str) -> str:
    redacted = str(message)
    if api_key:
        redacted = redacted.replace(api_key, "[REDACTED]")
    redacted = re.sub(r"(?i)(api[_-]?key=)[^&\s\"'}]+", r"\1[REDACTED]", redacted)
    return redacted


def _model_test_daily_start():
    now = shanghai_now()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _model_test_count_today(db: Session, user_id: int) -> int:
    return int(
        db.scalar(
            select(func.count(ApiLog.id)).where(
                ApiLog.user_id == user_id,
                ApiLog.endpoint == "model_config.test",
                ApiLog.created_at >= _model_test_daily_start(),
            )
        )
        or 0
    )


def _model_test_limit_response(used: int) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "code": "model_test_daily_limit_exceeded",
            "message": f"模型连接测试每日免费 {MODEL_TEST_DAILY_FREE_LIMIT} 次，今天已用完。",
            "feature_key": "model_test",
            "limit": MODEL_TEST_DAILY_FREE_LIMIT,
            "used": used,
        },
    )


def _record_model_test_attempt(db: Session, *, current_user: User, config: ModelConfig, result_status: str, used_before: int) -> None:
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
                "attempt": used_before + 1,
                "limit": MODEL_TEST_DAILY_FREE_LIMIT,
            },
        )
    )
    db.commit()


@router.get("")
def get_model_configs(
    model_type: Optional[str] = Query(default=None, pattern="^(text|image)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
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


@router.post("/{config_id}/test")
def test_model_config(
    config_id: int,
    current_user: User = Depends(get_current_user),
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

    used_today = _model_test_count_today(db, current_user.id)
    if used_today >= MODEL_TEST_DAILY_FREE_LIMIT:
        return _model_test_limit_response(used_today)

    def finish(result: dict) -> dict:
        _record_model_test_attempt(db, current_user=current_user, config=config, result_status=result["status"], used_before=used_today)
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
                f"{base_url}/images/generations",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": config.model_name, "prompt": "test", "n": 1, "size": "256x256"},
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
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    config = _get_owned_config(db, current_user, config_id)
    db.delete(config)
    db.commit()
    return {"id": config_id, "status": "deleted"}


@router.post("/{config_id}/set-default")
def set_default_model_config(
    config_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    config = _get_owned_config(db, current_user, config_id)
    _clear_default_for_type(db, current_user.id, config.model_type)
    config.is_default = True
    db.commit()
    db.refresh(config)
    return _serialize_config(config)

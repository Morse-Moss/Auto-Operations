from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.security import decrypt_text
from backend.app.models import ModelConfig, User

ModelCapability = str
IMAGE_GENERATION_PROVIDERS = {"runninghub-ai-app", "openai-compatible"}
VISION_PROVIDERS = {"volcengine-ark", "openai-compatible"}


def _supports_capability(config: ModelConfig, capability: ModelCapability | None) -> bool:
    if capability is None:
        return True
    if capability == "image_generation":
        return config.provider in IMAGE_GENERATION_PROVIDERS
    if capability == "vision":
        return config.provider in VISION_PROVIDERS
    if capability == "text":
        return config.model_type == "text"
    return True


def _first_supported(configs: list[ModelConfig], capability: ModelCapability | None) -> ModelConfig | None:
    for config in configs:
        if _supports_capability(config, capability):
            return config
    return None


def get_default_model_config(
    db: Session,
    *,
    user_id: int,
    model_type: str,
    capability: ModelCapability | None = None,
) -> ModelConfig | None:
    user_configs = db.scalars(
        select(ModelConfig).where(
            ModelConfig.user_id == user_id,
            ModelConfig.model_type == model_type,
            ModelConfig.is_default.is_(True),
        )
    ).all()
    config = _first_supported(user_configs, capability)
    if config is not None:
        return config

    admin_configs = db.scalars(
        select(ModelConfig)
        .join(User, User.id == ModelConfig.user_id)
        .where(
            User.role == "admin",
            User.status == "active",
            ModelConfig.model_type == model_type,
        )
        .order_by(ModelConfig.is_default.desc(), ModelConfig.id.asc())
    ).all()
    return _first_supported(admin_configs, capability)


def require_default_model_context(
    db: Session,
    *,
    user_id: int,
    model_type: str,
    capability: ModelCapability | None = None,
) -> tuple[ModelConfig, str]:
    model_config = get_default_model_config(db, user_id=user_id, model_type=model_type, capability=capability)
    if model_config is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Default {model_type} model is not configured",
        )
    api_key = decrypt_text(model_config.encrypted_api_key) if model_config.encrypted_api_key else ""
    return model_config, api_key

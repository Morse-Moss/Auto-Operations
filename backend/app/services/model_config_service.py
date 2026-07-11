from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.security import decrypt_text
from backend.app.models import ModelCapabilityDefault, ModelConfig, User

MODEL_CAPABILITIES = ("text", "vision", "image_generation")
IMAGE_GENERATION_PROVIDERS = {"runninghub-ai-app", "openai-compatible"}
VISION_PROVIDERS = {"volcengine-ark", "openai-compatible"}


def supported_capabilities(config: ModelConfig) -> list[str]:
    supported: list[str] = []
    if config.model_type == "text":
        supported.append("text")
    if config.model_type == "image" and config.provider in VISION_PROVIDERS:
        supported.append("vision")
    if config.model_type == "image" and config.provider in IMAGE_GENERATION_PROVIDERS:
        supported.append("image_generation")
    return supported


def assigned_capabilities(db: Session, model_config_id: int) -> list[str]:
    return list(
        db.scalars(
            select(ModelCapabilityDefault.capability)
            .where(ModelCapabilityDefault.model_config_id == model_config_id)
            .order_by(ModelCapabilityDefault.capability.asc())
        ).all()
    )


def _capability_binding(db: Session, capability: str) -> ModelCapabilityDefault | None:
    if capability not in MODEL_CAPABILITIES:
        raise ValueError(f"Unsupported model capability: {capability}")
    return db.scalar(
        select(ModelCapabilityDefault).where(
            ModelCapabilityDefault.capability == capability
        )
    )


def _active_admin_owner(db: Session, config: ModelConfig) -> User | None:
    owner = db.get(User, config.user_id)
    if owner is None or owner.role != "admin" or owner.status != "active":
        return None
    return owner


def get_model_config_for_capability(
    db: Session,
    capability: str,
) -> ModelConfig | None:
    binding = _capability_binding(db, capability)
    if binding is None:
        return None
    config = db.get(ModelConfig, binding.model_config_id)
    if config is None or _active_admin_owner(db, config) is None:
        return None
    if capability not in supported_capabilities(config):
        return None
    if not config.model_name or not config.base_url or not config.encrypted_api_key:
        return None
    return config


def _capability_error(capability: str, code: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"code": code, "capability": capability},
    )


def require_model_capability_context(
    db: Session,
    capability: str,
) -> tuple[ModelConfig, str]:
    binding = _capability_binding(db, capability)
    if binding is None:
        raise _capability_error(
            capability,
            "MODEL_CAPABILITY_DEFAULT_NOT_CONFIGURED",
        )
    config = db.get(ModelConfig, binding.model_config_id)
    if config is None or _active_admin_owner(db, config) is None:
        raise _capability_error(capability, "MODEL_CAPABILITY_DEFAULT_INVALID")
    if capability not in supported_capabilities(config):
        raise _capability_error(
            capability,
            "MODEL_CAPABILITY_DEFAULT_INCOMPATIBLE",
        )
    if not config.model_name or not config.base_url or not config.encrypted_api_key:
        raise _capability_error(capability, "MODEL_CAPABILITY_DEFAULT_INCOMPLETE")
    try:
        api_key = decrypt_text(config.encrypted_api_key)
    except Exception as exc:
        raise _capability_error(
            capability,
            "MODEL_CAPABILITY_DEFAULT_INVALID",
        ) from exc
    if not api_key:
        raise _capability_error(capability, "MODEL_CAPABILITY_DEFAULT_INCOMPLETE")
    return config, api_key

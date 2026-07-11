from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import ModelCapabilityDefault, ModelConfig, User


def bind_test_model_capability(
    db: Session,
    *,
    config: ModelConfig,
    capability: str,
) -> ModelCapabilityDefault:
    owner = db.get(User, config.user_id)
    assert owner is not None
    owner.role = "admin"
    owner.status = "active"
    db.add(config)
    db.flush()

    binding = db.scalar(
        select(ModelCapabilityDefault).where(
            ModelCapabilityDefault.capability == capability
        )
    )
    if binding is None:
        binding = ModelCapabilityDefault(capability=capability)
        db.add(binding)
    binding.model_config_id = config.id
    binding.updated_by_user_id = owner.id
    db.flush()
    return binding

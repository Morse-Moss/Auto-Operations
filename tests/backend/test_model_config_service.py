import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import Base
from backend.app.core.security import encrypt_text
from backend.app.models import ModelCapabilityDefault, ModelConfig, User
from backend.app.services.model_config_service import (
    get_model_config_for_capability,
    require_model_capability_context,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def seed_user(db_session, *, role: str = "admin", status: str = "active") -> User:
    user = User(
        username=f"{role}-{status}-{db_session.query(User).count()}",
        password_hash="test",
        role=role,
        status=status,
    )
    db_session.add(user)
    db_session.flush()
    return user


def seed_config(
    db_session,
    user_id: int,
    *,
    provider: str,
    model_type: str,
    encrypted_api_key: str | None = None,
) -> ModelConfig:
    config = ModelConfig(
        user_id=user_id,
        name=f"{provider}-{model_type}",
        model_type=model_type,
        provider=provider,
        model_name="test-model",
        base_url="https://api.example.test/v1",
        encrypted_api_key=(
            encrypt_text("sk-test")
            if encrypted_api_key is None
            else encrypted_api_key
        ),
        is_default=False,
    )
    db_session.add(config)
    db_session.flush()
    return config


def test_model_capability_defaults_table_has_unique_capability_and_restricting_foreign_keys():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)

    columns = {column["name"] for column in inspector.get_columns("model_capability_defaults")}
    unique_sets = {
        tuple(item["column_names"])
        for item in inspector.get_unique_constraints("model_capability_defaults")
    }
    foreign_keys = {
        tuple(item["constrained_columns"]): item
        for item in inspector.get_foreign_keys("model_capability_defaults")
    }

    assert columns == {
        "id",
        "capability",
        "model_config_id",
        "updated_by_user_id",
        "created_at",
        "updated_at",
    }
    assert ("capability",) in unique_sets
    assert foreign_keys[("model_config_id",)]["referred_table"] == "model_configs"
    assert ModelCapabilityDefault.__tablename__ == "model_capability_defaults"


def test_image_generation_uses_explicit_binding_even_when_older_compatible_config_exists(db_session):
    admin = seed_user(db_session)
    stale = seed_config(
        db_session,
        admin.id,
        provider="openai-compatible",
        model_type="image",
    )
    runninghub = seed_config(
        db_session,
        admin.id,
        provider="runninghub-ai-app",
        model_type="image",
    )
    db_session.add(
        ModelCapabilityDefault(
            capability="image_generation",
            model_config_id=runninghub.id,
            updated_by_user_id=admin.id,
        )
    )
    db_session.commit()

    selected = get_model_config_for_capability(db_session, "image_generation")

    assert stale.id < runninghub.id
    assert selected is not None
    assert selected.id == runninghub.id


@pytest.mark.parametrize("capability", ["text", "vision", "image_generation"])
def test_required_capability_fails_closed_without_binding(db_session, capability):
    with pytest.raises(HTTPException) as exc_info:
        require_model_capability_context(db_session, capability)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == {
        "code": "MODEL_CAPABILITY_DEFAULT_NOT_CONFIGURED",
        "capability": capability,
    }


def test_required_capability_rejects_binding_owned_by_inactive_admin(db_session):
    admin = seed_user(db_session, status="disabled")
    config = seed_config(
        db_session,
        admin.id,
        provider="runninghub-ai-app",
        model_type="image",
    )
    db_session.add(
        ModelCapabilityDefault(
            capability="image_generation",
            model_config_id=config.id,
            updated_by_user_id=admin.id,
        )
    )
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        require_model_capability_context(db_session, "image_generation")

    assert exc_info.value.detail["code"] == "MODEL_CAPABILITY_DEFAULT_INVALID"


def test_required_capability_rejects_incompatible_binding(db_session):
    admin = seed_user(db_session)
    config = seed_config(
        db_session,
        admin.id,
        provider="volcengine-ark",
        model_type="image",
    )
    db_session.add(
        ModelCapabilityDefault(
            capability="image_generation",
            model_config_id=config.id,
            updated_by_user_id=admin.id,
        )
    )
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        require_model_capability_context(db_session, "image_generation")

    assert exc_info.value.detail["code"] == "MODEL_CAPABILITY_DEFAULT_INCOMPATIBLE"


def test_required_capability_rejects_incomplete_binding(db_session):
    admin = seed_user(db_session)
    config = seed_config(
        db_session,
        admin.id,
        provider="runninghub-ai-app",
        model_type="image",
        encrypted_api_key="",
    )
    db_session.add(
        ModelCapabilityDefault(
            capability="image_generation",
            model_config_id=config.id,
            updated_by_user_id=admin.id,
        )
    )
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        require_model_capability_context(db_session, "image_generation")

    assert exc_info.value.detail["code"] == "MODEL_CAPABILITY_DEFAULT_INCOMPLETE"


def test_required_capability_returns_decrypted_key(db_session):
    admin = seed_user(db_session)
    config = seed_config(
        db_session,
        admin.id,
        provider="runninghub-ai-app",
        model_type="image",
    )
    db_session.add(
        ModelCapabilityDefault(
            capability="image_generation",
            model_config_id=config.id,
            updated_by_user_id=admin.id,
        )
    )
    db_session.commit()

    selected, api_key = require_model_capability_context(
        db_session,
        "image_generation",
    )

    assert selected.id == config.id
    assert api_key == "sk-test"

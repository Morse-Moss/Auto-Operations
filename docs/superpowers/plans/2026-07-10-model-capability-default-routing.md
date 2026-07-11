# Model Capability Default Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace implicit model fallback with administrator-managed, system-wide defaults for text, vision, and image-generation capabilities.

**Architecture:** Store one explicit `ModelConfig` binding per capability in a new normalized table. Route every AI call through a single capability resolver that validates the bound admin configuration and fails closed before quota reservation; expose the bindings through admin APIs and a focused routing panel on the existing model configuration page.

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy, Alembic, SQLite/MySQL-compatible schema, React 19, TypeScript, Vite, Ant Design, pytest.

---

## Execution Constraints

- Work in `E:\小红书` on `master`; the current root worktree is dirty, so modify only the files named in this plan.
- Do not stage, commit, push, stop/restart `18080/18081`, or call a real paid image provider without separate authorization.
- Use mocked Provider requests for tests.
- Run database migration verification against a temporary SQLite database, not `data/spider_xhs.db`.

## File Map

- `backend/app/models/ai.py`: define the capability-default entity.
- `backend/app/models/__init__.py`: export the entity.
- `backend/alembic/versions/20260710_model_capability_defaults.py`: create and conservatively backfill the table.
- `backend/app/services/model_config_service.py`: own capability constants, compatibility checks, exact selection, and fail-closed errors.
- `backend/app/api/model_configs.py`: expose routing CRUD, capability metadata, test routing, and delete protection.
- `backend/app/api/ai.py`: request capability contexts and sanitize model-configuration failures.
- `backend/app/services/scheduler_service.py`, `backend/app/services/note_analysis_service.py`, `backend/app/services/feishu_bitable_service.py`, `backend/app/services/wechat_official_content_service.py`, `backend/app/api/auto_tasks.py`: replace legacy default scans with exact capability lookup.
- `frontend/src/types/index.ts`: add capability-routing contracts.
- `frontend/src/lib/api.ts`: add capability-routing API functions and capability-aware model tests.
- `frontend/src/pages/models/model-config-page.tsx`: add the administrator routing panel and remove ambiguous type-default controls.
- `tests/backend/test_api.py`: cover model routing APIs and request-path regression behavior.
- `tests/backend/test_model_config_service.py`: cover resolver behavior in isolation.
- `tests/frontend/test_model_capability_routing_contract.py`: protect the management-page contract.

### Task 1: Add Capability Default Persistence

**Files:**
- Create: `tests/backend/test_model_config_service.py`
- Modify: `backend/app/models/ai.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/20260710_model_capability_defaults.py`

- [ ] **Step 1: Write the failing model metadata test**

Create `tests/backend/test_model_config_service.py` with an in-memory SQLite session helper and this assertion:

```python
from sqlalchemy import create_engine, inspect

from backend.app.core.database import Base
from backend.app.models import ModelCapabilityDefault


def test_model_capability_defaults_table_has_unique_capability_and_restricting_foreign_keys():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)

    columns = {column["name"] for column in inspector.get_columns("model_capability_defaults")}
    unique_sets = {tuple(item["column_names"]) for item in inspector.get_unique_constraints("model_capability_defaults")}
    foreign_keys = {tuple(item["constrained_columns"]): item for item in inspector.get_foreign_keys("model_capability_defaults")}

    assert columns == {"id", "capability", "model_config_id", "updated_by_user_id", "created_at", "updated_at"}
    assert ("capability",) in unique_sets
    assert foreign_keys[("model_config_id",)]["referred_table"] == "model_configs"
    assert ModelCapabilityDefault.__tablename__ == "model_capability_defaults"
```

- [ ] **Step 2: Run the metadata test and confirm RED**

Run: `py -X utf8 -m pytest tests/backend/test_model_config_service.py::test_model_capability_defaults_table_has_unique_capability_and_restricting_foreign_keys -q`

Expected: FAIL because `ModelCapabilityDefault` is not defined/exported.

- [ ] **Step 3: Add the SQLAlchemy model and export**

Add this model to `backend/app/models/ai.py` and export it from `backend/app/models/__init__.py`:

```python
class ModelCapabilityDefault(Base):
    __tablename__ = "model_capability_defaults"
    __table_args__ = (UniqueConstraint("capability", name="uq_model_capability_defaults_capability"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    capability: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model_config_id: Mapped[int] = mapped_column(ForeignKey("model_configs.id", ondelete="RESTRICT"), nullable=False, index=True)
    updated_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now, onupdate=shanghai_now)
```

Update imports in `ai.py` to include `UniqueConstraint`; existing `DateTime`, `ForeignKey`, `Integer`, `String`, `Mapped`, `mapped_column`, and `shanghai_now` remain reused.

- [ ] **Step 4: Add the Alembic migration**

Create revision `20260710_model_capability_defaults` with `down_revision = "20260708_usage_ledger_followup_unique"`. The migration must:

```python
CAPABILITIES = {
    "text": ("text", None),
    "vision": ("image", {"volcengine-ark", "openai-compatible"}),
    "image_generation": ("image", {"runninghub-ai-app", "openai-compatible"}),
}


def _candidate_rows(bind, *, model_type: str, providers: set[str] | None, require_default: bool):
    conditions = ["u.role = 'admin'", "u.status = 'active'", "mc.model_type = :model_type"]
    params = {"model_type": model_type}
    if require_default:
        conditions.append("mc.is_default = 1")
    if providers:
        placeholders = []
        for index, provider in enumerate(sorted(providers)):
            key = f"provider_{index}"
            params[key] = provider
            placeholders.append(f":{key}")
        conditions.append(f"mc.provider IN ({','.join(placeholders)})")
    query = sa.text(
        "SELECT mc.id AS model_config_id, mc.user_id AS updated_by_user_id "
        "FROM model_configs mc JOIN users u ON u.id = mc.user_id WHERE " + " AND ".join(conditions)
    )
    return list(bind.execute(query, params).mappings())
```

After table creation, insert a binding only when the candidate list has exactly one row. Use `require_default=True` for `text` and `vision`, and `require_default=False` for `image_generation`. Never sort and pick a candidate.

- [ ] **Step 5: Run the metadata test and Alembic head check**

Run:

```powershell
py -X utf8 -m pytest tests/backend/test_model_config_service.py::test_model_capability_defaults_table_has_unique_capability_and_restricting_foreign_keys -q
py -X utf8 -m alembic -c backend/alembic.ini heads
```

Expected: test PASS; Alembic prints exactly `20260710_model_capability_defaults (head)`.

### Task 2: Build the Exact Capability Resolver

**Files:**
- Modify: `tests/backend/test_model_config_service.py`
- Modify: `backend/app/services/model_config_service.py`

- [ ] **Step 1: Write failing resolver tests**

Add a session factory and seed helper, then cover these exact behaviors:

```python
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import Base
from backend.app.core.security import encrypt_text
from backend.app.models import ModelCapabilityDefault, ModelConfig, User
from backend.app.services.model_config_service import get_model_config_for_capability, require_model_capability_context


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
    user = User(username=f"{role}-{status}-{db_session.query(User).count()}", password_hash="test", role=role, status=status)
    db_session.add(user)
    db_session.flush()
    return user


def seed_config(db_session, user_id: int, *, provider: str, model_type: str) -> ModelConfig:
    config = ModelConfig(
        user_id=user_id,
        name=f"{provider}-{model_type}",
        model_type=model_type,
        provider=provider,
        model_name="test-model",
        base_url="https://api.example.test/v1",
        encrypted_api_key=encrypt_text("sk-test"),
        is_default=False,
    )
    db_session.add(config)
    db_session.flush()
    return config


def test_image_generation_uses_explicit_binding_even_when_older_compatible_config_exists(db_session):
    admin = seed_user(db_session, role="admin", status="active")
    stale = seed_config(db_session, admin.id, provider="openai-compatible", model_type="image")
    runninghub = seed_config(db_session, admin.id, provider="runninghub-ai-app", model_type="image")
    db_session.add(ModelCapabilityDefault(capability="image_generation", model_config_id=runninghub.id, updated_by_user_id=admin.id))
    db_session.commit()

    selected = get_model_config_for_capability(db_session, "image_generation")

    assert stale.id < runninghub.id
    assert selected.id == runninghub.id


@pytest.mark.parametrize(
    ("capability", "code"),
    [
        ("text", "MODEL_CAPABILITY_DEFAULT_NOT_CONFIGURED"),
        ("vision", "MODEL_CAPABILITY_DEFAULT_NOT_CONFIGURED"),
        ("image_generation", "MODEL_CAPABILITY_DEFAULT_NOT_CONFIGURED"),
    ],
)
def test_required_capability_fails_closed_without_binding(db_session, capability, code):
    with pytest.raises(HTTPException) as exc_info:
        require_model_capability_context(db_session, capability)
    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["code"] == code
```

Also add tests for inactive admin ownership, incompatible Provider/type, missing encrypted key, and successful decryption.

- [ ] **Step 2: Run resolver tests and confirm RED**

Run: `py -X utf8 -m pytest tests/backend/test_model_config_service.py -q`

Expected: FAIL because the capability constants and resolver functions do not exist.

- [ ] **Step 3: Implement the resolver**

Replace implicit admin scanning with these public concepts in `model_config_service.py`:

```python
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


def get_model_config_for_capability(db: Session, capability: str) -> ModelConfig | None:
    if capability not in MODEL_CAPABILITIES:
        raise ValueError(f"Unsupported model capability: {capability}")
    statement = (
        select(ModelConfig)
        .join(ModelCapabilityDefault, ModelCapabilityDefault.model_config_id == ModelConfig.id)
        .join(User, User.id == ModelConfig.user_id)
        .where(
            ModelCapabilityDefault.capability == capability,
            User.role == "admin",
            User.status == "active",
        )
    )
    config = db.scalars(statement).first()
    if config is None or capability not in supported_capabilities(config):
        return None
    return config


def require_model_capability_context(db: Session, capability: str) -> tuple[ModelConfig, str]:
    config = get_model_config_for_capability(db, capability)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "MODEL_CAPABILITY_DEFAULT_NOT_CONFIGURED", "capability": capability},
        )
    if not config.model_name or not config.base_url or not config.encrypted_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "MODEL_CAPABILITY_DEFAULT_INCOMPLETE", "capability": capability},
        )
    return config, decrypt_text(config.encrypted_api_key)
```

Differentiate invalid ownership/binding from missing binding by querying the binding first; return the stable error codes from the design instead of collapsing every case into NOT_CONFIGURED.

- [ ] **Step 4: Run resolver tests and confirm GREEN**

Run: `py -X utf8 -m pytest tests/backend/test_model_config_service.py -q`

Expected: all tests PASS.

### Task 3: Add Administrator Capability Routing APIs

**Files:**
- Modify: `tests/backend/test_api.py`
- Modify: `backend/app/api/model_configs.py`

- [ ] **Step 1: Write failing API tests**

Using the existing `_override_database`, registration helpers, and authenticated client, add tests that assert:

```python
def _create_test_model_config(token: str, **overrides) -> dict:
    payload = {
        "name": "Test model",
        "model_type": "image",
        "provider": "openai-compatible",
        "model_name": "test-model",
        "base_url": "https://api.example.test/v1",
        "api_key": "sk-test",
        "is_default": False,
    }
    payload.update(overrides)
    response = client.post("/api/model-configs", headers={"Authorization": f"Bearer {token}"}, json=payload)
    assert response.status_code == 200
    return response.json()


def test_admin_can_assign_distinct_vision_and_image_generation_defaults(tmp_path):
    db_dependency = _override_database(tmp_path)
    admin_token = _register_and_get_admin_access_token("capability-default-admin")
    headers = {"Authorization": f"Bearer {admin_token}"}
    try:
        vision = _create_test_model_config(
            admin_token,
            name="Vision",
            provider="volcengine-ark",
            model_name="doubao-seed-2-0-mini-260428",
            base_url="https://ark.cn-beijing.volces.com/api/v3",
        )
        generation = _create_test_model_config(
            admin_token,
            name="RunningHub",
            provider="runninghub-ai-app",
            model_name="runninghub-image-g",
            base_url="https://www.runninghub.cn",
        )

        assert client.put("/api/model-configs/capability-defaults/vision", headers=headers, json={"model_config_id": vision["id"]}).status_code == 200
        assert client.put("/api/model-configs/capability-defaults/image_generation", headers=headers, json={"model_config_id": generation["id"]}).status_code == 200
        response = client.get("/api/model-configs/capability-defaults", headers=headers)

        assert response.status_code == 200
        by_capability = {item["capability"]: item for item in response.json()["items"]}
        assert by_capability["text"]["model_config"] is None
        assert by_capability["vision"]["model_config"]["provider"] == "volcengine-ark"
        assert by_capability["image_generation"]["model_config"]["provider"] == "runninghub-ai-app"
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_capability_assignment_rejects_incompatible_model(tmp_path):
    db_dependency = _override_database(tmp_path)
    admin_token = _register_and_get_admin_access_token("capability-incompatible-admin")
    headers = {"Authorization": f"Bearer {admin_token}"}
    try:
        text_config = _create_test_model_config(admin_token, model_type="text", provider="volcengine-ark")
        response = client.put(
            "/api/model-configs/capability-defaults/image_generation",
            headers=headers,
            json={"model_config_id": text_config["id"]},
        )
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "MODEL_CAPABILITY_INCOMPATIBLE"
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_bound_model_config_cannot_be_deleted(tmp_path):
    db_dependency = _override_database(tmp_path)
    admin_token = _register_and_get_admin_access_token("bound-config-admin")
    headers = {"Authorization": f"Bearer {admin_token}"}
    try:
        config = _create_test_model_config(admin_token, provider="runninghub-ai-app")
        assigned = client.put(
            "/api/model-configs/capability-defaults/image_generation",
            headers=headers,
            json={"model_config_id": config["id"]},
        )
        assert assigned.status_code == 200
        response = client.delete(f"/api/model-configs/{config['id']}", headers=headers)
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "MODEL_CONFIG_IN_USE"
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_normal_user_cannot_manage_capability_defaults(tmp_path):
    db_dependency = _override_database(tmp_path)
    user_token = _register_and_get_access_token("capability-default-user")
    headers = {"Authorization": f"Bearer {user_token}"}
    try:
        assert client.get("/api/model-configs/capability-defaults", headers=headers).status_code == 403
        response = client.put(
            "/api/model-configs/capability-defaults/vision",
            headers=headers,
            json={"model_config_id": 1},
        )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.pop(db_dependency, None)
```

- [ ] **Step 2: Run API tests and confirm RED**

Run: `py -X utf8 -m pytest tests/backend/test_api.py -q -k "capability_default or capability_assignment or bound_model_config"`

Expected: FAIL with 404 for the new routes.

- [ ] **Step 3: Implement serializers and endpoints**

Add:

```python
class CapabilityDefaultUpdateRequest(BaseModel):
    model_config_id: int = Field(gt=0)


def _serialize_config(db: Session, config: ModelConfig) -> dict:
    return {
        "id": config.id,
        "name": config.name,
        "model_type": config.model_type,
        "provider": config.provider,
        "model_name": config.model_name,
        "base_url": config.base_url,
        "has_api_key": bool(config.encrypted_api_key),
        "supported_capabilities": supported_capabilities(config),
        "assigned_capabilities": assigned_capabilities(db, config.id),
    }


def _serialize_capability_default(db: Session, capability: str) -> dict:
    binding = db.scalar(select(ModelCapabilityDefault).where(ModelCapabilityDefault.capability == capability))
    config = db.get(ModelConfig, binding.model_config_id) if binding else None
    if binding is None:
        binding_status = "not_configured"
    elif config is None or capability not in supported_capabilities(config):
        binding_status = "invalid"
    else:
        binding_status = "configured"
    return {
        "capability": capability,
        "model_config": _serialize_config(db, config) if config else None,
        "status": binding_status,
    }
```

Implement `GET /capability-defaults` before the `/{config_id}` routes so FastAPI does not parse `capability-defaults` as an integer ID. Implement `PUT /capability-defaults/{capability}` as an atomic upsert owned by `require_admin_user`.

Change `_serialize_config` to accept `db: Session`, update all endpoint call sites, and include:

```python
"supported_capabilities": supported_capabilities(config),
"assigned_capabilities": assigned_capabilities(db, config.id),
```

Guard deletion by querying `ModelCapabilityDefault` and returning HTTP 409 with the assigned capability list.

- [ ] **Step 4: Run the focused API tests and confirm GREEN**

Run: `py -X utf8 -m pytest tests/backend/test_api.py -q -k "capability_default or capability_assignment or bound_model_config"`

Expected: all selected tests PASS.

### Task 4: Route Every AI Consumer by Explicit Capability

**Files:**
- Modify: `tests/backend/test_api.py`
- Modify: `backend/app/api/ai.py`
- Modify: `backend/app/services/scheduler_service.py`
- Modify: `backend/app/services/note_analysis_service.py`
- Modify: `backend/app/services/feishu_bitable_service.py`
- Modify: `backend/app/services/wechat_official_content_service.py`
- Modify: `backend/app/api/auto_tasks.py`

- [ ] **Step 1: Strengthen the image-generation routing regression test**

Update the existing image routing test to create three admin configs in this order: stale OpenAI-compatible generation, default Doubao vision, RunningHub generation. Bind vision to Doubao and image generation to RunningHub, then assert the generated task and fake client only use RunningHub:

```python
monkeypatch.setattr(ai_api, "RunningHubImageClient", lambda: fake_client)
client.put(
    "/api/model-configs/capability-defaults/vision",
    headers={"Authorization": f"Bearer {admin_token}"},
    json={"model_config_id": vision_config_id},
)
client.put(
    "/api/model-configs/capability-defaults/image_generation",
    headers={"Authorization": f"Bearer {admin_token}"},
    json={"model_config_id": runninghub_config_id},
)
assert fake_client.calls == [
    ("runninghub-ai-app", "runninghub-image-g", "runninghub-key", "生成一张配图", None, owner_user_id, "1:1")
]
assert tasks[0]["payload"]["model_config_id"] == runninghub_config_id
```

Add a test asserting an unbound image-generation request returns 503 before any `UsageLedger` row or concurrency lease is created.

Add a Provider-authentication failure test that mocks a 401 and asserts the stored/public task payload contains `error_code == "MODEL_PROVIDER_UNAUTHORIZED"` and a safe Chinese action message, but does not contain the upstream host or API Key.

- [ ] **Step 2: Run routing tests and confirm RED**

Run: `py -X utf8 -m pytest tests/backend/test_api.py -q -k "image_generation_prefers or unbound_image_generation"`

Expected: the old implementation selects the stale lower-ID config or creates quota state.

- [ ] **Step 3: Replace AI API context helpers**

Use:

```python
def _text_model_context(db: Session, current_user: User) -> tuple[ModelConfig, str]:
    return require_model_capability_context(db, "text")


def _image_model_context(db: Session, current_user: User, *, capability: str) -> tuple[ModelConfig, str]:
    return require_model_capability_context(db, capability)
```

Remove `_get_default_text_model`, `_get_default_image_model`, and the legacy resolver imports when no longer used. Keep capability selection before `_acquire_image_generation_guard` and `_reserve_usage`.

Normalize known Provider failures before persisting task errors:

```python
def _public_image_generation_error(exc: Exception) -> tuple[str, str]:
    cause = exc.__cause__
    response = getattr(cause, "response", None)
    if getattr(response, "status_code", None) == 401:
        return "MODEL_PROVIDER_UNAUTHORIZED", "图片生成模型鉴权失败，请管理员检查模型配置"
    return "MODEL_PROVIDER_FAILED", "图片生成模型调用失败，请稍后重试或联系管理员"
```

Use the safe message in task payloads and user responses. Keep `model_config_id` and `provider` as structured diagnostics; log the redacted exception server-side without persisting the upstream URL in normal-user task data.

- [ ] **Step 4: Update background/service consumers**

Replace every `get_default_model_config(... capability="text")` call with `get_model_config_for_capability(db, "text")`, and replace the note-analysis vision call with `get_model_config_for_capability(db, "vision")`. Preserve each caller's existing behavior when the resolver returns `None`; do not add fallback selection.

Run: `rg -n "get_default_model_config|require_default_model_context" backend/app`

Expected: no runtime call sites remain outside an intentional compatibility wrapper in `model_config_service.py`.

- [ ] **Step 5: Run routing and adjacent service tests**

Run:

```powershell
py -X utf8 -m pytest tests/backend/test_api.py -q -k "image_generation_prefers or unbound_image_generation or system_note_analysis or model_config"
py -X utf8 -m pytest tests/backend/test_feishu_integration.py -q
```

Expected: selected tests PASS and no implicit-fallback assertions remain.

### Task 5: Make Model Tests Capability-Specific

**Files:**
- Modify: `tests/backend/test_api.py`
- Modify: `backend/app/api/model_configs.py`
- Modify: `backend/app/services/ai_service.py` only if a small reusable request builder is necessary.

- [ ] **Step 1: Write failing capability-test tests**

Add mocked-request tests:

```python
def test_openai_image_generation_model_test_calls_images_generation_endpoint(tmp_path, monkeypatch):
    import backend.app.api.model_configs as model_configs_api

    captured = {}

    class FakeResponse:
        status_code = 200
        content = b'{"data":[{"url":"https://cdn.example.test/test.png"}]}'
        encoding = "utf-8"
        apparent_encoding = "utf-8"
        text = content.decode()

        def json(self):
            return {"data": [{"url": "https://cdn.example.test/test.png"}]}

    def fake_post(url, **kwargs):
        captured.update(url=url, json=kwargs["json"])
        return FakeResponse()

    db_dependency = _override_database(tmp_path)
    admin_token = _register_and_get_admin_access_token("generation-test-admin")
    headers = {"Authorization": f"Bearer {admin_token}"}
    try:
        config = _create_test_model_config(
            admin_token,
            model_name="image-generation-model",
            base_url="https://api.example.test/v1",
        )
        monkeypatch.setattr(model_configs_api.http_requests, "post", fake_post)
        response = client.post(
            f"/api/model-configs/{config['id']}/test?capability=image_generation",
            headers=headers,
        )
        assert response.status_code == 200
        assert captured["url"] == "https://api.example.test/v1/images/generations"
        assert captured["json"]["model"] == "image-generation-model"
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_model_test_rejects_capability_not_supported_by_config(tmp_path):
    db_dependency = _override_database(tmp_path)
    admin_token = _register_and_get_admin_access_token("incompatible-test-admin")
    headers = {"Authorization": f"Bearer {admin_token}"}
    try:
        text_config = _create_test_model_config(admin_token, model_type="text", provider="volcengine-ark")
        response = client.post(
            f"/api/model-configs/{text_config['id']}/test?capability=vision",
            headers=headers,
        )
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "MODEL_CAPABILITY_INCOMPATIBLE"
    finally:
        app.dependency_overrides.pop(db_dependency, None)
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `py -X utf8 -m pytest tests/backend/test_api.py -q -k "generation_model_test or test_rejects_capability"`

Expected: current image-model test calls `/chat/completions` regardless of requested generation capability.

- [ ] **Step 3: Implement capability-specific test dispatch**

Add a required `capability` query parameter validated against `MODEL_CAPABILITIES`. Dispatch:

- `text`: existing text `/chat/completions` probe.
- `vision`: existing one-pixel image `/chat/completions` probe.
- `image_generation` + OpenAI-compatible: POST the configured `/images/generations` endpoint with the configured model and a small explicit test prompt, discard the returned image reference.
- `image_generation` + RunningHub: retain the non-generating authenticated API demo check.

Record `capability` in `ApiLog.meta`. Continue redacting the key and response body. Update user-facing text to state that OpenAI-compatible image-generation tests may consume upstream quota.

- [ ] **Step 4: Run model-test and quota tests**

Run:

```powershell
py -X utf8 -m pytest tests/backend/test_api.py -q -k "model_config and test"
py -X utf8 -m pytest tests/backend/test_usage_quota.py -q -k "model_test"
```

Expected: all selected tests PASS.

### Task 6: Add Frontend Capability Contracts

**Files:**
- Create: `tests/frontend/test_model_capability_routing_contract.py`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Write the failing source contract test**

```python
from pathlib import Path


def test_model_config_frontend_exposes_explicit_capability_routing_contract():
    types_source = Path("frontend/src/types/index.ts").read_text(encoding="utf-8")
    api_source = Path("frontend/src/lib/api.ts").read_text(encoding="utf-8")

    assert 'export type ModelCapability = "text" | "vision" | "image_generation"' in types_source
    assert "supported_capabilities: ModelCapability[]" in types_source
    assert "assigned_capabilities: ModelCapability[]" in types_source
    assert "fetchModelCapabilityDefaults" in api_source
    assert "setModelCapabilityDefault" in api_source
    assert "capability" in api_source
```

- [ ] **Step 2: Run the contract test and confirm RED**

Run: `py -X utf8 -m pytest tests/frontend/test_model_capability_routing_contract.py -q`

Expected: FAIL because the types and API functions do not exist.

- [ ] **Step 3: Add TypeScript contracts and API functions**

Add:

```typescript
export type ModelCapability = "text" | "vision" | "image_generation";

export type ModelCapabilityDefault = {
  capability: ModelCapability;
  model_config: ModelConfig | null;
  status: "configured" | "not_configured" | "invalid";
};
```

Extend `ModelConfig` with `supported_capabilities` and `assigned_capabilities`. Add:

```typescript
export async function fetchModelCapabilityDefaults(): Promise<{ items: ModelCapabilityDefault[] }> {
  const response = await http.get<{ items: ModelCapabilityDefault[] }>("/model-configs/capability-defaults");
  return response.data;
}

export async function setModelCapabilityDefault(capability: ModelCapability, modelConfigId: number): Promise<ModelCapabilityDefault> {
  const response = await http.put<ModelCapabilityDefault>(`/model-configs/capability-defaults/${capability}`, {
    model_config_id: modelConfigId,
  });
  return response.data;
}
```

Change `testModelConfig` to require a `ModelCapability` argument and pass it as a query parameter.

- [ ] **Step 4: Run the contract test and TypeScript build**

Run:

```powershell
py -X utf8 -m pytest tests/frontend/test_model_capability_routing_contract.py -q
npm --prefix frontend run build
```

Expected: contract PASS and build succeeds.

### Task 7: Build the Administrator Routing Panel

**Files:**
- Modify: `tests/frontend/test_model_capability_routing_contract.py`
- Modify: `frontend/src/pages/models/model-config-page.tsx`

- [ ] **Step 1: Add failing management-page assertions**

Extend the contract test:

```python
page_source = Path("frontend/src/pages/models/model-config-page.tsx").read_text(encoding="utf-8")
assert "能力路由" in page_source
assert "文本生成" in page_source
assert "图片理解" in page_source
assert "图片生成" in page_source
assert "fetchModelCapabilityDefaults" in page_source
assert "setModelCapabilityDefault" in page_source
assert "setDefaultModelConfig" not in page_source
assert "设为该类型默认模型" not in page_source
```

- [ ] **Step 2: Run the page contract and confirm RED**

Run: `py -X utf8 -m pytest tests/frontend/test_model_capability_routing_contract.py -q`

Expected: FAIL because the routing panel is absent and legacy default controls remain.

- [ ] **Step 3: Implement the focused routing UI**

At the top of `ModelConfigPage`, load configs and capability defaults together. Render an Ant Design `Card` titled “能力路由” with three responsive columns. Each column contains:

- capability label and short purpose;
- current model name and Provider or “尚未配置”;
- a `Select<number>` filtered by `supported_capabilities.includes(capability)`;
- status tag;
- a primary “保存路由” action with per-capability loading state.

Use a single constant:

```typescript
const capabilityMeta: Record<ModelCapability, { label: string; description: string }> = {
  text: { label: "文本生成", description: "改写、草稿与分析文本" },
  vision: { label: "图片理解", description: "图片描述与内容理解" },
  image_generation: { label: "图片生成", description: "文生图与参考图生图" },
};
```

Remove the `is_default` checkbox, `handleSetDefault`, `setDefaultModelConfig` import, and star/default button. Display assigned capability tags on each config card. Preserve existing add/edit/test/delete behavior and Ant Design styling.

- [ ] **Step 4: Validate error and responsive states**

Ensure route loading failure appears in the existing error alert, unconfigured capabilities remain selectable, bound-config deletion shows the API's 409 message, and the three route columns use `xs={24} md={8}` without horizontal overflow.

- [ ] **Step 5: Run frontend verification**

Run:

```powershell
py -X utf8 -m pytest tests/frontend/test_model_capability_routing_contract.py -q
npm --prefix frontend run build
```

Expected: contract PASS and production build succeeds with no TypeScript errors.

### Task 8: Verify Migration, Regression Scope, and Current Data Readiness

**Files:**
- Modify only files already named if verification exposes a scoped defect.

- [ ] **Step 1: Run migration against a temporary database**

Run:

```powershell
$tempDb = (Resolve-Path '.').Path + '\.tmp-model-capability-routing.db'
$env:DATABASE_URL = 'sqlite:///' + ($tempDb -replace '\\','/')
py -X utf8 -m alembic -c backend/alembic.ini upgrade head
py -X utf8 -m alembic -c backend/alembic.ini current
Remove-Item -LiteralPath $tempDb -Force
Remove-Item Env:DATABASE_URL
```

Expected: upgrade succeeds and current revision is `20260710_model_capability_defaults`.

- [ ] **Step 2: Run focused backend suites**

Run:

```powershell
py -X utf8 -m pytest tests/backend/test_model_config_service.py -q
py -X utf8 -m pytest tests/backend/test_api.py -q -k "model_config or image_generation or image_describe or system_note_analysis"
py -X utf8 -m pytest tests/backend/test_usage_quota.py tests/backend/test_beta_concurrency_limits.py -q
```

Expected: all selected tests PASS.

- [ ] **Step 3: Run frontend and static checks**

Run:

```powershell
py -X utf8 -m pytest tests/frontend/test_model_capability_routing_contract.py -q
npm --prefix frontend run build
git diff --check
```

Expected: tests and build PASS; `git diff --check` emits no errors.

- [ ] **Step 4: Inspect current live database read-only**

Query `data/spider_xhs.db` without writing and report:

- the current admin configs compatible with each capability;
- that image generation has multiple candidates and therefore migration will not guess;
- that RunningHub config `#5` is the intended manual binding based on prior successful tasks.

Do not apply the migration to the live database or write the binding until the user authorizes root service migration/restart.

- [ ] **Step 5: Report exact delivery state**

Report separately:

- root `master` code verified;
- design and plan files uncommitted;
- live database not migrated;
- capability default not yet applied to live data;
- root services not restarted;
- no real Provider request made.

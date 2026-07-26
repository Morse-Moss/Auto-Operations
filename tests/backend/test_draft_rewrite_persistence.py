from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.api.ai import get_text_ai_client
from backend.app.core.database import Base, get_db
from backend.app.core.security import create_access_token, encrypt_text, hash_password
from backend.app.main import app
from backend.app.models import AiDraft, ModelCapabilityDefault, ModelConfig, User


client = TestClient(app)


class FakeRewriteClient:
    def rewrite_note(self, *, model_config, api_key, title, body, instruction):
        return f"{title}\n\n候选正文：{instruction}"


def _setup_database(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'draft-rewrite-persistence.db'}",
        connect_args={"check_same_thread": False},
    )
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return testing_session


def _seed_rewrite_context(testing_session):
    db = testing_session()
    try:
        owner = User(username="rewrite-owner", password_hash=hash_password("secret123"))
        intruder = User(username="rewrite-intruder", password_hash=hash_password("secret123"))
        admin = User(
            username="rewrite-admin",
            password_hash=hash_password("secret123"),
            role="admin",
            status="active",
        )
        db.add_all([owner, intruder, admin])
        db.flush()

        model = ModelConfig(
            user_id=admin.id,
            name="Rewrite test model",
            model_type="text",
            provider="openai-compatible",
            model_name="rewrite-test-model",
            base_url="https://api.example.test/v1",
            encrypted_api_key=encrypt_text("sk-test-only"),
            is_default=True,
        )
        db.add(model)
        db.flush()
        db.add(
            ModelCapabilityDefault(
                capability="text",
                model_config_id=model.id,
                updated_by_user_id=admin.id,
            )
        )
        draft = AiDraft(
            user_id=owner.id,
            platform="xhs",
            draft_name="持久化测试",
            title="当前草稿标题",
            body="当前草稿正文",
            tags=[{"name": "当前标签"}],
        )
        db.add(draft)
        db.commit()
        db.refresh(draft)
        return {
            "draft_id": draft.id,
            "owner_headers": {"Authorization": f"Bearer {create_access_token(owner.id)}"},
            "intruder_headers": {"Authorization": f"Bearer {create_access_token(intruder.id)}"},
        }
    finally:
        db.close()


def _rewrite(draft_id: int, headers: dict[str, str], mode: str, instruction: str):
    response = client.post(
        "/api/ai/rewrite-note",
        headers={**headers, "Idempotency-Key": f"rewrite-{mode}-{instruction.encode('utf-8').hex()}"},
        json={"draft_id": draft_id, "mode": mode, "instruction": instruction},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_rewrite_candidates_restore_latest_per_mode_without_overwriting_current_draft(tmp_path):
    testing_session = _setup_database(tmp_path)
    context = _seed_rewrite_context(testing_session)
    app.dependency_overrides[get_text_ai_client] = lambda: FakeRewriteClient()
    try:
        first_safe = _rewrite(context["draft_id"], context["owner_headers"], "safe", "安全版一")
        polish = _rewrite(context["draft_id"], context["owner_headers"], "polish", "润色版")
        latest_safe = _rewrite(context["draft_id"], context["owner_headers"], "safe", "安全版二")

        candidates_response = client.get(
            f"/api/drafts/{context['draft_id']}/rewrite-candidates",
            headers=context["owner_headers"],
        )
        assert candidates_response.status_code == 200
        candidates = candidates_response.json()["candidates"]
        assert set(candidates) == {"safe", "polish"}
        assert candidates["safe"]["body"] == latest_safe["body"]
        assert candidates["safe"]["body"] != first_safe["body"]
        assert candidates["polish"]["body"] == polish["body"]
        assert isinstance(candidates["safe"]["generated_at"], str)

        drafts_response = client.get(
            "/api/drafts",
            params={"platform": "xhs"},
            headers=context["owner_headers"],
        )
        assert drafts_response.status_code == 200
        persisted_draft = drafts_response.json()["items"][0]
        assert persisted_draft["title"] == "当前草稿标题"
        assert persisted_draft["body"] == "当前草稿正文"

        adopt_response = client.patch(
            f"/api/drafts/{context['draft_id']}",
            headers=context["owner_headers"],
            json={
                "title": candidates["safe"]["title"],
                "body": candidates["safe"]["body"],
                "tags": candidates["safe"]["tags"],
            },
        )
        assert adopt_response.status_code == 200
        assert adopt_response.json()["body"] == candidates["safe"]["body"]
    finally:
        app.dependency_overrides.pop(get_text_ai_client, None)
        app.dependency_overrides.pop(get_db, None)


def test_discard_rewrite_candidate_persists_and_is_owner_scoped(tmp_path):
    testing_session = _setup_database(tmp_path)
    context = _seed_rewrite_context(testing_session)
    app.dependency_overrides[get_text_ai_client] = lambda: FakeRewriteClient()
    try:
        _rewrite(context["draft_id"], context["owner_headers"], "safe", "安全版")
        _rewrite(context["draft_id"], context["owner_headers"], "polish", "润色版")

        intruder_get = client.get(
            f"/api/drafts/{context['draft_id']}/rewrite-candidates",
            headers=context["intruder_headers"],
        )
        assert intruder_get.status_code == 404

        intruder_delete = client.delete(
            f"/api/drafts/{context['draft_id']}/rewrite-candidates/safe",
            headers=context["intruder_headers"],
        )
        assert intruder_delete.status_code == 404

        discard_response = client.delete(
            f"/api/drafts/{context['draft_id']}/rewrite-candidates/safe",
            headers=context["owner_headers"],
        )
        assert discard_response.status_code == 200
        assert set(discard_response.json()["candidates"]) == {"polish"}

        restored_response = client.get(
            f"/api/drafts/{context['draft_id']}/rewrite-candidates",
            headers=context["owner_headers"],
        )
        assert restored_response.status_code == 200
        assert set(restored_response.json()["candidates"]) == {"polish"}
    finally:
        app.dependency_overrides.pop(get_text_ai_client, None)
        app.dependency_overrides.pop(get_db, None)

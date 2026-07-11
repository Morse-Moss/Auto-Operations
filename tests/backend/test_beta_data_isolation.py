from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.database import Base, get_db
from backend.app.core.security import encrypt_text
from backend.app.main import app
from backend.app.models import (
    AiDraft,
    AiGeneratedAsset,
    DraftAsset,
    ModelConfig,
    Note,
    NoteAsset,
    PlatformAccount,
    PublishAsset,
    PublishJob,
    Task,
    User,
)
from backend.app.models.analysis_report import AnalysisReport
from test_support.beta_invites import create_test_invite_code

client = TestClient(app)


def _override_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'beta-data-isolation-test.db'}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return get_db


def _register(username: str) -> dict:
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": "secret123", "invite_code": create_test_invite_code()},
    )
    assert response.status_code == 200
    return response.json()


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _with_db(action):
    db = next(app.dependency_overrides[get_db]())
    try:
        return action(db)
    finally:
        db.close()


def _seed_owner_graph(owner_id: int) -> dict[str, int]:
    def seed(db: Session) -> dict[str, int]:
        account = PlatformAccount(
            user_id=owner_id,
            platform="xhs",
            sub_type="creator",
            external_user_id="owner-xhs",
            nickname="Owner Account",
            status="active",
        )
        note = Note(
            user_id=owner_id,
            platform_account_id=1,
            platform="xhs",
            note_id="owner-note",
            title="Owner note",
            content="Owner content",
            author_name="Owner",
        )
        draft = AiDraft(user_id=owner_id, platform="xhs", title="Owner draft", body="Owner body")
        generated_asset = AiGeneratedAsset(
            user_id=owner_id,
            prompt="owner image",
            model_name="gpt-image",
            file_path="u1/generated.png",
        )
        model_config = ModelConfig(
            user_id=owner_id,
            name="Owner Model",
            model_type="text",
            provider="openai-compatible",
            model_name="gpt-test",
            base_url="https://api.example.test/v1",
            encrypted_api_key=encrypt_text("sk-owner-secret"),
            is_default=True,
        )
        task = Task(
            user_id=owner_id,
            platform="xhs",
            task_type="owner_task",
            status="pending",
            progress=0,
            payload={"owner": True},
        )
        report = AnalysisReport(
            user_id=owner_id,
            platform="xhs",
            report_type="content_analysis",
            status="completed",
            title="Owner report",
            input_config={"keyword_group_id": 1, "excluded_note_ids": []},
            data_health={"status": "minimum", "can_generate": True},
            evidence_pool={"notes": [], "comments": [], "keywords": [], "metrics": [], "benchmarks": []},
            result_json={"topic_cards": [{"id": "card-1", "title": "Owner card"}]},
            html_file_path="exports/owner.html",
        )
        publish_job = PublishJob(
            user_id=owner_id,
            platform_account_id=None,
            platform="xhs",
            title="Owner publish",
            body="Owner publish body",
            publish_mode="immediate",
            status="pending",
        )
        db.add_all([account, note, draft, generated_asset, model_config, task, report, publish_job])
        db.flush()
        note_asset = NoteAsset(note_id=note.id, asset_type="image", url="https://example.test/owner-note.png")
        draft_asset = DraftAsset(draft_id=draft.id, asset_type="image", url="https://example.test/owner-draft.png", sort_order=1)
        publish_asset = PublishAsset(publish_job_id=publish_job.id, asset_type="image", file_path="u1/publish.png")
        db.add_all([note_asset, draft_asset, publish_asset])
        db.commit()
        return {
            "account_id": account.id,
            "note_id": note.id,
            "note_asset_id": note_asset.id,
            "draft_id": draft.id,
            "draft_asset_id": draft_asset.id,
            "generated_asset_id": generated_asset.id,
            "model_config_id": model_config.id,
            "task_id": task.id,
            "report_id": report.id,
            "publish_job_id": publish_job.id,
            "publish_asset_id": publish_asset.id,
        }

    return _with_db(seed)


def test_beta_api_lists_only_current_user_data(tmp_path):
    db_dependency = _override_database(tmp_path)
    try:
        owner = _register("isolation-list-owner")
        intruder = _register("isolation-list-intruder")
        ids = _seed_owner_graph(owner["user"]["id"])

        expectations = [
            ("/api/accounts", "items"),
            ("/api/notes", "items"),
            ("/api/drafts", "items"),
            ("/api/ai/images/assets", "items"),
            ("/api/publish/jobs", "items"),
            ("/api/tasks", "items"),
            ("/api/xhs/analytics/analysis/reports", None),
        ]
        for path, items_key in expectations:
            response = client.get(path, headers=_auth_headers(intruder["access_token"]))
            assert response.status_code == 200, path
            payload = response.json()
            items = payload if items_key is None else payload[items_key]
            assert items == [], path

        model_configs = client.get(
            "/api/model-configs",
            headers=_auth_headers(intruder["access_token"]),
        )
        assert model_configs.status_code == 403

        owner_response = client.get("/api/tasks", headers=_auth_headers(owner["access_token"]))
        assert owner_response.status_code == 200
        assert [item["id"] for item in owner_response.json()["items"]] == [ids["task_id"]]
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_beta_api_rejects_cross_user_account_operations(tmp_path):
    db_dependency = _override_database(tmp_path)
    try:
        owner = _register("isolation-account-owner")
        intruder = _register("isolation-account-intruder")
        ids = _seed_owner_graph(owner["user"]["id"])
        headers = _auth_headers(intruder["access_token"])

        responses = [
            client.post(f"/api/accounts/{ids['account_id']}/check", headers=headers),
            client.patch(f"/api/accounts/{ids['account_id']}", headers=headers, json={"nickname": "takeover"}),
            client.delete(f"/api/accounts/{ids['account_id']}", headers=headers),
        ]

        assert [response.status_code for response in responses] == [404, 404, 404]
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_beta_api_rejects_cross_user_content_and_asset_operations(tmp_path):
    db_dependency = _override_database(tmp_path)
    try:
        owner = _register("isolation-content-owner")
        intruder = _register("isolation-content-intruder")
        ids = _seed_owner_graph(owner["user"]["id"])
        headers = _auth_headers(intruder["access_token"])

        responses = [
            client.get(f"/api/notes/{ids['note_id']}", headers=headers),
            client.delete(f"/api/notes/{ids['note_id']}", headers=headers),
            client.get(f"/api/notes/{ids['note_id']}/assets", headers=headers),
            client.delete(f"/api/notes/{ids['note_id']}/assets/{ids['note_asset_id']}", headers=headers),
            client.patch(f"/api/drafts/{ids['draft_id']}", headers=headers, json={"title": "takeover"}),
            client.post(f"/api/drafts/{ids['draft_id']}/duplicate", headers=headers),
            client.post(f"/api/drafts/{ids['draft_id']}/send-to-publish", headers=headers, json={}),
            client.get(f"/api/drafts/{ids['draft_id']}/assets", headers=headers),
            client.patch(
                f"/api/drafts/{ids['draft_id']}/assets/{ids['draft_asset_id']}",
                headers=headers,
                json={"url": "https://example.test/takeover.png"},
            ),
            client.delete(f"/api/drafts/{ids['draft_id']}/assets/{ids['draft_asset_id']}", headers=headers),
            client.delete(f"/api/ai/images/assets/{ids['generated_asset_id']}", headers=headers),
        ]

        assert [response.status_code for response in responses] == [404] * len(responses)
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def test_beta_api_rejects_cross_user_publish_task_model_and_report_operations(tmp_path):
    db_dependency = _override_database(tmp_path)
    try:
        owner = _register("isolation-control-owner")
        intruder = _register("isolation-control-intruder")
        ids = _seed_owner_graph(owner["user"]["id"])
        headers = _auth_headers(intruder["access_token"])

        responses = [
            client.get(f"/api/publish/jobs/{ids['publish_job_id']}", headers=headers),
            client.patch(f"/api/publish/jobs/{ids['publish_job_id']}", headers=headers, json={"title": "takeover"}),
            client.post(f"/api/publish/jobs/{ids['publish_job_id']}/retry", headers=headers),
            client.post(f"/api/publish/jobs/{ids['publish_job_id']}/cancel", headers=headers),
            client.delete(f"/api/publish/jobs/{ids['publish_job_id']}", headers=headers),
            client.get(f"/api/publish/jobs/{ids['publish_job_id']}/assets", headers=headers),
            client.delete(f"/api/publish/assets/{ids['publish_asset_id']}", headers=headers),
            client.get(f"/api/tasks/{ids['task_id']}", headers=headers),
            client.post(f"/api/tasks/{ids['task_id']}/cancel", headers=headers),
            client.post(f"/api/tasks/{ids['task_id']}/retry", headers=headers),
            client.post(f"/api/model-configs/{ids['model_config_id']}/test?capability=text", headers=headers),
            client.patch(f"/api/model-configs/{ids['model_config_id']}", headers=headers, json={"name": "takeover"}),
            client.delete(f"/api/model-configs/{ids['model_config_id']}", headers=headers),
            client.post(f"/api/model-configs/{ids['model_config_id']}/set-default", headers=headers),
            client.get(f"/api/xhs/analytics/analysis/reports/{ids['report_id']}", headers=headers),
            client.post(f"/api/xhs/analytics/analysis/reports/{ids['report_id']}/rerun", headers=headers),
            client.post(
                f"/api/xhs/analytics/analysis/reports/{ids['report_id']}/topic-cards/card-1/drafts",
                headers=headers,
                json={"topic_cards": [{"id": "card-1", "title": "takeover"}]},
            ),
        ]

        assert [response.status_code for response in responses] == [404] * 10 + [403] * 4 + [404] * 3
    finally:
        app.dependency_overrides.pop(db_dependency, None)

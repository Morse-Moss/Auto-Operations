from __future__ import annotations

import json

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import Base, get_db
from backend.app.core.security import create_access_token, hash_password, encrypt_text
from backend.app.main import app
from backend.app.models import ModelConfig, Note, NoteAnalysisResult, NoteAsset, User
from backend.app.services import feishu_bitable_service, note_analysis_service, scheduler_service
from test_support.model_capabilities import bind_test_model_capability

client = TestClient(app)

SYSTEM_DONE = "\u5df2\u5b8c\u6210"


def _override_database(tmp_path, name: str = "note-analysis-system-source.db"):
    engine = create_engine(f"sqlite:///{tmp_path / name}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestingSessionLocal


def _create_user(SessionLocal, username: str = "system-analysis-owner") -> int:
    db = SessionLocal()
    try:
        user = User(username=username, password_hash=hash_password("secret123"))
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id
    finally:
        db.close()


def _auth_headers(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


def _create_note(
    SessionLocal,
    *,
    user_id: int,
    note_id: str = "system-analysis-note",
    title: str = "Small kitchen storage checklist",
    content: str = "Five practical storage steps for small kitchens.",
    raw_json: dict | None = None,
) -> int:
    db = SessionLocal()
    try:
        note = Note(
            user_id=user_id,
            platform_account_id=1,
            platform="xhs",
            note_id=note_id,
            title=title,
            content=content,
            author_name="author",
            raw_json=raw_json or {},
        )
        db.add(note)
        db.commit()
        db.refresh(note)
        return note.id
    finally:
        db.close()


def _add_analysis(
    SessionLocal,
    *,
    user_id: int,
    note_id: int,
    source: str,
    analysis_status: str = SYSTEM_DONE,
    subject_object: str = "subject",
    content_type: str = "system-content",
    reusable_models: list[str] | None = None,
    reuse_value: str = "system-usage",
    search_attribute: str = "system-search",
    push_status: str = "not_synced",
    pull_status: str = "not_pulled",
    external_record_id: str | None = None,
    score: float | None = None,
    rating: str | None = None,
    raw_payload: dict | None = None,
    **extra,
) -> None:
    db = SessionLocal()
    try:
        db.add(
            NoteAnalysisResult(
                user_id=user_id,
                note_id=note_id,
                source=source,
                analysis_status=analysis_status,
                subject_object=subject_object,
                content_type=content_type,
                core_points=f"{source}-core",
                target_audience=f"{source}-audience",
                title_hook=f"{source}-hook",
                content_structure=f"{source}-structure",
                reusable_models=reusable_models or [f"{source}-model"],
                reuse_value=reuse_value,
                search_attribute=search_attribute,
                push_status=push_status,
                pull_status=pull_status,
                external_record_id=external_record_id,
                score=score,
                rating=rating,
                raw_payload=raw_payload,
                **extra,
            )
        )
        db.commit()
    finally:
        db.close()


def test_content_library_prefers_system_analysis_but_keeps_feishu_sync_status(tmp_path):
    SessionLocal = _override_database(tmp_path, "library-effective-analysis.db")
    try:
        user_id = _create_user(SessionLocal, "library-effective-owner")
        note_id = _create_note(SessionLocal, user_id=user_id)
        _add_analysis(
            SessionLocal,
            user_id=user_id,
            note_id=note_id,
            source="feishu",
            content_type="stale-feishu-content",
            push_status="synced",
            pull_status="success",
            external_record_id="rec_feishu",
        )
        _add_analysis(
            SessionLocal,
            user_id=user_id,
            note_id=note_id,
            source="system",
            content_type="fresh-system-content",
            reuse_value="fresh-system-usage",
            push_status="not_synced",
        )

        response = client.get("/api/notes", headers=_auth_headers(user_id), params={"platform": "xhs"})

        assert response.status_code == 200
        item = response.json()["items"][0]
        assert item["analysis_result"]["content_type"] == "fresh-system-content"
        assert item["analysis_result"]["reuse_value"] == "fresh-system-usage"
        assert item["feishu_sync"]["push_status"] == "synced"
        assert item["feishu_sync"]["pull_status"] == "success"
        assert item["feishu_sync"]["external_record_id"] == "rec_feishu"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_analysis_filters_use_system_row_when_present(tmp_path):
    SessionLocal = _override_database(tmp_path, "library-analysis-filter.db")
    try:
        user_id = _create_user(SessionLocal, "library-filter-owner")
        note_id = _create_note(SessionLocal, user_id=user_id)
        _add_analysis(
            SessionLocal,
            user_id=user_id,
            note_id=note_id,
            source="feishu",
            content_type="stale-feishu-content",
            push_status="synced",
        )
        _add_analysis(
            SessionLocal,
            user_id=user_id,
            note_id=note_id,
            source="system",
            content_type="fresh-system-content",
        )

        system_response = client.get(
            "/api/notes",
            headers=_auth_headers(user_id),
            params={"platform": "xhs", "content_type": "fresh-system-content"},
        )
        stale_response = client.get(
            "/api/notes",
            headers=_auth_headers(user_id),
            params={"platform": "xhs", "content_type": "stale-feishu-content"},
        )

        assert system_response.status_code == 200
        assert [item["note_id"] for item in system_response.json()["items"]] == ["system-analysis-note"]
        assert stale_response.status_code == 200
        assert stale_response.json()["items"] == []
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_filter_options_use_system_rows_with_feishu_fallback_for_legacy_rows(tmp_path):
    SessionLocal = _override_database(tmp_path, "library-filter-options.db")
    try:
        user_id = _create_user(SessionLocal, "library-options-owner")
        modern_note_id = _create_note(SessionLocal, user_id=user_id, note_id="modern-note")
        legacy_note_id = _create_note(SessionLocal, user_id=user_id, note_id="legacy-note")
        _add_analysis(SessionLocal, user_id=user_id, note_id=modern_note_id, source="feishu", content_type="stale-feishu-content")
        _add_analysis(SessionLocal, user_id=user_id, note_id=modern_note_id, source="system", content_type="fresh-system-content")
        _add_analysis(SessionLocal, user_id=user_id, note_id=legacy_note_id, source="feishu", content_type="legacy-feishu-content")

        response = client.get("/api/notes/filter-options", headers=_auth_headers(user_id), params={"platform": "xhs"})

        assert response.status_code == 200
        values = {option["value"] for option in response.json()["contentType"]}
        assert "fresh-system-content" in values
        assert "legacy-feishu-content" in values
        assert "stale-feishu-content" not in values
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_running_single_note_analysis_upserts_system_row_without_mutating_feishu(tmp_path):
    SessionLocal = _override_database(tmp_path, "single-note-system-analysis.db")
    try:
        user_id = _create_user(SessionLocal, "single-note-analysis-owner")
        note_id = _create_note(
            SessionLocal,
            user_id=user_id,
            raw_json={"liked_count": 1201, "collected_count": 801, "comment_count": 301, "share_count": 101},
        )
        _add_analysis(
            SessionLocal,
            user_id=user_id,
            note_id=note_id,
            source="feishu",
            analysis_status="feishu-status",
            content_type="feishu-content",
            push_status="synced",
            external_record_id="rec_keep",
        )

        response = client.post(f"/api/notes/{note_id}/analysis", headers=_auth_headers(user_id), json={})

        assert response.status_code == 200
        payload = response.json()
        assert payload["source"] == "system"
        assert payload["analysis_status"] == SYSTEM_DONE
        assert payload["score"] == 10.0
        assert payload["rating"]
        assert payload["analysis_note"] == ""

        db = SessionLocal()
        try:
            system_result = db.scalar(select(NoteAnalysisResult).where(NoteAnalysisResult.note_id == note_id, NoteAnalysisResult.source == "system"))
            feishu_result = db.scalar(select(NoteAnalysisResult).where(NoteAnalysisResult.note_id == note_id, NoteAnalysisResult.source == "feishu"))
            assert system_result is not None
            assert system_result.analysis_status == SYSTEM_DONE
            assert system_result.score == 10.0
            assert feishu_result.analysis_status == "feishu-status"
            assert feishu_result.content_type == "feishu-content"
            assert feishu_result.push_status == "synced"
            assert feishu_result.external_record_id == "rec_keep"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_system_note_analysis_uses_default_text_model_and_ignores_text_cover_type(tmp_path, monkeypatch):
    SessionLocal = _override_database(tmp_path, "single-note-system-analysis-text-model.db")
    try:
        user_id = _create_user(SessionLocal, "single-note-text-model-owner")
        note_id = _create_note(
            SessionLocal,
            user_id=user_id,
            title="AI workflow checklist",
            content="Use a repeatable workflow to reduce manual collaboration cost.",
            raw_json={"liked_count": 300, "collected_count": 150, "comment_count": 80, "share_count": 30},
        )
        db = SessionLocal()
        try:
            config = ModelConfig(
                user_id=user_id,
                name="Default Text",
                model_type="text",
                provider="openai-compatible",
                model_name="fake-text-model",
                base_url="https://example.test/v1",
                encrypted_api_key=encrypt_text("fake-key"),
                is_default=True,
            )
            bind_test_model_capability(db, config=config, capability="text")
            db.commit()
        finally:
            db.close()

        calls: list[dict] = []

        class FakeTextClient:
            def complete_json_prompt(self, **kwargs):
                calls.append({
                    "model_name": kwargs["model_config"].model_name,
                    "api_key": kwargs["api_key"],
                })
                return json.dumps({
                    "subject_object": "AI workflow",
                    "content_type": "教程",
                    "core_points": "用流程降低协作成本",
                    "target_audience": "想提升效率阶段",
                    "title_hook": "清单承诺",
                    "title_type": "清单承诺型",
                    "cover_type": "大字报",
                    "content_structure": "开场：提出协作问题\n展开：拆解流程\n推进：给出清单\n高潮：强调效率提升\n结尾：引导复用",
                    "reusable_models": ["教程方法模型"],
                    "reuse_values": ["正文结构参考"],
                    "search_attribute": "强搜索",
                    "analysis_note": "should be ignored",
                }, ensure_ascii=False)

        monkeypatch.setattr(note_analysis_service, "OpenAICompatibleTextClient", FakeTextClient)

        response = client.post(f"/api/notes/{note_id}/analysis", headers=_auth_headers(user_id), json={})

        assert response.status_code == 200
        payload = response.json()
        assert calls
        assert calls[0]["model_name"] == "fake-text-model"
        assert calls[0]["api_key"] == "fake-key"
        assert payload["content_type"] == "教程"
        assert payload["core_points"] == "用流程降低协作成本"
        assert payload["title_type"] == "清单承诺型"
        assert payload["cover_type"] is None
        assert payload["analysis_note"] == ""
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_text_model_helpers_use_admin_default_doubao_for_regular_user(tmp_path, monkeypatch):
    SessionLocal = _override_database(tmp_path, "admin-default-text-model-helpers.db")
    try:
        user_id = _create_user(SessionLocal, "admin-default-text-owner")
        admin_id = _create_user(SessionLocal, "admin-default-text-admin")
        note_id = _create_note(
            SessionLocal,
            user_id=user_id,
            title="Reusable breakfast workflow",
            content="A short note about low-cost breakfast prep.",
            raw_json={"liked_count": 10, "collected_count": 5},
        )
        db = SessionLocal()
        try:
            admin = db.get(User, admin_id)
            admin.role = "admin"
            config = ModelConfig(
                user_id=admin_id,
                name="Doubao Text",
                model_type="text",
                provider="volcengine-ark",
                model_name="doubao-seed-2-0-mini-260428",
                base_url="https://ark.cn-beijing.volces.com/api/v3",
                encrypted_api_key=encrypt_text("sk-doubao-text"),
                is_default=True,
            )
            bind_test_model_capability(db, config=config, capability="text")
            db.commit()

            config, api_key = scheduler_service._get_text_model_for_user(db, user_id)
            assert config.model_name == "doubao-seed-2-0-mini-260428"
            assert api_key == "sk-doubao-text"

            calls: list[dict] = []

            class FakeTextClient:
                def complete_json_prompt(self, **kwargs):
                    calls.append({"model_name": kwargs["model_config"].model_name, "api_key": kwargs["api_key"]})
                    return json.dumps(
                        {
                            "content_type": "经验分享",
                            "reusable_models": ["场景种草模型"],
                            "reuse_values": ["选题参考"],
                            "search_attribute": "强搜索",
                        },
                        ensure_ascii=False,
                    )

            monkeypatch.setattr(feishu_bitable_service, "OpenAICompatibleTextClient", FakeTextClient)
            note = db.get(Note, note_id)
            analysis, warning = feishu_bitable_service.preanalyze_note_for_feishu(db, user_id=user_id, note=note)

            assert warning == ""
            assert calls == [{"model_name": "doubao-seed-2-0-mini-260428", "api_key": "sk-doubao-text"}]
            assert analysis["content_type"] == "经验分享"
            assert analysis["search_attribute"] == "强搜索"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_system_note_analysis_uses_default_image_model_for_cover_type(tmp_path):
    SessionLocal = _override_database(tmp_path, "single-note-system-analysis-image-model.db")
    try:
        user_id = _create_user(SessionLocal, "single-note-image-model-owner")
        note_id = _create_note(
            SessionLocal,
            user_id=user_id,
            raw_json={"liked_count": 10, "collected_count": 5, "comment_count": 1, "share_count": 1},
        )
        db = SessionLocal()
        try:
            config = ModelConfig(
                user_id=user_id,
                name="Default Image",
                model_type="image",
                provider="openai-compatible",
                model_name="fake-vision-model",
                base_url="https://example.test/v1",
                encrypted_api_key=encrypt_text("fake-image-key"),
                is_default=True,
            )
            bind_test_model_capability(db, config=config, capability="vision")
            db.add(NoteAsset(note_id=note_id, asset_type="image", url="https://images.example/cover.jpg", local_path="", sort_order=0))
            db.commit()

            calls: list[dict] = []

            class FakeImageClient:
                def describe_image(self, **kwargs):
                    calls.append({
                        "model_name": kwargs["model_config"].model_name,
                        "api_key": kwargs["api_key"],
                        "image_url": kwargs["image_url"],
                    })
                    return "截图式"

            note = db.get(Note, note_id)
            result = note_analysis_service.analyze_note_system(db, user_id=user_id, note=note, text_client=object(), image_client=FakeImageClient())

            assert calls == [{
                "model_name": "fake-vision-model",
                "api_key": "fake-image-key",
                "image_url": "https://images.example/cover.jpg",
            }]
            assert result.cover_type == "截图式"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_system_note_analysis_keeps_text_result_when_image_model_fails(tmp_path):
    SessionLocal = _override_database(tmp_path, "single-note-system-analysis-image-failure.db")
    try:
        user_id = _create_user(SessionLocal, "single-note-image-failure-owner")
        note_id = _create_note(
            SessionLocal,
            user_id=user_id,
            title="AI workflow checklist",
            content="Use a repeatable workflow to reduce manual collaboration cost.",
            raw_json={"cover_url": "https://images.example/cover.jpg", "liked_count": 300},
        )
        db = SessionLocal()
        try:
            text_config = ModelConfig(
                user_id=user_id,
                name="Default Text",
                model_type="text",
                provider="openai-compatible",
                model_name="fake-text-model",
                base_url="https://example.test/v1",
                encrypted_api_key=encrypt_text("fake-key"),
                is_default=True,
            )
            image_config = ModelConfig(
                user_id=user_id,
                name="Default Image",
                model_type="image",
                provider="openai-compatible",
                model_name="fake-vision-model",
                base_url="https://example.test/v1",
                encrypted_api_key=encrypt_text("fake-image-key"),
                is_default=True,
            )
            bind_test_model_capability(db, config=text_config, capability="text")
            bind_test_model_capability(db, config=image_config, capability="vision")
            db.commit()

            class FakeTextClient:
                def complete_json_prompt(self, **kwargs):
                    return json.dumps({"core_points": "用流程降低协作成本", "content_type": "教程"}, ensure_ascii=False)

            class FailingImageClient:
                def describe_image(self, **kwargs):
                    raise RuntimeError("vision unavailable")

            note = db.get(Note, note_id)
            result = note_analysis_service.analyze_note_system(
                db,
                user_id=user_id,
                note=note,
                text_client=FakeTextClient(),
                image_client=FailingImageClient(),
            )

            assert result.analysis_status == SYSTEM_DONE
            assert result.core_points == "用流程降低协作成本"
            assert result.content_type == "教程"
            assert result.cover_type is None
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_serializer_prefers_cover_and_title_type_columns_with_raw_payload_fallback():
    from backend.app.api.notes import _serialize_analysis_result

    column_result = NoteAnalysisResult(
        user_id=1,
        note_id=1,
        source="system",
        cover_type="column-cover",
        title_type="column-title",
        raw_payload={"cover_type": "payload-cover", "title_type": "payload-title"},
    )
    fallback_result = NoteAnalysisResult(
        user_id=1,
        note_id=2,
        source="feishu",
        raw_payload={"cover_type": "payload-cover", "title_type": "payload-title"},
    )

    assert _serialize_analysis_result(column_result)["cover_type"] == "column-cover"
    assert _serialize_analysis_result(column_result)["title_type"] == "column-title"
    assert _serialize_analysis_result(fallback_result)["cover_type"] == "payload-cover"
    assert _serialize_analysis_result(fallback_result)["title_type"] == "payload-title"


def test_feishu_push_and_pull_keep_using_feishu_row_when_system_row_exists(tmp_path):
    SessionLocal = _override_database(tmp_path, "feishu-row-isolation.db")
    try:
        user_id = _create_user(SessionLocal, "feishu-row-owner")
        note_id = _create_note(SessionLocal, user_id=user_id)
        _add_analysis(
            SessionLocal,
            user_id=user_id,
            note_id=note_id,
            source="system",
            analysis_status=SYSTEM_DONE,
            content_type="system-content",
            push_status="not_synced",
        )

        db = SessionLocal()
        try:
            push_result = feishu_bitable_service.push_notes_to_feishu_dry_run(db, user_id=user_id, note_ids=[note_id])
            assert push_result["updated_count"] == 1
            system_result = db.scalar(select(NoteAnalysisResult).where(NoteAnalysisResult.note_id == note_id, NoteAnalysisResult.source == "system"))
            feishu_result = db.scalar(select(NoteAnalysisResult).where(NoteAnalysisResult.note_id == note_id, NoteAnalysisResult.source == "feishu"))
            assert system_result.push_status == "not_synced"
            assert system_result.content_type == "system-content"
            assert feishu_result is not None
            assert feishu_result.push_status == "dry_run"

            pull_result = feishu_bitable_service.pull_feishu_analysis_records(
                db,
                user_id=user_id,
                records=[{"record_id": "rec_pull", "fields": {"\u7cfb\u7edf\u7b14\u8bb0ID": str(note_id), "content_type": "ignored"}}],
                note_ids=[note_id],
            )
            assert pull_result["updated_count"] == 1
            db.refresh(system_result)
            db.refresh(feishu_result)
            assert system_result.content_type == "system-content"
            assert feishu_result.external_record_id == "rec_pull"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)

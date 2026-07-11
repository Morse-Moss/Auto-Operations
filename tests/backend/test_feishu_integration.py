from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import Base, get_db
from backend.app.core.security import create_access_token, encrypt_text, hash_password
from backend.app.main import app
from backend.app.models import FeishuIntegrationConfig, ModelCapabilityDefault, Note, NoteAnalysisResult, NoteAsset, User
from backend.app.services import feishu_bitable_service

client = TestClient(app)


def _override_database(tmp_path, name="feishu-integration.db"):
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


def _create_user(SessionLocal, username="feishu-owner"):
    db = SessionLocal()
    try:
        user = User(
            username=username,
            password_hash=hash_password("secret123"),
            role="admin",
            status="active",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id
    finally:
        db.close()


def _auth_headers(user_id: int):
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


def test_feishu_models_are_registered_in_metadata():
    assert FeishuIntegrationConfig.__tablename__ == "feishu_integration_configs"
    assert NoteAnalysisResult.__tablename__ == "note_analysis_results"
    assert "feishu_integration_configs" in Base.metadata.tables
    assert "note_analysis_results" in Base.metadata.tables


def test_feishu_config_api_encrypts_secret_and_redacts_response(tmp_path):
    SessionLocal = _override_database(tmp_path, "feishu-config.db")
    try:
        user_id = _create_user(SessionLocal)
        headers = _auth_headers(user_id)
        payload = {
            "app_id": "cli_xxx",
            "app_secret": "secret-value",
            "bitable_url": "https://example.feishu.cn/base/app_token?table=tbl_xxx&view=vew_xxx",
            "table_id": "tbl_xxx",
            "enabled": True,
            "collaborator_member_type": "openchat",
            "collaborator_member_id": "oc_xxx",
            "collaborator_perm": "edit",
        }

        response = client.put("/api/integrations/feishu/config", headers=headers, json=payload)

        assert response.status_code == 200
        body = response.json()
        assert body["app_id"] == "cli_xxx"
        assert body["has_app_secret"] is True
        assert "app_secret" not in body
        assert body["table_id"] == "tbl_xxx"
        assert body["collaborator_member_type"] == "openchat"
        assert body["collaborator_member_id"] == "oc_xxx"
        assert body["collaborator_perm"] == "edit"
        assert body["enabled"] is True

        db = SessionLocal()
        try:
            config = db.scalar(select(FeishuIntegrationConfig))
            assert config is not None
            assert config.encrypted_app_secret
            assert config.encrypted_app_secret != "secret-value"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_feishu_test_endpoint_uses_real_client_boundary_without_leaking_secret(tmp_path, monkeypatch):
    SessionLocal = _override_database(tmp_path, "feishu-test.db")
    fake = FakeFeishuClient()

    def fake_create_client(config):
        assert config.app_id == "cli_xxx"
        assert config.encrypted_app_secret != "secret"
        return fake

    monkeypatch.setattr("backend.app.api.feishu_integration.create_feishu_client_from_config", fake_create_client)
    try:
        user_id = _create_user(SessionLocal)
        headers = _auth_headers(user_id)
        client.put(
            "/api/integrations/feishu/config",
            headers=headers,
            json={"app_id": "cli_xxx", "app_secret": "secret", "bitable_url": "https://example.feishu.cn/base/app?table=tbl", "enabled": True},
        )

        response = client.post("/api/integrations/feishu/test", headers=headers)

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert "secret" not in body["message"]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_feishu_ensure_fields_dry_run_returns_expected_template(tmp_path):
    SessionLocal = _override_database(tmp_path, "feishu-fields.db")
    try:
        user_id = _create_user(SessionLocal)
        headers = _auth_headers(user_id)
        client.put(
            "/api/integrations/feishu/config",
            headers=headers,
            json={"app_id": "cli_xxx", "app_secret": "secret", "bitable_url": "https://example.feishu.cn/base/app?table=tbl", "enabled": True},
        )

        response = client.post("/api/integrations/feishu/ensure-fields", headers=headers, json={"dry_run": True})

        assert response.status_code == 200
        body = response.json()
        assert body["dry_run"] is True
        field_names = [item["field_name"] for item in body["fields"]]
        assert "系统笔记ID" in field_names
        assert "笔记标题" in field_names
        assert "分析状态" in field_names
        assert "可复用模型" in field_names
        assert "评分" in field_names
        assert "评级" in field_names
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_feishu_ensure_fields_endpoint_marks_config_failed_when_service_fails(tmp_path, monkeypatch):
    SessionLocal = _override_database(tmp_path, "feishu-fields-failed.db")
    fake = FakeFeishuClient()
    fake.fields = [
        {
            "field_id": "fld_analysis_status_alias",
            "field_name": "分析状态确认",
            "type": 3,
            "property": {"options": [{"name": "待分析"}, {"name": "分析中"}, {"name": "已完成"}]},
        }
    ]

    def fake_create_client(config):
        return fake

    monkeypatch.setattr("backend.app.api.feishu_integration.create_feishu_client_from_config", fake_create_client)
    try:
        user_id = _create_user(SessionLocal)
        headers = _auth_headers(user_id)
        client.put(
            "/api/integrations/feishu/config",
            headers=headers,
            json={"app_id": "cli_xxx", "app_secret": "secret", "bitable_url": "https://example.feishu.cn/base/app?table=tbl", "enabled": True},
        )

        response = client.post("/api/integrations/feishu/ensure-fields", headers=headers, json={"dry_run": False})

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "failed"
        assert "字段补齐完成" not in body["message"]
        assert "分析状态确认" in body["message"]
        assert "已废弃" in body["message"]
        db = SessionLocal()
        try:
            config = db.scalar(select(FeishuIntegrationConfig))
            assert config.last_test_status == "failed"
            assert "分析状态确认" in config.last_test_message
            assert "已废弃" in config.last_test_message
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_push_notes_to_feishu_dry_run_creates_analysis_result_state(tmp_path):
    SessionLocal = _override_database(tmp_path, "feishu-push.db")
    try:
        user_id = _create_user(SessionLocal)
        db = SessionLocal()
        try:
            note = Note(user_id=user_id, platform_account_id=1, platform="xhs", note_id="xhs-1", title="标题", content="正文", author_name="作者")
            db.add(note)
            db.commit()
            db.refresh(note)
            note_id = note.id
        finally:
            db.close()
        headers = _auth_headers(user_id)

        response = client.post("/api/integrations/feishu/xhs-notes/push", headers=headers, json={"note_ids": [note_id], "dry_run": True})

        assert response.status_code == 200
        body = response.json()
        assert body["dry_run"] is True
        assert body["updated_count"] == 1
        assert body["failed_count"] == 0
        assert body["records"][0]["fields"]["系统笔记ID"] == str(note_id)
        assert body["records"][0]["fields"]["原链接"] == {"text": "标题", "link": "https://www.xiaohongshu.com/explore/xhs-1"}
        assert body["records"][0]["fields"]["分析状态"] == "待分析"

        db = SessionLocal()
        try:
            result = db.scalar(select(NoteAnalysisResult).where(NoteAnalysisResult.note_id == note_id))
            assert result is not None
            assert result.push_status == "dry_run"
            assert result.analysis_status == "待分析"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


class FakeFeishuClient:
    def __init__(self):
        self.fields = []
        self.records = []
        self.created_fields = []
        self.updated_fields = []
        self.created_records = []
        self.updated_records = []
        self.created_apps = []
        self.created_tables = []
        self.permission_members = []
        self.uploaded_attachments = []
        self.bitable_app_token = ""
        self.table_id = ""

    def create_app(self, *, name, folder_token=""):
        app = {"app_token": "app_created", "name": name, "folder_token": folder_token}
        self.created_apps.append(app)
        return app

    def create_table(self, *, name):
        table = {"table_id": "tbl_created", "name": name}
        self.created_tables.append(table)
        return table

    def list_fields(self):
        return self.fields

    def create_field(self, definition):
        field = feishu_bitable_service._feishu_field_payload(definition)
        self.fields.append(field)
        self.created_fields.append(field)
        return field

    def update_field(self, field_id, definition):
        updated = {"field_id": field_id, **feishu_bitable_service._feishu_field_payload(definition)}
        for field in self.fields:
            if field.get("field_id") == field_id:
                field.update(updated)
                self.updated_fields.append(updated)
                return updated
        raise AssertionError(f"field_id not found: {field_id}")

    def list_records(self):
        return self.records

    def export_bitable_csv(self):
        return getattr(self, "exported_csv", b"")

    def create_record(self, fields):
        record = {"record_id": f"rec_{len(self.records) + 1}", "fields": fields}
        self.records.append(record)
        self.created_records.append(record)
        return record

    def update_record(self, record_id, fields):
        record = {"record_id": record_id, "fields": fields}
        self.updated_records.append(record)
        return record

    def upload_bitable_attachment(self, *, file_name, content, content_type="application/octet-stream"):
        token = f"file_{len(self.uploaded_attachments) + 1}"
        self.uploaded_attachments.append({"file_name": file_name, "content": content, "content_type": content_type, "file_token": token})
        return token

    def add_bitable_permission_member(self, *, app_token, member_type, member_id, perm="edit", notify_lark=False):
        member = {"app_token": app_token, "member_type": member_type, "member_id": member_id, "perm": perm, "notify_lark": notify_lark}
        self.permission_members.append(member)
        return {"is_all_success": True, "fail_members": []}


def test_create_feishu_analysis_base_creates_app_table_and_fields_without_network():
    fake = FakeFeishuClient()

    result = feishu_bitable_service.create_feishu_analysis_base(fake, base_name="小红书内容分析总表", table_name="小红书内容分析")

    assert result["status"] == "success"
    assert result["app_token"] == "app_created"
    assert result["table_id"] == "tbl_created"
    assert result["bitable_url"] == "https://www.feishu.cn/base/app_created?table=tbl_created"
    assert result["created_fields"] == len(feishu_bitable_service.FEISHU_FIELD_DEFINITIONS)
    assert fake.created_apps[0]["name"] == "小红书内容分析总表"
    assert fake.created_tables[0]["name"] == "小红书内容分析"


def test_grant_permission_endpoint_grants_openchat_edit_access(tmp_path, monkeypatch):
    SessionLocal = _override_database(tmp_path, "feishu-grant-permission.db")
    fake = FakeFeishuClient()

    def fake_create_client(config):
        assert config.bitable_app_token == "app"
        return fake

    monkeypatch.setattr("backend.app.api.feishu_integration.create_feishu_client_from_config", fake_create_client)
    try:
        user_id = _create_user(SessionLocal)
        headers = _auth_headers(user_id)
        client.put(
            "/api/integrations/feishu/config",
            headers=headers,
            json={
                "app_id": "cli_xxx",
                "app_secret": "secret",
                "bitable_url": "https://www.feishu.cn/base/app?table=tbl",
                "table_id": "tbl",
                "enabled": True,
                "collaborator_member_type": "userid",
                "collaborator_member_id": "oc_xxx",
                "collaborator_perm": "edit",
            },
        )

        response = client.post("/api/integrations/feishu/grant-permission", headers=headers, json={})

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert body["config"]["collaborator_member_type"] == "openchat"
        assert fake.permission_members == [{"app_token": "app", "member_type": "openchat", "member_id": "oc_xxx", "perm": "edit", "notify_lark": False}]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_create_analysis_base_endpoint_updates_config_with_fake_client(tmp_path, monkeypatch):
    SessionLocal = _override_database(tmp_path, "feishu-create-base.db")
    fake = FakeFeishuClient()

    def fake_create_client(config):
        assert config.app_id == "cli_xxx"
        return fake

    monkeypatch.setattr("backend.app.api.feishu_integration.create_feishu_bootstrap_client_from_config", fake_create_client)
    try:
        user_id = _create_user(SessionLocal)
        headers = _auth_headers(user_id)
        client.put(
            "/api/integrations/feishu/config",
            headers=headers,
            json={
                "app_id": "cli_xxx",
                "app_secret": "secret",
                "bitable_url": "",
                "table_id": "",
                "enabled": True,
                "collaborator_member_type": "openchat",
                "collaborator_member_id": "oc_xxx",
                "collaborator_perm": "edit",
            },
        )

        response = client.post("/api/integrations/feishu/create-analysis-base", headers=headers, json={"base_name": "小红书内容分析总表", "table_name": "小红书内容分析"})

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert body["app_token"] == "app_created"
        assert body["table_id"] == "tbl_created"
        assert body["config"]["bitable_url"] == "https://www.feishu.cn/base/app_created?table=tbl_created"
        assert body["grant_result"]["status"] == "success"
        assert fake.permission_members == [{"app_token": "app_created", "member_type": "openchat", "member_id": "oc_xxx", "perm": "edit", "notify_lark": False}]
        db = SessionLocal()
        try:
            config = db.scalar(select(FeishuIntegrationConfig))
            assert config.bitable_app_token == "app_created"
            assert config.table_id == "tbl_created"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_feishu_analysis_status_definition_includes_discarded():
    analysis_status = next(item for item in feishu_bitable_service.FEISHU_FIELD_DEFINITIONS if item["field_name"] == "分析状态")

    assert "已废弃" in analysis_status["options"]


def test_ensure_feishu_fields_updates_existing_analysis_status_options():
    fake = FakeFeishuClient()
    existing_options = [
        {"name": "待分析", "id": "opt_1", "color": 0},
        {"name": "分析中", "id": "opt_2", "color": 1},
        {"name": "已完成", "id": "opt_3", "color": 2},
    ]
    fake.fields = [
        {
            "field_id": "fld_analysis_status",
            "field_name": "分析状态",
            "type": 3,
            "property": {"options": existing_options},
        }
    ]

    result = feishu_bitable_service.ensure_feishu_fields(fake)

    assert result["status"] == "ok"
    assert fake.updated_fields[0]["field_id"] == "fld_analysis_status"
    assert fake.updated_fields[0]["property"]["options"] == [
        {"name": "待分析", "id": "opt_1", "color": 0},
        {"name": "分析中", "id": "opt_2", "color": 1},
        {"name": "已完成", "id": "opt_3", "color": 2},
        {"name": "废弃"},
        {"name": "已废弃"},
    ]


def test_ensure_feishu_fields_fails_when_analysis_status_is_non_select_and_missing_option():
    fake = FakeFeishuClient()
    fake.fields = [
        {
            "field_id": "fld_analysis_status",
            "field_name": "分析状态",
            "type": 1,
            "property": {"options": [{"name": "待分析"}]},
        }
    ]

    result = feishu_bitable_service.ensure_feishu_fields(fake)

    assert result["status"] == "failed"
    assert result["updated_count"] == 0
    assert fake.updated_fields == []
    assert "分析状态" in result["errors"][0]
    assert "单选" in result["errors"][0]


def test_ensure_feishu_fields_fails_when_analysis_status_alias_lacks_discarded_option():
    fake = FakeFeishuClient()
    fake.fields = [
        {
            "field_id": "fld_analysis_status_alias",
            "field_name": "分析状态确认",
            "type": 3,
            "property": {"options": [{"name": "待分析"}, {"name": "分析中"}, {"name": "已完成"}]},
        }
    ]

    result = feishu_bitable_service.ensure_feishu_fields(fake)

    assert result["status"] == "failed"
    assert result["updated_count"] == 0
    assert fake.updated_fields == []
    assert result["errors"]
    assert "分析状态确认" in result["errors"][0]
    assert "已废弃" in result["errors"][0]


def test_real_ensure_fields_service_uses_client_without_network():
    fake = FakeFeishuClient()

    result = feishu_bitable_service.ensure_feishu_fields(fake)

    assert result["dry_run"] is False
    assert result["status"] == "ok"
    assert result["created_count"] == len(feishu_bitable_service.FEISHU_FIELD_DEFINITIONS)
    assert fake.created_fields[0]["field_name"] == "系统笔记ID"


def test_push_notes_to_feishu_stops_when_required_feishu_fields_fail(tmp_path):
    SessionLocal = _override_database(tmp_path, "feishu-push-field-failure.db")
    try:
        user_id = _create_user(SessionLocal)
        db = SessionLocal()
        try:
            note = Note(user_id=user_id, platform_account_id=1, platform="xhs", note_id="xhs-field-fail", title="标题", content="正文", author_name="作者")
            db.add(note)
            db.commit()
            db.refresh(note)
            note_id = note.id
        finally:
            db.close()

        fake = FakeFeishuClient()
        fake.fields = [
            {
                "field_id": "fld_analysis_status_alias",
                "field_name": "分析状态确认",
                "type": 3,
                "property": {"options": [{"name": "待分析"}, {"name": "分析中"}, {"name": "已完成"}]},
            }
        ]
        db = SessionLocal()
        try:
            with pytest.raises(feishu_bitable_service.FeishuIntegrationError) as exc_info:
                feishu_bitable_service.push_notes_to_feishu(db, user_id=user_id, note_ids=[note_id], client=fake)
        finally:
            db.close()

        assert "分析状态确认" in str(exc_info.value)
        assert "已废弃" in str(exc_info.value)
        assert fake.created_records == []
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_real_push_service_creates_or_updates_feishu_records_with_fake_client(tmp_path):
    SessionLocal = _override_database(tmp_path, "feishu-real-push.db")
    try:
        user_id = _create_user(SessionLocal)
        db = SessionLocal()
        try:
            note = Note(user_id=user_id, platform_account_id=1, platform="xhs", note_id="xhs-real", title="真实同步标题", content="正文", author_name="作者")
            db.add(note)
            db.commit()
            db.refresh(note)
            note_id = note.id
        finally:
            db.close()

        fake = FakeFeishuClient()
        db = SessionLocal()
        try:
            created = feishu_bitable_service.push_notes_to_feishu(db, user_id=user_id, note_ids=[note_id], client=fake)
            assert created["created_count"] == 1
            assert created["updated_count"] == 0
            assert fake.created_records[0]["fields"]["系统笔记ID"] == str(note_id)
            assert fake.created_records[0]["fields"]["原链接"] == {"text": "真实同步标题", "link": "https://www.xiaohongshu.com/explore/xhs-real"}
            assert fake.created_records[0]["fields"]["内容类型"] == "经验分享"
            assert fake.created_records[0]["fields"]["可复用模型"] == ["测评背书模型"]
            assert fake.created_records[0]["fields"]["内容利用方式"] == ["选题参考"]
            assert fake.created_records[0]["fields"]["搜索属性"] == "泛流量"

            fake.fields = [
                {"field_name": "系统笔记ID"},
                {"field_name": "平台笔记ID"},
                {"field_id": "fld_analysis_status", "field_name": "分析状态", "type": 3, "property": {"options": [{"name": option} for option in feishu_bitable_service.ANALYSIS_STATUS_OPTIONS]}},
                {"field_name": "内容类型"},
                {"field_name": "内容利用方式"},
            ]
            fake.records[0]["fields"]["内容类型"] = "测评"
            updated = feishu_bitable_service.push_notes_to_feishu(db, user_id=user_id, note_ids=[note_id], client=fake)
            assert updated["created_count"] == 0
            assert updated["updated_count"] == 1
            assert fake.updated_records[0]["record_id"] == "rec_1"
            assert "分析状态" not in fake.updated_records[0]["fields"]
            assert "内容类型" not in fake.updated_records[0]["fields"]

            result = db.scalar(select(NoteAnalysisResult).where(NoteAnalysisResult.note_id == note_id))
            assert result.push_status == "synced"
            assert result.external_record_id == "rec_1"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_feishu_preanalysis_normalizes_avoidance_tutorial_to_avoidance():
    note = Note(id=1, user_id=1, platform_account_id=1, platform="xhs", note_id="xhs", title="装修避坑教程", content="这些步骤不要踩坑", author_name="作者")

    assert feishu_bitable_service.normalize_content_type("避坑教程") == "避坑"
    assert feishu_bitable_service.normalize_search_attribute("", note) == "强搜索"


def test_feishu_preanalysis_prompt_uses_reusable_model_decision_rules():
    note = Note(id=1, user_id=1, platform_account_id=1, platform="xhs", note_id="xhs", title="小户型装修前后对比", content="先说痛点，再给出具体方法和真实体验反馈。", author_name="作者")

    prompt = feishu_bitable_service._feishu_preanalysis_prompt(note, ["装修", "小户型"])

    assert "可复用模型指内容背后的传播方式、吸引逻辑或说服机制" in prompt
    assert "不分析内容主题" in prompt
    assert "不分析标题形式" in prompt
    assert "不分析内容结构" in prompt
    assert "不允许因为出现案例就直接判断故事案例模型" in prompt
    assert "至少输出1项，最多输出3项" in prompt
    assert "按影响强弱排序" in prompt


def test_rule_based_reusable_models_follow_user_priority_rules():
    note = Note(
        id=1,
        user_id=1,
        platform_account_id=1,
        platform="xhs",
        note_id="xhs",
        title="小户型装修避坑",
        content="入住前最担心踩坑，改造前后差别很大。我按这几个方法一步步解决，收纳效率提升很多。",
        author_name="作者",
    )

    assert feishu_bitable_service.infer_reusable_models(note) == ["问题驱动模型", "教程方法模型", "对比反差模型"]


def test_rule_based_reusable_models_detects_review_backing():
    note = Note(
        id=1,
        user_id=1,
        platform_account_id=1,
        platform="xhs",
        note_id="xhs",
        title="柜子收纳工具测评",
        content="我实测了三种方案，用真实体验和反馈对比效果，最后这款最稳定。",
        author_name="作者",
    )

    assert "测评背书模型" in feishu_bitable_service.infer_reusable_models(note)


def test_real_push_service_uploads_cover_attachment_and_uses_legacy_field_aliases(tmp_path, monkeypatch):
    SessionLocal = _override_database(tmp_path, "feishu-cover-push.db")
    try:
        user_id = _create_user(SessionLocal)
        db = SessionLocal()
        try:
            admin = User(
                username="feishu-model-admin",
                password_hash=hash_password("secret123"),
                role="admin",
                status="active",
            )
            db.add(admin)
            db.flush()
            model = feishu_bitable_service.ModelConfig(
                user_id=admin.id,
                name="text",
                model_type="text",
                provider="openai-compatible",
                model_name="mock",
                base_url="https://example.test/v1",
                encrypted_api_key=encrypt_text("model-secret"),
                is_default=True,
            )
            note = Note(
                user_id=user_id,
                platform_account_id=1,
                platform="xhs",
                note_id="xhs-cover",
                title="小户型浴室避坑教程",
                content="装修前先看这些坑，附步骤",
                author_name="作者",
                raw_json={"cover_url": "https://img.example.test/cover.jpg", "tags": ["装修", "避坑"]},
            )
            db.add_all([model, note])
            db.flush()
            db.add(
                ModelCapabilityDefault(
                    capability="text",
                    model_config_id=model.id,
                    updated_by_user_id=admin.id,
                )
            )
            db.commit()
            db.refresh(note)
            note_id = note.id
        finally:
            db.close()

        def fake_read_cover_bytes(ref):
            assert ref == "https://img.example.test/cover.jpg"
            return b"\xff\xd8\xfffake", "image/jpeg"

        class FakeTextClient:
            def complete_json_prompt(self, **kwargs):
                return '{"content_type":"避坑教程","reusable_models":["问题驱动模型","教程方法模型"],"reuse_values":["选题参考","正文结构参考"],"search_attribute":"强搜索"}'

        monkeypatch.setattr(feishu_bitable_service, "_read_cover_bytes", fake_read_cover_bytes)
        monkeypatch.setattr(feishu_bitable_service, "OpenAICompatibleTextClient", FakeTextClient)

        fake = FakeFeishuClient()
        fake.fields = [
            {"field_name": "系统笔记ID"},
            {"field_name": "平台笔记ID"},
            {"field_name": "标签/话题"},
            {"field_name": "复用价值"},
            {"field_name": "搜素属性"},
            {"field_name": "封面"},
            {"field_name": "内容类型"},
            {"field_name": "可复用模型"},
        ]
        db = SessionLocal()
        try:
            created = feishu_bitable_service.push_notes_to_feishu(db, user_id=user_id, note_ids=[note_id], client=fake)
            fields = fake.created_records[0]["fields"]
            assert created["created_count"] == 1
            assert fields["内容类型"] == "避坑"
            assert fields["可复用模型"] == ["问题驱动模型", "教程方法模型"]
            assert fields["复用价值"] == ["选题参考", "正文结构参考"]
            assert fields["搜素属性"] == "强搜索"
            assert fields["标签/话题"] == "装修、避坑"
            assert fields["封面"] == [{"file_token": "file_1"}]
            assert fake.uploaded_attachments[0]["file_name"] == f"xhs-note-{note_id}-cover.jpg"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_infer_note_type_reads_nested_xhs_raw_json():
    note = Note(
        id=1,
        user_id=1,
        platform_account_id=1,
        platform="xhs",
        note_id="xhs-nested",
        title="标题",
        content="正文",
        author_name="作者",
        raw_json={
            "data": {
                "items": [
                    {
                        "model_type": "note",
                        "note_card": {
                            "type": "normal",
                            "image_list": [{"url": "https://img.example.test/cover.webp"}],
                        },
                    }
                ]
            }
        },
    )

    assert feishu_bitable_service.infer_note_type(note) == "图文"


def test_push_service_overwrites_existing_analysis_type_and_cover_from_managed_media(tmp_path, monkeypatch):
    SessionLocal = _override_database(tmp_path, "feishu-overwrite-cover.db")
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    media_name = "xhs-asset-u3-cover.webp"
    media_dir.joinpath(media_name).write_bytes(b"RIFF\x10\x00\x00\x00WEBPVP8 fake")
    monkeypatch.setattr(feishu_bitable_service, "get_settings", lambda: SimpleNamespace(storage_dir=str(tmp_path)))
    try:
        user_id = _create_user(SessionLocal)
        db = SessionLocal()
        try:
            note = Note(
                user_id=user_id,
                platform_account_id=1,
                platform="xhs",
                note_id="xhs-overwrite",
                title="小户型装修",
                content="小户型装修方案",
                author_name="作者",
                raw_json={
                    "data": {
                        "items": [
                            {
                                "model_type": "note",
                                "note_card": {"type": "normal", "image_list": [{"url": "https://img.example.test/fallback.webp"}]},
                            }
                        ]
                    }
                },
            )
            db.add(note)
            db.commit()
            db.refresh(note)
            note_id = note.id
            db.add(NoteAsset(note_id=note_id, asset_type="image", url="https://img.example.test/cover.webp", local_path=media_name, sort_order=0))
            db.add(
                NoteAnalysisResult(
                    user_id=user_id,
                    note_id=note_id,
                    source="feishu",
                    external_record_id="rec_existing",
                    content_type="测评",
                    reusable_models=["测评背书模型"],
                    reuse_value="竞品参考",
                    analysis_status="已完成",
                )
            )
            db.commit()
        finally:
            db.close()

        fake = FakeFeishuClient()
        fake.records = [
            {
                "record_id": "rec_existing",
                "fields": {
                    "系统笔记ID": str(note_id),
                    "平台笔记ID": "xhs-overwrite",
                    "笔记类型": "未知",
                    "封面": [{"file_token": "old_file"}],
                    "内容类型": "测评",
                    "可复用模型": ["测评背书模型"],
                    "内容利用方式": ["竞品参考"],
                    "搜索属性": "泛流量",
                    "分析状态": "已完成",
                },
            }
        ]
        db = SessionLocal()
        try:
            result = feishu_bitable_service.push_notes_to_feishu(db, user_id=user_id, note_ids=[note_id], client=fake, overwrite_existing=True)
            assert result["updated_count"] == 1
            assert fake.uploaded_attachments[0]["file_name"] == f"xhs-note-{note_id}-cover.webp"
            fields = fake.updated_records[0]["fields"]
            assert fields["笔记类型"] == "图文"
            assert fields["封面"] == [{"file_token": "file_1"}]
            assert fields["内容类型"] == "经验分享"
            assert fields["可复用模型"] == ["场景种草模型"]
            assert fields["内容利用方式"] == ["选题参考"]

            analysis = db.scalar(select(NoteAnalysisResult).where(NoteAnalysisResult.note_id == note_id))
            assert analysis.content_type == "经验分享"
            assert analysis.reusable_models == ["场景种草模型"]
            assert analysis.reuse_value == "选题参考"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_push_all_endpoint_forwards_overwrite_existing_to_batches(tmp_path, monkeypatch):
    SessionLocal = _override_database(tmp_path, "feishu-push-all-overwrite.db")
    calls = []

    def fake_create_client(config):
        return FakeFeishuClient()

    def fake_push(db, *, user_id, note_ids, client, overwrite_existing=False):
        calls.append({"note_ids": list(note_ids), "overwrite_existing": overwrite_existing})
        return {
            "dry_run": False,
            "created_count": 0,
            "updated_count": len(note_ids),
            "failed_count": 0,
            "errors": [],
            "records": [{"note_id": note_id, "status": "updated"} for note_id in note_ids],
        }

    monkeypatch.setattr("backend.app.api.feishu_integration.create_feishu_client_from_config", fake_create_client)
    monkeypatch.setattr("backend.app.api.feishu_integration.push_notes_to_feishu", fake_push)
    try:
        user_id = _create_user(SessionLocal)
        db = SessionLocal()
        try:
            db.add(FeishuIntegrationConfig(user_id=user_id, app_id="cli_xxx", encrypted_app_secret="encrypted", bitable_url="https://www.feishu.cn/base/app?table=tbl", bitable_app_token="app", table_id="tbl", enabled=True))
            for index in range(2):
                db.add(Note(user_id=user_id, platform_account_id=1, platform="xhs", note_id=f"xhs-overwrite-{index}", title=f"标题{index}", content="正文", author_name="作者"))
            db.commit()
        finally:
            db.close()
        headers = _auth_headers(user_id)

        response = client.post("/api/integrations/feishu/xhs-notes/push-all", headers=headers, json={"dry_run": False, "batch_size": 1, "overwrite_existing": True})

        assert response.status_code == 200
        body = response.json()
        assert body["updated_count"] == 2
        assert [call["overwrite_existing"] for call in calls] == [True, True]
        assert [len(call["note_ids"]) for call in calls] == [1, 1]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_push_all_xhs_notes_endpoint_batches_all_notes(tmp_path, monkeypatch):
    SessionLocal = _override_database(tmp_path, "feishu-push-all.db")
    fake = FakeFeishuClient()
    calls = []

    def fake_create_client(config):
        assert config.bitable_app_token == "app"
        return fake

    def fake_push(db, *, user_id, note_ids, client, overwrite_existing=False):
        assert overwrite_existing is False
        calls.append(list(note_ids))
        return {
            "dry_run": False,
            "created_count": len(note_ids),
            "updated_count": 0,
            "failed_count": 0,
            "errors": [],
            "records": [{"note_id": note_id, "status": "created"} for note_id in note_ids],
        }

    monkeypatch.setattr("backend.app.api.feishu_integration.create_feishu_client_from_config", fake_create_client)
    monkeypatch.setattr("backend.app.api.feishu_integration.push_notes_to_feishu", fake_push)
    try:
        user_id = _create_user(SessionLocal)
        db = SessionLocal()
        try:
            db.add(FeishuIntegrationConfig(user_id=user_id, app_id="cli_xxx", encrypted_app_secret="encrypted", bitable_url="https://www.feishu.cn/base/app?table=tbl", bitable_app_token="app", table_id="tbl", enabled=True))
            for index in range(3):
                db.add(Note(user_id=user_id, platform_account_id=1, platform="xhs", note_id=f"xhs-{index}", title=f"标题{index}", content="正文", author_name="作者"))
            db.commit()
        finally:
            db.close()
        headers = _auth_headers(user_id)

        response = client.post("/api/integrations/feishu/xhs-notes/push-all", headers=headers, json={"dry_run": False, "batch_size": 2})

        assert response.status_code == 200
        body = response.json()
        assert body["total_count"] == 3
        assert body["processed_count"] == 3
        assert body["created_count"] == 3
        assert body["updated_count"] == 0
        assert body["failed_count"] == 0
        assert [len(batch) for batch in calls] == [2, 1]
        assert body["batches"][0]["count"] == 2
        assert body["batches"][1]["count"] == 1
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_real_pull_service_reads_client_records_with_note_id_filter(tmp_path):
    SessionLocal = _override_database(tmp_path, "feishu-real-pull.db")
    try:
        user_id = _create_user(SessionLocal)
        db = SessionLocal()
        try:
            note = Note(user_id=user_id, platform_account_id=1, platform="xhs", note_id="xhs-pull", title="标题", content="正文", author_name="作者")
            db.add(note)
            db.commit()
            db.refresh(note)
            note_id = note.id
        finally:
            db.close()

        fake = FakeFeishuClient()
        fake.records = [
            {
                "record_id": "rec_pull",
                "fields": {
                    "系统笔记ID": str(note_id),
                    "分析状态": "已完成",
                    "产品/主题对象": "主题",
                    "内容类型": "教程",
                    "复用价值": "标题参考",
                },
            }
        ]
        db = SessionLocal()
        try:
            result = feishu_bitable_service.pull_feishu_analysis_records_from_client(db, user_id=user_id, client=fake, note_ids=[note_id])
            assert result["updated_count"] == 1
            analysis = db.scalar(select(NoteAnalysisResult).where(NoteAnalysisResult.note_id == note_id))
            assert analysis.analysis_status == "已完成"
            assert analysis.content_type == "教程"
            assert analysis.reuse_value == "标题参考"
            assert analysis.external_record_id == "rec_pull"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_full_pull_service_reads_exported_csv_ai_fields(tmp_path):
    SessionLocal = _override_database(tmp_path, "feishu-full-pull-csv.db")
    try:
        user_id = _create_user(SessionLocal)
        db = SessionLocal()
        try:
            note = Note(user_id=user_id, platform_account_id=1, platform="xhs", note_id="xhs-csv-pull", title="标题", content="正文", author_name="作者")
            db.add(note)
            db.commit()
            db.refresh(note)
            note_id = note.id
        finally:
            db.close()

        fake = FakeFeishuClient()
        fake.records = []
        fake.exported_csv = (
            "﻿使用状态,分析状态确认,系统笔记ID,评分,评级,核心产品/服务,核心卖点/观点,目标人群,内容钩子,封面类型,标题类型,笔记结构分析,可复用模型,内容利用方式,搜素属性\n"
            f"已同步,分析完成,{note_id},9.5,爆款潜力,衣柜收纳,强调省空间和低成本,小户型家庭,痛点开场,前后对比封面,数字清单标题,先痛点后方案,问题驱动模型、教程方法模型,标题参考、正文结构参考,强搜索\n"
        ).encode("utf-8-sig")
        db = SessionLocal()
        try:
            result = feishu_bitable_service.pull_feishu_analysis_records_from_client(db, user_id=user_id, client=fake, note_ids=None)
            assert result["updated_count"] == 1
            analysis = db.scalar(select(NoteAnalysisResult).where(NoteAnalysisResult.note_id == note_id))
            assert analysis.analysis_status == "分析完成"
            assert analysis.score == 9.5
            assert analysis.rating == "爆款潜力"
            assert analysis.subject_object == "衣柜收纳"
            assert analysis.core_points == "强调省空间和低成本"
            assert analysis.target_audience == "小户型家庭"
            assert analysis.title_hook == "痛点开场"
            assert analysis.content_structure == "先痛点后方案"
            assert analysis.reusable_models == ["问题驱动模型", "教程方法模型"]
            assert analysis.reuse_value == "标题参考、正文结构参考"
            assert analysis.search_attribute == "强搜索"
            assert analysis.raw_payload["封面类型"] == "前后对比封面"
            assert analysis.raw_payload["标题类型"] == "数字清单标题"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_pull_feishu_analysis_payload_updates_analysis_result(tmp_path):
    SessionLocal = _override_database(tmp_path, "feishu-pull.db")
    try:
        user_id = _create_user(SessionLocal)
        db = SessionLocal()
        try:
            note = Note(user_id=user_id, platform_account_id=1, platform="xhs", note_id="xhs-2", title="标题", content="正文", author_name="作者")
            db.add(note)
            db.commit()
            db.refresh(note)
            note_id = note.id
        finally:
            db.close()
        headers = _auth_headers(user_id)
        payload = {
            "dry_run": True,
            "records": [
                {
                    "fields": {
                        "系统笔记ID": str(note_id),
                        "分析状态": "已完成",
                        "产品/主题对象": "表达力训练",
                        "内容类型": "种草",
                        "核心卖点/核心观点": "真实体验带出卖点",
                        "目标人群": "宝妈",
                        "封面/标题钩子": "孩子不敢表达怎么办",
                        "内容结构分析": "痛点开头-经验分享-行动引导",
                        "可复用模型": ["问题驱动模型", "场景种草模型"],
                        "复用价值": "可直接改写",
                        "搜索属性": "强搜索",
                        "评分": 7.5,
                        "评级": [{"text": "优质内容", "type": "text"}],
                        "分析备注": "适合二创",
                    },
                    "record_id": "rec_xxx",
                }
            ],
        }

        response = client.post("/api/integrations/feishu/xhs-notes/pull", headers=headers, json=payload)

        assert response.status_code == 200
        assert response.json()["updated_count"] == 1
        db = SessionLocal()
        try:
            result = db.scalar(select(NoteAnalysisResult).where(NoteAnalysisResult.note_id == note_id))
            assert result.analysis_status == "已完成"
            assert result.subject_object == "表达力训练"
            assert result.content_type == "种草"
            assert result.reusable_models == ["问题驱动模型", "场景种草模型"]
            assert result.reuse_value == "可直接改写"
            assert result.search_attribute == "强搜索"
            assert result.score == 7.5
            assert result.rating == "优质内容"
            assert result.external_record_id == "rec_xxx"
            assert result.pull_status == "success"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_pull_feishu_analysis_records_persists_search_attribute_and_clears_blank(tmp_path):
    SessionLocal = _override_database(tmp_path, "feishu-search-attribute.db")
    try:
        user_id = _create_user(SessionLocal)
        db = SessionLocal()
        try:
            note = Note(user_id=user_id, platform_account_id=1, platform="xhs", note_id="xhs-search", title="AI 搜索教程", content="强搜索选题", author_name="作者")
            db.add(note)
            db.commit()
            db.refresh(note)
            note_id = note.id
        finally:
            db.close()

        headers = _auth_headers(user_id)
        response = client.post(
            "/api/integrations/feishu/xhs-notes/pull",
            headers=headers,
            json={
                "dry_run": True,
                "records": [
                    {
                        "record_id": "rec_search_1",
                        "fields": {
                            "系统笔记ID": str(note_id),
                            "分析状态": "已完成",
                            "核心产品/服务": "AI 工具",
                            "内容类型": "教程",
                            "可复用模型": ["教程方法模型"],
                            "内容利用方式": ["正文结构参考"],
                            "搜索属性": "强搜索",
                        },
                    }
                ],
            },
        )

        assert response.status_code == 200
        assert response.json()["updated_count"] == 1
        db = SessionLocal()
        try:
            result = db.scalar(select(NoteAnalysisResult).where(NoteAnalysisResult.note_id == note_id))
            assert result is not None
            assert result.search_attribute == "强搜索"
        finally:
            db.close()

        clear_response = client.post(
            "/api/integrations/feishu/xhs-notes/pull",
            headers=headers,
            json={
                "dry_run": True,
                "records": [
                    {
                        "record_id": "rec_search_1",
                        "fields": {
                            "系统笔记ID": str(note_id),
                            "分析状态": "已完成",
                            "搜索属性": "",
                        },
                    }
                ],
            },
        )

        assert clear_response.status_code == 200
        db = SessionLocal()
        try:
            result = db.scalar(select(NoteAnalysisResult).where(NoteAnalysisResult.note_id == note_id))
            assert result is not None
            assert result.search_attribute is None
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)

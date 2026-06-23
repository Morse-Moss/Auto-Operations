from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import Base, get_db
from backend.app.core.security import create_access_token, hash_password
from backend.app.main import app
from backend.app.models import FeishuIntegrationConfig, Note, NoteAnalysisResult, User
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
        user = User(username=username, password_hash=hash_password("secret123"))
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
        }

        response = client.put("/api/integrations/feishu/config", headers=headers, json=payload)

        assert response.status_code == 200
        body = response.json()
        assert body["app_id"] == "cli_xxx"
        assert body["has_app_secret"] is True
        assert "app_secret" not in body
        assert body["table_id"] == "tbl_xxx"
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
        self.created_records = []
        self.updated_records = []

    def list_fields(self):
        return self.fields

    def create_field(self, definition):
        field = {"field_name": definition["field_name"], "type": definition["type"]}
        self.fields.append(field)
        self.created_fields.append(field)
        return field

    def list_records(self):
        return self.records

    def create_record(self, fields):
        record = {"record_id": f"rec_{len(self.records) + 1}", "fields": fields}
        self.records.append(record)
        self.created_records.append(record)
        return record

    def update_record(self, record_id, fields):
        record = {"record_id": record_id, "fields": fields}
        self.updated_records.append(record)
        return record


def test_real_ensure_fields_service_uses_client_without_network():
    fake = FakeFeishuClient()

    result = feishu_bitable_service.ensure_feishu_fields(fake)

    assert result["dry_run"] is False
    assert result["status"] == "ok"
    assert result["created_count"] == len(feishu_bitable_service.FEISHU_FIELD_DEFINITIONS)
    assert fake.created_fields[0]["field_name"] == "系统笔记ID"


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

            updated = feishu_bitable_service.push_notes_to_feishu(db, user_id=user_id, note_ids=[note_id], client=fake)
            assert updated["created_count"] == 0
            assert updated["updated_count"] == 1
            assert fake.updated_records[0]["record_id"] == "rec_1"
            assert "分析状态" not in fake.updated_records[0]["fields"]

            result = db.scalar(select(NoteAnalysisResult).where(NoteAnalysisResult.note_id == note_id))
            assert result.push_status == "synced"
            assert result.external_record_id == "rec_1"
        finally:
            db.close()
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
            assert result.external_record_id == "rec_xxx"
            assert result.pull_status == "success"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from backend.app.api.platforms.xhs.pc import get_xhs_pc_api_adapter_factory
from backend.app.core.database import Base, get_db
from backend.app.core.security import create_access_token, hash_password
from backend.app.main import app
from backend.app.api.platforms.xhs import crawl as xhs_crawl
from backend.app.models import Note, NoteAnalysisResult, NoteAsset, NoteExclusion, PlatformAccount, User
from backend.app.services import feishu_bitable_service
from backend.app.services.note_exclusion_service import build_current_cleanup_candidates, is_note_excluded, mark_notes_excluded

client = TestClient(app)


def _override_database(tmp_path, name="note-exclusions.db", return_engine=False):
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
    if return_engine:
        return TestingSessionLocal, engine
    return TestingSessionLocal


def _create_user(SessionLocal, username="exclusion-owner"):
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


def _create_note_with_analysis(
    SessionLocal,
    user_id: int,
    *,
    note_id: str,
    title: str,
    content: str = "",
    score=None,
    rating=None,
    subject="",
    status="分析完成",
    external_record_id_marker="default",
    raw_payload=None,
):
    db = SessionLocal()
    try:
        note = Note(user_id=user_id, platform_account_id=1, platform="xhs", note_id=note_id, title=title, content=content, author_name="作者")
        db.add(note)
        db.flush()
        analysis = NoteAnalysisResult(
            user_id=user_id,
            note_id=note.id,
            source="feishu",
            analysis_status=status,
            score=score,
            rating=rating,
            subject_object=subject,
            external_record_id=f"rec_{note_id}" if external_record_id_marker == "default" else external_record_id_marker,
            raw_payload=raw_payload,
        )
        db.add(analysis)
        db.commit()
        db.refresh(note)
        return note.id
    finally:
        db.close()


def _create_note_without_analysis(SessionLocal, user_id: int, *, note_id: str, title: str, content: str = ""):
    db = SessionLocal()
    try:
        note = Note(user_id=user_id, platform_account_id=1, platform="xhs", note_id=note_id, title=title, content=content, author_name="作者")
        db.add(note)
        db.commit()
        db.refresh(note)
        return note.id
    finally:
        db.close()


class RecordingFeishuClient:
    def __init__(self, failing_record_id: str | None = None, field_names: list[str] | None = None, on_update=None):
        self.failing_record_id = failing_record_id
        self.field_names = field_names or ["分析状态", "内容利用方式", "分析备注"]
        self.on_update = on_update
        self.updated_records = []
        self.list_fields_count = 0

    def list_fields(self):
        self.list_fields_count += 1
        return [{"field_name": name} for name in self.field_names]

    def update_record(self, record_id, fields):
        if self.on_update is not None:
            self.on_update(record_id, fields)
        if record_id == self.failing_record_id:
            raise RuntimeError("Feishu update failed")
        self.updated_records.append((record_id, fields))


class FieldListFailingFeishuClient:
    def __init__(self):
        self.updated_records = []

    def list_fields(self):
        raise RuntimeError("list fields boom")

    def update_record(self, record_id, fields):
        raise AssertionError("update_record should not be called when field listing fails")


class MinimalFeishuPushClient:
    def __init__(self):
        self.fields = [{"field_name": definition["field_name"]} for definition in feishu_bitable_service.FEISHU_FIELD_DEFINITIONS]
        self.records = []
        self.created_records = []
        self.updated_records = []
        self.uploaded = []

    def list_fields(self):
        return self.fields

    def create_field(self, definition):
        self.fields.append({"field_name": definition["field_name"]})
        return {"field": definition}

    def list_records(self):
        return self.records

    def create_record(self, fields):
        record = {"record_id": f"rec_{len(self.records) + 1}", "fields": fields}
        self.records.append(record)
        self.created_records.append(record)
        return record

    def update_record(self, record_id, fields):
        self.updated_records.append({"record_id": record_id, "fields": fields})
        return {"record_id": record_id, "fields": fields}

    def upload_bitable_attachment(self, *, file_name, content, content_type):
        self.uploaded.append(file_name)
        return f"file_{len(self.uploaded)}"


def test_note_exclusion_model_is_registered_in_metadata():
    table = Base.metadata.tables["note_exclusions"]

    assert NoteExclusion.__tablename__ == "note_exclusions"
    assert table.c.created_at.nullable is False
    assert table.c.updated_at.nullable is False
    assert table.c.updated_at.onupdate is not None
    assert next(iter(table.c.note_id.foreign_keys)).ondelete == "SET NULL"


def test_mark_notes_excluded_creates_memory_and_is_idempotent(tmp_path):
    SessionLocal = _override_database(tmp_path, "mark-excluded.db")
    try:
        user_id = _create_user(SessionLocal)
        note_id = _create_note_with_analysis(SessionLocal, user_id, note_id="xhs-low", title="低分素材", score=2.0, rating="低表现内容", subject="浴缸")
        db = SessionLocal()
        try:
            first = mark_notes_excluded(db, user_id=user_id, note_ids=[note_id], reason_code="low_score_bathtub", reason_text="浴缸低分", client=None)
            second = mark_notes_excluded(db, user_id=user_id, note_ids=[note_id], reason_code="low_score_bathtub", reason_text="浴缸低分", client=None)
            exclusion = db.scalar(select(NoteExclusion).where(NoteExclusion.platform_note_id == "xhs-low"))
            analysis = db.scalar(select(NoteAnalysisResult).where(NoteAnalysisResult.note_id == note_id))

            assert first["excluded_count"] == 1
            assert second["excluded_count"] == 1
            assert db.query(NoteExclusion).count() == 1
            assert exclusion.reason_code == "low_score_bathtub"
            assert exclusion.score == 2.0
            assert analysis.analysis_status == "已废弃"
            assert analysis.reuse_value == "废弃"
            assert is_note_excluded(db, user_id=user_id, platform="xhs", platform_note_id="xhs-low") is True
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_mark_notes_excluded_recovers_from_concurrent_unique_conflict(tmp_path):
    SessionLocal = _override_database(tmp_path, "mark-excluded-integrity-conflict.db")
    try:
        user_id = _create_user(SessionLocal)
        note_id = _create_note_with_analysis(SessionLocal, user_id, note_id="race-note", title="并发废弃", score=3.0, subject="浴缸")
        db = SessionLocal()
        original_commit = db.commit
        conflict_inserted = {"value": False}

        def commit_with_concurrent_insert():
            if not conflict_inserted["value"]:
                conflict_inserted["value"] = True
                competing_db = SessionLocal()
                try:
                    competing_db.add(
                        NoteExclusion(
                            user_id=user_id,
                            note_id=note_id,
                            platform="xhs",
                            platform_note_id="race-note",
                            reason_code="manual_excluded",
                            reason_text="并发先写入",
                        )
                    )
                    competing_db.commit()
                finally:
                    competing_db.close()
            return original_commit()

        db.commit = commit_with_concurrent_insert
        try:
            result = mark_notes_excluded(db, user_id=user_id, note_ids=[note_id], reason_code="low_score_bathtub", reason_text="重试更新", client=None)
            exclusion = db.scalar(select(NoteExclusion).where(NoteExclusion.platform_note_id == "race-note"))

            assert result["excluded_count"] == 1
            assert result["feishu_failed_count"] == 0
            assert db.query(NoteExclusion).count() == 1
            assert exclusion.reason_code == "low_score_bathtub"
            assert exclusion.reason_text == "重试更新"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_build_current_cleanup_candidates_matches_strict_rules(tmp_path):
    SessionLocal = _override_database(tmp_path, "cleanup-candidates.db")
    try:
        user_id = _create_user(SessionLocal)
        geo_id = _create_note_with_analysis(SessionLocal, user_id, note_id="geo-1", title="GEO 可以做什么", score=None, subject="")
        square_id = _create_note_with_analysis(SessionLocal, user_id, note_id="bath-square", title="粉色方形浴缸", score=9.0, subject="浴缸")
        low_bath_id = _create_note_with_analysis(SessionLocal, user_id, note_id="bath-low", title="小户型浴缸", score=6.5, subject="浴缸")
        high_bath_id = _create_note_with_analysis(SessionLocal, user_id, note_id="bath-high", title="浴缸避坑指南", score=9.0, subject="浴缸")
        low_other_id = _create_note_with_analysis(SessionLocal, user_id, note_id="other-low", title="飞书教程", score=3.0, subject="安装服务")
        db = SessionLocal()
        try:
            candidates = build_current_cleanup_candidates(db, user_id=user_id, strict=True)
            by_note_id = {item["note_id"]: item for item in candidates}

            assert geo_id in by_note_id
            assert by_note_id[geo_id]["reason_code"] == "geo"
            assert square_id in by_note_id
            assert by_note_id[square_id]["reason_code"] == "square_wall_bathtub"
            assert low_bath_id in by_note_id
            assert by_note_id[low_bath_id]["reason_code"] == "low_score_bathtub"
            assert low_other_id in by_note_id
            assert by_note_id[low_other_id]["reason_code"] == "low_score_non_bathtub"
            assert high_bath_id not in by_note_id
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_build_current_cleanup_candidates_fetches_analysis_without_n_plus_one(tmp_path):
    SessionLocal, engine = _override_database(tmp_path, "cleanup-candidates-query-count.db", return_engine=True)
    try:
        user_id = _create_user(SessionLocal)
        for index in range(5):
            _create_note_with_analysis(
                SessionLocal,
                user_id,
                note_id=f"query-count-{index}",
                title=f"低分浴缸 {index}",
                score=2.0,
                subject="浴缸",
            )
        analysis_selects = []

        def record_analysis_select(conn, cursor, statement, parameters, context, executemany):
            if "FROM note_analysis_results" in statement and statement.lstrip().upper().startswith("SELECT"):
                analysis_selects.append(statement)

        event.listen(engine, "before_cursor_execute", record_analysis_select)
        db = SessionLocal()
        try:
            candidates = build_current_cleanup_candidates(db, user_id=user_id, strict=True)
        finally:
            db.close()
            event.remove(engine, "before_cursor_execute", record_analysis_select)

        assert len(candidates) == 5
        assert len(analysis_selects) <= 1
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_build_current_cleanup_candidates_excludes_already_excluded_notes(tmp_path):
    SessionLocal = _override_database(tmp_path, "cleanup-candidates-existing-exclusion.db")
    try:
        user_id = _create_user(SessionLocal)
        existing_id = _create_note_with_analysis(SessionLocal, user_id, note_id="already-excluded", title="浴缸低分", score=2.0, subject="浴缸")
        fresh_id = _create_note_with_analysis(SessionLocal, user_id, note_id="fresh-low", title="另一个浴缸低分", score=2.0, subject="浴缸")
        db = SessionLocal()
        try:
            mark_notes_excluded(db, user_id=user_id, note_ids=[existing_id], reason_code="low_score_bathtub", reason_text="已处理", client=None)

            candidates = build_current_cleanup_candidates(db, user_id=user_id, strict=True)
            by_note_id = {item["note_id"]: item for item in candidates}

            assert existing_id not in by_note_id
            assert fresh_id in by_note_id
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_low_score_regular_bathroom_is_not_bathtub(tmp_path):
    SessionLocal = _override_database(tmp_path, "cleanup-candidates-regular-bathroom.db")
    try:
        user_id = _create_user(SessionLocal)
        note_id = _create_note_with_analysis(SessionLocal, user_id, note_id="regular-bathroom", title="普通卫生间浴室改造", score=3.0, subject="主卫收纳")
        db = SessionLocal()
        try:
            candidates = build_current_cleanup_candidates(db, user_id=user_id, strict=True)
            by_note_id = {item["note_id"]: item for item in candidates}

            assert by_note_id[note_id]["reason_code"] == "low_score_non_bathtub"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_build_current_cleanup_candidates_ignores_geo_in_raw_payload_url_and_id(tmp_path):
    SessionLocal = _override_database(tmp_path, "cleanup-candidates-opaque-id.db")
    try:
        user_id = _create_user(SessionLocal)
        note_id = _create_note_with_analysis(
            SessionLocal,
            user_id,
            note_id="ordinary-platform-id",
            title="普通装修记录",
            content="记录安装进度和预算",
            score=9.0,
            subject="安装服务",
            rating="可复用",
            raw_payload={"record_id": "geo_record_001", "url": "https://example.com/geo/ordinary"},
        )
        db = SessionLocal()
        try:
            candidates = build_current_cleanup_candidates(db, user_id=user_id, strict=True)
            by_note_id = {item["note_id"]: item for item in candidates}

            assert note_id not in by_note_id
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_geo_cleanup_does_not_match_geoffrey_or_geography_substrings(tmp_path):
    SessionLocal = _override_database(tmp_path, "cleanup-candidates-geo-boundary.db")
    try:
        user_id = _create_user(SessionLocal)
        geoffrey_id = _create_note_with_analysis(SessionLocal, user_id, note_id="geoffrey", title="Geoffrey 的装修记录", content="普通案例", score=9.0, subject="安装服务")
        geography_id = _create_note_with_analysis(SessionLocal, user_id, note_id="geography", title="geography 风格墙面", content="普通案例", score=9.0, subject="安装服务")
        standalone_geo_id = _create_note_with_analysis(SessionLocal, user_id, note_id="standalone-geo", title="SEO GEO 选题方法", content="适合 AI 搜索", score=9.0, subject="安装服务")
        db = SessionLocal()
        try:
            candidates = build_current_cleanup_candidates(db, user_id=user_id, strict=True)
            by_note_id = {item["note_id"]: item for item in candidates}

            assert geoffrey_id not in by_note_id
            assert geography_id not in by_note_id
            assert by_note_id[standalone_geo_id]["reason_code"] == "geo"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_geo_cleanup_matches_chinese_adjacent_geo_phrases(tmp_path):
    SessionLocal = _override_database(tmp_path, "cleanup-candidates-geo-chinese-adjacent.db")
    try:
        user_id = _create_user(SessionLocal)
        optimize_id = _create_note_with_analysis(SessionLocal, user_id, note_id="geo-optimize", title="GEO优化怎么做", content="普通案例", score=9.0, subject="安装服务")
        related_id = _create_note_with_analysis(SessionLocal, user_id, note_id="geo-related", title="内容策略", content="GEO相关案例", score=9.0, subject="安装服务")
        poisoning_id = _create_note_with_analysis(SessionLocal, user_id, note_id="geo-poison", title="GEO投毒风险", content="普通案例", score=9.0, subject="安装服务")
        geoffrey_id = _create_note_with_analysis(SessionLocal, user_id, note_id="geoffrey-cn", title="Geoffrey 的 GEOgraphy 记录", content="普通案例", score=9.0, subject="安装服务")
        db = SessionLocal()
        try:
            candidates = build_current_cleanup_candidates(db, user_id=user_id, strict=True)
            by_note_id = {item["note_id"]: item for item in candidates}

            assert by_note_id[optimize_id]["reason_code"] == "geo"
            assert by_note_id[related_id]["reason_code"] == "geo"
            assert by_note_id[poisoning_id]["reason_code"] == "geo"
            assert geoffrey_id not in by_note_id
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_current_cleanup_candidates_endpoint_returns_shape_and_user_scope(tmp_path):
    SessionLocal = _override_database(tmp_path, "cleanup-candidates-endpoint-scope.db")
    try:
        owner_id = _create_user(SessionLocal, "cleanup-owner")
        other_id = _create_user(SessionLocal, "cleanup-other")
        owner_note_id = _create_note_with_analysis(SessionLocal, owner_id, note_id="owner-low", title="浴缸低分", score=2.0, subject="浴缸")
        other_note_id = _create_note_with_analysis(SessionLocal, other_id, note_id="other-low", title="浴缸低分", score=2.0, subject="浴缸")

        response = client.get("/api/notes/exclusions/current-cleanup-candidates", headers=_auth_headers(owner_id))

        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"items"}
        assert [item["note_id"] for item in body["items"]] == [owner_note_id]
        item = body["items"][0]
        assert {
            "note_id",
            "platform_note_id",
            "title",
            "score",
            "rating",
            "external_record_id",
            "reason_code",
            "reason_text",
        }.issubset(item)
        assert other_note_id not in [candidate["note_id"] for candidate in body["items"]]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_mark_notes_excluded_reports_feishu_update_outcomes(tmp_path):
    SessionLocal = _override_database(tmp_path, "mark-excluded-feishu.db")
    try:
        user_id = _create_user(SessionLocal)
        success_note_id = _create_note_with_analysis(SessionLocal, user_id, note_id="success", title="成功同步", external_record_id_marker="rec_success")
        missing_record_note_id = _create_note_with_analysis(SessionLocal, user_id, note_id="missing-record", title="缺少记录", external_record_id_marker="")
        missing_analysis_note_id = _create_note_without_analysis(SessionLocal, user_id, note_id="missing-analysis", title="缺少分析")
        failing_note_id = _create_note_with_analysis(SessionLocal, user_id, note_id="failing", title="同步失败", external_record_id_marker="rec_failing")
        client = RecordingFeishuClient(failing_record_id="rec_failing")
        db = SessionLocal()
        try:
            result = mark_notes_excluded(
                db,
                user_id=user_id,
                note_ids=[success_note_id, missing_record_note_id, missing_analysis_note_id, failing_note_id],
                reason_code="manual_excluded",
                reason_text="规格审查废弃",
                client=client,
            )

            success_analysis = db.scalar(select(NoteAnalysisResult).where(NoteAnalysisResult.note_id == success_note_id))
            missing_analysis = db.scalar(select(NoteAnalysisResult).where(NoteAnalysisResult.note_id == missing_analysis_note_id))
            failing_analysis = db.scalar(select(NoteAnalysisResult).where(NoteAnalysisResult.note_id == failing_note_id))
            assert result["excluded_count"] == 4
            assert result["feishu_updated_count"] == 1
            assert result["feishu_failed_count"] == 3
            assert client.updated_records == [
                (
                    "rec_success",
                    {
                        "分析状态": "已废弃",
                        "内容利用方式": ["废弃"],
                        "分析备注": "系统已废弃：规格审查废弃",
                    },
                )
            ]
            assert success_analysis.push_status == "synced"
            assert success_analysis.last_pushed_at is not None
            assert success_analysis.last_error == ""
            assert missing_analysis is not None
            assert missing_analysis.source == "feishu"
            assert missing_analysis.push_status == "failed"
            assert "缺少 external_record_id" in missing_analysis.last_error
            assert failing_analysis.push_status == "failed"
            assert "Feishu update failed" in failing_analysis.last_error
            assert {error["note_id"] for error in result["errors"]} == {missing_record_note_id, missing_analysis_note_id, failing_note_id}
            assert len([error for error in result["errors"] if "Feishu 同步未完成" in error["error"] and "external_record_id" in error["error"]]) == 2
            assert any(error.get("record_id") == "rec_failing" and "Feishu update failed" in error["error"] for error in result["errors"])
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_mark_notes_excluded_persists_failed_status_when_field_listing_fails(tmp_path):
    SessionLocal = _override_database(tmp_path, "mark-excluded-feishu-list-fields-failure.db")
    try:
        user_id = _create_user(SessionLocal)
        note_with_analysis_id = _create_note_with_analysis(SessionLocal, user_id, note_id="field-list-existing", title="已有分析", external_record_id_marker="rec_existing")
        note_without_analysis_id = _create_note_without_analysis(SessionLocal, user_id, note_id="field-list-missing", title="无分析")
        db = SessionLocal()
        try:
            result = mark_notes_excluded(
                db,
                user_id=user_id,
                note_ids=[note_with_analysis_id, note_without_analysis_id],
                reason_code="manual_excluded",
                reason_text="字段查询失败",
                client=FieldListFailingFeishuClient(),
            )

            existing_analysis = db.scalar(select(NoteAnalysisResult).where(NoteAnalysisResult.note_id == note_with_analysis_id))
            created_analysis = db.scalar(select(NoteAnalysisResult).where(NoteAnalysisResult.note_id == note_without_analysis_id))
            assert result["excluded_count"] == 2
            assert result["feishu_updated_count"] == 0
            assert result["feishu_failed_count"] == 2
            assert all(error.get("feishu_failed") is True and "list fields boom" in error["error"] for error in result["errors"])
            assert existing_analysis.push_status == "failed"
            assert "list fields boom" in existing_analysis.last_error
            assert created_analysis is not None
            assert created_analysis.source == "feishu"
            assert created_analysis.push_status == "failed"
            assert "list fields boom" in created_analysis.last_error
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_mark_notes_excluded_uses_aliases_for_remote_update_payload(tmp_path):
    SessionLocal = _override_database(tmp_path, "mark-excluded-feishu-alias.db")
    try:
        user_id = _create_user(SessionLocal)
        note_id = _create_note_with_analysis(SessionLocal, user_id, note_id="alias", title="别名同步", external_record_id_marker="rec_alias")
        client = RecordingFeishuClient(field_names=["分析状态确认", "复用价值", "分析备注"])
        db = SessionLocal()
        try:
            result = mark_notes_excluded(
                db,
                user_id=user_id,
                note_ids=[note_id],
                reason_code="manual_excluded",
                reason_text="别名字段废弃",
                client=client,
            )

            assert result["feishu_updated_count"] == 1
            assert client.list_fields_count == 1
            assert client.updated_records == [
                (
                    "rec_alias",
                    {
                        "分析状态确认": "已废弃",
                        "复用价值": ["废弃"],
                        "分析备注": "系统已废弃：别名字段废弃",
                    },
                )
            ]
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_mark_notes_excluded_fetches_remote_field_names_once_per_batch(tmp_path):
    SessionLocal = _override_database(tmp_path, "mark-excluded-feishu-field-names-once.db")
    try:
        user_id = _create_user(SessionLocal)
        first_id = _create_note_with_analysis(SessionLocal, user_id, note_id="field-once-1", title="同步 1", external_record_id_marker="rec_once_1")
        second_id = _create_note_with_analysis(SessionLocal, user_id, note_id="field-once-2", title="同步 2", external_record_id_marker="rec_once_2")
        client = RecordingFeishuClient(field_names=["分析状态确认", "复用价值", "分析备注"])
        db = SessionLocal()
        try:
            result = mark_notes_excluded(
                db,
                user_id=user_id,
                note_ids=[first_id, second_id],
                reason_code="manual_excluded",
                reason_text="批量字段别名",
                client=client,
            )

            assert result["feishu_updated_count"] == 2
            assert client.list_fields_count == 1
            assert [record_id for record_id, _fields in client.updated_records] == ["rec_once_1", "rec_once_2"]
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_mark_notes_excluded_commits_local_changes_before_remote_update(tmp_path):
    SessionLocal = _override_database(tmp_path, "mark-excluded-commit-before-remote.db")
    try:
        user_id = _create_user(SessionLocal)
        note_id = _create_note_with_analysis(SessionLocal, user_id, note_id="commit-order", title="提交顺序", external_record_id_marker="rec_commit")

        def assert_local_committed_before_remote_update(record_id, fields):
            verify_db = SessionLocal()
            try:
                assert verify_db.scalar(select(NoteExclusion).where(NoteExclusion.platform_note_id == "commit-order")) is not None
                persisted = verify_db.scalar(select(NoteAnalysisResult).where(NoteAnalysisResult.note_id == note_id))
                assert persisted.analysis_status == "已废弃"
                assert persisted.reuse_value == "废弃"
                assert persisted.push_status != "synced"
            finally:
                verify_db.close()

        client = RecordingFeishuClient(on_update=assert_local_committed_before_remote_update)
        db = SessionLocal()
        try:
            result = mark_notes_excluded(db, user_id=user_id, note_ids=[note_id], reason_code="manual_excluded", reason_text="提交顺序", client=client)

            assert result["feishu_updated_count"] == 1
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_notes_list_hides_excluded_notes_by_default(tmp_path):
    SessionLocal = _override_database(tmp_path, "hide-excluded.db")
    try:
        user_id = _create_user(SessionLocal)
        hidden_id = _create_note_with_analysis(SessionLocal, user_id, note_id="hidden-xhs", title="GEO 可以做什么", score=2.0, subject="")
        visible_id = _create_note_with_analysis(SessionLocal, user_id, note_id="visible-xhs", title="浴缸避坑指南", score=9.0, subject="浴缸")
        db = SessionLocal()
        try:
            mark_notes_excluded(db, user_id=user_id, note_ids=[hidden_id], reason_code="geo", reason_text="GEO相关", client=None)
        finally:
            db.close()

        response = client.get("/api/notes", headers=_auth_headers(user_id), params={"platform": "xhs", "page_size": 100})

        assert response.status_code == 200
        ids = [item["id"] for item in response.json()["items"]]
        assert visible_id in ids
        assert hidden_id not in ids
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_note_ids_hides_excluded_notes_by_default(tmp_path):
    SessionLocal = _override_database(tmp_path, "hide-excluded-ids.db")
    try:
        user_id = _create_user(SessionLocal)
        hidden_id = _create_note_with_analysis(SessionLocal, user_id, note_id="hidden-id-xhs", title="GEO 可以做什么", score=2.0, subject="")
        _create_note_with_analysis(SessionLocal, user_id, note_id="visible-id-xhs", title="浴缸避坑指南", score=9.0, subject="浴缸")
        db = SessionLocal()
        try:
            mark_notes_excluded(db, user_id=user_id, note_ids=[hidden_id], reason_code="geo", reason_text="GEO相关", client=None)
        finally:
            db.close()

        response = client.get("/api/notes/ids", headers=_auth_headers(user_id), params={"platform": "xhs"})

        assert response.status_code == 200
        assert response.json()["items"] == ["visible-id-xhs"]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_note_filter_options_hides_excluded_notes_by_default(tmp_path):
    SessionLocal = _override_database(tmp_path, "hide-excluded-filter-options.db")
    try:
        user_id = _create_user(SessionLocal)
        hidden_id = _create_note_with_analysis(
            SessionLocal,
            user_id,
            note_id="hidden-filter-xhs",
            title="GEO 可以做什么",
            score=2.0,
            subject="隐藏服务",
            status="隐藏状态",
        )
        _create_note_with_analysis(
            SessionLocal,
            user_id,
            note_id="visible-filter-xhs",
            title="浴缸避坑指南",
            score=9.0,
            subject="可见服务",
            status="可见状态",
        )
        db = SessionLocal()
        try:
            mark_notes_excluded(db, user_id=user_id, note_ids=[hidden_id], reason_code="geo", reason_text="GEO相关", client=None)
        finally:
            db.close()

        response = client.get("/api/notes/filter-options", headers=_auth_headers(user_id), params={"platform": "xhs"})

        assert response.status_code == 200
        body = response.json()
        assert body["analysisStatus"] == [{"label": "可见状态", "value": "可见状态"}]
        assert body["coreProductService"] == [{"label": "可见服务", "value": "可见服务"}]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_batch_save_skips_excluded_note_ids(tmp_path):
    SessionLocal = _override_database(tmp_path, "skip-import.db")
    try:
        user_id = _create_user(SessionLocal)
        db = SessionLocal()
        try:
            account = PlatformAccount(user_id=user_id, platform="xhs", nickname="pc", sub_type="pc")
            db.add(account)
            db.flush()
            note = Note(user_id=user_id, platform_account_id=account.id, platform="xhs", note_id="excluded-import", title="旧标题", content="旧内容", author_name="作者")
            db.add(note)
            db.flush()
            note_id = note.id
            db.add(NoteExclusion(user_id=user_id, note_id=note.id, platform="xhs", platform_note_id="excluded-import", reason_code="geo", reason_text="GEO相关"))
            db.commit()
            account_id = account.id
        finally:
            db.close()

        response = client.post(
            "/api/notes/batch-save",
            headers=_auth_headers(user_id),
            json={
                "account_id": account_id,
                "notes": [
                    {"note_id": "excluded-import", "title": "新标题不应写入", "content": "新内容", "author_name": "作者"},
                    {"note_id": "fresh-import", "title": "新素材", "content": "正文", "author_name": "作者"},
                ],
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["saved_count"] == 1
        assert body["skipped_count"] == 1
        assert body["skipped_items"] == [{"note_id": "excluded-import", "reason": "excluded"}]
        db = SessionLocal()
        try:
            old_note = db.get(Note, note_id)
            fresh_note = db.scalar(select(Note).where(Note.note_id == "fresh-import"))
            assert old_note.title == "旧标题"
            assert fresh_note is not None
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_xhs_crawl_save_normalized_notes_matches_existing_by_platform_and_note_id(tmp_path, monkeypatch):
    SessionLocal = _override_database(tmp_path, "crawl-save-platform-condition.db")
    try:
        user_id = _create_user(SessionLocal)
        downloaded_urls = []
        monkeypatch.setattr(xhs_crawl, "_download_asset", lambda url, user_id, asset_type: downloaded_urls.append(url) or f"local-{asset_type}")
        db = SessionLocal()
        try:
            wechat_account = PlatformAccount(user_id=user_id, platform="wechat_official", nickname="公众号", sub_type="official")
            xhs_account = PlatformAccount(user_id=user_id, platform="xhs", nickname="pc", sub_type="pc")
            db.add_all([wechat_account, xhs_account])
            db.flush()
            wechat_note = Note(
                user_id=user_id,
                platform_account_id=wechat_account.id,
                platform="wechat_official",
                note_id="same-crawl-note-id",
                title="公众号原标题",
                content="公众号原内容",
                author_name="公众号作者",
            )
            db.add(wechat_note)
            db.commit()
            wechat_note_id = wechat_note.id

            saved = xhs_crawl._save_normalized_notes(
                db,
                xhs_account,
                [{"note_id": "same-crawl-note-id", "title": "小红书标题", "content": "小红书内容", "author_name": "小红书作者"}],
            )

            assert [note.note_id for note in saved] == ["same-crawl-note-id"]
            old_note = db.get(Note, wechat_note_id)
            xhs_note = db.scalar(select(Note).where(Note.platform == "xhs", Note.note_id == "same-crawl-note-id"))
            assert old_note.title == "公众号原标题"
            assert old_note.content == "公众号原内容"
            assert xhs_note is not None
            assert xhs_note.id != old_note.id
            assert xhs_note.title == "小红书标题"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


class SearchOnlyExcludedAdapter:
    def search_note(self, keyword, page=1, **kwargs):
        return True, "ok", {
            "data": {
                "items": [
                    {
                        "note_card": {
                            "note_id": "crawl-search-excluded",
                            "display_title": "已废弃搜索结果",
                            "desc": "正文",
                            "user": {"nickname": "作者"},
                            "interact_info": {"liked_count": 9},
                            "image_list": [{"url": "https://img.example/excluded.png"}],
                        }
                    }
                ]
            }
        }


class UserNotesOnlyExcludedAdapter:
    def get_user_notes(self, user_url):
        return True, "ok", {
            "data": {
                "items": [
                    {
                        "note_card": {
                            "note_id": "crawl-user-excluded",
                            "display_title": "已废弃主页结果",
                            "desc": "正文",
                            "user": {"nickname": "作者"},
                            "interact_info": {"liked_count": 9},
                            "image_list": [{"url": "https://img.example/excluded.png"}],
                        }
                    }
                ]
            }
        }


class DetailOnlyExcludedSaveableAdapter:
    def get_note_info(self, url):
        return True, "ok", {
            "data": {
                "items": [
                    {
                        "note_card": {
                            "note_id": "crawl-url-excluded",
                            "display_title": "已废弃详情结果",
                            "desc": "正文",
                            "user": {"nickname": "作者"},
                            "interact_info": {"liked_count": 9},
                            "image_list": [{"url": "https://img.example/excluded.png"}],
                        }
                    }
                ]
            }
        }



def test_xhs_crawl_save_normalized_notes_skips_excluded_notes_before_upsert_and_assets(tmp_path, monkeypatch):
    SessionLocal = _override_database(tmp_path, "crawl-save-skip-excluded.db")
    try:
        user_id = _create_user(SessionLocal)
        downloaded_urls = []
        monkeypatch.setattr(xhs_crawl, "_download_asset", lambda url, user_id, asset_type: downloaded_urls.append(url) or f"local-{asset_type}")
        db = SessionLocal()
        try:
            account = PlatformAccount(user_id=user_id, platform="xhs", nickname="pc", sub_type="pc")
            db.add(account)
            db.flush()
            excluded_note = Note(
                user_id=user_id,
                platform_account_id=account.id,
                platform="xhs",
                note_id="crawl-excluded",
                title="旧标题",
                content="旧内容",
                author_name="旧作者",
            )
            db.add(excluded_note)
            db.flush()
            db.add(NoteAsset(note_id=excluded_note.id, asset_type="image", url="https://old.example/image.jpg", local_path="old-image"))
            db.add(
                NoteExclusion(
                    user_id=user_id,
                    note_id=excluded_note.id,
                    platform="xhs",
                    platform_note_id="crawl-excluded",
                    reason_code="manual_excluded",
                    reason_text="已废弃",
                )
            )
            db.commit()
            excluded_note_id = excluded_note.id

            saved = xhs_crawl._save_normalized_notes(
                db,
                account,
                [
                    {
                        "note_id": "crawl-excluded",
                        "title": "新标题不应写入",
                        "content": "新内容不应写入",
                        "author_name": "新作者",
                        "image_urls": ["https://new.example/excluded.jpg"],
                    },
                    {
                        "note_id": "crawl-fresh",
                        "title": "新素材",
                        "content": "正文",
                        "author_name": "作者",
                        "image_urls": ["https://new.example/fresh.jpg"],
                    },
                ],
            )

            assert [note.note_id for note in saved] == ["crawl-fresh"]
            old_note = db.get(Note, excluded_note_id)
            old_assets = db.scalars(select(NoteAsset).where(NoteAsset.note_id == excluded_note_id)).all()
            fresh_note = db.scalar(select(Note).where(Note.note_id == "crawl-fresh"))
            assert old_note.title == "旧标题"
            assert old_note.content == "旧内容"
            assert [(asset.url, asset.local_path) for asset in old_assets] == [("https://old.example/image.jpg", "old-image")]
            assert fresh_note is not None
            assert downloaded_urls == ["https://new.example/fresh.jpg"]
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_non_streaming_search_endpoint_reports_excluded_saveable_items(tmp_path, monkeypatch):
    SessionLocal = _override_database(tmp_path, "crawl-search-reports-excluded.db")
    app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: (lambda cookies: SearchOnlyExcludedAdapter())
    monkeypatch.setattr(xhs_crawl, "_get_owned_pc_account_cookies", lambda db, current_user, account_id: "cookie")
    try:
        user_id = _create_user(SessionLocal)
        db = SessionLocal()
        try:
            account = PlatformAccount(user_id=user_id, platform="xhs", nickname="pc", sub_type="pc")
            db.add(account)
            db.flush()
            account_id = account.id
            db.add(NoteExclusion(user_id=user_id, platform="xhs", platform_note_id="crawl-search-excluded", reason_code="manual_excluded", reason_text="已废弃"))
            db.commit()
        finally:
            db.close()

        response = client.post(
            "/api/xhs/crawl/search-notes",
            headers=_auth_headers(user_id),
            json={"account_id": account_id, "keyword": "浴缸"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["saved_count"] == 0
        assert body["skipped_low_quality_count"] == 1
        assert body["skipped_items"][0]["note_id"] == "crawl-search-excluded"
        assert body["skipped_items"][0]["reason"] == "excluded"
        assert body["skipped_items"][0]["save_diagnostic_kind"] == "excluded_note"
    finally:
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)
        app.dependency_overrides.pop(get_db, None)


def test_non_streaming_note_urls_endpoint_reports_excluded_saveable_items(tmp_path, monkeypatch):
    SessionLocal = _override_database(tmp_path, "crawl-note-url-reports-excluded.db")
    app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: (lambda cookies: DetailOnlyExcludedSaveableAdapter())
    monkeypatch.setattr(xhs_crawl, "_get_owned_pc_account_cookies", lambda db, current_user, account_id: "cookie")
    try:
        user_id = _create_user(SessionLocal)
        db = SessionLocal()
        try:
            account = PlatformAccount(user_id=user_id, platform="xhs", nickname="pc", sub_type="pc")
            db.add(account)
            db.flush()
            account_id = account.id
            db.add(NoteExclusion(user_id=user_id, platform="xhs", platform_note_id="crawl-url-excluded", reason_code="manual_excluded", reason_text="已废弃"))
            db.commit()
        finally:
            db.close()

        response = client.post(
            "/api/xhs/crawl/note-urls",
            headers=_auth_headers(user_id),
            json={"account_id": account_id, "urls": ["https://www.xiaohongshu.com/explore/crawl-url-excluded?xsec_token=token"]},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["saved_count"] == 0
        assert body["skipped_low_quality_count"] == 1
        assert body["skipped_items"][0]["note_id"] == "crawl-url-excluded"
        assert body["skipped_items"][0]["reason"] == "excluded"
        assert body["skipped_items"][0]["save_diagnostic_kind"] == "excluded_note"
    finally:
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)
        app.dependency_overrides.pop(get_db, None)


def test_non_streaming_user_notes_endpoint_reports_excluded_saveable_items(tmp_path, monkeypatch):
    SessionLocal = _override_database(tmp_path, "crawl-user-reports-excluded.db")
    app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: (lambda cookies: UserNotesOnlyExcludedAdapter())
    monkeypatch.setattr(xhs_crawl, "_get_owned_pc_account_cookies", lambda db, current_user, account_id: "cookie")
    try:
        user_id = _create_user(SessionLocal)
        db = SessionLocal()
        try:
            account = PlatformAccount(user_id=user_id, platform="xhs", nickname="pc", sub_type="pc")
            db.add(account)
            db.flush()
            account_id = account.id
            db.add(NoteExclusion(user_id=user_id, platform="xhs", platform_note_id="crawl-user-excluded", reason_code="manual_excluded", reason_text="已废弃"))
            db.commit()
        finally:
            db.close()

        response = client.post(
            "/api/xhs/crawl/user-notes",
            headers=_auth_headers(user_id),
            json={"account_id": account_id, "user_url": "https://www.xiaohongshu.com/user/profile/demo"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["saved_count"] == 0
        assert body["skipped_low_quality_count"] == 1
        assert body["skipped_items"][0]["note_id"] == "crawl-user-excluded"
        assert body["skipped_items"][0]["reason"] == "excluded"
        assert body["skipped_items"][0]["save_diagnostic_kind"] == "excluded_note"
    finally:
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)
        app.dependency_overrides.pop(get_db, None)


class ShouldNotFetchCommentsAdapter:
    def __init__(self, cookies):
        raise AssertionError("comment adapter should not be initialized for fully excluded batch")


class DetailOnlyAdapter:
    def get_note_info(self, url):
        return True, "", {"url": url}

    def get_note_comments(self, url):
        raise AssertionError("comment request should be skipped for excluded notes")


class CommentsOnlyExcludedAdapter:
    def get_note_comments(self, url):
        raise AssertionError("direct comments mode should skip excluded URL before comment request")


def test_streaming_comments_mode_skips_excluded_url_before_fetching_comments(tmp_path, monkeypatch):
    SessionLocal = _override_database(tmp_path, "crawl-comments-mode-skip-excluded-url.db")
    app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: (lambda cookies: CommentsOnlyExcludedAdapter())
    try:
        user_id = _create_user(SessionLocal)
        db = SessionLocal()
        try:
            account = PlatformAccount(user_id=user_id, platform="xhs", nickname="pc", sub_type="pc")
            db.add(account)
            db.flush()
            account_id = account.id
            db.add(
                NoteExclusion(
                    user_id=user_id,
                    platform="xhs",
                    platform_note_id="comments-excluded",
                    reason_code="manual_excluded",
                    reason_text="已废弃",
                )
            )
            db.commit()
        finally:
            db.close()

        monkeypatch.setattr(xhs_crawl, "_get_owned_pc_account_cookies", lambda db, current_user, account_id: "cookie")
        response = client.post(
            "/api/xhs/crawl/data",
            headers=_auth_headers(user_id),
            json={
                "account_id": account_id,
                "mode": "comments",
                "urls": ["https://www.xiaohongshu.com/explore/comments-excluded?xsec_token=token"],
                "fetch_comments": False,
                "save_to_library": False,
            },
        )

        assert response.status_code == 200
        body = response.text
        assert "direct comments mode should skip" not in body
        assert '"status": "partial"' in body
        assert '"comment_status": "skipped_excluded"' in body
        assert '"comment_error": "该笔记已标记废弃，本轮跳过评论抓取和保存。"' in body
    finally:
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)
        app.dependency_overrides.pop(get_db, None)


def test_streaming_data_crawl_skips_comments_for_excluded_note(tmp_path, monkeypatch):
    SessionLocal = _override_database(tmp_path, "crawl-streaming-skip-excluded-comments.db")
    app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: (lambda cookies: DetailOnlyAdapter())
    try:
        user_id = _create_user(SessionLocal)
        db = SessionLocal()
        try:
            account = PlatformAccount(user_id=user_id, platform="xhs", nickname="pc", sub_type="pc")
            db.add(account)
            db.flush()
            account_id = account.id
            db.add(
                NoteExclusion(
                    user_id=user_id,
                    platform="xhs",
                    platform_note_id="stream-excluded",
                    reason_code="manual_excluded",
                    reason_text="已废弃",
                )
            )
            db.commit()
        finally:
            db.close()

        monkeypatch.setattr(xhs_crawl, "_get_owned_pc_account_cookies", lambda db, current_user, account_id: "cookie")
        monkeypatch.setattr(xhs_crawl, "_normalize_detail_payload", lambda raw, source_url="": {"note_id": "stream-excluded", "title": "已废弃", "content": "正文", "author_name": "作者", "note_url": source_url, "raw": raw})
        monkeypatch.setattr(xhs_crawl, "evaluate_detail_quality", lambda note, raw: {"can_save": True, "quality_status": "ok", "diagnostic_kind": None, "recoverable": False, "user_message": ""})

        response = client.post(
            "/api/xhs/crawl/data",
            headers=_auth_headers(user_id),
            json={
                "account_id": account_id,
                "mode": "note_urls",
                "urls": ["https://xhs.example/excluded"],
                "fetch_comments": True,
                "save_to_library": True,
            },
        )

        assert response.status_code == 200
        body = response.text
        assert "comment request should be skipped" not in body
        assert '"saved_count": 0' in body
        assert '"skipped_count": 1' in body
        assert '"comment_status": "skipped_excluded"' in body
    finally:
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)
        app.dependency_overrides.pop(get_db, None)


def test_batch_save_all_excluded_with_fetch_comments_skips_before_cookie_lookup(tmp_path):
    SessionLocal = _override_database(tmp_path, "skip-all-fetch-comments.db")
    app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: ShouldNotFetchCommentsAdapter
    try:
        user_id = _create_user(SessionLocal)
        db = SessionLocal()
        try:
            account = PlatformAccount(user_id=user_id, platform="xhs", nickname="pc-no-cookie", sub_type="pc")
            db.add(account)
            db.flush()
            account_id = account.id
            db.add(
                NoteExclusion(
                    user_id=user_id,
                    platform="xhs",
                    platform_note_id="excluded-one",
                    reason_code="manual_excluded",
                    reason_text="已废弃",
                )
            )
            db.add(
                NoteExclusion(
                    user_id=user_id,
                    platform="xhs",
                    platform_note_id="excluded-two",
                    reason_code="manual_excluded",
                    reason_text="已废弃",
                )
            )
            db.commit()
        finally:
            db.close()

        response = client.post(
            "/api/notes/batch-save",
            headers=_auth_headers(user_id),
            json={
                "account_id": account_id,
                "fetch_comments": True,
                "notes": [
                    {"note_id": "excluded-one", "title": "不应保存", "note_url": "https://xhs.example/1"},
                    {"note_id": "excluded-two", "title": "不应保存", "note_url": "https://xhs.example/2"},
                ],
            },
        )

        assert response.status_code == 200
        assert response.json()["saved_count"] == 0
        assert response.json()["skipped_count"] == 2
        assert response.json()["skipped_items"] == [
            {"note_id": "excluded-one", "reason": "excluded"},
            {"note_id": "excluded-two", "reason": "excluded"},
        ]
        assert response.json()["items"] == []
    finally:
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)
        app.dependency_overrides.pop(get_db, None)


def test_batch_save_checks_excluded_note_ids_in_one_query(tmp_path):
    SessionLocal, engine = _override_database(tmp_path, "skip-import-one-query.db", return_engine=True)
    try:
        user_id = _create_user(SessionLocal)
        db = SessionLocal()
        try:
            account = PlatformAccount(user_id=user_id, platform="xhs", nickname="pc", sub_type="pc")
            db.add(account)
            db.flush()
            account_id = account.id
            db.add(
                NoteExclusion(
                    user_id=user_id,
                    platform="xhs",
                    platform_note_id="excluded-import",
                    reason_code="manual_excluded",
                    reason_text="已废弃",
                )
            )
            db.commit()
        finally:
            db.close()

        exclusion_selects = []

        def record_exclusion_select(conn, cursor, statement, parameters, context, executemany):
            if "FROM note_exclusions" in statement and statement.lstrip().upper().startswith("SELECT"):
                exclusion_selects.append(statement)

        event.listen(engine, "before_cursor_execute", record_exclusion_select)
        try:
            response = client.post(
                "/api/notes/batch-save",
                headers=_auth_headers(user_id),
                json={
                    "account_id": account_id,
                    "notes": [
                        {"note_id": "excluded-import", "title": "不应保存"},
                        {"note_id": "fresh-import-a", "title": "新素材 A"},
                        {"note_id": "fresh-import-b", "title": "新素材 B"},
                    ],
                },
            )
        finally:
            event.remove(engine, "before_cursor_execute", record_exclusion_select)

        assert response.status_code == 200
        assert response.json()["saved_count"] == 2
        assert response.json()["skipped_count"] == 1
        assert len(exclusion_selects) == 1
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_batch_save_deduplicates_note_ids_before_exclusion_query(tmp_path):
    SessionLocal, engine = _override_database(tmp_path, "skip-import-dedupe-query.db", return_engine=True)
    try:
        user_id = _create_user(SessionLocal)
        db = SessionLocal()
        try:
            account = PlatformAccount(user_id=user_id, platform="xhs", nickname="pc", sub_type="pc")
            db.add(account)
            db.flush()
            account_id = account.id
            db.add(
                NoteExclusion(
                    user_id=user_id,
                    platform="xhs",
                    platform_note_id="duplicate-import",
                    reason_code="manual_excluded",
                    reason_text="已废弃",
                )
            )
            db.commit()
        finally:
            db.close()

        exclusion_parameters = []

        def record_exclusion_select(conn, cursor, statement, parameters, context, executemany):
            if "FROM note_exclusions" in statement and statement.lstrip().upper().startswith("SELECT"):
                exclusion_parameters.append(parameters)

        event.listen(engine, "before_cursor_execute", record_exclusion_select)
        try:
            response = client.post(
                "/api/notes/batch-save",
                headers=_auth_headers(user_id),
                json={
                    "account_id": account_id,
                    "notes": [
                        {"note_id": "duplicate-import", "title": "不应保存 1"},
                        {"note_id": "duplicate-import", "title": "不应保存 2"},
                        {"note_id": "fresh-dedupe", "title": "新素材"},
                        {"note_id": "fresh-dedupe", "title": "新素材重复"},
                    ],
                },
            )
        finally:
            event.remove(engine, "before_cursor_execute", record_exclusion_select)

        assert response.status_code == 200
        assert response.json()["saved_count"] == 2
        assert response.json()["skipped_count"] == 2
        assert len(exclusion_parameters) == 1
        bound_values = list(exclusion_parameters[0])
        assert bound_values.count("duplicate-import") == 1
        assert bound_values.count("fresh-dedupe") == 1
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_batch_save_matches_existing_note_by_platform_and_note_id(tmp_path):
    SessionLocal = _override_database(tmp_path, "cross-platform-note-id.db")
    try:
        user_id = _create_user(SessionLocal)
        db = SessionLocal()
        try:
            wechat_account = PlatformAccount(user_id=user_id, platform="wechat_official", nickname="公众号", sub_type="official")
            xhs_account = PlatformAccount(user_id=user_id, platform="xhs", nickname="pc", sub_type="pc")
            db.add_all([wechat_account, xhs_account])
            db.flush()
            wechat_note = Note(
                user_id=user_id,
                platform_account_id=wechat_account.id,
                platform="wechat_official",
                note_id="same-platform-note-id",
                title="公众号原标题",
                content="公众号原内容",
                author_name="公众号作者",
            )
            db.add(wechat_note)
            db.commit()
            wechat_note_id = wechat_note.id
            xhs_account_id = xhs_account.id
        finally:
            db.close()

        response = client.post(
            "/api/notes/batch-save",
            headers=_auth_headers(user_id),
            json={
                "account_id": xhs_account_id,
                "notes": [
                    {"note_id": "same-platform-note-id", "title": "小红书标题", "content": "小红书内容", "author_name": "小红书作者"},
                ],
            },
        )

        assert response.status_code == 200
        assert response.json()["saved_count"] == 1
        db = SessionLocal()
        try:
            wechat_note = db.get(Note, wechat_note_id)
            xhs_note = db.scalar(select(Note).where(Note.platform == "xhs", Note.note_id == "same-platform-note-id"))
            assert wechat_note.title == "公众号原标题"
            assert wechat_note.content == "公众号原内容"
            assert xhs_note is not None
            assert xhs_note.id != wechat_note.id
            assert xhs_note.title == "小红书标题"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_mark_exclusions_endpoint_marks_notes_and_hides_them(tmp_path):
    SessionLocal = _override_database(tmp_path, "endpoint-mark.db")
    try:
        user_id = _create_user(SessionLocal)
        note_id = _create_note_with_analysis(SessionLocal, user_id, note_id="endpoint-xhs", title="小户型浴缸低分", score=2.0, rating="低表现内容", subject="浴缸")

        response = client.post(
            "/api/notes/exclusions/mark",
            headers=_auth_headers(user_id),
            json={"note_ids": [note_id], "reason_code": "low_score_bathtub", "reason_text": "浴缸低分", "sync_feishu": False},
        )

        assert response.status_code == 200
        assert response.json()["excluded_count"] == 1
        db = SessionLocal()
        try:
            exclusion = db.scalar(select(NoteExclusion).where(NoteExclusion.note_id == note_id))
            analysis = db.scalar(select(NoteAnalysisResult).where(NoteAnalysisResult.note_id == note_id))
            assert exclusion.reason_code == "low_score_bathtub"
            assert analysis.analysis_status == "已废弃"
            assert analysis.reuse_value == "废弃"
        finally:
            db.close()

        list_response = client.get("/api/notes", headers=_auth_headers(user_id), params={"platform": "xhs", "page_size": 100})
        assert note_id not in [item["id"] for item in list_response.json()["items"]]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_mark_exclusions_endpoint_rejects_non_xhs_notes(tmp_path):
    SessionLocal = _override_database(tmp_path, "endpoint-mark-non-xhs.db")
    try:
        user_id = _create_user(SessionLocal)
        db = SessionLocal()
        try:
            account = PlatformAccount(user_id=user_id, platform="wechat_official", nickname="公众号", sub_type="official")
            db.add(account)
            db.flush()
            note = Note(
                user_id=user_id,
                platform_account_id=account.id,
                platform="wechat_official",
                note_id="wechat-note",
                title="公众号素材",
                content="正文",
                author_name="作者",
            )
            db.add(note)
            db.commit()
            note_id = note.id
        finally:
            db.close()

        response = client.post(
            "/api/notes/exclusions/mark",
            headers=_auth_headers(user_id),
            json={"note_ids": [note_id], "reason_code": "manual_excluded", "reason_text": "不应废弃非小红书", "sync_feishu": False},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["excluded_count"] == 0
        assert body["skipped_count"] == 1
        assert body["errors"] == [{"note_id": note_id, "error": "Only xhs notes can be excluded by this endpoint"}]
        db = SessionLocal()
        try:
            assert db.scalar(select(NoteExclusion).where(NoteExclusion.note_id == note_id)) is None
            assert db.get(Note, note_id).title == "公众号素材"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_mark_exclusions_endpoint_sync_feishu_client_failure_still_marks_local(tmp_path, monkeypatch):
    SessionLocal = _override_database(tmp_path, "endpoint-mark-sync-feishu-client-failure.db")
    try:
        user_id = _create_user(SessionLocal)
        note_id = _create_note_with_analysis(SessionLocal, user_id, note_id="endpoint-client-failure", title="本地仍应废弃", external_record_id_marker="rec_client_failure")

        from backend.app.api import feishu_integration

        monkeypatch.setattr(feishu_integration, "_get_config", lambda db, config_user_id: {"user_id": config_user_id})

        def fail_client(config):
            raise RuntimeError("client boom")

        monkeypatch.setattr(feishu_integration, "_client_or_error", fail_client)

        response = client.post(
            "/api/notes/exclusions/mark",
            headers=_auth_headers(user_id),
            json={"note_ids": [note_id], "reason_code": "manual_excluded", "reason_text": "客户端失败", "sync_feishu": True},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["excluded_count"] == 1
        assert body["feishu_updated_count"] == 0
        assert body["feishu_failed_count"] >= 1
        assert any(error.get("feishu_failed") is True and "Feishu client error" in error["error"] and "client boom" in error["error"] for error in body["errors"])

        db = SessionLocal()
        try:
            exclusion = db.scalar(select(NoteExclusion).where(NoteExclusion.note_id == note_id))
            analysis = db.scalar(select(NoteAnalysisResult).where(NoteAnalysisResult.note_id == note_id))
            assert exclusion is not None
            assert exclusion.reason_text == "客户端失败"
            assert analysis.analysis_status == "已废弃"
            assert analysis.reuse_value == "废弃"
            assert analysis.push_status == "failed"
            assert "Feishu client error" in analysis.last_error
            assert "client boom" in analysis.last_error
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)



def test_feishu_push_dry_run_skips_excluded_selected_note_without_preanalysis(tmp_path, monkeypatch):
    SessionLocal = _override_database(tmp_path, "feishu-push-dry-run-skip-excluded.db")
    try:
        user_id = _create_user(SessionLocal)
        note_id = _create_note_with_analysis(SessionLocal, user_id, note_id="push-dry-excluded", title="已废弃", subject="旧主题")
        db = SessionLocal()
        try:
            mark_notes_excluded(db, user_id=user_id, note_ids=[note_id], reason_code="manual_excluded", reason_text="已废弃", client=None)
        finally:
            db.close()

        def fail_preanalysis(*args, **kwargs):
            raise AssertionError("excluded note should not be preanalyzed")

        monkeypatch.setattr(feishu_bitable_service, "preanalyze_note_for_feishu", fail_preanalysis)
        db = SessionLocal()
        try:
            result = feishu_bitable_service.push_notes_to_feishu_dry_run(db, user_id=user_id, note_ids=[note_id])

            assert result["updated_count"] == 0
            assert result["failed_count"] == 0
            assert result["records"] == [{"note_id": note_id, "status": "skipped", "reason": "excluded"}]
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_feishu_push_skips_excluded_selected_note_without_remote_write(tmp_path, monkeypatch):
    SessionLocal = _override_database(tmp_path, "feishu-push-skip-excluded.db")
    try:
        user_id = _create_user(SessionLocal)
        note_id = _create_note_with_analysis(SessionLocal, user_id, note_id="push-excluded", title="已废弃", subject="旧主题")
        db = SessionLocal()
        try:
            mark_notes_excluded(db, user_id=user_id, note_ids=[note_id], reason_code="manual_excluded", reason_text="已废弃", client=None)
        finally:
            db.close()

        def fail_preanalysis(*args, **kwargs):
            raise AssertionError("excluded note should not be preanalyzed")

        monkeypatch.setattr(feishu_bitable_service, "preanalyze_note_for_feishu", fail_preanalysis)
        fake = MinimalFeishuPushClient()
        db = SessionLocal()
        try:
            result = feishu_bitable_service.push_notes_to_feishu(db, user_id=user_id, note_ids=[note_id], client=fake)

            assert result["created_count"] == 0
            assert result["updated_count"] == 0
            assert result["failed_count"] == 0
            assert result["records"] == [{"note_id": note_id, "status": "skipped", "reason": "excluded"}]
            assert fake.created_records == []
            assert fake.updated_records == []
            assert fake.uploaded == []
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_feishu_push_dry_run_skips_tombstone_exclusion_without_note_id(tmp_path, monkeypatch):
    SessionLocal = _override_database(tmp_path, "feishu-push-dry-run-skip-tombstone.db")
    try:
        user_id = _create_user(SessionLocal)
        note_id = _create_note_with_analysis(SessionLocal, user_id, note_id="push-dry-tombstone", title="已废弃", subject="旧主题")
        db = SessionLocal()
        try:
            db.add(NoteExclusion(user_id=user_id, note_id=None, platform="xhs", platform_note_id="push-dry-tombstone", reason_code="manual_excluded", reason_text="已废弃"))
            db.commit()
        finally:
            db.close()

        def fail_preanalysis(*args, **kwargs):
            raise AssertionError("tombstone-excluded note should not be preanalyzed")

        monkeypatch.setattr(feishu_bitable_service, "preanalyze_note_for_feishu", fail_preanalysis)
        db = SessionLocal()
        try:
            result = feishu_bitable_service.push_notes_to_feishu_dry_run(db, user_id=user_id, note_ids=[note_id])

            assert result["updated_count"] == 0
            assert result["failed_count"] == 0
            assert result["records"] == [{"note_id": note_id, "status": "skipped", "reason": "excluded"}]
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_feishu_push_skips_tombstone_exclusion_without_note_id(tmp_path, monkeypatch):
    SessionLocal = _override_database(tmp_path, "feishu-push-skip-tombstone.db")
    try:
        user_id = _create_user(SessionLocal)
        note_id = _create_note_with_analysis(SessionLocal, user_id, note_id="push-tombstone", title="已废弃", subject="旧主题")
        db = SessionLocal()
        try:
            db.add(NoteExclusion(user_id=user_id, note_id=None, platform="xhs", platform_note_id="push-tombstone", reason_code="manual_excluded", reason_text="已废弃"))
            db.commit()
        finally:
            db.close()

        def fail_preanalysis(*args, **kwargs):
            raise AssertionError("tombstone-excluded note should not be preanalyzed")

        monkeypatch.setattr(feishu_bitable_service, "preanalyze_note_for_feishu", fail_preanalysis)
        fake = MinimalFeishuPushClient()
        db = SessionLocal()
        try:
            result = feishu_bitable_service.push_notes_to_feishu(db, user_id=user_id, note_ids=[note_id], client=fake)

            assert result["created_count"] == 0
            assert result["updated_count"] == 0
            assert result["failed_count"] == 0
            assert result["records"] == [{"note_id": note_id, "status": "skipped", "reason": "excluded"}]
            assert fake.created_records == []
            assert fake.updated_records == []
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_feishu_push_all_endpoint_excludes_tombstone_before_batching(tmp_path, monkeypatch):
    SessionLocal = _override_database(tmp_path, "feishu-push-all-skip-tombstone.db")
    calls = []

    def fake_push(db, *, user_id, note_ids, client=None, overwrite_existing=False):
        calls.append(list(note_ids))
        return {
            "dry_run": True,
            "updated_count": len(note_ids),
            "failed_count": 0,
            "errors": [],
            "records": [{"note_id": note_id, "status": "dry_run"} for note_id in note_ids],
        }

    monkeypatch.setattr("backend.app.api.feishu_integration.push_notes_to_feishu_dry_run", fake_push)
    try:
        user_id = _create_user(SessionLocal)
        visible_id = _create_note_with_analysis(SessionLocal, user_id, note_id="push-all-tombstone-visible", title="可同步")
        _excluded_id = _create_note_with_analysis(SessionLocal, user_id, note_id="push-all-tombstone-excluded", title="已废弃")
        db = SessionLocal()
        try:
            db.add(NoteExclusion(user_id=user_id, note_id=None, platform="xhs", platform_note_id="push-all-tombstone-excluded", reason_code="manual_excluded", reason_text="已废弃"))
            db.commit()
        finally:
            db.close()

        response = client.post("/api/integrations/feishu/xhs-notes/push-all", headers=_auth_headers(user_id), json={"dry_run": True, "batch_size": 10})

        assert response.status_code == 200
        assert response.json()["total_count"] == 1
        assert calls == [[visible_id]]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_feishu_push_all_endpoint_excludes_marked_notes_before_batching(tmp_path, monkeypatch):
    SessionLocal = _override_database(tmp_path, "feishu-push-all-skip-excluded.db")
    calls = []

    def fake_push(db, *, user_id, note_ids, client=None, overwrite_existing=False):
        calls.append(list(note_ids))
        return {
            "dry_run": True,
            "updated_count": len(note_ids),
            "failed_count": 0,
            "errors": [],
            "records": [{"note_id": note_id, "status": "dry_run"} for note_id in note_ids],
        }

    monkeypatch.setattr("backend.app.api.feishu_integration.push_notes_to_feishu_dry_run", fake_push)
    try:
        user_id = _create_user(SessionLocal)
        visible_id = _create_note_with_analysis(SessionLocal, user_id, note_id="push-all-visible", title="可同步")
        excluded_id = _create_note_with_analysis(SessionLocal, user_id, note_id="push-all-excluded", title="已废弃")
        db = SessionLocal()
        try:
            mark_notes_excluded(db, user_id=user_id, note_ids=[excluded_id], reason_code="manual_excluded", reason_text="已废弃", client=None)
        finally:
            db.close()

        response = client.post("/api/integrations/feishu/xhs-notes/push-all", headers=_auth_headers(user_id), json={"dry_run": True, "batch_size": 10})

        assert response.status_code == 200
        assert response.json()["total_count"] == 1
        assert calls == [[visible_id]]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_feishu_pull_skips_excluded_note_without_overwriting_local_analysis(tmp_path):
    SessionLocal = _override_database(tmp_path, "feishu-pull-skip-excluded.db")
    try:
        user_id = _create_user(SessionLocal)
        note_id = _create_note_with_analysis(SessionLocal, user_id, note_id="pull-excluded", title="已废弃", subject="本地主题", status="已废弃")
        db = SessionLocal()
        try:
            mark_notes_excluded(db, user_id=user_id, note_ids=[note_id], reason_code="manual_excluded", reason_text="已废弃", client=None)
            result = feishu_bitable_service.pull_feishu_analysis_records(
                db,
                user_id=user_id,
                records=[{"record_id": "rec_remote", "fields": {"系统笔记ID": str(note_id), "分析状态": "已完成", "核心产品/服务": "远程主题", "内容利用方式": "标题参考"}}],
                note_ids=[note_id],
            )
            analysis = db.scalar(select(NoteAnalysisResult).where(NoteAnalysisResult.note_id == note_id))

            assert result["updated_count"] == 0
            assert result["skipped_count"] == 1
            assert analysis.analysis_status == "已废弃"
            assert analysis.subject_object == "本地主题"
            assert analysis.reuse_value == "废弃"
            assert analysis.external_record_id == "rec_pull-excluded"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_mark_exclusions_endpoint_syncs_feishu_when_requested(tmp_path, monkeypatch):
    SessionLocal = _override_database(tmp_path, "endpoint-mark-sync-feishu.db")
    try:
        user_id = _create_user(SessionLocal)
        note_id = _create_note_with_analysis(SessionLocal, user_id, note_id="endpoint-sync", title="人工废弃", external_record_id_marker="rec_endpoint_sync")
        feishu_client = RecordingFeishuClient()

        from backend.app.api import feishu_integration

        monkeypatch.setattr(feishu_integration, "_get_config", lambda db, config_user_id: {"user_id": config_user_id})
        monkeypatch.setattr(feishu_integration, "_client_or_error", lambda config: feishu_client)

        response = client.post(
            "/api/notes/exclusions/mark",
            headers=_auth_headers(user_id),
            json={"note_ids": [note_id], "reason_code": "manual_excluded", "reason_text": "同步废弃", "sync_feishu": True},
        )

        assert response.status_code == 200
        assert response.json()["feishu_updated_count"] == 1
        assert feishu_client.updated_records == [
            (
                "rec_endpoint_sync",
                {
                    "分析状态": "已废弃",
                    "内容利用方式": ["废弃"],
                    "分析备注": "系统已废弃：同步废弃",
                },
            )
        ]
    finally:
        app.dependency_overrides.pop(get_db, None)

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.database import get_db
from backend.app.main import app

from backend.app.core.database import Base
from backend.app.core.security import encrypt_text
from backend.app.models.ai import AiDraft, ModelConfig
from backend.app.models.analysis_report import AnalysisReport
from backend.app.models.keyword_group import KeywordGroup
from backend.app.models.note_exclusion import NoteExclusion
from backend.app.models.usage_quota import UsageLedger
from backend.app.models.user import User
from backend.app.services.usage_quota_service import UsageQuotaService, get_or_create_default_tenant_context
from backend.app.services.xhs_analysis_center_service import AnalysisValidationError, XhsAnalysisCenterService


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'xhs-analysis-center-test.db'}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


_api_testing_session_local = None


@pytest.fixture
def client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'xhs-analysis-center-api-test.db'}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    global _api_testing_session_local
    _api_testing_session_local = TestingSessionLocal
    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        _api_testing_session_local = None
        Base.metadata.drop_all(bind=engine)


def _create_user(db: Session, username: str = "analysis-user") -> User:
    user = User(username=username, password_hash="hashed")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _create_keyword_group(db: Session, user_id: int, keywords: list[str]):
    from backend.app.models.keyword_group import KeywordGroup

    group = KeywordGroup(user_id=user_id, platform="xhs", name="AI 编程", keywords=keywords)
    db.add(group)
    db.commit()
    db.refresh(group)
    return group


def _register_and_get_access_token(client: TestClient, username: str = "operator") -> str:
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": "secret123"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _with_api_db(action):
    assert _api_testing_session_local is not None
    db = _api_testing_session_local()
    try:
        return action(db)
    finally:
        db.close()


def _seed_keyword_group_via_db(username: str) -> int:
    def action(db: Session) -> int:
        user = db.scalar(select(User).where(User.username == username))
        assert user is not None
        group = _create_keyword_group(db, user.id, ["Claude Code", "AI编程"])
        _create_note_with_comments(db, user.id, title="少量样本", content="Claude Code 入门", comments=["怎么配置？"])
        return group.id

    return _with_api_db(action)


def _seed_minimum_keyword_group_via_db(username: str) -> int:
    def action(db: Session) -> int:
        user = db.scalar(select(User).where(User.username == username))
        assert user is not None
        group = _create_keyword_group(db, user.id, ["Claude Code", "AI编程", "Cursor"])
        for index in range(10):
            _create_note_with_comments(
                db,
                user.id,
                title=f"Claude Code 入门 {index}",
                content="Claude Code Cursor AI编程 入门配置",
                comments=[f"新手怎么配置 {index}-{item}？" for item in range(3)],
                raw_json={"liked_count": 70, "collected_count": 30, "comment_count": 3, "share_count": 5},
            )
        return group.id

    return _with_api_db(action)


def _seed_report_via_db(username: str, *, title: str = "失败报告") -> int:
    def action(db: Session) -> int:
        user = db.scalar(select(User).where(User.username == username))
        assert user is not None
        report = AnalysisReport(
            user_id=user.id,
            platform="xhs",
            report_type="content_analysis",
            status="failed",
            title=title,
            input_config={"keyword_group_id": 1, "excluded_note_ids": []},
            data_health={"status": "insufficient", "can_generate": False},
            evidence_pool={"notes": [], "comments": [], "keywords": [], "metrics": [], "benchmarks": []},
            html_file_path="",
            error_message="数据低于最低门槛，未调用模型",
        )
        db.add(report)
        db.commit()
        db.refresh(report)
        return report.id

    return _with_api_db(action)


def _seed_failed_report_via_db(username: str) -> int:
    return _seed_report_via_db(username)


def _create_text_model_config_via_db(username: str) -> int:
    def action(db: Session) -> int:
        user = db.scalar(select(User).where(User.username == username))
        assert user is not None
        config = ModelConfig(
            user_id=user.id,
            name="Default Text",
            model_type="text",
            provider="openai-compatible",
            model_name="gpt-analysis-quota-test",
            base_url="https://api.example.test/v1",
            encrypted_api_key=encrypt_text("sk-analysis-secret"),
            is_default=True,
        )
        db.add(config)
        db.commit()
        db.refresh(config)
        return config.id

    return _with_api_db(action)


class FakeApiJsonAiClient:
    def __init__(self, response: str = "{}"):
        self.response = response
        self.calls = 0

    def complete_json_prompt(self, **kwargs):
        self.calls += 1
        return self.response


class TrapApiJsonAiClient:
    called = False

    def complete_json_prompt(self, **kwargs):
        self.called = True
        raise AssertionError("provider must not be called when analysis_report quota is exhausted")


def _create_note_with_comments(
    db: Session,
    user_id: int,
    title: str,
    content: str,
    comments: list[str],
    raw_json: dict | None = None,
):
    from backend.app.models.note import Note, NoteComment

    note = Note(
        user_id=user_id,
        platform_account_id=1,
        platform="xhs",
        note_id=f"note-{user_id}-{title}",
        title=title,
        content=content,
        author_name="测试作者",
        raw_json=raw_json or {"liked_count": 1, "collected_count": 1, "comment_count": len(comments), "share_count": 0},
    )
    db.add(note)
    db.commit()
    db.refresh(note)

    for index, text in enumerate(comments):
        db.add(
            NoteComment(
                note_id=note.id,
                comment_id=f"comment-{note.id}-{index}",
                user_name="测试用户",
                content=text,
                like_count=index,
            )
        )
    db.commit()
    return note


def test_health_api_returns_can_generate_false_for_insufficient_data(client: TestClient):
    token = _register_and_get_access_token(client, username="health-api")
    group_id = _seed_keyword_group_via_db("health-api")

    response = client.post(
        "/api/xhs/analytics/analysis/health",
        headers={"Authorization": f"Bearer {token}"},
        json={"keyword_group_id": group_id, "excluded_note_ids": []},
    )

    assert response.status_code == 200
    assert response.json()["can_generate"] is False

    ledger_count = _with_api_db(lambda db: db.scalar(select(func.count(UsageLedger.id)).where(UsageLedger.bucket == "analysis_report")))
    assert ledger_count == 0


def test_reports_api_rejects_other_user_report(client: TestClient):
    _register_and_get_access_token(client, username="owner")
    token_b = _register_and_get_access_token(client, username="intruder")
    report_id = _seed_failed_report_via_db(username="owner")

    response = client.get(
        f"/api/xhs/analytics/analysis/reports/{report_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )

    assert response.status_code == 404


def test_reports_api_lists_and_reads_only_current_user_reports(client: TestClient):
    token = _register_and_get_access_token(client, username="report-reader")
    own_report_id = _seed_report_via_db(username="report-reader", title="自己的报告")

    list_response = client.get(
        "/api/xhs/analytics/analysis/reports",
        headers={"Authorization": f"Bearer {token}"},
    )
    detail_response = client.get(
        f"/api/xhs/analytics/analysis/reports/{own_report_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [own_report_id]
    assert detail_response.status_code == 200
    assert detail_response.json()["title"] == "自己的报告"


def test_create_report_api_below_minimum_does_not_call_model(client: TestClient):
    from backend.app.api.platforms.xhs import analysis_center

    token = _register_and_get_access_token(client, username="create-api")
    group_id = _seed_keyword_group_via_db("create-api")
    fake_client = FakeApiJsonAiClient()
    app.dependency_overrides[analysis_center.get_text_ai_client] = lambda: fake_client
    try:
        response = client.post(
            "/api/xhs/analytics/analysis/reports",
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "analysis-below-minimum"},
            json={"keyword_group_id": group_id, "title": "数据不足报告", "excluded_note_ids": []},
        )
    finally:
        app.dependency_overrides.pop(analysis_center.get_text_ai_client, None)

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert "数据低于最低门槛" in response.json()["error_message"]
    assert fake_client.calls == 0

    balance = client.get("/api/usage/balance", headers={"Authorization": f"Bearer {token}"})
    assert balance.status_code == 200
    assert balance.json()["buckets"]["analysis_report"]["remaining"] == 5
    operations = _with_api_db(
        lambda db: [
            row.operation
            for row in db.scalars(
                select(UsageLedger).where(UsageLedger.bucket == "analysis_report").order_by(UsageLedger.id)
            ).all()
        ]
    )
    assert operations == ["reserve", "refund"]


def test_create_report_api_completed_commits_analysis_report_quota(client: TestClient):
    from backend.app.api.platforms.xhs import analysis_center

    token = _register_and_get_access_token(client, username="analysis-success")
    group_id = _seed_minimum_keyword_group_via_db("analysis-success")
    model_config_id = _create_text_model_config_via_db("analysis-success")
    fake_client = FakeApiJsonAiClient(response=json.dumps(_valid_ai_result(["metric:question_rate"]), ensure_ascii=False))
    app.dependency_overrides[analysis_center.get_text_ai_client] = lambda: fake_client
    try:
        response = client.post(
            "/api/xhs/analytics/analysis/reports",
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "analysis-report-success"},
            json={"keyword_group_id": group_id, "title": "完成报告", "excluded_note_ids": []},
        )
    finally:
        app.dependency_overrides.pop(analysis_center.get_text_ai_client, None)

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert fake_client.calls == 1

    balance = client.get("/api/usage/balance", headers={"Authorization": f"Bearer {token}"})
    assert balance.status_code == 200
    assert balance.json()["buckets"]["analysis_report"]["remaining"] == 4
    rows = _with_api_db(
        lambda db: db.scalars(
            select(UsageLedger).where(UsageLedger.bucket == "analysis_report").order_by(UsageLedger.id)
        ).all()
    )
    assert [(row.feature_key, row.operation, row.model_config_id) for row in rows] == [
        ("analysis.report_create", "reserve", model_config_id),
        ("analysis.report_create.commit", "commit", model_config_id),
    ]
    assert rows[0].request_summary == {
        "keyword_group_id": group_id,
        "excluded_note_count": 0,
        "source_note_count": 0,
        "benchmark_target_count": 0,
    }


def test_create_report_api_quota_shortage_returns_402_without_calling_provider(client: TestClient):
    from backend.app.api.platforms.xhs import analysis_center

    token = _register_and_get_access_token(client, username="analysis-limit")
    group_id = _seed_minimum_keyword_group_via_db("analysis-limit")
    _create_text_model_config_via_db("analysis-limit")
    trap_client = TrapApiJsonAiClient()

    def exhaust_quota(db: Session) -> None:
        user = db.scalar(select(User).where(User.username == "analysis-limit"))
        assert user is not None
        context = get_or_create_default_tenant_context(db, user.id)
        UsageQuotaService(db).adjust_bucket(context.tenant.id, "analysis_report", total=0, reason="test exhausts analysis report quota")

    _with_api_db(exhaust_quota)
    app.dependency_overrides[analysis_center.get_text_ai_client] = lambda: trap_client
    try:
        response = client.post(
            "/api/xhs/analytics/analysis/reports",
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "analysis-report-limit"},
            json={"keyword_group_id": group_id, "title": "超额报告", "excluded_note_ids": []},
        )
    finally:
        app.dependency_overrides.pop(analysis_center.get_text_ai_client, None)

    assert response.status_code == 402
    assert response.json()["bucket"] == "analysis_report"
    assert trap_client.called is False


def test_rerun_report_api_commits_analysis_report_quota(client: TestClient):
    from backend.app.api.platforms.xhs import analysis_center

    token = _register_and_get_access_token(client, username="analysis-rerun")
    group_id = _seed_minimum_keyword_group_via_db("analysis-rerun")
    _create_text_model_config_via_db("analysis-rerun")

    def seed_original_report(db: Session) -> int:
        user = db.scalar(select(User).where(User.username == "analysis-rerun"))
        assert user is not None
        report = AnalysisReport(
            user_id=user.id,
            platform="xhs",
            report_type="content_analysis",
            status="completed",
            title="原报告",
            input_config={"keyword_group_id": group_id, "excluded_note_ids": []},
            data_health={"status": "minimum", "can_generate": True},
            evidence_pool={"notes": [], "comments": [], "keywords": [], "metrics": [], "benchmarks": []},
            result_json=_valid_ai_result(["metric:question_rate"]),
            html_file_path="exports/original.html",
        )
        db.add(report)
        db.commit()
        db.refresh(report)
        return report.id

    original_report_id = _with_api_db(seed_original_report)
    fake_client = FakeApiJsonAiClient(response=json.dumps(_valid_ai_result(["metric:question_rate"]), ensure_ascii=False))
    app.dependency_overrides[analysis_center.get_text_ai_client] = lambda: fake_client
    try:
        response = client.post(
            f"/api/xhs/analytics/analysis/reports/{original_report_id}/rerun",
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "analysis-report-rerun"},
        )
    finally:
        app.dependency_overrides.pop(analysis_center.get_text_ai_client, None)

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["rerun_from_report_id"] == original_report_id
    assert fake_client.calls == 1

    balance = client.get("/api/usage/balance", headers={"Authorization": f"Bearer {token}"})
    assert balance.status_code == 200
    assert balance.json()["buckets"]["analysis_report"]["remaining"] == 4
    operations = _with_api_db(
        lambda db: [
            (row.feature_key, row.operation)
            for row in db.scalars(
                select(UsageLedger).where(UsageLedger.bucket == "analysis_report").order_by(UsageLedger.id)
            ).all()
        ]
    )
    assert operations == [("analysis.report_rerun", "reserve"), ("analysis.report_rerun.commit", "commit")]


def test_create_drafts_api_allows_owner_and_rejects_other_user_report(client: TestClient):
    owner_token = _register_and_get_access_token(client, username="draft-owner")
    intruder_token = _register_and_get_access_token(client, username="draft-intruder")
    report_id = _seed_report_via_db(username="draft-owner", title="可生成草稿报告")
    card = _valid_ai_result(["metric:question_rate"])["topic_cards"][0]

    owner_response = client.post(
        f"/api/xhs/analytics/analysis/reports/{report_id}/topic-cards/{card['id']}/drafts",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"topic_cards": [card]},
    )
    intruder_response = client.post(
        f"/api/xhs/analytics/analysis/reports/{report_id}/topic-cards/{card['id']}/drafts",
        headers={"Authorization": f"Bearer {intruder_token}"},
        json={"topic_cards": [card]},
    )

    assert owner_response.status_code == 200
    owner_payload = owner_response.json()
    assert owner_payload[0]["platform"] == "xhs"
    assert owner_payload[0]["title"] == card["title_direction"]
    assert owner_payload[0]["tags"] == [{"name": "ClaudeCode"}]
    assert "正文结构大纲" in owner_payload[0]["body"]
    assert "完整正文" not in owner_payload[0]["body"]
    assert owner_payload[0]["source_note_id"] is None
    assert owner_payload[0]["created_at"]
    assert intruder_response.status_code == 404

    draft_count = _with_api_db(lambda db: db.scalar(select(func.count(AiDraft.id))))
    assert draft_count == 1


def test_analysis_report_model_persists_json(db_session: Session):
    user = _create_user(db_session)
    report = AnalysisReport(
        user_id=user.id,
        platform="xhs",
        report_type="content_analysis",
        status="completed",
        title="AI 编程 - 小红书分析报告 - 2026-06-16",
        input_config={"keyword_group_id": 1, "excluded_note_ids": []},
        data_health={"status": "minimum", "can_generate": True},
        evidence_pool={"notes": [], "comments": [], "keywords": [], "metrics": [], "benchmarks": []},
        result_json={
            "summary": {"facts": [], "inferences": [], "recommendations": []},
            "insight_cards": [],
            "topic_cards": [],
            "report_warnings": [],
        },
        html_file_path="exports/xhs-analysis-report-u1-test.html",
    )
    db_session.add(report)
    db_session.commit()
    db_session.refresh(report)

    assert report.id > 0
    assert report.platform == "xhs"
    assert report.input_config["keyword_group_id"] == 1
    assert report.data_health["status"] == "minimum"
    assert report.evidence_pool["notes"] == []
    assert report.error_message is None


def test_analysis_reports_table_has_required_columns(db_session: Session):
    columns = {column["name"] for column in inspect(db_session.bind).get_columns("analysis_reports")}

    assert {
        "id",
        "user_id",
        "platform",
        "report_type",
        "status",
        "title",
        "input_config",
        "data_health",
        "evidence_pool",
        "result_json",
        "html_file_path",
        "source_task_id",
        "rerun_from_report_id",
        "error_message",
        "created_at",
        "started_at",
        "finished_at",
    }.issubset(columns)


def test_analysis_health_below_minimum_blocks_generation(db_session: Session):
    user = _create_user(db_session, "below-minimum")
    group = _create_keyword_group(db_session, user.id, ["Claude Code", "AI编程"])
    _create_note_with_comments(db_session, user.id, title="少量样本", content="Claude Code 入门", comments=["怎么配置？"])

    service = XhsAnalysisCenterService(db_session)
    health = service.check_health(user_id=user.id, keyword_group_id=group.id, excluded_note_ids=[])

    assert health["status"] == "insufficient"
    assert health["can_generate"] is False
    assert health["metrics"]["valid_note_count"] < 10
    assert health["collection_plan"]["needed"] is True


def test_analysis_health_allows_generation_without_comments_but_recommends_comment_collection(db_session: Session):
    user = _create_user(db_session, "minimum-no-comments")
    group = _create_keyword_group(db_session, user.id, ["Claude Code", "AI编程", "Cursor"])
    for index in range(10):
        _create_note_with_comments(
            db_session,
            user.id,
            title=f"Claude Code 入门 {index}",
            content="Claude Code Cursor AI编程 新手配置",
            comments=[],
            raw_json={"liked_count": 20 + index, "collected_count": 10, "comment_count": 0, "share_count": 1},
        )

    service = XhsAnalysisCenterService(db_session)
    health = service.check_health(user_id=user.id, keyword_group_id=group.id, excluded_note_ids=[])

    assert health["status"] == "minimum"
    assert health["can_generate"] is True
    assert health["confidence_cap"] == "medium"
    assert "comments" not in {item["key"] for item in health["missing"]}
    assert health["collection_plan"]["should_collect_comments"] is True
    assert any("没有已存评论" in warning for warning in health["warnings"])


def test_analysis_health_minimum_caps_confidence_to_medium(db_session: Session):
    user = _create_user(db_session, "minimum")
    group = _create_keyword_group(db_session, user.id, ["Claude Code", "AI编程", "Cursor"])
    for index in range(10):
        _create_note_with_comments(
            db_session,
            user.id,
            title=f"Claude Code 入门 {index}",
            content="Claude Code Cursor AI编程 新手配置",
            comments=[f"新手怎么配置 {index}-{item}？" for item in range(3)],
            raw_json={"liked_count": 20 + index, "collected_count": 10, "comment_count": 3, "share_count": 1},
        )

    service = XhsAnalysisCenterService(db_session)
    health = service.check_health(user_id=user.id, keyword_group_id=group.id, excluded_note_ids=[])

    assert health["status"] == "minimum"
    assert health["can_generate"] is True
    assert health["confidence_cap"] == "medium"


def test_analysis_health_standard_allows_high_confidence(db_session: Session):
    user = _create_user(db_session, "standard")
    group = _create_keyword_group(db_session, user.id, ["Claude Code", "AI编程", "Cursor", "AI工具", "效率工具"])
    for index in range(30):
        _create_note_with_comments(
            db_session,
            user.id,
            title=f"Claude Code 效率工具 {index}",
            content="Claude Code Cursor AI编程 AI工具 效率工具 配置教程",
            comments=[f"怎么买课程 {index}-{item}？" for item in range(4)],
            raw_json={"liked_count": 80 + index, "collected_count": 40, "comment_count": 4, "share_count": 10},
        )

    service = XhsAnalysisCenterService(db_session)
    health = service.check_health(user_id=user.id, keyword_group_id=group.id, excluded_note_ids=[])

    assert health["status"] == "standard"
    assert health["can_generate"] is True
    assert health["confidence_cap"] == "high"


def test_analysis_health_and_evidence_pool_exclude_persisted_note_exclusions(db_session: Session):
    user = _create_user(db_session, "persisted-exclusion-scope")
    group = _create_keyword_group(db_session, user.id, ["Claude Code", "AI编程", "Cursor"])
    active_note = _create_note_with_comments(
        db_session,
        user.id,
        title="Claude Code 新手配置",
        content="Claude Code Cursor AI编程 入门教程",
        comments=["新手怎么配置？"],
        raw_json={"liked_count": 100, "collected_count": 60, "comment_count": 1, "share_count": 5},
    )
    excluded_note = _create_note_with_comments(
        db_session,
        user.id,
        title="Claude Code 废弃样本",
        content="Claude Code Cursor AI编程 旧资料",
        comments=["不应进入证据池"],
        raw_json={"liked_count": 100, "collected_count": 60, "comment_count": 1, "share_count": 5},
    )
    db_session.add(
        NoteExclusion(
            user_id=user.id,
            note_id=None,
            platform="xhs",
            platform_note_id=excluded_note.note_id,
            reason_code="manual_excluded",
            reason_text="已废弃",
        )
    )
    db_session.commit()

    service = XhsAnalysisCenterService(db_session)
    health = service.check_health(user_id=user.id, keyword_group_id=group.id, excluded_note_ids=[])
    pool = service.build_evidence_pool(user_id=user.id, keyword_group_id=group.id, excluded_note_ids=[])

    assert health["metrics"]["valid_note_count"] == 1
    assert [item["note_id"] for item in pool["notes"]] == [active_note.id]
    assert {item["note_id"] for item in pool["comments"]} == {active_note.id}
    assert excluded_note.id not in [item["note_id"] for item in pool["notes"]]


def test_evidence_pool_contains_only_real_notes_comments_keywords_and_metrics(db_session: Session):
    user = _create_user(db_session, "evidence")
    group = _create_keyword_group(db_session, user.id, ["Claude Code", "AI编程", "Cursor"])
    note = _create_note_with_comments(
        db_session,
        user.id,
        title="Claude Code 新手配置",
        content="Claude Code Cursor AI编程 入门教程",
        comments=["新手完全不会配置，有没有保姆级教程？", "多少钱可以买课程？"],
        raw_json={"liked_count": 100, "collected_count": 60, "comment_count": 2, "share_count": 5},
    )

    service = XhsAnalysisCenterService(db_session)
    pool = service.build_evidence_pool(user_id=user.id, keyword_group_id=group.id, excluded_note_ids=[])

    assert pool["notes"][0]["evidence_id"] == f"note:{note.id}"
    assert pool["comments"][0]["evidence_id"].startswith("comment:")
    assert {item["keyword"] for item in pool["keywords"]} == {"Claude Code", "AI编程", "Cursor"}
    assert any(metric["evidence_id"] == "metric:question_rate" for metric in pool["metrics"])
    assert "beginner_need" in pool["comments"][0]["signals"]
    assert "price_intent" in pool["comments"][1]["signals"]


class FakeJsonAiClient:
    def __init__(self, response: str):
        self.response = response
        self.calls = 0

    def complete_json_prompt(self, **kwargs):
        self.calls += 1
        return self.response


def test_create_report_below_minimum_does_not_call_model(db_session: Session):
    user = _create_user(db_session, "no-model-call")
    group = _create_keyword_group(db_session, user.id, ["Claude Code", "AI编程"])
    _create_note_with_comments(db_session, user.id, "少量 Claude Code", "Claude Code", ["怎么配置？"])
    client = FakeJsonAiClient(response="{}")

    service = XhsAnalysisCenterService(db_session)
    report = service.create_report(
        user_id=user.id,
        payload={"keyword_group_id": group.id, "title": "数据不足报告", "excluded_note_ids": []},
        model_config=None,
        api_key="",
        ai_client=client,
    )

    assert report.status == "failed"
    assert "数据低于最低门槛" in report.error_message
    assert client.calls == 0


def test_create_report_invalid_json_saves_failed_snapshot(db_session: Session):
    user = _seed_minimum_dataset(db_session, "invalid-json")
    group = db_session.scalar(select(KeywordGroup).where(KeywordGroup.user_id == user.id))
    client = FakeJsonAiClient(response="not json")
    model_config = _create_model_config(db_session, user.id)

    service = XhsAnalysisCenterService(db_session)
    report = service.create_report(
        user_id=user.id,
        payload={"keyword_group_id": group.id, "title": "非法 JSON", "excluded_note_ids": []},
        model_config=model_config,
        api_key="test-key",
        ai_client=client,
    )

    assert report.status == "failed"
    assert "模型输出不是合法 JSON" in report.error_message
    assert report.evidence_pool["notes"]
    assert report.html_file_path == ""


def _seed_minimum_dataset(db: Session, username: str) -> User:
    user = _create_user(db, username)
    _create_keyword_group(db, user.id, ["Claude Code", "AI编程", "Cursor"])
    for index in range(10):
        _create_note_with_comments(
            db,
            user.id,
            title=f"Claude Code 入门 {index}",
            content="Claude Code Cursor AI编程 入门配置",
            comments=[f"新手怎么配置 {index}-{item}？" for item in range(3)],
            raw_json={"liked_count": 70, "collected_count": 30, "comment_count": 3, "share_count": 5},
        )
    return user


def _create_model_config(db: Session, user_id: int):
    from backend.app.models.ai import ModelConfig

    config = ModelConfig(
        user_id=user_id,
        name="测试文本模型",
        model_type="text",
        provider="openai-compatible",
        model_name="test-model",
        base_url="https://example.invalid/v1",
        encrypted_api_key="encrypted",
        is_default=True,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


def test_renderer_outputs_static_html_with_disclaimer(tmp_path):
    from backend.app.services.xhs_analysis_report_renderer import render_xhs_analysis_report_html

    html = render_xhs_analysis_report_html(
        title="AI 编程 - 小红书分析报告 <b>不要注入</b>",
        data_health={"status": "minimum", "warnings": ["样本未达标准阈值，结论仅供初筛"]},
        evidence_pool={"notes": [{"evidence_id": "note:1", "title": "真实笔记", "engagement": 100}], "comments": [], "keywords": [], "metrics": [], "benchmarks": []},
        result_json=_valid_ai_result(["note:1"]),
    )

    assert "AI 编程 - 小红书分析报告" in html
    assert "样本未达标准阈值" in html
    assert "报告基于当前已采集数据生成" in html
    assert "&lt;b&gt;不要注入&lt;/b&gt;" in html
    assert "<b>不要注入</b>" not in html
    assert "<script" not in html.lower()


def test_create_report_completed_writes_html_and_failed_keeps_empty_html_path(db_session: Session, tmp_path, monkeypatch):
    monkeypatch.setattr("backend.app.core.config.Settings.storage_dir", property(lambda self: tmp_path))
    user = _seed_minimum_dataset(db_session, "completed-html")
    group = db_session.scalar(select(KeywordGroup).where(KeywordGroup.user_id == user.id))
    model_config = _create_model_config(db_session, user.id)
    completed_client = FakeJsonAiClient(response=json.dumps(_valid_ai_result(["metric:question_rate"]), ensure_ascii=False))

    service = XhsAnalysisCenterService(db_session)
    completed_report = service.create_report(
        user_id=user.id,
        payload={"keyword_group_id": group.id, "title": "完成报告", "excluded_note_ids": []},
        model_config=model_config,
        api_key="test-key",
        ai_client=completed_client,
    )

    assert completed_report.status == "completed"
    assert completed_report.html_file_path
    assert completed_report.html_file_path.endswith(f"xhs-analysis-report-u{user.id}-{completed_report.id}.html")
    html_path = tmp_path / "exports" / f"xhs-analysis-report-u{user.id}-{completed_report.id}.html"
    assert html_path.read_text(encoding="utf-8")
    assert "<script" not in html_path.read_text(encoding="utf-8").lower()

    failed_client = FakeJsonAiClient(response="not json")
    failed_report = service.create_report(
        user_id=user.id,
        payload={"keyword_group_id": group.id, "title": "失败报告", "excluded_note_ids": []},
        model_config=model_config,
        api_key="test-key",
        ai_client=failed_client,
    )

    assert failed_report.status == "failed"
    assert failed_report.html_file_path == ""


def test_validate_result_rejects_nonexistent_evidence_id(db_session: Session):
    service = XhsAnalysisCenterService(db_session)
    evidence_pool = {"notes": [], "comments": [], "keywords": [], "metrics": [{"evidence_id": "metric:question_rate"}], "benchmarks": []}
    result = _valid_ai_result(evidence_ids=["metric:not_exists"])

    with pytest.raises(AnalysisValidationError, match="Unknown evidence_id"):
        service.validate_ai_result(result, evidence_pool=evidence_pool, confidence_cap="high")


def test_validate_result_rejects_high_confidence_when_cap_is_medium(db_session: Session):
    service = XhsAnalysisCenterService(db_session)
    evidence_pool = {"notes": [], "comments": [], "keywords": [], "metrics": [{"evidence_id": "metric:question_rate"}], "benchmarks": []}
    result = _valid_ai_result(evidence_ids=["metric:question_rate"], confidence="high")

    with pytest.raises(AnalysisValidationError, match="exceeds confidence cap"):
        service.validate_ai_result(result, evidence_pool=evidence_pool, confidence_cap="medium")


def test_create_drafts_from_topic_cards_saves_skeleton_only(db_session: Session):
    user = _create_user(db_session, "drafts")
    service = XhsAnalysisCenterService(db_session)
    card = _valid_ai_result(["metric:question_rate"])["topic_cards"][0]
    card["title_direction"] = "Claude Code 新手配置清单" * 30

    drafts = service.create_drafts_from_topic_cards(user_id=user.id, topic_cards=[card])

    assert len(drafts) == 1
    assert drafts[0].platform == "xhs"
    assert len(drafts[0].title) == 256
    assert drafts[0].tags == [{"name": "ClaudeCode"}]
    assert drafts[0].source_note_id is None
    for section in [
        "标题方向",
        "目标用户痛点",
        "内容角度",
        "正文结构大纲",
        "推荐内容形态",
        "封面建议",
        "预期优势",
        "参考证据",
        "风险提醒",
    ]:
        assert section in drafts[0].body
    assert "适合谁" in drafts[0].body
    assert "metric:question_rate" in drafts[0].body
    assert "完整正文" not in drafts[0].body


def _valid_ai_result(evidence_ids: list[str], confidence: str = "medium") -> dict:
    return {
        "summary": {
            "facts": [{"id": "fact_1", "text": "评论中提问占比较高。", "evidence_ids": evidence_ids}],
            "inferences": [{"id": "inference_1", "text": "用户需要更清晰的配置教程。", "evidence_ids": evidence_ids}],
            "recommendations": [{"id": "recommendation_1", "text": "优先制作保姆级教程。", "evidence_ids": evidence_ids}],
        },
        "insight_cards": [
            {
                "id": "insight_1",
                "title": "新手配置门槛是高频痛点",
                "score": 80,
                "sub_scores": {"traffic_potential": 70, "demand_strength": 90, "competition_pressure": 60, "actionability": 85},
                "confidence": confidence,
                "confidence_reason": "基于评论信号和指标。",
                "facts": [],
                "inferences": [],
                "recommendations": [],
                "evidence_ids": evidence_ids,
                "topic_card_ids": ["topic_1"],
            }
        ],
        "topic_cards": [
            {
                "id": "topic_1",
                "insight_id": "insight_1",
                "title_direction": "Claude Code 新手配置清单",
                "target_pain": "新手不会配置。",
                "content_angle": "保姆级教程。",
                "recommended_structure": ["适合谁", "配置步骤", "常见坑"],
                "recommended_content_form": ["教程型"],
                "tags": ["ClaudeCode"],
                "cover_suggestion": "第一次用 Claude Code，照着做就能跑",
                "expected_advantage": "新手问题明确。",
                "risk_warning": "不要写泛泛介绍。",
                "evidence_ids": evidence_ids,
            }
        ],
        "report_warnings": [],
    }

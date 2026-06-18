from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.api.keyword_groups import get_huitun_live_keyword_client
from backend.app.core.database import Base, get_db
from backend.app.core.security import create_access_token, encrypt_text, hash_password
from backend.app.main import app
from backend.app.models import AccountCookieVersion, KeywordDiscoveryItem, KeywordDiscoveryRun, PlatformAccount, User

client = TestClient(app)


def test_huitun_rows_from_response_finds_nested_lists_under_data_records():
    from backend.app.services.huitun_live_keyword_source import _rows_from_response

    rows = _rows_from_response(
        "低卡早餐",
        {
            "status": 0,
            "data": {
                "result": {
                    "records": [
                        {"word": "低卡早餐食谱", "searchIndex": "1.2w", "noteNum": 300, "rankIndex": 1}
                    ]
                }
            },
        },
        10,
    )

    assert rows == [
        {
            "source_keyword": "低卡早餐",
            "keyword": "低卡早餐食谱",
            "hot_value_text": "1.2w",
            "hot_value_number": None,
            "note_count": 300,
            "interaction_text": None,
            "interaction_number": None,
            "categories": [],
            "rank_index": 1,
        }
    ]


def test_huitun_rows_from_response_reports_structure_change_when_no_list_exists():
    from backend.app.services.huitun_live_keyword_source import HUITUN_STRUCTURE_CHANGED_MESSAGE, _rows_from_response

    with pytest.raises(RuntimeError) as exc_info:
        _rows_from_response("低卡早餐", {"status": 0, "extData": {"unexpected": {"value": 1}}}, 10)

    assert str(exc_info.value) == HUITUN_STRUCTURE_CHANGED_MESSAGE


def test_huitun_rows_from_response_reports_empty_result_when_list_is_present_but_has_no_rows():
    from backend.app.services.huitun_live_keyword_source import HUITUN_EMPTY_RESULT_MESSAGE, _rows_from_response

    with pytest.raises(RuntimeError) as exc_info:
        _rows_from_response("低卡早餐", {"status": 0, "data": {"records": []}}, 10)

    assert str(exc_info.value) == HUITUN_EMPTY_RESULT_MESSAGE


def test_huitun_failure_message_preserves_safe_upstream_message():
    from backend.app.services.huitun_live_keyword_source import _huitun_failure_message

    message = _huitun_failure_message({"status": 5001, "message": "关键词不能为空或无权限访问"})

    assert message == "灰豚候选词获取失败：关键词不能为空或无权限访问"


def test_fetch_huitun_hotwords_caps_live_page_size(monkeypatch):
    from backend.app.services import huitun_live_keyword_source as source

    captured: dict[str, Any] = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"status": 0, "data": {"records": [{"word": "浴缸", "rankIndex": 1}]}}

    class FakeSession:
        cookies: dict[str, str] = {}

        def post(self, _url, *, params, json, timeout):
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr(source, "validate_huitun_login_state", lambda _cookie_text: {"nickname": "灰豚账号"})
    monkeypatch.setattr(source, "_session_from_cookie_text", lambda _cookie_text: FakeSession())

    rows = source.fetch_huitun_hotwords("session=ok", "浴缸", 50)

    assert captured["json"]["pageSize"] == 20
    assert rows[0]["keyword"] == "浴缸"


def test_huitun_rows_from_response_reports_decrypt_failure_for_invalid_ext_data():
    from backend.app.services.huitun_crypto import HUITUN_EXT_DATA_DECRYPT_FAILED_MESSAGE
    from backend.app.services.huitun_live_keyword_source import _rows_from_response

    with pytest.raises(RuntimeError) as exc_info:
        _rows_from_response("低卡早餐", {"status": 0, "extData": "not-valid-encrypted-payload"}, 10)

    assert str(exc_info.value) == HUITUN_EXT_DATA_DECRYPT_FAILED_MESSAGE


class FakeHuitunClient:
    def __init__(self, results: dict[str, list[dict[str, Any]]], failures: dict[str, str] | None = None) -> None:
        self.results = results
        self.failures = failures or {}
        self.calls: list[tuple[str, str, int]] = []

    def fetch_huitun_hotwords(self, cookie_text: str, seed_keyword: str, limit: int) -> list[dict[str, Any]]:
        self.calls.append((cookie_text, seed_keyword, limit))
        if seed_keyword in self.failures:
            raise RuntimeError(self.failures[seed_keyword])
        return self.results.get(seed_keyword, [])[:limit]


def override_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'huitun-discovery-test.db'}", connect_args={"check_same_thread": False})
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


def create_user_account_and_headers(SessionLocal):
    db = SessionLocal()
    try:
        user = User(username="operator", password_hash=hash_password("secret123"))
        db.add(user)
        db.flush()
        account = PlatformAccount(
            user_id=user.id,
            platform="huitun",
            sub_type="main",
            external_user_id="huitun-1",
            nickname="灰豚测试账号",
            status="active",
        )
        db.add(account)
        db.flush()
        db.add(AccountCookieVersion(platform_account_id=account.id, encrypted_cookies=encrypt_text("session=ok")))
        db.commit()
        return account.id, {"Authorization": f"Bearer {create_access_token(user.id)}"}
    finally:
        db.close()


def test_live_huitun_batch_discovery_keeps_successful_seed_items_when_one_seed_fails(tmp_path):
    SessionLocal = override_database(tmp_path)
    try:
        account_id, headers = create_user_account_and_headers(SessionLocal)
        fake = FakeHuitunClient(
            results={
                "低卡早餐": [
                    {
                        "source_keyword": "低卡早餐",
                        "keyword": "低卡早餐食谱",
                        "hot_value_text": "1.2w",
                        "hot_value_number": 12000,
                        "note_count": 300,
                        "interaction_text": "900",
                        "interaction_number": 900,
                        "categories": [{"label": "美食", "rate": "80"}],
                        "rank_index": 1,
                    }
                ]
            },
            failures={"通勤穿搭": "灰豚候选词返回结构已变化，请先使用手工导入并等待适配。"},
        )
        app.dependency_overrides[get_huitun_live_keyword_client] = lambda: fake

        response = client.post(
            "/api/keyword-groups/huitun/discovery-runs",
            headers=headers,
            json={
                "source_mode": "live_account",
                "account_id": account_id,
                "limit_per_seed": 50,
                "inputs": [
                    {"source_keyword": "低卡早餐"},
                    {"source_keyword": "通勤穿搭"},
                ],
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "partial_failed"
        assert payload["limit_per_seed"] == 20
        assert payload["summary"] == {
            "success_seed_count": 1,
            "failed_seed_count": 1,
            "total_item_count": 1,
        }
        assert payload["seed_results"] == [
            {"source_keyword": "低卡早餐", "status": "success", "item_count": 1, "error_message": ""},
            {
                "source_keyword": "通勤穿搭",
                "status": "failed",
                "item_count": 0,
                "error_message": "灰豚候选词返回结构已变化，请先使用手工导入并等待适配。",
            },
        ]
        assert [item["keyword"] for item in payload["items"]] == ["低卡早餐食谱"]
        assert fake.calls == [("session=ok", "低卡早餐", 20), ("session=ok", "通勤穿搭", 20)]

        db = SessionLocal()
        try:
            runs = db.scalars(select(KeywordDiscoveryRun)).all()
            assert len(runs) == 1
            run = runs[0]
            assert run.status == "partial_failed"
            assert "灰豚候选词返回结构已变化" in (run.error_message or "")
            assert "通勤穿搭" in (run.error_message or "")

            items = db.scalars(select(KeywordDiscoveryItem)).all()
            assert len(items) == 1
            assert items[0].run_id == run.id
            assert items[0].source_keyword == "低卡早餐"
            assert items[0].keyword == "低卡早餐食谱"
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_huitun_live_keyword_client, None)
        app.dependency_overrides.pop(get_db, None)


def test_live_huitun_batch_discovery_returns_failed_run_instead_of_http_400_when_all_seeds_fail(tmp_path):
    SessionLocal = override_database(tmp_path)
    try:
        account_id, headers = create_user_account_and_headers(SessionLocal)
        fake = FakeHuitunClient(results={}, failures={"低卡早餐": "灰豚登录态已过期，请到账号矩阵重新登录。"})
        app.dependency_overrides[get_huitun_live_keyword_client] = lambda: fake

        response = client.post(
            "/api/keyword-groups/huitun/discovery-runs",
            headers=headers,
            json={
                "source_mode": "live_account",
                "account_id": account_id,
                "limit_per_seed": 50,
                "inputs": [{"source_keyword": "低卡早餐"}],
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "failed"
        assert payload["items"] == []
        assert payload["summary"] == {
            "success_seed_count": 0,
            "failed_seed_count": 1,
            "total_item_count": 0,
        }
        assert payload["seed_results"] == [
            {
                "source_keyword": "低卡早餐",
                "status": "failed",
                "item_count": 0,
                "error_message": "灰豚登录态已过期，请到账号矩阵重新登录。",
            }
        ]
        assert payload["limit_per_seed"] == 20
        assert fake.calls == [("session=ok", "低卡早餐", 20)]
    finally:
        app.dependency_overrides.pop(get_huitun_live_keyword_client, None)
        app.dependency_overrides.pop(get_db, None)


def test_huitun_discovery_run_history_lists_current_user_runs_without_items(tmp_path):
    SessionLocal = override_database(tmp_path)
    try:
        account_id, headers = create_user_account_and_headers(SessionLocal)
        fake = FakeHuitunClient(
            results={
                "低卡早餐": [
                    {"source_keyword": "低卡早餐", "keyword": "低卡早餐食谱", "rank_index": 1, "categories": []}
                ]
            }
        )
        app.dependency_overrides[get_huitun_live_keyword_client] = lambda: fake

        create_response = client.post(
            "/api/keyword-groups/huitun/discovery-runs",
            headers=headers,
            json={
                "source_mode": "live_account",
                "account_id": account_id,
                "limit_per_seed": 20,
                "inputs": [{"source_keyword": "低卡早餐"}],
            },
        )
        assert create_response.status_code == 200

        list_response = client.get("/api/keyword-groups/huitun/discovery-runs", headers=headers)

        assert list_response.status_code == 200
        payload = list_response.json()
        assert payload["total"] == 1
        assert payload["items"][0]["seed_keywords"] == ["低卡早餐"]
        assert payload["items"][0]["summary"]["total_item_count"] == 1
        assert payload["items"][0]["items"] == []
    finally:
        app.dependency_overrides.pop(get_huitun_live_keyword_client, None)
        app.dependency_overrides.pop(get_db, None)


def test_successful_huitun_candidates_can_still_import_to_new_keyword_group(tmp_path):
    SessionLocal = override_database(tmp_path)
    try:
        account_id, headers = create_user_account_and_headers(SessionLocal)
        fake = FakeHuitunClient(
            results={
                "低卡早餐": [
                    {"source_keyword": "低卡早餐", "keyword": "低卡早餐食谱", "rank_index": 1, "categories": []},
                    {"source_keyword": "低卡早餐", "keyword": "低卡早餐空气炸锅", "rank_index": 2, "categories": []},
                ]
            }
        )
        app.dependency_overrides[get_huitun_live_keyword_client] = lambda: fake

        create_response = client.post(
            "/api/keyword-groups/huitun/discovery-runs",
            headers=headers,
            json={
                "source_mode": "live_account",
                "account_id": account_id,
                "limit_per_seed": 20,
                "inputs": [{"source_keyword": "低卡早餐"}],
            },
        )
        assert create_response.status_code == 200
        candidate_ids = [item["id"] for item in create_response.json()["items"]]

        import_response = client.post(
            "/api/keyword-groups/import-keyword-candidates",
            headers=headers,
            json={
                "candidate_ids": candidate_ids,
                "merge_mode": "append_dedupe",
                "target": {"mode": "create", "name": "低卡早餐热词", "platform": "xhs"},
            },
        )

        assert import_response.status_code == 200
        payload = import_response.json()
        assert payload["group"]["name"] == "低卡早餐热词"
        assert payload["imported_keywords"] == ["低卡早餐食谱", "低卡早餐空气炸锅"]
    finally:
        app.dependency_overrides.pop(get_huitun_live_keyword_client, None)
        app.dependency_overrides.pop(get_db, None)

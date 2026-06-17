from backend.app.api.platforms.xhs.crawl import _search_failure_kind, _search_failure_user_message
from backend.app.services.crawl_diagnostics import diagnostic_payload_summary


def test_search_failure_detects_expired_xhs_login_from_error_code():
    payload = {"code": -100, "success": False, "msg": "登录已过期", "data": {}}

    kind = _search_failure_kind("登录已过期", payload)

    assert kind == "xhs_account_expired"
    assert "重新登录" in _search_failure_user_message(kind)


def test_search_failure_detects_expired_xhs_login_from_mojibake_message():
    payload = {"code": -100, "success": False, "msg": "��¼�ѹ���", "data": {}}

    kind = _search_failure_kind("��¼�ѹ���", payload)

    assert kind == "xhs_account_expired"


def test_diagnostic_summary_preserves_top_level_xhs_code():
    summary = diagnostic_payload_summary({"code": -100, "success": False, "msg": "登录已过期", "data": {}}, "飞书")

    assert summary["error_code"] == -100
    assert summary["message"] == "登录已过期"

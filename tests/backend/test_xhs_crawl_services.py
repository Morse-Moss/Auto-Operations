from backend.app.services.xhs_crawl_quality_service import (
    filter_saveable_notes,
    search_failure_kind,
    search_failure_user_message,
)


def test_xhs_crawl_quality_service_classifies_login_expiry_and_rate_limit():
    expired_payload = {"code": -100, "success": False, "msg": "登录已过期", "data": {}}

    expired_kind = search_failure_kind("登录已过期", expired_payload)
    rate_limited_kind = search_failure_kind("error_code=300013 访问频繁", {"msg": "访问频繁"})

    assert expired_kind == "xhs_account_expired"
    assert "重新登录" in search_failure_user_message(expired_kind)
    assert rate_limited_kind == "xhs_rate_limited"


def test_xhs_crawl_quality_service_filters_saveable_notes():
    valid = {
        "note_id": "valid-detail",
        "note_url": "https://www.xiaohongshu.com/explore/valid-detail?xsec_token=token",
        "content": "正文",
        "image_urls": [],
    }
    search_card_only = {
        "note_id": "card-only",
        "note_url": "https://www.xiaohongshu.com/explore/card-only?xsec_token=token",
        "title": "只有标题",
        "likes": 12,
    }
    empty = {"note_id": "empty", "note_url": "https://www.xiaohongshu.com/explore/empty?xsec_token=token"}

    saveable, skipped = filter_saveable_notes([valid, search_card_only, empty])

    assert [item["note_id"] for item in saveable] == ["valid-detail"]
    assert [item["note_id"] for item in skipped] == ["card-only", "empty"]
    assert all(item["save_diagnostic_kind"] == "save_skipped_low_quality" for item in skipped)
    assert skipped[0]["quality_status"] == "search_card_only"
    assert skipped[1]["quality_status"] == "empty_detail_payload"

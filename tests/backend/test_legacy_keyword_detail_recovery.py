from __future__ import annotations

from backend.app.services.crawl_diagnostics import diagnostic_payload_summary, redact_diagnostic_raw
from backend.app.services.huitun_crypto import decrypt_huitun_ext_data
from backend.app.services.huitun_keyword_source import (
    dedupe_keyword_candidates,
    parse_hotword_rows_from_cells,
    parse_huitun_categories,
    parse_huitun_number,
    prioritize_exact_hotword_rows,
)
from backend.app.services.xhs_detail_recovery import (
    evaluate_detail_quality,
    is_xhs_rate_limit_signal,
    mask_xsec_token,
    should_reject_short_explore_url,
)


def test_decrypt_huitun_ext_data_matches_web_client_aes_ecb_payload():
    encrypted = "Wwqv3HPZinqRDh8BaBPy5Hq54ohd4/T3A3YGtR+95x5NVHXAeQGZhgho9nAYUF4DzZnHsomjpTgz+ThHadh3DQ=="

    assert decrypt_huitun_ext_data(encrypted) == {"list": [{"keyword": "浴缸", "hotValue": "12.3万"}]}


def test_parse_huitun_number_handles_empty_and_units():
    assert parse_huitun_number(None) is None
    assert parse_huitun_number("") is None
    assert parse_huitun_number("--") is None
    assert parse_huitun_number("暂无") is None
    assert parse_huitun_number("12.3万") == 123000
    assert parse_huitun_number("8.6w") == 86000
    assert parse_huitun_number("3,400") == 3400


def test_parse_huitun_categories_handles_percent_lines_and_plain_labels():
    assert parse_huitun_categories("户外 42.5%\n穿搭 18%") == [
        {"label": "户外", "rate": "42.5"},
        {"label": "穿搭", "rate": "18"},
    ]
    assert parse_huitun_categories("暂无分类") == [{"label": "暂无分类", "rate": None}]
    assert parse_huitun_categories("--") == []


def test_parse_hotword_rows_from_cells_skips_invalid_rows_and_normalizes_fields():
    rows = parse_hotword_rows_from_cells(
        "露营",
        [
            ["露营装备", "12.3万", "3400", "8.6万", "户外 42.5%"],
            ["列太少", "1"],
            ["  ", "1", "2", "3", "分类"],
            ["户外帐篷", "--", "暂无", "", "户外"],
        ],
    )

    assert rows == [
        {
            "source_keyword": "露营",
            "keyword": "露营装备",
            "hot_value_text": "12.3万",
            "hot_value_number": 123000,
            "note_count": 3400,
            "interaction_text": "8.6万",
            "interaction_number": 86000,
            "categories": [{"label": "户外", "rate": "42.5"}],
            "rank_index": 1,
        },
        {
            "source_keyword": "露营",
            "keyword": "户外帐篷",
            "hot_value_text": None,
            "hot_value_number": None,
            "note_count": None,
            "interaction_text": None,
            "interaction_number": None,
            "categories": [{"label": "户外", "rate": None}],
            "rank_index": 2,
        },
    ]


def test_prioritize_and_dedupe_hotword_candidates():
    rows = [
        {"keyword": "露营装备", "rank_index": 1},
        {"keyword": "露营", "rank_index": 2},
        {"keyword": "露营装备", "rank_index": 3},
    ]

    assert [row["keyword"] for row in prioritize_exact_hotword_rows("露营", rows)] == [
        "露营",
        "露营装备",
        "露营装备",
    ]
    assert [row["keyword"] for row in dedupe_keyword_candidates(rows)] == ["露营装备", "露营"]


def test_short_explore_url_requires_xsec_token():
    assert should_reject_short_explore_url("https://www.xiaohongshu.com/explore/abc") is True
    assert should_reject_short_explore_url("/explore/abc") is True
    assert should_reject_short_explore_url("https://www.xiaohongshu.com/explore/abc?xsec_token=t") is False
    assert should_reject_short_explore_url("https://www.xiaohongshu.com/search_result/abc?xsec_token=t") is False


def test_rate_limit_signal_detection():
    assert is_xhs_rate_limit_signal(
        url="https://www.xiaohongshu.com/website-login/error?error_code=300013"
    ) is True
    assert is_xhs_rate_limit_signal(text="访问频繁，请稍后再试") is True
    assert is_xhs_rate_limit_signal(message="error_code=300013 访问频繁") is True
    assert is_xhs_rate_limit_signal(message="普通详情失败") is False


def test_mask_xsec_token_never_returns_full_token():
    token = "abcdefghijk"
    masked = mask_xsec_token(token)

    assert masked != token
    assert masked == "abcd***hijk"
    assert mask_xsec_token("abc") == "***"
    assert mask_xsec_token(None) is None


def test_detail_quality_accepts_strong_detail_signals():
    content_quality = evaluate_detail_quality({"content": "完整正文", "note_url": "https://example.test"})
    media_quality = evaluate_detail_quality({"image_urls": ["https://example.test/a.jpg"]})
    tag_quality = evaluate_detail_quality({"tags": ["露营"]})
    raw_detail_quality = evaluate_detail_quality({}, {"data": {"noteDetailMap": {"feed1": {"desc": "正文"}}}})

    assert content_quality["quality_status"] == "valid_detail"
    assert content_quality["can_save"] is True
    assert media_quality["quality_status"] == "valid_detail"
    assert tag_quality["quality_status"] == "valid_detail"
    assert raw_detail_quality["quality_status"] == "valid_detail"


def test_detail_quality_rejects_weak_search_card_only_payloads():
    quality = evaluate_detail_quality(
        {
            "note_id": "feed1",
            "note_url": "https://www.xiaohongshu.com/explore/feed1?xsec_token=token",
            "title": "标题",
            "cover_url": "https://example.test/cover.jpg",
            "likes": 12,
            "collects": 3,
            "comments": 1,
            "shares": 0,
        }
    )

    assert quality["quality_status"] == "search_card_only"
    assert quality["diagnostic_kind"] == "empty_detail_payload"
    assert quality["recoverable"] is True
    assert quality["can_save"] is False


def test_detail_quality_rejects_empty_and_invalid_source_payloads():
    empty_quality = evaluate_detail_quality({})
    invalid_url_quality = evaluate_detail_quality({"note_url": "https://www.xiaohongshu.com/explore/feed1"})

    assert empty_quality["quality_status"] == "empty_detail_payload"
    assert empty_quality["can_save"] is False
    assert invalid_url_quality["quality_status"] == "invalid_source_url"
    assert invalid_url_quality["diagnostic_kind"] == "missing_xsec_token_short_explore"
    assert invalid_url_quality["recoverable"] is False


def test_diagnostic_summary_redacts_sensitive_values():
    raw_payload = {
        "headers": {"Authorization": "Bearer secret", "Cookie": "web_session=secret"},
        "xsec_token": "abcdefghijk",
        "web_session": "secret-session",
        "html": "<html>secret</html>",
        "error_code": 300013,
        "message": "访问频繁，请稍后再试",
        "data": {"items": [{"note_card": {"note_id": "feed1", "desc": "正文"}}]},
    }

    summary = diagnostic_payload_summary(raw_payload, "https://www.xiaohongshu.com/explore/feed1?xsec_token=abcdefghijk")
    redacted = redact_diagnostic_raw(raw_payload)

    assert summary["error_code"] == 300013
    assert summary["message"] == "访问频繁，请稍后再试"
    assert summary["note_id"] == "feed1"
    assert summary["has_xsec_token"] is True
    assert "abcdefghijk" not in str(summary)
    assert "secret" not in str(summary)
    assert "<html>" not in str(summary)
    assert "secret" not in str(redacted)
    assert "abcdefghijk" not in str(redacted)

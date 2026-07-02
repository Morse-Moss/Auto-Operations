import pytest

from backend.app.services.asset_storage_policy import (
    asset_owner_prefix,
    export_owner_prefix,
    validate_owned_export_file_name,
    validate_owned_media_file_name,
)


def test_accepts_legacy_xhs_media_owner_prefixes_for_user():
    user_id = 7

    assert validate_owned_media_file_name(f"xhs-upload-u{user_id}-photo.png", user_id) == f"xhs-upload-u{user_id}-photo.png"
    assert validate_owned_media_file_name(f"xhs-asset-u{user_id}-remote.jpg", user_id) == f"xhs-asset-u{user_id}-remote.jpg"
    assert validate_owned_media_file_name(f"xhs-image-u{user_id}-cover.png", user_id) == f"xhs-image-u{user_id}-cover.png"


def test_accepts_platform_aware_media_owner_prefixes_for_user():
    user_id = 7

    assert asset_owner_prefix("wechat_official", "upload", user_id) == f"wechat_official-upload-u{user_id}-"
    assert asset_owner_prefix("wechat_official", "asset", user_id) == f"wechat_official-asset-u{user_id}-"
    assert asset_owner_prefix("wechat_official", "image", user_id) == f"wechat_official-image-u{user_id}-"
    assert validate_owned_media_file_name(f"wechat_official-upload-u{user_id}-photo.png", user_id) == f"wechat_official-upload-u{user_id}-photo.png"
    assert validate_owned_media_file_name(f"wechat_official-asset-u{user_id}-remote.jpg", user_id) == f"wechat_official-asset-u{user_id}-remote.jpg"
    assert validate_owned_media_file_name(f"wechat_official-image-u{user_id}-cover.png", user_id) == f"wechat_official-image-u{user_id}-cover.png"


def test_accepts_wechat_official_user_owned_media_policy_examples():
    name = f"{asset_owner_prefix('wechat_official', 'asset', 7)}abc123.jpg"

    assert validate_owned_media_file_name(name, 7) == name


@pytest.mark.parametrize(
    "file_name",
    [
        "../xhs-upload-u7-photo.png",
        "nested/xhs-upload-u7-photo.png",
        "nested\\xhs-upload-u7-photo.png",
        "xhs-upload-u7-..photo.png",
    ],
)
def test_rejects_path_traversal_and_subdirectory_media_names(file_name):
    with pytest.raises(ValueError):
        validate_owned_media_file_name(file_name, 7)


def test_rejects_cross_user_media_prefixes():
    with pytest.raises(ValueError):
        validate_owned_media_file_name("xhs-upload-u8-photo.png", 7)

    with pytest.raises(ValueError):
        validate_owned_media_file_name("wechat_official-image-u8-cover.png", 7)


def test_accepts_legacy_and_platform_aware_export_owner_prefixes_for_user():
    user_id = 7

    assert export_owner_prefix("xhs", "notes", user_id) == f"xhs-notes-u{user_id}-"
    assert export_owner_prefix("xhs", "report", user_id) == f"xhs-report-u{user_id}-"
    assert export_owner_prefix("wechat_official", "notes", user_id) == f"wechat_official-notes-u{user_id}-"
    assert export_owner_prefix("wechat_official", "report", user_id) == f"wechat_official-report-u{user_id}-"
    assert export_owner_prefix("wechat_official", "articles", user_id) == f"wechat_official-articles-u{user_id}-"
    assert validate_owned_export_file_name(f"xhs-notes-u{user_id}-export.csv", user_id) == f"xhs-notes-u{user_id}-export.csv"
    assert validate_owned_export_file_name(f"xhs-report-u{user_id}-report.json", user_id) == f"xhs-report-u{user_id}-report.json"
    assert validate_owned_export_file_name(f"wechat_official-notes-u{user_id}-export.csv", user_id) == f"wechat_official-notes-u{user_id}-export.csv"
    assert validate_owned_export_file_name(f"wechat_official-report-u{user_id}-report.json", user_id) == f"wechat_official-report-u{user_id}-report.json"
    assert validate_owned_export_file_name(f"wechat_official-articles-u{user_id}-export.csv", user_id) == f"wechat_official-articles-u{user_id}-export.csv"


def test_accepts_wechat_official_user_owned_export_policy_examples():
    name = f"{export_owner_prefix('wechat_official', 'articles', 7)}20260701120000.csv"

    assert validate_owned_export_file_name(name, 7) == name


@pytest.mark.parametrize(
    "factory,platform,kind",
    [
        (asset_owner_prefix, "unknown", "upload"),
        (asset_owner_prefix, "xhs/evil", "upload"),
        (asset_owner_prefix, "xhs", "notes"),
        (export_owner_prefix, "unknown", "notes"),
        (export_owner_prefix, "wechat_official", "asset"),
    ],
)
def test_invalid_platform_or_owner_kind_does_not_generate_prefix(factory, platform, kind):
    with pytest.raises(ValueError):
        factory(platform, kind, 7)


def test_rejects_cross_user_and_unsafe_export_names():
    with pytest.raises(ValueError):
        validate_owned_export_file_name("xhs-notes-u8-export.csv", 7)

    with pytest.raises(ValueError):
        validate_owned_export_file_name("nested/xhs-notes-u7-export.csv", 7)

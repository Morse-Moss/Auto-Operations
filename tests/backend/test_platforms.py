from fastapi.testclient import TestClient

from backend.app.core.platforms import PlatformId, get_platform, get_platforms
from backend.app.main import app
from backend.app.services.platform_service import get_platform_detail


client = TestClient(app)


def test_xhs_platform_registry_exposes_enriched_metadata_and_required_capabilities():
    xhs = get_platform(PlatformId.XHS)
    payload = xhs.to_dict()
    capabilities = {item["key"]: item for item in payload["capabilities"]}

    assert payload["id"] == "xhs"
    assert payload["name_cn"] == "小红书"
    assert payload["name_en"] == "XiaoHongShu"
    assert payload["enabled"] is True
    assert payload["status"] == "enabled"
    assert payload["release_stage"] == "enabled"
    assert payload["region"] == "cn"
    assert payload["platform_type"] == "hybrid"
    assert payload["default_route"] == "/platforms/xhs/dashboard"
    assert payload["adapter_key"] == "xhs"
    assert payload["risk_level"] == "high"
    assert payload["auth_modes"] == ["cookie", "qr_login"]
    assert payload["accent_color"] == "#ff2442"
    assert payload["icon"] == "xhs"

    assert "account.manage" in capabilities
    assert "publish.real_publish" in capabilities
    assert "engagement.reply_execute" in capabilities
    assert "workflow.auto_ops" in capabilities


def test_xhs_reply_execute_capability_is_blocked_high_risk_and_requires_confirmation():
    xhs = get_platform("xhs")
    payload = xhs.to_dict()
    capabilities = {item["key"]: item for item in payload["capabilities"]}

    assert capabilities["engagement.reply_execute"]["status"] == "blocked"
    assert capabilities["engagement.reply_execute"]["risk"] == "high"
    assert capabilities["engagement.reply_execute"]["requires_confirmation"] is True



def test_planned_platform_status_uses_canonical_release_stage_and_legacy_status_alias():
    douyin = get_platform(PlatformId.DOUYIN)
    payload = douyin.to_dict()

    assert payload["enabled"] is False
    assert payload["release_stage"] == "planned"
    assert payload["status"] == "coming_soon"



def test_get_platform_accepts_platform_id_or_string_and_unknown_string_raises_keyerror():
    from_enum = get_platform(PlatformId.XHS)
    from_string = get_platform("xhs")

    assert from_enum is from_string

    try:
        get_platform("unknown")
    except KeyError as exc:
        assert exc.args == ("unknown",)
    else:
        raise AssertionError("expected KeyError for unknown platform")



def test_platform_service_returns_platform_detail_and_raises_for_unknown_platform():
    detail = get_platform_detail("xhs")

    assert detail["id"] == "xhs"
    assert detail["default_route"] == "/platforms/xhs/dashboard"
    assert detail["capabilities"]

    try:
        get_platform_detail("unknown")
    except KeyError as exc:
        assert exc.args == ("unknown",)
    else:
        raise AssertionError("expected KeyError for unknown platform")



def test_platform_registry_list_still_contains_xhs_and_douyin_entries():
    platforms = get_platforms()
    by_id = {platform.id: platform for platform in platforms}

    assert by_id[PlatformId.XHS].enabled is True
    assert by_id[PlatformId.DOUYIN].enabled is False



def test_platform_registry_list_endpoint_preserves_legacy_fields_and_exposes_enriched_fields():
    response = client.get("/api/platforms")
    assert response.status_code == 200

    payload = response.json()
    xhs = next(item for item in payload["items"] if item["id"] == "xhs")
    douyin = next(item for item in payload["items"] if item["id"] == "douyin")

    assert xhs["id"] == "xhs"
    assert xhs["name_cn"] == "小红书"
    assert xhs["name_en"] == "XiaoHongShu"
    assert xhs["enabled"] is True
    assert xhs["status"] == "enabled"
    assert xhs["accent_color"] == "#ff2442"
    assert xhs["icon"] == "xhs"

    assert xhs["release_stage"] == "enabled"
    assert xhs["region"] == "cn"
    assert xhs["platform_type"] == "hybrid"
    assert xhs["default_route"] == "/platforms/xhs/dashboard"
    assert xhs["adapter_key"] == "xhs"
    assert xhs["risk_level"] == "high"
    assert xhs["auth_modes"] == ["cookie", "qr_login"]
    assert isinstance(xhs["capabilities"], list)
    assert xhs["capabilities"]

    assert douyin["enabled"] is False
    assert douyin["release_stage"] == "planned"
    assert douyin["status"] == "coming_soon"



def test_platform_detail_endpoint_returns_platform_and_404_for_unknown():
    response = client.get("/api/platforms/xhs")
    assert response.status_code == 200
    assert response.json()["id"] == "xhs"

    missing = client.get("/api/platforms/unknown")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "platform_not_found"}

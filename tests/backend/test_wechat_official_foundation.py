from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.core.platforms import PlatformId, get_platform
from backend.app.main import app


client = TestClient(app)


def _capabilities_by_key(platform_payload: dict) -> dict[str, dict]:
    return {item["key"]: item for item in platform_payload["capabilities"]}


def test_wechat_official_registry_is_beta_enabled_foundation_workspace():
    payload = get_platform(PlatformId.WECHAT_OFFICIAL).to_dict()

    assert payload["id"] == "wechat_official"
    assert payload["name_cn"] == "公众号"
    assert payload["name_en"] == "WeChat Official"
    assert payload["enabled"] is True
    assert payload["release_stage"] == "beta"
    assert payload["status"] == "beta"
    assert payload["region"] == "cn"
    assert payload["platform_type"] == "content"
    assert payload["default_route"] == "/platforms/wechat-official/dashboard"
    assert payload["adapter_key"] == "wechat_official"
    assert payload["risk_level"] == "medium"
    assert payload["auth_modes"] == ["none"]
    assert payload["accent_color"] == "#0a9b57"
    assert payload["icon"] == "wechat_official"


def test_wechat_official_capabilities_are_planned_or_blocked_and_publish_is_fail_closed():
    payload = get_platform("wechat_official").to_dict()
    capabilities = _capabilities_by_key(payload)

    assert capabilities["account.manage"] == {
        "key": "account.manage",
        "status": "planned",
        "risk": "medium",
        "requires_confirmation": False,
        "notes": "公众号账号配置待 GitHub 开源系统调研和微信官方 API 策略确认后接入；本轮不开放凭据输入。",
    }
    assert capabilities["content.library"]["status"] == "planned"
    assert capabilities["content.rewrite"]["status"] == "planned"
    assert capabilities["publish.dry_run"]["status"] == "planned"
    assert capabilities["publish.real_publish"] == {
        "key": "publish.real_publish",
        "status": "blocked",
        "risk": "high",
        "requires_confirmation": True,
        "notes": "公众号群发发布属于高风险动作；正式 QA、dry-run 和动作级确认机制完成前保持阻断。",
    }


def test_platform_registry_endpoint_exposes_wechat_official_beta_metadata():
    response = client.get("/api/platforms")

    assert response.status_code == 200
    payload = response.json()
    wechat = next(item for item in payload["items"] if item["id"] == "wechat_official")

    assert wechat["enabled"] is True
    assert wechat["release_stage"] == "beta"
    assert wechat["status"] == "beta"
    assert wechat["default_route"] == "/platforms/wechat-official/dashboard"
    assert wechat["adapter_key"] == "wechat_official"
    assert wechat["auth_modes"] == ["none"]
    assert _capabilities_by_key(wechat)["publish.real_publish"]["status"] == "blocked"


def test_wechat_official_adapter_reports_local_foundation_status_without_external_integration():
    from backend.app.adapters.wechat_official import WechatOfficialAdapter

    adapter = WechatOfficialAdapter()
    status = adapter.get_status()

    assert adapter.supported_capabilities == set()
    assert status == {
        "platform_id": "wechat_official",
        "external_integration_enabled": False,
        "stage": "foundation_ready",
        "blocked_actions": [
            "真实授权",
            "素材上传",
            "草稿同步",
            "预览发送",
            "群发发布",
        ],
    }


def test_wechat_official_adapter_blocks_external_integration_attempts():
    from backend.app.adapters.wechat_official import WechatOfficialAdapter, WechatOfficialIntegrationDisabledError

    adapter = WechatOfficialAdapter()

    try:
        adapter.assert_external_integration_enabled("publish.real_publish")
    except WechatOfficialIntegrationDisabledError as exc:
        assert str(exc) == "微信公众号外部接入尚未启用：publish.real_publish 已被阻断。"
        assert exc.capability_key == "publish.real_publish"
    else:
        raise AssertionError("expected WechatOfficialIntegrationDisabledError")


def test_wechat_official_overview_api_returns_foundation_status_and_research_gate():
    response = client.get("/api/wechat-official/overview")

    assert response.status_code == 200
    payload = response.json()

    assert payload["platform_id"] == "wechat_official"
    assert payload["stage"] == "foundation_ready"
    assert payload["external_integration_enabled"] is False
    assert payload["research_required_before_integration"] is True
    assert payload["research_topics"] == [
        "GitHub 微信公众号开源系统架构调研",
        "微信官方草稿箱、素材、群发、预览 API 能力边界确认",
        "凭据保存与加密策略确认",
        "真实群发风险与 QA 流程确认",
    ]
    assert payload["blocked_actions"] == [
        "真实授权",
        "素材上传",
        "草稿同步",
        "预览发送",
        "群发发布",
    ]

    capabilities = {item["key"]: item for item in payload["capabilities"]}
    assert capabilities["account.manage"] == {
        "key": "account.manage",
        "label": "账号配置",
        "status": "planned",
        "message": "正式接入前不开放 AppID/AppSecret 配置。",
    }
    assert capabilities["publish.real_publish"] == {
        "key": "publish.real_publish",
        "label": "群发发布",
        "status": "blocked",
        "message": "高风险动作，正式 QA、dry-run 和动作级确认机制完成前保持阻断。",
    }

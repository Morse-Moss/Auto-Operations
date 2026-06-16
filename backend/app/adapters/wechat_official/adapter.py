from __future__ import annotations


BLOCKED_ACTIONS = (
    "真实授权",
    "素材上传",
    "草稿同步",
    "预览发送",
    "群发发布",
)


class WechatOfficialIntegrationDisabledError(RuntimeError):
    def __init__(self, capability_key: str) -> None:
        self.capability_key = capability_key
        super().__init__(f"微信公众号外部接入尚未启用：{capability_key} 已被阻断。")


class WechatOfficialAdapter:
    supported_capabilities: frozenset[str] = frozenset()

    def get_status(self) -> dict:
        return {
            "platform_id": "wechat_official",
            "external_integration_enabled": False,
            "stage": "foundation_ready",
            "blocked_actions": list(BLOCKED_ACTIONS),
        }

    def assert_external_integration_enabled(self, capability_key: str) -> None:
        raise WechatOfficialIntegrationDisabledError(capability_key)

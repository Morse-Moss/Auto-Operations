from __future__ import annotations

from fastapi import APIRouter

from backend.app.adapters.wechat_official import WechatOfficialAdapter

router = APIRouter(prefix="/wechat-official", tags=["wechat-official"])


RESEARCH_TOPICS = [
    "GitHub 微信公众号开源系统架构调研",
    "微信官方草稿箱、素材、群发、预览 API 能力边界确认",
    "凭据保存与加密策略确认",
    "真实群发风险与 QA 流程确认",
]

CAPABILITY_OVERVIEW = [
    {
        "key": "account.manage",
        "label": "账号配置",
        "status": "planned",
        "message": "正式接入前不开放 AppID/AppSecret 配置。",
    },
    {
        "key": "content.library",
        "label": "图文内容库",
        "status": "planned",
        "message": "待调研后设计公众号图文内容模型。",
    },
    {
        "key": "content.rewrite",
        "label": "文章改写",
        "status": "planned",
        "message": "待内容模型确认后接入公众号文章改写。",
    },
    {
        "key": "publish.dry_run",
        "label": "发布 dry-run",
        "status": "planned",
        "message": "待草稿箱、素材和群发 API 能力确认后设计。",
    },
    {
        "key": "publish.real_publish",
        "label": "群发发布",
        "status": "blocked",
        "message": "高风险动作，正式 QA、dry-run 和动作级确认机制完成前保持阻断。",
    },
]


@router.get("/overview")
def get_wechat_official_overview() -> dict:
    adapter_status = WechatOfficialAdapter().get_status()
    return {
        "platform_id": "wechat_official",
        "stage": adapter_status["stage"],
        "external_integration_enabled": adapter_status["external_integration_enabled"],
        "research_required_before_integration": True,
        "research_topics": RESEARCH_TOPICS,
        "capabilities": CAPABILITY_OVERVIEW,
        "blocked_actions": adapter_status["blocked_actions"],
    }

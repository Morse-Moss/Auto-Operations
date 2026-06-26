from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.app.core.deps import get_current_user
from backend.app.models import User

router = APIRouter(prefix="/wechat-official/browser-fallback", tags=["wechat-official"])


class WechatOfficialBrowserFallbackPlanRequest(BaseModel):
    url: str = Field(min_length=1)
    reason: str = "manual_verification_required"


@router.post("/plan")
def create_browser_fallback_plan(payload: WechatOfficialBrowserFallbackPlanRequest, current_user: User = Depends(get_current_user)):
    del current_user
    return {
        "mode": "manual_browser_verification",
        "url": payload.url,
        "reason": payload.reason,
        "safe_to_automate": False,
        "retry_policy": "do_not_auto_retry",
        "blocked_actions": ["captcha_bypass", "risk_control_evasion", "high_frequency_retry"],
        "steps": [
            {
                "key": "open_browser",
                "label": "在浏览器打开文章",
                "instruction": "使用当前登录态浏览器打开该公众号文章 URL，不在后台批量重试。",
            },
            {
                "key": "manual_verify",
                "label": "完成人工验证",
                "instruction": "如果页面要求验证，请由用户完成人工验证；系统不会实现验证码绕过或风控规避。",
            },
            {
                "key": "retry_import",
                "label": "回到系统重试导入/补全",
                "instruction": "验证完成后回到内容库或发现页重试导入/补全，仍然保持低频串行。",
            },
        ],
    }

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class WechatOfficialBackendLoginCompleteRequest(BaseModel):
    cookie: str = Field(min_length=1)
    token: str = Field(min_length=1)
    auth_key: str = Field(min_length=1)
    biz: str = ""
    nickname: str = ""
    user_agent: str = ""
    expires_at: datetime | None = None


class WechatOfficialCredentialImportRequest(BaseModel):
    biz: str = Field(min_length=1)
    uin: str = Field(min_length=1)
    key: str = Field(min_length=1)
    pass_ticket: str = Field(min_length=1)
    wap_sid2: str = Field(min_length=1)
    appmsg_token: str = Field(min_length=1)
    cookie: str = Field(min_length=1)
    timestamp: int | str
    nickname: str = ""
    article_url: str = ""
    captured_at: str | None = None


class WechatOfficialCredentialValidateRequest(BaseModel):
    biz: str | None = None
    uin: str | None = None
    key: str | None = None
    pass_ticket: str | None = None
    wap_sid2: str | None = None
    appmsg_token: str | None = None
    cookie: str | None = None
    timestamp: int | str | None = None
    nickname: str | None = None
    article_url: str | None = None
    captured_at: str | None = None

    def as_payload(self) -> dict[str, Any]:
        return self.model_dump()


class WechatOfficialProxyTestRequest(BaseModel):
    request_type: str = "public"
    success: bool = True
    error_message: str = ""


class WechatOfficialSearchAccountsRequest(BaseModel):
    backend_session_id: int
    keyword: str = Field(min_length=1)
    upstream_payload: dict[str, Any] = Field(default_factory=dict)


class WechatOfficialArticleSyncRequest(BaseModel):
    backend_session_id: int
    account_id: int | None = None
    keyword: str = ""
    limit: int = Field(default=50, ge=0, le=100)
    upstream_payload: dict[str, Any] = Field(default_factory=dict)


class WechatOfficialArticleSnapshotRequest(BaseModel):
    html: str = ""


class WechatOfficialArticleMetricsRequest(BaseModel):
    credential_id: int
    html: str | None = None
    cgi_data: dict[str, Any] | None = None


class WechatOfficialArticleCommentsRequest(BaseModel):
    comments_payload: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=50, ge=1, le=100)


class WechatOfficialRecommendationUpdateRequest(BaseModel):
    recommendation_status: str | None = None
    low_follower_evidence: bool | None = None
    low_follower_note: str | None = None
    business_direction: str | None = None
    title_type: str | None = None
    article_type_label: str | None = None
    viral_factors: list[str] | None = None
    core_insight: str | None = None
    case_info: dict[str, Any] | None = None
    customer_conversion_method: str | None = None


class WechatOfficialCreateDraftRequest(BaseModel):
    rewrite_style: str = "保持原文结构"
    target_audience: str = "公众号读者"
    call_to_action: str = "关注后续更新"


class WechatOfficialDraftDryRunRequest(BaseModel):
    title: str | None = None
    body: str | None = None

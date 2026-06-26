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


class WechatOfficialRedfoxConfigRequest(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    base_url: str | None = None
    api_key: str | None = None


class WechatOfficialRedfoxKeywordCollectRequest(BaseModel):
    keyword: str = Field(min_length=1)
    pages: int = Field(default=1, ge=1, le=3)
    target_count: int | None = Field(default=None, ge=1, le=50)
    max_pages: int | None = Field(default=None, ge=1, le=5)
    sort_type: str = "_4"
    min_read_count: int = Field(default=100000, ge=0)
    save_snapshot: bool = True


class WechatOfficialRedfoxAccountCollectRequest(BaseModel):
    account: str = Field(min_length=1)
    account_name: str = ""
    pages: int = Field(default=1, ge=1, le=3)
    sort_type: str = "_4"
    publish_time_start: str | None = None
    publish_time_end: str | None = None
    min_read_count: int = Field(default=100000, ge=0)
    save_snapshot: bool = True


class WechatOfficialRedfoxUrlImportRequest(BaseModel):
    url: str = Field(min_length=1)
    min_read_count: int = Field(default=100000, ge=0)
    save_snapshot: bool = True


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
    credential_id: int
    comments_payload: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=50, ge=1, le=100)


class WechatOfficialContentExportRequest(BaseModel):
    article_ids: list[int] = Field(min_length=1)
    format: str = "json"


class WechatOfficialContentAutoRefreshRequest(BaseModel):
    article_ids: list[int] = Field(min_length=1)


class WechatOfficialRecommendationUpdateRequest(BaseModel):
    recommendation_status: str | None = None
    pool_status: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    is_favorite: bool | None = None
    read_status: str | None = None
    low_follower_evidence: bool | str | None = None
    low_follower_note: str | None = None
    business_direction: str | None = None
    title_type: str | None = None
    article_type_label: str | None = None
    viral_factors: list[str] | None = None
    core_insight: str | None = None
    case_info: dict[str, Any] | None = None
    customer_conversion_method: str | None = None
    hotspot_breakdown: dict[str, Any] | None = None
    draft_template_key: str | None = None
    analysis_mode: str | None = None
    analysis_updated_at: str | None = None


class WechatOfficialHotspotAnalyzeRequest(BaseModel):
    mode: str = "auto"
    instruction: str = ""


class WechatOfficialCreateDraftRequest(BaseModel):
    rewrite_style: str = "保持原文结构"
    target_audience: str = "公众号读者"
    call_to_action: str = "关注后续更新"
    template_key: str | None = None
    template_name: str | None = None
    template_instruction: str | None = None
    opening_angle: str | None = None


class WechatOfficialDraftDryRunRequest(BaseModel):
    title: str | None = None
    body: str | None = None

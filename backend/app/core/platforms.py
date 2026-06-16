from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List


class PlatformId(str, Enum):
    XHS = "xhs"
    DOUYIN = "douyin"
    KUAISHOU = "kuaishou"
    BILIBILI = "bilibili"
    WECHAT_CHANNELS = "wechat_channels"
    WECHAT_OFFICIAL = "wechat_official"
    WEIBO = "weibo"
    XIANYU = "xianyu"
    TAOBAO = "taobao"


class PlatformRegion(str, Enum):
    CN = "cn"
    GLOBAL = "global"


class ReleaseStage(str, Enum):
    ENABLED = "enabled"
    BETA = "beta"
    PLANNED = "planned"
    UNAVAILABLE = "unavailable"


class PlatformType(str, Enum):
    CONTENT = "content"
    SOCIAL = "social"
    COMMERCE = "commerce"
    HYBRID = "hybrid"


class AuthMode(str, Enum):
    COOKIE = "cookie"
    QR_LOGIN = "qr_login"
    OAUTH = "oauth"
    MANUAL = "manual"
    NONE = "none"


class CapabilityStatus(str, Enum):
    AVAILABLE = "available"
    PARTIAL = "partial"
    PLANNED = "planned"
    BLOCKED = "blocked"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CapabilityKey(str, Enum):
    ACCOUNT_MANAGE = "account.manage"
    ACCOUNT_LOGIN_COOKIE = "account.login_cookie"
    ACCOUNT_LOGIN_QR = "account.login_qr"
    CONTENT_DISCOVER = "content.discover"
    CONTENT_CRAWL_DETAIL = "content.crawl_detail"
    CONTENT_LIBRARY = "content.library"
    CONTENT_REWRITE = "content.rewrite"
    ASSET_IMAGE_GENERATE = "asset.image_generate"
    ASSET_VIDEO_GENERATE = "asset.video_generate"
    PUBLISH_CREATE_JOB = "publish.create_job"
    PUBLISH_SCHEDULE = "publish.schedule"
    PUBLISH_DRY_RUN = "publish.dry_run"
    PUBLISH_REAL_PUBLISH = "publish.real_publish"
    MONITORING_KEYWORD = "monitoring.keyword"
    MONITORING_COMPETITOR = "monitoring.competitor"
    ENGAGEMENT_COMMENT_READ = "engagement.comment_read"
    ENGAGEMENT_REPLY_SUGGEST = "engagement.reply_suggest"
    ENGAGEMENT_REPLY_EXECUTE = "engagement.reply_execute"
    WORKFLOW_AUTO_OPS = "workflow.auto_ops"


@dataclass(frozen=True)
class PlatformCapability:
    key: CapabilityKey
    status: CapabilityStatus
    risk: RiskLevel
    requires_confirmation: bool
    notes: str

    def to_dict(self) -> dict:
        return {
            "key": self.key.value,
            "status": self.status.value,
            "risk": self.risk.value,
            "requires_confirmation": self.requires_confirmation,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class PlatformMeta:
    id: PlatformId
    name_cn: str
    name_en: str
    enabled: bool
    release_stage: ReleaseStage
    region: PlatformRegion
    platform_type: PlatformType
    accent_color: str
    icon: str
    default_route: str | None = None
    adapter_key: str | None = None
    risk_level: RiskLevel = RiskLevel.LOW
    auth_modes: list[AuthMode] = field(default_factory=list)
    capabilities: list[PlatformCapability] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.release_stage is ReleaseStage.PLANNED:
            return "coming_soon"
        return self.release_stage.value

    def to_dict(self) -> dict:
        return {
            "id": self.id.value,
            "name_cn": self.name_cn,
            "name_en": self.name_en,
            "enabled": self.enabled,
            "status": self.status,
            "release_stage": self.release_stage.value,
            "region": self.region.value,
            "platform_type": self.platform_type.value,
            "accent_color": self.accent_color,
            "icon": self.icon,
            "default_route": self.default_route,
            "adapter_key": self.adapter_key,
            "risk_level": self.risk_level.value,
            "auth_modes": [mode.value for mode in self.auth_modes],
            "capabilities": [capability.to_dict() for capability in self.capabilities],
        }


_XHS_CAPABILITIES = [
    PlatformCapability(CapabilityKey.ACCOUNT_MANAGE, CapabilityStatus.AVAILABLE, RiskLevel.MEDIUM, False, "已有账号矩阵能力"),
    PlatformCapability(CapabilityKey.ACCOUNT_LOGIN_COOKIE, CapabilityStatus.AVAILABLE, RiskLevel.HIGH, True, "Cookie 属敏感凭据"),
    PlatformCapability(CapabilityKey.ACCOUNT_LOGIN_QR, CapabilityStatus.AVAILABLE, RiskLevel.MEDIUM, False, "已有扫码登录路径"),
    PlatformCapability(CapabilityKey.CONTENT_DISCOVER, CapabilityStatus.AVAILABLE, RiskLevel.MEDIUM, False, "已有笔记发现/关键词能力"),
    PlatformCapability(CapabilityKey.CONTENT_CRAWL_DETAIL, CapabilityStatus.AVAILABLE, RiskLevel.MEDIUM, False, "受接口和账号状态影响"),
    PlatformCapability(CapabilityKey.CONTENT_LIBRARY, CapabilityStatus.AVAILABLE, RiskLevel.LOW, False, "已有内容库能力"),
    PlatformCapability(CapabilityKey.CONTENT_REWRITE, CapabilityStatus.AVAILABLE, RiskLevel.LOW, False, "已有 AI 改写能力"),
    PlatformCapability(CapabilityKey.ASSET_IMAGE_GENERATE, CapabilityStatus.AVAILABLE, RiskLevel.LOW, False, "已有图片工坊能力"),
    PlatformCapability(CapabilityKey.ASSET_VIDEO_GENERATE, CapabilityStatus.PLANNED, RiskLevel.MEDIUM, False, "视频工坊存在但生成能力需单独验证"),
    PlatformCapability(CapabilityKey.PUBLISH_CREATE_JOB, CapabilityStatus.AVAILABLE, RiskLevel.MEDIUM, False, "已有发布任务能力"),
    PlatformCapability(CapabilityKey.PUBLISH_SCHEDULE, CapabilityStatus.AVAILABLE, RiskLevel.MEDIUM, False, "已有排期/任务能力"),
    PlatformCapability(CapabilityKey.PUBLISH_DRY_RUN, CapabilityStatus.AVAILABLE, RiskLevel.LOW, False, "真实发布前应优先 dry-run"),
    PlatformCapability(CapabilityKey.PUBLISH_REAL_PUBLISH, CapabilityStatus.PARTIAL, RiskLevel.HIGH, True, "真实账号发布必须显式授权"),
    PlatformCapability(CapabilityKey.MONITORING_KEYWORD, CapabilityStatus.AVAILABLE, RiskLevel.MEDIUM, False, "已有关键词监控能力"),
    PlatformCapability(CapabilityKey.MONITORING_COMPETITOR, CapabilityStatus.AVAILABLE, RiskLevel.MEDIUM, False, "已有竞品/监控模型"),
    PlatformCapability(CapabilityKey.ENGAGEMENT_COMMENT_READ, CapabilityStatus.PARTIAL, RiskLevel.MEDIUM, False, "评论读取受接口限制"),
    PlatformCapability(CapabilityKey.ENGAGEMENT_REPLY_SUGGEST, CapabilityStatus.PLANNED, RiskLevel.LOW, False, "建议回复可做，执行另议"),
    PlatformCapability(CapabilityKey.ENGAGEMENT_REPLY_EXECUTE, CapabilityStatus.BLOCKED, RiskLevel.HIGH, True, "第一轮明确不开放自动评论"),
    PlatformCapability(CapabilityKey.WORKFLOW_AUTO_OPS, CapabilityStatus.AVAILABLE, RiskLevel.HIGH, True, "自动运营属于高风险链路"),
]


_WECHAT_OFFICIAL_CAPABILITIES = [
    PlatformCapability(
        key=CapabilityKey.ACCOUNT_MANAGE,
        status=CapabilityStatus.PLANNED,
        risk=RiskLevel.MEDIUM,
        requires_confirmation=False,
        notes="公众号账号配置待 GitHub 开源系统调研和微信官方 API 策略确认后接入；本轮不开放凭据输入。",
    ),
    PlatformCapability(
        key=CapabilityKey.CONTENT_LIBRARY,
        status=CapabilityStatus.PLANNED,
        risk=RiskLevel.LOW,
        requires_confirmation=False,
        notes="公众号图文内容库待正式接入设计后实现；本轮只展示平台骨架状态。",
    ),
    PlatformCapability(
        key=CapabilityKey.CONTENT_REWRITE,
        status=CapabilityStatus.PLANNED,
        risk=RiskLevel.LOW,
        requires_confirmation=False,
        notes="公众号文章改写待内容模型确认后实现；本轮不生成或同步真实公众号草稿。",
    ),
    PlatformCapability(
        key=CapabilityKey.PUBLISH_DRY_RUN,
        status=CapabilityStatus.PLANNED,
        risk=RiskLevel.MEDIUM,
        requires_confirmation=False,
        notes="公众号发布 dry-run 待草稿箱、素材和群发 API 能力确认后设计；本轮不执行发布模拟。",
    ),
    PlatformCapability(
        key=CapabilityKey.PUBLISH_REAL_PUBLISH,
        status=CapabilityStatus.BLOCKED,
        risk=RiskLevel.HIGH,
        requires_confirmation=True,
        notes="公众号群发发布属于高风险动作；正式 QA、dry-run 和动作级确认机制完成前保持阻断。",
    ),
]


_PLATFORMS: List[PlatformMeta] = [
    PlatformMeta(
        id=PlatformId.XHS,
        name_cn="小红书",
        name_en="XiaoHongShu",
        enabled=True,
        release_stage=ReleaseStage.ENABLED,
        region=PlatformRegion.CN,
        platform_type=PlatformType.HYBRID,
        accent_color="#ff2442",
        icon="xhs",
        default_route="/platforms/xhs/dashboard",
        adapter_key="xhs",
        risk_level=RiskLevel.HIGH,
        auth_modes=[AuthMode.COOKIE, AuthMode.QR_LOGIN],
        capabilities=_XHS_CAPABILITIES,
    ),
    PlatformMeta(
        id=PlatformId.DOUYIN,
        name_cn="抖音",
        name_en="Douyin",
        enabled=False,
        release_stage=ReleaseStage.PLANNED,
        region=PlatformRegion.CN,
        platform_type=PlatformType.CONTENT,
        accent_color="#111111",
        icon="douyin",
        risk_level=RiskLevel.MEDIUM,
        auth_modes=[AuthMode.NONE],
    ),
    PlatformMeta(
        id=PlatformId.KUAISHOU,
        name_cn="快手",
        name_en="Kuaishou",
        enabled=False,
        release_stage=ReleaseStage.PLANNED,
        region=PlatformRegion.CN,
        platform_type=PlatformType.CONTENT,
        accent_color="#ff7a00",
        icon="kuaishou",
        risk_level=RiskLevel.MEDIUM,
        auth_modes=[AuthMode.NONE],
    ),
    PlatformMeta(
        id=PlatformId.BILIBILI,
        name_cn="哔哩哔哩",
        name_en="Bilibili",
        enabled=False,
        release_stage=ReleaseStage.PLANNED,
        region=PlatformRegion.CN,
        platform_type=PlatformType.CONTENT,
        accent_color="#00a1d6",
        icon="bilibili",
        risk_level=RiskLevel.MEDIUM,
        auth_modes=[AuthMode.NONE],
    ),
    PlatformMeta(
        id=PlatformId.WECHAT_CHANNELS,
        name_cn="视频号",
        name_en="WeChat Channels",
        enabled=False,
        release_stage=ReleaseStage.PLANNED,
        region=PlatformRegion.CN,
        platform_type=PlatformType.SOCIAL,
        accent_color="#07c160",
        icon="wechat_channels",
        risk_level=RiskLevel.MEDIUM,
        auth_modes=[AuthMode.NONE],
    ),
    PlatformMeta(
        id=PlatformId.WECHAT_OFFICIAL,
        name_cn="公众号",
        name_en="WeChat Official",
        enabled=True,
        release_stage=ReleaseStage.BETA,
        region=PlatformRegion.CN,
        platform_type=PlatformType.CONTENT,
        accent_color="#0a9b57",
        icon="wechat_official",
        default_route="/platforms/wechat-official/dashboard",
        adapter_key="wechat_official",
        risk_level=RiskLevel.MEDIUM,
        auth_modes=[AuthMode.NONE],
        capabilities=_WECHAT_OFFICIAL_CAPABILITIES,
    ),
    PlatformMeta(
        id=PlatformId.WEIBO,
        name_cn="微博",
        name_en="Weibo",
        enabled=False,
        release_stage=ReleaseStage.PLANNED,
        region=PlatformRegion.CN,
        platform_type=PlatformType.SOCIAL,
        accent_color="#e6162d",
        icon="weibo",
        risk_level=RiskLevel.MEDIUM,
        auth_modes=[AuthMode.NONE],
    ),
    PlatformMeta(
        id=PlatformId.XIANYU,
        name_cn="闲鱼",
        name_en="Xianyu",
        enabled=False,
        release_stage=ReleaseStage.PLANNED,
        region=PlatformRegion.CN,
        platform_type=PlatformType.COMMERCE,
        accent_color="#ffe100",
        icon="xianyu",
        risk_level=RiskLevel.MEDIUM,
        auth_modes=[AuthMode.NONE],
    ),
    PlatformMeta(
        id=PlatformId.TAOBAO,
        name_cn="淘宝",
        name_en="Taobao",
        enabled=False,
        release_stage=ReleaseStage.PLANNED,
        region=PlatformRegion.CN,
        platform_type=PlatformType.COMMERCE,
        accent_color="#ff5000",
        icon="taobao",
        risk_level=RiskLevel.MEDIUM,
        auth_modes=[AuthMode.NONE],
    ),
]


def get_platforms() -> List[PlatformMeta]:
    return list(_PLATFORMS)


def get_platform(platform_id: PlatformId | str) -> PlatformMeta:
    lookup = platform_id.value if isinstance(platform_id, PlatformId) else platform_id
    for platform in _PLATFORMS:
        if platform.id.value == lookup:
            return platform
    raise KeyError(lookup)

# Platform Adapter Contract Design：XHS-first 安全迁移合同

## 1. 背景与问题

当前项目已经完成第一轮多平台运营底座骨架：

- `backend/app/core/platforms.py` 已经成为平台事实源，包含 `PlatformMeta`、`CapabilityKey`、`PlatformCapability`、`ReleaseStage`、`RiskLevel` 等声明。
- `GET /api/platforms` 和 `GET /api/platforms/{platform_id}` 已经能返回 9 个平台及 XHS 能力矩阵。
- 前端平台中心已经能消费 enriched `PlatformMeta`，XHS 进入 dashboard，planned 平台进入 Coming Soon。

但当前系统仍然存在一个核心缺口：

> Registry 已经声明“平台能做什么、风险是什么”，但真实执行路径还没有统一经过能力门禁和 adapter 合同。

现状中，XHS 相关执行仍散落在多处：

- `backend/app/adapters/xhs/` 包装 PC、Creator、登录等能力，但不是统一平台 adapter 合同。
- `backend/app/api/platforms/xhs/*.py` 仍直接承载 XHS 路由逻辑。
- `backend/app/api/publish.py`、`backend/app/services/scheduler_service.py`、`backend/app/api/auto_tasks.py` 涉及发布、后台任务和自动运营，高风险动作需要统一门禁。
- `backend/app/api/platforms/xhs/pc.py` 中存在搜索、详情、评论等 payload normalization helper，后续 service 复用时容易形成 route 私有 helper 反向依赖。
- Huitun 当前是 XHS 关键词来源能力，不应被误升级为顶层平台工作区。

如果直接接抖音、视频号或其它平台，系统会重新回到：

```text
if platform == "xhs": ...
if platform == "douyin": ...
if platform == "wechat_channels": ...
```

这会让账号、内容、发布、监控、任务、错误处理和风险确认散落在 API 和页面里，长期不可维护。

因此下一轮必须先定义 Platform Adapter Contract。

## 2. 设计结论

第一轮不要做“多平台全量抽象”，而是做 **XHS-first 的安全迁移合同**。

目标不是马上接入真实新平台，而是先把现有 XHS 能力纳入统一边界：

```text
Registry / Policy
  ↓
Orchestration / Domain Contract
  ↓
Concrete Adapter
  ↓
Existing XHS SDK / signature layer
```

核心判断：

1. `backend/app/core/platforms.py` 继续作为平台事实源。
2. 新增 CapabilityGate，把能力、风险、确认、账号、限流等规则变成执行前强制门禁。
3. 新增 Contract DTO / Result / Error，把 XHS 当前 tuple / raw dict / RuntimeError 语义统一成稳定结果。
4. 新增 XHS Facade，包装现有 `backend/app/adapters/xhs/`，但不修改 `apis/`、`xhs_utils/`、`static/`。
5. 旧 API 继续兼容，未来逐步委托到合同服务，不要求前端一次性迁移。
6. planned 平台继续 fail closed，不接真实新平台。
7. Huitun 固定为 IntegrationSource / KeywordSourceProvider，不是 PlatformAdapter。

## 3. 目标

### 3.1 产品目标

让后续平台接入遵循同一套标准：

- 用户仍然看到统一平台工作区。
- 用户不需要理解 SDK、adapter、签名、Cookie、xsec token 等内部概念。
- 未开放平台只展示 Coming Soon，不出现半成品真实入口。
- 高风险动作有明确确认、dry-run、任务状态和用户反馈。

### 3.2 工程目标

- 把平台执行动作从 API route 中抽离到 adapter contract。
- 把 Registry 中的 capability/risk 声明变成执行门禁。
- 统一 adapter 返回值、错误分类、诊断、限流和重试语义。
- 保留旧接口和旧前端入口兼容。
- 为第二个平台做准备，但第一轮不接真实第二平台。

### 3.3 安全目标

- fail closed：能力缺失、平台 planned、adapter 缺失、确认缺失时默认拒绝。
- no bypass：API、scheduler、auto task、retry 必须走同一 gate。
- real publish 必须 dry-run-first + 动作级确认。
- engagement reply execute 当前继续 blocked。
- 明文 Cookie/token 不进入前端、日志、Task payload、Notification、diagnostics。

## 4. 非目标

本设计第一轮不做：

- 不接入任何真实新平台；抖音、快手、B站、视频号、公众号、微博、闲鱼、淘宝继续 planned/disabled/Coming Soon。
- 不把 legacy TypeScript CLI 当主系统入口。
- 不迁移 legacy SQLite 数据。
- 不修改 `apis/`、`xhs_utils/`、`static/` 的 SDK、签名或 JS 底层实现。
- 不做生产部署。
- 不改变本地端口约定：后端 `18081`，前端 `18080`。
- 不实现自动回复、自动点赞、关注、私信、验证码绕过、批量号池、高频自动化或风控规避。
- 不启用 `engagement.reply_execute`。
- 不把 Huitun 做成顶层平台工作区。
- 不做大规模数据库 schema migration。
- 不一次性重构前端 AppShell/router 为完整 capability-driven 多平台导航。
- 不把 `adapter_key`、SDK class、Cookie 字段名、`xsec_token`、Creator `fileIds`、`note_info`、`postTime`、raw payload 变成用户可见合同。
- 不让 Task retry、PublishJob retry、scheduler 或 auto task 成为绕过 CapabilityGate 的后门。
- 不在文档或 UI 中声称 dry-run 已经是完整产品能力，除非实现 no-side-effect path 并有测试证明。

## 5. 当前事实源

### 5.1 Platform Registry

`backend/app/core/platforms.py` 是当前平台事实源。

它已经定义：

- `PlatformId`
- `PlatformRegion`
- `ReleaseStage`
- `PlatformType`
- `AuthMode`
- `CapabilityStatus`
- `RiskLevel`
- `CapabilityKey`
- `PlatformCapability`
- `PlatformMeta`

当前注册平台：

| Platform ID | 状态 | 说明 |
|---|---|---|
| `xhs` | enabled | 当前唯一完整平台实现 |
| `douyin` | planned | 仅 Coming Soon |
| `kuaishou` | planned | 仅 Coming Soon |
| `bilibili` | planned | 仅 Coming Soon |
| `wechat_channels` | planned | 仅 Coming Soon |
| `wechat_official` | planned | 仅 Coming Soon |
| `weibo` | planned | 仅 Coming Soon |
| `xianyu` | planned | 仅 Coming Soon |
| `taobao` | planned | 仅 Coming Soon |

### 5.2 release_stage 与 status

`release_stage` 是 canonical 字段。

`status` 只是 legacy compatibility：

- `release_stage="enabled"` -> `status="enabled"`
- `release_stage="planned"` -> `status="coming_soon"`

新增执行逻辑不得依赖 `status`。

正确判断方式：

```text
release_stage + capability.status + capability.risk + capability.requires_confirmation
```

### 5.3 Capability Matrix

当前 XHS capability keys 已经是未来 adapter contract 的词汇表：

- `account.manage`
- `account.login_cookie`
- `account.login_qr`
- `content.discover`
- `content.crawl_detail`
- `content.library`
- `content.rewrite`
- `asset.image_generate`
- `asset.video_generate`
- `publish.create_job`
- `publish.schedule`
- `publish.dry_run`
- `publish.real_publish`
- `monitoring.keyword`
- `monitoring.competitor`
- `engagement.comment_read`
- `engagement.reply_suggest`
- `engagement.reply_execute`
- `workflow.auto_ops`

这些 key 是 product capability，不是 SDK 方法名。

例如：

- `content.discover` 可能对应搜索、关键词发现、笔记列表等多条路径。
- `publish.real_publish` 可能对应发布任务、素材上传、Creator post note、状态同步等编排。
- `workflow.auto_ops` 可能跨采集、生成、发布任务、监控等多个步骤。

## 6. 目标架构

### 6.1 三层边界

```text
Registry / Policy Layer
  - PlatformMeta
  - PlatformCapability
  - CapabilityGate
  - PlatformPolicyService

Orchestration / Domain Contract Layer
  - PublishOrchestrationService
  - ContentService / Mapper
  - TaskEvent / NotificationEvent
  - RetryDecision / DiagnosticEvent

Concrete Adapter Layer
  - XhsContractAdapter
  - XhsPcApiAdapter
  - XhsCreatorApiAdapter
  - XhsLoginAdapters
  - Existing SDK / signature layer
```

### 6.2 Registry / Policy Layer

职责：

- 读取平台事实源。
- 判断平台是否 enabled。
- 判断 capability 是否存在、可用、partial、planned、blocked。
- 判断是否 high risk。
- 判断是否需要 confirmation。
- 判断 adapter 是否存在。

不得：

- import XHS SDK。
- import `apis/`、`xhs_utils/`、`static/`。
- 执行真实平台动作。

### 6.3 Orchestration / Domain Contract Layer

职责：

- 管理主系统业务状态。
- 处理 PublishJob、PublishAsset、Task、Notification、Retry、MonitoringTarget、Note 持久化。
- 组装 PublishIntent、ContentQuery、ContentReference 等平台无关对象。
- 调用 CapabilityGate。
- 调用 adapter。
- 把 adapter result 映射为用户可理解的结果。

不得：

- 直接触碰明文凭据。
- 绕过 CapabilityGate。
- 直接 import fragile SDK/signature 层。

### 6.4 Concrete Adapter Layer

职责：

- 执行最小平台动作。
- 把平台返回转换为标准 DTO / Result / Error。
- 保留 redacted raw reference 供诊断。

XHS 第一版 adapter 只包装现有：

- `backend/app/adapters/xhs/pc_api_adapter.py`
- `backend/app/adapters/xhs/creator_api_adapter.py`
- `backend/app/adapters/xhs/pc_login_adapter.py`
- `backend/app/adapters/xhs/creator_login_adapter.py`

不得直接修改：

- `apis/`
- `xhs_utils/`
- `static/`

## 7. 合同模块

### 7.1 RegistryProvider

建议文件：`backend/app/platforms/contracts.py` 或 `backend/app/platforms/registry_provider.py`

接口：

```python
class RegistryProvider(Protocol):
    def get_meta(self, platform_id: str) -> PlatformMeta: ...
    def get_capability(self, platform_id: str, capability_key: str) -> PlatformCapability: ...
    def list_platforms(self) -> list[PlatformMeta]: ...
    def assert_enabled(self, platform_id: str) -> None: ...
```

职责：

- 只读 registry。
- 不知道具体 adapter。
- 不执行平台动作。

### 7.2 CapabilityGate / PlatformPolicyService

建议文件：`backend/app/platforms/policy.py`

接口：

```python
class PlatformPolicyService:
    def evaluate(self, context: CapabilityRequestContext) -> CapabilityDecision: ...
    def enforce(self, context: CapabilityRequestContext) -> CapabilityDecision: ...
```

职责：

- 执行 fail-closed 判断。
- 判断 high risk confirmation。
- 判断 dry-run-first。
- 判断 account platform/sub_type。
- 输出用户可理解的 blocked reason。

### 7.3 PlatformAdapterResolver

建议文件：`backend/app/platforms/resolver.py`

接口：

```python
class PlatformAdapterResolver:
    def resolve(self, platform_id: str, capability_key: str, context: CapabilityRequestContext) -> PlatformAdapter: ...
```

规则：

- 必须先通过 CapabilityGate。
- `adapter_key` 为空 -> blocked。
- resolver 找不到实现 -> blocked。
- adapter 声明支持但 registry blocked -> blocked。
- registry available 但 adapter 不支持 -> blocked。

### 7.4 CredentialProvider

建议文件：

- `backend/app/platforms/credentials.py`，如果保持纯平台合同。
- 或 `backend/app/services/credential_provider.py`，如果需要明显依赖 SQLAlchemy session。

接口：

```python
class CredentialProvider:
    def get_account_ref(self, account_id: int) -> PlatformAccountRef: ...
    def get_credentials(self, account_ref: PlatformAccountRef, required_auth_mode: str) -> PlatformCredentialContext: ...
    def validate_credential_status(self, account_ref: PlatformAccountRef) -> CapabilityDecision: ...
```

规则：

- 明文 Cookie/token 只在 adapter 最后一跳出现。
- route/service/scheduler 不直接拿明文。
- Task payload、Notification、diagnostics、frontend response 不允许包含完整凭据。

### 7.5 ContentDiscoveryAdapter

接口：

```python
class ContentDiscoveryAdapter(Protocol):
    supported_capabilities: set[str]

    def search_content(self, context: CapabilityRequestContext, query: ContentQuery) -> AdapterResultEnvelope[list[PlatformContentSummary]]: ...
    def get_content_detail(self, context: CapabilityRequestContext, reference: ContentReference) -> AdapterResultEnvelope[PlatformContentDetail]: ...
    def list_author_content(self, context: CapabilityRequestContext, query: ContentQuery) -> AdapterResultEnvelope[list[PlatformContentSummary]]: ...
    def read_comments(self, context: CapabilityRequestContext, reference: ContentReference, query: CommentQuery) -> AdapterResultEnvelope[list[PlatformComment]]: ...
```

规则：

- adapter 只返回标准 DTO 和 raw reference。
- adapter 不写数据库。
- 保存 Note、Diagnostic、Task 是 orchestration/service 的职责。

### 7.6 ContentMapper / MetricsMapper

建议文件：

- `backend/app/adapters/xhs/mappers.py`
- 或 `backend/app/services/xhs_content_mapper.py`

迁移对象：

- `_metric`
- `_note_url`
- `_normalize_search_item`
- `_normalize_detail_payload`
- `normalize_comment_payload`

目标：

- 解除 service -> API route private helper 的反向依赖。
- 用 golden tests 锁定旧响应字段。

### 7.7 KeywordSourceProvider

Huitun 不进入 PlatformAdapter，而是进入 source provider：

```python
class KeywordSourceProvider(Protocol):
    def discover_keywords(
        self,
        source_context: KeywordSourceContext,
        target_platform_id: str,
        seeds: list[str],
    ) -> KeywordDiscoveryRunResult: ...
```

语义：

```text
source_provider_id = "huitun"
target_platform_id = "xhs"
```

这能避免用户误以为 Huitun 支持内容库、发布、监控等平台工作区。

### 7.8 PublishAdapter

接口：

```python
class PublishAdapter(Protocol):
    supported_capabilities: set[str]

    def validate_publish_account(self, context: CapabilityRequestContext) -> AdapterResultEnvelope[AccountValidationResult]: ...
    def upload_asset(self, context: CapabilityRequestContext, asset: PublishAssetRef) -> AdapterResultEnvelope[UploadResult]: ...
    def dry_run_publish(self, context: CapabilityRequestContext, intent: PublishIntent) -> AdapterResultEnvelope[DryRunResult]: ...
    def publish(self, context: CapabilityRequestContext, intent: PublishIntent, uploaded_assets: list[UploadResult]) -> AdapterResultEnvelope[PublishResult]: ...
    def list_published(self, context: CapabilityRequestContext, query: PublishedContentQuery) -> AdapterResultEnvelope[list[PlatformContentSummary]]: ...
```

规则：

- 真实 publish 必须由 PublishOrchestrationService 在 gate 放行后调用。
- dry-run 必须证明 no-side-effect。
- 第一轮不允许 planned 平台实现真实 publish。

### 7.9 PublishOrchestrationService

建议文件：`backend/app/services/publish_orchestration_service.py`

接口：

```python
class PublishOrchestrationService:
    def build_intent(self, job_id: int) -> PublishIntent: ...
    def dry_run(self, intent: PublishIntent) -> DryRunResult: ...
    def publish(self, intent: PublishIntent) -> PublishResult: ...
    def run_due_job(self, job_id: int) -> PublishResult: ...
    def retry(self, job_id: int) -> PublishResult: ...
    def emit_task_event(self, event: TaskEvent) -> None: ...
    def emit_notification(self, event: NotificationEvent) -> None: ...
```

目标：

- 统一 `backend/app/api/publish.py` 与 `backend/app/services/scheduler_service.py`。
- 统一 note_info 组装、asset upload、post_note、状态写入、Task、Notification、Retry。
- 避免 scheduler 和 retry 绕过 API 的风险确认。

### 7.10 EngagementAdapter

第一轮只定义边界：

```python
class EngagementAdapter(Protocol):
    def read_comments(self, context: CapabilityRequestContext, reference: ContentReference, query: CommentQuery) -> AdapterResultEnvelope[list[PlatformComment]]: ...
    def suggest_reply(self, context: CapabilityRequestContext, comment: PlatformComment) -> AdapterResultEnvelope[ReplySuggestion]: ...
    def execute_reply(self, context: CapabilityRequestContext, comment: PlatformComment, reply: str) -> AdapterResultEnvelope[ReplyResult]: ...
```

规则：

- `read_comments` 可以 partial。
- `suggest_reply` 可以 planned。
- `execute_reply` 当前必须返回 blocked/risk_blocked。
- 不实现真实自动评论、点赞、关注、私信。

## 8. 核心类型

### 8.1 CapabilityRequestContext

```python
@dataclass(frozen=True)
class CapabilityRequestContext:
    user_id: int
    platform_id: str
    capability_key: str
    account_ref: PlatformAccountRef | None
    dry_run: bool
    confirmation_token: ConfirmationToken | None
    request_source: Literal["manual", "scheduler", "auto_task", "api", "retry"]
    correlation_id: str
    task_id: int | None
    idempotency_key: str | None
```

### 8.2 CapabilityDecision

```python
@dataclass(frozen=True)
class CapabilityDecision:
    allowed: bool
    blocked_reason: str | None
    risk_level: str
    requires_confirmation: bool
    confirmation_required_fields: list[str]
    effective_dry_run: bool
    account_safety_result: AccountSafetyResult | None
    rate_limit_result: RateLimitDecision | None
    user_message: str
    audit_reference: str | None
```

### 8.3 ConfirmationToken

```python
@dataclass(frozen=True)
class ConfirmationToken:
    capability_key: str
    platform_id: str
    account_id: int
    action_hash: str
    payload_summary_hash: str
    expires_at: datetime
    issued_by: int
    single_use: bool
    confirmed_risk_level: str
    request_source: Literal["manual", "scheduler", "auto_task", "api", "retry"] | None = None
```

规则：

- 必须动作级绑定。
- 高风险确认令牌必须是 single-use；同一令牌不得复用到第二次执行。
- 当动作依赖 request_source 审计边界时，确认令牌必须与请求来源精确绑定。
- 不能确认 A、执行 B。
- 真实发布和自动运营不能用通用 checkbox 代替。

### 8.4 PlatformAccountRef

```python
@dataclass(frozen=True)
class PlatformAccountRef:
    account_id: int
    platform_id: str
    account_kind: str | None
    sub_type: str | None
    display_role: str | None
    auth_mode: str
    status: str
    credential_status: str
    health_status: str
    profile_summary: dict
```

### 8.5 PlatformCredentialContext

```python
@dataclass(frozen=True)
class PlatformCredentialContext:
    account_ref: PlatformAccountRef
    credential_handle: str
    credential_version_id: int | None
    scopes: list[str]
    validated_at: datetime | None
    expires_at: datetime | None
```

不得包含可返回给前端或写入日志的明文 Cookie/token。

### 8.6 AdapterResultEnvelope

```python
@dataclass(frozen=True)
class AdapterResultEnvelope(Generic[T]):
    success: bool
    data: T | None
    message: str
    diagnostics: list[DiagnosticEvent]
    raw_reference: str | None
    retry_after_seconds: int | None
    rate_limit: RateLimitDecision | None
    error: AdapterError | None
    correlation_id: str
```

### 8.7 AdapterError

```python
@dataclass(frozen=True)
class AdapterError:
    category: Literal[
        "auth_expired",
        "credential_invalid",
        "rate_limited",
        "network",
        "signature_failed",
        "invalid_request",
        "upstream_changed",
        "not_found",
        "risk_blocked",
        "blocked_capability",
        "validation",
        "unknown",
    ]
    user_message: str
    platform_message: str | None
    retryable: bool
    rate_limited: bool
    credential_invalid: bool
    raw_reference: str | None
    next_action: str | None
```

用户体验要求：

- `auth_expired` / `credential_invalid`：引导重新登录。
- `rate_limited`：引导冷却后重试。
- `signature_failed` / `upstream_changed`：进入接口/签名诊断。
- `risk_blocked`：明确告诉用户动作未执行。

### 8.8 Content DTO

```python
@dataclass(frozen=True)
class ContentQuery:
    query_type: Literal["keyword", "url", "account", "brand", "feed"]
    value: str
    page: int | None
    cursor: str | None
    limit: int
    sort: str | None
    content_type: str | None
    time_range: str | None
    geo: str | None
    quality_gate: str | None
    save_policy: str | None
    platform_filters: dict
```

```python
@dataclass(frozen=True)
class ContentReference:
    platform_id: str
    external_content_id: str
    canonical_url: str | None
    source_url: str | None
    author_external_id: str | None
    source_kind: str
    private_adapter_metadata_ref: str | None
```

XHS 的 `xsec_token`、`xsec_source` 只能保存在 private metadata/ref 中，不进入用户可见 DTO。

```python
@dataclass(frozen=True)
class PlatformContentSummary:
    external_content_id: str
    canonical_url: str | None
    title: str
    excerpt: str
    author: PlatformAuthor
    cover_url: str | None
    media_type: str
    created_at_remote: datetime | None
    engagement_metrics: EngagementMetrics
    tags: list[str]
    quality_level: Literal["summary_only", "detail_ready"]
    raw_summary_ref: str | None
```

```python
@dataclass(frozen=True)
class PlatformContentDetail(PlatformContentSummary):
    body: str
    assets: list[PlatformAsset]
    video_asset: PlatformAsset | None
    full_tags: list[str]
    author_profile: dict
    location: str | None
    detail_quality: DetailQualityResult
    can_save: bool
    raw_detail_ref: str | None
```

### 8.9 Publish DTO

```python
@dataclass(frozen=True)
class PublishIntent:
    user_id: int
    platform_id: str
    account_ref: PlatformAccountRef
    source_draft_id: int | None
    title: str
    body: str
    media_type: str
    assets: list[PublishAssetRef]
    publish_mode: Literal["immediate", "app_schedule", "platform_schedule", "draft_only"]
    scheduled_at: datetime | None
    topics: list[str]
    location: str | None
    privacy: dict
    source: Literal["manual", "scheduler", "auto_task"]
    dry_run: bool
    confirmation_token: ConfirmationToken | None
```

```python
@dataclass(frozen=True)
class DryRunResult:
    valid: bool
    would_publish_payload_summary: dict
    required_account_role: str
    missing_fields: list[str]
    asset_checks: list[dict]
    account_checks: list[dict]
    topic_location_checks: list[dict]
    risk_level: str
    warnings: list[str]
    blocking_errors: list[str]
    estimated_platform_actions: list[str]
```

Dry-run 必须保证不调用真实发布接口。

```python
@dataclass(frozen=True)
class PublishResult:
    success: bool
    external_content_id: str | None
    status: Literal["published", "platform_scheduled", "failed"]
    published_at: datetime | None
    scheduled_at: datetime | None
    error_code: str | None
    error_message: str | None
    retryable: bool
    raw_payload_ref: str | None
```

## 9. 能力门禁规则

### 9.1 默认拒绝

以下任何条件成立，一律 blocked：

- PlatformMeta 缺失。
- `platform.enabled=false`。
- `release_stage=planned`。
- `release_stage=unavailable`。
- `adapter_key` 缺失。
- resolver 无实现。
- capability 缺失。
- `capability.status=planned`。
- `capability.status=unavailable`。
- `capability.status=blocked`。
- adapter 不支持该 capability。

不得因为 adapter 有同名方法就允许执行。

### 9.2 Registry 是唯一政策源

adapter 的 `supported_capabilities` 只能证明实现具备能力，不能提升 registry 中的状态。

如果冲突，取更保守结果：

```text
registry blocked + adapter supports -> blocked
registry available + adapter missing -> blocked
registry partial + adapter supports -> partial path only
```

### 9.3 高风险动作必须确认

以下能力必须显式确认：

- `account.login_cookie`
- `publish.real_publish`
- `workflow.auto_ops`
- 未来任何 `engagement.reply_execute`

确认必须动作级绑定：

- capability_key
- platform_id
- account_id
- action_hash
- payload summary hash
- source
- expiry

### 9.4 真实发布必须 dry-run-first

`publish.real_publish` 前必须有同一 action_hash 的有效 `DryRunResult`。

规则：

- `blocking_errors` 必须为空。
- dry-run 不得调用 `post_note`。
- 默认不得真实 upload，除非合同另行显式允许且测试覆盖。
- 缺 confirmation 或 dry-run 失效时必须 blocked。

### 9.5 app_schedule 与 platform_schedule 必须区分

主系统排期队列不等于平台侧预约发布。

- `app_schedule`：应用在本地 scheduler 到点执行。
- `platform_schedule`：平台接受预约发布。
- `published_at` 只能表示平台内容已存在或被平台接受，不能混用为本地排期时间。

### 9.6 后台任务无特权

以下路径必须和 API 一样走 CapabilityGate：

- scheduler
- auto task
- publish retry
- task retry
- background due jobs

不得绕过：

- confirmation
- dry-run
- account check
- rate limit
- low-frequency policy

### 9.7 workflow.auto_ops 默认只允许低风险链路

默认允许：

- 生成草稿。
- 创建 PublishJob。
- 本地排期。
- 生成诊断。

默认不允许：

- 后台直接真实上传。
- 后台直接 `post_note`。
- 自动评论。
- 自动点赞/关注/私信。

除非用户为该 AutoTask 明确配置可审计真实发布策略，否则后台不得直接真实发布。

### 9.8 engagement.reply_execute 必须 fail closed

当前规则：

```text
engagement.reply_execute = blocked / high / requires_confirmation=true
```

无论未来 adapter 是否出现对应方法，第一轮都必须返回：

```text
risk_blocked / blocked_capability
```

### 9.9 账号归属先于能力执行

执行前必须验证：

- `account_ref.platform_id == request.platform_id`
- `account_ref.sub_type` 满足能力需求

例如：

- XHS `content.discover` 使用 PC/read 账号。
- XHS `publish.real_publish` 使用 Creator/publish 账号。

### 9.10 凭据最小暴露

明文 Cookie/token 只能在：

```text
CredentialProvider -> adapter factory -> concrete adapter call
```

不得出现在：

- frontend response
- Task payload
- Notification
- logs
- diagnostics
- raw_json
- public DTO

### 9.11 限流是一等状态

rate limit 不应该只是字符串错误。

必须映射为：

- `AdapterError.category="rate_limited"`
- `RateLimitDecision`
- `retry_after_seconds`
- `cooldown_until`
- `should_skip_current_item`
- `should_pause_target`
- `user_message`

上层不得盲目重试。

### 9.12 planned 平台只读展示

以下平台当前只能 Coming Soon：

- `douyin`
- `kuaishou`
- `bilibili`
- `wechat_channels`
- `wechat_official`
- `weibo`
- `xianyu`
- `taobao`

不能出现真实：

- 登录
- 抓取
- 发布
- 监控
- 评论读取
- 自动运营

## 10. XHS 迁移路径

### Phase 1：合同文档与 scope firewall

只做设计和实施计划。

明确：

- 不改 `apis/`。
- 不改 `xhs_utils/`。
- 不改 `static/`。
- 不接真实新平台。
- 不做数据库大迁移。

### Phase 2：纯类型与 policy/resolver skeleton

建议新增：

- `backend/app/platforms/contracts.py`
- `backend/app/platforms/policy.py`
- `backend/app/platforms/resolver.py`

要求：

- 不改现有 API 输出。
- 不调用真实平台。
- 使用 fake adapter 测试 fail-closed。

### Phase 3：CapabilityGate / Resolver fake tests

测试必须证明：

- planned platform 不调用 adapter。
- disabled platform 不调用 adapter。
- missing capability 不调用 adapter。
- blocked capability 不调用 adapter。
- high risk 缺 confirmation 不调用 adapter。
- adapter 支持但 registry blocked 不调用 adapter。
- registry available 但 adapter 不支持不调用 adapter。
- 只有 registry 允许 + adapter 支持 + context 满足时才调用。

### Phase 4：CredentialProvider

逐步集中：

- `PlatformAccount`
- `AccountCookieVersion`
- `decrypt_text`
- cookie header/dict 转换

替代散落在以下文件中的重复 cookie 处理：

- `backend/app/api/publish.py`
- `backend/app/api/platforms/xhs/pc.py`
- `backend/app/api/platforms/xhs/creator.py`
- `backend/app/services/scheduler_service.py`

### Phase 5：清理直接 SDK 泄漏

重点检查：

- `backend/app/api/accounts.py`

如果存在直接 import `apis.xhs_creator_apis.XHS_Creator_Apis` 做健康检查或上传权限验证，应包装为：

```text
XHS Creator adapter / AccountAdapter.validate_credentials / validate_upload_permit
```

### Phase 6：XHS Facade

建议新增：

- `backend/app/adapters/xhs/contract_adapter.py`

它内部继续调用现有：

- `XhsPcApiAdapter`
- `XhsCreatorApiAdapter`
- `XhsPcLoginAdapter`
- `XhsCreatorLoginAdapter`

对外统一：

- `AdapterResultEnvelope`
- `AdapterError`
- standard DTO

### Phase 7：低风险 read-only mapper 迁移

先迁移 mapper，不迁移真实发布。

目标：

- 搜索结果 normalization。
- 详情 payload normalization。
- 评论 payload normalization。
- metrics extraction。

使用 golden tests 保证旧 `/api/xhs/*` 响应字段不变。

### Phase 8：解除 service -> route 私有 helper 反向依赖

让：

- `monitoring_crawl_service.py`
- `auto_tasks.py`

不再 import API route 私有 helper，而是使用 mapper / ContentDiscoveryAdapter。

### Phase 9：PublishOrchestrationService skeleton

统一：

- `backend/app/api/publish.py`
- `backend/app/services/scheduler_service.py`

覆盖：

- note_info 构造
- asset upload
- post_note
- PublishJob 状态
- PublishAsset 状态
- TaskEvent
- NotificationEvent
- RetryDecision

### Phase 10：dry-run no-side-effect contract

先加 `DryRunResult` service/test。

必须证明：

- dry-run 不调用 `upload_media`。
- dry-run 不调用 `post_note`。
- 缺素材、缺标题、账号错误等能返回 blocking_errors。

再决定是否新增：

```http
POST /api/publish/jobs/{job_id}/dry-run
```

或未来：

```http
POST /api/platforms/{platform_id}/publish/dry-run
```

### Phase 11：修复 auto-ops 后台绕过

`auto_tasks.py` 和 `scheduler_service.py` 都应生成：

- `AutoTaskRunContext`
- `PublishIntent`

然后通过 `PublishOrchestrationService` 执行。

规则：

- 失败不递增 `total_published`。
- retry 不绕过 gate。
- 后台真实发布必须有可审计授权来源。

### Phase 12：前端最小跟进

第一轮前端只做小修，不做大改：

- `PlatformMeta.status` 拓宽或逐步废弃 status 逻辑。
- 新代码只用 `release_stage`。
- `fetchPlatforms` 不应静默把 registry 故障伪装成完全成功。
- `ComingSoonPage` 对未知 platform 显示 unknown/404，而不是 XHS 兜底。

### Phase 13：旧 endpoint 保持兼容

旧 endpoint 继续服务前端：

- `/api/xhs/*`
- `/api/publish/*`
- `/api/notes/*`
- `/api/keyword-groups/*`

每迁移一个 route，只替换内部调用，不改变响应字段。

用 golden tests 锁兼容。

### Phase 14：第二个平台前置条件

只有当 XHS 合同迁移稳定后，才考虑第二个平台。

第二平台第一轮最多做：

- fake adapter。
- planned adapter fail-closed tests。
- 只读 `content.discover` 最小验证。

不接真实 API。

## 11. API 兼容策略

### 11.1 保留现有平台 API

继续保留：

```http
GET /api/platforms
GET /api/platforms/{platform_id}
```

兼容字段继续存在：

- `id`
- `name_cn`
- `name_en`
- `enabled`
- `status`
- `release_stage`
- `region`
- `platform_type`
- `accent_color`
- `icon`
- `default_route`
- `adapter_key`
- `risk_level`
- `auth_modes`
- `capabilities`

未知平台继续：

```json
{"detail":"platform_not_found"}
```

### 11.2 adapter_key 的短期与长期处理

短期：

- `adapter_key` 继续保留在 `/api/platforms` 响应中，避免破坏现有测试和前端类型。

长期：

- 新增 public workspace endpoint 隐藏 `adapter_key`。
- `adapter_key` 进入 backend-only `InternalAdapterDescriptor`。

### 11.3 旧 XHS endpoint 作为 wrapper

旧接口不立即删除：

```http
/api/xhs/pc/*
/api/xhs/creator/*
/api/xhs/crawl/*
/api/xhs/monitoring/*
/api/publish/*
```

未来逐步变成：

```text
旧 route -> orchestration service -> CapabilityGate -> XHS Facade -> existing XHS adapter
```

## 12. 风险与取舍

### 12.1 为什么不做全量多平台抽象

全量抽象会过早假设抖音、视频号、B站、公众号的真实接口形态。

当前更直接的路径是：

1. 先用 XHS 把合同跑通。
2. 再用第二平台验证哪些接口需要调整。
3. 不为了想象中的平台差异重构整个系统。

### 12.2 为什么保留 PlatformId enum

平台清单仍处于快速演进期，但当前只有 9 个声明平台。

保留 enum 的好处：

- 测试稳定。
- API shape 可控。
- 不引入数据库迁移。

代价：

- 新平台仍需改代码。

下一阶段可以接受这个代价。

### 12.3 为什么先迁移 read-only，再迁移 publish/auto-ops

内容发现和详情失败通常可恢复；真实发布和自动运营会影响账号和用户信任。

迁移顺序应该是：

```text
mapper/content read-only -> capability gate -> dry-run -> publish orchestration -> scheduler/auto-ops
```

不要反过来先改真实发布。

### 12.4 raw_json 作为逃生口，但要 redacted

现有系统有很多 raw payload。

第一轮不做大迁移，但需要原则：

- raw payload 可保留为调试逃生口。
- 对外只暴露 `raw_reference`。
- 敏感字段必须 redacted。
- 凭据、token、Cookie、签名参数不得进 raw_json。

## 13. 验证计划

### 13.1 保留现有 registry 测试

继续通过：

```bash
py -3 -m pytest tests/backend/test_platforms.py -q
```

验证：

- enriched fields。
- planned status alias。
- `engagement.reply_execute` blocked。
- detail 404。

### 13.2 CapabilityGate 测试

新增：`tests/backend/test_platform_capability_gate.py`

覆盖：

- unknown platform。
- planned platform。
- enabled=false。
- missing adapter_key。
- resolver 无实现。
- missing capability。
- capability blocked。
- capability planned。
- capability unavailable。
- partial capability。
- high risk 缺 confirmation。
- high risk 有 confirmation。
- account platform mismatch。
- account sub_type mismatch。

### 13.3 Resolver fake adapter 测试

新增：`tests/backend/test_platform_adapter_resolver.py`

覆盖：

- adapter 支持但 registry blocked -> 不调用。
- registry available 但 adapter 不支持 -> 不调用。
- planned platform -> 不调用。
- unknown adapter_key -> 不调用。
- registry 允许 + adapter 支持 + context 满足 -> 调用。

### 13.4 dry-run spy 测试

新增：`tests/backend/test_publish_orchestration_contract.py`

覆盖：

- dry-run valid 不调用 `upload_media`。
- dry-run valid 不调用 `post_note`。
- dry-run invalid 不调用 `upload_media`。
- dry-run invalid 不调用 `post_note`。
- real publish 缺 confirmation -> blocked。
- real publish 缺 dry-run -> blocked。
- real publish dry-run action_hash 不匹配 -> blocked。

### 13.5 XHS Facade 测试

新增：`tests/backend/test_xhs_contract_adapter.py`

覆盖：

- PC search tuple success -> success envelope。
- tuple failure 登录过期 -> `auth_expired` / `credential_invalid`。
- 限流文案 -> `rate_limited`。
- Creator RuntimeError -> `AdapterError`。
- `post_note` 成功 payload 能提取 external_content_id。

### 13.6 direct_xhs_request_env 测试

覆盖：

- 设置 `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY` 后，context 内移除。
- context 退出后完整恢复。
- 不联网。

### 13.7 Mapper golden tests

新增：`tests/backend/test_xhs_mappers.py`

用固定 raw payload 验证迁移后字段不变：

- `note_id`
- `note_url`
- `title`
- `content/body`
- `author_name`
- `cover_url`
- `image_urls`
- `video_url`
- metrics
- comments

### 13.8 no-bypass 静态测试

新增测试扫描：

```text
backend/app/**/*.py
```

除以下 allowlist 外：

- `backend/app/adapters/xhs/**`
- 明确临时 allowlist

禁止业务代码直接 import：

- `apis.*`
- `xhs_utils.*`
- `static.*`

如果当前已有泄漏，应先标 known blocker 或迁移后再纳入强断言。

### 13.9 scheduler / auto task 回归测试

覆盖：

- 后台真实发布必须经过 PublishOrchestrationService。
- publish failure 不递增 `total_published`。
- retry 不绕过 gate。
- NotificationEvent 正确触发。
- TaskEvent 状态正确写入。

### 13.10 前端 contract 测试或类型检查

覆盖：

- 新逻辑只用 `release_stage`。
- `status` 支持 beta/unavailable 或逐步不用于新逻辑。
- unknown `/platforms/foo` 不渲染小红书兜底。
- registry fetch failure 显示 degraded/cache 状态，而不是伪装成完全成功。

所有测试必须使用 fake/mock，不允许真实 XHS 请求、真实 Cookie、真实发布、真实评论执行。

## 14. 第一轮实施计划建议

第一轮 Platform Adapter Contract 实施不应一次性做完所有迁移。

建议拆成 4 个阶段：

### Stage A：Contract skeleton + tests

允许文件：

- `backend/app/platforms/contracts.py`
- `backend/app/platforms/policy.py`
- `backend/app/platforms/resolver.py`
- `tests/backend/test_platform_capability_gate.py`
- `tests/backend/test_platform_adapter_resolver.py`

验收：

- fake adapter tests 证明 fail closed。
- 不改现有 XHS route。
- 不改 `apis/`、`xhs_utils/`、`static/`。

### Stage B：CredentialProvider + no-bypass baseline

允许文件：

- `backend/app/platforms/credentials.py` 或 `backend/app/services/credential_provider.py`
- `tests/backend/test_platform_credentials.py`
- `tests/backend/test_no_bypass_imports.py`

验收：

- 明文凭据只在 provider/adapter 最后一跳。
- no-bypass 测试有明确 allowlist。
- 不破坏账号矩阵。

### Stage C：XHS mapper + Facade read-only path

允许文件：

- `backend/app/adapters/xhs/contract_adapter.py`
- `backend/app/adapters/xhs/mappers.py`
- `tests/backend/test_xhs_contract_adapter.py`
- `tests/backend/test_xhs_mappers.py`

验收：

- search/detail/comment mapper golden tests 通过。
- 旧 `/api/xhs/*` 响应字段不变。
- 不改底层签名/SDK。

### Stage D：Publish dry-run + orchestration skeleton

允许文件：

- `backend/app/services/publish_orchestration_service.py`
- `tests/backend/test_publish_orchestration_contract.py`

验收：

- dry-run 不调用 upload/post。
- real publish 缺 confirmation blocked。
- scheduler/auto task 不能绕过 gate。
- 旧 publish API 兼容。

## 15. 开放问题

### 15.1 publish.dry_run 当前状态

当前 registry 中 `publish.dry_run` 标为 available，但完整 no-side-effect dry-run path 尚未被本设计验证。

下一轮需要二选一：

1. 把 capability 状态调整为 partial/planned，直到 dry-run service 落地。
2. 同步实现最小 no-side-effect `DryRunResult`，并用测试证明不调用 upload/post。

推荐：第二种。因为 dry-run 是真实发布前的关键安全门禁。

### 15.2 ConfirmationToken 存储位置

候选：

- 数据库表。
- Task/Payload 审计记录。
- 短期缓存。
- request-level acknowledgement skeleton。

真实发布前必须明确。

第一轮 skeleton 可以先做 request-level acknowledgement，但文档必须说明它不能用于长期真实发布授权。

### 15.3 app_schedule vs platform_schedule 字段落点

当前 PublishJob 字段可能不足以表达：

- 主系统排期。
- 平台侧预约。

第一轮可先在 `PublishIntent` / `PublishResult` 层区分，数据库暂不迁移。

### 15.4 CredentialProvider 路径

如果 provider 需要直接访问 SQLAlchemy session，放在：

```text
backend/app/services/credential_provider.py
```

更自然。

如果只做纯合同类型，放在：

```text
backend/app/platforms/credentials.py
```

更清晰。

### 15.5 no-bypass allowlist

需要决定哪些现有文件短期允许继续 import 底层 SDK 或 `xhs_utils`。

建议：

- 第一版先生成扫描报告。
- 明确 allowlist。
- 每迁移一个路径就缩小 allowlist。

### 15.6 前端 PlatformId 拆分

当前前端 `PlatformId` 包含 `huitun`，但 backend registry 不包含 Huitun。

未来可拆分：

- `WorkspacePlatformId`
- `AccountPlatformId`
- `IntegrationSourceId`

第一轮 adapter contract 不强制拆。

### 15.7 自动运营历史任务授权

已有 AutoTask 如何补授权来源需要明确：

- 历史任务默认只能生成草稿 / 创建待发布任务？
- 是否需要用户重新确认后才允许后台真实发布？

建议：历史 AutoTask 不默认获得真实发布授权。

## 16. 成功标准

Platform Adapter Contract 第一轮完成后，应满足：

1. 新增合同类型和 CapabilityGate skeleton。
2. fake adapter 测试证明 fail closed。
3. XHS 仍然是唯一 enabled 平台。
4. planned 平台不能执行任何真实动作。
5. 旧 `/api/platforms` 和 `/api/xhs/*` 不被破坏。
6. 不修改 `apis/`、`xhs_utils/`、`static/`。
7. 不触发真实 XHS 请求、真实发布、真实评论执行。
8. 高风险动作缺 confirmation 时不会调用 adapter。
9. dry-run 测试证明 no-side-effect。
10. scheduler、auto task、retry 没有绕过 gate。

## 17. 下一步推荐输入

后续可用 `/goal` 启动第一轮实现：

```text
/goal 使用 Morse's development mode 实现 docs/superpowers/specs/2026-06-09-platform-adapter-contract-design.md 的第一轮 Platform Adapter Contract skeleton。

只做 Stage A：Contract skeleton + CapabilityGate + Resolver fake tests。
允许新增/修改 backend/app/platforms/contracts.py、backend/app/platforms/policy.py、backend/app/platforms/resolver.py、tests/backend/test_platform_capability_gate.py、tests/backend/test_platform_adapter_resolver.py。

全程禁止：
- 不接真实新平台
- 不改 apis/、xhs_utils/、static/
- 不改 XHS SDK/签名层
- 不改发布真实执行链路
- 不碰灰豚业务逻辑
- 不处理 unrelated git diff
- 不 commit、不 push，除非我明确要求

要求：
- 先写 failing tests
- fake adapter 证明 fail closed
- 每阶段给 stage contract、implementation report、independent review verdict、verification evidence
```

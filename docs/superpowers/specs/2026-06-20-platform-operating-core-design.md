# Platform Operating Core 设计：从 XHS_ALL_IN_ONE 沉淀多平台运营内核

> **For agentic workers:** REQUIRED SUB-SKILL: Use Morse's development mode for implementation. This document is a design spec, not an implementation patch. Do not modify business code from this spec alone; execute the paired plan in `docs/superpowers/plans/2026-06-20-platform-operating-core.md` stage-by-stage with review gates.

## 1. 背景与问题

当前项目主系统基线是 `XHS_ALL_IN_ONE`。系统已经从单一小红书平台向多平台运营系统演进，已有平台中心、能力矩阵、平台 adapter contract skeleton、公众号平台基础、共享草稿工作台等阶段性成果。

但实际开发新平台时仍然慢，核心原因不是缺少代码，而是缺少一条稳定的复用边界：

```text
平台注册 -> 账号接入 -> 内容发现/采集 -> 内容库 -> 标签/筛选/导出 -> 草稿工坊 -> 素材处理 -> 发布任务 -> 调度自动化 -> 诊断/通知/安全门禁
```

这条链路在 XHS 中已经基本跑通，但不少能力仍以 `xhs` 命名、XHS 页面、XHS raw_json 解析、XHS 文件前缀或 XHS route helper 的形式存在。结果是：

1. 新平台接入时，agent 容易复制页面、复制 API、复制模型，而不是接 adapter。
2. 通用表已经存在 `platform` 字段，但部分接口仍把平台写死为 `xhs`。
3. 平台差异散落在 UI、API route、service helper、raw_json 解析里。
4. 公众号等新能力已经出现专属模型和路由，但与通用运营链路的映射边界尚未完全固化。

本设计的目标是定义 **Platform Operating Core（多平台运营内核）**，把 XHS 已有的成熟能力沉淀成可复用框架。以后开发新平台，不再从零做一套平台系统，而是按 adapter checklist 接入共享内核。

## 2. 设计结论

不要把系统抽成一个“大而空的平台基类”。应该抽出一个面向用户运营目标的共享内核：

```text
Platform Operating Core
  = Platform Registry
  + Capability Policy
  + Account Matrix Core
  + Content Library Core
  + Draft Workbench Core
  + Asset Workshop Core
  + Publish Queue Core
  + Workflow Automation Core
  + Diagnostics / Notification / Audit Core
```

每个平台只实现自己的 adapter：

- 账号怎么登录和校验。
- 内容怎么发现、采集、归一化。
- 内容字段和指标怎么映射。
- 草稿有哪些平台校验。
- 素材尺寸、格式、数量限制是什么。
- 发布支持 dry-run、排期还是真实发布。
- 自动化有哪些工作流 step。
- 失败如何归因为用户能理解的诊断。

用户不应该理解 adapter、normalizer、policy decision、workflow definition 等内部概念。用户只应该看到：账号矩阵、内容库、草稿工坊、素材工坊、发布中心、自动运营、任务中心。

## 3. 目标

### 3.1 产品目标

1. 新平台上线后，用户获得熟悉的一致体验，而不是每个平台一套操作方式。
2. 用户在不同平台间复用同一套心智：账号、内容、草稿、素材、发布、任务。
3. 系统自动根据平台能力显示/隐藏动作，不让用户点到无效按钮。
4. 高风险动作默认 dry-run / 明确确认 / 清晰诊断。
5. 新平台第一版可以只开放部分能力，例如只读内容库或草稿工坊，不要求一次性完整闭环。

### 3.2 工程目标

1. 后续接新平台时，先注册平台能力，再实现 adapter，不复制整套页面和 API。
2. 把 XHS 中已经成熟的通用运营能力沉淀为共享 core。
3. 把平台差异集中在 adapter、normalizer、renderer、rules 中。
4. 逐步解除 `xhs` hardcode、route private helper 反向依赖和文件名前缀绑定。
5. 保持 XHS 现有功能稳定，不为了抽象破坏主流程。

### 3.3 安全目标

1. 真实发布、自动运营、账号凭据、评论执行等高风险动作必须经过 Capability Policy。
2. planned / unavailable / blocked 能力 fail closed。
3. 真实账号操作不得因为共享框架而放宽安全边界。
4. 不实现绕风控、验证码绕过、批量号池、高频自动化。
5. 明文 Cookie/token/API key 不进入前端、日志、Task payload、Notification、diagnostics 或文档。

## 4. 非目标

本设计不做：

- 不接入真实新平台。
- 不重写 XHS 底层 SDK、签名层、`apis/`、`xhs_utils/`、`static/`。
- 不把 legacy TypeScript CLI 当主系统入口。
- 不迁移旧 SQLite 数据。
- 不做生产部署。
- 不一次性重构所有 XHS 页面。
- 不删除现有 XHS route 或响应字段。
- 不统一所有平台的原始字段。
- 不把公众号、小红书、抖音、闲鱼等强行塞进同一张“万能内容表”的所有字段。
- 不把内部架构概念暴露成用户可见模块。
- 不启用真实自动评论、自动点赞、自动关注、自动私信或任何规避检测能力。

## 5. 当前可复用资产盘点

### 5.1 Platform Registry / Capability Matrix

已有基础：

- `backend/app/core/platforms.py`：平台 ID、发布阶段、区域、类型、能力 key、风险等级、`PlatformMeta`、`PlatformCapability`。
- `backend/app/services/platform_service.py`：平台列表与详情服务。
- `backend/app/api/platforms/registry.py`：平台注册 API。
- `frontend/src/types/index.ts`：前端 `PlatformId`、`PlatformMeta`、`PlatformCapability` 类型。

定位：这是多平台系统的事实源和入口，不应重写，应继续补强。

### 5.2 Capability Policy / Adapter Contract

已有基础：

- `backend/app/platforms/contracts.py`
- `backend/app/platforms/policy.py`
- `backend/app/platforms/resolver.py`

定位：这是所有平台动作的门禁层。后续发布、采集、自动化、评论读取、账号登录都应逐步接入，不应只停留在 skeleton。

### 5.3 Account Matrix

已有基础：

- `backend/app/models/platform_account.py`：`PlatformAccount`、`AccountCookieVersion`。
- `frontend/src/types/index.ts`：`PlatformAccount` 类型。
- `frontend/src/components/account/add-account-drawer.tsx`：已有账号绑定 UI，但平台、账号类型、登录方式仍偏硬编码。

定位：账号表已经平台化，UI 和 auth schema 需要从 hardcode 转为 registry/schema-driven。

### 5.4 Content Library

已有基础：

- `backend/app/models/note.py`：`Note`、`NoteAsset`、`NoteComment`、`Tag`。
- `backend/app/api/notes.py`：内容库、素材、评论、标签、导出等能力。
- `frontend/src/pages/platforms/xhs/library-page.tsx`：完整内容库体验。
- `frontend/src/types/index.ts`：`SavedNote`、`NoteAsset`、`NoteComment`、`Tag` 类型。

定位：这是最核心的共享用户工作台之一。底层模型已经部分通用，但 API 和页面仍有 XHS hardcode，应逐步抽成 `Content Library Core`。

### 5.5 Draft Workbench

已有基础：

- `frontend/src/components/draft-workbench/draft-workbench-types.ts`
- `frontend/src/components/draft-workbench/use-draft-workbench.ts`
- XHS 和公众号已经开始复用共享草稿工作台。

定位：这是当前抽象得最正确的样板，应作为多平台 UI adapter 模式的模板。

### 5.6 Publish Center

已有基础：

- `backend/app/models/publish.py`：`PublishJob`、`PublishAsset`。
- `backend/app/api/drafts.py`：草稿送发布中心。
- `frontend/src/types/index.ts`：`PublishJob`、`PublishOptions`、`SendDraftToPublishPayload`。

定位：发布任务模型已通用，真实发布执行应继续向 `PublishAdapter` + `PublishOrchestrationService` 演进。

### 5.7 Task / AutoTask / Scheduler

已有基础：

- `backend/app/models/task.py`：通用任务表。
- `backend/app/models/auto_task.py`：自动任务表。
- `backend/app/api/auto_tasks.py`：自动任务创建、调度时间计算。

定位：`Task` 已经通用；`AutoTask` 仍偏 XHS，需要升级为 workflow definition + payload + platform adapter。

### 5.8 Asset / File / Image Workshop

已有基础：

- `backend/app/api/files.py`：上传、媒体下载、图片合成、resize、导出下载。
- `backend/app/services/image_util.py`：图片处理。

定位：能力可复用，但命名前缀和 export owner policy 仍写死 XHS，需要平台化。

### 5.9 Diagnostics / Notifications / ApiLog

已有基础：

- `backend/app/api/notifications.py`
- `backend/app/models/api_log.py`
- `frontend/src/types/index.ts` 中的 `CrawlDiagnostic`、`AppNotification` 等类型。

定位：这是跨平台横切基础设施，应成为所有 adapter 和 workflow 的统一反馈层。

### 5.10 WeChat Official 专属层

已有基础：

- `backend/app/models/wechat_official.py`
- `backend/app/api/platforms/wechat_official/*`
- `backend/app/services/wechat_official_*`
- 公众号内容库、草稿、RedFox 等能力。

定位：公众号专属表可以作为平台原始层，但进入用户运营链路时应映射到通用 Content/Draft/Publish/Task 概念。平台原始层与运营层不能混淆。

## 6. 目标架构

```text
User Workspaces
  ├── Account Matrix
  ├── Content Library
  ├── Draft Workbench
  ├── Asset Workshop
  ├── Publish Center
  ├── Automation Workflows
  └── Tasks / Notifications / Diagnostics

Platform Operating Core
  ├── Platform Registry
  ├── Capability Policy
  ├── Account Matrix Core
  ├── Content Library Core
  ├── Draft Workbench Core
  ├── Asset Workshop Core
  ├── Publish Queue Core
  ├── Workflow Automation Core
  └── Diagnostics / Notification / Audit Core

Platform Adapters
  ├── xhs
  ├── wechat_official
  ├── douyin
  ├── wechat_channels
  ├── weibo
  └── ...

Native / External Capabilities
  ├── XHS SDK / signature
  ├── WeChat Official backend / RedFox
  ├── Douyin API or crawler
  └── External discovery sources
```

## 7. 核心模块设计

### 7.1 Platform Registry

职责：

- 平台元数据事实源。
- 平台能力矩阵。
- 平台默认路由。
- 平台 auth modes。
- 平台 adapter key。
- 平台风险等级。

必须保持：

- `release_stage` 是 canonical 字段。
- `status` 只作为 legacy compatibility。
- `capability.key` 表达产品能力，不表达 SDK 方法。

新平台必须先进入 registry，不能先写页面。

### 7.2 Capability Policy

职责：

- 平台是否存在。
- 平台是否 enabled。
- 能力是否 available / partial / planned / blocked。
- 高风险是否需要 confirmation。
- 账号归属和 sub_type 是否匹配。
- adapter 是否存在并支持 capability。
- 返回用户可理解的阻断原因。

规则：

- 所有真实平台动作默认 fail closed。
- Adapter 不能提升 registry 中的能力状态。
- Scheduler、auto task、retry 没有特权。
- 高风险动作不能用一个泛化 checkbox 代替动作级 confirmation。

### 7.3 Account Matrix Core

职责：

- 统一账号记录。
- 统一账号状态。
- 统一凭据版本。
- 统一账号健康检查。
- 平台声明 account kinds 和 auth modes。

建议接口：

```python
class AccountAdapter(Protocol):
    supported_auth_modes: set[str]
    account_kinds: set[str]

    def start_auth(self, context, auth_mode: str, account_kind: str) -> AdapterResultEnvelope[AuthStartResult]: ...
    def confirm_auth(self, context, session_ref: str) -> AdapterResultEnvelope[PlatformAccountRef]: ...
    def import_credential(self, context, payload) -> AdapterResultEnvelope[PlatformAccountRef]: ...
    def check_health(self, context, account_ref: PlatformAccountRef) -> AdapterResultEnvelope[AccountSafetyResult]: ...
```

前端应从 platform meta/auth schema 渲染登录方式，而不是在 `AddAccountDrawer` 中 hardcode 平台分支。

Stage 5 第一小步边界：账号添加抽屉先使用前端本地 `AccountAuthSchema` 作为低风险 fallback contract，只声明当前已有的 `xhs` / `huitun`、账号类型和登录方式；不改后端 registry、不改真实 login endpoint、不改凭据存储、不接入真实新平台。`QrLoginPanel` / `CookieImportPanel` 内部现有 XHS/Huitun API 分支仍作为当前平台 auth adapter UI endpoint 保留，后续阶段再下沉到更深 adapter contract。

### 7.4 Content Library Core

职责：

- 统一内容列表。
- 统一详情抽屉。
- 统一标签、筛选、排序、批量操作、导出。
- 统一素材和评论读取。
- 平台 adapter 提供 normalizer 和 renderer。

核心概念：

```text
PlatformRawContent       平台原始层，可专属表/专属 raw_json
NormalizedContentItem    运营层通用内容项
ContentMetric            统一指标字典
ContentAsset             图片/视频/附件
ContentComment           评论/回复
ContentRenderer          平台特有展示逻辑
```

过渡策略：

- 短期保留 `Note` 表名，不做高风险 migration。
- API 和前端概念逐步从 note-only 转为 content library。
- XHS raw_json 解析从 UI 页面迁移到 `xhsContentAdapter` / mapper。
- WeChat Article 保留专属原始表，但可映射到 Content Library。

Stage 3 前端抽取边界：

- `ContentLibraryShell` 和 `useContentLibrary` 只承载列表、筛选、分页、选择、批量动作、详情抽屉、素材/评论/标签/导出等通用 orchestration。
- XHS 文案、API 调用、作品 URL/作者 URL 构造、`raw_json` / `xsec_token` / `note_card.interact_info` 解析、卡片/表格/详情 renderer 均留在 `xhs-content-library-adapter.ts`。
- 本阶段不改后端 API、数据库、route 响应、不接公众号内容库、不迁移真实数据；XHS 用户可见行为应保持等价。

### 7.5 Draft Workbench Core

职责：

- 统一草稿列表。
- 统一编辑器。
- 统一保存、复制、删除、dry-run、从内容源创建草稿。
- 平台 adapter 提供校验、平台字段、AI 助手扩展、发布限制。

已有 `DraftWorkbenchAdapter`、`useDraftWorkbench` 和 `DraftWorkbenchShell` 是当前最成熟的前端 adapter 样板，应作为后续共享 UI 的 canonical pattern：共享 shell 只渲染标题、正文、标签、列表、基础动作和 extension slots；平台语义留在 XHS/公众号 adapter 与页面 extras 中。

当前标准化边界：

- 共享 workbench core 只依赖最小 `DraftWorkbenchDraft` shape，不读取 `source_note_id`、公众号来源文章、发布细节或平台 raw_json。
- XHS adapter 保持现有 XHS 草稿语义，可从内容库 note 创建草稿，并在 XHS 页面 extras 中展示来源笔记、AI 改写和送发布中心动作。
- 公众号 adapter 保持独立草稿语义，草稿区不展示内容库候选文章，不保留来源引用，真实发布/群发继续阻断，只暴露 dry-run 校验。
- 新平台接入草稿工坊时，先实现 `DraftWorkbenchAdapter`，再把平台专属校验、AI 辅助、发布入口放入 page-level extras，不允许把平台业务分支写进 shared shell。

后端建议补齐：

```python
class DraftAdapter(Protocol):
    def list_drafts(self, context, platform_id: str) -> AdapterResultEnvelope[list[DraftSummary]]: ...
    def save_draft(self, context, draft_id: int, patch: DraftPatch) -> AdapterResultEnvelope[DraftDetail]: ...
    def dry_run_draft(self, context, draft_id: int, payload: dict) -> AdapterResultEnvelope[DryRunResult]: ...
    def create_from_source(self, context, source_ref: ContentReference, payload: dict) -> AdapterResultEnvelope[DraftDetail]: ...
```

### 7.6 Asset Workshop Core

职责：

- 上传。
- 下载。
- 删除。
- 图片合成。
- resize/crop。
- 平台素材规则校验。
- 绑定到内容、草稿、发布任务。

必须修正的 hardcode：

- 文件名前缀不要固定 `xhs-*`。
- export owner policy 不要固定 `xhs-notes` / `xhs-report`。
- 平台素材规则应来自 `PlatformAssetRules`。

Stage 6 第一小步边界：先引入纯函数 owner prefix policy，允许 `xhs-*` legacy 前缀继续工作，同时支持基于 `PlatformId` allowlist 的 `<platform>-upload/asset/image-u{user}-` 和 `<platform>-notes/report-u{user}-` 前缀。该阶段不迁移目录、不删除旧文件、不改变 route response 字段、不放宽 basename/path traversal 检查，未知 platform 或未知 owner kind 必须 fail closed。

建议概念：

```text
asset_owner_type = content | draft | publish_job | user_upload | generated
asset_platform = xhs | wechat_official | ... | null
asset_kind = image | video | cover | export | report
```

### 7.7 Publish Queue Core

职责：

- 创建发布任务。
- 校验发布意图。
- dry-run。
- 上传素材。
- 真实发布。
- 排期。
- 状态流转。
- 错误归因。

现有 `PublishJob` / `PublishAsset` 可作为核心模型继续演进。

建议边界：

```text
Draft -> PublishJob      通用
PublishJob -> DryRun     通用 orchestration + platform adapter
PublishJob -> Publish    高风险，必须 policy + confirmation + no-bypass
```

不要把平台发布参数无限塞入一个全局 `PublishOptions`。应引入 platform publish schema / rules。

Stage 7 第一小步边界：`PublishOrchestrationService.dry_run` 只做本地状态校验和 `publish.dry_run` capability policy gate；dry-run 结果保持 `publish_blocked=true`，不得上传素材、不得调用真实发布、不得写入 `PublishJob.status` 或 `PublishAsset.upload_status`。XHS dry-run 当前只校验标题、正文提示、Creator 账号、图片素材、视频暂不支持、排期时间必须晚于当前时间。planned / blocked 平台能力 fail closed；公众号 `publish.dry_run` 仍按 registry planned 阻断。真实发布 endpoint 仍保留既有响应形状与 `confirm_real_publish` 语义，无确认先 403，且不得实例化/调用 adapter。

### 7.8 Workflow Automation Core

职责：

- 用 workflow definition 描述自动化链路。
- 复用 scheduler。
- 每个 step 通过 adapter 执行。
- 每个 step 输出标准 diagnostics / task event。

建议 workflow type：

```text
discover_to_library
library_to_draft
draft_to_publish_job
scheduled_publish
monitor_keywords
engagement_reply_suggest
```

`AutoTask` 应从 XHS-specific 字段逐步升级为：

```text
platform_id
workflow_type
account_refs
schedule
payload
risk_policy
authorization_ref
status
last_run_at
next_run_at
```

历史 AutoTask 不应默认获得真实发布授权。

Stage 8 第一小步边界：先新增纯函数 workflow skeleton，不接入 `/auto-tasks` API 路径、不改 `AutoTask` 表、不做 Alembic migration。Legacy XHS AutoTask 只能映射为 `auto_ops_legacy_skeleton` / publish-job-only 计划，保留 `pc` / `creator` 账号引用、keywords、AI instruction 和 schedule payload；`risk_policy.authorization_ref` 默认为空，`real_publish_authorized=false`，真实发布 step 在缺少动作级 `authorization_ref` 时必须 fail-closed。`engagement_reply_suggest` 只允许生成回复建议，不包含 `reply_execute` 或任何真实评论/点赞/关注/私信执行能力。本轮同时补上 scheduler no-bypass 安全门：后台 AutoTask runner 只能创建 `pending` 发布任务和 `pending` 素材，不得静默调用 Creator upload/post；真实发布必须继续走发布中心显式确认路径。

### 7.9 Diagnostics / Notification / Audit Core

职责：

- 平台失败统一归因。
- 用户可读下一步。
- 任务事件。
- 账号失效通知。
- 高风险审计。
- rate limit/cooldown 信息。

标准诊断字段：

```text
platform_id
capability_key
stage
severity
recoverable
category
user_message
next_action
raw_reference
correlation_id
```

用户体验原则：不要只说“失败”，要告诉用户是账号过期、限流、接口变化、能力被阻断、还是输入不合法。

Stage 9 第一小步边界：先新增后端纯诊断序列化 service 和 focused tests，标准化 `auth_expired`、`rate_limited`、`signature_failed`、`risk_blocked`、`validation` 五类用户可恢复信息；`raw_reference` 只能是日志/任务/URL 引用，不能携带 Cookie、token、API key、平台私有 token 或 raw_json payload。本阶段只把 `PublishOrchestrationService.dry_run` 作为低风险示例接入 diagnostics 输出，保持既有 `checks` / `policy` 响应字段，不新增数据库 migration，不改通知表，不暴露平台原始错误。

## 8. 平台原始层与运营层

必须区分：

```text
平台原始层：保留平台真实结构，服务采集、调试、增量同步。
运营层：用户实际操作的账号、内容、草稿、发布、任务。
```

示例：

- `WechatOfficialArticle` 可以继续作为公众号原始文章层。
- 进入内容库时，应映射为 `NormalizedContentItem`。
- 进入草稿时，应映射为 `Draft`。
- 进入发布中心时，应映射为 `PublishJob`。

不要为了统一而删除平台原始层；也不要让用户工作台直接依赖平台原始层。

## 9. 前端架构原则

### 9.1 页面按能力复用，不按平台复制

目标路径心智：

```text
/platforms/:platformId/accounts
/platforms/:platformId/library
/platforms/:platformId/drafts
/platforms/:platformId/assets
/platforms/:platformId/publish
/platforms/:platformId/automation
```

不是每个平台复制一整套页面。

### 9.2 UI shell 共享，adapter 注入差异

推荐前端模式：

```text
SharedPageShell
  + useSharedController(adapter)
  + platformRenderer
  + platformRules
```

草稿工坊已经采用这个方向。内容库、账号矩阵、发布中心应逐步跟进。

### 9.3 内部概念不外泄

用户不应看到：

- adapter_key
- normalizer
- policy decision
- workflow definition JSON
- xsec_token
- SDK class

用户应看到：

- 这个平台能做什么。
- 当前动作是否安全。
- 为什么不能执行。
- 下一步怎么恢复。

## 10. 后端架构原则

### 10.1 Route 不应承载平台业务细节

Route 负责：

- 认证。
- 参数校验。
- 调用 service。
- 返回响应。

Service / orchestration 负责：

- 业务状态。
- policy gate。
- adapter 调用。
- 数据落库。
- diagnostics。

Adapter 负责：

- 平台动作。
- 平台错误转换。
- raw reference。

### 10.2 Mapper 从 route 私有 helper 中抽离

XHS 中的 raw payload normalization 不应长期放在 API route 私有 helper。应逐步迁移到 mapper，并用 golden tests 锁定兼容字段。

Stage 4 第一小步的 mapper 边界：`backend/app/adapters/xhs/mappers.py` 只提供纯函数归一化，不依赖 DB/session/FastAPI/SDK，不改变 route response shape。当前先锁定 XHS raw payload 兼容字段：direct 与 `data.items[0].note_card` 指标、canonical note URL、author profile URL、tags、cover/video/assets、note type、publish timestamp。后续 route 接入必须单独加 focused serializer/API regression tests。

### 10.3 不直接碰底层 SDK

`apis/`、`xhs_utils/`、`static/` 是脆弱底层能力。新平台内核化阶段默认不改。

## 11. 新平台接入 Checklist

每个平台接入必须填写：

### 11.1 Platform Meta

- `platform_id`
- `name_cn` / `name_en`
- `region`
- `platform_type`
- `release_stage`
- `default_route`
- `adapter_key`
- `risk_level`
- `auth_modes`

### 11.2 Capability Matrix

至少评估：

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

每项必须声明：

- `status`
- `risk`
- `requires_confirmation`
- 用户可读 notes

### 11.3 Account Adapter

- account kinds。
- auth modes。
- credential storage。
- health check。
- expiry detection。
- status mapping。

### 11.4 Content Adapter

- discovery inputs。
- raw item shape。
- normalized content item。
- metrics mapping。
- asset extraction。
- comment extraction。
- source URL builder。
- private metadata / token handling。

### 11.5 Draft Adapter

- title/body/tags/assets 支持。
- source-to-draft mapping。
- draft validation。
- dry-run support。
- platform editor extras。

### 11.6 Publish Adapter

- publish modes。
- scheduled support。
- media upload requirements。
- dry-run validation。
- real publish support。
- receipt mapping。
- error categories。

### 11.7 Workflow Adapter

- supported workflow types。
- scheduler constraints。
- rate limits。
- recoverable failures。
- notification rules。

### 11.8 Second Platform Readiness Gate

接真实第二平台前必须先跑 readiness gate。该 gate 不执行真实平台动作，只把当前 core 能力压缩成可审查报告：

- `platform_registered`
- `read_only_adapter_path`
- `shared_content_library_or_deferral`
- `capability_policy_gate`
- `publish_dry_run_no_side_effect`
- `scheduler_no_bypass`
- `diagnostics_no_secret_leak`
- `credential_logging_safe`
- `real_publish_confirmation_gate`
- `disable_or_rollback_path`

Gate 输出只能是：

- `PASS`：允许开始第二平台 read-only adapter pilot。
- `FOLLOW_UP`：只能做 docs/fake adapter，不接真实平台。
- `BLOCKER`：不允许接真实平台，先修 core。

其中 Capability Policy、publish dry-run no-side-effect、scheduler no-bypass、diagnostics no-secret-leak、credential logging、real publish confirmation 属于 blocker 类；read-only adapter path、shared content shell、rollback/disable 等缺口属于 follow-up 类。该 gate 是产品安全门，不是技术打分：核心判断是用户能否安全获得一致体验，而不是代码抽象是否漂亮。

## 12. 迁移优先级

### P0：文档与合同先行

先写清楚内核边界、adapter checklist 和 hardcode 清单，不直接改业务代码。

### P1：草稿工坊作为标准样板

草稿工坊已经抽象正确，应固化为前端 adapter + 后端 draft service 设计样板。

### P2：内容库抽成 PlatformContentLibrary

内容库是最重要的复用资产。先抽 UI shell 和 normalizer，不急着改数据库表名。

### P3：账号矩阵 schema-driven

账号接入是新平台第一步。AddAccountDrawer 应由 platform auth schema 驱动。

### P4：素材/文件平台化

修正 `xhs-*` 文件前缀和 export policy，形成 Asset Workshop Core。

### P5：发布中心接入 Policy + Adapter

发布高风险，必须先有 dry-run 和 confirmation，再迁移真实发布。

### P6：AutoTask 升级为 Workflow Core

自动运营最后迁移，避免后台任务绕过 gate。

## 13. 测试策略

### 13.1 Contract Tests

- Platform Registry shape。
- Capability Policy fail closed。
- Adapter Resolver 不绕过 registry。
- planned/blocked/high risk 不调用 adapter。

### 13.2 Mapper Golden Tests

- XHS raw payload -> normalized content。
- WeChat article -> normalized content。
- metrics、assets、comments、URL、author 字段保持稳定。

### 13.3 UI Contract Tests / Type Checks

- DraftWorkbenchAdapter 新平台最小实现可编译。
- ContentLibraryAdapter 新平台最小实现可编译。
- capability 缺失时按钮隐藏。
- unknown platform 不渲染 XHS 兜底。

### 13.4 No-side-effect Tests

- dry-run 不调用真实 upload/post。
- planned 平台不调用真实平台。
- auto task/retry/scheduler 不绕过 gate。

### 13.5 Regression Tests

- XHS dashboard/accounts/library/drafts/publish/auto-ops 不破坏。
- 公众号内容库/草稿/RedFox 当前行为不破坏。
- 前端 build 通过。
- `git diff --check` 通过。

## 14. 风险与取舍

### 14.1 不做数据库大迁移

`Note` 命名不完美，但已有 platform 字段和大量使用。第一轮先在 service/API/UI 层抽象为 content item，不做表级 rename。

### 14.2 不强行统一所有字段

不同平台内容结构差异大。统一核心字段 + metrics dict + raw/private metadata，比设计万能字段更稳。

### 14.3 不直接重构真实发布

发布影响真实账号和用户信任。先做 dry-run no-side-effect 和 policy gate，再迁移真实发布。

### 14.4 不让 Huitun 成为顶层平台工作区

Huitun/RedFox 更像 discovery source / keyword source provider。它们可以服务目标平台，但不一定是完整运营平台。

### 14.5 文档先于实现

本次先把规范写清楚，是为了避免后续 agent 继续自由复制 XHS 代码。

## 15. 完成标准

本设计成立的标准：

1. 后续任何新平台接入都有明确 checklist。
2. 共享内核和平台 adapter 边界清楚。
3. 已列出 XHS 中可抽取的资产和硬编码迁移方向。
4. 高风险动作没有因为抽象而放宽。
5. 用户可见体验围绕账号、内容、草稿、素材、发布、自动化，而不是内部 adapter。
6. 配套实施计划能分阶段执行，且每阶段可验证、可回滚、可 review。

## 16. 下一步推荐输入

```text
/goal 使用 Morse's development mode 按 docs/superpowers/specs/2026-06-20-platform-operating-core-design.md 和 docs/superpowers/plans/2026-06-20-platform-operating-core.md 执行第一阶段 Platform Operating Core 文档化与最小骨架收敛。

先只做 Stage 1：抽取内容库/账号/素材/发布/自动化的 hardcode 清单和 adapter checklist，不改业务代码。
完成后给 evidence ledger、review verdict 和下一阶段建议。
```

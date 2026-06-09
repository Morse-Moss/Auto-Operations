# 多平台运营底座演进设计：国内版优先，以 XHS 为第一个完整平台

## 1. 背景

当前项目主系统基线是 `XHS_ALL_IN_ONE`，根目录代表一个 Web-first 小红书运营平台，技术栈为 FastAPI、SQLAlchemy、Alembic、React、Vite、Ant Design，以及现有 XHS SDK/签名/适配层。

项目已经具备多平台中心的入口雏形：

- 前端平台选择页：`frontend/src/pages/platform-select/platform-select-page.tsx`
- 前端平台卡片组件：`frontend/src/components/layout/platform-selector.tsx`
- 前端平台化路由：`frontend/src/app/router.tsx`
- 后端平台元数据：`backend/app/core/platforms.py`
- 后端平台注册 API：`backend/app/api/platforms/registry.py`

当前入口能展示平台卡片，小红书已启用，抖音、快手、微博、闲鱼、淘宝等为 Coming Soon。但这个入口目前主要是展示列表，还不是完整的多平台运营底座。它缺少平台区域、能力矩阵、风险边界、认证方式、默认路由、适配器标识等用于后续多平台扩展的核心语义。

用户未来目标是做多平台，并分成国内版和海外版。基于当前阶段约束，本设计选择“国内版优先，海外版预留”的演进路线。

## 2. 战略判断

### 2.1 不直接切换到 AiToEarn 底座

AiToEarn 已下载并分析到 `E:/tmp/AiToEarn`。它适合作为多平台能力参考，但不适合作为当前项目的主底座。

原因：

1. 当前项目已有 XHS 深水区资产，包括 XHS SDK、签名、账号、内容发现、草稿、发布、监控和自动任务。
2. AiToEarn 的技术栈是 NestJS、MongoDB、Next.js、Electron、Relay、插件和 MCP；当前项目主基线是 FastAPI、SQLAlchemy、React/Vite。
3. AiToEarn 的产品主线偏多平台内容营销、分发和变现；当前第一阶段目标是让国内平台运营底座成型，并保持小红书主流程稳定。
4. 直接切底座会造成大规模重写，短期不会提升小红书运营闭环。

AiToEarn 可参考的能力包括：发布日历、能力分层、Agent/MCP 工具思路、评论机会识别、AI 草稿任务化。不可直接引入的部分包括 Relay OAuth、插件作为主执行链、内容交易市场、Nest/Mongo 基础设施和默认自动互动。

### 2.2 不继续写死为“小红书专用系统”

虽然当前第一平台是小红书，但后续要接入国内多平台，并预留海外版。因此新增设计和代码不应继续把核心概念写死成 XHS-only。

目标是从：

```text
小红书运营系统
```

演进为：

```text
多平台智能运营系统，国内版优先；小红书是第一个完整平台实现，海外版预留接口。
```

## 3. 第一轮目标

第一轮 `/goal` 只做“多平台底座骨架”，不接新真实平台，不大改用户可见导航，不破坏现有小红书功能。

### 3.1 成功标准

1. 现有平台中心继续可用。
   - `frontend/src/pages/platform-select/platform-select-page.tsx` 继续作为平台入口。
   - `frontend/src/components/layout/platform-selector.tsx` 继续显示平台卡片。

2. 平台注册表从“展示列表”升级为“能力声明中心”。
   - `backend/app/core/platforms.py` 不只返回卡片信息，还声明平台区域、能力、风险、认证方式、默认路由和适配器标识。

3. XHS 成为第一个完整平台实现。
   - 现有 `/platforms/xhs/...` 路由保持不变。
   - 现有 XHS API 和页面不被移动，不做大重构。
   - XHS 当前能力被登记到能力矩阵中。

4. 国内版优先，海外版预留。
   - 第一轮平台清单以小红书、抖音、快手、微博、视频号、公众号、B站等为主。
   - 海外平台只在设计结构上预留 `region` 和 capability 体系，不进入第一轮实现范围。

5. 为下一轮接抖音、视频号或其它国内平台降低成本。
   - 后续加平台时，不应该重新设计账号、内容、发布、监控、互动这些核心概念，而是实现对应 adapter/capability。

### 3.2 非目标

第一轮不做：

- 不接真实抖音、快手或海外平台。
- 不做全局 UI 大改版。
- 不重构底层 XHS SDK、签名层、`apis/`、`xhs_utils/`、`static/`。
- 不做真实自动评论、自动关注或绕风控能力。
- 不迁移数据库到复杂多租户模型。
- 不引入 AiToEarn 的技术栈。
- 不实现海外 OAuth、App Review、Webhook、多时区排期或多语言内容系统。

## 4. 目标架构

目标架构分三层：

```text
Platform Center
  └── 用户进入不同平台工作区

Platform Core
  ├── Platform Registry
  ├── Capability Matrix
  ├── Account Core
  ├── Content Core
  ├── Publish Core
  ├── Monitoring Core
  ├── Engagement Core
  └── Workflow Core

Platform Implementations
  ├── xhs        当前完整实现
  ├── douyin     planned
  ├── kuaishou   planned
  ├── wechat     planned
  ├── bilibili   planned
  └── global/*   reserved
```

第一轮只落地 Platform Registry 和 Capability Matrix 的清晰结构；其它 Core 模块先定义边界，不强行重构现有 XHS 代码。

## 5. 核心模块边界

### 5.1 Platform Registry

Platform Registry 是平台事实源。它不再只是前端卡片数据，而是后端平台能力声明。

每个平台至少声明：

- `id`：平台 ID，如 `xhs`。
- `region`：`cn` 或 `global`。
- `name_cn`：中文名称。
- `name_en`：英文名称。
- `enabled`：当前是否开放真实工作区。
- `release_stage`：`enabled`、`beta`、`planned` 或 `unavailable`，作为平台发布阶段的 canonical 字段。
- `status`：legacy compatibility 字段；当平台处于 `planned` 时继续返回 `coming_soon`，其余阶段与 `release_stage` 对齐。
- `platform_type`：`content`、`social`、`commerce` 或 `hybrid`。
- `capabilities`：能力矩阵。
- `auth_modes`：认证方式。
- `risk_level`：平台整体风险等级。
- `default_route`：启用平台点击后的默认路由。
- `adapter_key`：后端适配器标识。

当前 `backend/app/core/platforms.py` 是第一轮改造起点。

### 5.2 Capability Matrix

Capability Matrix 用于回答：

> 这个平台现在能做什么？不能做什么？什么能力高风险？什么能力只是预留？

第一轮定义这些能力 key：

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

每个能力声明：

- `key`
- `status`：`available`、`partial`、`planned` 或 `blocked`
- `risk`：`low`、`medium` 或 `high`
- `requires_confirmation`
- `notes`

### 5.3 Account Core

Account Core 统一账号概念，但第一轮不强行重构现有表。

未来账号字段方向：

- `platform_id`
- `display_name`
- `auth_mode`
- `credential_status`
- `health_status`
- `risk_level`
- `last_checked_at`

第一轮只把 XHS 账号管理能力登记到能力矩阵。

相关现有文件：

- `backend/app/models/platform_account.py`
- `backend/app/api/accounts.py`
- `frontend/src/pages/platforms/xhs/accounts-page.tsx`

### 5.4 Content Core

Content Core 定义“一个内容资产，多平台版本”的未来方向。

未来分层：

- Content asset：标题、正文、图片、视频、标签、来源。
- Platform variant：平台特定标题、正文、标签、封面、发布参数。
- Source relation：来自采集、AI 生成、手动导入或改写。

第一轮不迁移现有内容库，只在设计中确立边界。

相关现有文件：

- `backend/app/models/note.py`
- `backend/app/api/notes.py`
- `frontend/src/pages/platforms/xhs/library-page.tsx`
- `frontend/src/pages/platforms/xhs/rewrite-page.tsx`

### 5.5 Publish Core

Publish Core 未来统一发布任务、排期、dry-run、真实发布、失败诊断、平台参数和风险确认。

第一轮只把 XHS 发布能力登记到 Capability Matrix，不改发布链路。

相关现有文件：

- `backend/app/models/publish.py`
- `backend/app/api/publish.py`
- `frontend/src/pages/platforms/xhs/publish-page.tsx`

### 5.6 Monitoring Core

Monitoring Core 未来统一关键词监控、竞品监控、品牌提及、评论线索和趋势发现。

当前 XHS 监控是第一个实现。

相关现有文件：

- `backend/app/models/monitoring.py`
- `backend/app/api/platforms/xhs/monitoring.py`
- `frontend/src/pages/platforms/xhs/monitoring-page.tsx`

### 5.7 Engagement Core

Engagement Core 未来统一评论读取、评论机会识别、AI 回复建议、人工确认和执行日志。

第一轮只定义边界，不做自动回复。国内平台互动执行风险高，默认只允许建议和人工确认。

### 5.8 Workflow Core

Workflow Core 未来统一：

```text
Discover -> Analyze -> Generate -> Review -> Schedule -> Publish -> Monitor -> Engage -> Report
```

当前 `backend/app/api/auto_tasks.py` 是 XHS 自动运营工作流的第一个样板。第一轮只登记 `workflow.auto_ops` 能力，不重写工作流引擎。

## 6. 数据结构设计

第一轮优先不建数据库表，先把平台能力定义放在代码配置层。原因是平台清单和能力矩阵还在快速演进期，用 Python dataclass / Pydantic schema 更轻，避免过早 Alembic 迁移。

### 6.1 PlatformMeta

建议扩展 `PlatformMeta`：

```python
PlatformMeta:
  id: PlatformId
  name_cn: str
  name_en: str
  enabled: bool
  release_stage: ReleaseStage
  region: PlatformRegion
  platform_type: PlatformType
  accent_color: str
  icon: str
  default_route: str | None
  adapter_key: str | None
  risk_level: RiskLevel
  auth_modes: list[AuthMode]
  capabilities: list[PlatformCapability]
```

### 6.2 PlatformCapability

```python
PlatformCapability:
  key: CapabilityKey
  status: CapabilityStatus
  risk: RiskLevel
  requires_confirmation: bool
  notes: str
```

### 6.3 枚举

```python
PlatformRegion:
  cn
  global

ReleaseStage:
  enabled
  beta
  planned
  unavailable

PlatformType:
  content
  social
  commerce
  hybrid

AuthMode:
  cookie
  qr_login
  oauth
  manual
  none

CapabilityStatus:
  available
  partial
  planned
  blocked

RiskLevel:
  low
  medium
  high
```

## 7. 平台清单第一版

### 7.1 国内平台

第一轮建议纳入平台注册表：

- `xhs`：enabled，完整 XHS 当前能力。
- `douyin`：planned。
- `kuaishou`：planned。
- `bilibili`：planned。
- `wechat_channels`：planned。
- `wechat_official`：planned。
- `weibo`：planned。

### 7.2 国内电商/交易平台

保留但不实现：

- `taobao`：planned。
- `xianyu`：planned。

### 7.3 海外预留

第一轮不在前端卡片展示海外平台，避免产品心智过早扩张。但数据结构必须支持：

- `tiktok`
- `youtube`
- `instagram`
- `facebook`
- `x`
- `linkedin`
- `pinterest`

这些平台可以暂不进入 `_PLATFORMS`，但枚举和设计不得阻止 future global platforms。

## 8. XHS 能力声明

`xhs` 第一轮能力声明如下：

| Capability | Status | Risk | Requires Confirmation | Notes |
|---|---|---|---|---|
| `account.manage` | available | medium | false | 已有账号矩阵能力 |
| `account.login_cookie` | available | high | true | Cookie 属敏感凭据 |
| `account.login_qr` | available | medium | false | 已有扫码登录路径 |
| `content.discover` | available | medium | false | 已有笔记发现/关键词能力 |
| `content.crawl_detail` | available | medium | false | 受接口和账号状态影响 |
| `content.library` | available | low | false | 已有内容库能力 |
| `content.rewrite` | available | low | false | 已有 AI 改写能力 |
| `asset.image_generate` | available | low | false | 已有图片工坊能力 |
| `asset.video_generate` | planned | medium | false | 视频工坊存在但生成能力需单独验证 |
| `publish.create_job` | available | medium | false | 已有发布任务能力 |
| `publish.schedule` | available | medium | false | 已有排期/任务能力 |
| `publish.dry_run` | available | low | false | 真实发布前应优先 dry-run |
| `publish.real_publish` | partial | high | true | 真实账号发布必须显式授权 |
| `monitoring.keyword` | available | medium | false | 已有关键词监控能力 |
| `monitoring.competitor` | available | medium | false | 已有竞品/监控模型 |
| `engagement.comment_read` | partial | medium | false | 评论读取受接口限制 |
| `engagement.reply_suggest` | planned | low | false | 建议回复可做，执行另议 |
| `engagement.reply_execute` | blocked | high | true | 第一轮明确不开放自动评论 |
| `workflow.auto_ops` | available | high | true | 自动运营属于高风险链路 |

`engagement.reply_execute` 必须明确为 `blocked`，避免造成“马上可以自动评论”的用户预期。

## 9. API 设计

当前已有：

```http
GET /platforms
```

第一轮保留该 API，并让返回字段更丰富。

### 9.1 平台列表

```http
GET /platforms
```

返回分页平台列表，包含基础信息和能力摘要。为兼容现有前端，原字段 `id`、`name_cn`、`name_en`、`enabled`、`status`、`accent_color`、`icon` 必须继续存在。其中 `release_stage` 是 canonical 字段；`status` 只作为 legacy compatibility 字段保留，`planned` 平台继续返回 `coming_soon`，其它阶段与 `release_stage` 对齐，避免前端一次性改动过大。

### 9.2 单个平台详情

```http
GET /platforms/{platform_id}
```

返回单个平台完整能力矩阵。

不存在平台返回：

```http
404 platform_not_found
```

第一轮不强制新增：

```http
GET /platforms/{platform_id}/capabilities
```

如果单平台详情已包含 `capabilities`，该接口可以后续再加，避免过度拆分。

## 10. 前端设计

### 10.1 PlatformMeta 类型

前端 `PlatformMeta` 类型需同步扩展：

```ts
type PlatformMeta = {
  id: string;
  name_cn: string;
  name_en: string;
  enabled: boolean;
  status?: string;
  release_stage: "enabled" | "beta" | "planned" | "unavailable";
  region: "cn" | "global";
  platform_type: "content" | "social" | "commerce" | "hybrid";
  accent_color: string;
  icon: string;
  default_route?: string | null;
  adapter_key?: string | null;
  risk_level: "low" | "medium" | "high";
  auth_modes: string[];
  capabilities?: PlatformCapability[];
};
```

### 10.2 平台中心卡片

当前 `frontend/src/components/layout/platform-selector.tsx` 根据 `enabled` 决定 Active / Coming Soon。

第一轮可轻量增强，但不做大改版：

- `enabled=true`：显示 Active。
- `release_stage=planned`：显示 Planned 或 Coming Soon。
- `release_stage=beta`：显示 Beta。
- `risk_level=high`：可展示小标签，但不阻断点击。

为了范围控制，第一轮 UI 可以只保证兼容新字段，不必须完整展示能力矩阵。

### 10.3 默认路由

当前平台卡片写死：

```ts
const href = platform.enabled
  ? `/platforms/${platform.id}/dashboard`
  : `/platforms/${platform.id}`;
```

建议改为：

```ts
const href = platform.enabled && platform.default_route
  ? platform.default_route
  : `/platforms/${platform.id}`;
```

这样 Platform Registry 成为路由事实源。

### 10.4 路由

当前路由已经平台化：

- `/platforms/xhs/dashboard`
- `/platforms/xhs/accounts`
- `/platforms/xhs/publish`
- `/platforms/xhs/auto-ops`

第一轮不改路由结构，只要求：

- 小红书卡片仍进入 `/platforms/xhs/dashboard`。
- 未启用平台继续进入 Coming Soon。
- 不存在平台显示 Coming Soon 或 Not Found 风格页面，不跳到小红书兜底。

## 11. 错误处理

### 11.1 平台不存在

请求 `GET /platforms/{platform_id}` 时，如果平台不存在，返回 `404 platform_not_found`。

前端显示 Coming Soon / Not Found 风格页面，不跳转到 XHS。

### 11.2 平台存在但未启用

未启用平台：

- API 仍返回平台元数据。
- `release_stage=planned` 表示 canonical 的发布阶段；legacy `status` 继续返回 `coming_soon` 供旧消费者使用。
- 前端展示 planned / coming soon。
- 不允许进入真实业务工作台。

### 11.3 能力不存在或不可用

如果未来某页面依赖能力，例如发布页依赖 `publish.create_job`：

- capability 不存在，或 status 不是 `available` / `partial`，页面应提示“该平台暂未开放此能力”。
- 页面不应显示可提交表单。

第一轮只定义规则，不强制所有页面接 capability gate。

### 11.4 高风险能力

如果能力声明：

```text
risk = high
requires_confirmation = true
```

表示未来执行时必须显式确认。第一轮先在数据结构中声明，不改真实动作链路。

## 12. 安全边界

### 12.1 XHS 原生能力

继续遵守项目 `CLAUDE.md`：

- 不直接改 `apis/`、`xhs_utils/`、`static/` 底层签名层。
- XHS PC/Creator 操作默认低频、串行。
- 发布和自动运营默认 dry-run / 人工确认。
- 不实现绕风控、验证码绕过、批量号池、高频自动化。

### 12.2 多平台扩展

国内平台第一原则：

> 能建议，不自动执行；能低频，不高频；能人工确认，不静默执行。

海外平台预留但不实现：

- OAuth token。
- App Review。
- Webhook。
- Rate limit。
- 多时区排期。
- 多语言内容。

### 12.3 AiToEarn 参考边界

可以参考：

- 发布日历。
- 能力分层。
- Agent/MCP 工具思想。
- 评论机会识别。

不能直接引入：

- Relay OAuth。
- 插件作为主执行链。
- 内容交易市场。
- Nest/Mongo 基础设施。
- 自动互动默认开启。

## 13. 验证标准

### 13.1 后端测试

第一轮至少验证：

- 平台列表 API 返回成功。
- `xhs` 平台详情包含完整能力矩阵。
- planned 平台可返回元数据但 `enabled=false`。
- 不存在平台返回 404。
- 能力字段序列化稳定。

建议在 `tests/` 下新增或扩展 platforms registry 相关测试。

### 13.2 前端验证

第一轮至少验证：

- 平台选择页正常加载。
- 小红书卡片仍可进入 `/platforms/xhs/dashboard`。
- 未启用平台仍进入 Coming Soon。
- 前端 `fallbackPlatforms` 与后端字段兼容。
- TypeScript build 通过。

### 13.3 回归验证

现有小红书关键页面不应受影响：

- dashboard
- accounts
- discovery
- library
- drafts/rewrite
- publish
- monitoring
- auto-ops

第一轮不是功能迁移，任何 XHS 主流程坏掉都算失败。

## 14. `/goal` 阶段拆分建议

### Phase 1：平台注册表设计落地

目标：

- 扩展 backend platform metadata。
- 定义 enums 和 capability schema。
- 保持 `GET /platforms` 兼容。
- 新增 `GET /platforms/{platform_id}`。

验收：

- API 测试通过。
- `xhs` 能力矩阵可读。
- planned 平台可读。

### Phase 2：前端类型与平台中心兼容

目标：

- 扩展前端 `PlatformMeta` 类型。
- 更新 `fallbackPlatforms`。
- 平台卡片支持 `default_route`。
- 保持现有 UI 不大改。

验收：

- 小红书仍可进入 dashboard。
- planned 平台仍 Coming Soon。
- 前端 build 通过。

### Phase 3：能力矩阵文档化与 XHS 映射

目标：

- 写清 XHS 当前能力与代码映射。
- 明确哪些能力是 available、partial、planned、blocked。
- 明确哪些 high risk 能力需要人工确认。

验收：

- 文档能指导后续接抖音或视频号。
- 不含“自动评论马上可用”等误导表述。

### Phase 4：回归验证与任务交接

目标：

- 跑后端测试。
- 跑前端 build。
- 检查关键页面入口。
- 输出下一轮建议：接第二平台前的最小 adapter 设计。

验收：

- 验证证据明确。
- 没有遗留 in-progress 状态。
- 不自动 commit，除非用户明确要求。

## 15. 下一步建议

第一轮完成后，下一轮不要急着接真实抖音。建议先做：

> Platform Adapter Contract Design

也就是定义每个平台 adapter 要实现哪些接口：

- account
- content discovery
- publish
- monitoring
- engagement
- workflow

再选择抖音或视频号做第二平台最小验证。

## 16. `/goal` 推荐输入

后续可以用下面的 `/goal` 触发实现：

```text
/goal 按 docs/superpowers/specs/2026-06-09-multiplatform-ops-foundation-design.md 实现第一轮多平台运营底座骨架。只做 Platform Registry + Capability Matrix + 前端平台中心兼容，不接新真实平台，不大改导航，不重构 XHS 底层 SDK。分阶段执行，每阶段给 review 和验证证据。
```

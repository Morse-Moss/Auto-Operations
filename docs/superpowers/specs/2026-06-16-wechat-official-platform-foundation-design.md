# 微信公众号平台骨架层设计：先准备主系统底座，正式接入前先调研开源系统

## 1. 背景

当前主系统基线是 `XHS_ALL_IN_ONE`，项目已经从小红书单平台系统演进出多平台入口和能力注册表。现有事实源包括：

- 平台注册表：`backend/app/core/platforms.py`
- 平台注册 API：`backend/app/api/platforms/registry.py`
- 平台选择页：`frontend/src/pages/platform-select/platform-select-page.tsx`
- 平台卡片组件：`frontend/src/components/layout/platform-selector.tsx`
- 平台化路由：`frontend/src/app/router.tsx`
- 平台 adapter 合同雏形：`backend/app/platforms/contracts.py`

微信公众号已经在平台注册表中作为 `wechat_official` 占位存在，但当前状态是 `planned` / `enabled=False`，用户只能看到 Coming Soon，系统内没有公众号独立 API、adapter、前端页面或状态说明。

用户当前决策是：先把微信公众号平台底座做好；真正接入微信公众号 API 前，必须先调研 GitHub 已有开源系统和微信官方能力边界，再正式设计接入方案。

## 2. 设计结论

本轮采用 **平台骨架层** 方案。

本轮只把系统准备成“可以承载公众号平台开发”的状态，不接微信 API，不引入 GitHub 开源项目代码，不实现真实授权、素材上传、草稿同步、预览或群发发布。

核心判断：

1. 公众号是独立平台工作区，不是小红书子功能。
2. 公众号需要独立 API、adapter、前端页面目录，避免后续把逻辑塞进 XHS 目录。
3. 本轮只开放本地状态和能力说明，不开放任何真实外部动作。
4. 正式接入前，必须先完成 GitHub 开源系统调研和微信官方 API 策略确认。
5. 群发发布属于高风险动作，正式实现前必须保持 blocked，并要求动作级确认。

## 3. 用户体验目标

用户进入平台中心时，应能明确理解公众号平台的当前状态：

- 公众号不是单纯 Coming Soon，而是 Beta / Preparing 状态，说明平台骨架已纳入主系统。
- 点击公众号卡片可以进入独立公众号工作区。
- 公众号工作区展示当前准备状态、能力清单和下一步调研要求。
- 页面不提供账号绑定、AppID/AppSecret 输入、素材上传、预览发送或群发按钮，避免用户误以为真实接入已经可用。
- 页面明确提示：正式接入前会先调研 GitHub 开源系统，不直接从零盲接微信 API。

## 4. 范围

### 4.1 本轮做

1. 更新 `wechat_official` 平台注册信息。
   - 从 planned/disabled 调整为 beta/enabled。
   - 增加 `default_route`。
   - 增加 `adapter_key`。
   - 保持 `auth_modes=[AuthMode.NONE]`，不开放真实授权。
   - 声明最小能力矩阵。

2. 新增公众号后端 API 目录。
   - `backend/app/api/platforms/wechat_official/__init__.py`
   - `backend/app/api/platforms/wechat_official/overview.py`
   - overview 接口只返回本地准备状态、能力清单、风险说明和调研要求。

3. 新增公众号 adapter 目录。
   - `backend/app/adapters/wechat_official/__init__.py`
   - `backend/app/adapters/wechat_official/adapter.py`
   - adapter 只提供 NotImplemented / fail-closed 骨架，不调用外部服务。

4. 新增公众号前端页面目录。
   - `frontend/src/pages/wechat-official/wechat-official-dashboard.tsx`
   - 页面展示 Beta 状态、准备清单、能力卡和下一步。

5. 新增前端 API 方法和类型。
   - 用于读取公众号 overview/status。
   - 不新增真实账号绑定、素材、草稿或发布 payload。

6. 新增路由。
   - `/platforms/wechat-official/dashboard`

7. 新增测试。
   - 后端验证平台注册和 overview 接口。
   - 前端至少通过 build 验证路由和类型。

### 4.2 本轮不做

本轮明确不做：

- 不接微信公众号 API。
- 不保存 AppID、AppSecret、Token、EncodingAESKey 或任何真实凭据。
- 不新增真实公众号账号绑定表单。
- 不新增公众号素材库表。
- 不新增公众号文章表。
- 不实现素材上传。
- 不实现草稿同步到微信。
- 不实现预览发送。
- 不实现群发发布。
- 不从 GitHub 拉代码、复制实现或引入开源依赖。
- 不改造小红书现有 XHS API、SDK、签名层或发布链路。
- 不把公众号逻辑放进 `backend/app/api/platforms/xhs/`。

## 5. 后端设计

### 5.1 平台注册表

更新 `backend/app/core/platforms.py` 中的 `wechat_official`：

```text
id = PlatformId.WECHAT_OFFICIAL
name_cn = "公众号"
name_en = "WeChat Official"
enabled = True
release_stage = ReleaseStage.BETA
region = PlatformRegion.CN
platform_type = PlatformType.CONTENT
accent_color = "#0a9b57"
icon = "wechat_official"
default_route = "/platforms/wechat-official/dashboard"
adapter_key = "wechat_official"
risk_level = RiskLevel.MEDIUM
auth_modes = [AuthMode.NONE]
```

能力矩阵使用现有 `CapabilityKey`，不为公众号过早扩展新 key：

| CapabilityKey | 状态 | 风险 | 确认 | 说明 |
|---|---|---|---|---|
| `account.manage` | planned | medium | false | 未来用于公众号配置管理；本轮不开放凭据输入。 |
| `content.library` | planned | low | false | 未来用于公众号图文内容库；本轮只展示方向。 |
| `content.rewrite` | planned | low | false | 未来用于将内容改写为公众号文章；本轮不实现。 |
| `publish.dry_run` | planned | medium | false | 未来用于发布前模拟和校验；本轮不实现。 |
| `publish.real_publish` | blocked | high | true | 群发发布高风险，正式 QA 和确认机制完成前阻断。 |

不新增 `research_required` 这类 capability key。调研要求属于公众号 overview 的状态说明，不属于全平台能力模型。

### 5.2 公众号 overview API

新增 API 前缀：

```text
/api/wechat-official/overview
```

返回结构建议：

```json
{
  "platform_id": "wechat_official",
  "stage": "foundation_ready",
  "external_integration_enabled": false,
  "research_required_before_integration": true,
  "research_topics": [
    "GitHub 微信公众号开源系统架构调研",
    "微信官方草稿箱、素材、群发、预览 API 能力边界确认",
    "凭据保存与加密策略确认",
    "真实群发风险与 QA 流程确认"
  ],
  "capabilities": [
    {
      "key": "account.manage",
      "label": "账号配置",
      "status": "planned",
      "message": "正式接入前不开放 AppID/AppSecret 配置。"
    }
  ],
  "blocked_actions": [
    "真实授权",
    "素材上传",
    "草稿同步",
    "预览发送",
    "群发发布"
  ]
}
```

接口只读取本地静态状态，不依赖网络、不依赖微信账号、不产生外部副作用。

### 5.3 公众号 adapter 骨架

新增 `backend/app/adapters/wechat_official/adapter.py`，定义 fail-closed adapter。

设计原则：

- adapter 可以被后续正式接入替换或扩展。
- 本轮所有真实动作返回明确的 not implemented / blocked 语义。
- 不抛出含糊的底层异常，不让调用方误判为临时网络错误。
- 不导入微信 SDK 或第三方开源库。

建议接口语义：

```text
WechatOfficialAdapter.get_status() -> 本地状态
WechatOfficialAdapter.assert_external_integration_enabled() -> 始终拒绝
```

真实操作方法如果需要预留，必须命名清楚并返回 blocked，不允许留空静默成功。

### 5.4 API 注册

新增公众号 router 后，需要挂载到主 API router。命名保持清晰，不与微信视频号混淆：

- Python package：`wechat_official`
- URL path：`/wechat-official/...`
- Platform ID：`wechat_official`
- 前端路径：`/platforms/wechat-official/dashboard`

## 6. 前端设计

### 6.1 路由

新增路由：

```text
/platforms/wechat-official/dashboard
```

该路由渲染 `WechatOfficialDashboard`。

### 6.2 页面信息架构

页面分四块：

1. 顶部标题区
   - 公众号
   - WeChat Official
   - Beta / Foundation Ready 标签

2. 当前状态卡
   - 平台骨架：已启用
   - 外部接入：未启用
   - 真实动作：全部阻断
   - 接入前置：GitHub 开源系统调研 + 微信官方 API 策略确认

3. 能力卡
   - 账号配置：待调研
   - 图文内容库：待设计
   - 文章改写：待设计
   - 发布 dry-run：待设计
   - 群发发布：高风险，已阻断

4. 下一步
   - 调研 GitHub 已有微信公众号开源系统。
   - 形成正式接入设计。
   - 再决定授权、素材、草稿、预览、群发的实现路径。

### 6.3 交互边界

页面不提供任何会诱导真实接入的操作按钮。

允许的交互：

- 返回平台中心。
- 查看准备状态。
- 查看能力说明。

不允许的交互：

- 绑定公众号。
- 输入 AppID/AppSecret。
- 上传素材。
- 同步草稿。
- 预览发送。
- 群发发布。

## 7. 数据与安全

本轮不新增数据库表，不新增 Alembic migration。

原因：正式接入前还没有完成 GitHub 开源系统调研和微信官方 API 能力确认，过早设计账号、素材、草稿、文章表会增加返工风险。

本轮安全策略：

- 不保存任何公众号凭据。
- 不调用任何微信外部接口。
- 不产生外部副作用。
- 群发发布在 registry 中保持 blocked。
- overview/status 接口只返回静态本地状态。
- 不在日志、测试数据或文档中写入真实公众号凭据示例。

## 8. 错误处理

由于本轮没有外部调用，错误主要来自本地路由或状态读取。

处理规则：

- overview 接口应稳定返回 200 和本地状态。
- 若平台 ID 不存在，沿用平台注册 API 的 404 语义。
- 若未来调用 adapter 的真实动作，必须返回明确 blocked/not implemented，不允许静默成功。
- 前端请求 overview 失败时，显示“公众号底座状态读取失败，请检查后端服务”，不显示“微信连接失败”，避免误导用户以为已经连接微信。

## 9. 测试与验证

### 9.1 后端验证

至少验证：

1. `GET /api/platforms` 中 `wechat_official` 存在。
2. `wechat_official.release_stage == "beta"`。
3. `wechat_official.enabled == true`。
4. `wechat_official.default_route == "/platforms/wechat-official/dashboard"`。
5. `wechat_official.auth_modes == ["none"]`。
6. `publish.real_publish` 能力为 blocked 且 requires_confirmation 为 true。
7. `GET /api/wechat-official/overview` 返回 `external_integration_enabled=false`。
8. overview 返回 `research_required_before_integration=true`。

### 9.2 前端验证

至少验证：

1. `npm run build` 在 `frontend/` 下通过。
2. TypeScript 类型通过。
3. 路由 `/platforms/wechat-official/dashboard` 能编译进入应用。
4. 页面文案不声称已经支持真实授权、同步或发布。

### 9.3 不需要验证

本轮不需要验证：

- 微信 OAuth。
- 公众号素材上传。
- 公众号草稿箱。
- 预览消息。
- 群发发布。
- GitHub 开源项目运行。

## 10. 对用户的影响

本轮完成后，用户会看到公众号平台已经纳入系统骨架，知道后续正式接入的方向和前置调研要求。

直接收益：

- 平台中心从“只有小红书可用，其它都是 Coming Soon”变成“公众号已进入 Beta 准备区”。
- 后续开发有稳定目录和路由边界。
- 后续 GitHub 调研结果可以落到明确 adapter/API/page 位置。
- 避免在调研前提前保存凭据或误触发高风险群发。

不会产生的影响：

- 不影响现有小红书功能。
- 不影响灰豚关键词发现链路。
- 不改变数据库结构。
- 不接触真实公众号账号。

## 11. 后续阶段

本轮之后，正式接入前需要新增独立调研规格或调研报告，至少覆盖：

1. GitHub 微信公众号开源系统调研。
   - 技术栈。
   - 授权方式。
   - 素材/草稿/群发实现路径。
   - 数据模型。
   - 安全处理。
   - 可参考和不可直接引入的部分。

2. 微信官方 API 能力确认。
   - 草稿箱 API。
   - 素材管理 API。
   - 预览 API。
   - 群发 API。
   - 频率限制。
   - 资质和权限要求。

3. 正式接入设计。
   - 凭据模型。
   - 素材模型。
   - 草稿模型。
   - dry-run 和 QA。
   - 真实群发确认机制。

只有完成这些调研和设计后，才能进入真实接入实现。

## 12. 完成标准

本轮开发完成应满足：

1. 平台选择页中公众号可进入 Beta 工作区。
2. 后端平台注册表中公众号为 beta/enabled。
3. 后端存在公众号 overview/status API，且只返回本地状态。
4. 后端存在公众号 adapter 骨架，真实外部动作 fail closed。
5. 前端存在公众号 dashboard 页面，清楚说明当前只是骨架层。
6. 没有新增真实凭据输入、保存或外部调用。
7. 后端相关测试通过。
8. 前端 build 通过。

## 13. 自审结果

- 无 `TBD` / `TODO` / 空白章节。
- 设计范围聚焦在公众号平台骨架层，没有包含正式微信 API 接入。
- 后端、前端、数据、安全、测试边界一致。
- 已明确不新增数据库表，避免在 GitHub 调研前过早定模型。
- 已明确真实群发保持 blocked，避免高风险动作误开放。
- 与既有多平台底座和 Platform Adapter Contract 设计兼容。

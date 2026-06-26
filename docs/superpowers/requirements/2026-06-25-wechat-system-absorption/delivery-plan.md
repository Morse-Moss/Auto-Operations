# 公众号系统完整吸收分阶段交付方案

## 总体判断

用户要求的是完整吸收公众号获取系统能力，而不是修 Redfox URL。当前主系统已有公众号数据模型和部分产品链路，最佳路线不是搬迁外部系统，而是把外部系统能力拆成 provider 和产品模块，逐步并入当前 FastAPI/React/SQLAlchemy 主系统。

## 分阶段路线

### Phase 0：规则和 provider 骨架（0.5-1 天）

目标：先建立主系统内的公众号 provider 规则，避免后续散落实现。

交付：

- 设计文档：公众号多源采集 provider 架构。
- Provider 接口约定：
  - `fetch_article_url`
  - `search_accounts`
  - `sync_account_articles`
  - `refresh_metrics`
  - `refresh_comments`
  - `health_check`
- 统一错误模型：
  - `provider_unavailable`
  - `wechat_verification_required`
  - `rate_limited`
  - `login_expired`
  - `article_deleted`
  - `parse_failed`
- 确定 P0 不新增大量表，优先复用 job/raw_json/ingest_errors。

验收：

- 后续 provider 都能通过统一接口接入。
- Redfox 不再被视为唯一核心源。

### Phase 1：URL/正文获取闭环（2-4 天 + 30% 风险池）

目标：解决当前最痛点，Redfox 详情失败时仍能通过微信文章页面获取正文。

交付：

- `WechatOfficialArticlePageProvider`：单篇 URL HTML 获取。
- 微信文章 HTML parser：
  - title、author、publish_time、digest
  - content_html、content_text
  - images
  - account/biz 尝试提取
  - 普通图文、图片文、短内容基础支持
- `import-url` 统一入口：从 `/redfox/import-url` 逐步迁到 `/articles/import-url`。
- Redfox 详情失败自动 fallback 到 ArticlePageProvider。
- 失败诊断：验证页、删除页、登录页、解析失败，不保存空壳。
- 内容库完整度展示：正文/图片/provider。

验收：

- Redfox `queryArticleDetail` SSL 失败时，给定公开微信文章 URL 仍能保存正文和图片。
- 对验证页/删除页返回明确错误。
- 相关后端测试覆盖 Redfox 成功、Redfox 失败 fallback 成功、fallback 失败不保存。

### Phase 2：公众号后台真实采集（5-8 天 + 35% 风险池）

目标：吸收公众号后台链路，做到搜索公众号和同步历史文章，不再只依赖 Redfox。

交付：

- 真实 QR 登录 client：
  - 获取二维码
  - 轮询扫码状态
  - 完成登录保存 cookie/token
  - 过期时间和状态展示
- SearchBiz provider：搜索公众号，保存 fakeid/biz/name/avatar/alias。
- AppMsgPublish/Profile provider：同步公众号历史文章列表。
- 账号详情页：展示账号、历史同步按钮、最近任务。
- 批量正文补全任务：历史列表入库后低频补正文。
- 限频策略：用户级、provider 级、任务级。

验收：

- 用户扫码登录后能搜索公众号。
- 选择公众号后能同步最近 N 篇文章列表。
- 文章列表可批量补正文进入内容库。
- 登录过期会提示重新授权。

### Phase 3：指标、评论、图片与内容管理（5-8 天 + 35% 风险池）

目标：吸收完整内容运营需要的数据层和管理层。

交付：

- Credential 管理页：显示哪些文章/账号可采集敏感数据。
- 阅读量、点赞、分享、评论数采集。
- 评论与评论回复采集。
- 图片代理或本地化策略：先支持预览稳定，再考虑导出资源打包。
- 内容管理增强：分类、标签、收藏、已读、黑名单/删除后跳过。
- 失败样本保存和重试。

验收：

- 凭证有效时可刷新文章指标和评论。
- 凭证缺失时用户知道需要准备什么。
- 内容库能按完整度、分类、状态筛选。

### Phase 4：RSS、导出、通知与自动更新（5-10 天 + 30% 风险池）

目标：吸收系统性运营能力。

交付：

- 公众号订阅：启用/停用、轮询间隔、分类。
- RSS feed 生成：单公众号、分类、全部。
- 定时轮询任务。
- 导出：优先 JSON/Markdown/HTML，再做 Excel/DOCX/PDF。
- 通知：授权过期、任务失败、采集完成，可接飞书/企微 webhook。
- 运营仪表盘：采集成功率、失败类型、授权状态、近期新增。

验收：

- 可把公众号订阅生成 RSS。
- 定时任务能发现新文章并入库。
- 用户能导出选中文章。
- 关键失败有通知。

### Phase 5：浏览器兜底与高级采集节点（Backlog，另估）

目标：提升风控场景成功率和多环境采集能力。

交付候选：

- 本机浏览器/CDP provider。
- 用户手动验证后继续采集。
- 服务器 Playwright provider。
- 多节点/级联采集。

触发条件：

- Phase 1/2 中 HTTP/provider 成功率不能满足业务。
- 用户明确需要无人值守或多机器采集。

## 初步工期范围

在不引入高频采集、不做验证码绕过、不做多节点的前提下：

| 范围 | 基础工期 | 风险池 | 总范围 |
|---|---:|---:|---:|
| Phase 0-1：恢复 URL/正文闭环 | 2.5-5 天 | 30% | 3-7 天 |
| Phase 0-2：加后台登录、搜索、历史文章 | 7.5-13 天 | 35% | 10-18 天 |
| Phase 0-3：加指标/评论/内容管理 | 12.5-21 天 | 35% | 17-29 天 |
| Phase 0-4：接近完整吸收 | 17.5-31 天 | 30%-35% | 23-42 天 |

说明：这是需求分析阶段估算，不是固定承诺。微信接口变动、真实账号授权、风控成功率会显著影响工期。

## 开发验收方式

每阶段都必须有：

- 后端单元/集成测试。
- 至少 1 条真实或录制样本链路验证。
- 失败状态样本验证。
- 前端可见反馈验证。
- 不保存空壳、不伪造指标、不吞底层错误。

## 下一步建议

先进入 Phase 0-1：

1. 写正式设计文档：`docs/superpowers/specs/2026-06-25-wechat-multi-provider-absorption-design.md`。
2. 写实施计划：`docs/superpowers/plans/2026-06-25-wechat-multi-provider-absorption.md`。
3. 第一轮实现只做 provider 骨架 + URL/正文闭环，解决 Redfox 详情失败导致 URL 导入不可用的问题。
4. 第二轮再做公众号后台登录和历史文章同步。

## 范围变更触发重估

以下需求加入时必须重估：

- 要求无人值守高频批量采集。
- 要求验证码自动处理或风控绕过。
- 要求真实公众号发布/群发/修改后台内容。
- 要求多机器采集节点。
- 要求完整高保真 PDF/DOCX 导出作为首期验收。
- 要求作为独立 RSS SaaS 对外开放。

# 已下载公众号系统复用评估

## 评估对象

| 系统 | 本地路径 | 上游 | 最近提交 | License | 结论 |
|---|---|---|---|---|---|
| wechat-article-exporter | `e:/tmp/wechat-article-exporter` | `https://github.com/wechat-article/wechat-article-exporter` | `8cf0641 2026-06-15 2.3.19` | MIT | 可参考/可二开，技术栈不同 |
| wechat-download-api | `e:/tmp/wechat-open-source-research/wechat-download-api` | `https://github.com/tmwgsicp/wechat-download-api.git` | `2e44427 2026-06-07` | AGPL-3.0 | 只能思想吸收或外部服务隔离，不直接拷代码 |
| we-mp-rss | `e:/tmp/wechat-open-source-research/we-mp-rss` | `https://github.com/rachelos/we-mp-rss.git` | `f1d0c9d 2026-06-14` | MIT | 功能完整，可参考架构和部分二开思想 |
| wechat-reader | `e:/tmp/wechat-open-source-research/wechat-reader` | `https://github.com/xiguawang/wechat-reader.git` | `f7b6413 2026-03-27` | MIT | 适合作为浏览器兜底/状态诊断参考 |
| wechat-article-crawler | `e:/tmp/wechat-open-source-research/wechat-article-crawler` | `https://github.com/gxcsoccer/wechat-article-crawler.git` | `b9712f0 2026-03-24` | 未在本轮确认 | 适合参考单篇文章解析，不作为主依赖 |

## 1. wechat-article-exporter

### 主要能力

- 公众号后台扫码登录与 Cookie/token 管理。
- 搜索公众号：`searchbiz`。
- 通过公众号后台接口拉取历史文章：`appmsgpublish`、`profile_ext_getmsg`。
- 下载文章 HTML，缓存到 IndexedDB。
- 阅读量、评论、回复等需要 credential 的数据采集。
- HTML/JSON/Excel/TXT/Markdown/DOCX 导出。
- 代理下载、公共/私有代理、失败重试、调试缓存。

### 可吸收部分

- 公众号后台接口链路：登录、searchbiz、appmsgpublish、comment。
- `proxyMpRequest` 的请求头与 Cookie 透传模式。
- 下载队列、代理失败冷却、并发限制思想。
- `validateHTMLContent` 对成功/删除/异常页面的分类。
- `parseCgiDataNew` 提取评论 ID、bizuin 等页面脚本数据的思想。
- 导出格式能力可以作为后续“素材导出”增强。

### 不能直接照搬的部分

- 前端是 Nuxt/Vue/Dexie，与当前 React/FastAPI/SQLAlchemy 不同。
- 客户端 IndexedDB 缓存不适合作为主系统事实源。
- 其代理公共节点和导出 UI 不应直接迁入。

### 模块策略

- 公众号后台接口：二开重写。
- 下载/队列/代理策略：二开重写。
- 导出能力：分阶段重写或接入当前导出能力。

## 2. wechat-download-api

### 主要能力

- `POST /api/article`：通过 URL 获取文章标题、HTML 正文、纯文本、图片、作者、发布时间。
- `GET /api/public/searchbiz`：公众号搜索。
- `GET /api/public/accountinfo`：公众号主体信息。
- `GET /api/articles`、`/api/articles/search`：历史文章和搜索。
- RSS 订阅、分类、黑名单、历史抓取、图片代理、Webhook 通知。
- `curl_cffi` Chrome TLS 指纹模拟、SOCKS5 代理池、三层限频。

### 可吸收部分

- 单篇文章 URL 获取和解析的降级路径。
- `has_article_content`、`is_article_unavailable`、验证页/登录页/删除页的判断逻辑。
- `extract_article_info` 对普通文章、图片文章、短内容、音频内容的解析策略。
- 图片代理/图片 URL 规范化思想。
- 限频策略：全局、用户/IP、文章请求间隔。
- RSS 订阅和历史轮询模型。

### 许可证约束

该项目为 AGPL-3.0。若直接复制、改造并作为网络服务提供，可能触发源代码开放义务。当前主系统不应直接拷贝其实现文件。允许：

- 研究公开行为和接口边界。
- 重新实现等价能力。
- 临时作为本地外部服务验证，但需明确隔离和合规风险。

### 模块策略

- 单篇 URL fetcher：重写。
- 状态诊断：重写。
- RSS/黑名单/分类：参考产品能力，按当前模型重写。
- 代理池/限频：重写。

## 3. we-mp-rss

### 主要能力

- 完整公众号订阅/RSS 系统。
- 扫码授权。
- 公众号搜索、添加、更新、删除、状态管理。
- 文章列表、文章详情、刷新单篇、去重、清理、已读/收藏。
- 内容获取 Web/API 双模式。
- Playwright 浏览器获取正文，移动端模式、图片滚动加载。
- 配置管理、缓存、通知、Access Key、级联系统、多节点任务分发。
- 导出 md/docx/pdf/json。

### 可吸收部分

- 文章内容获取模式：`web` 优先、`api` 兜底。
- Playwright 获取文章正文和图片懒加载的设计。
- 订阅号状态、文章刷新任务、任务状态查询。
- 文章已读/收藏/清理/去重等内容管理能力。
- 级联系统可作为远期“采集节点”设计参考。
- 环境异常统计和授权过期提醒。

### 不能直接照搬的部分

- 它本身是完整 RSS 产品，目标与当前主系统不同。
- Python 版本要求、配置系统、认证系统与当前项目不一致。
- 级联系统、用户系统、Access Key、缓存系统若直接接入会显著扩大复杂度。

### 模块策略

- 文章内容获取：二开重写。
- RSS 订阅：二开重写。
- 文章管理：部分直接映射到当前内容库。
- 级联节点：远期增强，不进 MVP。

## 4. wechat-reader

### 主要能力

- 面向 Agent 的微信公众号文章阅读工具。
- 支持 attach/launch/playwright/auto 浏览器策略。
- 输出结构化状态：`ok`、`captcha_required`、`rate_limited`、`article_not_rendered`、`navigation_failed`。
- 能复用真实浏览器会话。
- 支持 MCP、CLI、Python API。

### 可吸收部分

- 状态模型和用户提示策略。
- 浏览器兜底设计：Redfox/HTTP 都失败时，可让用户在真实浏览器完成验证。
- DOM 提取字段：title、author、account、content、html、publish_time。

### 模块策略

- 状态模型：直接借鉴重写。
- 浏览器兜底：二阶段接入。
- MCP/CLI：不纳入主系统。

## 5. wechat-article-crawler

### 主要能力

- 单篇微信文章抓取。
- MicroMessenger User-Agent。
- `#js_content` 等 DOM 提取。
- data-src 图片修正。
- Markdown 生成和本地图片下载。

### 可吸收部分

- 单篇 URL 解析、图片懒加载处理、Markdown 清理。
- 适合用于第一阶段 URL fetcher 的测试样例参考。

### 模块策略

- 不作为依赖。
- 解析策略重写到主系统。

## 总体复用结论

1. 当前主系统已经有公众号核心数据模型，不能把任何一个外部系统整体替换为主入口。
2. 最优策略是“能力吸收，不是系统迁移”：
   - 以当前 FastAPI/React/SQLAlchemy 为主干。
   - 把外部系统拆成功能模块逐步并入。
   - Redfox 变成多源采集器之一，不再是唯一核心。
3. License 决策：
   - MIT 项目可在保留版权声明前提下参考/二开，但仍建议按当前代码风格重写关键模块。
   - AGPL 项目只做行为学习和外部验证，不复制实现。
4. 最高优先级应是恢复并扩展“文章获取闭环”：搜索账号 → 同步历史文章 → 获取正文/图片/指标/评论 → 入内容库 → 分析/草稿。

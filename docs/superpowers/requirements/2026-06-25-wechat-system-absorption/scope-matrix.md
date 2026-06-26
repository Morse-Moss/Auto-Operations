# 公众号系统完整吸收范围矩阵

## 当前主系统已有能力基线

当前主系统已经存在以下公众号模块基础：

- 数据模型：账号、后台登录会话、文章 credential、代理节点、采集任务、文章、快照、指标、评论、评论回复、 ingest error、Redfox 配置、草稿来源、内容库删除墓碑。
- 服务：后台登录会话占位、账号搜索/文章同步适配入口、代理节点、credential、评论、内容库、Redfox 采集、草稿、飞书同步、readiness。
- 前端类型和页面：公众号内容库、dashboard、Redfox 配置/采集、内容详情、分析、草稿生成。

现状问题：大量基础表和接口已铺好，但“真实公众号后台/网页采集能力”仍主要依赖占位 upstream payload 或 Redfox，缺少完整 provider 层。

## 吸收后的目标模块分层

```text
公众号模块
├─ Provider 层
│  ├─ WeChat Backend Provider：公众号后台登录、搜索、历史文章、阅读量/评论
│  ├─ WeChat Article Page Provider：单篇 URL 正文/图片/状态识别
│  ├─ Browser Provider：真实浏览器兜底、验证页诊断
│  ├─ Redfox Provider：第三方爆文/账号/URL 增强源
│  └─ RSS Provider：订阅源生成和定时轮询
├─ Ingestion 层
│  ├─ 统一文章 upsert
│  ├─ 正文快照 materialize
│  ├─ 指标/评论入库
│  ├─ 失败诊断与 ingest error
│  └─ tombstone/去重/清理
├─ Product 层
│  ├─ 公众号账号库
│  ├─ 文章内容库
│  ├─ 选题池/标签/分类/状态
│  ├─ 热点分析
│  ├─ 草稿工坊
│  ├─ RSS/导出
│  └─ 通知/飞书协作
└─ Safety 层
   ├─ 密钥加密
   ├─ 限频和任务队列
   ├─ 代理健康
   ├─ 授权过期提醒
   └─ 风控状态提示
```

## 功能矩阵

| 功能 | 当前主系统状态 | 外部参考 | 吸收策略 | 优先级 | 验收标准 |
|---|---|---|---|---|---|
| Redfox 配置/搜索/账号/URL | 已有 | 当前代码 | 保留并降级为 provider 之一 | P0 | Redfox 成功时照常入库，失败时不阻断其他 provider |
| 单篇 URL 正文获取 | Redfox 依赖，脆弱 | wechat-download-api、wechat-reader、wechat-article-crawler | 重写 WeChat Article Page Provider | P0 | 输入 mp.weixin URL 后可保存标题、作者、正文、图片、快照；验证/删除页有明确错误 |
| HTML/纯文本/图片解析 | Redfox detail 归一化已有，微信 HTML 缺失 | wechat-download-api、we-mp-rss | 重写 parser，适配当前 snapshot | P0 | 支持 `#js_content`、`rich_media_content`、`page-content`、data-src 图片 |
| 公众号后台扫码登录 | 表和占位服务已有 | wechat-article-exporter、wechat-download-api、we-mp-rss | 二开真实登录 client | P0/P1 | 能获取二维码、轮询扫码、保存 cookie/token、展示过期时间 |
| 公众号搜索 | 当前需要 upstream_payload | wechat-article-exporter、wechat-download-api、we-mp-rss | 二开后台 searchbiz provider | P1 | 输入关键词返回 fakeid/biz/name/avatar，并入账号库 |
| 历史文章列表同步 | 当前需要 upstream_payload；Redfox 可补充 | wechat-article-exporter appmsgpublish、wechat-download-api articles | 二开后台列表 provider | P1 | 对指定公众号同步最近 N 篇，保存到文章库并记录 job |
| 文章正文批量补全 | 部分 refresh_from_redfox | we-mp-rss fetch_no_article、article refresh | 重写任务队列 | P1 | 对无正文文章批量低频补正文，失败记录原因 |
| 阅读量/点赞/分享指标 | Redfox 可提供，credential 表已有 | wechat-article-exporter comments/metadata | 二开敏感数据 provider | P2 | 凭证有效时采集指标；凭证缺失时提示准备项 |
| 评论/评论回复 | 表和服务已有，真实采集依赖不足 | wechat-article-exporter、wechat-download-api | 二开敏感数据 provider | P2 | 保存评论与回复，展示来源和采集时间 |
| 图片代理/下载 | 当前仅保存 URL | wechat-download-api、wechat-article-crawler | 先保存 URL，后续加代理/本地化 | P2 | 图片在内容详情可稳定预览；防盗链失败有 fallback |
| RSS 订阅 | 当前没有 | wechat-download-api、we-mp-rss | 按主系统重写 | P3 | 可订阅公众号，生成 RSS feed，定时更新 |
| 分类/标签/黑名单/收藏/已读 | 内容库已有部分状态/tombstone | wechat-download-api、we-mp-rss | 映射到内容库状态和标签 | P2/P3 | 支持分类筛选、黑名单跳过、收藏/已读状态 |
| 导出 HTML/JSON/MD/TXT/DOCX/Excel/PDF | 当前不是公众号主能力 | wechat-article-exporter、we-mp-rss | 分阶段接入导出服务 | P3 | 选中文章可导出至少 JSON/MD/HTML，复杂格式后置 |
| 代理池/限频/失败冷却 | 代理节点表已有 | wechat-download-api、wechat-article-exporter | 重写统一限频和代理健康 | P1 | 任务按 provider 限频，代理失败冷却，状态可见 |
| 浏览器兜底 | 当前无 | wechat-reader、we-mp-rss | 二阶段增强 | P2 | HTTP 失败时可提示用户浏览器验证并读取结果 |
| Webhook/企业微信/飞书通知 | 飞书协作已有，通知未系统化 | wechat-download-api、we-mp-rss | 结合当前飞书服务重写 | P3 | 授权过期/任务失败可通知 |
| 级联多节点 | 当前无 | we-mp-rss | 暂不进入近期范围 | Backlog | 有明确多机器采集需求后再估 |
| Access Key/API 开放 | 当前用户 API 基础已有 | we-mp-rss | 暂不优先 | Backlog | 外部系统需要接入时再做 |

## 模块策略分类

### 直接保留/增强

- 当前公众号数据模型的主体结构。
- 当前内容库、分析、草稿、飞书协作链路。
- 当前 Redfox 能力，但改成 provider 之一。
- 当前 tombstone/删除后跳过机制。

### 二开重写

- 公众号后台登录真实 client。
- SearchBiz / AppMsgPublish / Comment / Metadata provider。
- 单篇 URL HTML fetcher 和 parser。
- 任务队列、限频、代理健康。
- RSS 订阅和定时轮询。
- 导出能力。

### 暂不纳入近期

- 级联多节点采集。
- 外部 Access Key 开放平台。
- 完整 PDF/DOCX 高保真导出。
- 自动验证码处理或风控绕过。

## 数据模型影响

已有表可覆盖大部分需求，但建议新增/调整：

1. Provider 运行状态字段：
   - 可放在 job.params_json/raw_json 中先实现，不急着建表。
   - 后续可新增 `wechat_official_provider_runs` 记录 provider、status、error_kind、duration、raw diagnostics。
2. 订阅/RSS 表：
   - `wechat_official_subscriptions`：user_id、account_id、fake_id/biz、enabled、poll_interval、last_polled_at、category、raw_json。
   - `wechat_official_subscription_items` 可复用 articles，不必单独建文章表。
3. 分类/标签：
   - 第一阶段可复用 article.raw_json.analysis 和内容库标签。
   - 若需要强结构再新增 category/tag 表。
4. 导出任务：
   - 可复用任务中心或新增 export job，后置。

## API 影响

建议按 provider 和产品层分离：

- `/api/wechat-official/providers/status`
- `/api/wechat-official/sessions/*`：真实扫码登录。
- `/api/wechat-official/accounts/search`：后台 searchbiz。
- `/api/wechat-official/accounts/{id}/sync`：历史文章同步。
- `/api/wechat-official/articles/import-url`：不再挂在 redfox 下，做统一 URL 导入。
- `/api/wechat-official/articles/{id}/refresh-content`：多 provider 正文补全。
- `/api/wechat-official/articles/{id}/refresh-metrics`
- `/api/wechat-official/articles/{id}/refresh-comments`
- `/api/wechat-official/subscriptions/*`：RSS/订阅后置。
- 保留 `/redfox/*`，但前端应逐步从“Redfox 页面”转向“公众号采集中心”。

## 前端影响

当前前端公众号模块应从 Redfox 工具页升级为“公众号采集中心”：

1. 授权状态卡：显示公众号后台登录、Redfox、浏览器兜底状态。
2. 采集入口：
   - 搜公众号
   - 同步历史文章
   - 导入 URL
   - Redfox 爆文发现
3. 任务中心：显示 provider、进度、失败原因、可重试动作。
4. 内容库增强：正文完整度、指标完整度、评论完整度、来源标签。
5. 设置页：Redfox、代理、限频、RSS、通知。

## 验收优先级

- P0：URL/正文获取闭环和 provider 失败降级。
- P1：公众号后台登录、搜索、历史列表、批量正文补全。
- P2：指标、评论、图片稳定展示、分类/标签/黑名单、浏览器兜底。
- P3：RSS、导出、通知、管理增强。
- Backlog：级联、多节点、开放 API。

# 微信公众号 Redfox 爆文收集 MVP 设计

## 1. 背景

当前主系统基线是 `XHS_ALL_IN_ONE`。微信公众号平台已经完成第一轮接入：后端有独立的公众号采集模型、session/credential/proxy/crawl/content-library/draft/dry-run API，前端有微信公众号采集工作台，真实发布和群发保持阻断。

用户亲测后的关键问题是：

1. 产品壳仍然像“小红书系统”，公众号入口缺少运营中台语义。
2. 微信公众号页面是开发调试工作台，大量内部 ID、JSON、cookie/token 输入暴露在主流程里，运营人员无法直接完成“收集爆文 → 入库 → 二创”的目标。
3. RedFoxHub 已经提供公众号官方 API，适合作为公众号爆文自动收集的第一主路径。

本轮目标是做出最小可用闭环：

```text
运营中台 → 微信公众号爆文 → 配置 Redfox API Key → 收集 10万+ 文章 → 候选库 → 生成二创草稿 → dry-run blocked
```

## 2. 设计结论

本轮采用 **Redfox 数据源 + 现有公众号内容链路复用** 方案。

Redfox 只作为公众号文章发现和详情数据源，不作为微信官方发布 adapter。采集结果写入现有公众号内容模型：

- `WechatOfficialCrawlAccount`
- `WechatOfficialCrawlJob`
- `WechatOfficialArticle`
- `WechatOfficialArticleMetric`
- `WechatOfficialArticleSnapshot`
- `WechatOfficialDraftSource`

真实发布、群发、素材上传、公众号后台草稿同步继续 fail-closed。

## 3. 本轮范围

### 3.1 本轮做

1. 产品壳轻量中台化：
   - `Spider XHS` 改为 `运营中台`。
   - 左侧导航显式提供 `公众号爆文` 入口。

2. 新增 Redfox API Key 配置：
   - 服务端加密保存。
   - 前端只显示已配置/脱敏状态。
   - 不返回、不记录、不持久化明文 key。

3. 新增 Redfox 公众号采集能力：
   - 关键词收集：`searchArticle`。
   - 指定公众号收集：`queryWorkList`。
   - 文章 URL 补全：`queryArticleDetail`。

4. Redfox 入库：
   - 自动 upsert 公众号账号、文章、指标、正文快照。
   - `readCount >= 100000` 自动进入爆文候选。
   - 低粉证据默认 `unknown`。

5. 公众号页面产品化：
   - 默认展示 Redfox 配置、收集表单、候选库、草稿/dry-run 操作。
   - 原有 session、credential、proxy、上游 JSON、HTML/metrics/comments 调试能力折叠到“高级调试”。

6. 复用草稿链路：
   - Redfox 文章可创建 `AiDraft(platform="wechat_official")`。
   - dry-run 显示内容检查和 `publish/sendall blocked`。

7. 新增测试和验证：
   - Redfox key 加密与脱敏。
   - Redfox fake client 采集入库。
   - 内容库筛选和草稿创建。
   - 发布/群发安全门禁回归。
   - 前端 build 和本地 E2E。

### 3.2 本轮不做

- 不开放公众号真实发布。
- 不开放群发。
- 不开放素材上传。
- 不开放公众号官方草稿同步。
- 不实现验证码绕过、检测规避、批量号池或高频自动化。
- 不让前端直接调用 RedFoxHub。
- 不在自动测试中真实调用 Redfox 或消耗积分。
- 不承诺自动判定“低粉”，除非 Redfox 真实响应包含粉丝数或低粉标签。
- 不修改 `apis/`、`xhs_utils/`、`static/` 底层 XHS SDK/签名层。

## 4. Redfox 官方 API 使用边界

基础地址：

```text
https://redfox.hk
```

认证头：

```http
REDFOX_API_KEY: <api_key>
```

本轮使用三个公众号接口：

### 4.1 关键词文章搜索

```http
POST /story/api/gzhData/searchArticle
```

参数：

```json
{
  "keyword": "私域增长",
  "offset": 0,
  "sortType": "_4"
}
```

用途：按关键词收集热门公众号文章。

### 4.2 指定公众号作品列表

```http
POST /story/api/gzhData/queryWorkList
```

参数：

```json
{
  "account": "rmrbwx",
  "accountName": "人民日报",
  "offset": 0,
  "sortType": "_4",
  "publishTimeStart": "2026-04-01",
  "publishTimeEnd": "2026-06-17"
}
```

用途：按目标公众号收集热门文章。

### 4.3 文章 URL 详情

```http
POST /story/api/gzhData/queryArticleDetail
```

参数：

```json
{
  "url": "https://mp.weixin.qq.com/s/example"
}
```

用途：按公众号文章链接补全详情、正文和指标。

## 5. 数据映射

Redfox 响应先进入 `redfox_adapter.py` 标准化，再由 service 入库。service 不直接依赖散落的第三方字段名。

| Redfox 字段 | 主系统字段 |
|---|---|
| `workUuid` | `raw_json.redfox.work_uuid` |
| `title` | `WechatOfficialArticle.title` |
| `summary` | `WechatOfficialArticle.digest` |
| `workUrl` | `WechatOfficialArticle.article_url` / `content_url` |
| `publishTime` | `WechatOfficialArticle.publish_time_remote` |
| `author` | `WechatOfficialArticle.author_name` / account name |
| `coverUrl` | `WechatOfficialArticle.cover_url` |
| `content` | `WechatOfficialArticleSnapshot.text/html` |
| `readCount` | `WechatOfficialArticleMetric.read_count` |
| `likeCount` | `WechatOfficialArticleMetric.like_count` |
| `watchCount` | `WechatOfficialArticleMetric.wow_count` |
| `commentCount` | `WechatOfficialArticleMetric.comment_count` |
| `shareCount` | `WechatOfficialArticleMetric.share_count` |
| `collectCount` / `rewardCount` / `isOriginal` / `accountType` / `publishLocation` / `sourceUrl` / `originalAuthor` | `raw_json.redfox.*` |

## 6. 爆文和低粉规则

### 6.1 爆文候选

默认规则：

```text
read_count >= 100000 → is_candidate = true
```

入库时写入：

```json
{
  "analysis": {
    "recommendation_status": "candidate",
    "low_follower_evidence": "unknown"
  }
}
```

如果文章已有人工推荐状态，不覆盖人工字段。

### 6.2 低粉证据

Redfox 官方文档当前没有确认稳定返回粉丝数或低粉标签，所以默认：

```text
low_follower_evidence = "unknown"
```

只有在响应明确包含粉丝数或低粉标签时，才允许自动推断：

```text
followerCount < 10000 且 read_count >= 100000 → low_follower_evidence = "inferred"
```

否则必须由用户人工标记。

## 7. API 设计

### 7.1 配置

```http
GET /api/wechat-official/redfox/config
POST /api/wechat-official/redfox/config
POST /api/wechat-official/redfox/config/validate
```

响应不包含明文 key：

```json
{
  "configured": true,
  "config": {
    "id": 1,
    "name": "RedFoxHub",
    "base_url": "https://redfox.hk",
    "has_api_key": true,
    "masked_api_key": "****abcd",
    "status": "valid",
    "last_checked_at": "2026-06-17T10:00:00+08:00",
    "last_error": ""
  }
}
```

### 7.2 收集

```http
POST /api/wechat-official/redfox/collect/articles
POST /api/wechat-official/redfox/collect/account
POST /api/wechat-official/redfox/import-url
```

统一返回：

```json
{
  "summary": {
    "fetched": 20,
    "saved": 18,
    "deduped": 2,
    "viral_candidates": 8,
    "failed": 0,
    "api_calls": 1,
    "estimated_credit_cost": null
  },
  "job": {
    "id": 1,
    "source": "redfox",
    "status": "completed"
  },
  "items": []
}
```

## 8. 前端 UX

### 8.1 入口

- 左上品牌：`运营中台`。
- 左侧新增或突出：`公众号爆文`。
- 页面路径保持：`/platforms/wechat-official/dashboard`。

### 8.2 页面结构

1. 顶部说明：
   - `Redfox 公众号爆文收集`
   - 说明真实发布/群发 blocked。

2. Redfox API 配置卡：
   - 保存 API Key。
   - 校验连接。
   - 显示已配置/脱敏状态。

3. 爆文收集 tabs：
   - 按关键词收集。
   - 按公众号收集。
   - 文章 URL 补全。
   - 高级调试。

4. 候选库：
   - 默认展示 10万+。
   - 字段：标题、公众号、阅读数、点赞、在看、评论、分享、发布时间、推荐状态、低粉证据。
   - 操作：生成草稿、dry-run、标记推荐、标记低粉证据。

### 8.3 高级调试

以下既有能力保留但默认折叠：

- 后台 session 模拟。
- credential 导入。
- proxy 测试。
- searchbiz / appmsgpublish JSON。
- HTML snapshot。
- cgi_data metrics。
- comments payload。

## 9. 安全规则

- Redfox API Key 必须用 `encrypt_text` 加密。
- API 响应不得包含明文 key 或 `encrypted_api_key`。
- 日志、job params、raw_json、IngestError 不得包含明文 key。
- 前端不得保存 key 到 localStorage/sessionStorage。
- 自动测试不得真实调用 Redfox。
- 默认采集页数为 1，最大 3；前端显示预计 API 调用次数。
- `publish.real_publish` 保持 blocked。
- `sendall` 保持 blocked。
- 素材上传、官方草稿同步保持 blocked。

## 10. 验收标准

1. 打开系统后左上角显示 `运营中台`。
2. 进入 `公众号爆文` 后，默认看到 Redfox 配置和爆文收集表单，而不是 JSON 调试台。
3. 保存 Redfox API Key 后，前端只显示已配置/脱敏状态。
4. 关键词收集能把 fake/mock Redfox 的 `readCount=120000` 文章写入内容库。
5. `readCount=50000` 文章可入库但不作为爆文候选。
6. 候选库默认显示 10万+ 文章。
7. 低粉证据默认显示 `未知`。
8. 候选文章能生成公众号草稿。
9. dry-run 返回 `publish_blocked=true`、`sendall_blocked=true`。
10. 通用 send-to-publish 对公众号草稿继续返回阻断错误。
11. 后端相关 pytest 通过。
12. 前端 build 通过。
13. 本地 E2E 通过 mock Redfox 流程验证完整闭环。

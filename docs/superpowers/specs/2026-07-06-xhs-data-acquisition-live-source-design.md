# 小红书数据获取低风险数据源接入设计

## 1. 背景

当前系统已经具备小红书账号直连能力，包括 PC 搜索、URL 直达、用户笔记抓取、评论抓取、Creator 发布等。但真实小红书账号直接用于采集笔记和评论，已经出现较高封号风险。

系统内也已经存在灰豚相关能力：

- 灰豚账号扫码登录与 Cookie 导入。
- 灰豚热词 live connector。
- `extData` AES 解密能力。
- 灰豚热词候选导入关键词组。

这次设计目标不是从零接入新供应商，而是把已经跑通的灰豚 live connector 模式扩展为“小红书数据获取”的低风险主路径。

对外产品不展示“灰豚”或供应商名称。普通用户看到的是系统自己的数据获取能力；内部仍保留 `source=huitun` 以便排查、审计和后续维护。

## 2. 目标

### 2.1 产品目标

- 将“小红书数据获取”升级为统一入口。
- 默认推荐低风险数据获取能力。
- 保留小红书账号直连采集能力，但标记为高风险备用路径。
- 新获取的数据先进入待确认列表，用户确认后再入内容库。
- 入库后由现有内容库和分析中心消费，不自动生成报告。

### 2.2 技术目标

- 沿用现有灰豚账号、Cookie、`extData` 解密模式。
- 扩展 live connector 到笔记搜索、笔记榜单、笔记详情和关键词分析。
- 复用现有 `notes`、`note_assets`、`note_comments`、`keyword_groups`、`tasks`。
- 新增必要的数据获取 run、候选、快照表。
- 接入现有任务中心，所有数据获取任务异步执行。
- 管理员可查看内部来源、endpoint、解密状态、raw 和错误详情；普通用户不可见。

## 3. 非目标

- 不删除小红书账号直连能力。
- 不删除或重写现有灰豚热词 live connector。
- 不推翻现有 `extData` 解密模式。
- 不做多供应商抽象。
- 不自动切换 Excel/表格导入兜底。
- 不高频批量请求。
- 不绕过会员权限。
- 不自动访问小红书原文。
- 不自动下载封面或素材到本地。
- 不自动补全笔记详情。
- 不自动生成分析报告。
- 不把第三方分析结论伪装成原始评论或官方数据。

## 4. 已确认约束

### 4.1 对外隐藏供应商

普通用户界面不展示：

- 灰豚
- huitun
- 第三方数据源
- 供应商名
- extData
- connector
- cookie
- 内部接口

普通用户看到的能力名称为：

- 获取热词趋势
- 获取笔记数据
- 获取榜单笔记
- 补全笔记详情
- 关键词分析
- 导入数据文件

### 4.2 管理员可见内部信息

管理员或调试模式可见：

- `source=huitun`
- `source_mode=live_account`
- endpoint key
- 请求参数摘要
- 响应状态
- `extData` 是否解密成功
- 解析阶段
- raw snapshot id
- 错误码与错误摘要

### 4.3 现有能力默认保留

系统已经实现且正常工作的能力默认保留并沿用：

- 小红书账号直连采集。
- 灰豚热词 live connector。
- 内容库封面字段。
- `NoteAsset` 素材模型。
- 任务中心。
- 内容库。
- 分析中心。
- 排除模型和已有排除思路。

## 5. 信息架构

页面侧边栏只保留一个入口：

```text
系统数据源
```

该页面由现有“小红书数据抓取”升级而来，不删除旧功能。页面一级只分为：

- `系统发现`：默认入口，承载系统数据账号、关键词组获取、候选确认和入库。
- `小红书实时`：保留原“笔记发现”的笔记卡片、URL 直查和账号直连能力，明确列出限流、验证码、登录失效和封号风险。

关键词组属于系统发现的查询配置，通过页面内入口管理，不再单独占用侧边栏。旧 `/platforms/xhs/discovery` 与 `/platforms/xhs/keywords` 路由继续兼容，避免既有跳转失效。

第一屏任务卡片：

```text
获取热词趋势
获取笔记数据
获取榜单笔记
补全笔记详情
关键词分析
导入数据文件
```

页面下方展示：

```text
最近任务
待确认候选
小红书账号直连（高风险，折叠）
```

高风险区域文案：

```text
该方式依赖小红书账号登录态，可能触发账号风控。建议仅在明确需要时低频使用。
```

## 6. 用户流程

### 6.1 获取数据

```text
创建数据获取任务
→ 后台异步执行
→ 任务中心展示状态
→ 完成后进入待确认候选
→ 用户筛选、勾选或排除
→ 批量入库
→ 内容库查看
→ 手动补全详情
→ 手动进入分析中心生成报告
```

### 6.2 候选确认

新获取的数据不直接进入内容库。候选列表默认保留 30 天。

候选状态：

- `pending`：待确认。
- `imported`：已入库，长期留痕。
- `excluded`：已排除，长期留痕。
- `expired`：待确认候选过期。

排除支持一键排除，可选原因。

候选入库时，如果内容库已存在同一笔记，复用已有 `Note`，新增来源和指标快照。

### 6.3 详情补全

入库后默认不自动补全详情。

用户在内容库勾选笔记后点击“补全详情”，系统显示确认弹窗：

```text
将补全 25 条笔记详情。
预计请求 25 条。
可能获取：基础数据、阅读画像、评论分析、提及品牌/话题/商品、相似笔记。
是否继续？
```

用户确认后创建后台任务。

### 6.4 分析中心联动

数据获取完成后不自动生成分析报告。

入库完成后只提示：

```text
已入库 32 条笔记，可前往分析中心生成洞察。
```

分析中心只消费已入库内容，不消费 pending 候选。

## 7. 数据模型

### 7.1 复用现有表

继续复用：

- `notes`
- `note_assets`
- `note_comments`
- `keyword_groups`
- `tasks`
- `note_exclusions`

不新建独立的灰豚笔记表。

### 7.2 新增 `data_acquisition_runs`

用途：保存每次数据获取任务的业务参数和运行上下文，并关联全局任务。

核心字段：

```text
id
task_id
user_id
platform
acquisition_type
source
source_mode
status
requested_limit
effective_limit
params_json
admin_debug_json
error_code
error_message
rerun_of_run_id
cancellation_requested
created_at
started_at
finished_at
expires_at
```

`acquisition_type`：

- `trend_keywords`
- `note_search`
- `note_rank`
- `note_detail_enrichment`
- `keyword_analysis`
- `file_import`

`source` 第一版内部固定为 `huitun`。

### 7.3 新增 `data_acquisition_candidates`

用途：保存待确认候选数据。

核心字段：

```text
id
run_id
user_id
platform
candidate_type
source
external_id
platform_note_id
original_url
title
content_excerpt
author_name
cover_url
asset_urls_json
publish_time
update_time
rank_index
category
tags_json
metrics_json
raw_json
status
imported_note_id
decision_reason_code
decision_reason_text
created_at
updated_at
expires_at
```

`candidate_type`：

- `keyword`
- `note`
- `note_detail`
- `keyword_analysis`

### 7.4 新增 `note_source_snapshots`

用途：保存同一篇笔记在不同任务、不同时间的指标快照。

核心字段：

```text
id
note_id
run_id
candidate_id
user_id
platform
source
snapshot_type
source_url
source_record_id
fetched_at
rank_index
keyword
rank_type
category
tags_json
metrics_json
analysis_json
raw_json
created_at
```

`snapshot_type`：

- `search_result`
- `rank_result`
- `detail`
- `monitor`

`metrics_json` 示例：

```json
{
  "like_count": 1000,
  "collect_count": 500,
  "comment_count": 80,
  "share_count": 20,
  "interaction_count": 1600,
  "estimated_read_count": 10000
}
```

`analysis_json` 示例：

```json
{
  "reading_profile": {},
  "comment_analysis": {},
  "mentioned_brands": [],
  "mentioned_topics": [],
  "mentioned_products": [],
  "similar_notes": [],
  "promotion_effect": {}
}
```

如果只拿到分析结论，不拿到评论原文，只写 `analysis_json`，不写 `note_comments`。

### 7.5 新增 `keyword_source_snapshots`

用途：保存关键词分析结果，不污染 `keyword_groups`。

核心字段：

```text
id
run_id
user_id
platform
source
keyword
period
note_count
estimated_read_count
commercial_note_count
interaction_count
top_category
top_creator_attribute
related_hotwords_json
related_notes_json
related_creators_json
related_brands_json
related_lives_json
raw_json
created_at
```

## 8. 封面和素材

候选和入库笔记都保存封面 URL。

系统已具备：

- `SavedNote.cover_url`
- `SavedNote.asset_urls`
- `NoteAsset`

灰豚榜单页面已验证存在小红书 CDN 封面 URL，例如 `sns-img-hw.xhscdn.com`。

入库规则：

- 第一张图片写入 `cover_url`。
- 图片 URL 写入 `note_assets`，`asset_type=image`。
- 多图写多条 `note_assets`。
- 不自动下载本地，`local_path=""`。
- 视频笔记可保存封面和视频标识，但第一版不自动下载视频。

## 9. 去重与入库

候选入库时按以下优先级识别同一笔记：

1. 小红书官方 note id。
2. 原文 URL 解析出的 note id。
3. 灰豚内部 note key + 原文链接。
4. 标题 + 作者 + 发布时间，作为低置信度匹配。

如果已存在：

```text
复用 Note
新增 note_source_snapshots
更新必要 raw_json
候选状态改 imported
```

如果不存在：

```text
创建 Note
创建 NoteAsset
创建 note_source_snapshots
候选状态改 imported
```

不允许重复创建同一篇笔记。

## 10. API 设计

对外 API 不暴露供应商名。

```text
POST   /api/xhs/data-acquisition/runs
GET    /api/xhs/data-acquisition/runs
GET    /api/xhs/data-acquisition/runs/{run_id}
POST   /api/xhs/data-acquisition/runs/{run_id}/rerun
POST   /api/xhs/data-acquisition/runs/{run_id}/cancel

GET    /api/xhs/data-acquisition/candidates
POST   /api/xhs/data-acquisition/candidates/import
POST   /api/xhs/data-acquisition/candidates/exclude
POST   /api/xhs/data-acquisition/candidates/restore

POST   /api/xhs/data-acquisition/notes/enrich-details
```

### 10.1 创建任务

统一请求体：

```json
{
  "acquisition_type": "note_search",
  "params": {
    "keyword": "浴缸",
    "limit": 100,
    "sort": "interaction",
    "note_type": "all"
  }
}
```

不同类型参数：

#### 热词趋势

```json
{
  "acquisition_type": "trend_keywords",
  "params": {
    "seed_keywords": ["浴缸", "家居"],
    "limit_per_seed": 20
  }
}
```

#### 笔记搜索

```json
{
  "acquisition_type": "note_search",
  "params": {
    "keyword": "浴缸",
    "limit": 100,
    "sort": "interaction",
    "note_type": "all"
  }
}
```

#### 榜单笔记

```json
{
  "acquisition_type": "note_rank",
  "params": {
    "rank_type": "hot_notes",
    "category": "家居家装",
    "time_range": "7d",
    "limit": 100
  }
}
```

#### 详情补全

```json
{
  "acquisition_type": "note_detail_enrichment",
  "params": {
    "note_ids": [1, 2, 3]
  }
}
```

#### 关键词分析

```json
{
  "acquisition_type": "keyword_analysis",
  "params": {
    "keywords": ["浴缸", "宠物浴缸"],
    "period": "30d"
  }
}
```

## 11. 任务执行

所有数据获取任务异步执行。

```text
创建 tasks 记录
创建 data_acquisition_runs 记录
返回 run_id / task_id
后台执行器消费任务
前端轮询 run/task 状态
```

任务状态：

- `pending`
- `running`
- `completed`
- `partial_failed`
- `failed`
- `cancelled`
- `expired`

### 11.1 执行器分发

```text
trend_keywords → 现有 huitun_live_keyword_source.fetch_huitun_hotwords
note_search → 新增 huitun_live_note_source.search_notes
note_rank → 新增 huitun_live_note_source.fetch_rank_notes
note_detail_enrichment → 新增 huitun_live_note_detail_source.fetch_note_detail
keyword_analysis → 新增 huitun_live_keyword_analysis_source.fetch_keyword_analysis
file_import → 后续/手动入口
```

### 11.2 失败处理

失败就失败，不自动兜底。

记录：

- stage
- error_code
- error_message
- admin_debug_json
- raw_snapshot

普通用户看到：

```text
本次数据获取失败，任务已停止。
```

管理员看到具体内部错误。

### 11.3 重跑

`POST /runs/{run_id}/rerun`

规则：

- 复制原 run 参数。
- 创建新 task / run。
- 新 run 记录 `rerun_of_run_id`。
- 原失败 run 不覆盖。

### 11.4 取消

`POST /runs/{run_id}/cancel`

规则：

- `pending` 直接取消。
- `running` 标记 `cancellation_requested`。
- 当前单个请求完成后停止下一批。
- 已获取结果保留。
- 用户可查看已有候选或重跑。

## 12. 系统限额

第一版加保守默认上限，管理员可调整。

| 任务 | 默认上限 |
|---|---:|
| 热词趋势 | 20 条/种子词 |
| 笔记搜索 | 100 条/关键词 |
| 榜单笔记 | 100 条/任务 |
| 详情补全 | 50 条/批次 |
| 关键词分析 | 10 个关键词/任务 |

内部保存：

```text
requested_limit
effective_limit
admin_limit
```

## 13. 接口验证闸门

每个新增 live connector 开发前必须先做只读验证。

验证对象：

1. 笔记搜索。
2. 笔记榜单。
3. 笔记详情。
4. 关键词分析。

验证项：

| 验证项 | 标准 |
|---|---|
| 登录态 | 能使用系统保存的账号 cookie |
| endpoint | 找到稳定请求路径 |
| 返回格式 | 返回 JSON，不是页面 HTML |
| extData | 如果返回字符串，现有解密函数可解 |
| 字段 | 核心字段能映射到候选/快照 |
| 封面 | 能拿到封面 URL |
| 原文 | 能拿到原文链接或 note id |
| 权限 | 能识别权限不足/数量限制 |
| 失败 | 能拿到明确错误码或错误消息 |
| 频率 | 低频请求无异常 |
| 样本 | 至少 2 个不同关键词/榜单/笔记样本 |

没通过验证，不进入该 connector 实现。

验证记录写入本 spec 附录或单独验证文档。

阶段 0 当前验证记录：`docs/superpowers/specs/2026-07-06-xhs-data-acquisition-live-source-verification.md`。

当前闸门结论：`note.searchV2` 已验证可用，可进入笔记搜索链路开发；笔记榜单、笔记详情、关键词分析仍未 ready，不得混入第一阶段正式开发。

## 14. 测试策略

### 14.1 后端单元测试

覆盖：

- `extData` 解密兼容。
- 响应结构解析。
- 字段映射。
- 候选去重。
- 候选入库。
- 重复 Note 复用。
- 快照创建。
- 排除候选。
- 任务重跑。
- 任务取消标记。
- 普通用户不返回 debug。
- 管理员返回 debug。

### 14.2 后端集成测试

覆盖：

- 创建数据获取任务。
- 任务状态流转。
- 候选列表。
- 批量入库。
- 失败任务记录。
- 重跑生成新 run。
- 详情补全任务创建。

### 14.3 前端验证

覆盖：

- 数据获取页面渲染任务卡片。
- 创建任务表单参数正确。
- 候选列表展示封面和指标。
- 批量入库交互。
- 排除交互。
- 高风险账号直连区域折叠。
- 管理员调试信息只在管理员模式显示。

### 14.4 手工验证

至少跑通：

```text
获取榜单笔记
→ 候选列表
→ 选择 3 条
→ 入库
→ 内容库看到封面
→ 补全详情
→ 快照历史可见
```

## 15. 开发分阶段验收

### 阶段 0：接口验证

交付物：

- 验证记录。
- 每类 connector 是否 ready 的结论。

### 阶段 1：任务和候选骨架

验收：

- 能创建异步任务。
- 能写入候选。
- 能展示待确认列表。
- 能排除/入库。
- 能接任务中心。

### 阶段 2：笔记搜索/榜单

验收：

- 能获取候选笔记。
- 能显示封面。
- 能保存原文链接。
- 能批量入库。
- 重复笔记复用 Note。
- 快照创建成功。

### 阶段 3：详情补全

验收：

- 用户勾选后补全详情。
- 不自动补全。
- 成功、失败、部分成功状态准确。
- 快照记录详情字段。

### 阶段 4：关键词分析

验收：

- 能获取关键词分析。
- 能写入关键词分析快照。
- 能辅助关键词组/分析中心。

## 16. 开发后验证命令

后端：

```bash
python -m pytest tests/backend
```

前端：

```bash
cd frontend
npm run build
```

如果涉及 Alembic：

```bash
alembic heads
```

必须只有一个 head。

## 17. 待接口验证后补充

以下内容必须在阶段 0 验证后补充：

- 笔记搜索 endpoint key。
- 笔记榜单 endpoint key。
- 笔记详情 endpoint key。
- 关键词分析 endpoint key。
- 每个 endpoint 的字段映射表。
- 每个 endpoint 的权限失败样例。
- 每个 endpoint 是否沿用现有 `decrypt_huitun_ext_data`。

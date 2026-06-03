# XHS Legacy Keywords + Detail Recovery Integration Design

## Goal

把 legacy TypeScript 系统里已经验证过的两类能力，按当前 `XHS_ALL_IN_ONE` 主系统架构接入到 Web 平台：

1. **灰豚热词获取**：让用户不再手工维护关键词，而是能从灰豚热词中筛选并导入关键词组。
2. **XHS 详情恢复与不可见链接诊断**：减少“只采到链接、打开看不到内容、仍被当成成功入库”的情况。
3. **基础诊断记录**：让采集失败能解释原因，并给用户下一步动作，而不是只显示“失败”。

设计目标不是复制 legacy CLI，而是吸收其中对用户有价值的能力，并落在当前 FastAPI / React / SQLAlchemy 架构里。

## User Impact

当前系统的问题不是“缺少更多按钮”，而是两个关键链路不闭环：

- 关键词组页面只能手工输入关键词，用户需要自己去外部平台找热词，再复制回来。
- 数据抓取页面能返回链接，但当详情不可见、短链接缺少 `xsec_token`、详情为空或触发访问频繁时，系统缺少质量门禁和解释，容易把低质量数据污染到内容库。

接入后，用户体验应变成：

- 在关键词组里输入一个种子词，系统展示灰豚热词候选，包括热度、笔记数、互动数、分类和排名。
- 用户勾选热词后，一键合并到已有关键词组或创建新关键词组。
- 数据抓取时，系统区分“成功抓到详情”“只抓到搜索卡片”“短链接缺 token”“访问频繁已停止”“详情为空不入库”。
- 失败项给出可执行提示：例如“请使用搜索结果链接或带 xsec_token 的 explore 链接重新抓取”，而不是让用户自己判断链接为什么打不开。

## Decision

第一批 legacy 能力接入采用 **port core logic, not legacy runtime**：

1. 不把 `legacy/xhs-ops-collector` 作为主系统运行入口。
2. 不让根目录依赖 legacy CLI 命令完成生产流程。
3. 将 legacy 中稳定、可测试的解析与判定逻辑移植到 Python 服务层。
4. 灰豚第一批默认只做表格/JSON 解析、候选保存和导入关键词组；浏览器 connector 只作为后续本地开关能力，不作为默认后端采集流程。
5. 所有结果写入当前主系统表、API 和页面，不写回 legacy SQLite。

为什么这样做：

- 主系统已经迁移为 Web-first 平台，继续调用 legacy CLI 会让两个基线同时存在，后续维护成本更高。
- legacy 中最有价值的是解析规则、质量门禁、诊断模型和失败语义，不是旧 CLI 的进程形态。
- 用户真正需要的是在 Web 页面完成“找词 → 抓取 → 入库 → 诊断”，不是再回到命令行。

## In Scope

第一批只做三件事：

1. 灰豚热词候选解析、保存、导入关键词组。
2. XHS 详情恢复、详情质量门禁、不可见链接诊断。
3. 采集诊断记录和前端可见提示。

## Out of Scope

第一批不做：

- 飞书同步。
- AI 生成、改写或模型配置改造。
- Creator 发布、Provider/API 发布、自动发布策略改造。
- 大规模媒体归档和 manifest 完整性系统。
- legacy SQLite 数据迁移。
- 生产部署方案。
- 默认接入灰豚浏览器自动化采集。
- 修改 `apis/`、`xhs_utils/`、`static/` 底层签名层。
- 风控绕过、验证码绕过、批量号池、高频重试或检测规避。

## Current Main System State

### Keyword groups

当前关键词组模型只保存用户、平台、组名和关键词 JSON 列表：

```text
backend/app/models/keyword_group.py
```

当前 API 支持手工 CRUD 和基于已保存笔记的趋势统计：

```text
backend/app/api/keyword_groups.py
```

局限：

- 每个关键词没有来源、热度、笔记数、互动数和分类来源。
- 无法记录“这个关键词来自灰豚哪个种子词、哪次导入、排名是多少”。
- 页面只能输入逗号或换行分隔的关键词。

### XHS PC detail and crawl

当前 PC API 已有搜索、详情、评论入口：

```text
backend/app/api/platforms/xhs/pc.py
```

当前抓取 API 会在搜索模式里逐条调用详情，并可保存到内容库：

```text
backend/app/api/platforms/xhs/crawl.py
```

局限：

- `_note_url` 在缺少 `xsec_token` 时会退化成短 explore URL，这类 URL 很可能不能稳定打开详情。
- 详情失败时只返回错误文本，缺少结构化 failure kind。
- 详情内容为空但有链接时，缺少质量门禁，可能被保存成“看起来成功、实际不可用”的笔记。
- `/xhs/crawl/search-notes` 和 `/xhs/crawl/user-notes` 当前会直接保存搜索卡片数据；第一批需要明确质量语义，避免把“卡片数据”误当“详情数据”。
- 访问频繁、短链接缺 token、详情接口结构变化、评论失败等场景没有统一诊断记录。

## Legacy Capabilities to Port

### Huitun hotword parsing

Legacy source:

```text
legacy/xhs-ops-collector/src/browser/hotword-search.ts
legacy/xhs-ops-collector/src/types.ts
legacy/xhs-ops-collector/src/utils/number.ts
```

可移植能力：

- 热词行解析：`word`、`hotValueText`、`hotValueNumber`、`noteCount`、`interactionText`、`interactionNumber`、`categories`、`rankIndex`。
- 精确匹配优先：当灰豚结果中包含与种子词完全相同的词时优先展示。
- 数字解析：支持中文热度文本、万级单位、空值。

第一批数据来源约束：

- 支持手工粘贴灰豚表格、上传/提交灰豚 JSON，或接收本地 connector 的标准化输出。
- `source_mode` 第一批只允许 `manual_table`、`manual_json`、`local_connector_output`。
- `local_connector_output` 表示“用户在本地工具中完成灰豚采集后，把结果交给主系统解析”，不是后端默认代管灰豚登录态。
- 不保存灰豚 Cookie、token、账号密码或浏览器会话。

不直接复制的能力：

- 不把 Playwright 采集流程作为主系统默认运行入口。
- 不要求用户回到 CLI 执行灰豚任务。
- 不在第一批让后端持久化灰豚登录态或自动维护灰豚会话。

### XHS detail recovery and diagnostics

Legacy source:

```text
legacy/xhs-ops-collector/src/browser/xhs-note-detail.ts
legacy/xhs-ops-collector/src/xhs-search-collector.ts
legacy/xhs-ops-collector/src/xhs-types.ts
```

可移植能力：

- 短 explore URL 拒绝：没有 `xsec_token` 的 `https://www.xiaohongshu.com/explore/<id>` 不应盲目当作可恢复详情链接。
- 访问频繁识别：`error_code=300013`、`访问频繁`、`请稍后再试` 应被标记为 rate limit，并停止本轮详情抓取。
- 详情有效性判断：有正文、原始详情文本、媒体源、标签或可识别详情结构，才算有效详情。
- 详情失败结构化记录：记录 feed id、source URL、failure kind、message、是否 rate limited。
- 诊断快照思想：保留足够信息用于解释失败，但不保存敏感 Cookie。

第一批不移植完整 DOM 初始状态解析。原因：当前主系统默认走原生 PC API 适配层，不是 Playwright DOM 采集链路。DOM/initial-state recovery 可以作为第二批 browser fallback，但第一批先把 URL 质量、API 详情、空详情门禁和诊断做扎实。

## Target Architecture

### Backend service boundaries

新增服务层，而不是直接把逻辑塞进路由：

```text
backend/app/services/huitun_keyword_source.py
backend/app/services/xhs_detail_recovery.py
backend/app/services/crawl_diagnostics.py
```

职责：

- `huitun_keyword_source.py`
  - 灰豚热词结果解析。
  - 热词候选标准化。
  - 候选词去重、排序、合并建议。
  - 第一批支持手工粘贴表格、JSON、或本地 connector 已经输出的标准化结果。

- `xhs_detail_recovery.py`
  - URL 识别和短 explore URL 拒绝。
  - 从搜索结果 raw payload 中提取 `note_id`、`xsec_token`、`xsec_source` 并构造稳定详情 URL。
  - 调用现有 `XhsPcApiAdapter.get_note_info`。
  - 判断详情是否有效。
  - 将失败归类为可操作的 failure kind。

- `crawl_diagnostics.py`
  - 写入采集诊断记录。
  - 生成前端可展示的用户提示。
  - 汇总任务级质量报告。
  - 对 `raw_json` 做白名单摘要和敏感字段脱敏。

### API shape

#### Huitun keyword discovery

新增 API：

```text
POST /api/keyword-groups/huitun/discovery-runs
GET  /api/keyword-groups/huitun/discovery-runs/{run_id}
POST /api/keyword-groups/{group_id}/import-keyword-candidates
POST /api/keyword-groups/import-keyword-candidates
```

`POST /api/keyword-groups/huitun/discovery-runs` request:

```json
{
  "seed_keywords": ["露营", "夏季穿搭"],
  "limit_per_seed": 20,
  "source_mode": "manual_table",
  "table_rows": [
    ["露营装备", "12.3万", "3400", "8.6万", "户外 42.5%"]
  ]
}
```

可选 `source_mode`：

- `manual_table`：用户粘贴灰豚表格行。
- `manual_json`：用户提交灰豚 JSON 或本地导出 JSON。
- `local_connector_output`：本地 connector 已完成采集，主系统只接收标准化输出。

response:

```json
{
  "run_id": 12,
  "status": "completed",
  "items": [
    {
      "id": 101,
      "source_keyword": "露营",
      "keyword": "露营装备",
      "hot_value_text": "12.3万",
      "hot_value_number": 123000,
      "note_count": 3400,
      "interaction_text": "8.6万",
      "interaction_number": 86000,
      "categories": [{ "label": "户外", "rate": "42.5" }],
      "rank_index": 1
    }
  ]
}
```

`POST /api/keyword-groups/{group_id}/import-keyword-candidates` 用于合并到已有组。

```json
{
  "candidate_ids": [101, 102, 103],
  "merge_mode": "append_dedupe"
}
```

`POST /api/keyword-groups/import-keyword-candidates` 用于创建新组或统一表达目标：

```json
{
  "candidate_ids": [101, 102, 103],
  "merge_mode": "append_dedupe",
  "target": {
    "mode": "create",
    "name": "露营热词"
  }
}
```

行为：

- 导入时只把候选词文本合并进 `KeywordGroup.keywords`。
- 候选词的来源、热度和分类保存在候选表，不塞进 `KeywordGroup.keywords` JSON 列表。
- 这样可以保持当前关键词组 API 和页面已有逻辑稳定，同时保留来源追踪。

#### XHS detail recovery and diagnostics

不新增新的详情入口作为第一选择，而是增强现有入口：

```text
POST /api/xhs/pc/notes/detail
POST /api/xhs/crawl/data
POST /api/xhs/crawl/note-urls
POST /api/xhs/crawl/search-notes
POST /api/xhs/crawl/user-notes
```

新增诊断查询：

```text
GET /api/xhs/crawl/diagnostics?task_id=123
```

持久化规则：

- `/xhs/crawl/data`、`/xhs/crawl/note-urls`、`/xhs/crawl/search-notes`、`/xhs/crawl/user-notes` 有任务上下文，应写入持久化 diagnostics。
- `/xhs/pc/notes/detail` 是单次详情入口，第一批只返回 inline diagnostic；如后续要落库，`crawl_diagnostics.task_id` 必须允许为空。

抓取 item response 增加字段：

```json
{
  "source": "https://www.xiaohongshu.com/explore/abc",
  "status": "failed",
  "quality_status": "invalid_source_url",
  "recoverable": false,
  "diagnostic_kind": "missing_xsec_token_short_explore",
  "save_diagnostic_kind": null,
  "user_message": "这个链接缺少 xsec_token，无法稳定获取详情。请从搜索结果重新采集，或提供带 xsec_token 的完整链接。",
  "saved": false,
  "note": null,
  "comments": [],
  "comment_count": 0
}
```

成功但质量不足时：

```json
{
  "status": "partial",
  "quality_status": "search_card_only",
  "recoverable": true,
  "diagnostic_kind": "empty_detail_payload",
  "save_diagnostic_kind": "save_skipped_low_quality",
  "user_message": "已拿到搜索卡片，但详情为空，本条不会自动入库。可稍后低频重试。",
  "saved": false
}
```

## Data Model

### Keyword discovery tables

新增 `keyword_discovery_runs`：

- `id`
- `user_id`
- `platform`
- `source`：第一批固定为 `huitun`
- `seed_keywords` JSON
- `limit_per_seed`
- `source_mode`
- `status`：`running` / `completed` / `partial_failed` / `failed`
- `error_message`
- `created_at`
- `finished_at`

新增 `keyword_discovery_items`：

- `id`
- `run_id`
- `user_id`
- `platform`
- `source`
- `source_keyword`
- `keyword`
- `hot_value_text`
- `hot_value_number`
- `note_count`
- `interaction_text`
- `interaction_number`
- `categories` JSON
- `rank_index`
- `selected`
- `imported_group_id`
- `raw_json`
- `created_at`

不改 `KeywordGroup.keywords` 的结构。原因：

- 当前前端和 API 已经把它当作 `list[str]` 使用。
- 改成复杂对象会牵连趋势统计、自动运营配置和已有测试。
- 来源数据是候选词历史，不是用户最终运营关键词组的核心结构。

### Crawl diagnostics table

新增 `crawl_diagnostics`：

- `id`
- `user_id`
- `task_id`：nullable；批量抓取有值，单次详情诊断可为空。
- `platform_account_id`
- `platform`
- `source`：原始 URL、搜索页、关键词页等
- `note_id`
- `note_url`
- `stage`：`search` / `detail` / `comments` / `save`
- `kind`：结构化失败类型
- `severity`：`info` / `warning` / `error` / `blocked`
- `recoverable`
- `message`：技术 message
- `user_message`：前端展示 message
- `raw_json`：脱敏后的原始响应摘要
- `created_at`

第一批不存完整 HTML。若后续需要 DOM/browser fallback，再设计快照文件存储与脱敏策略。

### Alembic and model registration

实现时必须同步：

- 新模型加入 `backend/app/models/__init__.py`。
- 新迁移放入 `backend/alembic/versions/`。
- JSON 字段沿用当前 SQLAlchemy `JSON` 写法，保持 SQLite 兼容。
- 新增 datetime 字段不加入旧的 SQLite datetime normalization 迁移；该兼容迁移只处理历史表。新表从创建开始使用当前时间约定。

## Diagnostic Redaction Rules

诊断记录必须使用白名单摘要，不保存完整请求上下文。

禁止写入 `raw_json`：

- Cookie。
- Authorization header。
- access token / refresh token。
- 明文 `xsec_token` 完整值。
- 请求头。
- 账号 Cookie 字符串。
- API key。
- 完整 HTML。

允许写入的摘要字段：

- `error_code`
- `message`
- `note_id`
- `source_url_kind`
- `has_xsec_token`
- `masked_xsec_token`：如确需展示，只保留前后 4 位，中间替换为 `***`。
- `payload_keys`
- `has_data`
- `item_count`
- `has_content`
- `has_media`
- `has_tags`
- `has_interaction`

## Failure Kinds

第一批至少定义这些 `diagnostic_kind`：

| kind | stage | 场景 | 用户提示 |
|---|---|---|---|
| `missing_xsec_token_short_explore` | `detail` | 短 explore URL 没有 `xsec_token` | 使用搜索结果链接或带 token 的完整链接重新抓取 |
| `xhs_rate_limited` | `detail` | 命中 `error_code=300013` / 访问频繁 | 已停止本轮详情抓取，稍后低频重试 |
| `empty_detail_payload` | `detail` | API 成功但详情正文、媒体、标签都为空 | 本条不入库，稍后重试或换来源链接 |
| `detail_api_failed` | `detail` | `get_note_info` 返回失败 | 展示接口 message，记录可恢复状态 |
| `comment_api_failed` | `comments` | 评论获取失败 | 笔记可入库，但评论标记失败 |
| `invalid_note_identity` | `detail` | 无法识别 note id / feed id | 检查链接格式 |
| `save_skipped_low_quality` | `save` | 只有链接或搜索卡片，达不到入库质量 | 未污染内容库，可重新抓取详情 |

`save_skipped_low_quality` 是保存阶段结果，不是详情失败根因。item 上应同时保留根因，例如：

- `diagnostic_kind = empty_detail_payload`
- `save_diagnostic_kind = save_skipped_low_quality`

## Detail Quality Gate

详情入库前必须经过质量门禁。

### Valid detail

有效详情采用强弱信号分层：

强信号满足任一项，才可视为有效详情：

- `content` / `desc` / `detailText` 非空。
- `image_urls` 或 `video_url` 非空。
- `tags` 非空。
- raw payload 中存在可识别的 note detail map、note detail 或 detail card 结构。

弱信号只能辅助，不能单独让详情通过：

- likes / collects / comments / shares。
- note id。
- note URL。
- cover URL。
- title。

原因：搜索卡片也可能包含互动字段。如果互动字段单独通过，会继续把“只有卡片、没有详情”的数据误判为完整详情。

### Search card only

如果只有这些字段，则不能当作完整成功入库：

- note id。
- note URL。
- cover URL。
- title 很短或为空。
- content 为空。
- media 为空。

处理方式：

- API item 标记为 `partial`。
- 默认不保存到内容库。
- 如果未来允许“保存搜索卡片”，必须在 UI 上明确标记为“卡片数据，不是详情”。

### Rate limit behavior

命中访问频繁后：

- 停止本轮详情抓取。
- 不进行激进重试。
- 当前 `Task.status` 仍保持当前主系统兼容值：`completed` 或 `failed`。
- 部分失败信息写入 `Task.payload.failed_count`、`Task.payload.skipped_count`、`Task.payload.quality_summary` 和 `crawl_diagnostics`。
- 已成功的结果保留，未处理项标记为 skipped。
- 前端提示用户稍后再试，并展示已保存数量、失败数量、跳过数量。

如果后续要把 `Task.status` 扩展为 `partial_failed`，必须单独评估影响：

```text
backend/app/api/tasks.py
frontend/src/types/index.ts
任务中心页面
调度服务状态判断
```

## Frontend UX

### Keywords page

当前页面：

```text
frontend/src/pages/platforms/xhs/keywords-page.tsx
```

新增区域：**灰豚热词导入**。

推荐交互：

1. 用户输入种子关键词，或选择已有关键词组作为种子。
2. 用户粘贴灰豚表格、提交 JSON，或导入本地 connector 输出。
3. 页面展示候选词表格：词、热度、笔记数、互动数、分类、来源种子、排名。
4. 用户勾选候选词。
5. 选择“合并到当前组”或“创建新组”。
6. 成功后关键词组列表刷新，候选词保留来源记录。

关键 UX 规则：

- 默认去重，不重复导入同义文本。
- 不要求用户理解灰豚数据结构。
- 如果灰豚 connector 不可用，提示下一步：使用手工粘贴导入或 JSON 导入，而不是要求后端代管登录态。
- 不展示任何 Cookie、token 或会话敏感信息。

### Crawler page

当前页面：

```text
frontend/src/pages/platforms/xhs/crawler-page.tsx
```

新增展示：

- `成功`：已通过详情质量门禁并可入库。
- `部分成功`：拿到搜索卡片或评论失败，但详情不足。
- `失败`：无法获取详情或链接无效。
- `已跳过`：命中访问频繁后未继续处理。

表格增加列：

- 质量状态。
- 失败类型。
- 用户提示。
- 是否可恢复。
- 是否已入库。

前端类型必须同步更新：

```text
frontend/src/types/index.ts
frontend/src/pages/platforms/xhs/crawler-page.tsx
frontend/src/lib/api.ts
```

导出 Excel 时增加字段：

- 质量状态。
- 诊断类型。
- 保存诊断类型。
- 用户提示。
- 是否可恢复。
- 是否已入库。

## Implementation Sequence

### Phase 1: Pure logic and tests

1. 移植灰豚数字解析、热词行解析、分类解析为 Python 纯函数。
2. 移植短 explore URL 判定和 XHS rate-limit signal 判定为 Python 纯函数。
3. 新增详情质量门禁纯函数。
4. 新增单元测试覆盖：
   - 灰豚表格解析。
   - 热词去重和精确匹配优先。
   - `https://www.xiaohongshu.com/explore/<id>` 无 `xsec_token` 被拒绝。
   - 带 `xsec_token` 的 explore URL 允许继续。
   - `error_code=300013`、`访问频繁` 被识别为 rate limit。
   - 只有互动字段的搜索卡片不通过详情质量门禁。
   - 空详情不通过质量门禁。

### Phase 2: Backend persistence and APIs

1. 新增 SQLAlchemy models 和 Alembic migration。
2. 新增灰豚 discovery run API。
3. 新增候选词导入关键词组 API，包括导入已有组和创建新组。
4. 新增 crawl diagnostics 表和查询 API。
5. 增强 `crawl.py` 保存逻辑：低质量详情默认不入库。
6. 保持 `Task.status` 兼容，部分失败写入 payload 和 diagnostics。

### Phase 3: Detail recovery integration

1. 在 `/xhs/pc/notes/detail` 中加入 URL 预检查、质量状态和 inline diagnostic。
2. 在 `/xhs/crawl/data` 的 search / note_urls 模式中统一使用 detail recovery service。
3. 在 `/xhs/crawl/search-notes` 和 `/xhs/crawl/user-notes` 中明确卡片数据质量状态；默认不把低质量卡片伪装成完整详情。
4. 搜索结果带 `xsec_token` 时优先构造完整详情 URL。
5. 详情失败写入 diagnostics。
6. 命中 rate limit 后停止本轮详情抓取，不做激进重试。

### Phase 4: Frontend workflows

1. 关键词组页面增加灰豚热词导入卡片和候选词表格。
2. 数据抓取页面展示 quality status、failure kind、save diagnostic 和 user message。
3. Excel 导出增加诊断字段。
4. 空详情和短链接错误给出下一步动作。

### Phase 5: Verification

1. `py -3 -m pytest tests`
2. `npm --prefix frontend run build`
3. 后端 health check。
4. 本地 UI smoke。
5. 使用测试账号或用户明确授权的低风险账号，低频串行验证：
   - 搜索 1 个无害关键词。
   - 取 1 条详情。
   - 取少量评论。
   - 保存 1 条有效详情进内容库。
   - 用一个缺 `xsec_token` 的短 explore URL 验证失败诊断。
   - 不执行真实发布、Creator 发布、Provider/API 发布。

## Security and Operational Boundaries

- 不保存账号密码、明文 Cookie、Token、API Key 到代码或文档。
- XHS PC 操作默认低频、串行。
- 访问频繁时停止本轮任务，不做绕过、不做高频重试。
- 灰豚 connector 如果需要浏览器登录态，第一批不由后端接管；生产启用前必须另写风险设计。
- 真实账号发布、Creator 发布、Provider/API 发布不属于本设计，任何真实发布都需要用户对该次操作明确授权。
- 不修改 `apis/`、`xhs_utils/`、`static/` 底层 SDK/签名层；优先在 `backend/app/services/` 和 `backend/app/adapters/xhs/` 上层适配。

## Migration and Compatibility

- 现有 `keyword_groups.keywords` 保持 `list[str]`。
- 现有关键词组 API 不破坏。
- 新增表通过 Alembic migration 创建。
- 已有内容库笔记不回填质量状态；质量状态只从新采集任务开始记录。
- 旧 `data/xhs-ops.sqlite` 不导入。
- legacy TypeScript 文件继续保留在 `legacy/xhs-ops-collector/`，仅作为参考与测试对照。

## Verification Criteria

本设计对应的实现完成标准：

1. 用户能在关键词组页面从灰豚候选词导入关键词。
2. 每个候选词有来源种子、热度、笔记数、互动数、分类和排名。
3. 缺 `xsec_token` 的短 explore URL 不会被当作成功详情。
4. 只有链接、互动字段或空详情的数据不会默认污染内容库。
5. 访问频繁被结构化识别，并停止本轮详情抓取。
6. 采集结果表和导出文件都能看到失败原因和用户提示。
7. 后端测试、前端 build、health check 通过。
8. 不触发真实发布，不保存明文敏感信息。

## Later Enhancement Candidates

第一批之后再评估：

1. **Pipeline health check**：对采集任务、内容库、媒体和诊断记录生成健康报告。
2. **Analysis-source JSONL export**：把内容库中有效详情导出为稳定 Agent 分析包。
3. **Media archive manifest**：对图片/视频下载做完整性记录和重试。
4. **Feishu sync**：把内容库选题同步到飞书作为协作层，不作为事实源。
5. **Browser DOM fallback**：在本地低频浏览器 connector 下恢复 initial state / visible text，但必须先做脱敏和账号风险设计。

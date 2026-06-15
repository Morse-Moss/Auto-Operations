# 灰豚批量发现与运营体验修复设计

## 1. 背景与结论

用户在系统测试中暴露出两类问题：

1. 灰豚链路没有形成系统内资产化工作流：当前更像“输入一个词 -> 临时表格 -> 导入/导出”，不符合批量运营场景。
2. 发布中心、草稿工坊和 AI 生成入口没有贴合小红书真实运营习惯：可见性文案不对齐、缺复制草稿、参考材料输入过粗。

本轮直接做“一步到位”的最小完整闭环：

```text
灰豚批量种子词输入
  -> 每个种子独立诊断/成功/失败
  -> 候选词入库并可回看历史批次
  -> 成功候选词导入关键词组
  -> 从关键词组继续 XHS 采集并在系统内展示结果

同时修复：
  - 发布可见性文案对齐小红书
  - 草稿复制
  - AI 生成参考材料拆分
```

不做完整“灰豚工作台”独立模块，但把现有关键词组页升级为可支撑批量运营的灰豚发现入口。这样既能解决用户当前痛点，又避免把还不稳定的灰豚接口包装成过度复杂的产品。

## 2. 当前事实

### 2.1 灰豚候选词已有数据库表

现有模型：

- `backend/app/models/keyword_discovery.py`
  - `KeywordDiscoveryRun`
  - `KeywordDiscoveryItem`

这说明灰豚候选词已经能系统内入库，不需要从零建库。

### 2.2 后端 schema 已经支持批量 inputs

`backend/app/api/keyword_groups.py`：

```python
class HuitunDiscoveryRunRequest(BaseModel):
    source_mode: Literal["manual_table", "manual_json", "local_connector_output", "live_account"] = "manual_table"
    limit_per_seed: int = Field(default=20, ge=1, le=100)
    account_id: Optional[int] = None
    inputs: list[HuitunDiscoveryInput] = Field(min_length=1, max_length=50)
```

但前端 `frontend/src/pages/platforms/xhs/keywords-page.tsx` 只暴露单个 `huitunSeed`。

### 2.3 live_account 当前是整批失败语义

现有逻辑：

```python
for input_item in payload.inputs:
    rows.extend(live_keyword_client.fetch_huitun_hotwords(cookies_text, input_item.source_keyword, payload.limit_per_seed))
```

任何 seed 抛 `RuntimeError`，整个 run 被标记为 `failed` 并返回 400。批量场景下这会导致“一个词失败，整批不可用”。

### 2.4 灰豚接口失败缺少可操作诊断

当前失败消息主要是：

- `灰豚候选词获取失败，请先使用手工导入。`
- `灰豚登录态已过期，请到账号矩阵重新登录。`
- `灰豚候选词解密失败，请先使用手工导入。`

但没有区分：

- 登录态校验失败。
- HTTP 请求失败。
- 上游 status 非 0/200。
- extData 解密失败。
- extData 解密成功但列表路径不匹配。
- 单个 seed 失败还是整批失败。

### 2.5 发布可见性只支持 0/1

前端 `publish-page.tsx` 当前只有：

- `公开`
- `私密`

后端 `drafts.py`、`publish.py`、`creator.py` 当前 `privacy_type` 都限制 `ge=0, le=1`，发布时只映射到 `note_info["type"]`。

因此本轮只确定支持：

- `0`：公开可见。
- `1`：仅自己可见。

“仅互关好友可见”必须先确认底层 Creator SDK 枚举后才能启用真实发布，不允许前端假装可用。

### 2.6 草稿复制缺失

`backend/app/api/drafts.py` 没有 duplicate endpoint。前端草稿页也没有复制草稿按钮。

### 2.7 AI 生成参考材料输入过粗

`rewrite-page.tsx` 的生成模式只有：

- 选题。
- 参考材料。
- AI 指令。

“竞品链接、卖点、评论洞察、人群信息”全部塞进一个 TextArea，导致用户不知道该放链接还是写提示。

## 3. 目标

### 3.1 产品目标

1. 灰豚候选词支持批量种子词。
2. 每个种子词独立成功/失败，失败不拖垮整批。
3. 灰豚发现结果在系统内可回看、可筛选、可导入，不依赖 Excel。
4. 用户能看到失败原因和下一步行动：重新登录、稍后重试、使用手工导入、等待适配灰豚接口变化。
5. 复制草稿支持长文拆篇。
6. 发布可见性文案与小红书真实 UI 对齐，不误导用户。
7. AI 生成入口把链接和补充信息拆开，降低填写成本。

### 3.2 工程目标

1. 复用现有 `KeywordDiscoveryRun` / `KeywordDiscoveryItem`。
2. 不修改 `apis/`、`xhs_utils/`、`static/`。
3. 不做真实发布行为变化，只改 publish job 的可见性文案和参数收集。
4. 所有行为变化先写失败测试，再实现。
5. 使用 fake 灰豚 client 覆盖成功、部分失败、全失败、解密失败、上游结构变化。
6. 前端加轻量源码检查，确保核心 UI 入口存在。

## 4. 非目标

本轮不做：

- 不新建完整灰豚独立工作台。
- 不接入第二个平台。
- 不修改 XHS 底层 SDK/签名层。
- 不做真实账号发布验证。
- 不实现“只给谁看 / 不给谁看”的用户选择器。
- 不启用“仅互关好友可见”的真实发布参数，除非底层 Creator SDK 枚举被明确验证。
- 不删除 Excel 导出；可以保留作为辅助能力。
- 不重构整个关键词组页，只做围绕灰豚批量发现的手术式增强。

## 5. 核心设计

### 5.1 灰豚批量发现输入

前端将“种子关键词”从单行 Input 改为多行 TextArea：

```text
低卡早餐
通勤穿搭
小个子穿搭
职场新人
```

解析规则：

- 支持换行、中文逗号、英文逗号。
- trim 空白。
- 去重，保留首次出现顺序。
- 最多 50 个，沿用后端 schema。
- 空输入提示“请输入至少一个种子关键词”。

### 5.2 灰豚 live_account 执行语义

后端对每个 seed 独立执行：

```text
for seed in seeds:
  try fetch_huitun_hotwords
    success -> rows + seed_result.success
  except RuntimeError
    seed_result.failed，不中断整批
```

最终状态：

| 条件 | run.status |
|---|---|
| 至少 1 个成功，0 个失败 | `completed` |
| 至少 1 个成功，至少 1 个失败 | `partial_failed` |
| 0 个成功，至少 1 个失败 | `failed` |

HTTP 返回策略：

- 只要 run 被创建，就返回 200，包含 run 状态、items、seed_results。
- 只有请求本身不合法或账号不存在时返回 4xx。
- 全 seed 失败也返回 run，状态为 `failed`，前端展示失败详情。

这样用户不会因为整批失败而看不到诊断。

### 5.3 seed_results 存储方式

不做数据库 migration。利用现有 `KeywordDiscoveryRun.error_message` 存 JSON 文本。

格式：

```json
{
  "seed_results": [
    {
      "source_keyword": "低卡早餐",
      "status": "success",
      "item_count": 12,
      "error_message": ""
    },
    {
      "source_keyword": "通勤穿搭",
      "status": "failed",
      "item_count": 0,
      "error_message": "灰豚登录态已过期，请到账号矩阵重新登录。"
    }
  ],
  "summary": {
    "success_seed_count": 1,
    "failed_seed_count": 1,
    "total_item_count": 12
  }
}
```

序列化 API 时新增兼容字段：

```json
{
  "seed_results": [...],
  "summary": {...}
}
```

如果旧数据 `error_message` 不是 JSON，序列化时返回：

```json
{
  "seed_results": [],
  "summary": {
    "success_seed_count": 0,
    "failed_seed_count": 0,
    "total_item_count": len(items)
  }
}
```

保留原 `error_message` 字段，避免破坏兼容。

### 5.4 最近灰豚批次

新增后端 endpoint：

```http
GET /api/keyword-groups/huitun/discovery-runs?page=1&page_size=10
```

返回当前用户的灰豚发现 run，按 `created_at desc, id desc` 排序，每条包含：

- id
- source_mode
- status
- seed_keywords
- limit_per_seed
- created_at
- finished_at
- error_message
- seed_results
- summary
- items（可选，详情接口已有；列表接口可先返回空 items 或最近 items 的精简版）

推荐列表接口返回完整 `items`，因为最近 10 条、每条最多 50*100，但页面只展示最近 5-10 条时仍可能偏大。为了稳妥，第一版列表接口返回 items 为空，点击“查看”再调用现有：

```http
GET /api/keyword-groups/huitun/discovery-runs/{run_id}
```

### 5.5 前端灰豚发现体验

关键词组页的灰豚卡片升级为：

1. 灰豚账号选择。
2. 批量种子词 TextArea。
3. 每词候选词数量 `limit_per_seed`，默认 50。
4. “批量获取灰豚候选词”按钮。
5. 当前批次概览：成功种子、失败种子、候选词数量。
6. 失败 seed 列表：展示错误和建议行动。
7. 候选词 Table 保持现有列，新增来源 seed 筛选。
8. 导入选中候选词保持现有逻辑。
9. “最近灰豚批次”折叠列表：查看历史 run，恢复候选词表格继续导入。

### 5.6 灰豚接口诊断增强

`huitun_live_keyword_source.fetch_huitun_hotwords()` 保持对外抛 `RuntimeError`，但内部错误消息更稳定：

| 场景 | 用户消息 |
|---|---|
| 登录态校验失败 | 灰豚登录态已过期，请到账号矩阵重新登录。 |
| HTTP/network/JSON 失败 | 灰豚候选词获取失败，请稍后重试或使用手工导入。 |
| status 1001/401/403 | 灰豚登录态已过期，请到账号矩阵重新登录。 |
| extData 解密失败 | 灰豚候选词解密失败，请先使用手工导入。 |
| payload 结构不支持 | 灰豚候选词返回结构已变化，请先使用手工导入并等待适配。 |
| 解出列表为空 | 没有获取到候选词，可换种子词或使用手工导入。 |

解析增强：

- `_first_list()` 递归向下查找常见列表字段，最大深度 4。
- 支持 `extData`、`data`、`result`、`records`、`items`、`list`、`rows`。
- 当 payload 结构没有任何列表时抛结构变化消息，而不是静默空列表。

注意：如果灰豚加密 key 已变化，本轮不会绕过或破解风控，只提供明确诊断和手工导入兜底。

### 5.7 手工导入增强边界

保留现有“手工导入灰豚热词”。本轮只修解析容错，不做复杂 Excel 上传。

解析规则仍保持：每行至少 5 列：关键词、热度、笔记数、互动、分类。

### 5.8 发布可见性修复

前端选项改为：

- `public`：公开可见。
- `private`：仅自己可见。
- disabled：仅互关好友可见（待确认发布接口支持）。

提交给后端仍只传：

- public -> `privacy_type=0`, `is_private=false`
- private -> `privacy_type=1`, `is_private=true`

不改后端枚举范围，不冒险传未知值。

用户影响：文案对齐小红书，不误导用户“私密”是什么意思。

### 5.9 草稿复制

新增 endpoint：

```http
POST /api/drafts/{draft_id}/duplicate
```

行为：

- 只能复制当前用户自己的草稿。
- 新草稿字段：
  - `platform`：原值。
  - `title`：`{原标题} - 副本`；如果原标题为空，则 `未命名草稿 - 副本`。
  - `body`：原值。
  - `tags`：深拷贝。
  - `source_note_id`：保留。
- 复制 `DraftAsset` 记录：
  - asset_type
  - url
  - local_path
  - sort_order
- 不复制物理文件，只复制引用。
- 返回新草稿序列化结果。

前端：

- 草稿卡片或操作区新增“复制”按钮。
- 成功后刷新列表并选中新副本。
- 提示“已复制草稿，可拆分成多篇继续编辑”。

### 5.10 AI 生成参考材料拆分

前端生成模式字段改为：

1. 选题。
2. 参考链接：多行 TextArea，placeholder：`每行一个竞品笔记/网页链接，可不填`。
3. 补充信息：TextArea，placeholder：`卖点、评论洞察、人群信息、要强调/避免的内容`。
4. AI 指令。

后端不新增字段，前端在调用 `generateNoteWithAi` 前拼接为现有 `reference`：

```text
【参考链接】
<links>

【补充信息】
<context>
```

如果某块为空则不拼对应标题。

这样不改后端 AI 接口，降低风险。

## 6. 数据与 API 设计

### 6.1 新增响应类型：SeedResult

前端类型：

```ts
export type HuitunSeedResult = {
  source_keyword: string;
  status: "success" | "failed" | string;
  item_count: number;
  error_message: string;
};

export type HuitunDiscoverySummary = {
  success_seed_count: number;
  failed_seed_count: number;
  total_item_count: number;
};
```

扩展：

```ts
export type KeywordDiscoveryRun = {
  ...
  seed_results?: HuitunSeedResult[];
  summary?: HuitunDiscoverySummary;
};
```

### 6.2 后端序列化

`_serialize_discovery_run(run, items)` 新增：

- `seed_results`
- `summary`

并兼容旧 `error_message`。

### 6.3 新增列表接口

```python
@router.get("/huitun/discovery-runs")
def list_huitun_discovery_runs(...):
    ...
```

注意路由顺序：必须放在 `/{group_id}` 之前，且放在 `/{run_id}` 详情附近，避免被 `/{group_id}` 捕获。

### 6.4 导入候选词逻辑不改

保留：

- `POST /keyword-groups/import-keyword-candidates`
- `POST /keyword-groups/{group_id}/import-keyword-candidates`

## 7. 测试策略

### 7.1 后端 TDD 测试

新增：`tests/backend/test_huitun_keyword_discovery.py`

覆盖：

1. `live_account` 单 seed 成功。
2. `live_account` 多 seed 部分失败返回 200，run.status=`partial_failed`，成功 items 入库。
3. `live_account` 多 seed 全失败返回 200，run.status=`failed`，items 为空，seed_results 保留错误。
4. 最近 run 列表只返回当前用户数据。
5. 候选词导入仍可把成功 items 导入新关键词组。
6. payload 结构变化映射为可读错误。
7. extData 解密失败映射为可读错误。

### 7.2 草稿复制测试

新增或扩展：`tests/backend/test_drafts_duplicate.py`

覆盖：

1. 复制草稿会复制 title/body/tags/source_note_id。
2. 复制草稿会复制 draft assets 引用和 sort_order。
3. 不能复制其他用户草稿。

### 7.3 前端源码检查

现有测试风格里已有源码检查。扩展 `tests/backend/test_api.py` 或新建 `tests/backend/test_frontend_ops_ux_sources.py`：

覆盖：

- 关键词页包含批量种子词输入、最近灰豚批次、seed_results 展示。
- api.ts 包含 `fetchHuitunKeywordDiscoveryRuns`。
- types 包含 `HuitunSeedResult`。
- publish page 包含“公开可见”“仅自己可见”“仅互关好友可见”。
- drafts page 包含复制草稿按钮和 `duplicateDraft` API。
- rewrite/generate page 包含“参考链接”“补充信息”。

### 7.4 前端构建

运行：

```bash
cd frontend && npm run build
```

### 7.5 后端相关测试

运行：

```bash
py -3 -m pytest tests/backend/test_huitun_keyword_discovery.py tests/backend/test_drafts_duplicate.py tests/backend/test_api.py -q
```

如果 Windows 环境 `py` 不可用，用：

```bash
python -m pytest tests/backend/test_huitun_keyword_discovery.py tests/backend/test_drafts_duplicate.py tests/backend/test_api.py -q
```

## 8. 风险与控制

### 8.1 灰豚真实接口不可控

风险：灰豚加密 key 或接口结构已经变化。

控制：

- 不承诺自动获取一定恢复。
- 先增强诊断和结构解析。
- 保留手工导入。
- 如果真实响应显示 key 失效，单独写适配设计，不在本轮盲改底层。

### 8.2 批量请求触发风控

风险：多 seed 连续调用灰豚接口可能触发限流。

控制：

- 本轮仍是服务端低频串行。
- 不做并发。
- 每个 seed 独立失败，不自动高频重试。
- 如需 sleep，可在后端加小间隔或前端提示，但本轮不引入复杂队列。

### 8.3 error_message 存 JSON 是过渡方案

风险：把结构化 seed_results 放进 text 字段不够优雅。

控制：

- 不做 migration，降低本轮风险。
- 序列化函数封装 JSON 读写，未来可迁移到独立表。
- 文档明确这是第一版兼容方案。

### 8.4 发布可见性不能假装支持互关

风险：前端开放“仅互关好友可见”但后端/SDK 不支持，造成发布行为不符合预期。

控制：

- 本轮 disabled 展示。
- 只传 0/1。
- 后端枚举不扩展。

### 8.5 草稿复制资产只复制引用

风险：如果源文件后续被删除，副本素材也不可用。

控制：

- 当前系统素材本身就是引用模型。
- 本轮不复制物理文件，避免大范围文件管理改造。
- 后续如果要做“独立副本”，再设计媒体资产复制策略。

## 9. 成功标准

本轮完成后，必须满足：

1. 关键词组页能输入多个灰豚种子词并批量获取。
2. 一个 seed 失败不会导致成功 seed 的候选词丢失。
3. 前端能显示成功/失败 seed 数、失败原因和候选词总数。
4. 最近灰豚批次能回看，并能恢复候选词继续导入。
5. 候选词导入关键词组逻辑保持可用。
6. 灰豚接口结构变化/解密失败有明确用户消息。
7. 发布中心文案显示“公开可见 / 仅自己可见”，互关选项不误导为可用。
8. 草稿可复制，素材引用随副本保留。
9. AI 生成参考材料拆成“参考链接 / 补充信息”。
10. 后端相关 pytest 通过。
11. 前端 build 通过。
12. 不修改 `apis/`、`xhs_utils/`、`static/`。
13. 不执行真实发布、不绕过平台风控、不做高频批量请求。

## 10. 95% 把握门禁

进入开发前必须满足：

1. Spec 和 plan 已落盘。
2. 每个行为变化都有对应测试任务。
3. 灰豚真实接口不可控部分已经隔离成“诊断增强 + 手工兜底”，不以未知接口恢复作为唯一成功条件。
4. 不需要数据库 migration。
5. 不需要改底层 XHS SDK/签名层。
6. 不需要真实账号发布验证。

如果实现过程中出现以下情况，必须暂停并回报，而不是继续硬改：

- 灰豚接口需要新的加密 key 或新的签名机制。
- Creator SDK 明确支持的可见性枚举无法从现有代码确认。
- 前端 build 暴露大范围类型债务，超过本轮修改范围。
- 测试数据库 fixture 无法低成本构造，需要先补测试基础设施。

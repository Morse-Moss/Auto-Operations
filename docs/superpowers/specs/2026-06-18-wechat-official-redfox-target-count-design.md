# 公众号 Redfox 关键词收集目标篇数与相关性过滤设计

## 背景

当前公众号爆文发现的单关键词/批量关键词收集只让用户填写“页数”。Redfox 每页返回约 20 条，后端会把返回结果全部保存为候选，不检查标题、摘要或正文是否命中用户输入的关键词。

实际表现是：用户输入“浴缸”，系统会保存 Redfox 返回的所有结果，其中部分文章标题和摘要不包含“浴缸”，导致候选池看起来与关键词无关。

## 目标

让用户可以选择“获取多少篇相关候选”。用户填写目标篇数后，系统在安全页数上限内自动补页，并只保存与关键词相关的文章。

例如：用户输入关键词“浴缸”，目标相关篇数 10，最多翻页 3。系统最多调用 Redfox 3 页，过滤不命中关键词的结果，累计保留 10 篇相关候选后停止。

## 非目标

- 不使用 AI 判断语义相关性。
- 不修改 Redfox 第三方接口本身。
- 不改变按公众号、文章 URL 导入路径的核心语义。
- 不做真实发布、素材上传或草稿同步。

## 用户体验

### 单关键词收集

前端表单从“页数”主控改为：

- 关键词：必填。
- 目标相关篇数：默认 10，建议范围 1-50。
- 最多翻页：默认 3，建议范围 1-5。
- 最低阅读：保留现有默认值。

页面说明：系统会过滤标题、摘要或正文不命中关键词的结果，并在最多翻页范围内尽量补足目标篇数。

### 批量关键词收集

批量关键词使用同一套数量语义：每个关键词分别尝试获取目标相关篇数，串行执行，避免并发消耗 Redfox API。

### 结果反馈

最近一次收集结果展示：

- Redfox 返回条数。
- 相关命中条数。
- 过滤条数。
- 保存条数。
- API 调用数。
- 是否达到目标。

如果未达到目标，提示：Redfox 返回结果中相关内容不足，可换关键词或提高最多翻页。

## 后端数据流

现有路径：

1. 前端调用 `collectWechatOfficialRedfoxArticles`。
2. 后端 `WechatOfficialRedfoxService.collect_articles` 读取 keyword、pages、sort_type。
3. 后端按页调用 `WechatOfficialRedfoxClient.search_articles`。
4. 后端 normalize Redfox 返回结果。
5. `_save_collection` 保存全部结果。

新路径：

1. 前端提交 keyword、target_count、max_pages、sort_type、min_read_count。
2. 后端规范化 target_count 和 max_pages。
3. 后端按页调用 Redfox。
4. 每页 normalize 后立即进行关键词相关性过滤。
5. 只累计命中关键词的文章。
6. 达到 target_count 后停止继续翻页。
7. `_save_collection` 只保存命中关键词的文章。
8. summary 返回 fetched、filtered、relevance_matched、target_count、target_reached。

## 相关性规则

初版采用确定性文本包含规则，不做语义扩展。

候选文章命中以下任一字段即视为相关：

- title
- digest
- content_text
- Redfox raw.title
- Redfox raw.summary
- Redfox raw.memo

关键词规范化：

- 去除首尾空白。
- 如果用户输入包含空格、逗号、中文逗号、顿号或换行，拆分为多个 token。
- 任一 token 命中即可保留。
- 单关键词如“浴缸”必须原文命中。

过滤结果不保存到文章表，不进入候选池。

## API 兼容

新增 payload 字段：

- `target_count?: number`
- `max_pages?: number`

兼容旧字段：

- 如果没有 target_count，继续使用 pages * DEFAULT_PAGE_SIZE 作为目标上限。
- 如果没有 max_pages，则使用 pages 或默认 1。
- `pages` 暂时保留，避免旧前端或测试调用失败。

## Summary 字段

`WechatOfficialRedfoxCollectResponse.summary` 增加：

- `requested_target_count`
- `max_pages`
- `filtered`
- `relevance_matched`
- `target_reached`

保留现有字段：

- `fetched`
- `saved`
- `deduped`
- `viral_candidates`
- `failed`
- `api_calls`
- `estimated_credit_cost`

## 错误处理

- keyword 为空：继续返回 422。
- target_count 小于 1：归一到 1 或返回 422；实施时优先使用与现有 pages 相同的 bounded 风格。
- max_pages 超过上限：裁剪到上限。
- Redfox 某页失败：沿用当前异常路径，不静默吞掉。
- Redfox 返回不足：请求成功，`target_reached=false`，不作为错误。

## 测试方案

后端测试：

1. FakeRedfoxClient 返回混合结果：部分标题含“浴缸”，部分不含。
2. 调用关键词收集接口，传 target_count=2、max_pages=3。
3. 断言只保存命中“浴缸”的文章。
4. 断言 summary.filtered 统计正确。
5. 断言达到 target_count 后停止翻页。
6. 增加未达到目标场景，断言 target_reached=false。

前端验证：

1. TypeScript 类型包含 target_count、max_pages 和新增 summary 字段。
2. 单关键词表单展示“目标相关篇数”和“最多翻页”。
3. 批量关键词使用同样参数。
4. 最近一次结果展示过滤数量和是否达到目标。

## 影响范围

主要涉及：

- `backend/app/services/wechat_official_redfox_service.py`
- `frontend/src/types/index.ts`
- `frontend/src/pages/wechat-official/wechat-official-dashboard.tsx`
- `tests/backend/test_wechat_official_redfox_collect.py`

## 验收标准

- 用户可以在单关键词和批量关键词收集中填写目标相关篇数。
- 搜索“浴缸”时，不命中“浴缸”的文章不会作为候选入库。
- 如果 Redfox 返回很多不相关结果，系统展示过滤数量。
- 如果相关结果不足目标篇数，系统明确提示未达目标。
- 相关后端测试通过。
- 前端构建或类型检查通过。

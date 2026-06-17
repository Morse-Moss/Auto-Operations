# 小红书数据爬取页保存入系统设计

## 背景

当前「数据抓取」页的手动关键词、笔记链接和评论抓取结果只显示在本次页面表格中，用户只能导出 Excel。关键词组采集路径已经会把有效笔记保存到内容库，并在开启评论抓取时保存评论；但手动采集路径 `/api/xhs/crawl/data` 没有复用这套保存逻辑，导致用户认为“爬取完成了”，但系统内容库和分析链路没有获得数据。

## 目标

让数据爬取页成为系统内数据入口，而不是临时 Excel 工具：

1. 手动关键词采集和笔记链接采集支持保存到系统内容库。
2. 开启「同时抓取评论」时，已成功抓到的评论随对应笔记一起保存到 `note_comments`。
3. Excel 导出继续保留，作为离线交付方式。
4. 前端结果表的「入库」列真实反映保存结果。
5. 评论抓取失败或限流不阻断笔记保存。

## 非目标

1. 不修改 XHS 底层 SDK、签名逻辑或风控策略。
2. 不增加高频重试、绕过检测、验证码处理或号池能力。
3. 不在本次改造中支持“只爬评论模式”自动写入任意新笔记；评论入库必须依附系统内已保存的笔记。
4. 不重构内容库整体模型，不新增数据库表。

## 现有能力复用判断

### 可复用能力

- `backend/app/api/platforms/xhs/crawl.py` 中已有：
  - `_save_normalized_notes`
  - `_save_note_comments`
  - `_save_with_quality_gate`
- 关键词组采集已经使用上述函数实现：有效详情入库、评论跟随笔记入库、低质量结果跳过并记录诊断。
- `backend/app/api/notes.py` 的 `/notes/batch-save` 已支持内容库保存和可选评论抓取，并有测试覆盖。

### 复用边界

数据爬取页不应直接调用 `/notes/batch-save` 作为保存路径。原因：`crawl_data` 已经在后端流式抓到了详情和评论，再调用 `/notes/batch-save(fetch_comments=true)` 会重复请求评论接口，增加耗时和风控风险。

因此本次采用后端内部保存函数复用：在 `crawl_data` 内复用 `_save_normalized_notes` 和 `_save_note_comments`，避免重复网络请求。

## 用户体验设计

### 表单区

在数据爬取表单中增加「保存到系统内容库」复选框：

- 默认开启。
- 适用于「手动关键词」和「笔记链接」模式。
- 「只爬取评论」模式下置灰或显示说明：只爬评论不会创建新笔记；评论入库需要关联已有内容库笔记。
- 当「同时抓取评论」开启且「保存到系统内容库」开启时，提示：评论会随笔记一起入库。

### 结果区

保留现有列，并让以下列具备明确含义：

- 「入库」：显示已保存、未保存、跳过原因。
- 「评论状态」：显示未请求、成功、失败、访问频繁、因访问频繁跳过。
- 顶部汇总：显示成功、失败、已保存、跳过、评论限流、评论跳过。

### 操作区

- 主按钮仍是开始采集。
- 导出 Excel 继续保留。
- 不新增“抓完后再保存”主按钮，避免用户多一步和结果刷新丢失。

## 后端设计

### 请求模型

在 `DataCrawlRequest` 增加字段：

```python
save_to_library: bool = True
```

### `note_urls` 模式

流程：

1. 调用 `adapter.get_note_info(url)` 获取详情。
2. 标准化并执行 `evaluate_detail_quality`。
3. 若 `fetch_comments=true` 且质量允许保存，则调用 `adapter.get_note_comments(url)`。
4. 若 `save_to_library=true` 且质量允许保存，则调用 `_save_normalized_notes`。
5. 若保存成功且本次抓到评论，则调用 `_save_note_comments`。
6. SSE item 返回 `saved=true/false`、`comment_status`、`comment_count`。

### `search` 模式

流程：

1. 搜索关键词获取搜索卡片。
2. 对每条结果获取详情。
3. 质量允许时可抓评论。
4. 若 `save_to_library=true`，复用同样的保存逻辑。
5. 评论限流只停止后续评论抓取，不停止笔记详情抓取和笔记保存。

### `comments` 模式

本次保持为临时评论抓取：

- 返回评论结果供页面查看和 Excel 导出。
- 不默认创建新笔记。
- 不自动入库，除非后续新增“匹配已有笔记后保存评论”的独立设计。

### 汇总事件

`done` SSE 事件补充或保持以下字段：

- `total`
- `success_count`
- `failed_count`
- `saved_count`
- `skipped_count`
- `comment_rate_limited_count`
- `comment_skipped_count`
- `summary_message`

## 前端设计

### 状态

在 `XhsCrawlerPage` 增加：

```ts
const [saveToLibraryChecked, setSaveToLibraryChecked] = useState(true);
const [savedCount, setSavedCount] = useState(0);
const [skippedCount, setSkippedCount] = useState(0);
```

### 请求参数

`crawlXhsDataStream` payload 增加：

```ts
save_to_library: saveToLibraryChecked
```

关键词组采集维持现状：关键词组路径已经默认保存，不在本次改变其语义。

### 展示

- 表单中展示「保存到系统内容库」复选框。
- 若当前是 `comments` 模式，复选框置灰并说明“只爬评论不会创建新笔记”。
- 采集完成后显示汇总：保存 N 条、跳过 M 条、评论限流 X 条。

## 测试策略

### 后端测试优先

新增或扩展后端测试，先写失败用例：

1. `crawl_data` 的 `search` 模式在 `save_to_library=true` 时保存有效详情笔记。
2. `crawl_data` 的 `search` 模式在 `fetch_comments=true` 且评论成功时保存评论。
3. 评论接口限流时，笔记仍然保存，评论状态返回 `rate_limited` 或后续 `skipped_rate_limited`。
4. `save_to_library=false` 时，返回抓取结果但不写入 `notes` / `note_comments`。
5. 低质量详情不入库，并返回跳过原因。

### 前端验证

1. TypeScript 构建通过。
2. 数据爬取页能发送 `save_to_library`。
3. 结果汇总显示保存数量。
4. Excel 导出仍可用。

## 风险与控制

1. **重复网络请求风险**：通过复用本次已抓取的详情和评论数据，避免重复调评论接口。
2. **风控风险**：保持现有低频串行策略；评论限流后停止本轮后续评论抓取。
3. **脏数据风险**：继续使用现有质量门禁，低质量详情不自动入库。
4. **重复数据风险**：保存函数按 `note_id` 更新已有笔记，不重复创建。
5. **用户误解风险**：前端明确显示保存选项、保存数量和跳过原因。

## 完成标准

1. 手动关键词采集默认把有效笔记保存到内容库。
2. 笔记链接采集默认把有效笔记保存到内容库。
3. 开启评论抓取后，成功抓到的评论可在内容库笔记详情的评论接口中查到。
4. 关闭保存选项时，只展示和导出，不写入内容库。
5. 评论失败不影响笔记保存。
6. 相关后端测试通过，前端构建通过。

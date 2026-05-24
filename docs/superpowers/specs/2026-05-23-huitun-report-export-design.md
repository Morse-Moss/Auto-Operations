# 灰豚采集结果报告与 CSV 导出设计

## 背景

当前系统已经能通过 CLI 连接已登录浏览器，从灰豚采集热词、热词详情、热点笔记列表和部分笔记详情，并写入本地 SQLite。采集结束后 CLI 会输出一段 JSON 质量报告，但用户仍需要打开 SQLite 或阅读原始 JSON 才能判断本次采集是否可用、哪些热词贡献了有效笔记、以及如何把热点笔记交给后续选题分析。

本轮目标是把“采集完的数据”变成可直接使用的本地交付物：一个人可读的 run 报告，以及一个按热点笔记排序的 CSV 文件。

## 范围

本轮只做 CLI 只读能力：

- 查看最新或指定采集 run 的摘要报告。
- 导出最新或指定采集 run 的热点笔记 CSV。
- 为 run 选择、报告聚合、CSV 排序和 CSV 转义补测试。

本轮不做：

- 不修改灰豚页面采集流程。
- 不新增浏览器自动化动作。
- 不新增 Web 后台或可视化页面。
- 不做选题评分、内容生成或自动发布。
- 不保存账号、cookie、token 或任何登录凭证。

## CLI 交互

保留现有采集命令用法不变。新增两个子命令：

```bash
npm run collect -- report
npm run collect -- report --run-id 123
npm run collect -- export --output data/exports/run-123-notes.csv
npm run collect -- export --run-id 123 --output data/exports/run-123-notes.csv
```

公共参数：

- `--db-path <path>`：默认 `data/xhs-ops.sqlite`。
- `--run-id <id>`：可选。未传时选择最近一条已结束 run。

`export` 参数：

- `--output <path>`：必填。写入 CSV 文件。若父目录不存在，命令失败并提示用户创建目录或换路径；不自动创建新目录，避免把文件写到意外位置。

## 默认 run 选择

未传 `--run-id` 时，选择 `collection_runs` 中 `status != 'running'` 的最近一条记录，排序规则为：

1. `finished_at desc`
2. `id desc`

如果没有已结束 run：

- CLI 失败退出。
- 错误信息说明当前没有可报告的已结束采集 run，并提示用户先完成采集或传入明确的 `--run-id`。

传入 `--run-id` 时：

- 如果 run 不存在，失败退出。
- 如果 run 仍是 `running`，允许查看/导出，但报告顶部标注“run still running”，CSV 只导出现有记录。这样可以用于排查中途状态，不强行阻止用户查看已有数据。

## 报告内容

`report` 输出纯文本，面向运营判断，不输出大段 JSON。

报告包含：

- Run 基础信息：`id`、关键词、状态、天数、开始时间、结束时间。
- 采集参数：`limit_hotwords`、`limit_notes`。
- 总量：热词数、热词详情快照数、笔记数、有详情字段的笔记数、raw snapshots 数。
- 覆盖率：
  - 笔记详情覆盖率 = 有详情字段的笔记数 / 笔记数。
  - 点赞字段完整率 = 有 `list_likes` 或 `likes` 的笔记数 / 笔记数。
- 错误快照：按 `raw_snapshots.kind` 分组计数。
- 贡献热词：按每个热词贡献笔记数降序列出，包含最终保留笔记数、最高 `list_likes`、最低 `list_rank`。重复候选数不从历史 SQLite 近似推断，避免误导判断。
- 去重说明：最终保留和导出的笔记按稳定身份去重，同一篇笔记不会在 CSV 中重复出现。
- 警告：
  - run 状态为 `failed` 或 `partial_success`。
  - 详情覆盖率低于 100%。
  - 存在 raw snapshots。
  - 没有笔记。
  - run 仍为 `running`。

报告示例结构：

```text
Run #123  keyword="护肤"  status=partial_success  days=7
Started: 2026-05-23 10:00:00  Finished: 2026-05-23 10:08:00

Totals
- Hot words: 10
- Hot word snapshots: 9
- Notes: 87
- Detailed notes: 82
- Raw snapshots: 2

Coverage
- Detail coverage: 94.3%
- Likes completeness: 100.0%

Top contributing hot words
1. 早C晚A  notes=20  top_likes=12000  best_rank=1
2. 敏感肌修护  notes=18  top_likes=8300  best_rank=1

Raw snapshot warnings
- parse_note_detail_error: 2
```

## CSV 导出内容

CSV 使用 UTF-8，不加 BOM。第一行固定表头。所有字段按 CSV 规则转义：包含逗号、双引号、换行时用双引号包裹，双引号写成两个双引号。

排序规则：

1. 稳定笔记身份去重：同一个 `huitun_note_key` + `coalesce(published_at, '')` 组合只导出一行。
2. `hot_word` 升序。
3. `list_rank` 升序，空值排后。
4. `list_likes` 降序，空值排后。
5. `id` 升序，保证稳定输出。

字段顺序：

1. `run_id`
2. `source_keyword`
3. `hot_word`
4. `list_rank`
5. `list_page`
6. `title`
7. `author_name`
8. `is_video`
9. `published_at`
10. `likes`
11. `collects`
12. `comments`
13. `shares`
14. `estimated_reads`
15. `estimated_exposure`
16. `author_followers`
17. `author_note_count`
18. `read_exposure_ratio_text`
19. `read_follower_ratio_text`
20. `tags`
21. `huitun_note_key`

`tags` 从 `tags_json` 解析为 `|` 分隔字符串。解析失败时输出原始字符串，并在 report 的 warning 逻辑之外保持 export 成功；这是历史数据容错，不改变采集质量判断。

## 模块设计

新增模块：

- `src/reporting/types.ts`
  - 定义 run summary、hot word contribution、note export row 类型。
- `src/reporting/report.ts`
  - 把 repository 查询结果格式化为纯文本报告。
- `src/reporting/csv.ts`
  - CSV 表头、字段映射、转义和整表序列化。

扩展 repository：

- `findLatestFinishedRun()`：返回最近已结束 run。
- `findRunById(runId)`：返回指定 run。
- `getRunReportData(runId)`：返回报告需要的聚合数据。
- `listNoteExportRows(runId)`：返回 CSV 行数据。

CLI 调整：

- 将现有采集逻辑保留为默认命令行为。
- 在 `createProgram()` 中新增 `report` 和 `export` 子命令。
- 子命令只打开 SQLite，不连接浏览器。

## 错误处理

- 数据库文件不存在：命令失败，提示先运行采集或检查 `--db-path`。
- 已存在的旧 SQLite schema：命令打开后先运行迁移，补齐 report/export 需要的列并清理重复稳定身份；迁移失败时命令失败。
- `--run-id` 非正整数：参数解析失败。
- 指定 run 不存在：命令失败并说明 run id。
- `export --output` 缺失：参数解析失败。
- 输出文件父目录不存在，或父路径存在但不是目录：命令失败，不自动创建目录。
- 写文件失败：保留底层错误信息，并说明目标路径。

## 测试策略

新增或扩展测试：

- CLI options：验证 `report`、`export` 参数解析和无效 run id。
- DB repository：插入多条 run，验证最新已结束 run 选择规则。
- Report formatter：验证总量、覆盖率、warning、贡献热词排序。
- CSV formatter：验证表头、字段顺序、排序、空值、逗号/引号/换行转义、tags 解析。
- Export query：验证同一稳定笔记身份只导出一行，最终 CSV 不重复。
- Export command：使用临时 SQLite 和临时输出文件验证完整写入。

每次实现后运行：

```bash
npm test
npm run typecheck
```

## 完成标准

本轮完成后：

- 用户可以不打开 SQLite，直接查看最近一次采集 run 的可读摘要。
- 用户可以把最近或指定 run 的热点笔记导出为 CSV。
- 采集命令原有行为保持兼容。
- 报告/导出逻辑有单元测试覆盖。
- `npm test` 和 `npm run typecheck` 通过。

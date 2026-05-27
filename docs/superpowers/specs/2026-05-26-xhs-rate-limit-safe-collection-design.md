# 小红书搜索安全采集优化设计

## 背景

2026-05-26 对灰豚 run 11 的「浴缸」二级搜索做全量验收：10 个热词、4 个排序、每排序 20 条，并开启 `--with-details`。命令完成并入库，但所有 `xhs_search_runs` 都是 `partial_success`。本地 SQLite 复核结果：共写入 547 条搜索笔记，其中 500 条有详情、474 条有标签、500 条有媒体；47 条详情失败集中在最后一个词「浴缸在卧室」。失败快照显示小红书跳转到 `/website-login/error`，URL 参数包含 `error_code=300013`，错误信息为「访问频繁，请稍后再试」。

根因不是登录失效，也不是解析器崩溃，而是详情页连续访问过密触发平台频率限制。现有实现会在每个排序后立即串行打开该排序的所有详情页；遇到频率限制时只把单条详情记为失败，然后继续打开后续详情页和关键词。这会扩大账号风险，并产生大量已知不可恢复的失败快照。

## 目标

采用已确认的 B 方案：保留“一条命令跑完整链路”的体验，但给详情采集加默认限速、预算和熔断，使系统在可用性和账号安全之间取平衡。

本轮要实现：

- `xhs-search --with-details` 默认低频打开详情页。
- 单次命令默认有详情页预算，避免一次性打完几百个详情页。
- 明确识别小红书频率限制，并在命中后立即停止继续访问详情页和后续关键词。
- 保留已经成功入库的列表和详情数据，不因为后续频率限制回滚。
- 支持后续重新运行时跳过已有详情，只补缺失详情，减少重复访问。
- 用测试覆盖频率限制识别、熔断、预算和 resume 行为。

## 不做

- 不绕过登录、风控、验证码或平台权限。
- 不保存账号、密码、cookie、localStorage 或浏览器会话凭证。
- 不并发打开大量详情页。
- 不调用或破解小红书非公开接口。
- 不把详情访问频率做成隐蔽规避机制；只做正常低频访问和遇限停止。
- 不改变现有小红书搜索列表采集的数据模型。
- 不在本轮做 GUI、后台任务队列或定时调度。

## CLI 交互

保留现有用法：

```bash
npm run collect -- xhs-search --from-huitun-run-id 11 --with-details
npm run collect -- xhs-search --keyword 浴缸 --with-details
```

新增参数：

- `--detail-delay-min-ms <ms>`：详情页之间的最小等待时间，默认 `20000`。
- `--detail-delay-max-ms <ms>`：详情页之间的最大等待时间，默认 `60000`。
- `--detail-budget <count>`：单次命令最多补充多少条详情，默认 `30`。
- `--no-stop-on-rate-limit`：关闭频率限制熔断；默认开启熔断。
- `--no-resume-missing-details`：关闭跳过已有详情；默认只补缺失详情。

参数校验：

- `detail-delay-min-ms` 和 `detail-delay-max-ms` 必须是非负整数。
- `detail-delay-max-ms` 必须大于等于 `detail-delay-min-ms`。
- `detail-budget` 必须是正整数。
- `--with-details` 未开启时，详情限速参数允许传入但不产生效果；CLI 不失败，避免用户脚本需要分支。

## 默认行为

开启 `--with-details` 后：

1. 仍然先采集搜索列表并写入 `xhs_search_notes`。
2. 准备补详情时，过滤掉已经有 `detail_text` 或 `raw_detail_text` 或 `media_sources_json` 非空的记录。
3. 按当前关键词、排序、排名顺序串行补详情。
4. 每成功或失败访问一个详情页后，若还有预算且未触发熔断，则等待一个 `[detailDelayMinMs, detailDelayMaxMs]` 区间内的随机时长。
5. 当前命令累计详情访问数达到 `detailBudget` 后，停止详情补充；已采列表仍入库，run 标记为 `partial_success`。
6. 如果检测到频率限制，立即记录快照并停止整个批次，不继续当前关键词剩余详情，也不继续后续关键词。

默认参数的用户影响：

- 一次全量命令仍能拿到搜索列表。
- 默认最多补 30 条详情，所以大批量 run 会需要多次执行才能补齐详情。
- 多次执行同一个命令会自动跳过已经有详情的笔记，逐步补齐缺失详情。
- 触发小红书访问频繁时，命令会早停，避免把后续所有详情都打成失败。

## 频率限制识别

新增统一判断函数，检查错误对象、最终 URL、页面文本和诊断消息。命中任一条件即认为是小红书频率限制：

- URL 包含 `/website-login/error` 且包含 `error_code=300013`。
- URL query 或文本包含 `访问频繁`。
- URL query 或文本包含 `请稍后再试`，并且 host 是 `xiaohongshu.com` 或 `www.xiaohongshu.com`。
- 错误消息中包含 `error_code=300013`。

识别后使用专门错误类型或结果状态向上抛出，避免被普通详情失败吞掉。

## 熔断行为

命中频率限制时：

1. 当前详情失败不再作为普通 `xhs_detail_collection_error` 处理。
2. 写入 `xhs_raw_snapshots.kind = xhs_rate_limited`。
3. `object_key` 使用 `<keyword>:<sortKey>:<feedId>`。
4. `text_content` 第一行写入诊断原因，例如 `XHS rate limited: error_code=300013 访问频繁，请稍后再试`，后面附页面文本。
5. 当前 `xhs_search_runs` 结束为 `partial_success`，`error_stage = xhs_rate_limited`，`error_message` 写入可读提示。
6. 整个 `collectXhsSearch` 返回时包含 `rateLimited: true`、触发 keyword、sortKey、feedId 和已消耗详情预算。
7. 批量模式停止后续关键词。

如果某个排序列表结果不足 `limit-per-sort`，仍沿用 `xhs_note_list_short`，不视为频率限制。

## Resume 行为

默认 `--resume-missing-details` 开启。详情补充前判断当前 note 是否已有有效详情：

- `detail_text` 非空，或
- `raw_detail_text` 非空，或
- `media_sources_json` 解析后长度大于 0。

满足任一条件就跳过，不再打开详情页。这样同一批数据可以多次执行命令逐步补齐，且不会重复访问已经成功的详情页。

当前表唯一键是 `run_id + keyword + sort_key + feed_id`。同一命令重新运行会创建新的 `xhs_search_runs`，因此本轮 resume 只保证“同一个 run 内已经成功的详情不重复补”。跨 run 去重和跨 run 补详情需要单独设计，不在本轮做。

## 预算行为

`detailBudget` 以“本次命令实际打开详情页次数”为单位，而不是成功详情数。普通失败和频率限制触发页都会消耗预算。

预算耗尽时：

- 当前 run 标记为 `partial_success`。
- 写入 `xhs_raw_snapshots.kind = xhs_detail_budget_exhausted`，说明本次详情预算用尽。
- 不再打开后续详情页。
- 批量模式可以继续下一个关键词的列表采集，但不再补详情，避免列表流程被详情预算阻塞。

## 数据与类型变化

扩展 `XhsSearchCommandOptions`：

- `detailDelayMinMs: number`
- `detailDelayMaxMs: number`
- `detailBudget: number`
- `stopOnRateLimit: boolean`
- `resumeMissingDetails: boolean`

扩展 `XhsSearchCollectorResult`：

- `rateLimited: boolean`
- `detailBudgetUsed: number`
- `rateLimitContext?: { keyword: string; sortKey: XhsSearchSortKey; feedId: string; message: string }`

新增 raw snapshot kind：

- `xhs_rate_limited`
- `xhs_detail_budget_exhausted`

不新增数据库表字段；状态仍使用现有 `RunStatus`，频率限制通过 `error_stage`、`error_message` 和 raw snapshot 表达。

## 模块调整

### `src/cli.ts`

- 增加详情限速、预算、熔断和 resume 参数。
- 校验新参数。
- 将新参数传入 `collectXhsSearch`。

### `src/browser/xhs-note-detail.ts`

- 在详情打开后检查最终 URL 和页面文本是否命中频率限制。
- 命中时抛出可识别错误，不再继续解析为普通详情失败。
- 保持现有完整 `search_result_url` 访问策略。

### `src/xhs-search-collector.ts`

- 引入详情访问预算计数。
- 在详情访问之间等待随机延迟。
- 遇到频率限制时写入 `xhs_rate_limited` 并停止整个批次。
- 预算耗尽时写入 `xhs_detail_budget_exhausted` 并停止详情补充。
- resume 开启时跳过已有详情的行。

### `src/db/repositories.ts`

- 增加读取当前 run 已有详情状态所需的查询，或在采集过程中用刚写入的 row 状态判断。
- 保持 upsert 行为不覆盖已有成功详情为空值。

## 测试策略

单元测试：

- CLI 参数解析：默认值、非法 delay、非法 budget、`--no-stop-on-rate-limit`、`--no-resume-missing-details`。
- 频率限制识别：`/website-login/error?error_code=300013`、文本「访问频繁，请稍后再试」、普通详情错误不误判。
- 预算：超过 `detailBudget` 后不再调用详情采集。
- 熔断：命中频率限制后不继续当前排序、当前关键词或后续关键词。
- resume：已有详情的 note 不再调用详情采集。
- repository upsert：已有成功详情不会被空详情覆盖。

人工验收：

1. 小批量真实运行：
   ```bash
   npm run collect -- xhs-search --from-huitun-run-id 11 --limit-keywords 1 --sorts most_liked --limit-per-sort 3 --with-details --detail-budget 2 --detail-delay-min-ms 1000 --detail-delay-max-ms 2000
   ```
   预期：列表入库 3 条，最多补 2 条详情，run 为 `partial_success`，存在 `xhs_detail_budget_exhausted`。
2. 用测试 fixture 模拟 300013：确认 CLI 结果包含 `rateLimited: true`，并写入 `xhs_rate_limited`。
3. 不再直接运行 10 词 × 4 排序 × 20 详情的高风险命令作为验收方式。

## 运营使用建议

- 全量搜索列表可以继续跑，但详情默认分批补。
- 如果目标是快速判断选题，优先采 `most_liked` 和 `most_collected`，减少详情访问量。
- 触发 `xhs_rate_limited` 后当天不再继续访问详情页。
- 报告或导出时需要展示详情覆盖率，避免把详情缺失误当成真实内容缺失。

## 成功标准

- 默认 `--with-details` 不会连续打开几百个详情页。
- 触发 `error_code=300013` 时立即停止后续详情和关键词。
- 已成功入库的列表和详情被保留。
- 重跑同一个 run 的补详情流程不会重复访问已有详情。
- 测试覆盖限速参数、预算、频率限制识别、熔断和 resume。

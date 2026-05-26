# 小红书二级搜索采集设计

## 背景

当前系统第一阶段已经能从灰豚热词搜索和热词详情页采集热词、灰豚笔记列表和部分详情，并写入本地 SQLite。下一步需要在拿到热点帖子关键词后，去小红书站内按关键词搜索，并按排序维度获取候选爆款帖子，再集中分析。

本设计参考 TeamWiseFlow/wiseflow 的 `xhs-content-ops` skill，但只采用其“浏览器登录态 + 小红书搜索页 + 排序筛选 + 笔记详情链接”的采集思路，不引入发布、评论、点赞、收藏等运营动作。

## 实测结论

2026-05-25 使用已登录小红书的浏览器 CDP 验证了以下事实：

1. 搜索入口可用：`https://www.xiaohongshu.com/search_result?keyword=护肤`，页面会自动补 `type=51`。
2. 未登录时页面显示“登录后查看搜索结果”，不能读取搜索结果。采集必须先检测登录墙。
3. 已登录后，搜索页顶部有频道：全部、图文、视频、用户。
4. “筛选”面板中存在排序依据：综合、最新、最多点赞、最多评论、最多收藏。
5. 排序按钮 DOM 中有 `data-hp-kind="filter-tag-最新"`、`filter-tag-最多点赞`、`filter-tag-最多评论`、`filter-tag-最多收藏` 等辅助节点，但实际切换应点击其后面的可见 sibling，不能只点击隐藏辅助层。
6. 已实测 `latest`、`most_liked`、`most_commented`、`most_collected` 均能切换，并能读取至少 20 条 `section.note-item` 搜索结果。
7. 搜索结果卡片中可读取标题、作者、发布日期、当前排序指标、封面图、笔记链接。
8. 隐藏的 `/explore/{feed_id}` 短链接直接打开会重定向到推荐流，不能作为详情访问链接。
9. 可见封面/标题链接形如 `/search_result/{feed_id}?xsec_token=...&xsec_source=`，必须保存并使用这个完整链接或通过站内点击打开。
10. 使用完整搜索结果链接打开后，会跳转到 `/explore/{feed_id}?xsec_token=...`，可读取正文、标签、评论数、赞藏指标等详情页文本。

## 目标

新增 `xhs-search` 二级采集能力：

- 支持手动输入关键词，或后续从灰豚采集 run 中读取热词。
- 对每个关键词在小红书搜索页按多个排序维度采集候选笔记。
- 默认排序维度为：最新、最多点赞、最多评论、最多收藏。
- 每个排序默认采集前 20 篇。
- 将搜索结果和可选详情字段写入 SQLite，供后续集中判断分析。

## 本轮范围

### 做

- 新增小红书搜索采集 CLI 子命令。
- 连接用户已有登录态浏览器，不启动无登录态浏览器作为默认路径。
- 打开小红书搜索页并检测登录态。
- 打开筛选面板，按排序维度切换搜索结果。
- 滚动加载并采集每个排序前 N 条笔记。
- 保存搜索列表字段、完整详情链接、`feed_id`、`xsec_token`、排序维度和排序内排名。
- 可选打开详情页补充正文、标签、详情页互动数据。
- 记录失败快照和不可用排序。
- 为 URL、排序解析、列表 DOM 解析、详情 URL 提取、数据库写入补测试。

### 不做

- 不点赞、不收藏、不评论、不关注、不发布。
- 不绕过登录、风控、验证码或平台权限。
- 不保存账号、密码、cookie、localStorage 或浏览器会话凭证。
- 不调用或破解小红书非公开接口。
- 不并发打开大量详情页。
- 不把小红书搜索结果混进现有灰豚 `notes` 表。
- 不在本轮做内容生成或自动选题评分。

## CLI 交互

新增子命令：

```bash
npm run collect -- xhs-search --keyword 护肤
npm run collect -- xhs-search --keyword 护肤 --sorts latest,most_liked,most_commented,most_collected --limit-per-sort 20
npm run collect -- xhs-search --keyword 护肤 --with-details
npm run collect -- xhs-search --from-huitun-run-id 123 --limit-keywords 10
```

参数：

- `--keyword <keyword>`：单个小红书搜索关键词。
- `--from-huitun-run-id <id>`：从指定灰豚 run 的热词中读取关键词。和 `--keyword` 二选一。
- `--limit-keywords <count>`：从灰豚 run 读取时最多处理多少个热词，默认 10。
- `--sorts <list>`：逗号分隔排序维度，默认 `latest,most_liked,most_commented,most_collected`。
- `--limit-per-sort <count>`：每个排序维度最多采集多少条，默认 20。
- `--with-details`：是否打开笔记详情页补充正文、标签、评论数和详情互动数据。默认关闭，避免高频打开详情页。
- `--db-path <path>`：SQLite 数据库路径，默认 `data/xhs-ops.sqlite`。
- `--cdp-url <url>`：浏览器 CDP 地址，默认 `http://127.0.0.1:9222`。

## 数据模型

### xhs_search_runs

记录每次小红书搜索采集任务。

字段：

- `id`
- `source`：`manual_keyword` 或 `huitun_run`
- `source_run_id`：来自灰豚 run 时填写
- `keyword`
- `sorts_json`
- `limit_per_sort`
- `with_details`
- `status`
- `started_at`
- `finished_at`
- `error_stage`
- `error_message`

### xhs_search_notes

记录小红书搜索结果候选笔记。

字段：

- `id`
- `run_id`
- `keyword`
- `sort_key`：`latest`、`most_liked`、`most_commented`、`most_collected`
- `sort_label`：页面中文排序名
- `rank_index`
- `feed_id`
- `xsec_token`
- `search_result_url`：从搜索结果卡片读取的完整链接
- `explore_url`：打开详情后最终地址，可为空
- `title`
- `author_name`
- `author_profile_url`
- `cover_url`
- `published_at_text`
- `metric_text`：当前排序下卡片显示的指标文本
- `detail_text`
- `detail_tags_json`
- `detail_comment_count_text`
- `detail_like_text`
- `detail_collect_text`
- `detail_share_text`
- `raw_card_text`
- `collected_at`

唯一性：`run_id + keyword + sort_key + feed_id`。同一篇笔记可以出现在多个排序维度中，每个排序保留自己的排名和指标。

### xhs_raw_snapshots

记录排错快照。

字段：

- `id`
- `run_id`
- `kind`
- `object_key`
- `page_url`
- `text_content`
- `html_content`
- `captured_at`

常见 `kind`：

- `xhs_login_required`
- `xhs_sort_not_found`
- `xhs_sort_click_failed`
- `xhs_note_list_short`
- `xhs_note_parse_error`
- `xhs_note_detail_error`

## 模块设计

新增模块：

- `src/browser/xhs-session.ts`
  - 连接浏览器 CDP，新开页面，检测小红书登录态，捕获页面快照。
- `src/browser/xhs-search.ts`
  - 构造搜索 URL。
  - 打开搜索页。
  - 展开筛选面板。
  - 根据排序 key 找到并点击可见排序按钮。
  - 滚动加载并解析 `section.note-item`。
- `src/browser/xhs-note-detail.ts`
  - 使用搜索结果完整链接打开详情页。
  - 解析最终 `explore_url`、正文、标签和详情页可见互动数据。
- `src/xhs-types.ts`
  - 定义小红书 run、排序、列表行、详情类型。避免和灰豚类型混在一起。

扩展：

- `src/db/schema.ts`
  - 新增 `xhs_search_runs`、`xhs_search_notes`、`xhs_raw_snapshots`。
- `src/db/repositories.ts`
  - 新增小红书搜索 run、note、snapshot 写入方法。
- `src/cli.ts`
  - 新增 `xhs-search` 子命令。

## 采集流程

单关键词流程：

1. 创建 `xhs_search_runs`，状态为 `running`。
2. 连接浏览器 CDP，新开小红书页面。
3. 打开搜索页 `https://www.xiaohongshu.com/search_result?keyword=<keyword>`。
4. 读取 body 文本，若包含“登录后查看搜索结果”，记录 `xhs_login_required` 并失败退出。
5. 打开筛选面板。
6. 对每个排序维度：
   1. 查找对应排序按钮。
   2. 点击可见 sibling 切换排序。
   3. 等待 active 状态或首条结果变化。
   4. 滚动加载直到采集到 `limit_per_sort` 条，或连续滚动无新增。
   5. 解析并写入 `xhs_search_notes`。
7. 如果 `--with-details` 开启，则串行打开每条笔记的完整 `search_result_url`，补充详情字段。
8. 汇总成功和失败排序，更新 run 状态。

从灰豚 run 输入关键词流程：

1. 读取指定灰豚 run 中的 `hot_words`，按 `rank_index` 升序取前 `limit-keywords`。
2. 对每个热词执行单关键词流程。
3. 同一个 `xhs_search_runs` 可以记录一个源关键词；为简化排错，批量模式为每个关键词创建独立 xhs run。

## 解析策略

搜索结果卡片：

- 主选择器：`section.note-item`。
- 详情链接优先级：
  1. `.cover[href*="/search_result/"]`
  2. `.title[href*="/search_result/"]`
  3. 其他包含 `xsec_token` 的 `/search_result/` 链接
- `feed_id` 从 `/search_result/{feed_id}` 或最终 `/explore/{feed_id}` 提取。
- `xsec_token` 从 URL query 提取。
- 卡片文本按行解析标题、作者、发布时间、指标。解析失败时保留 `raw_card_text`，但不写空 `feed_id` 行。
- “大家都在搜”等推荐块没有有效链接，必须跳过。

排序切换：

- 排序 key 映射：
  - `latest` → 最新
  - `most_liked` → 最多点赞
  - `most_commented` → 最多评论
  - `most_collected` → 最多收藏
- 优先通过 `data-hp-kind="filter-tag-<label>"` 找到辅助节点，再点击 `nextElementSibling` 这个可见按钮。
- 如果辅助节点不存在，则退回到筛选面板内按文本查找可见 `.tags`。
- 点击后必须验证对应中文 label 出现在排序区域 active 项中；验证失败记录 `xhs_sort_click_failed`。

详情页：

- 不能直接拼 `/explore/{feed_id}` 短 URL。
- 必须使用搜索结果里的完整 `search_result_url`，或通过站内点击进入。
- 成功后保存最终 `location.href`，通常为 `/explore/{feed_id}?xsec_token=...`。

## 错误处理

- 浏览器 CDP 连接失败：命令失败，提示用户启动已登录小红书的浏览器 CDP。
- 登录墙：命令失败，提示“当前小红书登录态不可用，请在 CDP 浏览器中登录小红书后重试”。
- 排序不存在：该排序标为失败，继续其他排序。
- 排序点击后 active 未变化：记录快照并跳过该排序。
- 某排序不足 20 条：保留已采集结果，run 标记为 `partial_success`。
- 详情页打不开或被推荐流重定向：记录 `xhs_note_detail_error`，保留列表结果。
- 单条笔记解析失败：跳过该条并记录快照，不终止整个 run。

## 安全和频率控制

- 默认串行处理排序和详情页。
- 默认不打开详情页；只有用户显式传 `--with-details` 时才补详情。
- 每次排序切换后等待页面稳定。
- 每次详情页打开后关闭详情 tab。
- 不写入任何登录凭证。
- 不调用点赞、收藏、评论、关注、发布相关页面能力。

## 测试策略

新增或扩展测试：

- CLI options：验证 `xhs-search` 参数解析、`--keyword` 和 `--from-huitun-run-id` 互斥、排序 key 校验。
- URL builder：验证关键词编码和搜索 URL 构造。
- Sort mapping：验证排序 key 到中文 label 的映射。
- DOM parser：用实测搜索卡片 HTML fixture 验证 `feed_id`、`xsec_token`、标题、作者、日期、指标、封面和完整链接解析。
- Detail URL parser：验证从 `/search_result/{id}?xsec_token=...` 和 `/explore/{id}?xsec_token=...` 提取身份。
- Repository：验证 xhs run、notes、snapshots 写入和唯一性。
- Login detection：验证“登录后查看搜索结果”会触发登录态错误。

实现后运行：

```bash
npm test
npm run typecheck
```

## 完成标准

本轮完成后：

- `xhs-search --keyword 护肤` 能在已登录浏览器中按默认四个排序维度采集候选笔记。
- 每个可用排序默认最多保存 20 条。
- SQLite 中能区分关键词、排序维度、排序内排名和小红书笔记身份。
- 列表结果保存完整 `search_result_url` 和 `xsec_token`。
- `--with-details` 能串行补充详情页文本和标签，失败不影响列表结果。
- 未登录时不会误报空结果，会明确提示登录态不可用。
- 相关测试通过，`npm test` 和 `npm run typecheck` 通过。

# 灰豚爆文样本采集 MVP 设计

## 目标

第一阶段构建一个本地灰豚数据采集器，把人工流程自动化并写入 SQLite：业务关键词 → 热词列表 → 热词详情 → 笔记列表 → 笔记详情弹窗 → 爆文样本库。

## 实测灰豚流程

已在登录态浏览器中验证以下路径：

1. 打开灰豚热词搜索页：`https://xhs.huitun.com/#/hotWords/hot_words_recommend`。
2. 在“请输入热词关键词”输入业务关键词，例如“浴缸”。
3. 页面跳转到 `#/hotWords/hot_words_search?searchValue=浴缸`，展示热词列表。
4. 热词列表包含：热词、热度值、笔记数、笔记互动量、关联分类。
5. 热词详情页可通过 `#/hotWords/hot_word_detail?hotWord=浴缸` 打开。
6. 详情页包含近 30 天概览、近 7/30/90/180 天筛选、商业/非商业筛选、热词趋势和笔记列表。
7. 点击笔记标题会打开灰豚笔记详情弹窗，弹窗包含更完整的笔记、作者和指标数据。

## 技术判断

灰豚核心接口可观察到，例如 `/hotword/search/v2`、`/hotword/detail`、`/hotword/overviewV3`、`/hotword/detail/notesV3`，但返回内容包含 `encrypt: true`。第一阶段不破解接口加密，改用浏览器读取已渲染 DOM。

这个方案的好处是贴近人工操作路径，能利用用户已有登录态，且页面字段变化时容易通过 DOM 快照排查。

## 第一阶段范围

### 做

- 连接用户已有 Edge/Chrome 登录态。
- 自动打开灰豚热词搜索页。
- 输入业务关键词并采集热词列表。
- 打开目标热词详情页。
- 采集热词概览和笔记列表。
- 点击笔记标题，采集笔记详情弹窗字段。
- 写入本地 SQLite。
- 支持重复运行去重。
- 记录采集批次、失败阶段和原始 DOM 快照。

### 不做

- 不破解灰豚加密接口。
- 不抓小红书原文正文。
- 不自动发布小红书。
- 不生成标题、文案、封面或视频素材。
- 不做复杂 Web 后台。
- 不多 agent 并发操作同一个灰豚登录态页面。

## 用户入口

第一版提供命令行入口：

```bash
npm run collect -- --keyword 浴缸 --limit-hotwords 10 --limit-notes 20 --days 7
```

参数含义：

- `--keyword`：业务关键词。
- `--limit-hotwords`：最多采集多少个热词。
- `--limit-notes`：每个热词最多采集多少条笔记。
- `--days`：详情页时间范围，第一版支持 `7`、`30`、`90`、`180`。

## 数据模型

### collection_runs

记录每次采集任务。

字段：

- `id`
- `keyword`
- `days`
- `limit_hotwords`
- `limit_notes`
- `status`
- `started_at`
- `finished_at`
- `error_stage`
- `error_message`

### hot_words

记录热词搜索页结果。

字段：

- `id`
- `run_id`
- `source_keyword`
- `word`
- `hot_value_text`
- `hot_value_number`
- `note_count`
- `interaction_text`
- `interaction_number`
- `categories_json`
- `rank_index`
- `collected_at`

### hot_word_snapshots

记录热词详情页概览。

字段：

- `id`
- `run_id`
- `word`
- `days`
- `page_url`
- `heat_text`
- `related_notes_text`
- `total_interactions_text`
- `overview_json`
- `collected_at`

### notes

记录灰豚笔记基础信息和详情弹窗补充信息。

字段：

- `id`
- `run_id`
- `source_keyword`
- `hot_word`
- `huitun_note_key`
- `title`
- `author_name`
- `author_level`
- `cover_url`
- `is_video`
- `video_duration`
- `published_at`
- `updated_at`
- `tags_json`
- `estimated_exposure`
- `estimated_reads`
- `likes`
- `collects`
- `comments`
- `shares`
- `author_followers`
- `author_note_count`
- `author_total_likes_collects`
- `read_exposure_ratio_text`
- `read_follower_ratio_text`
- `collected_at`

去重规则：`huitun_note_key` 和 `published_at` 组成唯一约束。若同一笔记重复采集，更新指标字段和 `collected_at`。

### raw_snapshots

记录排错用原始快照。

字段：

- `id`
- `run_id`
- `kind`
- `object_key`
- `page_url`
- `text_content`
- `html_content`
- `created_at`

## 模块设计

### CLI

`src/cli.ts` 负责解析参数、初始化数据库、启动采集任务、输出采集统计。

### 浏览器连接

`src/browser/huitun-session.ts` 负责连接 Chrome DevTools Protocol，打开或复用浏览器页面，提供导航、等待、截图/DOM 快照等能力。

### 热词搜索采集

`src/browser/hotword-search.ts` 负责热词搜索页操作和热词表格解析。

输出：`HotWordRow[]`。

### 热词详情采集

`src/browser/hotword-detail.ts` 负责打开热词详情页、切换时间范围、解析概览和笔记列表。

输出：`HotWordSnapshot` 和 `NoteListRow[]`。

### 笔记详情采集

`src/browser/note-detail.ts` 负责点击笔记标题、解析弹窗详情、关闭弹窗。

输出：`NoteDetail`。

### 数据库层

`src/db/schema.ts` 创建 SQLite schema。

`src/db/client.ts` 创建数据库连接。

`src/db/repositories.ts` 负责批次、热词、快照和笔记的 upsert。

## 错误处理

采集失败时记录：

- 当前阶段：`search_hotwords`、`open_hotword_detail`、`parse_note_list`、`open_note_detail`、`parse_note_detail`、`save_database`
- 当前对象：关键词、热词或笔记 key
- 错误信息
- 当前页面 URL
- 当前 DOM 文本快照

单条笔记详情失败不终止整个批次，只记录失败并继续下一条。热词详情页打不开时跳过该热词并继续下一个热词。搜索页打不开或数据库初始化失败时终止批次。

## 验证标准

用“浴缸”跑一轮采集，满足以下条件才算完成：

- `collection_runs` 有一条成功或部分成功记录。
- `hot_words` 至少有 5 条热词。
- `hot_word_snapshots` 至少有 1 条热词详情快照。
- `notes` 至少有 10 条笔记。
- 至少 3 条笔记包含详情弹窗字段：作者粉丝数、预估曝光量、分享数或比例字段。
- 重复运行同一关键词不会重复插入同一条笔记。
- 抽查 3 条笔记，SQLite 字段与灰豚页面可见字段一致。

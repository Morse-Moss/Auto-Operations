# 小红书数据抓取双关键词通道设计

## 背景

当前「数据抓取」页已经同时具备两类关键词抓取能力：

1. 通过关键词组批量低频采集，调用现有 `crawlXhsKeywordGroupStream`。
2. 用户手动输入单个搜索关键词，调用现有 `crawlXhsDataStream` 且 `mode="search"`。

问题不在能力缺失，而在入口表达不清。页面默认加载关键词组后会自动进入关键词组模式，用户要手动输入关键词必须先清空关键词组，再选择「通过搜索爬取详情」。这让「手动关键词」通道隐藏在间接操作里，用户容易误以为数据抓取只能从关键词组开始。

## 目标

把「数据抓取」页改成两条明确的主通道：

- **关键词组采集**：从已有关键词组中选择，按关键词数量和每词数量批量采集。
- **手动关键词采集**：用户直接输入一个关键词，设置抓取数量和搜索筛选条件后采集。

目标是降低用户理解成本，让用户进入页面后能立即判断自己应该走哪条路径。

## 非目标

本次不做以下事项：

- 不新增后端接口。
- 不修改 XHS SDK、签名层、详情质量门禁或保存逻辑。
- 不改变现有低频串行抓取策略。
- 不移除原有笔记链接抓取、评论抓取能力；这些能力可以保留为次级入口。
- 不新增数据库字段或迁移。

## 推荐方案

在「数据抓取」表单顶部增加一个明确的采集通道选择控件：

- `关键词组`
- `手动关键词`

交互规则：

1. 如果 URL 带有 `keyword_group_id`，默认进入「关键词组」通道，并选中对应关键词组。
2. 如果 URL 不带 `keyword_group_id`，默认进入「手动关键词」通道。
3. 切换到「手动关键词」通道时，表单不再被已选关键词组劫持，直接显示搜索关键词输入框。
4. 切换到「关键词组」通道时，显示关键词组选择、关键词数、每词最多、高级设置。
5. 提交时按当前通道分发：
   - 关键词组通道调用现有 `crawlXhsKeywordGroupStream`。
   - 手动关键词通道调用现有 `crawlXhsDataStream`，固定使用 `mode="search"`。
6. 原有「笔记链接」「只爬取评论」能力不作为主通道展示，保留在次级入口或原有模式中，避免本次需求扩大。

## 用户体验

页面核心文案从「关键词组一键采集」调整为更中性的「选择采集通道」。用户先选择目标，再填写参数：

- 想批量跑已有词库：选择「关键词组」。
- 临时想到一个词想抓：选择「手动关键词」。

这符合运营工作流：关键词组用于计划内批量采集，手动关键词用于临时探索和验证选题。

## 技术设计

### 前端状态

在 `frontend/src/pages/platforms/xhs/crawler-page.tsx` 中新增通道状态，例如：

- `crawlChannel: "keyword_group" | "manual_keyword"`

初始化逻辑：

- `initialKeywordGroupId ? "keyword_group" : "manual_keyword"`

保留现有 `selectedKeywordGroupId`、`keyword`、`maxNotes`、`filters` 等状态，减少改动范围。

### 模式判断

当前代码使用 `Boolean(selectedKeywordGroupId)` 作为是否关键词组模式的判断。这会导致“只要有选中的关键词组，用户就无法顺畅手动输入关键词”。

需要改成由 `crawlChannel` 决定：

- `isKeywordGroupMode = crawlChannel === "keyword_group"`
- `isManualKeywordMode = crawlChannel === "manual_keyword"`

### 提交流程

`handleRun` 中：

1. 如果 `crawlChannel === "keyword_group"`，执行现有 `handleSimpleRun`。
2. 如果 `crawlChannel === "manual_keyword"`：
   - 校验 PC 账号。
   - 校验 `keyword.trim()`。
   - 调用 `crawlXhsDataStream`，payload 中使用 `mode: "search"`。

### 表单展示

表单顶部展示通道选择。

关键词组通道展示：

- PC 账号
- 关键词组
- 关键词数
- 每词最多
- 同时抓取评论
- 高级设置：Time Sleep、Comment Sleep、排序、类型、时间范围

手动关键词通道展示：

- PC 账号
- 搜索关键词
- 爬取数量
- 排序
- 类型
- 时间范围
- 距离
- Geo
- 同时抓取评论

### 结果展示

沿用现有结果表格、统计、导出 Excel、质量状态、评论状态和错误提示，不改变数据结构。

## 错误处理

- 关键词组通道未选择关键词组：提示「请先选择一个关键词组。」
- 手动关键词通道未输入关键词：提示「请填写搜索关键词。」
- 未选择 PC 账号：沿用「请先选择一个 PC 账号。」
- 抓取失败：沿用现有错误处理。

## 验证方式

1. 运行 `npm --prefix frontend run build`，确认 TypeScript 与 Vite 构建通过。
2. 手动检查页面逻辑：
   - 无 `keyword_group_id` 进入页面时默认手动关键词通道。
   - 带 `keyword_group_id` 进入页面时默认关键词组通道。
   - 切换通道后表单内容符合当前通道，不被已选关键词组误判。
   - 提交按钮在两条通道下都能触发正确校验路径。

## 影响范围

主要影响文件：

- `frontend/src/pages/platforms/xhs/crawler-page.tsx`

预计不影响：

- 后端 API
- 数据库模型
- XHS 底层 SDK/签名层
- 关键词组管理页
- 内容库保存逻辑

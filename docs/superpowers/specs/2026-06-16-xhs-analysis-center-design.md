# 小红书分析中心设计规格

日期：2026-06-16

## 1. 背景与目标

当前主系统已经具备灰豚候选词、小红书关键词组、低频串行采集、内容库、评论入库、草稿工坊、监控目标和基础数据洞察能力。现有 [backend/app/api/platforms/xhs/analytics.py](../../../backend/app/api/platforms/xhs/analytics.py) 与 [frontend/src/pages/platforms/xhs/analytics-page.tsx](../../../frontend/src/pages/platforms/xhs/analytics-page.tsx) 已能展示基础指标，但还不是一个真正可指导运营动作的分析中心。

第一版“小红书分析中心”的目标是跑通一条真实可用的分析闭环：

> 关键词组/笔记范围 → 数据健康检查 → 样本预览排除 → 结构化 AI 分析 → 分析报告快照 → 静态 HTML 导出 → 选题卡编辑 → 草稿骨架。

用户核心问题不是“数据怎么样”，而是：

- 哪些关键词、痛点和内容方向值得继续做？
- 用户真实在问什么、抱怨什么、想买什么？
- 哪些结论来自事实，哪些是 AI 推断？
- 下一批小红书选题应该写什么？
- 哪些选题可以进入草稿工坊继续扩写？

## 2. 参考链路吸收

本设计吸收成熟项目和 skill 的分析链路，但不引入外部工具依赖。

- `lucasygu/redbook`：吸收关键词矩阵、互动信号、机会评分、受众推断、爆款复刻、内容策划等模块化分析思路。
- `XHS_Business_Idea_Validator`：吸收“关键词/业务想法 → 笔记和评论 → 评论痛点 → 综合分析 → HTML 报告”的链路。
- `redbook-analytics` skill：吸收账号诊断报告结构、可执行建议、内容日历、标签策略和“下一步动作”导向。
- `xhs-toolkit`：仅作为后续账号复盘阶段的参考，不进入第一版，不接 Selenium/ChromeDriver，不接创作者中心数据。

第一版只复用主系统已有数据源，不接 `redbook` CLI、不接 `xhs-toolkit`、不接 TikHub、不新增外部小红书采集系统。

## 3. 范围边界

### 3.1 第一版聚焦

第一版聚焦：

- **关键词/选题分析**：基于关键词组、搜索采集结果、互动数据，找内容方向。
- **用户痛点/需求洞察**：基于评论和笔记内容识别问题、抱怨、购买意图、场景需求。

### 3.2 第一版不做

第一版明确不做：

- 完整账号复盘。
- 完整竞品分析。
- 创作者中心数据接入。
- 粉丝画像。
- 发布后增长诊断。
- 行业模板库。
- 独立内容类型分析图表。
- 逐条评论排除。
- 自动定时重跑。
- 交互式 HTML 导出。
- 产品演示假数据或假报告。

### 3.3 轻量对标

第一版允许选择已有 `MonitoringTarget` 中的账号或品牌作为轻量参考样本，但不做完整竞品画像、粉丝结构或增长路径复盘。

## 4. 产品命名

导航继续使用“数据洞察”，页面主标题改为：

> 小红书分析中心

产品层命名：

- 报告：分析报告。
- 卡片：洞察卡。
- 选题：选题卡。
- 证据：证据池。
- 草稿：草稿骨架。

避免把页面命名为“机会分析中心”。后端 API 与类型也应优先使用 `analysis`、`content_analysis`、`insight`、`topic_card`，不使用 `opportunity` 作为主要产品命名。

## 5. 用户工作流

### 5.1 主入口

主入口为现有“数据洞察”页面，升级为“小红书分析中心”。页面包括：

1. 顶部创建入口。
2. 模型状态提示。
3. 轻量数据概览。
4. 历史分析报告列表。
5. 报告详情区域或抽屉。
6. 创建报告三步向导。

### 5.2 关键词组入口

在 [frontend/src/pages/platforms/xhs/keywords-page.tsx](../../../frontend/src/pages/platforms/xhs/keywords-page.tsx) 增加“分析”入口。用户从关键词组页点击后，跳转数据洞察页并带上 `keyword_group_id`，分析中心自动打开创建向导并预选该关键词组。

### 5.3 内容库入口

内容库入口为轻量可选项：用户从内容库勾选笔记后可带 `source_note_ids` 进入分析中心，但仍需要选择或确认关键词组作为分析上下文。第一版优先保证关键词组入口跑通。

## 6. 创建报告三步向导

### Step 1：选择范围

字段：

- 关键词组：必选。
- 笔记范围：默认使用该关键词组命中的已采集笔记。
- 已选内容库笔记：如果从内容库带入，则自动填充。
- 轻量对标目标：可选，来自已有监控目标。
- 报告标题：自动生成，可编辑。

默认标题示例：`AI 编程 - 小红书分析报告 - 2026-06-16`。

### Step 2：数据健康与样本预览

调用健康检查 API，展示：

- 有效笔记数：当前 / 最低 / 标准。
- 评论数：当前 / 最低 / 标准。
- 覆盖关键词数：当前 / 最低 / 标准。
- 代表性/高互动样本数：当前 / 最低 / 标准。
- 参与分析笔记样本。
- 排除/恢复笔记操作。

规则：

- 支持排除笔记。
- 不支持逐条排除评论。
- 被排除笔记的评论也不参与分析。
- 排除后重新计算健康状态。
- 排除后低于最低门槛则不能继续生成。

数据不足时，展示半自动补采集建议：推荐补采关键词、每词建议采集数量、是否建议采评论，并提供跳转采集页或关键词组页的入口。第一版不在分析页面直接启动采集任务。

### Step 3：生成报告确认

展示：

- 关键词组。
- 参与分析笔记数。
- 评论数。
- 排除笔记数。
- 对标目标数。
- 数据健康状态。
- 模型状态。
- 预计输出：轻量 AI 总结、最多 5 张洞察卡、每张洞察卡最多 3 张选题卡、静态 HTML 报告。

用户点击“生成分析报告”后，后端执行结构化分析。

## 7. 数据健康门槛

### 7.1 最低门槛

低于最低门槛时，不生成报告、不调用模型、不生成 HTML。

最低门槛：

- 有效笔记 ≥ 10。
- 评论 ≥ 30。
- 覆盖关键词 ≥ 3。
- 至少 1 篇代表性样本。

低于任一关键项时，只显示数据缺口和补采集建议。

### 7.2 标准阈值

标准阈值：

- 有效笔记 ≥ 30。
- 评论 ≥ 100。
- 覆盖关键词 ≥ 5。
- 至少 3 篇高互动样本。

达到标准阈值时，允许高 / 中 / 低置信度。

### 7.3 最低与标准之间

达到最低门槛但未达标准阈值时：

- 允许生成报告。
- 全局标注“样本未达标准阈值，结论仅供初筛”。
- 所有洞察卡最高置信度只能是 `medium`。
- 不允许出现 `high` 置信度。
- HTML 报告也必须写明样本限制。

### 7.4 高互动样本定义

高互动样本使用混合定义：

- 当前分析样本互动 Top 10%，且互动数 ≥ 50。
- 如果整体样本互动偏低，则至少取 Top 3 作为候选代表性样本，但报告标注“整体互动偏低，高互动样本置信度有限”。

## 8. 系统架构

第一版按四层设计：

1. **数据输入层**：关键词组、笔记、评论、标签/话题、轻量对标目标、排除笔记。
2. **证据计算层**：健康检查、样本筛选、高互动样本识别、评论信号统计、关键词覆盖统计、证据池构造。
3. **AI 分析层**：模型配置检查、基于证据池生成结构化 JSON、Schema 校验、证据 ID 校验、失败门禁。
4. **产品输出层**：分析报告快照、洞察卡、选题卡、HTML 报告、草稿骨架、历史列表和重跑。

核心原则：AI 不能直接决定事实，只能基于后端提供的证据池做推断和建议。

## 9. 后端设计

### 9.1 路由层

新增文件：

- [backend/app/api/platforms/xhs/analysis_center.py](../../../backend/app/api/platforms/xhs/analysis_center.py)

路由挂在 `/xhs/analytics/analysis` 下，避免继续膨胀 [backend/app/api/platforms/xhs/analytics.py](../../../backend/app/api/platforms/xhs/analytics.py)。

API：

- `GET /xhs/analytics/analysis/reports`：历史报告列表。
- `POST /xhs/analytics/analysis/reports`：创建分析报告。
- `GET /xhs/analytics/analysis/reports/{report_id}`：报告详情。
- `POST /xhs/analytics/analysis/reports/{report_id}/rerun`：基于历史配置重跑。
- `POST /xhs/analytics/analysis/reports/{report_id}/topic-cards/{card_id}/drafts`：基于编辑后的选题卡生成草稿骨架。
- `POST /xhs/analytics/analysis/health`：数据健康检查。
- `POST /xhs/analytics/analysis/collection-plan`：生成半自动补采集建议。

### 9.2 服务层

新增文件：

- [backend/app/services/xhs_analysis_center_service.py](../../../backend/app/services/xhs_analysis_center_service.py)

核心职责：

- 解析输入范围。
- 拉取关键词组、笔记、评论、对标目标。
- 执行数据健康检查。
- 构造 evidence pool。
- 计算基础指标。
- 调用模型生成结构化分析。
- 校验模型输出。
- 保存报告快照。
- 生成 HTML。
- 基于选题卡创建草稿骨架。

可拆分 HTML 渲染：

- [backend/app/services/xhs_analysis_report_renderer.py](../../../backend/app/services/xhs_analysis_report_renderer.py)

### 9.3 数据模型

新增模型文件：

- [backend/app/models/analysis_report.py](../../../backend/app/models/analysis_report.py)

表名：`analysis_reports`。

字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | int | 主键 |
| user_id | int | 用户 |
| platform | string | 第一版固定 `xhs` |
| report_type | string | 第一版建议 `content_analysis` |
| status | string | `pending` / `running` / `completed` / `failed` |
| title | string | 报告标题 |
| input_config | JSON | 输入范围、关键词组、排除笔记、对标目标、阈值 |
| data_health | JSON | 数据健康检查结果 |
| evidence_pool | JSON | 证据池快照 |
| result_json | JSON | 模型结构化输出 |
| html_file_path | text | 静态 HTML 文件路径 |
| source_task_id | int/null | 预留异步任务 |
| rerun_from_report_id | int/null | 来源报告 |
| error_message | text/null | 失败原因 |
| created_at | datetime | 创建时间 |
| started_at | datetime/null | 开始时间 |
| finished_at | datetime/null | 完成时间 |

保存 `evidence_pool` 是硬要求：报告必须能复盘当时依据，不能依赖当前数据库状态重新解释历史报告。

## 10. 关键 JSON 结构

### 10.1 input_config

```json
{
  "keyword_group_id": 12,
  "keyword_group_name": "AI 编程",
  "keywords": ["AI编程", "Claude Code", "Cursor"],
  "source_note_ids": [1, 2, 3],
  "excluded_note_ids": [8, 13],
  "benchmark_target_ids": [5],
  "thresholds": {
    "minimum": {
      "valid_notes": 10,
      "comments": 30,
      "keyword_coverage": 3,
      "representative_notes": 1
    },
    "standard": {
      "valid_notes": 30,
      "comments": 100,
      "keyword_coverage": 5,
      "high_engagement_notes": 3
    }
  },
  "topic_cards_per_insight": 3,
  "max_insight_cards": 5
}
```

### 10.2 data_health

```json
{
  "status": "standard",
  "can_generate": true,
  "confidence_cap": "high",
  "metrics": {
    "valid_note_count": 36,
    "comment_count": 142,
    "covered_keyword_count": 6,
    "representative_note_count": 4,
    "high_engagement_note_count": 3
  },
  "missing": [],
  "warnings": ["部分关键词评论样本偏少"],
  "collection_plan": {
    "needed": false,
    "recommended_keywords": [],
    "recommended_notes_per_keyword": 0,
    "should_collect_comments": false
  }
}
```

### 10.3 evidence_pool

```json
{
  "notes": [
    {
      "evidence_id": "note:123",
      "note_id": 123,
      "title": "普通人怎么用 Claude Code 提效",
      "author_name": "示例作者",
      "likes": 520,
      "collects": 310,
      "comments": 48,
      "shares": 20,
      "engagement": 898,
      "matched_keywords": ["Claude Code", "AI编程"],
      "excerpt": "我把 Claude Code 从安装到第一个自动化任务的步骤整理成清单。"
    }
  ],
  "comments": [
    {
      "evidence_id": "comment:456",
      "comment_id": 456,
      "note_id": 123,
      "content": "新手完全不会配置，有没有保姆级教程？",
      "like_count": 18,
      "signals": ["question", "beginner_need"]
    }
  ],
  "keywords": [
    {
      "evidence_id": "keyword:Claude Code",
      "keyword": "Claude Code",
      "matched_notes": 12,
      "matched_comments": 35
    }
  ],
  "metrics": [
    {
      "evidence_id": "metric:question_rate",
      "name": "question_rate",
      "value": 0.31,
      "description": "评论中提问评论占比"
    }
  ],
  "benchmarks": [
    {
      "evidence_id": "benchmark:5",
      "target_id": 5,
      "name": "某对标账号",
      "matched_notes": 4
    }
  ]
}
```

### 10.4 result_json

```json
{
  "summary": {
    "facts": [
      {
        "id": "fact_1",
        "text": "评论中有 31% 是提问类内容。",
        "evidence_ids": ["metric:question_rate"]
      }
    ],
    "inferences": [
      {
        "id": "inference_1",
        "text": "用户更缺少入门级步骤，而不是工具概念介绍。",
        "evidence_ids": ["metric:question_rate", "comment:456"]
      }
    ],
    "recommendations": [
      {
        "id": "recommendation_1",
        "text": "优先制作保姆级教程和清单型内容。",
        "evidence_ids": ["comment:456", "note:123"]
      }
    ]
  },
  "insight_cards": [
    {
      "id": "insight_1",
      "title": "新手配置门槛是高频痛点",
      "score": 86,
      "sub_scores": {
        "traffic_potential": 78,
        "demand_strength": 92,
        "competition_pressure": 65,
        "actionability": 88
      },
      "confidence": "medium",
      "confidence_reason": "提问评论集中在配置门槛，但样本未达标准阈值。",
      "facts": [],
      "inferences": [],
      "recommendations": [],
      "evidence_ids": ["note:123", "comment:456", "metric:question_rate"],
      "topic_card_ids": ["topic_1", "topic_2", "topic_3"]
    }
  ],
  "topic_cards": [
    {
      "id": "topic_1",
      "insight_id": "insight_1",
      "title_direction": "Claude Code 新手从 0 到能用的配置清单",
      "target_pain": "新手不知道如何安装、配置和开始第一个任务。",
      "content_angle": "保姆级教程，降低入门门槛。",
      "recommended_structure": ["适合谁", "准备什么", "安装配置步骤", "第一个可复制任务", "常见坑"],
      "recommended_content_form": ["教程型", "清单型"],
      "tags": ["ClaudeCode", "AI编程", "效率工具"],
      "cover_suggestion": "大字标题：第一次用 Claude Code，照着做就能跑",
      "expected_advantage": "评论中有明确新手问题，教程型内容更容易获得收藏。",
      "risk_warning": "不要写成泛泛工具介绍，要给可复制步骤。",
      "evidence_ids": ["comment:456", "note:123"]
    }
  ],
  "report_warnings": []
}
```

## 11. AI 分析链路

1. 检查模型配置：无可用文本模型则不生成。
2. 执行数据健康检查：低于最低门槛不调用模型。
3. 构造 evidence pool：只来自真实数据库和后端确定性指标。
4. 构造模型输入：包含任务说明、健康状态、分析范围、证据池、Schema 和质量规则。
5. 模型输出结构化 JSON：不接受 Markdown 或自由文本。
6. 后端校验：Schema、证据 ID、置信度、数量限制、事实/推断/建议结构。
7. 保存 completed 或 failed 报告快照。

## 12. Prompt 设计原则

Prompt 需要包含硬规则：

```text
你是小红书内容分析助手。你只能基于输入 evidence_pool 中的证据做分析。
任何事实结论都必须引用 evidence_id。
不要编造数据、评论、笔记、用户反馈、行业基准或报告结论。
如果证据不足，少输出或降低置信度，不要补全。
输出必须是符合 JSON Schema 的 JSON，不要 Markdown。
必须区分 facts、inferences、recommendations。
```

禁止：

- 引用 evidence_pool 之外的证据。
- 使用“很多用户”“大量评论”等模糊表述，除非有对应 metric evidence。
- 编造具体数字。
- 编造不存在的评论原文。
- 编造不存在的笔记标题。
- 把推断写成事实。
- 在 `data_health.status = minimum` 时输出 `high` confidence。

## 13. 校验与失败门禁

### 13.1 必须失败的情况

模型前失败：

- 未配置模型。
- 数据低于最低门槛。
- 没有关键词组或分析范围。
- 无有效笔记。
- 无有效评论。

模型输出失败：

- 输出不是 JSON。
- JSON 不符合 Schema。
- 字段缺失。
- 洞察卡超过 5 个。
- 选题卡超过限制。
- 分数非法。
- 置信度非法。
- `minimum` 数据输出了 `high`。
- `evidence_id` 不存在。
- 洞察卡没有最低证据。
- facts 没有证据。
- 选题卡没有证据。

文件生成失败：

- HTML 写入失败。
- 导出路径生成失败。

### 13.2 失败处理

失败后：

- 保存 `status = failed`。
- 保存 `input_config`、`data_health`、`evidence_pool` 和 `error_message`。
- 不显示半成品 AI 文本。
- 不生成正式 HTML。
- 支持重试或基于历史配置重跑。

## 14. 评分设计

每张洞察卡包含：

- 综合分：0-100。
- 流量潜力：0-100。
- 需求强度：0-100。
- 竞争压力：0-100。
- 可执行性：0-100。

第一版采用“后端指标 + AI 解释”的混合方式。后端先计算总互动、平均互动、收藏/赞比、评论提问率、购买意图词命中、痛点词命中、关键词覆盖、高互动样本数、同质标题/内容重复信号。AI 输出分数和解释，但必须基于后端指标和证据。

如果后续发现评分漂移，再将更多评分逻辑收回后端确定性计算。

## 15. 评论信号

第一版评论主轴是需求，不是情绪。

后端基础信号：

- `question`：提问。
- `price_intent`：价格/多少钱。
- `purchase_intent`：怎么买/链接/店铺。
- `suitability`：适不适合/能不能用。
- `comparison`：A 和 B 哪个好。
- `complaint`：吐槽/踩坑/不好用。
- `beginner_need`：新手/小白/入门。
- `scenario`：场景词。

情绪只作为辅助标签：`positive`、`neutral`、`negative`。不做情绪比例大图，不作为核心结论主轴。

## 16. HTML 报告

HTML 报告是静态文件，内容来自已校验的 `result_json` 和 `evidence_pool`。

保存路径复用 `storage_dir / exports`，文件名类似：

`xhs-analysis-report-u{user_id}-{uuid}.html`

HTML 包含：

1. 报告标题。
2. 生成时间。
3. 关键词组和输入范围。
4. 数据健康状态。
5. 样本限制说明。
6. 核心总结：事实、推断、建议。
7. Top 5 洞察卡。
8. 每张洞察卡的子分与置信度。
9. 代表性证据。
10. 选题卡。
11. 风险提醒。
12. 免责声明：报告基于当前已采集数据生成，未采集到的数据不会被推断为事实，样本不足时结论仅供初筛。

HTML 不包含交互逻辑。系统页面负责交互，HTML 负责复盘和分享。

## 17. 草稿骨架生成

用户编辑/勾选选题卡后，调用生成草稿接口。

草稿保存到现有 `AiDraft`，不新建分析草稿表。

草稿内容包含：

- 标题方向或候选标题。
- 正文结构大纲。
- 推荐标签。
- 封面建议。
- 目标用户痛点。
- 参考证据摘要。
- 风险提醒/避免写法。

草稿不直接生成完整正文。分析模块负责“值得写什么”，草稿工坊负责“写成可发布内容”。

## 18. 前端类型与 API 客户端

更新 [frontend/src/types/index.ts](../../../frontend/src/types/index.ts)，新增类型：

- `AnalysisReport`
- `AnalysisReportStatus`
- `AnalysisDataHealth`
- `AnalysisEvidencePool`
- `InsightCard`
- `TopicCard`
- `CreateAnalysisReportPayload`
- `AnalysisHealthPayload`
- `CreateDraftFromTopicCardsPayload`

更新 [frontend/src/lib/api.ts](../../../frontend/src/lib/api.ts)，新增函数：

- `fetchXhsAnalysisReports`
- `createXhsAnalysisReport`
- `fetchXhsAnalysisReport`
- `rerunXhsAnalysisReport`
- `checkXhsAnalysisHealth`
- `createXhsAnalysisDrafts`
- `createXhsAnalysisCollectionPlan`

## 19. 测试策略

产品功能中不允许演示假数据、假报告或伪指标。

自动化测试可以使用隔离的测试 fixture，但 fixture 必须只存在于测试代码中，不进入产品 UI、不生成给用户的报告、不作为真实数据展示。

### 19.1 后端测试

新增 `tests/backend/test_xhs_analysis_center.py`，覆盖：

1. 健康检查：
   - 低于最低门槛 → `can_generate=false`。
   - minimum → `confidence_cap=medium`。
   - standard → `confidence_cap=high`。

2. 报告创建：
   - 无模型配置 → 失败。
   - 低于最低门槛 → 不调用模型。
   - 模型合法输出 → completed。
   - 模型非法 JSON → failed。
   - evidence_id 不存在 → failed。
   - minimum 状态输出 high → failed。

3. 报告权限：
   - 用户不能读取他人报告。

4. HTML：
   - completed 生成 HTML。
   - failed 不生成正式 HTML。

5. 草稿：
   - 选题卡生成草稿骨架。
   - 草稿包含标题、大纲、标签、封面建议、证据摘要、风险提醒。

### 19.2 前端验证

- `npm run build` in [frontend/](../../../frontend/)。
- 页面能正常加载。
- 向导能走通。
- 报告列表/详情能展示。
- failed 状态能展示错误。
- 选题卡编辑后可生成草稿。

### 19.3 端到端手动验收

用真实已有数据验证：

1. 选择一个已采集关键词组。
2. 健康检查达最低门槛。
3. 排除一条笔记后健康状态刷新。
4. 生成报告。
5. 查看洞察卡和证据。
6. 编辑选题卡。
7. 生成草稿骨架。
8. 下载 HTML。
9. 重跑报告。

## 20. 里程碑

### Milestone 1：后端报告骨架

完成：

- `analysis_reports` 表。
- 报告 CRUD。
- 健康检查。
- 报告列表/详情 API。

### Milestone 2：证据池 + AI 结构化分析

完成：

- evidence pool。
- prompt。
- JSON Schema。
- 模型调用。
- 校验失败门禁。
- `result_json` 保存。

### Milestone 3：HTML + 草稿骨架

完成：

- 静态 HTML 生成。
- HTML 下载。
- 选题卡编辑后生成草稿骨架。

### Milestone 4：前端分析中心

完成：

- 页面主标题和结构重构。
- 三步向导。
- 历史报告列表。
- 报告详情。
- 证据折叠。
- 选题卡编辑。
- failed 状态展示。

### Milestone 5：关键词组入口 + 半自动补采集

完成：

- 关键词组页分析入口。
- URL 参数带入。
- 数据不足时生成补采集计划。
- 跳转采集页/关键词组页预填。

## 21. 第一版完成定义

第一版完成必须满足：

- 能从关键词组进入小红书分析中心。
- 能检查真实数据是否足够。
- 低于最低门槛不生成。
- 没模型不生成。
- AI 输出结构化 JSON。
- Schema 和 evidence 校验生效。
- 能保存历史报告。
- 能展示 completed/failed 报告。
- 能下载静态 HTML。
- 能编辑选题卡。
- 能生成草稿骨架。
- 能基于历史报告重跑。
- 不使用外部小红书工具。
- 不使用产品假数据。
- 不输出伪报告。

## 22. 风险与处理

### 风险 1：现有评论数据不足

处理：健康检查明确提示，生成半自动补采集建议，不强行生成报告。

### 风险 2：模型输出不稳定

处理：JSON Schema、evidence_id 校验、有限重试、失败状态可见。

### 风险 3：前端一次性改太大

处理：保留现有数据洞察 API，重构页面但不删除旧能力，优先跑通创建报告和详情，旧指标作为辅助概览。

### 风险 4：报告质量泛

处理：强制 facts / inferences / recommendations，强制证据，强制选题卡可执行字段，低证据限制置信度。

### 风险 5：范围膨胀

处理：A/C 后置，行业模板后置，创作者中心后置，完整竞品分析后置，自动定时重跑后置。

## 23. 质量红线

1. 宁愿失败，不伪造数据。
2. 宁愿失败，不伪造报告。
3. 事实必须有证据。
4. AI 推断必须标成推断。
5. 建议必须可执行。
6. 数据不足不强行分析。
7. Schema 不过不展示。
8. 证据 ID 不存在不展示。
9. 第一版先跑通，不做大而全。

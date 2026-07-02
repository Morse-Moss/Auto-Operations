# 小红书草稿工坊布局改版设计

## 背景

当前小红书草稿工坊基于共享草稿壳实现，页面主结构是三栏：来源面板、草稿编辑器、AI 助手。这个结构的问题是：

- 来源面板作为左侧主列，占用了过高视觉优先级，但来源信息对草稿工坊只是上下文，不是用户当前主要任务。
- 草稿编辑器在三栏布局下宽度不足，正文编辑空间被压缩。
- 系统评分、AI 改写、标题生成、标签生成、图片工坊入口、发布中心入口混在右侧 AI 助手里，用户无法快速判断当前是在“诊断草稿”还是“生成候选”。

本次改版只调整前端信息架构和布局，不改变现有后端 API、不改变 AI 打分/改写/标题标签生成/图片工坊/发布中心的业务语义。

## 目标

1. 将来源信息从主板块降级为顶部横向可折叠上下文条。
2. 将草稿编辑器恢复为页面主工作区，扩大编辑空间。
3. 将“系统评分”和“AI 改写”拆成右侧两个主 Tab，避免操作混杂。
4. 将“送入图片工坊”和“送发布中心”从 AI 改写操作区移出，作为草稿生命周期的下一步动作。
5. 保持微信等其他平台草稿工坊不受影响。

## 非目标

- 不改造后端打分、改写、标题生成、标签生成接口。
- 不新增草稿数据表或迁移。
- 不改变 AI 改写“生成候选后人工采纳”的安全机制。
- 不改造图片工坊或发布中心页面。
- 不重构 XHS SDK、签名、采集层。

## 当前结构

主要文件：

- `frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx`
  - 小红书草稿工坊页面。
  - 管理来源笔记、图片素材、AI 打分、AI 改写、标题标签候选、图片工坊跳转、发布中心跳转。
- `frontend/src/components/draft-workbench/draft-workbench-shell.tsx`
  - 共享草稿工坊壳。
  - 当前硬编码支持 `renderSourcePanel` 左侧来源列、编辑器中列、`renderAssistantExtras` 右侧助手列。
- `frontend/src/components/draft-workbench/draft-workbench-types.ts`
  - 共享草稿壳 adapter/controller 类型。

当前有来源面板时布局为：

```text
来源面板 6 / 草稿编辑器 12 / AI 助手 6
```

目标布局为：

```text
顶部：当前草稿条
顶部：来源摘要折叠条
主体：草稿编辑器 16 / 右侧主工作区 8
```

## 目标体验

页面默认状态：

```text
草稿工坊标题

[当前草稿：草稿名 / 草稿数 / 切换草稿]
[来源摘要：来源标题 · 图文/视频 · 素材 N 项 · 查看原文 · 展开]

┌──────────────────────────────┬────────────────────────┐
│ 草稿编辑器                    │ 草稿优化                │
│ - 草稿名                      │ [系统评分] [AI 改写]    │
│ - 标题                        │                        │
│ - 正文                        │ 系统评分 Tab：           │
│ - 标签                        │ - 保存并打分             │
│ - 草稿图片素材                │ - 总分/维度/风险/建议    │
│ - 基础操作                    │                        │
│ - 下一步动作                  │ AI 改写 Tab：            │
│                              │ - 模式/指令/高级设置     │
│                              │ - 生成改写/标题/标签     │
│                              │ - 候选结果/采纳/放弃     │
└──────────────────────────────┴────────────────────────┘
```

## 设计方案

### 1. 来源信息：顶部横向可折叠上下文条

小红书页面不再把来源信息传给共享壳的左侧 `renderSourcePanel`。改为使用新的顶部上下文插槽渲染来源摘要。

默认收起状态显示：

- 来源笔记标题。
- 图文/视频类型。
- 素材数量。
- “查看原文”按钮。
- “展开来源”按钮。

展开后显示：

- 来源正文摘要，保留可展开能力。
- 来源状态标签，例如“来源草稿已独立化”。
- 来源素材缩略图预览，复用现有 `renderDraftSourceAssetPreview` 的视觉逻辑。

无来源草稿：

- 不渲染大面积空来源卡片。
- 可以隐藏来源条，或只显示一行轻量提示：“当前草稿无来源笔记”。推荐隐藏，减少视觉噪音。

### 2. 共享草稿壳：新增顶部上下文与主操作插槽

在 `DraftWorkbenchShell` 中新增两个可选插槽：

```ts
renderContextPanel?: (draft: TDraft) => ReactNode;
renderPrimaryActions?: (draft: TDraft) => ReactNode;
```

用途：

- `renderContextPanel`：渲染编辑区上方、当前草稿条下方的上下文信息。小红书用于来源摘要折叠条。
- `renderPrimaryActions`：渲染编辑器底部的业务主操作。小红书用于“送入图片工坊”和“送发布中心”。

兼容策略：

- 保留现有 `renderSourcePanel`，默认行为不变。
- 如果页面继续传 `renderSourcePanel`，仍按当前左侧来源列渲染。
- 小红书页面改为不传 `renderSourcePanel`，改传 `renderContextPanel`。
- 微信草稿工坊等其他页面不需要同步修改。

### 3. 主体布局：三栏降为两栏

共享壳布局调整规则：

- 如果存在 `renderSourcePanel`：继续使用旧三栏布局，兼容旧页面。
- 如果不存在 `renderSourcePanel`：使用两栏布局。
  - 编辑器：`lg=16`
  - 右侧主工作区：`lg=8`

小红书页面将不再使用左侧来源列，因此进入两栏布局。

用户影响：正文编辑面积增加，来源上下文仍可查看，但不抢主任务位置。

### 4. 右侧主工作区：系统评分 / AI 改写两个主 Tab

小红书的 `renderAssistantExtras` 改为渲染 `Tabs`。

#### 系统评分 Tab

只包含评分诊断相关内容：

- “保存并打分”按钮。
- 最近一次评分 loading 状态。
- 总分、等级、summary。
- 维度分、风险、建议、机会标签、disclaimer。

复用现有：

- `fetchLatestDraftAiScore`
- `scoreDraftWithAi`
- `renderDraftScore`
- `handleScoreDraft`

不放入：

- AI 改写模式。
- 标题候选。
- 标签候选。
- 送图片工坊。
- 送发布中心。

#### AI 改写 Tab

只包含生成候选和采纳相关内容：

- 改写模式：安全改写 / 轻度润色 / 种草增强。
- 改写指令输入。
- 高级设置：角色提示词，默认折叠。
- 生成改写。
- 生成标题。
- 生成标签。
- 标题候选。
- 标签候选。
- 改写候选结果。
- 采纳 / 放弃。

复用现有：

- `rewriteDraftWithAi`
- `generateTitleOptions`
- `generateTagOptions`
- `REWRITE_TEMPLATES`
- `rewriteCandidates`
- `handleRewrite`
- `handleAdoptRewriteCandidate`
- `handleDiscardRewriteCandidate`
- `handleGenerateTitles`
- `handleGenerateTags`

保留安全语义：AI 改写结果仍是候选，不直接覆盖中间编辑区；必须点击“采纳”才写入当前编辑状态，再由用户保存。

### 5. 草稿生命周期动作：移到编辑器底部

“送入图片工坊”和“送发布中心”不再放在 AI 改写 Tab 内。

它们应通过 `renderPrimaryActions` 渲染到草稿编辑器底部，和保存/复制/删除处于同一操作区域，但视觉上分组为“下一步”。

建议文案：

```text
下一步：[送入图片工坊] [送发布中心]
```

原因：

- 图片工坊和发布中心是草稿流转动作，不属于 AI 改写动作。
- 用户编辑完成后，在编辑器底部自然寻找下一步，而不是去 AI 面板中寻找发布入口。

### 6. 错误与空状态

保留现有错误反馈方式：

- 业务失败继续使用 `antMessage.error`。
- 页面级加载失败继续使用 `controller.error`。
- 无草稿时右侧显示空状态。

新增布局下的空状态规则：

- 没有来源笔记：隐藏来源上下文条。
- 没有评分结果：评分 Tab 显示现有“暂无系统打分，保存草稿后可开始打分”。
- 没有改写候选：AI 改写 Tab 显示现有候选空状态。

## 实施边界

预计修改文件：

1. `frontend/src/components/draft-workbench/draft-workbench-types.ts`
   - 为 shell props/controller 类型增加新插槽类型，或仅在 shell props 中定义。

2. `frontend/src/components/draft-workbench/draft-workbench-shell.tsx`
   - 新增 `renderContextPanel`、`renderPrimaryActions` props。
   - 在当前草稿条下方渲染顶部上下文。
   - 根据是否存在 `renderSourcePanel` 决定三栏或两栏布局。
   - 在编辑器底部基础操作后渲染 `renderPrimaryActions`。

3. `frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx`
   - 不再传 `renderSourcePanel`。
   - 新增来源摘要折叠条渲染函数。
   - 将右侧 `renderAssistantExtras` 重组为 `Tabs`。
   - 将图片工坊和发布中心按钮移到 `renderPrimaryActions`。

不修改：

- 后端 API。
- AI 服务逻辑。
- 数据模型。
- Alembic 迁移。
- XHS SDK/签名层。

## 验证标准

手动验收：

1. 打开小红书草稿工坊。
2. 来源信息不再占左侧主列。
3. 有来源草稿时，当前草稿条下方显示一条横向来源摘要；点击可展开详情。
4. 草稿编辑器宽度大于旧版三栏布局。
5. 右侧主工作区显示“系统评分 / AI 改写”两个 Tab。
6. 系统评分 Tab 中只出现评分相关信息和“保存并打分”。
7. AI 改写 Tab 中只出现改写、标题生成、标签生成、候选采纳相关能力。
8. “送入图片工坊”和“送发布中心”出现在编辑器底部的下一步区域。
9. AI 改写生成候选后不会直接覆盖编辑器；点击采纳后才写入编辑状态。
10. 无来源草稿不会出现大面积空来源面板。

自动验证：

- 运行前端构建或项目现有前端检查命令。
- 如果项目没有专门的前端单测覆盖该页面，至少运行 `frontend` 构建，确认 TypeScript 和 Vite 编译通过。

## 风险与控制

### 风险 1：共享壳改动影响其他平台

控制：保留 `renderSourcePanel` 的旧行为；小红书使用新插槽，其他平台不改调用方式。

### 风险 2：右侧 Tab 中状态丢失

控制：只移动 JSX 结构，不改变 `useState` 和 handler 语义；`rewriteCandidates`、`draftAiScore` 等状态继续留在小红书页面组件中。

### 风险 3：操作入口移动后用户找不到发布按钮

控制：在编辑器底部用“下一步”明确分组，按钮文案保持“送入图片工坊”和“送发布中心”。

## 完成定义

本次改版完成必须同时满足：

- 小红书草稿工坊完成两栏布局。
- 来源信息完成顶部折叠化。
- 系统评分和 AI 改写完成 Tab 化隔离。
- 图片工坊和发布中心入口移动到编辑器底部下一步动作区。
- 其他平台草稿工坊无行为变化。
- 前端构建或等效验证通过，若失败需明确报告失败原因。

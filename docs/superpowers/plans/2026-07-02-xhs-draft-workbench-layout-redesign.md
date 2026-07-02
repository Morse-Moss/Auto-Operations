# XHS Draft Workbench Layout Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the 小红书草稿工坊 layout so source context is a top collapsible strip, the main body is a two-column editor/assistant layout, system scoring and AI rewrite are separated into right-side tabs, and image-studio/publish actions become editor-bottom next-step actions.

**Architecture:** Keep the shared draft workbench shell backward-compatible by adding optional top-context and primary-action slots while preserving the existing side source panel behavior. Refactor only the XHS page JSX composition: move source rendering into the new context slot, split assistant extras into Ant Design tabs, and move lifecycle actions into the new primary actions slot. Existing state, handlers, API calls, and rewrite-candidate safety semantics stay unchanged.

**Tech Stack:** React 19, TypeScript 5.9, Vite 7, Ant Design 6, React Router, existing frontend API client.

---

## Repository and Safety Notes

- Current root workspace is `E:\小红书` on branch `master`.
- There are existing unrelated modified/untracked files in the workspace. Do not format or rewrite unrelated files.
- Project rule overrides generic plan guidance: do not commit unless the user explicitly asks. Each task ends with a git status checkpoint instead of a commit.
- The frontend has no configured test runner in `frontend/package.json`; validation is `npm run build` from `frontend/` plus manual QA.

## File Structure

### Modify: `frontend/src/components/draft-workbench/draft-workbench-shell.tsx`

Responsibility: shared page shell for platform draft workbenches.

Changes:

- Add optional props:
  - `renderContextPanel?: (draft: TDraft) => ReactNode`
  - `renderPrimaryActions?: (draft: TDraft) => ReactNode`
- Render `renderContextPanel` directly under the current-draft card when a draft is selected.
- Keep old `renderSourcePanel` left-column behavior for compatibility.
- Use two-column `lg=16/8` layout when no side source panel exists.
- Use old three-column `lg=6/12/6` layout when a side source panel exists.
- Render `renderPrimaryActions` after built-in editor actions.

### Modify: `frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx`

Responsibility: XHS-specific draft workbench features.

Changes:

- Import `Tabs` from Ant Design and one icon for the collapsible source strip if desired.
- Add a helper renderer for the compact top source strip.
- Stop passing `renderSourcePanel` to `DraftWorkbenchShell`.
- Pass source strip through `renderContextPanel`.
- Pass image-studio and publish buttons through `renderPrimaryActions`.
- Replace one long assistant `Space` with `Tabs` containing:
  - `score`: system score panel only.
  - `rewrite`: rewrite/title/tag/candidate panel only.

### No changes

- Backend API files.
- SQLAlchemy models and migrations.
- `apis/`, `xhs_utils/`, `static/` XHS SDK/signature layers.
- Existing rewrite-candidate helper modules.

---

## Task 1: Extend the Shared Draft Workbench Shell Slots

**Files:**

- Modify: `frontend/src/components/draft-workbench/draft-workbench-shell.tsx`

- [ ] **Step 1: Inspect current shell props and layout**

Open `frontend/src/components/draft-workbench/draft-workbench-shell.tsx` and confirm these existing lines are still present before editing:

```tsx
export type DraftWorkbenchShellProps<TDraft extends DraftWorkbenchDraft> = {
  adapter: DraftWorkbenchAdapter<TDraft>;
  controller: DraftWorkbenchController<TDraft>;
  renderSourcePanel?: (draft: TDraft) => ReactNode;
  renderEditorExtras?: (draft: TDraft) => ReactNode;
  renderAssistantExtras?: (draft: TDraft) => ReactNode;
};
```

Expected: the shell still has only `renderSourcePanel`, `renderEditorExtras`, and `renderAssistantExtras` extension slots.

- [ ] **Step 2: Add the two optional shell slots**

Change the props type to:

```tsx
export type DraftWorkbenchShellProps<TDraft extends DraftWorkbenchDraft> = {
  adapter: DraftWorkbenchAdapter<TDraft>;
  controller: DraftWorkbenchController<TDraft>;
  renderSourcePanel?: (draft: TDraft) => ReactNode;
  renderContextPanel?: (draft: TDraft) => ReactNode;
  renderEditorExtras?: (draft: TDraft) => ReactNode;
  renderPrimaryActions?: (draft: TDraft) => ReactNode;
  renderAssistantExtras?: (draft: TDraft) => ReactNode;
};
```

Then update the function parameter destructuring to:

```tsx
export function DraftWorkbenchShell<TDraft extends DraftWorkbenchDraft>({
  adapter,
  controller,
  renderSourcePanel,
  renderContextPanel,
  renderEditorExtras,
  renderPrimaryActions,
  renderAssistantExtras,
}: DraftWorkbenchShellProps<TDraft>) {
```

- [ ] **Step 3: Render the context panel below the current-draft card**

Immediately after the current-draft card closes and before `<Row gutter={[16, 16]} align="stretch">`, insert:

```tsx
        {selectedDraft && renderContextPanel ? <div>{renderContextPanel(selectedDraft)}</div> : null}
```

The surrounding section should become:

```tsx
        <Card size="small" styles={{ body: { padding: 12 } }}>
          <Space direction="vertical" size={12} style={{ width: "100%" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
              <Space direction="vertical" size={2} style={{ minWidth: 0 }}>
                <Text type="secondary" style={{ fontSize: 12 }}>当前草稿</Text>
                <Text strong ellipsis style={{ maxWidth: 520 }}>{selectedDraftName}</Text>
              </Space>
              <Space wrap>
                <Text type="secondary">共 {controller.drafts.length} 个草稿</Text>
                <Button onClick={() => setIsDraftListOpen((open) => !open)}>
                  {isDraftListOpen ? "收起草稿" : "切换草稿"}
                </Button>
              </Space>
            </div>
            {isDraftListOpen ? <div>{renderDraftList()}</div> : null}
          </Space>
        </Card>

        {selectedDraft && renderContextPanel ? <div>{renderContextPanel(selectedDraft)}</div> : null}

        <Row gutter={[16, 16]} align="stretch">
```

- [ ] **Step 4: Keep source-panel compatibility and widen assistant column when no side source exists**

Find the editor and assistant columns:

```tsx
          <Col xs={24} lg={hasSourcePanel ? 12 : 16}>
```

and:

```tsx
          <Col xs={24} lg={6}>
```

Keep the editor line as-is. Change the assistant column to:

```tsx
          <Col xs={24} lg={hasSourcePanel ? 6 : 8}>
```

This preserves old `6/12/6` when `renderSourcePanel` exists and creates `16/8` when no side source panel exists.

- [ ] **Step 5: Render primary actions after built-in editor actions**

Find the built-in editor action `Space` ending after save/copy/delete/dry-run buttons:

```tsx
                  <Space wrap>
                    <Button type="primary" icon={<SaveOutlined />} onClick={() => void controller.saveSelectedDraft()} loading={controller.isLoading}>
                      保存
                    </Button>
                    {canDuplicate ? (
                      <Button icon={<CopyOutlined />} onClick={() => void controller.duplicateSelectedDraft()} loading={controller.isLoading}>
                        复制
                      </Button>
                    ) : null}
                    {canDelete ? (
                      <Button danger icon={<DeleteOutlined />} onClick={() => void controller.deleteSelectedDraft()} loading={controller.isLoading}>
                        删除
                      </Button>
                    ) : null}
                    {canDryRun ? (
                      <Button icon={<ReloadOutlined />} onClick={() => void controller.dryRunSelectedDraft({})} loading={controller.isLoading}>
                        Dry-run
                      </Button>
                    ) : null}
                  </Space>
```

Add the new primary-action renderer immediately after it:

```tsx
                  {renderPrimaryActions ? <div>{renderPrimaryActions(selectedDraft)}</div> : null}
```

- [ ] **Step 6: Run TypeScript build to catch shell type errors**

Run from `frontend/`:

```bash
npm run build
```

Expected: either build passes, or any failure is unrelated to this shell edit. If it fails on `DraftWorkbenchShellProps`, fix the prop names until TypeScript accepts `renderContextPanel` and `renderPrimaryActions`.

- [ ] **Step 7: Check changed files**

Run from repo root:

```bash
git status --short -- frontend/src/components/draft-workbench/draft-workbench-shell.tsx
```

Expected: only `frontend/src/components/draft-workbench/draft-workbench-shell.tsx` is listed for this task.

---

## Task 2: Add the XHS Top Source Context Strip

**Files:**

- Modify: `frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx`

- [ ] **Step 1: Add needed Ant Design imports**

At the top of `frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx`, change the Ant Design import from:

```tsx
import { Alert, Button, Card, Collapse, Empty, Input, Modal, Progress, Select, Space, Tag, Typography, Upload, message as antMessage } from "antd";
```

to:

```tsx
import { Alert, Button, Card, Collapse, Empty, Input, Modal, Progress, Select, Space, Tag, Tabs, Typography, Upload, message as antMessage } from "antd";
```

No icon import is required for the source strip; use the existing `LinkOutlined` for “查看原文”.

- [ ] **Step 2: Add a compact source context renderer**

Add this helper after `renderDraftSourceAssetPreview` and before `export function XhsDraftsPage()`:

```tsx
function renderSourceContextStrip(note: SavedNote | null, draftAssets: DraftAsset[]) {
  if (!note) return null;
  const hasVideo = draftAssets.some((asset) => asset.asset_type === "video");

  return (
    <Collapse
      size="small"
      ghost
      items={[
        {
          key: "source-context",
          label: (
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap", width: "100%" }}>
              <Space size={8} wrap>
                <Text type="secondary">来源</Text>
                <Text strong ellipsis style={{ maxWidth: 520 }}>{note.title || "未命名来源"}</Text>
                <Tag color={hasVideo ? "purple" : "green"}>{hasVideo ? "视频" : "图文"}</Tag>
                <Text type="secondary">素材 {draftAssets.length} 项</Text>
              </Space>
              <a href={getNoteUrl(note)} target="_blank" rel="noreferrer" onClick={(event) => event.stopPropagation()}>
                <Button type="link" size="small" icon={<LinkOutlined />}>查看原文</Button>
              </a>
            </div>
          ),
          children: (
            <Card size="small" styles={{ body: { padding: 12 } }}>
              <Space direction="vertical" size={10} style={{ width: "100%" }}>
                <Paragraph ellipsis={{ rows: 3, expandable: true, symbol: "展开" }} type="secondary" style={{ marginBottom: 0 }}>
                  {note.content}
                </Paragraph>
                <Space size={4} wrap>
                  <Tag color="blue">来源草稿已独立化</Tag>
                  <Tag color={hasVideo ? "purple" : "green"}>{hasVideo ? "视频" : "图文"}</Tag>
                  <Text type="secondary">素材 {draftAssets.length} 项</Text>
                </Space>
                {renderDraftSourceAssetPreview(draftAssets)}
              </Space>
            </Card>
          ),
        },
      ]}
    />
  );
}
```

Reasoning: `Collapse` makes the source strip horizontally compact by default, and `ghost` keeps it visually lighter than a main page card.

- [ ] **Step 3: Replace the side source panel with the context strip slot**

In the `<DraftWorkbenchShell ... />` call, remove the entire `renderSourcePanel={() => (...)}` prop block.

Add this prop instead:

```tsx
      renderContextPanel={() => renderSourceContextStrip(currentSourceNote, draftAssets)}
```

The top of the shell call should start like this:

```tsx
      <DraftWorkbenchShell
        adapter={adapter}
        controller={controller}
        renderContextPanel={() => renderSourceContextStrip(currentSourceNote, draftAssets)}
        renderEditorExtras={() => (
```

Expected behavior: no side source panel is passed, so the shared shell uses the two-column `16/8` layout.

- [ ] **Step 4: Run TypeScript build to catch JSX errors**

Run from `frontend/`:

```bash
npm run build
```

Expected: build passes. If it fails on `Collapse` label typing, keep the `label` value as JSX and ensure `Tabs`/`Collapse` are imported from `antd`.

- [ ] **Step 5: Check changed files**

Run from repo root:

```bash
git status --short -- frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx frontend/src/components/draft-workbench/draft-workbench-shell.tsx
```

Expected: both the shell and XHS page are modified.

---

## Task 3: Split the XHS Assistant into System Score and AI Rewrite Tabs

**Files:**

- Modify: `frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx`

- [ ] **Step 1: Locate the current assistant extras block**

Find the existing prop:

```tsx
        renderAssistantExtras={() => (
          <Space direction="vertical" size={12} style={{ width: "100%" }}>
```

It currently contains the system score card, advanced prompt collapse, rewrite mode, action buttons, title candidates, tag candidates, and rewrite candidate result in one vertical stack.

- [ ] **Step 2: Replace assistant extras with Tabs**

Replace the whole `renderAssistantExtras={() => (...)}` block with:

```tsx
        renderAssistantExtras={() => (
          <Tabs
            defaultActiveKey="score"
            items={[
              {
                key: "score",
                label: "系统评分",
                children: (
                  <Card
                    size="small"
                    title={<Space><TrophyOutlined />系统打分</Space>}
                    loading={isLoadingDraftAiScore}
                    extra={(
                      <Button size="small" type="primary" loading={isScoringDraft} disabled={!selectedDraft} onClick={() => void handleScoreDraft()}>
                        保存并打分
                      </Button>
                    )}
                  >
                    {renderDraftScore(draftAiScore)}
                  </Card>
                ),
              },
              {
                key: "rewrite",
                label: "AI 改写",
                children: (
                  <Space direction="vertical" size={12} style={{ width: "100%" }}>
                    <Collapse
                      size="small"
                      items={[
                        {
                          key: "system-prompt",
                          label: "高级设置：角色提示词",
                          children: (
                            <TextArea rows={4} value={systemPrompt} onChange={(event) => setSystemPrompt(event.target.value)} />
                          ),
                        },
                      ]}
                    />

                    <div>
                      <Text type="secondary" style={{ display: "block", marginBottom: 6 }}>改写模式</Text>
                      <Space direction="vertical" size={8} style={{ width: "100%" }}>
                        <Input value={instruction} onChange={(event) => setInstruction(event.target.value)} placeholder="填写 AI 改写指令" />
                        <Space wrap>
                          {Object.entries(REWRITE_TEMPLATES).map(([key, template]) => (
                            <Button key={key} size="small" type={rewriteTemplate === key ? "primary" : "default"} icon={<EditOutlined />} onClick={() => {
                              setRewriteTemplate(key as RewriteTemplateKey);
                              setInstruction(template.instruction);
                            }}>
                              {template.label}
                            </Button>
                          ))}
                        </Space>
                      </Space>
                    </div>

                    <Space wrap>
                      <Button onClick={() => void handleRewrite()} loading={isRewriting} icon={<ReloadOutlined />}>
                        {activeRewriteTemplate.buttonLabel}
                      </Button>
                      <Button onClick={() => void handleGenerateTitles()}>生成标题</Button>
                      <Button onClick={() => void handleGenerateTags()}>生成标签</Button>
                    </Space>

                    {titleOptions.length > 0 ? (
                      <Card size="small" title="标题候选">
                        <Space wrap>
                          {titleOptions.map((option) => (
                            <Button key={option} size="small" onClick={() => controller.setTitle(option)}>{option}</Button>
                          ))}
                        </Space>
                      </Card>
                    ) : null}

                    {tagOptions.length > 0 ? (
                      <Card size="small" title="标签候选">
                        <Space wrap>
                          {tagOptions.map((option) => (
                            <Tag key={option} color="blue" onClick={() => handleAdoptTagOption(option)} style={{ cursor: "pointer" }}>{option}</Tag>
                          ))}
                        </Space>
                      </Card>
                    ) : null}

                    {activeRewriteCandidate ? (
                      <Card
                        size="small"
                        title={`改写结果 · ${activeRewriteTemplate.label}`}
                        styles={{ body: { maxHeight: 420, overflow: "auto" } }}
                      >
                        <Space direction="vertical" size={12} style={{ width: "100%" }}>
                          <Alert
                            type="info"
                            showIcon
                            message="候选结果尚未覆盖中间草稿"
                            description="你可以和中间编辑区原文对比，确认后再点击采纳。"
                          />
                          <div>
                            <Text type="secondary" style={{ display: "block", marginBottom: 4 }}>
                              标题
                            </Text>
                            <Text strong>{activeRewriteCandidate.title || "未命名候选"}</Text>
                          </div>
                          <div>
                            <Text type="secondary" style={{ display: "block", marginBottom: 4 }}>
                              正文
                            </Text>
                            <Paragraph style={{ whiteSpace: "pre-wrap", marginBottom: 0 }}>
                              {activeRewriteCandidate.body || "暂无正文"}
                            </Paragraph>
                          </div>
                          {activeRewriteCandidate.tags.length > 0 ? (
                            <Space size={[4, 8]} wrap>
                              {activeRewriteCandidate.tags.map((tag) => (
                                <Tag key={tag.id || tag.name} color="blue">
                                  #{tag.name}
                                </Tag>
                              ))}
                            </Space>
                          ) : null}
                          <Space wrap>
                            <Button type="primary" aria-label="adopt rewrite candidate" onClick={handleAdoptRewriteCandidate}>
                              采纳
                            </Button>
                            <Button aria-label="discard rewrite candidate" onClick={handleDiscardRewriteCandidate}>放弃</Button>
                          </Space>
                        </Space>
                      </Card>
                    ) : (
                      <Empty
                        image={Empty.PRESENTED_IMAGE_SIMPLE}
                        description={`当前模式还没有候选，生成${activeRewriteTemplate.label}后可和中间草稿对比。`}
                      />
                    )}
                  </Space>
                ),
              },
            ]}
          />
        )}
```

Important: this block intentionally excludes “送入图片工坊” and “送发布中心”. Those move in Task 4.

- [ ] **Step 3: Run TypeScript build to catch bracket/import issues**

Run from `frontend/`:

```bash
npm run build
```

Expected: build passes. If JSX nesting fails, fix only the assistant block brackets and do not change handler logic.

- [ ] **Step 4: Verify operation separation in code**

Search in `frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx` and confirm:

- The string `系统评分` appears in the `Tabs` items.
- The string `AI 改写` appears in the `Tabs` items.
- `handleScoreDraft` is only referenced inside the score tab.
- `handleRewrite`, `handleGenerateTitles`, and `handleGenerateTags` are only referenced inside the rewrite tab.

Use editor search or this command from repo root:

```bash
git diff -- frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx
```

Expected: the diff shows scoring and rewrite JSX separated under different `Tabs` item keys.

---

## Task 4: Move Image Studio and Publish Actions to Editor Bottom

**Files:**

- Modify: `frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx`

- [ ] **Step 1: Add primary actions prop to `DraftWorkbenchShell` call**

Add this prop between `renderEditorExtras` and `renderAssistantExtras` in the shell call:

```tsx
        renderPrimaryActions={() => (
          <Space direction="vertical" size={8} style={{ width: "100%" }}>
            <Text type="secondary" style={{ fontSize: 12 }}>下一步</Text>
            <Space wrap>
              <Button onClick={() => void handleSendToImageStudio()} loading={isSendingImageStudio} icon={<PictureOutlined />}>
                送入图片工坊
              </Button>
              <Button type="primary" onClick={() => void handleSendToPublish()} loading={isSendingPublish} icon={<SaveOutlined />}>
                送发布中心
              </Button>
            </Space>
          </Space>
        )}
```

The shell props should now follow this order:

```tsx
      <DraftWorkbenchShell
        adapter={adapter}
        controller={controller}
        renderContextPanel={() => renderSourceContextStrip(currentSourceNote, draftAssets)}
        renderEditorExtras={() => (
          ...
        )}
        renderPrimaryActions={() => (
          ...
        )}
        renderAssistantExtras={() => (
          ...
        )}
      />
```

- [ ] **Step 2: Confirm lifecycle buttons are absent from AI rewrite tab**

In the AI rewrite tab action `Space`, confirm it contains exactly these three buttons:

```tsx
                    <Space wrap>
                      <Button onClick={() => void handleRewrite()} loading={isRewriting} icon={<ReloadOutlined />}>
                        {activeRewriteTemplate.buttonLabel}
                      </Button>
                      <Button onClick={() => void handleGenerateTitles()}>生成标题</Button>
                      <Button onClick={() => void handleGenerateTags()}>生成标签</Button>
                    </Space>
```

Expected: no `handleSendToImageStudio` or `handleSendToPublish` call remains inside the rewrite tab.

- [ ] **Step 3: Run TypeScript build**

Run from `frontend/`:

```bash
npm run build
```

Expected: build passes.

- [ ] **Step 4: Check final frontend diff for intended scope**

Run from repo root:

```bash
git diff -- frontend/src/components/draft-workbench/draft-workbench-shell.tsx frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx
```

Expected diff contains only:

- New shell slots.
- New context strip rendering.
- XHS shell prop changes.
- Assistant tabs.
- Lifecycle action movement.

Expected diff does not contain:

- Backend API edits.
- Type model edits.
- Unrelated formatting-only rewrites.

---

## Task 5: Manual QA and Final Verification

**Files:**

- No source edits expected.
- Verify: `frontend/src/components/draft-workbench/draft-workbench-shell.tsx`
- Verify: `frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx`

- [ ] **Step 1: Run production build**

Run from `frontend/`:

```bash
npm run build
```

Expected:

```text
> spider-xhs-frontend@0.1.0 build
> tsc && vite build
```

and the command exits with code 0.

- [ ] **Step 2: Start or use the existing app for manual QA**

If a frontend dev server is already running for the root workspace, use it. If not, run from `frontend/`:

```bash
npm run dev
```

Expected: Vite prints a local URL. Use the existing project backend if the page needs API data.

- [ ] **Step 3: Manual QA for source context strip**

Open the 小红书草稿工坊 page and select a draft that has `source_note_id`.

Verify:

- No left-side “来源面板” column is visible.
- A compact source row appears under the current-draft card.
- The source row shows the source title, 图文/视频 tag, material count, and 查看原文.
- Clicking the source row expands original text and image previews.
- A draft with no source note does not show a large empty source panel.

- [ ] **Step 4: Manual QA for two-column layout**

With any selected XHS draft, verify:

- Editor column is visibly wider than before and occupies roughly two-thirds of desktop width.
- Right column occupies roughly one-third of desktop width.
- On narrow viewport, columns stack vertically.

- [ ] **Step 5: Manual QA for system score tab**

Open the right-side “系统评分” tab.

Verify:

- It shows “保存并打分”.
- It shows existing score result or the empty score state.
- It does not show AI rewrite mode buttons.
- It does not show title/tag generation buttons.
- It does not show “送入图片工坊” or “送发布中心”.

- [ ] **Step 6: Manual QA for AI rewrite tab**

Open the right-side “AI 改写” tab.

Verify:

- It shows 安全改写 / 轻度润色 / 种草增强.
- It shows the rewrite instruction input.
- The role prompt stays inside “高级设置：角色提示词”.
- It shows 生成改写 / 生成标题 / 生成标签.
- Generated rewrite result remains a candidate and does not overwrite the editor until “采纳” is clicked.
- It does not show score dimensions or score risk cards.
- It does not show “保存并打分”.

- [ ] **Step 7: Manual QA for editor-bottom next-step actions**

Scroll to the bottom of the editor card.

Verify:

- Existing 保存 / 复制 / 删除 / Dry-run actions still work as before.
- A “下一步” group is visible below built-in editor actions.
- “送入图片工坊” saves the draft context and navigates to `/platforms/xhs/image-studio?from=draft`.
- “送发布中心” still calls the existing publish flow and shows the success/error toast.

- [ ] **Step 8: Compatibility check for non-XHS draft workbench**

Open the WeChat official draft workbench if available in the app.

Verify:

- Its existing source panel behavior is unchanged if it uses `renderSourcePanel`.
- Its editor and assistant columns still render.
- No TypeScript or runtime error appears from the new optional shell props.

- [ ] **Step 9: Final git status checkpoint**

Run from repo root:

```bash
git status --short
```

Expected: the relevant files are modified/untracked:

```text
 M frontend/src/components/draft-workbench/draft-workbench-shell.tsx
 M frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx
?? docs/superpowers/specs/2026-07-02-xhs-draft-workbench-layout-redesign.md
?? docs/superpowers/plans/2026-07-02-xhs-draft-workbench-layout-redesign.md
```

There may be pre-existing unrelated changes from earlier work. Do not include them in any completion claim for this task.

---

## Self-Review

### Spec coverage

- Source information becomes top collapsible strip: Task 2.
- Main body becomes two columns: Task 1 and Task 2.
- System scoring and AI rewrite separated into tabs: Task 3.
- Image-studio and publish actions move to editor-bottom next-step area: Task 4.
- Other platform draft workbenches stay compatible: Task 1 compatibility behavior and Task 5 compatibility QA.
- No backend/API/model changes: File Structure and Task 4 diff check.

### Placeholder scan

The plan contains no TBD, TODO, “fill in details”, or undefined future work. All code changes are shown with exact file paths and concrete snippets.

### Type consistency

- New shell props use `renderContextPanel` and `renderPrimaryActions` consistently in the type, function destructuring, and XHS shell call.
- Existing handlers keep their current names: `handleScoreDraft`, `handleRewrite`, `handleGenerateTitles`, `handleGenerateTags`, `handleSendToImageStudio`, and `handleSendToPublish`.
- Existing state variables keep their current names: `draftAiScore`, `isLoadingDraftAiScore`, `isScoringDraft`, `rewriteTemplate`, `instruction`, `systemPrompt`, `titleOptions`, `tagOptions`, `activeRewriteCandidate`, `isSendingImageStudio`, and `isSendingPublish`.

# 小红书草稿工坊 AI 改写候选区 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复小红书草稿工坊 AI 改写交互，让生成结果先进入右侧候选区，三种改写模式在当前页面会话内分别保留候选，只有点击“采纳”才覆盖中间编辑区。

**Architecture:** 不改后端接口和数据库，只在前端页面内维护会话态候选缓存。把候选缓存操作提取到一个纯 TypeScript helper，先用轻量 check 锁定“按模式保留、按模式清空、候选标准化”的行为，再让 `XhsDraftsPage` 使用该 helper 渲染右侧候选结果和采纳/放弃按钮。

**Tech Stack:** React 19, Vite, TypeScript, Ant Design, existing `rewriteDraftWithAi` / `updateDraft` API helpers.

---

## File Structure

- Create: `frontend/src/pages/platforms/xhs/xhs-rewrite-candidates.ts`
  - 负责 AI 改写候选的纯数据结构与操作：标准化 API 返回的 draft、按模式写入候选、读取候选、清空当前模式候选。
  - 不依赖 React，便于轻量测试和后续复用。

- Create: `frontend/src/pages/platforms/xhs/xhs-rewrite-candidates.check.ts`
  - 轻量行为检查脚本，覆盖当前 bug 的核心状态规则：生成一个模式不覆盖另一个模式，清空当前模式不影响其他模式。

- Modify: `frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx`
  - 把 AI 改写结果从“直接写入中间编辑区”改成“写入右侧候选缓存”。
  - 增加“改写结果”Card，提供“采纳”和“放弃”。
  - 切换草稿时清空候选，避免不同草稿之间串候选。

- Verify only: `frontend/package.json`
  - 不新增依赖，不修改 scripts。
  - 通过 `npm run build` 做最终类型和构建验证。

---

### Task 1: Add pure rewrite-candidate state helper with failing checks

**Files:**
- Create: `frontend/src/pages/platforms/xhs/xhs-rewrite-candidates.check.ts`
- Create after RED: `frontend/src/pages/platforms/xhs/xhs-rewrite-candidates.ts`

- [ ] **Step 1: Write the failing check**

Create `frontend/src/pages/platforms/xhs/xhs-rewrite-candidates.check.ts` with this exact content:

```ts
import {
  clearRewriteCandidate,
  getRewriteCandidate,
  setRewriteCandidate,
  toRewriteCandidate,
} from "./xhs-rewrite-candidates";

function assert(condition: boolean, message: string): void {
  if (!condition) {
    throw new Error(message);
  }
}

const safeCandidate = toRewriteCandidate(
  {
    title: "安全改写标题",
    body: "安全改写正文",
    tags: [{ name: "安全" }],
  },
  101,
);

const polishCandidate = toRewriteCandidate(
  {
    title: "轻度润色标题",
    body: "轻度润色正文",
    tags: [{ name: "润色" }],
  },
  202,
);

const emptyCandidates = {};
const withSafe = setRewriteCandidate(emptyCandidates, "safe", safeCandidate);
const withSafeAndPolish = setRewriteCandidate(withSafe, "polish", polishCandidate);

assert(getRewriteCandidate(withSafeAndPolish, "safe")?.title === "安全改写标题", "safe candidate should survive after generating polish candidate");
assert(getRewriteCandidate(withSafeAndPolish, "polish")?.title === "轻度润色标题", "polish candidate should be stored independently");
assert(getRewriteCandidate(withSafeAndPolish, "seed") === null, "missing candidate should read as null");
assert(getRewriteCandidate(withSafeAndPolish, "safe")?.generatedAt === 101, "safe candidate should keep deterministic generatedAt");
assert(getRewriteCandidate(withSafeAndPolish, "polish")?.tags[0]?.name === "润色", "candidate should keep normalized tags");

const withoutPolish = clearRewriteCandidate(withSafeAndPolish, "polish");

assert(getRewriteCandidate(withoutPolish, "polish") === null, "clearing polish should remove only polish candidate");
assert(getRewriteCandidate(withoutPolish, "safe")?.body === "安全改写正文", "clearing polish should not remove safe candidate");
assert(withoutPolish !== withSafeAndPolish, "clearing should return a new map object");
assert(withSafe !== emptyCandidates, "setting should return a new map object");
```

- [ ] **Step 2: Run the check and verify RED**

Run from `frontend/`:

```bash
npx tsc --target ES2020 --module ES2020 --moduleResolution Bundler --jsx react-jsx --outDir .tmp/rewrite-candidates-check --noEmit false --skipLibCheck true src/pages/platforms/xhs/xhs-rewrite-candidates.check.ts
```

Expected: FAIL because `src/pages/platforms/xhs/xhs-rewrite-candidates.ts` does not exist yet. The important failure text should include a module-not-found message for `./xhs-rewrite-candidates`.

- [ ] **Step 3: Add the minimal helper implementation**

Create `frontend/src/pages/platforms/xhs/xhs-rewrite-candidates.ts` with this exact content:

```ts
import type { Draft } from "../../../types";

import type { RewriteTemplateKey } from "./rewrite-templates";

export type RewriteCandidate = {
  title: string;
  body: string;
  tags: NonNullable<Draft["tags"]>;
  generatedAt: number;
};

export type RewriteCandidateMap = Partial<Record<RewriteTemplateKey, RewriteCandidate>>;

export function toRewriteCandidate(
  draft: Pick<Draft, "title" | "body" | "tags">,
  generatedAt: number,
): RewriteCandidate {
  return {
    title: draft.title,
    body: draft.body,
    tags: Array.isArray(draft.tags) ? draft.tags : [],
    generatedAt,
  };
}

export function setRewriteCandidate(
  candidates: RewriteCandidateMap,
  mode: RewriteTemplateKey,
  candidate: RewriteCandidate,
): RewriteCandidateMap {
  return {
    ...candidates,
    [mode]: candidate,
  };
}

export function getRewriteCandidate(
  candidates: RewriteCandidateMap,
  mode: RewriteTemplateKey,
): RewriteCandidate | null {
  return candidates[mode] ?? null;
}

export function clearRewriteCandidate(
  candidates: RewriteCandidateMap,
  mode: RewriteTemplateKey,
): RewriteCandidateMap {
  const next = { ...candidates };
  delete next[mode];
  return next;
}
```

- [ ] **Step 4: Run the check and verify GREEN**

Run from `frontend/`:

```bash
npx tsc --target ES2020 --module ES2020 --moduleResolution Bundler --jsx react-jsx --outDir .tmp/rewrite-candidates-check --noEmit false --skipLibCheck true src/pages/platforms/xhs/xhs-rewrite-candidates.check.ts && node --experimental-specifier-resolution=node .tmp/rewrite-candidates-check/xhs-rewrite-candidates.check.js
```

Expected: PASS with no thrown assertion errors.

If Node emits an experimental warning for `--experimental-specifier-resolution=node`, that is acceptable for this local check. Any thrown `Error(...)` from the check is a failure.

- [ ] **Step 5: Clean temporary check output**

Run from `frontend/`:

```bash
rm -rf .tmp/rewrite-candidates-check
```

Expected: `.tmp/rewrite-candidates-check` is removed. This cleanup touches only generated temporary output.

- [ ] **Step 6: Checkpoint**

Do not commit unless the user explicitly asks. Record these files as the Task 1 checkpoint:

```text
frontend/src/pages/platforms/xhs/xhs-rewrite-candidates.ts
frontend/src/pages/platforms/xhs/xhs-rewrite-candidates.check.ts
```

---

### Task 2: Route AI rewrite generation into per-mode candidates instead of the editor

**Files:**
- Modify: `frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx`

- [ ] **Step 1: Update imports for candidate helper and Alert**

In `frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx`, replace the first three import lines:

```ts
import { useEffect, useMemo, useState } from "react";
import { Button, Card, Collapse, Input, Space, Tag, Typography, message as antMessage } from "antd";
import { EditOutlined, LinkOutlined, ReloadOutlined, SaveOutlined } from "@ant-design/icons";
```

with:

```ts
import { useEffect, useMemo, useState } from "react";
import { Alert, Button, Card, Collapse, Empty, Input, Space, Tag, Typography, message as antMessage } from "antd";
import { EditOutlined, LinkOutlined, ReloadOutlined, SaveOutlined } from "@ant-design/icons";
```

Then after the existing rewrite-template imports:

```ts
import type { RewriteTemplateKey } from "./rewrite-templates";
import { DEFAULT_REWRITE_TEMPLATE_KEY, REWRITE_TEMPLATES } from "./rewrite-templates";
```

add:

```ts
import {
  clearRewriteCandidate,
  getRewriteCandidate,
  setRewriteCandidate,
  toRewriteCandidate,
} from "./xhs-rewrite-candidates";
import type { RewriteCandidateMap } from "./xhs-rewrite-candidates";
```

- [ ] **Step 2: Add candidate state**

Inside `XhsDraftsPage`, after this existing state:

```ts
const [tagOptions, setTagOptions] = useState<string[]>([]);
const [isRewriting, setIsRewriting] = useState(false);
const [isSendingPublish, setIsSendingPublish] = useState(false);
```

add:

```ts
const [rewriteCandidates, setRewriteCandidates] = useState<RewriteCandidateMap>({});
```

- [ ] **Step 3: Add derived current candidate**

After these existing derived values:

```ts
const selectedDraft = controller.selectedDraft;
const hasSourceNote = Boolean(selectedDraft?.source_note_id);
```

add:

```ts
const activeRewriteTemplate = REWRITE_TEMPLATES[rewriteTemplate];
const activeRewriteCandidate = getRewriteCandidate(rewriteCandidates, rewriteTemplate);
```

- [ ] **Step 4: Clear candidates when switching drafts**

After the existing source-note `useEffect` block that depends on `[selectedDraft?.id, selectedDraft?.source_note_id]`, add this separate effect:

```ts
useEffect(() => {
  setRewriteCandidates({});
}, [selectedDraft?.id]);
```

This intentionally clears page-session candidates only when the selected draft changes. It does not persist anything to the backend.

- [ ] **Step 5: Replace `handleRewrite` so generation only updates the right-side candidate cache**

Replace the existing `handleRewrite()` function:

```ts
async function handleRewrite() {
  if (!selectedDraft) return;
  setIsRewriting(true);
  try {
    await updateDraft(selectedDraft.id, { title: controller.title, body: controller.body, tags: controller.tags });
    const rewritten = await rewriteDraftWithAi({ draft_id: selectedDraft.id, instruction: `${systemPrompt}\n${instruction}` });
    controller.setTitle(rewritten.title);
    controller.setBody(rewritten.body);
    controller.setTags(Array.isArray(rewritten.tags) ? rewritten.tags : []);
    antMessage.success("AI 改写完成，请检查后保存。");
  } catch (error) {
    antMessage.error(error instanceof Error ? error.message : "AI 改写失败");
  } finally {
    setIsRewriting(false);
  }
}
```

with:

```ts
async function handleRewrite() {
  if (!selectedDraft) return;
  setIsRewriting(true);
  try {
    await updateDraft(selectedDraft.id, { title: controller.title, body: controller.body, tags: controller.tags });
    const rewritten = await rewriteDraftWithAi({ draft_id: selectedDraft.id, instruction: `${systemPrompt}\n${instruction}` });
    const candidate = toRewriteCandidate(rewritten, Date.now());
    setRewriteCandidates((current) => setRewriteCandidate(current, rewriteTemplate, candidate));
    antMessage.success("AI 改写候选已生成，点击采纳后才会覆盖中间草稿。");
  } catch (error) {
    antMessage.error(error instanceof Error ? error.message : "AI 改写失败");
  } finally {
    setIsRewriting(false);
  }
}
```

This is the core regression fix: the function no longer calls `controller.setTitle`, `controller.setBody`, or `controller.setTags` after generation.

- [ ] **Step 6: Add adopt and discard handlers**

After `handleRewrite()`, add:

```ts
function handleAdoptRewriteCandidate() {
  if (!activeRewriteCandidate) return;
  controller.setTitle(activeRewriteCandidate.title);
  controller.setBody(activeRewriteCandidate.body);
  controller.setTags(activeRewriteCandidate.tags);
  antMessage.success("已采纳到中间编辑区，请检查后保存。");
}

function handleDiscardRewriteCandidate() {
  setRewriteCandidates((current) => clearRewriteCandidate(current, rewriteTemplate));
  antMessage.success("已放弃当前模式候选。");
}
```

- [ ] **Step 7: Make mode switching use the derived template**

In the mode button `onClick`, keep the behavior but ensure the instruction is loaded from the clicked template. The existing block is already correct:

```tsx
onClick={() => {
  setRewriteTemplate(key as RewriteTemplateKey);
  setInstruction(template.instruction);
}}
```

No change is required in this step if the block still matches the snippet above.

- [ ] **Step 8: Replace the generic AI rewrite button with mode-specific generation text**

Find this existing button:

```tsx
<Button onClick={() => void handleRewrite()} loading={isRewriting} icon={<ReloadOutlined />}>
  AI 改写
</Button>
```

Replace it with:

```tsx
<Button onClick={() => void handleRewrite()} loading={isRewriting} icon={<ReloadOutlined />}>
  {activeRewriteTemplate.buttonLabel}
</Button>
```

- [ ] **Step 9: Render the right-side candidate result below the action buttons**

Immediately after the existing `<Space wrap>` block that contains the rewrite/title/tag/publish buttons, add this JSX:

```tsx
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
        <Button type="primary" onClick={handleAdoptRewriteCandidate}>
          采纳
        </Button>
        <Button onClick={handleDiscardRewriteCandidate}>放弃</Button>
      </Space>
    </Space>
  </Card>
) : (
  <Empty
    image={Empty.PRESENTED_IMAGE_SIMPLE}
    description={`当前模式还没有候选，生成${activeRewriteTemplate.label}后可和中间草稿对比。`}
  />
)}
```

- [ ] **Step 10: Run TypeScript build check**

Run from `frontend/`:

```bash
npm run build
```

Expected: PASS. This verifies the new component imports, helper types, JSX, and production build.

- [ ] **Step 11: Checkpoint**

Do not commit unless the user explicitly asks. Record this file as the Task 2 checkpoint:

```text
frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx
```

---

### Task 3: Verify the full user workflow manually in the browser

**Files:**
- Verify only: `frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx`
- Verify only: browser/local app runtime

- [ ] **Step 1: Start the app using the project’s normal development entrypoint**

Use the project’s existing launch command for local frontend/backend validation. If services are already running on the standard project ports, reuse them instead of starting duplicate services.

For frontend-only validation, run from `frontend/`:

```bash
npm run dev
```

Expected: Vite starts successfully and prints a local URL.

- [ ] **Step 2: Open the draft workshop page**

Navigate to the XHS draft workshop route used by the router for `XhsDraftsPage`. The router import is `frontend/src/app/router.tsx`, where `XhsDraftsPage` is imported from `../pages/platforms/xhs/rewrite-page`; the page currently delegates to `xhs-draft-workbench.tsx`.

Expected: The draft workshop renders with three columns: draft list, center draft editor, right AI assistant.

- [ ] **Step 3: Verify generation does not overwrite the center editor**

Manual steps:

1. Select a draft.
2. Put a recognizable title and body in the center editor, for example title `原文 A` and body `中间操作台原文 A`.
3. In the right AI assistant, select `安全改写`.
4. Click `生成安全改写版`.
5. Wait for the request to finish.

Expected:

- Center title remains `原文 A` until the user clicks `采纳`.
- Center body remains `中间操作台原文 A` until the user clicks `采纳`.
- Right side shows a Card titled `改写结果 · 安全改写`.
- The right Card contains `采纳` and `放弃` buttons.

- [ ] **Step 4: Verify per-mode candidate retention**

Manual steps:

1. Keep the safe candidate visible.
2. Switch to `轻度润色`.
3. Generate a candidate.
4. Switch back to `安全改写`.

Expected:

- The center editor still shows the original unadopted content.
- The safe candidate is still visible after switching back.
- The polish candidate is visible when switching again to `轻度润色`.

- [ ] **Step 5: Verify adopt is the only overwrite action**

Manual steps:

1. While `安全改写` candidate is visible, click `采纳`.

Expected:

- Center title becomes the safe candidate title.
- Center body becomes the safe candidate body.
- A success message says `已采纳到中间编辑区，请检查后保存。`
- The user can still edit before clicking the existing center `保存` button.

- [ ] **Step 6: Verify discard only clears the active mode**

Manual steps:

1. Generate candidates for `安全改写` and `轻度润色`.
2. While `轻度润色` is active, click `放弃`.
3. Switch to `安全改写`.

Expected:

- `轻度润色` shows the empty state after discard.
- `安全改写` candidate is still present.
- Center editor content does not change during discard.

- [ ] **Step 7: Stop any development server started for this task**

If this task started a temporary Vite process, stop it with Ctrl+C in that terminal. Do not stop shared root workspace services unless the user explicitly authorized it.

- [ ] **Step 8: Checkpoint**

Do not commit unless the user explicitly asks. Record verification evidence in the final report:

```text
npm run build: PASS/FAIL with command output summary
manual browser workflow: PASS/FAIL with observed behavior
```

---

## Final Verification

Run from `frontend/`:

```bash
npm run build
```

Expected: PASS.

Run the focused helper check from `frontend/`:

```bash
npx tsc --target ES2020 --module ES2020 --moduleResolution Bundler --jsx react-jsx --outDir .tmp/rewrite-candidates-check --noEmit false --skipLibCheck true src/pages/platforms/xhs/xhs-rewrite-candidates.check.ts && node --experimental-specifier-resolution=node .tmp/rewrite-candidates-check/xhs-rewrite-candidates.check.js
rm -rf .tmp/rewrite-candidates-check
```

Expected: PASS with no assertion errors.

Manual browser acceptance must confirm:

- Generating a rewrite candidate does not overwrite the center editor.
- Safe/polish/seed each keep their own latest candidate while staying on the same selected draft.
- Clicking `采纳` is the only action that writes candidate title/body/tags into the center editor.
- Clicking `放弃` clears only the current mode candidate.
- Switching to another draft clears in-memory candidates.
- Refreshing the page loses candidates, as designed.

## Self-Review Notes

- Spec coverage: The plan covers session-only candidate state, per-mode retention, adopt-only overwrite, discard, draft-switch cleanup, no backend/database changes, and final build/manual verification.
- Placeholder scan: No `TBD`, `TODO`, or unspecified implementation steps remain. Every code change step includes exact code.
- Type consistency: `RewriteTemplateKey`, `RewriteCandidateMap`, `Draft["tags"]`, `setRewriteCandidate`, `getRewriteCandidate`, and `clearRewriteCandidate` use the same names across helper, check, and component tasks.
- Project rule adaptation: The skill template recommends frequent commits, but this project requires explicit user authorization before commits. The plan uses checkpoints and says not to commit unless the user explicitly asks.

# 多平台草稿工作台共享骨架 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把公众号和 XHS 的草稿页收敛成同一套三栏工作台骨架，并让未来平台只需接自己的 adapter 就能复用同样的草稿体验。

**Architecture:** 抽出平台无关的草稿工作台壳和状态钩子，统一处理草稿列表、选中态、保存、复制、删除和 dry-run 的公共流程；平台差异留在 adapter 和页面级 extras 里。公众号继续只看独立草稿，不再把内容库候选混进草稿区；XHS 保留现有草稿语义，但改成接入同一个共享骨架。未来新增平台时，只需要补 adapter，不需要再复制整页。

**Tech Stack:** React, Vite, TypeScript, Ant Design, React Router, pytest.

---

## File Structure

- Create: `frontend/src/components/draft-workbench/draft-workbench-types.ts` — shared draft workbench types, capability flags, and adapter contract.
- Create: `frontend/src/components/draft-workbench/use-draft-workbench.ts` — shared controller hook for loading drafts, selection, and draft actions.
- Create: `frontend/src/components/draft-workbench/draft-workbench-shell.tsx` — reusable three-column layout and empty/error/loading states.
- Create: `frontend/src/components/draft-workbench/index.ts` — barrel export for the new workbench package.
- Create: `frontend/src/pages/platforms/xhs/xhs-draft-workbench-adapter.ts` — XHS adapter over existing draft APIs and page-specific copy.
- Modify: `frontend/src/pages/platforms/xhs/rewrite-page.tsx:206-964` — replace the inline three-column draft layout with the shared shell and the XHS adapter.
- Modify: `frontend/src/pages/platforms/xhs/drafts-page.tsx` — turn the duplicate XHS draft page into a compatibility re-export so there is one canonical XHS workbench implementation.
- Create: `frontend/src/pages/wechat-official/wechat-official-draft-workbench.tsx` — WeChat draft workbench wrapper that uses the shared shell and only loads independent drafts.
- Modify: `frontend/src/pages/wechat-official/wechat-official-dashboard.tsx:303-605` — swap the drafts branch to the shared WeChat workbench and keep content-library candidate UI out of the drafts section.
- Test: `pytest tests/backend/test_wechat_official_drafts.py -v` — regression coverage for the existing source-free WeChat draft behavior.
- Test: `cd frontend && npm run build` — TypeScript and Vite verification for the new workbench components and page wiring.
- Test: `git diff --check` — final whitespace / patch sanity check.

## Non-goals

- 不改 `backend/app/api/drafts.py` 的 XHS 通用草稿语义。
- 不改 `backend/app/services/wechat_official_draft_service.py` 的公众号“无来源引用”修复逻辑。
- 不新增数据库表或 Alembic migration。
- 不重构 XHS SDK、公众号内容库、Redfox 配置页或发布策略。
- 不把 `frontend/src/pages/platforms/xhs/drafts-page.tsx` 和 `rewrite-page.tsx` 保留成两套并行实现；这次要收敛成一个 canonical XHS workbench。

---

### Task 1: Extract the shared draft-workbench contract and shell

**Files:**
- Create: `frontend/src/components/draft-workbench/draft-workbench-types.ts`
- Create: `frontend/src/components/draft-workbench/use-draft-workbench.ts`
- Create: `frontend/src/components/draft-workbench/draft-workbench-shell.tsx`
- Create: `frontend/src/components/draft-workbench/index.ts`

- [ ] **Step 1: Write the failing type contract and shell wiring**

Add the shared contract first so the compiler has one place to enforce the shape of every platform adapter.

```ts
// frontend/src/components/draft-workbench/draft-workbench-types.ts
import type React from "react";
import type { Draft, PlatformId } from "../../types";

export type DraftWorkbenchDraft = Pick<Draft, "id" | "title" | "body" | "tags" | "created_at">;

export type DraftWorkbenchDraftPatch = {
  title: string;
  body: string;
  tags: Draft["tags"];
};

export type DraftWorkbenchDryRunResult = {
  ok: boolean;
  publish_blocked: boolean;
  sendall_blocked: boolean;
  checks: Record<string, "ok" | "warning" | "missing" | "blocked">;
};

export type DraftWorkbenchCapabilities = {
  canCreateFromSource: boolean;
  canDuplicate: boolean;
  canDelete: boolean;
  canDryRun: boolean;
  canSendToPublish: boolean;
};

export type DraftWorkbenchAdapter<TDraft extends DraftWorkbenchDraft = DraftWorkbenchDraft> = {
  platform: PlatformId;
  pageTitle: string;
  pageDescription: string;
  capabilities: DraftWorkbenchCapabilities;
  loadDrafts(): Promise<TDraft[]>;
  saveDraft(draftId: number, patch: DraftWorkbenchDraftPatch): Promise<TDraft>;
  duplicateDraft?(draftId: number): Promise<TDraft>;
  deleteDraft?(draftId: number): Promise<void>;
  dryRunDraft?(draftId: number, payload?: Record<string, unknown>): Promise<DraftWorkbenchDryRunResult>;
  createDraftFromSource?(sourceId: number, payload?: Record<string, unknown>): Promise<TDraft>;
  getListSubtitle(draft: TDraft): string;
  getEmptyState(): { title: string; description: string; actionLabel?: string };
};

export type DraftWorkbenchController<TDraft extends DraftWorkbenchDraft = DraftWorkbenchDraft> = {
  drafts: TDraft[];
  selectedDraftId: number | null;
  selectedDraft: TDraft | null;
  isLoading: boolean;
  error: string | null;
  message: string | null;
  loadDrafts(): Promise<void>;
  selectDraft(draftId: number): void;
  updateTitle(title: string): void;
  updateBody(body: string): void;
  updateTags(tags: Draft["tags"]): void;
  saveSelectedDraft(): Promise<void>;
  duplicateSelectedDraft(): Promise<void>;
  deleteSelectedDraft(): Promise<void>;
  dryRunSelectedDraft(payload?: Record<string, unknown>): Promise<DraftWorkbenchDryRunResult | null>;
};
```

Build the hook and shell around that contract so the first `npm run build` fails until the new files exist and the shared controller is wired through the page layer.

```tsx
// frontend/src/components/draft-workbench/draft-workbench-shell.tsx
import type React from "react";
import { Alert, Button, Card, Col, Empty, Input, List, Row, Space, Spin, Tag, Typography } from "antd";
import type { DraftWorkbenchController, DraftWorkbenchDraft } from "./draft-workbench-types";

export type DraftWorkbenchShellProps<TDraft extends DraftWorkbenchDraft> = {
  controller: DraftWorkbenchController<TDraft>;
  title: string;
  description: string;
  renderEditorExtras?: (draft: TDraft) => React.ReactNode;
  renderAssistantExtras?: (draft: TDraft) => React.ReactNode;
};

export function DraftWorkbenchShell<TDraft extends DraftWorkbenchDraft>({
  controller,
  title,
  description,
  renderEditorExtras,
  renderAssistantExtras,
}: DraftWorkbenchShellProps<TDraft>) {
  // shell renders the three columns, common loading/error/empty states, and the shared editor fields
}
```

- [ ] **Step 2: Run the build and confirm it fails before the hook and shell are implemented**

Run:

```bash
cd frontend && npm run build
```

Expected: FAIL with TypeScript errors for the missing `draft-workbench` exports or unresolved controller methods.

- [ ] **Step 3: Write the minimal hook and shell implementation**

Implement the hook so it owns only shared state: draft list, selected draft, dirty edits, and the common action methods.

```ts
// frontend/src/components/draft-workbench/use-draft-workbench.ts
import { useCallback, useEffect, useMemo, useState } from "react";
import type {
  DraftWorkbenchAdapter,
  DraftWorkbenchController,
  DraftWorkbenchDraft,
  DraftWorkbenchDraftPatch,
  DraftWorkbenchDryRunResult,
} from "./draft-workbench-types";

export function useDraftWorkbench<TDraft extends DraftWorkbenchDraft>(adapter: DraftWorkbenchAdapter<TDraft>): DraftWorkbenchController<TDraft> {
  const [drafts, setDrafts] = useState<TDraft[]>([]);
  const [selectedDraftId, setSelectedDraftId] = useState<number | null>(null);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [tags, setTags] = useState<DraftWorkbenchDraftPatch["tags"]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const selectedDraft = useMemo(() => drafts.find((draft) => draft.id === selectedDraftId) ?? null, [drafts, selectedDraftId]);

  const loadDrafts = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const items = await adapter.loadDrafts();
      setDrafts(items);
      const first = selectedDraftId ? items.find((draft) => draft.id === selectedDraftId) : items[0];
      if (first) {
        setSelectedDraftId(first.id);
        setTitle(first.title);
        setBody(first.body);
        setTags(Array.isArray(first.tags) ? first.tags : []);
      } else {
        setSelectedDraftId(null);
        setTitle("");
        setBody("");
        setTags([]);
      }
    } catch {
      setDrafts([]);
      setSelectedDraftId(null);
      setError("草稿列表加载失败。");
    } finally {
      setIsLoading(false);
    }
  }, [adapter, selectedDraftId]);

  useEffect(() => {
    void loadDrafts();
  }, [loadDrafts]);

  return {
    drafts,
    selectedDraftId,
    selectedDraft,
    isLoading,
    error,
    message,
    loadDrafts,
    selectDraft: setSelectedDraftId,
    updateTitle: setTitle,
    updateBody: setBody,
    updateTags: setTags,
    saveSelectedDraft: async () => {
      if (!selectedDraft) return;
      setError(null);
      const updated = await adapter.saveDraft(selectedDraft.id, { title, body, tags });
      setDrafts((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setSelectedDraftId(updated.id);
      setTitle(updated.title);
      setBody(updated.body);
      setTags(Array.isArray(updated.tags) ? updated.tags : []);
      setMessage(`草稿 #${updated.id} 已保存。`);
    },
    duplicateSelectedDraft: async () => {
      if (!selectedDraft || !adapter.duplicateDraft) return;
      const copied = await adapter.duplicateDraft(selectedDraft.id);
      setDrafts((current) => [copied, ...current.filter((item) => item.id !== copied.id)]);
      setSelectedDraftId(copied.id);
      setTitle(copied.title);
      setBody(copied.body);
      setTags(Array.isArray(copied.tags) ? copied.tags : []);
      setMessage(`草稿 #${copied.id} 已复制。`);
    },
    deleteSelectedDraft: async () => {
      if (!selectedDraft || !adapter.deleteDraft) return;
      await adapter.deleteDraft(selectedDraft.id);
      setDrafts((current) => current.filter((item) => item.id !== selectedDraft.id));
      setSelectedDraftId(null);
      setTitle("");
      setBody("");
      setTags([]);
      setMessage(`草稿 #${selectedDraft.id} 已删除。`);
    },
    dryRunSelectedDraft: async (payload?: Record<string, unknown>) => {
      if (!selectedDraft || !adapter.dryRunDraft) return null;
      return await adapter.dryRunDraft(selectedDraft.id, payload) as DraftWorkbenchDryRunResult;
    },
  };
}
```

- [ ] **Step 4: Run the build again and confirm the shared package is wired correctly**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS, with the new `draft-workbench` package compiling cleanly.

- [ ] **Step 5: Commit the shared shell extraction**

```bash
git add frontend/src/components/draft-workbench

git commit -m "feat: add shared draft workbench shell"
```

---

### Task 2: Migrate the XHS draft page onto the shared shell

**Files:**
- Create: `frontend/src/pages/platforms/xhs/xhs-draft-workbench-adapter.ts`
- Modify: `frontend/src/pages/platforms/xhs/rewrite-page.tsx:206-964`
- Modify: `frontend/src/pages/platforms/xhs/drafts-page.tsx`

- [ ] **Step 1: Write the XHS adapter against the new shared contract**

Keep the XHS adapter thin: it should use the existing XHS draft APIs, keep current XHS semantics, and expose only platform-allowed actions.

```ts
// frontend/src/pages/platforms/xhs/xhs-draft-workbench-adapter.ts
import type { Draft } from "../../../types";
import {
  deleteDraft,
  duplicateDraft,
  fetchDrafts,
  sendDraftToPublish,
  updateDraft,
} from "../../../lib/api";
import type { DraftWorkbenchAdapter } from "../../../components/draft-workbench/draft-workbench-types";

export function createXhsDraftWorkbenchAdapter(): DraftWorkbenchAdapter<Draft> {
  return {
    platform: "xhs",
    pageTitle: "小红书草稿工坊",
    pageDescription: "左侧草稿队列，中间编辑器，右侧 AI 助手；草稿继续保持 XHS 现有语义。",
    capabilities: {
      canCreateFromSource: true,
      canDuplicate: true,
      canDelete: true,
      canDryRun: false,
      canSendToPublish: true,
    },
    loadDrafts: async () => (await fetchDrafts("xhs")).items,
    saveDraft: async (draftId, patch) => await updateDraft(draftId, patch),
    duplicateDraft: async (draftId) => await duplicateDraft(draftId),
    deleteDraft: async (draftId) => {
      await deleteDraft(draftId);
    },
    getListSubtitle: (draft) => draft.created_at,
    getEmptyState: () => ({
      title: "还没有草稿",
      description: "先去内容库挑一篇笔记，或者用现有草稿复制一份继续写。",
      actionLabel: "去内容库",
    }),
  };
}
```

Replace the inline three-column JSX in `rewrite-page.tsx` with the shared shell and keep the page-specific source preview, asset controls, AI rewrite controls, and publish controls in render props or local helpers. The page should still own XHS-specific behavior, but the layout and selection state should move into the shared controller.

```tsx
const adapter = useMemo(() => createXhsDraftWorkbenchAdapter(), []);
const controller = useDraftWorkbench(adapter);

return (
  <DraftWorkbenchShell
    controller={controller}
    title={adapter.pageTitle}
    description={adapter.pageDescription}
    renderEditorExtras={(draft) => (
      <>
        {sourceNote && <SourcePreviewCard note={sourceNote} />}
        {assetPanels}
      </>
    )}
    renderAssistantExtras={(draft) => (
      <>
        {rewriteControls}
        {titleTagGenerators}
        {publishControls}
      </>
    )}
  />
);
```

Make `frontend/src/pages/platforms/xhs/drafts-page.tsx` a compatibility re-export so there is one XHS implementation to maintain.

```ts
export { XhsDraftsPage } from "./rewrite-page";
```

- [ ] **Step 2: Run the frontend build and confirm the XHS page still compiles**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS, with the XHS route still rendering the same behaviors through the shared shell.

- [ ] **Step 3: Move any XHS page-local state that the shared controller now owns out of the old render tree**

Delete the duplicated list/selection/save state from `rewrite-page.tsx` once the controller supplies it, but keep the XHS-specific source-note and media helpers where the adapter shell still needs them. Do not delete the existing XHS draft actions; just move them behind the new shell boundary.

- [ ] **Step 4: Commit the XHS migration**

```bash
git add frontend/src/pages/platforms/xhs/rewrite-page.tsx frontend/src/pages/platforms/xhs/drafts-page.tsx frontend/src/pages/platforms/xhs/xhs-draft-workbench-adapter.ts

git commit -m "feat: migrate xhs drafts to shared workbench"
```

---

### Task 3: Move the WeChat drafts section onto the shared shell

**Files:**
- Create: `frontend/src/pages/wechat-official/wechat-official-draft-workbench.tsx`
- Create: `frontend/src/pages/wechat-official/wechat-official-draft-workbench-adapter.ts`
- Modify: `frontend/src/pages/wechat-official/wechat-official-dashboard.tsx:303-605`

- [ ] **Step 1: Write the WeChat adapter and the draft-workbench wrapper**

The WeChat drafts workbench must only read independent drafts. It must not reuse the content-library candidate list as draft data, and it must not depend on `source_note_id` for page logic.

```ts
// frontend/src/pages/wechat-official/wechat-official-draft-workbench-adapter.ts
import type { WechatOfficialDraft } from "../../types";
import {
  deleteDraft,
  duplicateDraft,
  fetchDrafts,
  dryRunWechatOfficialDraft,
  updateDraft,
} from "../../lib/api";
import type { DraftWorkbenchAdapter } from "../../components/draft-workbench/draft-workbench-types";

export function createWechatOfficialDraftWorkbenchAdapter(): DraftWorkbenchAdapter<WechatOfficialDraft> {
  return {
    platform: "wechat_official",
    pageTitle: "公众号草稿工坊",
    pageDescription: "这里只管理独立草稿；从内容库生成后不保留引用关系。",
    capabilities: {
      canCreateFromSource: false,
      canDuplicate: true,
      canDelete: true,
      canDryRun: true,
      canSendToPublish: false,
    },
    loadDrafts: async () => (await fetchDrafts("wechat_official")).items.map((draft) => ({
      id: draft.id,
      platform: "wechat_official",
      title: draft.title,
      body: draft.body,
      tags: draft.tags,
      created_at: draft.created_at,
    })),
    saveDraft: async (draftId, patch) => await updateDraft(draftId, patch),
    duplicateDraft: async (draftId) => await duplicateDraft(draftId),
    deleteDraft: async (draftId) => {
      await deleteDraft(draftId);
    },
    dryRunDraft: async (draftId, payload) => await dryRunWechatOfficialDraft(draftId, payload ?? {}),
    getListSubtitle: (draft) => draft.created_at,
    getEmptyState: () => ({
      title: "还没有公众号草稿",
      description: "先从内容库生成一个独立草稿，或者直接等待新的草稿入库。",
    }),
  };
}
```

```tsx
// frontend/src/pages/wechat-official/wechat-official-draft-workbench.tsx
export function WechatOfficialDraftWorkbench() {
  const adapter = useMemo(() => createWechatOfficialDraftWorkbenchAdapter(), []);
  const controller = useDraftWorkbench(adapter);

  return (
    <DraftWorkbenchShell
      controller={controller}
      title={adapter.pageTitle}
      description={adapter.pageDescription}
      renderAssistantExtras={(draft) => <WechatDryRunPanel draft={draft} />}
    />
  );
}
```

Replace the current drafts branch in `wechat-official-dashboard.tsx` with that wrapper, and keep the content-library candidate list on the library/discovery sections only. The drafts section should load `fetchDrafts("wechat_official")` through the adapter and should never render `contentItems` as draft cards.

```tsx
{showDrafts ? (
  <WechatOfficialDraftWorkbench />
) : (
  displayedItems.map((item) => (
    <WechatContentCard key={item.article.id} item={item} />
  ))
)}
```

- [ ] **Step 2: Run the frontend build and confirm the WeChat branch still compiles**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS, with the WeChat drafts section rendering the shared shell and no longer depending on the old draft-specific state in the dashboard.

- [ ] **Step 3: Remove the stale WeChat draft-specific state from the dashboard once the wrapper owns it**

Delete the dashboard-local `wechatDrafts`, `isDraftsLoading`, and `draftsError` state after the wrapper owns draft loading and dry-run. Keep the rest of the WeChat dashboard behavior intact.

- [ ] **Step 4: Commit the WeChat migration**

```bash
git add frontend/src/pages/wechat-official/wechat-official-dashboard.tsx frontend/src/pages/wechat-official/wechat-official-draft-workbench.tsx frontend/src/pages/wechat-official/wechat-official-draft-workbench-adapter.ts

git commit -m "feat: migrate wechat drafts to shared workbench"
```

---

### Task 4: Verify the shared workbench end to end

**Files:**
- No code changes expected

- [ ] **Step 1: Run the focused backend regression suite**

Run:

```bash
pytest tests/backend/test_wechat_official_drafts.py -v
```

Expected: PASS, proving the WeChat draft flow still stays source-free and independent of the content library.

- [ ] **Step 2: Run the frontend production build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS, with the shared shell, adapters, and both platform workbench wrappers compiling cleanly.

- [ ] **Step 3: Start the app and smoke the two draft routes manually**

Run:

```bash
python main.py --with-frontend
```

Expected: backend on `http://127.0.0.1:18081` and frontend on `http://127.0.0.1:18080`.

Then open:

- `/platforms/xhs/drafts` — confirm the XHS three-column workbench still shows the draft list, editor, and assistant, with XHS-specific actions intact.
- `/platforms/wechat-official/drafts` — confirm the WeChat drafts section shows independent drafts only, not content-library candidates, and that dry-run is still available.

- [ ] **Step 4: Check the working tree for accidental edits**

Run:

```bash
git diff --check
```

Expected: no whitespace or patch-format errors.

- [ ] **Step 5: Mark the implementation complete with a clean summary commit if any verification step changed code**

If verification forces any last-minute fix, commit it immediately. If verification is clean, no extra commit is needed.

---

## Self-review

### Spec coverage

- Shared shell + adapter architecture: covered by Task 1.
- XHS keeps existing semantics but shares the shell: covered by Task 2.
- WeChat shows only independent drafts and no content-library candidates in the drafts area: covered by Task 3.
- Future platform extensibility through adapter-only integration: covered by the shared contract in Task 1.
- Validation and user-facing smoke checks: covered by Task 4.

### Placeholder scan

- No `TBD`, `TODO`, or unnamed helper methods in the plan.
- No ambiguous "similar to" references.
- No missing file paths.

### Type consistency

- `DraftWorkbenchAdapter`, `DraftWorkbenchController`, `DraftWorkbenchShell`, and `useDraftWorkbench` are named consistently across all tasks.
- `WechatOfficialDraftWorkbench` and `createWechatOfficialDraftWorkbenchAdapter` are used consistently in the WeChat task.
- `XhsDraftsPage` remains the route-facing export name so the router does not need to change.

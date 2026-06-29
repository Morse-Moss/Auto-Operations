# XHS 图片工坊草稿 AI 改图定稿 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the XHS image studio behave as a draft image finalization page: AI-edited images are saved back to the current draft, replace the referenced originals in the final publish queue, and are reliably sendable to publish center.

**Architecture:** Extract the queue/candidate rules into a small pure helper module, then wire `XhsImageStudioPage` to use those helpers for initial selection, AI generation success, manual upload, and publish validation. Keep backend behavior unchanged unless tests prove a missing API contract; use existing `addDraftAsset`, `fetchDraftAssets`, `startImageGenerationTask`, and `sendDraftToPublish` APIs.

**Tech Stack:** React + TypeScript + Vite + Ant Design frontend; existing FastAPI draft asset APIs; Node static/unit frontend tests; `npm --prefix frontend run build` for type/build verification.

---

## Scope and file map

**Spec:** `docs/superpowers/specs/2026-06-27-xhs-image-studio-draft-ai-finalization-design.md`

**Create:**
- `frontend/src/pages/platforms/xhs/image-studio-finalization.ts` — pure candidate/final-publish queue helpers.
- `frontend/tests/xhs-image-studio-finalization.test.ts` — functional tests for helper behavior.

**Modify:**
- `frontend/src/components/image-studio/draft-image-studio-context.ts` — add `ai_edit` as a valid candidate source if helper/page needs to persist AI edit candidates in draft context.
- `frontend/src/pages/platforms/xhs/xhs-image-studio-context.ts` — include `ai_edit` in XHS candidate context filtering.
- `frontend/src/pages/platforms/xhs/image-studio-page.tsx` — use helper functions; save AI edits back to current draft; update candidate list and final queue; validate publish paths.
- `frontend/tests/xhs-image-studio-draft-context.test.ts` — update static coverage for route recovery, multi-select, AI edit label, auto save-to-draft, and publish validation.

**Do not modify:**
- `apis/`, `xhs_utils/`, `static/`.
- Real XHS publish execution code.
- WeChat Official image studio behavior except preserving its existing branch in shared page code.

**Git safety:** This repo currently has unrelated dirty files. Stage only files in this plan. Do not commit unless the user explicitly authorizes commit.

---

## Task 1: Add pure finalization helper and tests

**Files:**
- Create: `frontend/src/pages/platforms/xhs/image-studio-finalization.ts`
- Create: `frontend/tests/xhs-image-studio-finalization.test.ts`

- [ ] **Step 1: Write the failing helper tests**

Create `frontend/tests/xhs-image-studio-finalization.test.ts` with this content:

```ts
import assert from "node:assert/strict";

import {
  buildInitialFinalPublishImages,
  candidateImageSourceLabel,
  candidateToFinalImage,
  fileNameFromMediaPath,
  replaceReferenceSelectionsWithGenerated,
  validateFinalPublishImages,
  upsertCandidateImage,
  type FinalPublishImage,
  type XhsFinalizationCandidateImage,
} from "../src/pages/platforms/xhs/image-studio-finalization.ts";

const candidates: XhsFinalizationCandidateImage[] = [
  { id: 1, url: "/api/files/media/u1_draft-a.jpg", local_path: "u1_draft-a.jpg", source: "draft_asset" },
  { id: 2, url: "/api/files/media/u1_draft-b.jpg", local_path: "u1_draft-b.jpg", source: "draft_asset" },
  { url: "https://example.test/source.jpg", source: "source_note" },
];

const initial = buildInitialFinalPublishImages(candidates);
assert.deepEqual(
  initial.map((image) => image.publishPath),
  ["/api/files/media/u1_draft-a.jpg", "/api/files/media/u1_draft-b.jpg"],
  "Initial final publish queue should include all draft assets",
);
assert.deepEqual(
  initial.map((image) => image.source),
  ["draft_asset", "draft_asset"],
  "Initial final publish queue should not include source note images",
);

const aiEdit = candidateToFinalImage(
  { id: 3, url: "/api/files/media/u1_ai-edit.jpg", local_path: "u1_ai-edit.jpg", source: "ai_edit" },
  3,
);
assert.ok(aiEdit, "AI edit candidate should become a final publish image");
assert.equal(aiEdit.label, "AI 改图 4");

const replaced = replaceReferenceSelectionsWithGenerated(
  [
    ...initial,
    { key: "https://example.test/source.jpg", url: "https://example.test/source.jpg", publishPath: "https://example.test/source.jpg", source: "source_note", label: "原笔记案例图 3" },
  ],
  ["/api/files/media/u1_draft-a.jpg", "/api/files/media/u1_draft-b.jpg"],
  aiEdit,
);
assert.deepEqual(
  replaced.map((image) => image.publishPath),
  ["https://example.test/source.jpg", "/api/files/media/u1_ai-edit.jpg"],
  "AI edit should replace only this generation's reference images and keep unrelated selections",
);

const upserted = upsertCandidateImage(candidates, { id: 3, url: "/api/files/media/u1_ai-edit.jpg", local_path: "u1_ai-edit.jpg", source: "ai_edit" });
assert.equal(upserted.length, 4);
assert.equal(upsertCandidateImage(upserted, { id: 3, url: "/api/files/media/u1_ai-edit.jpg", local_path: "u1_ai-edit.jpg", source: "ai_edit" }).length, 4);

assert.equal(fileNameFromMediaPath("/api/files/media/u1_ai-edit.jpg"), "u1_ai-edit.jpg");
assert.equal(fileNameFromMediaPath("E:\\data\\media\\u1_ai-edit.jpg"), "u1_ai-edit.jpg");

assert.equal(candidateImageSourceLabel("ai_edit"), "AI 改图");
assert.equal(candidateImageSourceLabel("draft_asset"), "草稿素材");

const invalid: FinalPublishImage[] = [
  { key: "blob:preview", url: "blob:preview", publishPath: "blob:preview", source: "generated", label: "预览图" },
];
assert.deepEqual(validateFinalPublishImages(invalid), { ok: false, invalidCount: 1 });
assert.deepEqual(validateFinalPublishImages(replaced), { ok: true, invalidCount: 0 });

console.log("xhs-image-studio finalization tests passed");
```

- [ ] **Step 2: Run the helper test to verify RED**

Run:

```powershell
node "E:\小红书\frontend\tests\xhs-image-studio-finalization.test.ts"
```

Expected: FAIL because `frontend/src/pages/platforms/xhs/image-studio-finalization.ts` does not exist or does not export the tested helpers.

- [ ] **Step 3: Create the helper implementation**

Create `frontend/src/pages/platforms/xhs/image-studio-finalization.ts` with this content:

```ts
import type { XhsImageStudioCandidateImage } from "./xhs-image-studio-context";

export type XhsFinalizationCandidateImage = XhsImageStudioCandidateImage;

export type FinalPublishImage = {
  key: string;
  url: string;
  publishPath: string;
  source: "draft_asset" | "source_note" | "manual" | "generated" | "asset" | "ai_edit";
  label: string;
};

export function candidateImageSourceLabel(source: XhsFinalizationCandidateImage["source"] | FinalPublishImage["source"]): string {
  if (source === "draft_asset") return "草稿素材";
  if (source === "source_note") return "原笔记案例图";
  if (source === "ai_edit") return "AI 改图";
  if (source === "asset") return "AI 图片资产";
  if (source === "generated") return "AI 生成图";
  return "手动添加";
}

export function candidateToFinalImage(image: XhsFinalizationCandidateImage, index: number): FinalPublishImage | null {
  if (!image.url) return null;
  return {
    key: image.url,
    url: image.url,
    publishPath: image.url,
    source: image.source,
    label: `${candidateImageSourceLabel(image.source)} ${index + 1}`,
  };
}

export function buildInitialFinalPublishImages(candidates: XhsFinalizationCandidateImage[]): FinalPublishImage[] {
  return candidates
    .filter((image) => image.source === "draft_asset" || image.source === "ai_edit")
    .map((image, index) => candidateToFinalImage(image, index))
    .filter((image): image is FinalPublishImage => Boolean(image));
}

export function fileNameFromMediaPath(filePath: string): string {
  return filePath.replace(/^\/api\/files\/media\//, "").split(/[\\/]/).pop() ?? filePath;
}

export function isPublishableFinalImagePath(value: string): boolean {
  return value.startsWith("/api/files/media/") || value.startsWith("http://") || value.startsWith("https://");
}

export function validateFinalPublishImages(images: FinalPublishImage[]): { ok: boolean; invalidCount: number } {
  const invalidCount = images.filter((image) => !isPublishableFinalImagePath(image.publishPath)).length;
  return { ok: invalidCount === 0, invalidCount };
}

export function replaceReferenceSelectionsWithGenerated(
  current: FinalPublishImage[],
  referenceUrls: string[],
  generated: FinalPublishImage,
): FinalPublishImage[] {
  const referenceSet = new Set(referenceUrls);
  const withoutReferences = current.filter((image) => !referenceSet.has(image.publishPath) && !referenceSet.has(image.url));
  if (withoutReferences.some((image) => image.publishPath === generated.publishPath)) return withoutReferences;
  return [...withoutReferences, generated];
}

export function upsertCandidateImage(
  current: XhsFinalizationCandidateImage[],
  candidate: XhsFinalizationCandidateImage,
): XhsFinalizationCandidateImage[] {
  if (current.some((image) => image.url === candidate.url)) {
    return current.map((image) => (image.url === candidate.url ? { ...image, ...candidate } : image));
  }
  return [...current, candidate];
}
```

- [ ] **Step 4: Run the helper test to verify GREEN**

Run:

```powershell
node "E:\小红书\frontend\tests\xhs-image-studio-finalization.test.ts"
```

Expected: PASS with `xhs-image-studio finalization tests passed`.

- [ ] **Step 5: Checkpoint**

Do not commit unless the user has explicitly authorized committing. Record that Task 1 changed:

```text
frontend/src/pages/platforms/xhs/image-studio-finalization.ts
frontend/tests/xhs-image-studio-finalization.test.ts
```

---

## Task 2: Allow and persist `ai_edit` candidate source

**Files:**
- Modify: `frontend/src/components/image-studio/draft-image-studio-context.ts`
- Modify: `frontend/src/pages/platforms/xhs/xhs-image-studio-context.ts`
- Modify: `frontend/tests/xhs-image-studio-draft-context.test.ts`

- [ ] **Step 1: Extend the static test for `ai_edit` source**

Append these assertions before the final `console.log` in `frontend/tests/xhs-image-studio-draft-context.test.ts`:

```ts
const sharedContextPath = path.resolve(__dirname, "../src/components/image-studio/draft-image-studio-context.ts");
const xhsContextPath = path.resolve(__dirname, "../src/pages/platforms/xhs/xhs-image-studio-context.ts");
const sharedContextSource = readFileSync(sharedContextPath, "utf8");
const xhsContextSource = readFileSync(xhsContextPath, "utf8");

assert.match(
  sharedContextSource,
  /"ai_edit"/,
  "Shared draft image studio context should allow persisted AI edit candidates",
);

assert.match(
  xhsContextSource,
  /image\.source === "ai_edit"/,
  "XHS image studio context should preserve AI edit candidates when loading from session storage",
);
```

- [ ] **Step 2: Run the static test to verify RED**

Run:

```powershell
node "E:\小红书\frontend\tests\xhs-image-studio-draft-context.test.ts"
```

Expected: FAIL because `ai_edit` is not yet an allowed candidate source or is not preserved by XHS context filtering.

- [ ] **Step 3: Update shared candidate sources**

In `frontend/src/components/image-studio/draft-image-studio-context.ts`, update `DRAFT_IMAGE_STUDIO_CANDIDATE_IMAGE_SOURCES` so it includes `ai_edit`:

```ts
const DRAFT_IMAGE_STUDIO_CANDIDATE_IMAGE_SOURCES = [
  "draft_asset",
  "source_note",
  "article_cover",
  "snapshot_image",
  "manual",
  "ai_edit",
] as const;
```

Keep the existing `isCandidateImageSource` implementation; it will now accept `ai_edit` through the source array.

- [ ] **Step 4: Update XHS context filtering**

In `frontend/src/pages/platforms/xhs/xhs-image-studio-context.ts`, update the source union:

```ts
export type XhsImageStudioCandidateImage = DraftImageStudioCandidateImage & {
  source: "draft_asset" | "source_note" | "manual" | "ai_edit";
};
```

Update the `toXhsContext` filter:

```ts
candidate_images: context.candidate_images.filter((image): image is XhsImageStudioCandidateImage =>
  image.source === "draft_asset" || image.source === "source_note" || image.source === "manual" || image.source === "ai_edit",
),
```

- [ ] **Step 5: Run the static and helper tests to verify GREEN**

Run:

```powershell
node "E:\小红书\frontend\tests\xhs-image-studio-draft-context.test.ts"
node "E:\小红书\frontend\tests\xhs-image-studio-finalization.test.ts"
```

Expected: both PASS.

- [ ] **Step 6: Checkpoint**

Do not commit unless the user has explicitly authorized committing. Record that Task 2 changed:

```text
frontend/src/components/image-studio/draft-image-studio-context.ts
frontend/src/pages/platforms/xhs/xhs-image-studio-context.ts
frontend/tests/xhs-image-studio-draft-context.test.ts
```

---

## Task 3: Wire XHS image studio to save AI edits back to draft and replace reference selections

**Files:**
- Modify: `frontend/src/pages/platforms/xhs/image-studio-page.tsx`
- Modify: `frontend/tests/xhs-image-studio-draft-context.test.ts`

- [ ] **Step 1: Extend static test for page integration**

Append these assertions before the final `console.log` in `frontend/tests/xhs-image-studio-draft-context.test.ts`:

```ts
assert.match(
  source,
  /import \{[\s\S]*replaceReferenceSelectionsWithGenerated[\s\S]*upsertCandidateImage[\s\S]*validateFinalPublishImages[\s\S]*\} from "\.\/image-studio-finalization";/,
  "Image studio page should use finalization helpers for AI edit queue behavior and publish validation",
);

assert.match(
  source,
  /const addedAsset = await addDraftAsset\(draftContext\.draft_id, \{[\s\S]*asset_type: "image",[\s\S]*local_path: fileNameFromMediaPath\(mediaPath\),[\s\S]*\}\);/,
  "AI edit generation should save generated media back to the current draft as a DraftAsset",
);

assert.match(
  source,
  /source: "ai_edit"/,
  "AI edit generation should add a candidate tagged as AI 改图",
);

assert.match(
  source,
  /replaceReferenceSelectionsWithGenerated\([\s\S]*referenceImages,[\s\S]*generatedFinalImage[\s\S]*\)/,
  "AI edit generation should replace this generation's reference images in the final publish queue",
);

assert.match(
  source,
  /saveImageStudioDraftContext\(\{[\s\S]*candidate_images: nextCandidates,[\s\S]*\}\)/,
  "AI edit generation should persist updated draft candidate context for refresh recovery",
);

assert.match(
  source,
  /validateFinalPublishImages\(finalPublishImages\)/,
  "Sending to publish should validate final publish image paths before creating the publish job",
);
```

- [ ] **Step 2: Run the static test to verify RED**

Run:

```powershell
node "E:\小红书\frontend\tests\xhs-image-studio-draft-context.test.ts"
```

Expected: FAIL because the page does not yet save generated images back to the draft, tag them as `ai_edit`, persist updated context, or validate publish paths through the helper.

- [ ] **Step 3: Update imports in `image-studio-page.tsx`**

In `frontend/src/pages/platforms/xhs/image-studio-page.tsx`, update the XHS context import to include `saveImageStudioDraftContext`:

```ts
import {
  clearImageStudioDraftContext,
  loadImageStudioDraftContext,
  saveImageStudioDraftContext,
  type XhsImageStudioCandidateImage,
  type XhsImageStudioDraftContext,
} from "./xhs-image-studio-context";
```

Add the helper import:

```ts
import {
  buildInitialFinalPublishImages as buildInitialXhsFinalPublishImages,
  candidateImageSourceLabel as xhsCandidateImageSourceLabel,
  candidateToFinalImage as xhsCandidateToFinalImage,
  fileNameFromMediaPath,
  isPublishableFinalImagePath,
  replaceReferenceSelectionsWithGenerated,
  upsertCandidateImage,
  validateFinalPublishImages,
  type FinalPublishImage,
} from "./image-studio-finalization";
```

Remove the local `FinalPublishImage` type and use the imported type.

- [ ] **Step 4: Keep WeChat labels local and delegate XHS labels to helper**

Replace the current `candidateImageSourceLabel` implementation with this shape:

```ts
function candidateImageSourceLabel(source: ImageStudioDraftContext["candidate_images"][number]["source"] | FinalPublishImage["source"]): string {
  if (source === "article_cover") return "文章封面";
  if (source === "snapshot_image") return "正文配图";
  return xhsCandidateImageSourceLabel(source);
}
```

Replace the current top-level `candidateToFinalImage` implementation with this shape:

```ts
function candidateToFinalImage(
  image: ImageStudioDraftContext["candidate_images"][number],
  index: number,
): FinalPublishImage | null {
  if (image.source === "article_cover" || image.source === "snapshot_image") return null;
  return xhsCandidateToFinalImage(image as XhsImageStudioCandidateImage, index);
}
```

Replace `buildInitialFinalPublishImages` with this shape:

```ts
function buildInitialFinalPublishImages(context: ImageStudioDraftContext): FinalPublishImage[] {
  if (isWechatOfficialDraftContext(context)) return [];
  return buildInitialXhsFinalPublishImages(context.candidate_images);
}
```

- [ ] **Step 5: Add a draft context candidate updater inside the component**

Inside `XhsImageStudioPage`, near `selectAllDraftAssetImages`, add:

```ts
function updateXhsDraftCandidates(nextCandidates: XhsImageStudioCandidateImage[]) {
  if (!draftContext || isWechatOfficialDraftContext(draftContext)) return;
  const nextContext: XhsImageStudioDraftContext = {
    ...draftContext,
    candidate_images: nextCandidates,
    created_at: Date.now(),
  };
  setDraftContext(nextContext);
  saveImageStudioDraftContext(nextContext);
}
```

- [ ] **Step 6: Replace AI generation success handling**

In `handleGenerate`, replace the `completed` branch after `const result = imageResultFromTask(task);` with this behavior:

```ts
const mediaPath = generatedPublishMediaPath(result);
const publishPath = mediaPath ?? result.url;
setGeneratedPreview(publishPath);
setGeneratedMediaPath(mediaPath);

if (draftContext && !isWechatOfficialDraftContext(draftContext)) {
  if (!mediaPath || !isPublishableFinalImagePath(mediaPath)) {
    throw new Error("AI 图片已生成，但未保存为可发布素材，请重新生成并开启保存到资产。");
  }
  let addedAsset;
  try {
    addedAsset = await addDraftAsset(draftContext.draft_id, {
      asset_type: "image",
      local_path: fileNameFromMediaPath(mediaPath),
    });
  } catch {
    throw new Error("AI 改图生成成功，但保存到草稿失败，已保留预览，请重试保存。");
  }
  const aiEditCandidate: XhsImageStudioCandidateImage = {
    id: addedAsset.id,
    url: addedAsset.url,
    local_path: addedAsset.local_path,
    source: "ai_edit",
  };
  const nextCandidates = upsertCandidateImage(draftContext.candidate_images, aiEditCandidate);
  updateXhsDraftCandidates(nextCandidates);
  const generatedFinalImage = xhsCandidateToFinalImage(aiEditCandidate, nextCandidates.length - 1);
  if (generatedFinalImage) {
    setFinalPublishImages((prev) => replaceReferenceSelectionsWithGenerated(prev, referenceImages, generatedFinalImage));
  }
  setMessage("AI 改图已生成，并保存到当前草稿；已替换本次参考图的发布选择。");
} else if (isPublishableFinalImagePath(publishPath)) {
  addFinalPublishImage({
    url: publishPath,
    publishPath,
    source: "generated",
    label: "AI 生成图",
  });
  setMessage("图片生成成功。");
}

if (result.asset) {
  setAssets((prev) => [result.asset!, ...prev]);
} else {
  void loadAssets();
}
return;
```

Keep the existing failed/cancelled/exhausted handling and polling loop.

- [ ] **Step 7: Validate publish queue before sending**

In `handleSendFinalImagesToPublish`, after the empty queue check and before `setIsSendingPublish(true)`, add:

```ts
const validation = validateFinalPublishImages(finalPublishImages);
if (!validation.ok) {
  setError(`有 ${validation.invalidCount} 张图片不是可发布素材，请重新保存、上传或移除后再送发布中心。`);
  return;
}
```

- [ ] **Step 8: Run static and helper tests to verify GREEN**

Run:

```powershell
node "E:\小红书\frontend\tests\xhs-image-studio-finalization.test.ts"
node "E:\小红书\frontend\tests\xhs-image-studio-draft-context.test.ts"
```

Expected: both PASS.

- [ ] **Step 9: Checkpoint**

Do not commit unless the user has explicitly authorized committing. Record that Task 3 changed:

```text
frontend/src/pages/platforms/xhs/image-studio-page.tsx
frontend/tests/xhs-image-studio-draft-context.test.ts
```

---

## Task 4: Make manual upload and UI copy match the draft finalization model

**Files:**
- Modify: `frontend/src/pages/platforms/xhs/image-studio-page.tsx`
- Modify: `frontend/tests/xhs-image-studio-draft-context.test.ts`

- [ ] **Step 1: Extend static test for manual upload and UI copy**

Append these assertions before the final `console.log` in `frontend/tests/xhs-image-studio-draft-context.test.ts`:

```ts
assert.match(
  source,
  /const manualCandidate: XhsImageStudioCandidateImage = \{[\s\S]*source: "manual",[\s\S]*\};/,
  "Manual uploads in draft-linked image studio should also become draft context candidates",
);

assert.match(
  source,
  /updateXhsDraftCandidates\(upsertCandidateImage\(draftContext\.candidate_images, manualCandidate\)\)/,
  "Manual upload candidates should be persisted into the current draft image studio context",
);

assert.match(
  source,
  />生成 AI 改图</,
  "Draft-linked image studio generation button should communicate that it creates an AI edit",
);

assert.match(
  source,
  /AI 改图/,
  "Image studio UI should display AI edit source copy",
);
```

- [ ] **Step 2: Run the static test to verify RED**

Run:

```powershell
node "E:\小红书\frontend\tests\xhs-image-studio-draft-context.test.ts"
```

Expected: FAIL because manual uploads are not persisted as draft context candidates and generation button copy is still generic.

- [ ] **Step 3: Update manual upload handling**

In `handleUploadFile`, after creating `newItem`, add draft-context candidate persistence when in XHS draft context:

```ts
if (draftContext && !isWechatOfficialDraftContext(draftContext)) {
  const manualCandidate: XhsImageStudioCandidateImage = {
    url: uploaded.download_url,
    local_path: uploaded.file_name,
    source: "manual",
  };
  updateXhsDraftCandidates(upsertCandidateImage(draftContext.candidate_images, manualCandidate));
}
```

Keep the existing `setUserImages` and `addFinalPublishImage` behavior so uploaded images still default into the final publish queue.

- [ ] **Step 4: Update generation button copy**

In the AI image generation card, change the main generation button label to reflect draft context:

```tsx
{draftContext && !isWechatOfficialDraftContext(draftContext) ? "生成 AI 改图" : "生成"}
```

Keep the button icon and loading state unchanged.

- [ ] **Step 5: Run static tests to verify GREEN**

Run:

```powershell
node "E:\小红书\frontend\tests\xhs-image-studio-draft-context.test.ts"
```

Expected: PASS.

- [ ] **Step 6: Checkpoint**

Do not commit unless the user has explicitly authorized committing. Record that Task 4 changed:

```text
frontend/src/pages/platforms/xhs/image-studio-page.tsx
frontend/tests/xhs-image-studio-draft-context.test.ts
```

---

## Task 5: Full verification

**Files:**
- Verify all files from Tasks 1-4.

- [ ] **Step 1: Run focused frontend tests**

Run:

```powershell
node "E:\小红书\frontend\tests\xhs-image-studio-finalization.test.ts"
node "E:\小红书\frontend\tests\xhs-image-studio-draft-context.test.ts"
node "E:\小红书\frontend\tests\xhs-draft-workbench-preview.test.ts"
```

Expected:

```text
xhs-image-studio finalization tests passed
xhs-image-studio draft context tests passed
xhs-draft-workbench preview tests passed
```

- [ ] **Step 2: Run frontend build**

Run:

```powershell
npm --prefix "E:\小红书\frontend" run build
```

Expected: TypeScript and Vite build pass. The existing Vite chunk-size warning is acceptable if it is the only warning.

- [ ] **Step 3: Optional browser smoke if services are running**

If `18080/18081` services are running, manually verify in browser:

```text
1. Open 小红书草稿工坊.
2. Select a draft with at least two draft images.
3. Click 送入图片工坊.
4. Confirm 来自草稿 appears and draft assets are selected.
5. Use selected reference images to generate AI 改图.
6. Confirm generated image appears as AI 改图, is saved back to draft candidates, and replaces reference selections in final publish queue.
7. Click 送入发布中心.
8. Confirm publish center receives AI 改图 path in the pending job and does not execute real publish.
```

Do not call paid/real provider APIs for this smoke unless the user explicitly authorizes that specific API call. If no safe image generation provider is available, skip Step 5.3 and report it as skipped.

- [ ] **Step 4: Report verification and changed files**

Report:

```text
Verification:
- node frontend/tests/xhs-image-studio-finalization.test.ts: PASS
- node frontend/tests/xhs-image-studio-draft-context.test.ts: PASS
- node frontend/tests/xhs-draft-workbench-preview.test.ts: PASS
- npm --prefix frontend run build: PASS, existing chunk-size warning only
- Browser smoke: PASS or skipped with reason

Changed files:
- frontend/src/pages/platforms/xhs/image-studio-finalization.ts
- frontend/src/pages/platforms/xhs/image-studio-page.tsx
- frontend/src/pages/platforms/xhs/xhs-image-studio-context.ts
- frontend/src/components/image-studio/draft-image-studio-context.ts
- frontend/tests/xhs-image-studio-finalization.test.ts
- frontend/tests/xhs-image-studio-draft-context.test.ts
```

Do not claim completion if any required focused test or build fails.

---

## Plan self-review

**Spec coverage:**
- Stable draft candidate display: covered by existing route recovery work and Task 3 context persistence.
- Multi-select final publish queue: covered by helper tests and page wiring.
- AI edit auto-save to draft: Task 3 uses `addDraftAsset` with generated media path.
- AI edit label: Task 1/2 helper/context source and Task 4 UI/static coverage.
- Replace this generation's reference images: Task 1 helper and Task 3 integration.
- Publish path validation: Task 1 helper and Task 3 preflight check.
- Manual upload candidate behavior: Task 4.
- No real publish / no SDK changes: captured in scope and verification constraints.

**Placeholder scan:** No TBD/TODO/fill-in placeholders. Every task has concrete files, snippets, commands, and expected results.

**Type consistency:** `ai_edit` is added to shared source, XHS source union, helper candidate source, and page final image source. `FinalPublishImage` has a single exported definition in the helper and is imported by the page.

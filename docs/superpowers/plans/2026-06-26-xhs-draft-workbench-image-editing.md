# XHS Draft Workbench Image Editing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the XHS draft workbench into a real image+text draft workspace: draft images reliably enter image studio, tags can be adopted into body, layout prioritizes source content/current draft/AI assistant, and draft images can be added, deleted, and AI-edited.

**Architecture:** Keep the current FastAPI/React/SQLAlchemy architecture. Do not add image version tables. Make `DraftAsset` the working image source in draft workbench; image edits create new `DraftAsset` rows and preserve originals. Add one backend localize endpoint so external draft images can become server-managed media before image-to-image generation.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, React, Vite, Ant Design, existing `/ai/images/generate-async` task flow.

---

## Scope and safety

Before implementation starts, report the current workspace path and branch. This plan was written for the root workspace `E:\小红书` on `master`; do not use or create a worktree unless the user explicitly requests it.

### In scope

- `DraftAsset` image URL resolution shared by draft workbench and image studio context.
- `POST /drafts/{draft_id}/assets/{asset_id}/localize` for converting external image URLs to local media.
- XHS draft workbench layout redesign:
  - top draft selector;
  - left source-content panel;
  - middle draft editor and draft image asset panel;
  - right AI assistant with rewrite/title/tag candidates.
- Tag candidate click behavior: append hashtag to body and add to draft tags.
- Draft image panel:
  - show images;
  - add by URL;
  - add by upload;
  - delete;
  - edit via image-to-image; edited image is added as a new draft asset.
- Verification tests and frontend build.

### Out of scope

- No real XHS publish action.
- No changes under `apis/`, `xhs_utils/`, or `static/`.
- No image version table.
- No bidirectional sync between draft workbench and image studio.
- No provider bypass, CAPTCHA bypass, high-frequency automation, or risk-control evasion.
- Do not delete source note assets when deleting draft assets.

### Important current repo state

The repo has many unrelated dirty files from other threads. During implementation and closeout, stage explicit files/hunks only. Do not use `git add .` or broad staging.

---

## Files overview

### Backend

- Modify: `backend/app/api/drafts.py`
  - Add localize endpoint.
  - Reuse `download_asset_to_local`.
  - Keep draft ownership checks.
- Test: `tests/backend/test_drafts.py`
  - Add localize endpoint tests.
  - Add delete-does-not-delete-source-note-asset test if not already covered.

### Frontend shared helpers/API

- Modify: `frontend/src/components/image-studio/draft-image-studio-context.ts`
  - Add/export `draftAssetImageUrl(asset)`.
  - Update `draftAssetToImageStudioCandidate` to use resolver.
- Modify: `frontend/src/lib/api.ts`
  - Add `localizeDraftAsset(draftId, assetId)`.
  - Reuse existing `uploadAssetFile`, `addDraftAsset`, `deleteDraftAsset`, `startImageGenerationTask`, `fetchTask`.
- Test: `frontend/tests/xhs-draft-workbench-preview.test.ts` or a new focused test file.
  - Add static/source tests for resolver behavior and workbench controls.

### Frontend draft workbench shell

- Modify: `frontend/src/components/draft-workbench/draft-workbench-shell.tsx`
  - Replace fixed left draft list with top draft selector.
  - Add `renderSourcePanel` slot.
  - Keep shared shell platform-neutral.
- Modify: `frontend/src/components/draft-workbench/draft-workbench-types.ts`
  - Add optional shell render slots if needed.

### XHS workbench

- Modify: `frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx`
  - Use `draftAssetImageUrl`.
  - Move source content to `renderSourcePanel`.
  - Move title/tag candidates to `renderAssistantExtras`.
  - Add tag candidate adoption.
  - Add current-tag deletion.
  - Add draft image asset panel.
  - Add image edit modal and async generation polling.
  - Ensure send-to-image-studio uses latest draft assets and resolver.

### Image studio

- Modify only if needed: `frontend/src/pages/platforms/xhs/image-studio-page.tsx`
  - Confirm it reads candidate images from context and defaults first candidate into final publish images/reference images.
  - Avoid broad refactors.

---

## Task 1: Backend localize endpoint for draft assets

**Files:**

- Modify: `backend/app/api/drafts.py`
- Test: `tests/backend/test_drafts.py`

### Behavior

Add:

```text
POST /drafts/{draft_id}/assets/{asset_id}/localize
```

Rules:

1. Draft must belong to current user.
2. Asset must belong to draft.
3. Asset must be `asset_type == "image"`.
4. If `asset.local_path` exists, return `_serialize_draft_asset(asset)` unchanged.
5. If `asset.url` is not `http://` or `https://`, return 400.
6. Download external URL using `download_asset_to_local(asset.url, current_user.id, "image", platform="xhs")`.
7. If download returns no file name, return 400 with:
   ```text
   图片本地化失败，请先上传本地图或更换图片。
   ```
8. Save filename to `asset.local_path`, commit, refresh, return serialized asset.

### Steps

- [ ] **Step 1: Add failing backend tests**

Add tests in `tests/backend/test_drafts.py`:

```python
def test_localize_draft_asset_returns_existing_local_path(client, auth_headers, db_session):
    # Arrange user, draft, DraftAsset(asset_type="image", url="https://example.com/a.jpg", local_path="xhs_user_1_asset_existing.jpg")
    # Act POST /api/drafts/{draft.id}/assets/{asset.id}/localize
    # Assert 200, local_path unchanged, url == /api/files/media/xhs_user_1_asset_existing.jpg
```

```python
def test_localize_draft_asset_downloads_external_url(client, auth_headers, monkeypatch, db_session):
    # Arrange image asset with url=https://example.com/a.jpg and no local_path
    # monkeypatch backend.app.api.drafts.download_asset_to_local to return "xhs_user_1_asset_new.jpg"
    # Act POST localize
    # Assert 200, local_path persisted, serialized url is /api/files/media/xhs_user_1_asset_new.jpg
```

```python
def test_localize_draft_asset_rejects_download_failure(client, auth_headers, monkeypatch, db_session):
    # monkeypatch download_asset_to_local to return None
    # Assert 400 and no local_path persisted
```

```python
def test_localize_draft_asset_rejects_other_user_asset(client, auth_headers, db_session):
    # Asset belongs to another user's draft
    # Assert 404
```

```python
def test_delete_draft_asset_does_not_delete_source_note_asset(client, auth_headers, db_session):
    # Create NoteAsset and copied DraftAsset
    # Delete DraftAsset
    # Assert DraftAsset gone, NoteAsset still exists
```

- [ ] **Step 2: Run failing tests**

Run:

```powershell
$env:PYTHONPATH = 'E:\小红书'; pytest tests/backend/test_drafts.py -q
```

Expected: localize tests fail because endpoint does not exist.

- [ ] **Step 3: Implement endpoint**

In `backend/app/api/drafts.py`, add import if missing:

```python
from backend.app.services.asset_downloader import download_asset_to_local
```

Add route near existing draft asset routes:

```python
@router.post("/{draft_id}/assets/{asset_id}/localize")
def localize_draft_asset(
    draft_id: int,
    asset_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    draft = db.get(AiDraft, draft_id)
    if draft is None or draft.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Draft not found")
    asset = db.scalars(select(DraftAsset).where(DraftAsset.id == asset_id, DraftAsset.draft_id == draft.id)).first()
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    if asset.asset_type != "image":
        raise HTTPException(status_code=400, detail="Only image draft assets can be localized")
    if asset.local_path:
        return _serialize_draft_asset(asset)
    if not asset.url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="图片本地化失败，请先上传本地图或更换图片。")
    file_name = download_asset_to_local(asset.url, current_user.id, "image", platform="xhs")
    if not file_name:
        raise HTTPException(status_code=400, detail="图片本地化失败，请先上传本地图或更换图片。")
    asset.local_path = file_name
    db.commit()
    db.refresh(asset)
    return _serialize_draft_asset(asset)
```

- [ ] **Step 4: Run tests**

Run:

```powershell
$env:PYTHONPATH = 'E:\小红书'; pytest tests/backend/test_drafts.py -q
```

Expected: pass.

---

## Task 2: Shared draft asset image URL resolver

**Files:**

- Modify: `frontend/src/components/image-studio/draft-image-studio-context.ts`
- Modify: `frontend/src/pages/platforms/xhs/xhs-image-studio-context.ts`
- Test: `frontend/tests/xhs-draft-workbench-preview.test.ts` or new `frontend/tests/draft-image-studio-context.test.ts`

### Behavior

Add a single resolver for image URL display/use:

```ts
export function draftAssetImageUrl(asset: DraftAsset): string {
  if (asset.asset_type !== "image") return "";
  if (isUsableImageUrl(asset.url)) return asset.url;
  if (isUsableImageUrl(asset.local_path)) return asset.local_path;
  if (asset.local_path.trim()) {
    const fileName = asset.local_path.replace(/^\/api\/files\/media\//, "");
    return `/api/files/media/${fileName}`;
  }
  return "";
}
```

Update:

```ts
export function draftAssetToImageStudioCandidate(asset: DraftAsset): DraftImageStudioCandidateImage | null {
  const url = draftAssetImageUrl(asset);
  if (!url) return null;
  return {
    id: asset.id,
    url,
    local_path: asset.local_path,
    source: "draft_asset",
  };
}
```

### Steps

- [ ] **Step 1: Add resolver tests**

Add tests verifying:

- image `url=https://...` returns `url`;
- image `url=/api/files/media/a.jpg` returns `url`;
- image `local_path=a.jpg` returns `/api/files/media/a.jpg`;
- image `local_path=/api/files/media/a.jpg` returns `/api/files/media/a.jpg`;
- video returns empty;
- `draftAssetToImageStudioCandidate` uses the resolver.

- [ ] **Step 2: Run tests and confirm failure**

Use this fallback order:

1. If `frontend/tests` are wired into a frontend test script, run the focused frontend test.
2. Otherwise add source-level contract assertions to `tests/backend/test_api.py` and run:

```powershell
$env:PYTHONPATH = 'E:\小红书'; pytest tests/backend/test_api.py -q
```

Expected: assertions fail before implementation because `draftAssetImageUrl` is missing and `draftAssetToImageStudioCandidate` still only checks `asset.url`.

- [ ] **Step 3: Implement resolver and update candidate conversion**

Modify `frontend/src/components/image-studio/draft-image-studio-context.ts`.

- [ ] **Step 4: Update XHS context import/export if needed**

In `frontend/src/pages/platforms/xhs/xhs-image-studio-context.ts`, re-export `draftAssetImageUrl` if XHS workbench will import from XHS-specific context.

- [ ] **Step 5: Verify**

Run focused tests and later full frontend build.

---

## Task 3: Make tag candidates adoptable and current tags removable

**Files:**

- Modify: `frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx`
- Possibly modify: `frontend/src/components/draft-workbench/draft-workbench-shell.tsx`
- Test: focused frontend/static test

### Behavior

Tag candidate click:

1. Adds tag to `controller.tags` if absent.
2. Appends `#tag` to `controller.body` if absent.
3. Does not duplicate tags or hashtags.

Current tag close:

1. Removes tag from `controller.tags`.
2. Does not mutate body automatically.

### Helper design

In XHS workbench add:

```ts
function normalizeTagName(value: string): string {
  return value.replace(/^#/, "").trim();
}

function appendHashtag(body: string, tagName: string): string {
  const clean = normalizeTagName(tagName);
  if (!clean) return body;
  const hashtag = `#${clean}`;
  if (body.includes(hashtag)) return body;
  return body.trim() ? `${body.trimEnd()}\n\n${hashtag}` : hashtag;
}
```

Adopt:

```ts
function handleAdoptTagCandidate(option: string) {
  const clean = normalizeTagName(option);
  if (!clean) return;
  controller.setTags(
    controller.tags.some((tag) => tag.name === clean)
      ? controller.tags
      : [...controller.tags, { id: clean, name: clean }],
  );
  controller.setBody(appendHashtag(controller.body, clean));
}
```

Remove current tag:

```ts
function handleRemoveTag(tagName: string) {
  controller.setTags(controller.tags.filter((tag) => tag.name !== tagName));
}
```

### Steps

- [ ] Add focused tests/static assertions for `handleAdoptTagCandidate`, `appendHashtag`, candidate buttons, and current tag `onClose`.
- [ ] Implement helper and handlers.
- [ ] Move tag candidate UI to assistant area if doing Task 5 later; for this task, behavior can be implemented before layout move.
- [ ] Verify candidate click no duplicates.

---

## Task 4: Add frontend API for localizing draft assets and draft image utilities

**Files:**

- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx`

### Behavior

Add:

```ts
export async function localizeDraftAsset(draftId: number, assetId: number): Promise<DraftAsset> {
  const response = await http.post<DraftAsset>(`/drafts/${draftId}/assets/${assetId}/localize`);
  return response.data;
}
```

Add helper in XHS workbench:

```ts
function mediaFileNameFromPath(path: string): string {
  return path.replace(/^\/api\/files\/media\//, "");
}
```

Use only for uploaded/generated server media paths.

### Steps

- [ ] Add API function.
- [ ] Add source/static test that `localizeDraftAsset` calls `/drafts/${draftId}/assets/${assetId}/localize`.
- [ ] Verify TypeScript compiles in final build.

---

## Task 5: Redesign shared DraftWorkbenchShell layout

**Files:**

- Modify: `frontend/src/components/draft-workbench/draft-workbench-types.ts`
- Modify: `frontend/src/components/draft-workbench/draft-workbench-shell.tsx`
- Modify consumers:
  - `frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx`
  - `frontend/src/pages/wechat-official/wechat-official-draft-workbench.tsx` if it uses the shell and needs compile compatibility.

### Behavior

Add optional source panel slot:

```ts
renderSourcePanel?: (draft: TDraft) => ReactNode;
```

The shell layout becomes:

```text
Header
Alerts
Draft selector card / compact list toggle
Row:
  left: source panel
  center: editor
  right: assistant
```

Draft selector:

- Display selected draft name and count.
- Button toggles a compact list using `Collapse`, `Drawer`, or inline `Card`.
- Do not keep the list as permanent left column.

### Implementation guidance

Keep shell platform-neutral. Do not import XHS-specific code into shell.

Pseudo layout:

```tsx
<Card size="small" title="当前草稿" extra={<Button onClick={() => setDraftListOpen((v) => !v)}>切换草稿</Button>}>
  <Text strong>{selectedDraft?.draft_name || selectedDraft?.title || "未选择草稿"}</Text>
  {draftListOpen ? <List ... /> : null}
</Card>

<Row gutter={16} align="stretch">
  <Col xs={24} xl={7}>{renderSourcePanel?.(selectedDraft) ?? <Empty ... />}</Col>
  <Col xs={24} xl={10}>editor</Col>
  <Col xs={24} xl={7}>assistant</Col>
</Row>
```

If no selected draft, source/editor/assistant should show empty states.

### Steps

- [ ] Update types.
- [ ] Update shell layout.
- [ ] Ensure XHS and WeChat consumers compile.
- [ ] Keep existing save/duplicate/delete/dry-run buttons in editor card.
- [ ] Verify no unrelated page behavior changes.

---

## Task 6: Move source content and AI candidates into the new XHS layout

**Files:**

- Modify: `frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx`

### Behavior

- `renderSourcePanel` renders source note title/body/link/source image preview.
- `renderEditorExtras` no longer renders source note, title candidates, or tag candidates.
- `renderAssistantExtras` renders:
  - system prompt collapse;
  - rewrite controls;
  - generate title/tag buttons;
  - title candidate card;
  - tag candidate card;
  - rewrite candidate card.

### Source panel details

Use existing `currentSourceNote`, `sourceAssets`, `getNoteUrl`, `renderDraftSourceAssetPreview`, but make preview use `draftAssetImageUrl`.

### Candidate details

Title candidates remain buttons:

```tsx
<Button key={option} size="small" onClick={() => controller.setTitle(option)}>{option}</Button>
```

Tag candidates become clickable:

```tsx
<Tag key={option} color="blue" onClick={() => handleAdoptTagCandidate(option)} style={{ cursor: "pointer" }}>#{option}</Tag>
```

### Steps

- [ ] Add `renderSourcePanel` to XHS shell usage.
- [ ] Trim `renderEditorExtras` to only editor-related extras after Task 7 adds image panel.
- [ ] Move title/tag candidate cards into `renderAssistantExtras`.
- [ ] Verify labels and empty states.

---

## Task 7: Add draft image asset panel with add/delete

**Files:**

- Modify: `frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx`
- Use existing APIs from `frontend/src/lib/api.ts`:
  - `fetchDraftAssets`
  - `addDraftAsset`
  - `deleteDraftAsset`
  - `uploadAssetFile`

### State

Add:

```ts
const [draftAssets, setDraftAssets] = useState<DraftAsset[]>([]);
const [assetUrlInput, setAssetUrlInput] = useState("");
const [isAssetMutating, setIsAssetMutating] = useState(false);
```

Current code has `sourceAssets`; rename or split carefully:

- `sourceAssets`: source/reference assets for left source panel.
- `draftAssets`: current editable draft assets for middle panel.

Important: if current `sourceAssets` already represents `fetchDraftAssets(selectedDraft.id)`, rename it to `draftAssets` and use it in both source preview and edit panel as appropriate.

### Load assets

Whenever `selectedDraft.id` changes, fetch latest draft assets even if no `source_note_id` exists. Current code only fetches when `source_note_id` exists; that fails drafts created manually or after source deletion.

New rule:

```text
if selectedDraft exists:
  fetchDraftAssets(selectedDraft.id)
if selectedDraft.source_note_id exists:
  also fetch source note
```

### Image panel

Render in middle editor extras:

```text
草稿图片素材
[添加图片 URL input + 添加]
[上传按钮]
Grid of images:
  thumbnail
  #index
  编辑
  删除
```

Use `draftAssetImageUrl(asset)` for thumbnail.

### Add URL

```ts
async function handleAddDraftAssetUrl() {
  if (!selectedDraft || !assetUrlInput.trim()) return;
  await addDraftAsset(selectedDraft.id, { asset_type: "image", url: assetUrlInput.trim() });
  setAssetUrlInput("");
  await loadDraftAssets(selectedDraft.id);
}
```

### Upload

Use Ant Design `Upload` with `beforeUpload` returning `false` or custom request. Simpler first version:

```tsx
<Upload showUploadList={false} beforeUpload={(file) => { void handleUploadDraftAsset(file as File); return false; }}>
  <Button icon={<UploadOutlined />}>上传图片</Button>
</Upload>
```

```ts
async function handleUploadDraftAsset(file: File) {
  const uploaded = await uploadAssetFile(file);
  if (uploaded.asset_type !== "image") {
    antMessage.warning("请上传图片文件。");
    return;
  }
  await addDraftAsset(selectedDraft.id, {
    asset_type: "image",
    local_path: uploaded.file_path.replace(/^\/api\/files\/media\//, ""),
  });
  await loadDraftAssets(selectedDraft.id);
}
```

### Delete

```ts
async function handleDeleteDraftAsset(asset: DraftAsset) {
  await deleteDraftAsset(selectedDraft.id, asset.id);
  await loadDraftAssets(selectedDraft.id);
}
```

Deletion to 0 images is allowed.

### Steps

- [ ] Add robust asset loading independent of source note.
- [ ] Add image panel UI.
- [ ] Add URL add.
- [ ] Add upload add.
- [ ] Add delete.
- [ ] Update send-to-image-studio to use latest `draftAssets` and resolver.
- [ ] Verify deletion does not block save/send-to-image-studio.

---

## Task 8: Add draft image AI edit modal

**Files:**

- Modify: `frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx`
- Use APIs:
  - `localizeDraftAsset`
  - `startImageGenerationTask`
  - `fetchTask`
  - `addDraftAsset`

### State

Add:

```ts
const [editingAsset, setEditingAsset] = useState<DraftAsset | null>(null);
const [imageEditPrompt, setImageEditPrompt] = useState("");
const [imageEditAspectRatio, setImageEditAspectRatio] = useState<"auto" | "1:1" | "3:4" | "4:3" | "9:16" | "16:9">("auto");
const [isEditingImage, setIsEditingImage] = useState(false);
const [imageEditMessage, setImageEditMessage] = useState<string | null>(null);
```

Use constants copied or extracted from image studio:

```ts
const IMAGE_GENERATION_POLL_INTERVAL_MS = 3000;
const IMAGE_GENERATION_MAX_POLLS = 80;
```

If duplicating constants feels bad, extract to a shared helper only if it stays surgical. Do not refactor all image studio logic.

### Flow

```ts
async function handleGenerateEditedDraftAsset() {
  if (!selectedDraft || !editingAsset || !imageEditPrompt.trim()) return;
  setIsEditingImage(true);
  try {
    const localAsset = await localizeDraftAsset(selectedDraft.id, editingAsset.id);
    const referenceUrl = draftAssetImageUrl(localAsset);
    if (!referenceUrl.startsWith("/api/files/media/")) throw new Error("图片本地化失败，请先上传本地图或更换图片。");
    const started = await startImageGenerationTask({
      prompt: imageEditPrompt.trim(),
      reference_images: [referenceUrl],
      save_to_assets: true,
      aspect_ratio: imageEditAspectRatio,
    });
    // poll fetchTask
    // get result.asset.file_path
    // addDraftAsset(...local_path)
    // refresh assets
  } finally {
    setIsEditingImage(false);
  }
}
```

Task result parsing can mirror `imageResultFromTask` in `image-studio-page.tsx`. Prefer extracting a tiny shared helper only if it prevents copy/paste complexity; otherwise duplicate minimal logic in XHS workbench for surgical scope.

### Success behavior

- Add generated image as a new draft asset.
- Keep original asset.
- Close modal or show success and keep modal open with result message. Recommended: close modal and show `antMessage.success("AI 编辑图已新增到草稿图片素材。")`.

### Failure behavior

- Keep modal open.
- Preserve prompt.
- Show error.

### Steps

- [ ] Add modal UI.
- [ ] Add edit button on each image card.
- [ ] Add localize → async image task → poll → add draft asset flow.
- [ ] Add error handling.
- [ ] Verify original remains and generated image is appended.

---

## Task 9: Fix send-to-image-studio context to use current editable draft assets

**Files:**

- Modify: `frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx`
- Possibly modify: `frontend/src/pages/platforms/xhs/xhs-image-studio-context.ts`

### Behavior

On send to image studio:

1. Save draft text/tags.
2. Fetch latest draft assets.
3. Convert all image assets with `draftAssetToCandidate` using resolver.
4. Add source-note raw image candidates only if not duplicated.
5. Save context.
6. Navigate.

If zero candidates:

```text
已保存草稿，正在进入图片工坊。这个草稿暂无候选图，可在图片工坊手动上传参考图。
```

If nonzero:

```text
已保存草稿并带入 N 张候选图，正在进入图片工坊。
```

### Steps

- [ ] Ensure latest assets are fetched inside handler, not relying only on component state.
- [ ] Use resolver-based `draftAssetToCandidate`.
- [ ] Ensure source-note candidates do not duplicate draft asset URLs.
- [ ] Verify image studio receives candidates after local_path-only assets.

---

## Task 10: Verification pass

**Files:**

- Backend tests: `tests/backend/test_drafts.py`
- Frontend build: `frontend/`
- Optional static tests: `tests/backend/test_api.py` only if repo convention requires source assertions.

### Required commands

Run backend focused tests:

```powershell
$env:PYTHONPATH = 'E:\小红书'; pytest tests/backend/test_drafts.py -q
```

Run broader backend set impacted by draft/image/publish contracts:

```powershell
$env:PYTHONPATH = 'E:\小红书'; pytest tests/backend/test_api.py tests/backend/test_drafts.py -q
```

Run frontend build:

```powershell
npm --prefix frontend run build
```

If frontend test runner exists and is configured, run focused frontend tests. If not, rely on TypeScript build plus backend static source assertions.

### Manual verification checklist

Do not trigger real XHS publish.

- [ ] Create/open a draft from content library note with images.
- [ ] Draft workbench left panel shows source text and source images.
- [ ] Middle draft image panel shows editable draft images.
- [ ] Delete all draft images; UI allows 0 images.
- [ ] Add image by URL.
- [ ] Upload image.
- [ ] Edit one image via prompt; generated image appears as a new draft image and original remains.
- [ ] Click tag candidate; hashtag appears in body and tag appears in current tags.
- [ ] Remove current tag via close icon.
- [ ] Send to image studio; candidate images appear.
- [ ] Image studio still allows final publish image selection.
- [ ] Do not click real publish.

---

## Expected final report

Report:

- workspace path and branch;
- files changed;
- tests/build results;
- whether manual browser verification was performed;
- explicitly state no real publish was triggered;
- explicitly state no bottom-layer XHS SDK/signature files changed.

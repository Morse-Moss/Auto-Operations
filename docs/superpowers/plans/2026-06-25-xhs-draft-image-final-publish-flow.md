# XHS Draft Image Final Publish Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let operators carry one XHS draft through content library → draft workbench → image studio → publish center, explicitly choosing 1-N final publish images from original images, uploaded images, and AI-generated images.

**Architecture:** Keep the existing `AiDraft` / `DraftAsset` / `PublishJob` / `PublishAsset` model. Extend the publish handoff API compatibly with `asset_file_paths?: string[]`, then add front-end task UI that surfaces draft assets, maintains a page-local final image selection, and sends that ordered list to publish center. Do not add image task/version tables in this iteration.

**Tech Stack:** Python 3.10+, FastAPI, Pydantic, SQLAlchemy, pytest, React, Vite, TypeScript, Ant Design.

---

## Context and constraints

- Current workspace: `E:\小红书`.
- Current branch when plan was written: `master`.
- The repository already has many uncommitted changes. Keep edits surgical and do not format unrelated files.
- Project rule: do not modify `apis/`, `xhs_utils/`, or `static/` for this feature.
- Project rule: do not trigger real XHS publish during validation. Creating publish jobs is allowed; pressing the real publish action is not.
- Project rule overrides generic plan skill commit guidance: do not commit unless the user explicitly asks for a commit.

## File structure

### Backend

- Modify: `backend/app/api/drafts.py`
  - Add `asset_file_paths` to `DraftSendToPublishRequest`.
  - Add helpers for normalizing handoff paths.
  - Preserve existing single `asset_file_path` behavior.
  - Allow `http://` and `https://` only for the new multi-image handoff.
  - Keep `/api/files/media/...` validation for server-managed media files.

- Modify: `tests/backend/test_drafts.py`
  - Import `NoteAsset`.
  - Add test that creating a draft from a source note copies `NoteAsset` into `DraftAsset`.
  - Add test that `asset_file_paths` creates ordered publish assets.
  - Add test that invalid server-managed media paths in `asset_file_paths` fail before job creation.
  - Keep existing single `asset_file_path` tests unchanged.

### Frontend types and API

- Modify: `frontend/src/types/index.ts`
  - Add `asset_file_paths?: string[] | null` to `SendDraftToPublishPayload`.

### XHS draft workbench

- Modify: `frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx`
  - Display source/draft image thumbnails inside the existing source content card.
  - Keep existing source note loading logic.
  - Add clear copy that these assets go into image studio.

### XHS image studio

- Modify: `frontend/src/pages/platforms/xhs/image-studio-page.tsx`
  - Add `FinalPublishImage` local type.
  - Add final image selection state.
  - Add helper functions to add/remove/reorder final images.
  - Default-select the first draft candidate image when entering from a draft.
  - Add buttons to add draft candidates, uploaded user images, AI image assets, and newly generated images to final publish images.
  - Replace “用这张图送发布中心” with final image selection handoff using `asset_file_paths`.

### XHS publish center

- Modify: `frontend/src/pages/platforms/xhs/publish-page.tsx`
  - Rename image section label from “图片素材” to “最终发布图片”.
  - Surface image upload status on each thumbnail.
  - Show empty guidance that points back to draft/image studio when there are no assets.

---

## Task 1: Add backend tests for source asset copy and multi-image handoff

**Files:**
- Modify: `tests/backend/test_drafts.py`

- [ ] **Step 1: Add `NoteAsset` to the test imports**

Change the existing import near the top from:

```python
from backend.app.models import AiDraft, DraftAsset, Note, PlatformAccount, PublishAsset, PublishJob, User
```

to:

```python
from backend.app.models import AiDraft, DraftAsset, Note, NoteAsset, PlatformAccount, PublishAsset, PublishJob, User
```

- [ ] **Step 2: Add failing test for copying `NoteAsset` into `DraftAsset`**

Append this test after `test_create_update_and_list_draft_uses_internal_draft_name`:

```python
def test_create_draft_from_source_note_copies_note_assets_to_draft_assets(tmp_path):
    SessionLocal = override_database(tmp_path)
    try:
        db = SessionLocal()
        try:
            owner = create_user(db, "draft-create-source-assets-owner")
            account = PlatformAccount(
                user_id=owner.id,
                platform="xhs",
                sub_type="pc",
                external_user_id=f"source-account-{owner.id}",
                nickname="来源账号",
                status="active",
            )
            db.add(account)
            db.flush()
            source_note = Note(
                user_id=owner.id,
                platform_account_id=account.id,
                platform="xhs",
                note_id=f"source-note-with-assets-{owner.id}",
                title="来源标题",
                content="来源正文",
                author_name="来源作者",
            )
            db.add(source_note)
            db.flush()
            db.add_all([
                NoteAsset(
                    note_id=source_note.id,
                    asset_type="image",
                    url="https://example.test/source-a.webp",
                    local_path="notes/source-a.webp",
                    sort_order=0,
                ),
                NoteAsset(
                    note_id=source_note.id,
                    asset_type="image",
                    url="https://example.test/source-b.webp",
                    local_path="notes/source-b.webp",
                    sort_order=1,
                ),
            ])
            db.commit()
            headers = auth_headers(owner)
            source_note_id = source_note.id
        finally:
            db.close()

        response = client.post(
            "/api/drafts",
            headers=headers,
            json={"platform": "xhs", "source_note_id": source_note_id, "intent": "rewrite"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["source_note_id"] == source_note_id
        assert payload["title"] == "来源标题"
        assert payload["body"] == "来源正文"

        db = SessionLocal()
        try:
            copied_assets = db.scalars(
                select(DraftAsset)
                .where(DraftAsset.draft_id == payload["id"])
                .order_by(DraftAsset.sort_order.asc(), DraftAsset.id.asc())
            ).all()
            assert [
                (asset.asset_type, asset.url, asset.local_path, asset.sort_order)
                for asset in copied_assets
            ] == [
                ("image", "https://example.test/source-a.webp", "notes/source-a.webp", 0),
                ("image", "https://example.test/source-b.webp", "notes/source-b.webp", 1),
            ]
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)
```

- [ ] **Step 3: Add failing test for ordered `asset_file_paths` handoff**

Append this test after `test_send_draft_to_publish_accepts_current_user_existing_managed_media_path`:

```python
def test_send_draft_to_publish_accepts_ordered_asset_file_paths(tmp_path, monkeypatch):
    SessionLocal = override_database(tmp_path)
    storage_dir = tmp_path / "storage"
    media_dir = storage_dir / "media"
    media_dir.mkdir(parents=True)
    try:
        db = SessionLocal()
        try:
            owner = create_user(db, "draft-publish-multi-image-owner")
            draft = create_original_draft_with_assets(db, owner)
            file_name = f"xhs-image-u{owner.id}-generated-final.png"
            (media_dir / file_name).write_bytes(b"fake-image")
            monkeypatch.setattr("backend.app.api.drafts.get_settings", lambda: SimpleNamespace(storage_dir=storage_dir))
            draft_id = draft.id
            headers = auth_headers(owner)
        finally:
            db.close()

        response = client.post(
            f"/api/drafts/{draft_id}/send-to-publish",
            headers=headers,
            json={
                "publish_mode": "immediate",
                "asset_file_paths": [
                    "https://cdn.example.test/final-a.webp",
                    "",
                    f"/api/files/media/{file_name}",
                    "https://cdn.example.test/final-a.webp",
                    "https://cdn.example.test/final-b.webp",
                ],
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "pending"
        assert payload["source_draft_id"] == draft_id

        db = SessionLocal()
        try:
            publish_assets = db.scalars(
                select(PublishAsset)
                .where(PublishAsset.publish_job_id == payload["id"])
                .order_by(PublishAsset.id.asc())
            ).all()
            assert [asset.asset_type for asset in publish_assets] == ["image", "image", "image"]
            assert [asset.file_path for asset in publish_assets] == [
                "https://cdn.example.test/final-a.webp",
                f"/api/files/media/{file_name}",
                "https://cdn.example.test/final-b.webp",
            ]
            assert [asset.upload_status for asset in publish_assets] == ["pending", "pending", "pending"]
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)
```

- [ ] **Step 4: Add failing test for rejecting invalid server-managed path in multi-image handoff**

Append this test after the ordered `asset_file_paths` test:

```python
def test_send_draft_to_publish_rejects_invalid_managed_path_in_asset_file_paths_before_creating_job(tmp_path, monkeypatch):
    SessionLocal = override_database(tmp_path)
    storage_dir = tmp_path / "storage"
    (storage_dir / "media").mkdir(parents=True)
    try:
        db = SessionLocal()
        try:
            owner = create_user(db, "draft-publish-multi-invalid-owner")
            draft = create_original_draft_with_assets(db, owner)
            monkeypatch.setattr("backend.app.api.drafts.get_settings", lambda: SimpleNamespace(storage_dir=storage_dir))
            draft_id = draft.id
            headers = auth_headers(owner)
        finally:
            db.close()

        response = client.post(
            f"/api/drafts/{draft_id}/send-to-publish",
            headers=headers,
            json={
                "publish_mode": "immediate",
                "asset_file_paths": [
                    "https://cdn.example.test/final-a.webp",
                    "/api/files/media/xhs-image-u999999-stolen.png",
                ],
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "asset_file_path must be a current-user managed media file"

        db = SessionLocal()
        try:
            assert db.scalars(select(PublishJob)).all() == []
            assert db.scalars(select(PublishAsset)).all() == []
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)
```

- [ ] **Step 5: Run the new backend tests and verify expected failure**

Run:

```bash
pytest tests/backend/test_drafts.py::test_create_draft_from_source_note_copies_note_assets_to_draft_assets tests/backend/test_drafts.py::test_send_draft_to_publish_accepts_ordered_asset_file_paths tests/backend/test_drafts.py::test_send_draft_to_publish_rejects_invalid_managed_path_in_asset_file_paths_before_creating_job -q
```

Expected:

- The source asset copy test may already pass because source asset copying exists.
- The two `asset_file_paths` tests must fail before Task 2 because the request model does not yet accept/use `asset_file_paths`.

---

## Task 2: Implement backend multi-image handoff

**Files:**
- Modify: `backend/app/api/drafts.py`

- [ ] **Step 1: Extend `DraftSendToPublishRequest`**

Change the class to include `asset_file_paths`:

```python
class DraftSendToPublishRequest(BaseModel):
    platform_account_id: Optional[int] = None
    publish_mode: str = Field(default="immediate", pattern="^(immediate|scheduled)$")
    scheduled_at: Optional[datetime] = None
    topics: Optional[list[str]] = None
    location: Optional[str] = None
    privacy_type: Optional[int] = Field(default=None, ge=0, le=1)
    is_private: Optional[bool] = None
    asset_file_path: Optional[str] = Field(default=None, max_length=2048)
    asset_file_paths: Optional[list[str]] = None
```

- [ ] **Step 2: Add URL/path normalization helpers below `_validate_handoff_asset_file_path`**

Insert this code after `_validate_handoff_asset_file_path`:

```python
def _is_external_image_url(file_path: str) -> bool:
    return file_path.startswith("http://") or file_path.startswith("https://")


def _normalize_handoff_asset_file_paths(payload: DraftSendToPublishRequest, current_user: User) -> list[str]:
    raw_paths: list[str] = []
    if payload.asset_file_paths:
        raw_paths.extend(payload.asset_file_paths)
    elif payload.asset_file_path:
        raw_paths.append(payload.asset_file_path)

    normalized: list[str] = []
    seen: set[str] = set()
    for raw_path in raw_paths:
        path = (raw_path or "").strip()
        if not path or path in seen:
            continue
        if path.startswith("/api/files/media/"):
            _validate_handoff_asset_file_path(path, current_user)
        elif _is_external_image_url(path):
            pass
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="asset_file_path must start with /api/files/media/ or http(s)://",
            )
        seen.add(path)
        normalized.append(path)
    return normalized
```

- [ ] **Step 3: Replace single-path validation in `send_draft_to_publish`**

Replace:

```python
    handoff_asset_file_path = (payload.asset_file_path or "").strip()
    if handoff_asset_file_path:
        _validate_handoff_asset_file_path(handoff_asset_file_path, current_user)
```

with:

```python
    handoff_asset_file_paths = _normalize_handoff_asset_file_paths(payload, current_user)
```

- [ ] **Step 4: Replace single publish asset creation branch**

Replace:

```python
    if handoff_asset_file_path:
        db.add(
            PublishAsset(
                publish_job_id=job.id,
                asset_type="image",
                file_path=handoff_asset_file_path,
                upload_status="pending",
            )
        )
    else:
```

with:

```python
    if handoff_asset_file_paths:
        for handoff_asset_file_path in handoff_asset_file_paths:
            db.add(
                PublishAsset(
                    publish_job_id=job.id,
                    asset_type="image",
                    file_path=handoff_asset_file_path,
                    upload_status="pending",
                )
            )
    else:
```

Keep the existing `draft_assets = db.scalars(...)` fallback block unchanged under the `else`.

- [ ] **Step 5: Run focused backend tests**

Run:

```bash
pytest tests/backend/test_drafts.py::test_send_draft_to_publish_accepts_current_user_existing_managed_media_path tests/backend/test_drafts.py::test_send_draft_to_publish_accepts_ordered_asset_file_paths tests/backend/test_drafts.py::test_send_draft_to_publish_rejects_invalid_managed_path_in_asset_file_paths_before_creating_job tests/backend/test_drafts.py::test_send_draft_to_publish_rejects_wrong_user_managed_media_path_before_creating_job tests/backend/test_drafts.py::test_send_draft_to_publish_rejects_missing_managed_media_path_before_creating_job tests/backend/test_drafts.py::test_send_draft_to_publish_rejects_non_media_asset_file_path_before_creating_job -q
```

Expected: all selected tests pass. The legacy single `asset_file_path` HTTPS rejection test should still pass because the new `http(s)` allowance applies through `_normalize_handoff_asset_file_paths`; if the implementation currently allows `http(s)` for legacy `asset_file_path`, adjust the helper so single-path legacy mode still calls `_validate_handoff_asset_file_path` only:

```python
def _normalize_handoff_asset_file_paths(payload: DraftSendToPublishRequest, current_user: User) -> list[str]:
    if payload.asset_file_paths:
        raw_paths = payload.asset_file_paths
        allow_external_urls = True
    elif payload.asset_file_path:
        raw_paths = [payload.asset_file_path]
        allow_external_urls = False
    else:
        raw_paths = []
        allow_external_urls = False

    normalized: list[str] = []
    seen: set[str] = set()
    for raw_path in raw_paths:
        path = (raw_path or "").strip()
        if not path or path in seen:
            continue
        if path.startswith("/api/files/media/"):
            _validate_handoff_asset_file_path(path, current_user)
        elif allow_external_urls and _is_external_image_url(path):
            pass
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="asset_file_path must start with /api/files/media/" if not allow_external_urls else "asset_file_path must start with /api/files/media/ or http(s)://",
            )
        seen.add(path)
        normalized.append(path)
    return normalized
```

- [ ] **Step 6: Run all draft backend tests**

Run:

```bash
pytest tests/backend/test_drafts.py -q
```

Expected: all tests in `test_drafts.py` pass.

- [ ] **Step 7: Checkpoint**

Run:

```bash
git diff -- backend/app/api/drafts.py tests/backend/test_drafts.py
```

Expected: diff only contains request payload, helper, send-to-publish branch, and tests. Do not commit unless the user explicitly authorizes a commit.

---

## Task 3: Update frontend API type for multi-image handoff

**Files:**
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Extend `SendDraftToPublishPayload`**

Change:

```ts
export type SendDraftToPublishPayload = {
  platform_account_id?: number | null;
  publish_mode?: "immediate" | "scheduled";
  scheduled_at?: string | null;
  topics?: string[];
  location?: string | null;
  privacy_type?: 0 | 1 | null;
  is_private?: boolean | null;
  asset_file_path?: string | null;
};
```

to:

```ts
export type SendDraftToPublishPayload = {
  platform_account_id?: number | null;
  publish_mode?: "immediate" | "scheduled";
  scheduled_at?: string | null;
  topics?: string[];
  location?: string | null;
  privacy_type?: 0 | 1 | null;
  is_private?: boolean | null;
  asset_file_path?: string | null;
  asset_file_paths?: string[] | null;
};
```

- [ ] **Step 2: Run TypeScript check or build after later UI changes**

No standalone command is necessary yet because this type has no runtime behavior. Run the frontend build in Task 7.

---

## Task 4: Show source image thumbnails in XHS draft workbench

**Files:**
- Modify: `frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx`

- [ ] **Step 1: Add image candidate helper below `sourceNoteImageCandidates`**

Insert:

```tsx
function renderDraftSourceAssetPreview(sourceAssets: DraftAsset[]) {
  const imageAssets = sourceAssets.filter((asset) => asset.asset_type === "image" && isUsableImageUrl(asset.url));
  if (imageAssets.length === 0) {
    return (
      <Text type="secondary" style={{ fontSize: 12 }}>
        这个草稿暂无来源图片，可在图片工坊上传参考图继续。
      </Text>
    );
  }

  const visibleAssets = imageAssets.slice(0, 6);
  const hiddenCount = imageAssets.length - visibleAssets.length;
  return (
    <Space direction="vertical" size={6} style={{ width: "100%" }}>
      <Text type="secondary" style={{ fontSize: 12 }}>
        这些图片会随“送入图片工坊”一起带入，后续可选择最终发布图。
      </Text>
      <Space size={8} wrap>
        {visibleAssets.map((asset) => (
          <div key={asset.id} style={{ width: 56 }}>
            <div style={{ width: 56, height: 56, borderRadius: 6, overflow: "hidden", background: "#1a1a1a", border: "1px solid #303030" }}>
              <img src={asset.url} alt={`draft-asset-${asset.id}`} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
            </div>
          </div>
        ))}
        {hiddenCount > 0 ? <Tag color="blue">+{hiddenCount}</Tag> : null}
      </Space>
    </Space>
  );
}
```

If TypeScript reports `DraftAsset` is not imported as a value/type, ensure the existing import from `../../../lib/api` includes the type:

```tsx
import type { DraftAsset } from "../../../lib/api";
```

- [ ] **Step 2: Replace the existing source card footer with thumbnail preview**

In `renderEditorExtras`, locate the card that starts:

```tsx
<Card size="small" title="草稿内容" extra={<a href={getNoteUrl(currentSourceNote)} target="_blank" rel="noreferrer"><Button type="link" size="small" icon={<LinkOutlined />}>查看原文</Button></a>}>
```

Inside it, after the existing `Space` that shows tags and `素材 {sourceAssets.length} 项`, add:

```tsx
<div style={{ marginTop: 10 }}>
  {renderDraftSourceAssetPreview(sourceAssets)}
</div>
```

The final card body should include title, paragraph, existing tag row, and the new preview block.

- [ ] **Step 3: Verify no behavioral changes to send-to-image-studio**

Run:

```bash
git diff -- frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx
```

Expected: only rendering helper and source card JSX changed. `handleSendToImageStudio` should still call `fetchDraftAssets`, build candidates, save context, and navigate.

---

## Task 5: Add final publish image selection to XHS image studio

**Files:**
- Modify: `frontend/src/pages/platforms/xhs/image-studio-page.tsx`

- [ ] **Step 1: Add reorder icons to imports**

Change icon import from:

```tsx
import {
  DeleteOutlined,
  FileImageOutlined,
  InboxOutlined,
  LinkOutlined,
  SendOutlined,
  PictureOutlined,
  PlusOutlined,
  ReloadOutlined,
  RobotOutlined,
  StarOutlined,
  UploadOutlined,
} from "@ant-design/icons";
```

to:

```tsx
import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  DeleteOutlined,
  FileImageOutlined,
  InboxOutlined,
  LinkOutlined,
  SendOutlined,
  PictureOutlined,
  PlusOutlined,
  ReloadOutlined,
  RobotOutlined,
  StarOutlined,
  UploadOutlined,
} from "@ant-design/icons";
```

- [ ] **Step 2: Add final image type below `ImageStudioDraftContext`**

Insert after:

```tsx
type ImageStudioDraftContext = XhsImageStudioDraftContext | WechatOfficialImageStudioDraftContext;
```

this type:

```tsx
type FinalPublishImage = {
  key: string;
  url: string;
  publishPath: string;
  source: "draft_asset" | "source_note" | "manual" | "generated" | "asset";
  label: string;
};
```

- [ ] **Step 3: Add final image state**

After existing state:

```tsx
const [isAttachingDraftAsset, setIsAttachingDraftAsset] = useState(false);
```

add:

```tsx
const [finalPublishImages, setFinalPublishImages] = useState<FinalPublishImage[]>([]);
```

- [ ] **Step 4: Add helper functions before `handleGenerate`**

Insert after `loadAssets`:

```tsx
function addFinalPublishImage(image: Omit<FinalPublishImage, "key">) {
  const key = image.publishPath;
  setFinalPublishImages((current) => {
    if (current.some((item) => item.publishPath === image.publishPath)) return current;
    return [...current, { ...image, key }];
  });
}

function removeFinalPublishImage(publishPath: string) {
  setFinalPublishImages((current) => current.filter((item) => item.publishPath !== publishPath));
}

function moveFinalPublishImage(index: number, direction: -1 | 1) {
  setFinalPublishImages((current) => {
    const nextIndex = index + direction;
    if (nextIndex < 0 || nextIndex >= current.length) return current;
    const next = [...current];
    const [item] = next.splice(index, 1);
    next.splice(nextIndex, 0, item);
    return next;
  });
}

function isFinalPublishImageSelected(publishPath: string): boolean {
  return finalPublishImages.some((item) => item.publishPath === publishPath);
}

function candidateToFinalImage(image: ImageStudioDraftContext["candidate_images"][number], index: number): FinalPublishImage | null {
  if (!image.url) return null;
  return {
    key: image.url,
    url: image.url,
    publishPath: image.url,
    source: image.source === "draft_asset" || image.source === "source_note" ? image.source : "manual",
    label: `${candidateImageSourceLabel(image.source)} ${index + 1}`,
  };
}
```

- [ ] **Step 5: Add generated result to final candidates after generation succeeds**

Inside `handleGenerate`, after:

```tsx
setGeneratedPreview(mediaPath ?? result.url);
setGeneratedMediaPath(mediaPath);
```

add:

```tsx
addFinalPublishImage({
  url: mediaPath ?? result.url,
  publishPath: mediaPath ?? result.url,
  source: "generated",
  label: "AI 生成图",
});
```

This makes the successful generated image immediately available in the final image list while still requiring the user to press “送发布中心”.

- [ ] **Step 6: Update upload handler to add uploaded images as manual final candidates**

Inside `handleUploadFile`, after:

```tsx
setUserImages((prev) => [newItem, ...prev]);
```

add:

```tsx
addFinalPublishImage({
  url: uploaded.download_url,
  publishPath: uploaded.download_url,
  source: "manual",
  label: uploaded.file_name,
});
```

- [ ] **Step 7: Clear final image selection when clearing draft context**

Inside `handleClearDraftContext`, after:

```tsx
setDraftContext(null);
```

add:

```tsx
setFinalPublishImages([]);
```

- [ ] **Step 8: Replace send-to-publish handler with multi-image handoff**

Replace `handleSendGeneratedToPublish` with:

```tsx
async function handleSendFinalImagesToPublish() {
  if (!draftContext) return;
  if (isWechatOfficialDraftContext(draftContext)) {
    setMessage("公众号图片工坊第一版只做生成/整理/下载和本地资产回挂，material_upload_blocked：不上传公众号素材，也不送发布中心。");
    return;
  }
  if (finalPublishImages.length === 0) {
    setError("请先选择至少 1 张最终发布图片。可以使用原图、上传图或 AI 生成图。");
    return;
  }
  setIsSendingPublish(true);
  setError(null);
  setMessage(null);
  try {
    const job = await sendDraftToPublish(draftContext.draft_id, {
      publish_mode: "immediate",
      asset_file_paths: finalPublishImages.map((image) => image.publishPath),
    });
    clearImageStudioDraftContext();
    setDraftContext(null);
    setFinalPublishImages([]);
    setMessage(`已创建发布中心待发布任务 #${job.id}，不会自动发布。`);
    navigate(`/platforms/xhs/publish?jobId=${job.id}`);
  } catch (err) {
    const detail = err instanceof Error ? err.message : "送发布中心失败，请稍后重试。";
    setError(detail);
  } finally {
    setIsSendingPublish(false);
  }
}
```

- [ ] **Step 9: Default-select first draft candidate when loading draft context**

Inside the `useEffect` that loads draft context, after `setDraftContext(context);`, add:

```tsx
setFinalPublishImages((current) => {
  if (current.length > 0) return current;
  const firstCandidate = context.candidate_images
    .map((image, index) => candidateToFinalImage(image, index))
    .find((image): image is FinalPublishImage => Boolean(image));
  return firstCandidate ? [firstCandidate] : [];
});
```

- [ ] **Step 10: Add candidate action buttons in the draft context card**

In the draft context candidate thumbnail map, after the source label `Text`, add:

```tsx
{candidateToFinalImage(image, index) ? (
  <Button
    size="small"
    type={isFinalPublishImageSelected(candidateToFinalImage(image, index)!.publishPath) ? "default" : "link"}
    disabled={isFinalPublishImageSelected(candidateToFinalImage(image, index)!.publishPath)}
    onClick={() => {
      const finalImage = candidateToFinalImage(image, index);
      if (finalImage) addFinalPublishImage(finalImage);
    }}
    style={{ padding: 0, fontSize: 10 }}
  >
    {isFinalPublishImageSelected(candidateToFinalImage(image, index)!.publishPath) ? "已加入" : "加入最终"}
  </Button>
) : null}
```

If TypeScript dislikes repeated non-null assertions, assign inside the map callback before `return`:

```tsx
const finalImage = candidateToFinalImage(image, index);
```

and use `finalImage` in the JSX.

- [ ] **Step 11: Replace generated result publish button**

Replace the button text and handler in the generated result section:

```tsx
<Button
  type="primary"
  icon={<SendOutlined />}
  onClick={handleSendGeneratedToPublish}
  loading={isSendingPublish}
  disabled={isGenerating || !generatedMediaPath}
  title={generatedMediaPath ? undefined : "生成图需要先保存为服务器媒体资产"}
>
  用这张图送发布中心
</Button>
```

with:

```tsx
<Button
  type="primary"
  icon={<PlusOutlined />}
  onClick={() => addFinalPublishImage({
    url: generatedPreview,
    publishPath: generatedMediaPath ?? generatedPreview,
    source: "generated",
    label: "AI 生成图",
  })}
  disabled={isGenerating || !generatedPreview || isFinalPublishImageSelected(generatedMediaPath ?? generatedPreview)}
>
  {isFinalPublishImageSelected(generatedMediaPath ?? generatedPreview) ? "已加入最终发布" : "加入最终发布图片"}
</Button>
```

- [ ] **Step 12: Add final publish image card before the bottom `Tabs`**

Insert before:

```tsx
{/* ---- Bottom: Tabs ---- */}
```

this block:

```tsx
{draftContext && !isWechatOfficialDraftContext(draftContext) && (
  <Card
    title={<Space><SendOutlined /> 最终发布图片</Space>}
    extra={<Text type="secondary">已选择 {finalPublishImages.length} 张</Text>}
    style={{ marginBottom: 24, borderColor: "#254f2a", background: "linear-gradient(135deg, rgba(37,79,42,0.18), rgba(20,20,20,0.72))" }}
  >
    <Space direction="vertical" size={12} style={{ width: "100%" }}>
      <Text type="secondary" style={{ fontSize: 12 }}>
        发布中心将按当前顺序使用这些图片。可以从原图、上传图或 AI 生成图中选择。
      </Text>
      {finalPublishImages.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="请先选择至少 1 张最终发布图片。" />
      ) : (
        <Row gutter={[12, 12]}>
          {finalPublishImages.map((image, index) => (
            <Col xs={12} sm={8} md={6} lg={4} key={image.key}>
              <Card size="small" styles={{ body: { padding: 8 } }}>
                <div style={{ height: 96, borderRadius: 6, overflow: "hidden", background: "#1a1a1a", display: "flex", alignItems: "center", justifyContent: "center", marginBottom: 6 }}>
                  {isRenderableImage(image.url) ? (
                    <img src={image.url} alt={image.label} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                  ) : (
                    <PictureOutlined style={{ fontSize: 24, color: "#666" }} />
                  )}
                </div>
                <Space direction="vertical" size={4} style={{ width: "100%" }}>
                  <Tag color="green" style={{ margin: 0 }}>#{index + 1} {image.label}</Tag>
                  <Space size={4} wrap>
                    <Button size="small" icon={<ArrowUpOutlined />} disabled={index === 0} onClick={() => moveFinalPublishImage(index, -1)} />
                    <Button size="small" icon={<ArrowDownOutlined />} disabled={index === finalPublishImages.length - 1} onClick={() => moveFinalPublishImage(index, 1)} />
                    <Button size="small" danger icon={<DeleteOutlined />} onClick={() => removeFinalPublishImage(image.publishPath)} />
                  </Space>
                </Space>
              </Card>
            </Col>
          ))}
        </Row>
      )}
      <Space>
        <Button onClick={() => setFinalPublishImages([])} disabled={finalPublishImages.length === 0}>
          清空选择
        </Button>
        <Button
          type="primary"
          icon={<SendOutlined />}
          onClick={handleSendFinalImagesToPublish}
          loading={isSendingPublish}
          disabled={finalPublishImages.length === 0}
        >
          送入发布中心
        </Button>
      </Space>
    </Space>
  </Card>
)}
```

- [ ] **Step 13: Add final-image buttons to AI image assets cards**

Inside each AI asset card, before the delete button, add:

```tsx
<Button
  type="link"
  size="small"
  icon={<PlusOutlined />}
  onClick={() => addFinalPublishImage({
    url: asset.file_path,
    publishPath: asset.file_path,
    source: "asset",
    label: "AI 图片资产",
  })}
  disabled={isFinalPublishImageSelected(asset.file_path)}
  style={{ width: "100%", marginTop: 4 }}
>
  {isFinalPublishImageSelected(asset.file_path) ? "已加入最终发布" : "加入最终发布"}
</Button>
```

- [ ] **Step 14: Add final-image buttons to user image cards**

Inside each user image card, before the delete button, add:

```tsx
<Button
  type="link"
  size="small"
  icon={<PlusOutlined />}
  onClick={() => addFinalPublishImage({
    url: img.url,
    publishPath: img.url,
    source: "manual",
    label: img.file_name,
  })}
  disabled={isFinalPublishImageSelected(img.url)}
  style={{ width: "100%", marginTop: 4 }}
>
  {isFinalPublishImageSelected(img.url) ? "已加入最终发布" : "加入最终发布"}
</Button>
```

- [ ] **Step 15: Run frontend build after this task**

Run:

```bash
cd frontend && npm run build
```

Expected: build succeeds. If it fails with `candidateToFinalImage(image, index)!` typing issues, refactor the map callback to compute `const finalImage = candidateToFinalImage(image, index);` once and guard the button with `finalImage ? ... : null`.

---

## Task 6: Improve publish center final image display

**Files:**
- Modify: `frontend/src/pages/platforms/xhs/publish-page.tsx`

- [ ] **Step 1: Rename image section label**

Find:

```tsx
<PictureOutlined /> 图片素材 ({imageAssets.length})
```

Replace with:

```tsx
<PictureOutlined /> 最终发布图片 ({imageAssets.length})
```

- [ ] **Step 2: Add upload status under each image**

Replace the `imageAssets.map` block currently returning only `<Image ... />` with:

```tsx
{imageAssets.map((asset, index) => (
  <div key={asset.id} style={{ width: 88 }}>
    <Image
      src={asset.file_path}
      width={80}
      height={80}
      style={{ objectFit: "cover", borderRadius: 6 }}
      referrerPolicy="no-referrer"
      fallback="data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iODAiIGhlaWdodD0iODAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2Zz4PHJlY3Qgd2lkdGg9IjgwIiBoZWlnaHQ9IjgwIiBmaWxsPSIjMjYyNjI2Ii8+PHRleHQgeD0iNTAlIiB5PSI1MCUiIGRvbWluYW50LWJhc2VsaW5lPSJtaWRkbGUiIHRleHQtYW5jaG9yPSJtaWRkbGUiIGZpbGw9IiM4YzhjOGMiIGZvbnQtc2l6ZT0iMTIiPuWbvueJhzwvdGV4dD48L3N2Zz4="
    />
    <Text type="secondary" ellipsis style={{ display: "block", fontSize: 10, marginTop: 2 }}>
      #{index + 1} · {asset.upload_status}
    </Text>
  </div>
))}
```

Keep the surrounding `Image.PreviewGroup` and `Space`.

- [ ] **Step 3: Improve empty asset text**

Replace:

```tsx
{!hasAnyAsset && <Text type="secondary">暂无素材</Text>}
```

with:

```tsx
{!hasAnyAsset && (
  <Alert
    type="warning"
    showIcon
    message="暂无最终发布图片"
    description="请从草稿工坊进入图片工坊，选择原图、上传图或 AI 生成图后再送入发布中心。"
  />
)}
```

`Alert` is already imported at the top of this file.

- [ ] **Step 4: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: build succeeds.

---

## Task 7: Full verification

**Files:**
- No new files. This task verifies all changes.

- [ ] **Step 1: Run backend draft tests**

Run:

```bash
pytest tests/backend/test_drafts.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run broader backend tests likely touched by draft/publish changes**

Run:

```bash
pytest tests/backend/test_api.py tests/backend/test_auto_tasks_accounts.py tests/backend/test_drafts.py -q
```

Expected: all selected tests pass. If unrelated existing failures appear, record the failing test names and error messages; do not hide them.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: Vite build succeeds.

- [ ] **Step 4: Manual app verification without real publish**

Use the running app or start it with the project’s normal commands. Verify this path without pressing the real publish confirmation:

```text
1. Open XHS content library.
2. Pick a saved note with images.
3. Create or open its draft in draft workbench.
4. Confirm the draft workbench shows image thumbnails and the “送入图片工坊” expectation text.
5. Click “送入图片工坊”.
6. Confirm image studio shows draft title/body/tags and candidate images.
7. Confirm at least one candidate is selected in “最终发布图片”.
8. Upload a customer/product image and confirm it can be added to final images.
9. If image generation model is configured, generate an image and confirm it can be added to final images.
10. Click “送入发布中心”.
11. Confirm publish center opens with the new job selected.
12. Confirm publish center shows the same final publish images in the selected order.
13. Stop before clicking the real “发布” confirmation.
```

Expected: the full handoff works and no real XHS publish is triggered.

- [ ] **Step 5: Inspect final diff**

Run:

```bash
git diff -- backend/app/api/drafts.py tests/backend/test_drafts.py frontend/src/types/index.ts frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx frontend/src/pages/platforms/xhs/image-studio-page.tsx frontend/src/pages/platforms/xhs/publish-page.tsx docs/superpowers/specs/2026-06-25-xhs-draft-image-final-publish-flow-design.md docs/superpowers/plans/2026-06-25-xhs-draft-image-final-publish-flow.md
```

Expected: diff is limited to this feature’s backend handoff, tests, frontend task UI, publish preview, spec, and plan.

---

## Completion checklist

Before reporting completion, confirm each item with evidence:

- [ ] Source note assets copy to draft assets is covered by test or existing passing behavior.
- [ ] `asset_file_paths` creates multiple `PublishAsset` rows in input order.
- [ ] Legacy `asset_file_path` behavior still works and still rejects external URLs.
- [ ] Draft workbench shows image thumbnails for source/draft assets.
- [ ] Image studio has final publish image selection, remove, clear, and reorder controls.
- [ ] Image studio sends `asset_file_paths` to publish center.
- [ ] Publish center labels the images as final publish images and shows upload status.
- [ ] Backend tests pass.
- [ ] Frontend build passes.
- [ ] No real XHS publish was triggered.
- [ ] No unrelated SDK/signature files were modified.

## Execution notes

- Do not commit automatically. If the user later asks for a commit, use a scoped commit message such as `feat: support xhs final image publish handoff`.
- If a step reveals that `PublishAsset` ordering by `id` is insufficient in practice, stop and ask whether to add an explicit `sort_order` migration; do not expand scope silently.
- If frontend build exposes existing unrelated TypeScript errors, report them with exact output and continue only after deciding whether they block this feature.

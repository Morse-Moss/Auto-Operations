import assert from "node:assert/strict";

import {
  buildInitialFinalPublishImages,
  candidateImageSourceLabel,
  candidateToFinalImage,
  fileNameFromMediaPath,
  isPublishableFinalImagePath,
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
  { url: "/api/files/media/u1_manual.jpg", local_path: "u1_manual.jpg", source: "manual" },
];

const initial = buildInitialFinalPublishImages(candidates);
assert.deepEqual(
  initial.map((image) => image.publishPath),
  ["/api/files/media/u1_draft-a.jpg", "/api/files/media/u1_draft-b.jpg", "/api/files/media/u1_manual.jpg"],
  "Initial final publish queue should include draft assets and manual uploads",
);
assert.deepEqual(
  initial.map((image) => image.source),
  ["draft_asset", "draft_asset", "manual"],
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
  ["/api/files/media/u1_manual.jpg", "https://example.test/source.jpg", "/api/files/media/u1_ai-edit.jpg"],
  "AI edit should replace only this generation's reference images and keep unrelated selections",
);

const upserted = upsertCandidateImage(candidates, { id: 3, url: "/api/files/media/u1_ai-edit.jpg", local_path: "u1_ai-edit.jpg", source: "ai_edit" });
assert.equal(upserted.length, 5);
assert.equal(upsertCandidateImage(upserted, { id: 3, url: "/api/files/media/u1_ai-edit.jpg", local_path: "u1_ai-edit.jpg", source: "ai_edit" }).length, 5);
const emptyUrlCandidates = upsertCandidateImage(
  [{ id: 10, url: "", local_path: "empty-a.jpg", source: "draft_asset" }],
  { id: 11, url: "", local_path: "empty-b.jpg", source: "ai_edit" },
);
assert.equal(emptyUrlCandidates.length, 2, "Empty URL candidates should not overwrite each other");
const sameUrlDifferentSourceCandidates = upsertCandidateImage(
  [{ id: 20, url: "/api/files/media/shared.jpg", local_path: "shared-draft.jpg", source: "draft_asset" }],
  { id: 21, url: "/api/files/media/shared.jpg", local_path: "shared-ai.jpg", source: "ai_edit" },
);
assert.equal(sameUrlDifferentSourceCandidates.length, 2, "Same URL candidates from different sources should coexist");
const sameUrlSameSourceCandidates = upsertCandidateImage(
  [{ id: 30, url: "/api/files/media/retry.jpg", local_path: "old.jpg", source: "ai_edit" }],
  { id: 30, url: "/api/files/media/retry.jpg", local_path: "new.jpg", source: "ai_edit" },
);
assert.equal(sameUrlSameSourceCandidates.length, 1, "Same URL, source, and id should update the existing candidate");
assert.equal(sameUrlSameSourceCandidates[0].local_path, "new.jpg");

assert.equal(fileNameFromMediaPath("/api/files/media/u1_ai-edit.jpg"), "u1_ai-edit.jpg");
assert.equal(fileNameFromMediaPath("E:\\data\\media\\u1_ai-edit.jpg"), "u1_ai-edit.jpg");

assert.equal(candidateImageSourceLabel("ai_edit"), "AI 改图");
assert.equal(candidateImageSourceLabel("draft_asset"), "草稿素材");

assert.equal(isPublishableFinalImagePath("/api/files/media/u1_ai-edit.jpg"), true);
assert.equal(isPublishableFinalImagePath("https://example.test/source.jpg"), true);
assert.equal(isPublishableFinalImagePath("/api/files/media/"), false);
assert.equal(isPublishableFinalImagePath("/api/files/media/../x.jpg"), false);
assert.equal(isPublishableFinalImagePath("/api/files/media/subdir/u1_ai-edit.jpg"), false);
assert.equal(isPublishableFinalImagePath("https://"), false);

const invalid: FinalPublishImage[] = [
  { key: "blob:preview", url: "blob:preview", publishPath: "blob:preview", source: "generated", label: "预览图" },
  { key: "empty-media", url: "/api/files/media/", publishPath: "/api/files/media/", source: "generated", label: "空媒体路径" },
  { key: "traversal-media", url: "/api/files/media/../x.jpg", publishPath: "/api/files/media/../x.jpg", source: "generated", label: "穿越媒体路径" },
  { key: "nested-media", url: "/api/files/media/subdir/u1_ai-edit.jpg", publishPath: "/api/files/media/subdir/u1_ai-edit.jpg", source: "generated", label: "嵌套媒体路径" },
  { key: "empty-https", url: "https://", publishPath: "https://", source: "generated", label: "空 HTTPS URL" },
];
assert.deepEqual(validateFinalPublishImages(invalid), { ok: false, invalidCount: 5, tooManyCount: 0 });
assert.deepEqual(validateFinalPublishImages(replaced), { ok: true, invalidCount: 0, tooManyCount: 0 });

const tooManyImages = Array.from({ length: 19 }, (_, index): FinalPublishImage => ({
  key: `/api/files/media/${index}.jpg`,
  url: `/api/files/media/${index}.jpg`,
  publishPath: `/api/files/media/${index}.jpg`,
  source: "draft_asset",
  label: `草稿素材 ${index + 1}`,
}));
assert.deepEqual(validateFinalPublishImages(tooManyImages), { ok: false, invalidCount: 0, tooManyCount: 19 });

console.log("xhs-image-studio finalization tests passed");

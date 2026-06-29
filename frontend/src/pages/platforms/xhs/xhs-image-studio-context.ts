import type { Draft } from "../../../types";
import type { DraftAsset } from "../../../lib/api";
import {
  clearDraftImageStudioContext,
  DRAFT_IMAGE_STUDIO_CONTEXT_TTL_MS,
  draftAssetImageUrl,
  draftAssetToImageStudioCandidate,
  isUsableImageUrl,
  loadDraftImageStudioContext,
  saveDraftImageStudioContext,
  type DraftImageStudioCandidateImage,
  type DraftImageStudioDraftContext,
} from "../../../components/image-studio/draft-image-studio-context";

export const XHS_IMAGE_STUDIO_DRAFT_CONTEXT_KEY = "xhs:image-studio:draft-context";
export const IMAGE_STUDIO_DRAFT_CONTEXT_TTL_MS = DRAFT_IMAGE_STUDIO_CONTEXT_TTL_MS;

export type XhsImageStudioCandidateImage = DraftImageStudioCandidateImage & {
  source: "draft_asset" | "source_note" | "manual" | "ai_edit";
};

export type XhsImageStudioDraftContext = Omit<
  DraftImageStudioDraftContext,
  "platform" | "source_article_id" | "candidate_images" | "material_upload_blocked"
> & {
  tags: NonNullable<Draft["tags"]>;
  source_note_id?: number | null;
  candidate_images: XhsImageStudioCandidateImage[];
};

function toXhsContext(context: DraftImageStudioDraftContext | null): XhsImageStudioDraftContext | null {
  if (!context) return null;
  return {
    source: "draft",
    draft_id: context.draft_id,
    draft_name: context.draft_name ?? null,
    title: context.title,
    body: context.body,
    tags: context.tags,
    source_note_id: context.source_note_id ?? null,
    candidate_images: context.candidate_images.filter((image): image is XhsImageStudioCandidateImage =>
      image.source === "draft_asset" || image.source === "source_note" || image.source === "manual" || image.source === "ai_edit",
    ),
    created_at: context.created_at,
  };
}

export function saveImageStudioDraftContext(context: Omit<XhsImageStudioDraftContext, "created_at"> & { created_at?: number }): boolean {
  return saveDraftImageStudioContext(XHS_IMAGE_STUDIO_DRAFT_CONTEXT_KEY, {
    platform: "xhs",
    ...context,
    created_at: context.created_at ?? Date.now(),
  });
}

export function loadImageStudioDraftContext(options?: { requireFresh?: boolean }): XhsImageStudioDraftContext | null {
  return toXhsContext(loadDraftImageStudioContext(XHS_IMAGE_STUDIO_DRAFT_CONTEXT_KEY, { ...options, platform: "xhs" }));
}

export function clearImageStudioDraftContext(): void {
  clearDraftImageStudioContext(XHS_IMAGE_STUDIO_DRAFT_CONTEXT_KEY);
}

export { draftAssetImageUrl, isUsableImageUrl };

export function draftAssetToCandidate(asset: DraftAsset): XhsImageStudioCandidateImage | null {
  const candidate = draftAssetToImageStudioCandidate(asset);
  if (!candidate || candidate.source !== "draft_asset") return null;
  return candidate as XhsImageStudioCandidateImage;
}

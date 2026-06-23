import type { DraftAsset } from "../../lib/api";
import type { WechatOfficialContentDetail, WechatOfficialContentImage, WechatOfficialDraft } from "../../types";
import {
  clearDraftImageStudioContext,
  draftAssetToImageStudioCandidate,
  isUsableImageUrl,
  loadDraftImageStudioContext,
  saveDraftImageStudioContext,
  type DraftImageStudioCandidateImage,
  type DraftImageStudioDraftContext,
} from "../../components/image-studio/draft-image-studio-context";

export const WECHAT_OFFICIAL_IMAGE_STUDIO_DRAFT_CONTEXT_KEY = "wechat-official:image-studio:draft-context";

export type WechatOfficialImageStudioCandidateImage = DraftImageStudioCandidateImage & {
  source: "draft_asset" | "article_cover" | "snapshot_image" | "manual";
};

export type WechatOfficialImageStudioDraftContext = Omit<
  DraftImageStudioDraftContext,
  "platform" | "source_note_id" | "candidate_images"
> & {
  platform: "wechat_official";
  source_article_id?: number | null;
  candidate_images: WechatOfficialImageStudioCandidateImage[];
  material_upload_blocked: true;
};

function toWechatOfficialContext(context: DraftImageStudioDraftContext | null): WechatOfficialImageStudioDraftContext | null {
  if (!context || context.platform !== "wechat_official") return null;
  return {
    platform: "wechat_official",
    source: "draft",
    draft_id: context.draft_id,
    draft_name: context.draft_name ?? null,
    title: context.title,
    body: context.body,
    tags: context.tags,
    source_article_id: context.source_article_id ?? null,
    candidate_images: context.candidate_images.filter((image): image is WechatOfficialImageStudioCandidateImage =>
      image.source === "draft_asset" || image.source === "article_cover" || image.source === "snapshot_image" || image.source === "manual",
    ),
    created_at: context.created_at,
    material_upload_blocked: true,
  };
}

function imageCandidate(url: string, source: WechatOfficialImageStudioCandidateImage["source"]): WechatOfficialImageStudioCandidateImage | null {
  return isUsableImageUrl(url) ? { url, source } : null;
}

export function extractWechatOfficialDraftImageCandidates(
  detail: WechatOfficialContentDetail | null,
  draftAssets: DraftAsset[] = [],
): WechatOfficialImageStudioCandidateImage[] {
  const candidates: WechatOfficialImageStudioCandidateImage[] = [];
  const seen = new Set<string>();

  function add(candidate: WechatOfficialImageStudioCandidateImage | null): void {
    if (!candidate || seen.has(candidate.url)) return;
    seen.add(candidate.url);
    candidates.push(candidate);
  }

  draftAssets.forEach((asset) => {
    const candidate = draftAssetToImageStudioCandidate(asset);
    if (candidate?.source === "draft_asset") add(candidate as WechatOfficialImageStudioCandidateImage);
  });

  const cover = detail?.article.cover_url || "";
  add(imageCandidate(cover, "article_cover"));

  (detail?.images ?? []).forEach((image: WechatOfficialContentImage) => {
    add(imageCandidate(image.url, "snapshot_image"));
  });

  return candidates;
}

export function saveWechatOfficialImageStudioDraftContext(
  context: Omit<WechatOfficialImageStudioDraftContext, "platform" | "created_at" | "material_upload_blocked"> & { created_at?: number },
): boolean {
  return saveDraftImageStudioContext(WECHAT_OFFICIAL_IMAGE_STUDIO_DRAFT_CONTEXT_KEY, {
    platform: "wechat_official",
    material_upload_blocked: true,
    ...context,
  });
}

export function loadWechatOfficialImageStudioDraftContext(options?: { requireFresh?: boolean }): WechatOfficialImageStudioDraftContext | null {
  return toWechatOfficialContext(loadDraftImageStudioContext(WECHAT_OFFICIAL_IMAGE_STUDIO_DRAFT_CONTEXT_KEY, { ...options, platform: "wechat_official" }));
}

export function clearWechatOfficialImageStudioDraftContext(): void {
  clearDraftImageStudioContext(WECHAT_OFFICIAL_IMAGE_STUDIO_DRAFT_CONTEXT_KEY);
}

export function wechatOfficialDraftToImageStudioContext(
  draft: WechatOfficialDraft,
  candidateImages: WechatOfficialImageStudioCandidateImage[],
  sourceArticleId?: number | null,
): Omit<WechatOfficialImageStudioDraftContext, "platform" | "created_at" | "material_upload_blocked"> {
  return {
    source: "draft",
    draft_id: draft.id,
    draft_name: draft.draft_name ?? null,
    title: draft.title,
    body: draft.body,
    tags: Array.isArray(draft.tags) ? draft.tags : [],
    source_article_id: sourceArticleId ?? null,
    candidate_images: candidateImages,
  };
}

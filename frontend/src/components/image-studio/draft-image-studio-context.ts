import type { Draft } from "../../types";
import type { DraftAsset } from "../../lib/api";

export const DRAFT_IMAGE_STUDIO_CONTEXT_TTL_MS = 30 * 60 * 1000;

export const DRAFT_IMAGE_STUDIO_CANDIDATE_IMAGE_SOURCES = [
  "draft_asset",
  "source_note",
  "article_cover",
  "snapshot_image",
  "manual",
] as const;

export type DraftImageStudioPlatform = "xhs" | "wechat_official" | string;
export type DraftImageStudioCandidateImageSource = (typeof DRAFT_IMAGE_STUDIO_CANDIDATE_IMAGE_SOURCES)[number];
type DraftTag = NonNullable<Draft["tags"]>[number];

export type DraftImageStudioCandidateImage = {
  id?: number;
  url: string;
  local_path?: string;
  source: DraftImageStudioCandidateImageSource;
};

export type DraftImageStudioDraftContext = {
  platform: DraftImageStudioPlatform;
  source: "draft";
  draft_id: number;
  draft_name?: string | null;
  title: string;
  body: string;
  tags: NonNullable<Draft["tags"]>;
  source_note_id?: number | null;
  source_article_id?: number | null;
  candidate_images: DraftImageStudioCandidateImage[];
  created_at: number;
  material_upload_blocked?: boolean;
};

export type DraftImageStudioDraftContextInput = Omit<DraftImageStudioDraftContext, "created_at"> & { created_at?: number };

function getSessionStorage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage ?? null;
  } catch {
    return null;
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isPositiveInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value > 0;
}

function isNullablePositiveInteger(value: unknown): value is number | null | undefined {
  return value === undefined || value === null || isPositiveInteger(value);
}

function isValidCreatedAt(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value > 0;
}

function isFreshCreatedAt(value: number): boolean {
  return Date.now() - value <= DRAFT_IMAGE_STUDIO_CONTEXT_TTL_MS;
}

function isCandidateImageSource(value: unknown): value is DraftImageStudioCandidateImageSource {
  return typeof value === "string" && DRAFT_IMAGE_STUDIO_CANDIDATE_IMAGE_SOURCES.includes(value as DraftImageStudioCandidateImageSource);
}

function isDraftTag(value: unknown): value is DraftTag {
  if (!isObject(value)) return false;
  return typeof value.name === "string" && value.name.trim().length > 0 && (value.id === undefined || typeof value.id === "string");
}

function isCandidateImage(value: unknown): value is DraftImageStudioCandidateImage {
  if (!isObject(value)) return false;
  return (
    isUsableImageUrl(value.url) &&
    isCandidateImageSource(value.source) &&
    (value.id === undefined || isPositiveInteger(value.id)) &&
    (value.local_path === undefined || typeof value.local_path === "string")
  );
}

export function parseDraftImageStudioContext(
  value: unknown,
  options?: { requireFresh?: boolean; platform?: DraftImageStudioPlatform },
): DraftImageStudioDraftContext | null {
  if (!isObject(value)) return null;
  if (typeof value.platform !== "string" || !value.platform.trim()) return null;
  if (options?.platform && value.platform !== options.platform) return null;
  if (value.source !== "draft" || !isPositiveInteger(value.draft_id)) return null;
  if (value.draft_name !== undefined && value.draft_name !== null && typeof value.draft_name !== "string") return null;
  if (typeof value.title !== "string" || typeof value.body !== "string") return null;
  if (!Array.isArray(value.tags) || !value.tags.every(isDraftTag)) return null;
  if (!isNullablePositiveInteger(value.source_note_id)) return null;
  if (!isNullablePositiveInteger(value.source_article_id)) return null;
  if (!Array.isArray(value.candidate_images) || !value.candidate_images.every(isCandidateImage)) return null;
  if (!isValidCreatedAt(value.created_at)) return null;
  if (value.material_upload_blocked !== undefined && typeof value.material_upload_blocked !== "boolean") return null;
  if (options?.requireFresh && !isFreshCreatedAt(value.created_at)) return null;

  return {
    platform: value.platform,
    source: "draft",
    draft_id: value.draft_id,
    draft_name: value.draft_name ?? null,
    title: value.title,
    body: value.body,
    tags: value.tags,
    source_note_id: value.source_note_id ?? null,
    source_article_id: value.source_article_id ?? null,
    candidate_images: value.candidate_images,
    created_at: value.created_at,
    material_upload_blocked: value.material_upload_blocked ?? false,
  };
}

export function saveDraftImageStudioContext(storageKey: string, context: DraftImageStudioDraftContextInput): boolean {
  const storage = getSessionStorage();
  if (!storage) return false;
  try {
    storage.setItem(storageKey, JSON.stringify({ ...context, created_at: context.created_at ?? Date.now() }));
    return true;
  } catch {
    return false;
  }
}

export function loadDraftImageStudioContext(
  storageKey: string,
  options?: { requireFresh?: boolean; platform?: DraftImageStudioPlatform },
): DraftImageStudioDraftContext | null {
  const storage = getSessionStorage();
  if (!storage) return null;

  let raw: string | null;
  try {
    raw = storage.getItem(storageKey);
  } catch {
    return null;
  }
  if (!raw) return null;

  try {
    const parsed = parseDraftImageStudioContext(JSON.parse(raw), options);
    if (parsed) return parsed;
  } catch {
    // Invalid JSON is treated the same as an invalid persisted shape.
  }
  return null;
}

export function clearDraftImageStudioContext(storageKey: string): void {
  const storage = getSessionStorage();
  if (!storage) return;
  try {
    storage.removeItem(storageKey);
  } catch {
    // Ignore storage failures so SSR/test/privacy-mode contexts never crash.
  }
}

export function isUsableImageUrl(value: unknown): value is string {
  return typeof value === "string" && (/^https?:\/\//i.test(value) || value.startsWith("/api/")) && !/\.(mp4|mov|m4v|avi|webm)(\?|#|$)/i.test(value);
}

export function draftAssetImageUrl(asset: DraftAsset): string {
  if (asset.asset_type !== "image") return "";
  if (isUsableImageUrl(asset.url)) return asset.url;

  const rawLocalPath: unknown = asset.local_path;
  if (isUsableImageUrl(rawLocalPath)) return rawLocalPath;

  const localPath = typeof rawLocalPath === "string" ? rawLocalPath.trim() : "";
  if (!localPath) return "";

  const fileName = localPath.replace(/^\/api\/files\/media\//, "").split(/[\\/]/).pop()?.trim() ?? "";
  return fileName ? `/api/files/media/${fileName}` : "";
}

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

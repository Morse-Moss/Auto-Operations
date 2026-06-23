import type { Draft } from "../../../types";
import type { DraftAsset } from "../../../lib/api";

export const XHS_IMAGE_STUDIO_DRAFT_CONTEXT_KEY = "xhs:image-studio:draft-context";
export const IMAGE_STUDIO_DRAFT_CONTEXT_TTL_MS = 30 * 60 * 1000;

const CANDIDATE_IMAGE_SOURCES = ["draft_asset", "source_note", "manual"] as const;

type CandidateImageSource = (typeof CANDIDATE_IMAGE_SOURCES)[number];

type DraftTag = NonNullable<Draft["tags"]>[number];

export type XhsImageStudioCandidateImage = {
  id?: number;
  url: string;
  local_path?: string;
  source: CandidateImageSource;
};

export type XhsImageStudioDraftContext = {
  source: "draft";
  draft_id: number;
  draft_name?: string | null;
  title: string;
  body: string;
  tags: NonNullable<Draft["tags"]>;
  source_note_id?: number | null;
  candidate_images: XhsImageStudioCandidateImage[];
  created_at: number;
};

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
  return Date.now() - value <= IMAGE_STUDIO_DRAFT_CONTEXT_TTL_MS;
}

function isCandidateImageSource(value: unknown): value is CandidateImageSource {
  return typeof value === "string" && CANDIDATE_IMAGE_SOURCES.includes(value as CandidateImageSource);
}

function isDraftTag(value: unknown): value is DraftTag {
  if (!isObject(value)) return false;
  return typeof value.name === "string" && value.name.trim().length > 0 && (value.id === undefined || typeof value.id === "string");
}

function isCandidateImage(value: unknown): value is XhsImageStudioCandidateImage {
  if (!isObject(value)) return false;
  return (
    isUsableImageUrl(value.url) &&
    isCandidateImageSource(value.source) &&
    (value.id === undefined || isPositiveInteger(value.id)) &&
    (value.local_path === undefined || typeof value.local_path === "string")
  );
}

function parseImageStudioDraftContext(value: unknown, options?: { requireFresh?: boolean }): XhsImageStudioDraftContext | null {
  if (!isObject(value)) return null;
  if (value.source !== "draft" || !isPositiveInteger(value.draft_id)) return null;
  if (value.draft_name !== undefined && value.draft_name !== null && typeof value.draft_name !== "string") return null;
  if (typeof value.title !== "string" || typeof value.body !== "string") return null;
  if (!Array.isArray(value.tags) || !value.tags.every(isDraftTag)) return null;
  if (!isNullablePositiveInteger(value.source_note_id)) return null;
  if (!Array.isArray(value.candidate_images) || !value.candidate_images.every(isCandidateImage)) return null;
  if (!isValidCreatedAt(value.created_at)) return null;
  if (options?.requireFresh && !isFreshCreatedAt(value.created_at)) return null;

  return {
    source: "draft",
    draft_id: value.draft_id,
    draft_name: value.draft_name ?? null,
    title: value.title,
    body: value.body,
    tags: value.tags,
    source_note_id: value.source_note_id ?? null,
    candidate_images: value.candidate_images,
    created_at: value.created_at,
  };
}

export function saveImageStudioDraftContext(context: Omit<XhsImageStudioDraftContext, "created_at"> & { created_at?: number }): boolean {
  const storage = getSessionStorage();
  if (!storage) return false;
  try {
    storage.setItem(XHS_IMAGE_STUDIO_DRAFT_CONTEXT_KEY, JSON.stringify({ ...context, created_at: context.created_at ?? Date.now() }));
    return true;
  } catch {
    return false;
  }
}

export function loadImageStudioDraftContext(options?: { requireFresh?: boolean }): XhsImageStudioDraftContext | null {
  const storage = getSessionStorage();
  if (!storage) return null;

  let raw: string | null;
  try {
    raw = storage.getItem(XHS_IMAGE_STUDIO_DRAFT_CONTEXT_KEY);
  } catch {
    return null;
  }
  if (!raw) return null;

  try {
    const parsed = parseImageStudioDraftContext(JSON.parse(raw), options);
    if (parsed) return parsed;
  } catch {
    // Invalid JSON is treated the same as an invalid persisted shape.
  }
  return null;
}

export function clearImageStudioDraftContext(): void {
  const storage = getSessionStorage();
  if (!storage) return;
  try {
    storage.removeItem(XHS_IMAGE_STUDIO_DRAFT_CONTEXT_KEY);
  } catch {
    // Ignore storage failures so SSR/test/privacy-mode contexts never crash.
  }
}

export function isUsableImageUrl(value: unknown): value is string {
  return typeof value === "string" && (/^https?:\/\//i.test(value) || value.startsWith("/api/")) && !/\.(mp4|mov|m4v|avi|webm)(\?|#|$)/i.test(value);
}

export function draftAssetToCandidate(asset: DraftAsset): XhsImageStudioCandidateImage | null {
  if (asset.asset_type !== "image" || !isUsableImageUrl(asset.url)) return null;
  return {
    id: asset.id,
    url: asset.url,
    local_path: asset.local_path,
    source: "draft_asset",
  };
}

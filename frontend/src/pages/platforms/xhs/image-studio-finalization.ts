import type { XhsImageStudioCandidateImage } from "./xhs-image-studio-context";

export type XhsFinalizationCandidateImage = Omit<XhsImageStudioCandidateImage, "source"> & {
  source: XhsImageStudioCandidateImage["source"] | "ai_edit";
};

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
    .filter((image) => image.source === "draft_asset" || image.source === "ai_edit" || image.source === "manual")
    .map((image, index) => candidateToFinalImage(image, index))
    .filter((image): image is FinalPublishImage => Boolean(image));
}

export function fileNameFromMediaPath(filePath: string): string {
  return filePath.replace(/^\/api\/files\/media\//, "").split(/[\\/]/).pop() ?? filePath;
}

const MEDIA_FILE_PREFIX = "/api/files/media/";
const XHS_FINAL_PUBLISH_IMAGE_LIMIT = 18;

function isSafeMediaFilePath(value: string): boolean {
  if (!value.startsWith(MEDIA_FILE_PREFIX)) return false;
  const fileName = value.slice(MEDIA_FILE_PREFIX.length);
  if (!fileName || fileName.includes("/") || fileName.includes("\\")) return false;
  try {
    const decoded = decodeURIComponent(fileName);
    return Boolean(decoded) && decoded !== "." && decoded !== ".." && !decoded.includes("/") && !decoded.includes("\\");
  } catch {
    return false;
  }
}

function isValidHttpImageUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return (url.protocol === "http:" || url.protocol === "https:") && Boolean(url.hostname);
  } catch {
    return false;
  }
}

export function isPublishableFinalImagePath(value: string): boolean {
  if (!value || value.trim() !== value) return false;
  return isSafeMediaFilePath(value) || isValidHttpImageUrl(value);
}

export function validateFinalPublishImages(images: FinalPublishImage[]): { ok: boolean; invalidCount: number; tooManyCount: number } {
  const invalidCount = images.filter((image) => !isPublishableFinalImagePath(image.publishPath)).length;
  const tooManyCount = images.length > XHS_FINAL_PUBLISH_IMAGE_LIMIT ? images.length : 0;
  return { ok: invalidCount === 0 && tooManyCount === 0, invalidCount, tooManyCount };
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

function isSameCandidateImage(
  image: XhsFinalizationCandidateImage,
  candidate: XhsFinalizationCandidateImage,
): boolean {
  if (!image.url || !candidate.url) return false;
  if (image.url !== candidate.url || image.source !== candidate.source) return false;
  if (image.id !== undefined || candidate.id !== undefined) return image.id === candidate.id;
  return true;
}

export function upsertCandidateImage(
  current: XhsFinalizationCandidateImage[],
  candidate: XhsFinalizationCandidateImage,
): XhsFinalizationCandidateImage[] {
  if (current.some((image) => isSameCandidateImage(image, candidate))) {
    return current.map((image) => (isSameCandidateImage(image, candidate) ? { ...image, ...candidate } : image));
  }
  return [...current, candidate];
}

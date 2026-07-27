import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const filePath = path.resolve(__dirname, "../src/pages/platforms/xhs/image-studio-page.tsx");
const source = readFileSync(filePath, "utf8");

assert.match(
  source,
  /function loadDraftContextForCurrentRoute\(/,
  "Image studio should load draft context through a route-aware helper instead of only checking ?from=draft inline",
);

assert.ok(
  source.includes("const shouldRestoreExistingDraftContext = shouldRestoreDraftImageStudioContext({") &&
    source.includes("hasCurrentContext: Boolean(draftContextRef.current),") &&
    source.includes("fromDraft: shouldLoadDraftContext,") &&
    source.includes("isReload: isPageReloadNavigation(),") &&
    source.includes("const context = shouldRestoreExistingDraftContext ? loadDraftContextForCurrentRoute(isWechatOfficialRoute) : null;"),
  "Image studio should restore draft context via the shared shouldRestoreDraftImageStudioContext helper",
);

const draftHandoffNavigateIndex = source.indexOf('navigate("/platforms/xhs/image-studio", { replace: true });');
const draftContextRefUpdateIndex = source.indexOf("draftContextRef.current = context;");
assert.ok(
  draftContextRefUpdateIndex >= 0 && draftHandoffNavigateIndex > draftContextRefUpdateIndex,
  "Image studio should update draftContextRef before replacing ?from=draft so the follow-up route effect does not clear the just-loaded draft context",
);

assert.match(
  source,
  /function buildInitialFinalPublishImages\(context: ImageStudioDraftContext\): FinalPublishImage\[\]/,
  "Image studio should build the initial final-publish queue through a dedicated multi-select helper",
);

assert.match(
  source,
  /return buildInitialXhsFinalPublishImages\(context\.candidate_images\);/,
  "Initial final-publish queue should delegate to the XHS finalization helper for draft_asset and ai_edit defaults",
);

assert.match(
  source,
  /function toggleFinalPublishImage\(/,
  "Candidate thumbnails should support toggling final-publish selection for multi-select behavior",
);

assert.match(
  source,
  /Checkbox[\s\S]*?checked=\{isSelected\}[\s\S]*?onChange=\{\(event\) => \{[\s\S]*?event\.stopPropagation\(\);[\s\S]*?toggleFinalPublishImage\(finalImage\);/,
  "Draft candidate cards should expose checkbox multi-select controls tied to final-publish selection",
);

assert.match(
  source,
  /onClick=\{\(\) => \{[\s\S]*?if \(!finalImage(?: \|\| isWechatOfficialDraftContext\(draftContext\))?\) return;[\s\S]*?toggleFinalPublishImage\(finalImage\);/,
  "Clicking an XHS candidate thumbnail should toggle whether it is included in final-publish images",
);

assert.match(
  source,
  /全选草稿素材/,
  "Draft context card should offer a clear select-all action for draft assets",
);

assert.match(
  source,
  /取消全选/,
  "Draft context card should offer a clear action to remove all selected final-publish images",
);

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

assert.match(
  source,
  /import \{[\s\S]*replaceReferenceSelectionsWithGenerated[\s\S]*upsertCandidateImage[\s\S]*validateFinalPublishImages[\s\S]*\} from "\.\/image-studio-finalization";/,
  "Image studio page should use finalization helpers for AI edit queue behavior and publish validation",
);

assert.ok(
  source.includes("addedAsset = await addDraftAsset(latestDraftContext.draft_id, {") &&
    source.includes("asset_type: \"image\",") &&
    source.includes("local_path: fileNameFromMediaPath(mediaPath),"),
  "AI edit generation should save generated media back to the current draft as a DraftAsset",
);

assert.match(
  source,
  /source: "ai_edit"/,
  "AI edit generation should add a candidate tagged as AI 改图",
);

assert.match(
  source,
  /replaceReferenceSelectionsWithGenerated\([\s\S]*generationReferenceImages,[\s\S]*generatedFinalImage[\s\S]*\)/,
  "AI edit generation should replace this generation's reference images in the final publish queue",
);

assert.ok(
  source.includes("const nextContext: XhsImageStudioDraftContext = {") &&
    source.includes("candidate_images: nextCandidates,") &&
    source.includes("saveImageStudioDraftContext(nextContext);"),
  "AI edit generation should persist updated draft candidate context for refresh recovery",
);

assert.match(
  source,
  /validateFinalPublishImages\(finalPublishImages\)/,
  "Sending to publish should validate final publish image paths before creating the publish job",
);

assert.ok(
  source.includes("const draftContextRef = useRef<ImageStudioDraftContext | null>(null);") &&
    source.includes("draftContextRef.current") &&
    source.includes("latestDraftContext.draft_id !== generationDraftContext.draft_id"),
  "AI edit completion should guard against stale draft context before writing generated assets back to a draft",
);

assert.ok(
  source.includes("const generationReferenceImages = [...referenceImages];") &&
    source.includes("replaceReferenceSelectionsWithGenerated(prev, generationReferenceImages, generatedFinalImage)"),
  "AI edit completion should use the generation's reference image snapshot instead of a stale async closure",
);

assert.ok(
  source.includes("const shouldSaveToAssets = Boolean(generationDraftContext && !isWechatOfficialDraftContext(generationDraftContext)) || saveToAssets;") &&
    source.includes("save_to_assets: shouldSaveToAssets,"),
  "XHS draft-context generation should force save_to_assets so generated images have a publishable mediaPath",
);

assert.ok(
  source.includes("if (draftContextRef.current) {") &&
    source.includes("setDraftContext(null);") &&
    source.includes("setFinalPublishImages([]);"),
  "Route/context refresh with no fresh context should clear stale draft context and final publish images",
);

assert.ok(
  source.includes("onClick={(event) => event.stopPropagation()}") &&
    source.includes("onChange={(event) => {") &&
    source.includes("toggleFinalPublishImage(finalImage);"),
  "Draft candidate checkbox should stop click propagation before the parent thumbnail toggles selection",
);

assert.match(
  source,
  /async function handleSendFinalImagesToPublish\(\)[\s\S]*?clearImageStudioDraftContext\(\);\s*draftContextRef\.current = null;\s*setDraftContext\(null\);/,
  "Sending selected draft images to publish should clear draftContextRef.current together with stored draft context state",
);

const handleClearDraftContextBody = source.match(
  /function handleClearDraftContext\(\) \{([\s\S]*?)\r?\n  \}\r?\n\r?\n  async function handleAttachGeneratedToWechatDraft/,
)?.[1] ?? "";

assert.ok(
  handleClearDraftContextBody.includes("draftContextRef.current = null;") &&
    handleClearDraftContextBody.includes("setDraftContext(null);") &&
    handleClearDraftContextBody.includes("setFinalPublishImages([]);") &&
    handleClearDraftContextBody.includes("setReferenceImages([]);"),
  "Manually clearing draft context should also clear stale reference images so later AI generation does not reuse draft images",
);

assert.ok(
  /const isSameDraftContext =[\s\S]*?draftContextRef\.current\.draft_id === context\.draft_id/.test(source) &&
    /const nextReferenceImages = context\.candidate_images[\s\S]*?\.slice\(0, RUNNINGHUB_CURRENT_REFERENCE_IMAGE_LIMIT\);/.test(source) &&
    /if \(!isSameDraftContext\) \{[\s\S]*?setPrompt\(buildDraftImagePrompt\(context\)\);[\s\S]*?setReferenceImages\(nextReferenceImages\);[\s\S]*?\}/.test(source),
  "Loading a different draft context should reset prompt and reference images from the new draft instead of preserving previous draft input",
);

assert.ok(
  source.includes("const latestDraftContextAfterSave = draftContextRef.current;") &&
    source.includes("latestDraftContextAfterSave.draft_id !== latestDraftContext.draft_id") &&
    source.includes("updateXhsDraftCandidates(latestDraftContextAfterSave, nextCandidates)"),
  "AI edit generation should re-check the active draft after addDraftAsset resolves before updating page/session state",
);

assert.ok(
  source.includes("const uploadDraftContext = draftContextRef.current;") &&
    source.includes("const latestUploadDraftContext = draftContextRef.current;") &&
    source.includes("latestUploadDraftContext.draft_id === uploadDraftContext.draft_id") &&
    source.includes("updateXhsDraftCandidates(latestUploadDraftContext, upsertCandidateImage(latestUploadDraftContext.candidate_images, manualCandidate))"),
  "Manual upload should use a latest draft ref guard so async uploads do not resurrect or overwrite stale draft context",
);

assert.ok(
  source.includes("const generationHadDraftContext = Boolean(generationDraftContext);") &&
    source.includes("const latestContextForStandaloneGeneration = draftContextRef.current;") &&
    source.includes("!generationHadDraftContext && !latestContextForStandaloneGeneration"),
  "Standalone AI generation should only add to the final publish queue when the page is still standalone at completion time",
);

assert.ok(
  /const latestUploadDraftContext = draftContextRef\.current;[\s\S]*?if \(!uploadDraftContext\) \{[\s\S]*?if \(!latestUploadDraftContext\) \{[\s\S]*?addFinalPublishImage\([\s\S]*?\}\s*\} else if \(!isWechatOfficialDraftContext\(uploadDraftContext\)\) \{[\s\S]*?latestUploadDraftContext\.draft_id === uploadDraftContext\.draft_id[\s\S]*?addFinalPublishImage\([\s\S]*?updateXhsDraftCandidates/.test(source),
  "Manual upload should only add to the current final publish queue when there was no draft at upload start and still no draft at completion, or the same XHS draft is still active",
);

assert.ok(
  source.includes("const candidateLocalPath = addedAsset.local_path || fileNameFromMediaPath(mediaPath);") &&
    source.includes("const candidateUrl = addedAsset.url || (addedAsset.local_path ? `/api/files/media/${fileNameFromMediaPath(addedAsset.local_path)}` : mediaPath) || mediaPath;") &&
    source.includes("url: candidateUrl,") &&
    source.includes("local_path: candidateLocalPath,"),
  "AI edit candidates should fall back from addedAsset.url/local_path to generated mediaPath-derived publishable paths",
);

assert.ok(
  /setFinalPublishImages\(\(current\) => \{[\s\S]*?if \(isSameDraftContext\) return current;[\s\S]*?return buildInitialFinalPublishImages\(context\);[\s\S]*?\}\);/.test(source) &&
    !source.includes("isSameDraftContext && current.length > 0"),
  "Same draft context hydration should preserve the current final publish queue even when the user cleared it to an empty array",
);

assert.ok(
  /if \(!isSameDraftContext\) \{[\s\S]*?setPrompt\(buildDraftImagePrompt\(context\)\);[\s\S]*?setReferenceImages\(nextReferenceImages\);[\s\S]*?\}/.test(source) &&
    /isWechatOfficialDraftContext\(draftContextRef\.current\) === isWechatOfficialDraftContext\(context\)/.test(source) &&
    !/!isWechatOfficialDraftContext\(draftContextRef\.current\)[\s\S]*?!isWechatOfficialDraftContext\(context\)[\s\S]*?draftContextRef\.current\.draft_id === context\.draft_id/.test(source) &&
    !/setPrompt\(\(current\) => \(current\.trim\(\) \? current : buildDraftImagePrompt\(context\)\)\)/.test(source) &&
    !/setReferenceImages\(\(current\) => \{[\s\S]*?if \(current\.length > 0\) return current;[\s\S]*?return nextReferenceImages;[\s\S]*?\}\)/.test(source),
  "Same draft context hydration should not refill prompt or reference images after the user clears them; only cross-draft hydration should reset them",
);

assert.ok(
  /if \(!context\) \{[\s\S]*?setDraftContext\(null\);[\s\S]*?setFinalPublishImages\(\[\]\);[\s\S]*?setReferenceImages\(\[\]\);/.test(source),
  "Missing or expired draft context should clear stale reference images together with draft context state",
);

assert.ok(
  source.includes("const effectiveSaveToAssets = Boolean(draftContext && !isWechatOfficialDraftContext(draftContext)) || saveToAssets;") &&
    source.includes("const shouldSaveToAssets = Boolean(generationDraftContext && !isWechatOfficialDraftContext(generationDraftContext)) || saveToAssets;") &&
    source.includes("checked={effectiveSaveToAssets}") &&
    source.includes("!effectiveSaveToAssets &&"),
  "XHS draft mode should use an effective save-to-assets value consistently for controls and generated-result actions",
);

assert.ok(
  /function selectAllDraftAssetImages\(\)[\s\S]*?candidate_images\.filter\(\(image\) => image\.source === "draft_asset"\)[\s\S]*?setFinalPublishImages/.test(source),
  "The select-all draft asset action should select only draft_asset images, not existing AI edit or manual candidates",
);

assert.ok(
  source.includes("validation.tooManyCount > 0") &&
    source.includes("最终发布图片最多支持 18 张"),
  "Sending to publish should block more than 18 final images before calling the backend",
);

assert.ok(
  /onClick=\{\(\) => \{[\s\S]*?if \(!finalImage \|\| isWechatOfficialDraftContext\(draftContext\)\) return;[\s\S]*?toggleFinalPublishImage\(finalImage\);/.test(source),
  "WeChat Official draft thumbnails should not toggle the hidden XHS final publish state",
);

assert.match(
  source,
  /const manualCandidate: XhsImageStudioCandidateImage = \{[\s\S]*source: "manual",[\s\S]*\};/,
  "Manual uploads in draft-linked image studio should also become draft context candidates",
);

assert.match(
  source,
  /updateXhsDraftCandidates\(latestUploadDraftContext, upsertCandidateImage\(latestUploadDraftContext\.candidate_images, manualCandidate\)\)/,
  "Manual upload candidates should be persisted into the current draft image studio context using the latest draft context",
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

console.log("xhs-image-studio draft context tests passed");

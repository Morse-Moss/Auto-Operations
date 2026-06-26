import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const filePath = path.resolve(__dirname, "../src/pages/platforms/xhs/xhs-draft-workbench.tsx");
const shellFilePath = path.resolve(__dirname, "../src/components/draft-workbench/draft-workbench-shell.tsx");
const source = readFileSync(filePath, "utf8");
const shellSource = readFileSync(shellFilePath, "utf8");

assert.match(
  source,
  /visibleAssets\.map\(\(asset, index\) =>/,
  "Draft source asset thumbnails should expose the index for user-facing alt text",
);

assert.match(
  source,
  /referrerPolicy="no-referrer"/,
  "Draft source asset thumbnails should not send a referrer when loading remote images",
);

assert.match(
  source,
  /alt=\{`来源图片 \$\{index \+ 1\}`\}/,
  "Draft source asset thumbnails should use user-facing alt text",
);

assert.match(
  source,
  /function normalizeTagName\(value: string\): string/,
  "XHS draft workbench should expose a tag normalizer before adopting generated tags",
);

assert.match(
  source,
  /function appendHashtag\(body: string, tagName: string\): string/,
  "XHS draft workbench should append generated hashtags through a dedicated helper",
);

assert.match(
  source,
  /onClick=\{\(\) => handleAdoptTagOption\(option\)\}/,
  "Generated tag candidates should be clickable and call the adoption handler",
);

assert.match(
  shellSource,
  /closable[\s\S]*?onClose=\{\(event\) => \{[\s\S]*?event\.preventDefault\(\);[\s\S]*?controller\.setTags\(/,
  "Current draft tags should be closable and update controller.tags in onClose",
);

assert.match(
  shellSource,
  /renderSourcePanel\?: \(draft: TDraft\) => ReactNode/,
  "DraftWorkbenchShellProps should expose an optional renderSourcePanel slot",
);

assert.match(
  source,
  /renderSourcePanel=\{\(\) => \([\s\S]*?title="草稿内容"[\s\S]*?renderDraftSourceAssetPreview\(draftAssets\)/,
  "XHS drafts page should render source draft content in DraftWorkbenchShell renderSourcePanel",
);

assert.match(
  source,
  /renderAssistantExtras=\{\(\) => \([\s\S]*?title="标题候选"[\s\S]*?title="标签候选"[\s\S]*?onClick=\{\(\) => handleAdoptTagOption\(option\)\}/,
  "Generated title and tag candidates should live in the AI assistant extras slot",
);

const editorExtrasMatch = source.match(/renderEditorExtras=\{\(\) => \([\s\S]*?\n\s*\)\}\n\s*renderAssistantExtras=/);
if (editorExtrasMatch) {
  assert.doesNotMatch(
    editorExtrasMatch[0],
    /标题候选|标签候选/,
    "Editor extras should not contain generated title or tag candidate cards",
  );
}

assert.match(
  shellSource,
  /setIsDraftListOpen\(\(open\) => !open\)/,
  "DraftWorkbenchShell should expose a compact toggle for opening and closing the draft list",
);

assert.doesNotMatch(
  shellSource,
  /<Col xs=\{24\} lg=\{6\}>[\s\S]*?<Text strong>草稿列表<\/Text>[\s\S]*?<\/Col>/,
  "Draft list should not remain as a permanent fixed left Col lg={6}",
);

assert.match(
  source,
  /title="草稿图片素材"/,
  "XHS draft workbench should render a draft image asset card in the editor extras slot",
);

assert.match(
  source,
  /addDraftAsset/,
  "XHS draft workbench should allow adding draft assets from URLs or uploads",
);

assert.match(
  source,
  /deleteDraftAsset/,
  "XHS draft workbench should allow deleting draft assets",
);

assert.match(
  source,
  /uploadAssetFile/,
  "XHS draft workbench should upload local files before registering draft assets",
);

assert.match(
  source,
  /local_path: uploaded\.file_name/,
  "Uploaded draft images should register the managed media file_name, not the absolute server file_path",
);

assert.match(
  source,
  /draftAssetImageUrl\(asset\)/,
  "Draft asset thumbnails should resolve through draftAssetImageUrl",
);

assert.match(
  source,
  /当前草稿暂无图片/,
  "Draft image asset card should show an empty state when the draft has no images",
);

assert.match(
  source,
  /localizeDraftAsset/,
  "Draft image AI edit should localize the source image before generation",
);

assert.match(
  source,
  /startImageGenerationTask/,
  "Draft image AI edit should call the existing async image generation API",
);

assert.match(
  source,
  /fetchTask/,
  "Draft image AI edit should poll the async generation task",
);

assert.match(
  source,
  /reference_images:\s*\[referenceUrl\]/,
  "Draft image AI edit should pass the localized image as reference_images",
);

assert.match(
  source,
  /save_to_assets:\s*true/,
  "Draft image AI edit should save generated results into image assets",
);

assert.match(
  source,
  />编辑<|编辑图片|AI 编辑图片/,
  "Draft image cards should expose an edit button and AI edit modal copy",
);

assert.match(
  source,
  /AI 编辑图已新增/,
  "Draft image AI edit should confirm that the generated image was added",
);

assert.match(
  source,
  /const assets = await fetchDraftAssets\(saved\.id\);[\s\S]*?setDraftAssets\(assets\.items\);[\s\S]*?\.map\(draftAssetToCandidate\)/,
  "Sending a draft to image studio should fetch latest editable draft assets, sync state, and convert them through draftAssetToCandidate",
);

assert.match(
  source,
  /const usedUrls = new Set\(draftAssetCandidates\.map\(\(item\) => item\.url\)\);[\s\S]*?sourceNoteImageCandidates\(matchingSourceNote, usedUrls\)/,
  "Sending a draft to image studio should deduplicate source-note images against current draft image candidates",
);

console.log("xhs-draft-workbench preview tests passed");

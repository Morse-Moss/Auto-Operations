import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const pageSource = readFileSync(path.resolve(__dirname, "../src/pages/platforms/xhs/xhs-draft-workbench.tsx"), "utf8");
const apiSource = readFileSync(path.resolve(__dirname, "../src/lib/api/shared.ts"), "utf8");
const controllerSource = readFileSync(path.resolve(__dirname, "../src/components/draft-workbench/use-draft-workbench.ts"), "utf8");
const controllerTypesSource = readFileSync(path.resolve(__dirname, "../src/components/draft-workbench/draft-workbench-types.ts"), "utf8");

const controllerModule = await import("../src/components/draft-workbench/use-draft-workbench.ts");
assert.equal(
  typeof controllerModule.replaceDraftById,
  "function",
  "Draft workbench should expose a tested immutable replacement helper",
);
const replaceDraftById = controllerModule.replaceDraftById as <T extends { id: number }>(drafts: T[], saved: T) => T[];
const originalDrafts = [
  { id: 1, title: "old title" },
  { id: 2, title: "other title" },
];
const savedDraft = { id: 1, title: "adopted title" };
const replacedDrafts = replaceDraftById(originalDrafts, savedDraft);
assert.equal(replacedDrafts[0], savedDraft, "Saved draft should replace the stale list entry");
assert.equal(replacedDrafts[1], originalDrafts[1], "Unrelated drafts should retain their identity");
assert.notEqual(replacedDrafts, originalDrafts, "Draft replacement should be immutable");

assert.match(
  apiSource,
  /fetchDraftRewriteCandidates\(draftId: number\)/,
  "Draft API should load persisted rewrite candidates for the selected draft",
);
assert.match(
  apiSource,
  /discardDraftRewriteCandidate\(\s*draftId: number,\s*mode:/,
  "Draft API should persist candidate discard",
);
assert.match(
  pageSource,
  /async function restoreRewriteCandidates\(draftId: number\)[\s\S]*?fetchDraftRewriteCandidates\(draftId\)[\s\S]*?if \(selectedDraft\) void restoreRewriteCandidates\(selectedDraft\.id\)/,
  "Draft workbench should restore candidates when selecting a draft",
);
assert.match(
  pageSource,
  /mode: rewriteTemplate/,
  "Rewrite generation should tell the backend which candidate mode to persist",
);
assert.match(
  pageSource,
  /const saved = await updateDraft\(draftId, \{[\s\S]*?title: candidate\.title,[\s\S]*?body: candidate\.body,[\s\S]*?tags: candidate\.tags[\s\S]*?controller\.applySavedDraft\(saved\)/,
  "Adopting a candidate should save and synchronize the current draft",
);
assert.match(
  pageSource,
  /const savedDraft = await updateDraft\(draftId, \{[\s\S]*?draft_name: controller\.draftName,[\s\S]*?controller\.applySavedDraft\(savedDraft\)[\s\S]*?rewriteDraftWithAi/,
  "Generating a candidate should synchronize the current draft saved before the AI call",
);
assert.match(
  pageSource,
  /await discardDraftRewriteCandidate\(draftId, mode\)/,
  "Discarding a candidate should update backend state",
);
assert.match(
  controllerTypesSource,
  /applySavedDraft\(draft: TDraft\): void/,
  "Draft workbench controller should expose saved-draft synchronization",
);
assert.match(
  controllerSource,
  /const applySavedDraft =[\s\S]*?setDrafts\([\s\S]*?replaceDraftById[\s\S]*?syncDraftState\(savedDraft\)/,
  "Saved-draft synchronization should update both the list and selected editor state",
);

console.log("xhs draft rewrite persistence tests passed");

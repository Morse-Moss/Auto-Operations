import {
  clearRewriteCandidate,
  getRewriteCandidate,
  parseRewriteCandidates,
  setRewriteCandidate,
  toRewriteCandidate,
} from "./xhs-rewrite-candidates.js";

function assert(condition: boolean, message: string): void {
  if (!condition) {
    throw new Error(message);
  }
}

const safeCandidate = toRewriteCandidate(
  {
    title: "安全改写标题",
    body: "安全改写正文",
    tags: [{ name: "安全" }],
  },
  101,
);

const polishCandidate = toRewriteCandidate(
  {
    title: "轻度润色标题",
    body: "轻度润色正文",
    tags: [{ name: "润色" }],
  },
  202,
);

const emptyCandidates = {};
const withSafe = setRewriteCandidate(emptyCandidates, "safe", safeCandidate);
const withSafeAndPolish = setRewriteCandidate(withSafe, "polish", polishCandidate);

assert(getRewriteCandidate(withSafeAndPolish, "safe")?.title === "安全改写标题", "safe candidate should survive after generating polish candidate");
assert(getRewriteCandidate(withSafeAndPolish, "polish")?.title === "轻度润色标题", "polish candidate should be stored independently");
assert(getRewriteCandidate(withSafeAndPolish, "seed") === null, "missing candidate should read as null");
assert(getRewriteCandidate(withSafeAndPolish, "safe")?.generatedAt === 101, "safe candidate should keep deterministic generatedAt");
assert(getRewriteCandidate(withSafeAndPolish, "polish")?.tags[0]?.name === "润色", "candidate should keep normalized tags");

const withoutPolish = clearRewriteCandidate(withSafeAndPolish, "polish");

assert(getRewriteCandidate(withoutPolish, "polish") === null, "clearing polish should remove only polish candidate");
assert(getRewriteCandidate(withoutPolish, "safe")?.body === "安全改写正文", "clearing polish should not remove safe candidate");
assert(withoutPolish !== withSafeAndPolish, "clearing should return a new map object");
assert(withSafe !== emptyCandidates, "setting should return a new map object");

const restored = parseRewriteCandidates({
  safe: {
    title: "restored title",
    body: "restored body",
    tags: [{ name: "restored" }],
    generated_at: "2026-07-22T16:00:00+08:00",
  },
  unknown: {
    title: "invalid mode",
    body: "invalid mode body",
    tags: [],
    generated_at: "2026-07-22T16:00:00+08:00",
  },
});

assert(getRewriteCandidate(restored, "safe")?.title === "restored title", "persisted safe candidate should restore");
assert(Number.isFinite(getRewriteCandidate(restored, "safe")?.generatedAt), "persisted generated_at should become a timestamp");
assert(Object.keys(restored).length === 1, "unknown rewrite modes should be ignored during restore");
assert(Object.keys(parseRewriteCandidates(null)).length === 0, "missing persisted candidates should restore as empty");

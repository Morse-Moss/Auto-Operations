import assert from "node:assert/strict";

import {
  parseDraftImageStudioContext,
  saveDraftImageStudioContext,
} from "../src/components/image-studio/draft-image-studio-context.ts";

const baseContext = {
  platform: "xhs",
  source: "draft" as const,
  draft_id: 1,
  draft_name: "测试草稿",
  title: "测试标题",
  body: "测试正文",
  source_note_id: null,
  candidate_images: [{ url: "/api/files/media/a.jpg", source: "draft_asset" }],
  created_at: Date.now(),
};

const parsed = parseDraftImageStudioContext({
  ...baseContext,
  tags: ["穿搭", { id: 12, name: "通勤" }, { name: "显瘦" }, "  "],
});

assert.ok(parsed, "Draft image studio context should accept legacy/string tag shapes");
assert.deepEqual(parsed.tags, [
  { id: "穿搭", name: "穿搭" },
  { id: "12", name: "通勤" },
  { name: "显瘦" },
]);

const storage = new Map<string, string>();
Object.defineProperty(globalThis, "window", {
  configurable: true,
  value: {
    sessionStorage: {
      setItem(key: string, value: string) {
        storage.set(key, value);
      },
      getItem(key: string) {
        return storage.get(key) ?? null;
      },
      removeItem(key: string) {
        storage.delete(key);
      },
    },
  },
});

const saved = saveDraftImageStudioContext("test:image-studio:draft-context", {
  ...baseContext,
  tags: ["穿搭", { id: 12, name: "通勤" }, { name: "显瘦" }, "  "] as never,
});

assert.equal(saved, true);
const raw = storage.get("test:image-studio:draft-context");
assert.ok(raw, "Draft image studio context should be saved");
assert.deepEqual(JSON.parse(raw).tags, [
  { id: "穿搭", name: "穿搭" },
  { id: "12", name: "通勤" },
  { name: "显瘦" },
]);

console.log("draft-image-studio context tests passed");

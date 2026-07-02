import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { registerHooks, stripTypeScriptTypes } from "node:module";

registerHooks({
  load(url, context, nextLoad) {
    if (url.endsWith(".tsx")) {
      const source = readFileSync(new URL(url), "utf8");
      return {
        format: "module",
        shortCircuit: true,
        source: stripTypeScriptTypes(source, { mode: "strip" }),
      };
    }
    return nextLoad(url, context);
  },
});

const { createDemoPlatformContentLibraryAdapter } = await import("../src/pages/demo-platform/demo-content-library-adapter.tsx");

const adapter = createDemoPlatformContentLibraryAdapter();
assert.equal(adapter.platform, "demo_platform");
assert.equal(adapter.pageTitle.includes("Demo"), true);

const page = await adapter.loadItems({ page: 1, page_size: 20 });
assert.equal(page.total, 2);
assert.equal(page.items[0].platform, "demo_platform");
assert.equal(page.items[0].title.length > 0, true);

const detail = await adapter.loadItem(page.items[0].id);
assert.equal(detail.id, page.items[0].id);

const assets = await adapter.loadAssets(page.items[0].id);
assert.equal(assets.page, 1);
assert.equal(Array.isArray(assets.items), true);

const comments = await adapter.loadComments(page.items[0].id, 1);
assert.equal(comments.total, 0);

assert.equal(adapter.capabilities.canReadComments, true, "demo platform may read empty local comments");
assert.equal(adapter.capabilities.canFilterAssets, false, "demo platform must not expose asset filters it does not implement");
assert.equal(adapter.capabilities.canCreateDraft, false, "demo platform must not expose create draft actions");
assert.equal(adapter.capabilities.canBatchCreateDrafts, false, "demo platform must not expose batch draft actions");
assert.equal(adapter.capabilities.canDelete, false, "demo platform must not expose delete actions");
assert.equal(adapter.capabilities.canBatchDelete, false, "demo platform must not expose batch delete actions");
assert.equal(adapter.capabilities.canTag, false, "demo platform must not expose tag write actions");
assert.equal(adapter.capabilities.canExport, false, "demo platform must not expose export actions");
await assert.rejects(() => adapter.createTag({ name: "blocked" }), /read-only/);
await assert.rejects(() => adapter.batchTagItems({ item_ids: [page.items[0].id], tag_ids: [1], mode: "add" }), /read-only/);
await assert.rejects(() => adapter.deleteItem(page.items[0].id), /read-only/);
await assert.rejects(() => adapter.batchCreateDrafts([page.items[0].id]), /read-only/);
await assert.rejects(() => adapter.createDraftFromItem(page.items[0], "rewrite"), /read-only/);
await assert.rejects(() => adapter.exportItems([page.items[0].id], "json"), /read-only/);
await assert.rejects(
  () => adapter.downloadExport({ exported_count: 0, file_name: "demo.json", file_path: "", download_url: "" }),
  /read-only/,
);
assert.equal(adapter.renderDetail !== undefined, true);

console.log("demo-platform-content-library-adapter tests passed");

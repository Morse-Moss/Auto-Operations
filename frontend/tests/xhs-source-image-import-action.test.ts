import assert from "node:assert/strict";

import {
  getActionErrorMessage,
  runXhsSourceImageImportAction,
  type XhsSourceImageImportResult,
} from "../src/pages/platforms/xhs/xhs-source-image-import-action.ts";

type NoticeKind = "success" | "warning" | "error";

function createHarness(importImages: () => Promise<XhsSourceImageImportResult>) {
  const busyStates: boolean[] = [];
  const detailErrors: Array<string | null> = [];
  const actionMessages: Array<string | null> = [];
  const notices: Array<{ kind: NoticeKind; text: string }> = [];
  let refreshCount = 0;

  return {
    busyStates,
    detailErrors,
    actionMessages,
    notices,
    get refreshCount() {
      return refreshCount;
    },
    dependencies: {
      importImages,
      refreshSelectedItem: async () => {
        refreshCount += 1;
      },
      setBusy: (busy: boolean) => busyStates.push(busy),
      setDetailError: (error: string | null) => detailErrors.push(error),
      setDetailActionMessage: (message: string | null) => actionMessages.push(message),
      notify: (kind: NoticeKind, text: string) => notices.push({ kind, text }),
    },
  };
}

const loginMessage = "请前往账号矩阵登录后重试";
assert.equal(
  getActionErrorMessage({
    response: { data: { detail: { code: "xhs_login_required", message: `  ${loginMessage}  ` } } },
  }),
  loginMessage,
  "structured HTTP 409 detail.message should be trimmed and shown verbatim",
);
assert.equal(
  getActionErrorMessage({ response: { data: { detail: "  账号登录已失效  " } } }),
  "账号登录已失效",
  "string detail should be trimmed before display",
);
assert.equal(
  getActionErrorMessage(Object.assign(new Error("fallback message"), {
    response: { data: { detail: { code: "xhs_login_required", message: "   " } } },
  })),
  "fallback message",
  "blank structured messages should continue to the existing Error fallback",
);
assert.equal(
  getActionErrorMessage(Object.assign(new Error("fallback string detail"), {
    response: { data: { detail: "   " } },
  })),
  "fallback string detail",
  "blank string details should continue to the existing Error fallback",
);

const successHarness = createHarness(async () => ({
  total_source_image_count: 4,
  imported_count: 3,
  skipped_count: 1,
  downloaded_count: 3,
  failed_count: 0,
}));
await runXhsSourceImageImportAction(successHarness.dependencies);
assert.deepEqual(successHarness.busyStates, [true, false]);
assert.equal(successHarness.refreshCount, 1);
assert.deepEqual(successHarness.detailErrors, [null, null]);
assert.equal(successHarness.actionMessages.length, 2);
assert.match(successHarness.actionMessages[0] ?? "", /正在自动补全原文图片/);
assert.match(successHarness.actionMessages[1] ?? "", /新增 3 张，已存在 1 张，已保存 3 张，失败 0 张/);
assert.deepEqual(successHarness.notices, [{ kind: "success", text: successHarness.actionMessages[1] }]);

const partialHarness = createHarness(async () => ({
  total_source_image_count: 5,
  imported_count: 3,
  skipped_count: 1,
  downloaded_count: 2,
  failed_count: 1,
}));
await runXhsSourceImageImportAction(partialHarness.dependencies);
assert.deepEqual(partialHarness.busyStates, [true, false]);
assert.equal(partialHarness.refreshCount, 1);
assert.match(partialHarness.detailErrors.at(-1) ?? "", /部分图片保存失败/);
assert.match(partialHarness.actionMessages.at(-1) ?? "", /处理完成（部分失败）/);
assert.match(partialHarness.actionMessages.at(-1) ?? "", /新增 3 张，已存在 1 张，已保存 2 张，失败 1 张/);
assert.deepEqual(partialHarness.notices, [{ kind: "warning", text: partialHarness.actionMessages.at(-1) }]);

const zeroHarness = createHarness(async () => ({
  total_source_image_count: 0,
  imported_count: 0,
  skipped_count: 0,
  downloaded_count: 0,
  failed_count: 0,
}));
await runXhsSourceImageImportAction(zeroHarness.dependencies);
assert.deepEqual(zeroHarness.busyStates, [true, false]);
assert.equal(zeroHarness.refreshCount, 0);
assert.deepEqual(zeroHarness.actionMessages, ["正在自动补全原文图片...", null]);
assert.equal(zeroHarness.detailErrors.at(-1), "自动补全原文图片失败：原文详情未返回可补全的图片。");
assert.deepEqual(zeroHarness.notices, [{ kind: "error", text: zeroHarness.detailErrors.at(-1) }]);

const throwHarness = createHarness(async () => {
  throw { response: { data: { detail: { code: "xhs_login_required", message: loginMessage } } } };
});
await runXhsSourceImageImportAction(throwHarness.dependencies);
assert.deepEqual(throwHarness.busyStates, [true, false]);
assert.equal(throwHarness.refreshCount, 0);
assert.deepEqual(throwHarness.actionMessages, ["正在自动补全原文图片...", null]);
assert.equal(throwHarness.detailErrors.at(-1), `自动补全原文图片失败：${loginMessage}`);
assert.deepEqual(throwHarness.notices, [{ kind: "error", text: throwHarness.detailErrors.at(-1) }]);

let scriptSideEffectCount = 0;
const originalNavigator = globalThis.navigator;
const originalDocument = globalThis.document;
Object.defineProperty(globalThis, "navigator", {
  configurable: true,
  value: {
    clipboard: { writeText: async () => { scriptSideEffectCount += 1; } },
    sendBeacon: () => { scriptSideEffectCount += 1; return true; },
  },
});
Object.defineProperty(globalThis, "document", {
  configurable: true,
  value: { execCommand: () => { scriptSideEffectCount += 1; return true; } },
});
try {
  const sideEffectHarness = createHarness(async () => ({
    total_source_image_count: 1,
    imported_count: 1,
    skipped_count: 0,
    downloaded_count: 1,
    failed_count: 0,
  }));
  await runXhsSourceImageImportAction(sideEffectHarness.dependencies);
  assert.equal(scriptSideEffectCount, 0, "automatic import must not access script, beacon, or clipboard APIs");
} finally {
  Object.defineProperty(globalThis, "navigator", { configurable: true, value: originalNavigator });
  if (originalDocument === undefined) {
    delete (globalThis as { document?: unknown }).document;
  } else {
    Object.defineProperty(globalThis, "document", { configurable: true, value: originalDocument });
  }
}

console.log("xhs-source-image-import-action tests passed");

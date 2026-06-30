import assert from "node:assert/strict";

import {
  CREATOR_LOGIN_REQUIRED_MESSAGE,
  accountLoginStatusLabel,
  publishErrorMessage,
} from "../src/pages/platforms/xhs/xhs-user-messages.ts";

assert.equal(
  publishErrorMessage("Account has no cookies"),
  CREATOR_LOGIN_REQUIRED_MESSAGE,
  "Creator publish cookie errors should tell the user to log in instead of exposing the raw backend message",
);

assert.equal(
  publishErrorMessage("Some upstream error"),
  "Some upstream error",
  "Unknown backend errors should remain visible for diagnosis",
);

assert.equal(accountLoginStatusLabel("active"), "已登录");
assert.equal(accountLoginStatusLabel("healthy"), "已登录");
assert.equal(accountLoginStatusLabel("expired"), "登录已过期");
assert.equal(accountLoginStatusLabel("unknown"), "未确认登录状态");

console.log("xhs-user-messages tests passed");

import assert from "node:assert/strict";

import {
  buildXhsPcAccountOptions,
  selectReadyXhsPcAccountId,
} from "../src/pages/platforms/xhs/xhs-pc-account-selection.ts";
import type { PlatformAccount } from "../src/types/index.ts";

const accounts: PlatformAccount[] = [
  {
    id: 1,
    platform: "xhs",
    sub_type: "pc",
    nickname: "已失效账号",
    status: "active",
    login_ready: false,
    login_readiness_message: "账号登录信息不可用，请重新登录",
  },
  {
    id: 2,
    platform: "xhs",
    sub_type: "pc",
    nickname: "可用账号 A",
    status: "active",
    login_ready: true,
  },
  {
    id: 3,
    platform: "xhs",
    sub_type: "pc",
    nickname: "可用账号 B",
    status: "active",
    login_ready: true,
  },
  {
    id: 4,
    platform: "xhs",
    sub_type: "creator",
    nickname: "Creator",
    status: "active",
  },
];

assert.equal(
  selectReadyXhsPcAccountId(accounts, 3),
  3,
  "the current PC account should be retained while it remains ready",
);
assert.equal(
  selectReadyXhsPcAccountId(accounts, 1),
  2,
  "an unready current account should fall back to the first ready PC account",
);
assert.equal(
  selectReadyXhsPcAccountId(accounts, null),
  2,
  "the first ready PC account should be selected by API order",
);
assert.equal(
  selectReadyXhsPcAccountId(accounts.filter((account) => account.login_ready !== true), 1),
  null,
  "no account should be selected when none are ready",
);

const options = buildXhsPcAccountOptions(accounts);
assert.deepEqual(
  options.map(({ value, disabled }) => ({ value, disabled })),
  [
    { value: 1, disabled: true },
    { value: 2, disabled: false },
    { value: 3, disabled: false },
  ],
  "all PC accounts should remain visible while unready accounts are disabled",
);
assert.match(options[0].label, /需重新登录/);
assert.doesNotMatch(options[0].label, /web_session|session|Cookie/i);

console.log("xhs-pc-account-selection tests passed");

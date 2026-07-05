import assert from "node:assert/strict";

import {
  getDefaultLoginMethod,
  type AccountAuthSchema,
} from "../src/components/account/account-auth-schema.ts";

const xhsRegistrySchema: AccountAuthSchema = {
  platform: "xhs",
  label: "小红书",
  drawerTitle: "添加小红书账号",
  defaultAccountType: "pc",
  accountTypes: [
    { label: "PC", value: "pc" },
    { label: "Creator", value: "creator" },
  ],
  loginMethods: [
    { label: "小红书 PC Cookie 导入", value: "cookie" },
    { label: "小红书扫码登录", value: "qr" },
  ],
  accountTypeSelectorVisible: true,
};

assert.equal(
  getDefaultLoginMethod(xhsRegistrySchema, undefined, "creator"),
  "qr",
  "Creator binding should keep QR as the default after registry schemas load so the QR panel continues polling the created session",
);

assert.equal(
  getDefaultLoginMethod(xhsRegistrySchema, "cookie", "creator"),
  "cookie",
  "An explicit user-selected login method should still be respected",
);

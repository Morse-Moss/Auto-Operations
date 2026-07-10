import assert from "node:assert/strict";

import { AxiosError } from "axios";

import { accountLoginErrorMessage } from "../src/components/account/account-login-errors.ts";

const responseWithDetail = {
  data: { detail: "账号登录已确认，但读取账号资料失败，请刷新二维码后重试。" },
  status: 502,
  statusText: "Bad Gateway",
  headers: {},
  config: {},
};

assert.equal(
  accountLoginErrorMessage(
    new AxiosError("profile failed", "ERR_BAD_RESPONSE", undefined, undefined, responseWithDetail),
    "轮询登录状态失败，正在等待下一次尝试。",
  ),
  "账号登录已确认，但读取账号资料失败，请刷新二维码后重试。",
  "QR polling should show the actionable backend detail when login profile fetch fails",
);

assert.equal(
  accountLoginErrorMessage(new Error("network"), "轮询登录状态失败，正在等待下一次尝试。"),
  "轮询登录状态失败，正在等待下一次尝试。",
  "Non-Axios polling failures should keep the generic retry message",
);

console.log("account-login-error-message tests passed");

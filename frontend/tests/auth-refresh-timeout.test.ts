import assert from "node:assert/strict";

import axios from "axios";

const storage = new Map<string, string>();

globalThis.window = {
  localStorage: {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => {
      storage.set(key, value);
    },
    removeItem: (key: string) => {
      storage.delete(key);
    },
  },
} as unknown as Window & typeof globalThis;

storage.set("spider_xhs_refresh_token", "refresh-token");

const api = await import("../src/lib/api.ts");

const originalPost = axios.post;
let capturedConfig: unknown;

axios.post = (async (_url: string, _payload?: unknown, config?: unknown) => {
  capturedConfig = config;
  return { data: { access_token: "new-access-token", token_type: "bearer" } };
}) as typeof axios.post;

try {
  await api.refreshAccessToken();
} finally {
  axios.post = originalPost;
}

assert.equal(api.getAccessToken(), "new-access-token");
assert.equal(
  (capturedConfig as { timeout?: number } | undefined)?.timeout,
  10000,
  "refreshAccessToken should use a short request timeout so protected routes cannot stay black indefinitely",
);

console.log("auth-refresh-timeout tests passed");

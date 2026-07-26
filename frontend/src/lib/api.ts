// client.ts also exports internal singletons (http, persistAuthPayload) shared by
// the domain files; they were module-private before the split, so re-export only
// the original public surface here.
export {
  getAccessToken,
  hasRefreshToken,
  clearAuthTokens,
  refreshAccessToken,
  apiErrorMessage,
  getUsageLimitError,
} from "./api/client";
export type { AuthCredentials } from "./api/client";
export * from "./api/auth";
export * from "./api/admin";
export * from "./api/shared";
export * from "./api/xhs";
export * from "./api/wechat-official";
export * from "./api/feishu";
export * from "./api/ai";

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const mainSource = readFileSync("frontend/src/main.tsx", "utf8");
const apiSource = readFileSync("frontend/src/lib/api.ts", "utf8");
const diagnosticsSource = readFileSync("frontend/src/lib/diagnostics.ts", "utf8");
const errorBoundarySource = readFileSync("frontend/src/components/ui/error-boundary.tsx", "utf8");

assert.match(
  mainSource,
  /installGlobalDiagnosticsHandlers\(\);/,
  "main entry should install global browser error diagnostics before rendering",
);
assert.match(
  mainSource,
  /<ErrorBoundary>[\s\S]*?<AppProviders>/,
  "React root should wrap the app with ErrorBoundary",
);
assert.match(
  apiSource,
  /ensureRequestId\(\)/,
  "API request interceptor should attach a request id to outbound requests",
);
assert.match(
  apiSource,
  /recordResponseRequestId\(response\.headers\["x-request-id"\]\)/,
  "API response interceptor should retain backend request ids for diagnostics",
);
assert.match(
  diagnosticsSource,
  /export function buildDiagnosticText/,
  "diagnostics helper should build copyable support text",
);
assert.match(
  diagnosticsSource,
  /window\.addEventListener\("error"/,
  "diagnostics helper should subscribe to window error events",
);
assert.match(
  diagnosticsSource,
  /window\.addEventListener\("unhandledrejection"/,
  "diagnostics helper should subscribe to unhandled promise rejection events",
);
assert.match(
  diagnosticsSource,
  /navigator\.sendBeacon/,
  "diagnostic reports should use sendBeacon when available",
);
assert.match(
  diagnosticsSource,
  /\/api\/client-errors/,
  "frontend diagnostics should post to the backend client error endpoint",
);
assert.match(
  diagnosticsSource,
  /VITE_APP_VERSION/,
  "frontend diagnostics should include the build version",
);
assert.match(
  errorBoundarySource,
  /页面加载失败/,
  "ErrorBoundary should show a user-facing fallback instead of a blank screen",
);
assert.match(
  errorBoundarySource,
  /复制诊断信息/,
  "ErrorBoundary should let users copy diagnostic information",
);
assert.match(
  errorBoundarySource,
  /\/logo\.png/,
  "ErrorBoundary should use the canonical Tavix logo asset",
);
assert.match(
  errorBoundarySource,
  /TAVIX OPERATIONS PLATFORM/,
  "ErrorBoundary should identify the Tavix product",
);
assert.match(
  errorBoundarySource,
  /拓效自动化运营系统/,
  "ErrorBoundary should show the Chinese Tavix product name",
);
assert.match(
  errorBoundarySource,
  /letterSpacing: 0/,
  "ErrorBoundary brand text should use the product typography spacing rule",
);

console.log("diagnostics-contract tests passed");

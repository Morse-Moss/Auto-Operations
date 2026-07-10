export type ClientDiagnosticReport = {
  event_type: string;
  message: string;
  stack?: string;
  url: string;
  app_version: string;
  request_id?: string;
  user_agent: string;
  timestamp: string;
  extra?: Record<string, unknown>;
};

const CLIENT_ERROR_ENDPOINT = "/api/client-errors";
const MAX_MESSAGE_LENGTH = 2000;
const MAX_STACK_LENGTH = 12000;
const APP_VERSION =
  (import.meta as ImportMeta & { env?: { VITE_APP_VERSION?: string } }).env?.VITE_APP_VERSION || "dev";

let lastRequestId = "";
let handlersInstalled = false;

function safeTrim(value: unknown, maxLength: number): string {
  if (value === null || value === undefined) return "";
  const text = String(value);
  return text.length > maxLength ? `${text.slice(0, maxLength)}...` : text;
}

function generateRequestId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `web-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function safeCurrentUrl(): string {
  if (typeof window === "undefined") return "";
  try {
    const url = new URL(window.location.href);
    return `${url.origin}${url.pathname}`;
  } catch {
    return window.location.pathname || "";
  }
}

function normalizeError(error: unknown): { message: string; stack: string } {
  if (error instanceof Error) {
    return {
      message: safeTrim(error.message || error.name || "Browser error", MAX_MESSAGE_LENGTH),
      stack: safeTrim(error.stack || "", MAX_STACK_LENGTH),
    };
  }
  if (typeof error === "string") {
    return { message: safeTrim(error, MAX_MESSAGE_LENGTH), stack: "" };
  }
  return { message: safeTrim(error || "Browser error", MAX_MESSAGE_LENGTH), stack: "" };
}

export function ensureRequestId(): string {
  lastRequestId = generateRequestId();
  return lastRequestId;
}

export function recordResponseRequestId(value: unknown): void {
  if (typeof value === "string" && value.trim()) {
    lastRequestId = value.trim();
  }
}

export function createDiagnosticReport(
  input: Partial<ClientDiagnosticReport> & { error?: unknown } = {},
): ClientDiagnosticReport {
  const normalized = normalizeError(input.error ?? input.message);
  const requestId = input.request_id || lastRequestId || ensureRequestId();
  return {
    event_type: safeTrim(input.event_type || "browser_error", 80),
    message: safeTrim(input.message || normalized.message || "Browser error", MAX_MESSAGE_LENGTH),
    stack: safeTrim(input.stack || normalized.stack || "", MAX_STACK_LENGTH),
    url: safeTrim(input.url || safeCurrentUrl(), 2048),
    app_version: safeTrim(input.app_version || APP_VERSION, 120),
    request_id: safeTrim(requestId, 120),
    user_agent: safeTrim(input.user_agent || (typeof navigator === "undefined" ? "" : navigator.userAgent), 512),
    timestamp: input.timestamp || new Date().toISOString(),
    extra: input.extra,
  };
}

export function buildDiagnosticText(input?: Partial<ClientDiagnosticReport>): string {
  const report = createDiagnosticReport(input);
  const lines = [
    "页面加载失败",
    `页面: ${report.url || "-"}`,
    `版本: ${report.app_version || "-"}`,
    `时间: ${report.timestamp || "-"}`,
    `Request ID: ${report.request_id || "-"}`,
    `错误: ${report.message || "-"}`,
    `浏览器: ${report.user_agent || "-"}`,
  ];
  if (report.stack) {
    lines.push("堆栈:", report.stack);
  }
  return lines.join("\n");
}

export function reportClientError(input: Partial<ClientDiagnosticReport> & { error?: unknown } = {}): ClientDiagnosticReport {
  const report = createDiagnosticReport(input);
  const body = JSON.stringify(report);

  try {
    if (typeof navigator !== "undefined" && navigator.sendBeacon) {
      const blob = new Blob([body], { type: "application/json" });
      if (navigator.sendBeacon(CLIENT_ERROR_ENDPOINT, blob)) {
        return report;
      }
    }
  } catch {
    // Ignore diagnostics transport failures; the user-facing fallback should still render.
  }

  if (typeof fetch !== "undefined") {
    void fetch(CLIENT_ERROR_ENDPOINT, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Request-ID": report.request_id || ensureRequestId(),
      },
      body,
      keepalive: true,
    }).catch(() => undefined);
  }

  return report;
}

export function installGlobalDiagnosticsHandlers(): void {
  if (handlersInstalled || typeof window === "undefined") return;
  handlersInstalled = true;

  window.addEventListener("error", (event) => {
    reportClientError({
      event_type: "window_error",
      message: event.message,
      error: event.error,
      extra: {
        filename: event.filename,
        lineno: event.lineno,
        colno: event.colno,
      },
    });
  });

  window.addEventListener("unhandledrejection", (event) => {
    reportClientError({
      event_type: "unhandledrejection",
      error: event.reason,
    });
  });
}

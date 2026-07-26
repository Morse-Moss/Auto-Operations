import axios, { AxiosHeaders } from "axios";
import { message } from "antd";

import { ensureRequestId, recordResponseRequestId } from "../diagnostics";
import type {
  AuthPayload,
  UsageLimitError
} from "../../types";

export const http = axios.create({
  baseURL: "/api",
  timeout: 120000,
});

const REFRESH_TOKEN_KEY = "spider_xhs_refresh_token";
const AUTH_REFRESH_TIMEOUT_MS = 10000;
let accessToken: string | null = null;
let refreshPromise: Promise<string> | null = null;
let authExpiredMessageShown = false;

export type AuthCredentials = {
  username: string;
  password: string;
  invite_code?: string;
};

export function getAccessToken(): string | null {
  return accessToken;
}

export function hasRefreshToken(): boolean {
  return Boolean(window.localStorage.getItem(REFRESH_TOKEN_KEY));
}

function getRefreshToken(): string | null {
  return window.localStorage.getItem(REFRESH_TOKEN_KEY);
}

function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function persistAuthPayload(payload: AuthPayload): AuthPayload {
  setAccessToken(payload.access_token);
  if (payload.refresh_token) {
    window.localStorage.setItem(REFRESH_TOKEN_KEY, payload.refresh_token);
  }
  return payload;
}

export function clearAuthTokens(): void {
  setAccessToken(null);
  window.localStorage.removeItem(REFRESH_TOKEN_KEY);
}

http.interceptors.request.use((config) => {
  const headers = AxiosHeaders.from(config.headers);
  headers.set("X-Request-ID", ensureRequestId());
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }
  config.headers = headers;
  return config;
});

http.interceptors.response.use(
  (response) => {
    recordResponseRequestId(response.headers["x-request-id"]);
    return response;
  },
  async (error) => {
    recordResponseRequestId(error.response?.headers?.["x-request-id"]);
    const originalRequest = error.config as typeof error.config & { _authRetry?: boolean; _silent?: boolean };
    const isRefreshRequest = originalRequest?.url === "/auth/refresh";
    if (isRefreshRequest) {
      clearAuthTokens();
    }
    if (error.response?.status !== 401 || originalRequest?._authRetry || isRefreshRequest || !getRefreshToken()) {
      if (!originalRequest?._silent) {
        const msg = apiErrorMessage(error, "请求失败，请稍后重试");
        message.error(msg);
      }
      return Promise.reject(error);
    }

    originalRequest._authRetry = true;
    try {
      const token = await refreshAccessToken();
      const headers = AxiosHeaders.from(originalRequest.headers);
      headers.set("Authorization", `Bearer ${token}`);
      headers.set("X-Request-ID", ensureRequestId());
      originalRequest.headers = headers;
      return http(originalRequest);
    } catch (refreshError) {
      clearAuthTokens();
      if (!authExpiredMessageShown) {
        authExpiredMessageShown = true;
        message.error("登录已过期，请重新登录");
      }
      return Promise.reject(refreshError);
    }
  }
);

export async function refreshAccessToken(): Promise<string> {
  if (refreshPromise) {
    return refreshPromise;
  }

  refreshPromise = (async () => {
    const refreshToken = getRefreshToken();
    if (!refreshToken) {
      throw new Error("Missing refresh token");
    }

    const response = await axios.post<{ access_token: string; token_type: "bearer" }>(
      "/api/auth/refresh",
      {
        refresh_token: refreshToken
      },
      {
        timeout: AUTH_REFRESH_TIMEOUT_MS,
        headers: { "X-Request-ID": ensureRequestId() }
      }
    );
    recordResponseRequestId(response.headers["x-request-id"]);
    setAccessToken(response.data.access_token);
    authExpiredMessageShown = false;
    return response.data.access_token;
  })().finally(() => {
    refreshPromise = null;
  });

  return refreshPromise;
}

export function apiErrorMessage(error: unknown, fallback: string): string {
  if (!axios.isAxiosError(error)) return fallback;
  const data = error.response?.data;
  if (data && typeof data === "object") {
    const record = data as Record<string, unknown>;
    if (typeof record.message === "string" && record.message.trim()) return record.message;
    const detail = record.detail;
    if (typeof detail === "string" && detail.trim()) return detail;
    if (detail && typeof detail === "object") {
      const detailRecord = detail as Record<string, unknown>;
      if (typeof detailRecord.message === "string" && detailRecord.message.trim()) return detailRecord.message;
    }
  }
  return fallback;
}

export function getUsageLimitError(error: unknown): UsageLimitError | null {
  if (!axios.isAxiosError(error)) return null;
  const data = error.response?.data;
  const detail = data && typeof data === "object" ? (data as Record<string, unknown>).detail : null;
  const payload = detail && typeof detail === "object" ? detail : data;
  if (!payload || typeof payload !== "object") return null;
  const record = payload as UsageLimitError;
  if (record.code === "usage_quota_insufficient") {
    const required = typeof record.required === "number" ? record.required : null;
    const remaining = typeof record.remaining === "number" ? record.remaining : null;
    return {
      ...record,
      message:
        required !== null && remaining !== null
          ? `积分不足，本次需要 ${required} 积分，当前剩余 ${remaining} 积分。`
          : "积分不足，请联系管理员补充额度后再试。",
    };
  }
  return null;
}

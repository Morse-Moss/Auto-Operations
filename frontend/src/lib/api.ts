import axios from "axios";
import { message } from "antd";

import { fallbackPlatforms } from "./platforms";
import type {
  AuthPayload,
  AutoTask,
  AutoTaskCreatePayload,
  AutoTaskRunResult,
  AutoTaskUpdatePayload,
  AnalyticsCommentInsight,
  AnalyticsHotTopic,
  AnalyticsReportPayload,
  AnalyticsReportResponse,
  AnalyticsTopContent,
  AppNotification,
  BenchmarkCreateDraftsResponse,
  BenchmarkOverview,
  BatchCreateDraftsPayload,
  BatchCreateDraftsResponse,
  BatchTagNotesPayload,
  BatchTagNotesResponse,
  ComposeImagePayload,
  CreateDraftPayload,
  DashboardOverview,
  Draft,
  DescribeImagePayload,
  GenerateNotePayload,
  GenerateCoverPayload,
  GenerateImagePayload,
  GenerateImageResult,
  GeneratedImageAsset,
  GenerateTagsPayload,
  GenerateTitlePayload,
  ImageUtilityFile,
  CrawlDiagnostic,
  HuitunDiscoveryRunPayload,
  KeywordCandidateImportPayload,
  KeywordCandidateImportResponse,
  KeywordDiscoveryRun,
  KeywordGroup,
  KeywordGroupDetail,
  KeywordGroupPayload,
  ModelConfig,
  ModelConfigPayload,
  ModelType,
  MonitoringNote,
  MonitoringRefreshResponse,
  MonitoringSnapshot,
  MonitoringTarget,
  MonitoringTargetPayload,
  NoteAsset,
  NoteComment,
  NotesExportPayload,
  NotesExportResponse,
  Paginated,
  PlatformAccount,
  PlatformMeta,
  PlatformUser,
  PublishAsset,
  PublishAssetPayload,
  PublishJob,
  PublishJobUpdatePayload,
  PolishTextPayload,
  ResizeImagePayload,
  RewriteDraftPayload,
  RunDueTasksResponse,
  SchedulerStatus,
  SavedNote,
  SaveNotesResponse,
  SendDraftToPublishPayload,
  Tag,
  UserImageFile,
  TagPayload,
  TaskRecord,
  WechatOfficialArticleComment,
  WechatOfficialArticleCommentsPayload,
  WechatOfficialArticleMetric,
  WechatOfficialArticleMetricsPayload,
  WechatOfficialArticleSnapshot,
  WechatOfficialArticleSnapshotPayload,
  WechatOfficialArticleSyncPayload,
  WechatOfficialArticleSyncResponse,
  WechatOfficialBackendLoginCompletePayload,
  WechatOfficialBackendSession,
  WechatOfficialContentLibraryItem,
  WechatOfficialCreateDraftPayload,
  WechatOfficialCrawlAccount,
  WechatOfficialCredential,
  WechatOfficialCredentialGuide,
  WechatOfficialCredentialImportPayload,
  WechatOfficialCredentialValidatePayload,
  WechatOfficialCredentialValidation,
  WechatOfficialDraft,
  WechatOfficialDraftDryRun,
  WechatOfficialDraftDryRunPayload,
  WechatOfficialListResponse,
  WechatOfficialOverview,
  WechatOfficialProxy,
  WechatOfficialProxyTestPayload,
  WechatOfficialQrLoginSession,
  WechatOfficialRecommendationUpdatePayload,
  WechatOfficialRedfoxAccountCollectPayload,
  WechatOfficialRedfoxCollectResponse,
  WechatOfficialRedfoxConfigPayload,
  WechatOfficialRedfoxConfigResponse,
  WechatOfficialRedfoxKeywordCollectPayload,
  WechatOfficialRedfoxUrlImportPayload,
  WechatOfficialSearchAccountsPayload,
  XhsNoteSearchResponse,
  XhsDataCrawlItem,
  XhsDataCrawlPayload,
  XhsDataCrawlResponse,
  XhsKeywordGroupCrawlPayload,
  XhsKeywordGroupCrawlSummary,
  XhsSearchOptions,
  XhsSearchNote,
  XhsQrLoginSession
} from "../types";

const http = axios.create({
  baseURL: "/api",
  timeout: 120000,
});

const REFRESH_TOKEN_KEY = "spider_xhs_refresh_token";
let accessToken: string | null = null;
let refreshPromise: Promise<string> | null = null;
let authExpiredMessageShown = false;

export type AuthCredentials = {
  username: string;
  password: string;
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

function persistAuthPayload(payload: AuthPayload): AuthPayload {
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
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  return config;
});

http.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config as typeof error.config & { _authRetry?: boolean; _silent?: boolean };
    if (error.response?.status !== 401 || originalRequest?._authRetry || !getRefreshToken()) {
      if (!originalRequest?._silent) {
        const detail = error.response?.data?.detail;
        const msg = typeof detail === "string" ? detail : "请求失败，请稍后重试";
        message.error(msg);
      }
      return Promise.reject(error);
    }

    originalRequest._authRetry = true;
    try {
      const token = await refreshAccessToken();
      originalRequest.headers.Authorization = `Bearer ${token}`;
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

export async function login(credentials: AuthCredentials): Promise<AuthPayload> {
  const response = await http.post<AuthPayload>("/auth/login", credentials);
  return persistAuthPayload(response.data);
}

export async function register(credentials: AuthCredentials): Promise<AuthPayload> {
  const response = await http.post<AuthPayload>("/auth/register", credentials);
  return persistAuthPayload(response.data);
}

export async function refreshAccessToken(): Promise<string> {
  if (refreshPromise) {
    return refreshPromise;
  }

  refreshPromise = (async () => {
    const refreshToken = getRefreshToken();
    if (!refreshToken) {
      throw new Error("Missing refresh token");
    }

    const response = await axios.post<{ access_token: string; token_type: "bearer" }>("/api/auth/refresh", {
      refresh_token: refreshToken
    });
    setAccessToken(response.data.access_token);
    authExpiredMessageShown = false;
    return response.data.access_token;
  })().finally(() => {
    refreshPromise = null;
  });

  return refreshPromise;
}

export async function fetchMe(): Promise<PlatformUser> {
  const response = await http.get<PlatformUser>("/auth/me");
  return response.data;
}

export async function bootstrapAuth(): Promise<PlatformUser | null> {
  if (!getAccessToken() && hasRefreshToken()) {
    await refreshAccessToken();
  }
  if (!getAccessToken()) {
    return null;
  }
  return fetchMe();
}

export async function logout(): Promise<void> {
  try {
    await http.post("/auth/logout");
  } finally {
    clearAuthTokens();
  }
}

export async function fetchPlatforms(): Promise<PlatformMeta[]> {
  try {
    const response = await http.get<Paginated<PlatformMeta>>("/platforms");
    return response.data.items;
  } catch {
    return fallbackPlatforms;
  }
}

export async function fetchXhsOverview(): Promise<DashboardOverview> {
  const response = await http.get<DashboardOverview>("/xhs/analytics/overview");
  return response.data;
}

export async function fetchWechatOfficialOverview(): Promise<WechatOfficialOverview> {
  const response = await http.get<WechatOfficialOverview>("/wechat-official/overview");
  return response.data;
}

export async function startWechatOfficialQrLogin(): Promise<WechatOfficialQrLoginSession> {
  const response = await http.post<WechatOfficialQrLoginSession>("/wechat-official/accounts/login/qrcode");
  return response.data;
}

export async function completeWechatOfficialQrLogin(
  loginSessionId: number,
  payload: WechatOfficialBackendLoginCompletePayload
): Promise<WechatOfficialBackendSession> {
  const response = await http.post<WechatOfficialBackendSession>(
    `/wechat-official/accounts/login/${loginSessionId}/complete`,
    payload
  );
  return response.data;
}

export async function fetchWechatOfficialSessions(): Promise<WechatOfficialListResponse<WechatOfficialBackendSession>> {
  const response = await http.get<WechatOfficialListResponse<WechatOfficialBackendSession>>(
    "/wechat-official/accounts/sessions"
  );
  return response.data;
}

export async function fetchWechatOfficialCredentialGuide(): Promise<WechatOfficialCredentialGuide> {
  const response = await http.get<WechatOfficialCredentialGuide>("/wechat-official/credentials/guide");
  return response.data;
}

export async function importWechatOfficialCredential(
  payload: WechatOfficialCredentialImportPayload
): Promise<WechatOfficialCredential> {
  const response = await http.post<WechatOfficialCredential>("/wechat-official/credentials/import", payload);
  return response.data;
}

export async function validateWechatOfficialCredential(
  payload: WechatOfficialCredentialValidatePayload
): Promise<WechatOfficialCredentialValidation> {
  const response = await http.post<WechatOfficialCredentialValidation>("/wechat-official/credentials/validate", payload);
  return response.data;
}

export async function fetchWechatOfficialCredentials(): Promise<WechatOfficialListResponse<WechatOfficialCredential>> {
  const response = await http.get<WechatOfficialListResponse<WechatOfficialCredential>>("/wechat-official/credentials");
  return response.data;
}

export async function fetchWechatOfficialProxies(): Promise<WechatOfficialListResponse<WechatOfficialProxy>> {
  const response = await http.get<WechatOfficialListResponse<WechatOfficialProxy>>("/wechat-official/proxies");
  return response.data;
}

export async function fetchWechatOfficialRedfoxConfig(): Promise<WechatOfficialRedfoxConfigResponse> {
  const response = await http.get<WechatOfficialRedfoxConfigResponse>("/wechat-official/redfox/config");
  return response.data;
}

export async function saveWechatOfficialRedfoxConfig(
  payload: WechatOfficialRedfoxConfigPayload
): Promise<WechatOfficialRedfoxConfigResponse> {
  const response = await http.post<WechatOfficialRedfoxConfigResponse>("/wechat-official/redfox/config", payload);
  return response.data;
}

export async function validateWechatOfficialRedfoxConfig(): Promise<{ ok: boolean; config: WechatOfficialRedfoxConfigResponse["config"]; message: string }> {
  const response = await http.post<{ ok: boolean; config: WechatOfficialRedfoxConfigResponse["config"]; message: string }>("/wechat-official/redfox/config/validate");
  return response.data;
}

export async function collectWechatOfficialRedfoxArticles(
  payload: WechatOfficialRedfoxKeywordCollectPayload
): Promise<WechatOfficialRedfoxCollectResponse> {
  const response = await http.post<WechatOfficialRedfoxCollectResponse>("/wechat-official/redfox/collect/articles", payload);
  return response.data;
}

export async function collectWechatOfficialRedfoxAccount(
  payload: WechatOfficialRedfoxAccountCollectPayload
): Promise<WechatOfficialRedfoxCollectResponse> {
  const response = await http.post<WechatOfficialRedfoxCollectResponse>("/wechat-official/redfox/collect/account", payload);
  return response.data;
}

export async function importWechatOfficialRedfoxUrl(
  payload: WechatOfficialRedfoxUrlImportPayload
): Promise<WechatOfficialRedfoxCollectResponse> {
  const response = await http.post<WechatOfficialRedfoxCollectResponse>("/wechat-official/redfox/import-url", payload);
  return response.data;
}

export async function testWechatOfficialProxy(
  proxyId: number,
  payload: WechatOfficialProxyTestPayload
): Promise<WechatOfficialProxy> {
  const response = await http.post<WechatOfficialProxy>(`/wechat-official/proxies/${proxyId}/test`, payload);
  return response.data;
}

export async function searchWechatOfficialAccounts(
  payload: WechatOfficialSearchAccountsPayload
): Promise<WechatOfficialListResponse<WechatOfficialCrawlAccount>> {
  const response = await http.post<WechatOfficialListResponse<WechatOfficialCrawlAccount>>(
    "/wechat-official/crawl/accounts/search",
    payload
  );
  return response.data;
}

export async function syncWechatOfficialArticles(
  payload: WechatOfficialArticleSyncPayload
): Promise<WechatOfficialArticleSyncResponse> {
  const response = await http.post<WechatOfficialArticleSyncResponse>("/wechat-official/crawl/articles/sync", payload);
  return response.data;
}

export async function captureWechatOfficialArticleSnapshot(
  articleId: number,
  payload: WechatOfficialArticleSnapshotPayload
): Promise<WechatOfficialArticleSnapshot> {
  const response = await http.post<WechatOfficialArticleSnapshot>(
    `/wechat-official/crawl/articles/${articleId}/snapshot`,
    payload
  );
  return response.data;
}

export async function captureWechatOfficialArticleMetrics(
  articleId: number,
  payload: WechatOfficialArticleMetricsPayload
): Promise<WechatOfficialArticleMetric> {
  const response = await http.post<WechatOfficialArticleMetric>(
    `/wechat-official/crawl/articles/${articleId}/metrics`,
    payload
  );
  return response.data;
}

export async function captureWechatOfficialArticleComments(
  articleId: number,
  payload: WechatOfficialArticleCommentsPayload
): Promise<WechatOfficialListResponse<WechatOfficialArticleComment>> {
  const response = await http.post<WechatOfficialListResponse<WechatOfficialArticleComment>>(
    `/wechat-official/crawl/articles/${articleId}/comments`,
    payload
  );
  return response.data;
}

export async function fetchWechatOfficialContentLibrary(params?: {
  viral_only?: boolean;
  min_read_count?: number;
  low_follower_evidence?: boolean | string;
  recommendation_status?: string;
  keyword?: string;
}): Promise<WechatOfficialListResponse<WechatOfficialContentLibraryItem>> {
  const response = await http.get<WechatOfficialListResponse<WechatOfficialContentLibraryItem>>(
    "/wechat-official/content-library",
    { params }
  );
  return response.data;
}

export async function updateWechatOfficialRecommendation(
  articleId: number,
  payload: WechatOfficialRecommendationUpdatePayload
): Promise<WechatOfficialContentLibraryItem> {
  const response = await http.patch<WechatOfficialContentLibraryItem>(
    `/wechat-official/content-library/${articleId}/recommendation`,
    payload
  );
  return response.data;
}

export async function createWechatOfficialDraft(
  articleId: number,
  payload: WechatOfficialCreateDraftPayload
): Promise<WechatOfficialDraft> {
  const response = await http.post<WechatOfficialDraft>(
    `/wechat-official/content-library/${articleId}/create-draft`,
    payload
  );
  return response.data;
}

export async function dryRunWechatOfficialDraft(
  draftId: number,
  payload: WechatOfficialDraftDryRunPayload = {}
): Promise<WechatOfficialDraftDryRun> {
  const response = await http.post<WechatOfficialDraftDryRun>(`/wechat-official/drafts/${draftId}/dry-run`, payload);
  return response.data;
}

export async function fetchXhsTopContent(): Promise<{ items: AnalyticsTopContent[] }> {
  const response = await http.get<{ items: AnalyticsTopContent[] }>("/xhs/analytics/top-content");
  return response.data;
}

export async function fetchXhsHotTopics(): Promise<{ items: AnalyticsHotTopic[] }> {
  const response = await http.get<{ items: AnalyticsHotTopic[] }>("/xhs/analytics/hot-topics");
  return response.data;
}

export async function fetchXhsCommentInsights(): Promise<AnalyticsCommentInsight> {
  const response = await http.get<AnalyticsCommentInsight>("/xhs/analytics/comment-insights");
  return response.data;
}

export async function fetchXhsBenchmarks(): Promise<BenchmarkOverview> {
  const response = await http.get<BenchmarkOverview>("/xhs/analytics/benchmarks");
  return response.data;
}

export async function createBenchmarkDrafts(targetId: number, limit = 5): Promise<BenchmarkCreateDraftsResponse> {
  const response = await http.post<BenchmarkCreateDraftsResponse>(
    `/xhs/analytics/benchmarks/${targetId}/create-drafts`,
    null,
    { params: { limit } }
  );
  return response.data;
}

export async function createXhsAnalyticsReport(
  payload: AnalyticsReportPayload = { format: "json" }
): Promise<AnalyticsReportResponse> {
  const response = await http.post<AnalyticsReportResponse>("/xhs/analytics/reports", payload);
  return response.data;
}

export async function fetchAccounts(platform?: string): Promise<PlatformAccount[]> {
  const response = await http.get<Paginated<PlatformAccount>>("/accounts", { params: platform ? { platform } : undefined });
  return response.data.items;
}

export type SavedNoteFilters = {
  platform?: string;
  q?: string;
  tag_id?: number;
  has_assets?: boolean;
  has_comments?: boolean;
  page_size?: number;
};

export async function fetchSavedNoteIds(platform = "xhs"): Promise<string[]> {
  const response = await http.get<{ items: string[] }>("/notes/ids", { params: { platform } });
  return response.data.items;
}

export async function fetchSavedNotes(platformOrFilters: string | SavedNoteFilters = "xhs"): Promise<Paginated<SavedNote>> {
  const params =
    typeof platformOrFilters === "string"
      ? { platform: platformOrFilters }
      : {
          platform: platformOrFilters.platform ?? "xhs",
          q: platformOrFilters.q || undefined,
          tag_id: platformOrFilters.tag_id,
          has_assets: platformOrFilters.has_assets,
          has_comments: platformOrFilters.has_comments,
          page_size: platformOrFilters.page_size,
        };
  const response = await http.get<Paginated<SavedNote>>("/notes", { params });
  return response.data;
}

export async function fetchSavedNote(noteId: number, silent = false): Promise<SavedNote> {
  const response = await http.get<SavedNote>(`/notes/${noteId}`, { _silent: silent } as never);
  return response.data;
}

export async function fetchSavedNoteAssets(noteId: number): Promise<Paginated<NoteAsset>> {
  const response = await http.get<Paginated<NoteAsset>>(`/notes/${noteId}/assets`);
  return response.data;
}

export async function addNoteAsset(noteId: number, payload: { asset_type: string; url?: string; local_path?: string }): Promise<NoteAsset> {
  const response = await http.post<NoteAsset>(`/notes/${noteId}/assets`, payload);
  return response.data;
}

export async function deleteNoteAsset(noteId: number, assetId: number): Promise<void> {
  await http.delete(`/notes/${noteId}/assets/${assetId}`);
}

export async function reorderNoteAssets(noteId: number, assetIds: number[]): Promise<void> {
  await http.put(`/notes/${noteId}/assets/reorder`, { asset_ids: assetIds });
}

export async function fetchSavedNoteComments(noteId: number, page = 1): Promise<Paginated<NoteComment>> {
  const response = await http.get<Paginated<NoteComment>>(`/notes/${noteId}/comments`, {
    params: { page, page_size: 50 }
  });
  return response.data;
}

export async function deleteSavedNote(noteId: number): Promise<{ id: number; status: string }> {
  const response = await http.delete<{ id: number; status: string }>(`/notes/${noteId}`);
  return response.data;
}

export async function fetchTags(): Promise<Paginated<Tag>> {
  const response = await http.get<Paginated<Tag>>("/tags");
  return response.data;
}

export async function createTag(payload: TagPayload): Promise<Tag> {
  const response = await http.post<Tag>("/tags", payload);
  return response.data;
}

export async function batchTagNotes(payload: BatchTagNotesPayload): Promise<BatchTagNotesResponse> {
  const response = await http.post<BatchTagNotesResponse>("/notes/batch-tag", payload);
  return response.data;
}

export async function batchCreateDraftsFromNotes(
  payload: BatchCreateDraftsPayload
): Promise<BatchCreateDraftsResponse> {
  const response = await http.post<BatchCreateDraftsResponse>("/notes/batch-create-drafts", payload);
  return response.data;
}

export async function exportSavedNotes(payload: NotesExportPayload): Promise<NotesExportResponse> {
  const response = await http.post<NotesExportResponse>("/notes/export", payload);
  return response.data;
}

export async function downloadExportFile(downloadUrl: string, fileName: string): Promise<void> {
  const endpoint = downloadUrl.startsWith("/api") ? downloadUrl.slice(4) : downloadUrl;
  const response = await http.get<Blob>(endpoint, { responseType: "blob" });
  const objectUrl = window.URL.createObjectURL(response.data);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(objectUrl);
}

export async function downloadMediaFile(downloadUrl: string, fileName: string): Promise<void> {
  return downloadExportFile(downloadUrl, fileName);
}

export type UploadedFile = {
  file_name: string;
  file_path: string;
  download_url: string;
  asset_type: "image" | "video";
  size: number;
};

export async function uploadAssetFile(file: File): Promise<UploadedFile> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await http.post<UploadedFile>("/files/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 120000,
  });
  return response.data;
}

export async function createMediaObjectUrl(downloadUrl: string): Promise<string> {
  const endpoint = downloadUrl.startsWith("/api") ? downloadUrl.slice(4) : downloadUrl;
  const response = await http.get<Blob>(endpoint, { responseType: "blob" });
  return window.URL.createObjectURL(response.data);
}

export async function searchXhsNotes(payload: XhsSearchOptions): Promise<XhsNoteSearchResponse> {
  const response = await http.post<XhsNoteSearchResponse>("/xhs/pc/search/notes", payload);
  return response.data;
}

async function streamXhsCrawl<TSummary>(
  endpoint: string,
  payload: Record<string, unknown>,
  initialResult: TSummary,
  onItem: (index: number, item: XhsDataCrawlItem) => void,
  onProgress?: (message: string) => void,
  onError?: (message: string) => void,
  mapDone?: (event: Record<string, unknown>) => TSummary,
): Promise<TSummary> {
  const token = getAccessToken();
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail || `HTTP ${response.status}`);
  }
  const reader = response.body?.getReader();
  if (!reader) throw new Error("No response stream");
  const decoder = new TextDecoder();
  let buffer = "";
  let result = initialResult;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      try {
        const event = JSON.parse(line.slice(6));
        if (event.type === "item") onItem(event.index, event.item);
        else if (event.type === "progress") onProgress?.(event.message);
        else if (event.type === "error") onError?.(event.message);
        else if (event.type === "done" && mapDone) result = mapDone(event);
      } catch { /* skip malformed events */ }
    }
  }
  return result;
}

export async function crawlXhsDataStream(
  payload: XhsDataCrawlPayload,
  onItem: (index: number, item: XhsDataCrawlItem) => void,
  onProgress?: (message: string) => void,
  onError?: (message: string) => void,
): Promise<{ total: number; success_count: number; failed_count: number; comment_rate_limited_count?: number; comment_skipped_count?: number }> {
  return streamXhsCrawl(
    "/api/xhs/crawl/data",
    payload as Record<string, unknown>,
    { total: 0, success_count: 0, failed_count: 0, comment_rate_limited_count: 0, comment_skipped_count: 0 },
    onItem,
    onProgress,
    onError,
    (event) => ({
      total: Number(event.total || 0),
      success_count: Number(event.success_count || 0),
      failed_count: Number(event.failed_count || 0),
      comment_rate_limited_count: Number(event.comment_rate_limited_count || 0),
      comment_skipped_count: Number(event.comment_skipped_count || 0),
    }),
  );
}

export async function crawlXhsKeywordGroupStream(
  payload: XhsKeywordGroupCrawlPayload,
  onItem: (index: number, item: XhsDataCrawlItem) => void,
  onProgress?: (message: string) => void,
  onError?: (message: string) => void,
): Promise<XhsKeywordGroupCrawlSummary> {
  return streamXhsCrawl<XhsKeywordGroupCrawlSummary>(
    "/api/xhs/crawl/keyword-group",
    payload as Record<string, unknown>,
    { total: 0, success_count: 0, failed_count: 0, saved_count: 0, skipped_count: 0, rate_limited_count: 0, missing_detail_count: 0, summary_message: "" },
    onItem,
    onProgress,
    onError,
    (event) => ({
      total: Number(event.total || 0),
      success_count: Number(event.success_count || 0),
      failed_count: Number(event.failed_count || 0),
      saved_count: Number(event.saved_count || 0),
      skipped_count: Number(event.skipped_count || 0),
      rate_limited_count: Number(event.rate_limited_count || 0),
      missing_detail_count: Number(event.missing_detail_count || 0),
      summary_message: String(event.summary_message || ""),
    }),
  );
}

export async function fetchXhsNoteDetail(payload: { account_id: number; url: string }): Promise<XhsSearchNote> {
  const response = await http.post<XhsSearchNote>("/xhs/pc/notes/detail", payload);
  return response.data;
}

export async function fetchXhsNoteComments(payload: {
  account_id: number;
  note_url: string;
}): Promise<Paginated<NoteComment>> {
  const response = await http.post<{ total: number; items: NoteComment[] }>("/xhs/pc/notes/comments", payload);
  return {
    total: response.data.total,
    page: 1,
    page_size: response.data.items.length,
    items: response.data.items
  };
}

export async function saveXhsNotesToLibrary(payload: {
  account_id: number;
  notes: XhsSearchNote[];
}): Promise<SaveNotesResponse> {
  const response = await http.post<SaveNotesResponse>("/notes/batch-save", payload);
  return response.data;
}

export async function createDraftFromNote(payload: CreateDraftPayload): Promise<Draft> {
  const response = await http.post<Draft>("/drafts", payload);
  return response.data;
}

export async function fetchDrafts(platform = "xhs"): Promise<Paginated<Draft>> {
  const response = await http.get<Paginated<Draft>>("/drafts", { params: { platform } });
  return response.data;
}

export async function duplicateDraft(draftId: number): Promise<Draft> {
  const response = await http.post<Draft>(`/drafts/${draftId}/duplicate`);
  return response.data;
}

export async function updateDraft(draftId: number, payload: { title?: string; body?: string; tags?: { id?: string; name: string }[] }): Promise<Draft> {
  const response = await http.patch<Draft>(`/drafts/${draftId}`, payload);
  return response.data;
}

export async function deleteDraft(draftId: number): Promise<{ id: number; status: string }> {
  const response = await http.delete<{ id: number; status: string }>(`/drafts/${draftId}`);
  return response.data;
}

export type DraftAsset = {
  id: number;
  draft_id: number;
  asset_type: "image" | "video" | string;
  url: string;
  local_path: string;
  sort_order: number;
};

export async function fetchDraftAssets(draftId: number): Promise<{ items: DraftAsset[] }> {
  const response = await http.get<{ items: DraftAsset[] }>(`/drafts/${draftId}/assets`);
  return response.data;
}

export async function addDraftAsset(draftId: number, payload: { asset_type: string; url?: string; local_path?: string }): Promise<DraftAsset> {
  const response = await http.post<DraftAsset>(`/drafts/${draftId}/assets`, payload);
  return response.data;
}

export async function deleteDraftAsset(draftId: number, assetId: number): Promise<void> {
  await http.delete(`/drafts/${draftId}/assets/${assetId}`);
}

export async function updateDraftAsset(draftId: number, assetId: number, payload: { url?: string; local_path?: string }): Promise<DraftAsset> {
  const response = await http.patch<DraftAsset>(`/drafts/${draftId}/assets/${assetId}`, payload);
  return response.data;
}

export async function reorderDraftAssets(draftId: number, assetIds: number[]): Promise<void> {
  await http.put(`/drafts/${draftId}/assets/reorder`, { asset_ids: assetIds });
}

export async function sendDraftToPublish(draftId: number, payload: SendDraftToPublishPayload): Promise<PublishJob> {
  const response = await http.post<PublishJob>(`/drafts/${draftId}/send-to-publish`, payload);
  return response.data;
}

export async function rewriteDraftWithAi(payload: RewriteDraftPayload): Promise<Draft> {
  const response = await http.post<Draft>("/ai/rewrite-note", payload);
  return response.data;
}

export async function generateNoteWithAi(payload: GenerateNotePayload): Promise<Draft> {
  const response = await http.post<Draft>("/ai/generate-note", payload);
  return response.data;
}

export async function generateTitleOptions(payload: GenerateTitlePayload): Promise<{ items: string[] }> {
  const response = await http.post<{ items: string[] }>("/ai/generate-title", payload);
  return response.data;
}

export async function generateTagOptions(payload: GenerateTagsPayload): Promise<{ items: string[] }> {
  const response = await http.post<{ items: string[] }>("/ai/generate-tags", payload);
  return response.data;
}

export async function polishTextWithAi(payload: PolishTextPayload): Promise<{ text: string }> {
  const response = await http.post<{ text: string }>("/ai/polish-text", payload);
  return response.data;
}

export async function fetchGeneratedImageAssets(): Promise<Paginated<GeneratedImageAsset>> {
  const response = await http.get<Paginated<GeneratedImageAsset>>("/ai/images/assets");
  return response.data;
}

export async function deleteGeneratedImageAsset(assetId: number): Promise<void> {
  await http.delete(`/ai/images/assets/${assetId}`);
}

export async function deleteUserImage(fileName: string): Promise<void> {
  await http.delete(`/files/images/${fileName}`);
}

export async function generateCoverWithAi(payload: GenerateCoverPayload): Promise<GeneratedImageAsset> {
  const response = await http.post<GeneratedImageAsset>("/ai/images/generate-cover", payload);
  return response.data;
}

export async function generateImageWithAi(payload: GenerateImagePayload): Promise<GenerateImageResult> {
  const response = await http.post<GenerateImageResult>("/ai/images/generate", payload, { timeout: 180000 });
  return response.data;
}

export async function fetchUserImages(): Promise<{ items: UserImageFile[] }> {
  const response = await http.get<{ items: UserImageFile[] }>("/files/images");
  return response.data;
}

export async function describeImageWithAi(payload: DescribeImagePayload): Promise<{ text: string }> {
  const response = await http.post<{ text: string }>("/ai/images/describe", payload);
  return response.data;
}

export async function composeImageUtility(payload: ComposeImagePayload): Promise<ImageUtilityFile> {
  const response = await http.post<ImageUtilityFile>("/files/images/compose", payload);
  return response.data;
}

export async function resizeImageUtility(payload: ResizeImagePayload): Promise<ImageUtilityFile> {
  const response = await http.post<ImageUtilityFile>("/files/images/resize", payload);
  return response.data;
}

export async function fetchModelConfigs(modelType?: ModelType): Promise<Paginated<ModelConfig>> {
  const response = await http.get<Paginated<ModelConfig>>("/model-configs", {
    params: modelType ? { model_type: modelType } : undefined
  });
  return response.data;
}

export async function createModelConfig(payload: ModelConfigPayload): Promise<ModelConfig> {
  const response = await http.post<ModelConfig>("/model-configs", payload);
  return response.data;
}

export async function setDefaultModelConfig(configId: number): Promise<ModelConfig> {
  const response = await http.post<ModelConfig>(`/model-configs/${configId}/set-default`);
  return response.data;
}

export async function updateModelConfig(configId: number, payload: Partial<ModelConfigPayload>): Promise<ModelConfig> {
  const response = await http.patch<ModelConfig>(`/model-configs/${configId}`, payload);
  return response.data;
}

export async function testModelConfig(configId: number): Promise<{ id: number; status: string; message: string }> {
  const response = await http.post<{ id: number; status: string; message: string }>(`/model-configs/${configId}/test`);
  return response.data;
}

export async function deleteModelConfig(configId: number): Promise<{ id: number; status: string }> {
  const response = await http.delete<{ id: number; status: string }>(`/model-configs/${configId}`);
  return response.data;
}

export async function fetchTasks(platform?: string): Promise<Paginated<TaskRecord>> {
  const response = await http.get<Paginated<TaskRecord>>("/tasks", {
    params: platform ? { platform } : undefined
  });
  return response.data;
}

export async function fetchSchedulerStatus(): Promise<SchedulerStatus> {
  const response = await http.get<SchedulerStatus>("/tasks/scheduler/status");
  return response.data;
}

export async function cancelTask(taskId: number): Promise<TaskRecord> {
  const response = await http.post<TaskRecord>(`/tasks/${taskId}/cancel`);
  return response.data;
}

export async function retryTask(taskId: number): Promise<TaskRecord> {
  const response = await http.post<TaskRecord>(`/tasks/${taskId}/retry`);
  return response.data;
}

export async function runDueTasks(platform = "xhs"): Promise<RunDueTasksResponse> {
  const response = await http.post<RunDueTasksResponse>("/tasks/run-due", null, { params: { platform } });
  return response.data;
}

export async function fetchMonitoringTargets(): Promise<Paginated<MonitoringTarget>> {
  const response = await http.get<Paginated<MonitoringTarget>>("/xhs/monitoring/targets");
  return response.data;
}

export async function createMonitoringTarget(payload: MonitoringTargetPayload): Promise<MonitoringTarget> {
  const response = await http.post<MonitoringTarget>("/xhs/monitoring/targets", payload);
  return response.data;
}

export async function updateMonitoringTarget(
  targetId: number,
  payload: Partial<MonitoringTargetPayload>
): Promise<MonitoringTarget> {
  const response = await http.patch<MonitoringTarget>(`/xhs/monitoring/targets/${targetId}`, payload);
  return response.data;
}

export async function deleteMonitoringTarget(targetId: number): Promise<{ id: number; status: string }> {
  const response = await http.delete<{ id: number; status: string }>(`/xhs/monitoring/targets/${targetId}`);
  return response.data;
}

export async function refreshMonitoringTarget(targetId: number): Promise<MonitoringRefreshResponse> {
  const response = await http.post<MonitoringRefreshResponse>(`/xhs/monitoring/targets/${targetId}/refresh`);
  return response.data;
}

export async function fetchMonitoringSnapshots(targetId: number): Promise<{ target_id: number; items: MonitoringSnapshot[] }> {
  const response = await http.get<{ target_id: number; items: MonitoringSnapshot[] }>(
    `/xhs/monitoring/targets/${targetId}/snapshots`
  );
  return response.data;
}

export async function fetchMonitoringTargetNotes(targetId: number): Promise<{ target_id: number; items: MonitoringNote[] }> {
  const response = await http.get<{ target_id: number; items: MonitoringNote[] }>(
    `/xhs/monitoring/targets/${targetId}/notes`
  );
  return response.data;
}

export async function fetchKeywordGroups(platform = "xhs"): Promise<Paginated<KeywordGroup>> {
  const response = await http.get<Paginated<KeywordGroup>>("/keyword-groups", { params: { platform } });
  return response.data;
}

export async function createKeywordGroup(payload: KeywordGroupPayload): Promise<KeywordGroup> {
  const response = await http.post<KeywordGroup>("/keyword-groups", payload);
  return response.data;
}

export async function fetchKeywordGroup(groupId: number): Promise<KeywordGroupDetail> {
  const response = await http.get<KeywordGroupDetail>(`/keyword-groups/${groupId}`);
  return response.data;
}

export async function updateKeywordGroup(
  groupId: number,
  payload: Partial<KeywordGroupPayload>
): Promise<KeywordGroup> {
  const response = await http.patch<KeywordGroup>(`/keyword-groups/${groupId}`, payload);
  return response.data;
}

export async function deleteKeywordGroup(groupId: number): Promise<{ id: number; status: string }> {
  const response = await http.delete<{ id: number; status: string }>(`/keyword-groups/${groupId}`);
  return response.data;
}

export async function createHuitunKeywordDiscoveryRun(
  payload: HuitunDiscoveryRunPayload
): Promise<KeywordDiscoveryRun> {
  const response = await http.post<KeywordDiscoveryRun>("/keyword-groups/huitun/discovery-runs", payload);
  return response.data;
}

export async function fetchHuitunKeywordDiscoveryRuns(page = 1, page_size = 10): Promise<Paginated<KeywordDiscoveryRun>> {
  const response = await http.get<Paginated<KeywordDiscoveryRun>>("/keyword-groups/huitun/discovery-runs", {
    params: { page, page_size },
  });
  return response.data;
}

export async function fetchHuitunKeywordDiscoveryRun(runId: number): Promise<KeywordDiscoveryRun> {
  const response = await http.get<KeywordDiscoveryRun>(`/keyword-groups/huitun/discovery-runs/${runId}`);
  return response.data;
}

export async function importKeywordCandidatesToGroup(
  groupId: number,
  payload: KeywordCandidateImportPayload
): Promise<KeywordCandidateImportResponse> {
  const response = await http.post<KeywordCandidateImportResponse>(
    `/keyword-groups/${groupId}/import-keyword-candidates`,
    payload
  );
  return response.data;
}

export async function importKeywordCandidates(
  payload: KeywordCandidateImportPayload
): Promise<KeywordCandidateImportResponse> {
  const response = await http.post<KeywordCandidateImportResponse>("/keyword-groups/import-keyword-candidates", payload);
  return response.data;
}

export async function fetchXhsCrawlDiagnostics(params?: {
  task_id?: number;
  stage?: string;
  kind?: string;
  page?: number;
  page_size?: number;
}): Promise<Paginated<CrawlDiagnostic>> {
  const response = await http.get<Paginated<CrawlDiagnostic>>("/xhs/crawl/diagnostics", { params });
  return response.data;
}

export async function fetchPublishJobs(platform = "xhs"): Promise<Paginated<PublishJob>> {
  const response = await http.get<Paginated<PublishJob>>("/publish/jobs", { params: { platform } });
  return response.data;
}

export async function fetchPublishJob(jobId: number): Promise<PublishJob> {
  const response = await http.get<PublishJob>(`/publish/jobs/${jobId}`);
  return response.data;
}

export async function updatePublishJob(jobId: number, payload: PublishJobUpdatePayload): Promise<PublishJob> {
  const response = await http.patch<PublishJob>(`/publish/jobs/${jobId}`, payload);
  return response.data;
}

export async function publishJobToCreator(jobId: number): Promise<PublishJob> {
  const response = await http.post<PublishJob>(`/publish/jobs/${jobId}/publish`);
  return response.data;
}

export async function retryPublishJob(jobId: number): Promise<PublishJob> {
  const response = await http.post<PublishJob>(`/publish/jobs/${jobId}/retry`);
  return response.data;
}

export async function cancelPublishJob(jobId: number): Promise<PublishJob> {
  const response = await http.post<PublishJob>(`/publish/jobs/${jobId}/cancel`);
  return response.data;
}

export async function deletePublishJob(jobId: number): Promise<void> {
  await http.delete(`/publish/jobs/${jobId}`);
}

export async function fetchPublishAssets(jobId: number): Promise<Paginated<PublishAsset>> {
  const response = await http.get<Paginated<PublishAsset>>(`/publish/jobs/${jobId}/assets`);
  return response.data;
}

export async function addPublishAsset(jobId: number, payload: PublishAssetPayload): Promise<PublishAsset> {
  const response = await http.post<PublishAsset>(`/publish/jobs/${jobId}/assets`, payload);
  return response.data;
}

export async function deletePublishAsset(assetId: number): Promise<{ id: number; status: string }> {
  const response = await http.delete<{ id: number; status: string }>(`/publish/assets/${assetId}`);
  return response.data;
}

export async function uploadPublishAsset(assetId: number): Promise<PublishAsset> {
  const response = await http.post<PublishAsset>(`/publish/assets/${assetId}/upload`);
  return response.data;
}

export async function importXhsCookieAccount(payload: {
  sub_type: "pc" | "creator";
  cookie_string: string;
  sync_creator?: boolean;
}): Promise<PlatformAccount> {
  const response = await http.post<PlatformAccount>("/accounts/import-cookie", {
    platform: "xhs",
    ...payload
  });
  return response.data;
}

export async function importHuitunCookieAccount(payload: {
  cookie_string: string;
}): Promise<PlatformAccount> {
  const response = await http.post<PlatformAccount>("/accounts/import-cookie", {
    platform: "huitun",
    sub_type: "main",
    cookie_string: payload.cookie_string,
  });
  return response.data;
}

export async function checkAccount(accountId: number): Promise<PlatformAccount> {
  const response = await http.post<PlatformAccount>(`/accounts/${accountId}/check`);
  return response.data;
}

export async function deleteAccount(accountId: number): Promise<{ id: number; status: string }> {
  const response = await http.delete<{ id: number; status: string }>(`/accounts/${accountId}`);
  return response.data;
}

export async function createXhsPcQrLoginSession(payload?: {
  sync_creator?: boolean;
}): Promise<XhsQrLoginSession> {
  const response = await http.post<XhsQrLoginSession>("/xhs/login-sessions/pc/qrcode", payload ?? {});
  return response.data;
}

export async function createXhsCreatorQrLoginSession(): Promise<XhsQrLoginSession> {
  const response = await http.post<XhsQrLoginSession>("/xhs/login-sessions/creator/qrcode");
  return response.data;
}

export async function createHuitunQrLoginSession(): Promise<XhsQrLoginSession> {
  const response = await http.post<XhsQrLoginSession>("/huitun/login-sessions/qrcode");
  return response.data;
}

export async function pollHuitunLoginSession(sessionId: number): Promise<XhsQrLoginSession> {
  const response = await http.get<XhsQrLoginSession>(`/huitun/login-sessions/${sessionId}`);
  return response.data;
}

export async function pollXhsLoginSession(sessionId: number): Promise<XhsQrLoginSession> {
  const response = await http.get<XhsQrLoginSession>(`/xhs/login-sessions/${sessionId}`);
  return response.data;
}

export async function sendXhsPhoneCode(payload: {
  sub_type: "pc" | "creator";
  phone: string;
  sync_creator?: boolean;
}): Promise<{ session_id: number; status: string; message: string }> {
  const response = await http.post<{ session_id: number; status: string; message: string }>(
    `/xhs/login-sessions/${payload.sub_type}/phone/send-code`,
    { phone: payload.phone, sync_creator: payload.sync_creator }
  );
  return response.data;
}

export async function confirmXhsPhoneLogin(payload: {
  sub_type: "pc" | "creator";
  session_id: number;
  phone: string;
  code: string;
  sync_creator?: boolean;
}): Promise<XhsQrLoginSession> {
  const response = await http.post<XhsQrLoginSession>(`/xhs/login-sessions/${payload.sub_type}/phone/confirm`, {
    session_id: payload.session_id,
    phone: payload.phone,
    code: payload.code,
    sync_creator: payload.sync_creator
  });
  return response.data;
}

export async function fetchNotifications(params?: { unread?: boolean; page?: number; page_size?: number }): Promise<Paginated<AppNotification>> {
  const response = await http.get<Paginated<AppNotification>>("/notifications", { params });
  return response.data;
}

export async function markNotificationRead(id: number): Promise<AppNotification> {
  const response = await http.post<AppNotification>(`/notifications/${id}/read`);
  return response.data;
}

export async function markAllNotificationsRead(): Promise<{ marked: number }> {
  const response = await http.post<{ marked: number }>("/notifications/read-all");
  return response.data;
}

// Auto Tasks (Auto Operations)

export async function fetchAutoTasks(): Promise<Paginated<AutoTask>> {
  const response = await http.get<Paginated<AutoTask>>("/auto-tasks");
  return response.data;
}

export async function createAutoTask(payload: AutoTaskCreatePayload): Promise<AutoTask> {
  const response = await http.post<AutoTask>("/auto-tasks", payload);
  return response.data;
}

export async function updateAutoTask(taskId: number, payload: AutoTaskUpdatePayload): Promise<AutoTask> {
  const response = await http.patch<AutoTask>(`/auto-tasks/${taskId}`, payload);
  return response.data;
}

export async function deleteAutoTask(taskId: number): Promise<{ id: number; status: string }> {
  const response = await http.delete<{ id: number; status: string }>(`/auto-tasks/${taskId}`);
  return response.data;
}

export async function runAutoTask(taskId: number): Promise<AutoTaskRunResult> {
  const response = await http.post<AutoTaskRunResult>(`/auto-tasks/${taskId}/run`);
  return response.data;
}

import { http } from "./client";
import type {
  NotesExportResponse,
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
  WechatOfficialAnalyzeHotspotsPayload,
  WechatOfficialAnalyzeHotspotsResponse,
  WechatOfficialArticlesExportPayload,
  WechatOfficialContentAutoRefreshPayload,
  WechatOfficialContentAutoRefreshResponse,
  WechatOfficialContentDetail,
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
  WechatOfficialReadiness,
  WechatOfficialRecommendationUpdatePayload,
  WechatOfficialRedfoxAccountCollectPayload,
  WechatOfficialRedfoxCollectJobDetail,
  WechatOfficialRedfoxCollectJobListResponse,
  WechatOfficialRedfoxCollectResponse,
  WechatOfficialRedfoxConfigPayload,
  WechatOfficialRedfoxConfigResponse,
  WechatOfficialRedfoxKeywordCollectPayload,
  WechatOfficialRedfoxUrlImportPayload,
  WechatOfficialSearchAccountsPayload
} from "../../types";

export async function fetchWechatOfficialOverview(): Promise<WechatOfficialOverview> {
  const response = await http.get<WechatOfficialOverview>("/wechat-official/overview");
  return response.data;
}

export async function fetchWechatOfficialReadiness(): Promise<WechatOfficialReadiness> {
  const response = await http.get<WechatOfficialReadiness>("/wechat-official/readiness");
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
  const response = await http.post<WechatOfficialRedfoxCollectResponse>("/wechat-official/redfox/collect/articles", payload, { _silent: true } as never);
  return response.data;
}

export async function collectWechatOfficialRedfoxAccount(
  payload: WechatOfficialRedfoxAccountCollectPayload
): Promise<WechatOfficialRedfoxCollectResponse> {
  const response = await http.post<WechatOfficialRedfoxCollectResponse>("/wechat-official/redfox/collect/account", payload, { _silent: true } as never);
  return response.data;
}

export async function importWechatOfficialArticleUrl(
  payload: WechatOfficialRedfoxUrlImportPayload
): Promise<WechatOfficialRedfoxCollectResponse> {
  const response = await http.post<WechatOfficialRedfoxCollectResponse>("/wechat-official/articles/import-url", payload, { _silent: true } as never);
  return response.data;
}

export async function importWechatOfficialRedfoxUrl(
  payload: WechatOfficialRedfoxUrlImportPayload
): Promise<WechatOfficialRedfoxCollectResponse> {
  const response = await http.post<WechatOfficialRedfoxCollectResponse>("/wechat-official/redfox/import-url", payload, { _silent: true } as never);
  return response.data;
}

export async function fetchWechatOfficialRedfoxCollectJobs(params?: {
  source_label?: string;
  page?: number;
  page_size?: number;
}): Promise<WechatOfficialRedfoxCollectJobListResponse> {
  const response = await http.get<WechatOfficialRedfoxCollectJobListResponse>(
    "/wechat-official/redfox/collect/jobs",
    { params }
  );
  return response.data;
}

export async function fetchWechatOfficialRedfoxCollectJob(jobId: number): Promise<WechatOfficialRedfoxCollectJobDetail> {
  const response = await http.get<WechatOfficialRedfoxCollectJobDetail>(`/wechat-official/redfox/collect/jobs/${jobId}`);
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
  pool_status?: string;
  category?: string;
  tag?: string;
  is_favorite?: boolean;
  read_status?: string;
  detail_complete?: boolean;
  keyword?: string;
  job_id?: number;
  page?: number;
  page_size?: number;
}): Promise<WechatOfficialListResponse<WechatOfficialContentLibraryItem>> {
  const response = await http.get<WechatOfficialListResponse<WechatOfficialContentLibraryItem>>(
    "/wechat-official/content-library",
    { params }
  );
  return response.data;
}

export async function fetchWechatOfficialContentDetail(articleId: number): Promise<WechatOfficialContentDetail> {
  const response = await http.get<WechatOfficialContentDetail>(`/wechat-official/content-library/${articleId}`);
  return response.data;
}

export async function deleteWechatOfficialContentLibraryItem(articleId: number): Promise<{ id: number; status: string }> {
  const response = await http.delete<{ id: number; status: string }>(`/wechat-official/content-library/${articleId}`);
  return response.data;
}

export async function refreshWechatOfficialContentDetail(articleId: number): Promise<WechatOfficialContentDetail> {
  const response = await http.post<WechatOfficialContentDetail>(`/wechat-official/content-library/${articleId}/refresh-detail`);
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

export async function exportWechatOfficialArticles(payload: WechatOfficialArticlesExportPayload): Promise<NotesExportResponse> {
  const response = await http.post<NotesExportResponse>("/wechat-official/content-library/export", payload);
  return response.data;
}

export async function autoRefreshWechatOfficialContent(payload: WechatOfficialContentAutoRefreshPayload): Promise<WechatOfficialContentAutoRefreshResponse> {
  const response = await http.post<WechatOfficialContentAutoRefreshResponse>("/wechat-official/content-library/auto-refresh", payload, { timeout: 600000 });
  return response.data;
}

export async function analyzeWechatOfficialHotspots(
  articleId: number,
  payload: WechatOfficialAnalyzeHotspotsPayload = {}
): Promise<WechatOfficialAnalyzeHotspotsResponse> {
  const response = await http.post<WechatOfficialAnalyzeHotspotsResponse>(
    `/wechat-official/content-library/${articleId}/analyze-hotspots`,
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

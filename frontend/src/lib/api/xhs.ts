import { getAccessToken, http } from "./client";
import type {
  AnalysisDataHealth,
  AnalysisHealthPayload,
  AnalysisReport,
  AnalyticsCommentInsight,
  AnalyticsHotTopic,
  AnalyticsReportPayload,
  AnalyticsReportResponse,
  AnalyticsTopContent,
  BenchmarkCreateDraftsResponse,
  BenchmarkOverview,
  CreateAnalysisReportPayload,
  DataAcquisitionCandidate,
  DataAcquisitionCandidateDecisionPayload,
  DataAcquisitionImportResponse,
  DataAcquisitionReadiness,
  DataAcquisitionRun,
  DataAcquisitionRunPayload,
  CreateDraftFromTopicCardsPayload,
  DashboardOverview,
  Draft,
  CrawlDiagnostic,
  HuitunDiscoveryRunPayload,
  KeywordCandidateImportPayload,
  KeywordCandidateImportResponse,
  KeywordDiscoveryRun,
  KeywordGroup,
  KeywordGroupDetail,
  KeywordGroupPayload,
  MonitoringNote,
  MonitoringRefreshResponse,
  MonitoringSnapshot,
  MonitoringTarget,
  MonitoringTargetPayload,
  NoteComment,
  Paginated,
  PlatformAccount,
  SaveNotesResponse,
  XhsNoteSearchResponse,
  XhsDataCrawlItem,
  XhsDataCrawlPayload,
  XhsKeywordGroupCrawlPayload,
  XhsKeywordGroupCrawlSummary,
  XhsSearchOptions,
  XhsSearchNote,
  XhsQrLoginSession
} from "../../types";

export async function fetchXhsOverview(): Promise<DashboardOverview> {
  const response = await http.get<DashboardOverview>("/xhs/analytics/overview");
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

export async function fetchXhsAnalysisReports(): Promise<AnalysisReport[]> {
  const response = await http.get<AnalysisReport[]>("/xhs/analytics/analysis/reports");
  return response.data;
}

export async function fetchXhsAnalysisReport(reportId: number): Promise<AnalysisReport> {
  const response = await http.get<AnalysisReport>(`/xhs/analytics/analysis/reports/${reportId}`);
  return response.data;
}

export async function checkXhsAnalysisHealth(payload: AnalysisHealthPayload): Promise<AnalysisDataHealth> {
  const response = await http.post<AnalysisDataHealth>("/xhs/analytics/analysis/health", payload);
  return response.data;
}

export async function createXhsAnalysisCollectionPlan(
  payload: AnalysisHealthPayload
): Promise<AnalysisDataHealth["collection_plan"]> {
  const response = await http.post<AnalysisDataHealth["collection_plan"]>(
    "/xhs/analytics/analysis/collection-plan",
    payload
  );
  return response.data;
}

export async function createXhsAnalysisReport(payload: CreateAnalysisReportPayload): Promise<AnalysisReport> {
  const response = await http.post<AnalysisReport>("/xhs/analytics/analysis/reports", payload);
  return response.data;
}

export async function rerunXhsAnalysisReport(reportId: number): Promise<AnalysisReport> {
  const response = await http.post<AnalysisReport>(`/xhs/analytics/analysis/reports/${reportId}/rerun`);
  return response.data;
}

export async function createXhsAnalysisDrafts(
  reportId: number,
  cardId: string,
  payload: CreateDraftFromTopicCardsPayload
): Promise<Draft[]> {
  const response = await http.post<Draft[]>(
    `/xhs/analytics/analysis/reports/${reportId}/topic-cards/${cardId}/drafts`,
    payload
  );
  return response.data;
}

export async function createDataAcquisitionRun(payload: DataAcquisitionRunPayload): Promise<DataAcquisitionRun> {
  const response = await http.post<DataAcquisitionRun>("/xhs/data-acquisition/runs", payload);
  return response.data;
}

export async function fetchDataAcquisitionReadiness(): Promise<DataAcquisitionReadiness> {
  const response = await http.get<DataAcquisitionReadiness>("/xhs/data-acquisition/readiness");
  return response.data;
}

export async function fetchDataAcquisitionRuns(params?: {
  status?: string;
  page?: number;
  page_size?: number;
}): Promise<Paginated<DataAcquisitionRun>> {
  const response = await http.get<Paginated<DataAcquisitionRun>>("/xhs/data-acquisition/runs", { params });
  return response.data;
}

export async function retryDataAcquisitionRun(runId: number): Promise<DataAcquisitionRun> {
  const response = await http.post<DataAcquisitionRun>(`/xhs/data-acquisition/runs/${runId}/rerun`);
  return response.data;
}

export async function cancelDataAcquisitionRun(runId: number): Promise<DataAcquisitionRun> {
  const response = await http.post<DataAcquisitionRun>(`/xhs/data-acquisition/runs/${runId}/cancel`);
  return response.data;
}

export async function fetchDataAcquisitionCandidates(params?: {
  run_id?: number;
  run_ids?: number[];
  status?: string;
  sort_by?: string;
  page?: number;
  page_size?: number;
}): Promise<Paginated<DataAcquisitionCandidate>> {
  const { run_ids, ...rest } = params || {};
  const response = await http.get<Paginated<DataAcquisitionCandidate>>("/xhs/data-acquisition/candidates", {
    params: run_ids?.length ? { ...rest, run_ids: run_ids.join(",") } : rest,
  });
  return response.data;
}

export async function importDataAcquisitionCandidates(
  payload: Pick<DataAcquisitionCandidateDecisionPayload, "candidate_ids">
): Promise<DataAcquisitionImportResponse> {
  const response = await http.post<DataAcquisitionImportResponse>("/xhs/data-acquisition/candidates/import", payload);
  return response.data;
}

export async function excludeDataAcquisitionCandidates(
  payload: DataAcquisitionCandidateDecisionPayload
): Promise<{ items: DataAcquisitionCandidate[] }> {
  const response = await http.post<{ items: DataAcquisitionCandidate[] }>("/xhs/data-acquisition/candidates/exclude", payload);
  return response.data;
}

export async function restoreDataAcquisitionCandidates(
  payload: DataAcquisitionCandidateDecisionPayload
): Promise<{ items: DataAcquisitionCandidate[] }> {
  const response = await http.post<{ items: DataAcquisitionCandidate[] }>("/xhs/data-acquisition/candidates/restore", payload);
  return response.data;
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
): Promise<{
  total: number;
  success_count: number;
  failed_count: number;
  saved_count: number;
  skipped_count: number;
  comment_rate_limited_count?: number;
  comment_skipped_count?: number;
  summary_message?: string;
}> {
  return streamXhsCrawl(
    "/api/xhs/crawl/data",
    payload as Record<string, unknown>,
    { total: 0, success_count: 0, failed_count: 0, saved_count: 0, skipped_count: 0, comment_rate_limited_count: 0, comment_skipped_count: 0, summary_message: "" },
    onItem,
    onProgress,
    onError,
    (event) => ({
      total: Number(event.total || 0),
      success_count: Number(event.success_count || 0),
      failed_count: Number(event.failed_count || 0),
      saved_count: Number(event.saved_count || 0),
      skipped_count: Number(event.skipped_count || 0),
      comment_rate_limited_count: Number(event.comment_rate_limited_count || 0),
      comment_skipped_count: Number(event.comment_skipped_count || 0),
      summary_message: String(event.summary_message || ""),
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

export async function confirmHuitunPasswordLogin(payload: {
  mobile: string;
  password: string;
  ticket: string;
  randStr: string;
  captcha?: string;
  session_id?: number;
}): Promise<XhsQrLoginSession> {
  const response = await http.post<XhsQrLoginSession>("/huitun/login-sessions/password/confirm", payload, { _silent: true } as never);
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

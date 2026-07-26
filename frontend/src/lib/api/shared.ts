import { http } from "./client";
import { fallbackPlatforms } from "../platforms";
import type {
  AutoTask,
  AutoTaskCreatePayload,
  AutoTaskRunResult,
  AutoTaskUpdatePayload,
  AppNotification,
  BatchCreateDraftsPayload,
  BatchCreateDraftsResponse,
  BatchTagNotesPayload,
  BatchTagNotesResponse,
  ComposeImagePayload,
  CreateDraftPayload,
  Draft,
  DraftAiScoreResult,
  ImageUtilityFile,
  NoteAnalysisResult,
  NoteAsset,
  NoteComment,
  NoteImageLocalizationResult,
  NoteSourceImageImportScript,
  NoteSourceImageImportResult,
  NotesExportPayload,
  NotesExportResponse,
  Paginated,
  PlatformAccount,
  PlatformMeta,
  PublishAppDraftHandoff,
  PublishAsset,
  PublishAssetPayload,
  PublishJob,
  PublishJobUpdatePayload,
  ResizeImagePayload,
  RunDueTasksResponse,
  SchedulerStatus,
  SavedNote,
  SendDraftToPublishPayload,
  Tag,
  UserImageFile,
  TagPayload,
  TaskRecord,
  UsageBalance,
  UsagePricing
} from "../../types";

export async function fetchUsageBalance(): Promise<UsageBalance> {
  const response = await http.get<UsageBalance>("/usage/balance", { _silent: true } as never);
  return response.data;
}

export async function fetchUsagePricing(): Promise<UsagePricing> {
  const response = await http.get<UsagePricing>("/usage/pricing", { _silent: true } as never);
  return response.data;
}

export async function fetchPlatforms(): Promise<PlatformMeta[]> {
  try {
    const response = await http.get<Paginated<PlatformMeta>>("/platforms");
    return response.data.items;
  } catch {
    return fallbackPlatforms;
  }
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
  visibility?: "active" | "all" | "excluded";
  feishu_push_status?: string;
  analysis_status?: string | string[];
  core_product_service?: string[];
  content_type?: string | string[];
  reusable_model?: string | string[];
  content_usage?: string[];
  search_attribute?: string[];
  reuse_value?: string | string[];
  sort_by?: "latest" | "engagement" | "likes" | "comments" | "collects";
  page?: number;
  page_size?: number;
};

export type SavedNoteFilterOptions = {
  analysisStatus: Array<{ value: string; label: string }>;
  coreProductService: Array<{ value: string; label: string }>;
  contentType: Array<{ value: string; label: string }>;
  reusableModel: Array<{ value: string; label: string }>;
  contentUsage: Array<{ value: string; label: string }>;
  searchAttribute: Array<{ value: string; label: string }>;
};

export async function fetchSavedNoteIds(platform = "xhs"): Promise<string[]> {
  const response = await http.get<{ items: string[] }>("/notes/ids", { params: { platform } });
  return response.data.items;
}

function csvParam(value?: string | string[]): string | undefined {
  if (Array.isArray(value)) return value.length ? value.join(",") : undefined;
  return value || undefined;
}

function mergeCsvParam(primary?: string | string[], alias?: string | string[]): string | undefined {
  const merged = [csvParam(primary), csvParam(alias)].filter(Boolean);
  return merged.length ? merged.join(",") : undefined;
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
          visibility: platformOrFilters.visibility,
          feishu_push_status: platformOrFilters.feishu_push_status,
          analysis_status: csvParam(platformOrFilters.analysis_status),
          core_product_service: csvParam(platformOrFilters.core_product_service),
          content_type: csvParam(platformOrFilters.content_type),
          reusable_model: csvParam(platformOrFilters.reusable_model),
          content_usage: mergeCsvParam(platformOrFilters.content_usage, platformOrFilters.reuse_value),
          search_attribute: csvParam(platformOrFilters.search_attribute),
          sort_by: platformOrFilters.sort_by,
          page: platformOrFilters.page,
          page_size: platformOrFilters.page_size,
        };
  const response = await http.get<Paginated<SavedNote>>("/notes", { params });
  return response.data;
}

export async function fetchSavedNoteFilterOptions(platform = "xhs", filters: Pick<SavedNoteFilters, "visibility"> = {}): Promise<SavedNoteFilterOptions> {
  const response = await http.get<SavedNoteFilterOptions>("/notes/filter-options", { params: { platform, visibility: filters.visibility } });
  return response.data;
}

export async function fetchSavedNote(noteId: number, silent = false): Promise<SavedNote> {
  const response = await http.get<SavedNote>(`/notes/${noteId}`, { _silent: silent } as never);
  return response.data;
}

export async function analyzeSavedNote(noteId: number): Promise<NoteAnalysisResult> {
  const response = await http.post<NoteAnalysisResult>(`/notes/${noteId}/analysis`, null, { timeout: 600000 });
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

export async function localizeSavedNoteImages(noteId: number): Promise<NoteImageLocalizationResult> {
  const response = await http.post<NoteImageLocalizationResult>(`/notes/${noteId}/assets/localize-images`, null, { _silent: true } as never);
  return response.data;
}

export async function importSavedNoteSourceImages(
  noteId: number,
  payload: { source_url: string; download?: boolean },
): Promise<NoteSourceImageImportResult> {
  const response = await http.post<NoteSourceImageImportResult>(`/notes/${noteId}/assets/import-source-images`, payload, { _silent: true } as never);
  return response.data;
}

export async function createSavedNoteSourceImageImportScript(noteId: number): Promise<NoteSourceImageImportScript> {
  const response = await http.post<NoteSourceImageImportScript>(`/notes/${noteId}/assets/import-source-images/page-script`, null, { _silent: true } as never);
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

export async function updateDraft(
  draftId: number,
  payload: { draft_name?: string; title?: string; body?: string; tags?: { id?: string; name: string }[] },
): Promise<Draft> {
  const response = await http.patch<Draft>(`/drafts/${draftId}`, payload);
  return response.data;
}

export type DraftRewriteCandidatePayload = {
  title: string;
  body: string;
  tags: { id?: string; name: string }[];
  generated_at: string;
};

export type DraftRewriteCandidatesResponse = {
  draft_id: number;
  candidates: Partial<Record<"safe" | "polish" | "seed", DraftRewriteCandidatePayload>>;
};

export async function fetchDraftRewriteCandidates(draftId: number): Promise<DraftRewriteCandidatesResponse> {
  const response = await http.get<DraftRewriteCandidatesResponse>(`/drafts/${draftId}/rewrite-candidates`, { _silent: true } as never);
  return response.data;
}

export async function discardDraftRewriteCandidate(
  draftId: number,
  mode: "safe" | "polish" | "seed",
): Promise<DraftRewriteCandidatesResponse> {
  const response = await http.delete<DraftRewriteCandidatesResponse>(`/drafts/${draftId}/rewrite-candidates/${mode}`, { _silent: true } as never);
  return response.data;
}

export async function deleteDraft(draftId: number): Promise<{ id: number; status: string }> {
  const response = await http.delete<{ id: number; status: string }>(`/drafts/${draftId}`);
  return response.data;
}

export async function scoreDraftWithAi(draftId: number): Promise<DraftAiScoreResult> {
  const response = await http.post<DraftAiScoreResult>(`/drafts/${draftId}/ai-score`, {});
  return response.data;
}

export async function fetchLatestDraftAiScore(draftId: number): Promise<DraftAiScoreResult> {
  const response = await http.get<DraftAiScoreResult>(`/drafts/${draftId}/ai-score/latest`, { _silent: true } as never);
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

export async function localizeDraftAsset(draftId: number, assetId: number): Promise<DraftAsset> {
  const response = await http.post<DraftAsset>(`/drafts/${draftId}/assets/${assetId}/localize`);
  return response.data;
}

export async function reorderDraftAssets(draftId: number, assetIds: number[]): Promise<void> {
  await http.put(`/drafts/${draftId}/assets/reorder`, { asset_ids: assetIds });
}

export async function sendDraftToPublish(draftId: number, payload: SendDraftToPublishPayload): Promise<PublishJob> {
  const response = await http.post<PublishJob>(`/drafts/${draftId}/send-to-publish`, payload);
  return response.data;
}

export async function deleteUserImage(fileName: string): Promise<void> {
  await http.delete(`/files/images/${fileName}`);
}

export async function fetchTask(taskId: number): Promise<TaskRecord> {
  const response = await http.get<TaskRecord>(`/tasks/${taskId}`);
  return response.data;
}

export async function fetchUserImages(): Promise<{ items: UserImageFile[] }> {
  const response = await http.get<{ items: UserImageFile[] }>("/files/images");
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

export async function runDueTasks(platform = "xhs", options?: { confirmRealPublish?: boolean }): Promise<RunDueTasksResponse> {
  const response = await http.post<RunDueTasksResponse>("/tasks/run-due", null, {
    params: { platform, confirm_real_publish: options?.confirmRealPublish === true },
  });
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

export async function publishJobToCreator(jobId: number, options?: { confirmRealPublish?: boolean }): Promise<PublishJob> {
  const response = await http.post<PublishJob>(`/publish/jobs/${jobId}/publish`, null, {
    params: { confirm_real_publish: options?.confirmRealPublish === true },
  });
  return response.data;
}

export async function preparePublishJobAppDraftHandoff(jobId: number): Promise<PublishAppDraftHandoff> {
  const response = await http.post<PublishAppDraftHandoff>(`/publish/jobs/${jobId}/app-draft-handoff`);
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

export async function checkAccount(accountId: number): Promise<PlatformAccount> {
  const response = await http.post<PlatformAccount>(`/accounts/${accountId}/check`);
  return response.data;
}

export async function deleteAccount(accountId: number): Promise<{ id: number; status: string }> {
  const response = await http.delete<{ id: number; status: string }>(`/accounts/${accountId}`);
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

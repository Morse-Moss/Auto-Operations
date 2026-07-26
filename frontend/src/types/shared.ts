import type { FeishuSyncState } from "./feishu";

export type PlatformId =
  | "xhs"
  | "huitun"
  | "douyin"
  | "kuaishou"
  | "bilibili"
  | "wechat_channels"
  | "wechat_official"
  | "demo_platform"
  | "weibo"
  | "xianyu"
  | "taobao";

export type PlatformReleaseStage = "enabled" | "beta" | "planned" | "unavailable";
export type PlatformRegion = "cn" | "global";
export type PlatformType = "content" | "social" | "commerce" | "hybrid";
export type PlatformRiskLevel = "low" | "medium" | "high";
export type PlatformCapabilityStatus = "available" | "partial" | "planned" | "blocked";

export type PlatformCapability = {
  key: string;
  status: PlatformCapabilityStatus;
  risk: PlatformRiskLevel;
  requires_confirmation: boolean;
  notes: string;
};

export type PlatformAccountAuthSchema = {
  key: string;
  label: string;
  auth_mode: "cookie" | "qr_login" | "phone" | "none" | string;
  sub_type?: "pc" | "creator" | "main" | string | null;
  account_kind?: "pc" | "creator" | "main" | string;
  endpoint?: string | null;
  method?: string;
  status: PlatformCapabilityStatus;
  risk?: PlatformRiskLevel;
  requires_confirmation?: boolean;
  requires_secret?: boolean;
  requires_user_action?: boolean;
  sensitive_fields?: string[];
  optional_fields?: string[];
  notes: string;
};
export type PlatformMeta = {
  id: PlatformId;
  name_cn: string;
  name_en: string;
  enabled: boolean;
  status: "enabled" | "beta" | "coming_soon" | "unavailable";
  release_stage: PlatformReleaseStage;
  region: PlatformRegion;
  platform_type: PlatformType;
  default_route: string | null;
  adapter_key: string | null;
  risk_level: PlatformRiskLevel;
  auth_modes: string[];
  capabilities: PlatformCapability[];
  account_auth_schemas?: PlatformAccountAuthSchema[];
  accent_color: string;
  icon: string;
};

export type Paginated<T> = {
  total: number;
  page: number;
  page_size: number;
  items: T[];
};

export type PlatformUser = {
  id: number;
  username: string;
  role: "admin" | "user" | string;
  status: "active" | "disabled" | string;
};

export type AuthTokens = {
  access_token: string;
  refresh_token?: string;
  token_type: "bearer";
};

export type AuthPayload = AuthTokens & {
  user: PlatformUser;
};

export type PlatformAccount = {
  id: number;
  platform: PlatformId;
  sub_type: "pc" | "creator" | "main" | null;
  external_user_id?: string;
  nickname: string;
  avatar_url?: string;
  status: "active" | "healthy" | "expired" | "risk" | "unknown" | string;
  status_message?: string;
  login_ready?: boolean;
  login_readiness_message?: string;
  profile?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
  action?: "created" | "updated" | string;
};

export type NoteAnalysisResult = {
  source?: "system" | "feishu" | string | null;
  analysis_status?: string | null;
  core_product_service?: string | null;
  subject_object: string;
  content_type?: string | null;
  core_points: string;
  target_audience: string;
  title_hook: string;
  cover_type?: string | null;
  title_type?: string | null;
  content_structure: string;
  reusable_model?: string[];
  reusable_models: string[];
  content_usage?: string | null;
  reuse_value?: string | null;
  search_attribute?: string | null;
  score?: number | null;
  rating?: string | null;
  analysis_note: string;
  last_pushed_at?: string | null;
  last_pulled_at?: string | null;
};

export type SavedNote = {
  id: number;
  platform: PlatformId;
  platform_account_id: number;
  note_id: string;
  title: string;
  content: string;
  author_name: string;
  raw_json?: Record<string, unknown>;
  source_url?: string;
  asset_urls?: string[];
  cover_url?: string;
  video_url?: string;
  video_addr?: string;
  media_type?: string;
  note_type?: string;
  created_at: string;
  engagement_metrics?: {
    likes: number;
    collects: number;
    comments: number;
    shares: number;
  };
  analysis_marks?: string[];
  is_analysis_focus?: boolean;
  feishu_sync?: FeishuSyncState;
  analysis_result?: NoteAnalysisResult | null;
  tags?: Tag[];
};

export type NoteAsset = {
  id: number;
  note_id: number;
  asset_type: "image" | "video" | string;
  url: string;
  local_path: string;
  download_url?: string;
  sort_order?: number;
};

export type NoteImageLocalizationResult = {
  total_image_count: number;
  downloaded_count: number;
  skipped_count: number;
  failed_count: number;
  items: Array<{
    asset_id: number;
    status: "downloaded" | "skipped" | "failed" | string;
    local_path: string;
    error: string;
  }>;
};

export type NoteSourceImageImportResult = {
  total_source_image_count: number;
  imported_count: number;
  skipped_count: number;
  downloaded_count: number;
  failed_count: number;
  items: Array<{
    url: string;
    status: "downloaded" | "imported" | "skipped" | "failed" | string;
    asset_id?: number | null;
    local_path: string;
    error: string;
  }>;
};

export type NoteSourceImageImportScript = {
  script: string;
  expires_in_seconds: number;
};

export type NoteComment = {
  id: number;
  note_id: number;
  comment_id: string;
  user_name: string;
  user_id?: string | null;
  content: string;
  like_count: number;
  parent_comment_id?: string | null;
  created_at_remote?: string | null;
  raw_json?: Record<string, unknown>;
};

export type Tag = {
  id: number;
  name: string;
  color: string;
};

export type TagPayload = {
  name: string;
  color?: string;
};

export type BatchTagNotesPayload = {
  note_ids: number[];
  tag_ids: number[];
  mode: "replace" | "add" | "remove";
};

export type BatchTagNotesResponse = {
  updated_count: number;
  items: SavedNote[];
};

export type BatchCreateDraftsPayload = {
  note_ids: number[];
  intent?: "rewrite" | "publish" | string;
};

export type BatchCreateDraftsResponse = {
  created_count: number;
  items: Draft[];
};

export type BenchmarkCreateDraftsResponse = BatchCreateDraftsResponse;

export type NotesExportPayload = {
  note_ids: number[];
  format?: "json" | "csv";
};

export type NotesExportResponse = {
  exported_count: number;
  file_name: string;
  file_path: string;
  download_url: string;
};

export type UsageBucketKey = "credits" | string;

export type UsageBucketBalance = {
  total: number;
  remaining: number;
  status: string;
};

export type UsageBalance = {
  tenant: {
    id: number;
    name: string;
    slug: string;
    kind: string;
    status: string;
  };
  membership: {
    role: string;
    status: string;
  };
  buckets: Record<UsageBucketKey, UsageBucketBalance>;
};

export type UsagePricing = {
  currency: "credits" | string;
  actions: Record<string, number>;
  features: Record<string, { action: string; cost: number }>;
};

export type UsageLimitError = {
  code: "usage_quota_insufficient" | string;
  message: string;
  feature_key?: string;
  bucket?: UsageBucketKey;
  required?: number;
  remaining?: number;
};

export type SaveNotesResponse = {
  saved_count: number;
  skipped_count: number;
  skipped_items: Array<{ note_id: string; reason: string }>;
  items: SavedNote[];
};

export type Draft = {
  id: number;
  platform: PlatformId;
  draft_name?: string;
  title: string;
  body: string;
  tags?: { id?: string; name: string }[];
  source_note_id?: number | null;
  source_article_id?: number | null;
  created_at: string;
};

export type DraftAiScoreLevel = "low" | "medium" | "high" | "excellent";

export type DraftAiScoreDimension = {
  key: string;
  label: string;
  score: number;
  max_score: number;
  reason: string;
};

export type DraftAiScoreRisk = {
  level: "low" | "medium" | "high" | string;
  title: string;
  detail: string;
};

export type DraftAiScoreSuggestion = {
  priority: "low" | "medium" | "high" | string;
  title: string;
  example?: string;
};

export type DraftAiScoreOpportunity = {
  type: string;
  label: string;
  reason: string;
};

export type DraftAiScoreResult = {
  id: number;
  draft_id: number;
  task_id?: number | null;
  overall_score: number;
  potential_level: DraftAiScoreLevel;
  summary: string;
  dimensions: DraftAiScoreDimension[];
  risks: DraftAiScoreRisk[];
  suggestions: DraftAiScoreSuggestion[];
  opportunities: DraftAiScoreOpportunity[];
  disclaimer: string;
  fallback_used?: boolean;
  created_at: string;
};

export type CreateDraftPayload = {
  platform: "xhs";
  source_note_id?: number | null;
  draft_name?: string;
  title?: string;
  body?: string;
  intent?: "rewrite" | "publish" | string;
};

export type TaskRecord = {
  id: number;
  platform: PlatformId;
  task_type: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled" | "exhausted" | string;
  progress: number;
  payload: Record<string, unknown>;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  duration_ms?: number | null;
  error_type?: string | null;
  retry_count?: number;
  max_retries?: number;
  parent_task_id?: number | null;
  children?: TaskRecord[];
};

export type SchedulerStatus = {
  enabled: boolean;
  running: boolean;
  interval_seconds: number;
  jobs: Array<{
    id: string;
    next_run_time?: string | null;
  }>;
  recent_tasks: TaskRecord[];
};

export type RunDueTasksResponse = {
  executed_count: number;
  failed_count: number;
  items: PublishJob[];
};

export type PublishJob = {
  id: number;
  platform_account_id: number;
  source_draft_id?: number | null;
  platform: PlatformId;
  title: string;
  body: string;
  publish_mode: "immediate" | "scheduled" | string;
  publish_options?: PublishOptions;
  status: "pending" | "uploading" | "publishing" | "scheduled" | "published" | "failed" | "cancelled" | string;
  scheduled_at?: string | null;
  external_note_id: string;
  publish_error: string;
  published_at?: string | null;
  created_at: string;
};

export type PublishOptions = {
  topics?: string[];
  location?: string;
  privacy_type?: 0 | 1 | number;
  is_private?: boolean;
  draft_tags?: Array<{ id?: string; name?: string }>;
};

export type PublishAppDraftHandoff = {
  job_id: number;
  status: "requires_mobile_app_handoff" | string;
  draft_saved: boolean;
  real_publish_blocked: boolean;
  handoff: {
    method: "xiaohongshu_app_composer" | string;
    title: string;
    suggested_test_title: string;
    body: string;
    assets: Array<{
      id: number;
      asset_type: "image" | "video" | string;
      file_path: string;
    }>;
    publish_options: PublishOptions;
  };
  verification: {
    verification_code: string;
    requires_user_app_check: boolean;
    acceptance: string;
  };
  limitations: string[];
};

export type SendDraftToPublishPayload = {
  platform_account_id?: number | null;
  publish_mode?: "immediate" | "scheduled";
  scheduled_at?: string | null;
  topics?: string[];
  location?: string | null;
  privacy_type?: 0 | 1 | null;
  is_private?: boolean | null;
  asset_file_path?: string | null;
  asset_file_paths?: string[] | null;
};

export type PublishJobUpdatePayload = {
  title?: string;
  body?: string;
  platform_account_id?: number | null;
  publish_mode?: "immediate" | "scheduled";
  scheduled_at?: string | null;
  topics?: string[];
  location?: string | null;
  privacy_type?: 0 | 1 | null;
  is_private?: boolean | null;
};

export type PublishAsset = {
  id: number;
  publish_job_id: number;
  asset_type: "image" | "video" | string;
  file_path: string;
  upload_status: "pending" | "uploading" | "uploaded" | "failed" | string;
  creator_media_id: string;
  upload_error: string;
  creator_upload_info: Record<string, unknown>;
};

export type PublishAssetPayload = {
  asset_type: "image" | "video";
  file_path: string;
};

export type AutoTask = {
  id: number;
  user_id: number;
  name: string;
  keywords: string[];
  pc_account_id: number;
  creator_account_id: number;
  ai_instruction: string;
  status: "active" | "paused" | "completed" | string;
  last_run_at?: string | null;
  next_run_at?: string | null;
  total_published: number;
  created_at: string;
  schedule_type: "manual" | "daily" | "weekly" | "interval";
  schedule_time: string;
  schedule_days: string;
  schedule_interval_hours: number;
};

export type AutoTaskCreatePayload = {
  name: string;
  keywords: string[];
  pc_account_id: number;
  creator_account_id: number;
  ai_instruction?: string;
  schedule_type?: "manual" | "daily" | "weekly" | "interval";
  schedule_time?: string;
  schedule_days?: string;
  schedule_interval_hours?: number;
};

export type AutoTaskUpdatePayload = {
  name?: string;
  keywords?: string[];
  ai_instruction?: string;
  status?: "active" | "paused" | "completed";
  schedule_type?: "manual" | "daily" | "weekly" | "interval";
  schedule_time?: string;
  schedule_days?: string;
  schedule_interval_hours?: number;
};

export type AutoTaskRunResult = {
  auto_task: AutoTask;
  keyword: string;
  source_note: {
    note_id: string;
    title: string;
    likes: number;
    collects: number;
    comments: number;
  };
  draft: {
    id: number;
    title: string;
    body: string;
    created_at: string;
  };
  publish_job: {
    id: number;
    status: string;
    platform_account_id: number;
  };
};

export type AppNotification = {
  id: number;
  title: string;
  body: string;
  level: "info" | "warning" | "error" | string;
  source_task_id?: number | null;
  source_type?: string | null;
  source_id?: number | null;
  read: boolean;
  created_at: string;
};

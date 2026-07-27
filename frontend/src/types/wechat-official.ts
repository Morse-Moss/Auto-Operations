import type { PlatformCapabilityStatus, Draft } from "./shared.ts";

export type WechatOfficialCapabilityOverview = {
  key: string;
  label: string;
  status: PlatformCapabilityStatus;
  message: string;
};

export type WechatOfficialOverview = {
  platform_id: "wechat_official";
  stage: "foundation_ready" | string;
  external_integration_enabled: boolean;
  research_required_before_integration: boolean;
  research_topics: string[];
  capabilities: WechatOfficialCapabilityOverview[];
  blocked_actions: string[];
};

export type WechatOfficialListResponse<T> = {
  total: number;
  items: T[];
  page?: number;
  page_size?: number;
};

export type WechatOfficialBackendSession = {
  id: number;
  account_id: number;
  biz?: string;
  nickname?: string;
  status: "pending" | "valid" | "expired" | "invalid" | string;
  expires_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type WechatOfficialQrLoginSession = {
  login_session_id: number;
  qrcode_url: string;
  status: "pending" | "valid" | "expired" | string;
};

export type WechatOfficialBackendLoginCompletePayload = {
  cookie: string;
  token: string;
  auth_key: string;
  biz?: string;
  nickname?: string;
  user_agent?: string;
  expires_at?: string | null;
};

export type WechatOfficialCredentialGuide = {
  title: string;
  expected_fields: string[];
  steps: string[];
  risk_warnings: string[];
};

export type WechatOfficialCredentialImportPayload = {
  biz: string;
  uin: string;
  key: string;
  pass_ticket: string;
  wap_sid2: string;
  appmsg_token: string;
  cookie: string;
  timestamp: number | string;
  nickname?: string;
  article_url?: string;
  captured_at?: string | null;
};

export type WechatOfficialCredentialValidatePayload = Partial<WechatOfficialCredentialImportPayload>;

export type WechatOfficialCredentialValidation = {
  valid: boolean;
  missing_fields: string[];
  expected_fields: string[];
};

export type WechatOfficialCredential = {
  id: number;
  account_id: number;
  biz?: string;
  nickname?: string;
  status: "valid" | "expired" | "invalid" | string;
  valid: boolean;
  expires_at?: string | null;
  capabilities: string[];
  article_url?: string;
  created_at?: string | null;
  updated_at?: string | null;
};

export type WechatOfficialProxy = {
  id: number;
  name: string;
  endpoint: string;
  enabled: boolean;
  status: "active" | "cooldown" | "disabled" | string;
  last_error?: string;
  type: "direct" | "public_reference" | "custom" | string;
  supports_sensitive_requests: boolean;
  success_count: number;
  failure_count: number;
  created_at?: string | null;
  updated_at?: string | null;
};

export type WechatOfficialProxyTestPayload = {
  request_type?: "public" | "sensitive" | string;
  success?: boolean;
  error_message?: string;
};

export type WechatOfficialCrawlAccount = {
  id: number;
  name: string;
  biz?: string;
  fake_id?: string;
  alias?: string;
  status: "active" | "login_pending" | "expired" | string;
  raw?: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
};

export type WechatOfficialCrawlJob = {
  id: number;
  account_id?: number | null;
  proxy_node_id?: number | null;
  keyword?: string | null;
  status: "running" | "succeeded" | "failed" | string;
  source?: "redfox" | "backend" | string;
  requested_limit: number;
  fetched_count: number;
  saved_count: number;
  error_message?: string;
  params?: Record<string, unknown>;
  started_at?: string | null;
  finished_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type WechatOfficialArticleMetric = {
  id: number;
  article_id: number;
  read_count: number;
  like_count: number;
  wow_count: number;
  share_count: number;
  comment_count: number;
  captured_at?: string | null;
};

export type WechatOfficialPoolStatus = "candidate" | "shortlisted" | "analyzing" | "draft_ready" | "rejected" | "archived";

export type WechatOfficialHotspotBreakdown = {
  hook?: string;
  pain_point?: string;
  promise?: string;
  credibility?: string;
  structure?: string;
  reuse_angle?: string;
  [key: string]: unknown;
};

export type WechatOfficialArticleAnalysis = {
  recommendation_status?: string;
  pool_status?: WechatOfficialPoolStatus | string;
  category?: string;
  tags?: string[];
  is_favorite?: boolean;
  read_status?: "unread" | "read" | "reading" | string;
  low_follower_evidence?: boolean | "unknown" | "manual" | "inferred" | string;
  low_follower_note?: string;
  business_direction?: string;
  title_type?: string;
  article_type_label?: string;
  viral_factors?: string[];
  core_insight?: string;
  case_info?: Record<string, unknown>;
  customer_conversion_method?: string;
  hotspot_breakdown?: WechatOfficialHotspotBreakdown;
  draft_template_key?: string;
  analysis_mode?: string;
  analysis_updated_at?: string;
  [key: string]: unknown;
};

export type WechatOfficialArticle = {
  id: number;
  account_id?: number | null;
  job_id?: number | null;
  article_url: string;
  title: string;
  digest: string;
  author_name?: string;
  cover_url?: string;
  content_url?: string;
  publish_time_remote?: string | null;
  latest_metric?: WechatOfficialArticleMetric | null;
  analysis?: WechatOfficialArticleAnalysis;
  detail_status?: WechatOfficialDetailStatus;
  is_candidate: boolean;
  created_at?: string | null;
  updated_at?: string | null;
};

export type WechatOfficialContentLibraryItem = WechatOfficialArticle;

export type WechatOfficialSearchAccountsPayload = {
  backend_session_id: number;
  keyword: string;
  upstream_payload?: Record<string, unknown>;
};

export type WechatOfficialArticleSyncPayload = {
  backend_session_id: number;
  account_id?: number | null;
  keyword?: string;
  limit?: number;
  upstream_payload?: Record<string, unknown>;
};

export type WechatOfficialArticleSyncResponse = {
  job: WechatOfficialCrawlJob;
  items: WechatOfficialArticle[];
};

export type WechatOfficialArticleSnapshotPayload = {
  html: string;
};

export type WechatOfficialContentImage = {
  url: string;
  type?: "cover" | "content" | "unknown" | string;
  alt?: string;
  width?: number | null;
  height?: number | null;
  source?: string;
};

export type WechatOfficialArticleSnapshot = {
  id: number;
  article_id: number;
  status: "captured" | "empty" | "failed" | string;
  text: string;
  html?: string;
  images_json?: WechatOfficialContentImage[];
  captured_at?: string | null;
  comment_id?: string;
};

export type WechatOfficialArticleMetricsPayload = {
  credential_id: number;
  html?: string | null;
  cgi_data?: Record<string, unknown> | null;
};

export type WechatOfficialArticleCommentsPayload = {
  comments_payload?: Record<string, unknown>;
  limit?: number;
};

export type WechatOfficialArticleComment = {
  comment_id: string;
  db_id?: number;
  user_name?: string;
  user_id?: string;
  content: string;
  like_count?: number;
  created_at_remote?: string;
  replies?: Array<Record<string, unknown>>;
  raw?: Record<string, unknown>;
};

export type WechatOfficialRecommendationUpdatePayload = {
  recommendation_status?: string | null;
  pool_status?: WechatOfficialPoolStatus | string | null;
  category?: string | null;
  tags?: string[] | null;
  is_favorite?: boolean | null;
  read_status?: "unread" | "read" | "reading" | string | null;
  low_follower_evidence?: boolean | "unknown" | "manual" | "inferred" | string | null;
  low_follower_note?: string | null;
  business_direction?: string | null;
  title_type?: string | null;
  article_type_label?: string | null;
  viral_factors?: string[] | null;
  core_insight?: string | null;
  case_info?: Record<string, unknown> | null;
  customer_conversion_method?: string | null;
  hotspot_breakdown?: WechatOfficialHotspotBreakdown | null;
  draft_template_key?: string | null;
  analysis_mode?: string | null;
};

export type WechatOfficialContentComments = {
  items: WechatOfficialArticleComment[];
  total: number;
  available?: boolean;
  source?: "stored" | "none" | string;
};

export type WechatOfficialDetailStatus = {
  has_cover: boolean;
  has_snapshot: boolean;
  has_text: boolean;
  has_html: boolean;
  image_count: number;
  comment_count: number;
  completeness?: "complete" | "partial" | "missing" | string;
  is_complete?: boolean;
  can_refresh_from_redfox: boolean;
};

export type WechatOfficialContentDetail = {
  article: WechatOfficialContentLibraryItem;
  latest_metric?: WechatOfficialArticleMetric | null;
  analysis: WechatOfficialArticleAnalysis;
  latest_snapshot?: WechatOfficialArticleSnapshot | null;
  images?: WechatOfficialContentImage[];
  comments?: WechatOfficialContentComments;
  detail_status?: WechatOfficialDetailStatus;
  raw_json?: Record<string, unknown>;
};

export type WechatOfficialAnalyzeHotspotsPayload = {
  mode?: "auto" | "template" | string;
  instruction?: string;
};

export type WechatOfficialAnalyzeHotspotsResponse = {
  article_id: number;
  analysis_mode: string;
  analysis: WechatOfficialArticleAnalysis;
};

export type WechatOfficialCreateDraftPayload = {
  rewrite_style?: string;
  target_audience?: string;
  call_to_action?: string;
  template_key?: string;
  template_name?: string;
  template_instruction?: string;
  opening_angle?: string;
};

export type WechatOfficialDraft = Omit<Draft, "platform" | "source_note_id"> & {
  platform: "wechat_official";
  source_article_id?: number | null;
};

export type WechatOfficialDraftDryRunPayload = {
  title?: string | null;
  body?: string | null;
};

export type WechatOfficialDraftDryRun = {
  draft_id: number;
  ok: boolean;
  publish_blocked: boolean;
  sendall_blocked: boolean;
  preview_blocked?: boolean;
  checks: Record<string, "ok" | "missing" | "blocked" | "warning" | string>;
};

export type WechatOfficialRedfoxConfig = {
  id: number;
  name: string;
  base_url: string;
  has_api_key: boolean;
  masked_api_key?: string;
  status: "unknown" | "valid" | "invalid" | string;
  last_checked_at?: string | null;
  last_error?: string;
  created_at?: string | null;
  updated_at?: string | null;
};

export type WechatOfficialRedfoxConfigResponse = {
  configured: boolean;
  config: WechatOfficialRedfoxConfig | null;
};

export type WechatOfficialRedfoxConfigPayload = {
  name?: string;
  base_url?: string;
  api_key?: string;
};

export type WechatOfficialRedfoxKeywordCollectPayload = {
  keyword: string;
  pages?: number;
  target_count?: number;
  max_pages?: number;
  sort_type?: "_0" | "_2" | "_4" | string;
  min_read_count?: number;
  save_snapshot?: boolean;
};

export type WechatOfficialRedfoxAccountCollectPayload = {
  account: string;
  account_name?: string;
  pages?: number;
  sort_type?: "_0" | "_2" | "_4" | string;
  publish_time_start?: string | null;
  publish_time_end?: string | null;
  min_read_count?: number;
  save_snapshot?: boolean;
};

export type WechatOfficialRedfoxUrlImportPayload = {
  url: string;
  min_read_count?: number;
  save_snapshot?: boolean;
};

export type WechatOfficialRedfoxCollectSummary = {
  fetched: number;
  saved: number;
  deduped: number;
  viral_candidates: number;
  failed: number;
  api_calls: number;
  requested_target_count?: number;
  max_pages?: number;
  filtered?: number;
  relevance_matched?: number;
  target_reached?: boolean;
  estimated_credit_cost?: number | null;
};

export type WechatOfficialRedfoxCollectResponse = {
  summary: WechatOfficialRedfoxCollectSummary;
  job: WechatOfficialCrawlJob & { source?: string };
  items: WechatOfficialContentLibraryItem[];
};

export type WechatOfficialRedfoxCollectJobListResponse = {
  items: WechatOfficialCrawlJob[];
  total: number;
  page: number;
  page_size: number;
};

export type WechatOfficialRedfoxCollectJobDetail = {
  job: WechatOfficialCrawlJob;
  items: WechatOfficialContentLibraryItem[];
  total: number;
};

export type WechatOfficialReadinessCheck = {
  key: string;
  label: string;
  status: "ready" | "partial" | "missing" | "blocked" | string;
  message: string;
  action: string;
};

export type WechatOfficialReadiness = {
  summary: {
    overall_status: "ready" | "partial" | "blocked" | string;
    next_actions: string[];
  };
  checks: WechatOfficialReadinessCheck[];
  redfox: { configured: boolean; status: string; last_error?: string; last_checked_at?: string | null };
  sessions: { valid: number; pending: number; expired: number; invalid: number; total: number };
  content: {
    total: number;
    candidate: number;
    shortlisted: number;
    analyzing: number;
    draft_ready: number;
    rejected: number;
    snapshots: number;
    images: number;
    comments: number;
    metrics: number;
  };
  feishu: { configured: boolean; enabled: boolean; last_test_status?: string | null; last_test_message?: string | null };
  drafts: { count: number; dry_run_available: boolean };
  image_studio: { available: boolean; material_upload_blocked: boolean };
  safety: { publish_blocked: boolean; sendall_blocked: boolean; preview_blocked: boolean; material_upload_blocked: boolean; message: string };
};

export type WechatOfficialArticlesExportPayload = {
  article_ids: number[];
  format?: "json" | "csv";
};

export type WechatOfficialContentAutoRefreshPayload = {
  article_ids: number[];
};

export type WechatOfficialContentAutoRefreshResponse = {
  requested_count: number;
  refreshed_count: number;
  failed_count: number;
  failed: Array<Record<string, unknown>>;
};

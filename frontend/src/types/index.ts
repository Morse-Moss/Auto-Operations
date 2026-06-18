export type PlatformId =
  | "xhs"
  | "huitun"
  | "douyin"
  | "kuaishou"
  | "bilibili"
  | "wechat_channels"
  | "wechat_official"
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
  accent_color: string;
  icon: string;
};

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
  status: "running" | "succeeded" | "failed" | string;
  requested_limit: number;
  fetched_count: number;
  saved_count: number;
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

export type WechatOfficialDraft = Draft & {
  platform: "wechat_official";
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
  estimated_credit_cost?: number | null;
};

export type WechatOfficialRedfoxCollectResponse = {
  summary: WechatOfficialRedfoxCollectSummary;
  job: WechatOfficialCrawlJob & { source?: string };
  items: WechatOfficialContentLibraryItem[];
};

export type Paginated<T> = {
  total: number;
  page: number;
  page_size: number;
  items: T[];
};

export type DashboardOverview = {
  platform: "xhs";
  today_crawls: number;
  saved_notes: number;
  pending_publishes: number;
  healthy_accounts: number;
  at_risk_accounts: number;
  comment_count?: number;
  total_engagement?: number;
  hot_topics: Array<{ keyword: string; notes: number; engagement: number }>;
  recent_activity: Array<{ type: string; title: string; status: string }>;
};

export type PlatformUser = {
  id: number;
  username: string;
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
  profile?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
  action?: "created" | "updated" | string;
};

export type XhsQrLoginSession = {
  session_id: number;
  status: "pending" | "scanned" | "confirmed" | "expired" | string;
  qr_url: string;
  qr_image_data_url?: string;
  account?: PlatformAccount | null;
  creator_account?: PlatformAccount | null;
};

export type XhsSearchNote = {
  note_id: string;
  note_url?: string;
  title: string;
  content: string;
  author_id: string;
  author_name: string;
  author_avatar: string;
  cover_url: string;
  likes: number;
  collects: number;
  comments: number;
  shares: number;
  type: string;
  timestamp?: number | string;
  image_urls?: string[];
  video_url?: string;
  video_addr?: string;
  tags?: string[];
  quality_status?: string;
  diagnostic_kind?: string | null;
  recoverable?: boolean;
  user_message?: string;
  can_save?: boolean;
  raw: Record<string, unknown>;
};

export type XhsNoteSearchResponse = {
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
  items: XhsSearchNote[];
  raw: Record<string, unknown>;
};

export type XhsSearchOptions = {
  account_id: number;
  keyword: string;
  page?: number;
  sort_type_choice?: number;
  note_type?: number;
  note_time?: number;
  note_range?: number;
  pos_distance?: number;
  geo?: string;
};

export type XhsDataCrawlMode = "note_urls" | "search" | "comments";

export type XhsDataCrawlPayload = {
  account_id: number;
  mode: XhsDataCrawlMode;
  urls?: string[];
  keyword?: string;
  pages?: number;
  max_notes?: number;
  time_sleep?: number;
  comment_sleep?: number;
  fetch_comments?: boolean;
  save_to_library?: boolean;
  sort_type_choice?: number;
  note_type?: number;
  note_time?: number;
  note_range?: number;
  pos_distance?: number;
  geo?: string;
};

export type XhsKeywordGroupCrawlPayload = {
  account_id: number;
  keyword_group_id: number;
  keyword_limit?: number;
  max_notes_per_keyword?: number;
  time_sleep?: number;
  comment_sleep?: number;
  fetch_comments?: boolean;
  sort_type_choice?: number;
  note_type?: number;
  note_time?: number;
};

export type XhsKeywordGroupCrawlSummary = {
  total: number;
  success_count: number;
  failed_count: number;
  saved_count: number;
  skipped_count: number;
  rate_limited_count: number;
  missing_detail_count: number;
  summary_message: string;
};

export type XhsDataCrawlItem = {
  source: string;
  status: "success" | "partial" | "failed" | "skipped" | string;
  error: string;
  keyword?: string;
  quality_status?: string;
  recoverable?: boolean;
  diagnostic_kind?: string | null;
  save_diagnostic_kind?: string | null;
  user_message?: string;
  saved?: boolean;
  note?: XhsSearchNote | null;
  comments: NoteComment[];
  comment_count: number;
  comment_status?: "not_requested" | "success" | "failed" | "rate_limited" | "skipped_rate_limited" | string;
  comment_error?: string;
};

export type XhsDataCrawlResponse = {
  task: TaskRecord;
  total: number;
  success_count: number;
  failed_count: number;
  items: XhsDataCrawlItem[];
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
  asset_urls?: string[];
  cover_url?: string;
  video_url?: string;
  video_addr?: string;
  created_at: string;
  engagement_metrics?: {
    likes: number;
    collects: number;
    comments: number;
    shares: number;
  };
  analysis_marks?: string[];
  is_analysis_focus?: boolean;
  tags?: Tag[];
};

export type AnalyticsTopContent = {
  id: number;
  note_id: string;
  title: string;
  author_name: string;
  created_at: string;
  likes: number;
  collects: number;
  comments: number;
  shares: number;
  engagement: number;
};

export type AnalyticsHotTopic = {
  keyword: string;
  notes: number;
  engagement: number;
};

export type AnalyticsCommentInsight = {
  total_comments: number;
  question_count: number;
  top_terms: Array<{ term: string; count: number }>;
  top_comments: Array<{
    id: number;
    note_id: number;
    user_name: string;
    content: string;
    like_count: number;
  }>;
};

export type BenchmarkTopNote = AnalyticsTopContent;

export type BenchmarkItem = {
  target_id: number;
  target_type: "account" | "brand" | string;
  name: string;
  value: string;
  status: string;
  last_refreshed_at?: string | null;
  matched_notes: number;
  total_engagement: number;
  average_engagement: number;
  top_notes: BenchmarkTopNote[];
};

export type BenchmarkOverview = {
  total_targets: number;
  matched_notes: number;
  total_engagement: number;
  average_engagement: number;
  items: BenchmarkItem[];
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

export type AnalyticsReportPayload = {
  note_ids?: number[];
  format?: "json";
};

export type AnalyticsReportResponse = {
  report_type: "operations";
  generated_at: string;
  note_count: number;
  file_name: string;
  file_path: string;
  download_url: string;
  summary: {
    note_count: number;
    total_engagement: number;
    comment_count: number;
    top_topics: AnalyticsHotTopic[];
    top_notes: AnalyticsTopContent[];
    benchmark_count: number;
  };
};

export type AnalysisReportStatus = "pending" | "running" | "completed" | "failed";

export type AnalysisDataHealth = {
  status: "insufficient" | "minimum" | "standard";
  can_generate: boolean;
  confidence_cap: "none" | "low" | "medium" | "high";
  metrics: {
    valid_note_count: number;
    comment_count: number;
    covered_keyword_count: number;
    representative_note_count: number;
    high_engagement_note_count: number;
    total_engagement?: number;
  };
  missing: Array<{ key: string; message: string; current: number; required: number }>;
  warnings: string[];
  collection_plan: {
    needed: boolean;
    recommended_keywords: string[];
    recommended_notes_per_keyword: number;
    should_collect_comments: boolean;
  };
};

export type AnalysisEvidencePool = {
  notes: Array<{
    evidence_id: string;
    note_id: number;
    title: string;
    author_name: string;
    likes: number;
    collects: number;
    comments: number;
    shares: number;
    engagement: number;
    matched_keywords: string[];
    excerpt: string;
  }>;
  comments: Array<{
    evidence_id: string;
    comment_id: number;
    note_id: number;
    content: string;
    like_count: number;
    signals: string[];
  }>;
  keywords: Array<{ evidence_id: string; keyword: string; matched_notes: number; matched_comments: number }>;
  metrics: Array<{ evidence_id: string; name: string; value: number; description: string }>;
  benchmarks: Array<Record<string, unknown>>;
};

export type InsightCard = {
  id: string;
  title: string;
  score: number;
  sub_scores: {
    traffic_potential: number;
    demand_strength: number;
    competition_pressure: number;
    actionability: number;
  };
  confidence: "low" | "medium" | "high";
  confidence_reason: string;
  facts: Array<Record<string, unknown>>;
  inferences: Array<Record<string, unknown>>;
  recommendations: Array<Record<string, unknown>>;
  evidence_ids: string[];
  topic_card_ids: string[];
};

export type TopicCard = {
  id: string;
  insight_id: string;
  title_direction: string;
  target_pain: string;
  content_angle: string;
  recommended_structure: string[];
  recommended_content_form: string[];
  tags: string[];
  cover_suggestion: string;
  expected_advantage: string;
  risk_warning: string;
  evidence_ids: string[];
};

export type AnalysisResultJson = {
  summary: {
    facts: Array<{ id: string; text: string; evidence_ids: string[] }>;
    inferences: Array<{ id: string; text: string; evidence_ids: string[] }>;
    recommendations: Array<{ id: string; text: string; evidence_ids: string[] }>;
  };
  insight_cards: InsightCard[];
  topic_cards: TopicCard[];
  report_warnings: string[];
};

export type AnalysisReport = {
  id: number;
  platform: PlatformId;
  report_type: string;
  status: AnalysisReportStatus;
  title: string;
  input_config: Record<string, unknown>;
  data_health: AnalysisDataHealth;
  evidence_pool: AnalysisEvidencePool;
  result_json?: AnalysisResultJson | null;
  html_file_path: string;
  error_message?: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
};

export type AnalysisHealthPayload = {
  keyword_group_id: number;
  excluded_note_ids?: number[];
  source_note_ids?: number[];
  benchmark_target_ids?: number[];
};

export type CreateAnalysisReportPayload = AnalysisHealthPayload & {
  title: string;
};

export type CreateDraftFromTopicCardsPayload = {
  topic_cards: TopicCard[];
};

export type SaveNotesResponse = {
  saved_count: number;
  items: SavedNote[];
};

export type Draft = {
  id: number;
  platform: PlatformId;
  title: string;
  body: string;
  tags?: { id?: string; name: string }[];
  source_note_id?: number | null;
  created_at: string;
};

export type CreateDraftPayload = {
  platform: "xhs";
  source_note_id?: number;
  title?: string;
  body?: string;
  intent?: "rewrite" | "publish" | string;
};

export type ModelType = "text" | "image";

export type ModelConfig = {
  id: number;
  name: string;
  model_type: ModelType;
  provider: string;
  model_name: string;
  base_url: string;
  has_api_key: boolean;
  is_default: boolean;
};

export type ModelConfigPayload = {
  name: string;
  model_type: ModelType;
  provider: string;
  model_name: string;
  base_url: string;
  api_key: string;
  is_default: boolean;
};

export type RewriteDraftPayload = {
  draft_id: number;
  instruction?: string;
};

export type GenerateNotePayload = {
  platform?: "xhs";
  topic: string;
  reference?: string;
  instruction?: string;
};

export type GenerateTitlePayload = {
  title?: string;
  body: string;
  count?: number;
};

export type GenerateTagsPayload = {
  title?: string;
  body: string;
  count?: number;
};

export type PolishTextPayload = {
  text: string;
  instruction?: string;
};

export type GeneratedImageAsset = {
  id: number;
  draft_id?: number | null;
  prompt: string;
  model_name: string;
  params: Record<string, unknown>;
  file_path: string;
  created_at: string;
};

export type GenerateCoverPayload = {
  prompt: string;
  draft_id?: number;
  size?: string;
  style?: string;
};

export type GenerateImagePayload = {
  prompt: string;
  reference_images?: string[];
  save_to_assets?: boolean;
};

export type GenerateImageResult = {
  url: string;
  raw?: unknown;
  asset?: GeneratedImageAsset;
};

export type GenerateImageTaskResult = {
  task_id: number;
  status: string;
  progress: number;
  payload: Record<string, unknown>;
};

export type UserImageFile = {
  file_name: string;
  url: string;
  size: number;
};

export type DescribeImagePayload = {
  image_url: string;
  instruction?: string;
};

export type ImageUtilityFile = {
  file_name: string;
  file_path: string;
  download_url: string;
  width: number;
  height: number;
  media_type: string;
};

export type ComposeImagePayload = {
  title: string;
  body?: string;
  width?: number;
  height?: number;
  background_color?: string;
  accent_color?: string;
};

export type ResizeImagePayload = {
  source_file_name: string;
  width?: number;
  height?: number;
  mode?: "cover" | "contain";
  format?: "png" | "jpeg";
  quality?: number;
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

export type MonitoringTarget = {
  id: number;
  platform: PlatformId;
  target_type: "keyword" | "account" | "brand" | "note_url" | string;
  name: string;
  value: string;
  status: "active" | "paused" | string;
  config: Record<string, unknown>;
  last_refreshed_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type MonitoringTargetPayload = {
  target_type: "keyword" | "account" | "brand" | "note_url";
  name?: string;
  value: string;
  status?: "active" | "paused";
  config?: Record<string, unknown>;
};

export type MonitoringSnapshot = {
  id: number;
  target_id: number;
  payload: {
    matched_count?: number;
    total_engagement?: number;
    top_notes?: Array<{
      id: number;
      note_id: string;
      title: string;
      author_name: string;
      engagement: number;
    }>;
  };
  created_at: string;
};

export type MonitoringNote = {
  id: number;
  note_id: string;
  title: string;
  author_name: string;
  created_at: string;
  likes: number;
  collects: number;
  comments: number;
  shares: number;
  engagement: number;
};

export type MonitoringRefreshResponse = {
  target: MonitoringTarget;
  task: TaskRecord;
  snapshot: MonitoringSnapshot;
};

export type KeywordGroup = {
  id: number;
  platform: PlatformId;
  name: string;
  keywords: string[];
  created_at: string;
  updated_at: string;
};

export type KeywordGroupPayload = {
  platform?: PlatformId;
  name: string;
  keywords: string[];
};

export type KeywordGroupDetail = KeywordGroup & {
  trend: {
    total_matches: number;
    total_engagement: number;
    keywords: Array<{ keyword: string; notes: number; engagement: number }>;
    matched_notes: Array<{
      id: number;
      note_id: string;
      title: string;
      author_name: string;
      engagement: number;
      created_at: string;
    }>;
  };
};

export type HuitunDiscoverySourceMode = "manual_table" | "manual_json" | "local_connector_output" | "live_account";

export type KeywordDiscoveryItem = {
  id: number;
  run_id: number;
  platform: PlatformId;
  source: "huitun" | string;
  source_keyword: string;
  keyword: string;
  hot_value_text?: string | null;
  hot_value_number?: number | null;
  note_count?: number | null;
  interaction_text?: string | null;
  interaction_number?: number | null;
  categories: Array<{ label: string; rate?: string | null }>;
  rank_index: number;
  selected: boolean;
  imported_group_id?: number | null;
  created_at: string;
};

export type HuitunKeywordDiscoverySeedResult = {
  source_keyword: string;
  status: "success" | "failed" | string;
  item_count: number;
  error_message?: string;
};

export type HuitunKeywordDiscoverySummary = {
  success_seed_count: number;
  failed_seed_count: number;
  total_item_count: number;
};

export type KeywordDiscoveryRun = {
  id: number;
  platform: PlatformId;
  source: "huitun" | string;
  seed_keywords: string[];
  limit_per_seed: number;
  source_mode: HuitunDiscoverySourceMode;
  status: "running" | "completed" | "partial_failed" | "failed" | string;
  error_message?: string | null;
  created_at: string;
  finished_at?: string | null;
  seed_results: HuitunKeywordDiscoverySeedResult[];
  summary: HuitunKeywordDiscoverySummary;
  items: KeywordDiscoveryItem[];
};

export type HuitunDiscoveryRunPayload = {
  source_mode: HuitunDiscoverySourceMode;
  limit_per_seed?: number;
  account_id?: number;
  inputs: Array<{
    source_keyword: string;
    table_rows?: string[][];
    items?: Array<Record<string, unknown>>;
  }>;
};

export type KeywordCandidateImportPayload = {
  candidate_ids: number[];
  merge_mode?: "append_dedupe";
  target?: {
    mode: "create";
    name: string;
    platform?: PlatformId;
  };
};

export type KeywordCandidateImportResponse = {
  group: KeywordGroup;
  imported_keywords: string[];
  items: KeywordDiscoveryItem[];
};

export type CrawlDiagnostic = {
  id: number;
  user_id: number;
  task_id?: number | null;
  platform_account_id?: number | null;
  platform: PlatformId;
  source: string;
  note_id?: string | null;
  note_url?: string | null;
  stage: string;
  kind: string;
  severity: "info" | "warning" | "error" | "blocked" | string;
  recoverable: boolean;
  message: string;
  user_message: string;
  raw_json: Record<string, unknown>;
  created_at: string;
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

export type SendDraftToPublishPayload = {
  platform_account_id?: number | null;
  publish_mode?: "immediate" | "scheduled";
  scheduled_at?: string | null;
  topics?: string[];
  location?: string | null;
  privacy_type?: 0 | 1 | null;
  is_private?: boolean | null;
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

import type { PlatformId, PlatformAccount, SavedNote, NoteComment, TaskRecord } from "./shared";

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

export type XhsQrLoginSession = {
  session_id: number;
  status: "pending" | "scanned" | "confirmed" | "expired" | string;
  qr_url: string;
  qr_image_data_url?: string;
  message?: string;
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

export type DataAcquisitionStatus = "pending" | "running" | "completed" | "partial_failed" | "failed" | "cancelled" | "expired";

export type DataAcquisitionType =
  | "trend_keywords"
  | "note_search"
  | "note_rank"
  | "note_detail_enrichment"
  | "keyword_analysis"
  | "file_import";

export type DataAcquisitionCandidate = {
  id: number;
  run_id: number;
  platform: "xhs" | string;
  candidate_type: "note" | "keyword" | "note_detail" | "keyword_analysis" | string;
  source_keyword: string;
  platform_note_id: string;
  original_url: string;
  title: string;
  content_excerpt: string;
  author_name: string;
  cover_url: string;
  asset_urls: string[];
  publish_time?: string | null;
  update_time?: string | null;
  rank_index: number;
  category: string;
  tags: string[];
  metrics: {
    like_count?: number;
    collect_count?: number;
    comment_count?: number;
    share_count?: number;
    estimated_read_count?: number;
    interaction_count?: number;
  };
  status: "pending" | "imported" | "excluded" | "expired" | string;
  imported_note_id?: number | null;
  decision_reason_code?: string;
  decision_reason_text?: string;
  created_at: string;
  updated_at: string;
  expires_at: string;
};

export type DataAcquisitionRun = {
  id: number;
  task_id?: number | null;
  platform: "xhs" | string;
  acquisition_type: DataAcquisitionType | string;
  status: DataAcquisitionStatus | string;
  requested_limit: number;
  effective_limit: number;
  params: Record<string, unknown>;
  candidate_count: number;
  user_message?: string;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  cancellation_requested: boolean;
  candidates?: DataAcquisitionCandidate[];
};

export type DataAcquisitionReadiness = {
  available: boolean;
  status: "ready" | "missing" | "expired" | string;
  message: string;
  next_action: string;
};

export type DataAcquisitionRunPayload = {
  acquisition_type: "note_search";
  account_id?: number | null;
  params: {
    keyword: string;
    limit?: number;
    sort?: string;
    note_type?: string;
  };
};

export type DataAcquisitionCandidateDecisionPayload = {
  candidate_ids: number[];
  reason_code?: string;
  reason_text?: string;
};

export type DataAcquisitionImportResponse = {
  imported_count: number;
  message: string;
  items: SavedNote[];
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

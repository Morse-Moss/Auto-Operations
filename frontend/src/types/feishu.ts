export type FeishuIntegrationConfig = {
  id?: number;
  app_id: string;
  has_app_secret: boolean;
  bitable_url: string;
  bitable_app_token?: string | null;
  table_id: string;
  view_id?: string | null;
  collaborator_member_type: string;
  collaborator_member_id: string;
  collaborator_perm: string;
  enabled: boolean;
  last_test_status?: string | null;
  last_test_message?: string | null;
  last_tested_at?: string | null;
};

export type FeishuIntegrationConfigPayload = {
  app_id: string;
  app_secret: string;
  bitable_url: string;
  table_id: string;
  enabled: boolean;
  collaborator_member_type: string;
  collaborator_member_id: string;
  collaborator_perm: string;
};

export type FeishuGrantPermissionPayload = {
  member_type?: string;
  member_id?: string;
  perm?: string;
  notify_lark?: boolean;
};

export type FeishuGrantPermissionResponse = {
  status: string;
  message?: string;
  is_all_success?: boolean;
  fail_members?: Array<Record<string, unknown>>;
  member_type?: string;
  member_id?: string;
  perm?: string;
  config?: FeishuIntegrationConfig;
};

export type FeishuCreateAnalysisBasePayload = {
  base_name?: string;
  table_name?: string;
  folder_token?: string;
};

export type FeishuCreateAnalysisBaseResponse = {
  status: string;
  message?: string;
  app_token?: string;
  table_id?: string;
  bitable_url?: string;
  created_fields?: number;
  skipped_fields?: number;
  grant_result?: FeishuGrantPermissionResponse | null;
  grant_message?: string;
  config?: FeishuIntegrationConfig;
};

export type FeishuSyncState = {
  push_status: "not_synced" | "dry_run" | "synced" | "failed" | string;
  pull_status: "not_pulled" | "success" | "failed" | string;
  external_record_id?: string | null;
  last_error: string;
};

export type FeishuPushNotesPayload = {
  note_ids: number[];
  dry_run?: boolean;
  overwrite_existing?: boolean;
};

export type FeishuPushAllNotesPayload = {
  dry_run?: boolean;
  only_unsynced?: boolean;
  batch_size?: number;
  overwrite_existing?: boolean;
};

export type FeishuPullNotesPayload = {
  note_ids?: number[];
  dry_run?: boolean;
  records?: Array<Record<string, unknown>>;
};

export type FeishuPushWechatOfficialArticlesPayload = {
  article_ids: number[];
  dry_run?: boolean;
};

export type FeishuPullWechatOfficialArticlesPayload = {
  article_ids?: number[];
  dry_run?: boolean;
  records?: Array<Record<string, unknown>>;
};

export type FeishuSyncResponse = {
  dry_run?: boolean;
  total_count?: number;
  processed_count?: number;
  created_count?: number;
  updated_count: number;
  failed_count: number;
  unmatched_count?: number;
  errors: unknown[];
  records?: Array<Record<string, unknown>>;
  batches?: Array<Record<string, unknown>>;
};

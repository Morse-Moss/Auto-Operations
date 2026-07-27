import { http } from "./client.ts";
import type {
  FeishuCreateAnalysisBasePayload,
  FeishuCreateAnalysisBaseResponse,
  FeishuGrantPermissionPayload,
  FeishuGrantPermissionResponse,
  FeishuIntegrationConfig,
  FeishuIntegrationConfigPayload,
  FeishuPullNotesPayload,
  FeishuPullWechatOfficialArticlesPayload,
  FeishuPushAllNotesPayload,
  FeishuPushNotesPayload,
  FeishuPushWechatOfficialArticlesPayload,
  FeishuSyncResponse
} from "../../types/index.ts";

export async function fetchFeishuConfig(): Promise<FeishuIntegrationConfig> {
  const response = await http.get<FeishuIntegrationConfig>("/integrations/feishu/config");
  return response.data;
}

export async function saveFeishuConfig(payload: FeishuIntegrationConfigPayload): Promise<FeishuIntegrationConfig> {
  const response = await http.put<FeishuIntegrationConfig>("/integrations/feishu/config", payload);
  return response.data;
}

export async function testFeishuConnection(): Promise<{ status: string; message: string; field_count?: number }> {
  const response = await http.post<{ status: string; message: string; field_count?: number }>("/integrations/feishu/test");
  return response.data;
}

export async function createFeishuAnalysisBase(payload: FeishuCreateAnalysisBasePayload = {}): Promise<FeishuCreateAnalysisBaseResponse> {
  const response = await http.post<FeishuCreateAnalysisBaseResponse>("/integrations/feishu/create-analysis-base", payload);
  return response.data;
}

export async function grantFeishuPermission(payload: FeishuGrantPermissionPayload = {}): Promise<FeishuGrantPermissionResponse> {
  const response = await http.post<FeishuGrantPermissionResponse>("/integrations/feishu/grant-permission", payload);
  return response.data;
}

export async function ensureFeishuFields(payload: { dry_run?: boolean } = { dry_run: true }): Promise<{ dry_run: boolean; status: string; fields: Array<Record<string, unknown>>; created_count?: number; skipped_count?: number; message?: string }> {
  const response = await http.post<{ dry_run: boolean; status: string; fields: Array<Record<string, unknown>>; created_count?: number; skipped_count?: number; message?: string }>("/integrations/feishu/ensure-fields", payload);
  return response.data;
}

export async function pushXhsNotesToFeishu(payload: FeishuPushNotesPayload): Promise<FeishuSyncResponse> {
  const response = await http.post<FeishuSyncResponse>("/integrations/feishu/xhs-notes/push", payload);
  return response.data;
}

export async function pushAllXhsNotesToFeishu(payload: FeishuPushAllNotesPayload = {}): Promise<FeishuSyncResponse> {
  const response = await http.post<FeishuSyncResponse>("/integrations/feishu/xhs-notes/push-all", payload, { timeout: 600000 });
  return response.data;
}

export async function pullXhsNotesFromFeishu(payload: FeishuPullNotesPayload): Promise<FeishuSyncResponse> {
  const response = await http.post<FeishuSyncResponse>("/integrations/feishu/xhs-notes/pull", payload);
  return response.data;
}

export async function pushWechatOfficialArticlesToFeishu(payload: FeishuPushWechatOfficialArticlesPayload): Promise<FeishuSyncResponse> {
  const response = await http.post<FeishuSyncResponse>("/integrations/feishu/wechat-official/articles/push", payload);
  return response.data;
}

export async function pullWechatOfficialArticlesFromFeishu(payload: FeishuPullWechatOfficialArticlesPayload): Promise<FeishuSyncResponse> {
  const response = await http.post<FeishuSyncResponse>("/integrations/feishu/wechat-official/articles/pull", payload);
  return response.data;
}

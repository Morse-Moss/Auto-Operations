import { readFileSync } from 'node:fs';
import { basename } from 'node:path';

import type { FeishuConfig } from './config.js';

export interface FeishuTransportResponse {
  ok: boolean;
  status: number;
  json(): Promise<unknown>;
}

export type FeishuTransport = (url: string, init: RequestInit) => Promise<FeishuTransportResponse>;

export interface FeishuRecord {
  recordId: string;
  fields: Record<string, unknown>;
}

export interface FeishuFileToken {
  fileToken: string;
}

export interface FeishuField {
  fieldId: string;
  fieldName: string;
  type: number;
  options: string[];
}

export interface FeishuFieldDefinition {
  fieldName: string;
  type: number;
}

interface FeishuApiResponse<T> {
  code?: number;
  msg?: string;
  data?: T;
}

const REQUEST_TIMEOUT_MS = 20_000;

function apiUrl(path: string): string {
  return `https://open.feishu.cn/open-apis${path}`;
}

export class FeishuClient {
  private tenantAccessToken: string | null = null;
  private bitableAppToken: string | null = null;

  constructor(
    private readonly config: FeishuConfig,
    private readonly transport: FeishuTransport = fetch as unknown as FeishuTransport,
  ) {}

  private async request<T>(url: string, init: RequestInit): Promise<T> {
    console.error(`[feishu-api] ${init.method ?? 'GET'} ${url}`);
    const response = await this.transport(url, { ...init, signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS) });
    const json = await response.json() as FeishuApiResponse<T>;
    if (!response.ok || (json.code !== undefined && json.code !== 0)) {
      throw new Error(`Feishu API failed: ${response.status} ${json.code ?? ''} ${json.msg ?? ''}`.trim());
    }
    if (json.data === undefined) {
      return {} as T;
    }
    return json.data;
  }

  async getTenantAccessToken(): Promise<string> {
    if (this.tenantAccessToken !== null) {
      return this.tenantAccessToken;
    }

    const url = apiUrl('/auth/v3/tenant_access_token/internal');
    console.error(`[feishu-api] POST ${url}`);
    const response = await this.transport(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ app_id: this.config.appId, app_secret: this.config.appSecret }),
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
    const json = await response.json() as FeishuApiResponse<{ tenant_access_token: string }> & { tenant_access_token?: string };
    if (!response.ok || (json.code !== undefined && json.code !== 0)) {
      throw new Error(`Feishu API failed: ${response.status} ${json.code ?? ''} ${json.msg ?? ''}`.trim());
    }
    const token = json.tenant_access_token ?? json.data?.tenant_access_token;
    if (token === undefined || token === '') {
      throw new Error('Feishu tenant access token response did not include tenant_access_token');
    }
    this.tenantAccessToken = token;
    return this.tenantAccessToken;
  }

  private async authHeaders(): Promise<Record<string, string>> {
    return { Authorization: `Bearer ${await this.getTenantAccessToken()}` };
  }

  async getBitableAppToken(): Promise<string> {
    if (this.config.bitableAppToken !== undefined) {
      return this.config.bitableAppToken;
    }
    if (this.bitableAppToken !== null) {
      return this.bitableAppToken;
    }
    if (this.config.wikiNodeToken === undefined) {
      throw new Error('Missing Feishu Bitable app token. Set FEISHU_BITABLE_APP_TOKEN or FEISHU_WIKI_NODE_TOKEN.');
    }

    const query = new URLSearchParams({ token: this.config.wikiNodeToken });
    const data = await this.request<{ node?: { obj_token?: string; obj_type?: string }; obj_token?: string; obj_type?: string }>(
      apiUrl(`/wiki/v2/spaces/get_node?${query}`),
      { method: 'GET', headers: await this.authHeaders() },
    );
    const objToken = data.node?.obj_token ?? data.obj_token;
    const objType = data.node?.obj_type ?? data.obj_type;
    if (objToken === undefined || objToken === '') {
      throw new Error(`Feishu Wiki node did not return a Bitable app token: ${this.config.wikiNodeToken}`);
    }
    if (objType !== undefined && !['bitable', 'base'].includes(objType)) {
      throw new Error(`Feishu Wiki node is not a Bitable document: ${objType}`);
    }

    this.bitableAppToken = objToken;
    return this.bitableAppToken;
  }

  async uploadFile(filePath: string): Promise<FeishuFileToken> {
    const appToken = await this.getBitableAppToken();
    const form = new FormData();
    const bytes = readFileSync(filePath);
    form.append('file_name', basename(filePath));
    form.append('parent_type', 'bitable_file');
    form.append('parent_node', appToken);
    form.append('size', String(bytes.length));
    form.append('file', new Blob([bytes]), basename(filePath));

    const data = await this.request<{ file_token: string }>(apiUrl('/drive/v1/medias/upload_all'), {
      method: 'POST',
      headers: await this.authHeaders(),
      body: form,
    });
    return { fileToken: data.file_token };
  }

  async listFields(): Promise<FeishuField[]> {
    const appToken = await this.getBitableAppToken();
    const fields: FeishuField[] = [];
    const seenPageTokens = new Set<string>();
    let pageToken: string | undefined;
    let hasMore = true;
    while (hasMore) {
      const query = new URLSearchParams({ page_size: '100' });
      if (pageToken !== undefined) {
        query.set('page_token', pageToken);
      }
      const data = await this.request<{ items?: Array<{ field_id: string; field_name: string; type: number; property?: { options?: Array<{ name?: string }> } }>; page_token?: string; has_more?: boolean }>(
        apiUrl(`/bitable/v1/apps/${appToken}/tables/${this.config.tableId}/fields?${query}`),
        { method: 'GET', headers: await this.authHeaders() },
      );
      fields.push(...(data.items ?? []).map((item) => ({
        fieldId: item.field_id,
        fieldName: item.field_name,
        type: item.type,
        options: item.property?.options?.flatMap((option) => option.name === undefined ? [] : [option.name]) ?? [],
      })));
      const nextPageToken = data.page_token;
      hasMore = data.has_more === true && nextPageToken !== undefined && nextPageToken !== '' && !seenPageTokens.has(nextPageToken);
      if (nextPageToken !== undefined && nextPageToken !== '') {
        seenPageTokens.add(nextPageToken);
      }
      pageToken = nextPageToken;
    }
    return fields;
  }

  async createField(definition: FeishuFieldDefinition): Promise<string> {
    const appToken = await this.getBitableAppToken();
    const data = await this.request<{ field: { field_id: string } }>(
      apiUrl(`/bitable/v1/apps/${appToken}/tables/${this.config.tableId}/fields`),
      {
        method: 'POST',
        headers: { ...await this.authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ field_name: definition.fieldName, type: definition.type }),
      },
    );
    return data.field.field_id;
  }

  async ensureFields(definitions: FeishuFieldDefinition[]): Promise<string[]> {
    const fields = await this.listFields();
    const existingNames = new Set(fields.map((field) => field.fieldName));
    const created: string[] = [];

    for (const definition of definitions) {
      if (existingNames.has(definition.fieldName)) {
        continue;
      }
      await this.createField(definition);
      existingNames.add(definition.fieldName);
      created.push(definition.fieldName);
    }

    return created;
  }

  async listRecords(): Promise<FeishuRecord[]> {
    const appToken = await this.getBitableAppToken();
    const records: FeishuRecord[] = [];
    const seenPageTokens = new Set<string>();
    let pageToken: string | undefined;
    let hasMore = true;
    while (hasMore) {
      const query = new URLSearchParams({ page_size: '500' });
      if (pageToken !== undefined) {
        query.set('page_token', pageToken);
      }
      const data = await this.request<{ items?: Array<{ record_id: string; fields: Record<string, unknown> }>; page_token?: string; has_more?: boolean }>(
        apiUrl(`/bitable/v1/apps/${appToken}/tables/${this.config.tableId}/records?${query}`),
        { method: 'GET', headers: await this.authHeaders() },
      );
      records.push(...(data.items ?? []).map((item) => ({ recordId: item.record_id, fields: item.fields })));
      const nextPageToken = data.page_token;
      hasMore = data.has_more === true && nextPageToken !== undefined && nextPageToken !== '' && !seenPageTokens.has(nextPageToken);
      if (nextPageToken !== undefined && nextPageToken !== '') {
        seenPageTokens.add(nextPageToken);
      }
      pageToken = nextPageToken;
    }
    return records;
  }

  async createRecord(fields: Record<string, unknown>): Promise<string> {
    const appToken = await this.getBitableAppToken();
    const data = await this.request<{ record: { record_id: string } }>(
      apiUrl(`/bitable/v1/apps/${appToken}/tables/${this.config.tableId}/records`),
      {
        method: 'POST',
        headers: { ...await this.authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ fields }),
      },
    );
    return data.record.record_id;
  }

  async updateRecord(recordId: string, fields: Record<string, unknown>): Promise<void> {
    const appToken = await this.getBitableAppToken();
    await this.request(
      apiUrl(`/bitable/v1/apps/${appToken}/tables/${this.config.tableId}/records/${recordId}`),
      {
        method: 'PUT',
        headers: { ...await this.authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ fields }),
      },
    );
  }
}

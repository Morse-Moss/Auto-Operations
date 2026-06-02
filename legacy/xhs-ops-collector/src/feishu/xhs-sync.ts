import { existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { DatabaseSync } from 'node:sqlite';

import { initializeSchema } from '../db/schema.js';
import type { XhsMediaArchiveManifestEntry } from '../xhs-media-types.js';
import { loadFeishuConfig, type FeishuConfig } from './config.js';
import { FeishuClient, type FeishuField, type FeishuFieldDefinition } from './client.js';

interface XhsSyncDbRow {
  rank_index: number;
  feed_id: string;
  keyword: string;
  sort_label: string;
  title: string;
  author_name: string | null;
  search_result_url: string;
  explore_url: string | null;
  detail_text: string | null;
  detail_tags_json: string;
  detail_comment_count_text: string | null;
  detail_like_text: string | null;
  detail_collect_text: string | null;
  detail_share_text: string | null;
  note_type: string;
  collected_at: string;
}

const MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024;
const UPLOAD_TIMEOUT_MS = 60_000;

interface XhsFeishuClient {
  listRecords(): Promise<Array<{ recordId: string; fields: Record<string, unknown> }>>;
  uploadFile(filePath: string): Promise<{ fileToken: string }>;
  createRecord(fields: Record<string, unknown>): Promise<string>;
  updateRecord(recordId: string, fields: Record<string, unknown>): Promise<void>;
  ensureFields?(definitions: FeishuFieldDefinition[]): Promise<string[]>;
  listFields?(): Promise<FeishuField[]>;
}

export interface XhsFeishuSyncOptions {
  runId: number;
  dbPath: string;
  manifestPath?: string;
  dryRun: boolean;
  config?: FeishuConfig;
  client?: XhsFeishuClient;
}

export interface XhsFeishuSyncResult {
  runId: number;
  dryRun: boolean;
  rowCount: number;
  created: number;
  updated: number;
  failed: number;
  ensuredFields: number;
  reportPath: string;
}

export const XHS_FEISHU_FIELD_DEFINITIONS: FeishuFieldDefinition[] = [
  { fieldName: 'runId', type: 2 },
  { fieldName: '排名', type: 2 },
  { fieldName: '关键词', type: 1 },
  { fieldName: '排序', type: 1 },
  { fieldName: '笔记ID', type: 1 },
  { fieldName: '标题', type: 1 },
  { fieldName: '作者', type: 1 },
  { fieldName: '笔记类型', type: 1 },
  { fieldName: '点赞数', type: 1 },
  { fieldName: '收藏数', type: 1 },
  { fieldName: '评论数', type: 1 },
  { fieldName: '分享数', type: 1 },
  { fieldName: '正文', type: 1 },
  { fieldName: '标签', type: 1 },
  { fieldName: '原链接', type: 1 },
  { fieldName: '图片附件', type: 17 },
  { fieldName: '视频附件', type: 17 },
  { fieldName: '媒体完整性', type: 1 },
  { fieldName: '本地媒体路径', type: 1 },
  { fieldName: '采集时间', type: 1 },
  { fieldName: '同步错误', type: 1 },
];

function openExistingDatabase(dbPath: string): DatabaseSync {
  if (dbPath !== ':memory:' && !existsSync(dbPath)) {
    throw new Error(`SQLite database not found: ${dbPath}`);
  }
  const db = new DatabaseSync(dbPath);
  db.exec('pragma foreign_keys = ON');
  initializeSchema(db);
  return db;
}

function parseTags(value: string): string {
  try {
    const parsed: unknown = JSON.parse(value);
    return Array.isArray(parsed) ? parsed.join('、') : '';
  } catch {
    return '';
  }
}

function archiveStatusText(entry: XhsMediaArchiveManifestEntry | undefined): string {
  if (entry === undefined) {
    return '部分缺失';
  }
  if (entry.noteType === 'video') {
    if (entry.completeVideoStatus === 'complete' || entry.completeVideoStatus === 'complete_short_mp4_structure_verified') {
      return '完整';
    }
    return '缺失视频';
  }
  return entry.status === 'success' ? '完整' : '缺失图片';
}

function attachmentField(tokens: string[]): Array<{ file_token: string }> {
  return tokens.map((fileToken) => ({ file_token: fileToken }));
}

function urlField(url: string | null | undefined, text: string): { link: string; text: string } | string {
  if (url === undefined || url === null || url === '') {
    return '';
  }
  return { link: url, text: text === '' ? url : text };
}

function dateField(value: string): number | string {
  const normalized = value.includes('T') ? value : value.replace(' ', 'T');
  const timestamp = new Date(normalized).getTime();
  return Number.isNaN(timestamp) ? value : timestamp;
}

function sortSelectText(label: string): string {
  const mapping: Record<string, string> = {
    最新: '按采集时间',
    最多点赞: '按点赞数',
    最多收藏: '按收藏数',
    最多评论: '按评论数',
  };
  return mapping[label] ?? label;
}

function noteTypeText(noteType: string): string {
  if (noteType === 'video') {
    return '视频';
  }
  if (noteType === 'image') {
    return '图文';
  }
  return '其他';
}

function selectOption(value: string, options: string[]): string {
  if (options.length === 0 || options.includes(value)) {
    return value;
  }
  return options.includes('其他') ? '其他' : options[0] ?? value;
}

function adaptFieldValue(field: FeishuField | undefined, value: unknown): unknown {
  if (field === undefined) {
    return value;
  }
  if (field.type === 1 && typeof value === 'object' && value !== null && 'link' in value) {
    return typeof value.link === 'string' ? value.link : '';
  }
  if (field.type === 3 && typeof value === 'string') {
    return selectOption(value, field.options);
  }
  if (field.type === 5 && typeof value === 'string') {
    return dateField(value);
  }
  if (field.type === 15) {
    return typeof value === 'string' ? urlField(value, value) : value;
  }
  return value;
}

function adaptFieldsToFeishuTypes(fields: Record<string, unknown>, fieldByName: Map<string, FeishuField>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(fields).map(([name, value]) => [name, adaptFieldValue(fieldByName.get(name), value)]));
}

function loadManifest(runId: number, manifestPath?: string): XhsMediaArchiveManifestEntry[] {
  const resolvedPath = manifestPath ?? `data/xhs-media/run-${runId}/manifest.json`;
  if (!existsSync(resolvedPath)) {
    throw new Error(`XHS media manifest not found: ${resolvedPath}`);
  }
  const parsed: unknown = JSON.parse(readFileSync(resolvedPath, 'utf8'));
  return Array.isArray(parsed) ? parsed as XhsMediaArchiveManifestEntry[] : [];
}

function readRunRows(db: DatabaseSync, runId: number): XhsSyncDbRow[] {
  return db.prepare(`
    select rank_index, feed_id, keyword, sort_label, title, author_name, search_result_url, explore_url,
           detail_text, detail_tags_json, detail_comment_count_text, detail_like_text, detail_collect_text,
           detail_share_text, note_type, collected_at
    from xhs_search_notes
    where run_id = ?
    order by rank_index, id
  `).all(runId) as unknown as XhsSyncDbRow[];
}

function withTimeout<T>(promise: Promise<T>, ms: number, message: string): Promise<T> {
  let timeout: ReturnType<typeof setTimeout>;
  const timeoutPromise = new Promise<never>((_, reject) => {
    timeout = setTimeout(() => reject(new Error(message)), ms);
  });
  return Promise.race([promise, timeoutPromise]).finally(() => clearTimeout(timeout));
}

function uniqueFiles(files: string[]): string[] {
  return [...new Set(files)];
}

function uploadableVideoFiles(entry: XhsMediaArchiveManifestEntry | undefined): string[] {
  if (entry === undefined) {
    return [];
  }
  if (entry.completeVideoFile !== undefined && entry.completeVideoFile !== null) {
    return [entry.completeVideoFile];
  }
  return entry.videoFiles ?? [];
}

async function uploadExistingFiles(params: {
  client: XhsFeishuClient;
  files: string[];
  label: string;
  feedId: string;
  maxBytes?: number;
}): Promise<{ tokens: string[]; errors: string[] }> {
  const tokens: string[] = [];
  const errors: string[] = [];
  for (const file of uniqueFiles(params.files)) {
    if (!existsSync(file)) {
      errors.push(`missing file: ${file}`);
      continue;
    }
    const bytes = statSync(file).size;
    if (params.maxBytes !== undefined && bytes > params.maxBytes) {
      errors.push(`skip oversized ${params.label}: ${file} ${bytes} bytes > ${params.maxBytes} bytes`);
      continue;
    }
    try {
      console.error(`[feishu-sync] upload ${params.label} feed=${params.feedId} bytes=${bytes} file=${file}`);
      const uploaded = await withTimeout(
        params.client.uploadFile(file),
        UPLOAD_TIMEOUT_MS,
        `upload timeout after ${UPLOAD_TIMEOUT_MS}ms: ${file}`,
      );
      tokens.push(uploaded.fileToken);
    } catch (error) {
      errors.push(`upload failed: ${file} ${error instanceof Error ? error.message : String(error)}`);
    }
  }
  return { tokens, errors };
}

function buildFields(params: {
  runId: number;
  row: XhsSyncDbRow;
  archive: XhsMediaArchiveManifestEntry | undefined;
  imageTokens: string[];
  videoTokens: string[];
  uploadErrors: string[];
  fieldByName: Map<string, FeishuField>;
}): Record<string, unknown> {
  const localFiles = [
    ...(params.archive?.imageFiles ?? []),
    ...(params.archive?.videoFiles ?? []),
  ];
  const sourceUrl = params.row.explore_url ?? params.row.search_result_url;
  const fields = {
    runId: params.runId,
    排名: params.row.rank_index,
    关键词: params.row.keyword,
    排序: sortSelectText(params.row.sort_label),
    笔记ID: params.row.feed_id,
    标题: params.row.title,
    作者: params.row.author_name ?? '',
    笔记类型: noteTypeText(params.row.note_type),
    点赞数: params.row.detail_like_text ?? '',
    收藏数: params.row.detail_collect_text ?? '',
    评论数: params.row.detail_comment_count_text ?? '',
    分享数: params.row.detail_share_text ?? '',
    正文: params.row.detail_text ?? '',
    标签: parseTags(params.row.detail_tags_json),
    原链接: urlField(sourceUrl, params.row.title),
    图片附件: attachmentField(params.imageTokens),
    视频附件: attachmentField(params.videoTokens),
    媒体完整性: archiveStatusText(params.archive),
    本地媒体路径: localFiles.join('\n'),
    采集时间: params.row.collected_at,
    同步错误: params.uploadErrors.join('\n'),
  };
  return adaptFieldsToFeishuTypes(fields, params.fieldByName);
}

function createClient(options: XhsFeishuSyncOptions): XhsFeishuClient {
  return options.client ?? new FeishuClient(options.config ?? loadFeishuConfig());
}

export async function syncXhsRunToFeishu(options: XhsFeishuSyncOptions): Promise<XhsFeishuSyncResult> {
  const db = openExistingDatabase(options.dbPath);
  const reportDir = join('data/feishu-sync', `run-${options.runId}`);
  mkdirSync(reportDir, { recursive: true });
  const reportPath = join(reportDir, 'sync-report.json');
  try {
    const rows = readRunRows(db, options.runId);
    const manifest = loadManifest(options.runId, options.manifestPath);
    const archiveByFeedId = new Map(manifest.map((entry) => [entry.feedId, entry]));
    const client = options.dryRun ? options.client : createClient(options);
    console.error(`[feishu-sync] loaded rows=${rows.length} manifest=${manifest.length} dryRun=${options.dryRun}`);
    const ensuredFields = !options.dryRun && client?.ensureFields !== undefined
      ? await client.ensureFields(XHS_FEISHU_FIELD_DEFINITIONS)
      : [];
    console.error(`[feishu-sync] ensured fields=${ensuredFields.length}`);
    const feishuFields = !options.dryRun && client?.listFields !== undefined ? await client.listFields() : [];
    console.error(`[feishu-sync] field metadata=${feishuFields.length}`);
    const fieldByName = new Map(feishuFields.map((field) => [field.fieldName, field]));
    const existing = options.dryRun ? [] : await client!.listRecords();
    console.error(`[feishu-sync] existing records=${existing.length}`);
    const recordByFeedId = new Map(existing.flatMap((record) => {
      const feedId = record.fields.笔记ID;
      return typeof feedId === 'string' ? [[feedId, record.recordId] as const] : [];
    }));
    let created = 0;
    let updated = 0;
    let failed = 0;
    const records = [];

    for (const row of rows) {
      const archive = archiveByFeedId.get(row.feed_id);
      try {
        console.error(`[feishu-sync] row ${records.length + 1}/${rows.length} feed=${row.feed_id} title=${row.title}`);
        const imageUpload = options.dryRun
          ? { tokens: [], errors: [] }
          : await uploadExistingFiles({ client: client!, files: archive?.imageFiles ?? [], label: 'image', feedId: row.feed_id });
        const videoUpload = options.dryRun
          ? { tokens: [], errors: [] }
          : await uploadExistingFiles({ client: client!, files: uploadableVideoFiles(archive), label: 'video', feedId: row.feed_id, maxBytes: MAX_ATTACHMENT_BYTES });
        const fields = buildFields({
          runId: options.runId,
          row,
          archive,
          imageTokens: imageUpload.tokens,
          videoTokens: videoUpload.tokens,
          uploadErrors: [...imageUpload.errors, ...videoUpload.errors],
          fieldByName,
        });
        if (!options.dryRun) {
          const recordId = recordByFeedId.get(row.feed_id);
          if (recordId === undefined) {
            await client!.createRecord(fields);
            created += 1;
          } else {
            await client!.updateRecord(recordId, fields);
            updated += 1;
          }
        }
        records.push({ feedId: row.feed_id, title: row.title, status: options.dryRun ? 'dry_run' : 'success', fields });
      } catch (error) {
        failed += 1;
        records.push({ feedId: row.feed_id, title: row.title, status: 'failed', error: error instanceof Error ? error.message : String(error) });
      }
    }

    const result = { runId: options.runId, dryRun: options.dryRun, rowCount: rows.length, created, updated, failed, ensuredFields: ensuredFields.length, reportPath };
    writeFileSync(reportPath, JSON.stringify({ ...result, ensuredFields, records }, null, 2), 'utf8');
    return result;
  } finally {
    db.close();
  }
}

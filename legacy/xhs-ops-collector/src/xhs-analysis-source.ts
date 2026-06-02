import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { DatabaseSync } from 'node:sqlite';

import {
  XhsAnalysisSourceContractVersion,
  type XhsAnalysisSourceOptions,
  type XhsAnalysisSourceResult,
} from './xhs-analysis-source-types.js';

interface XhsSearchRunRow {
  id: number;
  source: string;
  source_run_id: number | null;
  keyword: string;
  sorts_json: string;
  limit_per_sort: number;
  with_details: number;
  status: string;
  started_at: string;
  finished_at: string | null;
}

interface XhsSearchNoteRow {
  keyword: string;
  sort_key: string;
  sort_label: string;
  rank_index: number;
  feed_id: string;
  xsec_token: string | null;
  search_result_url: string;
  explore_url: string | null;
  title: string;
  author_name: string | null;
  detail_text: string | null;
  raw_detail_text: string | null;
  analysis_source_text: string | null;
  detail_tags_json: string;
  detail_like_text: string | null;
  detail_collect_text: string | null;
  detail_comment_count_text: string | null;
  detail_share_text: string | null;
  note_type: string;
  source_topic_texts_json: string;
  source_comments_json: string;
  media_sources_json: string;
  raw_card_text: string;
  collected_at: string;
}

interface ManifestEntry {
  feedId: string;
  status?: string;
  imageFiles?: string[];
  videoFiles?: string[];
  completeVideoFile?: string | null;
  completeVideoStatus?: string | null;
  sourceMediaUrls?: string[];
}

interface SyncRecord {
  feedId?: string;
  status?: string;
  fields?: Record<string, unknown>;
}

interface SyncReport {
  records?: SyncRecord[];
}

interface PipelineCheck {
  status?: string;
  agent?: {
    ready?: boolean;
  };
  warnings?: unknown;
}

interface SourceWarning {
  code: string;
  message: string;
}

function defaultManifestPath(runId: number): string {
  return `data/xhs-media/run-${runId}/manifest.json`;
}

function defaultSyncReportPath(runId: number): string {
  return `data/feishu-sync/run-${runId}/sync-report.json`;
}

function defaultPipelineCheckPath(runId: number): string {
  return `data/xhs-pipeline-check/run-${runId}/check.json`;
}

function defaultOutputDir(runId: number): string {
  return `data/xhs-analysis-source/run-${runId}`;
}

function parseJsonArray(
  value: string | null | undefined,
  context: { field: string; feedId: string },
  warnings: SourceWarning[],
): unknown[] {
  if (value === undefined || value === null || value.trim() === '') {
    return [];
  }

  try {
    const parsed = JSON.parse(value) as unknown;
    if (Array.isArray(parsed)) {
      return parsed;
    }
  } catch {
    // Fall through to a warning and empty array.
  }

  warnings.push(warning(
    'invalid_json_field',
    `Invalid JSON array in ${context.field} for feedId ${context.feedId}`,
  ));
  return [];
}

function readJson<T>(path: string, fallback: T, warnings: SourceWarning[]): T {
  try {
    return JSON.parse(readFileSync(path, 'utf8')) as T;
  } catch {
    warnings.push(warning('invalid_json_file', `Invalid JSON file: ${path}`));
    return fallback;
  }
}

function warning(code: string, message: string): SourceWarning {
  return { code, message };
}

function indexManifest(entries: ManifestEntry[]): Map<string, ManifestEntry> {
  return new Map(entries.map((entry) => [entry.feedId, entry]));
}

function syncRecordFeedId(record: SyncRecord): string | undefined {
  if (record.feedId !== undefined) {
    return record.feedId;
  }
  const fieldsFeedId = record.fields?.笔记ID;
  return typeof fieldsFeedId === 'string' ? fieldsFeedId : undefined;
}

function indexSyncRecords(records: SyncRecord[]): Map<string, SyncRecord> {
  return new Map(records.flatMap((record) => {
    const feedId = syncRecordFeedId(record);
    return feedId === undefined ? [] : [[feedId, record]];
  }));
}

export function buildXhsAnalysisSource(options: XhsAnalysisSourceOptions): XhsAnalysisSourceResult {
  const manifestPath = options.manifestPath ?? defaultManifestPath(options.runId);
  const syncReportPath = options.syncReportPath ?? defaultSyncReportPath(options.runId);
  const pipelineCheckPath = options.pipelineCheckPath ?? defaultPipelineCheckPath(options.runId);
  const outputDir = options.outputDir ?? defaultOutputDir(options.runId);
  const sourceJson = `${outputDir}/source.json`;
  const notesJsonl = `${outputDir}/notes.jsonl`;

  const warnings: SourceWarning[] = [];

  const manifestEntries = existsSync(manifestPath)
    ? readJson<ManifestEntry[]>(manifestPath, [], warnings)
    : [];
  if (!existsSync(manifestPath)) {
    warnings.push(warning('manifest_missing', `Manifest file not found: ${manifestPath}`));
  }
  const manifestByFeedId = indexManifest(manifestEntries);

  const syncRecords = existsSync(syncReportPath)
    ? (readJson<SyncReport>(syncReportPath, { records: [] }, warnings).records ?? [])
    : [];
  if (!existsSync(syncReportPath)) {
    warnings.push(warning('sync_report_missing', `Sync report file not found: ${syncReportPath}`));
  }
  const syncByFeedId = indexSyncRecords(syncRecords);

  const pipelineWarning = warning('pipeline_check_missing', `Pipeline check file not found: ${pipelineCheckPath}`);
  const pipelineCheck = existsSync(pipelineCheckPath)
    ? readJson<PipelineCheck>(pipelineCheckPath, { status: 'unknown', agent: { ready: false } }, warnings)
    : undefined;
  const pipeline = pipelineCheck === undefined
    ? { status: 'unknown', agentReady: false, warnings: [pipelineWarning] }
    : {
      status: pipelineCheck.status ?? 'unknown',
      agentReady: pipelineCheck.agent?.ready ?? false,
      warnings: Array.isArray(pipelineCheck.warnings) ? pipelineCheck.warnings : [],
    };
  if (!existsSync(pipelineCheckPath)) {
    warnings.push(pipelineWarning);
  }
  const db = new DatabaseSync(options.dbPath, { readOnly: true });

  try {
    const run = db.prepare(`
      select id, source, source_run_id, keyword, sorts_json, limit_per_sort, with_details,
        status, started_at, finished_at
      from xhs_search_runs
      where id = ?
    `).get(options.runId) as XhsSearchRunRow | undefined;

    if (run === undefined) {
      throw new Error(`XHS search run ${options.runId} not found`);
    }

    const rows = db.prepare(`
      select keyword, sort_key, sort_label, rank_index, feed_id, xsec_token, search_result_url,
        explore_url, title, author_name, detail_text, raw_detail_text, analysis_source_text,
        detail_tags_json, detail_like_text, detail_collect_text, detail_comment_count_text,
        detail_share_text, note_type, source_topic_texts_json, source_comments_json,
        media_sources_json, raw_card_text, collected_at
      from xhs_search_notes
      where run_id = ?
      order by sort_key, rank_index, id
    `).all(options.runId) as unknown as XhsSearchNoteRow[];

    if (rows.length === 0) {
      throw new Error(`XHS search run ${options.runId} has zero notes`);
    }

    const notes = rows.map((row) => {
      const manifest = manifestByFeedId.get(row.feed_id);
      const syncRecord = syncByFeedId.get(row.feed_id);
      const tags = parseJsonArray(row.detail_tags_json, { field: 'detail_tags_json', feedId: row.feed_id }, warnings);
      const topics = parseJsonArray(row.source_topic_texts_json, { field: 'source_topic_texts_json', feedId: row.feed_id }, warnings);
      const comments = parseJsonArray(row.source_comments_json, { field: 'source_comments_json', feedId: row.feed_id }, warnings);
      const mediaSources = parseJsonArray(row.media_sources_json, { field: 'media_sources_json', feedId: row.feed_id }, warnings);
      const localImages = manifest?.imageFiles ?? [];
      const localVideos = manifest?.videoFiles ?? [];
      const completeVideoFile = manifest?.completeVideoFile ?? null;
      const hasFeishuSyncWarning = syncRecord?.status !== 'success';

      return {
        contractVersion: XhsAnalysisSourceContractVersion,
        runId: options.runId,
        keyword: row.keyword,
        sort: {
          key: row.sort_key,
          label: row.sort_label,
          rankIndex: row.rank_index,
        },
        feedId: row.feed_id,
        xsecToken: row.xsec_token,
        urls: {
          searchResult: row.search_result_url,
          explore: row.explore_url,
        },
        title: row.title,
        author: {
          name: row.author_name,
        },
        content: {
          detailText: row.detail_text,
          rawDetailText: row.raw_detail_text,
          analysisSourceText: row.analysis_source_text,
          rawCardText: row.raw_card_text,
        },
        metrics: {
          likes: row.detail_like_text,
          collects: row.detail_collect_text,
          comments: row.detail_comment_count_text,
          shares: row.detail_share_text,
        },
        tags,
        topics,
        comments,
        mediaSources,
        media: {
          status: manifest?.status ?? null,
          localImages,
          localVideos,
          completeVideoFile,
          completeVideoStatus: manifest?.completeVideoStatus ?? null,
          sourceMediaUrls: manifest?.sourceMediaUrls ?? [],
        },
        feishu: {
          synced: syncRecord?.status === 'success',
          status: syncRecord?.status ?? null,
          fields: syncRecord?.fields ?? {},
        },
        noteType: row.note_type,
        collectedAt: row.collected_at,
        quality: {
          hasDetail: row.detail_text !== null && row.detail_text.trim() !== '',
          hasTags: tags.length > 0,
          hasComments: comments.length > 0,
          hasMediaSource: mediaSources.length > 0,
          hasLocalMedia: localImages.length > 0 || localVideos.length > 0 || (completeVideoFile !== null && completeVideoFile.trim() !== ''),
          hasFeishuSyncWarning,
        },
      };
    });

    const source = {
      contractVersion: XhsAnalysisSourceContractVersion,
      runId: options.runId,
      generatedAt: new Date().toISOString(),
      inputs: {
        dbPath: options.dbPath,
        manifestPath,
        syncReportPath,
        pipelineCheckPath,
      },
      files: {
        notesJsonl,
      },
      run,
      pipeline,
      warnings,
      counts: {
        notes: notes.length,
      },
    };

    mkdirSync(outputDir, { recursive: true });
    writeFileSync(sourceJson, JSON.stringify(source, null, 2), 'utf8');
    writeFileSync(notesJsonl, notes.map((note) => JSON.stringify(note)).join('\n') + (notes.length > 0 ? '\n' : ''), 'utf8');

    return {
      contractVersion: XhsAnalysisSourceContractVersion,
      runId: options.runId,
      files: {
        sourceJson,
        notesJsonl,
      },
      counts: {
        notes: notes.length,
      },
    };
  } finally {
    db.close();
  }
}

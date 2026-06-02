import { existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { DatabaseSync } from 'node:sqlite';

import type { XhsMediaArchiveManifestEntry } from './xhs-media-types.js';
import type { XhsPipelineCheckOptions, XhsPipelineCheckResult } from './xhs-pipeline-check-types.js';

function defaultManifestPath(runId: number): string {
  return `data/xhs-media/run-${runId}/manifest.json`;
}

function defaultSyncReportPath(runId: number): string {
  return `data/feishu-sync/run-${runId}/sync-report.json`;
}

function defaultOutputDir(runId: number): string {
  return `data/xhs-pipeline-check/run-${runId}`;
}

function parseJsonArray(value: string | null | undefined): unknown[] {
  if (value === null || value === undefined || value.trim() === '') {
    return [];
  }

  try {
    const parsed = JSON.parse(value) as unknown;
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function loadManifest(path: string): XhsMediaArchiveManifestEntry[] {
  if (!existsSync(path)) {
    return [];
  }
  const parsed = JSON.parse(readFileSync(path, 'utf8')) as unknown;
  return Array.isArray(parsed) ? parsed as XhsMediaArchiveManifestEntry[] : [];
}

function loadSyncReport(path: string): { rowCount?: number; failed?: number; records?: Array<{ status?: string; fields?: Record<string, unknown> }> } | undefined {
  if (!existsSync(path)) {
    return undefined;
  }
  return JSON.parse(readFileSync(path, 'utf8')) as { rowCount?: number; failed?: number; records?: Array<{ status?: string; fields?: Record<string, unknown> }> };
}

function fileSize(file: string): number | null {
  const candidates = [file, resolve(file)];
  for (const candidate of candidates) {
    try {
      if (existsSync(candidate)) {
        return statSync(candidate).size;
      }
    } catch {
      return null;
    }
  }
  return null;
}

function fileNonEmpty(file: string): boolean {
  const size = fileSize(file);
  return size !== null && size > 0;
}

function invalidManifestMediaFiles(entry: XhsMediaArchiveManifestEntry): string[] {
  const files = new Set<string>();
  for (const file of [...entry.imageFiles, ...entry.videoFiles]) {
    if (file.trim() !== '') {
      files.add(file);
    }
  }
  if (typeof entry.completeVideoFile === 'string' && entry.completeVideoFile.trim() !== '') {
    files.add(entry.completeVideoFile);
  }
  return [...files].filter((file) => !fileNonEmpty(file));
}

function isCompleteVideoStatus(status: XhsMediaArchiveManifestEntry['completeVideoStatus']): boolean {
  return status === 'complete' || status === 'complete_short_mp4_structure_verified';
}

function hasCompleteVideoEvidence(entry: XhsMediaArchiveManifestEntry): boolean {
  if (!isCompleteVideoStatus(entry.completeVideoStatus) || typeof entry.completeVideoFile !== 'string' || entry.completeVideoFile.trim() === '') {
    return false;
  }
  const size = fileSize(entry.completeVideoFile);
  if (size === null || size <= 0) {
    return false;
  }
  return typeof entry.completeVideoBytes === 'number' && entry.completeVideoBytes > 0 ? size === entry.completeVideoBytes : true;
}

function hasNonEmptySavedMediaFile(entry: XhsMediaArchiveManifestEntry): boolean {
  return [...entry.imageFiles, ...entry.videoFiles].some((file) => file.trim() !== '' && fileNonEmpty(file));
}

function isSuccessfulCompleteManifestEntry(entry: XhsMediaArchiveManifestEntry): boolean {
  if (invalidManifestMediaFiles(entry).length > 0) {
    return false;
  }
  if (entry.noteType === 'video') {
    return hasCompleteVideoEvidence(entry);
  }
  return entry.status === 'success' && hasNonEmptySavedMediaFile(entry);
}

function isIncompleteManifestEntry(entry: XhsMediaArchiveManifestEntry): boolean {
  if (invalidManifestMediaFiles(entry).length > 0) {
    return true;
  }
  if (entry.noteType === 'video') {
    return !hasCompleteVideoEvidence(entry);
  }
  return entry.status === 'no_media_saved' || entry.status === 'partial_failed' || !hasNonEmptySavedMediaFile(entry);
}

function renderMarkdown(result: XhsPipelineCheckResult): string {
  const issueLines = result.blockingIssues.length === 0
    ? '- 无阻断问题'
    : result.blockingIssues.map((issue) => `- ${issue.code}: ${issue.message}`).join('\n');
  const warningLines = result.warnings.length === 0
    ? '- 无警告'
    : result.warnings.map((warning) => `- ${warning.code}: ${warning.message}`).join('\n');

  return [
    '# 小红书采集入库检查报告',
    '',
    `Run ID: ${result.runId}`,
    `状态: ${result.status}`,
    '',
    '## 数据库',
    `- 笔记数: ${result.counts.notes}`,
    `- 详情数: ${result.counts.details}`,
    `- 标签数: ${result.counts.tags}`,
    `- 媒体源数: ${result.counts.mediaSources}`,
    '',
    '## 媒体归档',
    `- manifest 记录数: ${result.counts.manifestEntries}`,
    `- 与数据库匹配 feed 数: ${result.counts.manifestMatchedFeeds}`,
    `- 完整成功媒体记录数: ${result.counts.manifestSuccessfulCompleteEntries}`,
    `- 不完整媒体记录数: ${result.counts.manifestIncompleteEntries}`,
    `- 不完整视频数: ${result.counts.incompleteVideos}`,
    `- 数据库有笔记但 manifest 缺失数: ${result.counts.manifestMissingFeeds}`,
    '',
    '## 飞书同步',
    `- 同步记录数: ${result.counts.feishuSyncedRecords}`,
    '',
    '## 阻断问题',
    issueLines,
    '',
    '## 警告',
    warningLines,
    '',
    '## 下游接口',
    `- Agent ready: ${result.agent.ready}`,
    `- Input contract: ${result.agent.inputContractVersion}`,
    '',
  ].join('\n');
}

export function checkXhsPipeline(options: XhsPipelineCheckOptions): XhsPipelineCheckResult {
  const manifestPath = options.manifestPath ?? defaultManifestPath(options.runId);
  const syncReportPath = options.syncReportPath ?? defaultSyncReportPath(options.runId);
  const outputDir = options.outputDir ?? defaultOutputDir(options.runId);
  const jsonPath = `${outputDir}/check.json`;
  const markdownPath = `${outputDir}/check.md`;
  const db = new DatabaseSync(options.dbPath, { readOnly: true });

  try {
    const run = db.prepare('select id from xhs_search_runs where id = ?').get(options.runId) as { id: number } | undefined;
    const rows = db.prepare(`
      select feed_id, detail_text, raw_detail_text, detail_tags_json, media_sources_json
      from xhs_search_notes
      where run_id = ?
    `).all(options.runId) as Array<{
      feed_id: string;
      detail_text: string | null;
      raw_detail_text: string | null;
      detail_tags_json: string | null;
      media_sources_json: string | null;
    }>;
    const notes = rows.length;
    const details = rows.filter((row) => (row.detail_text?.trim() || row.raw_detail_text?.trim())).length;
    const tags = rows.filter((row) => parseJsonArray(row.detail_tags_json).length > 0).length;
    const mediaSources = rows.filter((row) => parseJsonArray(row.media_sources_json).length > 0).length;
    const manifest = loadManifest(manifestPath);
    const noteFeedIds = new Set(rows.map((row) => row.feed_id));
    const manifestFeedIds = new Set(manifest.map((entry) => entry.feedId));
    const matchedManifest = manifest.filter((entry) => noteFeedIds.has(entry.feedId));
    const manifestMatchedFeeds = matchedManifest.length;
    const manifestSuccessfulCompleteEntries = matchedManifest.filter((entry) => isSuccessfulCompleteManifestEntry(entry)).length;
    const manifestIncompleteEntries = matchedManifest.filter((entry) => isIncompleteManifestEntry(entry)).length;
    const incompleteVideos = matchedManifest.filter((entry) => entry.noteType === 'video' && !hasCompleteVideoEvidence(entry)).length;
    const invalidManifestFiles = matchedManifest.flatMap((entry) => invalidManifestMediaFiles(entry).map((file) => ({ feedId: entry.feedId, file })));
    const manifestMissingFeeds = rows.filter((row) => !manifestFeedIds.has(row.feed_id)).length;
    const syncReport = loadSyncReport(syncReportPath);
    const feishuSyncedRecords = syncReport?.rowCount ?? syncReport?.records?.length ?? 0;
    const warnings = [];
    if (run !== undefined && notes > 0 && !existsSync(manifestPath)) {
      warnings.push({ code: 'manifest_missing', message: `Media manifest not found: ${manifestPath}` });
    }
    if (run !== undefined && notes > 0 && syncReport === undefined) {
      warnings.push({ code: 'sync_report_missing', message: `Feishu sync report not found: ${syncReportPath}` });
    }
    if (run !== undefined && notes > 0 && manifestMissingFeeds > 0) {
      warnings.push({ code: 'media_missing_for_notes', message: `Media manifest is missing ${manifestMissingFeeds} database note feed(s).` });
    }
    if (run !== undefined && invalidManifestFiles.length > 0) {
      const sample = invalidManifestFiles.slice(0, 3).map((item) => `${item.feedId}: ${item.file}`).join('; ');
      warnings.push({
        code: 'manifest_media_file_invalid',
        message: `Media manifest references ${invalidManifestFiles.length} missing or empty local file(s).${sample === '' ? '' : ` Examples: ${sample}`}`,
      });
    }
    if (run !== undefined && manifestIncompleteEntries > 0) {
      warnings.push({ code: 'media_incomplete', message: `Media manifest has ${manifestIncompleteEntries} incomplete entry/entries.` });
    }
    if (run !== undefined && notes > 0 && manifestMatchedFeeds > 0 && manifestSuccessfulCompleteEntries < notes) {
      warnings.push({ code: 'media_success_less_than_notes', message: `Successful complete media entries ${manifestSuccessfulCompleteEntries} are less than database notes ${notes}.` });
    }
    for (const record of syncReport?.records ?? []) {
      const syncError = record.fields?.同步错误;
      if (typeof syncError === 'string' && syncError.trim() !== '') {
        warnings.push({
          code: syncError.includes('oversized video') ? 'oversized_video_skipped' : 'feishu_sync_warning',
          message: syncError,
        });
      }
    }
    const blockingIssues = run === undefined
      ? [{ code: 'run_missing', message: `XHS search run #${options.runId} does not exist.` }]
      : [];
    if (run !== undefined && notes === 0) {
      blockingIssues.push({ code: 'notes_empty', message: `XHS search run #${options.runId} has no collected notes.` });
    }

    const result: XhsPipelineCheckResult = {
      runId: options.runId,
      status: blockingIssues.length > 0 ? 'failed' : warnings.length > 0 ? 'partial' : 'complete',
      blockingIssues,
      warnings,
      paths: {
        dbPath: options.dbPath,
        manifestPath,
        syncReportPath,
        outputDir,
        jsonPath,
        markdownPath,
      },
      counts: {
        notes,
        details,
        tags,
        mediaSources,
        manifestEntries: manifest.length,
        manifestMatchedFeeds,
        manifestSuccessfulCompleteEntries,
        manifestIncompleteEntries,
        incompleteVideos,
        manifestMissingFeeds,
        feishuSyncedRecords,
      },
      agent: {
        ready: blockingIssues.length === 0,
        inputContractVersion: 'xhs-analysis-source/v1',
        recommendedInput: {
          dbPath: options.dbPath,
          runId: options.runId,
          manifestPath,
          syncReportPath,
        },
      },
    };

    mkdirSync(outputDir, { recursive: true });
    writeFileSync(jsonPath, JSON.stringify(result, null, 2), 'utf8');
    writeFileSync(markdownPath, renderMarkdown(result), 'utf8');
    return result;
  } finally {
    db.close();
  }
}

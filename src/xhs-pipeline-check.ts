import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
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
    const manifestMatchedFeeds = manifest.filter((entry) => noteFeedIds.has(entry.feedId)).length;
    const syncReport = loadSyncReport(syncReportPath);
    const feishuSyncedRecords = syncReport?.rowCount ?? syncReport?.records?.length ?? 0;
    const warnings = [];
    if (run !== undefined && notes > 0 && !existsSync(manifestPath)) {
      warnings.push({ code: 'manifest_missing', message: `Media manifest not found: ${manifestPath}` });
    }
    if (run !== undefined && notes > 0 && syncReport === undefined) {
      warnings.push({ code: 'sync_report_missing', message: `Feishu sync report not found: ${syncReportPath}` });
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

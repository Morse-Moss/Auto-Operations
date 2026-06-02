# XHS Pre-analysis Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one `xhs-preanalysis-run` command that starts from Huitun, runs the full pre-analysis chain through Feishu sync, and writes a clear status report plus analysis-source artifacts.

**Architecture:** Add a thin orchestrator module with dependency injection. It reuses existing collection, media archive, Feishu sync, pipeline check, and analysis-source modules instead of duplicating their logic. The CLI wires real dependencies; unit tests pass fake dependencies so failure/recovery behavior is deterministic and does not launch browsers or call Feishu.

**Tech Stack:** Node.js, TypeScript, Commander, Vitest, local filesystem artifacts, existing SQLite-backed collector modules.

---

## Commit Policy Note

This plan intentionally omits mandatory commit steps. The active Claude Code harness instruction says to commit only when the user asks. If the user later asks to commit, use an English commit message and include the required Claude co-author trailer.

## File Structure

- Create: `src/xhs-preanalysis-run-types.ts`
  - Owns options, dependency signatures, stage records, result shape, and status vocabulary.
- Create: `src/xhs-preanalysis-run.ts`
  - Owns orchestration, status aggregation, recovery command generation, and `status.json` / `status.md` writing.
  - Does not scrape, parse DOM, upload to Feishu directly, or merge analysis-source data.
- Modify: `src/cli.ts`
  - Adds `xhs-preanalysis-run` parser, help, command option type, and `main()` dispatch that wires real dependencies.
- Create: `tests/xhs-preanalysis-run.test.ts`
  - Unit tests orchestration using fake dependencies only.
- Modify: `tests/cli-options.test.ts`
  - Adds parser/help tests for `xhs-preanalysis-run`.
- Existing spec: `docs/superpowers/specs/2026-06-01-xhs-preanalysis-run-design.md`
  - Source of truth for scope and verification.

## Task 1: Core success path and status artifacts

**Files:**
- Create: `tests/xhs-preanalysis-run.test.ts`
- Create: `src/xhs-preanalysis-run-types.ts`
- Create: `src/xhs-preanalysis-run.ts`

- [ ] **Step 1: Write the failing success-path test**

Create `tests/xhs-preanalysis-run.test.ts` with this initial content:

```ts
import { existsSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { runXhsPreanalysisRun } from '../src/xhs-preanalysis-run.js';
import type {
  XhsPreanalysisRunDependencies,
  XhsPreanalysisRunOptions,
} from '../src/xhs-preanalysis-run-types.js';

let tempDir: string | undefined;

function createTempDir(): string {
  tempDir = mkdtempSync(join(tmpdir(), 'xhs-preanalysis-run-test-'));
  return tempDir;
}

function baseOptions(outputDir: string): XhsPreanalysisRunOptions {
  return {
    orchestrationId: 'test-run',
    keyword: '浴缸',
    dbPath: 'data/test.sqlite',
    huitunCdpUrl: 'http://127.0.0.1:9222',
    xhsCdpUrl: 'http://127.0.0.1:9222',
    mediaCdpUrl: 'http://127.0.0.1:17330',
    limitHotwords: 5,
    limitNotes: 20,
    days: 7,
    xhsLimitKeywords: 5,
    xhsSorts: ['latest', 'most_liked'],
    xhsLimitPerSort: 20,
    withDetails: true,
    detailBudget: 30,
    detailDelayMinMs: 20_000,
    detailDelayMaxMs: 60_000,
    stopOnRateLimit: true,
    resumeMissingDetails: true,
    mediaDelayMinMs: 8_000,
    mediaDelayMaxMs: 15_000,
    feishuDryRun: false,
    outputDir,
  };
}

interface FakeCalls {
  collectHuitun: unknown[];
  collectXhsSearch: unknown[];
  archiveXhsRunMedia: unknown[];
  syncXhsRunToFeishu: unknown[];
  checkXhsPipeline: unknown[];
  buildXhsAnalysisSource: unknown[];
}

function createFakeDependencies(calls: FakeCalls): XhsPreanalysisRunDependencies {
  return {
    now: () => '2026-06-01T10:00:00.000Z',
    collectHuitun: async (options) => {
      calls.collectHuitun.push(options);
      return {
        runId: 12,
        status: 'success',
        hotWordCount: 5,
        noteCount: 20,
        detailCount: 10,
        dbPath: options.dbPath,
        qualityReport: { runId: 12 },
      };
    },
    collectXhsSearch: async (options) => {
      calls.collectXhsSearch.push(options);
      return {
        runs: [{ runId: 32, keyword: '浴缸', status: 'success', noteCount: 20 }],
        dbPath: options.dbPath,
        detailBudgetUsed: 3,
        rateLimited: false,
      };
    },
    archiveXhsRunMedia: async (options) => {
      calls.archiveXhsRunMedia.push(options);
      return {
        runId: options.runId,
        rows: 20,
        success: 20,
        noMediaSaved: 0,
        imageFiles: 20,
        videoFiles: 2,
        completeVideos: 2,
        incompleteVideos: 0,
        root: `data/xhs-media/run-${options.runId}`,
        csv: `data/xhs-media/run-${options.runId}/小红书_run${options.runId}_本地媒体_UTF8BOM.csv`,
        safetyStopped: false,
        manifest: `data/xhs-media/run-${options.runId}/manifest.json`,
      };
    },
    syncXhsRunToFeishu: async (options) => {
      calls.syncXhsRunToFeishu.push(options);
      return {
        runId: options.runId,
        dryRun: options.dryRun,
        rowCount: 20,
        created: 20,
        updated: 0,
        failed: 0,
        ensuredFields: 0,
        reportPath: `data/feishu-sync/run-${options.runId}/sync-report.json`,
      };
    },
    checkXhsPipeline: (options) => {
      calls.checkXhsPipeline.push(options);
      return {
        runId: options.runId,
        status: 'complete',
        blockingIssues: [],
        warnings: [],
        paths: {
          dbPath: options.dbPath,
          manifestPath: options.manifestPath ?? `data/xhs-media/run-${options.runId}/manifest.json`,
          syncReportPath: options.syncReportPath ?? `data/feishu-sync/run-${options.runId}/sync-report.json`,
          outputDir: options.outputDir ?? `data/xhs-pipeline-check/run-${options.runId}`,
          jsonPath: `data/xhs-pipeline-check/run-${options.runId}/check.json`,
          markdownPath: `data/xhs-pipeline-check/run-${options.runId}/check.md`,
        },
        counts: {
          notes: 20,
          details: 20,
          tags: 20,
          mediaSources: 20,
          manifestEntries: 20,
          manifestMatchedFeeds: 20,
          manifestSuccessfulCompleteEntries: 20,
          manifestIncompleteEntries: 0,
          incompleteVideos: 0,
          manifestMissingFeeds: 0,
          feishuSyncedRecords: 20,
        },
        agent: {
          ready: true,
          inputContractVersion: 'xhs-analysis-source/v1',
          recommendedInput: {
            dbPath: options.dbPath,
            runId: options.runId,
            manifestPath: options.manifestPath ?? `data/xhs-media/run-${options.runId}/manifest.json`,
            syncReportPath: options.syncReportPath ?? `data/feishu-sync/run-${options.runId}/sync-report.json`,
          },
        },
      };
    },
    buildXhsAnalysisSource: (options) => {
      calls.buildXhsAnalysisSource.push(options);
      return {
        contractVersion: 'xhs-analysis-source/v1',
        runId: options.runId,
        files: {
          sourceJson: `data/xhs-analysis-source/run-${options.runId}/source.json`,
          notesJsonl: `data/xhs-analysis-source/run-${options.runId}/notes.jsonl`,
        },
        counts: { notes: 20 },
      };
    },
  };
}

describe('XHS pre-analysis run orchestration', () => {
  afterEach(() => {
    if (tempDir !== undefined) {
      rmSync(tempDir, { recursive: true, force: true });
      tempDir = undefined;
    }
  });

  it('runs the full pre-analysis chain and writes status reports for analysis-ready runs', async () => {
    const root = createTempDir();
    const outputDir = join(root, 'preanalysis');
    const calls: FakeCalls = {
      collectHuitun: [],
      collectXhsSearch: [],
      archiveXhsRunMedia: [],
      syncXhsRunToFeishu: [],
      checkXhsPipeline: [],
      buildXhsAnalysisSource: [],
    };

    const result = await runXhsPreanalysisRun(baseOptions(outputDir), createFakeDependencies(calls));

    expect(result.status).toBe('success');
    expect(result.huitunCollection.runId).toBe(12);
    expect(result.xhsSearchCollections).toHaveLength(1);
    expect(result.analysisSources).toContainEqual(expect.objectContaining({ runId: 32, status: 'success' }));
    expect(calls.collectHuitun).toHaveLength(1);
    expect(calls.collectXhsSearch).toHaveLength(1);
    expect(calls.archiveXhsRunMedia).toHaveLength(1);
    expect(calls.syncXhsRunToFeishu).toHaveLength(1);
    expect(calls.checkXhsPipeline).toHaveLength(1);
    expect(calls.buildXhsAnalysisSource).toHaveLength(1);
    expect(calls.collectXhsSearch[0]).toMatchObject({ fromHuitunRunId: 12, limitKeywords: 5, withDetails: true });
    expect(calls.archiveXhsRunMedia[0]).toMatchObject({ runId: 32, cdpUrl: 'http://127.0.0.1:17330' });
    expect(calls.syncXhsRunToFeishu[0]).toMatchObject({ runId: 32, dryRun: false, manifestPath: 'data/xhs-media/run-32/manifest.json' });

    expect(existsSync(result.paths.statusJson)).toBe(true);
    expect(existsSync(result.paths.statusMarkdown)).toBe(true);
    const statusJson = JSON.parse(readFileSync(result.paths.statusJson, 'utf8')) as { status: string; analysisSources: unknown[] };
    expect(statusJson.status).toBe('success');
    expect(statusJson.analysisSources).toHaveLength(1);
    const statusMarkdown = readFileSync(result.paths.statusMarkdown, 'utf8');
    expect(statusMarkdown).toContain('Analysis-ready runs');
    expect(statusMarkdown).toContain('Run #32');
    expect(statusMarkdown).toContain('data/xhs-analysis-source/run-32/source.json');
    expect(statusMarkdown).not.toContain('选题');
    expect(statusMarkdown).not.toContain('文案');
  });
});
```

- [ ] **Step 2: Run the test to verify RED**

Run:

```bash
npm test -- tests/xhs-preanalysis-run.test.ts
```

Expected: FAIL because `../src/xhs-preanalysis-run.js` and `../src/xhs-preanalysis-run-types.js` do not exist.

- [ ] **Step 3: Create the types file**

Create `src/xhs-preanalysis-run-types.ts`:

```ts
import type { XhsAnalysisSourceOptions, XhsAnalysisSourceResult } from './xhs-analysis-source-types.js';
import type { XhsFeishuSyncOptions, XhsFeishuSyncResult } from './feishu/xhs-sync.js';
import type { XhsMediaArchiveOptions, XhsMediaArchiveResult } from './xhs-media-archive.js';
import type { XhsPipelineCheckOptions, XhsPipelineCheckResult } from './xhs-pipeline-check-types.js';
import type { CollectorOptions, RunStatus } from './types.js';
import type { XhsSearchSortKey } from './xhs-types.js';

export type XhsPreanalysisStageStatus = 'pending' | 'running' | 'success' | 'partial_success' | 'failed' | 'skipped';

export interface XhsPreanalysisRunOptions {
  orchestrationId?: string;
  keyword: string;
  dbPath: string;
  huitunCdpUrl: string;
  xhsCdpUrl: string;
  mediaCdpUrl: string;
  limitHotwords: number;
  limitNotes: number;
  days: 7 | 30 | 90 | 180;
  xhsLimitKeywords: number;
  xhsSorts: XhsSearchSortKey[];
  xhsLimitPerSort: number;
  withDetails: boolean;
  detailBudget: number;
  detailDelayMinMs: number;
  detailDelayMaxMs: number;
  stopOnRateLimit: boolean;
  resumeMissingDetails: boolean;
  mediaDelayMinMs: number;
  mediaDelayMaxMs: number;
  feishuDryRun: boolean;
  outputDir?: string;
}

export interface XhsPreanalysisHuitunResult {
  runId: number;
  status: RunStatus;
  hotWordCount: number;
  noteCount: number;
  detailCount: number;
  dbPath: string;
  qualityReport: unknown;
}

export interface XhsPreanalysisXhsSearchRunResult {
  runId: number;
  keyword: string;
  status: RunStatus;
  noteCount: number;
}

export interface XhsPreanalysisXhsSearchResult {
  runs: XhsPreanalysisXhsSearchRunResult[];
  dbPath: string;
  detailBudgetUsed: number;
  rateLimited: boolean;
  rateLimitContext?: unknown;
}

export interface XhsPreanalysisRunDependencies {
  now?: () => string;
  collectHuitun(options: CollectorOptions): Promise<XhsPreanalysisHuitunResult>;
  collectXhsSearch(options: {
    keyword?: string;
    fromHuitunRunId?: number;
    limitKeywords: number;
    sorts: XhsSearchSortKey[];
    limitPerSort: number;
    withDetails: boolean;
    detailDelayMinMs: number;
    detailDelayMaxMs: number;
    detailBudget: number;
    stopOnRateLimit: boolean;
    resumeMissingDetails: boolean;
    dbPath: string;
    cdpUrl: string;
  }): Promise<XhsPreanalysisXhsSearchResult>;
  archiveXhsRunMedia(options: XhsMediaArchiveOptions): Promise<XhsMediaArchiveResult>;
  syncXhsRunToFeishu(options: XhsFeishuSyncOptions): Promise<XhsFeishuSyncResult>;
  checkXhsPipeline(options: XhsPipelineCheckOptions): XhsPipelineCheckResult;
  buildXhsAnalysisSource(options: XhsAnalysisSourceOptions): XhsAnalysisSourceResult;
}

export interface XhsPreanalysisStageRecord<T = unknown> {
  stage: string;
  status: XhsPreanalysisStageStatus;
  startedAt: string;
  finishedAt: string;
  command: string;
  runId?: number;
  keyword?: string;
  result?: T;
  errorMessage?: string;
  recoveryCommand?: string;
}

export interface XhsPreanalysisRunResult {
  orchestrationId: string;
  keyword: string;
  status: 'success' | 'partial_success' | 'failed';
  startedAt: string;
  finishedAt: string;
  paths: {
    outputDir: string;
    statusJson: string;
    statusMarkdown: string;
  };
  huitunCollection: XhsPreanalysisStageRecord<XhsPreanalysisHuitunResult>;
  xhsSearchCollections: Array<XhsPreanalysisStageRecord<XhsPreanalysisXhsSearchRunResult>>;
  mediaArchives: Array<XhsPreanalysisStageRecord<XhsMediaArchiveResult>>;
  feishuSyncs: Array<XhsPreanalysisStageRecord<XhsFeishuSyncResult>>;
  pipelineChecks: Array<XhsPreanalysisStageRecord<XhsPipelineCheckResult>>;
  analysisSources: Array<XhsPreanalysisStageRecord<XhsAnalysisSourceResult>>;
}
```

- [ ] **Step 4: Implement the minimal success-path orchestrator**

Create `src/xhs-preanalysis-run.ts`:

```ts
import { mkdirSync, writeFileSync } from 'node:fs';

import type {
  XhsPreanalysisRunDependencies,
  XhsPreanalysisRunOptions,
  XhsPreanalysisRunResult,
  XhsPreanalysisStageRecord,
} from './xhs-preanalysis-run-types.js';

function timestampId(value: string): string {
  return value.replace(/[:.]/g, '-');
}

function now(dependencies: XhsPreanalysisRunDependencies): string {
  return dependencies.now?.() ?? new Date().toISOString();
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function defaultOutputDir(orchestrationId: string): string {
  return `data/xhs-preanalysis-run/${orchestrationId}`;
}

function mediaManifestPath(runId: number): string {
  return `data/xhs-media/run-${runId}/manifest.json`;
}

function feishuSyncReportPath(runId: number): string {
  return `data/feishu-sync/run-${runId}/sync-report.json`;
}

function pipelineCheckJsonPath(runId: number): string {
  return `data/xhs-pipeline-check/run-${runId}/check.json`;
}

function command(parts: string[]): string {
  return parts.filter((part) => part.trim() !== '').join(' ');
}

function huitunCommand(options: XhsPreanalysisRunOptions): string {
  return command([
    'npm run collect --',
    '--keyword', options.keyword,
    '--limit-hotwords', String(options.limitHotwords),
    '--limit-notes', String(options.limitNotes),
    '--days', String(options.days),
    '--db-path', options.dbPath,
    '--cdp-url', options.huitunCdpUrl,
  ]);
}

function xhsSearchCommand(options: XhsPreanalysisRunOptions, huitunRunId: number): string {
  return command([
    'npm run collect -- xhs-search',
    '--from-huitun-run-id', String(huitunRunId),
    '--limit-keywords', String(options.xhsLimitKeywords),
    '--sorts', options.xhsSorts.join(','),
    '--limit-per-sort', String(options.xhsLimitPerSort),
    options.withDetails ? '--with-details' : '',
    '--detail-budget', String(options.detailBudget),
    '--detail-delay-min-ms', String(options.detailDelayMinMs),
    '--detail-delay-max-ms', String(options.detailDelayMaxMs),
    options.stopOnRateLimit ? '' : '--no-stop-on-rate-limit',
    options.resumeMissingDetails ? '' : '--no-resume-missing-details',
    '--db-path', options.dbPath,
    '--cdp-url', options.xhsCdpUrl,
  ]);
}

function mediaArchiveCommand(options: XhsPreanalysisRunOptions, runId: number): string {
  return command([
    'npm run collect -- xhs-media-archive',
    '--run-id', String(runId),
    '--db-path', options.dbPath,
    '--cdp-url', options.mediaCdpUrl,
    '--delay-min-ms', String(options.mediaDelayMinMs),
    '--delay-max-ms', String(options.mediaDelayMaxMs),
  ]);
}

function feishuSyncCommand(options: XhsPreanalysisRunOptions, runId: number): string {
  return command([
    'npm run collect -- xhs-sync-feishu',
    '--run-id', String(runId),
    '--db-path', options.dbPath,
    '--manifest', mediaManifestPath(runId),
    options.feishuDryRun ? '--dry-run' : '',
  ]);
}

function pipelineCheckCommand(options: XhsPreanalysisRunOptions, runId: number): string {
  return command([
    'npm run collect -- xhs-pipeline-check',
    '--run-id', String(runId),
    '--db-path', options.dbPath,
    '--manifest', mediaManifestPath(runId),
    '--sync-report', feishuSyncReportPath(runId),
  ]);
}

function analysisSourceCommand(options: XhsPreanalysisRunOptions, runId: number): string {
  return command([
    'npm run collect -- xhs-analysis-source',
    '--run-id', String(runId),
    '--db-path', options.dbPath,
    '--manifest', mediaManifestPath(runId),
    '--sync-report', feishuSyncReportPath(runId),
    '--pipeline-check', pipelineCheckJsonPath(runId),
  ]);
}

function renderMarkdown(result: XhsPreanalysisRunResult): string {
  const readyRuns = result.analysisSources.filter((stage) => stage.status === 'success');
  const partialRuns = result.pipelineChecks.filter((stage) => stage.result?.status === 'partial');
  const failedStages = [
    result.huitunCollection,
    ...result.xhsSearchCollections,
    ...result.mediaArchives,
    ...result.feishuSyncs,
    ...result.pipelineChecks,
    ...result.analysisSources,
  ].filter((stage) => stage.status === 'failed' || stage.status === 'skipped');

  const readyLines = readyRuns.length === 0
    ? ['- 无']
    : readyRuns.map((stage) => [
      `- Run #${stage.runId}: ready`,
      `  - Source: ${stage.result?.files.sourceJson ?? ''}`,
      `  - Notes: ${stage.result?.files.notesJsonl ?? ''}`,
    ].join('\n'));

  const partialLines = partialRuns.length === 0
    ? ['- 无']
    : partialRuns.map((stage) => `- Run #${stage.runId}: usable with warnings (${stage.result?.warnings.map((warning) => warning.code).join(', ')})`);

  const failedLines = failedStages.length === 0
    ? ['- 无']
    : failedStages.map((stage) => [
      `- ${stage.stage}${stage.runId === undefined ? '' : ` run #${stage.runId}`}: ${stage.status}`,
      stage.errorMessage === undefined ? '' : `  - Error: ${stage.errorMessage}`,
      stage.recoveryCommand === undefined ? '' : `  - Recovery: ${stage.recoveryCommand}`,
    ].filter(Boolean).join('\n'));

  return [
    '# XHS Pre-analysis Run Status',
    '',
    `Keyword: ${result.keyword}`,
    `Status: ${result.status}`,
    `Orchestration: ${result.orchestrationId}`,
    '',
    '## Analysis-ready runs',
    ...readyLines,
    '',
    '## Partial runs',
    ...partialLines,
    '',
    '## Failed or skipped stages',
    ...failedLines,
    '',
  ].join('\n');
}

function writeStatus(result: XhsPreanalysisRunResult): void {
  mkdirSync(result.paths.outputDir, { recursive: true });
  writeFileSync(result.paths.statusJson, JSON.stringify(result, null, 2), 'utf8');
  writeFileSync(result.paths.statusMarkdown, renderMarkdown(result), 'utf8');
}

function aggregateStatus(result: Omit<XhsPreanalysisRunResult, 'status'>): XhsPreanalysisRunResult['status'] {
  const stages = [
    result.huitunCollection,
    ...result.xhsSearchCollections,
    ...result.mediaArchives,
    ...result.feishuSyncs,
    ...result.pipelineChecks,
    ...result.analysisSources,
  ];
  if (result.huitunCollection.status === 'failed' || result.analysisSources.every((stage) => stage.status !== 'success')) {
    return 'failed';
  }
  return stages.some((stage) => stage.status !== 'success') ? 'partial_success' : 'success';
}

function stageRecord<T>(params: {
  stage: string;
  status: XhsPreanalysisStageRecord<T>['status'];
  startedAt: string;
  finishedAt: string;
  command: string;
  runId?: number;
  keyword?: string;
  result?: T;
  errorMessage?: string;
  recoveryCommand?: string;
}): XhsPreanalysisStageRecord<T> {
  return params;
}

export async function runXhsPreanalysisRun(
  options: XhsPreanalysisRunOptions,
  dependencies: XhsPreanalysisRunDependencies,
): Promise<XhsPreanalysisRunResult> {
  const startedAt = now(dependencies);
  const orchestrationId = options.orchestrationId ?? timestampId(startedAt);
  const outputDir = options.outputDir ?? defaultOutputDir(orchestrationId);
  const paths = {
    outputDir,
    statusJson: `${outputDir}/status.json`,
    statusMarkdown: `${outputDir}/status.md`,
  };

  const huitunStartedAt = now(dependencies);
  let huitunCollection: XhsPreanalysisRunResult['huitunCollection'];
  try {
    const result = await dependencies.collectHuitun({
      keyword: options.keyword,
      limitHotwords: options.limitHotwords,
      limitNotes: options.limitNotes,
      days: options.days,
      dbPath: options.dbPath,
      cdpUrl: options.huitunCdpUrl,
      headless: false,
    });
    huitunCollection = stageRecord({
      stage: 'huitunCollection',
      status: result.status === 'success' ? 'success' : 'partial_success',
      startedAt: huitunStartedAt,
      finishedAt: now(dependencies),
      command: huitunCommand(options),
      runId: result.runId,
      keyword: options.keyword,
      result,
      recoveryCommand: huitunCommand(options),
    });
  } catch (error) {
    const finishedAt = now(dependencies);
    huitunCollection = stageRecord({
      stage: 'huitunCollection',
      status: 'failed',
      startedAt: huitunStartedAt,
      finishedAt,
      command: huitunCommand(options),
      keyword: options.keyword,
      errorMessage: errorMessage(error),
      recoveryCommand: huitunCommand(options),
    });
    const failedResult: XhsPreanalysisRunResult = {
      orchestrationId,
      keyword: options.keyword,
      status: 'failed',
      startedAt,
      finishedAt,
      paths,
      huitunCollection,
      xhsSearchCollections: [],
      mediaArchives: [],
      feishuSyncs: [],
      pipelineChecks: [],
      analysisSources: [],
    };
    writeStatus(failedResult);
    return failedResult;
  }

  const xhsStartedAt = now(dependencies);
  const xhsSearchResult = await dependencies.collectXhsSearch({
    fromHuitunRunId: huitunCollection.runId,
    limitKeywords: options.xhsLimitKeywords,
    sorts: options.xhsSorts,
    limitPerSort: options.xhsLimitPerSort,
    withDetails: options.withDetails,
    detailDelayMinMs: options.detailDelayMinMs,
    detailDelayMaxMs: options.detailDelayMaxMs,
    detailBudget: options.detailBudget,
    stopOnRateLimit: options.stopOnRateLimit,
    resumeMissingDetails: options.resumeMissingDetails,
    dbPath: options.dbPath,
    cdpUrl: options.xhsCdpUrl,
  });
  const xhsSearchCollections = xhsSearchResult.runs.map((run) => stageRecord({
    stage: 'xhsSearchCollection',
    status: run.status === 'success' ? 'success' : run.status === 'failed' ? 'failed' : 'partial_success',
    startedAt: xhsStartedAt,
    finishedAt: now(dependencies),
    command: xhsSearchCommand(options, huitunCollection.runId ?? 0),
    runId: run.runId,
    keyword: run.keyword,
    result: run,
    recoveryCommand: xhsSearchCommand(options, huitunCollection.runId ?? 0),
  }));

  const mediaArchives: XhsPreanalysisRunResult['mediaArchives'] = [];
  const feishuSyncs: XhsPreanalysisRunResult['feishuSyncs'] = [];
  const pipelineChecks: XhsPreanalysisRunResult['pipelineChecks'] = [];
  const analysisSources: XhsPreanalysisRunResult['analysisSources'] = [];

  for (const xhsRun of xhsSearchResult.runs) {
    const mediaResult = await dependencies.archiveXhsRunMedia({
      runId: xhsRun.runId,
      dbPath: options.dbPath,
      cdpUrl: options.mediaCdpUrl,
      force: false,
      resumeMissingMedia: true,
      delayMinMs: options.mediaDelayMinMs,
      delayMaxMs: options.mediaDelayMaxMs,
    });
    mediaArchives.push(stageRecord({
      stage: 'mediaArchive',
      status: mediaResult.safetyStopped || mediaResult.incompleteVideos > 0 || mediaResult.noMediaSaved > 0 ? 'partial_success' : 'success',
      startedAt: now(dependencies),
      finishedAt: now(dependencies),
      command: mediaArchiveCommand(options, xhsRun.runId),
      runId: xhsRun.runId,
      keyword: xhsRun.keyword,
      result: mediaResult,
      recoveryCommand: mediaArchiveCommand(options, xhsRun.runId),
    }));

    const syncResult = await dependencies.syncXhsRunToFeishu({
      runId: xhsRun.runId,
      dbPath: options.dbPath,
      manifestPath: mediaManifestPath(xhsRun.runId),
      dryRun: options.feishuDryRun,
    });
    feishuSyncs.push(stageRecord({
      stage: 'feishuSync',
      status: syncResult.failed > 0 ? 'partial_success' : 'success',
      startedAt: now(dependencies),
      finishedAt: now(dependencies),
      command: feishuSyncCommand(options, xhsRun.runId),
      runId: xhsRun.runId,
      keyword: xhsRun.keyword,
      result: syncResult,
      recoveryCommand: feishuSyncCommand(options, xhsRun.runId),
    }));

    const checkResult = dependencies.checkXhsPipeline({
      runId: xhsRun.runId,
      dbPath: options.dbPath,
      manifestPath: mediaManifestPath(xhsRun.runId),
      syncReportPath: feishuSyncReportPath(xhsRun.runId),
    });
    pipelineChecks.push(stageRecord({
      stage: 'pipelineCheck',
      status: checkResult.status === 'complete' ? 'success' : checkResult.status === 'failed' ? 'failed' : 'partial_success',
      startedAt: now(dependencies),
      finishedAt: now(dependencies),
      command: pipelineCheckCommand(options, xhsRun.runId),
      runId: xhsRun.runId,
      keyword: xhsRun.keyword,
      result: checkResult,
      recoveryCommand: pipelineCheckCommand(options, xhsRun.runId),
    }));

    const sourceResult = dependencies.buildXhsAnalysisSource({
      runId: xhsRun.runId,
      dbPath: options.dbPath,
      manifestPath: mediaManifestPath(xhsRun.runId),
      syncReportPath: feishuSyncReportPath(xhsRun.runId),
      pipelineCheckPath: pipelineCheckJsonPath(xhsRun.runId),
    });
    analysisSources.push(stageRecord({
      stage: 'analysisSource',
      status: 'success',
      startedAt: now(dependencies),
      finishedAt: now(dependencies),
      command: analysisSourceCommand(options, xhsRun.runId),
      runId: xhsRun.runId,
      keyword: xhsRun.keyword,
      result: sourceResult,
      recoveryCommand: analysisSourceCommand(options, xhsRun.runId),
    }));
  }

  const withoutStatus = {
    orchestrationId,
    keyword: options.keyword,
    startedAt,
    finishedAt: now(dependencies),
    paths,
    huitunCollection,
    xhsSearchCollections,
    mediaArchives,
    feishuSyncs,
    pipelineChecks,
    analysisSources,
  };
  const result: XhsPreanalysisRunResult = {
    ...withoutStatus,
    status: aggregateStatus(withoutStatus),
  };
  writeStatus(result);
  return result;
}
```

- [ ] **Step 5: Run the success-path test to verify GREEN**

Run:

```bash
npm test -- tests/xhs-preanalysis-run.test.ts
```

Expected: PASS for the first test. If TypeScript complains about exact type inference for fake dependency result literals, add `as const` only to literal status fields such as `'success'` and `'complete'`.

## Task 2: Recoverable failure behavior

**Files:**
- Modify: `tests/xhs-preanalysis-run.test.ts`
- Modify: `src/xhs-preanalysis-run.ts`

- [ ] **Step 1: Add failing tests for stop/continue rules**

Append these tests inside the existing `describe('XHS pre-analysis run orchestration', () => { ... })` block in `tests/xhs-preanalysis-run.test.ts`:

```ts
  it('stops after Huitun failure and writes a recovery command', async () => {
    const root = createTempDir();
    const outputDir = join(root, 'preanalysis');
    const calls: FakeCalls = {
      collectHuitun: [],
      collectXhsSearch: [],
      archiveXhsRunMedia: [],
      syncXhsRunToFeishu: [],
      checkXhsPipeline: [],
      buildXhsAnalysisSource: [],
    };
    const dependencies = createFakeDependencies(calls);
    dependencies.collectHuitun = async (options) => {
      calls.collectHuitun.push(options);
      throw new Error('Huitun login required');
    };

    const result = await runXhsPreanalysisRun(baseOptions(outputDir), dependencies);

    expect(result.status).toBe('failed');
    expect(result.huitunCollection.status).toBe('failed');
    expect(result.huitunCollection.errorMessage).toBe('Huitun login required');
    expect(result.huitunCollection.recoveryCommand).toContain('npm run collect --');
    expect(calls.collectXhsSearch).toHaveLength(0);
    expect(existsSync(result.paths.statusJson)).toBe(true);
    expect(readFileSync(result.paths.statusMarkdown, 'utf8')).toContain('Recovery: npm run collect --');
  });

  it('continues to pipeline check and analysis-source when media archive and Feishu sync fail', async () => {
    const root = createTempDir();
    const outputDir = join(root, 'preanalysis');
    const calls: FakeCalls = {
      collectHuitun: [],
      collectXhsSearch: [],
      archiveXhsRunMedia: [],
      syncXhsRunToFeishu: [],
      checkXhsPipeline: [],
      buildXhsAnalysisSource: [],
    };
    const dependencies = createFakeDependencies(calls);
    dependencies.archiveXhsRunMedia = async (options) => {
      calls.archiveXhsRunMedia.push(options);
      throw new Error('XHS safety verification');
    };
    dependencies.syncXhsRunToFeishu = async (options) => {
      calls.syncXhsRunToFeishu.push(options);
      throw new Error('Feishu token expired');
    };

    const result = await runXhsPreanalysisRun(baseOptions(outputDir), dependencies);

    expect(result.status).toBe('partial_success');
    expect(result.mediaArchives).toContainEqual(expect.objectContaining({
      runId: 32,
      status: 'failed',
      errorMessage: 'XHS safety verification',
      recoveryCommand: expect.stringContaining('xhs-media-archive'),
    }));
    expect(result.feishuSyncs).toContainEqual(expect.objectContaining({
      runId: 32,
      status: 'failed',
      errorMessage: 'Feishu token expired',
      recoveryCommand: expect.stringContaining('xhs-sync-feishu'),
    }));
    expect(result.pipelineChecks).toContainEqual(expect.objectContaining({ runId: 32, status: 'success' }));
    expect(result.analysisSources).toContainEqual(expect.objectContaining({ runId: 32, status: 'success' }));
  });

  it('skips analysis-source when pipeline check reports zero notes', async () => {
    const root = createTempDir();
    const outputDir = join(root, 'preanalysis');
    const calls: FakeCalls = {
      collectHuitun: [],
      collectXhsSearch: [],
      archiveXhsRunMedia: [],
      syncXhsRunToFeishu: [],
      checkXhsPipeline: [],
      buildXhsAnalysisSource: [],
    };
    const dependencies = createFakeDependencies(calls);
    dependencies.checkXhsPipeline = (options) => {
      calls.checkXhsPipeline.push(options);
      return {
        runId: options.runId,
        status: 'failed',
        blockingIssues: [{ code: 'notes_empty', message: 'XHS search run has no collected notes.' }],
        warnings: [],
        paths: {
          dbPath: options.dbPath,
          manifestPath: options.manifestPath ?? `data/xhs-media/run-${options.runId}/manifest.json`,
          syncReportPath: options.syncReportPath ?? `data/feishu-sync/run-${options.runId}/sync-report.json`,
          outputDir: options.outputDir ?? `data/xhs-pipeline-check/run-${options.runId}`,
          jsonPath: `data/xhs-pipeline-check/run-${options.runId}/check.json`,
          markdownPath: `data/xhs-pipeline-check/run-${options.runId}/check.md`,
        },
        counts: {
          notes: 0,
          details: 0,
          tags: 0,
          mediaSources: 0,
          manifestEntries: 0,
          manifestMatchedFeeds: 0,
          manifestSuccessfulCompleteEntries: 0,
          manifestIncompleteEntries: 0,
          incompleteVideos: 0,
          manifestMissingFeeds: 0,
          feishuSyncedRecords: 0,
        },
        agent: {
          ready: false,
          inputContractVersion: 'xhs-analysis-source/v1',
          recommendedInput: {
            dbPath: options.dbPath,
            runId: options.runId,
            manifestPath: options.manifestPath ?? `data/xhs-media/run-${options.runId}/manifest.json`,
            syncReportPath: options.syncReportPath ?? `data/feishu-sync/run-${options.runId}/sync-report.json`,
          },
        },
      };
    };

    const result = await runXhsPreanalysisRun(baseOptions(outputDir), dependencies);

    expect(result.status).toBe('failed');
    expect(calls.buildXhsAnalysisSource).toHaveLength(0);
    expect(result.analysisSources).toContainEqual(expect.objectContaining({
      runId: 32,
      status: 'skipped',
      errorMessage: expect.stringContaining('zero notes'),
      recoveryCommand: expect.stringContaining('xhs-search'),
    }));
  });
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
npm test -- tests/xhs-preanalysis-run.test.ts
```

Expected: FAIL because media/Feishu exceptions currently escape and zero-note checks still call `buildXhsAnalysisSource()`.

- [ ] **Step 3: Add safe stage execution and zero-note skipping**

In `src/xhs-preanalysis-run.ts`, replace the downstream loop body inside `for (const xhsRun of xhsSearchResult.runs) { ... }` with this implementation:

```ts
    try {
      const mediaResult = await dependencies.archiveXhsRunMedia({
        runId: xhsRun.runId,
        dbPath: options.dbPath,
        cdpUrl: options.mediaCdpUrl,
        force: false,
        resumeMissingMedia: true,
        delayMinMs: options.mediaDelayMinMs,
        delayMaxMs: options.mediaDelayMaxMs,
      });
      mediaArchives.push(stageRecord({
        stage: 'mediaArchive',
        status: mediaResult.safetyStopped || mediaResult.incompleteVideos > 0 || mediaResult.noMediaSaved > 0 ? 'partial_success' : 'success',
        startedAt: now(dependencies),
        finishedAt: now(dependencies),
        command: mediaArchiveCommand(options, xhsRun.runId),
        runId: xhsRun.runId,
        keyword: xhsRun.keyword,
        result: mediaResult,
        recoveryCommand: mediaArchiveCommand(options, xhsRun.runId),
      }));
    } catch (error) {
      mediaArchives.push(stageRecord({
        stage: 'mediaArchive',
        status: 'failed',
        startedAt: now(dependencies),
        finishedAt: now(dependencies),
        command: mediaArchiveCommand(options, xhsRun.runId),
        runId: xhsRun.runId,
        keyword: xhsRun.keyword,
        errorMessage: errorMessage(error),
        recoveryCommand: mediaArchiveCommand(options, xhsRun.runId),
      }));
    }

    try {
      const syncResult = await dependencies.syncXhsRunToFeishu({
        runId: xhsRun.runId,
        dbPath: options.dbPath,
        manifestPath: mediaManifestPath(xhsRun.runId),
        dryRun: options.feishuDryRun,
      });
      feishuSyncs.push(stageRecord({
        stage: 'feishuSync',
        status: syncResult.failed > 0 ? 'partial_success' : 'success',
        startedAt: now(dependencies),
        finishedAt: now(dependencies),
        command: feishuSyncCommand(options, xhsRun.runId),
        runId: xhsRun.runId,
        keyword: xhsRun.keyword,
        result: syncResult,
        recoveryCommand: feishuSyncCommand(options, xhsRun.runId),
      }));
    } catch (error) {
      feishuSyncs.push(stageRecord({
        stage: 'feishuSync',
        status: 'failed',
        startedAt: now(dependencies),
        finishedAt: now(dependencies),
        command: feishuSyncCommand(options, xhsRun.runId),
        runId: xhsRun.runId,
        keyword: xhsRun.keyword,
        errorMessage: errorMessage(error),
        recoveryCommand: feishuSyncCommand(options, xhsRun.runId),
      }));
    }

    let checkResult;
    try {
      checkResult = dependencies.checkXhsPipeline({
        runId: xhsRun.runId,
        dbPath: options.dbPath,
        manifestPath: mediaManifestPath(xhsRun.runId),
        syncReportPath: feishuSyncReportPath(xhsRun.runId),
      });
      pipelineChecks.push(stageRecord({
        stage: 'pipelineCheck',
        status: checkResult.status === 'complete' ? 'success' : checkResult.status === 'failed' ? 'failed' : 'partial_success',
        startedAt: now(dependencies),
        finishedAt: now(dependencies),
        command: pipelineCheckCommand(options, xhsRun.runId),
        runId: xhsRun.runId,
        keyword: xhsRun.keyword,
        result: checkResult,
        recoveryCommand: pipelineCheckCommand(options, xhsRun.runId),
      }));
    } catch (error) {
      pipelineChecks.push(stageRecord({
        stage: 'pipelineCheck',
        status: 'failed',
        startedAt: now(dependencies),
        finishedAt: now(dependencies),
        command: pipelineCheckCommand(options, xhsRun.runId),
        runId: xhsRun.runId,
        keyword: xhsRun.keyword,
        errorMessage: errorMessage(error),
        recoveryCommand: pipelineCheckCommand(options, xhsRun.runId),
      }));
    }

    if (checkResult !== undefined && checkResult.counts.notes === 0) {
      analysisSources.push(stageRecord({
        stage: 'analysisSource',
        status: 'skipped',
        startedAt: now(dependencies),
        finishedAt: now(dependencies),
        command: analysisSourceCommand(options, xhsRun.runId),
        runId: xhsRun.runId,
        keyword: xhsRun.keyword,
        errorMessage: `Skip analysis-source for run #${xhsRun.runId}: zero notes`,
        recoveryCommand: xhsSearchCommand(options, huitunCollection.runId ?? 0),
      }));
      continue;
    }

    try {
      const sourceResult = dependencies.buildXhsAnalysisSource({
        runId: xhsRun.runId,
        dbPath: options.dbPath,
        manifestPath: mediaManifestPath(xhsRun.runId),
        syncReportPath: feishuSyncReportPath(xhsRun.runId),
        pipelineCheckPath: pipelineCheckJsonPath(xhsRun.runId),
      });
      analysisSources.push(stageRecord({
        stage: 'analysisSource',
        status: 'success',
        startedAt: now(dependencies),
        finishedAt: now(dependencies),
        command: analysisSourceCommand(options, xhsRun.runId),
        runId: xhsRun.runId,
        keyword: xhsRun.keyword,
        result: sourceResult,
        recoveryCommand: analysisSourceCommand(options, xhsRun.runId),
      }));
    } catch (error) {
      analysisSources.push(stageRecord({
        stage: 'analysisSource',
        status: 'failed',
        startedAt: now(dependencies),
        finishedAt: now(dependencies),
        command: analysisSourceCommand(options, xhsRun.runId),
        runId: xhsRun.runId,
        keyword: xhsRun.keyword,
        errorMessage: errorMessage(error),
        recoveryCommand: analysisSourceCommand(options, xhsRun.runId),
      }));
    }
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
npm test -- tests/xhs-preanalysis-run.test.ts
```

Expected: PASS.

## Task 3: XHS collection failure and partial-run aggregation

**Files:**
- Modify: `tests/xhs-preanalysis-run.test.ts`
- Modify: `src/xhs-preanalysis-run.ts`

- [ ] **Step 1: Add tests for XHS collection errors and multiple run aggregation**

Append these tests inside the same `describe` block:

```ts
  it('records XHS collection failure and does not run downstream stages when no XHS runs are returned', async () => {
    const root = createTempDir();
    const outputDir = join(root, 'preanalysis');
    const calls: FakeCalls = {
      collectHuitun: [],
      collectXhsSearch: [],
      archiveXhsRunMedia: [],
      syncXhsRunToFeishu: [],
      checkXhsPipeline: [],
      buildXhsAnalysisSource: [],
    };
    const dependencies = createFakeDependencies(calls);
    dependencies.collectXhsSearch = async (options) => {
      calls.collectXhsSearch.push(options);
      throw new Error('XHS login required');
    };

    const result = await runXhsPreanalysisRun(baseOptions(outputDir), dependencies);

    expect(result.status).toBe('failed');
    expect(result.xhsSearchCollections).toContainEqual(expect.objectContaining({
      stage: 'xhsSearchCollection',
      status: 'failed',
      errorMessage: 'XHS login required',
      recoveryCommand: expect.stringContaining('xhs-search'),
    }));
    expect(calls.archiveXhsRunMedia).toHaveLength(0);
    expect(calls.syncXhsRunToFeishu).toHaveLength(0);
    expect(calls.checkXhsPipeline).toHaveLength(0);
    expect(calls.buildXhsAnalysisSource).toHaveLength(0);
  });

  it('processes multiple XHS runs serially and marks the whole orchestration partial when one run is partial', async () => {
    const root = createTempDir();
    const outputDir = join(root, 'preanalysis');
    const calls: FakeCalls = {
      collectHuitun: [],
      collectXhsSearch: [],
      archiveXhsRunMedia: [],
      syncXhsRunToFeishu: [],
      checkXhsPipeline: [],
      buildXhsAnalysisSource: [],
    };
    const dependencies = createFakeDependencies(calls);
    dependencies.collectXhsSearch = async (options) => {
      calls.collectXhsSearch.push(options);
      return {
        runs: [
          { runId: 32, keyword: '浴缸', status: 'success', noteCount: 20 },
          { runId: 33, keyword: '浴缸装修', status: 'partial_success', noteCount: 15 },
        ],
        dbPath: options.dbPath,
        detailBudgetUsed: 30,
        rateLimited: true,
        rateLimitContext: { keyword: '浴缸装修', sortKey: 'most_liked', feedId: 'feed33', message: '访问频繁' },
      };
    };

    const result = await runXhsPreanalysisRun(baseOptions(outputDir), dependencies);

    expect(result.status).toBe('partial_success');
    expect(result.xhsSearchCollections).toEqual([
      expect.objectContaining({ runId: 32, status: 'success' }),
      expect.objectContaining({ runId: 33, status: 'partial_success' }),
    ]);
    expect(calls.archiveXhsRunMedia).toHaveLength(2);
    expect(calls.syncXhsRunToFeishu).toHaveLength(2);
    expect(calls.checkXhsPipeline).toHaveLength(2);
    expect(calls.buildXhsAnalysisSource).toHaveLength(2);
  });
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
npm test -- tests/xhs-preanalysis-run.test.ts
```

Expected: FAIL if `collectXhsSearch()` exceptions are not caught.

- [ ] **Step 3: Catch XHS collection failure**

In `src/xhs-preanalysis-run.ts`, replace the direct `const xhsSearchResult = await dependencies.collectXhsSearch(...)` block with:

```ts
  let xhsSearchResult;
  let xhsSearchCollections: XhsPreanalysisRunResult['xhsSearchCollections'] = [];
  try {
    xhsSearchResult = await dependencies.collectXhsSearch({
      fromHuitunRunId: huitunCollection.runId,
      limitKeywords: options.xhsLimitKeywords,
      sorts: options.xhsSorts,
      limitPerSort: options.xhsLimitPerSort,
      withDetails: options.withDetails,
      detailDelayMinMs: options.detailDelayMinMs,
      detailDelayMaxMs: options.detailDelayMaxMs,
      detailBudget: options.detailBudget,
      stopOnRateLimit: options.stopOnRateLimit,
      resumeMissingDetails: options.resumeMissingDetails,
      dbPath: options.dbPath,
      cdpUrl: options.xhsCdpUrl,
    });
    xhsSearchCollections = xhsSearchResult.runs.map((run) => stageRecord({
      stage: 'xhsSearchCollection',
      status: run.status === 'success' ? 'success' : run.status === 'failed' ? 'failed' : 'partial_success',
      startedAt: xhsStartedAt,
      finishedAt: now(dependencies),
      command: xhsSearchCommand(options, huitunCollection.runId ?? 0),
      runId: run.runId,
      keyword: run.keyword,
      result: run,
      recoveryCommand: xhsSearchCommand(options, huitunCollection.runId ?? 0),
    }));
  } catch (error) {
    xhsSearchCollections = [stageRecord({
      stage: 'xhsSearchCollection',
      status: 'failed',
      startedAt: xhsStartedAt,
      finishedAt: now(dependencies),
      command: xhsSearchCommand(options, huitunCollection.runId ?? 0),
      errorMessage: errorMessage(error),
      recoveryCommand: xhsSearchCommand(options, huitunCollection.runId ?? 0),
    })];
    const failedResultBase = {
      orchestrationId,
      keyword: options.keyword,
      startedAt,
      finishedAt: now(dependencies),
      paths,
      huitunCollection,
      xhsSearchCollections,
      mediaArchives: [],
      feishuSyncs: [],
      pipelineChecks: [],
      analysisSources: [],
    };
    const failedResult: XhsPreanalysisRunResult = {
      ...failedResultBase,
      status: aggregateStatus(failedResultBase),
    };
    writeStatus(failedResult);
    return failedResult;
  }
```

After this replacement, keep the existing downstream arrays and change the downstream loop to:

```ts
  for (const xhsRun of xhsSearchResult.runs) {
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
npm test -- tests/xhs-preanalysis-run.test.ts
```

Expected: PASS.

## Task 4: CLI parser and help

**Files:**
- Modify: `tests/cli-options.test.ts`
- Modify: `src/cli.ts`

- [ ] **Step 1: Add failing CLI option tests**

In `tests/cli-options.test.ts`, update the import line to include `parseXhsPreanalysisRunOptions`:

```ts
import { parseExportOptions, parseOptions, parseReportOptions, parseXhsAnalysisSourceOptions, parseXhsFeishuSyncOptions, parseXhsMediaArchiveOptions, parseXhsPipelineCheckOptions, parseXhsPreanalysisRunOptions, parseXhsSearchOptions } from '../src/cli.js';
```

Add these tests after the `parses xhs-analysis-source explicit artifact paths` test:

```ts
  it('parses xhs-preanalysis-run defaults', () => {
    expect(parseXhsPreanalysisRunOptions(['node', 'src/cli.ts', 'xhs-preanalysis-run', '--keyword', '浴缸'])).toEqual({
      keyword: '浴缸',
      dbPath: 'data/xhs-ops.sqlite',
      huitunCdpUrl: 'http://127.0.0.1:9222',
      xhsCdpUrl: 'http://127.0.0.1:9222',
      mediaCdpUrl: 'http://127.0.0.1:17330',
      limitHotwords: 5,
      limitNotes: 20,
      days: 7,
      xhsLimitKeywords: 5,
      xhsSorts: ['latest', 'most_liked', 'most_commented', 'most_collected'],
      xhsLimitPerSort: 20,
      withDetails: false,
      detailBudget: 30,
      detailDelayMinMs: 20000,
      detailDelayMaxMs: 60000,
      stopOnRateLimit: true,
      resumeMissingDetails: true,
      mediaDelayMinMs: 8000,
      mediaDelayMaxMs: 15000,
      feishuDryRun: false,
      outputDir: undefined,
    });
  });

  it('parses xhs-preanalysis-run production preview options', () => {
    expect(parseXhsPreanalysisRunOptions([
      'node',
      'src/cli.ts',
      'xhs-preanalysis-run',
      '--keyword',
      '浴缸',
      '--db-path',
      'data/custom.sqlite',
      '--huitun-cdp-url',
      'http://127.0.0.1:9223',
      '--xhs-cdp-url',
      'http://127.0.0.1:9224',
      '--media-cdp-url',
      'http://127.0.0.1:17330',
      '--limit-hotwords',
      '10',
      '--limit-notes',
      '20',
      '--days',
      '30',
      '--xhs-limit-keywords',
      '10',
      '--xhs-sorts',
      'most_liked,most_collected',
      '--xhs-limit-per-sort',
      '20',
      '--with-details',
      '--detail-budget',
      '50',
      '--detail-delay-min-ms',
      '30000',
      '--detail-delay-max-ms',
      '90000',
      '--no-stop-on-rate-limit',
      '--no-resume-missing-details',
      '--media-delay-min-ms',
      '9000',
      '--media-delay-max-ms',
      '16000',
      '--feishu-dry-run',
      '--output-dir',
      'data/custom-preanalysis',
    ])).toEqual({
      keyword: '浴缸',
      dbPath: 'data/custom.sqlite',
      huitunCdpUrl: 'http://127.0.0.1:9223',
      xhsCdpUrl: 'http://127.0.0.1:9224',
      mediaCdpUrl: 'http://127.0.0.1:17330',
      limitHotwords: 10,
      limitNotes: 20,
      days: 30,
      xhsLimitKeywords: 10,
      xhsSorts: ['most_liked', 'most_collected'],
      xhsLimitPerSort: 20,
      withDetails: true,
      detailBudget: 50,
      detailDelayMinMs: 30000,
      detailDelayMaxMs: 90000,
      stopOnRateLimit: false,
      resumeMissingDetails: false,
      mediaDelayMinMs: 9000,
      mediaDelayMaxMs: 16000,
      feishuDryRun: true,
      outputDir: 'data/custom-preanalysis',
    });
  });

  it('rejects invalid xhs-preanalysis-run delay ranges', () => {
    expect(() => parseXhsPreanalysisRunOptions([
      'node',
      'src/cli.ts',
      'xhs-preanalysis-run',
      '--keyword',
      '浴缸',
      '--detail-delay-min-ms',
      '90000',
      '--detail-delay-max-ms',
      '30000',
    ])).toThrow('--detail-delay-max-ms 必须大于等于 --detail-delay-min-ms');

    expect(() => parseXhsPreanalysisRunOptions([
      'node',
      'src/cli.ts',
      'xhs-preanalysis-run',
      '--keyword',
      '浴缸',
      '--media-delay-min-ms',
      '16000',
      '--media-delay-max-ms',
      '9000',
    ])).toThrow('--media-delay-max-ms 必须大于等于 --media-delay-min-ms');
  });
```

In the root help test, add:

```ts
    expect(result.stdout).toContain('xhs-preanalysis-run');
```

Add this help test near the other subcommand help tests:

```ts
  it('prints xhs-preanalysis-run help with orchestration options', () => {
    const result = spawnSync('node', ['--no-warnings', './node_modules/tsx/dist/cli.mjs', 'src/cli.ts', 'xhs-preanalysis-run', '--help'], {
      encoding: 'utf8',
    });

    expect(result.status).toBe(0);
    expect(result.stdout).toContain('Usage: xhs-huitun-collector xhs-preanalysis-run [options]');
    expect(result.stdout).toContain('--keyword');
    expect(result.stdout).toContain('--xhs-limit-keywords');
    expect(result.stdout).toContain('--xhs-limit-per-sort');
    expect(result.stdout).toContain('--with-details');
    expect(result.stdout).toContain('--feishu-dry-run');
    expect(result.stdout).toContain('--output-dir');
    expect(result.stderr).not.toContain('CommanderError');
  });
```

- [ ] **Step 2: Run CLI tests to verify RED**

Run:

```bash
npm test -- tests/cli-options.test.ts
```

Expected: FAIL because `parseXhsPreanalysisRunOptions` and the subcommand do not exist.

- [ ] **Step 3: Add CLI types, parser, and subcommand**

In `src/cli.ts`:

1. Add this import with the existing type imports near the top:

```ts
import type { XhsPreanalysisRunOptions } from './xhs-preanalysis-run-types.js';
```

2. Add the CLI options interface after `XhsAnalysisSourceCliOptions`:

```ts
interface XhsPreanalysisRunCliOptions {
  keyword?: string;
  dbPath: string;
  huitunCdpUrl: string;
  xhsCdpUrl: string;
  mediaCdpUrl: string;
  limitHotwords: number;
  limitNotes: number;
  days: SupportedDays;
  xhsLimitKeywords: number;
  xhsSorts?: string;
  xhsLimitPerSort: number;
  withDetails: boolean;
  detailBudget: number;
  detailDelayMinMs: number;
  detailDelayMaxMs: number;
  stopOnRateLimit: boolean;
  resumeMissingDetails: boolean;
  mediaDelayMinMs: number;
  mediaDelayMaxMs: number;
  feishuDryRun: boolean;
  outputDir?: string;
}
```

3. Add this export interface after `XhsAnalysisSourceCommandOptions`:

```ts
export type XhsPreanalysisRunCommandOptions = XhsPreanalysisRunOptions;
```

4. Add the subcommand to `createProgram()`:

```ts
    .addCommand(createXhsPipelineCheckSubcommand())
    .addCommand(createXhsAnalysisSourceSubcommand())
    .addCommand(createXhsPreanalysisRunSubcommand());
```

5. Add this program builder after `createXhsAnalysisSourceSubcommand()`:

```ts
function createXhsPreanalysisRunProgram(): Command {
  return new Command()
    .name('xhs-huitun-collector xhs-preanalysis-run')
    .description('Run the full Huitun-to-Feishu pre-analysis pipeline')
    .requiredOption('--keyword <keyword>', '灰豚业务关键词')
    .option('--db-path <path>', 'SQLite 数据库路径', 'data/xhs-ops.sqlite')
    .option('--huitun-cdp-url <url>', '灰豚登录态浏览器 CDP 地址', 'http://127.0.0.1:9222')
    .option('--xhs-cdp-url <url>', '小红书登录态浏览器 CDP 地址', 'http://127.0.0.1:9222')
    .option('--media-cdp-url <url>', '媒体归档浏览器 CDP 地址', 'http://127.0.0.1:17330')
    .option('--limit-hotwords <count>', '灰豚最多采集热词数量', (value) => parsePositiveInteger(value, '--limit-hotwords'), 5)
    .option('--limit-notes <count>', '灰豚每个热词最多采集笔记数量', (value) => parsePositiveInteger(value, '--limit-notes'), 20)
    .option('--days <days>', '灰豚热词详情时间范围，只支持 7、30、90、180', parseDays, 7)
    .option('--xhs-limit-keywords <count>', '最多使用灰豚热词数量进入小红书搜索', (value) => parsePositiveInteger(value, '--xhs-limit-keywords'), 5)
    .option('--xhs-sorts <list>', '逗号分隔的小红书搜索排序键')
    .option('--xhs-limit-per-sort <count>', '小红书每个排序最多采集笔记数量', (value) => parsePositiveInteger(value, '--xhs-limit-per-sort'), 20)
    .option('--with-details', '采集小红书详情页', false)
    .option('--detail-budget <count>', '本次最多打开的小红书详情页数量', (value) => parsePositiveInteger(value, '--detail-budget'), 30)
    .option('--detail-delay-min-ms <ms>', '详情页之间的最小等待毫秒数', (value) => parseNonNegativeInteger(value, '--detail-delay-min-ms'), 20_000)
    .option('--detail-delay-max-ms <ms>', '详情页之间的最大等待毫秒数', (value) => parseNonNegativeInteger(value, '--detail-delay-max-ms'), 60_000)
    .option('--no-stop-on-rate-limit', '遇到小红书访问频繁时不熔断')
    .option('--no-resume-missing-details', '不跳过已有详情的笔记')
    .option('--media-delay-min-ms <ms>', '媒体归档之间的最小等待毫秒数', (value) => parseNonNegativeInteger(value, '--media-delay-min-ms'), 8_000)
    .option('--media-delay-max-ms <ms>', '媒体归档之间的最大等待毫秒数', (value) => parseNonNegativeInteger(value, '--media-delay-max-ms'), 15_000)
    .option('--feishu-dry-run', '只验证飞书同步 payload，不写入飞书', false)
    .option('--output-dir <path>', '总编排状态输出目录；默认 data/xhs-preanalysis-run/<id>');
}

function createXhsPreanalysisRunSubcommand(): Command {
  const program = createXhsPreanalysisRunProgram();
  program.name('xhs-preanalysis-run');
  return program;
}
```

6. Add parser after `parseXhsAnalysisSourceOptions()`:

```ts
function parseXhsPreanalysisRunOptions(argv = process.argv): XhsPreanalysisRunCommandOptions {
  const program = createXhsPreanalysisRunProgram();
  program.exitOverride();
  program.parse(argvWithoutSubcommand(argv));
  const options = program.opts<XhsPreanalysisRunCliOptions>();

  if (options.keyword === undefined || options.keyword.trim() === '') {
    throw new Error('xhs-preanalysis-run requires --keyword');
  }
  if (options.detailDelayMaxMs < options.detailDelayMinMs) {
    throw new Error('--detail-delay-max-ms 必须大于等于 --detail-delay-min-ms');
  }
  if (options.mediaDelayMaxMs < options.mediaDelayMinMs) {
    throw new Error('--media-delay-max-ms 必须大于等于 --media-delay-min-ms');
  }

  return {
    keyword: options.keyword,
    dbPath: options.dbPath,
    huitunCdpUrl: options.huitunCdpUrl,
    xhsCdpUrl: options.xhsCdpUrl,
    mediaCdpUrl: options.mediaCdpUrl,
    limitHotwords: options.limitHotwords,
    limitNotes: options.limitNotes,
    days: options.days,
    xhsLimitKeywords: options.xhsLimitKeywords,
    xhsSorts: parseXhsSortKeys(options.xhsSorts),
    xhsLimitPerSort: options.xhsLimitPerSort,
    withDetails: options.withDetails,
    detailBudget: options.detailBudget,
    detailDelayMinMs: options.detailDelayMinMs,
    detailDelayMaxMs: options.detailDelayMaxMs,
    stopOnRateLimit: options.stopOnRateLimit,
    resumeMissingDetails: options.resumeMissingDetails,
    mediaDelayMinMs: options.mediaDelayMinMs,
    mediaDelayMaxMs: options.mediaDelayMaxMs,
    feishuDryRun: options.feishuDryRun,
    outputDir: options.outputDir,
  };
}
```

7. Add `parseXhsPreanalysisRunOptions` to the bottom export list.

- [ ] **Step 4: Run CLI tests to verify GREEN for parsing/help**

Run:

```bash
npm test -- tests/cli-options.test.ts
```

Expected: PASS for parser/help tests, except the real command route is not wired yet.

## Task 5: CLI runtime wiring

**Files:**
- Modify: `src/cli.ts`
- Modify: `tests/cli-options.test.ts`

- [ ] **Step 1: Add a route smoke test for invalid CDP behavior**

Append this test near the existing route tests in `tests/cli-options.test.ts`:

```ts
  it('routes xhs-preanalysis-run to the orchestrator instead of root collection', () => {
    const result = spawnSync(
      'node',
      [
        '--no-warnings',
        './node_modules/tsx/dist/cli.mjs',
        'src/cli.ts',
        'xhs-preanalysis-run',
        '--keyword',
        '浴缸',
        '--db-path',
        ':memory:',
        '--huitun-cdp-url',
        'http://127.0.0.1:1',
      ],
      { encoding: 'utf8' },
    );

    expect(result.status).toBe(1);
    expect(result.stderr).toContain('无法连接浏览器 CDP：http://127.0.0.1:1');
    expect(result.stderr).not.toContain("required option '--keyword <keyword>' not specified");
    expect(result.stderr).not.toContain('too many arguments');
    expect(result.stderr).not.toContain('CommanderError');
  });
```

- [ ] **Step 2: Run CLI tests to verify RED**

Run:

```bash
npm test -- tests/cli-options.test.ts
```

Expected: FAIL until `main()` routes `xhs-preanalysis-run` to the orchestrator.

- [ ] **Step 3: Wire real dependencies in `main()`**

In `src/cli.ts`, add this branch before the final root `parseOptions(argv)` path:

```ts
  if (command === 'xhs-preanalysis-run') {
    const [
      { runXhsPreanalysisRun },
      { collectXhsSearch },
      { archiveXhsRunMedia },
      { syncXhsRunToFeishu },
      { checkXhsPipeline },
      { buildXhsAnalysisSource },
    ] = await Promise.all([
      import('./xhs-preanalysis-run.js'),
      import('./xhs-search-collector.js'),
      import('./xhs-media-archive.js'),
      import('./feishu/xhs-sync.js'),
      import('./xhs-pipeline-check.js'),
      import('./xhs-analysis-source.js'),
    ]);
    const result = await runXhsPreanalysisRun(parseXhsPreanalysisRunOptions(argv), {
      collectHuitun: collect,
      collectXhsSearch,
      archiveXhsRunMedia,
      syncXhsRunToFeishu,
      checkXhsPipeline,
      buildXhsAnalysisSource,
    });
    console.log(JSON.stringify(result));
    return;
  }
```

- [ ] **Step 4: Run targeted tests to verify GREEN**

Run:

```bash
npm test -- tests/xhs-preanalysis-run.test.ts
npm test -- tests/cli-options.test.ts
```

Expected: PASS.

## Task 6: Full verification and production-preview smoke

**Files:**
- No code changes unless verification reveals a defect.

- [ ] **Step 1: Run focused tests**

Run:

```bash
npm test -- tests/xhs-preanalysis-run.test.ts
npm test -- tests/cli-options.test.ts
```

Expected: PASS.

- [ ] **Step 2: Run full test suite**

Run:

```bash
npm test
```

Expected: PASS.

- [ ] **Step 3: Run typecheck**

Run:

```bash
npm run typecheck
```

Expected: PASS.

- [ ] **Step 4: Run production-preview smoke**

Run:

```bash
npm run collect -- xhs-preanalysis-run \
  --keyword 浴缸 \
  --limit-hotwords 5 \
  --xhs-limit-keywords 5 \
  --xhs-limit-per-sort 20 \
  --with-details
```

Expected behavior:

- Starts from Huitun collection.
- Creates at least one `xhs_search_runs` row if browser/login state is valid.
- Attempts media archive for each created XHS run.
- Attempts Feishu sync for each created XHS run.
- Runs pipeline check for each created XHS run.
- Writes analysis-source for each XHS run with usable notes.
- Writes `data/xhs-preanalysis-run/<id>/status.json` and `status.md`.

- [ ] **Step 5: Inspect smoke outputs**

Inspect the command output and generated status files. Confirm:

```text
data/xhs-preanalysis-run/<id>/status.json
data/xhs-preanalysis-run/<id>/status.md
```

For at least one XHS run with usable notes, confirm:

```text
data/feishu-sync/run-<xhs-run-id>/sync-report.json
data/xhs-pipeline-check/run-<xhs-run-id>/check.json
data/xhs-analysis-source/run-<xhs-run-id>/source.json
data/xhs-analysis-source/run-<xhs-run-id>/notes.jsonl
```

Expected report content:

- `status.md` has `Analysis-ready runs`.
- `status.md` identifies partial/failed stages if any.
- `status.md` contains recovery commands.
- `status.md` does not contain topic ideas, title generation, copywriting, or content recommendations.

## Self-Review

- Spec coverage: This plan implements the one-command Huitun-to-Feishu-to-analysis-source chain, status artifacts, recoverable failure behavior, CLI options, serial execution, no analysis/model calls, and real smoke verification.
- Placeholder scan: No TBD/TODO/fill-in placeholders remain. The only `TODO`-like items are checkbox steps, which are the required plan format.
- Type consistency: `XhsPreanalysisRunOptions`, `XhsPreanalysisRunDependencies`, `XhsPreanalysisStageRecord`, and `runXhsPreanalysisRun()` names are consistent across tests, implementation, and CLI.
- Scope check: This is one subsystem: pre-analysis orchestration. It does not implement the next analysis module.

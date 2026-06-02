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
    huitunCdpUrl: 'http://127.0.0.1:17331',
    xhsCdpUrl: 'http://127.0.0.1:17330',
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

  it('writes copyable status commands with caller-specific recovery options', async () => {
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
    const options: XhsPreanalysisRunOptions = {
      ...baseOptions(outputDir),
      dbPath: 'data/custom-preanalysis.sqlite',
      huitunCdpUrl: 'http://127.0.0.1:19222',
      xhsCdpUrl: 'http://127.0.0.1:29222',
      mediaCdpUrl: 'http://127.0.0.1:39222',
      withDetails: false,
    };

    const result = await runXhsPreanalysisRun(options, createFakeDependencies(calls));
    const statusMarkdown = readFileSync(result.paths.statusMarkdown, 'utf8');
    const commandText = [...result.commands, statusMarkdown].join('\n');
    const xhsSearchCommand = result.commands.find((command) => command.includes('xhs-search'));
    const mediaCommand = result.commands.find((command) => command.includes('xhs-media-archive'));
    const feishuCommand = result.commands.find((command) => command.includes('xhs-sync-feishu'));
    const pipelineCommand = result.commands.find((command) => command.includes('xhs-pipeline-check'));
    const analysisCommand = result.commands.find((command) => command.includes('xhs-analysis-source'));

    expect(commandText).toContain('npm run collect -- xhs-sync-feishu --run-id <xhsRunId>');
    expect(commandText).not.toContain('xhs-feishu-sync');
    expect(commandText).not.toContain('--no-with-details');
    expect(xhsSearchCommand).toBeDefined();
    expect(xhsSearchCommand).not.toContain('--with-details');
    expect(mediaCommand).toContain('--db-path data/custom-preanalysis.sqlite');
    expect(mediaCommand).toContain('--cdp-url http://127.0.0.1:39222');
    expect(feishuCommand).toContain('--db-path data/custom-preanalysis.sqlite');
    expect(feishuCommand).toContain('--manifest data/xhs-media/run-<xhsRunId>/manifest.json');
    expect(pipelineCommand).toContain('--db-path data/custom-preanalysis.sqlite');
    expect(pipelineCommand).toContain('--manifest data/xhs-media/run-<xhsRunId>/manifest.json');
    expect(pipelineCommand).toContain('--sync-report data/feishu-sync/run-<xhsRunId>/sync-report.json');
    expect(analysisCommand).toContain('--db-path data/custom-preanalysis.sqlite');
    expect(analysisCommand).toContain('--manifest data/xhs-media/run-<xhsRunId>/manifest.json');
    expect(analysisCommand).toContain('--sync-report data/feishu-sync/run-<xhsRunId>/sync-report.json');
    expect(analysisCommand).toContain('--pipeline-check data/xhs-pipeline-check/run-<xhsRunId>/check.json');
  });

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
    expect(result.xhsSearchCollections).toContainEqual(
      expect.objectContaining({
        stage: 'xhsSearchCollection',
        status: 'failed',
        errorMessage: 'XHS login required',
        recoveryCommand: expect.stringContaining('xhs-search'),
      }),
    );
    expect(calls.archiveXhsRunMedia).toHaveLength(0);
    expect(calls.syncXhsRunToFeishu).toHaveLength(0);
    expect(calls.checkXhsPipeline).toHaveLength(0);
    expect(calls.buildXhsAnalysisSource).toHaveLength(0);
  });

  it('continues downstream for XHS runs recovered after collection throws', async () => {
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
    const dependencies = createFakeDependencies(calls) as XhsPreanalysisRunDependencies & {
      listCreatedXhsRunsForHuitunRun: (params: { sourceRunId: number; dbPath: string }) => Array<{
        runId: number;
        keyword: string;
        status: 'partial_success';
        noteCount: number;
      }>;
    };
    dependencies.collectXhsSearch = async (options) => {
      calls.collectXhsSearch.push(options);
      throw new Error('rate limit after first keyword');
    };
    dependencies.listCreatedXhsRunsForHuitunRun = (params) => {
      expect(params).toEqual({ sourceRunId: 12, dbPath: 'data/test.sqlite' });
      return [{ runId: 32, keyword: '浴缸', status: 'partial_success', noteCount: 12 }];
    };

    const result = await runXhsPreanalysisRun(baseOptions(outputDir), dependencies);

    expect(result.status).toBe('partial_success');
    expect(result.xhsSearchCollections).toContainEqual(expect.objectContaining({ status: 'failed', errorMessage: 'rate limit after first keyword' }));
    expect(result.xhsSearchCollections).toContainEqual(expect.objectContaining({ runId: 32, status: 'partial_success' }));
    expect(calls.archiveXhsRunMedia).toHaveLength(1);
    expect(calls.syncXhsRunToFeishu).toHaveLength(1);
    expect(calls.checkXhsPipeline).toHaveLength(1);
    expect(calls.buildXhsAnalysisSource).toHaveLength(1);
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

  it('marks a partial XHS search run as partial success when analysis source generation succeeds', async () => {
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
        runs: [{ runId: 32, keyword: '浴缸', status: 'partial_success', noteCount: 20 }],
        dbPath: options.dbPath,
        detailBudgetUsed: 3,
        rateLimited: false,
      };
    };

    const result = await runXhsPreanalysisRun(baseOptions(outputDir), dependencies);

    expect(result.status).toBe('partial_success');
    expect(result.analysisSources).toContainEqual(expect.objectContaining({ runId: 32, status: 'success' }));
    expect(calls.buildXhsAnalysisSource).toHaveLength(1);
  });

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
    expect(result.mediaArchives).toContainEqual(
      expect.objectContaining({
        runId: 32,
        status: 'failed',
        errorMessage: 'XHS safety verification',
        recoveryCommand: expect.stringContaining('xhs-media-archive'),
      }),
    );
    expect(result.feishuSyncs).toContainEqual(
      expect.objectContaining({
        runId: 32,
        status: 'failed',
        errorMessage: 'Feishu token expired',
        recoveryCommand: expect.stringContaining('xhs-sync-feishu'),
      }),
    );
    expect(result.pipelineChecks).toContainEqual(expect.objectContaining({ runId: 32, status: 'success' }));
    expect(result.analysisSources).toContainEqual(expect.objectContaining({ runId: 32, status: 'success' }));
  });

  it('records failed pipeline check and still builds analysis source with default paths', async () => {
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
      throw new Error('check json invalid');
    };

    const result = await runXhsPreanalysisRun(baseOptions(outputDir), dependencies);

    expect(result.status).toBe('partial_success');
    expect(result.pipelineChecks).toContainEqual(
      expect.objectContaining({
        runId: 32,
        status: 'failed',
        errorMessage: 'check json invalid',
        recoveryCommand: expect.stringContaining('xhs-pipeline-check'),
      }),
    );
    expect(result.analysisSources).toContainEqual(expect.objectContaining({ runId: 32, status: 'success' }));
    expect(calls.buildXhsAnalysisSource[0]).toMatchObject({
      manifestPath: 'data/xhs-media/run-32/manifest.json',
      syncReportPath: 'data/feishu-sync/run-32/sync-report.json',
      pipelineCheckPath: 'data/xhs-pipeline-check/run-32/check.json',
    });
    const statusMarkdown = readFileSync(result.paths.statusMarkdown, 'utf8');
    expect(statusMarkdown).toContain('check json invalid');
    expect(statusMarkdown).toContain('xhs-pipeline-check');
  });

  it('records failed analysis-source build and writes status artifacts', async () => {
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
    dependencies.buildXhsAnalysisSource = (options) => {
      calls.buildXhsAnalysisSource.push(options);
      throw new Error('source build failed');
    };

    const result = await runXhsPreanalysisRun(baseOptions(outputDir), dependencies);

    expect(result.status).toBe('failed');
    expect(result.analysisSources).toContainEqual(
      expect.objectContaining({
        runId: 32,
        status: 'failed',
        errorMessage: 'source build failed',
        recoveryCommand: expect.stringContaining('xhs-analysis-source'),
      }),
    );
    expect(existsSync(result.paths.statusJson)).toBe(true);
    expect(existsSync(result.paths.statusMarkdown)).toBe(true);
    const statusMarkdown = readFileSync(result.paths.statusMarkdown, 'utf8');
    expect(statusMarkdown).toContain('source build failed');
    expect(statusMarkdown).toContain('xhs-analysis-source');
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
    expect(result.analysisSources).toContainEqual(
      expect.objectContaining({
        runId: 32,
        status: 'skipped',
        errorMessage: expect.stringContaining('zero notes'),
        recoveryCommand: expect.stringContaining('xhs-search'),
      }),
    );
  });
});

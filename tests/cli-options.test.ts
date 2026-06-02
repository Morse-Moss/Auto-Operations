import { spawnSync } from 'node:child_process';

import { describe, expect, it } from 'vitest';

import { parseExportOptions, parseOptions, parseReportOptions, parseXhsAnalysisSourceOptions, parseXhsFeishuSyncOptions, parseXhsMediaArchiveOptions, parseXhsPipelineCheckOptions, parseXhsPreanalysisRunOptions, parseXhsSearchOptions } from '../src/cli.js';

describe('parseOptions', () => {
  it('parses global target note collection options', () => {
    expect(
      parseOptions([
        'node',
        'src/cli.ts',
        '--keyword',
        '浴缸',
        '--target-notes',
        '20',
        '--limit-hotwords',
        '5',
        '--days',
        '7',
      ]),
    ).toMatchObject({
      keyword: '浴缸',
      targetNotes: 20,
      limitHotwords: 5,
      limitNotes: 20,
      days: 7,
    });
  });

  it('preserves per-hotword mode when no global target is provided', () => {
    const options = parseOptions(['node', 'src/cli.ts', '--keyword', '浴缸']);

    expect(options.targetNotes).toBeUndefined();
    expect(options.limitHotwords).toBe(10);
    expect(options.limitNotes).toBe(20);
    expect(options.cdpUrl).toBe('http://127.0.0.1:17331');
  });

  it('rejects non-positive target note counts', () => {
    expect(() => parseOptions(['node', 'src/cli.ts', '--keyword', '浴缸', '--target-notes', '0'])).toThrow(
      '--target-notes 必须是正整数，收到：0',
    );
  });

  it('parses report command options', () => {
    expect(parseReportOptions(['node', 'src/cli.ts', 'report', '--run-id', '123', '--db-path', 'data/custom.sqlite'])).toEqual({
      runId: 123,
      dbPath: 'data/custom.sqlite',
    });
  });

  it('parses export command options', () => {
    expect(
      parseExportOptions([
        'node',
        'src/cli.ts',
        'export',
        '--run-id',
        '123',
        '--db-path',
        'data/custom.sqlite',
        '--output',
        'data/exports/run-123-notes.csv',
      ]),
    ).toEqual({
      runId: 123,
      dbPath: 'data/custom.sqlite',
      output: 'data/exports/run-123-notes.csv',
    });
  });

  it('rejects non-positive report run ids', () => {
    expect(() => parseReportOptions(['node', 'src/cli.ts', 'report', '--run-id', '0'])).toThrow(
      '--run-id 必须是正整数，收到：0',
    );
  });

  it('parses xhs-media-archive defaults for browser-service', () => {
    expect(parseXhsMediaArchiveOptions(['node', 'src/cli.ts', 'xhs-media-archive', '--run-id', '32'])).toEqual({
      runId: 32,
      dbPath: 'data/xhs-ops.sqlite',
      cdpUrl: 'http://127.0.0.1:17330',
      outputDir: undefined,
      force: false,
      resumeMissingMedia: true,
      delayMinMs: 8000,
      delayMaxMs: 15000,
    });
  });

  it('parses xhs-media-archive no-resume option', () => {
    expect(parseXhsMediaArchiveOptions(['node', 'src/cli.ts', 'xhs-media-archive', '--run-id', '32', '--no-resume-missing-media'])).toMatchObject({
      resumeMissingMedia: false,
    });
  });

  it('parses xhs-sync-feishu dry run options', () => {
    expect(parseXhsFeishuSyncOptions(['node', 'src/cli.ts', 'xhs-sync-feishu', '--run-id', '32', '--dry-run', '--manifest', 'data/manifest.json'])).toEqual({
      runId: 32,
      dbPath: 'data/xhs-ops.sqlite',
      manifestPath: 'data/manifest.json',
      dryRun: true,
    });
  });

  it('parses xhs-pipeline-check defaults', () => {
    expect(parseXhsPipelineCheckOptions(['node', 'src/cli.ts', 'xhs-pipeline-check', '--run-id', '32'])).toEqual({
      runId: 32,
      dbPath: 'data/xhs-ops.sqlite',
      manifestPath: undefined,
      syncReportPath: undefined,
      outputDir: undefined,
    });
  });

  it('parses xhs-pipeline-check explicit artifact paths', () => {
    expect(parseXhsPipelineCheckOptions([
      'node',
      'src/cli.ts',
      'xhs-pipeline-check',
      '--run-id',
      '32',
      '--db-path',
      'data/custom.sqlite',
      '--manifest',
      'data/custom-manifest.json',
      '--sync-report',
      'data/custom-sync-report.json',
      '--output-dir',
      'data/custom-check',
    ])).toEqual({
      runId: 32,
      dbPath: 'data/custom.sqlite',
      manifestPath: 'data/custom-manifest.json',
      syncReportPath: 'data/custom-sync-report.json',
      outputDir: 'data/custom-check',
    });
  });

  it('rejects invalid xhs-pipeline-check run ids', () => {
    expect(() => parseXhsPipelineCheckOptions(['node', 'src/cli.ts', 'xhs-pipeline-check', '--run-id', '0'])).toThrow(
      '--run-id 必须是正整数，收到：0',
    );
  });

  it('parses xhs-analysis-source defaults', () => {
    expect(parseXhsAnalysisSourceOptions(['node', 'src/cli.ts', 'xhs-analysis-source', '--run-id', '32'])).toEqual({
      runId: 32,
      dbPath: 'data/xhs-ops.sqlite',
      manifestPath: undefined,
      syncReportPath: undefined,
      pipelineCheckPath: undefined,
      outputDir: undefined,
    });
  });

  it('parses xhs-analysis-source explicit artifact paths', () => {
    expect(parseXhsAnalysisSourceOptions([
      'node',
      'src/cli.ts',
      'xhs-analysis-source',
      '--run-id',
      '32',
      '--db-path',
      'data/custom.sqlite',
      '--manifest',
      'data/custom-manifest.json',
      '--sync-report',
      'data/custom-sync-report.json',
      '--pipeline-check',
      'data/custom-check.json',
      '--output-dir',
      'data/custom-analysis-source',
    ])).toEqual({
      runId: 32,
      dbPath: 'data/custom.sqlite',
      manifestPath: 'data/custom-manifest.json',
      syncReportPath: 'data/custom-sync-report.json',
      pipelineCheckPath: 'data/custom-check.json',
      outputDir: 'data/custom-analysis-source',
    });
  });

  it('parses xhs-preanalysis-run defaults', () => {
    expect(parseXhsPreanalysisRunOptions(['node', 'src/cli.ts', 'xhs-preanalysis-run', '--keyword', '浴缸'])).toEqual({
      keyword: '浴缸',
      dbPath: 'data/xhs-ops.sqlite',
      huitunCdpUrl: 'http://127.0.0.1:17331',
      xhsCdpUrl: 'http://127.0.0.1:17330',
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

  it('parses explicit xhs-preanalysis-run options', () => {
    expect(
      parseXhsPreanalysisRunOptions([
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
      ]),
    ).toEqual({
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
    expect(() =>
      parseXhsPreanalysisRunOptions([
        'node',
        'src/cli.ts',
        'xhs-preanalysis-run',
        '--keyword',
        '浴缸',
        '--detail-delay-min-ms',
        '90000',
        '--detail-delay-max-ms',
        '30000',
      ]),
    ).toThrow('--detail-delay-max-ms 必须大于等于 --detail-delay-min-ms');

    expect(() =>
      parseXhsPreanalysisRunOptions([
        'node',
        'src/cli.ts',
        'xhs-preanalysis-run',
        '--keyword',
        '浴缸',
        '--media-delay-min-ms',
        '16000',
        '--media-delay-max-ms',
        '9000',
      ]),
    ).toThrow('--media-delay-max-ms 必须大于等于 --media-delay-min-ms');
  });

  it('parses xhs-search manual keyword defaults', () => {
    expect(parseXhsSearchOptions(['node', 'src/cli.ts', 'xhs-search', '--keyword', '护肤'])).toEqual({
      keyword: '护肤',
      fromHuitunRunId: undefined,
      limitKeywords: 10,
      sorts: ['latest', 'most_liked', 'most_commented', 'most_collected'],
      limitPerSort: 20,
      withDetails: false,
      detailDelayMinMs: 20000,
      detailDelayMaxMs: 60000,
      detailBudget: 30,
      stopOnRateLimit: true,
      resumeMissingDetails: true,
      dbPath: 'data/xhs-ops.sqlite',
      cdpUrl: 'http://127.0.0.1:17330',
    });
  });

  it('parses xhs-search detail safety defaults', () => {
    expect(parseXhsSearchOptions(['node', 'src/cli.ts', 'xhs-search', '--keyword', '护肤'])).toMatchObject({
      detailDelayMinMs: 20000,
      detailDelayMaxMs: 60000,
      detailBudget: 30,
      stopOnRateLimit: true,
      resumeMissingDetails: true,
    });
  });

  it('parses explicit xhs-search detail safety options', () => {
    expect(
      parseXhsSearchOptions([
        'node',
        'src/cli.ts',
        'xhs-search',
        '--keyword',
        '护肤',
        '--with-details',
        '--detail-delay-min-ms',
        '1000',
        '--detail-delay-max-ms',
        '2000',
        '--detail-budget',
        '2',
        '--no-stop-on-rate-limit',
        '--no-resume-missing-details',
      ]),
    ).toMatchObject({
      withDetails: true,
      detailDelayMinMs: 1000,
      detailDelayMaxMs: 2000,
      detailBudget: 2,
      stopOnRateLimit: false,
      resumeMissingDetails: false,
    });
  });

  it('rejects invalid xhs-search detail safety options', () => {
    expect(() => parseXhsSearchOptions(['node', 'src/cli.ts', 'xhs-search', '--keyword', '护肤', '--detail-delay-min-ms', '-1'])).toThrow(
      '--detail-delay-min-ms 必须是非负整数，收到：-1',
    );

    expect(() =>
      parseXhsSearchOptions([
        'node',
        'src/cli.ts',
        'xhs-search',
        '--keyword',
        '护肤',
        '--detail-delay-min-ms',
        '2000',
        '--detail-delay-max-ms',
        '1000',
      ]),
    ).toThrow('--detail-delay-max-ms 必须大于等于 --detail-delay-min-ms');

    expect(() => parseXhsSearchOptions(['node', 'src/cli.ts', 'xhs-search', '--keyword', '护肤', '--detail-budget', '0'])).toThrow(
      '--detail-budget 必须是正整数，收到：0',
    );
  });

  it('parses xhs-search Huitun run source options', () => {
    expect(
      parseXhsSearchOptions([
        'node',
        'src/cli.ts',
        'xhs-search',
        '--from-huitun-run-id',
        '123',
        '--limit-keywords',
        '5',
        '--sorts',
        'latest,most_collected',
        '--limit-per-sort',
        '12',
        '--with-details',
        '--db-path',
        'data/custom.sqlite',
        '--cdp-url',
        'http://127.0.0.1:9333',
      ]),
    ).toEqual({
      keyword: undefined,
      fromHuitunRunId: 123,
      limitKeywords: 5,
      sorts: ['latest', 'most_collected'],
      limitPerSort: 12,
      withDetails: true,
      detailDelayMinMs: 20000,
      detailDelayMaxMs: 60000,
      detailBudget: 30,
      stopOnRateLimit: true,
      resumeMissingDetails: true,
      dbPath: 'data/custom.sqlite',
      cdpUrl: 'http://127.0.0.1:9333',
    });
  });

  it('requires exactly one xhs-search source', () => {
    expect(() => parseXhsSearchOptions(['node', 'src/cli.ts', 'xhs-search'])).toThrow(
      'xhs-search requires exactly one of --keyword or --from-huitun-run-id',
    );
    expect(() => parseXhsSearchOptions(['node', 'src/cli.ts', 'xhs-search', '--keyword', '护肤', '--from-huitun-run-id', '123'])).toThrow(
      'xhs-search requires exactly one of --keyword or --from-huitun-run-id',
    );
  });

  it('propagates invalid xhs-search sort key errors', () => {
    expect(() => parseXhsSearchOptions(['node', 'src/cli.ts', 'xhs-search', '--keyword', '护肤', '--sorts', 'latest,bad'])).toThrow(
      'Unsupported XHS sort key: bad',
    );
  });

  it('requires export output path', () => {
    expect(() => parseExportOptions(['node', 'src/cli.ts', 'export'])).toThrow("required option '--output <path>' not specified");
  });

  it('prints root help with report, export, and xhs-search commands', () => {
    const result = spawnSync('node', ['--no-warnings', './node_modules/tsx/dist/cli.mjs', 'src/cli.ts', '--help'], {
      encoding: 'utf8',
    });

    expect(result.status).toBe(0);
    expect(result.stdout).toContain('report');
    expect(result.stdout).toContain('export');
    expect(result.stdout).toContain('xhs-search');
    expect(result.stdout).toContain('xhs-preanalysis-run');
    expect(result.stdout).toContain('xhs-pipeline-check');
    expect(result.stdout).toContain('xhs-analysis-source');
    expect(result.stderr).not.toContain('CommanderError');
  });

  it('prints xhs-analysis-source help with artifact options', () => {
    const result = spawnSync('node', ['--no-warnings', './node_modules/tsx/dist/cli.mjs', 'src/cli.ts', 'xhs-analysis-source', '--help'], {
      encoding: 'utf8',
    });

    expect(result.status).toBe(0);
    expect(result.stdout).toContain('Usage: xhs-huitun-collector xhs-analysis-source [options]');
    expect(result.stdout).toContain('--run-id');
    expect(result.stdout).toContain('--manifest');
    expect(result.stdout).toContain('--sync-report');
    expect(result.stdout).toContain('--pipeline-check');
    expect(result.stdout).toContain('--output-dir');
    expect(result.stderr).not.toContain('CommanderError');
  });

  it('prints xhs-pipeline-check help with artifact options', () => {
    const result = spawnSync('node', ['--no-warnings', './node_modules/tsx/dist/cli.mjs', 'src/cli.ts', 'xhs-pipeline-check', '--help'], {
      encoding: 'utf8',
    });

    expect(result.status).toBe(0);
    expect(result.stdout).toContain('Usage: xhs-huitun-collector xhs-pipeline-check [options]');
    expect(result.stdout).toContain('--run-id');
    expect(result.stdout).toContain('--manifest');
    expect(result.stdout).toContain('--sync-report');
    expect(result.stdout).toContain('--output-dir');
    expect(result.stderr).not.toContain('CommanderError');
  });

  it('prints xhs-media-archive help with resume control option', () => {
    const result = spawnSync('node', ['--no-warnings', './node_modules/tsx/dist/cli.mjs', 'src/cli.ts', 'xhs-media-archive', '--help'], {
      encoding: 'utf8',
    });

    expect(result.status).toBe(0);
    expect(result.stdout).toContain('Usage: xhs-huitun-collector xhs-media-archive [options]');
    expect(result.stdout).toContain('--force');
    expect(result.stdout).toContain('--no-resume-missing-media');
    expect(result.stderr).not.toContain('CommanderError');
  });

  it('prints xhs-preanalysis-run help with key options', () => {
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

  it('prints xhs-search help with real command options', () => {
    const result = spawnSync('node', ['--no-warnings', './node_modules/tsx/dist/cli.mjs', 'src/cli.ts', 'xhs-search', '--help'], {
      encoding: 'utf8',
    });

    expect(result.status).toBe(0);
    expect(result.stdout).toContain('Usage: xhs-huitun-collector xhs-search [options]');
    expect(result.stdout).toContain('--keyword');
    expect(result.stdout).toContain('--from-huitun-run-id');
    expect(result.stdout).toContain('--sorts');
    expect(result.stdout).toContain('--detail-delay-min-ms');
    expect(result.stdout).toContain('--detail-delay-max-ms');
    expect(result.stdout).toContain('--detail-budget');
    expect(result.stdout).toContain('--no-stop-on-rate-limit');
    expect(result.stdout).toContain('--no-resume-missing-details');
    expect(result.stderr).not.toContain('CommanderError');
  });

  it('routes real xhs-search source validation errors through the xhs-search parser', () => {
    const result = spawnSync('node', ['--no-warnings', './node_modules/tsx/dist/cli.mjs', 'src/cli.ts', 'xhs-search'], {
      encoding: 'utf8',
    });

    expect(result.status).toBe(1);
    expect(result.stderr).toContain('xhs-search requires exactly one of --keyword or --from-huitun-run-id');
    expect(result.stderr).not.toContain('too many arguments');
    expect(result.stderr).not.toContain('CommanderError');
  });

  it('routes valid real xhs-search invocations to collection instead of the placeholder', () => {
    const result = spawnSync(
      'node',
      [
        '--no-warnings',
        './node_modules/tsx/dist/cli.mjs',
        'src/cli.ts',
        'xhs-search',
        '--keyword',
        '护肤',
        '--db-path',
        ':memory:',
        '--cdp-url',
        'http://127.0.0.1:1',
      ],
      { encoding: 'utf8' },
    );

    expect(result.status).toBe(1);
    expect(result.stdout).not.toContain('xhs-search collection is not wired yet');
    expect(result.stderr).toContain('无法连接浏览器 CDP：http://127.0.0.1:1');
    expect(result.stderr).not.toContain('too many arguments');
    expect(result.stderr).not.toContain('CommanderError');
  });

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

  it('prints report help without an uncaught CommanderError stack trace', () => {
    const result = spawnSync('node', ['--no-warnings', './node_modules/tsx/dist/cli.mjs', 'src/cli.ts', 'report', '--help'], {
      encoding: 'utf8',
    });

    expect(result.status).toBe(0);
    expect(result.stdout).toContain('Usage: xhs-huitun-collector report [options]');
    expect(result.stderr).not.toContain('CommanderError');
  });

  it('prints invalid report option errors without an uncaught CommanderError stack trace', () => {
    const result = spawnSync('node', ['--no-warnings', './node_modules/tsx/dist/cli.mjs', 'src/cli.ts', 'report', '--run-id', '0'], {
      encoding: 'utf8',
    });

    expect(result.status).toBe(1);
    expect(result.stderr).toContain('--run-id 必须是正整数，收到：0');
    expect(result.stderr).not.toContain('CommanderError');
  });

  it('prints root invalid option errors without an uncaught CommanderError stack trace', () => {
    const result = spawnSync('node', ['--no-warnings', './node_modules/tsx/dist/cli.mjs', 'src/cli.ts', '--target-notes', '0'], {
      encoding: 'utf8',
    });

    expect(result.status).toBe(1);
    expect(result.stderr).toContain('--target-notes 必须是正整数，收到：0');
    expect(result.stderr).not.toContain('CommanderError');
  });

  it('prints root missing keyword errors without an uncaught CommanderError stack trace', () => {
    const result = spawnSync('node', ['--no-warnings', './node_modules/tsx/dist/cli.mjs', 'src/cli.ts'], {
      encoding: 'utf8',
    });

    expect(result.status).toBe(1);
    expect(result.stderr).toContain("required option '--keyword <keyword>' not specified");
    expect(result.stderr).not.toContain('CommanderError');
  });

  it('prints missing export output errors without an uncaught CommanderError stack trace', () => {
    const result = spawnSync('node', ['--no-warnings', './node_modules/tsx/dist/cli.mjs', 'src/cli.ts', 'export'], {
      encoding: 'utf8',
    });

    expect(result.status).toBe(1);
    expect(result.stderr).toContain("required option '--output <path>' not specified");
    expect(result.stderr).not.toContain('CommanderError');
  });

  it('prints missing report database errors without a stack trace', () => {
    const result = spawnSync(
      'node',
      ['--no-warnings', './node_modules/tsx/dist/cli.mjs', 'src/cli.ts', 'report', '--db-path', 'data/does-not-exist.sqlite'],
      { encoding: 'utf8' },
    );

    expect(result.status).toBe(1);
    expect(result.stderr).toContain('SQLite database not found: data/does-not-exist.sqlite');
    expect(result.stderr).not.toContain('Error: SQLite database not found');
    expect(result.stderr).not.toContain('at openExistingDatabase');
  });

  it('prints missing export directory errors without a stack trace', () => {
    const result = spawnSync(
      'node',
      [
        '--no-warnings',
        './node_modules/tsx/dist/cli.mjs',
        'src/cli.ts',
        'export',
        '--output',
        'data/missing-dir/latest-notes.csv',
      ],
      { encoding: 'utf8' },
    );

    expect(result.status).toBe(1);
    expect(result.stderr).toContain('Output directory does not exist: data/missing-dir');
    expect(result.stderr).not.toContain('Error: Output directory does not exist');
    expect(result.stderr).not.toContain('at exportRunNotesToCsv');
  });
});

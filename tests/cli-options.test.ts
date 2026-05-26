import { spawnSync } from 'node:child_process';

import { describe, expect, it } from 'vitest';

import { parseExportOptions, parseOptions, parseReportOptions, parseXhsSearchOptions } from '../src/cli.js';

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

  it('parses xhs-search manual keyword defaults', () => {
    expect(parseXhsSearchOptions(['node', 'src/cli.ts', 'xhs-search', '--keyword', '护肤'])).toEqual({
      keyword: '护肤',
      fromHuitunRunId: undefined,
      limitKeywords: 10,
      sorts: ['latest', 'most_liked', 'most_commented', 'most_collected'],
      limitPerSort: 20,
      withDetails: false,
      dbPath: 'data/xhs-ops.sqlite',
      cdpUrl: 'http://127.0.0.1:9222',
    });
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

# XHS Analysis Source v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Build `xhs-analysis-source/v1`, a stable two-file local input package (`source.json` + `notes.jsonl`) for future Agent analysis.

**Architecture:** Read XHS run/note facts from SQLite, merge local media data from the run manifest, merge Feishu sync audit data from sync-report, and copy pipeline health from pipeline-check. The module writes only machine-readable files and does not invoke Claude/API/Agent analysis.

**Tech Stack:** Node.js, TypeScript, Node SQLite, JSON/JSONL, Commander, Vitest.

---

## File Structure

- Create: `src/xhs-analysis-source-types.ts`
  - Owns the `xhs-analysis-source/v1` contract types.
- Create: `src/xhs-analysis-source.ts`
  - Loads SQLite rows, manifest, sync report, and pipeline-check; writes `source.json` and `notes.jsonl`.
- Modify: `src/cli.ts`
  - Adds `xhs-analysis-source` parser, subcommand, and main dispatch.
- Create: `tests/xhs-analysis-source.test.ts`
  - TDD coverage for source package generation and defensive merging.
- Modify: `tests/cli-options.test.ts`
  - Parser/help tests for the new CLI command.
- Update: `docs/superpowers/specs/2026-05-31-xhs-analysis-source-design.md`
  - Already updated to two-file output; keep as source of truth.

## Task 1: Define the contract with a failing test

**Files:**
- Create: `tests/xhs-analysis-source.test.ts`
- Create after RED: `src/xhs-analysis-source-types.ts`
- Create after RED: `src/xhs-analysis-source.ts`

- [x] **Step 1: Write the failing test**

Create `tests/xhs-analysis-source.test.ts` with this initial test shape:

```ts
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { openDatabase } from '../src/db/client.js';
import { initializeSchema } from '../src/db/schema.js';
import { buildXhsAnalysisSource } from '../src/xhs-analysis-source.js';

let tempDir: string | undefined;

function createTempDir(): string {
  tempDir = mkdtempSync(join(tmpdir(), 'xhs-analysis-source-test-'));
  return tempDir;
}

function seedCompleteRun(dbPath: string, root: string): { manifestPath: string; syncReportPath: string; pipelineCheckPath: string } {
  const db = openDatabase(dbPath);
  initializeSchema(db);
  db.prepare(`insert into xhs_search_runs (id, source, source_run_id, keyword, sorts_json, limit_per_sort, with_details, status, started_at, finished_at) values (1, 'manual_keyword', null, '浴缸', '["most_liked"]', 20, 1, 'success', '2026-05-31 10:00:00', '2026-05-31 10:10:00')`).run();
  db.prepare(`
    insert into xhs_search_notes (
      run_id, keyword, sort_key, sort_label, rank_index, feed_id, xsec_token, search_result_url,
      explore_url, title, author_name, detail_text, raw_detail_text, analysis_source_text,
      detail_tags_json, detail_like_text, detail_collect_text, detail_comment_count_text,
      detail_share_text, note_type, source_topic_texts_json, source_comments_json,
      media_sources_json, raw_card_text
    ) values (
      1, '浴缸', 'most_liked', '最多点赞', 1, 'feed1', 'token', 'https://www.xiaohongshu.com/search_result/feed1?xsec_token=token',
      'https://www.xiaohongshu.com/explore/feed1', '浴缸标题', '作者A', '正文', '原始详情', '分析文本',
      '["浴缸","装修"]', '100', '20', '3', '1', 'video', '["浴缸"]', '["想知道尺寸"]',
      '[{"url":"https://example.com/image.webp","type":"image"}]', '卡片文本'
    )
  `).run();
  db.close();

  const mediaDir = join(root, 'media');
  mkdirSync(mediaDir, { recursive: true });
  const imageFile = join(mediaDir, 'image.webp');
  const videoFile = join(mediaDir, 'video.mp4');
  writeFileSync(imageFile, 'image-bytes');
  writeFileSync(videoFile, 'video-bytes');

  const manifestPath = join(root, 'manifest.json');
  writeFileSync(manifestPath, JSON.stringify([{ feedId: 'feed1', status: 'success', imageFiles: [imageFile], videoFiles: [videoFile], completeVideoFile: videoFile, completeVideoStatus: 'complete', sourceMediaUrls: ['https://example.com/image.webp'] }]), 'utf8');

  const syncReportPath = join(root, 'sync-report.json');
  writeFileSync(syncReportPath, JSON.stringify({ runId: 1, rowCount: 1, failed: 0, records: [{ feedId: 'feed1', status: 'success', fields: { 笔记ID: 'feed1' } }] }), 'utf8');

  const pipelineCheckPath = join(root, 'check.json');
  writeFileSync(pipelineCheckPath, JSON.stringify({ status: 'complete', warnings: [], agent: { ready: true } }), 'utf8');

  return { manifestPath, syncReportPath, pipelineCheckPath };
}

describe('XHS analysis source', () => {
  afterEach(() => {
    if (tempDir !== undefined) {
      rmSync(tempDir, { recursive: true, force: true });
      tempDir = undefined;
    }
  });

  it('writes source.json and notes.jsonl for a complete run', () => {
    const root = createTempDir();
    const dbPath = join(root, 'xhs.sqlite');
    const { manifestPath, syncReportPath, pipelineCheckPath } = seedCompleteRun(dbPath, root);
    const outputDir = join(root, 'analysis-source');

    const result = buildXhsAnalysisSource({ runId: 1, dbPath, manifestPath, syncReportPath, pipelineCheckPath, outputDir });

    expect(result.contractVersion).toBe('xhs-analysis-source/v1');
    expect(result.files.notesJsonl).toBe(join(outputDir, 'notes.jsonl'));
    const source = JSON.parse(readFileSync(result.files.sourceJson, 'utf8')) as { counts: { notes: number } };
    expect(source.counts.notes).toBe(1);
    const lines = readFileSync(result.files.notesJsonl, 'utf8').trim().split('\n');
    expect(lines).toHaveLength(1);
    const note = JSON.parse(lines[0]) as { feedId: string; media: { localImages: string[] }; feishu: { synced: boolean } };
    expect(note.feedId).toBe('feed1');
    expect(note.media.localImages).toHaveLength(1);
    expect(note.feishu.synced).toBe(true);
  });
});
```

- [x] **Step 2: Run test to verify RED**

Run:

```bash
npm test -- tests/xhs-analysis-source.test.ts
```

Expected: FAIL because `../src/xhs-analysis-source.js` does not exist.

- [x] **Step 3: Write minimal implementation**

Create `src/xhs-analysis-source-types.ts` with contract types for:

```ts
export type XhsAnalysisSourceContractVersion = 'xhs-analysis-source/v1';

export interface XhsAnalysisSourceOptions {
  runId: number;
  dbPath: string;
  manifestPath?: string;
  syncReportPath?: string;
  pipelineCheckPath?: string;
  outputDir?: string;
}
```

Create `src/xhs-analysis-source.ts` with:

- default paths:
  - `data/xhs-media/run-<id>/manifest.json`
  - `data/feishu-sync/run-<id>/sync-report.json`
  - `data/xhs-pipeline-check/run-<id>/check.json`
  - `data/xhs-analysis-source/run-<id>`
- `buildXhsAnalysisSource(options)`
- write `source.json`
- write `notes.jsonl`

Only implement enough fields to pass the first test.

- [x] **Step 4: Run test to verify GREEN**

Run:

```bash
npm test -- tests/xhs-analysis-source.test.ts
```

Expected: PASS.

## Task 2: Preserve notes with missing artifacts

**Files:**
- Modify: `tests/xhs-analysis-source.test.ts`
- Modify: `src/xhs-analysis-source.ts`

- [x] **Step 1: Add failing tests**

Add tests:

```ts
it('keeps notes and warns when manifest is missing', () => { ... });
it('keeps notes and warns when sync report is missing', () => { ... });
it('keeps notes and marks pipeline unknown when pipeline check is missing', () => { ... });
```

Expected assertions:

- `source.warnings` contains `manifest_missing`, `sync_report_missing`, or `pipeline_check_missing`.
- `notes.jsonl` still contains one note.
- `media.localImages` is empty when manifest is missing.
- `feishu.synced` is false when sync report is missing.
- `source.pipeline.status` is `unknown` when pipeline check is missing.

- [x] **Step 2: Run tests to verify RED**

Run:

```bash
npm test -- tests/xhs-analysis-source.test.ts
```

Expected: FAIL because missing artifact warnings are not implemented.

- [x] **Step 3: Implement missing artifact behavior**

In `src/xhs-analysis-source.ts`:

- If manifest path missing, use empty manifest array and add warning `{ code: 'manifest_missing', message: ... }`.
- If sync report missing, use empty records and add warning `{ code: 'sync_report_missing', message: ... }`.
- If pipeline check missing, set pipeline `{ status: 'unknown', agentReady: false, warnings: [{ code: 'pipeline_check_missing', message: ... }] }` and add source warning.

- [x] **Step 4: Run tests to verify GREEN**

Run:

```bash
npm test -- tests/xhs-analysis-source.test.ts
```

Expected: PASS.

## Task 3: Defensive JSON parsing and note quality

**Files:**
- Modify: `tests/xhs-analysis-source.test.ts`
- Modify: `src/xhs-analysis-source.ts`

- [x] **Step 1: Add failing test**

Add a test where `detail_tags_json`, `source_comments_json`, or `media_sources_json` contains invalid JSON.

Expected:

- output note keeps the row;
- invalid field becomes `[]`;
- `source.warnings` includes `invalid_json_field`;
- note quality flags reflect missing parsed data.

- [x] **Step 2: Run tests to verify RED**

Run:

```bash
npm test -- tests/xhs-analysis-source.test.ts
```

Expected: FAIL because invalid JSON warning/defensive parse is missing.

- [x] **Step 3: Implement defensive parser**

Add helper:

```ts
function parseJsonArray(value: string | null | undefined, context: { feedId: string; field: string }, warnings: XhsAnalysisSourceWarning[]): unknown[] {
  if (value === undefined || value === null || value.trim() === '') return [];
  try {
    const parsed = JSON.parse(value) as unknown;
    if (Array.isArray(parsed)) return parsed;
  } catch {}
  warnings.push({ code: 'invalid_json_field', message: `Invalid JSON in ${context.field} for feed ${context.feedId}` });
  return [];
}
```

Use it for tags, topics, comments, and media sources.

- [x] **Step 4: Run tests to verify GREEN**

Run:

```bash
npm test -- tests/xhs-analysis-source.test.ts
```

Expected: PASS.

## Task 4: CLI integration

**Files:**
- Modify: `tests/cli-options.test.ts`
- Modify: `src/cli.ts`

- [x] **Step 1: Add failing CLI tests**

Add tests for:

```ts
parseXhsAnalysisSourceOptions(['node', 'src/cli.ts', 'xhs-analysis-source', '--run-id', '32'])
```

Expected default return:

```ts
{
  runId: 32,
  dbPath: 'data/xhs-ops.sqlite',
  manifestPath: undefined,
  syncReportPath: undefined,
  pipelineCheckPath: undefined,
  outputDir: undefined,
}
```

Add help test expecting root help includes `xhs-analysis-source`, and subcommand help includes:

- `--run-id`
- `--manifest`
- `--sync-report`
- `--pipeline-check`
- `--output-dir`

- [x] **Step 2: Run CLI tests to verify RED**

Run:

```bash
npm test -- tests/cli-options.test.ts
```

Expected: FAIL because parser/export/subcommand are missing.

- [x] **Step 3: Implement CLI**

In `src/cli.ts`:

- Add `XhsAnalysisSourceCliOptions`.
- Add `XhsAnalysisSourceCommandOptions`.
- Add `createXhsAnalysisSourceProgram()`.
- Add `createXhsAnalysisSourceSubcommand()`.
- Add `parseXhsAnalysisSourceOptions()`.
- Add to `createProgram()`.
- Add `main()` branch:

```ts
if (command === 'xhs-analysis-source') {
  const { buildXhsAnalysisSource } = await import('./xhs-analysis-source.js');
  const result = buildXhsAnalysisSource(parseXhsAnalysisSourceOptions(argv));
  console.log(JSON.stringify(result));
  return;
}
```

- Export `parseXhsAnalysisSourceOptions`.

- [x] **Step 4: Run CLI tests to verify GREEN**

Run:

```bash
npm test -- tests/cli-options.test.ts
```

Expected: PASS.

## Task 5: Full verification and smoke

**Files:**
- No code changes unless verification reveals a defect.

- [x] **Step 1: Run focused tests**

```bash
npm test -- tests/xhs-analysis-source.test.ts
npm test -- tests/cli-options.test.ts
```

Expected: PASS.

- [x] **Step 2: Run full verification**

```bash
npm test
npm run typecheck
```

Expected: PASS.

- [x] **Step 3: Run local smoke**

```bash
npm run collect -- xhs-analysis-source --run-id 32
```

Expected output files:

```text
data/xhs-analysis-source/run-32/source.json
data/xhs-analysis-source/run-32/notes.jsonl
```

Expected not to create:

```text
data/xhs-analysis-source/run-32/summary.md
```

- [x] **Step 4: Inspect smoke output**

Confirm:

- `source.json.contractVersion` is `xhs-analysis-source/v1`.
- `source.json.files.notesJsonl` points to the generated JSONL.
- `notes.jsonl` has one line per XHS note.
- No analysis/topic/title/copywriting content is generated.

## Self-Review

- Spec coverage: Plan covers two-file output, SQLite/manifest/sync-report/pipeline-check merging, missing artifact warnings, defensive JSON parsing, CLI integration, and verification.
- Placeholder scan: No TBD/TODO/fill-in placeholders are used.
- Type consistency: Function name is consistently `buildXhsAnalysisSource`; contract version is consistently `xhs-analysis-source/v1`; outputs are consistently `source.json` and `notes.jsonl` only.

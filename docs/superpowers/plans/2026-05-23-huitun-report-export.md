# Huitun Report Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add local CLI commands that turn saved Huitun SQLite collection runs into a readable report and a de-duplicated hot-note CSV export.

**Architecture:** Keep scraping untouched. Add a read-only reporting layer over SQLite: repository query methods return typed run/report/export data, formatting modules render text and CSV, and CLI command helpers open the database without connecting to a browser.

**Tech Stack:** Node.js + TypeScript, `node:sqlite`, Commander, Vitest, existing project scripts `npm test` and `npm run typecheck`.

---

## File Structure

- Create `src/reporting/types.ts` — shared report/export read-model types.
- Create `src/reporting/csv.ts` — CSV headers, tag parsing, field mapping, cell escaping, and serialization.
- Create `src/reporting/report.ts` — human-readable text report formatting and warning text.
- Create `src/reporting/commands.ts` — read-command orchestration: open existing SQLite, resolve run id, generate report text, write CSV.
- Modify `src/db/repositories.ts` — add read-only methods for latest run selection, run lookup, report data, and de-duplicated note export rows.
- Modify `src/cli.ts` — dispatch `report` and `export` before legacy collection parsing; preserve existing `--keyword` collection behavior.
- Modify `tests/db.test.ts` — cover repository read methods, latest finished run selection, contribution aggregation, and de-duplicated export rows.
- Create `tests/reporting-csv.test.ts` — cover CSV header, ordering, empty cells, tags, and escaping.
- Create `tests/reporting-report.test.ts` — cover readable report output and warning rendering.
- Create `tests/reporting-commands.test.ts` — cover command helper behavior against a temporary SQLite database and output path validation.
- Modify `tests/cli-options.test.ts` — cover `report` and `export` option parsing.

## Execution Notes

- Do not modify browser automation files in this round.
- Do not connect Playwright or CDP for report/export commands.
- Final CSV rows must be unique by stable note identity: `huitun_note_key + coalesce(published_at, '')`.
- Local commit steps below are checkpoints. Execute them only when the user has authorized local commits.

---

### Task 1: Repository read models and SQLite queries

**Files:**
- Create: `src/reporting/types.ts`
- Modify: `src/db/repositories.ts`
- Test: `tests/db.test.ts`

- [ ] **Step 1: Write failing repository tests**

Add these tests inside the existing `describe('CollectorRepository', () => { ... })` block in `tests/db.test.ts`:

```ts
  it('finds the latest finished run and ignores running runs', () => {
    const firstRunId = repository.createRun({
      keyword: '护肤',
      days: 7,
      limitHotwords: 3,
      limitNotes: 20,
    });
    repository.finishRun(firstRunId, 'success');

    const latestFinishedRunId = repository.createRun({
      keyword: '咖啡',
      days: 30,
      limitHotwords: 5,
      limitNotes: 10,
    });
    repository.finishRun(latestFinishedRunId, 'partial_success', 'collector', '部分失败');

    const runningRunId = repository.createRun({
      keyword: '露营',
      days: 7,
      limitHotwords: 2,
      limitNotes: 20,
    });

    expect(repository.findLatestFinishedRun()).toMatchObject({
      id: latestFinishedRunId,
      keyword: '咖啡',
      status: 'partial_success',
      errorStage: 'collector',
      errorMessage: '部分失败',
    });
    expect(repository.findRunById(runningRunId)).toMatchObject({
      id: runningRunId,
      status: 'running',
      finishedAt: null,
    });
  });

  it('builds report data and de-duplicated note export rows for a run', () => {
    const runId = repository.createRun({
      keyword: '护肤',
      days: 7,
      limitHotwords: 3,
      limitNotes: 20,
    });

    repository.insertHotWordSnapshot(runId, {
      word: '早C晚A',
      days: 7,
      pageUrl: 'https://xhs.huitun.com/#/hotWords/hot_word_detail?hotWord=早C晚A',
      heatText: '1,510',
      relatedNotesText: '26',
      totalInteractionsText: '1.4w',
      overview: { 热度值: '1,510' },
    });
    repository.insertRawSnapshot(runId, {
      kind: 'parse_note_detail_error',
      objectKey: 'note-2',
      pageUrl: 'https://xhs.huitun.com/#/hotWords/hot_word_detail?hotWord=早C晚A',
      textContent: '详情失败',
      htmlContent: null,
    });

    repository.upsertNote(
      runId,
      '护肤',
      {
        hotWord: '早C晚A',
        huitunNoteKey: 'note-1',
        title: '第一篇',
        authorName: '作者A',
        authorLevel: 'Lv3',
        coverUrl: null,
        isVideo: false,
        videoDuration: null,
        publishedAt: '2026-05-01',
        updatedAt: '2026-05-02',
        tags: ['精华', '抗老'],
        estimatedReads: 1000,
        likes: 120,
        collects: 30,
        comments: 4,
        listRank: 2,
        listPage: 1,
      },
      {
        huitunNoteKey: 'note-1',
        estimatedExposure: 5000,
        estimatedReads: 1100,
        likes: 125,
        collects: 32,
        comments: 5,
        shares: 2,
        authorFollowers: 20000,
        authorNoteCount: 88,
        authorTotalLikesCollects: 900000,
        readExposureRatioText: '22%',
        readFollowerRatioText: '5.5%',
      },
    );

    repository.upsertNote(
      runId,
      '护肤',
      {
        hotWord: '早C晚A',
        huitunNoteKey: 'note-2',
        title: '第二篇',
        authorName: '作者B',
        authorLevel: null,
        coverUrl: null,
        isVideo: true,
        videoDuration: '00:30',
        publishedAt: '2026-05-02',
        updatedAt: '2026-05-03',
        tags: ['修护'],
        estimatedReads: 800,
        likes: 80,
        collects: 20,
        comments: 3,
        listRank: 1,
        listPage: 1,
      },
      null,
    );

    repository.upsertNote(
      runId,
      '护肤',
      {
        hotWord: '早C晚A',
        huitunNoteKey: 'note-2',
        title: '第二篇更新',
        authorName: '作者B',
        authorLevel: null,
        coverUrl: null,
        isVideo: true,
        videoDuration: '00:30',
        publishedAt: '2026-05-02',
        updatedAt: '2026-05-04',
        tags: ['修护', '敏感肌'],
        estimatedReads: 900,
        likes: 90,
        collects: 22,
        comments: 4,
        listRank: 1,
        listPage: 1,
      },
      null,
    );

    repository.finishRun(runId, 'partial_success');

    expect(repository.getRunReportData(runId)).toMatchObject({
      run: {
        id: runId,
        keyword: '护肤',
        status: 'partial_success',
        days: 7,
      },
      totals: {
        hotWords: 0,
        hotWordSnapshots: 1,
        notes: 2,
        detailedNotes: 1,
        rawSnapshots: 1,
      },
      detailCoverageRate: 0.5,
      likesCompletenessRate: 1,
      rawSnapshotsByKind: { parse_note_detail_error: 1 },
      hotWordContributions: [{ hotWord: '早C晚A', notes: 2, topLikes: 120, bestRank: 1 }],
    });

    expect(repository.listNoteExportRows(runId).map((row) => row.huitunNoteKey)).toEqual(['note-2', 'note-1']);
    expect(repository.listNoteExportRows(runId)).toHaveLength(2);
  });
```

- [ ] **Step 2: Run repository tests to verify they fail**

Run:

```bash
npm test -- tests/db.test.ts
```

Expected: FAIL because `findLatestFinishedRun`, `findRunById`, `getRunReportData`, and `listNoteExportRows` do not exist yet.

- [ ] **Step 3: Create reporting read-model types**

Create `src/reporting/types.ts`:

```ts
import type { RunStatus } from '../types.js';

export interface CollectionRunRecord {
  id: number;
  keyword: string;
  days: number;
  limitHotwords: number;
  limitNotes: number;
  status: RunStatus;
  startedAt: string;
  finishedAt: string | null;
  errorStage: string | null;
  errorMessage: string | null;
}

export interface RunReportTotals {
  hotWords: number;
  hotWordSnapshots: number;
  notes: number;
  detailedNotes: number;
  rawSnapshots: number;
}

export interface HotWordContribution {
  hotWord: string;
  notes: number;
  topLikes: number | null;
  bestRank: number | null;
}

export interface RunReportData {
  run: CollectionRunRecord;
  totals: RunReportTotals;
  detailCoverageRate: number;
  likesCompletenessRate: number;
  rawSnapshotsByKind: Record<string, number>;
  hotWordContributions: HotWordContribution[];
}

export interface NoteExportRow {
  id: number;
  runId: number;
  sourceKeyword: string;
  hotWord: string;
  listRank: number | null;
  listPage: number | null;
  title: string;
  authorName: string | null;
  isVideo: number;
  publishedAt: string | null;
  likes: number | null;
  collects: number | null;
  comments: number | null;
  shares: number | null;
  estimatedReads: number | null;
  estimatedExposure: number | null;
  authorFollowers: number | null;
  authorNoteCount: number | null;
  readExposureRatioText: string | null;
  readFollowerRatioText: string | null;
  tagsJson: string;
  huitunNoteKey: string;
}
```

- [ ] **Step 4: Add repository read methods**

Modify the import block in `src/db/repositories.ts`:

```ts
import type { DatabaseSync } from 'node:sqlite';

import type {
  CollectionRunRecord,
  HotWordContribution,
  NoteExportRow,
  RunReportData,
} from '../reporting/types.js';
import type {
  CollectionRunInput,
  HotWordRow,
  HotWordSnapshot,
  NoteDetail,
  NoteListRow,
  RawSnapshotInput,
  RunStatus,
} from '../types.js';
```

Add these helper types and functions above `export class CollectorRepository`:

```ts
interface CollectionRunDbRow {
  id: number;
  keyword: string;
  days: number;
  limit_hotwords: number;
  limit_notes: number;
  status: RunStatus;
  started_at: string;
  finished_at: string | null;
  error_stage: string | null;
  error_message: string | null;
}

function mapCollectionRun(row: CollectionRunDbRow): CollectionRunRecord {
  return {
    id: row.id,
    keyword: row.keyword,
    days: row.days,
    limitHotwords: row.limit_hotwords,
    limitNotes: row.limit_notes,
    status: row.status,
    startedAt: row.started_at,
    finishedAt: row.finished_at,
    errorStage: row.error_stage,
    errorMessage: row.error_message,
  };
}

function ratio(numerator: number, denominator: number): number {
  return denominator === 0 ? 0 : numerator / denominator;
}
```

Add these methods inside `CollectorRepository`, before `createRun(input: CollectionRunInput): number`:

```ts
  findLatestFinishedRun(): CollectionRunRecord | null {
    const row = this.db
      .prepare(`
        select *
        from collection_runs
        where status != 'running'
        order by finished_at desc, id desc
        limit 1
      `)
      .get() as CollectionRunDbRow | undefined;

    return row === undefined ? null : mapCollectionRun(row);
  }

  findRunById(runId: number): CollectionRunRecord | null {
    const row = this.db.prepare('select * from collection_runs where id = :runId').get({ runId }) as
      | CollectionRunDbRow
      | undefined;

    return row === undefined ? null : mapCollectionRun(row);
  }

  getRunReportData(runId: number): RunReportData {
    const run = this.findRunById(runId);
    if (run === null) {
      throw new Error(`Collection run not found: ${runId}`);
    }

    const likesRow = this.db
      .prepare(`
        select count(*) as count
        from notes
        where run_id = :runId
          and coalesce(list_likes, likes) is not null
      `)
      .get({ runId }) as { count: number };

    const hotWordContributions = this.db
      .prepare(`
        select
          hot_word as hotWord,
          count(*) as notes,
          max(list_likes) as topLikes,
          min(list_rank) as bestRank
        from notes
        where run_id = :runId
        group by hot_word
        order by notes desc, hot_word asc
      `)
      .all({ runId }) as HotWordContribution[];

    const totals = {
      hotWords: this.countHotWordsForRun(runId),
      hotWordSnapshots: this.countHotWordSnapshotsForRun(runId),
      notes: this.countNotesForRun(runId),
      detailedNotes: this.countDetailedNotesForRun(runId),
      rawSnapshots: this.countRawSnapshotsForRun(runId),
    };

    return {
      run,
      totals,
      detailCoverageRate: ratio(totals.detailedNotes, totals.notes),
      likesCompletenessRate: ratio(likesRow.count, totals.notes),
      rawSnapshotsByKind: this.countRawSnapshotsByKindForRun(runId),
      hotWordContributions,
    };
  }

  listNoteExportRows(runId: number): NoteExportRow[] {
    return this.db
      .prepare(`
        with ranked_notes as (
          select
            notes.*,
            row_number() over (
              partition by huitun_note_key, coalesce(published_at, '')
              order by updated_record_at desc, id desc
            ) as identity_rank
          from notes
          where run_id = :runId
        )
        select
          id,
          run_id as runId,
          source_keyword as sourceKeyword,
          hot_word as hotWord,
          list_rank as listRank,
          list_page as listPage,
          title,
          author_name as authorName,
          is_video as isVideo,
          published_at as publishedAt,
          likes,
          collects,
          comments,
          shares,
          estimated_reads as estimatedReads,
          estimated_exposure as estimatedExposure,
          author_followers as authorFollowers,
          author_note_count as authorNoteCount,
          read_exposure_ratio_text as readExposureRatioText,
          read_follower_ratio_text as readFollowerRatioText,
          tags_json as tagsJson,
          huitun_note_key as huitunNoteKey
        from ranked_notes
        where identity_rank = 1
        order by
          hot_word asc,
          list_rank is null,
          list_rank asc,
          list_likes is null,
          list_likes desc,
          id asc
      `)
      .all({ runId }) as NoteExportRow[];
  }
```

- [ ] **Step 5: Run repository tests to verify they pass**

Run:

```bash
npm test -- tests/db.test.ts
```

Expected: PASS for all `CollectorRepository` tests.

- [ ] **Step 6: Commit checkpoint if authorized**

Run only if local commits are authorized:

```bash
git add src/reporting/types.ts src/db/repositories.ts tests/db.test.ts
git commit -m "feat: add Huitun report read queries"
```

---

### Task 2: CSV formatter

**Files:**
- Create: `src/reporting/csv.ts`
- Test: `tests/reporting-csv.test.ts`

- [ ] **Step 1: Write failing CSV formatter tests**

Create `tests/reporting-csv.test.ts`:

```ts
import { describe, expect, it } from 'vitest';

import { NOTE_EXPORT_HEADERS, serializeNoteExportRows } from '../src/reporting/csv.js';
import type { NoteExportRow } from '../src/reporting/types.js';

const baseRow: NoteExportRow = {
  id: 1,
  runId: 9,
  sourceKeyword: '护肤',
  hotWord: '早C晚A',
  listRank: 1,
  listPage: 1,
  title: '标题,含逗号',
  authorName: '作者"A',
  isVideo: 0,
  publishedAt: '2026-05-01',
  likes: 120,
  collects: 30,
  comments: 4,
  shares: 2,
  estimatedReads: 1000,
  estimatedExposure: 5000,
  authorFollowers: 20000,
  authorNoteCount: 88,
  readExposureRatioText: '20%',
  readFollowerRatioText: '5%',
  tagsJson: JSON.stringify(['精华', '抗老']),
  huitunNoteKey: 'note-1',
};

describe('serializeNoteExportRows', () => {
  it('writes the fixed CSV header', () => {
    expect(NOTE_EXPORT_HEADERS).toEqual([
      'run_id',
      'source_keyword',
      'hot_word',
      'list_rank',
      'list_page',
      'title',
      'author_name',
      'is_video',
      'published_at',
      'likes',
      'collects',
      'comments',
      'shares',
      'estimated_reads',
      'estimated_exposure',
      'author_followers',
      'author_note_count',
      'read_exposure_ratio_text',
      'read_follower_ratio_text',
      'tags',
      'huitun_note_key',
    ]);
  });

  it('serializes rows with CSV escaping and parsed tags', () => {
    expect(serializeNoteExportRows([baseRow])).toBe(
      'run_id,source_keyword,hot_word,list_rank,list_page,title,author_name,is_video,published_at,likes,collects,comments,shares,estimated_reads,estimated_exposure,author_followers,author_note_count,read_exposure_ratio_text,read_follower_ratio_text,tags,huitun_note_key\n' +
        '9,护肤,早C晚A,1,1,"标题,含逗号","作者""A",false,2026-05-01,120,30,4,2,1000,5000,20000,88,20%,5%,精华|抗老,note-1\n',
    );
  });

  it('serializes null values as empty cells and preserves invalid tags text', () => {
    const csv = serializeNoteExportRows([
      {
        ...baseRow,
        listRank: null,
        authorName: null,
        likes: null,
        tagsJson: 'not-json',
      },
    ]);

    expect(csv).toContain('9,护肤,早C晚A,,1,"标题,含逗号",,false,2026-05-01,');
    expect(csv).toContain('not-json,note-1\n');
  });

  it('escapes newlines inside cells', () => {
    expect(serializeNoteExportRows([{ ...baseRow, title: '第一行\n第二行' }])).toContain('"第一行\n第二行"');
  });
});
```

- [ ] **Step 2: Run CSV tests to verify they fail**

Run:

```bash
npm test -- tests/reporting-csv.test.ts
```

Expected: FAIL because `src/reporting/csv.ts` does not exist.

- [ ] **Step 3: Implement CSV formatter**

Create `src/reporting/csv.ts`:

```ts
import type { NoteExportRow } from './types.js';

export const NOTE_EXPORT_HEADERS = [
  'run_id',
  'source_keyword',
  'hot_word',
  'list_rank',
  'list_page',
  'title',
  'author_name',
  'is_video',
  'published_at',
  'likes',
  'collects',
  'comments',
  'shares',
  'estimated_reads',
  'estimated_exposure',
  'author_followers',
  'author_note_count',
  'read_exposure_ratio_text',
  'read_follower_ratio_text',
  'tags',
  'huitun_note_key',
] as const;

type CsvCell = string | number | boolean | null;
type NoteExportHeader = (typeof NOTE_EXPORT_HEADERS)[number];

function parseTags(tagsJson: string): string {
  try {
    const parsed = JSON.parse(tagsJson) as unknown;
    if (Array.isArray(parsed)) {
      return parsed.map((tag) => String(tag)).join('|');
    }
  } catch {
    return tagsJson;
  }

  return tagsJson;
}

function formatCell(value: CsvCell): string {
  if (value === null) {
    return '';
  }

  const text = String(value);
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function mapRow(row: NoteExportRow): Record<NoteExportHeader, CsvCell> {
  return {
    run_id: row.runId,
    source_keyword: row.sourceKeyword,
    hot_word: row.hotWord,
    list_rank: row.listRank,
    list_page: row.listPage,
    title: row.title,
    author_name: row.authorName,
    is_video: row.isVideo === 1,
    published_at: row.publishedAt,
    likes: row.likes,
    collects: row.collects,
    comments: row.comments,
    shares: row.shares,
    estimated_reads: row.estimatedReads,
    estimated_exposure: row.estimatedExposure,
    author_followers: row.authorFollowers,
    author_note_count: row.authorNoteCount,
    read_exposure_ratio_text: row.readExposureRatioText,
    read_follower_ratio_text: row.readFollowerRatioText,
    tags: parseTags(row.tagsJson),
    huitun_note_key: row.huitunNoteKey,
  };
}

export function serializeNoteExportRows(rows: NoteExportRow[]): string {
  const lines = [
    NOTE_EXPORT_HEADERS.join(','),
    ...rows.map((row) => {
      const mapped = mapRow(row);
      return NOTE_EXPORT_HEADERS.map((header) => formatCell(mapped[header])).join(',');
    }),
  ];

  return `${lines.join('\n')}\n`;
}
```

- [ ] **Step 4: Run CSV tests to verify they pass**

Run:

```bash
npm test -- tests/reporting-csv.test.ts
```

Expected: PASS for all CSV formatter tests.

- [ ] **Step 5: Commit checkpoint if authorized**

Run only if local commits are authorized:

```bash
git add src/reporting/csv.ts tests/reporting-csv.test.ts
git commit -m "feat: add Huitun note CSV formatter"
```

---

### Task 3: Text report formatter

**Files:**
- Create: `src/reporting/report.ts`
- Test: `tests/reporting-report.test.ts`

- [ ] **Step 1: Write failing report formatter tests**

Create `tests/reporting-report.test.ts`:

```ts
import { describe, expect, it } from 'vitest';

import { formatRunReport } from '../src/reporting/report.js';
import type { RunReportData } from '../src/reporting/types.js';

const reportData: RunReportData = {
  run: {
    id: 123,
    keyword: '护肤',
    days: 7,
    limitHotwords: 10,
    limitNotes: 20,
    status: 'partial_success',
    startedAt: '2026-05-23 10:00:00',
    finishedAt: '2026-05-23 10:08:00',
    errorStage: null,
    errorMessage: null,
  },
  totals: {
    hotWords: 10,
    hotWordSnapshots: 9,
    notes: 87,
    detailedNotes: 82,
    rawSnapshots: 2,
  },
  detailCoverageRate: 82 / 87,
  likesCompletenessRate: 1,
  rawSnapshotsByKind: {
    parse_note_detail_error: 2,
  },
  hotWordContributions: [
    { hotWord: '早C晚A', notes: 20, topLikes: 12000, bestRank: 1 },
    { hotWord: '敏感肌修护', notes: 18, topLikes: 8300, bestRank: 1 },
  ],
};

describe('formatRunReport', () => {
  it('formats a human-readable run report', () => {
    const text = formatRunReport(reportData);

    expect(text).toContain('Run #123  keyword="护肤"  status=partial_success  days=7');
    expect(text).toContain('Started: 2026-05-23 10:00:00  Finished: 2026-05-23 10:08:00');
    expect(text).toContain('- Hot words: 10');
    expect(text).toContain('- Hot word snapshots: 9');
    expect(text).toContain('- Notes: 87');
    expect(text).toContain('- Detailed notes: 82');
    expect(text).toContain('- Raw snapshots: 2');
    expect(text).toContain('- Detail coverage: 94.3%');
    expect(text).toContain('- Likes completeness: 100.0%');
    expect(text).toContain('1. 早C晚A  notes=20  top_likes=12000  best_rank=1');
    expect(text).toContain('- parse_note_detail_error: 2');
    expect(text).toContain('- Run completed with status partial_success.');
    expect(text).toContain('- Some note details are missing.');
    expect(text).not.toContain('duplicates=');
  });

  it('marks a running run and empty notes clearly', () => {
    const text = formatRunReport({
      ...reportData,
      run: { ...reportData.run, status: 'running', finishedAt: null },
      totals: { ...reportData.totals, notes: 0, detailedNotes: 0, rawSnapshots: 0 },
      detailCoverageRate: 0,
      likesCompletenessRate: 0,
      rawSnapshotsByKind: {},
      hotWordContributions: [],
    });

    expect(text).toContain('Finished: still running');
    expect(text).toContain('- Run is still running; report reflects currently persisted rows.');
    expect(text).toContain('- No notes were collected for this run.');
    expect(text).toContain('Top contributing hot words\n- None');
    expect(text).toContain('Raw snapshot warnings\n- None');
  });
});
```

- [ ] **Step 2: Run report tests to verify they fail**

Run:

```bash
npm test -- tests/reporting-report.test.ts
```

Expected: FAIL because `src/reporting/report.ts` does not exist.

- [ ] **Step 3: Implement text report formatter**

Create `src/reporting/report.ts`:

```ts
import type { RunReportData } from './types.js';

function formatPercent(rate: number): string {
  return `${(rate * 100).toFixed(1)}%`;
}

function formatNullableNumber(value: number | null): string {
  return value === null ? 'n/a' : String(value);
}

function buildWarnings(data: RunReportData): string[] {
  const warnings: string[] = [];

  if (data.run.status === 'running') {
    warnings.push('Run is still running; report reflects currently persisted rows.');
  } else if (data.run.status !== 'success') {
    warnings.push(`Run completed with status ${data.run.status}.`);
  }

  if (data.totals.notes === 0) {
    warnings.push('No notes were collected for this run.');
  }

  if (data.totals.notes > 0 && data.totals.detailedNotes < data.totals.notes) {
    warnings.push('Some note details are missing.');
  }

  if (data.totals.rawSnapshots > 0) {
    warnings.push('Raw snapshots were captured; inspect warning kinds below.');
  }

  if (data.run.errorStage !== null || data.run.errorMessage !== null) {
    warnings.push(`Run error: ${data.run.errorStage ?? 'unknown'} - ${data.run.errorMessage ?? 'unknown'}.`);
  }

  return warnings;
}

export function formatRunReport(data: RunReportData): string {
  const lines: string[] = [
    `Run #${data.run.id}  keyword="${data.run.keyword}"  status=${data.run.status}  days=${data.run.days}`,
    `Started: ${data.run.startedAt}  Finished: ${data.run.finishedAt ?? 'still running'}`,
    '',
    'Collection parameters',
    `- Limit hot words: ${data.run.limitHotwords}`,
    `- Limit notes: ${data.run.limitNotes}`,
    '',
    'Totals',
    `- Hot words: ${data.totals.hotWords}`,
    `- Hot word snapshots: ${data.totals.hotWordSnapshots}`,
    `- Notes: ${data.totals.notes}`,
    `- Detailed notes: ${data.totals.detailedNotes}`,
    `- Raw snapshots: ${data.totals.rawSnapshots}`,
    '',
    'Coverage',
    `- Detail coverage: ${formatPercent(data.detailCoverageRate)}`,
    `- Likes completeness: ${formatPercent(data.likesCompletenessRate)}`,
    '',
    'Top contributing hot words',
  ];

  if (data.hotWordContributions.length === 0) {
    lines.push('- None');
  } else {
    data.hotWordContributions.forEach((hotWord, index) => {
      lines.push(
        `${index + 1}. ${hotWord.hotWord}  notes=${hotWord.notes}  top_likes=${formatNullableNumber(
          hotWord.topLikes,
        )}  best_rank=${formatNullableNumber(hotWord.bestRank)}`,
      );
    });
  }

  lines.push('', 'Raw snapshot warnings');
  const rawSnapshotEntries = Object.entries(data.rawSnapshotsByKind);
  if (rawSnapshotEntries.length === 0) {
    lines.push('- None');
  } else {
    rawSnapshotEntries.forEach(([kind, count]) => {
      lines.push(`- ${kind}: ${count}`);
    });
  }

  lines.push('', 'Warnings');
  const warnings = buildWarnings(data);
  if (warnings.length === 0) {
    lines.push('- None');
  } else {
    warnings.forEach((warning) => {
      lines.push(`- ${warning}`);
    });
  }

  return `${lines.join('\n')}\n`;
}
```

- [ ] **Step 4: Run report tests to verify they pass**

Run:

```bash
npm test -- tests/reporting-report.test.ts
```

Expected: PASS for all report formatter tests.

- [ ] **Step 5: Commit checkpoint if authorized**

Run only if local commits are authorized:

```bash
git add src/reporting/report.ts tests/reporting-report.test.ts
git commit -m "feat: add Huitun run report formatter"
```

---

### Task 4: Report/export command helpers

**Files:**
- Create: `src/reporting/commands.ts`
- Test: `tests/reporting-commands.test.ts`

- [ ] **Step 1: Write failing command helper tests**

Create `tests/reporting-commands.test.ts`:

```ts
import { existsSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import type { DatabaseSync } from 'node:sqlite';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { openDatabase } from '../src/db/client.js';
import { CollectorRepository } from '../src/db/repositories.js';
import { initializeSchema } from '../src/db/schema.js';
import { exportRunNotesToCsv, generateReportText } from '../src/reporting/commands.js';

function seedRun(repository: CollectorRepository): number {
  const runId = repository.createRun({
    keyword: '护肤',
    days: 7,
    limitHotwords: 3,
    limitNotes: 20,
  });

  repository.upsertNote(
    runId,
    '护肤',
    {
      hotWord: '早C晚A',
      huitunNoteKey: 'note-1',
      title: '第一篇',
      authorName: '作者A',
      authorLevel: null,
      coverUrl: null,
      isVideo: false,
      videoDuration: null,
      publishedAt: '2026-05-01',
      updatedAt: '2026-05-02',
      tags: ['精华'],
      estimatedReads: 1000,
      likes: 120,
      collects: 30,
      comments: 4,
      listRank: 1,
      listPage: 1,
    },
    null,
  );
  repository.finishRun(runId, 'success');

  return runId;
}

describe('reporting commands', () => {
  let tempDir: string;
  let dbPath: string;
  let db: DatabaseSync;
  let repository: CollectorRepository;

  beforeEach(() => {
    tempDir = mkdtempSync(join(tmpdir(), 'xhs-report-command-test-'));
    dbPath = join(tempDir, 'collector.sqlite');
    db = openDatabase(dbPath);
    initializeSchema(db);
    repository = new CollectorRepository(db);
  });

  afterEach(() => {
    db.close();
    rmSync(tempDir, { recursive: true, force: true });
  });

  it('generates a report for the latest finished run by default', () => {
    const runId = seedRun(repository);

    const text = generateReportText({ dbPath });

    expect(text).toContain(`Run #${runId}`);
    expect(text).toContain('keyword="护肤"');
  });

  it('exports note rows to an existing output directory', () => {
    const runId = seedRun(repository);
    const output = join(tempDir, 'notes.csv');

    expect(exportRunNotesToCsv({ dbPath, runId, output })).toEqual({
      runId,
      output,
      rowCount: 1,
    });
    expect(existsSync(output)).toBe(true);
    expect(readFileSync(output, 'utf8')).toContain('note-1');
  });

  it('fails when the output parent directory does not exist', () => {
    const runId = seedRun(repository);

    expect(() => exportRunNotesToCsv({ dbPath, runId, output: join(tempDir, 'missing', 'notes.csv') })).toThrow(
      'Output directory does not exist:',
    );
  });

  it('fails when no finished run exists and no run id is provided', () => {
    repository.createRun({
      keyword: '运行中',
      days: 7,
      limitHotwords: 1,
      limitNotes: 20,
    });

    expect(() => generateReportText({ dbPath })).toThrow('No finished collection run found.');
  });
});
```

- [ ] **Step 2: Run command helper tests to verify they fail**

Run:

```bash
npm test -- tests/reporting-commands.test.ts
```

Expected: FAIL because `src/reporting/commands.ts` does not exist.

- [ ] **Step 3: Implement command helpers**

Create `src/reporting/commands.ts`:

```ts
import { existsSync, writeFileSync } from 'node:fs';
import { dirname } from 'node:path';
import { DatabaseSync } from 'node:sqlite';

import { CollectorRepository } from '../db/repositories.js';
import { serializeNoteExportRows } from './csv.js';
import { formatRunReport } from './report.js';

export interface ReportCommandOptions {
  dbPath: string;
  runId?: number;
}

export interface ExportCommandOptions extends ReportCommandOptions {
  output: string;
}

export interface ExportCommandResult {
  runId: number;
  output: string;
  rowCount: number;
}

function openExistingDatabase(dbPath: string): DatabaseSync {
  if (dbPath !== ':memory:' && !existsSync(dbPath)) {
    throw new Error(`SQLite database not found: ${dbPath}. 先运行采集或检查 --db-path。`);
  }

  const db = new DatabaseSync(dbPath);
  db.exec('pragma foreign_keys = ON');
  return db;
}

function resolveRunId(repository: CollectorRepository, requestedRunId: number | undefined): number {
  if (requestedRunId !== undefined) {
    const run = repository.findRunById(requestedRunId);
    if (run === null) {
      throw new Error(`Collection run not found: ${requestedRunId}`);
    }

    return run.id;
  }

  const latestRun = repository.findLatestFinishedRun();
  if (latestRun === null) {
    throw new Error('No finished collection run found. Run collection first or pass --run-id for a specific run.');
  }

  return latestRun.id;
}

export function generateReportText(options: ReportCommandOptions): string {
  const db = openExistingDatabase(options.dbPath);
  try {
    const repository = new CollectorRepository(db);
    const runId = resolveRunId(repository, options.runId);
    return formatRunReport(repository.getRunReportData(runId));
  } finally {
    db.close();
  }
}

export function exportRunNotesToCsv(options: ExportCommandOptions): ExportCommandResult {
  const outputDirectory = dirname(options.output);
  if (!existsSync(outputDirectory)) {
    throw new Error(`Output directory does not exist: ${outputDirectory}`);
  }

  const db = openExistingDatabase(options.dbPath);
  try {
    const repository = new CollectorRepository(db);
    const runId = resolveRunId(repository, options.runId);
    const rows = repository.listNoteExportRows(runId);
    writeFileSync(options.output, serializeNoteExportRows(rows), 'utf8');

    return {
      runId,
      output: options.output,
      rowCount: rows.length,
    };
  } finally {
    db.close();
  }
}
```

- [ ] **Step 4: Run command helper tests to verify they pass**

Run:

```bash
npm test -- tests/reporting-commands.test.ts
```

Expected: PASS for all reporting command helper tests.

- [ ] **Step 5: Commit checkpoint if authorized**

Run only if local commits are authorized:

```bash
git add src/reporting/commands.ts tests/reporting-commands.test.ts
git commit -m "feat: add Huitun report export commands"
```

---

### Task 5: CLI parsing and command dispatch

**Files:**
- Modify: `src/cli.ts`
- Modify: `tests/cli-options.test.ts`

- [ ] **Step 1: Write failing CLI option tests**

Append these tests to `tests/cli-options.test.ts`:

```ts
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

  it('requires export output path', () => {
    expect(() => parseExportOptions(['node', 'src/cli.ts', 'export'])).toThrow("required option '--output <path>' not specified");
  });
```

Update the import in `tests/cli-options.test.ts`:

```ts
import { parseExportOptions, parseOptions, parseReportOptions } from '../src/cli.js';
```

- [ ] **Step 2: Run CLI option tests to verify they fail**

Run:

```bash
npm test -- tests/cli-options.test.ts
```

Expected: FAIL because `parseReportOptions` and `parseExportOptions` are not exported yet.

- [ ] **Step 3: Add report/export parsing and dispatch to CLI**

Modify the import section in `src/cli.ts`:

```ts
import { resolve } from 'node:path';
import type { DatabaseSync } from 'node:sqlite';
import { pathToFileURL } from 'node:url';

import { Command, InvalidArgumentError } from 'commander';

import { collectHotWordRows } from './browser/hotword-search.js';
import { collectHotWordSnapshot, collectTopLikedNoteRows, openHotWordDetail } from './browser/hotword-detail.js';
import {
  capturePageSnapshot,
  createHuitunSession,
  HUITUN_LOGIN_REQUIRED_MESSAGE,
  type HuitunSession,
} from './browser/huitun-session.js';
import { collectNoteDetail } from './browser/note-detail.js';
import {
  buildCollectionQualityReport,
  effectiveNoteLimit,
  type CollectionQualityReport,
  type HotWordCollectionQuality,
} from './collection-quality.js';
import { selectDistinctNotesForTarget } from './collection-target.js';
import type { CollectorRepository } from './db/repositories.js';
import { exportRunNotesToCsv, generateReportText, type ExportCommandOptions, type ReportCommandOptions } from './reporting/commands.js';
import type { CollectorOptions, RunStatus } from './types.js';
```

Add these parser option interfaces below `interface CliOptions`:

```ts
interface ReportCliOptions {
  runId?: number;
  dbPath: string;
}

interface ExportCliOptions extends ReportCliOptions {
  output: string;
}
```

Add these parser helpers below `createProgram()`:

```ts
function argvWithoutSubcommand(argv: string[]): string[] {
  return [argv[0] ?? 'node', argv[1] ?? 'src/cli.ts', ...argv.slice(3)];
}

function createReportProgram(): Command {
  return new Command()
    .name('xhs-huitun-collector report')
    .description('Show a readable summary for a Huitun collection run')
    .option('--run-id <id>', '采集 run id；未传时选择最近已结束 run', (value) => parsePositiveInteger(value, '--run-id'))
    .option('--db-path <path>', 'SQLite 数据库路径', 'data/xhs-ops.sqlite');
}

function createExportProgram(): Command {
  return new Command()
    .name('xhs-huitun-collector export')
    .description('Export de-duplicated Huitun hot note rows to CSV')
    .option('--run-id <id>', '采集 run id；未传时选择最近已结束 run', (value) => parsePositiveInteger(value, '--run-id'))
    .option('--db-path <path>', 'SQLite 数据库路径', 'data/xhs-ops.sqlite')
    .requiredOption('--output <path>', 'CSV 输出路径');
}

function parseReportOptions(argv = process.argv): ReportCommandOptions {
  const program = createReportProgram();
  program.exitOverride();
  program.parse(argvWithoutSubcommand(argv));
  const options = program.opts<ReportCliOptions>();

  return {
    runId: options.runId,
    dbPath: options.dbPath,
  };
}

function parseExportOptions(argv = process.argv): ExportCommandOptions {
  const program = createExportProgram();
  program.exitOverride();
  program.parse(argvWithoutSubcommand(argv));
  const options = program.opts<ExportCliOptions>();

  return {
    runId: options.runId,
    dbPath: options.dbPath,
    output: options.output,
  };
}
```

Replace `main()` in `src/cli.ts` with:

```ts
async function main(argv = process.argv): Promise<void> {
  const command = argv[2];

  if (command === 'report') {
    console.log(generateReportText(parseReportOptions(argv)));
    return;
  }

  if (command === 'export') {
    const result = exportRunNotesToCsv(parseExportOptions(argv));
    console.log(`Exported ${result.rowCount} notes from run #${result.runId} to ${result.output}`);
    return;
  }

  const options = parseOptions(argv);
  const result = await collect(options);
  console.log(JSON.stringify(result));
}
```

Replace the final export line in `src/cli.ts` with:

```ts
export { collect, createProgram, formatRawSnapshotTextContent, parseExportOptions, parseOptions, parseReportOptions };
```

- [ ] **Step 4: Run CLI option tests to verify they pass**

Run:

```bash
npm test -- tests/cli-options.test.ts
```

Expected: PASS for all CLI option tests.

- [ ] **Step 5: Run existing CLI diagnostic tests**

Run:

```bash
npm test -- tests/cli-diagnostics.test.ts
```

Expected: PASS. This confirms `formatRawSnapshotTextContent` is still exported.

- [ ] **Step 6: Commit checkpoint if authorized**

Run only if local commits are authorized:

```bash
git add src/cli.ts tests/cli-options.test.ts
git commit -m "feat: wire Huitun report export CLI"
```

---

### Task 6: Final verification and manual smoke commands

**Files:**
- No code files unless verification exposes a defect.

- [ ] **Step 1: Run the full test suite**

Run:

```bash
npm test
```

Expected: PASS for all tests.

- [ ] **Step 2: Run TypeScript type checking**

Run:

```bash
npm run typecheck
```

Expected: PASS with no TypeScript errors.

- [ ] **Step 3: Smoke-test report command if a local database exists**

Run only if `data/xhs-ops.sqlite` exists:

```bash
npm run collect -- report
```

Expected: prints a text report starting with `Run #` and does not launch or connect to a browser.

- [ ] **Step 4: Smoke-test export command if a local database exists and `data/exports` exists**

Run only if both `data/xhs-ops.sqlite` and `data/exports` exist:

```bash
npm run collect -- export --output data/exports/latest-notes.csv
```

Expected: prints `Exported N notes from run #X to data/exports/latest-notes.csv`, and the CSV contains one header row plus de-duplicated note rows.

- [ ] **Step 5: Check git diff**

Run:

```bash
git diff -- src tests docs/superpowers/specs/2026-05-23-huitun-report-export-design.md docs/superpowers/plans/2026-05-23-huitun-report-export.md
```

Expected: diff only includes report/export code, tests, the spec update about de-duplicated final notes, and this implementation plan.

- [ ] **Step 6: Commit final checkpoint if authorized**

Run only if local commits are authorized and there are uncommitted changes:

```bash
git add src tests docs/superpowers/specs/2026-05-23-huitun-report-export-design.md docs/superpowers/plans/2026-05-23-huitun-report-export.md
git commit -m "feat: export Huitun collection results"
```

---

## Self-Review

**Spec coverage:**
- Latest or specified run report: Task 1 repository queries, Task 3 formatter, Task 4 command helper, Task 5 CLI dispatch.
- Latest or specified run CSV export: Task 1 export rows, Task 2 CSV serializer, Task 4 writer, Task 5 CLI dispatch.
- Final notes are not duplicated: Task 1 `row_number()` query and repository test.
- No scraping changes: all tasks avoid `src/browser/`.
- Output parent directory must exist: Task 4 command helper test and implementation.
- Tests and typecheck: Task 6.

**Placeholder scan:** No placeholder requirements remain in this plan. Each code-changing task includes concrete test code, implementation code, and verification commands.

**Type consistency:** Repository methods return the types defined in `src/reporting/types.ts`; CSV and report formatters consume those same types; CLI option parsers return `ReportCommandOptions` and `ExportCommandOptions` from `src/reporting/commands.ts`.

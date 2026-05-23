# Huitun SQLite MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local CLI collector that follows the verified Huitun hot-word workflow and stores hot words, hot-word snapshots, note rows, and note-detail metrics in SQLite.

**Architecture:** The CLI orchestrates one serial browser session connected through Chrome DevTools Protocol, because Huitun uses logged-in browser state and encrypted APIs. Browser modules extract rendered DOM into typed records; database modules own SQLite schema creation and idempotent upserts; tests focus on deterministic parsing and database behavior.

**Tech Stack:** Node.js 22+, TypeScript, Node built-in `node:sqlite`, `playwright-core` over CDP, `commander`, `vitest`, `tsx`.

---

## Implementation Notes

- Current project directory: `E:/小红书`.
- Current directory is not a git repository, so this plan does not require commit steps. If the directory is later initialized as git, commit after each completed task using the files listed in that task.
- Do not store cookies, tokens, passwords, or exported Huitun private data in code.
- Default database path: `data/xhs-ops.sqlite`.
- Default CDP endpoint: `http://127.0.0.1:9222`.
- First verification keyword: `浴缸`.

## File Structure

Create these files:

```text
package.json
tsconfig.json
vitest.config.ts
src/types.ts
src/utils/number.ts
src/db/client.ts
src/db/schema.ts
src/db/repositories.ts
src/browser/huitun-session.ts
src/browser/hotword-search.ts
src/browser/hotword-detail.ts
src/browser/note-detail.ts
src/cli.ts
tests/number.test.ts
tests/db.test.ts
tests/hotword-search-parser.test.ts
tests/note-list-parser.test.ts
```

Responsibilities:

- `src/types.ts`: Shared data shapes for hot words, snapshots, note rows, note details, run status, and CLI options.
- `src/utils/number.ts`: Convert Huitun display numbers such as `1.4w`, `1,317`, and `16.4w` into normalized numeric values.
- `src/db/client.ts`: Open SQLite with `DatabaseSync` and ensure the parent directory exists.
- `src/db/schema.ts`: Create tables and indexes.
- `src/db/repositories.ts`: Insert/update collection runs, hot words, snapshots, notes, and raw snapshots.
- `src/browser/huitun-session.ts`: Connect to an existing browser via CDP, create/close pages, navigate safely.
- `src/browser/hotword-search.ts`: Open hot-word search, submit keyword, parse hot-word table.
- `src/browser/hotword-detail.ts`: Open hot-word detail route, parse overview and note list.
- `src/browser/note-detail.ts`: Open a note detail modal, parse extra fields, close modal.
- `src/cli.ts`: Parse command arguments and orchestrate the collector.
- `tests/*.test.ts`: Unit tests for parsing and database idempotency.

---

### Task 1: Project Scaffold

**Files:**
- Create: `package.json`
- Create: `tsconfig.json`
- Create: `vitest.config.ts`

- [ ] **Step 1: Create `package.json`**

```json
{
  "name": "xhs-ops-collector",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "collect": "node --no-warnings ./node_modules/tsx/dist/cli.mjs src/cli.ts",
    "test": "node --no-warnings ./node_modules/vitest/vitest.mjs run --passWithNoTests",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "commander": "^13.1.0",
    "playwright-core": "^1.52.0"
  },
  "devDependencies": {
    "@types/node": "^22.15.21",
    "tsx": "^4.19.4",
    "typescript": "^5.8.3",
    "vitest": "^3.1.4"
  }
}
```

- [ ] **Step 2: Create `tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "strict": true,
    "esModuleInterop": true,
    "forceConsistentCasingInFileNames": true,
    "skipLibCheck": true,
    "types": ["node", "vitest/globals"],
    "outDir": "dist"
  },
  "include": ["vitest.config.ts", "src/**/*.ts", "tests/**/*.ts"]
}
```

- [ ] **Step 3: Create `vitest.config.ts`**

```ts
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    include: ['tests/**/*.test.ts'],
    environment: 'node'
  }
});
```

- [ ] **Step 4: Install dependencies**

Run:

```bash
npm install
```

Expected: `node_modules/` and `package-lock.json` are created, and npm exits with code 0.

- [ ] **Step 5: Run baseline checks**

Run:

```bash
npm run typecheck
npm test
```

Expected: typecheck passes; `npm test` exits 0 before test files exist because the script uses Vitest's `--passWithNoTests` scaffold baseline.

---

### Task 2: Shared Types and Number Parser

**Files:**
- Create: `src/types.ts`
- Create: `src/utils/number.ts`
- Create: `tests/number.test.ts`

- [ ] **Step 1: Write number parser tests**

Create `tests/number.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { parseHuitunNumber } from '../src/utils/number.js';

describe('parseHuitunNumber', () => {
  it('parses blank and dash values as null', () => {
    expect(parseHuitunNumber('')).toBeNull();
    expect(parseHuitunNumber('--')).toBeNull();
    expect(parseHuitunNumber('暂无')).toBeNull();
  });

  it('parses comma separated integers', () => {
    expect(parseHuitunNumber('1,317')).toBe(1317);
    expect(parseHuitunNumber('10')).toBe(10);
  });

  it('parses w suffix as ten-thousands', () => {
    expect(parseHuitunNumber('1.4w')).toBe(14000);
    expect(parseHuitunNumber('16.4w')).toBe(164000);
    expect(parseHuitunNumber('1984.6w')).toBe(19846000);
  });

  it('parses Chinese 万 suffix as ten-thousands', () => {
    expect(parseHuitunNumber('1.4万')).toBe(14000);
    expect(parseHuitunNumber('120.9万')).toBe(1209000);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
npm test -- tests/number.test.ts
```

Expected: FAIL because `src/utils/number.ts` does not exist.

- [ ] **Step 3: Create shared types**

Create `src/types.ts`:

```ts
export type RunStatus = 'running' | 'success' | 'partial_success' | 'failed';

export interface CollectorOptions {
  keyword: string;
  limitHotwords: number;
  limitNotes: number;
  days: 7 | 30 | 90 | 180;
  dbPath: string;
  cdpUrl: string;
  headless: boolean;
}

export interface CollectionRunInput {
  keyword: string;
  days: number;
  limitHotwords: number;
  limitNotes: number;
}

export interface HotWordRow {
  sourceKeyword: string;
  word: string;
  hotValueText: string | null;
  hotValueNumber: number | null;
  noteCount: number | null;
  interactionText: string | null;
  interactionNumber: number | null;
  categories: Array<{ label: string; rate: string | null }>;
  rankIndex: number;
}

export interface HotWordSnapshot {
  word: string;
  days: number;
  pageUrl: string;
  heatText: string | null;
  relatedNotesText: string | null;
  totalInteractionsText: string | null;
  overview: Record<string, string>;
}

export interface NoteListRow {
  hotWord: string;
  huitunNoteKey: string;
  title: string;
  authorName: string | null;
  authorLevel: string | null;
  coverUrl: string | null;
  isVideo: boolean;
  videoDuration: string | null;
  publishedAt: string | null;
  updatedAt: string | null;
  tags: string[];
  estimatedReads: number | null;
  likes: number | null;
  collects: number | null;
  comments: number | null;
}

export interface NoteDetail {
  huitunNoteKey: string;
  estimatedExposure: number | null;
  estimatedReads: number | null;
  likes: number | null;
  collects: number | null;
  comments: number | null;
  shares: number | null;
  authorFollowers: number | null;
  authorNoteCount: number | null;
  authorTotalLikesCollects: number | null;
  readExposureRatioText: string | null;
  readFollowerRatioText: string | null;
}

export interface RawSnapshotInput {
  kind: string;
  objectKey: string;
  pageUrl: string;
  textContent: string;
  htmlContent: string | null;
}
```

- [ ] **Step 4: Implement number parser**

Create `src/utils/number.ts`:

```ts
export function parseHuitunNumber(value: string | null | undefined): number | null {
  if (value == null) return null;

  const normalized = value.trim().replace(/,/g, '');
  if (!normalized || normalized === '--' || normalized === '暂无') return null;

  const tenThousandMatch = normalized.match(/^(-?\d+(?:\.\d+)?)(w|万)$/i);
  if (tenThousandMatch) {
    return Math.round(Number(tenThousandMatch[1]) * 10000);
  }

  const numeric = Number(normalized);
  return Number.isFinite(numeric) ? numeric : null;
}
```

- [ ] **Step 5: Run parser tests**

Run:

```bash
npm test -- tests/number.test.ts
```

Expected: PASS.

- [ ] **Step 6: Run typecheck**

Run:

```bash
npm run typecheck
```

Expected: PASS.

---

### Task 3: SQLite Schema and Repositories

**Files:**
- Create: `src/db/client.ts`
- Create: `src/db/schema.ts`
- Create: `src/db/repositories.ts`
- Create: `tests/db.test.ts`

- [ ] **Step 1: Write database tests**

Create `tests/db.test.ts`:

```ts
import { mkdtempSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { openDatabase } from '../src/db/client.js';
import { initializeSchema } from '../src/db/schema.js';
import { CollectorRepository } from '../src/db/repositories.js';

let tempDir: string;
let dbPath: string;

beforeEach(() => {
  tempDir = mkdtempSync(join(tmpdir(), 'xhs-ops-db-'));
  dbPath = join(tempDir, 'test.sqlite');
});

afterEach(() => {
  rmSync(tempDir, { recursive: true, force: true });
});

describe('CollectorRepository', () => {
  it('creates a run and marks it successful', () => {
    const db = openDatabase(dbPath);
    initializeSchema(db);
    const repo = new CollectorRepository(db);

    const runId = repo.createRun({ keyword: '浴缸', days: 7, limitHotwords: 10, limitNotes: 20 });
    repo.finishRun(runId, 'success');

    const row = db.prepare('select keyword, status, days from collection_runs where id = ?').get(runId) as { keyword: string; status: string; days: number };
    expect(row).toEqual({ keyword: '浴缸', status: 'success', days: 7 });
    db.close();
  });

  it('upserts the same note without duplicating it', () => {
    const db = openDatabase(dbPath);
    initializeSchema(db);
    const repo = new CollectorRepository(db);
    const runId = repo.createRun({ keyword: '浴缸', days: 7, limitHotwords: 10, limitNotes: 20 });

    repo.upsertNote(runId, '浴缸', {
      hotWord: '浴缸',
      huitunNoteKey: '11331652220-2026-05-19 16:39:27',
      title: '给我看看你们的浴缸👀',
      authorName: '晚儿的装修碎碎念（杭州老破小版）',
      authorLevel: '路人',
      coverUrl: 'http://example.com/cover.webp',
      isVideo: false,
      videoDuration: null,
      publishedAt: '2026-05-19 16:39:27',
      updatedAt: '2026-05-21 10:57:10',
      tags: ['浴缸选择', '泡澡'],
      estimatedReads: 1317,
      likes: 8,
      collects: 2,
      comments: 41
    }, null);

    repo.upsertNote(runId, '浴缸', {
      hotWord: '浴缸',
      huitunNoteKey: '11331652220-2026-05-19 16:39:27',
      title: '给我看看你们的浴缸👀',
      authorName: '晚儿的装修碎碎念（杭州老破小版）',
      authorLevel: '路人',
      coverUrl: 'http://example.com/cover.webp',
      isVideo: false,
      videoDuration: null,
      publishedAt: '2026-05-19 16:39:27',
      updatedAt: '2026-05-21 10:57:10',
      tags: ['浴缸选择', '泡澡'],
      estimatedReads: 1500,
      likes: 9,
      collects: 3,
      comments: 42
    }, {
      huitunNoteKey: '11331652220-2026-05-19 16:39:27',
      estimatedExposure: 3000,
      estimatedReads: 1500,
      likes: 9,
      collects: 3,
      comments: 42,
      shares: 1,
      authorFollowers: 1000,
      authorNoteCount: 50,
      authorTotalLikesCollects: 2000,
      readExposureRatioText: '50%',
      readFollowerRatioText: '150%'
    });

    const count = db.prepare('select count(*) as count from notes').get() as { count: number };
    const row = db.prepare('select estimated_reads, shares from notes where huitun_note_key = ?').get('11331652220-2026-05-19 16:39:27') as { estimated_reads: number; shares: number };
    expect(count.count).toBe(1);
    expect(row).toEqual({ estimated_reads: 1500, shares: 1 });
    db.close();
  });
});
```

- [ ] **Step 2: Run database tests to verify they fail**

Run:

```bash
npm test -- tests/db.test.ts
```

Expected: FAIL because database modules do not exist.

- [ ] **Step 3: Implement database client**

Create `src/db/client.ts`:

```ts
import { mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
import { DatabaseSync } from 'node:sqlite';

export function openDatabase(dbPath: string): DatabaseSync {
  mkdirSync(dirname(dbPath), { recursive: true });
  const db = new DatabaseSync(dbPath);
  db.exec(`
    pragma journal_mode = WAL;
    pragma foreign_keys = ON;
  `);
  return db;
}
```

- [ ] **Step 4: Implement schema**

Create `src/db/schema.ts`:

```ts
import type { DatabaseSync } from 'node:sqlite';

export function initializeSchema(db: DatabaseSync): void {
  db.exec(`
    create table if not exists collection_runs (
      id integer primary key autoincrement,
      keyword text not null,
      days integer not null,
      limit_hotwords integer not null,
      limit_notes integer not null,
      status text not null,
      started_at text not null default (datetime('now')),
      finished_at text,
      error_stage text,
      error_message text
    );

    create table if not exists hot_words (
      id integer primary key autoincrement,
      run_id integer not null references collection_runs(id),
      source_keyword text not null,
      word text not null,
      hot_value_text text,
      hot_value_number integer,
      note_count integer,
      interaction_text text,
      interaction_number integer,
      categories_json text not null,
      rank_index integer not null,
      collected_at text not null default (datetime('now'))
    );

    create index if not exists idx_hot_words_run_id on hot_words(run_id);
    create index if not exists idx_hot_words_word on hot_words(word);

    create table if not exists hot_word_snapshots (
      id integer primary key autoincrement,
      run_id integer not null references collection_runs(id),
      word text not null,
      days integer not null,
      page_url text not null,
      heat_text text,
      related_notes_text text,
      total_interactions_text text,
      overview_json text not null,
      collected_at text not null default (datetime('now'))
    );

    create index if not exists idx_hot_word_snapshots_word on hot_word_snapshots(word);

    create table if not exists notes (
      id integer primary key autoincrement,
      run_id integer not null references collection_runs(id),
      source_keyword text not null,
      hot_word text not null,
      huitun_note_key text not null,
      title text not null,
      author_name text,
      author_level text,
      cover_url text,
      is_video integer not null,
      video_duration text,
      published_at text,
      updated_at text,
      tags_json text not null,
      estimated_exposure integer,
      estimated_reads integer,
      likes integer,
      collects integer,
      comments integer,
      shares integer,
      author_followers integer,
      author_note_count integer,
      author_total_likes_collects integer,
      read_exposure_ratio_text text,
      read_follower_ratio_text text,
      collected_at text not null default (datetime('now')),
      unique(huitun_note_key, published_at)
    );

    create index if not exists idx_notes_run_id on notes(run_id);
    create index if not exists idx_notes_hot_word on notes(hot_word);

    create table if not exists raw_snapshots (
      id integer primary key autoincrement,
      run_id integer not null references collection_runs(id),
      kind text not null,
      object_key text not null,
      page_url text not null,
      text_content text not null,
      html_content text,
      created_at text not null default (datetime('now'))
    );

    create index if not exists idx_raw_snapshots_run_id on raw_snapshots(run_id);
  `);
}
```

- [ ] **Step 5: Implement repositories**

Create `src/db/repositories.ts`:

```ts
import type { DatabaseSync } from 'node:sqlite';
import type { CollectionRunInput, HotWordRow, HotWordSnapshot, NoteDetail, NoteListRow, RawSnapshotInput, RunStatus } from '../types.js';

export class CollectorRepository {
  constructor(private readonly db: DatabaseSync) {}

  createRun(input: CollectionRunInput): number {
    const result = this.db.prepare(`
      insert into collection_runs (keyword, days, limit_hotwords, limit_notes, status)
      values (?, ?, ?, ?, 'running')
    `).run(input.keyword, input.days, input.limitHotwords, input.limitNotes);
    return Number(result.lastInsertRowid);
  }

  finishRun(runId: number, status: RunStatus, errorStage?: string, errorMessage?: string): void {
    this.db.prepare(`
      update collection_runs
      set status = ?, finished_at = datetime('now'), error_stage = ?, error_message = ?
      where id = ?
    `).run(status, errorStage ?? null, errorMessage ?? null, runId);
  }

  insertHotWords(runId: number, rows: HotWordRow[]): void {
    const stmt = this.db.prepare(`
      insert into hot_words (
        run_id, source_keyword, word, hot_value_text, hot_value_number, note_count,
        interaction_text, interaction_number, categories_json, rank_index
      ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `);

    this.db.exec('begin');
    try {
      for (const row of rows) {
        stmt.run(
          runId,
          row.sourceKeyword,
          row.word,
          row.hotValueText,
          row.hotValueNumber,
          row.noteCount,
          row.interactionText,
          row.interactionNumber,
          JSON.stringify(row.categories),
          row.rankIndex
        );
      }
      this.db.exec('commit');
    } catch (error) {
      this.db.exec('rollback');
      throw error;
    }
  }

  insertHotWordSnapshot(runId: number, snapshot: HotWordSnapshot): void {
    this.db.prepare(`
      insert into hot_word_snapshots (
        run_id, word, days, page_url, heat_text, related_notes_text,
        total_interactions_text, overview_json
      ) values (?, ?, ?, ?, ?, ?, ?, ?)
    `).run(
      runId,
      snapshot.word,
      snapshot.days,
      snapshot.pageUrl,
      snapshot.heatText,
      snapshot.relatedNotesText,
      snapshot.totalInteractionsText,
      JSON.stringify(snapshot.overview)
    );
  }

  upsertNote(runId: number, sourceKeyword: string, row: NoteListRow, detail: NoteDetail | null): void {
    this.db.prepare(`
      insert into notes (
        run_id, source_keyword, hot_word, huitun_note_key, title, author_name, author_level,
        cover_url, is_video, video_duration, published_at, updated_at, tags_json,
        estimated_exposure, estimated_reads, likes, collects, comments, shares,
        author_followers, author_note_count, author_total_likes_collects,
        read_exposure_ratio_text, read_follower_ratio_text, collected_at
      ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
      on conflict(huitun_note_key, published_at) do update set
        run_id = excluded.run_id,
        source_keyword = excluded.source_keyword,
        hot_word = excluded.hot_word,
        title = excluded.title,
        author_name = excluded.author_name,
        author_level = excluded.author_level,
        cover_url = excluded.cover_url,
        is_video = excluded.is_video,
        video_duration = excluded.video_duration,
        updated_at = excluded.updated_at,
        tags_json = excluded.tags_json,
        estimated_exposure = excluded.estimated_exposure,
        estimated_reads = excluded.estimated_reads,
        likes = excluded.likes,
        collects = excluded.collects,
        comments = excluded.comments,
        shares = excluded.shares,
        author_followers = excluded.author_followers,
        author_note_count = excluded.author_note_count,
        author_total_likes_collects = excluded.author_total_likes_collects,
        read_exposure_ratio_text = excluded.read_exposure_ratio_text,
        read_follower_ratio_text = excluded.read_follower_ratio_text,
        collected_at = datetime('now')
    `).run(
      runId,
      sourceKeyword,
      row.hotWord,
      row.huitunNoteKey,
      row.title,
      row.authorName,
      row.authorLevel,
      row.coverUrl,
      row.isVideo ? 1 : 0,
      row.videoDuration,
      row.publishedAt,
      row.updatedAt,
      JSON.stringify(row.tags),
      detail?.estimatedExposure ?? null,
      detail?.estimatedReads ?? row.estimatedReads,
      detail?.likes ?? row.likes,
      detail?.collects ?? row.collects,
      detail?.comments ?? row.comments,
      detail?.shares ?? null,
      detail?.authorFollowers ?? null,
      detail?.authorNoteCount ?? null,
      detail?.authorTotalLikesCollects ?? null,
      detail?.readExposureRatioText ?? null,
      detail?.readFollowerRatioText ?? null
    );
  }

  insertRawSnapshot(runId: number, snapshot: RawSnapshotInput): void {
    this.db.prepare(`
      insert into raw_snapshots (run_id, kind, object_key, page_url, text_content, html_content)
      values (?, ?, ?, ?, ?, ?)
    `).run(runId, snapshot.kind, snapshot.objectKey, snapshot.pageUrl, snapshot.textContent, snapshot.htmlContent);
  }
}
```

- [ ] **Step 6: Run database tests**

Run:

```bash
npm test -- tests/db.test.ts
```

Expected: PASS.

- [ ] **Step 7: Run typecheck**

Run:

```bash
npm run typecheck
```

Expected: PASS.

---

### Task 4: Hot Word Search Parser

**Files:**
- Create: `src/browser/hotword-search.ts`
- Create: `tests/hotword-search-parser.test.ts`

- [ ] **Step 1: Write parser tests**

Create `tests/hotword-search-parser.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { parseHotWordRowsFromCells } from '../src/browser/hotword-search.js';

describe('parseHotWordRowsFromCells', () => {
  it('parses Huitun hot-word table cells', () => {
    const rows = parseHotWordRowsFromCells('浴缸', [
      ['浴缸', '1,510', '26', '1.4w', '家居家装 36.4%\n摄影 36.4%\n兴趣爱好 9.1%'],
      ['自砌浴缸', '912', '2', '8,920', '家居家装 100%'],
      ['酒店带浴缸', '23', '1', '226', '--']
    ]);

    expect(rows).toEqual([
      {
        sourceKeyword: '浴缸',
        word: '浴缸',
        hotValueText: '1,510',
        hotValueNumber: 1510,
        noteCount: 26,
        interactionText: '1.4w',
        interactionNumber: 14000,
        categories: [
          { label: '家居家装', rate: '36.4' },
          { label: '摄影', rate: '36.4' },
          { label: '兴趣爱好', rate: '9.1' }
        ],
        rankIndex: 1
      },
      {
        sourceKeyword: '浴缸',
        word: '自砌浴缸',
        hotValueText: '912',
        hotValueNumber: 912,
        noteCount: 2,
        interactionText: '8,920',
        interactionNumber: 8920,
        categories: [{ label: '家居家装', rate: '100' }],
        rankIndex: 2
      },
      {
        sourceKeyword: '浴缸',
        word: '酒店带浴缸',
        hotValueText: '23',
        hotValueNumber: 23,
        noteCount: 1,
        interactionText: '226',
        interactionNumber: 226,
        categories: [],
        rankIndex: 3
      }
    ]);
  });
});
```

- [ ] **Step 2: Run parser test to verify it fails**

Run:

```bash
npm test -- tests/hotword-search-parser.test.ts
```

Expected: FAIL because `src/browser/hotword-search.ts` does not exist.

- [ ] **Step 3: Implement hot-word parser and browser collector**

Create `src/browser/hotword-search.ts`:

```ts
import type { Page } from 'playwright-core';
import type { HotWordRow } from '../types.js';
import { parseHuitunNumber } from '../utils/number.js';

const SEARCH_URL = 'https://xhs.huitun.com/#/hotWords/hot_words_recommend';

function parseCategoryLines(value: string): Array<{ label: string; rate: string | null }> {
  if (!value || value.trim() === '--') return [];
  return value
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const match = line.match(/^(.+?)\s+(\d+(?:\.\d+)?)%$/);
      if (!match) return { label: line, rate: null };
      return { label: match[1].trim(), rate: match[2] };
    });
}

export function parseHotWordRowsFromCells(sourceKeyword: string, tableRows: string[][]): HotWordRow[] {
  return tableRows
    .filter((cells) => cells.length >= 5 && cells[0].trim())
    .map((cells, index) => {
      const hotValueText = cells[1]?.trim() || null;
      const interactionText = cells[3]?.trim() || null;
      return {
        sourceKeyword,
        word: cells[0].trim(),
        hotValueText,
        hotValueNumber: parseHuitunNumber(hotValueText),
        noteCount: parseHuitunNumber(cells[2]) ?? null,
        interactionText,
        interactionNumber: parseHuitunNumber(interactionText),
        categories: parseCategoryLines(cells[4] ?? ''),
        rankIndex: index + 1
      };
    });
}

export async function collectHotWordRows(page: Page, keyword: string, limitHotwords: number): Promise<HotWordRow[]> {
  await page.goto(SEARCH_URL, { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle', { timeout: 30_000 }).catch(() => undefined);

  const input = page.getByPlaceholder('请输入热词关键词');
  await input.waitFor({ timeout: 30_000 });
  await input.fill(keyword);
  await input.press('Enter');

  await page.waitForURL(/hot_words_search/, { timeout: 30_000 });
  await page.waitForSelector('tr.ant-table-row', { timeout: 30_000 });

  const tableRows = await page.locator('tr.ant-table-row').evaluateAll((rows) => rows.map((row) =>
    Array.from(row.querySelectorAll('td')).map((cell) => (cell.textContent ?? '').trim())
  ));

  return parseHotWordRowsFromCells(keyword, tableRows).slice(0, limitHotwords);
}
```

- [ ] **Step 4: Run parser tests**

Run:

```bash
npm test -- tests/hotword-search-parser.test.ts tests/number.test.ts
```

Expected: PASS.

- [ ] **Step 5: Run typecheck**

Run:

```bash
npm run typecheck
```

Expected: PASS.

---

### Task 5: Hot Word Detail and Note List Parser

**Files:**
- Create: `src/browser/hotword-detail.ts`
- Create: `tests/note-list-parser.test.ts`

- [ ] **Step 1: Write note-list parser tests**

Create `tests/note-list-parser.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { parseNoteRowsFromDomPayload } from '../src/browser/hotword-detail.js';

describe('parseNoteRowsFromDomPayload', () => {
  it('parses note list rows from Huitun detail table payload', () => {
    const rows = parseNoteRowsFromDomPayload('浴缸', [
      {
        key: '11331652220-2026-05-19 16:39:27',
        title: '给我看看你们的浴缸👀',
        authorName: '晚儿的装修碎碎念（杭州老破小版）',
        authorLevel: '路人',
        coverUrl: 'http://example.com/cover.webp',
        duration: null,
        updatedText: '更新时间：2026-05-21 10:57:10',
        tags: ['浴缸选择', '泡澡', '更多...'],
        cells: ['给我看看你们的浴缸👀\n晚儿的装修碎碎念（杭州老破小版）\n路人', '2026-05-19 16:39:27', '1,317', '8', '2', '41']
      },
      {
        key: '11304858949-2026-05-15 16:39:22',
        title: '瀑布按摩浴缸',
        authorName: '浴缸蒸汽房佛山源头厂家',
        authorLevel: '路人',
        coverUrl: 'http://example.com/video.webp',
        duration: '00:32',
        updatedText: '更新时间：2026-05-21 10:49:35',
        tags: ['浴缸源头厂家', '浴缸工厂'],
        cells: ['00:32\n瀑布按摩浴缸\n浴缸蒸汽房佛山源头厂家\n路人', '2026-05-15 16:39:22', '10', '1', '0', '0']
      }
    ]);

    expect(rows).toEqual([
      {
        hotWord: '浴缸',
        huitunNoteKey: '11331652220-2026-05-19 16:39:27',
        title: '给我看看你们的浴缸👀',
        authorName: '晚儿的装修碎碎念（杭州老破小版）',
        authorLevel: '路人',
        coverUrl: 'http://example.com/cover.webp',
        isVideo: false,
        videoDuration: null,
        publishedAt: '2026-05-19 16:39:27',
        updatedAt: '2026-05-21 10:57:10',
        tags: ['浴缸选择', '泡澡'],
        estimatedReads: 1317,
        likes: 8,
        collects: 2,
        comments: 41
      },
      {
        hotWord: '浴缸',
        huitunNoteKey: '11304858949-2026-05-15 16:39:22',
        title: '瀑布按摩浴缸',
        authorName: '浴缸蒸汽房佛山源头厂家',
        authorLevel: '路人',
        coverUrl: 'http://example.com/video.webp',
        isVideo: true,
        videoDuration: '00:32',
        publishedAt: '2026-05-15 16:39:22',
        updatedAt: '2026-05-21 10:49:35',
        tags: ['浴缸源头厂家', '浴缸工厂'],
        estimatedReads: 10,
        likes: 1,
        collects: 0,
        comments: 0
      }
    ]);
  });
});
```

- [ ] **Step 2: Run note-list parser test to verify it fails**

Run:

```bash
npm test -- tests/note-list-parser.test.ts
```

Expected: FAIL because `src/browser/hotword-detail.ts` does not exist.

- [ ] **Step 3: Implement hot-word detail parser and browser collector**

Create `src/browser/hotword-detail.ts`:

```ts
import type { Page } from 'playwright-core';
import type { HotWordSnapshot, NoteListRow } from '../types.js';
import { parseHuitunNumber } from '../utils/number.js';

export interface NoteDomPayload {
  key: string;
  title: string;
  authorName: string | null;
  authorLevel: string | null;
  coverUrl: string | null;
  duration: string | null;
  updatedText: string | null;
  tags: string[];
  cells: string[];
}

function stripLabel(value: string | null, label: string): string | null {
  if (!value) return null;
  const trimmed = value.trim();
  return trimmed.startsWith(label) ? trimmed.slice(label.length).trim() : trimmed;
}

export function parseNoteRowsFromDomPayload(hotWord: string, payloads: NoteDomPayload[]): NoteListRow[] {
  return payloads.map((payload) => ({
    hotWord,
    huitunNoteKey: payload.key,
    title: payload.title,
    authorName: payload.authorName,
    authorLevel: payload.authorLevel,
    coverUrl: payload.coverUrl,
    isVideo: Boolean(payload.duration),
    videoDuration: payload.duration,
    publishedAt: payload.cells[1]?.trim() || null,
    updatedAt: stripLabel(payload.updatedText, '更新时间：'),
    tags: payload.tags.filter((tag) => tag !== '更多...'),
    estimatedReads: parseHuitunNumber(payload.cells[2]),
    likes: parseHuitunNumber(payload.cells[3]),
    collects: parseHuitunNumber(payload.cells[4]),
    comments: parseHuitunNumber(payload.cells[5])
  }));
}

function dateRangeForDays(days: number): { startDate: string; endDate: string } {
  const end = new Date();
  const start = new Date(end);
  start.setDate(end.getDate() - days);
  const format = (date: Date) => date.toISOString().slice(0, 10);
  return { startDate: format(start), endDate: format(end) };
}

export async function openHotWordDetail(page: Page, hotWord: string): Promise<void> {
  const url = `https://xhs.huitun.com/#/hotWords/hot_word_detail?hotWord=${encodeURIComponent(hotWord)}`;
  await page.goto(url, { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle', { timeout: 30_000 }).catch(() => undefined);
  await page.waitForSelector('tr.ant-table-row', { timeout: 30_000 });
}

export async function collectHotWordSnapshot(page: Page, hotWord: string, days: number): Promise<HotWordSnapshot> {
  const text = await page.locator('body').innerText();
  const lines = text.split('\n').map((line) => line.trim()).filter(Boolean);
  const overview: Record<string, string> = {};

  for (let index = 0; index < lines.length - 1; index += 1) {
    const current = lines[index];
    const next = lines[index + 1];
    if (['热度值', '关联笔记数', '互动总量', '平均互动量', '平均点赞', '平均收藏', '平均评论', '平均分享'].includes(next)) {
      overview[next] = current;
    }
  }

  return {
    word: hotWord,
    days,
    pageUrl: page.url(),
    heatText: overview['热度值'] ?? null,
    relatedNotesText: overview['关联笔记数'] ?? null,
    totalInteractionsText: overview['互动总量'] ?? null,
    overview
  };
}

export async function collectNoteRows(page: Page, hotWord: string, limitNotes: number): Promise<NoteListRow[]> {
  const payloads = await page.locator('tr.ant-table-row').evaluateAll((rows) => rows.map((row) => {
    const cells = Array.from(row.querySelectorAll('td')).map((cell) => (cell.textContent ?? '').trim());
    const title = (row.querySelector('[class*="note_title"]')?.textContent ?? '').trim();
    const authorName = (row.querySelector('[class*="live_anchor"] [class*="one_line"]')?.textContent ?? '').trim() || null;
    const authorLevel = (row.querySelector('[class*="live_anchor"] span[style*="137"]')?.textContent ?? '').trim() || null;
    const images = Array.from(row.querySelectorAll('img')).map((img) => (img as HTMLImageElement).src).filter(Boolean);
    const coverUrl = images.find((src) => src.includes('xhscdn.com') && !src.includes('avatar')) ?? null;
    const duration = (row.querySelector('[class*="duration"] span')?.textContent ?? '').trim() || null;
    const updatedText = Array.from(row.querySelectorAll('div')).map((div) => (div.textContent ?? '').trim()).find((value) => value.startsWith('更新时间：')) ?? null;
    const tags = Array.from(row.querySelectorAll('[class*="item_tag"]')).map((tag) => (tag.textContent ?? '').trim()).filter(Boolean);
    return {
      key: row.getAttribute('data-row-key') ?? '',
      title,
      authorName,
      authorLevel,
      coverUrl,
      duration,
      updatedText,
      tags,
      cells
    };
  }));

  return parseNoteRowsFromDomPayload(hotWord, payloads).slice(0, limitNotes);
}

export function getDetailUrlForDebug(hotWord: string, days: number): string {
  const { startDate, endDate } = dateRangeForDays(days);
  return `https://xhs.huitun.com/#/hotWords/hot_word_detail?hotWord=${encodeURIComponent(hotWord)}&startDate=${startDate}&endDate=${endDate}`;
}
```

- [ ] **Step 4: Run parser tests**

Run:

```bash
npm test -- tests/note-list-parser.test.ts tests/number.test.ts
```

Expected: PASS.

- [ ] **Step 5: Run typecheck**

Run:

```bash
npm run typecheck
```

Expected: PASS.

---

### Task 6: Browser Session and Note Detail Modal

**Files:**
- Create: `src/browser/huitun-session.ts`
- Create: `src/browser/note-detail.ts`

- [ ] **Step 1: Implement browser session**

Create `src/browser/huitun-session.ts`:

```ts
import { chromium, type Browser, type BrowserContext, type Page } from 'playwright-core';

export interface HuitunSession {
  browser: Browser;
  context: BrowserContext;
  page: Page;
  close: () => Promise<void>;
}

export async function createHuitunSession(cdpUrl: string): Promise<HuitunSession> {
  let browser: Browser;
  try {
    browser = await chromium.connectOverCDP(cdpUrl);
  } catch (error) {
    throw new Error(`无法连接浏览器 CDP：${cdpUrl}。请先启动带 remote debugging 的 Edge/Chrome，再重试。原始错误：${String(error)}`);
  }

  const context = browser.contexts()[0] ?? await browser.newContext();
  const page = await context.newPage();
  page.setDefaultTimeout(30_000);

  return {
    browser,
    context,
    page,
    close: async () => {
      await page.close().catch(() => undefined);
      await browser.close().catch(() => undefined);
    }
  };
}

export async function capturePageSnapshot(page: Page): Promise<{ url: string; text: string; html: string }> {
  return {
    url: page.url(),
    text: await page.locator('body').innerText().catch(() => ''),
    html: await page.content().catch(() => '')
  };
}
```

- [ ] **Step 2: Implement note detail modal parser**

Create `src/browser/note-detail.ts`:

```ts
import type { Page } from 'playwright-core';
import type { NoteDetail, NoteListRow } from '../types.js';
import { parseHuitunNumber } from '../utils/number.js';

function valueBeforeLabel(lines: string[], label: string): string | null {
  const index = lines.findIndex((line) => line === label);
  if (index <= 0) return null;
  return lines[index - 1] ?? null;
}

function normalizeLines(text: string): string[] {
  return text.split('\n').map((line) => line.trim()).filter(Boolean);
}

export function parseNoteDetailText(huitunNoteKey: string, text: string): NoteDetail {
  const lines = normalizeLines(text);
  return {
    huitunNoteKey,
    estimatedExposure: parseHuitunNumber(valueBeforeLabel(lines, '预估曝光量')),
    estimatedReads: parseHuitunNumber(valueBeforeLabel(lines, '预估阅读量')),
    likes: parseHuitunNumber(valueBeforeLabel(lines, '点赞')),
    collects: parseHuitunNumber(valueBeforeLabel(lines, '收藏')),
    comments: parseHuitunNumber(valueBeforeLabel(lines, '评论')),
    shares: parseHuitunNumber(valueBeforeLabel(lines, '分享')),
    authorFollowers: parseHuitunNumber(valueBeforeLabel(lines, '粉丝数')),
    authorNoteCount: parseHuitunNumber(valueBeforeLabel(lines, '笔记数')),
    authorTotalLikesCollects: parseHuitunNumber(valueBeforeLabel(lines, '赞藏总数')),
    readExposureRatioText: valueBeforeLabel(lines, '阅读曝光比'),
    readFollowerRatioText: valueBeforeLabel(lines, '阅读粉丝比')
  };
}

export async function collectNoteDetail(page: Page, note: NoteListRow): Promise<NoteDetail | null> {
  const rows = page.locator('tr.ant-table-row');
  const count = await rows.count();

  for (let index = 0; index < count; index += 1) {
    const row = rows.nth(index);
    const key = await row.getAttribute('data-row-key');
    if (key !== note.huitunNoteKey) continue;

    const title = row.locator('[class*="note_title"]').first();
    await title.click();
    const modal = page.locator('.ant-modal').filter({ hasText: '数据概览' }).last();
    await modal.waitFor({ timeout: 30_000 });
    const text = await modal.innerText();
    const detail = parseNoteDetailText(note.huitunNoteKey, text);
    await page.keyboard.press('Escape');
    await modal.waitFor({ state: 'hidden', timeout: 10_000 }).catch(() => undefined);
    return detail;
  }

  return null;
}
```

- [ ] **Step 3: Add parser test for note detail text**

Append to `tests/note-list-parser.test.ts`:

```ts
import { parseNoteDetailText } from '../src/browser/note-detail.js';

describe('parseNoteDetailText', () => {
  it('parses note detail modal metrics', () => {
    const detail = parseNoteDetailText('11304858949-2026-05-15 16:39:22', `
00:32
瀑布按摩浴缸
查看笔记
10
1
0
0
0
达人主页
发布时间：2026-05-15 16:39:22
浴缸蒸汽房佛山源头厂家
路人
176
粉丝数
113
笔记数
337
赞藏总数
基础数据
更新于：2026-05-21 10:49:35
数据概览
379
预估曝光量
10
预估阅读量
1
点赞
0
收藏
0
评论
0
分享
2.64%
阅读曝光比
5.68%
阅读粉丝比
`);

    expect(detail).toEqual({
      huitunNoteKey: '11304858949-2026-05-15 16:39:22',
      estimatedExposure: 379,
      estimatedReads: 10,
      likes: 1,
      collects: 0,
      comments: 0,
      shares: 0,
      authorFollowers: 176,
      authorNoteCount: 113,
      authorTotalLikesCollects: 337,
      readExposureRatioText: '2.64%',
      readFollowerRatioText: '5.68%'
    });
  });
});
```

- [ ] **Step 4: Run parser tests**

Run:

```bash
npm test -- tests/note-list-parser.test.ts
```

Expected: PASS.

- [ ] **Step 5: Run typecheck**

Run:

```bash
npm run typecheck
```

Expected: PASS.

---

### Task 7: CLI Orchestration

**Files:**
- Create: `src/cli.ts`

- [ ] **Step 1: Implement CLI argument parsing and collector orchestration**

Create `src/cli.ts`:

```ts
import { Command } from 'commander';
import { openDatabase } from './db/client.js';
import { initializeSchema } from './db/schema.js';
import { CollectorRepository } from './db/repositories.js';
import { createHuitunSession, capturePageSnapshot } from './browser/huitun-session.js';
import { collectHotWordRows } from './browser/hotword-search.js';
import { collectHotWordSnapshot, collectNoteRows, openHotWordDetail } from './browser/hotword-detail.js';
import { collectNoteDetail } from './browser/note-detail.js';
import type { CollectorOptions, RunStatus } from './types.js';

function parsePositiveInt(value: string, name: string): number {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed <= 0) {
    throw new Error(`${name} 必须是正整数，收到：${value}`);
  }
  return parsed;
}

function parseDays(value: string): 7 | 30 | 90 | 180 {
  const parsed = Number(value);
  if (parsed === 7 || parsed === 30 || parsed === 90 || parsed === 180) return parsed;
  throw new Error(`--days 只支持 7、30、90、180，收到：${value}`);
}

function parseOptions(): CollectorOptions {
  const program = new Command();
  program
    .requiredOption('--keyword <keyword>', '业务关键词，例如：浴缸')
    .option('--limit-hotwords <number>', '最多采集热词数量', '10')
    .option('--limit-notes <number>', '每个热词最多采集笔记数量', '20')
    .option('--days <days>', '热词详情时间范围：7、30、90、180', '7')
    .option('--db-path <path>', 'SQLite 数据库路径', 'data/xhs-ops.sqlite')
    .option('--cdp-url <url>', 'Chrome DevTools Protocol 地址', 'http://127.0.0.1:9222')
    .option('--headless', '保留参数，当前 CDP 登录态模式不启动新浏览器', false)
    .parse(process.argv);

  const options = program.opts();
  return {
    keyword: String(options.keyword).trim(),
    limitHotwords: parsePositiveInt(options.limitHotwords, '--limit-hotwords'),
    limitNotes: parsePositiveInt(options.limitNotes, '--limit-notes'),
    days: parseDays(options.days),
    dbPath: String(options.dbPath),
    cdpUrl: String(options.cdpUrl),
    headless: Boolean(options.headless)
  };
}

async function main(): Promise<void> {
  const options = parseOptions();
  const db = openDatabase(options.dbPath);
  initializeSchema(db);
  const repo = new CollectorRepository(db);
  const runId = repo.createRun({
    keyword: options.keyword,
    days: options.days,
    limitHotwords: options.limitHotwords,
    limitNotes: options.limitNotes
  });

  let status: RunStatus = 'success';
  let session: Awaited<ReturnType<typeof createHuitunSession>> | null = null;
  let hotWordCount = 0;
  let noteCount = 0;
  let detailCount = 0;

  try {
    session = await createHuitunSession(options.cdpUrl);
    const { page } = session;

    const hotWords = await collectHotWordRows(page, options.keyword, options.limitHotwords);
    hotWordCount = hotWords.length;
    repo.insertHotWords(runId, hotWords);

    for (const hotWord of hotWords) {
      try {
        await openHotWordDetail(page, hotWord.word);
        const snapshot = await collectHotWordSnapshot(page, hotWord.word, options.days);
        repo.insertHotWordSnapshot(runId, snapshot);

        const notes = await collectNoteRows(page, hotWord.word, options.limitNotes);
        noteCount += notes.length;

        for (const note of notes) {
          let detail = null;
          try {
            detail = await collectNoteDetail(page, note);
            if (detail) detailCount += 1;
          } catch (error) {
            status = 'partial_success';
            const snap = await capturePageSnapshot(page);
            repo.insertRawSnapshot(runId, {
              kind: 'parse_note_detail_error',
              objectKey: note.huitunNoteKey,
              pageUrl: snap.url,
              textContent: `${String(error)}\n\n${snap.text}`,
              htmlContent: snap.html
            });
          }

          repo.upsertNote(runId, options.keyword, note, detail);
        }
      } catch (error) {
        status = 'partial_success';
        const snap = await capturePageSnapshot(page);
        repo.insertRawSnapshot(runId, {
          kind: 'hot_word_detail_error',
          objectKey: hotWord.word,
          pageUrl: snap.url,
          textContent: `${String(error)}\n\n${snap.text}`,
          htmlContent: snap.html
        });
      }
    }

    repo.finishRun(runId, status);
    console.log(JSON.stringify({ runId, status, hotWordCount, noteCount, detailCount, dbPath: options.dbPath }, null, 2));
  } catch (error) {
    repo.finishRun(runId, 'failed', 'collector', String(error));
    throw error;
  } finally {
    await session?.close();
    db.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
```

- [ ] **Step 2: Run all tests**

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

---

### Task 8: Manual Huitun Verification

**Files:**
- Uses: `src/cli.ts`
- Writes runtime data: `data/xhs-ops.sqlite`

- [ ] **Step 1: Confirm browser CDP is available**

Run:

```bash
node "C:/Users/Administrator/.claude/skills/web-access/scripts/check-deps.mjs"
```

Expected output contains:

```text
node: ok
browser: ok
proxy: ready
```

- [ ] **Step 2: Run the collector with a small sample**

Run:

```bash
npm run collect -- --keyword 浴缸 --limit-hotwords 1 --limit-notes 3 --days 7
```

Expected: Browser opens Huitun in a background tab, searches `浴缸`, opens one hot-word detail page, collects at least one note, then prints JSON similar to:

```json
{
  "runId": 1,
  "status": "success",
  "hotWordCount": 1,
  "noteCount": 3,
  "detailCount": 3,
  "dbPath": "data/xhs-ops.sqlite"
}
```

`status` may be `partial_success` if one note detail modal fails, but `hotWordCount` must be at least 1 and `noteCount` must be at least 1.

- [ ] **Step 3: Inspect SQLite counts**

Run:

```bash
NODE_NO_WARNINGS=1 node -e "const { DatabaseSync } = require('node:sqlite'); const db = new DatabaseSync('data/xhs-ops.sqlite'); console.log({runs: db.prepare('select count(*) c from collection_runs').get().c, hotWords: db.prepare('select count(*) c from hot_words').get().c, snapshots: db.prepare('select count(*) c from hot_word_snapshots').get().c, notes: db.prepare('select count(*) c from notes').get().c}); db.close();"
```

Expected: Output object has `runs >= 1`, `hotWords >= 1`, `snapshots >= 1`, `notes >= 1`.

- [ ] **Step 4: Run duplicate verification**

Run the same collector command again:

```bash
npm run collect -- --keyword 浴缸 --limit-hotwords 1 --limit-notes 3 --days 7
```

Then run:

```bash
NODE_NO_WARNINGS=1 node -e "const { DatabaseSync } = require('node:sqlite'); const db = new DatabaseSync('data/xhs-ops.sqlite'); console.log(db.prepare('select huitun_note_key, published_at, count(*) c from notes group by huitun_note_key, published_at having c > 1').all()); db.close();"
```

Expected:

```text
[]
```

- [ ] **Step 5: Run full MVP sample**

Run:

```bash
npm run collect -- --keyword 浴缸 --limit-hotwords 3 --limit-notes 10 --days 7
```

Expected: At least 5 hot-word rows across runs, at least 10 notes total, and at least 3 notes with detail fields populated.

- [ ] **Step 6: Inspect populated detail fields**

Run:

```bash
NODE_NO_WARNINGS=1 node -e "const { DatabaseSync } = require('node:sqlite'); const db = new DatabaseSync('data/xhs-ops.sqlite'); console.log(db.prepare('select title, author_followers, estimated_exposure, shares, read_exposure_ratio_text from notes where author_followers is not null or estimated_exposure is not null limit 5').all()); db.close();"
```

Expected: At least 3 rows show non-null `author_followers`, `estimated_exposure`, `shares`, or `read_exposure_ratio_text`.

---

## Self-Review

- Spec coverage: The plan covers project scaffold, typed parsing, SQLite schema, idempotent note upsert, browser CDP connection, hot-word search, hot-word detail, note detail modal, CLI orchestration, and manual verification using `浴缸`.
- Placeholder scan: No `TBD`, `TODO`, or vague implementation steps remain.
- Type consistency: `HotWordRow`, `HotWordSnapshot`, `NoteListRow`, `NoteDetail`, and repository methods are defined before use and referenced consistently across tasks.

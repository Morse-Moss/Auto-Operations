import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { DatabaseSync } from 'node:sqlite';
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

  it('runs schema migrations before reading an existing older database', () => {
    db.close();
    db = new DatabaseSync(dbPath);
    db.exec(`
      drop table notes;
      create table notes (
        id integer primary key autoincrement,
        run_id integer not null references collection_runs(id) on delete cascade,
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
        estimated_reads integer,
        likes integer,
        collects integer,
        comments integer,
        created_at text not null default current_timestamp,
        unique(huitun_note_key, published_at)
      );
    `);
    const result = db
      .prepare(`
        insert into collection_runs (keyword, days, limit_hotwords, limit_notes, status, finished_at)
        values ('护肤', 7, 3, 20, 'success', current_timestamp)
      `)
      .run();
    const runId = Number(result.lastInsertRowid);
    db
      .prepare(`
        insert into notes (
          run_id,
          source_keyword,
          hot_word,
          huitun_note_key,
          title,
          is_video,
          published_at,
          tags_json,
          likes,
          collects,
          comments
        ) values (?, '护肤', '早C晚A', 'note-legacy', '旧库笔记', 0, '2026-05-01', '["精华"]', 120, 30, 4)
      `)
      .run(runId);
    db.close();
    db = openDatabase(dbPath);

    const text = generateReportText({ dbPath });

    expect(text).toContain(`Run #${runId}`);
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

  it('exports an older database that contains duplicate null-date note identities', () => {
    db.close();
    db = new DatabaseSync(dbPath);
    db.exec('drop index idx_notes_stable_identity');
    const result = db
      .prepare(`
        insert into collection_runs (keyword, days, limit_hotwords, limit_notes, status, finished_at)
        values ('护肤', 7, 3, 20, 'success', current_timestamp)
      `)
      .run();
    const runId = Number(result.lastInsertRowid);
    db
      .prepare(`
        insert into notes (
          run_id,
          source_keyword,
          hot_word,
          huitun_note_key,
          title,
          is_video,
          published_at,
          tags_json,
          likes,
          list_likes,
          updated_record_at
        ) values
          (?, '护肤', '早C晚A', 'note-null-date', '旧记录', 0, null, '[]', 10, 10, '2026-05-01 00:00:00'),
          (?, '护肤', '早C晚A', 'note-null-date', '新记录', 0, null, '[]', 20, 20, '2026-05-02 00:00:00')
      `)
      .run(runId, runId);
    db.close();
    db = openDatabase(dbPath);
    const output = join(tempDir, 'legacy-duplicates.csv');

    expect(exportRunNotesToCsv({ dbPath, runId, output })).toMatchObject({ rowCount: 1 });
    expect(readFileSync(output, 'utf8')).toContain('新记录');
    expect(readFileSync(output, 'utf8')).not.toContain('旧记录');
  });

  it('fails when the output parent path is a file', () => {
    const runId = seedRun(repository);
    const outputParent = join(tempDir, 'not-a-directory');
    writeFileSync(outputParent, 'file', 'utf8');

    expect(() => exportRunNotesToCsv({ dbPath, runId, output: join(outputParent, 'notes.csv') })).toThrow(
      'Output directory does not exist:',
    );
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

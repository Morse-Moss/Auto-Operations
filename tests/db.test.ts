import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import type { DatabaseSync } from 'node:sqlite';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { openDatabase } from '../src/db/client.js';
import { CollectorRepository } from '../src/db/repositories.js';
import { initializeSchema } from '../src/db/schema.js';

interface CollectionRunRow {
  id: number;
  keyword: string;
  days: number;
  limit_hotwords: number;
  limit_notes: number;
  status: string;
  started_at: string;
  finished_at: string | null;
  error_stage: string | null;
  error_message: string | null;
}

interface NoteRow {
  huitun_note_key: string;
  source_keyword: string;
  hot_word: string;
  title: string;
  author_name: string | null;
  author_level: string | null;
  cover_url: string | null;
  is_video: number;
  video_duration: string | null;
  published_at: string | null;
  updated_at: string | null;
  tags_json: string;
  estimated_exposure: number | null;
  estimated_reads: number | null;
  likes: number | null;
  collects: number | null;
  comments: number | null;
  shares: number | null;
  author_followers: number | null;
  author_note_count: number | null;
  author_total_likes_collects: number | null;
  read_exposure_ratio_text: string | null;
  read_follower_ratio_text: string | null;
  list_rank: number | null;
  list_page: number | null;
  list_likes: number | null;
  updated_record_at: string;
}

describe('CollectorRepository', () => {
  let tempDir: string;
  let db: DatabaseSync;
  let repository: CollectorRepository;

  beforeEach(() => {
    tempDir = mkdtempSync(join(tmpdir(), 'xhs-db-test-'));
    db = openDatabase(join(tempDir, 'nested', 'collector.sqlite'));
    initializeSchema(db);
    repository = new CollectorRepository(db);
  });

  afterEach(() => {
    db.close();
    rmSync(tempDir, { recursive: true, force: true });
  });

  it('creates schema, creates a collection run, and finishes it as success', () => {
    const runId = repository.createRun({
      keyword: '咖啡',
      days: 30,
      limitHotwords: 12,
      limitNotes: 25,
    });

    repository.finishRun(runId, 'success');

    const row = db
      .prepare('select * from collection_runs where id = ?')
      .get(runId) as CollectionRunRow | undefined;

    expect(row).toMatchObject({
      id: runId,
      keyword: '咖啡',
      days: 30,
      limit_hotwords: 12,
      limit_notes: 25,
      status: 'success',
      error_stage: null,
      error_message: null,
    });
    expect(row?.started_at).toEqual(expect.any(String));
    expect(row?.finished_at).toEqual(expect.any(String));
  });

  it('upserts the same note without duplicates and updates metric and detail fields', () => {
    const runId = repository.createRun({
      keyword: '露营',
      days: 7,
      limitHotwords: 3,
      limitNotes: 10,
    });

    repository.upsertNote(
      runId,
      '露营',
      {
        hotWord: '露营装备',
        huitunNoteKey: 'note-123',
        title: '初始标题',
        authorName: '作者A',
        authorLevel: 'Lv3',
        coverUrl: 'https://example.com/cover-a.jpg',
        isVideo: false,
        videoDuration: null,
        publishedAt: '2026-05-01',
        updatedAt: '2026-05-02',
        tags: ['帐篷'],
        estimatedReads: 100,
        likes: 10,
        collects: 5,
        comments: 2,
      },
      null,
    );

    const firstRow = db
      .prepare('select updated_record_at from notes where huitun_note_key = ? and published_at = ?')
      .get('note-123', '2026-05-01') as Pick<NoteRow, 'updated_record_at'> | undefined;
    expect(firstRow?.updated_record_at).toEqual(expect.any(String));

    repository.upsertNote(
      runId,
      '露营',
      {
        hotWord: '露营装备',
        huitunNoteKey: 'note-123',
        title: '更新标题',
        authorName: '作者B',
        authorLevel: 'Lv4',
        coverUrl: 'https://example.com/cover-b.jpg',
        isVideo: true,
        videoDuration: '01:23',
        publishedAt: '2026-05-01',
        updatedAt: '2026-05-03',
        tags: ['帐篷', '天幕'],
        estimatedReads: 250,
        likes: 30,
        collects: 15,
        comments: 7,
        listRank: 1,
        listPage: 1,
      },
      {
        huitunNoteKey: 'note-123',
        estimatedExposure: 1000,
        estimatedReads: 280,
        likes: 35,
        collects: 18,
        comments: 8,
        shares: 4,
        authorFollowers: 5000,
        authorNoteCount: 42,
        authorTotalLikesCollects: 90000,
        readExposureRatioText: '28%',
        readFollowerRatioText: '5.6%',
      },
    );

    const countRow = db.prepare('select count(*) as count from notes').get() as { count: number };
    const row = db
      .prepare('select * from notes where huitun_note_key = ? and published_at = ?')
      .get('note-123', '2026-05-01') as NoteRow | undefined;

    expect(countRow.count).toBe(1);
    expect(row).toMatchObject({
      huitun_note_key: 'note-123',
      source_keyword: '露营',
      hot_word: '露营装备',
      title: '更新标题',
      author_name: '作者B',
      author_level: 'Lv4',
      cover_url: 'https://example.com/cover-b.jpg',
      is_video: 1,
      video_duration: '01:23',
      published_at: '2026-05-01',
      updated_at: '2026-05-03',
      tags_json: JSON.stringify(['帐篷', '天幕']),
      estimated_exposure: 1000,
      estimated_reads: 280,
      likes: 35,
      collects: 18,
      comments: 8,
      shares: 4,
      author_followers: 5000,
      author_note_count: 42,
      author_total_likes_collects: 90000,
      read_exposure_ratio_text: '28%',
      read_follower_ratio_text: '5.6%',
      list_rank: 1,
      list_page: 1,
      list_likes: 30,
    });
    expect(row?.updated_record_at).toEqual(expect.any(String));
  });

  it('counts persisted notes for a run without overreporting duplicate upserts', () => {
    const runId = repository.createRun({
      keyword: '露营',
      days: 7,
      limitHotwords: 3,
      limitNotes: 10,
    });

    const note = {
      hotWord: '露营装备',
      huitunNoteKey: 'note-counted-once',
      title: '初始标题',
      authorName: '作者A',
      authorLevel: 'Lv3',
      coverUrl: 'https://example.com/cover-a.jpg',
      isVideo: false,
      videoDuration: null,
      publishedAt: '2026-05-01',
      updatedAt: '2026-05-02',
      tags: ['帐篷'],
      estimatedReads: 100,
      likes: 10,
      collects: 5,
      comments: 2,
    };

    repository.upsertNote(runId, '露营', note, null);
    repository.upsertNote(
      runId,
      '露营',
      {
        ...note,
        title: '更新标题',
        estimatedReads: 250,
        likes: 30,
        collects: 15,
        comments: 7,
      },
      {
        huitunNoteKey: 'note-counted-once',
        estimatedExposure: 1000,
        estimatedReads: 280,
        likes: 35,
        collects: 18,
        comments: 8,
        shares: 4,
        authorFollowers: 5000,
        authorNoteCount: 42,
        authorTotalLikesCollects: 90000,
        readExposureRatioText: '28%',
        readFollowerRatioText: '5.6%',
      },
    );

    expect(repository.countNotesForRun(runId)).toBe(1);
    expect(repository.countDetailedNotesForRun(runId)).toBe(1);
  });

  it('counts hot words persisted for a run', () => {
    const firstRunId = repository.createRun({
      keyword: '护肤',
      days: 7,
      limitHotwords: 3,
      limitNotes: 10,
    });
    const secondRunId = repository.createRun({
      keyword: '咖啡',
      days: 30,
      limitHotwords: 3,
      limitNotes: 10,
    });

    repository.insertHotWords(firstRunId, [
      {
        sourceKeyword: '护肤',
        word: '早C晚A',
        hotValueText: '1万',
        hotValueNumber: 10000,
        noteCount: 20,
        interactionText: '5千',
        interactionNumber: 5000,
        categories: [{ label: '护肤', rate: null }],
        rankIndex: 1,
      },
      {
        sourceKeyword: '护肤',
        word: '屏障修复',
        hotValueText: '8千',
        hotValueNumber: 8000,
        noteCount: 12,
        interactionText: '3千',
        interactionNumber: 3000,
        categories: [{ label: '护肤', rate: null }],
        rankIndex: 2,
      },
    ]);
    repository.insertHotWords(secondRunId, [
      {
        sourceKeyword: '咖啡',
        word: '手冲咖啡',
        hotValueText: '2万',
        hotValueNumber: 20000,
        noteCount: 30,
        interactionText: '8千',
        interactionNumber: 8000,
        categories: [{ label: '咖啡', rate: null }],
        rankIndex: 1,
      },
    ]);

    expect(repository.countHotWordsForRun(firstRunId)).toBe(2);
    expect(repository.countHotWordsForRun(secondRunId)).toBe(1);
  });

  it('upserts notes with missing published dates as one stable note identity', () => {
    const runId = repository.createRun({
      keyword: '咖啡',
      days: 7,
      limitHotwords: 3,
      limitNotes: 10,
    });

    repository.upsertNote(
      runId,
      '咖啡',
      {
        hotWord: '手冲咖啡',
        huitunNoteKey: 'note-null-date',
        title: '旧标题',
        authorName: '作者A',
        authorLevel: 'Lv2',
        coverUrl: 'https://example.com/old.jpg',
        isVideo: false,
        videoDuration: null,
        publishedAt: null,
        updatedAt: '2026-05-01',
        tags: ['咖啡'],
        estimatedReads: 100,
        likes: 10,
        collects: 5,
        comments: 2,
      },
      null,
    );

    repository.upsertNote(
      runId,
      '咖啡',
      {
        hotWord: '手冲咖啡',
        huitunNoteKey: 'note-null-date',
        title: '新标题',
        authorName: '作者B',
        authorLevel: 'Lv3',
        coverUrl: 'https://example.com/new.jpg',
        isVideo: true,
        videoDuration: '00:30',
        publishedAt: null,
        updatedAt: '2026-05-02',
        tags: ['咖啡', '器具'],
        estimatedReads: 260,
        likes: 26,
        collects: 13,
        comments: 6,
      },
      null,
    );

    const countRow = db.prepare('select count(*) as count from notes').get() as { count: number };
    const row = db
      .prepare('select * from notes where huitun_note_key = ?')
      .get('note-null-date') as NoteRow | undefined;

    expect(countRow.count).toBe(1);
    expect(row).toMatchObject({
      title: '新标题',
      author_name: '作者B',
      author_level: 'Lv3',
      cover_url: 'https://example.com/new.jpg',
      is_video: 1,
      video_duration: '00:30',
      published_at: null,
      updated_at: '2026-05-02',
      tags_json: JSON.stringify(['咖啡', '器具']),
      estimated_reads: 260,
      likes: 26,
      collects: 13,
      comments: 6,
    });
  });

  it('preserves detail-only note fields when a later list-only upsert has no detail', () => {
    const runId = repository.createRun({
      keyword: '穿搭',
      days: 7,
      limitHotwords: 3,
      limitNotes: 10,
    });

    repository.upsertNote(
      runId,
      '穿搭',
      {
        hotWord: '春季穿搭',
        huitunNoteKey: 'note-detail-preserved',
        title: '详情标题',
        authorName: '作者A',
        authorLevel: 'Lv5',
        coverUrl: 'https://example.com/detail.jpg',
        isVideo: false,
        videoDuration: null,
        publishedAt: '2026-05-04',
        updatedAt: '2026-05-05',
        tags: ['穿搭'],
        estimatedReads: 100,
        likes: 10,
        collects: 5,
        comments: 2,
      },
      {
        huitunNoteKey: 'note-detail-preserved',
        estimatedExposure: 1000,
        estimatedReads: 120,
        likes: 12,
        collects: 6,
        comments: 3,
        shares: 4,
        authorFollowers: 5000,
        authorNoteCount: 42,
        authorTotalLikesCollects: 90000,
        readExposureRatioText: '12%',
        readFollowerRatioText: '2.4%',
      },
    );

    repository.upsertNote(
      runId,
      '穿搭',
      {
        hotWord: '春季穿搭',
        huitunNoteKey: 'note-detail-preserved',
        title: '列表标题',
        authorName: '作者B',
        authorLevel: 'Lv6',
        coverUrl: 'https://example.com/list.jpg',
        isVideo: true,
        videoDuration: '02:00',
        publishedAt: '2026-05-04',
        updatedAt: '2026-05-06',
        tags: ['穿搭', '通勤'],
        estimatedReads: 300,
        likes: 30,
        collects: 15,
        comments: 8,
      },
      null,
    );

    const row = db
      .prepare('select * from notes where huitun_note_key = ? and published_at = ?')
      .get('note-detail-preserved', '2026-05-04') as NoteRow | undefined;

    expect(row).toMatchObject({
      title: '列表标题',
      author_name: '作者B',
      author_level: 'Lv6',
      cover_url: 'https://example.com/list.jpg',
      is_video: 1,
      video_duration: '02:00',
      updated_at: '2026-05-06',
      tags_json: JSON.stringify(['穿搭', '通勤']),
      estimated_reads: 300,
      likes: 30,
      collects: 15,
      comments: 8,
      estimated_exposure: 1000,
      shares: 4,
      author_followers: 5000,
      author_note_count: 42,
      author_total_likes_collects: 90000,
      read_exposure_ratio_text: '12%',
      read_follower_ratio_text: '2.4%',
    });
  });

  it('counts report snapshot totals for a run', () => {
    const runId = repository.createRun({
      keyword: '浴缸',
      days: 7,
      limitHotwords: 3,
      limitNotes: 20,
    });

    repository.insertHotWordSnapshot(runId, {
      word: '浴缸',
      days: 7,
      pageUrl: 'https://xhs.huitun.com/#/hotWords/hot_word_detail?hotWord=浴缸',
      heatText: '1,510',
      relatedNotesText: '26',
      totalInteractionsText: '1.4w',
      overview: { 热度值: '1,510' },
    });
    repository.insertRawSnapshot(runId, {
      kind: 'note_list_sort_error',
      objectKey: '浴缸',
      pageUrl: 'https://xhs.huitun.com/#/hotWords/hot_word_detail?hotWord=浴缸',
      textContent: '排序失败',
      htmlContent: '<html></html>',
    });
    repository.insertRawSnapshot(runId, {
      kind: 'parse_note_detail_error',
      objectKey: 'note-1',
      pageUrl: 'https://xhs.huitun.com/#/hotWords/hot_word_detail?hotWord=浴缸',
      textContent: '详情失败',
      htmlContent: null,
    });

    expect(repository.countHotWordSnapshotsForRun(runId)).toBe(1);
    expect(repository.countRawSnapshotsForRun(runId)).toBe(2);
    expect(repository.countRawSnapshotsByKindForRun(runId)).toEqual({
      note_list_sort_error: 1,
      parse_note_detail_error: 1,
    });
  });

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

  it('uses detail likes when list likes are missing in hot word contributions', () => {
    const runId = repository.createRun({
      keyword: '护肤',
      days: 7,
      limitHotwords: 3,
      limitNotes: 20,
    });
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
          list_likes
        ) values (?, '护肤', '早C晚A', 'note-legacy-likes', '旧库笔记', 0, '2026-05-01', '[]', 321, null)
      `)
      .run(runId);

    expect(repository.getRunReportData(runId).hotWordContributions).toEqual([
      { hotWord: '早C晚A', notes: 1, topLikes: 321, bestRank: null },
    ]);
  });

  it('deduplicates physically duplicated note export rows by stable identity', () => {
    db.exec('drop index idx_notes_stable_identity');
    const runId = repository.createRun({
      keyword: '护肤',
      days: 7,
      limitHotwords: 3,
      limitNotes: 20,
    });
    const insertDuplicate = db.prepare(`
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
      ) values (?, '护肤', '早C晚A', 'note-null-date', ?, 0, null, '[]', ?, ?, ?)
    `);
    insertDuplicate.run(runId, '旧记录', 100, 100, '2026-05-01 00:00:00');
    insertDuplicate.run(runId, '新记录', 200, 200, '2026-05-02 00:00:00');

    const rows = repository.listNoteExportRows(runId);

    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ title: '新记录', likes: 200, huitunNoteKey: 'note-null-date' });
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

  it('rolls back all hot words when a mid-batch row fails', () => {
    const runId = repository.createRun({
      keyword: '护肤',
      days: 7,
      limitHotwords: 3,
      limitNotes: 10,
    });

    expect(() =>
      repository.insertHotWords(runId, [
        {
          sourceKeyword: '护肤',
          word: '早C晚A',
          hotValueText: '1万',
          hotValueNumber: 10000,
          noteCount: 20,
          interactionText: '5千',
          interactionNumber: 5000,
          categories: [{ label: '护肤', rate: null }],
          rankIndex: 1,
        },
        {
          sourceKeyword: '护肤',
          word: null,
          hotValueText: '2万',
          hotValueNumber: 20000,
          noteCount: 30,
          interactionText: '8千',
          interactionNumber: 8000,
          categories: [{ label: '护肤', rate: null }],
          rankIndex: 2,
        } as unknown as Parameters<CollectorRepository['insertHotWords']>[1][number],
      ]),
    ).toThrow();

    const countRow = db
      .prepare('select count(*) as count from hot_words where run_id = ?')
      .get(runId) as { count: number };
    expect(countRow.count).toBe(0);
  });
});

import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import type { DatabaseSync } from 'node:sqlite';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { openDatabase } from '../src/db/client.js';
import { CollectorRepository } from '../src/db/repositories.js';
import { initializeSchema } from '../src/db/schema.js';

interface XhsSearchRunRow {
  id: number;
  source: string;
  source_run_id: number | null;
  keyword: string;
  sorts_json: string;
  limit_per_sort: number;
  with_details: number;
  status: string;
  started_at: string;
  finished_at: string | null;
  error_stage: string | null;
  error_message: string | null;
}

interface XhsSearchNoteDbRow {
  keyword: string;
  sort_key: string;
  sort_label: string;
  rank_index: number;
  feed_id: string;
  xsec_token: string | null;
  search_result_url: string;
  explore_url: string | null;
  title: string;
  author_name: string | null;
  author_profile_url: string | null;
  cover_url: string | null;
  published_at_text: string | null;
  metric_text: string | null;
  detail_text: string | null;
  detail_tags_json: string;
  detail_comment_count_text: string | null;
  detail_like_text: string | null;
  detail_collect_text: string | null;
  detail_share_text: string | null;
  note_type: string;
  cover_alt_text: string | null;
  raw_detail_text: string | null;
  source_topic_texts_json: string;
  source_comments_json: string;
  media_sources_json: string;
  analysis_source_text: string | null;
  raw_card_text: string;
  updated_record_at: string;
}

function columnNames(db: DatabaseSync, tableName: string): string[] {
  return (db.prepare(`pragma table_info(${tableName})`).all() as Array<{ name: string }>).map(
    (column) => column.name,
  );
}

function indexNames(db: DatabaseSync, tableName: string): string[] {
  return (db.prepare(`pragma index_list(${tableName})`).all() as Array<{ name: string }>).map(
    (index) => index.name,
  );
}

function uniqueIndexNames(db: DatabaseSync, tableName: string): string[] {
  return (db.prepare(`pragma index_list(${tableName})`).all() as Array<{ name: string; unique: number }>)
    .filter((index) => index.unique === 1)
    .map((index) => index.name);
}

describe('XHS schema migration safety', () => {
  it('adds legacy XHS columns before creating indexes that depend on them', () => {
    const legacyDir = mkdtempSync(join(tmpdir(), 'xhs-schema-migration-test-'));
    const legacyDb = openDatabase(join(legacyDir, 'legacy.sqlite'));

    try {
      legacyDb.exec(`
        create table xhs_search_runs (
          id integer primary key autoincrement,
          source text not null,
          keyword text not null,
          sorts_json text not null,
          limit_per_sort integer not null,
          with_details integer not null,
          status text not null,
          started_at text not null default current_timestamp
        );

        create table xhs_search_notes (
          id integer primary key autoincrement,
          run_id integer not null references xhs_search_runs(id) on delete cascade,
          keyword text not null,
          sort_key text not null,
          sort_label text not null,
          rank_index integer not null,
          xsec_token text,
          search_result_url text not null,
          title text not null,
          author_name text,
          author_profile_url text,
          cover_url text,
          published_at_text text,
          metric_text text,
          raw_card_text text not null,
          collected_at text not null default current_timestamp
        );

        create table xhs_raw_snapshots (
          id integer primary key autoincrement,
          run_id integer not null references xhs_search_runs(id) on delete cascade,
          kind text not null,
          object_key text not null,
          page_url text not null,
          text_content text not null,
          captured_at text not null default current_timestamp
        );
      `);

      expect(() => initializeSchema(legacyDb)).not.toThrow();
      expect(columnNames(legacyDb, 'xhs_search_runs')).toContain('source_run_id');
      expect(columnNames(legacyDb, 'xhs_search_notes')).toEqual(
        expect.arrayContaining([
          'feed_id',
          'explore_url',
          'detail_tags_json',
          'note_type',
          'cover_alt_text',
          'raw_detail_text',
          'source_topic_texts_json',
          'source_comments_json',
          'media_sources_json',
          'analysis_source_text',
          'updated_record_at',
        ]),
      );
      expect(columnNames(legacyDb, 'xhs_raw_snapshots')).toContain('html_content');
      expect(indexNames(legacyDb, 'xhs_search_runs')).toContain('idx_xhs_search_runs_source_run_id');
      expect(indexNames(legacyDb, 'xhs_search_notes')).toEqual(
        expect.arrayContaining(['idx_xhs_search_notes_run_id', 'idx_xhs_search_notes_feed_id']),
      );
      expect(indexNames(legacyDb, 'xhs_raw_snapshots')).toContain('idx_xhs_raw_snapshots_run_id');
    } finally {
      legacyDb.close();
      rmSync(legacyDir, { recursive: true, force: true });
    }
  });

  it('backfills legacy feed IDs before deduping migrated XHS search notes', () => {
    const legacyDir = mkdtempSync(join(tmpdir(), 'xhs-schema-feed-id-backfill-test-'));
    const legacyDb = openDatabase(join(legacyDir, 'legacy.sqlite'));

    try {
      legacyDb.exec(`
        create table xhs_search_runs (
          id integer primary key autoincrement,
          source text not null,
          keyword text not null,
          sorts_json text not null,
          limit_per_sort integer not null,
          with_details integer not null,
          status text not null,
          started_at text not null default current_timestamp
        );

        create table xhs_search_notes (
          id integer primary key autoincrement,
          run_id integer not null references xhs_search_runs(id) on delete cascade,
          keyword text not null,
          sort_key text not null,
          sort_label text not null,
          rank_index integer not null,
          xsec_token text,
          search_result_url text not null,
          title text not null,
          author_name text,
          author_profile_url text,
          cover_url text,
          published_at_text text,
          metric_text text,
          raw_card_text text not null,
          collected_at text not null default current_timestamp
        );

        insert into xhs_search_runs (id, source, keyword, sorts_json, limit_per_sort, with_details, status)
        values (1, 'manual_keyword', '护肤', '["latest"]', 20, 0, 'running');

        insert into xhs_search_notes (
          run_id,
          keyword,
          sort_key,
          sort_label,
          rank_index,
          xsec_token,
          search_result_url,
          title,
          raw_card_text
        ) values
          (
            1,
            '护肤',
            'latest',
            '最新',
            1,
            'token-a',
            'https://www.xiaohongshu.com/search_result/feed-a?xsec_token=token-a',
            '标题A',
            '卡片A'
          ),
          (
            1,
            '护肤',
            'latest',
            '最新',
            2,
            'token-b',
            'https://www.xiaohongshu.com/search_result/feed-b?xsec_token=token-b',
            '标题B',
            '卡片B'
          );
      `);

      initializeSchema(legacyDb);

      const rows = legacyDb
        .prepare('select feed_id, search_result_url from xhs_search_notes order by rank_index')
        .all() as Array<{ feed_id: string | null; search_result_url: string }>;

      expect(rows).toEqual([
        {
          feed_id: 'feed-a',
          search_result_url: 'https://www.xiaohongshu.com/search_result/feed-a?xsec_token=token-a',
        },
        {
          feed_id: 'feed-b',
          search_result_url: 'https://www.xiaohongshu.com/search_result/feed-b?xsec_token=token-b',
        },
      ]);
      expect(uniqueIndexNames(legacyDb, 'xhs_search_notes')).toContain('idx_xhs_search_notes_identity');
    } finally {
      legacyDb.close();
      rmSync(legacyDir, { recursive: true, force: true });
    }
  });

  it('adds XHS search note identity uniqueness to migrated legacy tables', () => {
    const legacyDir = mkdtempSync(join(tmpdir(), 'xhs-schema-identity-test-'));
    const legacyDb = openDatabase(join(legacyDir, 'legacy.sqlite'));

    try {
      legacyDb.exec(`
        create table xhs_search_runs (
          id integer primary key autoincrement,
          source text not null,
          keyword text not null,
          sorts_json text not null,
          limit_per_sort integer not null,
          with_details integer not null,
          status text not null,
          started_at text not null default current_timestamp
        );

        create table xhs_search_notes (
          id integer primary key autoincrement,
          run_id integer not null references xhs_search_runs(id) on delete cascade,
          keyword text not null,
          sort_key text not null,
          sort_label text not null,
          rank_index integer not null,
          xsec_token text,
          search_result_url text not null,
          title text not null,
          author_name text,
          author_profile_url text,
          cover_url text,
          published_at_text text,
          metric_text text,
          raw_card_text text not null,
          collected_at text not null default current_timestamp
        );
      `);

      initializeSchema(legacyDb);
      const legacyRepository = new CollectorRepository(legacyDb);
      const runId = legacyRepository.createXhsSearchRun({
        source: 'manual_keyword',
        sourceRunId: null,
        keyword: '护肤',
        sorts: ['latest'],
        limitPerSort: 20,
        withDetails: true,
      });

      expect(() =>
        legacyRepository.upsertXhsSearchNotes(runId, [
          {
            keyword: '护肤',
            sortKey: 'latest',
            sortLabel: '最新',
            rankIndex: 1,
            feedId: 'feed-legacy-1',
            xsecToken: 'token-a',
            searchResultUrl: 'https://www.xiaohongshu.com/search_result/feed-legacy-1?xsec_token=token-a',
            exploreUrl: null,
            title: '旧标题',
            authorName: '作者A',
            authorProfileUrl: null,
            coverUrl: null,
            publishedAtText: '1天前',
            metricText: '赞 10 收藏 2',
            detailText: null,
            detailTags: [],
            detailCommentCountText: null,
            detailLikeText: null,
            detailCollectText: null,
            detailShareText: null,
            noteType: 'unknown',
            coverAltText: null,
            rawDetailText: null,
            sourceTopicTexts: [],
            sourceComments: [],
            mediaSources: [],
            analysisSourceText: null,
            rawCardText: '旧卡片文本',
          },
        ]),
      ).not.toThrow();

      expect(() =>
        legacyRepository.upsertXhsSearchNotes(runId, [
          {
            keyword: '护肤',
            sortKey: 'latest',
            sortLabel: '最新',
            rankIndex: 2,
            feedId: 'feed-legacy-1',
            xsecToken: 'token-b',
            searchResultUrl: 'https://www.xiaohongshu.com/search_result/feed-legacy-1?xsec_token=token-b',
            exploreUrl: 'https://www.xiaohongshu.com/explore/feed-legacy-1?xsec_token=token-b',
            title: '新标题',
            authorName: '作者B',
            authorProfileUrl: 'https://www.xiaohongshu.com/user/profile/b',
            coverUrl: 'https://example.com/cover-b.jpg',
            publishedAtText: '刚刚',
            metricText: '赞 20 收藏 8',
            detailText: '详情正文',
            detailTags: ['护肤', '精华'],
            detailCommentCountText: '3',
            detailLikeText: '20',
            detailCollectText: '8',
            detailShareText: '1',
            noteType: 'video',
            coverAltText: '白底封面',
            rawDetailText: '详情原文',
            sourceTopicTexts: ['护肤', '精华'],
            sourceComments: [{ contentText: '哪里买？', authorName: '用户A', likeText: '3', rawText: '用户A\n哪里买？\n3' }],
            mediaSources: [{ kind: 'image', url: 'https://example.com/image.jpg', posterUrl: null, altText: '白底封面' }],
            analysisSourceText: '标题：新标题\n评论摘录：\n- 用户A：哪里买？（赞 3）\n媒体素材：\n- image：https://example.com/image.jpg（白底封面）',
            rawCardText: '新卡片文本',
          },
        ]),
      ).not.toThrow();

      const countRow = legacyDb.prepare('select count(*) as count from xhs_search_notes').get() as { count: number };
      const row = legacyDb
        .prepare('select * from xhs_search_notes where run_id = ? and keyword = ? and sort_key = ? and feed_id = ?')
        .get(runId, '护肤', 'latest', 'feed-legacy-1') as XhsSearchNoteDbRow | undefined;

      expect(uniqueIndexNames(legacyDb, 'xhs_search_notes')).toContain('idx_xhs_search_notes_identity');
      expect(countRow.count).toBe(1);
      expect(row).toMatchObject({
        keyword: '护肤',
        sort_key: 'latest',
        rank_index: 2,
        feed_id: 'feed-legacy-1',
        xsec_token: 'token-b',
        title: '新标题',
        detail_text: '详情正文',
        detail_tags_json: JSON.stringify(['护肤', '精华']),
        note_type: 'video',
        cover_alt_text: '白底封面',
        raw_detail_text: '详情原文',
        source_topic_texts_json: JSON.stringify(['护肤', '精华']),
        source_comments_json: JSON.stringify([{ contentText: '哪里买？', authorName: '用户A', likeText: '3', rawText: '用户A\n哪里买？\n3' }]),
        media_sources_json: JSON.stringify([{ kind: 'image', url: 'https://example.com/image.jpg', posterUrl: null, altText: '白底封面' }]),
        analysis_source_text: '标题：新标题\n评论摘录：\n- 用户A：哪里买？（赞 3）\n媒体素材：\n- image：https://example.com/image.jpg（白底封面）',
      });
    } finally {
      legacyDb.close();
      rmSync(legacyDir, { recursive: true, force: true });
    }
  });
});

describe('XHS database repository', () => {
  let tempDir: string;
  let db: DatabaseSync;
  let repository: CollectorRepository;

  beforeEach(() => {
    tempDir = mkdtempSync(join(tmpdir(), 'xhs-search-db-test-'));
    db = openDatabase(join(tempDir, 'nested', 'collector.sqlite'));
    initializeSchema(db);
    repository = new CollectorRepository(db);
  });

  afterEach(() => {
    db.close();
    rmSync(tempDir, { recursive: true, force: true });
  });

  it('creates and finishes an XHS search run', () => {
    const runId = repository.createXhsSearchRun({
      source: 'manual_keyword',
      sourceRunId: null,
      keyword: '护肤',
      sorts: ['latest', 'most_collected'],
      limitPerSort: 20,
      withDetails: false,
    });

    repository.finishXhsSearchRun(runId, 'success');

    const row = db
      .prepare('select * from xhs_search_runs where id = ?')
      .get(runId) as XhsSearchRunRow | undefined;

    expect(row).toMatchObject({
      id: runId,
      source: 'manual_keyword',
      source_run_id: null,
      keyword: '护肤',
      sorts_json: JSON.stringify(['latest', 'most_collected']),
      limit_per_sort: 20,
      with_details: 0,
      status: 'success',
      error_stage: null,
      error_message: null,
    });
    expect(row?.started_at).toEqual(expect.any(String));
    expect(row?.finished_at).toEqual(expect.any(String));
  });

  it('upserts XHS notes per run keyword sort feed id', () => {
    const runId = repository.createXhsSearchRun({
      source: 'manual_keyword',
      sourceRunId: null,
      keyword: '护肤',
      sorts: ['latest'],
      limitPerSort: 20,
      withDetails: true,
    });

    repository.upsertXhsSearchNotes(runId, [
      {
        keyword: '护肤',
        sortKey: 'latest',
        sortLabel: '最新',
        rankIndex: 1,
        feedId: 'feed-1',
        xsecToken: 'token-a',
        searchResultUrl: 'https://www.xiaohongshu.com/search_result/feed-1?xsec_token=token-a',
        exploreUrl: null,
        title: '旧标题',
        authorName: '作者A',
        authorProfileUrl: 'https://www.xiaohongshu.com/user/profile/a',
        coverUrl: 'https://example.com/cover-a.jpg',
        publishedAtText: '1天前',
        metricText: '赞 10 收藏 2',
        detailText: null,
        detailTags: [],
        detailCommentCountText: null,
        detailLikeText: null,
        detailCollectText: null,
        detailShareText: null,
        noteType: 'unknown',
        coverAltText: null,
        rawDetailText: null,
        sourceTopicTexts: [],
        sourceComments: [],
        mediaSources: [],
        analysisSourceText: null,
        rawCardText: '旧卡片文本',
      },
    ]);

    repository.upsertXhsSearchNotes(runId, [
      {
        keyword: '护肤',
        sortKey: 'latest',
        sortLabel: '最新',
        rankIndex: 2,
        feedId: 'feed-1',
        xsecToken: 'token-b',
        searchResultUrl: 'https://www.xiaohongshu.com/search_result/feed-1?xsec_token=token-b',
        exploreUrl: 'https://www.xiaohongshu.com/explore/feed-1?xsec_token=token-b',
        title: '新标题',
        authorName: '作者B',
        authorProfileUrl: 'https://www.xiaohongshu.com/user/profile/b',
        coverUrl: 'https://example.com/cover-b.jpg',
        publishedAtText: '刚刚',
        metricText: '赞 20 收藏 8',
        detailText: '详情正文',
        detailTags: ['护肤', '精华'],
        detailCommentCountText: '3',
        detailLikeText: '20',
        detailCollectText: '8',
        detailShareText: '1',
        noteType: 'video',
        coverAltText: '白底封面',
        rawDetailText: '详情原文',
        sourceTopicTexts: ['护肤', '精华'],
        sourceComments: [{ contentText: '哪里买？', authorName: '用户A', likeText: '3', rawText: '用户A\n哪里买？\n3' }],
        mediaSources: [{ kind: 'image', url: 'https://example.com/image.jpg', posterUrl: null, altText: '白底封面' }],
        analysisSourceText: '标题：新标题\n评论摘录：\n- 用户A：哪里买？（赞 3）\n媒体素材：\n- image：https://example.com/image.jpg（白底封面）',
        rawCardText: '新卡片文本',
      },
    ]);

    const countRow = db.prepare('select count(*) as count from xhs_search_notes').get() as { count: number };
    const row = db
      .prepare('select * from xhs_search_notes where run_id = ? and keyword = ? and sort_key = ? and feed_id = ?')
      .get(runId, '护肤', 'latest', 'feed-1') as XhsSearchNoteDbRow | undefined;

    expect(countRow.count).toBe(1);
    expect(row).toMatchObject({
      keyword: '护肤',
      sort_key: 'latest',
      sort_label: '最新',
      rank_index: 2,
      feed_id: 'feed-1',
      xsec_token: 'token-b',
      search_result_url: 'https://www.xiaohongshu.com/search_result/feed-1?xsec_token=token-b',
      explore_url: 'https://www.xiaohongshu.com/explore/feed-1?xsec_token=token-b',
      title: '新标题',
      author_name: '作者B',
      author_profile_url: 'https://www.xiaohongshu.com/user/profile/b',
      cover_url: 'https://example.com/cover-b.jpg',
      published_at_text: '刚刚',
      metric_text: '赞 20 收藏 8',
      detail_text: '详情正文',
      detail_tags_json: JSON.stringify(['护肤', '精华']),
      note_type: 'video',
      cover_alt_text: '白底封面',
      raw_detail_text: '详情原文',
      source_topic_texts_json: JSON.stringify(['护肤', '精华']),
      source_comments_json: JSON.stringify([{ contentText: '哪里买？', authorName: '用户A', likeText: '3', rawText: '用户A\n哪里买？\n3' }]),
      media_sources_json: JSON.stringify([{ kind: 'image', url: 'https://example.com/image.jpg', posterUrl: null, altText: '白底封面' }]),
      analysis_source_text: '标题：新标题\n评论摘录：\n- 用户A：哪里买？（赞 3）\n媒体素材：\n- image：https://example.com/image.jpg（白底封面）',
      detail_comment_count_text: '3',
      detail_like_text: '20',
      detail_collect_text: '8',
      detail_share_text: '1',
      raw_card_text: '新卡片文本',
    });
    expect(JSON.parse(row?.detail_tags_json ?? 'null')).toEqual(['护肤', '精华']);
    expect(JSON.parse(row?.source_topic_texts_json ?? 'null')).toEqual(['护肤', '精华']);
    expect(JSON.parse(row?.source_comments_json ?? 'null')).toEqual([
      { contentText: '哪里买？', authorName: '用户A', likeText: '3', rawText: '用户A\n哪里买？\n3' },
    ]);
    expect(JSON.parse(row?.media_sources_json ?? 'null')).toEqual([
      { kind: 'image', url: 'https://example.com/image.jpg', posterUrl: null, altText: '白底封面' },
    ]);
    expect(row?.updated_record_at).toEqual(expect.any(String));
  });

  it('keeps existing non-empty analysis source fields when later upserts are empty', () => {
    const runId = repository.createXhsSearchRun({
      source: 'manual_keyword',
      sourceRunId: null,
      keyword: '护肤',
      sorts: ['most_collected'],
      limitPerSort: 20,
      withDetails: true,
    });

    const richRow = {
      keyword: '护肤',
      sortKey: 'most_collected' as const,
      sortLabel: '最多收藏',
      rankIndex: 1,
      feedId: 'feed-rich',
      xsecToken: 'token-a',
      searchResultUrl: 'https://www.xiaohongshu.com/search_result/feed-rich?xsec_token=token-a',
      exploreUrl: 'https://www.xiaohongshu.com/explore/feed-rich?xsec_token=token-a',
      title: '标题',
      authorName: '作者A',
      authorProfileUrl: null,
      coverUrl: null,
      publishedAtText: null,
      metricText: '收藏 9',
      detailText: '详情正文',
      detailTags: ['护肤'],
      detailCommentCountText: '2',
      detailLikeText: '10',
      detailCollectText: '9',
      detailShareText: null,
      noteType: 'image' as const,
      coverAltText: '封面文字',
      rawDetailText: '详情页完整文本',
      sourceTopicTexts: ['护肤'],
      sourceComments: [{ contentText: '好用吗？', authorName: '用户A', likeText: '4', rawText: '用户A\n好用吗？\n4' }],
      mediaSources: [{ kind: 'video' as const, url: 'blob:https://www.xiaohongshu.com/video', posterUrl: 'https://example.com/poster.jpg', altText: null }],
      analysisSourceText: '标题：标题\n评论摘录：\n- 用户A：好用吗？（赞 4）\n媒体素材：\n- video：blob:https://www.xiaohongshu.com/video，封面 https://example.com/poster.jpg',
      rawCardText: '卡片文本',
    };

    repository.upsertXhsSearchNotes(runId, [richRow]);
    repository.upsertXhsSearchNotes(runId, [{
      ...richRow,
      rankIndex: 2,
      xsecToken: 'token-b',
      searchResultUrl: 'https://www.xiaohongshu.com/search_result/feed-rich?xsec_token=token-b',
      detailText: null,
      detailTags: [],
      detailCommentCountText: null,
      detailLikeText: null,
      detailCollectText: null,
      detailShareText: null,
      noteType: 'unknown',
      coverAltText: null,
      rawDetailText: null,
      sourceTopicTexts: [],
      sourceComments: [],
      mediaSources: [],
      analysisSourceText: null,
    }]);

    const row = db.prepare('select * from xhs_search_notes where feed_id = ?').get('feed-rich') as unknown as XhsSearchNoteDbRow;
    expect(row).toMatchObject({
      rank_index: 2,
      xsec_token: 'token-b',
      detail_text: '详情正文',
      detail_tags_json: JSON.stringify(['护肤']),
      note_type: 'image',
      cover_alt_text: '封面文字',
      raw_detail_text: '详情页完整文本',
      source_topic_texts_json: JSON.stringify(['护肤']),
      source_comments_json: JSON.stringify([{ contentText: '好用吗？', authorName: '用户A', likeText: '4', rawText: '用户A\n好用吗？\n4' }]),
      media_sources_json: JSON.stringify([{ kind: 'video', url: 'blob:https://www.xiaohongshu.com/video', posterUrl: 'https://example.com/poster.jpg', altText: null }]),
      analysis_source_text: '标题：标题\n评论摘录：\n- 用户A：好用吗？（赞 4）\n媒体素材：\n- video：blob:https://www.xiaohongshu.com/video，封面 https://example.com/poster.jpg',
    });
  });

  it('returns no hot words for a missing Huitun run when resolving XHS keywords', () => {
    expect(repository.listHotWordKeywordsForRun(999999, 10)).toEqual([]);
  });

  it('stores XHS raw snapshots and reads hot words from a Huitun run', () => {
    const huitunRunId = repository.createRun({
      keyword: '护肤',
      days: 7,
      limitHotwords: 2,
      limitNotes: 10,
    });
    repository.insertHotWords(huitunRunId, [
      {
        sourceKeyword: '护肤',
        word: '屏障修复',
        hotValueText: '8千',
        hotValueNumber: 8000,
        noteCount: 12,
        interactionText: '3千',
        interactionNumber: 3000,
        categories: [{ label: '护肤', rate: null }],
        rankIndex: 1,
      },
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
        word: '熬夜急救',
        hotValueText: '6千',
        hotValueNumber: 6000,
        noteCount: 8,
        interactionText: '2千',
        interactionNumber: 2000,
        categories: [{ label: '护肤', rate: null }],
        rankIndex: 2,
      },
    ]);

    expect(repository.listHotWordKeywordsForRun(huitunRunId, 2)).toEqual(['屏障修复', '早C晚A']);

    const xhsRunId = repository.createXhsSearchRun({
      source: 'huitun_run',
      sourceRunId: huitunRunId,
      keyword: '早C晚A',
      sorts: ['most_collected'],
      limitPerSort: 20,
      withDetails: false,
    });
    repository.insertXhsRawSnapshot(xhsRunId, {
      kind: 'search_result',
      objectKey: '早C晚A:most_collected',
      pageUrl: 'https://www.xiaohongshu.com/search_result?keyword=%E6%97%A9C%E6%99%9AA',
      textContent: '搜索结果文本',
      htmlContent: '<html></html>',
    });

    const countRow = db.prepare('select count(*) as count from xhs_raw_snapshots').get() as { count: number };
    expect(countRow.count).toBe(1);
  });
});

import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it, vi } from 'vitest';

import { openDatabase } from '../src/db/client.js';
import { initializeSchema } from '../src/db/schema.js';
import type { XhsSession } from '../src/browser/xhs-session.js';
import type { XhsSearchNoteRow } from '../src/xhs-types.js';

const xhsDetailMocks = vi.hoisted(() => ({
  collectXhsNoteDetail: vi.fn(),
}));

const xhsSearchMocks = vi.hoisted(() => ({
  collectXhsSearchNoteRows: vi.fn(),
  openXhsSearchPage: vi.fn(),
}));

const xhsSessionMocks = vi.hoisted(() => ({
  captureXhsPageSnapshot: vi.fn(),
  createXhsSession: vi.fn(),
}));

vi.mock('../src/browser/xhs-note-detail.js', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/browser/xhs-note-detail.js')>();

  return {
    ...actual,
    collectXhsNoteDetail: xhsDetailMocks.collectXhsNoteDetail,
  };
});

vi.mock('../src/browser/xhs-search.js', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/browser/xhs-search.js')>();

  return {
    ...actual,
    collectXhsSearchNoteRows: xhsSearchMocks.collectXhsSearchNoteRows,
    openXhsSearchPage: xhsSearchMocks.openXhsSearchPage,
  };
});

vi.mock('../src/browser/xhs-session.js', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/browser/xhs-session.js')>();

  return {
    ...actual,
    captureXhsPageSnapshot: xhsSessionMocks.captureXhsPageSnapshot,
    createXhsSession: xhsSessionMocks.createXhsSession,
  };
});

import * as xhsSearchCollector from '../src/xhs-search-collector.js';

function noteRow(overrides: Partial<XhsSearchNoteRow> = {}): XhsSearchNoteRow {
  const feedId = overrides.feedId ?? 'feed-1';
  const sortKey = overrides.sortKey ?? 'latest';
  return {
    keyword: '护肤',
    sortKey,
    sortLabel: overrides.sortLabel ?? '最新',
    rankIndex: overrides.rankIndex ?? 1,
    feedId,
    xsecToken: overrides.xsecToken ?? 'token-a',
    searchResultUrl: overrides.searchResultUrl ?? `https://www.xiaohongshu.com/search_result/${feedId}?xsec_token=token-a`,
    exploreUrl: null,
    title: overrides.title ?? '标题',
    authorName: null,
    authorProfileUrl: null,
    coverUrl: null,
    publishedAtText: null,
    metricText: null,
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
    rawCardText: overrides.rawCardText ?? '标题',
    ...overrides,
  };
}

describe('XHS search collector helpers', () => {
  afterEach(() => {
    vi.resetAllMocks();
  });

  it('keeps short-list rows when diagnostic snapshot capture fails', async () => {
    const tempDir = mkdtempSync(join(tmpdir(), 'xhs-search-collector-test-'));
    const dbPath = join(tempDir, 'collector.sqlite');
    const row = noteRow();
    const session = {
      page: {},
      close: vi.fn().mockResolvedValue(undefined),
    } as unknown as XhsSession;

    xhsSessionMocks.createXhsSession.mockResolvedValue(session);
    xhsSearchMocks.openXhsSearchPage.mockResolvedValue(undefined);
    xhsSearchMocks.collectXhsSearchNoteRows.mockResolvedValue([row]);
    xhsSessionMocks.captureXhsPageSnapshot.mockRejectedValue(new Error('snapshot failed'));

    try {
      const result = await xhsSearchCollector.collectXhsSearch({
        keyword: '护肤',
        limitKeywords: 10,
        sorts: ['latest'],
        limitPerSort: 2,
        withDetails: false,
        dbPath,
        cdpUrl: 'http://127.0.0.1:9222',
      });

      expect(result.runs).toEqual([{ runId: 1, keyword: '护肤', status: 'partial_success', noteCount: 1 }]);
      const db = openDatabase(dbPath);
      try {
        const noteCount = db.prepare('select count(*) as count from xhs_search_notes').get() as { count: number };
        const run = db.prepare('select status from xhs_search_runs where id = 1').get() as { status: string };
        expect(noteCount.count).toBe(1);
        expect(run.status).toBe('partial_success');
      } finally {
        db.close();
      }
    } finally {
      rmSync(tempDir, { recursive: true, force: true });
    }
  });

  it('merges analysis source fields from detail pages into search rows', async () => {
    const row = noteRow();
    const detailPage = {
      setDefaultTimeout: vi.fn(),
      close: vi.fn().mockResolvedValue(undefined),
    };
    const session = {
      context: {
        newPage: vi.fn().mockResolvedValue(detailPage),
      },
    } as unknown as XhsSession;
    xhsDetailMocks.collectXhsNoteDetail.mockResolvedValue({
      feedId: 'feed-1',
      xsecToken: 'detail-token',
      exploreUrl: 'https://www.xiaohongshu.com/explore/feed-1?xsec_token=detail-token',
      detailText: '详情正文',
      tags: ['护肤'],
      commentCountText: '2',
      likeText: '10',
      collectText: '9',
      shareText: '1',
      noteType: 'image',
      rawDetailText: '详情页完整文本',
      sourceTopicTexts: ['护肤', '屏障修护'],
      sourceComments: [{ contentText: '敏感肌能用吗？', authorName: '用户A', likeText: '4', rawText: '用户A\n敏感肌能用吗？\n4' }],
      mediaSources: [{ kind: 'image', url: 'https://example.com/image.jpg', posterUrl: null, altText: '封面' }],
      analysisSourceText: '标题：标题\n评论摘录：\n- 用户A：敏感肌能用吗？（赞 4）\n媒体素材：\n- image：https://example.com/image.jpg（封面）',
    });

    const result = await xhsSearchCollector.enrichXhsSearchRowsWithDetails(session, [row]);

    expect(xhsDetailMocks.collectXhsNoteDetail).toHaveBeenCalledWith(detailPage, row.searchResultUrl, {
      title: '标题',
      noteType: 'unknown',
      coverAltText: null,
      coverUrl: null,
      sourceTopicTexts: [],
    });
    expect(result.detailFailures).toEqual([]);
    expect(result.rows[0]).toMatchObject({
      xsecToken: 'detail-token',
      exploreUrl: 'https://www.xiaohongshu.com/explore/feed-1?xsec_token=detail-token',
      detailText: '详情正文',
      detailTags: ['护肤'],
      detailCommentCountText: '2',
      detailLikeText: '10',
      detailCollectText: '9',
      detailShareText: '1',
      noteType: 'image',
      rawDetailText: '详情页完整文本',
      sourceTopicTexts: ['护肤', '屏障修护'],
      sourceComments: [{ contentText: '敏感肌能用吗？', authorName: '用户A', likeText: '4', rawText: '用户A\n敏感肌能用吗？\n4' }],
      mediaSources: [{ kind: 'image', url: 'https://example.com/image.jpg', posterUrl: null, altText: '封面' }],
      analysisSourceText: '标题：标题\n评论摘录：\n- 用户A：敏感肌能用吗？（赞 4）\n媒体素材：\n- image：https://example.com/image.jpg（封面）',
    });
  });

  it('keeps original rows when opening a detail page fails', async () => {
    const row = noteRow();
    const session = {
      context: {
        newPage: async () => {
          throw new Error('Cannot open detail page');
        },
      },
    } as unknown as XhsSession;

    await expect(xhsSearchCollector.enrichXhsSearchRowsWithDetails(session, [row])).resolves.toEqual({
      rows: [row],
      detailFailures: [{ feedId: 'feed-1', message: 'Cannot open detail page' }],
    });
  });

  it('dedupes search rows by feed id preserving the first occurrence', () => {
    const firstRow = noteRow();
    const duplicateRow = { ...noteRow(), rankIndex: 2, title: '重复标题' };

    const rows = xhsSearchCollector.dedupeXhsSearchRowsByFeedId([firstRow, duplicateRow]);

    expect(rows).toEqual([firstRow]);
  });

  it('collects replacement rows when later sort results duplicate earlier sort feed ids', async () => {
    const tempDir = mkdtempSync(join(tmpdir(), 'xhs-search-collector-test-'));
    const dbPath = join(tempDir, 'collector.sqlite');
    const session = {
      page: { mouse: { wheel: vi.fn() } },
      close: vi.fn().mockResolvedValue(undefined),
    } as unknown as XhsSession;

    xhsSessionMocks.createXhsSession.mockResolvedValue(session);
    xhsSearchMocks.openXhsSearchPage.mockResolvedValue(undefined);
    xhsSessionMocks.captureXhsPageSnapshot.mockResolvedValue({ url: 'https://www.xiaohongshu.com/search_result?keyword=护肤', text: '', html: '' });
    xhsSearchMocks.collectXhsSearchNoteRows
      .mockResolvedValueOnce([
        noteRow({ sortKey: 'most_liked', sortLabel: '最多点赞', feedId: 'feed-a', rankIndex: 1, title: 'A' }),
        noteRow({ sortKey: 'most_liked', sortLabel: '最多点赞', feedId: 'feed-b', rankIndex: 2, title: 'B' }),
      ])
      .mockResolvedValueOnce([
        noteRow({ sortKey: 'most_commented', sortLabel: '最多评论', feedId: 'feed-a', rankIndex: 1, title: 'A duplicate' }),
        noteRow({ sortKey: 'most_commented', sortLabel: '最多评论', feedId: 'feed-c', rankIndex: 2, title: 'C' }),
        noteRow({ sortKey: 'most_commented', sortLabel: '最多评论', feedId: 'feed-d', rankIndex: 3, title: 'D' }),
      ]);

    try {
      const result = await xhsSearchCollector.collectXhsSearch({
        keyword: '护肤',
        limitKeywords: 10,
        sorts: ['most_liked', 'most_commented'],
        limitPerSort: 2,
        withDetails: false,
        dbPath,
        cdpUrl: 'http://127.0.0.1:9222',
      });

      expect(result.runs).toEqual([{ runId: 1, keyword: '护肤', status: 'success', noteCount: 4 }]);
      expect(xhsSearchMocks.collectXhsSearchNoteRows).toHaveBeenNthCalledWith(1, session.page, '护肤', 'most_liked', 2);
      expect(xhsSearchMocks.collectXhsSearchNoteRows).toHaveBeenNthCalledWith(2, session.page, '护肤', 'most_commented', 4);

      const db = openDatabase(dbPath);
      try {
        const rows = db.prepare('select sort_key, rank_index, feed_id, title from xhs_search_notes order by sort_key, rank_index').all();
        expect(rows).toEqual([
          { sort_key: 'most_commented', rank_index: 1, feed_id: 'feed-c', title: 'C' },
          { sort_key: 'most_commented', rank_index: 2, feed_id: 'feed-d', title: 'D' },
          { sort_key: 'most_liked', rank_index: 1, feed_id: 'feed-a', title: 'A' },
          { sort_key: 'most_liked', rank_index: 2, feed_id: 'feed-b', title: 'B' },
        ]);
      } finally {
        db.close();
      }
    } finally {
      rmSync(tempDir, { recursive: true, force: true });
    }
  });

  it('rejects missing Huitun run keywords before creating a browser session', async () => {
    const tempDir = mkdtempSync(join(tmpdir(), 'xhs-search-collector-test-'));
    const dbPath = join(tempDir, 'collector.sqlite');
    const db = openDatabase(dbPath);
    try {
      initializeSchema(db);
    } finally {
      db.close();
    }

    try {
      await expect(
        xhsSearchCollector.collectXhsSearch({
          keyword: undefined,
          fromHuitunRunId: 999999,
          limitKeywords: 10,
          sorts: ['latest'],
          limitPerSort: 1,
          withDetails: false,
          dbPath,
          cdpUrl: 'http://127.0.0.1:1',
        }),
      ).rejects.toThrow('No keywords found for xhs-search.');
    } finally {
      rmSync(tempDir, { recursive: true, force: true });
    }
  });
});

import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it, vi } from 'vitest';

import { openDatabase } from '../src/db/client.js';
import { CollectorRepository } from '../src/db/repositories.js';
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

import { XhsRateLimitError } from '../src/browser/xhs-note-detail.js';
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
    vi.useRealTimers();
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
        detailDelayMinMs: 0,
        detailDelayMaxMs: 0,
        detailBudget: 30,
        stopOnRateLimit: true,
        resumeMissingDetails: true,
        dbPath,
        cdpUrl: 'http://127.0.0.1:9222',
      });

      expect(result.runs).toEqual([{ runId: 1, keyword: '护肤', status: 'partial_success', noteCount: 1 }]);
      expect(result).toMatchObject({ rateLimited: false, detailBudgetUsed: 0 });
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

    const detailState = { detailBudgetUsed: 0, rateLimited: false, detailBudgetExhausted: false };

    const result = await xhsSearchCollector.enrichXhsSearchRowsWithDetails(session, [row], {
      detailDelayMinMs: 0,
      detailDelayMaxMs: 0,
      detailBudget: 30,
    }, detailState);

    expect(xhsDetailMocks.collectXhsNoteDetail).toHaveBeenCalledWith(detailPage, row.searchResultUrl, {
      title: '标题',
      noteType: 'unknown',
      coverAltText: null,
      coverUrl: null,
      sourceTopicTexts: [],
    });
    expect(result.detailFailures).toEqual([]);
    expect(detailState.detailBudgetUsed).toBe(1);
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

    const detailState = { detailBudgetUsed: 0, rateLimited: false, detailBudgetExhausted: false };

    await expect(
      xhsSearchCollector.enrichXhsSearchRowsWithDetails(
        session,
        [row],
        {
          detailDelayMinMs: 0,
          detailDelayMaxMs: 0,
          detailBudget: 30,
        },
        detailState,
      ),
    ).resolves.toEqual({
      rows: [row],
      detailFailures: [{ feedId: 'feed-1', message: 'Cannot open detail page', rateLimited: false }],
    });
    expect(detailState.detailBudgetUsed).toBe(0);
  });

  it('does not spend detail budget when opening a page fails and attempts later rows', async () => {
    const tempDir = mkdtempSync(join(tmpdir(), 'xhs-search-collector-test-'));
    const dbPath = join(tempDir, 'collector.sqlite');
    const rows = [
      noteRow({ feedId: 'feed-a', rankIndex: 1, title: 'A' }),
      noteRow({ feedId: 'feed-b', rankIndex: 2, title: 'B' }),
    ];
    const detailPage = {
      setDefaultTimeout: vi.fn(),
      close: vi.fn().mockResolvedValue(undefined),
    };
    const session = {
      page: {},
      context: {
        newPage: vi.fn().mockRejectedValueOnce(new Error('Cannot open detail page')).mockResolvedValueOnce(detailPage),
      },
      close: vi.fn().mockResolvedValue(undefined),
    } as unknown as XhsSession;

    xhsSessionMocks.createXhsSession.mockResolvedValue(session);
    xhsSearchMocks.openXhsSearchPage.mockResolvedValue(undefined);
    xhsSearchMocks.collectXhsSearchNoteRows.mockResolvedValue(rows);
    xhsSessionMocks.captureXhsPageSnapshot.mockResolvedValue({ url: 'https://www.xiaohongshu.com/search_result?keyword=护肤', text: 'snapshot text', html: '<html></html>' });
    xhsDetailMocks.collectXhsNoteDetail.mockResolvedValue({
      feedId: 'feed-b',
      xsecToken: 'detail-token-b',
      exploreUrl: 'https://www.xiaohongshu.com/explore/feed-b?xsec_token=detail-token-b',
      detailText: '详情正文 B',
      tags: ['护肤'],
      commentCountText: '2',
      likeText: '10',
      collectText: '9',
      shareText: '1',
      noteType: 'image',
      rawDetailText: '详情页完整文本 B',
      sourceTopicTexts: ['护肤'],
      sourceComments: [],
      mediaSources: [],
      analysisSourceText: '标题：B',
    });

    try {
      const result = await xhsSearchCollector.collectXhsSearch({
        keyword: '护肤',
        limitKeywords: 10,
        sorts: ['latest'],
        limitPerSort: 2,
        withDetails: true,
        detailDelayMinMs: 0,
        detailDelayMaxMs: 0,
        detailBudget: 1,
        stopOnRateLimit: true,
        resumeMissingDetails: true,
        dbPath,
        cdpUrl: 'http://127.0.0.1:9222',
      });

      expect(session.context.newPage).toHaveBeenCalledTimes(2);
      expect(xhsDetailMocks.collectXhsNoteDetail).toHaveBeenCalledTimes(1);
      expect(xhsDetailMocks.collectXhsNoteDetail).toHaveBeenCalledWith(detailPage, rows[1].searchResultUrl, {
        title: 'B',
        noteType: 'unknown',
        coverAltText: null,
        coverUrl: null,
        sourceTopicTexts: [],
      });
      expect(result).toMatchObject({ detailBudgetUsed: 1, rateLimited: false });
      expect(result.runs).toEqual([{ runId: 1, keyword: '护肤', status: 'partial_success', noteCount: 2 }]);

      const db = openDatabase(dbPath);
      try {
        const notes = db.prepare('select feed_id, title, detail_text from xhs_search_notes order by rank_index').all();
        expect(notes).toEqual([
          { feed_id: 'feed-a', title: 'A', detail_text: null },
          { feed_id: 'feed-b', title: 'B', detail_text: '详情正文 B' },
        ]);

        const snapshots = db.prepare('select kind, object_key, text_content from xhs_raw_snapshots order by id').all();
        expect(snapshots).toEqual(
          expect.arrayContaining([
            expect.objectContaining({ kind: 'xhs_detail_collection_error', object_key: '护肤:latest:feed-a', text_content: expect.stringContaining('Cannot open detail page') }),
            expect.objectContaining({ kind: 'xhs_detail_budget_exhausted', object_key: '护肤:latest', text_content: expect.stringContaining('Used 1/1') }),
          ]),
        );
        expect(snapshots).toHaveLength(2);
      } finally {
        db.close();
      }
    } finally {
      rmSync(tempDir, { recursive: true, force: true });
    }
  });

  it('waits until the configured fixed detail delay elapses', async () => {
    vi.useFakeTimers();

    let resolved = false;
    const waitPromise = xhsSearchCollector.waitForXhsDetailDelay({ detailDelayMinMs: 1000, detailDelayMaxMs: 1000 }).then(() => {
      resolved = true;
    });

    await vi.advanceTimersByTimeAsync(999);
    expect(resolved).toBe(false);

    await vi.advanceTimersByTimeAsync(1);
    await waitPromise;
    expect(resolved).toBe(true);
  });

  it('stops detail enrichment when the detail budget is exhausted', async () => {
    const tempDir = mkdtempSync(join(tmpdir(), 'xhs-search-collector-test-'));
    const dbPath = join(tempDir, 'collector.sqlite');
    const rows = [
      noteRow({ feedId: 'feed-a', rankIndex: 1, title: 'A' }),
      noteRow({ feedId: 'feed-b', rankIndex: 2, title: 'B' }),
      noteRow({ feedId: 'feed-c', rankIndex: 3, title: 'C' }),
    ];
    const detailPage = {
      setDefaultTimeout: vi.fn(),
      close: vi.fn().mockResolvedValue(undefined),
    };
    const session = {
      page: {},
      context: {
        newPage: vi.fn().mockResolvedValue(detailPage),
      },
      close: vi.fn().mockResolvedValue(undefined),
    } as unknown as XhsSession;

    xhsSessionMocks.createXhsSession.mockResolvedValue(session);
    xhsSearchMocks.openXhsSearchPage.mockResolvedValue(undefined);
    xhsSearchMocks.collectXhsSearchNoteRows.mockResolvedValue(rows);
    xhsSessionMocks.captureXhsPageSnapshot.mockResolvedValue({ url: 'https://www.xiaohongshu.com/search_result?keyword=护肤', text: '', html: '' });
    xhsDetailMocks.collectXhsNoteDetail.mockResolvedValue({
      feedId: 'feed-a',
      xsecToken: 'detail-token',
      exploreUrl: 'https://www.xiaohongshu.com/explore/feed-a?xsec_token=detail-token',
      detailText: '详情正文',
      tags: ['护肤'],
      commentCountText: '2',
      likeText: '10',
      collectText: '9',
      shareText: '1',
      noteType: 'image',
      rawDetailText: '详情页完整文本',
      sourceTopicTexts: ['护肤'],
      sourceComments: [],
      mediaSources: [],
      analysisSourceText: '标题：A',
    });

    try {
      const result = await xhsSearchCollector.collectXhsSearch({
        keyword: '护肤',
        limitKeywords: 10,
        sorts: ['latest'],
        limitPerSort: 3,
        withDetails: true,
        detailDelayMinMs: 0,
        detailDelayMaxMs: 0,
        detailBudget: 1,
        stopOnRateLimit: true,
        resumeMissingDetails: true,
        dbPath,
        cdpUrl: 'http://127.0.0.1:9222',
      });

      expect(result).toMatchObject({ detailBudgetUsed: 1, rateLimited: false });
      expect(result.runs).toEqual([{ runId: 1, keyword: '护肤', status: 'partial_success', noteCount: 3 }]);
      expect(xhsDetailMocks.collectXhsNoteDetail).toHaveBeenCalledTimes(1);

      const db = openDatabase(dbPath);
      try {
        const snapshots = db.prepare('select kind, object_key, text_content from xhs_raw_snapshots order by id').all();
        expect(snapshots).toEqual([
          { kind: 'xhs_detail_budget_exhausted', object_key: '护肤:latest', text_content: expect.stringContaining('Used 1/1') },
        ]);
      } finally {
        db.close();
      }
    } finally {
      rmSync(tempDir, { recursive: true, force: true });
    }
  });

  it('stops the whole batch when a detail page hits XHS rate limit', async () => {
    const tempDir = mkdtempSync(join(tmpdir(), 'xhs-search-rate-limit-test-'));
    const dbPath = join(tempDir, 'collector.sqlite');
    const detailPage = {
      setDefaultTimeout: vi.fn(),
      close: vi.fn().mockResolvedValue(undefined),
    };
    const session = {
      page: {},
      context: {
        newPage: vi.fn().mockResolvedValue(detailPage),
      },
      close: vi.fn().mockResolvedValue(undefined),
    } as unknown as XhsSession;

    xhsSessionMocks.createXhsSession.mockResolvedValue(session);
    xhsSearchMocks.openXhsSearchPage.mockResolvedValue(undefined);
    xhsSessionMocks.captureXhsPageSnapshot.mockResolvedValue({
      url: 'https://www.xiaohongshu.com/search_result?keyword=护肤',
      text: '访问频繁，请稍后再试',
      html: '<html></html>',
    });
    xhsSearchMocks.collectXhsSearchNoteRows.mockResolvedValueOnce([
      noteRow({ keyword: '护肤', feedId: 'feed-a', rankIndex: 1, title: 'A' }),
    ]);
    xhsDetailMocks.collectXhsNoteDetail.mockRejectedValue(
      new XhsRateLimitError(
        'XHS rate limited: error_code=300013 访问频繁，请稍后再试',
        'https://www.xiaohongshu.com/website-login/error?error_code=300013',
        '访问频繁，请稍后再试',
      ),
    );

    try {
      const result = await xhsSearchCollector.collectXhsSearch({
        keyword: '护肤',
        limitKeywords: 10,
        sorts: ['latest', 'most_liked'],
        limitPerSort: 1,
        withDetails: true,
        detailDelayMinMs: 0,
        detailDelayMaxMs: 0,
        detailBudget: 30,
        stopOnRateLimit: true,
        resumeMissingDetails: true,
        dbPath,
        cdpUrl: 'http://127.0.0.1:9222',
      });

      expect(result.rateLimited).toBe(true);
      expect(result.rateLimitContext).toEqual({
        keyword: '护肤',
        sortKey: 'latest',
        feedId: 'feed-a',
        message: 'XHS rate limited: error_code=300013 访问频繁，请稍后再试',
      });
      expect(result.runs).toEqual([{ runId: 1, keyword: '护肤', status: 'partial_success', noteCount: 1 }]);
      expect(xhsSearchMocks.collectXhsSearchNoteRows).toHaveBeenCalledTimes(1);

      const db = openDatabase(dbPath);
      try {
        const run = db.prepare('select status, error_stage, error_message from xhs_search_runs where id = 1').get();
        const snapshots = db.prepare('select kind, object_key from xhs_raw_snapshots').all();
        expect(run).toEqual({
          status: 'partial_success',
          error_stage: 'xhs_rate_limited',
          error_message: 'XHS rate limited: error_code=300013 访问频繁，请稍后再试',
        });
        expect(snapshots).toEqual([{ kind: 'xhs_rate_limited', object_key: '护肤:latest:feed-a' }]);
      } finally {
        db.close();
      }
    } finally {
      rmSync(tempDir, { recursive: true, force: true });
    }
  });

  it('treats XHS rate limit as an ordinary detail failure when stopOnRateLimit is disabled', async () => {
    const tempDir = mkdtempSync(join(tmpdir(), 'xhs-search-no-stop-rate-limit-test-'));
    const dbPath = join(tempDir, 'collector.sqlite');
    const detailPage = {
      setDefaultTimeout: vi.fn(),
      close: vi.fn().mockResolvedValue(undefined),
    };
    const session = {
      page: {},
      context: {
        newPage: vi.fn().mockResolvedValue(detailPage),
      },
      close: vi.fn().mockResolvedValue(undefined),
    } as unknown as XhsSession;

    xhsSessionMocks.createXhsSession.mockResolvedValue(session);
    xhsSearchMocks.openXhsSearchPage.mockResolvedValue(undefined);
    xhsSessionMocks.captureXhsPageSnapshot.mockResolvedValue({
      url: 'https://www.xiaohongshu.com/search_result?keyword=护肤',
      text: '访问频繁，请稍后再试',
      html: '<html></html>',
    });
    xhsSearchMocks.collectXhsSearchNoteRows
      .mockResolvedValueOnce([
        noteRow({ keyword: '护肤', sortKey: 'latest', feedId: 'feed-a', rankIndex: 1, title: 'A' }),
      ])
      .mockResolvedValueOnce([
        noteRow({ keyword: '护肤', sortKey: 'most_liked', sortLabel: '最多点赞', feedId: 'feed-b', rankIndex: 1, title: 'B' }),
      ]);
    xhsDetailMocks.collectXhsNoteDetail
      .mockRejectedValueOnce(
        new XhsRateLimitError(
          'XHS rate limited: error_code=300013 访问频繁，请稍后再试',
          'https://www.xiaohongshu.com/website-login/error?error_code=300013',
          '访问频繁，请稍后再试',
        ),
      )
      .mockResolvedValueOnce({
        feedId: 'feed-b',
        xsecToken: 'detail-token-b',
        exploreUrl: 'https://www.xiaohongshu.com/explore/feed-b?xsec_token=detail-token-b',
        detailText: '详情正文 B',
        tags: ['护肤'],
        commentCountText: '2',
        likeText: '10',
        collectText: '9',
        shareText: '1',
        noteType: 'image',
        rawDetailText: '详情页完整文本 B',
        sourceTopicTexts: ['护肤'],
        sourceComments: [],
        mediaSources: [],
        analysisSourceText: '标题：B',
      });

    try {
      const result = await xhsSearchCollector.collectXhsSearch({
        keyword: '护肤',
        limitKeywords: 10,
        sorts: ['latest', 'most_liked'],
        limitPerSort: 1,
        withDetails: true,
        detailDelayMinMs: 0,
        detailDelayMaxMs: 0,
        detailBudget: 30,
        stopOnRateLimit: false,
        resumeMissingDetails: true,
        dbPath,
        cdpUrl: 'http://127.0.0.1:9222',
      });

      expect(result.rateLimited).toBe(false);
      expect(result.rateLimitContext).toBeUndefined();
      expect(result.runs).toEqual([{ runId: 1, keyword: '护肤', status: 'partial_success', noteCount: 2 }]);
      expect(xhsSearchMocks.collectXhsSearchNoteRows).toHaveBeenCalledTimes(2);

      const db = openDatabase(dbPath);
      try {
        const run = db.prepare('select status, error_stage, error_message from xhs_search_runs where id = 1').get();
        const snapshots = db.prepare('select kind, object_key from xhs_raw_snapshots order by id').all();
        expect(run).toEqual({ status: 'partial_success', error_stage: null, error_message: null });
        expect(snapshots).toEqual([
          { kind: 'xhs_detail_collection_error', object_key: '护肤:latest:feed-a' },
        ]);
      } finally {
        db.close();
      }
    } finally {
      rmSync(tempDir, { recursive: true, force: true });
    }
  });

  it('does not start later Huitun keyword collection after XHS rate limit', async () => {
    const tempDir = mkdtempSync(join(tmpdir(), 'xhs-search-huitun-rate-limit-test-'));
    const dbPath = join(tempDir, 'collector.sqlite');
    const db = openDatabase(dbPath);
    let huitunRunId: number;
    try {
      initializeSchema(db);
      const repository = new CollectorRepository(db);
      huitunRunId = repository.createRun({
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
          rankIndex: 2,
        },
      ]);
    } finally {
      db.close();
    }

    const detailPage = {
      setDefaultTimeout: vi.fn(),
      close: vi.fn().mockResolvedValue(undefined),
    };
    const session = {
      page: {},
      context: {
        newPage: vi.fn().mockResolvedValue(detailPage),
      },
      close: vi.fn().mockResolvedValue(undefined),
    } as unknown as XhsSession;

    xhsSessionMocks.createXhsSession.mockResolvedValue(session);
    xhsSearchMocks.openXhsSearchPage.mockResolvedValue(undefined);
    xhsSessionMocks.captureXhsPageSnapshot.mockResolvedValue({
      url: 'https://www.xiaohongshu.com/search_result',
      text: '访问频繁，请稍后再试',
      html: '<html></html>',
    });
    xhsSearchMocks.collectXhsSearchNoteRows.mockResolvedValueOnce([
      noteRow({ keyword: '屏障修复', feedId: 'feed-a', rankIndex: 1, title: 'A' }),
    ]);
    xhsDetailMocks.collectXhsNoteDetail.mockRejectedValue(
      new XhsRateLimitError(
        'XHS rate limited: error_code=300013 访问频繁，请稍后再试',
        'https://www.xiaohongshu.com/website-login/error?error_code=300013',
        '访问频繁，请稍后再试',
      ),
    );

    try {
      const result = await xhsSearchCollector.collectXhsSearch({
        keyword: undefined,
        fromHuitunRunId: huitunRunId,
        limitKeywords: 2,
        sorts: ['latest'],
        limitPerSort: 1,
        withDetails: true,
        detailDelayMinMs: 0,
        detailDelayMaxMs: 0,
        detailBudget: 30,
        stopOnRateLimit: true,
        resumeMissingDetails: true,
        dbPath,
        cdpUrl: 'http://127.0.0.1:9222',
      });

      expect(result.rateLimited).toBe(true);
      expect(result.runs).toEqual([
        { runId: 1, keyword: '屏障修复', status: 'partial_success', noteCount: 1 },
      ]);
      expect(xhsSearchMocks.openXhsSearchPage).toHaveBeenCalledTimes(1);
      expect(xhsSearchMocks.collectXhsSearchNoteRows).toHaveBeenCalledTimes(1);
      expect(xhsSearchMocks.collectXhsSearchNoteRows).toHaveBeenCalledWith(session.page, '屏障修复', 'latest', 1);
    } finally {
      rmSync(tempDir, { recursive: true, force: true });
    }
  });

  it('marks later Huitun keyword runs partial when the global detail budget is already exhausted', async () => {
    const tempDir = mkdtempSync(join(tmpdir(), 'xhs-search-collector-test-'));
    const dbPath = join(tempDir, 'collector.sqlite');
    const db = openDatabase(dbPath);
    let huitunRunId: number;
    try {
      initializeSchema(db);
      const repository = new CollectorRepository(db);
      huitunRunId = repository.createRun({
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
          rankIndex: 2,
        },
      ]);
    } finally {
      db.close();
    }

    const detailPage = {
      setDefaultTimeout: vi.fn(),
      close: vi.fn().mockResolvedValue(undefined),
    };
    const session = {
      page: {},
      context: {
        newPage: vi.fn().mockResolvedValue(detailPage),
      },
      close: vi.fn().mockResolvedValue(undefined),
    } as unknown as XhsSession;

    xhsSessionMocks.createXhsSession.mockResolvedValue(session);
    xhsSearchMocks.openXhsSearchPage.mockResolvedValue(undefined);
    xhsSessionMocks.captureXhsPageSnapshot.mockResolvedValue({ url: 'https://www.xiaohongshu.com/search_result', text: 'search text', html: '<html></html>' });
    xhsSearchMocks.collectXhsSearchNoteRows
      .mockResolvedValueOnce([
        noteRow({ keyword: '屏障修复', feedId: 'feed-a', rankIndex: 1, title: 'A' }),
        noteRow({ keyword: '屏障修复', feedId: 'feed-b', rankIndex: 2, title: 'B' }),
      ])
      .mockResolvedValueOnce([
        noteRow({ keyword: '早C晚A', feedId: 'feed-c', rankIndex: 1, title: 'C' }),
        noteRow({ keyword: '早C晚A', feedId: 'feed-d', rankIndex: 2, title: 'D' }),
      ]);
    xhsDetailMocks.collectXhsNoteDetail.mockResolvedValue({
      feedId: 'feed-a',
      xsecToken: 'detail-token',
      exploreUrl: 'https://www.xiaohongshu.com/explore/feed-a?xsec_token=detail-token',
      detailText: '详情正文',
      tags: ['护肤'],
      commentCountText: '2',
      likeText: '10',
      collectText: '9',
      shareText: '1',
      noteType: 'image',
      rawDetailText: '详情页完整文本',
      sourceTopicTexts: ['护肤'],
      sourceComments: [],
      mediaSources: [],
      analysisSourceText: '标题：A',
    });

    try {
      const result = await xhsSearchCollector.collectXhsSearch({
        keyword: undefined,
        fromHuitunRunId: huitunRunId,
        limitKeywords: 2,
        sorts: ['latest'],
        limitPerSort: 2,
        withDetails: true,
        detailDelayMinMs: 0,
        detailDelayMaxMs: 0,
        detailBudget: 1,
        stopOnRateLimit: true,
        resumeMissingDetails: true,
        dbPath,
        cdpUrl: 'http://127.0.0.1:9222',
      });

      expect(result.detailBudgetUsed).toBe(1);
      expect(result.runs).toEqual([
        { runId: 1, keyword: '屏障修复', status: 'partial_success', noteCount: 2 },
        { runId: 2, keyword: '早C晚A', status: 'partial_success', noteCount: 2 },
      ]);
      expect(xhsDetailMocks.collectXhsNoteDetail).toHaveBeenCalledTimes(1);

      const resultDb = openDatabase(dbPath);
      try {
        const notes = resultDb.prepare('select run_id, feed_id, title from xhs_search_notes order by run_id, rank_index').all();
        expect(notes).toEqual([
          { run_id: 1, feed_id: 'feed-a', title: 'A' },
          { run_id: 1, feed_id: 'feed-b', title: 'B' },
          { run_id: 2, feed_id: 'feed-c', title: 'C' },
          { run_id: 2, feed_id: 'feed-d', title: 'D' },
        ]);

        const snapshots = resultDb
          .prepare('select run_id, kind, object_key from xhs_raw_snapshots where kind = ? order by run_id, id')
          .all('xhs_detail_budget_exhausted');
        expect(snapshots).toEqual([
          { run_id: 1, kind: 'xhs_detail_budget_exhausted', object_key: '屏障修复:latest' },
          { run_id: 2, kind: 'xhs_detail_budget_exhausted', object_key: '早C晚A:latest' },
        ]);
      } finally {
        resultDb.close();
      }
    } finally {
      rmSync(tempDir, { recursive: true, force: true });
    }
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
        detailDelayMinMs: 0,
        detailDelayMaxMs: 0,
        detailBudget: 30,
        stopOnRateLimit: true,
        resumeMissingDetails: true,
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
          detailDelayMinMs: 0,
          detailDelayMaxMs: 0,
          detailBudget: 30,
          stopOnRateLimit: true,
          resumeMissingDetails: true,
          dbPath,
          cdpUrl: 'http://127.0.0.1:1',
        }),
      ).rejects.toThrow('No keywords found for xhs-search.');
    } finally {
      rmSync(tempDir, { recursive: true, force: true });
    }
  });
});

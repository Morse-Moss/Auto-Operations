import { describe, expect, it, vi } from 'vitest';
import type { Page } from 'playwright-core';
import {
  collectTopLikedNoteRows,
  getDetailUrlForDebug,
  openHotWordDetail,
  parseNoteRowsFromDomPayload,
} from '../src/browser/hotword-detail.js';
import { collectNoteDetail, parseNoteDetailText } from '../src/browser/note-detail.js';

import type { NoteListRow } from '../src/types.js';

describe('openHotWordDetail', () => {
  it('opens the same date-range detail URL exposed by the debug helper', async () => {
    const page = {
      goto: vi.fn().mockResolvedValue(undefined),
      waitForLoadState: vi.fn().mockResolvedValue(undefined),
      waitForSelector: vi.fn().mockResolvedValue(undefined),
    } as unknown as Page;

    await openHotWordDetail(page, '浴缸', 30);

    expect(page.goto).toHaveBeenCalledWith(getDetailUrlForDebug('浴缸', 30), { waitUntil: 'domcontentloaded' });
  });
});

describe('parseNoteRowsFromDomPayload', () => {
  it('parses Huitun note-list DOM payloads into NoteListRow values', () => {
    const payloads = [
      {
        key: '11331652220-2026-05-19 16:39:27',
        title: '给我看看你们的浴缸👀',
        authorName: '晚儿的装修碎碎念（杭州老破小版）',
        authorLevel: '路人',
        coverUrl: 'http://example.com/cover.webp',
        duration: null,
        updatedText: '更新时间：2026-05-21 10:57:10',
        tags: ['浴缸选择', '泡澡', '更多...'],
        cells: [
          '给我看看你们的浴缸👀\n晚儿的装修碎碎念（杭州老破小版）\n路人',
          '2026-05-19 16:39:27',
          '1,317',
          '8',
          '2',
          '41',
        ],
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
        cells: [
          '00:32\n瀑布按摩浴缸\n浴缸蒸汽房佛山源头厂家\n路人',
          '2026-05-15 16:39:22',
          '10',
          '1',
          '0',
          '0',
        ],
      },
    ];

    const expected: NoteListRow[] = [
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
        comments: 41,
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
        comments: 0,
      },
    ];

    expect(parseNoteRowsFromDomPayload('浴缸', payloads)).toEqual(expected);
  });

  it('parses note metrics by table headers when metric columns are reordered', () => {
    const [row] = parseNoteRowsFromDomPayload('浴缸', [
      {
        key: 'hot-note-1',
        title: '点赞排序后的热点笔记',
        authorName: '作者',
        authorLevel: '路人',
        coverUrl: null,
        duration: null,
        updatedText: '更新时间：2026-05-21 10:57:10',
        tags: ['热点'],
        headers: ['笔记', '发布时间', '点赞数', '预估阅读量', '收藏数', '评论数'],
        cells: ['点赞排序后的热点笔记\n作者\n路人', '2026-05-19 16:39:27', '88', '1,317', '9', '7'],
      },
    ]);

    expect(row).toMatchObject({
      estimatedReads: 1317,
      likes: 88,
      collects: 9,
      comments: 7,
    });
  });
});

describe('collectTopLikedNoteRows', () => {
  it('caps collection to top 20 rows and verifies likes order', async () => {
    const headers = ['笔记', '发布时间', '预估阅读量', '点赞', '收藏', '评论'];
    const rows = Array.from({ length: 25 }, (_, index) => {
      const likes = 100 - index;
      return {
        getAttribute: vi.fn().mockResolvedValue(`note-${index + 1}`),
        locator: vi.fn((selector: string) => {
          if (selector === 'td') {
            return {
              allTextContents: vi.fn().mockResolvedValue([
                `热点笔记${index + 1}\n作者\n路人`,
                '2026-05-19 16:39:27',
                String(1000 - index),
                String(likes),
                '5',
                '1',
              ]),
            };
          }
          if (selector === 'img') {
            return { count: vi.fn().mockResolvedValue(0) };
          }
          if (selector === '[class*="note_title"]') {
            return { count: vi.fn().mockResolvedValue(1), first: vi.fn(() => ({ textContent: vi.fn().mockResolvedValue(`热点笔记${index + 1}`) })) };
          }
          if (selector === '[class*="live_anchor"] [class*="one_line"]') {
            return { count: vi.fn().mockResolvedValue(1), first: vi.fn(() => ({ textContent: vi.fn().mockResolvedValue('作者') })) };
          }
          if (selector === '[class*="live_anchor"] span[style*="137"]') {
            return { count: vi.fn().mockResolvedValue(1), first: vi.fn(() => ({ textContent: vi.fn().mockResolvedValue('路人') })) };
          }
          if (selector === '[class*="duration"] span, [class*="duration"]') {
            return { count: vi.fn().mockResolvedValue(0) };
          }
          if (selector === 'div') {
            return { allTextContents: vi.fn().mockResolvedValue(['更新时间：2026-05-21 10:57:10']) };
          }
          if (selector === '[class*="item_tag"]') {
            return { allTextContents: vi.fn().mockResolvedValue(['热点']) };
          }
          return { count: vi.fn().mockResolvedValue(0), allTextContents: vi.fn().mockResolvedValue([]) };
        }),
      };
    });
    const rowLocator = {
      count: vi.fn().mockResolvedValue(rows.length),
      nth: vi.fn((index: number) => rows[index]),
    };
    const headerLocator = {
      allTextContents: vi.fn().mockResolvedValue(headers),
      filter: vi.fn(() => ({
        count: vi.fn().mockResolvedValue(1),
        first: vi.fn(() => ({
          click: vi.fn().mockResolvedValue(undefined),
          getAttribute: vi.fn().mockResolvedValue('descending'),
          locator: vi.fn(() => ({ count: vi.fn().mockResolvedValue(1) })),
        })),
      })),
    };
    const page = {
      locator: vi.fn((selector: string) => {
        if (selector === 'tr.ant-table-row') return rowLocator;
        if (selector === 'thead th') return headerLocator;
        if (selector === '.ant-spin-spinning') return { count: vi.fn().mockResolvedValue(0) };
        return { count: vi.fn().mockResolvedValue(0) };
      }),
      waitForLoadState: vi.fn().mockResolvedValue(undefined),
      waitForTimeout: vi.fn().mockResolvedValue(undefined),
    } as unknown as Page;

    const result = await collectTopLikedNoteRows(page, '浴缸', 25);

    expect(result.rows).toHaveLength(20);
    expect(result.rows[0]).toMatchObject({ huitunNoteKey: 'note-1', likes: 100, listRank: 1, listPage: 1 });
    expect(result.rows[19]).toMatchObject({ huitunNoteKey: 'note-20', likes: 81, listRank: 20, listPage: 1 });
    expect(result.likesSort.status).toBe('verified');
  });
});

describe('collectNoteDetail', () => {
  it('scrolls and force-clicks the note title, then presses Escape when the modal never becomes visible', async () => {
    const click = vi.fn().mockResolvedValue(undefined);
    const title = {
      first: vi.fn(() => title),
      scrollIntoViewIfNeeded: vi.fn().mockResolvedValue(undefined),
      click,
    };
    const row = {
      count: vi.fn().mockResolvedValue(1),
      first: vi.fn(() => row),
      locator: vi.fn(() => title),
    };
    const modal = {
      filter: vi.fn(() => modal),
      first: vi.fn(() => modal),
      waitFor: vi.fn().mockRejectedValue(new Error('modal did not open')),
      innerText: vi.fn(),
    };
    const keyboard = {
      press: vi.fn().mockResolvedValue(undefined),
    };
    const page = {
      locator: vi.fn((selector: string) => (selector === '.ant-modal' ? modal : row)),
      keyboard,
    } as unknown as Page;
    const note: NoteListRow = {
      hotWord: '浴缸',
      huitunNoteKey: 'note-cleanup',
      title: '浴缸笔记',
      authorName: null,
      authorLevel: null,
      coverUrl: null,
      isVideo: false,
      videoDuration: null,
      publishedAt: null,
      updatedAt: null,
      tags: [],
      estimatedReads: null,
      likes: null,
      collects: null,
      comments: null,
    };

    await expect(collectNoteDetail(page, note)).rejects.toThrow('modal did not open');

    expect(title.scrollIntoViewIfNeeded).toHaveBeenCalledTimes(1);
    expect(click).toHaveBeenCalledWith({ force: true });
    expect(keyboard.press).toHaveBeenCalledWith('Escape');
  });
});

describe('parseNoteDetailText', () => {
  it('parses Huitun note-detail modal text into NoteDetail values', () => {
    const text = `00:32
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
阅读粉丝比`;

    expect(parseNoteDetailText('11304858949-2026-05-15 16:39:22', text)).toEqual({
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
      readFollowerRatioText: '5.68%',
    });
  });

  it('prefers metric labels from 数据概览 when labels repeat earlier in the modal', () => {
    const text = `浴缸爆款笔记
99
点赞
88
收藏
77
评论
66
分享
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
2
收藏
3
评论
4
分享
2.64%
阅读曝光比
5.68%
阅读粉丝比`;

    expect(parseNoteDetailText('11304858949-2026-05-15 16:39:22', text)).toMatchObject({
      estimatedExposure: 379,
      estimatedReads: 10,
      likes: 1,
      collects: 2,
      comments: 3,
      shares: 4,
      authorFollowers: 176,
      authorNoteCount: 113,
      authorTotalLikesCollects: 337,
      readExposureRatioText: '2.64%',
      readFollowerRatioText: '5.68%',
    });
  });
});

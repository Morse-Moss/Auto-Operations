import type { Page } from 'playwright-core';
import { describe, expect, it } from 'vitest';

import {
  XHS_LOGIN_REQUIRED_MESSAGE,
  XHS_SEARCH_SORTS,
  assertXhsLoggedIn,
  buildXhsSearchUrl,
  collectXhsSearchNoteRows,
  extractXhsNoteIdentity,
  isXhsLoginRequiredText,
  isXhsSortActive,
  parseXhsInitialStateSearchCardPayloads,
  parseXhsSearchNoteRows,
  parseXhsSortKeys,
  pickBestXhsSearchResultUrl,
  pickXhsSearchCardsForCollection,
  switchXhsSearchSort,
} from '../src/browser/xhs-search.js';

describe('XHS search helpers', () => {
  it('builds an encoded Xiaohongshu search URL', () => {
    expect(buildXhsSearchUrl('护肤 修护')).toBe('https://www.xiaohongshu.com/search_result?keyword=%E6%8A%A4%E8%82%A4%20%E4%BF%AE%E6%8A%A4');
  });

  it('maps supported sort keys to verified Xiaohongshu labels', () => {
    expect(XHS_SEARCH_SORTS).toEqual({
      latest: '最新',
      most_liked: '最多点赞',
      most_commented: '最多评论',
      most_collected: '最多收藏',
    });
  });

  it('parses comma-separated sort keys', () => {
    expect(parseXhsSortKeys('latest,most_liked,most_commented,most_collected')).toEqual([
      'latest',
      'most_liked',
      'most_commented',
      'most_collected',
    ]);
  });

  it('uses the default sort list when the sort string is undefined', () => {
    expect(parseXhsSortKeys(undefined)).toEqual(['latest', 'most_liked', 'most_commented', 'most_collected']);
  });

  it('returns a fresh default sort list each time', () => {
    const sorts = parseXhsSortKeys(undefined);
    sorts.reverse();

    expect(parseXhsSortKeys(undefined)).toEqual(['latest', 'most_liked', 'most_commented', 'most_collected']);
  });

  it('rejects unsupported sort keys', () => {
    expect(() => parseXhsSortKeys('latest,most_shared')).toThrow('Unsupported XHS sort key: most_shared');
  });

  it('detects Xiaohongshu login walls', () => {
    expect(isXhsLoginRequiredText('登录后查看搜索结果\n手机号登录')).toBe(true);
    expect(isXhsLoginRequiredText('我 马上登录即可 刷到更懂你的优质内容\n搜索最新种草、拔草信息')).toBe(true);
    expect(isXhsLoginRequiredText('全部\n图文\n筛选\n最多收藏')).toBe(false);
  });

  it('detects the active Xiaohongshu search sort by exact label', () => {
    expect(isXhsSortActive(['综合', '最多收藏'], 'most_collected')).toBe(true);
    expect(isXhsSortActive(['综合', '最多评论'], 'most_collected')).toBe(false);
  });

  it('picks tokenized search result URLs before tokenized explore URLs while rejecting short or empty note URLs', () => {
    expect(pickBestXhsSearchResultUrl([
      '/explore/feed1',
      '/search_result/feed1?xsec_token=token%2Ba',
    ])).toBe('https://www.xiaohongshu.com/search_result/feed1?xsec_token=token%2Ba');

    expect(pickBestXhsSearchResultUrl([
      'https://www.xiaohongshu.com/explore/feed1?xsec_token=token',
      'https://www.xiaohongshu.com/search_result/feed2?xsec_token=token2',
    ])).toBe('https://www.xiaohongshu.com/search_result/feed2?xsec_token=token2');

    expect(pickBestXhsSearchResultUrl(['/explore/feed1?xsec_token=token'])).toBe('https://www.xiaohongshu.com/explore/feed1?xsec_token=token');
    expect(pickBestXhsSearchResultUrl(['/explore/feed1'])).toBeNull();
    expect(pickBestXhsSearchResultUrl(['/explore/?xsec_token=token'])).toBeNull();
    expect(pickBestXhsSearchResultUrl(['/search_result/?xsec_token=token'])).toBeNull();
  });

  it('prefers valid DOM cards over initial-state cards for collection', () => {
    const domCards = [
      {
        searchResultUrl: '/explore/dom-feed?xsec_token=dom-token',
        authorProfileUrl: '/user/profile/dom-author',
        coverUrl: null,
        rawText: 'DOM sorted result',
      },
    ];
    const initialStateCards = [
      {
        searchResultUrl: '/search_result/stale-feed?xsec_token=stale-token',
        authorProfileUrl: '/user/profile/stale-author',
        coverUrl: null,
        rawText: 'Stale initial state result',
      },
    ];

    expect(pickXhsSearchCardsForCollection(domCards, initialStateCards)).toEqual(domCards);
  });

  it('falls back to initial-state cards when DOM cards do not contain valid tokenized search results', () => {
    const domCards = [
      {
        searchResultUrl: null,
        authorProfileUrl: null,
        coverUrl: null,
        rawText: 'Profile recommendation without note URL',
      },
      {
        searchResultUrl: 'https://www.xiaohongshu.com/user/profile/dom-author',
        authorProfileUrl: '/user/profile/dom-author',
        coverUrl: null,
        rawText: 'Profile recommendation without note identity',
      },
    ];
    const initialStateCards = [
      {
        searchResultUrl: '/search_result/fallback-feed?xsec_token=fallback-token',
        authorProfileUrl: '/user/profile/fallback-author',
        coverUrl: null,
        rawText: 'Fallback initial state result',
      },
    ];

    expect(pickXhsSearchCardsForCollection(domCards, initialStateCards)).toEqual(initialStateCards);
  });

  it('parses Xiaohongshu search card payloads from initial state feeds', () => {
    const payloads = parseXhsInitialStateSearchCardPayloads({
      search: {
        feeds: {
          _rawValue: [
            {
              id: 'feed1',
              xsecToken: 'token+a',
              title: '标题A',
              user: { userId: 'u1', nickname: '作者A' },
              cover: { urlDefault: 'https://example.com/cover-a.jpg', alt: '封面写着屏障修护步骤' },
              noteCard: {
                displayTitle: '展示标题A',
                type: 'video',
                tagList: [{ name: '屏障修护' }, { tagName: '干皮护肤' }],
              },
            },
          ],
        },
      },
    });

    expect(payloads).toEqual([{
      searchResultUrl: 'https://www.xiaohongshu.com/search_result/feed1?xsec_token=token%2Ba',
      authorProfileUrl: 'https://www.xiaohongshu.com/user/profile/u1',
      coverUrl: 'https://example.com/cover-a.jpg',
      noteType: 'video',
      coverAltText: '封面写着屏障修护步骤',
      sourceTopicTexts: ['护肤', '搜索排序:未知', '屏障修护', '干皮护肤'],
      rawText: expect.stringContaining('展示标题A'),
    }]);
    expect(payloads[0]?.rawText).toContain('标题A');
    expect(payloads[0]?.rawText).toContain('作者A');
  });

  it('returns no initial state search payloads when feeds are missing', () => {
    expect(parseXhsInitialStateSearchCardPayloads({ search: {} })).toEqual([]);
  });

  it('extracts note identity from absolute search result URLs and decodes xsec_token', () => {
    expect(extractXhsNoteIdentity('https://www.xiaohongshu.com/search_result/abc123?xsec_token=abc%2Bdef')).toEqual({
      feedId: 'abc123',
      xsecToken: 'abc+def',
    });
  });

  it('extracts note identity from relative explore URLs', () => {
    expect(extractXhsNoteIdentity('/explore/feed456?xsec_token=token')).toEqual({
      feedId: 'feed456',
      xsecToken: 'token',
    });
  });

  it('extracts note identity from short explore URLs without xsec_token', () => {
    expect(extractXhsNoteIdentity('/explore/feed789')).toEqual({
      feedId: 'feed789',
      xsecToken: null,
    });
  });

  it('rejects absolute URLs from unrelated hosts when extracting note identity', () => {
    expect(extractXhsNoteIdentity('https://evil.com/explore/feed?xsec_token=t')).toBeNull();
  });

  it('accepts the apex Xiaohongshu host when extracting note identity', () => {
    expect(extractXhsNoteIdentity('https://xiaohongshu.com/explore/feed?xsec_token=t')).toEqual({
      feedId: 'feed',
      xsecToken: 't',
    });
  });

  it('returns null for URLs without a usable note feed id', () => {
    expect(extractXhsNoteIdentity('https://www.xiaohongshu.com/user/profile/123')).toBeNull();
  });

  it('parses valid search card payloads into ranked note rows and skips invalid cards', () => {
    const rows = parseXhsSearchNoteRows({
      keyword: '护肤',
      sortKey: 'most_liked',
      cards: [
        {
          searchResultUrl: 'https://www.xiaohongshu.com/search_result/feed1?xsec_token=like%2Btoken',
          authorProfileUrl: 'https://www.xiaohongshu.com/user/profile/author1',
          coverUrl: 'https://ci.xiaohongshu.com/cover1.jpg',
          noteType: 'image',
          coverAltText: '白底产品封面',
          sourceTopicTexts: ['屏障修护', '护肤干货'],
          rawText: '爆款修护精华\n小红薯A\n2026-05-20\n点赞 1.2万',
        },
        {
          searchResultUrl: 'https://www.xiaohongshu.com/user/profile/recommendation',
          authorProfileUrl: null,
          coverUrl: null,
          rawText: '推荐用户\n不是笔记',
        },
        {
          searchResultUrl: '/explore/feed2?xsec_token=commentToken',
          authorProfileUrl: '/user/profile/author2',
          coverUrl: 'https://ci.xiaohongshu.com/cover2.jpg',
          rawText: '屏障修护经验\n小红薯B\n昨天\n评论 88',
        },
      ],
    });

    expect(rows).toHaveLength(2);
    expect(rows[0]).toMatchObject({
      keyword: '护肤',
      sortKey: 'most_liked',
      sortLabel: '最多点赞',
      rankIndex: 1,
      feedId: 'feed1',
      xsecToken: 'like+token',
      searchResultUrl: 'https://www.xiaohongshu.com/search_result/feed1?xsec_token=like%2Btoken',
      exploreUrl: null,
      title: '爆款修护精华',
      authorName: '小红薯A',
      authorProfileUrl: 'https://www.xiaohongshu.com/user/profile/author1',
      coverUrl: 'https://ci.xiaohongshu.com/cover1.jpg',
      publishedAtText: '2026-05-20',
      metricText: '点赞 1.2万',
      noteType: 'image',
      coverAltText: '白底产品封面',
      sourceTopicTexts: ['护肤', '搜索排序:最多点赞', '屏障修护', '护肤干货'],
      detailText: null,
      detailTags: [],
      detailCommentCountText: null,
      detailLikeText: null,
      detailCollectText: null,
      detailShareText: null,
      rawCardText: '爆款修护精华\n小红薯A\n2026-05-20\n点赞 1.2万',
    });
    expect(rows[1]).toMatchObject({
      keyword: '护肤',
      sortKey: 'most_liked',
      sortLabel: '最多点赞',
      rankIndex: 2,
      feedId: 'feed2',
      xsecToken: 'commentToken',
      searchResultUrl: '/explore/feed2?xsec_token=commentToken',
      exploreUrl: null,
      title: '屏障修护经验',
      authorName: '小红薯B',
      authorProfileUrl: '/user/profile/author2',
      coverUrl: 'https://ci.xiaohongshu.com/cover2.jpg',
      publishedAtText: '昨天',
      metricText: null,
      detailText: null,
      detailTags: [],
      detailCommentCountText: null,
      detailLikeText: null,
      detailCollectText: null,
      detailShareText: null,
      rawCardText: '屏障修护经验\n小红薯B\n昨天\n评论 88',
    });
  });

  it('prefers the metric footer over title and author text for non-latest sorts', () => {
    const rows = parseXhsSearchNoteRows({
      keyword: '护肤',
      sortKey: 'most_liked',
      cards: [{
        searchResultUrl: '/explore/feed321?xsec_token=metricToken',
        authorProfileUrl: '/user/profile/author321',
        coverUrl: null,
        rawText: '点赞收藏避坑标题\n点赞达人作者\n05-24\n点赞 321',
      }],
    });

    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      feedId: 'feed321',
      metricText: '点赞 321',
    });
  });

  it('falls back to feed id when card raw text is blank', () => {
    expect(parseXhsSearchNoteRows({
      keyword: '护肤',
      sortKey: 'latest',
      cards: [{
        searchResultUrl: '/explore/feed-without-text?xsec_token=token',
        authorProfileUrl: null,
        coverUrl: null,
        rawText: '  \n\t ',
      }],
    })[0]).toMatchObject({
      feedId: 'feed-without-text',
      title: 'feed-without-text',
      authorName: null,
      publishedAtText: null,
      metricText: null,
    });
  });

  it('collects only visible DOM search cards after sort switching', async () => {
    class FakeElement {
      constructor(
        readonly text: string,
        readonly width: number,
        readonly height: number,
        readonly display: string,
        readonly visibility: string,
      ) {}

      get textContent(): string {
        return this.text;
      }

      get innerText(): string {
        return this.text;
      }

      getBoundingClientRect(): { width: number; height: number } {
        return { width: this.width, height: this.height };
      }

      getAttribute(_name: string): string | null {
        return null;
      }
    }

    class FakeAnchor extends FakeElement {
      constructor(readonly href: string) {
        super('', 1, 1, 'block', 'visible');
      }

      override getAttribute(name: string): string | null {
        return name === 'href' ? this.href : null;
      }
    }

    class FakeSection extends FakeElement {
      constructor(
        text: string,
        width: number,
        height: number,
        display: string,
        visibility: string,
        readonly hrefs: string[],
      ) {
        super(text, width, height, display, visibility);
      }

      querySelectorAll(selector: string): FakeAnchor[] {
        return selector === 'a[href]' ? this.hrefs.map((href) => new FakeAnchor(href)) : [];
      }

      querySelector(_selector: string): null {
        return null;
      }
    }

    const sections = [
      new FakeSection('旧排序隐藏结果\n旧作者\n点赞 999', 0, 120, 'block', 'visible', ['/explore/hidden-feed?xsec_token=hidden-token', '/user/profile/hidden-author']),
      new FakeSection('新排序可见结果\n新作者\n点赞 100', 240, 120, 'block', 'visible', ['/explore/visible-feed?xsec_token=visible-token', '/user/profile/visible-author']),
    ];
    const globals = globalThis as typeof globalThis & {
      document?: { querySelectorAll: (selector: string) => FakeSection[] };
      window?: { getComputedStyle: (element: FakeElement) => { display: string; visibility: string } };
      HTMLElement?: typeof FakeElement;
      HTMLAnchorElement?: typeof FakeAnchor;
    };
    const originalDocument = globals.document;
    const originalWindow = globals.window;
    const originalHTMLElement = globals.HTMLElement;
    const originalHTMLAnchorElement = globals.HTMLAnchorElement;

    Object.defineProperty(globals, 'document', {
      configurable: true,
      value: { querySelectorAll: (selector: string) => selector === 'section.note-item' ? sections : [] },
    });
    Object.defineProperty(globals, 'window', {
      configurable: true,
      value: { getComputedStyle: (element: FakeElement) => ({ display: element.display, visibility: element.visibility }) },
    });
    Object.defineProperty(globals, 'HTMLElement', { configurable: true, value: FakeElement });
    Object.defineProperty(globals, 'HTMLAnchorElement', { configurable: true, value: FakeAnchor });

    try {
      const page = {
        evaluate: async (callback: unknown, arg?: unknown) => {
          const source = String(callback);
          if (source.includes('sortLabels')) {
            return true;
          }
          if (source.includes('candidates.find')) {
            return true;
          }
          if (source.includes('cardSignatures')) {
            return { cardCount: 1, signature: 'visible-before' };
          }
          if (source.includes('data-hp-kind') && arg === '最多点赞') {
            return true;
          }
          if (source.includes('activeElements')) {
            return ['最多点赞'];
          }
          if (source.includes('__INITIAL_STATE__')) {
            return null;
          }
          if (source.includes('authorProfileUrl') && source.includes('coverUrl')) {
            return (callback as () => unknown)();
          }
          return false;
        },
        getByText: () => ({ click: async () => undefined }),
        waitForFunction: async () => undefined,
        waitForTimeout: async () => undefined,
        mouse: { wheel: async () => undefined },
      } as unknown as Page;

      const rows = await collectXhsSearchNoteRows(page, '护肤', 'most_liked', 1);

      expect(rows).toHaveLength(1);
      expect(rows[0]).toMatchObject({
        feedId: 'visible-feed',
        title: '新排序可见结果',
        authorName: '新作者',
      });
    } finally {
      Object.defineProperty(globals, 'document', { configurable: true, value: originalDocument });
      Object.defineProperty(globals, 'window', { configurable: true, value: originalWindow });
      Object.defineProperty(globals, 'HTMLElement', { configurable: true, value: originalHTMLElement });
      Object.defineProperty(globals, 'HTMLAnchorElement', { configurable: true, value: originalHTMLAnchorElement });
    }
  });

  it('waits for sort labels after opening the filter panel before falling back', async () => {
    let fallbackClicks = 0;
    let sortClickCount = 0;
    let panelReady = false;
    const page = {
      evaluate: async (callback: unknown, arg?: unknown) => {
        const source = String(callback);
        if (source.includes('sortLabels')) {
          return panelReady;
        }
        if (source.includes('candidates.find')) {
          return true;
        }
        if (source.includes('document.querySelectorAll(\'section.note-item\')')) {
          return { cardCount: sortClickCount > 0 ? 1 : 0, signature: sortClickCount > 0 ? 'new-card' : '' };
        }
        if (source.includes('data-hp-kind') && arg === '最多收藏') {
          sortClickCount += 1;
          return true;
        }
        if (source.includes('activeElements')) {
          return sortClickCount > 0 ? ['最多收藏'] : ['综合'];
        }
        return false;
      },
      getByText: () => ({
        click: async () => {
          fallbackClicks += 1;
          panelReady = false;
        },
      }),
      waitForTimeout: async () => undefined,
      waitForFunction: async (callback: unknown, arg?: unknown) => {
        const source = String(callback);
        if (source.includes('sortLabels')) {
          panelReady = true;
          return;
        }
        if (source.includes('expectedLabel')) {
          return;
        }
        if (source.includes('visibleCardSignatures')) {
          return;
        }
        const matched = (callback as (value?: unknown) => unknown)(arg);
        if (!matched) {
          throw new Error('Timeout exceeded');
        }
      },
    } as unknown as Page;

    await expect(switchXhsSearchSort(page, 'most_collected')).resolves.toBeUndefined();
    expect(fallbackClicks).toBe(0);
    expect(sortClickCount).toBe(1);
  });

  it('waits for the filter button before dispatching the filter panel click', async () => {
    let fallbackClicks = 0;
    let sortClickCount = 0;
    let filterReady = false;
    let panelReady = false;
    const page = {
      evaluate: async (callback: unknown, arg?: unknown) => {
        const source = String(callback);
        if (source.includes('sortLabels')) {
          return panelReady;
        }
        if (source.includes('candidates.find')) {
          if (!filterReady) {
            return false;
          }
          panelReady = true;
          return true;
        }
        if (source.includes('document.querySelectorAll(\'section.note-item\')')) {
          return { cardCount: sortClickCount > 0 ? 1 : 0, signature: sortClickCount > 0 ? 'new-card' : '' };
        }
        if (source.includes('data-hp-kind') && arg === '最多收藏') {
          sortClickCount += 1;
          return true;
        }
        if (source.includes('activeElements')) {
          return sortClickCount > 0 ? ['最多收藏'] : ['综合'];
        }
        return false;
      },
      getByText: () => ({
        click: async () => {
          fallbackClicks += 1;
        },
      }),
      waitForTimeout: async () => undefined,
      waitForFunction: async (callback: unknown, arg?: unknown) => {
        const source = String(callback);
        if (source.includes('筛选') && source.includes('candidates.some')) {
          filterReady = true;
          return;
        }
        if (source.includes('sortLabels')) {
          if (!panelReady) {
            throw new Error('Timeout exceeded');
          }
          return;
        }
        if (source.includes('expectedLabel')) {
          return;
        }
        if (source.includes('visibleCardSignatures')) {
          return;
        }
        const matched = (callback as (value?: unknown) => unknown)(arg);
        if (!matched) {
          throw new Error('Timeout exceeded');
        }
      },
    } as unknown as Page;

    await expect(switchXhsSearchSort(page, 'most_collected')).resolves.toBeUndefined();
    expect(fallbackClicks).toBe(0);
    expect(sortClickCount).toBe(1);
  });

  it('retries the filter panel click until sort labels appear', async () => {
    let filterClickCount = 0;
    let sortClickCount = 0;
    let panelReady = false;
    const page = {
      evaluate: async (callback: unknown, arg?: unknown) => {
        const source = String(callback);
        if (source.includes('sortLabels')) {
          return panelReady;
        }
        if (source.includes('candidates.find')) {
          filterClickCount += 1;
          panelReady = filterClickCount >= 2;
          return true;
        }
        if (source.includes('document.querySelectorAll(\'section.note-item\')')) {
          return { cardCount: sortClickCount > 0 ? 1 : 0, signature: sortClickCount > 0 ? 'new-card' : '' };
        }
        if (source.includes('data-hp-kind') && arg === '最多收藏') {
          sortClickCount += 1;
          return true;
        }
        if (source.includes('activeElements')) {
          return sortClickCount > 0 ? ['最多收藏'] : ['综合'];
        }
        return false;
      },
      getByText: () => ({
        click: async () => undefined,
      }),
      waitForTimeout: async () => undefined,
      waitForFunction: async (callback: unknown, arg?: unknown) => {
        const source = String(callback);
        if (source.includes('筛选') && source.includes('candidates.some')) {
          return;
        }
        if (source.includes('sortLabels')) {
          if (!panelReady) {
            throw new Error('Timeout exceeded');
          }
          return;
        }
        if (source.includes('expectedLabel')) {
          return;
        }
        if (source.includes('visibleCardSignatures')) {
          return;
        }
        const matched = (callback as (value?: unknown) => unknown)(arg);
        if (!matched) {
          throw new Error('Timeout exceeded');
        }
      },
    } as unknown as Page;

    await expect(switchXhsSearchSort(page, 'most_collected')).resolves.toBeUndefined();
    expect(filterClickCount).toBe(2);
    expect(sortClickCount).toBe(1);
  });

  it('fails sort switching when the filter panel does not show all sort labels after fallback click', async () => {
    let getByTextClicks = 0;
    const page = {
      evaluate: async (callback: unknown, arg?: unknown) => {
        const source = String(callback);
        if (source.includes('sortLabels')) {
          return false;
        }
        if (source.includes('candidates.find')) {
          return true;
        }
        if (source.includes('visibleCardSignatures')) {
          return false;
        }
        if (source.includes('document.querySelectorAll(\'section.note-item\')')) {
          return { cardCount: 1, signature: 'stale-card' };
        }
        if (source.includes('data-hp-kind') && arg === '最多点赞') {
          return true;
        }
        if (source.includes('activeElements')) {
          return ['最多点赞'];
        }
        return false;
      },
      getByText: () => ({
        click: async () => {
          getByTextClicks += 1;
        },
      }),
      waitForTimeout: async () => undefined,
      waitForFunction: async () => undefined,
    } as unknown as Page;

    await expect(switchXhsSearchSort(page, 'most_liked')).rejects.toThrow('小红书搜索筛选面板未显示排序选项');
    expect(getByTextClicks).toBe(1);
  });

  it('fails sort switching when hidden/container active text is not the visible requested sort label', async () => {
    class FakeMouseEvent {
      constructor(readonly type: string) {}
    }

    class FakeElement {
      constructor(
        readonly text: string,
        readonly width: number,
        readonly height: number,
        readonly display: string,
        readonly visibility: string,
        readonly attrs: Record<string, string> = {},
        readonly onClick?: () => void,
      ) {}

      get textContent(): string {
        return this.text;
      }

      get innerText(): string {
        return this.text;
      }

      getBoundingClientRect(): { width: number; height: number } {
        return { width: this.width, height: this.height };
      }

      getAttribute(name: string): string | null {
        return this.attrs[name] ?? null;
      }

      dispatchEvent(event: { type?: string }): boolean {
        if (event.type === 'click') {
          this.onClick?.();
        }
        return true;
      }

      querySelectorAll(_selector: string): FakeElement[] {
        return [];
      }
    }

    let sortClickCount = 0;
    const filterButton = new FakeElement('筛选', 48, 24, 'block', 'visible');
    const visibleActiveLatest = new FakeElement('最新', 56, 24, 'block', 'visible');
    const requestedSortTag = new FakeElement('最多点赞', 72, 24, 'block', 'visible', {}, () => {
      sortClickCount += 1;
    });
    const visibleAllSortsActiveContainer = new FakeElement('最新 最多点赞 最多评论 最多收藏', 260, 24, 'block', 'visible');
    const hiddenRequestedActive = new FakeElement('最多点赞', 0, 0, 'none', 'visible');
    const sortControls = [
      visibleAllSortsActiveContainer,
      visibleActiveLatest,
      requestedSortTag,
      new FakeElement('最多评论', 72, 24, 'block', 'visible'),
      new FakeElement('最多收藏', 72, 24, 'block', 'visible'),
    ];
    const activeElements = [hiddenRequestedActive, visibleAllSortsActiveContainer, visibleActiveLatest];
    const beforeSection = new FakeElement('排序前结果', 240, 160, 'block', 'visible');
    const afterLazyRerenderSection = new FakeElement('无关懒加载刷新结果', 240, 160, 'block', 'visible');
    const globals = globalThis as typeof globalThis & {
      document?: { querySelectorAll: (selector: string) => FakeElement[] };
      window?: { getComputedStyle: (element: FakeElement) => { display: string; visibility: string } };
      HTMLElement?: typeof FakeElement;
      HTMLAnchorElement?: typeof FakeElement;
      MouseEvent?: typeof FakeMouseEvent;
    };
    const originalDocument = globals.document;
    const originalWindow = globals.window;
    const originalHTMLElement = globals.HTMLElement;
    const originalHTMLAnchorElement = globals.HTMLAnchorElement;
    const originalMouseEvent = globals.MouseEvent;

    Object.defineProperty(globals, 'document', {
      configurable: true,
      value: {
        querySelectorAll: (selector: string) => {
          if (selector.includes('.active') || selector.includes('[aria-selected="true"]')) {
            return activeElements;
          }
          if (selector.includes('section.note-item')) {
            return [sortClickCount > 0 ? afterLazyRerenderSection : beforeSection];
          }
          if (selector === '[data-hp-kind]') {
            return [];
          }
          if (selector.includes('filter')) {
            return [filterButton];
          }
          if (selector.includes('tag') || selector.includes('button') || selector.includes('[role="button"]')) {
            return sortControls;
          }
          return [];
        },
      },
    });
    Object.defineProperty(globals, 'window', {
      configurable: true,
      value: { getComputedStyle: (element: FakeElement) => ({ display: element.display, visibility: element.visibility }) },
    });
    Object.defineProperty(globals, 'HTMLElement', { configurable: true, value: FakeElement });
    Object.defineProperty(globals, 'HTMLAnchorElement', { configurable: true, value: FakeElement });
    Object.defineProperty(globals, 'MouseEvent', { configurable: true, value: FakeMouseEvent });

    try {
      const page = {
        evaluate: async (callback: unknown, arg?: unknown) => (callback as (value?: unknown) => unknown)(arg),
        getByText: () => ({ click: async () => undefined }),
        waitForTimeout: async () => undefined,
        waitForFunction: async (callback: unknown, arg?: unknown) => {
          const matched = (callback as (value?: unknown) => unknown)(arg);
          if (!matched) {
            throw new Error('Timeout exceeded');
          }
        },
      } as unknown as Page;

      await expect(switchXhsSearchSort(page, 'most_liked')).rejects.toThrow('小红书搜索排序切换失败：期望 最多点赞');
      expect(sortClickCount).toBe(1);
    } finally {
      Object.defineProperty(globals, 'document', { configurable: true, value: originalDocument });
      Object.defineProperty(globals, 'window', { configurable: true, value: originalWindow });
      Object.defineProperty(globals, 'HTMLElement', { configurable: true, value: originalHTMLElement });
      Object.defineProperty(globals, 'HTMLAnchorElement', { configurable: true, value: originalHTMLAnchorElement });
      Object.defineProperty(globals, 'MouseEvent', { configurable: true, value: originalMouseEvent });
    }
  });

  it('rejects unrelated active exact-label elements when the actual active sort remains different', async () => {
    class FakeMouseEvent {
      constructor(readonly type: string) {}
    }

    class FakeElement {
      readonly tagName: string;

      constructor(
        readonly text: string,
        readonly width: number,
        readonly height: number,
        readonly display: string,
        readonly visibility: string,
        readonly attrs: Record<string, string> = {},
        tagName = 'div',
        readonly onClick?: () => void,
      ) {
        this.tagName = tagName.toUpperCase();
      }

      get textContent(): string {
        return this.text;
      }

      get innerText(): string {
        return this.text;
      }

      getBoundingClientRect(): { width: number; height: number } {
        return { width: this.width, height: this.height };
      }

      getAttribute(name: string): string | null {
        return this.attrs[name] ?? null;
      }

      dispatchEvent(event: { type?: string }): boolean {
        if (event.type === 'click') {
          this.onClick?.();
        }
        return true;
      }

      querySelectorAll(_selector: string): FakeElement[] {
        return [];
      }
    }

    let sortClickCount = 0;
    const filterButton = new FakeElement('筛选', 48, 24, 'block', 'visible', {}, 'button');
    const unrelatedActiveRequestedChip = new FakeElement('最多点赞', 96, 28, 'block', 'visible', { class: 'active note-card' });
    const actualActiveLatestSort = new FakeElement('最新', 56, 24, 'block', 'visible', { class: 'sort-tag active' });
    const requestedSortTag = new FakeElement('最多点赞', 72, 24, 'block', 'visible', { class: 'sort-tag' }, 'div', () => {
      sortClickCount += 1;
    });
    const sortControls = [
      filterButton,
      actualActiveLatestSort,
      requestedSortTag,
      new FakeElement('最多评论', 72, 24, 'block', 'visible', { class: 'sort-tag' }),
      new FakeElement('最多收藏', 72, 24, 'block', 'visible', { class: 'sort-tag' }),
    ];
    const beforeSection = new FakeElement('切换前可见结果', 240, 160, 'block', 'visible');
    const afterLazyRerenderSection = new FakeElement('无关懒加载刷新结果', 240, 160, 'block', 'visible');
    const globals = globalThis as typeof globalThis & {
      document?: { querySelectorAll: (selector: string) => FakeElement[] };
      window?: { getComputedStyle: (element: FakeElement) => { display: string; visibility: string } };
      HTMLElement?: typeof FakeElement;
      HTMLAnchorElement?: typeof FakeElement;
      MouseEvent?: typeof FakeMouseEvent;
    };
    const originalDocument = globals.document;
    const originalWindow = globals.window;
    const originalHTMLElement = globals.HTMLElement;
    const originalHTMLAnchorElement = globals.HTMLAnchorElement;
    const originalMouseEvent = globals.MouseEvent;

    Object.defineProperty(globals, 'document', {
      configurable: true,
      value: {
        querySelectorAll: (selector: string) => {
          if (selector.includes('.active') || selector.includes('[aria-selected="true"]')) {
            return [unrelatedActiveRequestedChip, actualActiveLatestSort];
          }
          if (selector.includes('section.note-item')) {
            return [sortClickCount > 0 ? afterLazyRerenderSection : beforeSection];
          }
          if (selector === '[data-hp-kind]') {
            return [];
          }
          if (selector.includes('tag') || selector.includes('button') || selector.includes('[role="button"]') || selector.includes('filter')) {
            return sortControls;
          }
          return [];
        },
      },
    });
    Object.defineProperty(globals, 'window', {
      configurable: true,
      value: { getComputedStyle: (element: FakeElement) => ({ display: element.display, visibility: element.visibility }) },
    });
    Object.defineProperty(globals, 'HTMLElement', { configurable: true, value: FakeElement });
    Object.defineProperty(globals, 'HTMLAnchorElement', { configurable: true, value: FakeElement });
    Object.defineProperty(globals, 'MouseEvent', { configurable: true, value: FakeMouseEvent });

    try {
      const page = {
        evaluate: async (callback: unknown, arg?: unknown) => (callback as (value?: unknown) => unknown)(arg),
        getByText: () => ({ click: async () => undefined }),
        waitForTimeout: async () => undefined,
        waitForFunction: async (callback: unknown, arg?: unknown) => {
          const matched = (callback as (value?: unknown) => unknown)(arg);
          if (!matched) {
            throw new Error('Timeout exceeded');
          }
        },
      } as unknown as Page;

      await expect(switchXhsSearchSort(page, 'most_liked')).rejects.toThrow('小红书搜索排序切换失败：期望 最多点赞');
      expect(sortClickCount).toBe(1);
    } finally {
      Object.defineProperty(globals, 'document', { configurable: true, value: originalDocument });
      Object.defineProperty(globals, 'window', { configurable: true, value: originalWindow });
      Object.defineProperty(globals, 'HTMLElement', { configurable: true, value: originalHTMLElement });
      Object.defineProperty(globals, 'HTMLAnchorElement', { configurable: true, value: originalHTMLAnchorElement });
      Object.defineProperty(globals, 'MouseEvent', { configurable: true, value: originalMouseEvent });
    }
  });

  it('fails sort switching when visible result cards do not refresh after the active sort label changes', async () => {
    const page = {
      evaluate: async (callback: unknown, arg?: unknown) => {
        const source = String(callback);
        if (source.includes('sortLabels')) {
          return true;
        }
        if (source.includes('candidates.find')) {
          return true;
        }
        if (source.includes('document.querySelectorAll(\'section.note-item\')')) {
          return { cardCount: 1, signature: 'stale-card' };
        }
        if (source.includes('data-hp-kind') && arg === '最多点赞') {
          return true;
        }
        if (source.includes('activeElements')) {
          return ['最多点赞'];
        }
        return false;
      },
      getByText: () => ({ click: async () => undefined }),
      waitForTimeout: async () => undefined,
      waitForFunction: async (callback: unknown) => {
        const source = String(callback);
        if (source.includes('visibleCardSignatures')) {
          throw new Error('Timeout 2500ms exceeded');
        }
      },
    } as unknown as Page;

    await expect(switchXhsSearchSort(page, 'most_liked')).rejects.toThrow('小红书搜索排序结果未刷新：最多点赞');
  });

  it('throws the login-required message when the page shows a login wall', async () => {
    const page = {
      locator: () => ({ innerText: async () => '登录后查看搜索结果\n手机号登录' }),
    } as unknown as Page;

    await expect(assertXhsLoggedIn(page)).rejects.toThrow(XHS_LOGIN_REQUIRED_MESSAGE);
  });

  it('propagates page text read failures during login checks', async () => {
    const page = {
      locator: () => ({ innerText: async () => { throw new Error('body unavailable'); } }),
    } as unknown as Page;

    await expect(assertXhsLoggedIn(page)).rejects.toThrow('body unavailable');
  });
});

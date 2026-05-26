# XHS Search Secondary Collection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an `xhs-search` secondary collector that searches Xiaohongshu keywords, switches verified sort filters, saves top candidate notes per sort to SQLite, and optionally enriches notes from detail pages.

**Architecture:** Keep Xiaohongshu collection separate from the existing Huitun collector. Add focused XHS browser modules for search/detail behavior, XHS-specific types, XHS tables in SQLite, and a CLI subcommand that orchestrates collection without mixing XHS rows into the existing Huitun `notes` table.

**Tech Stack:** Node.js, TypeScript, Playwright CDP via `playwright-core`, SQLite via `node:sqlite`, Commander, Vitest.

**Commit policy:** Do not create commits while executing this plan unless the user explicitly asks. Each task ends with a git status checkpoint instead of a commit.

---

## File Structure

Create:

- `src/xhs-types.ts` — XHS-specific run, sort, note, detail, and snapshot types.
- `src/browser/xhs-search.ts` — search URL construction, login detection, sort mapping, search-card parsing, filter switching, result loading.
- `src/browser/xhs-note-detail.ts` — detail URL identity extraction and detail-page text parsing.
- `src/browser/xhs-session.ts` — CDP session wrapper and XHS page snapshot helper.
- `src/xhs-search-collector.ts` — orchestration for single keyword and Huitun-run keyword inputs.
- `tests/xhs-search-parser.test.ts` — URL, sort, login, and search-card parser tests.
- `tests/xhs-note-detail-parser.test.ts` — detail URL and detail text parser tests.
- `tests/xhs-db.test.ts` — XHS schema/repository tests.

Modify:

- `src/db/schema.ts` — add `xhs_search_runs`, `xhs_search_notes`, `xhs_raw_snapshots` tables and indexes.
- `src/db/repositories.ts` — add XHS run/note/snapshot methods and Huitun hot-word lookup for `--from-huitun-run-id`.
- `src/cli.ts` — add `xhs-search` subcommand and option parser.
- `tests/cli-options.test.ts` — add CLI parser/help tests for `xhs-search`.

Do not modify these existing dirty files unless a later task explicitly needs to resolve test conflicts caused by this feature:

- `src/browser/hotword-detail.ts`
- `src/browser/hotword-search.ts`
- `tests/hotword-search-parser.test.ts`
- `tests/note-list-parser.test.ts`

---

### Task 1: Add XHS types, sort mapping, URL, and login helpers

**Files:**
- Create: `src/xhs-types.ts`
- Create: `src/browser/xhs-search.ts`
- Test: `tests/xhs-search-parser.test.ts`

- [ ] **Step 1: Write failing tests for sort parsing, URL construction, and login detection**

Create `tests/xhs-search-parser.test.ts` with:

```ts
import { describe, expect, it } from 'vitest';

import {
  XHS_SEARCH_SORTS,
  buildXhsSearchUrl,
  isXhsLoginRequiredText,
  parseXhsSortKeys,
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

  it('rejects unsupported sort keys', () => {
    expect(() => parseXhsSortKeys('latest,most_shared')).toThrow('Unsupported XHS sort key: most_shared');
  });

  it('detects Xiaohongshu login walls', () => {
    expect(isXhsLoginRequiredText('登录后查看搜索结果\n手机号登录')).toBe(true);
    expect(isXhsLoginRequiredText('全部\n图文\n筛选\n最多收藏')).toBe(false);
  });
});
```

- [ ] **Step 2: Run the test and verify it fails because files/functions do not exist**

Run:

```bash
npm test -- tests/xhs-search-parser.test.ts
```

Expected: FAIL with a module resolution error for `../src/browser/xhs-search.js` or missing exported functions.

- [ ] **Step 3: Add XHS shared types**

Create `src/xhs-types.ts`:

```ts
import type { RunStatus } from './types.js';

export type XhsSearchSortKey = 'latest' | 'most_liked' | 'most_commented' | 'most_collected';
export type XhsSearchRunSource = 'manual_keyword' | 'huitun_run';

export interface XhsSearchRunInput {
  source: XhsSearchRunSource;
  sourceRunId: number | null;
  keyword: string;
  sorts: XhsSearchSortKey[];
  limitPerSort: number;
  withDetails: boolean;
}

export interface XhsSearchRunRecord {
  id: number;
  source: XhsSearchRunSource;
  sourceRunId: number | null;
  keyword: string;
  sorts: XhsSearchSortKey[];
  limitPerSort: number;
  withDetails: boolean;
  status: RunStatus;
  startedAt: string;
  finishedAt: string | null;
  errorStage: string | null;
  errorMessage: string | null;
}

export interface XhsNoteIdentity {
  feedId: string;
  xsecToken: string | null;
}

export interface XhsSearchNoteRow {
  keyword: string;
  sortKey: XhsSearchSortKey;
  sortLabel: string;
  rankIndex: number;
  feedId: string;
  xsecToken: string | null;
  searchResultUrl: string;
  exploreUrl: string | null;
  title: string;
  authorName: string | null;
  authorProfileUrl: string | null;
  coverUrl: string | null;
  publishedAtText: string | null;
  metricText: string | null;
  detailText: string | null;
  detailTags: string[];
  detailCommentCountText: string | null;
  detailLikeText: string | null;
  detailCollectText: string | null;
  detailShareText: string | null;
  rawCardText: string;
}

export interface XhsSearchCardPayload {
  searchResultUrl: string | null;
  authorProfileUrl: string | null;
  coverUrl: string | null;
  rawText: string;
}

export interface XhsNoteDetail {
  feedId: string;
  xsecToken: string | null;
  exploreUrl: string;
  detailText: string | null;
  tags: string[];
  commentCountText: string | null;
  likeText: string | null;
  collectText: string | null;
  shareText: string | null;
}

export interface XhsRawSnapshotInput {
  kind: string;
  objectKey: string;
  pageUrl: string;
  textContent: string;
  htmlContent: string | null;
}
```

- [ ] **Step 4: Add helper implementation**

Create `src/browser/xhs-search.ts` with the helper content first; browser automation will be added in later tasks:

```ts
import type { Page } from 'playwright-core';

import type { XhsSearchSortKey } from '../xhs-types.js';

export const XHS_SEARCH_SORTS: Record<XhsSearchSortKey, string> = {
  latest: '最新',
  most_liked: '最多点赞',
  most_commented: '最多评论',
  most_collected: '最多收藏',
};

export const DEFAULT_XHS_SEARCH_SORTS: XhsSearchSortKey[] = ['latest', 'most_liked', 'most_commented', 'most_collected'];

const XHS_LOGIN_REQUIRED_PATTERNS = [/登录后查看搜索结果/, /手机号登录/, /扫码登录/, /请先登录/];

export const XHS_LOGIN_REQUIRED_MESSAGE = '当前小红书登录态不可用，请在 CDP 浏览器中登录小红书后重试。';

export function buildXhsSearchUrl(keyword: string): string {
  return `https://www.xiaohongshu.com/search_result?keyword=${encodeURIComponent(keyword)}`;
}

export function parseXhsSortKeys(value: string | undefined): XhsSearchSortKey[] {
  if (value === undefined || value.trim() === '') {
    return DEFAULT_XHS_SEARCH_SORTS;
  }

  return value.split(',').map((part) => {
    const key = part.trim();
    if (!Object.prototype.hasOwnProperty.call(XHS_SEARCH_SORTS, key)) {
      throw new Error(`Unsupported XHS sort key: ${key}`);
    }
    return key as XhsSearchSortKey;
  });
}

export function isXhsLoginRequiredText(text: string): boolean {
  const normalizedText = text.replace(/\s+/g, '');
  return XHS_LOGIN_REQUIRED_PATTERNS.some((pattern) => pattern.test(normalizedText));
}

export async function assertXhsLoggedIn(page: Page): Promise<void> {
  const text = await page.locator('body').innerText().catch(() => '');
  if (isXhsLoginRequiredText(text)) {
    throw new Error(XHS_LOGIN_REQUIRED_MESSAGE);
  }
}
```

- [ ] **Step 5: Run the helper tests and verify they pass**

Run:

```bash
npm test -- tests/xhs-search-parser.test.ts
```

Expected: PASS.

- [ ] **Step 6: Run typecheck**

Run:

```bash
npm run typecheck
```

Expected: PASS.

- [ ] **Step 7: Checkpoint without committing**

Run:

```bash
git status --short
```

Expected: new `src/xhs-types.ts`, `src/browser/xhs-search.ts`, and `tests/xhs-search-parser.test.ts` appear; no commit is created.

---

### Task 2: Add XHS search card identity and parser logic

**Files:**
- Modify: `src/browser/xhs-search.ts`
- Test: `tests/xhs-search-parser.test.ts`

- [ ] **Step 1: Extend parser tests for card payload parsing and URL identity extraction**

Append to `tests/xhs-search-parser.test.ts`:

```ts
import { extractXhsNoteIdentity, parseXhsSearchNoteRows } from '../src/browser/xhs-search.js';

describe('XHS search card parsing', () => {
  it('extracts feed id and xsec token from a search result URL', () => {
    expect(
      extractXhsNoteIdentity(
        'https://www.xiaohongshu.com/search_result/69755391000000000a02b2b8?xsec_token=ABBfhNdxYui9ysgmtuYLVEoJ44qkjKbrBvGAgTnmMVVkc%3D&xsec_source=',
      ),
    ).toEqual({
      feedId: '69755391000000000a02b2b8',
      xsecToken: 'ABBfhNdxYui9ysgmtuYLVEoJ44qkjKbrBvGAgTnmMVVkc=',
    });
  });

  it('extracts feed id and xsec token from a final explore URL', () => {
    expect(
      extractXhsNoteIdentity('https://www.xiaohongshu.com/explore/69755391000000000a02b2b8?xsec_token=token-123'),
    ).toEqual({ feedId: '69755391000000000a02b2b8', xsecToken: 'token-123' });
  });

  it('rejects explore short URLs without xsec token for detail navigation safety', () => {
    expect(extractXhsNoteIdentity('https://www.xiaohongshu.com/explore/69755391000000000a02b2b8')).toEqual({
      feedId: '69755391000000000a02b2b8',
      xsecToken: null,
    });
  });

  it('parses valid note card payloads and skips recommendation blocks', () => {
    const rows = parseXhsSearchNoteRows('护肤', 'most_collected', [
      {
        searchResultUrl:
          'https://www.xiaohongshu.com/search_result/69755391000000000a02b2b8?xsec_token=ABBfhNdxYui9ysgmtuYLVEoJ44qkjKbrBvGAgTnmMVVkc%3D&xsec_source=',
        authorProfileUrl:
          'https://www.xiaohongshu.com/user/profile/5a7414d411be1076fd3f1535?xsec_token=author-token&xsec_source=pc_search',
        coverUrl: 'https://sns-webpic-qc.xhscdn.com/cover.webp',
        rawText: '护肤真心话：皮肤不好！90%是脸都没洗干净…\n陈莴笋\n01-25\n22.5万',
      },
      {
        searchResultUrl: null,
        authorProfileUrl: null,
        coverUrl: null,
        rawText: '大家都在搜\n男生护肤\n护肤养肤',
      },
    ]);

    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      keyword: '护肤',
      sortKey: 'most_collected',
      sortLabel: '最多收藏',
      rankIndex: 1,
      feedId: '69755391000000000a02b2b8',
      xsecToken: 'ABBfhNdxYui9ysgmtuYLVEoJ44qkjKbrBvGAgTnmMVVkc=',
      title: '护肤真心话：皮肤不好！90%是脸都没洗干净…',
      authorName: '陈莴笋',
      authorProfileUrl: 'https://www.xiaohongshu.com/user/profile/5a7414d411be1076fd3f1535?xsec_token=author-token&xsec_source=pc_search',
      coverUrl: 'https://sns-webpic-qc.xhscdn.com/cover.webp',
      publishedAtText: '01-25',
      metricText: '22.5万',
      rawCardText: '护肤真心话：皮肤不好！90%是脸都没洗干净…\n陈莴笋\n01-25\n22.5万',
    });
  });
});
```

- [ ] **Step 2: Run tests and verify parser failures**

Run:

```bash
npm test -- tests/xhs-search-parser.test.ts
```

Expected: FAIL because `extractXhsNoteIdentity` and `parseXhsSearchNoteRows` are not implemented.

- [ ] **Step 3: Implement identity extraction and card parser**

Add to `src/browser/xhs-search.ts`:

```ts
import type { XhsNoteIdentity, XhsSearchCardPayload, XhsSearchNoteRow } from '../xhs-types.js';

function absoluteXhsUrl(url: string): string {
  return new URL(url, 'https://www.xiaohongshu.com').toString();
}

export function extractXhsNoteIdentity(url: string): XhsNoteIdentity | null {
  const parsed = new URL(url, 'https://www.xiaohongshu.com');
  const match = parsed.pathname.match(/^\/(?:search_result|explore)\/([^/]+)$/);
  if (!match) {
    return null;
  }

  return {
    feedId: match[1],
    xsecToken: parsed.searchParams.get('xsec_token'),
  };
}

function parseCardText(rawText: string): {
  title: string;
  authorName: string | null;
  publishedAtText: string | null;
  metricText: string | null;
} {
  const lines = rawText
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean);

  return {
    title: lines[0] ?? '',
    authorName: lines[1] ?? null,
    publishedAtText: lines[2] ?? null,
    metricText: lines[3] ?? null,
  };
}

export function parseXhsSearchNoteRows(
  keyword: string,
  sortKey: XhsSearchSortKey,
  payloads: XhsSearchCardPayload[],
): XhsSearchNoteRow[] {
  const rows: XhsSearchNoteRow[] = [];
  const sortLabel = XHS_SEARCH_SORTS[sortKey];

  for (const payload of payloads) {
    if (!payload.searchResultUrl) {
      continue;
    }

    const searchResultUrl = absoluteXhsUrl(payload.searchResultUrl);
    const identity = extractXhsNoteIdentity(searchResultUrl);
    if (!identity) {
      continue;
    }

    const parsedText = parseCardText(payload.rawText);
    if (!parsedText.title) {
      continue;
    }

    rows.push({
      keyword,
      sortKey,
      sortLabel,
      rankIndex: rows.length + 1,
      feedId: identity.feedId,
      xsecToken: identity.xsecToken,
      searchResultUrl,
      exploreUrl: null,
      title: parsedText.title,
      authorName: parsedText.authorName,
      authorProfileUrl: payload.authorProfileUrl ? absoluteXhsUrl(payload.authorProfileUrl) : null,
      coverUrl: payload.coverUrl,
      publishedAtText: parsedText.publishedAtText,
      metricText: parsedText.metricText,
      detailText: null,
      detailTags: [],
      detailCommentCountText: null,
      detailLikeText: null,
      detailCollectText: null,
      detailShareText: null,
      rawCardText: payload.rawText,
    });
  }

  return rows;
}
```

- [ ] **Step 4: Run parser tests**

Run:

```bash
npm test -- tests/xhs-search-parser.test.ts
```

Expected: PASS.

- [ ] **Step 5: Run typecheck**

Run:

```bash
npm run typecheck
```

Expected: PASS.

- [ ] **Step 6: Checkpoint without committing**

Run:

```bash
git status --short
```

Expected: only XHS files from this plan are new/modified in addition to pre-existing dirty Huitun files.

---

### Task 3: Add XHS detail parser

**Files:**
- Create: `src/browser/xhs-note-detail.ts`
- Test: `tests/xhs-note-detail-parser.test.ts`

**XHS-Downloader reference applied:** Reimplement the idea, not its GPL code: for opened detail pages, prefer browser-page `window.__INITIAL_STATE__` extraction, then fall back to visible DOM text parsing.

- [ ] **Step 1: Write failing detail parser tests**

Create `tests/xhs-note-detail-parser.test.ts`:

```ts
import { describe, expect, it } from 'vitest';

import { parseXhsInitialStateNoteDetail, parseXhsNoteDetailFromText, shouldRejectShortExploreUrl } from '../src/browser/xhs-note-detail.js';

describe('XHS note detail parsing', () => {
  it('rejects short explore URLs without xsec token as unsafe for navigation', () => {
    expect(shouldRejectShortExploreUrl('https://www.xiaohongshu.com/explore/69755391000000000a02b2b8')).toBe(true);
    expect(
      shouldRejectShortExploreUrl(
        'https://www.xiaohongshu.com/explore/69755391000000000a02b2b8?xsec_token=ABBfhNdxYui9ysgmtuYLVEoJ44qkjKbrBvGAgTnmMVVkc=',
      ),
    ).toBe(false);
    expect(
      shouldRejectShortExploreUrl(
        'https://www.xiaohongshu.com/search_result/69755391000000000a02b2b8?xsec_token=ABBfhNdxYui9ysgmtuYLVEoJ44qkjKbrBvGAgTnmMVVkc=',
      ),
    ).toBe(false);
  });

  it('parses structured detail data from Xiaohongshu page initial state', () => {
    const detail = parseXhsInitialStateNoteDetail({
      note: {
        noteDetailMap: {
          feed1: {
            note: {
              desc: '护肤真心话：皮肤不好！90%是脸都没洗干净…',
              tagList: [{ name: '正确洗脸' }, { name: '新手护肤' }],
              interactInfo: {
                commentCount: '1881',
                likedCount: '10万+',
                collectedCount: '10万+',
                shareCount: '23',
              },
            },
          },
        },
      },
    });

    expect(detail).toEqual({
      detailText: '护肤真心话：皮肤不好！90%是脸都没洗干净…',
      tags: ['正确洗脸', '新手护肤'],
      commentCountText: '1881',
      likeText: '10万+',
      collectText: '10万+',
      shareText: '23',
    });
  });

  it('parses visible detail text, tags, comments, and bottom metrics as DOM fallback', () => {
    const detail = parseXhsNoteDetailFromText(
      '陈莴笋\n关注\n护肤真心话：皮肤不好！90%是脸都没洗干净…\n-\n#正确洗脸#新手护肤#护肤干货#洗脸\n01-25\n共 1881 条评论\n说点什么...\n10万+\n10万+\n可以添加到收藏夹啦\n1881\n发送',
    );

    expect(detail).toEqual({
      detailText: '护肤真心话：皮肤不好！90%是脸都没洗干净…',
      tags: ['正确洗脸', '新手护肤', '护肤干货', '洗脸'],
      commentCountText: '1881',
      likeText: '10万+',
      collectText: '10万+',
      shareText: null,
    });
  });
});
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
npm test -- tests/xhs-note-detail-parser.test.ts
```

Expected: FAIL because `src/browser/xhs-note-detail.ts` does not exist.

- [ ] **Step 3: Implement detail parser helpers**

Create `src/browser/xhs-note-detail.ts`:

```ts
import type { Page } from 'playwright-core';

import { extractXhsNoteIdentity } from './xhs-search.js';
import type { XhsNoteDetail } from '../xhs-types.js';

interface ParsedXhsDetailText {
  detailText: string | null;
  tags: string[];
  commentCountText: string | null;
  likeText: string | null;
  collectText: string | null;
  shareText: string | null;
}

function firstRecordValue(value: unknown): unknown {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null;
  }
  return Object.values(value as Record<string, unknown>)[0] ?? null;
}

function getStringField(record: Record<string, unknown>, keys: string[]): string | null {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === 'string' && value.trim() !== '') {
      return value;
    }
    if (typeof value === 'number') {
      return String(value);
    }
  }
  return null;
}

export function parseXhsInitialStateNoteDetail(state: unknown): ParsedXhsDetailText | null {
  if (!state || typeof state !== 'object') {
    return null;
  }

  const root = state as Record<string, unknown>;
  const noteRoot = root.note && typeof root.note === 'object' ? root.note as Record<string, unknown> : root;
  const detailMap = noteRoot.noteDetailMap ?? noteRoot.noteMap;
  const detailRecord = firstRecordValue(detailMap);
  const note = detailRecord && typeof detailRecord === 'object' && 'note' in detailRecord
    ? (detailRecord as Record<string, unknown>).note
    : detailRecord;

  if (!note || typeof note !== 'object') {
    return null;
  }

  const noteRecord = note as Record<string, unknown>;
  const interactInfo = noteRecord.interactInfo && typeof noteRecord.interactInfo === 'object'
    ? noteRecord.interactInfo as Record<string, unknown>
    : {};
  const tagList = Array.isArray(noteRecord.tagList) ? noteRecord.tagList : [];

  return {
    detailText: getStringField(noteRecord, ['desc', 'description', 'content']),
    tags: tagList.map((tag) => typeof tag === 'object' && tag !== null ? getStringField(tag as Record<string, unknown>, ['name', 'tagName']) : null).filter((tag): tag is string => tag !== null),
    commentCountText: getStringField(interactInfo, ['commentCount', 'comment_count']),
    likeText: getStringField(interactInfo, ['likedCount', 'likeCount', 'liked_count']),
    collectText: getStringField(interactInfo, ['collectedCount', 'collectCount', 'collected_count']),
    shareText: getStringField(interactInfo, ['shareCount', 'share_count']),
  };
}

export function shouldRejectShortExploreUrl(url: string): boolean {
  const parsed = new URL(url, 'https://www.xiaohongshu.com');
  return parsed.pathname.startsWith('/explore/') && !parsed.searchParams.has('xsec_token');
}

export function parseXhsNoteDetailFromText(text: string): ParsedXhsDetailText {
  const lines = text
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean);
  const tagLine = lines.find((line) => line.includes('#')) ?? '';
  const tags = Array.from(tagLine.matchAll(/#([^#\s]+)/g)).map((match) => match[1]);
  const commentLine = lines.find((line) => /^共\s*.+\s*条评论$/.test(line));
  const commentCountText = commentLine?.replace(/^共\s*/, '').replace(/\s*条评论$/, '') ?? null;
  const inputIndex = lines.findIndex((line) => line === '说点什么...');
  const metricLines = inputIndex >= 0 ? lines.slice(inputIndex + 1) : [];
  const detailText = lines.find((line, index) => index > 0 && line !== '关注' && line !== '-' && !line.startsWith('#')) ?? null;

  return {
    detailText,
    tags,
    commentCountText,
    likeText: metricLines[0] ?? null,
    collectText: metricLines[1] ?? null,
    shareText: null,
  };
}

export async function collectXhsNoteDetail(page: Page, searchResultUrl: string): Promise<XhsNoteDetail> {
  if (shouldRejectShortExploreUrl(searchResultUrl)) {
    throw new Error('XHS detail navigation requires a search_result URL or explore URL with xsec_token.');
  }

  await page.goto(searchResultUrl, { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle').catch(() => undefined);
  const finalUrl = page.url();
  const identity = extractXhsNoteIdentity(finalUrl);
  if (!identity) {
    throw new Error(`XHS detail page did not resolve to a note URL: ${finalUrl}`);
  }

  const initialState = await page.evaluate(() => (window as unknown as { __INITIAL_STATE__?: unknown }).__INITIAL_STATE__).catch(() => null);
  const text = await page.locator('body').innerText();
  const parsed = parseXhsInitialStateNoteDetail(initialState) ?? parseXhsNoteDetailFromText(text);

  return {
    feedId: identity.feedId,
    xsecToken: identity.xsecToken,
    exploreUrl: finalUrl,
    detailText: parsed.detailText,
    tags: parsed.tags,
    commentCountText: parsed.commentCountText,
    likeText: parsed.likeText,
    collectText: parsed.collectText,
    shareText: parsed.shareText,
  };
}
```

- [ ] **Step 4: Run detail parser tests**

Run:

```bash
npm test -- tests/xhs-note-detail-parser.test.ts
```

Expected: PASS.

- [ ] **Step 5: Run typecheck**

Run:

```bash
npm run typecheck
```

Expected: PASS.

- [ ] **Step 6: Checkpoint without committing**

Run:

```bash
git status --short
```

Expected: new detail parser files are visible; no commit is created.

---

### Task 4: Add XHS SQLite schema and repository methods

**Files:**
- Modify: `src/db/schema.ts`
- Modify: `src/db/repositories.ts`
- Test: `tests/xhs-db.test.ts`

- [ ] **Step 1: Write failing database tests**

Create `tests/xhs-db.test.ts`:

```ts
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import type { DatabaseSync } from 'node:sqlite';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { openDatabase } from '../src/db/client.js';
import { CollectorRepository } from '../src/db/repositories.js';
import { initializeSchema } from '../src/db/schema.js';

describe('XHS search repository', () => {
  let tempDir: string;
  let db: DatabaseSync;
  let repository: CollectorRepository;

  beforeEach(() => {
    tempDir = mkdtempSync(join(tmpdir(), 'xhs-search-db-test-'));
    db = openDatabase(join(tempDir, 'collector.sqlite'));
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
    const row = db.prepare('select * from xhs_search_runs where id = ?').get(runId) as {
      id: number;
      source: string;
      source_run_id: number | null;
      keyword: string;
      sorts_json: string;
      limit_per_sort: number;
      with_details: number;
      status: string;
      finished_at: string | null;
    };

    expect(row).toMatchObject({
      id: runId,
      source: 'manual_keyword',
      source_run_id: null,
      keyword: '护肤',
      sorts_json: JSON.stringify(['latest', 'most_collected']),
      limit_per_sort: 20,
      with_details: 0,
      status: 'success',
    });
    expect(row.finished_at).toEqual(expect.any(String));
  });

  it('upserts XHS notes per run keyword sort and feed id', () => {
    const runId = repository.createXhsSearchRun({
      source: 'manual_keyword',
      sourceRunId: null,
      keyword: '护肤',
      sorts: ['most_collected'],
      limitPerSort: 20,
      withDetails: true,
    });

    repository.upsertXhsSearchNotes(runId, [
      {
        keyword: '护肤',
        sortKey: 'most_collected',
        sortLabel: '最多收藏',
        rankIndex: 1,
        feedId: '69755391000000000a02b2b8',
        xsecToken: 'token-a',
        searchResultUrl: 'https://www.xiaohongshu.com/search_result/69755391000000000a02b2b8?xsec_token=token-a',
        exploreUrl: null,
        title: '旧标题',
        authorName: '陈莴笋',
        authorProfileUrl: 'https://www.xiaohongshu.com/user/profile/u1',
        coverUrl: 'https://sns-webpic-qc.xhscdn.com/cover.webp',
        publishedAtText: '01-25',
        metricText: '22.5万',
        detailText: null,
        detailTags: [],
        detailCommentCountText: null,
        detailLikeText: null,
        detailCollectText: null,
        detailShareText: null,
        rawCardText: '旧标题\n陈莴笋\n01-25\n22.5万',
      },
    ]);

    repository.upsertXhsSearchNotes(runId, [
      {
        keyword: '护肤',
        sortKey: 'most_collected',
        sortLabel: '最多收藏',
        rankIndex: 1,
        feedId: '69755391000000000a02b2b8',
        xsecToken: 'token-a',
        searchResultUrl: 'https://www.xiaohongshu.com/search_result/69755391000000000a02b2b8?xsec_token=token-a',
        exploreUrl: 'https://www.xiaohongshu.com/explore/69755391000000000a02b2b8?xsec_token=token-a',
        title: '新标题',
        authorName: '陈莴笋',
        authorProfileUrl: 'https://www.xiaohongshu.com/user/profile/u1',
        coverUrl: 'https://sns-webpic-qc.xhscdn.com/cover.webp',
        publishedAtText: '01-25',
        metricText: '22.5万',
        detailText: '详情正文',
        detailTags: ['正确洗脸', '护肤干货'],
        detailCommentCountText: '1881',
        detailLikeText: '10万+',
        detailCollectText: '10万+',
        detailShareText: null,
        rawCardText: '新标题\n陈莴笋\n01-25\n22.5万',
      },
    ]);

    const rows = db.prepare('select * from xhs_search_notes').all() as Array<{
      title: string;
      detail_text: string | null;
      detail_tags_json: string;
      detail_comment_count_text: string | null;
      explore_url: string | null;
    }>;

    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      title: '新标题',
      detail_text: '详情正文',
      detail_tags_json: JSON.stringify(['正确洗脸', '护肤干货']),
      detail_comment_count_text: '1881',
      explore_url: 'https://www.xiaohongshu.com/explore/69755391000000000a02b2b8?xsec_token=token-a',
    });
  });

  it('stores XHS raw snapshots and reads hot words from a Huitun run', () => {
    const huitunRunId = repository.createRun({ keyword: '护肤', days: 7, limitHotwords: 3, limitNotes: 20 });
    repository.insertHotWords(huitunRunId, [
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
        noteCount: 10,
        interactionText: '3千',
        interactionNumber: 3000,
        categories: [{ label: '护肤', rate: null }],
        rankIndex: 2,
      },
    ]);
    const xhsRunId = repository.createXhsSearchRun({
      source: 'huitun_run',
      sourceRunId: huitunRunId,
      keyword: '早C晚A',
      sorts: ['latest'],
      limitPerSort: 20,
      withDetails: false,
    });

    repository.insertXhsRawSnapshot(xhsRunId, {
      kind: 'xhs_sort_not_found',
      objectKey: 'most_collected',
      pageUrl: 'https://www.xiaohongshu.com/search_result?keyword=早C晚A',
      textContent: '排序不存在',
      htmlContent: '<html></html>',
    });

    expect(repository.listHotWordKeywordsForRun(huitunRunId, 1)).toEqual(['早C晚A']);
    expect(db.prepare('select count(*) as count from xhs_raw_snapshots').get()).toEqual({ count: 1 });
  });
});
```

- [ ] **Step 2: Run database tests and verify failure**

Run:

```bash
npm test -- tests/xhs-db.test.ts
```

Expected: FAIL because XHS repository methods and tables do not exist.

- [ ] **Step 3: Add XHS tables to schema**

Modify `src/db/schema.ts` inside the main `db.exec` block, after `raw_snapshots` table creation:

```ts
    create table if not exists xhs_search_runs (
      id integer primary key autoincrement,
      source text not null,
      source_run_id integer,
      keyword text not null,
      sorts_json text not null,
      limit_per_sort integer not null,
      with_details integer not null,
      status text not null,
      started_at text not null default current_timestamp,
      finished_at text,
      error_stage text,
      error_message text
    );

    create table if not exists xhs_search_notes (
      id integer primary key autoincrement,
      run_id integer not null references xhs_search_runs(id) on delete cascade,
      keyword text not null,
      sort_key text not null,
      sort_label text not null,
      rank_index integer not null,
      feed_id text not null,
      xsec_token text,
      search_result_url text not null,
      explore_url text,
      title text not null,
      author_name text,
      author_profile_url text,
      cover_url text,
      published_at_text text,
      metric_text text,
      detail_text text,
      detail_tags_json text not null,
      detail_comment_count_text text,
      detail_like_text text,
      detail_collect_text text,
      detail_share_text text,
      raw_card_text text not null,
      collected_at text not null default current_timestamp,
      updated_record_at text not null default current_timestamp,
      unique(run_id, keyword, sort_key, feed_id)
    );

    create table if not exists xhs_raw_snapshots (
      id integer primary key autoincrement,
      run_id integer not null references xhs_search_runs(id) on delete cascade,
      kind text not null,
      object_key text not null,
      page_url text not null,
      text_content text not null,
      html_content text,
      captured_at text not null default current_timestamp
    );

    create index if not exists idx_xhs_search_runs_source_run_id on xhs_search_runs(source_run_id);
    create index if not exists idx_xhs_search_notes_run_id on xhs_search_notes(run_id);
    create index if not exists idx_xhs_search_notes_feed_id on xhs_search_notes(feed_id);
    create index if not exists idx_xhs_raw_snapshots_run_id on xhs_raw_snapshots(run_id);
```

Then add migration-safe `ensureColumn` calls after the existing note migrations:

```ts
  ensureColumn(db, 'xhs_search_runs', 'error_stage', 'text');
  ensureColumn(db, 'xhs_search_runs', 'error_message', 'text');
  ensureColumn(db, 'xhs_search_notes', 'explore_url', 'text');
  ensureColumn(db, 'xhs_search_notes', 'detail_text', 'text');
  ensureColumn(db, 'xhs_search_notes', 'detail_tags_json', "text not null default '[]'");
  ensureColumn(db, 'xhs_search_notes', 'detail_comment_count_text', 'text');
  ensureColumn(db, 'xhs_search_notes', 'detail_like_text', 'text');
  ensureColumn(db, 'xhs_search_notes', 'detail_collect_text', 'text');
  ensureColumn(db, 'xhs_search_notes', 'detail_share_text', 'text');
  ensureColumn(db, 'xhs_search_notes', 'updated_record_at', 'text');
  db.exec('update xhs_search_notes set updated_record_at = current_timestamp where updated_record_at is null');
```

- [ ] **Step 4: Add repository imports and row interfaces**

Modify `src/db/repositories.ts` imports:

```ts
import type {
  XhsRawSnapshotInput,
  XhsSearchNoteRow,
  XhsSearchRunInput,
} from '../xhs-types.js';
```

Add row interfaces near existing DB row interfaces:

```ts
interface HotWordKeywordDbRow {
  word: string;
}
```

- [ ] **Step 5: Add repository methods**

Add these methods inside `CollectorRepository`:

```ts
  createXhsSearchRun(input: XhsSearchRunInput): number {
    const result = this.db
      .prepare(`
        insert into xhs_search_runs (
          source,
          source_run_id,
          keyword,
          sorts_json,
          limit_per_sort,
          with_details,
          status
        ) values (
          :source,
          :sourceRunId,
          :keyword,
          :sortsJson,
          :limitPerSort,
          :withDetails,
          'running'
        )
      `)
      .run({
        source: input.source,
        sourceRunId: input.sourceRunId,
        keyword: input.keyword,
        sortsJson: JSON.stringify(input.sorts),
        limitPerSort: input.limitPerSort,
        withDetails: input.withDetails ? 1 : 0,
      });

    return Number(result.lastInsertRowid);
  }

  finishXhsSearchRun(runId: number, status: RunStatus, errorStage?: string, errorMessage?: string): void {
    this.db
      .prepare(`
        update xhs_search_runs
        set status = :status,
            finished_at = current_timestamp,
            error_stage = :errorStage,
            error_message = :errorMessage
        where id = :runId
      `)
      .run({
        runId,
        status,
        errorStage: errorStage ?? null,
        errorMessage: errorMessage ?? null,
      });
  }

  upsertXhsSearchNotes(runId: number, rows: XhsSearchNoteRow[]): void {
    const insert = this.db.prepare(`
      insert into xhs_search_notes (
        run_id,
        keyword,
        sort_key,
        sort_label,
        rank_index,
        feed_id,
        xsec_token,
        search_result_url,
        explore_url,
        title,
        author_name,
        author_profile_url,
        cover_url,
        published_at_text,
        metric_text,
        detail_text,
        detail_tags_json,
        detail_comment_count_text,
        detail_like_text,
        detail_collect_text,
        detail_share_text,
        raw_card_text,
        updated_record_at
      ) values (
        :runId,
        :keyword,
        :sortKey,
        :sortLabel,
        :rankIndex,
        :feedId,
        :xsecToken,
        :searchResultUrl,
        :exploreUrl,
        :title,
        :authorName,
        :authorProfileUrl,
        :coverUrl,
        :publishedAtText,
        :metricText,
        :detailText,
        :detailTagsJson,
        :detailCommentCountText,
        :detailLikeText,
        :detailCollectText,
        :detailShareText,
        :rawCardText,
        current_timestamp
      )
      on conflict(run_id, keyword, sort_key, feed_id) do update set
        rank_index = excluded.rank_index,
        xsec_token = excluded.xsec_token,
        search_result_url = excluded.search_result_url,
        explore_url = coalesce(excluded.explore_url, xhs_search_notes.explore_url),
        title = excluded.title,
        author_name = excluded.author_name,
        author_profile_url = excluded.author_profile_url,
        cover_url = excluded.cover_url,
        published_at_text = excluded.published_at_text,
        metric_text = excluded.metric_text,
        detail_text = coalesce(excluded.detail_text, xhs_search_notes.detail_text),
        detail_tags_json = case
          when excluded.detail_tags_json != '[]' then excluded.detail_tags_json
          else xhs_search_notes.detail_tags_json
        end,
        detail_comment_count_text = coalesce(excluded.detail_comment_count_text, xhs_search_notes.detail_comment_count_text),
        detail_like_text = coalesce(excluded.detail_like_text, xhs_search_notes.detail_like_text),
        detail_collect_text = coalesce(excluded.detail_collect_text, xhs_search_notes.detail_collect_text),
        detail_share_text = coalesce(excluded.detail_share_text, xhs_search_notes.detail_share_text),
        raw_card_text = excluded.raw_card_text,
        updated_record_at = current_timestamp
    `);

    this.db.exec('savepoint upsert_xhs_search_notes_batch');
    try {
      for (const row of rows) {
        insert.run({
          runId,
          keyword: row.keyword,
          sortKey: row.sortKey,
          sortLabel: row.sortLabel,
          rankIndex: row.rankIndex,
          feedId: row.feedId,
          xsecToken: row.xsecToken,
          searchResultUrl: row.searchResultUrl,
          exploreUrl: row.exploreUrl,
          title: row.title,
          authorName: row.authorName,
          authorProfileUrl: row.authorProfileUrl,
          coverUrl: row.coverUrl,
          publishedAtText: row.publishedAtText,
          metricText: row.metricText,
          detailText: row.detailText,
          detailTagsJson: JSON.stringify(row.detailTags),
          detailCommentCountText: row.detailCommentCountText,
          detailLikeText: row.detailLikeText,
          detailCollectText: row.detailCollectText,
          detailShareText: row.detailShareText,
          rawCardText: row.rawCardText,
        });
      }
      this.db.exec('release upsert_xhs_search_notes_batch');
    } catch (error) {
      this.db.exec('rollback to upsert_xhs_search_notes_batch');
      this.db.exec('release upsert_xhs_search_notes_batch');
      throw error;
    }
  }

  insertXhsRawSnapshot(runId: number, snapshot: XhsRawSnapshotInput): void {
    this.db
      .prepare(`
        insert into xhs_raw_snapshots (
          run_id,
          kind,
          object_key,
          page_url,
          text_content,
          html_content
        ) values (
          :runId,
          :kind,
          :objectKey,
          :pageUrl,
          :textContent,
          :htmlContent
        )
      `)
      .run({
        runId,
        kind: snapshot.kind,
        objectKey: snapshot.objectKey,
        pageUrl: snapshot.pageUrl,
        textContent: snapshot.textContent,
        htmlContent: snapshot.htmlContent,
      });
  }

  listHotWordKeywordsForRun(runId: number, limit: number): string[] {
    const rows = this.db
      .prepare(`
        select word
        from hot_words
        where run_id = :runId
        order by rank_index asc, id asc
        limit :limit
      `)
      .all({ runId, limit }) as HotWordKeywordDbRow[];

    return rows.map((row) => row.word);
  }
```

- [ ] **Step 6: Run XHS DB tests**

Run:

```bash
npm test -- tests/xhs-db.test.ts
```

Expected: PASS.

- [ ] **Step 7: Run existing DB tests**

Run:

```bash
npm test -- tests/db.test.ts
```

Expected: PASS, proving existing Huitun repository behavior still works.

- [ ] **Step 8: Run typecheck**

Run:

```bash
npm run typecheck
```

Expected: PASS.

- [ ] **Step 9: Checkpoint without committing**

Run:

```bash
git status --short
```

Expected: DB schema/repository and XHS DB test changes are visible; no commit is created.

---

### Task 5: Add XHS browser session and search automation

**Files:**
- Create: `src/browser/xhs-session.ts`
- Modify: `src/browser/xhs-search.ts`
- Test: `tests/xhs-search-parser.test.ts`

**XHS-Downloader reference applied:** Reimplement the idea, not its GPL code: after each search-page scroll, prefer browser-page `window.__INITIAL_STATE__` feed extraction, then fall back to `section.note-item` DOM parsing.

- [ ] **Step 1: Add tests for sort active verification helper and safe URL selection**

Append to `tests/xhs-search-parser.test.ts`:

```ts
import { isXhsSortActive, pickBestXhsSearchResultUrl } from '../src/browser/xhs-search.js';

describe('XHS browser automation helpers', () => {
  it('checks active sort labels by exact label', () => {
    expect(isXhsSortActive(['综合', '最多收藏'], 'most_collected')).toBe(true);
    expect(isXhsSortActive(['综合', '最多评论'], 'most_collected')).toBe(false);
  });

  it('prefers search_result links with xsec token over short explore links', () => {
    expect(
      pickBestXhsSearchResultUrl([
        'https://www.xiaohongshu.com/explore/69755391000000000a02b2b8',
        'https://www.xiaohongshu.com/search_result/69755391000000000a02b2b8?xsec_token=token-a&xsec_source=',
      ]),
    ).toBe('https://www.xiaohongshu.com/search_result/69755391000000000a02b2b8?xsec_token=token-a&xsec_source=');
  });
});
```

- [ ] **Step 2: Run parser tests and verify failure**

Run:

```bash
npm test -- tests/xhs-search-parser.test.ts
```

Expected: FAIL because `isXhsSortActive` and `pickBestXhsSearchResultUrl` are not implemented.

- [ ] **Step 3: Add session wrapper**

Create `src/browser/xhs-session.ts`:

```ts
import { chromium } from 'playwright-core';
import type { Browser, BrowserContext, Page } from 'playwright-core';

export interface XhsSession {
  browser: Browser;
  context: BrowserContext;
  page: Page;
  close: () => Promise<void>;
}

export async function createXhsSession(cdpUrl: string): Promise<XhsSession> {
  let browser: Browser;

  try {
    browser = await chromium.connectOverCDP(cdpUrl);
  } catch (error) {
    throw new Error(`无法连接浏览器 CDP：${cdpUrl}。请先启动带 remote debugging 且已登录小红书的 Edge/Chrome，再重试。原始错误：${String(error)}`);
  }

  const context = browser.contexts()[0] ?? (await browser.newContext());
  const page = await context.newPage();
  page.setDefaultTimeout(30_000);

  return {
    browser,
    context,
    page,
    close: async () => {
      await page.close().catch(() => undefined);
      await browser.close({ reason: 'xhs search collector finished' }).catch(() => undefined);
    },
  };
}

export async function captureXhsPageSnapshot(page: Page): Promise<{ url: string; text: string; html: string }> {
  const text = await page.locator('body').innerText().catch(() => '');
  const html = await page.content().catch(() => '');

  return {
    url: page.url(),
    text,
    html,
  };
}
```

- [ ] **Step 4: Add automation helpers and collection functions**

Extend `src/browser/xhs-search.ts`:

```ts
export function isXhsSortActive(activeLabels: string[], sortKey: XhsSearchSortKey): boolean {
  return activeLabels.includes(XHS_SEARCH_SORTS[sortKey]);
}

export function pickBestXhsSearchResultUrl(urls: string[]): string | null {
  const absoluteUrls = urls.map((url) => absoluteXhsUrl(url));
  return absoluteUrls.find((url) => url.includes('/search_result/') && url.includes('xsec_token=')) ?? null;
}

export function parseXhsInitialStateSearchCardPayloads(state: unknown): XhsSearchCardPayload[] {
  if (!state || typeof state !== 'object') {
    return [];
  }

  const searchRoot = (state as Record<string, unknown>).search;
  if (!searchRoot || typeof searchRoot !== 'object') {
    return [];
  }

  const feeds = (searchRoot as Record<string, unknown>).feeds;
  const rawFeeds = feeds && typeof feeds === 'object' && '_rawValue' in feeds
    ? (feeds as Record<string, unknown>)._rawValue
    : feeds;
  if (!Array.isArray(rawFeeds)) {
    return [];
  }

  return rawFeeds.flatMap((item): XhsSearchCardPayload[] => {
    if (!item || typeof item !== 'object') {
      return [];
    }
    const record = item as Record<string, unknown>;
    const id = typeof record.id === 'string' ? record.id : typeof record.noteId === 'string' ? record.noteId : null;
    const xsecToken = typeof record.xsecToken === 'string' ? record.xsecToken : typeof record.xsec_token === 'string' ? record.xsec_token : null;
    if (!id || !xsecToken) {
      return [];
    }

    const title = typeof record.title === 'string' ? record.title : '';
    const author = record.user && typeof record.user === 'object' && 'nickname' in record.user
      ? String((record.user as Record<string, unknown>).nickname ?? '')
      : '';

    return [{
      searchResultUrl: `https://www.xiaohongshu.com/search_result/${id}?xsec_token=${encodeURIComponent(xsecToken)}`,
      authorProfileUrl: null,
      coverUrl: null,
      rawText: [title, author].filter(Boolean).join('\n'),
    }];
  });
}

async function openXhsFilterPanel(page: Page): Promise<void> {
  if ((await page.locator('.filter-panel').count()) > 0) {
    return;
  }

  await page.locator('.filter').click();
  await page.locator('.filter-panel').waitFor({ state: 'visible' });
}

async function activeXhsSortLabels(page: Page): Promise<string[]> {
  return page.locator('.filter-panel .filters').first().locator('.tags.active').allTextContents();
}

export async function openXhsSearchPage(page: Page, keyword: string): Promise<void> {
  await page.goto(buildXhsSearchUrl(keyword), { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle').catch(() => undefined);
  await assertXhsLoggedIn(page);
}

export async function switchXhsSearchSort(page: Page, sortKey: XhsSearchSortKey): Promise<void> {
  await openXhsFilterPanel(page);
  const label = XHS_SEARCH_SORTS[sortKey];
  const hiddenButton = page.locator(`[data-hp-kind="filter-tag-${label}"]`).first();

  if ((await hiddenButton.count()) === 0) {
    const visibleByText = page.locator('.filter-panel .filters').first().locator('.tags').filter({ hasText: label }).last();
    if ((await visibleByText.count()) === 0) {
      throw new Error(`XHS sort option not found: ${label}`);
    }
    await visibleByText.click();
  } else {
    await hiddenButton.evaluate((element) => {
      const visible = element.nextElementSibling as HTMLElement | null;
      if (!visible) {
        throw new Error('XHS visible sort button sibling not found.');
      }
      visible.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
      visible.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
      visible.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
    });
  }

  await page.waitForFunction(
    ({ expectedLabel }) => {
      const labels = Array.from(document.querySelectorAll('.filter-panel .filters:first-child .tags.active')).map((node) =>
        (node.textContent ?? '').trim(),
      );
      return labels.includes(expectedLabel);
    },
    { expectedLabel: label },
  );
}

async function collectInitialStateXhsSearchCardPayloads(page: Page): Promise<XhsSearchCardPayload[]> {
  const state = await page.evaluate(() => (window as unknown as { __INITIAL_STATE__?: unknown }).__INITIAL_STATE__).catch(() => null);
  return parseXhsInitialStateSearchCardPayloads(state);
}

async function collectVisibleXhsSearchCardPayloads(page: Page): Promise<XhsSearchCardPayload[]> {
  const sections = page.locator('section.note-item');
  const count = await sections.count();
  const payloads: XhsSearchCardPayload[] = [];

  for (let index = 0; index < count; index += 1) {
    const section = sections.nth(index);
    const rawText = (await section.innerText().catch(() => '')).trim();
    const hrefs = await section.locator('a').evaluateAll((anchors) => anchors.map((anchor) => (anchor as HTMLAnchorElement).href));
    const searchResultUrl = pickBestXhsSearchResultUrl(hrefs);
    const authorProfileUrl = hrefs.find((href) => href.includes('/user/profile/')) ?? null;
    const coverUrl = await section.locator('img').first().getAttribute('src').catch(() => null);

    payloads.push({
      searchResultUrl,
      authorProfileUrl,
      coverUrl,
      rawText,
    });
  }

  return payloads;
}

export async function collectXhsSearchNoteRows(
  page: Page,
  keyword: string,
  sortKey: XhsSearchSortKey,
  limit: number,
): Promise<XhsSearchNoteRow[]> {
  await switchXhsSearchSort(page, sortKey);

  const payloadsByFeedId = new Map<string, XhsSearchCardPayload>();
  let unchangedScrolls = 0;

  while (payloadsByFeedId.size < limit && unchangedScrolls < 4) {
    const previousSize = payloadsByFeedId.size;
    const initialStatePayloads = await collectInitialStateXhsSearchCardPayloads(page);
    const payloads = initialStatePayloads.length > 0 ? initialStatePayloads : await collectVisibleXhsSearchCardPayloads(page);
    for (const payload of payloads) {
      if (!payload.searchResultUrl) {
        continue;
      }
      const identity = extractXhsNoteIdentity(payload.searchResultUrl);
      if (identity && !payloadsByFeedId.has(identity.feedId)) {
        payloadsByFeedId.set(identity.feedId, payload);
      }
    }

    unchangedScrolls = payloadsByFeedId.size === previousSize ? unchangedScrolls + 1 : 0;
    if (payloadsByFeedId.size >= limit) {
      break;
    }

    await page.mouse.wheel(0, 1800);
    await page.waitForTimeout(700);
  }

  return parseXhsSearchNoteRows(keyword, sortKey, Array.from(payloadsByFeedId.values())).slice(0, limit);
}
```

- [ ] **Step 5: Run XHS search parser tests**

Run:

```bash
npm test -- tests/xhs-search-parser.test.ts
```

Expected: PASS.

- [ ] **Step 6: Run typecheck**

Run:

```bash
npm run typecheck
```

Expected: PASS.

- [ ] **Step 7: Checkpoint without committing**

Run:

```bash
git status --short
```

Expected: XHS browser automation files are visible; no commit is created.

---

### Task 6: Add CLI option parsing for `xhs-search`

**Files:**
- Modify: `src/cli.ts`
- Modify: `tests/cli-options.test.ts`

- [ ] **Step 1: Write failing CLI parser tests**

Append to `tests/cli-options.test.ts`:

```ts
import { parseXhsSearchOptions } from '../src/cli.js';

describe('parseXhsSearchOptions', () => {
  it('parses manual keyword XHS search options with defaults', () => {
    expect(parseXhsSearchOptions(['node', 'src/cli.ts', 'xhs-search', '--keyword', '护肤'])).toEqual({
      keyword: '护肤',
      fromHuitunRunId: undefined,
      limitKeywords: 10,
      sorts: ['latest', 'most_liked', 'most_commented', 'most_collected'],
      limitPerSort: 20,
      withDetails: false,
      dbPath: 'data/xhs-ops.sqlite',
      cdpUrl: 'http://127.0.0.1:9222',
    });
  });

  it('parses Huitun run source options', () => {
    expect(
      parseXhsSearchOptions([
        'node',
        'src/cli.ts',
        'xhs-search',
        '--from-huitun-run-id',
        '123',
        '--limit-keywords',
        '5',
        '--sorts',
        'latest,most_collected',
        '--limit-per-sort',
        '12',
        '--with-details',
        '--db-path',
        'data/custom.sqlite',
        '--cdp-url',
        'http://127.0.0.1:9333',
      ]),
    ).toEqual({
      keyword: undefined,
      fromHuitunRunId: 123,
      limitKeywords: 5,
      sorts: ['latest', 'most_collected'],
      limitPerSort: 12,
      withDetails: true,
      dbPath: 'data/custom.sqlite',
      cdpUrl: 'http://127.0.0.1:9333',
    });
  });

  it('requires exactly one XHS keyword source', () => {
    expect(() => parseXhsSearchOptions(['node', 'src/cli.ts', 'xhs-search'])).toThrow(
      'xhs-search requires exactly one of --keyword or --from-huitun-run-id',
    );
    expect(() =>
      parseXhsSearchOptions(['node', 'src/cli.ts', 'xhs-search', '--keyword', '护肤', '--from-huitun-run-id', '123']),
    ).toThrow('xhs-search requires exactly one of --keyword or --from-huitun-run-id');
  });

  it('rejects invalid XHS sort keys', () => {
    expect(() => parseXhsSearchOptions(['node', 'src/cli.ts', 'xhs-search', '--keyword', '护肤', '--sorts', 'latest,bad'])).toThrow(
      'Unsupported XHS sort key: bad',
    );
  });

  it('prints root help with xhs-search command', () => {
    const result = spawnSync('node', ['--no-warnings', './node_modules/tsx/dist/cli.mjs', 'src/cli.ts', '--help'], {
      encoding: 'utf8',
    });

    expect(result.status).toBe(0);
    expect(result.stdout).toContain('xhs-search');
  });
});
```

- [ ] **Step 2: Run CLI tests and verify failure**

Run:

```bash
npm test -- tests/cli-options.test.ts
```

Expected: FAIL because `parseXhsSearchOptions` is not exported and `xhs-search` help is missing.

- [ ] **Step 3: Add XHS CLI option types and parser imports**

Modify `src/cli.ts` imports:

```ts
import { parseXhsSortKeys } from './browser/xhs-search.js';
import type { XhsSearchSortKey } from './xhs-types.js';
```

Add interface after existing CLI option interfaces:

```ts
interface XhsSearchCliOptions {
  keyword?: string;
  fromHuitunRunId?: number;
  limitKeywords: number;
  sorts?: string;
  limitPerSort: number;
  withDetails: boolean;
  dbPath: string;
  cdpUrl: string;
}

export interface XhsSearchCommandOptions {
  keyword?: string;
  fromHuitunRunId?: number;
  limitKeywords: number;
  sorts: XhsSearchSortKey[];
  limitPerSort: number;
  withDetails: boolean;
  dbPath: string;
  cdpUrl: string;
}
```

- [ ] **Step 4: Add command and parser functions**

Modify `createProgram()` to add the command name:

```ts
function createProgram(): Command {
  return createCollectionProgram()
    .addCommand(new Command('report').description('Show a readable summary for a Huitun collection run'))
    .addCommand(new Command('export').description('Export de-duplicated Huitun hot note rows to CSV'))
    .addCommand(new Command('xhs-search').description('Collect Xiaohongshu search results for hot keywords'));
}
```

Add parser function after `createExportProgram()`:

```ts
function createXhsSearchProgram(): Command {
  return new Command()
    .name('xhs-huitun-collector xhs-search')
    .description('Collect Xiaohongshu search results for hot keywords')
    .option('--keyword <keyword>', '单个小红书搜索关键词')
    .option('--from-huitun-run-id <id>', '从指定灰豚 run 的热词中读取关键词', (value) => parsePositiveInteger(value, '--from-huitun-run-id'))
    .option('--limit-keywords <count>', '从灰豚 run 读取时最多处理多少个热词', (value) => parsePositiveInteger(value, '--limit-keywords'), 10)
    .option('--sorts <list>', '逗号分隔排序维度：latest,most_liked,most_commented,most_collected')
    .option('--limit-per-sort <count>', '每个排序维度最多采集多少条', (value) => parsePositiveInteger(value, '--limit-per-sort'), 20)
    .option('--with-details', '串行打开详情页补充正文、标签和详情互动数据', false)
    .option('--db-path <path>', 'SQLite 数据库路径', 'data/xhs-ops.sqlite')
    .option('--cdp-url <url>', '已登录浏览器的 CDP 地址', 'http://127.0.0.1:9222');
}

function parseXhsSearchOptions(argv = process.argv): XhsSearchCommandOptions {
  const program = createXhsSearchProgram();
  program.exitOverride();
  program.parse(argvWithoutSubcommand(argv));
  const options = program.opts<XhsSearchCliOptions>();

  const sourceCount = Number(options.keyword !== undefined) + Number(options.fromHuitunRunId !== undefined);
  if (sourceCount !== 1) {
    throw new InvalidArgumentError('xhs-search requires exactly one of --keyword or --from-huitun-run-id');
  }

  return {
    keyword: options.keyword,
    fromHuitunRunId: options.fromHuitunRunId,
    limitKeywords: options.limitKeywords,
    sorts: parseXhsSortKeys(options.sorts),
    limitPerSort: options.limitPerSort,
    withDetails: options.withDetails,
    dbPath: options.dbPath,
    cdpUrl: options.cdpUrl,
  };
}
```

- [ ] **Step 5: Export parser**

Modify the export list at the bottom of `src/cli.ts`:

```ts
export {
  collect,
  createProgram,
  formatRawSnapshotTextContent,
  parseExportOptions,
  parseOptions,
  parseReportOptions,
  parseXhsSearchOptions,
};
```

- [ ] **Step 6: Run CLI tests**

Run:

```bash
npm test -- tests/cli-options.test.ts
```

Expected: PASS.

- [ ] **Step 7: Run typecheck**

Run:

```bash
npm run typecheck
```

Expected: PASS.

- [ ] **Step 8: Checkpoint without committing**

Run:

```bash
git status --short
```

Expected: `src/cli.ts` and `tests/cli-options.test.ts` are modified; no commit is created.

---

### Task 7: Add XHS search collector orchestration

**Files:**
- Create: `src/xhs-search-collector.ts`
- Modify: `src/cli.ts`
- Test: `tests/xhs-db.test.ts`

- [ ] **Step 1: Add failing keyword-resolution tests**

Append to `tests/xhs-db.test.ts` inside the existing describe block:

```ts
  it('returns no hot words for a missing Huitun run when resolving XHS keywords', () => {
    expect(repository.listHotWordKeywordsForRun(999999, 10)).toEqual([]);
  });
```

- [ ] **Step 2: Run XHS DB tests**

Run:

```bash
npm test -- tests/xhs-db.test.ts
```

Expected: PASS if Task 4 already implemented `listHotWordKeywordsForRun`; if it fails, fix that method before continuing.

- [ ] **Step 3: Create collector orchestration file**

Create `src/xhs-search-collector.ts`:

```ts
import type { DatabaseSync } from 'node:sqlite';

import { collectXhsNoteDetail } from './browser/xhs-note-detail.js';
import { collectXhsSearchNoteRows, openXhsSearchPage, XHS_LOGIN_REQUIRED_MESSAGE } from './browser/xhs-search.js';
import { captureXhsPageSnapshot, createXhsSession, type XhsSession } from './browser/xhs-session.js';
import type { XhsSearchCommandOptions } from './cli.js';
import type { CollectorRepository } from './db/repositories.js';
import type { RunStatus } from './types.js';
import type { XhsNoteDetail, XhsSearchNoteRow } from './xhs-types.js';

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

async function insertXhsRawSnapshotFromPage(
  repository: CollectorRepository,
  runId: number,
  session: XhsSession,
  kind: string,
  objectKey: string,
  diagnosticMessage?: string,
): Promise<void> {
  const snapshot = await captureXhsPageSnapshot(session.page);
  repository.insertXhsRawSnapshot(runId, {
    kind,
    objectKey,
    pageUrl: snapshot.url,
    textContent: diagnosticMessage === undefined ? snapshot.text : `${diagnosticMessage}\n\n${snapshot.text}`,
    htmlContent: snapshot.html,
  });
}

function applyDetail(row: XhsSearchNoteRow, detail: XhsNoteDetail): XhsSearchNoteRow {
  return {
    ...row,
    exploreUrl: detail.exploreUrl,
    xsecToken: detail.xsecToken ?? row.xsecToken,
    detailText: detail.detailText,
    detailTags: detail.tags,
    detailCommentCountText: detail.commentCountText,
    detailLikeText: detail.likeText,
    detailCollectText: detail.collectText,
    detailShareText: detail.shareText,
  };
}

async function enrichRowsWithDetails(session: XhsSession, rows: XhsSearchNoteRow[]): Promise<XhsSearchNoteRow[]> {
  const enrichedRows: XhsSearchNoteRow[] = [];

  for (const row of rows) {
    try {
      const detailPage = await session.context.newPage();
      detailPage.setDefaultTimeout(30_000);
      try {
        const detail = await collectXhsNoteDetail(detailPage, row.searchResultUrl);
        enrichedRows.push(applyDetail(row, detail));
      } finally {
        await detailPage.close().catch(() => undefined);
      }
    } catch {
      enrichedRows.push(row);
    }
  }

  return enrichedRows;
}

async function collectSingleXhsKeyword(
  repository: CollectorRepository,
  session: XhsSession,
  options: XhsSearchCommandOptions,
  keyword: string,
  sourceRunId: number | null,
): Promise<{ runId: number; status: RunStatus; noteCount: number }> {
  const runId = repository.createXhsSearchRun({
    source: sourceRunId === null ? 'manual_keyword' : 'huitun_run',
    sourceRunId,
    keyword,
    sorts: options.sorts,
    limitPerSort: options.limitPerSort,
    withDetails: options.withDetails,
  });
  let status: RunStatus = 'success';
  let noteCount = 0;

  try {
    await openXhsSearchPage(session.page, keyword);

    for (const sortKey of options.sorts) {
      try {
        let rows = await collectXhsSearchNoteRows(session.page, keyword, sortKey, options.limitPerSort);
        if (rows.length < options.limitPerSort) {
          status = 'partial_success';
          await insertXhsRawSnapshotFromPage(
            repository,
            runId,
            session,
            'xhs_note_list_short',
            `${keyword}:${sortKey}`,
            `Expected ${options.limitPerSort} notes, collected ${rows.length}.`,
          );
        }

        if (options.withDetails) {
          rows = await enrichRowsWithDetails(session, rows);
        }

        repository.upsertXhsSearchNotes(runId, rows);
        noteCount += rows.length;
      } catch (error) {
        status = 'partial_success';
        const message = errorMessage(error);
        const kind = message.includes('sort option not found') ? 'xhs_sort_not_found' : 'xhs_sort_click_failed';
        await insertXhsRawSnapshotFromPage(repository, runId, session, kind, `${keyword}:${sortKey}`, message);
      }
    }

    repository.finishXhsSearchRun(runId, status);
    return { runId, status, noteCount };
  } catch (error) {
    const message = errorMessage(error);
    const errorStage = message === XHS_LOGIN_REQUIRED_MESSAGE ? 'xhs_login' : 'xhs_search';
    if (message === XHS_LOGIN_REQUIRED_MESSAGE) {
      await insertXhsRawSnapshotFromPage(repository, runId, session, 'xhs_login_required', keyword, message).catch(() => undefined);
    }
    repository.finishXhsSearchRun(runId, 'failed', errorStage, message);
    throw error;
  }
}

export async function collectXhsSearch(options: XhsSearchCommandOptions): Promise<{
  runs: Array<{ runId: number; keyword: string; status: RunStatus; noteCount: number }>;
  dbPath: string;
}> {
  let db: DatabaseSync | undefined;
  let repository: CollectorRepository | undefined;
  let session: XhsSession | undefined;

  try {
    const [{ openDatabase }, { initializeSchema }, { CollectorRepository }] = await Promise.all([
      import('./db/client.js'),
      import('./db/schema.js'),
      import('./db/repositories.js'),
    ]);

    db = openDatabase(options.dbPath);
    initializeSchema(db);
    repository = new CollectorRepository(db);
    session = await createXhsSession(options.cdpUrl);

    const keywords = options.keyword
      ? [options.keyword]
      : repository.listHotWordKeywordsForRun(options.fromHuitunRunId ?? 0, options.limitKeywords);

    if (keywords.length === 0) {
      throw new Error('No keywords found for xhs-search.');
    }

    const runs: Array<{ runId: number; keyword: string; status: RunStatus; noteCount: number }> = [];
    for (const keyword of keywords) {
      const result = await collectSingleXhsKeyword(repository, session, options, keyword, options.fromHuitunRunId ?? null);
      runs.push({ keyword, ...result });
    }

    return { runs, dbPath: options.dbPath };
  } finally {
    await session?.close();
    db?.close();
  }
}
```

- [ ] **Step 4: Wire CLI command to collector**

Modify `main()` in `src/cli.ts` before the root help branch:

```ts
  if (command === 'xhs-search') {
    const { collectXhsSearch } = await import('./xhs-search-collector.js');
    const result = await collectXhsSearch(parseXhsSearchOptions(argv));
    console.log(JSON.stringify(result));
    return;
  }
```

- [ ] **Step 5: Run CLI option tests**

Run:

```bash
npm test -- tests/cli-options.test.ts
```

Expected: PASS.

- [ ] **Step 6: Run XHS DB tests**

Run:

```bash
npm test -- tests/xhs-db.test.ts
```

Expected: PASS.

- [ ] **Step 7: Run typecheck**

Run:

```bash
npm run typecheck
```

Expected: PASS.

- [ ] **Step 8: Checkpoint without committing**

Run:

```bash
git status --short
```

Expected: `src/xhs-search-collector.ts` and `src/cli.ts` are visible; no commit is created.

---

### Task 8: Run full automated verification and manual XHS smoke test

**Files:**
- No source changes expected unless verification reveals a bug.

- [ ] **Step 1: Run all tests**

Run:

```bash
npm test
```

Expected: PASS.

- [ ] **Step 2: Run typecheck**

Run:

```bash
npm run typecheck
```

Expected: PASS.

- [ ] **Step 3: Run a logged-in browser smoke test for one keyword without details**

Use an already logged-in Xiaohongshu CDP browser. Run:

```bash
npm run collect -- xhs-search --keyword 护肤 --sorts most_collected --limit-per-sort 3
```

Expected: command prints JSON with one run, status `success` or `partial_success`, and `noteCount` at least 1.

- [ ] **Step 4: Inspect SQLite rows from smoke test**

Run:

```bash
node --input-type=module - <<'NODE'
import { DatabaseSync } from 'node:sqlite';
const db = new DatabaseSync('data/xhs-ops.sqlite');
const run = db.prepare('select id, keyword, status from xhs_search_runs order by id desc limit 1').get();
const notes = db.prepare('select keyword, sort_key, rank_index, feed_id, title, metric_text, search_result_url from xhs_search_notes where run_id = ? order by rank_index').all(run.id);
console.log(JSON.stringify({ run, notes }, null, 2));
db.close();
NODE
```

Expected: rows include `sort_key = 'most_collected'`, non-empty `feed_id`, non-empty `title`, non-empty `search_result_url` containing `/search_result/` and `xsec_token=`.

- [ ] **Step 5: Run a logged-in browser smoke test with details for one note**

Run:

```bash
npm run collect -- xhs-search --keyword 护肤 --sorts most_collected --limit-per-sort 1 --with-details
```

Expected: command prints JSON with one run and `noteCount` equal to 1.

- [ ] **Step 6: Inspect detail fields from smoke test**

Run:

```bash
node --input-type=module - <<'NODE'
import { DatabaseSync } from 'node:sqlite';
const db = new DatabaseSync('data/xhs-ops.sqlite');
const run = db.prepare('select id, keyword, status from xhs_search_runs order by id desc limit 1').get();
const note = db.prepare('select feed_id, explore_url, detail_text, detail_tags_json, detail_comment_count_text, detail_like_text, detail_collect_text from xhs_search_notes where run_id = ? order by rank_index limit 1').get(run.id);
console.log(JSON.stringify({ run, note }, null, 2));
db.close();
NODE
```

Expected: `explore_url` contains `/explore/` and `xsec_token=`, and at least one of `detail_text`, `detail_tags_json`, or `detail_comment_count_text` is populated.

- [ ] **Step 7: Verify no unwanted actions were added**

Run:

```bash
npm test -- tests/xhs-search-parser.test.ts tests/xhs-note-detail-parser.test.ts tests/xhs-db.test.ts
```

Expected: PASS. Search source files for interactive action strings:

```bash
node --input-type=module - <<'NODE'
import { readFileSync } from 'node:fs';
const files = ['src/browser/xhs-search.ts', 'src/browser/xhs-note-detail.ts', 'src/xhs-search-collector.ts'];
for (const file of files) {
  const text = readFileSync(file, 'utf8');
  for (const forbidden of ['点赞', '收藏', '评论', '关注', '发布']) {
    if (text.includes(`click${forbidden}`) || text.includes(`do${forbidden}`)) {
      throw new Error(`${file} contains suspicious action string: ${forbidden}`);
    }
  }
}
console.log('no forbidden action helpers found');
NODE
```

Expected: `no forbidden action helpers found`.

- [ ] **Step 8: Final working tree checkpoint**

Run:

```bash
git status --short
```

Expected: implementation files and tests are modified/new; no commit is created unless the user explicitly requested one.

---

## Self-Review

Spec coverage:

- Login wall detection is covered by Task 1 and Task 7.
- Verified sort dimensions are covered by Task 1, Task 5, and Task 8.
- Top-N per sort collection is covered by Task 5 and Task 7.
- Separate SQLite tables are covered by Task 4.
- Full `search_result` URL and `xsec_token` handling are covered by Task 2, Task 3, and Task 8.
- Optional detail enrichment is covered by Task 3, Task 7, and Task 8.
- Huitun run keyword input is covered by Task 4, Task 6, and Task 7.
- No publishing/interactions are enforced by scope and checked in Task 8.

Type consistency:

- Sort keys use `XhsSearchSortKey` everywhere.
- Run statuses reuse existing `RunStatus`.
- Repository methods consume `XhsSearchRunInput`, `XhsSearchNoteRow`, and `XhsRawSnapshotInput` from `src/xhs-types.ts`.
- CLI parser returns `XhsSearchCommandOptions`, consumed by `collectXhsSearch`.

Execution notes:

- The smoke tests require a real logged-in Xiaohongshu browser on the configured CDP port.
- If the smoke test sees “登录后查看搜索结果”, the implementation should fail with the XHS login message instead of inserting empty rows.
- If Xiaohongshu changes DOM classes, parser tests remain useful for pure parsing, and raw snapshots from smoke tests should guide selector updates.

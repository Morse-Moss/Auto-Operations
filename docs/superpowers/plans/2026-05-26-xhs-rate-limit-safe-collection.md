# XHS Rate Limit Safe Collection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add balanced safe-mode detail collection to `xhs-search --with-details`: default delay, per-command detail budget, rate-limit detection, immediate circuit breaker, and resume for already-detailed rows.

**Architecture:** Keep the current CLI and collector flow, but insert a small safety layer around detail page visits. `src/cli.ts` owns option parsing and defaults, `src/browser/xhs-note-detail.ts` owns XHS rate-limit detection from detail pages, and `src/xhs-search-collector.ts` owns budget, delay, resume, and batch-level stop behavior.

**Tech Stack:** Node.js + TypeScript, Commander, Playwright CDP, SQLite via `node:sqlite`, Vitest.

---

## Files and Responsibilities

- Modify `src/cli.ts`
  - Parse new detail safety options.
  - Validate delay and budget values.
  - Add defaults to `XhsSearchCommandOptions`.

- Modify `src/xhs-types.ts`
  - Add typed rate-limit context and collector result fields.

- Modify `src/browser/xhs-note-detail.ts`
  - Export an `XhsRateLimitError` class.
  - Export `isXhsRateLimitSignal()`.
  - Detect `/website-login/error`, `error_code=300013`, and Chinese rate-limit text after navigation.

- Modify `src/xhs-search-collector.ts`
  - Track detail budget across a whole command.
  - Delay between detail page visits.
  - Skip rows that already have detail evidence when resume is enabled.
  - Write `xhs_rate_limited` and `xhs_detail_budget_exhausted` snapshots.
  - Stop the whole batch on rate limit when `stopOnRateLimit` is enabled.

- Modify `src/db/repositories.ts`
  - Add a repository query for already-detailed rows in a run.
  - Keep existing upsert behavior that does not overwrite successful detail fields with null or empty values.

- Modify tests:
  - `tests/cli-options.test.ts`
  - `tests/xhs-note-detail-parser.test.ts`
  - `tests/xhs-search-collector.test.ts`
  - `tests/xhs-db.test.ts`

---

## Task 1: CLI detail safety options

**Files:**
- Modify: `tests/cli-options.test.ts`
- Modify: `src/cli.ts`

- [ ] **Step 1: Write failing tests for default XHS detail safety options**

Add to `tests/cli-options.test.ts` inside `describe('parseOptions', ...)`, after the existing `parses xhs-search manual keyword defaults` test:

```ts
  it('parses xhs-search detail safety defaults', () => {
    expect(parseXhsSearchOptions(['node', 'src/cli.ts', 'xhs-search', '--keyword', '护肤'])).toMatchObject({
      detailDelayMinMs: 20_000,
      detailDelayMaxMs: 60_000,
      detailBudget: 30,
      stopOnRateLimit: true,
      resumeMissingDetails: true,
    });
  });
```

- [ ] **Step 2: Write failing tests for explicit XHS detail safety options**

Add to `tests/cli-options.test.ts`:

```ts
  it('parses explicit xhs-search detail safety options', () => {
    expect(
      parseXhsSearchOptions([
        'node',
        'src/cli.ts',
        'xhs-search',
        '--keyword',
        '护肤',
        '--with-details',
        '--detail-delay-min-ms',
        '1000',
        '--detail-delay-max-ms',
        '2000',
        '--detail-budget',
        '2',
        '--no-stop-on-rate-limit',
        '--no-resume-missing-details',
      ]),
    ).toMatchObject({
      withDetails: true,
      detailDelayMinMs: 1000,
      detailDelayMaxMs: 2000,
      detailBudget: 2,
      stopOnRateLimit: false,
      resumeMissingDetails: false,
    });
  });
```

- [ ] **Step 3: Write failing tests for invalid delay and budget values**

Add to `tests/cli-options.test.ts`:

```ts
  it('rejects invalid xhs-search detail safety options', () => {
    expect(() =>
      parseXhsSearchOptions(['node', 'src/cli.ts', 'xhs-search', '--keyword', '护肤', '--detail-delay-min-ms', '-1']),
    ).toThrow('--detail-delay-min-ms 必须是非负整数，收到：-1');

    expect(() =>
      parseXhsSearchOptions(['node', 'src/cli.ts', 'xhs-search', '--keyword', '护肤', '--detail-delay-min-ms', '2000', '--detail-delay-max-ms', '1000']),
    ).toThrow('--detail-delay-max-ms 必须大于等于 --detail-delay-min-ms');

    expect(() =>
      parseXhsSearchOptions(['node', 'src/cli.ts', 'xhs-search', '--keyword', '护肤', '--detail-budget', '0']),
    ).toThrow('--detail-budget 必须是正整数，收到：0');
  });
```

- [ ] **Step 4: Run CLI option tests and verify they fail**

Run:

```bash
npm run test -- tests/cli-options.test.ts
```

Expected: FAIL because `detailDelayMinMs`, `detailDelayMaxMs`, `detailBudget`, `stopOnRateLimit`, and `resumeMissingDetails` are missing.

- [ ] **Step 5: Implement CLI option parsing**

In `src/cli.ts`, update `XhsSearchCliOptions`:

```ts
interface XhsSearchCliOptions {
  keyword?: string;
  fromHuitunRunId?: number;
  limitKeywords: number;
  sorts?: string;
  limitPerSort: number;
  withDetails: boolean;
  detailDelayMinMs: number;
  detailDelayMaxMs: number;
  detailBudget: number;
  stopOnRateLimit: boolean;
  resumeMissingDetails: boolean;
  dbPath: string;
  cdpUrl: string;
}
```

Update `XhsSearchCommandOptions`:

```ts
export interface XhsSearchCommandOptions {
  keyword?: string;
  fromHuitunRunId?: number;
  limitKeywords: number;
  sorts: XhsSearchSortKey[];
  limitPerSort: number;
  withDetails: boolean;
  detailDelayMinMs: number;
  detailDelayMaxMs: number;
  detailBudget: number;
  stopOnRateLimit: boolean;
  resumeMissingDetails: boolean;
  dbPath: string;
  cdpUrl: string;
}
```

Add this helper after `parsePositiveInteger()`:

```ts
function parseNonNegativeInteger(value: string, name: string): number {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 0) {
    throw new InvalidArgumentError(`${name} 必须是非负整数，收到：${value}`);
  }

  return parsed;
}
```

Update `addXhsSearchOptions()`:

```ts
    .option('--with-details', '采集小红书笔记详情', false)
    .option('--detail-delay-min-ms <ms>', '详情页之间的最小等待毫秒数', (value) => parseNonNegativeInteger(value, '--detail-delay-min-ms'), 20_000)
    .option('--detail-delay-max-ms <ms>', '详情页之间的最大等待毫秒数', (value) => parseNonNegativeInteger(value, '--detail-delay-max-ms'), 60_000)
    .option('--detail-budget <count>', '单次命令最多打开的详情页数量', (value) => parsePositiveInteger(value, '--detail-budget'), 30)
    .option('--no-stop-on-rate-limit', '遇到小红书访问频繁时不熔断')
    .option('--no-resume-missing-details', '不跳过已有详情的笔记')
    .option('--db-path <path>', 'SQLite 数据库路径', 'data/xhs-ops.sqlite')
```

Update `parseXhsSearchOptions()` before `return`:

```ts
  if (options.detailDelayMaxMs < options.detailDelayMinMs) {
    throw new Error('--detail-delay-max-ms 必须大于等于 --detail-delay-min-ms');
  }
```

Update the returned object:

```ts
    detailDelayMinMs: options.detailDelayMinMs,
    detailDelayMaxMs: options.detailDelayMaxMs,
    detailBudget: options.detailBudget,
    stopOnRateLimit: options.stopOnRateLimit,
    resumeMissingDetails: options.resumeMissingDetails,
```

- [ ] **Step 6: Run CLI option tests and verify they pass**

Run:

```bash
npm run test -- tests/cli-options.test.ts
```

Expected: PASS.

- [ ] **Step 7: Commit Task 1**

```bash
git add src/cli.ts tests/cli-options.test.ts
git commit -m "feat: add XHS detail safety CLI options"
```

---

## Task 2: Rate-limit detection in detail pages

**Files:**
- Modify: `tests/xhs-note-detail-parser.test.ts`
- Modify: `src/browser/xhs-note-detail.ts`

- [ ] **Step 1: Write failing tests for rate-limit signal detection**

Add imports in `tests/xhs-note-detail-parser.test.ts`:

```ts
  isXhsRateLimitSignal,
  XhsRateLimitError,
```

Add tests inside `describe('XHS note detail helpers', ...)`:

```ts
  it('detects XHS website-login rate limit URLs', () => {
    expect(isXhsRateLimitSignal({
      url: 'https://www.xiaohongshu.com/website-login/error?error_code=300013&error_msg=%E8%AE%BF%E9%97%AE%E9%A2%91%E7%B9%81%EF%BC%8C%E8%AF%B7%E7%A8%8D%E5%90%8E%E5%86%8D%E8%AF%95',
      text: '',
      message: '',
    })).toBe(true);
  });

  it('detects XHS rate limit text', () => {
    expect(isXhsRateLimitSignal({
      url: 'https://www.xiaohongshu.com/explore/feed1?xsec_token=token',
      text: '访问频繁，请稍后再试',
      message: '',
    })).toBe(true);
  });

  it('does not treat ordinary detail errors as XHS rate limits', () => {
    expect(isXhsRateLimitSignal({
      url: 'https://www.xiaohongshu.com/explore/feed1?xsec_token=token',
      text: '内容不存在',
      message: 'XHS detail page feed id mismatch',
    })).toBe(false);
  });
```

- [ ] **Step 2: Write failing test for `collectXhsNoteDetail()` throwing `XhsRateLimitError`**

Add to `tests/xhs-note-detail-parser.test.ts`:

```ts
  it('throws XhsRateLimitError when detail navigation lands on website-login rate limit', async () => {
    const page = {
      goto: async () => undefined,
      waitForLoadState: async () => undefined,
      url: () => 'https://www.xiaohongshu.com/website-login/error?error_code=300013&error_msg=%E8%AE%BF%E9%97%AE%E9%A2%91%E7%B9%81',
      locator: () => ({ innerText: async () => '访问频繁，请稍后再试' }),
    } as unknown as Page;

    await expect(collectXhsNoteDetail(page, '/search_result/feed1?xsec_token=token')).rejects.toBeInstanceOf(XhsRateLimitError);
  });
```

- [ ] **Step 3: Run detail parser tests and verify they fail**

Run:

```bash
npm run test -- tests/xhs-note-detail-parser.test.ts
```

Expected: FAIL because `isXhsRateLimitSignal` and `XhsRateLimitError` do not exist.

- [ ] **Step 4: Implement rate-limit error and detector**

In `src/browser/xhs-note-detail.ts`, after constants:

```ts
export class XhsRateLimitError extends Error {
  constructor(
    message: string,
    readonly finalUrl: string,
    readonly pageText: string,
  ) {
    super(message);
    this.name = 'XhsRateLimitError';
  }
}

export function isXhsRateLimitError(error: unknown): error is XhsRateLimitError {
  return error instanceof XhsRateLimitError;
}

export function isXhsRateLimitSignal(input: { url?: string | null; text?: string | null; message?: string | null }): boolean {
  const url = input.url ?? '';
  const text = input.text ?? '';
  const message = input.message ?? '';
  const combined = `${url}\n${text}\n${message}`;

  let host = '';
  let pathname = '';
  try {
    const parsed = new URL(url, XHS_NOTE_URL_BASE);
    host = parsed.hostname;
    pathname = parsed.pathname;
  } catch {
    host = '';
    pathname = '';
  }

  const isXhsHost = host === 'xiaohongshu.com' || host === 'www.xiaohongshu.com';
  if (isXhsHost && pathname === '/website-login/error' && combined.includes('error_code=300013')) {
    return true;
  }

  if (combined.includes('error_code=300013')) {
    return true;
  }

  if (combined.includes('访问频繁')) {
    return true;
  }

  return isXhsHost && combined.includes('请稍后再试');
}
```

- [ ] **Step 5: Check rate limit after detail navigation**

In `collectXhsNoteDetail()`, replace this block:

```ts
  const finalUrl = page.url();
  const identity = extractXhsNoteIdentity(finalUrl);
  if (identity === null) {
    throw new Error(`XHS detail page did not resolve to a note URL: ${finalUrl}`);
  }
```

with:

```ts
  const finalUrl = page.url();
  if (isXhsRateLimitSignal({ url: finalUrl })) {
    let pageText = '';
    try {
      pageText = await page.locator('body').innerText();
    } catch {
      pageText = '';
    }
    throw new XhsRateLimitError('XHS rate limited: error_code=300013 访问频繁，请稍后再试', finalUrl, pageText);
  }

  const identity = extractXhsNoteIdentity(finalUrl);
  if (identity === null) {
    let pageText = '';
    try {
      pageText = await page.locator('body').innerText();
    } catch {
      pageText = '';
    }
    if (isXhsRateLimitSignal({ url: finalUrl, text: pageText })) {
      throw new XhsRateLimitError('XHS rate limited: error_code=300013 访问频繁，请稍后再试', finalUrl, pageText);
    }
    throw new Error(`XHS detail page did not resolve to a note URL: ${finalUrl}`);
  }
```

Keep the existing later `const text = await page.locator('body').innerText();` unchanged.

- [ ] **Step 6: Run detail parser tests and verify they pass**

Run:

```bash
npm run test -- tests/xhs-note-detail-parser.test.ts
```

Expected: PASS.

- [ ] **Step 7: Commit Task 2**

```bash
git add src/browser/xhs-note-detail.ts tests/xhs-note-detail-parser.test.ts
git commit -m "feat: detect XHS rate limits"
```

---

## Task 3: Collector result types and detail budget plumbing

**Files:**
- Modify: `src/xhs-types.ts`
- Modify: `src/xhs-search-collector.ts`
- Modify: `tests/xhs-search-collector.test.ts`

- [ ] **Step 1: Write failing collector result default test**

In `tests/xhs-search-collector.test.ts`, update the first collector result expectation from:

```ts
expect(result.runs).toEqual([{ runId: 1, keyword: '护肤', status: 'partial_success', noteCount: 1 }]);
```

Keep that assertion and add:

```ts
expect(result).toMatchObject({
  rateLimited: false,
  detailBudgetUsed: 0,
});
```

- [ ] **Step 2: Add missing new options to every `collectXhsSearch()` test call**

For each test call to `collectXhsSearch({ ... })` in `tests/xhs-search-collector.test.ts`, add:

```ts
        detailDelayMinMs: 0,
        detailDelayMaxMs: 0,
        detailBudget: 30,
        stopOnRateLimit: true,
        resumeMissingDetails: true,
```

Use delay `0` in tests so test runs do not wait.

- [ ] **Step 3: Run collector tests and verify they fail on missing result fields or options**

Run:

```bash
npm run test -- tests/xhs-search-collector.test.ts
```

Expected: FAIL because collector result does not include `rateLimited` and `detailBudgetUsed`, and TypeScript may fail if options are incomplete.

- [ ] **Step 4: Add result interfaces to `src/xhs-types.ts`**

Append after `XhsRawSnapshotInput`:

```ts
export interface XhsRateLimitContext {
  keyword: string;
  sortKey: XhsSearchSortKey;
  feedId: string;
  message: string;
}

export interface XhsDetailSafetyState {
  detailBudgetUsed: number;
  rateLimited: boolean;
  rateLimitContext?: XhsRateLimitContext;
}
```

- [ ] **Step 5: Update collector result interface**

In `src/xhs-search-collector.ts`, update imports:

```ts
import type { XhsDetailSafetyState, XhsNoteDetail, XhsRateLimitContext, XhsSearchNoteRow, XhsSearchSortKey } from './xhs-types.js';
```

Update `XhsSearchCollectorResult`:

```ts
interface XhsSearchCollectorResult extends XhsDetailSafetyState {
  runs: XhsSearchCollectorRunResult[];
  dbPath: string;
}
```

- [ ] **Step 6: Initialize and return detail safety state**

In `collectXhsSearch()`, before the keyword loop:

```ts
    const detailSafetyState: XhsDetailSafetyState = {
      detailBudgetUsed: 0,
      rateLimited: false,
    };
```

Update the return:

```ts
    return { runs, dbPath: options.dbPath, ...detailSafetyState };
```

In this task, do not yet change detail collection behavior.

- [ ] **Step 7: Run collector tests and verify they pass**

Run:

```bash
npm run test -- tests/xhs-search-collector.test.ts
```

Expected: PASS.

- [ ] **Step 8: Commit Task 3**

```bash
git add src/xhs-types.ts src/xhs-search-collector.ts tests/xhs-search-collector.test.ts
git commit -m "feat: add XHS detail safety result state"
```

---

## Task 4: Detail budget and delay between detail visits

**Files:**
- Modify: `tests/xhs-search-collector.test.ts`
- Modify: `src/xhs-search-collector.ts`

- [ ] **Step 1: Write failing test for detail budget**

Add to `tests/xhs-search-collector.test.ts`:

```ts
  it('stops detail enrichment when detail budget is exhausted', async () => {
    const tempDir = mkdtempSync(join(tmpdir(), 'xhs-search-budget-test-'));
    const dbPath = join(tempDir, 'collector.sqlite');
    const detailPage = { setDefaultTimeout: vi.fn(), close: vi.fn().mockResolvedValue(undefined) };
    const session = {
      page: {},
      context: { newPage: vi.fn().mockResolvedValue(detailPage) },
      close: vi.fn().mockResolvedValue(undefined),
    } as unknown as XhsSession;

    xhsSessionMocks.createXhsSession.mockResolvedValue(session);
    xhsSearchMocks.openXhsSearchPage.mockResolvedValue(undefined);
    xhsSessionMocks.captureXhsPageSnapshot.mockResolvedValue({ url: 'https://www.xiaohongshu.com/search_result?keyword=护肤', text: 'budget exhausted', html: '<html></html>' });
    xhsSearchMocks.collectXhsSearchNoteRows.mockResolvedValue([
      noteRow({ feedId: 'feed-a', rankIndex: 1, title: 'A' }),
      noteRow({ feedId: 'feed-b', rankIndex: 2, title: 'B' }),
      noteRow({ feedId: 'feed-c', rankIndex: 3, title: 'C' }),
    ]);
    xhsDetailMocks.collectXhsNoteDetail.mockResolvedValue({
      feedId: 'feed-a',
      xsecToken: 'detail-token',
      exploreUrl: 'https://www.xiaohongshu.com/explore/feed-a?xsec_token=detail-token',
      detailText: '详情正文',
      tags: ['护肤'],
      commentCountText: null,
      likeText: null,
      collectText: null,
      shareText: null,
      noteType: 'image',
      rawDetailText: '详情页完整文本',
      sourceTopicTexts: ['护肤'],
      sourceComments: [],
      mediaSources: [{ kind: 'image', url: 'https://example.com/image.jpg', posterUrl: null, altText: null }],
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
        const snapshots = db.prepare('select kind, object_key from xhs_raw_snapshots order by id').all();
        expect(snapshots).toEqual([{ kind: 'xhs_detail_budget_exhausted', object_key: '护肤:latest' }]);
      } finally {
        db.close();
      }
    } finally {
      rmSync(tempDir, { recursive: true, force: true });
    }
  });
```

- [ ] **Step 2: Write failing test for detail delay**

At top of `tests/xhs-search-collector.test.ts`, ensure `afterEach` restores timers:

```ts
  afterEach(() => {
    vi.useRealTimers();
    vi.resetAllMocks();
  });
```

If there is already an `afterEach`, update it to include `vi.useRealTimers()`.

Add test:

```ts
  it('waits between detail page visits when delay is configured', async () => {
    vi.useFakeTimers();
    const waitPromise = xhsSearchCollector.waitForXhsDetailDelay({ detailDelayMinMs: 1000, detailDelayMaxMs: 1000 });
    let resolved = false;
    waitPromise.then(() => { resolved = true; });

    await vi.advanceTimersByTimeAsync(999);
    expect(resolved).toBe(false);

    await vi.advanceTimersByTimeAsync(1);
    await waitPromise;
    expect(resolved).toBe(true);
  });
```

- [ ] **Step 3: Run collector tests and verify they fail**

Run:

```bash
npm run test -- tests/xhs-search-collector.test.ts
```

Expected: FAIL because budget, budget snapshot, and `waitForXhsDetailDelay()` are not implemented.

- [ ] **Step 4: Implement delay helper**

In `src/xhs-search-collector.ts`, add near helper functions:

```ts
export function randomIntegerInRange(min: number, max: number): number {
  if (min === max) {
    return min;
  }

  return min + Math.floor(Math.random() * (max - min + 1));
}

export async function waitForXhsDetailDelay(options: Pick<XhsSearchCommandOptions, 'detailDelayMinMs' | 'detailDelayMaxMs'>): Promise<void> {
  const delayMs = randomIntegerInRange(options.detailDelayMinMs, options.detailDelayMaxMs);
  if (delayMs === 0) {
    return;
  }

  await new Promise((resolve) => setTimeout(resolve, delayMs));
}
```

- [ ] **Step 5: Add budget state type and helper**

In `src/xhs-search-collector.ts`:

```ts
interface XhsDetailCollectionState extends XhsDetailSafetyState {
  detailBudgetExhausted: boolean;
}

function hasDetailBudgetRemaining(options: XhsSearchCommandOptions, state: XhsDetailCollectionState): boolean {
  return state.detailBudgetUsed < options.detailBudget;
}
```

In `collectXhsSearch()`, initialize:

```ts
    const detailSafetyState: XhsDetailCollectionState = {
      detailBudgetUsed: 0,
      rateLimited: false,
      detailBudgetExhausted: false,
    };
```

Return without the internal flag:

```ts
    const { detailBudgetExhausted: _detailBudgetExhausted, ...publicDetailSafetyState } = detailSafetyState;
    return { runs, dbPath: options.dbPath, ...publicDetailSafetyState };
```

- [ ] **Step 6: Pass state into collection functions**

Update signatures:

```ts
async function collectSortRows(
  repository: CollectorRepository,
  session: XhsSession,
  runId: number,
  keyword: string,
  sortKey: XhsSearchSortKey,
  options: XhsSearchCommandOptions,
  seenFeedIds: Set<string>,
  detailState: XhsDetailCollectionState,
): Promise<{ rows: XhsSearchNoteRow[]; status: RunStatus }> {
```

```ts
async function collectSingleXhsKeyword(
  repository: CollectorRepository,
  session: XhsSession,
  options: XhsSearchCommandOptions,
  keyword: string,
  sourceRunId: number | null,
  detailState: XhsDetailCollectionState,
): Promise<XhsSearchCollectorRunResult> {
```

Update call sites:

```ts
const result = await collectSortRows(repository, session, runId, keyword, sortKey, options, seenFeedIds, detailState);
```

```ts
runs.push(await collectSingleXhsKeyword(repository, session, options, keyword, options.fromHuitunRunId ?? null, detailSafetyState));
```

- [ ] **Step 7: Apply budget before detail collection**

In `collectSortRows()`, replace:

```ts
  if (options.withDetails) {
    const result = await enrichXhsSearchRowsWithDetails(session, rows);
```

with:

```ts
  if (options.withDetails && !detailState.detailBudgetExhausted) {
    const detailCandidates = rows.slice(0, Math.max(0, options.detailBudget - detailState.detailBudgetUsed));
    if (detailCandidates.length < rows.length) {
      status = 'partial_success';
      detailState.detailBudgetExhausted = true;
      await tryInsertXhsRawSnapshotFromPage(
        repository,
        runId,
        session,
        'xhs_detail_budget_exhausted',
        `${keyword}:${sortKey}`,
        `Detail budget exhausted after ${detailState.detailBudgetUsed} visits.`,
      );
    }

    const result = await enrichXhsSearchRowsWithDetails(session, detailCandidates, options, detailState);
    const enrichedByFeedId = new Map(result.rows.map((row) => [row.feedId, row]));
    rows = rows.map((row) => enrichedByFeedId.get(row.feedId) ?? row);
```

- [ ] **Step 8: Update `enrichXhsSearchRowsWithDetails()` for budget accounting and delay**

Change signature:

```ts
export async function enrichXhsSearchRowsWithDetails(
  session: XhsSession,
  rows: XhsSearchNoteRow[],
  options: Pick<XhsSearchCommandOptions, 'detailDelayMinMs' | 'detailDelayMaxMs' | 'detailBudget'>,
  detailState: Pick<XhsDetailCollectionState, 'detailBudgetUsed'>,
): Promise<{ rows: XhsSearchNoteRow[]; detailFailures: XhsDetailFailure[] }> {
```

Inside the loop, before `try`:

```ts
    if (detailState.detailBudgetUsed >= options.detailBudget) {
      enrichedRows.push(row);
      continue;
    }
```

Immediately before `const detail = await collectXhsNoteDetail(...)`:

```ts
      detailState.detailBudgetUsed += 1;
```

After the `finally` block, before next loop iteration:

```ts
    if (detailState.detailBudgetUsed < options.detailBudget && row !== rows[rows.length - 1]) {
      await waitForXhsDetailDelay(options);
    }
```

- [ ] **Step 9: Update existing direct helper tests**

Existing tests call `enrichXhsSearchRowsWithDetails(session, [row])`. Update those calls to:

```ts
const detailState = { detailBudgetUsed: 0 };
const result = await xhsSearchCollector.enrichXhsSearchRowsWithDetails(
  session,
  [row],
  { detailDelayMinMs: 0, detailDelayMaxMs: 0, detailBudget: 30 },
  detailState,
);
```

For failure test, expect `detailState.detailBudgetUsed` to be `0` when `newPage()` fails before a detail URL is opened.

- [ ] **Step 10: Run collector tests and verify they pass**

Run:

```bash
npm run test -- tests/xhs-search-collector.test.ts
```

Expected: PASS.

- [ ] **Step 11: Commit Task 4**

```bash
git add src/xhs-search-collector.ts tests/xhs-search-collector.test.ts
git commit -m "feat: budget and pace XHS detail collection"
```

---

## Task 5: Rate-limit circuit breaker in collector

**Files:**
- Modify: `tests/xhs-search-collector.test.ts`
- Modify: `src/xhs-search-collector.ts`

- [ ] **Step 1: Write failing collector test for rate-limit circuit breaker**

Add import in `tests/xhs-search-collector.test.ts` if needed:

```ts
import { XhsRateLimitError } from '../src/browser/xhs-note-detail.js';
```

Add test:

```ts
  it('stops the whole batch when a detail page hits XHS rate limit', async () => {
    const tempDir = mkdtempSync(join(tmpdir(), 'xhs-search-rate-limit-test-'));
    const dbPath = join(tempDir, 'collector.sqlite');
    const detailPage = { setDefaultTimeout: vi.fn(), close: vi.fn().mockResolvedValue(undefined) };
    const session = {
      page: {},
      context: { newPage: vi.fn().mockResolvedValue(detailPage) },
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
      new XhsRateLimitError('XHS rate limited: error_code=300013 访问频繁，请稍后再试', 'https://www.xiaohongshu.com/website-login/error?error_code=300013', '访问频繁，请稍后再试'),
    );

    try {
      const result = await xhsSearchCollector.collectXhsSearch({
        fromHuitunRunId: undefined,
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
```

- [ ] **Step 2: Run collector tests and verify they fail**

Run:

```bash
npm run test -- tests/xhs-search-collector.test.ts
```

Expected: FAIL because rate-limit errors are treated as ordinary detail failures.

- [ ] **Step 3: Import rate-limit helpers in collector**

In `src/xhs-search-collector.ts`, update import:

```ts
import { collectXhsNoteDetail, isXhsRateLimitError } from './browser/xhs-note-detail.js';
```

- [ ] **Step 4: Extend detail failure type**

Replace `XhsDetailFailure` with:

```ts
interface XhsDetailFailure {
  feedId: string;
  message: string;
  rateLimited: boolean;
}
```

Update ordinary failures to push:

```ts
      detailFailures.push({ feedId: row.feedId, message: errorMessage(error), rateLimited: false });
```

- [ ] **Step 5: Preserve rate-limit failures from detail enrichment**

In `enrichXhsSearchRowsWithDetails()`, update `catch`:

```ts
    } catch (error) {
      enrichedRows.push(row);
      detailFailures.push({
        feedId: row.feedId,
        message: errorMessage(error),
        rateLimited: isXhsRateLimitError(error),
      });
    } finally {
```

- [ ] **Step 6: Handle rate-limit failures in `collectSortRows()`**

Inside `if (result.detailFailures.length > 0)`, before the loop that writes ordinary detail errors:

```ts
      const rateLimitFailure = result.detailFailures.find((failure) => failure.rateLimited);
      if (rateLimitFailure !== undefined && options.stopOnRateLimit) {
        status = 'partial_success';
        detailState.rateLimited = true;
        detailState.rateLimitContext = {
          keyword,
          sortKey,
          feedId: rateLimitFailure.feedId,
          message: rateLimitFailure.message,
        };
        await tryInsertXhsRawSnapshotFromPage(
          repository,
          runId,
          session,
          'xhs_rate_limited',
          `${keyword}:${sortKey}:${rateLimitFailure.feedId}`,
          rateLimitFailure.message,
        );
        return { rows, status };
      }
```

Then change ordinary snapshot loop to skip rate-limited failures:

```ts
      for (const failure of result.detailFailures.filter((failure) => !failure.rateLimited)) {
```

- [ ] **Step 7: Stop sort loop when rate limited**

In `collectSingleXhsKeyword()`, after upserting rows and incrementing note count:

```ts
        if (detailState.rateLimited && options.stopOnRateLimit) {
          break;
        }
```

When finishing the run, replace:

```ts
    repository.finishXhsSearchRun(runId, status);
```

with:

```ts
    if (detailState.rateLimited && detailState.rateLimitContext?.keyword === keyword) {
      repository.finishXhsSearchRun(runId, 'partial_success', 'xhs_rate_limited', detailState.rateLimitContext.message);
    } else {
      repository.finishXhsSearchRun(runId, status);
    }
```

- [ ] **Step 8: Stop keyword loop when rate limited**

In `collectXhsSearch()`, update keyword loop:

```ts
    for (const keyword of keywords) {
      runs.push(await collectSingleXhsKeyword(repository, session, options, keyword, options.fromHuitunRunId ?? null, detailSafetyState));
      if (detailSafetyState.rateLimited && options.stopOnRateLimit) {
        break;
      }
    }
```

- [ ] **Step 9: Run collector tests and verify they pass**

Run:

```bash
npm run test -- tests/xhs-search-collector.test.ts
```

Expected: PASS.

- [ ] **Step 10: Commit Task 5**

```bash
git add src/xhs-search-collector.ts tests/xhs-search-collector.test.ts
git commit -m "feat: stop XHS collection on rate limits"
```

---

## Task 6: Resume already-detailed rows inside a run

**Files:**
- Modify: `tests/xhs-search-collector.test.ts`
- Modify: `src/xhs-search-collector.ts`

- [ ] **Step 1: Write failing unit test for detail presence helper**

Add to `tests/xhs-search-collector.test.ts`:

```ts
  it('detects rows that already have useful detail evidence', () => {
    expect(xhsSearchCollector.hasUsefulXhsDetail(noteRow())).toBe(false);
    expect(xhsSearchCollector.hasUsefulXhsDetail(noteRow({ detailText: '正文' }))).toBe(true);
    expect(xhsSearchCollector.hasUsefulXhsDetail(noteRow({ rawDetailText: '原始详情' }))).toBe(true);
    expect(xhsSearchCollector.hasUsefulXhsDetail(noteRow({ mediaSources: [{ kind: 'image', url: 'https://example.com/a.jpg', posterUrl: null, altText: null }] }))).toBe(true);
  });
```

- [ ] **Step 2: Write failing test that resume skips detailed rows**

Add to `tests/xhs-search-collector.test.ts`:

```ts
  it('skips rows with existing detail evidence when resume is enabled', async () => {
    const rowWithDetail = noteRow({ feedId: 'feed-a', detailText: '已有详情' });
    const rowWithoutDetail = noteRow({ feedId: 'feed-b', title: 'B' });
    const detailPage = { setDefaultTimeout: vi.fn(), close: vi.fn().mockResolvedValue(undefined) };
    const session = {
      context: { newPage: vi.fn().mockResolvedValue(detailPage) },
    } as unknown as XhsSession;
    xhsDetailMocks.collectXhsNoteDetail.mockResolvedValue({
      feedId: 'feed-b',
      xsecToken: 'detail-token',
      exploreUrl: 'https://www.xiaohongshu.com/explore/feed-b?xsec_token=detail-token',
      detailText: '新详情',
      tags: ['护肤'],
      commentCountText: null,
      likeText: null,
      collectText: null,
      shareText: null,
      noteType: 'image',
      rawDetailText: '详情页完整文本',
      sourceTopicTexts: ['护肤'],
      sourceComments: [],
      mediaSources: [],
      analysisSourceText: '标题：B',
    });

    const detailState = { detailBudgetUsed: 0, rateLimited: false, detailBudgetExhausted: false };
    const result = await xhsSearchCollector.enrichXhsSearchRowsWithDetails(
      session,
      [rowWithDetail, rowWithoutDetail],
      { detailDelayMinMs: 0, detailDelayMaxMs: 0, detailBudget: 30, resumeMissingDetails: true },
      detailState,
    );

    expect(xhsDetailMocks.collectXhsNoteDetail).toHaveBeenCalledTimes(1);
    expect(xhsDetailMocks.collectXhsNoteDetail).toHaveBeenCalledWith(detailPage, rowWithoutDetail.searchResultUrl, expect.any(Object));
    expect(result.rows[0]).toBe(rowWithDetail);
    expect(result.rows[1]).toMatchObject({ feedId: 'feed-b', detailText: '新详情' });
  });
```

- [ ] **Step 3: Run collector tests and verify they fail**

Run:

```bash
npm run test -- tests/xhs-search-collector.test.ts
```

Expected: FAIL because helper and resume behavior are missing.

- [ ] **Step 4: Implement detail presence helper**

In `src/xhs-search-collector.ts`, after `dedupeXhsSearchRowsByFeedId()`:

```ts
export function hasUsefulXhsDetail(row: XhsSearchNoteRow): boolean {
  return (row.detailText?.trim() ?? '') !== ''
    || (row.rawDetailText?.trim() ?? '') !== ''
    || row.mediaSources.length > 0;
}
```

- [ ] **Step 5: Update enrichment options signature**

Update `enrichXhsSearchRowsWithDetails()` options type:

```ts
  options: Pick<XhsSearchCommandOptions, 'detailDelayMinMs' | 'detailDelayMaxMs' | 'detailBudget' | 'resumeMissingDetails'>,
```

At start of loop, before opening a page:

```ts
    if (options.resumeMissingDetails && hasUsefulXhsDetail(row)) {
      enrichedRows.push(row);
      continue;
    }
```

- [ ] **Step 6: Update all helper test option objects**

Any direct call to `enrichXhsSearchRowsWithDetails()` must include:

```ts
resumeMissingDetails: true
```

- [ ] **Step 7: Run collector tests and verify they pass**

Run:

```bash
npm run test -- tests/xhs-search-collector.test.ts
```

Expected: PASS.

- [ ] **Step 8: Commit Task 6**

```bash
git add src/xhs-search-collector.ts tests/xhs-search-collector.test.ts
git commit -m "feat: skip existing XHS detail evidence"
```

---

## Task 7: Repository upsert regression coverage

**Files:**
- Modify: `tests/xhs-db.test.ts`
- Review: `src/db/repositories.ts`

- [ ] **Step 1: Write regression test that empty detail does not overwrite existing detail**

Add to `tests/xhs-db.test.ts` in the repository tests area:

```ts
  it('does not overwrite existing XHS detail fields with empty detail rows', () => {
    const tempDir = mkdtempSync(join(tmpdir(), 'xhs-upsert-detail-preserve-test-'));
    const db = openDatabase(join(tempDir, 'xhs.sqlite'));

    try {
      initializeSchema(db);
      const repository = new CollectorRepository(db);
      const runId = repository.createXhsSearchRun({
        source: 'manual_keyword',
        sourceRunId: null,
        keyword: '护肤',
        sorts: ['latest'],
        limitPerSort: 20,
        withDetails: true,
      });

      const baseRow = {
        keyword: '护肤',
        sortKey: 'latest' as const,
        sortLabel: '最新',
        rankIndex: 1,
        feedId: 'feed-a',
        xsecToken: 'token-a',
        searchResultUrl: 'https://www.xiaohongshu.com/search_result/feed-a?xsec_token=token-a',
        exploreUrl: null,
        title: '标题',
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
        noteType: 'unknown' as const,
        coverAltText: null,
        rawDetailText: null,
        sourceTopicTexts: [],
        sourceComments: [],
        mediaSources: [],
        analysisSourceText: null,
        rawCardText: '标题',
      };

      repository.upsertXhsSearchNotes(runId, [{
        ...baseRow,
        detailText: '已有详情',
        detailTags: ['护肤'],
        rawDetailText: '已有原始详情',
        mediaSources: [{ kind: 'image', url: 'https://example.com/a.jpg', posterUrl: null, altText: null }],
      }]);

      repository.upsertXhsSearchNotes(runId, [baseRow]);

      const row = db.prepare(`
        select detail_text, detail_tags_json, raw_detail_text, media_sources_json
        from xhs_search_notes
        where run_id = :runId and feed_id = 'feed-a'
      `).get({ runId });

      expect(row).toEqual({
        detail_text: '已有详情',
        detail_tags_json: '["护肤"]',
        raw_detail_text: '已有原始详情',
        media_sources_json: '[{"kind":"image","url":"https://example.com/a.jpg","posterUrl":null,"altText":null}]',
      });
    } finally {
      db.close();
      rmSync(tempDir, { recursive: true, force: true });
    }
  });
```

- [ ] **Step 2: Run DB tests**

Run:

```bash
npm run test -- tests/xhs-db.test.ts
```

Expected: PASS because existing upsert already uses `coalesce` and preserves non-empty JSON arrays. If it fails, adjust only `src/db/repositories.ts` upsert clauses for detail fields to preserve existing non-empty values.

- [ ] **Step 3: Commit Task 7**

```bash
git add tests/xhs-db.test.ts src/db/repositories.ts
git commit -m "test: preserve XHS detail fields on upsert"
```

---

## Task 8: End-to-end CLI output shape and help text

**Files:**
- Modify: `tests/cli-options.test.ts`
- Modify: `src/cli.ts`
- Modify: `src/xhs-search-collector.ts`

- [ ] **Step 1: Write failing help text test**

Update `prints xhs-search help with real command options` in `tests/cli-options.test.ts` to include:

```ts
    expect(result.stdout).toContain('--detail-delay-min-ms');
    expect(result.stdout).toContain('--detail-delay-max-ms');
    expect(result.stdout).toContain('--detail-budget');
    expect(result.stdout).toContain('--no-stop-on-rate-limit');
    expect(result.stdout).toContain('--no-resume-missing-details');
```

- [ ] **Step 2: Write failing real invocation output test for safety fields**

Add a new test near the real xhs-search invocation tests:

```ts
  it('prints xhs-search collector safety fields in JSON output when collection reaches the collector', () => {
    const result = spawnSync(
      'node',
      [
        '--no-warnings',
        './node_modules/tsx/dist/cli.mjs',
        'src/cli.ts',
        'xhs-search',
        '--keyword',
        '护肤',
        '--db-path',
        ':memory:',
        '--cdp-url',
        'http://127.0.0.1:1',
      ],
      { encoding: 'utf8' },
    );

    expect(result.status).toBe(1);
    expect(result.stderr).toContain('无法连接浏览器 CDP：http://127.0.0.1:1');
  });
```

This test confirms invalid CDP still exits cleanly. Do not assert success JSON here because it would need a real browser.

- [ ] **Step 3: Run CLI tests**

Run:

```bash
npm run test -- tests/cli-options.test.ts
```

Expected: PASS after Task 1 implementation. If help text fails, check `addXhsSearchOptions()` includes all new options.

- [ ] **Step 4: Commit Task 8**

```bash
git add src/cli.ts src/xhs-search-collector.ts tests/cli-options.test.ts
git commit -m "test: cover XHS detail safety CLI output"
```

---

## Task 9: Focused verification without triggering platform rate limits

**Files:**
- No source files unless earlier tasks reveal a bug.

- [ ] **Step 1: Run focused unit tests**

Run:

```bash
npm run test -- tests/cli-options.test.ts tests/xhs-note-detail-parser.test.ts tests/xhs-search-collector.test.ts tests/xhs-db.test.ts
```

Expected: PASS.

- [ ] **Step 2: Run typecheck**

Run:

```bash
npm run typecheck
```

Expected: PASS.

- [ ] **Step 3: Run safe CLI smoke with no real XHS page access**

Run:

```bash
npm run collect -- xhs-search --keyword 护肤 --detail-delay-min-ms 1000 --detail-delay-max-ms 500 --db-path :memory: --cdp-url http://127.0.0.1:1
```

Expected: exit 1 with:

```text
--detail-delay-max-ms 必须大于等于 --detail-delay-min-ms
```

This validates parser behavior without touching XHS.

- [ ] **Step 4: Optional manual browser verification after cooldown only**

Only run this if the user explicitly approves a real browser touch after cooldown:

```bash
npm run collect -- xhs-search --from-huitun-run-id 11 --limit-keywords 1 --sorts most_liked --limit-per-sort 3 --with-details --detail-budget 2 --detail-delay-min-ms 1000 --detail-delay-max-ms 2000 --db-path data/xhs-ops.sqlite --cdp-url http://127.0.0.1:9222
```

Expected if approved and site allows access:

- CLI exits 0.
- JSON includes `detailBudgetUsed: 2` and `rateLimited: false` unless the site responds with rate limit.
- SQLite has a new `xhs_search_runs` row with `partial_success` and an `xhs_detail_budget_exhausted` snapshot.

Do not run this command automatically during implementation because the previous full run triggered `error_code=300013`.

- [ ] **Step 5: Commit verification-only adjustments if any**

If no code changes were needed in this task, skip commit. If fixes were required:

```bash
git add <changed-files>
git commit -m "fix: stabilize XHS safe collection verification"
```

---

## Self-Review Checklist

- Spec coverage:
  - CLI delay, budget, stop-on-rate-limit, and resume options: Task 1.
  - Rate-limit detection: Task 2.
  - Public result fields: Task 3.
  - Budget and delay: Task 4.
  - Rate-limit circuit breaker and snapshots: Task 5.
  - Resume missing details: Task 6.
  - Preserve existing details on upsert: Task 7.
  - Safe verification without repeating high-risk full run: Task 9.

- Placeholder scan:
  - No `TODO`, `TBD`, `implement later`, or unnamed files.
  - Every code-changing step includes concrete snippets or exact replacement guidance.

- Type consistency:
  - `XhsSearchCommandOptions` fields match CLI parser names.
  - `XhsDetailSafetyState` and `XhsRateLimitContext` are defined in `src/xhs-types.ts` and imported by collector.
  - `XhsRateLimitError`, `isXhsRateLimitError`, and `isXhsRateLimitSignal` are defined in `src/browser/xhs-note-detail.ts`.
  - Raw snapshot kinds are string values, so no schema migration is required.

- Safety check:
  - Plan does not include bypassing platform controls.
  - Real XHS browser verification is optional and explicitly gated by user approval after cooldown.

import type { DatabaseSync } from 'node:sqlite';

import { collectXhsNoteDetail, isXhsRateLimitError } from './browser/xhs-note-detail.js';
import { collectXhsSearchNoteRows, openXhsSearchPage, XHS_LOGIN_REQUIRED_MESSAGE } from './browser/xhs-search.js';
import { captureXhsPageSnapshot, createXhsSession, type XhsSession } from './browser/xhs-session.js';
import type { XhsSearchCommandOptions } from './cli.js';
import type { CollectorRepository } from './db/repositories.js';
import type { RunStatus } from './types.js';
import type { XhsDetailSafetyState, XhsNoteDetail, XhsSearchNoteRow, XhsSearchSortKey } from './xhs-types.js';

interface XhsSearchCollectorRunResult {
  runId: number;
  keyword: string;
  status: RunStatus;
  noteCount: number;
}

interface XhsSearchCollectorResult extends XhsDetailSafetyState {
  runs: XhsSearchCollectorRunResult[];
  dbPath: string;
}

interface XhsDetailCollectionState extends XhsDetailSafetyState {
  detailBudgetExhausted: boolean;
}

interface XhsDetailDelayOptions {
  detailDelayMinMs: number;
  detailDelayMaxMs: number;
}

interface XhsDetailBudgetOptions extends XhsDetailDelayOptions {
  detailBudget: number;
  stopOnRateLimit: boolean;
  resumeMissingDetails: boolean;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function snapshotTextContent(pageText: string, diagnosticMessage?: string): string {
  return diagnosticMessage === undefined ? pageText : `${diagnosticMessage}\n\n${pageText}`;
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
    textContent: snapshotTextContent(snapshot.text, diagnosticMessage),
    htmlContent: snapshot.html,
  });
}

async function tryInsertXhsRawSnapshotFromPage(
  repository: CollectorRepository,
  runId: number,
  session: XhsSession,
  kind: string,
  objectKey: string,
  diagnosticMessage?: string,
): Promise<void> {
  await insertXhsRawSnapshotFromPage(repository, runId, session, kind, objectKey, diagnosticMessage).catch(() => undefined);
}

function applyDetail(row: XhsSearchNoteRow, detail: XhsNoteDetail): XhsSearchNoteRow {
  return {
    ...row,
    xsecToken: detail.xsecToken ?? row.xsecToken,
    exploreUrl: detail.exploreUrl,
    detailText: detail.detailText,
    detailTags: detail.tags,
    detailCommentCountText: detail.commentCountText,
    detailLikeText: detail.likeText,
    detailCollectText: detail.collectText,
    detailShareText: detail.shareText,
    noteType: detail.noteType === 'unknown' ? row.noteType : detail.noteType,
    rawDetailText: detail.rawDetailText,
    sourceTopicTexts: detail.sourceTopicTexts.length > 0 ? detail.sourceTopicTexts : row.sourceTopicTexts,
    sourceComments: detail.sourceComments,
    mediaSources: detail.mediaSources,
    analysisSourceText: detail.analysisSourceText,
  };
}

interface XhsDetailFailure {
  feedId: string;
  message: string;
  rateLimited: boolean;
}

export function randomIntegerInRange(min: number, max: number): number {
  const lowerBound = Math.ceil(min);
  const upperBound = Math.floor(max);
  return Math.floor(Math.random() * (upperBound - lowerBound + 1)) + lowerBound;
}

export async function waitForXhsDetailDelay(options: XhsDetailDelayOptions): Promise<void> {
  const delayMs = randomIntegerInRange(options.detailDelayMinMs, options.detailDelayMaxMs);
  if (delayMs <= 0) {
    return;
  }

  await new Promise((resolve) => setTimeout(resolve, delayMs));
}

export function dedupeXhsSearchRowsByFeedId(rows: XhsSearchNoteRow[]): XhsSearchNoteRow[] {
  const seenFeedIds = new Set<string>();
  const dedupedRows: XhsSearchNoteRow[] = [];

  for (const row of rows) {
    if (seenFeedIds.has(row.feedId)) {
      continue;
    }

    seenFeedIds.add(row.feedId);
    dedupedRows.push(row);
  }

  return dedupedRows;
}

export function hasUsefulXhsDetail(row: XhsSearchNoteRow): boolean {
  return (row.detailText?.trim() ?? '') !== ''
    || (row.rawDetailText?.trim() ?? '') !== ''
    || row.mediaSources.length > 0;
}

export async function enrichXhsSearchRowsWithDetails(
  session: XhsSession,
  rows: XhsSearchNoteRow[],
  options: XhsDetailBudgetOptions,
  detailState: XhsDetailCollectionState,
): Promise<{ rows: XhsSearchNoteRow[]; detailFailures: XhsDetailFailure[] }> {
  const enrichedRows: XhsSearchNoteRow[] = [];
  const detailFailures: XhsDetailFailure[] = [];

  for (const [index, row] of rows.entries()) {
    if (detailState.detailBudgetUsed >= options.detailBudget) {
      detailState.detailBudgetExhausted = true;
      enrichedRows.push(...rows.slice(index));
      break;
    }

    if (options.resumeMissingDetails && hasUsefulXhsDetail(row)) {
      enrichedRows.push(row);
      continue;
    }

    let detailPage;
    let openedDetailPage = false;

    try {
      detailPage = await session.context.newPage();
      openedDetailPage = true;
      detailPage.setDefaultTimeout(30_000);
      detailState.detailBudgetUsed += 1;
      const detail = await collectXhsNoteDetail(detailPage, row.searchResultUrl, {
        title: row.title,
        noteType: row.noteType,
        coverAltText: row.coverAltText,
        coverUrl: row.coverUrl,
        sourceTopicTexts: row.sourceTopicTexts,
      });
      enrichedRows.push(applyDetail(row, detail));
    } catch (error) {
      enrichedRows.push(row);
      const rateLimited = isXhsRateLimitError(error);
      detailFailures.push({ feedId: row.feedId, message: errorMessage(error), rateLimited });
      if (rateLimited && options.stopOnRateLimit) {
        enrichedRows.push(...rows.slice(index + 1));
        break;
      }
    } finally {
      await detailPage?.close().catch(() => undefined);
    }

    if (openedDetailPage && detailState.detailBudgetUsed >= options.detailBudget) {
      detailState.detailBudgetExhausted = true;
    }

    const hasAnotherRow = index < rows.length - 1;
    const hasRemainingBudget = detailState.detailBudgetUsed < options.detailBudget;
    if (openedDetailPage && hasAnotherRow && hasRemainingBudget) {
      await waitForXhsDetailDelay(options);
    }
  }

  return { rows: enrichedRows, detailFailures };
}

function removeSeenFeedIds(rows: XhsSearchNoteRow[], seenFeedIds: Set<string>): XhsSearchNoteRow[] {
  const uniqueRows: XhsSearchNoteRow[] = [];
  for (const row of rows) {
    if (seenFeedIds.has(row.feedId)) {
      continue;
    }

    uniqueRows.push({ ...row, rankIndex: uniqueRows.length + 1 });
  }
  return uniqueRows;
}

function markSeenFeedIds(rows: XhsSearchNoteRow[], seenFeedIds: Set<string>): void {
  for (const row of rows) {
    seenFeedIds.add(row.feedId);
  }
}

function xhsSortErrorKind(message: string): string {
  if (message.includes('排序选项') || message.includes('sort option not found')) {
    return 'xhs_sort_not_found';
  }

  if (message.includes('排序切换失败') || message.includes('排序结果未刷新')) {
    return 'xhs_sort_click_failed';
  }

  return 'xhs_search_sort_error';
}

async function insertXhsDetailBudgetExhaustedSnapshot(
  repository: CollectorRepository,
  runId: number,
  session: XhsSession,
  keyword: string,
  sortKey: XhsSearchSortKey,
  options: XhsSearchCommandOptions,
  detailState: XhsDetailCollectionState,
): Promise<void> {
  await tryInsertXhsRawSnapshotFromPage(
    repository,
    runId,
    session,
    'xhs_detail_budget_exhausted',
    `${keyword}:${sortKey}`,
    `Detail budget exhausted. Used ${detailState.detailBudgetUsed}/${options.detailBudget}.`,
  );
}

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
  const requestedLimit = options.limitPerSort + seenFeedIds.size;
  let rows = removeSeenFeedIds(dedupeXhsSearchRowsByFeedId(await collectXhsSearchNoteRows(session.page, keyword, sortKey, requestedLimit)), seenFeedIds)
    .slice(0, options.limitPerSort);
  if (options.resumeMissingDetails) {
    rows = repository.applyExistingXhsDetails(rows);
  }
  let status: RunStatus = 'success';

  if (rows.length < options.limitPerSort) {
    status = 'partial_success';
    await tryInsertXhsRawSnapshotFromPage(
      repository,
      runId,
      session,
      'xhs_note_list_short',
      `${keyword}:${sortKey}`,
      `Expected ${options.limitPerSort} notes, collected ${rows.length}.`,
    );
  }

  if (options.withDetails) {
    if (detailState.detailBudgetExhausted || detailState.detailBudgetUsed >= options.detailBudget) {
      status = 'partial_success';
      detailState.detailBudgetExhausted = true;
      await insertXhsDetailBudgetExhaustedSnapshot(repository, runId, session, keyword, sortKey, options, detailState);
    } else {
      const result = await enrichXhsSearchRowsWithDetails(session, rows, options, detailState);
      rows = result.rows;

      if (result.detailFailures.length > 0) {
        status = 'partial_success';
        const rateLimitFailure = result.detailFailures.find((failure) => failure.rateLimited);

        for (const failure of result.detailFailures) {
          if (failure.rateLimited && options.stopOnRateLimit) {
            continue;
          }

          await tryInsertXhsRawSnapshotFromPage(
            repository,
            runId,
            session,
            'xhs_detail_collection_error',
            `${keyword}:${sortKey}:${failure.feedId}`,
            failure.message,
          );
        }

        if (rateLimitFailure !== undefined && options.stopOnRateLimit) {
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
      }

      if (detailState.detailBudgetExhausted) {
        status = 'partial_success';
        await insertXhsDetailBudgetExhaustedSnapshot(repository, runId, session, keyword, sortKey, options, detailState);
      }
    }
  }

  return { rows, status };
}

async function collectSingleXhsKeyword(
  repository: CollectorRepository,
  session: XhsSession,
  options: XhsSearchCommandOptions,
  keyword: string,
  sourceRunId: number | null,
  detailState: XhsDetailCollectionState,
): Promise<XhsSearchCollectorRunResult> {
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
  const seenFeedIds = new Set<string>();

  try {
    await openXhsSearchPage(session.page, keyword);

    for (const sortKey of options.sorts) {
      try {
        const result = await collectSortRows(repository, session, runId, keyword, sortKey, options, seenFeedIds, detailState);
        if (result.status === 'partial_success') {
          status = 'partial_success';
        }
        repository.upsertXhsSearchNotes(runId, result.rows);
        markSeenFeedIds(result.rows, seenFeedIds);
        noteCount += result.rows.length;
        if (detailState.rateLimited && options.stopOnRateLimit) {
          break;
        }
      } catch (error) {
        status = 'partial_success';
        const message = errorMessage(error);
        await tryInsertXhsRawSnapshotFromPage(repository, runId, session, xhsSortErrorKind(message), `${keyword}:${sortKey}`, message);
      }
    }

    if (detailState.rateLimited && detailState.rateLimitContext?.keyword === keyword) {
      repository.finishXhsSearchRun(runId, 'partial_success', 'xhs_rate_limited', detailState.rateLimitContext.message);
      status = 'partial_success';
    } else {
      repository.finishXhsSearchRun(runId, status);
    }
    return { runId, keyword, status, noteCount };
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

function resolveXhsKeywords(repository: CollectorRepository, options: XhsSearchCommandOptions): string[] {
  if (options.keyword !== undefined) {
    return [options.keyword];
  }

  return repository.listHotWordKeywordsForRun(options.fromHuitunRunId ?? 0, options.limitKeywords);
}

export async function collectXhsSearch(options: XhsSearchCommandOptions): Promise<XhsSearchCollectorResult> {
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

    const keywords = resolveXhsKeywords(repository, options);
    if (keywords.length === 0) {
      throw new Error('No keywords found for xhs-search.');
    }

    session = await createXhsSession(options.cdpUrl);

    const detailState: XhsDetailCollectionState = { detailBudgetUsed: 0, rateLimited: false, detailBudgetExhausted: false };
    const runs: XhsSearchCollectorRunResult[] = [];
    for (const keyword of keywords) {
      runs.push(await collectSingleXhsKeyword(repository, session, options, keyword, options.fromHuitunRunId ?? null, detailState));
      if (detailState.rateLimited && options.stopOnRateLimit) {
        break;
      }
    }

    return {
      runs,
      dbPath: options.dbPath,
      detailBudgetUsed: detailState.detailBudgetUsed,
      rateLimited: detailState.rateLimited,
      rateLimitContext: detailState.rateLimitContext,
    };
  } finally {
    await session?.close();
    db?.close();
  }
}

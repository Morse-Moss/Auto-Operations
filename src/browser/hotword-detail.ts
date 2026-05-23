import type { Locator, Page } from 'playwright-core';
import { effectiveNoteLimit, type LikesSortVerification, verifyLikesDescending } from '../collection-quality.js';
import type { HotWordSnapshot, NoteListRow } from '../types.js';
import { parseHuitunNumber } from '../utils/number.js';
import { assertHuitunLoggedIn } from './huitun-session.js';

const DETAIL_URL = 'https://xhs.huitun.com/#/hotWords/hot_word_detail';
const OVERVIEW_LABELS = [
  '热度值',
  '关联笔记数',
  '互动总量',
  '平均互动量',
  '平均点赞',
  '平均收藏',
  '平均评论',
  '平均分享',
];

export interface NoteDomPayload {
  key: string;
  title: string;
  authorName: string | null;
  authorLevel: string | null;
  coverUrl: string | null;
  duration: string | null;
  updatedText: string | null;
  tags: string[];
  cells: string[];
  headers?: string[];
}

export interface NoteListCollectionResult {
  rows: NoteListRow[];
  likesSort: LikesSortVerification;
}

function textOrNull(value: string | null | undefined): string | null {
  const trimmed = value?.trim() ?? '';
  return trimmed ? trimmed : null;
}

async function locatorTextOrNull(locator: Locator): Promise<string | null> {
  if ((await locator.count()) === 0) return null;
  return textOrNull(await locator.first().textContent());
}

async function locatorAllTrimmedText(locator: Locator): Promise<string[]> {
  return (await locator.allTextContents()).map((value) => value.trim());
}

async function collectImageSrcs(row: Locator): Promise<string[]> {
  const imageLocator = row.locator('img');
  const imageCount = await imageLocator.count();
  const srcs: string[] = [];

  for (let imageIndex = 0; imageIndex < imageCount; imageIndex += 1) {
    const src = await imageLocator.nth(imageIndex).getAttribute('src');
    if (src) srcs.push(src);
  }

  return srcs;
}

function stripLabel(value: string | null | undefined, label: string): string | null {
  const trimmed = textOrNull(value);
  if (!trimmed) return null;
  return textOrNull(trimmed.startsWith(label) ? trimmed.slice(label.length) : trimmed);
}

function normalizeHeader(value: string): string {
  return value.replace(/\s+/g, '');
}

function metricCell(payload: NoteDomPayload, labels: string[], fallbackIndex: number): string | null {
  const headers = payload.headers?.map(normalizeHeader) ?? [];
  const headerIndex = headers.findIndex((header) => labels.some((label) => header.includes(label)));
  const cell = payload.cells[headerIndex >= 0 ? headerIndex : fallbackIndex];
  return cell ?? null;
}

export function parseNoteRowsFromDomPayload(hotWord: string, payloads: NoteDomPayload[]): NoteListRow[] {
  return payloads.map((payload) => {
    const videoDuration = textOrNull(payload.duration);

    return {
      hotWord: hotWord.trim(),
      huitunNoteKey: payload.key,
      title: payload.title.trim(),
      authorName: textOrNull(payload.authorName),
      authorLevel: textOrNull(payload.authorLevel),
      coverUrl: textOrNull(payload.coverUrl),
      isVideo: videoDuration !== null,
      videoDuration,
      publishedAt: textOrNull(metricCell(payload, ['发布时间'], 1)),
      updatedAt: stripLabel(payload.updatedText, '更新时间：'),
      tags: payload.tags.map((tag) => tag.trim()).filter((tag) => tag && tag !== '更多...'),
      estimatedReads: parseHuitunNumber(metricCell(payload, ['预估阅读量', '阅读量'], 2)),
      likes: parseHuitunNumber(metricCell(payload, ['点赞'], 3)),
      collects: parseHuitunNumber(metricCell(payload, ['收藏'], 4)),
      comments: parseHuitunNumber(metricCell(payload, ['评论'], 5)),
    };
  });
}

function dateRangeForDays(days: number): { startDate: string; endDate: string } {
  const end = new Date();
  const start = new Date(end);
  start.setDate(end.getDate() - days);
  const format = (date: Date): string => date.toISOString().slice(0, 10);
  return { startDate: format(start), endDate: format(end) };
}

function detailUrl(hotWord: string, days?: number): string {
  const baseUrl = `${DETAIL_URL}?hotWord=${encodeURIComponent(hotWord)}`;
  if (days === undefined) return baseUrl;

  const { startDate, endDate } = dateRangeForDays(days);
  return `${baseUrl}&startDate=${startDate}&endDate=${endDate}`;
}

export async function openHotWordDetail(page: Page, hotWord: string, days?: number): Promise<void> {
  await page.goto(detailUrl(hotWord, days), { waitUntil: 'domcontentloaded' });
  await assertHuitunLoggedIn(page);

  try {
    await page.waitForLoadState('networkidle', { timeout: 30_000 });
  } catch {
    // Best-effort: Huitun pages can keep background requests open.
  }

  await assertHuitunLoggedIn(page);

  await page.waitForSelector('tr.ant-table-row', { timeout: 30_000 });
}

export async function collectHotWordSnapshot(page: Page, hotWord: string, days: number): Promise<HotWordSnapshot> {
  const text = await page.locator('body').innerText();
  const lines = text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
  const overview: Record<string, string> = {};

  for (let index = 0; index < lines.length - 1; index += 1) {
    const value = lines[index];
    const label = lines[index + 1];
    if (OVERVIEW_LABELS.includes(label)) {
      overview[label] = value;
    }
  }

  return {
    word: hotWord,
    days,
    pageUrl: page.url(),
    heatText: overview['热度值'] ?? null,
    relatedNotesText: overview['关联笔记数'] ?? null,
    totalInteractionsText: overview['互动总量'] ?? null,
    overview,
  };
}

async function waitForNoteTableSettled(page: Page): Promise<void> {
  const deadline = Date.now() + 30_000;

  while (Date.now() < deadline) {
    const spinner = page.locator('.ant-spin-spinning');
    const spinnerCount = await spinner.count().catch(() => 0);
    let visibleSpinnerCount = 0;

    for (let index = 0; index < spinnerCount; index += 1) {
      if (await spinner.nth(index).isVisible().catch(() => false)) {
        visibleSpinnerCount += 1;
      }
    }

    if (visibleSpinnerCount === 0) break;
    await page.waitForTimeout(250);
  }

  await page.waitForLoadState('networkidle', { timeout: 5_000 }).catch(() => undefined);
}

async function visibleTableHeaders(page: Page): Promise<string[]> {
  return locatorAllTrimmedText(page.locator('thead th'));
}

async function collectVisibleNotePayloads(page: Page, headers: string[], limitNotes: number, listPage: number): Promise<NoteDomPayload[]> {
  const rowLocator = page.locator('tr.ant-table-row');
  const rowCount = Math.min(await rowLocator.count(), limitNotes);
  const payloads: NoteDomPayload[] = [];

  for (let rowIndex = 0; rowIndex < rowCount; rowIndex += 1) {
    const row = rowLocator.nth(rowIndex);
    const cells = await locatorAllTrimmedText(row.locator('td'));
    const title = (await locatorTextOrNull(row.locator('[class*="note_title"]'))) ?? '';
    const authorName = await locatorTextOrNull(row.locator('[class*="live_anchor"] [class*="one_line"]'));
    const authorLevel = await locatorTextOrNull(row.locator('[class*="live_anchor"] span[style*="137"]'));
    const images = await collectImageSrcs(row);
    const coverUrl =
      images.find((src) => !src.includes('avatar') && (src.includes('xhscdn.com') || src.includes('huitun'))) ??
      images.find((src) => !src.includes('avatar')) ??
      null;
    const duration = await locatorTextOrNull(row.locator('[class*="duration"] span, [class*="duration"]'));
    const updatedText =
      (await locatorAllTrimmedText(row.locator('div'))).find((value) => value.startsWith('更新时间：')) ?? null;
    const tags = (await locatorAllTrimmedText(row.locator('[class*="item_tag"]'))).filter(Boolean);

    payloads.push({
      key: (await row.getAttribute('data-row-key')) ?? '',
      title,
      authorName,
      authorLevel,
      coverUrl,
      duration,
      updatedText,
      tags,
      cells,
      headers,
    });
  }

  return payloads.map((payload, index) => ({ ...payload, key: payload.key || `page-${listPage}-row-${index + 1}` }));
}

export async function sortNoteListByLikesDescending(page: Page): Promise<void> {
  const likesHeader = page.locator('thead th').filter({ hasText: '点赞' }).first();

  for (let attempt = 0; attempt < 3; attempt += 1) {
    const ariaSort = await likesHeader.getAttribute('aria-sort').catch(() => null);
    const hasActiveDescSorter = (await likesHeader.locator('.ant-table-column-sorter-down.active').count().catch(() => 0)) > 0;
    if (ariaSort === 'descending' || hasActiveDescSorter) {
      await waitForNoteTableSettled(page);
      return;
    }

    await likesHeader.click();
    await waitForNoteTableSettled(page);
  }

  const ariaSort = await likesHeader.getAttribute('aria-sort').catch(() => null);
  const hasActiveDescSorter = (await likesHeader.locator('.ant-table-column-sorter-down.active').count().catch(() => 0)) > 0;
  if (ariaSort !== 'descending' && !hasActiveDescSorter) {
    throw new Error('无法确认灰豚笔记列表已按点赞倒序排序，跳过该热词以避免采集非爆文样本。');
  }
}

export async function openNoteListPage(page: Page, pageIndex: number): Promise<void> {
  if (pageIndex <= 1) return;

  const targetPage = page.locator('.ant-pagination-item').filter({ hasText: String(pageIndex) }).first();
  await targetPage.click();
  await waitForNoteTableSettled(page);
}

async function collectVisibleVerifiedNoteRows(page: Page, hotWord: string, targetLimit: number): Promise<NoteListCollectionResult> {
  const deadline = Date.now() + 30_000;
  let lastResult: NoteListCollectionResult = {
    rows: [],
    likesSort: {
      status: 'insufficient_data',
      checkedRows: 0,
      missingLikesCount: 0,
      violationCount: 0,
    },
  };

  while (Date.now() < deadline) {
    const headers = await visibleTableHeaders(page);
    const payloads = await collectVisibleNotePayloads(page, headers, targetLimit, 1);
    const rows = parseNoteRowsFromDomPayload(hotWord, payloads)
      .slice(0, targetLimit)
      .map((row, index) => ({ ...row, listRank: index + 1, listPage: 1 }));
    const likesSort = verifyLikesDescending(rows);
    lastResult = { rows, likesSort };

    if (likesSort.status === 'verified' || (likesSort.status === 'insufficient_data' && rows.length > 0)) {
      return lastResult;
    }

    await page.waitForTimeout(500);
  }

  if (lastResult.likesSort.status === 'violated') {
    throw new Error('灰豚笔记列表点赞倒序验证失败，跳过该热词以避免采集非爆文样本。');
  }

  return lastResult;
}

export async function collectTopLikedNoteRows(page: Page, hotWord: string, limitNotes: number): Promise<NoteListCollectionResult> {
  const targetLimit = effectiveNoteLimit(limitNotes);
  await sortNoteListByLikesDescending(page);
  return collectVisibleVerifiedNoteRows(page, hotWord, targetLimit);
}

export async function collectNoteRows(page: Page, hotWord: string, limitNotes: number): Promise<NoteListRow[]> {
  return (await collectTopLikedNoteRows(page, hotWord, limitNotes)).rows;
}

export function getDetailUrlForDebug(hotWord: string, days: number): string {
  return detailUrl(hotWord, days);
}

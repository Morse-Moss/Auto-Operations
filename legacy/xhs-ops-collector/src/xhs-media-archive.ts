import { existsSync, mkdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { DatabaseSync } from 'node:sqlite';
import { createHash } from 'node:crypto';

import { chromium, type Browser, type BrowserContext, type Page, type Response } from 'playwright-core';

import { initializeSchema } from './db/schema.js';
import type { XhsMediaSource } from './xhs-types.js';
import type { XhsArchivedMediaFile, XhsMediaArchiveManifestEntry, XhsMediaArchiveSafetyStop, XhsMediaArchiveSafetyStopReason, XhsMediaArchiveSummary } from './xhs-media-types.js';
import {
  buildByteRanges,
  checkMp4Structure,
  csvCell,
  detectMediaKind,
  extensionFromContentType,
  extensionFromUrl,
  isCompleteMp4,
  parseContentRange,
  parseJsonArray,
  relativePosixPath,
  sanitizePathSegment,
  shouldArchiveMediaResponse,
} from './xhs-media-archive-utils.js';

const DEFAULT_BLOCK_SIZE = 1024 * 1024;

interface XhsArchiveDbRow {
  id: number;
  rank_index: number;
  feed_id: string;
  title: string;
  note_type: string;
  keyword: string;
  sort_label: string;
  search_result_url: string;
  explore_url: string | null;
  detail_tags_json: string;
  source_topic_texts_json: string;
  media_sources_json: string;
}

export interface XhsMediaArchiveOptions {
  runId: number;
  dbPath: string;
  cdpUrl: string;
  outputDir?: string;
  force: boolean;
  resumeMissingMedia: boolean;
  delayMinMs: number;
  delayMaxMs: number;
  blockSize?: number;
}

export interface XhsMediaArchiveResult extends XhsMediaArchiveSummary {
  manifest: string;
}

function openExistingDatabase(dbPath: string): DatabaseSync {
  const db = new DatabaseSync(dbPath);
  db.exec('pragma foreign_keys = ON');
  initializeSchema(db);
  return db;
}

function randomIntegerInRange(min: number, max: number): number {
  const lowerBound = Math.ceil(min);
  const upperBound = Math.floor(max);
  return Math.floor(Math.random() * (upperBound - lowerBound + 1)) + lowerBound;
}

async function wait(ms: number): Promise<void> {
  if (ms <= 0) {
    return;
  }
  await new Promise((resolve) => setTimeout(resolve, ms));
}

function archiveRoot(options: XhsMediaArchiveOptions): string {
  return resolve(options.outputDir ?? `data/xhs-media/run-${options.runId}`);
}

function entryDirectory(root: string, row: XhsArchiveDbRow): string {
  return join(root, `${String(row.rank_index).padStart(2, '0')}-${sanitizePathSegment(row.feed_id)}`);
}

function fileHash(value: string): string {
  return createHash('sha1').update(value).digest('hex').slice(0, 10);
}

function savedFilePath(params: { entryDir: string; kind: 'image' | 'video'; url: string; contentType: string; index: number }): string {
  const extension = extensionFromContentType(params.contentType) || extensionFromUrl(params.url) || (params.kind === 'video' ? '.bin' : '.img');
  return join(params.entryDir, params.kind === 'video' ? 'videos' : 'images', `${String(params.index).padStart(2, '0')}-${fileHash(params.url)}${extension}`);
}

function readRows(db: DatabaseSync, runId: number): XhsArchiveDbRow[] {
  return db.prepare(`
    select id, rank_index, feed_id, title, note_type, keyword, sort_label, search_result_url, explore_url,
           detail_tags_json, source_topic_texts_json, media_sources_json
    from xhs_search_notes
    where run_id = ?
    order by rank_index, id
  `).all(runId) as unknown as XhsArchiveDbRow[];
}

function contentLength(headers: Record<string, string>): number {
  const value = Number(headers['content-length'] ?? 0);
  return Number.isFinite(value) ? value : 0;
}

function decodeUrlText(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function normalizePageText(value: string): string {
  return value.replace(/\s+/g, ' ').trim();
}

function containsPlatformErrorUrl(value: string): boolean {
  return /\/website-login\/error(?:[/?#]|$)/i.test(value);
}

function containsRateLimitErrorCode(value: string): boolean {
  return /(?:^|[?&#\s])error_code\s*=\s*300013(?:$|[&#\s])/i.test(value);
}

function isKnownXhsNoteUrl(value: string): boolean {
  return /xiaohongshu\.com\/(?:search_result|explore)\//i.test(value);
}

function countVerificationSignals(value: string): number {
  const signals = [
    /安全验证/,
    /请完成验证/,
    /滑块验证/,
    /验证码/,
    /captcha/i,
    /robot/i,
    /人机验证/,
  ];
  return signals.reduce((count, signal) => count + (signal.test(value) ? 1 : 0), 0);
}

function isBareRateLimitPageText(text: string): boolean {
  return text.length <= 120
    && /(访问频繁|操作频繁|请求频繁)/.test(text)
    && /(请稍后|稍后再试|频繁访问|过于频繁)/.test(text);
}

function isBareVerificationPageText(text: string): boolean {
  return text.length <= 120
    && (/^(?:请)?(?:完成|进行|通过).{0,12}(?:安全验证|验证|校验)/.test(text)
      || /^(?:滑块|拖动|滑动).{0,12}(?:验证|拼图)/.test(text)
      || /^人机验证/.test(text)
      || /^captcha/i.test(text));
}

function isXhsSafetyPageSignal(input: { url?: string | null; text?: string | null; message?: string | null; hasChallengeContainer?: boolean }): XhsMediaArchiveSafetyStopReason | null {
  const url = input.url ?? '';
  const decodedUrl = decodeUrlText(url);
  const message = input.message ?? '';
  const decodedMessage = decodeUrlText(message);
  const text = normalizePageText(input.text ?? '');
  const urlAndMessage = `${url}\n${decodedUrl}\n${message}\n${decodedMessage}`;
  const combined = `${urlAndMessage}\n${text}`;

  if (containsRateLimitErrorCode(urlAndMessage) || (containsPlatformErrorUrl(urlAndMessage) && /访问频繁|操作频繁|请求频繁|稍后再试/.test(combined))) {
    return 'rate_limit';
  }
  if (containsPlatformErrorUrl(urlAndMessage)) {
    return 'safety_verification';
  }
  if (input.hasChallengeContainer === true) {
    return 'safety_verification';
  }

  const noteUrl = isKnownXhsNoteUrl(url) || isKnownXhsNoteUrl(decodedUrl);
  if (noteUrl) {
    return null;
  }

  if (isBareRateLimitPageText(text)) {
    return 'rate_limit';
  }

  if (isBareVerificationPageText(text) && countVerificationSignals(text) >= 1) {
    return 'safety_verification';
  }
  if (text.length <= 120 && countVerificationSignals(combined) >= 2) {
    return 'safety_verification';
  }

  return null;
}

async function readPageText(page: Page): Promise<string> {
  try {
    return await page.locator('body').innerText();
  } catch {
    return '';
  }
}

async function hasChallengeContainer(page: Page): Promise<boolean> {
  try {
    return await page.locator([
      '#captcha',
      '#captcha_container',
      '#captcha-container',
      '.captcha',
      '.captcha_container',
      '.captcha-container',
      '[class*="captcha"]',
      '[id*="captcha"]',
      '[class*="geetest"]',
      '[id*="geetest"]',
      '[class*="verify"]',
      '[id*="verify"]',
    ].join(',')).count() > 0;
  } catch {
    return false;
  }
}

function readPageUrl(page: Page): string {
  try {
    return page.url();
  } catch {
    return '';
  }
}

async function detectSafetyStop(page: Page, row: XhsArchiveDbRow, runId: number, phase: string, message?: string): Promise<XhsMediaArchiveSafetyStop | null> {
  const finalUrl = readPageUrl(page);
  const pageText = await readPageText(page);
  const reason = isXhsSafetyPageSignal({ url: finalUrl, text: pageText, message, hasChallengeContainer: await hasChallengeContainer(page) });
  if (reason === null) {
    return null;
  }

  return {
    runId,
    reason,
    message: `XHS safety stop: ${reason}`,
    phase,
    rankIndex: row.rank_index,
    feedId: row.feed_id,
    title: row.title,
    searchResultUrl: row.search_result_url,
    finalUrl,
    pageText,
    stoppedAt: new Date().toISOString(),
  };
}

async function captureMediaResponses(page: Page, row: XhsArchiveDbRow, root: string, runId: number): Promise<{ saved: XhsArchivedMediaFile[]; errors: string[]; safetyStop: XhsMediaArchiveSafetyStop | null }> {
  const entryDir = entryDirectory(root, row);
  mkdirSync(entryDir, { recursive: true });
  const seen = new Set<string>();
  const saved: XhsArchivedMediaFile[] = [];
  const errors: string[] = [];
  const captures: Array<Promise<void>> = [];

  page.on('response', (response: Response) => {
    const capture = (async () => {
      try {
        const url = response.url();
        const headers = response.headers();
        const contentType = headers['content-type'] ?? '';
        if (!shouldArchiveMediaResponse({ url, contentType, status: response.status() })) {
          return;
        }
        if (seen.has(url)) {
          return;
        }
        seen.add(url);

        const body = await response.body().catch((error: unknown) => {
          errors.push(`response body failed: ${url} ${error instanceof Error ? error.message : String(error)}`);
          return null;
        });
        if (body === null || body.length < 1024) {
          return;
        }

        const kind = detectMediaKind(url, contentType);
        if (kind === null) {
          return;
        }
        const file = savedFilePath({
          entryDir,
          kind,
          url,
          contentType,
          index: saved.filter((item) => item.kind === kind).length + 1,
        });
        mkdirSync(dirname(file), { recursive: true });
        writeFileSync(file, body);
        saved.push({
          kind,
          url,
          contentType,
          status: response.status(),
          bytes: body.length,
          file: relativePosixPath('.', file),
        });
      } catch (error) {
        errors.push(error instanceof Error ? error.message : String(error));
      }
    })();
    captures.push(capture);
  });

  let navigationMessage: string | undefined;
  await page.goto(row.search_result_url, { waitUntil: 'domcontentloaded' }).catch((error: unknown) => {
    navigationMessage = error instanceof Error ? error.message : String(error);
    errors.push(`goto failed: ${navigationMessage}`);
  });
  let safetyStop = await detectSafetyStop(page, row, runId, 'capture_media', navigationMessage);
  if (safetyStop !== null) {
    await Promise.allSettled(captures);
    return { saved, errors, safetyStop };
  }
  await page.waitForLoadState('networkidle').catch(async (error: unknown) => {
    safetyStop = await detectSafetyStop(page, row, runId, 'capture_media', error instanceof Error ? error.message : String(error));
  });
  if (safetyStop !== null) {
    await Promise.allSettled(captures);
    return { saved, errors, safetyStop };
  }
  await page.evaluate(() => {
    window.scrollTo(0, 600);
    for (const video of Array.from(document.querySelectorAll('video'))) {
      video.muted = true;
      video.play().catch(() => undefined);
    }
  }).catch(() => undefined);
  await wait(7_000);
  safetyStop = await detectSafetyStop(page, row, runId, 'capture_media');
  await Promise.allSettled(captures);

  return { saved, errors, safetyStop };
}

interface FreshVideoInfo {
  page: Page | null;
  url: string | null;
  totalBytes: number;
  safetyStop: XhsMediaArchiveSafetyStop | null;
}

async function findFreshVideoInfo(context: BrowserContext, row: XhsArchiveDbRow, runId: number): Promise<FreshVideoInfo> {
  const page = await context.newPage();
  page.setDefaultTimeout(30_000);
  const first: { current: { url: string; totalBytes: number } | null } = { current: null };

  page.on('response', (response: Response) => {
    const url = response.url();
    const headers = response.headers();
    const contentType = headers['content-type'] ?? '';
    if (first.current !== null || !contentType.toLowerCase().startsWith('video/mp4') || !url.includes('sns-video')) {
      return;
    }
    const range = parseContentRange(headers['content-range']);
    first.current = {
      url,
      totalBytes: range?.total ?? contentLength(headers),
    };
  });

  let navigationMessage: string | undefined;
  await page.goto(row.search_result_url, { waitUntil: 'domcontentloaded' }).catch((error: unknown) => {
    navigationMessage = error instanceof Error ? error.message : String(error);
  });
  let safetyStop = await detectSafetyStop(page, row, runId, 'complete_video', navigationMessage);
  if (safetyStop !== null) {
    await page.close().catch(() => undefined);
    return { page: null, url: null, totalBytes: 0, safetyStop };
  }
  await page.waitForLoadState('networkidle').catch(async (error: unknown) => {
    safetyStop = await detectSafetyStop(page, row, runId, 'complete_video', error instanceof Error ? error.message : String(error));
  });
  if (safetyStop !== null) {
    await page.close().catch(() => undefined);
    return { page: null, url: null, totalBytes: 0, safetyStop };
  }
  await page.evaluate(() => {
    const video = document.querySelector('video');
    if (video !== null) {
      video.muted = true;
      video.play().catch(() => undefined);
    }
  }).catch(() => undefined);

  for (let attempt = 0; attempt < 10 && first.current === null; attempt += 1) {
    safetyStop = await detectSafetyStop(page, row, runId, 'complete_video');
    if (safetyStop !== null) {
      await page.close().catch(() => undefined);
      return { page: null, url: null, totalBytes: 0, safetyStop };
    }
    await wait(1_000);
  }

  if (first.current === null) {
    await page.close().catch(() => undefined);
    return { page: null, url: null, totalBytes: 0, safetyStop: null };
  }

  let totalBytes = first.current.totalBytes;
  if (totalBytes <= 0) {
    const probe = await page.evaluate(async ({ url }) => {
      const response = await fetch(url, { headers: { Range: 'bytes=0-0' } });
      return {
        status: response.status,
        contentRange: response.headers.get('content-range'),
        contentLength: response.headers.get('content-length'),
      };
    }, { url: first.current.url }).catch(() => null);
    totalBytes = parseContentRange(probe?.contentRange)?.total ?? Number(probe?.contentLength ?? 0);
  }

  return { page, url: first.current.url, totalBytes, safetyStop: null };
}

async function fetchRange(page: Page, url: string, start: number, end: number): Promise<Buffer> {
  const result = await page.evaluate(async ({ url, start, end }) => {
    const response = await fetch(url, { headers: { Range: `bytes=${start}-${end}` } });
    const arrayBuffer = await response.arrayBuffer();
    return {
      status: response.status,
      contentRange: response.headers.get('content-range'),
      bytes: Array.from(new Uint8Array(arrayBuffer)),
    };
  }, { url, start, end });

  if (![200, 206].includes(result.status)) {
    throw new Error(`Range request failed: ${result.status} ${start}-${end}`);
  }
  return Buffer.from(result.bytes);
}

interface CompleteVideoArchiveResult extends Pick<XhsMediaArchiveManifestEntry, 'completeVideoStatus' | 'completeVideoFile' | 'completeVideoBytes' | 'completeVideoCoveredBytes' | 'completeVideoChunkCount' | 'completeVideoGaps'> {
  safetyStop: XhsMediaArchiveSafetyStop | null;
}

async function archiveCompleteVideo(context: BrowserContext, row: XhsArchiveDbRow, root: string, blockSize: number, runId: number): Promise<CompleteVideoArchiveResult> {
  const info = await findFreshVideoInfo(context, row, runId);
  if (info.safetyStop !== null) {
    return {
      completeVideoStatus: 'failed',
      completeVideoFile: null,
      completeVideoBytes: 0,
      completeVideoCoveredBytes: 0,
      completeVideoChunkCount: 0,
      completeVideoGaps: [],
      safetyStop: info.safetyStop,
    };
  }
  if (info.page === null || info.url === null || info.totalBytes <= 0) {
    return {
      completeVideoStatus: 'no_video_url',
      completeVideoFile: null,
      completeVideoBytes: 0,
      completeVideoCoveredBytes: 0,
      completeVideoChunkCount: 0,
      completeVideoGaps: [],
      safetyStop: null,
    };
  }

  try {
    if (info.totalBytes === 1) {
      const page = info.page;
      await page.close().catch(() => undefined);
      return {
        completeVideoStatus: 'incomplete',
        completeVideoFile: null,
        completeVideoBytes: 0,
        completeVideoCoveredBytes: 0,
        completeVideoChunkCount: 0,
        completeVideoGaps: [],
        safetyStop: null,
      };
    }

    const ranges = buildByteRanges(info.totalBytes, blockSize);
    const buffer = Buffer.alloc(info.totalBytes);
    let fetchedBytes = 0;
    for (const range of ranges) {
      const chunk = await fetchRange(info.page, info.url, range.start, range.end);
      if (chunk.length !== range.end - range.start + 1) {
        throw new Error(`Range length mismatch: ${range.start}-${range.end}, got ${chunk.length}`);
      }
      chunk.copy(buffer, range.start);
      fetchedBytes += chunk.length;
      await wait(300);
    }

    const entryDir = entryDirectory(root, row);
    const file = join(entryDir, 'videos', `active-${fileHash(info.url.split('?')[0])}.mp4`);
    mkdirSync(dirname(file), { recursive: true });
    writeFileSync(file, buffer);
    const complete = fetchedBytes === info.totalBytes;
    return {
      completeVideoStatus: complete ? 'complete' : 'incomplete',
      completeVideoFile: complete ? relativePosixPath('.', file) : null,
      completeVideoBytes: info.totalBytes,
      completeVideoCoveredBytes: fetchedBytes,
      completeVideoChunkCount: ranges.length,
      completeVideoGaps: complete ? [] : [[fetchedBytes, info.totalBytes - 1]],
      safetyStop: null,
    };
  } catch (error) {
    const safetyStop = await detectSafetyStop(info.page, row, runId, 'complete_video', error instanceof Error ? error.message : String(error));
    return {
      completeVideoStatus: 'failed',
      completeVideoFile: null,
      completeVideoBytes: info.totalBytes,
      completeVideoCoveredBytes: 0,
      completeVideoChunkCount: 0,
      completeVideoGaps: [[0, info.totalBytes - 1]],
      safetyStop,
    };
  } finally {
    await info.page.close().catch(() => undefined);
  }
}

function verifyShortVideos(entry: XhsMediaArchiveManifestEntry): void {
  if (entry.noteType !== 'video' || entry.completeVideoStatus === 'complete') {
    return;
  }

  const candidate = entry.videoFiles
    .filter((file) => !file.includes('/active-'))
    .map((file) => ({ file, size: statSync(file).size }))
    .filter((item) => item.size > 1024)
    .sort((a, b) => b.size - a.size)[0];

  if (candidate === undefined) {
    return;
  }

  const buffer = readFileSync(candidate.file);
  if (!isCompleteMp4(buffer)) {
    return;
  }

  entry.completeVideoStatus = 'complete_short_mp4_structure_verified';
  entry.completeVideoFile = candidate.file;
  entry.completeVideoBytes = candidate.size;
  entry.completeVideoCoveredBytes = candidate.size;
  entry.completeVideoChunkCount = 1;
  entry.completeVideoGaps = [];
}

function buildManifestEntry(row: XhsArchiveDbRow, saved: XhsArchivedMediaFile[], errors: string[]): XhsMediaArchiveManifestEntry {
  const imageFiles = saved.filter((item) => item.kind === 'image').map((item) => item.file);
  const videoFiles = saved.filter((item) => item.kind === 'video').map((item) => item.file);
  return normalizeManifestEntry({
    rankIndex: row.rank_index,
    feedId: row.feed_id,
    title: row.title,
    noteType: row.note_type,
    keyword: row.keyword,
    sortLabel: row.sort_label,
    searchResultUrl: row.search_result_url,
    exploreUrl: row.explore_url,
    tags: parseJsonArray<string>(row.detail_tags_json),
    topics: parseJsonArray<string>(row.source_topic_texts_json),
    sourceMediaUrls: parseJsonArray<XhsMediaSource>(row.media_sources_json).map((item) => item.url),
    status: saved.length === 0 ? 'no_media_saved' : errors.length === 0 ? 'success' : 'partial_failed',
    imageCount: imageFiles.length,
    videoCount: videoFiles.length,
    imageFiles,
    videoFiles,
    saved,
    errors,
  });
}

function isCompleteVideoStatus(status: XhsMediaArchiveManifestEntry['completeVideoStatus']): boolean {
  return status === 'complete' || status === 'complete_short_mp4_structure_verified';
}

function hasCompleteVideoFile(entry: XhsMediaArchiveManifestEntry): entry is XhsMediaArchiveManifestEntry & { completeVideoFile: string } {
  return entry.noteType === 'video'
    && isCompleteVideoStatus(entry.completeVideoStatus)
    && entry.completeVideoFile !== null
    && entry.completeVideoFile !== undefined
    && entry.completeVideoFile !== '';
}

function normalizeManifestEntry(entry: XhsMediaArchiveManifestEntry): XhsMediaArchiveManifestEntry {
  if (!hasCompleteVideoFile(entry)) {
    return entry;
  }

  const videoFiles = entry.videoFiles.includes(entry.completeVideoFile)
    ? entry.videoFiles
    : [entry.completeVideoFile, ...entry.videoFiles];
  return {
    ...entry,
    status: 'success',
    imageCount: entry.imageFiles.length,
    videoCount: videoFiles.length,
    videoFiles,
  };
}

function readExistingManifest(path: string): XhsMediaArchiveManifestEntry[] {
  if (!existsSync(path)) {
    return [];
  }

  try {
    const parsed = JSON.parse(readFileSync(path, 'utf8')) as unknown;
    return Array.isArray(parsed) ? parsed as XhsMediaArchiveManifestEntry[] : [];
  } catch {
    return [];
  }
}

function localPath(file: string): string | null {
  if (existsSync(file)) {
    return file;
  }
  const resolved = resolve(file);
  return existsSync(resolved) ? resolved : null;
}

function localFileSize(file: string): number | null {
  const path = localPath(file);
  if (path === null) {
    return null;
  }
  try {
    return statSync(path).size;
  } catch {
    return null;
  }
}

function localFileNonEmpty(file: string): boolean {
  const size = localFileSize(file);
  return size !== null && size > 0;
}

function completeVideoFileValid(entry: XhsMediaArchiveManifestEntry): boolean {
  if (entry.completeVideoFile === null || entry.completeVideoFile === undefined || entry.completeVideoFile.trim() === '') {
    return false;
  }
  const size = localFileSize(entry.completeVideoFile);
  if (size === null || size <= 0) {
    return false;
  }
  const expectedBytes = entry.completeVideoBytes;
  return typeof expectedBytes === 'number' && expectedBytes > 0 ? size === expectedBytes : true;
}

function manifestEntryComplete(entry: XhsMediaArchiveManifestEntry): boolean {
  const normalized = normalizeManifestEntry(entry);
  if (normalized.status !== 'success') {
    return false;
  }

  const mediaFiles = [...normalized.imageFiles, ...normalized.videoFiles];
  if (mediaFiles.length === 0 || mediaFiles.some((file) => !localFileNonEmpty(file))) {
    return false;
  }

  if (normalized.noteType !== 'video') {
    return true;
  }

  return isCompleteVideoStatus(normalized.completeVideoStatus) && completeVideoFileValid(normalized);
}

function rowIdentityKey(row: Pick<XhsArchiveDbRow, 'feed_id' | 'rank_index' | 'sort_label'>): string {
  return JSON.stringify([row.feed_id, row.rank_index, row.sort_label]);
}

function entryIdentityKey(entry: Pick<XhsMediaArchiveManifestEntry, 'feedId' | 'rankIndex' | 'sortLabel'>): string {
  return JSON.stringify([entry.feedId, entry.rankIndex, entry.sortLabel]);
}

function takeFirstCompleteEntry(entries: XhsMediaArchiveManifestEntry[]): XhsMediaArchiveManifestEntry | null {
  const index = entries.findIndex((entry) => manifestEntryComplete(normalizeManifestEntry(entry)));
  if (index < 0) {
    return null;
  }
  const [entry] = entries.splice(index, 1);
  return normalizeManifestEntry(entry);
}

interface ExistingManifestIndex {
  byIdentity: Map<string, XhsMediaArchiveManifestEntry[]>;
  byFeedId: Map<string, XhsMediaArchiveManifestEntry[]>;
  dbFeedCounts: Map<string, number>;
}

function buildExistingManifestIndex(entries: XhsMediaArchiveManifestEntry[], rows: XhsArchiveDbRow[]): ExistingManifestIndex {
  const byIdentity = new Map<string, XhsMediaArchiveManifestEntry[]>();
  const byFeedId = new Map<string, XhsMediaArchiveManifestEntry[]>();
  const dbFeedCounts = new Map<string, number>();
  for (const row of rows) {
    dbFeedCounts.set(row.feed_id, (dbFeedCounts.get(row.feed_id) ?? 0) + 1);
  }
  for (const entry of entries) {
    const identityKey = entryIdentityKey(entry);
    byIdentity.set(identityKey, [...byIdentity.get(identityKey) ?? [], entry]);
    byFeedId.set(entry.feedId, [...byFeedId.get(entry.feedId) ?? [], entry]);
  }
  return { byIdentity, byFeedId, dbFeedCounts };
}

function manifestEntryForRow(row: XhsArchiveDbRow, existingIndex: ExistingManifestIndex): XhsMediaArchiveManifestEntry | null {
  const identityMatch = takeFirstCompleteEntry(existingIndex.byIdentity.get(rowIdentityKey(row)) ?? []);
  if (identityMatch !== null) {
    return identityMatch;
  }

  if ((existingIndex.dbFeedCounts.get(row.feed_id) ?? 0) > 1) {
    return null;
  }

  const feedEntries = existingIndex.byFeedId.get(row.feed_id) ?? [];
  if (feedEntries.length !== 1) {
    return null;
  }
  return takeFirstCompleteEntry(feedEntries);
}

function writeManifestCsv(runId: number, root: string, manifest: XhsMediaArchiveManifestEntry[]): string {
  const output = join(root, `小红书_run${runId}_本地媒体_UTF8BOM.csv`);
  const columns: Array<[keyof Record<string, unknown>, string]> = [
    ['rankIndex', '排名'],
    ['feedId', '笔记ID'],
    ['noteTypeText', '笔记类型'],
    ['title', '标题'],
    ['statusText', '归档状态'],
    ['imageCount', '本地图片数'],
    ['videoCount', '本地视频数'],
    ['completeVideoStatusText', '完整视频状态'],
    ['imageFilesText', '本地图片路径'],
    ['videoFilesText', '本地视频路径'],
    ['tagsText', '标签'],
    ['searchResultUrl', '搜索结果链接'],
    ['errorsText', '失败原因'],
  ];
  const lines = [columns.map(([, label]) => csvCell(label)).join(',')];
  for (const item of manifest) {
    const values: Record<string, unknown> = {
      ...item,
      noteTypeText: item.noteType === 'video' ? '视频' : '图文',
      statusText: item.status === 'success' ? '成功' : item.status === 'no_media_saved' ? '未保存到媒体' : '部分失败',
      completeVideoStatusText: item.completeVideoStatus === 'complete'
        ? '完整'
        : item.completeVideoStatus === 'complete_short_mp4_structure_verified'
          ? '短视频完整（MP4结构已验证）'
          : item.completeVideoStatus ?? '',
      imageFilesText: item.imageFiles.join('\n'),
      videoFilesText: item.videoFiles.join('\n'),
      tagsText: item.tags.join('、'),
      errorsText: item.errors.join('\n'),
    };
    lines.push(columns.map(([key]) => csvCell(values[String(key)])).join(','));
  }
  writeFileSync(output, `﻿${lines.join('\r\n')}`, 'utf8');
  return output;
}

function summarize(runId: number, root: string, csv: string, manifest: XhsMediaArchiveManifestEntry[], safetyStop?: XhsMediaArchiveSafetyStop): XhsMediaArchiveSummary {
  return {
    runId,
    rows: manifest.length,
    success: manifest.filter((item) => item.status === 'success').length,
    noMediaSaved: manifest.filter((item) => item.status === 'no_media_saved').length,
    imageFiles: manifest.reduce((sum, item) => sum + item.imageCount, 0),
    videoFiles: manifest.reduce((sum, item) => sum + item.videoCount, 0),
    completeVideos: manifest.filter((item) => isCompleteVideoStatus(item.completeVideoStatus)).length,
    incompleteVideos: manifest.filter((item) => item.noteType === 'video' && !isCompleteVideoStatus(item.completeVideoStatus)).length,
    root: relativePosixPath('.', root),
    csv,
    safetyStopped: safetyStop !== undefined,
    ...(safetyStop === undefined ? {} : { safetyStop }),
  };
}

function writeArchiveArtifacts(runId: number, root: string, manifest: XhsMediaArchiveManifestEntry[], safetyStop?: XhsMediaArchiveSafetyStop): XhsMediaArchiveResult {
  const normalizedManifest = manifest.map(normalizeManifestEntry);
  const manifestPath = join(root, 'manifest.json');
  writeFileSync(manifestPath, JSON.stringify(normalizedManifest, null, 2), 'utf8');
  const csv = writeManifestCsv(runId, root, normalizedManifest);
  const summary = summarize(runId, root, csv, normalizedManifest, safetyStop);
  writeFileSync(join(root, 'summary.json'), JSON.stringify(summary, null, 2), 'utf8');
  const safetyStopPath = join(root, 'safety-stop.json');
  if (safetyStop !== undefined) {
    writeFileSync(safetyStopPath, JSON.stringify(safetyStop, null, 2), 'utf8');
  } else {
    rmSync(safetyStopPath, { force: true });
  }
  return { ...summary, manifest: relativePosixPath('.', manifestPath) };
}

export async function archiveXhsRunMedia(options: XhsMediaArchiveOptions): Promise<XhsMediaArchiveResult> {
  const db = openExistingDatabase(options.dbPath);
  let browser: Browser | undefined;
  try {
    const rows = readRows(db, options.runId);
    const root = archiveRoot(options);
    if (options.force) {
      rmSync(root, { recursive: true, force: true });
    }
    mkdirSync(root, { recursive: true });

    const manifestPath = join(root, 'manifest.json');
    const existingIndex = options.force || !options.resumeMissingMedia
      ? buildExistingManifestIndex([], rows)
      : buildExistingManifestIndex(readExistingManifest(manifestPath), rows);

    const manifest: Array<XhsMediaArchiveManifestEntry | null> = [];
    const rowsToProcess: Array<{ row: XhsArchiveDbRow; index: number }> = [];

    rows.forEach((row, index) => {
      const existing = manifestEntryForRow(row, existingIndex);
      if (existing !== null) {
        manifest[index] = existing;
      } else {
        manifest[index] = null;
        rowsToProcess.push({ row, index });
      }
    });

    if (rowsToProcess.length === 0) {
      return writeArchiveArtifacts(options.runId, root, manifest.filter((entry): entry is XhsMediaArchiveManifestEntry => entry !== null));
    }

    browser = await chromium.connectOverCDP(options.cdpUrl);
    const context = browser.contexts()[0] ?? await browser.newContext();

    for (const { row, index } of rowsToProcess) {
      const page = await context.newPage();
      page.setDefaultTimeout(30_000);
      const capture = await captureMediaResponses(page, row, root, options.runId);
      await page.close().catch(() => undefined);
      if (capture.safetyStop !== null) {
        return writeArchiveArtifacts(options.runId, root, manifest.filter((item): item is XhsMediaArchiveManifestEntry => item !== null), capture.safetyStop);
      }

      const entry = buildManifestEntry(row, capture.saved, capture.errors);
      manifest[index] = normalizeManifestEntry(entry);
      if (row.note_type === 'video') {
        const completeVideo = await archiveCompleteVideo(context, row, root, options.blockSize ?? DEFAULT_BLOCK_SIZE, options.runId);
        if (completeVideo.safetyStop !== null) {
          return writeArchiveArtifacts(options.runId, root, manifest.filter((item): item is XhsMediaArchiveManifestEntry => item !== null), completeVideo.safetyStop);
        }
        const { safetyStop: _safetyStop, ...completeVideoFields } = completeVideo;
        Object.assign(entry, completeVideoFields);
        if (completeVideo.completeVideoFile !== null && completeVideo.completeVideoFile !== undefined) {
          entry.videoFiles = [completeVideo.completeVideoFile, ...entry.videoFiles.filter((file) => file !== completeVideo.completeVideoFile)];
          entry.videoCount = entry.videoFiles.length;
        }
        verifyShortVideos(entry);
      }
      manifest[index] = normalizeManifestEntry(entry);
      await wait(randomIntegerInRange(options.delayMinMs, options.delayMaxMs));
    }

    return writeArchiveArtifacts(options.runId, root, manifest.filter((entry): entry is XhsMediaArchiveManifestEntry => entry !== null));
  } finally {
    await browser?.close().catch(() => undefined);
    db.close();
  }
}

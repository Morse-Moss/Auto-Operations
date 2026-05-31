import { mkdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { DatabaseSync } from 'node:sqlite';
import { createHash } from 'node:crypto';

import { chromium, type Browser, type BrowserContext, type Page, type Response } from 'playwright-core';

import { initializeSchema } from './db/schema.js';
import type { XhsMediaSource } from './xhs-types.js';
import type { XhsArchivedMediaFile, XhsMediaArchiveManifestEntry, XhsMediaArchiveSummary } from './xhs-media-types.js';
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

async function captureMediaResponses(page: Page, row: XhsArchiveDbRow, root: string): Promise<{ saved: XhsArchivedMediaFile[]; errors: string[] }> {
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

  await page.goto(row.search_result_url, { waitUntil: 'domcontentloaded' }).catch((error: unknown) => {
    errors.push(`goto failed: ${error instanceof Error ? error.message : String(error)}`);
  });
  await page.waitForLoadState('networkidle').catch(() => undefined);
  await page.evaluate(() => {
    window.scrollTo(0, 600);
    for (const video of Array.from(document.querySelectorAll('video'))) {
      video.muted = true;
      video.play().catch(() => undefined);
    }
  }).catch(() => undefined);
  await wait(7_000);
  await Promise.allSettled(captures);

  return { saved, errors };
}

interface FreshVideoInfo {
  page: Page | null;
  url: string | null;
  totalBytes: number;
}

async function findFreshVideoInfo(context: BrowserContext, row: XhsArchiveDbRow): Promise<FreshVideoInfo> {
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

  await page.goto(row.search_result_url, { waitUntil: 'domcontentloaded' }).catch(() => undefined);
  await page.waitForLoadState('networkidle').catch(() => undefined);
  await page.evaluate(() => {
    const video = document.querySelector('video');
    if (video !== null) {
      video.muted = true;
      video.play().catch(() => undefined);
    }
  }).catch(() => undefined);

  for (let attempt = 0; attempt < 10 && first.current === null; attempt += 1) {
    await wait(1_000);
  }

  if (first.current === null) {
    await page.close().catch(() => undefined);
    return { page: null, url: null, totalBytes: 0 };
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

  return { page, url: first.current.url, totalBytes };
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

async function archiveCompleteVideo(context: BrowserContext, row: XhsArchiveDbRow, root: string, blockSize: number): Promise<Pick<XhsMediaArchiveManifestEntry, 'completeVideoStatus' | 'completeVideoFile' | 'completeVideoBytes' | 'completeVideoCoveredBytes' | 'completeVideoChunkCount' | 'completeVideoGaps'>> {
  const info = await findFreshVideoInfo(context, row);
  if (info.page === null || info.url === null || info.totalBytes <= 0) {
    return {
      completeVideoStatus: 'no_video_url',
      completeVideoFile: null,
      completeVideoBytes: 0,
      completeVideoCoveredBytes: 0,
      completeVideoChunkCount: 0,
      completeVideoGaps: [],
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
    };
  } catch (error) {
    return {
      completeVideoStatus: 'failed',
      completeVideoFile: null,
      completeVideoBytes: info.totalBytes,
      completeVideoCoveredBytes: 0,
      completeVideoChunkCount: 0,
      completeVideoGaps: [[0, info.totalBytes - 1]],
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
  return {
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
  };
}

function writeManifestCsv(runId: number, manifest: XhsMediaArchiveManifestEntry[]): string {
  const output = `data/小红书_run${runId}_本地媒体_UTF8BOM.csv`;
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

function summarize(runId: number, root: string, csv: string, manifest: XhsMediaArchiveManifestEntry[]): XhsMediaArchiveSummary {
  return {
    runId,
    rows: manifest.length,
    success: manifest.filter((item) => item.status === 'success').length,
    noMediaSaved: manifest.filter((item) => item.status === 'no_media_saved').length,
    imageFiles: manifest.reduce((sum, item) => sum + item.imageCount, 0),
    videoFiles: manifest.reduce((sum, item) => sum + item.videoCount, 0),
    completeVideos: manifest.filter((item) => item.completeVideoStatus === 'complete' || item.completeVideoStatus === 'complete_short_mp4_structure_verified').length,
    incompleteVideos: manifest.filter((item) => item.noteType === 'video' && item.completeVideoStatus !== 'complete' && item.completeVideoStatus !== 'complete_short_mp4_structure_verified').length,
    root: relativePosixPath('.', root),
    csv,
  };
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

    browser = await chromium.connectOverCDP(options.cdpUrl);
    const context = browser.contexts()[0] ?? await browser.newContext();
    const manifest: XhsMediaArchiveManifestEntry[] = [];

    for (const row of rows) {
      const page = await context.newPage();
      page.setDefaultTimeout(30_000);
      const capture = await captureMediaResponses(page, row, root);
      await page.close().catch(() => undefined);
      const entry = buildManifestEntry(row, capture.saved, capture.errors);
      if (row.note_type === 'video') {
        const completeVideo = await archiveCompleteVideo(context, row, root, options.blockSize ?? DEFAULT_BLOCK_SIZE);
        Object.assign(entry, completeVideo);
        if (completeVideo.completeVideoFile !== null && completeVideo.completeVideoFile !== undefined) {
          entry.videoFiles = [completeVideo.completeVideoFile, ...entry.videoFiles.filter((file) => file !== completeVideo.completeVideoFile)];
          entry.videoCount = entry.videoFiles.length;
        }
        verifyShortVideos(entry);
      }
      manifest.push(entry);
      await wait(randomIntegerInRange(options.delayMinMs, options.delayMaxMs));
    }

    const manifestPath = join(root, 'manifest.json');
    writeFileSync(manifestPath, JSON.stringify(manifest, null, 2), 'utf8');
    const csv = writeManifestCsv(options.runId, manifest);
    const summary = summarize(options.runId, root, csv, manifest);
    writeFileSync(join(root, 'summary.json'), JSON.stringify(summary, null, 2), 'utf8');
    return { ...summary, manifest: relativePosixPath('.', manifestPath) };
  } finally {
    await browser?.close().catch(() => undefined);
    db.close();
  }
}

import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it, vi } from 'vitest';

import { openDatabase } from '../src/db/client.js';
import { initializeSchema } from '../src/db/schema.js';

const playwrightMocks = vi.hoisted(() => ({
  connectOverCDP: vi.fn(),
}));

vi.mock('playwright-core', () => ({
  chromium: {
    connectOverCDP: playwrightMocks.connectOverCDP,
  },
}));

import { archiveXhsRunMedia } from '../src/xhs-media-archive.js';

type MockPage = {
  setDefaultTimeout: ReturnType<typeof vi.fn>;
  on: ReturnType<typeof vi.fn>;
  goto: ReturnType<typeof vi.fn>;
  waitForLoadState: ReturnType<typeof vi.fn>;
  evaluate: ReturnType<typeof vi.fn>;
  locator: ReturnType<typeof vi.fn>;
  url: ReturnType<typeof vi.fn>;
  close: ReturnType<typeof vi.fn>;
};

let tempDir: string | undefined;

function createTempDir(): string {
  tempDir = mkdtempSync(join(tmpdir(), 'xhs-media-archive-test-'));
  return tempDir;
}

function createPage(params: { url: string; bodyText: string; mediaResponses?: Array<{ url: string; contentType: string; status?: number; body: Buffer }> }): MockPage {
  const responseHandlers: Array<(response: { url: () => string; headers: () => Record<string, string>; status: () => number; body: () => Promise<Buffer> }) => void> = [];
  return {
    setDefaultTimeout: vi.fn(),
    on: vi.fn().mockImplementation((event: string, handler: (response: { url: () => string; headers: () => Record<string, string>; status: () => number; body: () => Promise<Buffer> }) => void) => {
      if (event === 'response') {
        responseHandlers.push(handler);
      }
    }),
    goto: vi.fn().mockResolvedValue(undefined),
    waitForLoadState: vi.fn().mockResolvedValue(undefined),
    evaluate: vi.fn().mockImplementation(async () => {
      for (const mediaResponse of params.mediaResponses ?? []) {
        for (const handler of responseHandlers) {
          handler({
            url: () => mediaResponse.url,
            headers: () => ({
              'content-type': mediaResponse.contentType,
              'content-length': String(mediaResponse.body.length),
            }),
            status: () => mediaResponse.status ?? 200,
            body: async () => mediaResponse.body,
          });
        }
      }
      return undefined;
    }),
    locator: vi.fn().mockReturnValue({ innerText: vi.fn().mockResolvedValue(params.bodyText) }),
    url: vi.fn().mockReturnValue(params.url),
    close: vi.fn().mockResolvedValue(undefined),
  };
}

function mockBrowserWithPages(pages: MockPage[]): { context: { newPage: ReturnType<typeof vi.fn> } } {
  const queue = [...pages];
  const context = {
    newPage: vi.fn().mockImplementation(async () => {
      const page = queue.shift();
      if (page === undefined) {
        throw new Error('unexpected newPage call');
      }
      return page;
    }),
  };
  const browser = {
    contexts: vi.fn().mockReturnValue([context]),
    newContext: vi.fn().mockResolvedValue(context),
    close: vi.fn().mockResolvedValue(undefined),
  };
  playwrightMocks.connectOverCDP.mockResolvedValue(browser);
  return { context };
}

function seedRun(dbPath: string, rows: Array<{ rankIndex: number; feedId: string; noteType?: string; sortKey?: string; sortLabel?: string }>): void {
  const db = openDatabase(dbPath);
  initializeSchema(db);
  db.prepare(`insert into xhs_search_runs (id, source, source_run_id, keyword, sorts_json, limit_per_sort, with_details, status) values (1, 'manual_keyword', null, '护肤', '["latest"]', 20, 1, 'success')`).run();
  for (const row of rows) {
    const sortKey = row.sortKey ?? 'latest';
    const sortLabel = row.sortLabel ?? '最新';
    db.prepare(`
      insert into xhs_search_notes (
        run_id, keyword, sort_key, sort_label, rank_index, feed_id, xsec_token, search_result_url,
        title, author_name, detail_text, detail_tags_json, detail_like_text, detail_collect_text,
        detail_comment_count_text, detail_share_text, note_type, source_topic_texts_json,
        source_comments_json, media_sources_json, raw_card_text
      ) values (
        1, '护肤', ?, ?, ?, ?, 'token', ?,
        ?, '作者A', '正文', '[]', '10', '2', '1', '0', ?, '[]', '[]', '[]', ?
      )
    `).run(
      sortKey,
      sortLabel,
      row.rankIndex,
      row.feedId,
      `https://www.xiaohongshu.com/search_result/${row.feedId}?xsec_token=token`,
      `标题 ${row.feedId}`,
      row.noteType ?? 'image',
      `标题 ${row.feedId}`,
    );
  }
  db.close();
}

function imageManifestEntry(params: { feedId: string; rankIndex: number; imageFile: string; status?: string }) {
  return {
    rankIndex: params.rankIndex,
    feedId: params.feedId,
    title: `标题 ${params.feedId}`,
    noteType: 'image',
    keyword: '护肤',
    sortLabel: '最新',
    searchResultUrl: `https://www.xiaohongshu.com/search_result/${params.feedId}?xsec_token=token`,
    exploreUrl: null,
    tags: [],
    topics: [],
    sourceMediaUrls: [],
    status: params.status ?? 'success',
    imageCount: params.status === 'no_media_saved' ? 0 : 1,
    videoCount: 0,
    imageFiles: params.status === 'no_media_saved' ? [] : [params.imageFile],
    videoFiles: [],
    saved: [],
    errors: [],
  };
}

function completeVideoManifestEntry(params: { feedId: string; rankIndex: number; videoFile: string; status?: string; completeVideoStatus?: string }) {
  return {
    rankIndex: params.rankIndex,
    feedId: params.feedId,
    title: `标题 ${params.feedId}`,
    noteType: 'video',
    keyword: '护肤',
    sortLabel: '最新',
    searchResultUrl: `https://www.xiaohongshu.com/search_result/${params.feedId}?xsec_token=token`,
    exploreUrl: null,
    tags: [],
    topics: [],
    sourceMediaUrls: [],
    status: params.status ?? 'success',
    imageCount: 0,
    videoCount: 1,
    imageFiles: [],
    videoFiles: [params.videoFile],
    saved: [],
    errors: [],
    completeVideoStatus: params.completeVideoStatus ?? 'complete',
    completeVideoFile: params.videoFile,
    completeVideoBytes: 2048,
    completeVideoCoveredBytes: 2048,
    completeVideoChunkCount: 1,
    completeVideoGaps: [],
  };
}

function createCompleteVideoProbePage(videoBytes: Buffer): MockPage {
  const responseHandlers: Array<(response: { url: () => string; headers: () => Record<string, string> }) => void> = [];
  const videoUrl = 'https://sns-video-v4.xhscdn.com/stream/video.mp4?sign=abc';
  return {
    setDefaultTimeout: vi.fn(),
    on: vi.fn().mockImplementation((event: string, handler: (response: { url: () => string; headers: () => Record<string, string> }) => void) => {
      if (event === 'response') {
        responseHandlers.push(handler);
      }
    }),
    goto: vi.fn().mockResolvedValue(undefined),
    waitForLoadState: vi.fn().mockResolvedValue(undefined),
    evaluate: vi.fn().mockImplementation(async (_script: unknown, args?: { url?: string; start?: number; end?: number }) => {
      if (args?.url !== undefined && args.start !== undefined && args.end !== undefined) {
        return {
          status: 206,
          contentRange: `bytes ${args.start}-${args.end}/${videoBytes.length}`,
          bytes: Array.from(videoBytes.subarray(args.start, args.end + 1)),
        };
      }
      for (const handler of responseHandlers) {
        handler({
          url: () => videoUrl,
          headers: () => ({
            'content-type': 'video/mp4',
            'content-range': `bytes 0-0/${videoBytes.length}`,
          }),
        });
      }
      return undefined;
    }),
    locator: vi.fn().mockReturnValue({ innerText: vi.fn().mockResolvedValue('正常视频笔记页面') }),
    url: vi.fn().mockReturnValue('https://www.xiaohongshu.com/search_result/feed-video?xsec_token=token'),
    close: vi.fn().mockResolvedValue(undefined),
  };
}

describe('XHS media archive', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.resetAllMocks();
    if (tempDir !== undefined) {
      rmSync(tempDir, { recursive: true, force: true });
      tempDir = undefined;
    }
  });

  it('stops safely on an XHS rate-limit page and writes partial artifacts', async () => {
    const root = createTempDir();
    const dbPath = join(root, 'xhs.sqlite');
    const outputDir = join(root, 'media');
    seedRun(dbPath, [
      { rankIndex: 1, feedId: 'feed-ok' },
      { rankIndex: 2, feedId: 'feed-rate-limited' },
    ]);
    mockBrowserWithPages([
      createPage({ url: 'https://www.xiaohongshu.com/search_result/feed-ok?xsec_token=token', bodyText: '正常笔记页面' }),
      createPage({ url: 'https://www.xiaohongshu.com/website-login/error?error_code=300013', bodyText: '访问频繁，请稍后再试' }),
    ]);

    vi.useFakeTimers();
    const archivePromise = archiveXhsRunMedia({
      runId: 1,
      dbPath,
      cdpUrl: 'http://127.0.0.1:17330',
      outputDir,
      force: false,
      resumeMissingMedia: true,
      delayMinMs: 0,
      delayMaxMs: 0,
    });
    await vi.runAllTimersAsync();
    const result = await archivePromise;

    expect(result.safetyStopped).toBe(true);
    expect(result.rows).toBe(1);
    expect(existsSync(join(outputDir, 'manifest.json'))).toBe(true);
    expect(existsSync(join(outputDir, 'summary.json'))).toBe(true);
    expect(existsSync(join(outputDir, 'safety-stop.json'))).toBe(true);
    const manifest = JSON.parse(readFileSync(join(outputDir, 'manifest.json'), 'utf8')) as Array<{ feedId: string }>;
    expect(manifest.map((entry) => entry.feedId)).toEqual(['feed-ok']);
    const safetyStop = JSON.parse(readFileSync(join(outputDir, 'safety-stop.json'), 'utf8')) as { reason: string; feedId: string; message: string };
    expect(safetyStop).toMatchObject({
      reason: 'rate_limit',
      feedId: 'feed-rate-limited',
      message: 'XHS safety stop: rate_limit',
    });
  });

  it('stops safely when complete video probing reaches an XHS safety page', async () => {
    const root = createTempDir();
    const dbPath = join(root, 'xhs.sqlite');
    const outputDir = join(root, 'media');
    seedRun(dbPath, [
      { rankIndex: 1, feedId: 'feed-video', noteType: 'video' },
    ]);
    mockBrowserWithPages([
      createPage({ url: 'https://www.xiaohongshu.com/search_result/feed-video?xsec_token=token', bodyText: '正常视频笔记页面' }),
      createPage({ url: 'https://www.xiaohongshu.com/website-login/error?error_code=300013', bodyText: '访问频繁，请稍后再试' }),
    ]);

    vi.useFakeTimers();
    const archivePromise = archiveXhsRunMedia({
      runId: 1,
      dbPath,
      cdpUrl: 'http://127.0.0.1:17330',
      outputDir,
      force: false,
      resumeMissingMedia: true,
      delayMinMs: 0,
      delayMaxMs: 0,
    });
    await vi.runAllTimersAsync();
    const result = await archivePromise;

    expect(result.safetyStopped).toBe(true);
    const manifest = JSON.parse(readFileSync(join(outputDir, 'manifest.json'), 'utf8')) as Array<{ feedId: string; status: string; videoFiles: string[] }>;
    expect(manifest).toEqual([expect.objectContaining({ feedId: 'feed-video', status: 'no_media_saved', videoFiles: [] })]);
    const safetyStop = JSON.parse(readFileSync(join(outputDir, 'safety-stop.json'), 'utf8')) as { reason: string; phase: string; feedId: string };
    expect(safetyStop).toMatchObject({
      reason: 'rate_limit',
      phase: 'complete_video',
      feedId: 'feed-video',
    });
  });

  it('does not safety-stop when normal note content mentions verification words', async () => {
    const root = createTempDir();
    const dbPath = join(root, 'xhs.sqlite');
    const outputDir = join(root, 'media');
    seedRun(dbPath, [
      { rankIndex: 1, feedId: 'feed-normal' },
    ]);
    mockBrowserWithPages([
      createPage({
        url: 'https://www.xiaohongshu.com/search_result/feed-normal?xsec_token=token',
        bodyText: '这是一篇正常笔记，内容只是提到验证码、robot 和访问频繁这些词作为科普。',
      }),
    ]);

    vi.useFakeTimers();
    const archivePromise = archiveXhsRunMedia({
      runId: 1,
      dbPath,
      cdpUrl: 'http://127.0.0.1:17330',
      outputDir,
      force: false,
      resumeMissingMedia: true,
      delayMinMs: 0,
      delayMaxMs: 0,
    });
    await vi.runAllTimersAsync();
    const result = await archivePromise;

    expect(result.safetyStopped).toBe(false);
    expect(existsSync(join(outputDir, 'safety-stop.json'))).toBe(false);
    const manifest = JSON.parse(readFileSync(join(outputDir, 'manifest.json'), 'utf8')) as Array<{ feedId: string; status: string }>;
    expect(manifest).toEqual([expect.objectContaining({ feedId: 'feed-normal', status: 'no_media_saved' })]);
  });

  it('does not safety-stop on a normal note URL that discusses strong challenge phrases', async () => {
    const root = createTempDir();
    const dbPath = join(root, 'xhs.sqlite');
    const outputDir = join(root, 'media');
    seedRun(dbPath, [
      { rankIndex: 1, feedId: 'feed-article' },
    ]);
    mockBrowserWithPages([
      createPage({
        url: 'https://www.xiaohongshu.com/search_result/feed-article?xsec_token=token',
        bodyText: '这是一篇正常笔记，讨论 App 出现请完成安全验证、滑块验证、验证码和 robot 提示时该怎么办。',
      }),
    ]);

    vi.useFakeTimers();
    const archivePromise = archiveXhsRunMedia({
      runId: 1,
      dbPath,
      cdpUrl: 'http://127.0.0.1:17330',
      outputDir,
      force: false,
      resumeMissingMedia: true,
      delayMinMs: 0,
      delayMaxMs: 0,
    });
    await vi.runAllTimersAsync();
    const result = await archivePromise;

    expect(result.safetyStopped).toBe(false);
    expect(existsSync(join(outputDir, 'safety-stop.json'))).toBe(false);
    const manifest = JSON.parse(readFileSync(join(outputDir, 'manifest.json'), 'utf8')) as Array<{ feedId: string; status: string }>;
    expect(manifest).toEqual([expect.objectContaining({ feedId: 'feed-article', status: 'no_media_saved' })]);
  });

  it('returns without CDP when all existing manifest entries are complete', async () => {
    const root = createTempDir();
    const dbPath = join(root, 'xhs.sqlite');
    const outputDir = join(root, 'media');
    const existingImage = join(outputDir, 'existing.webp');
    seedRun(dbPath, [
      { rankIndex: 1, feedId: 'feed-complete' },
    ]);
    mkdirSync(outputDir, { recursive: true });
    writeFileSync(existingImage, 'image-bytes');
    writeFileSync(join(outputDir, 'manifest.json'), JSON.stringify([
      imageManifestEntry({ feedId: 'feed-complete', rankIndex: 1, imageFile: existingImage }),
    ]), 'utf8');

    const result = await archiveXhsRunMedia({
      runId: 1,
      dbPath,
      cdpUrl: 'http://127.0.0.1:17330',
      outputDir,
      force: false,
      resumeMissingMedia: true,
      delayMinMs: 0,
      delayMaxMs: 0,
    });

    expect(playwrightMocks.connectOverCDP).not.toHaveBeenCalled();
    expect(result.rows).toBe(1);
    const manifest = JSON.parse(readFileSync(join(outputDir, 'manifest.json'), 'utf8')) as Array<{ feedId: string; imageFiles: string[] }>;
    expect(manifest).toEqual([expect.objectContaining({ feedId: 'feed-complete', imageFiles: [existingImage] })]);
  });

  it('skips existing complete video entries whose initial capture saved no media', async () => {
    const root = createTempDir();
    const dbPath = join(root, 'xhs.sqlite');
    const outputDir = join(root, 'media');
    const existingDir = join(outputDir, 'existing');
    mkdirSync(existingDir, { recursive: true });
    const existingVideo = join(existingDir, 'feed-video.mp4');
    writeFileSync(existingVideo, Buffer.alloc(2048));
    seedRun(dbPath, [
      { rankIndex: 1, feedId: 'feed-video', noteType: 'video' },
    ]);
    writeFileSync(join(outputDir, 'manifest.json'), JSON.stringify([
      completeVideoManifestEntry({
        feedId: 'feed-video',
        rankIndex: 1,
        videoFile: existingVideo,
        status: 'no_media_saved',
        completeVideoStatus: 'complete_short_mp4_structure_verified',
      }),
    ]), 'utf8');

    const result = await archiveXhsRunMedia({
      runId: 1,
      dbPath,
      cdpUrl: 'http://127.0.0.1:17330',
      outputDir,
      force: false,
      resumeMissingMedia: true,
      delayMinMs: 0,
      delayMaxMs: 0,
    });

    expect(playwrightMocks.connectOverCDP).not.toHaveBeenCalled();
    expect(result.rows).toBe(1);
    expect(result.success).toBe(1);
    expect(result.noMediaSaved).toBe(0);
    expect(result.completeVideos).toBe(1);
    expect(result.incompleteVideos).toBe(0);
    const manifest = JSON.parse(readFileSync(join(outputDir, 'manifest.json'), 'utf8')) as Array<{ feedId: string; status: string; videoFiles: string[]; completeVideoStatus: string }>;
    expect(manifest).toEqual([
      expect.objectContaining({
        feedId: 'feed-video',
        status: 'success',
        videoFiles: [existingVideo],
        completeVideoStatus: 'complete_short_mp4_structure_verified',
      }),
    ]);
  });

  it('marks a video complete when range fetch succeeds after initial capture saves no media', async () => {
    const root = createTempDir();
    const dbPath = join(root, 'xhs.sqlite');
    const outputDir = join(root, 'media');
    const videoBytes = Buffer.alloc(2048, 1);
    seedRun(dbPath, [
      { rankIndex: 1, feedId: 'feed-video', noteType: 'video' },
    ]);
    mockBrowserWithPages([
      createPage({ url: 'https://www.xiaohongshu.com/search_result/feed-video?xsec_token=token', bodyText: '正常视频笔记页面' }),
      createCompleteVideoProbePage(videoBytes),
    ]);

    vi.useFakeTimers();
    const archivePromise = archiveXhsRunMedia({
      runId: 1,
      dbPath,
      cdpUrl: 'http://127.0.0.1:17330',
      outputDir,
      force: false,
      resumeMissingMedia: true,
      delayMinMs: 0,
      delayMaxMs: 0,
      blockSize: 1024,
    });
    await vi.runAllTimersAsync();
    const result = await archivePromise;

    expect(result.success).toBe(1);
    expect(result.noMediaSaved).toBe(0);
    expect(result.videoFiles).toBe(1);
    expect(result.completeVideos).toBe(1);
    expect(result.incompleteVideos).toBe(0);
    const manifest = JSON.parse(readFileSync(join(outputDir, 'manifest.json'), 'utf8')) as Array<{
      status: string;
      videoCount: number;
      videoFiles: string[];
      completeVideoStatus: string;
      completeVideoFile: string;
    }>;
    expect(manifest).toHaveLength(1);
    expect(manifest[0].status).toBe('success');
    expect(manifest[0].videoCount).toBe(1);
    expect(manifest[0].videoFiles).toEqual([manifest[0].completeVideoFile]);
    expect(manifest[0].completeVideoStatus).toBe('complete');
    expect(existsSync(manifest[0].completeVideoFile)).toBe(true);
  });

  it('resumes by default and skips existing successful complete media entries', async () => {
    const root = createTempDir();
    const dbPath = join(root, 'xhs.sqlite');
    const outputDir = join(root, 'media');
    const existingDir = join(outputDir, 'existing');
    mkdirSync(existingDir, { recursive: true });
    const existingImage = join(existingDir, 'feed-complete.webp');
    writeFileSync(existingImage, 'image-bytes');
    seedRun(dbPath, [
      { rankIndex: 1, feedId: 'feed-complete' },
      { rankIndex: 2, feedId: 'feed-failed' },
      { rankIndex: 3, feedId: 'feed-missing' },
    ]);
    mkdirSync(outputDir, { recursive: true });
    writeFileSync(join(outputDir, 'manifest.json'), JSON.stringify([
      imageManifestEntry({ feedId: 'feed-complete', rankIndex: 1, imageFile: existingImage }),
      imageManifestEntry({ feedId: 'feed-failed', rankIndex: 2, imageFile: existingImage, status: 'no_media_saved' }),
    ]), 'utf8');
    const { context } = mockBrowserWithPages([
      createPage({ url: 'https://www.xiaohongshu.com/search_result/feed-failed?xsec_token=token', bodyText: '正常笔记页面' }),
      createPage({ url: 'https://www.xiaohongshu.com/search_result/feed-missing?xsec_token=token', bodyText: '正常笔记页面' }),
      createPage({ url: 'https://www.xiaohongshu.com/search_result/unexpected?xsec_token=token', bodyText: '不应打开' }),
    ]);

    vi.useFakeTimers();
    const archivePromise = archiveXhsRunMedia({
      runId: 1,
      dbPath,
      cdpUrl: 'http://127.0.0.1:17330',
      outputDir,
      force: false,
      resumeMissingMedia: true,
      delayMinMs: 0,
      delayMaxMs: 0,
    });
    await vi.runAllTimersAsync();
    const result = await archivePromise;

    expect(playwrightMocks.connectOverCDP).toHaveBeenCalledWith('http://127.0.0.1:17330');
    expect(context.newPage).toHaveBeenCalledTimes(2);
    expect(result.rows).toBe(3);
    const manifest = JSON.parse(readFileSync(join(outputDir, 'manifest.json'), 'utf8')) as Array<{ feedId: string; status: string; imageFiles: string[] }>;
    expect(manifest.map((entry) => entry.feedId)).toEqual(['feed-complete', 'feed-failed', 'feed-missing']);
    expect(manifest[0]).toMatchObject({ feedId: 'feed-complete', status: 'success', imageFiles: [existingImage] });
  });

  it('reprocesses existing manifest entries when referenced media files are empty or missing', async () => {
    const root = createTempDir();
    const dbPath = join(root, 'xhs.sqlite');
    const outputDir = join(root, 'media');
    const emptyImage = join(outputDir, 'empty.webp');
    seedRun(dbPath, [
      { rankIndex: 1, feedId: 'feed-empty' },
      { rankIndex: 2, feedId: 'feed-missing-video', noteType: 'video' },
    ]);
    mkdirSync(outputDir, { recursive: true });
    writeFileSync(emptyImage, '');
    writeFileSync(join(outputDir, 'manifest.json'), JSON.stringify([
      imageManifestEntry({ feedId: 'feed-empty', rankIndex: 1, imageFile: emptyImage }),
      completeVideoManifestEntry({ feedId: 'feed-missing-video', rankIndex: 2, videoFile: join(outputDir, 'missing.mp4') }),
    ]), 'utf8');
    const { context } = mockBrowserWithPages([
      createPage({ url: 'https://www.xiaohongshu.com/search_result/feed-empty?xsec_token=token', bodyText: '正常笔记页面' }),
      createPage({ url: 'https://www.xiaohongshu.com/search_result/feed-missing-video?xsec_token=token', bodyText: '正常视频笔记页面' }),
      createPage({ url: 'https://www.xiaohongshu.com/search_result/feed-missing-video?xsec_token=token', bodyText: '正常视频笔记页面' }),
    ]);

    vi.useFakeTimers();
    const archivePromise = archiveXhsRunMedia({
      runId: 1,
      dbPath,
      cdpUrl: 'http://127.0.0.1:17330',
      outputDir,
      force: false,
      resumeMissingMedia: true,
      delayMinMs: 0,
      delayMaxMs: 0,
    });
    await vi.runAllTimersAsync();
    const result = await archivePromise;

    expect(playwrightMocks.connectOverCDP).toHaveBeenCalledWith('http://127.0.0.1:17330');
    expect(context.newPage).toHaveBeenCalledTimes(3);
    expect(result.rows).toBe(2);
  });

  it('requires complete video file size to match recorded bytes before resuming', async () => {
    const root = createTempDir();
    const dbPath = join(root, 'xhs.sqlite');
    const outputDir = join(root, 'media');
    const existingVideo = join(outputDir, 'existing.mp4');
    seedRun(dbPath, [
      { rankIndex: 1, feedId: 'feed-video', noteType: 'video' },
    ]);
    mkdirSync(outputDir, { recursive: true });
    writeFileSync(existingVideo, Buffer.alloc(1024));
    writeFileSync(join(outputDir, 'manifest.json'), JSON.stringify([
      completeVideoManifestEntry({ feedId: 'feed-video', rankIndex: 1, videoFile: existingVideo }),
    ]), 'utf8');
    const { context } = mockBrowserWithPages([
      createPage({ url: 'https://www.xiaohongshu.com/search_result/feed-video?xsec_token=token', bodyText: '正常视频笔记页面' }),
      createPage({ url: 'https://www.xiaohongshu.com/search_result/feed-video?xsec_token=token', bodyText: '正常视频笔记页面' }),
    ]);

    vi.useFakeTimers();
    const archivePromise = archiveXhsRunMedia({
      runId: 1,
      dbPath,
      cdpUrl: 'http://127.0.0.1:17330',
      outputDir,
      force: false,
      resumeMissingMedia: true,
      delayMinMs: 0,
      delayMaxMs: 0,
    });
    await vi.runAllTimersAsync();
    const result = await archivePromise;

    expect(playwrightMocks.connectOverCDP).toHaveBeenCalledWith('http://127.0.0.1:17330');
    expect(context.newPage).toHaveBeenCalledTimes(2);
    expect(result.rows).toBe(1);
  });

  it('removes stale safety-stop artifacts after a later successful resume', async () => {
    const root = createTempDir();
    const dbPath = join(root, 'xhs.sqlite');
    const outputDir = join(root, 'media');
    const existingImage = join(outputDir, 'existing.webp');
    seedRun(dbPath, [
      { rankIndex: 1, feedId: 'feed-complete' },
    ]);
    mkdirSync(outputDir, { recursive: true });
    writeFileSync(existingImage, 'image-bytes');
    writeFileSync(join(outputDir, 'manifest.json'), JSON.stringify([
      imageManifestEntry({ feedId: 'feed-complete', rankIndex: 1, imageFile: existingImage }),
    ]), 'utf8');
    writeFileSync(join(outputDir, 'safety-stop.json'), JSON.stringify({ stale: true }), 'utf8');

    const result = await archiveXhsRunMedia({
      runId: 1,
      dbPath,
      cdpUrl: 'http://127.0.0.1:17330',
      outputDir,
      force: false,
      resumeMissingMedia: true,
      delayMinMs: 0,
      delayMaxMs: 0,
    });

    expect(result.safetyStopped).toBe(false);
    expect(playwrightMocks.connectOverCDP).not.toHaveBeenCalled();
    expect(existsSync(join(outputDir, 'safety-stop.json'))).toBe(false);
  });

  it('keeps media captured for current video row when complete-video probing safety-stops', async () => {
    const root = createTempDir();
    const dbPath = join(root, 'xhs.sqlite');
    const outputDir = join(root, 'media');
    seedRun(dbPath, [
      { rankIndex: 1, feedId: 'feed-video', noteType: 'video' },
    ]);
    mockBrowserWithPages([
      createPage({
        url: 'https://www.xiaohongshu.com/search_result/feed-video?xsec_token=token',
        bodyText: '正常视频笔记页面',
        mediaResponses: [{
          url: 'https://sns-video-v4.xhscdn.com/feed-video.mp4',
          contentType: 'video/mp4',
          body: Buffer.alloc(2048, 1),
        }],
      }),
      createPage({ url: 'https://www.xiaohongshu.com/website-login/error?error_code=300013', bodyText: '访问频繁，请稍后再试' }),
    ]);

    vi.useFakeTimers();
    const archivePromise = archiveXhsRunMedia({
      runId: 1,
      dbPath,
      cdpUrl: 'http://127.0.0.1:17330',
      outputDir,
      force: false,
      resumeMissingMedia: true,
      delayMinMs: 0,
      delayMaxMs: 0,
    });
    await vi.runAllTimersAsync();
    const result = await archivePromise;

    expect(result.safetyStopped).toBe(true);
    const manifest = JSON.parse(readFileSync(join(outputDir, 'manifest.json'), 'utf8')) as Array<{ feedId: string; status: string; videoFiles: string[] }>;
    expect(manifest).toHaveLength(1);
    expect(manifest[0].feedId).toBe('feed-video');
    expect(manifest[0].status).toBe('success');
    expect(manifest[0].videoFiles).toHaveLength(1);
    expect(existsSync(manifest[0].videoFiles[0])).toBe(true);
  });

  it('matches duplicate feedId resume entries one-to-one by row identity instead of reusing one entry', async () => {
    const root = createTempDir();
    const dbPath = join(root, 'xhs.sqlite');
    const outputDir = join(root, 'media');
    const existingImage = join(outputDir, 'existing.webp');
    seedRun(dbPath, [
      { rankIndex: 1, feedId: 'same-feed', sortKey: 'latest', sortLabel: '最新' },
      { rankIndex: 2, feedId: 'same-feed', sortKey: 'most_liked', sortLabel: '最多点赞' },
    ]);
    mkdirSync(outputDir, { recursive: true });
    writeFileSync(existingImage, 'image-bytes');
    writeFileSync(join(outputDir, 'manifest.json'), JSON.stringify([
      imageManifestEntry({ feedId: 'same-feed', rankIndex: 1, imageFile: existingImage }),
    ]), 'utf8');
    const { context } = mockBrowserWithPages([
      createPage({ url: 'https://www.xiaohongshu.com/search_result/same-feed?xsec_token=token', bodyText: '正常笔记页面' }),
    ]);

    vi.useFakeTimers();
    const archivePromise = archiveXhsRunMedia({
      runId: 1,
      dbPath,
      cdpUrl: 'http://127.0.0.1:17330',
      outputDir,
      force: false,
      resumeMissingMedia: true,
      delayMinMs: 0,
      delayMaxMs: 0,
    });
    await vi.runAllTimersAsync();
    const result = await archivePromise;

    expect(context.newPage).toHaveBeenCalledTimes(1);
    expect(result.rows).toBe(2);
    const manifest = JSON.parse(readFileSync(join(outputDir, 'manifest.json'), 'utf8')) as Array<{ feedId: string; rankIndex: number; imageFiles: string[] }>;
    expect(manifest).toHaveLength(2);
    expect(manifest[0]).toMatchObject({ feedId: 'same-feed', rankIndex: 1, imageFiles: [existingImage] });
    expect(manifest[1]).toMatchObject({ feedId: 'same-feed', rankIndex: 2, imageFiles: [] });
  });
});

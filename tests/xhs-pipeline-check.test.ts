import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { openDatabase } from '../src/db/client.js';
import { initializeSchema } from '../src/db/schema.js';
import { checkXhsPipeline } from '../src/xhs-pipeline-check.js';

let tempDir: string | undefined;

function createTempDir(): string {
  tempDir = mkdtempSync(join(tmpdir(), 'xhs-pipeline-check-test-'));
  return tempDir;
}

function createDb(dbPath: string): void {
  const db = openDatabase(dbPath);
  initializeSchema(db);
  db.close();
}

function seedRun(dbPath: string, status = 'success'): void {
  const db = openDatabase(dbPath);
  initializeSchema(db);
  db.prepare(`insert into xhs_search_runs (id, source, source_run_id, keyword, sorts_json, limit_per_sort, with_details, status) values (1, 'manual_keyword', null, '浴缸', '["most_liked"]', 20, 1, ?)`)
    .run(status);
  db.close();
}

function seedCompleteRun(dbPath: string, root: string): { manifestPath: string; syncReportPath: string } {
  const db = openDatabase(dbPath);
  initializeSchema(db);
  db.prepare(`insert into xhs_search_runs (id, source, source_run_id, keyword, sorts_json, limit_per_sort, with_details, status) values (1, 'manual_keyword', null, '浴缸', '["most_liked"]', 20, 1, 'success')`).run();
  db.prepare(`
    insert into xhs_search_notes (
      run_id, keyword, sort_key, sort_label, rank_index, feed_id, xsec_token, search_result_url,
      title, author_name, detail_text, detail_tags_json, detail_like_text, detail_collect_text,
      detail_comment_count_text, detail_share_text, note_type, source_topic_texts_json,
      source_comments_json, media_sources_json, raw_card_text
    ) values (
      1, '浴缸', 'most_liked', '最多点赞', 1, 'feed1', 'token', 'https://www.xiaohongshu.com/search_result/feed1?xsec_token=token',
      '浴缸标题', '作者A', '正文', '["浴缸","装修"]', '100', '20', '3', '1', 'video', '["浴缸"]', '["想知道尺寸"]', '[{"url":"https://example.com/image.webp","type":"image"}]', '浴缸标题'
    )
  `).run();
  db.close();

  const mediaDir = join(root, 'media');
  mkdirSync(mediaDir, { recursive: true });
  const imageFile = join(mediaDir, 'image.webp');
  const videoFile = join(mediaDir, 'video.mp4');
  writeFileSync(imageFile, 'image-bytes');
  writeFileSync(videoFile, 'video-bytes');

  const manifestPath = join(root, 'manifest.json');
  writeFileSync(manifestPath, JSON.stringify([{
    rankIndex: 1,
    feedId: 'feed1',
    title: '浴缸标题',
    noteType: 'video',
    keyword: '浴缸',
    sortLabel: '最多点赞',
    searchResultUrl: 'https://www.xiaohongshu.com/search_result/feed1?xsec_token=token',
    exploreUrl: null,
    tags: ['浴缸'],
    topics: ['浴缸'],
    sourceMediaUrls: [],
    status: 'success',
    imageCount: 1,
    videoCount: 1,
    imageFiles: [imageFile],
    videoFiles: [videoFile],
    saved: [],
    errors: [],
    completeVideoStatus: 'complete',
    completeVideoFile: videoFile,
    completeVideoBytes: 11,
    completeVideoCoveredBytes: 11,
    completeVideoChunkCount: 1,
    completeVideoGaps: [],
  }]), 'utf8');

  const syncReportPath = join(root, 'sync-report.json');
  writeFileSync(syncReportPath, JSON.stringify({
    runId: 1,
    dryRun: false,
    rowCount: 1,
    created: 1,
    updated: 0,
    failed: 0,
    ensuredFields: [],
    records: [{ feedId: 'feed1', title: '浴缸标题', status: 'success', fields: { 笔记ID: 'feed1', 标题: '浴缸标题' } }],
  }), 'utf8');

  return { manifestPath, syncReportPath };
}

describe('XHS pipeline check', () => {
  afterEach(() => {
    if (tempDir !== undefined) {
      rmSync(tempDir, { recursive: true, force: true });
      tempDir = undefined;
    }
  });

  it('returns failed when the XHS run is missing', () => {
    const root = createTempDir();
    const dbPath = join(root, 'xhs.sqlite');
    createDb(dbPath);

    const result = checkXhsPipeline({ runId: 999, dbPath, outputDir: join(root, 'check') });

    expect(result.status).toBe('failed');
    expect(result.blockingIssues).toContainEqual(expect.objectContaining({ code: 'run_missing' }));
    expect(result.agent.ready).toBe(false);
  });

  it('returns failed when the XHS run has no notes', () => {
    const root = createTempDir();
    const dbPath = join(root, 'xhs.sqlite');
    seedRun(dbPath);

    const result = checkXhsPipeline({ runId: 1, dbPath, outputDir: join(root, 'check') });

    expect(result.status).toBe('failed');
    expect(result.counts.notes).toBe(0);
    expect(result.blockingIssues).toContainEqual(expect.objectContaining({ code: 'notes_empty' }));
    expect(result.agent.ready).toBe(false);
  });

  it('returns complete when notes, media manifest, and Feishu sync report align', () => {
    const root = createTempDir();
    const dbPath = join(root, 'xhs.sqlite');
    const { manifestPath, syncReportPath } = seedCompleteRun(dbPath, root);

    const result = checkXhsPipeline({ runId: 1, dbPath, manifestPath, syncReportPath, outputDir: join(root, 'check') });

    expect(result.status).toBe('complete');
    expect(result.counts.notes).toBe(1);
    expect(result.counts.details).toBe(1);
    expect(result.counts.tags).toBe(1);
    expect(result.counts.mediaSources).toBe(1);
    expect(result.counts.manifestEntries).toBe(1);
    expect(result.counts.manifestMatchedFeeds).toBe(1);
    expect(result.counts.feishuSyncedRecords).toBe(1);
    expect(result.agent.ready).toBe(true);
    expect(result.agent.inputContractVersion).toBe('xhs-analysis-source/v1');
  });

  it('returns partial when the media manifest is missing but database notes exist', () => {
    const root = createTempDir();
    const dbPath = join(root, 'xhs.sqlite');
    const { syncReportPath } = seedCompleteRun(dbPath, root);

    const result = checkXhsPipeline({ runId: 1, dbPath, manifestPath: join(root, 'missing-manifest.json'), syncReportPath, outputDir: join(root, 'check') });

    expect(result.status).toBe('partial');
    expect(result.warnings).toContainEqual(expect.objectContaining({ code: 'manifest_missing' }));
    expect(result.agent.ready).toBe(true);
  });

  it('returns partial when the Feishu sync report is missing but database notes exist', () => {
    const root = createTempDir();
    const dbPath = join(root, 'xhs.sqlite');
    const { manifestPath } = seedCompleteRun(dbPath, root);

    const result = checkXhsPipeline({ runId: 1, dbPath, manifestPath, syncReportPath: join(root, 'missing-sync-report.json'), outputDir: join(root, 'check') });

    expect(result.status).toBe('partial');
    expect(result.warnings).toContainEqual(expect.objectContaining({ code: 'sync_report_missing' }));
    expect(result.agent.ready).toBe(true);
  });

  it('surfaces oversized video warnings from Feishu sync report records', () => {
    const root = createTempDir();
    const dbPath = join(root, 'xhs.sqlite');
    const { manifestPath, syncReportPath } = seedCompleteRun(dbPath, root);
    writeFileSync(syncReportPath, JSON.stringify({
      runId: 1,
      dryRun: false,
      rowCount: 1,
      created: 1,
      updated: 0,
      failed: 0,
      records: [{
        feedId: 'feed1',
        title: '浴缸标题',
        status: 'success',
        fields: { 笔记ID: 'feed1', 同步错误: 'skip oversized video: video.mp4 25000000 bytes > 20971520 bytes' },
      }],
    }), 'utf8');

    const result = checkXhsPipeline({ runId: 1, dbPath, manifestPath, syncReportPath, outputDir: join(root, 'check') });

    expect(result.status).toBe('partial');
    expect(result.warnings).toContainEqual(expect.objectContaining({ code: 'oversized_video_skipped' }));
  });

  it('writes JSON and Markdown reports without generating content ideas', () => {
    const root = createTempDir();
    const dbPath = join(root, 'xhs.sqlite');
    const { manifestPath, syncReportPath } = seedCompleteRun(dbPath, root);
    const outputDir = join(root, 'check');

    const result = checkXhsPipeline({ runId: 1, dbPath, manifestPath, syncReportPath, outputDir });

    expect(existsSync(result.paths.jsonPath)).toBe(true);
    expect(existsSync(result.paths.markdownPath)).toBe(true);
    const report = JSON.parse(readFileSync(result.paths.jsonPath, 'utf8')) as { status: string; agent: { inputContractVersion: string } };
    expect(report.status).toBe('complete');
    expect(report.agent.inputContractVersion).toBe('xhs-analysis-source/v1');
    const markdown = readFileSync(result.paths.markdownPath, 'utf8');
    expect(markdown).toContain('小红书采集入库检查报告');
    expect(markdown).not.toContain('选题');
    expect(markdown).not.toContain('标题生成');
    expect(markdown).not.toContain('文案');
  });
});

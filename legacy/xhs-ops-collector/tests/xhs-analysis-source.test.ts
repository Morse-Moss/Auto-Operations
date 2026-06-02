import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { openDatabase } from '../src/db/client.js';
import { initializeSchema } from '../src/db/schema.js';
import { buildXhsAnalysisSource } from '../src/xhs-analysis-source.js';

let tempDir: string | undefined;

function createTempDir(): string {
  tempDir = mkdtempSync(join(tmpdir(), 'xhs-analysis-source-test-'));
  return tempDir;
}

function seedRun(dbPath: string): void {
  const db = openDatabase(dbPath);
  initializeSchema(db);
  db.prepare(`
    insert into xhs_search_runs (
      id, source, source_run_id, keyword, sorts_json, limit_per_sort, with_details,
      status, started_at, finished_at
    ) values (
      1, 'manual_keyword', null, '浴缸', '["most_liked"]', 20, 1,
      'success', '2026-05-31T10:00:00.000Z', '2026-05-31T10:05:00.000Z'
    )
  `).run();
  db.close();
}

function seedCompleteRun(dbPath: string): void {
  seedRun(dbPath);
  const db = openDatabase(dbPath);
  db.prepare(`
    insert into xhs_search_notes (
      run_id, keyword, sort_key, sort_label, rank_index, feed_id, xsec_token, search_result_url,
      title, author_name, detail_text, raw_detail_text, analysis_source_text,
      detail_tags_json, detail_like_text, detail_collect_text, detail_comment_count_text,
      detail_share_text, note_type, source_topic_texts_json, source_comments_json,
      media_sources_json, raw_card_text
    ) values (
      1, '浴缸', 'most_liked', '最多点赞', 1, 'feed1', 'token',
      'https://www.xiaohongshu.com/search_result/feed1?xsec_token=token',
      '浴缸标题', '作者A', '正文', '原始详情', '分析文本',
      '["浴缸","装修"]', '100', '20', '3', '1', 'video',
      '["浴缸话题"]', '["想知道尺寸"]',
      '[{"url":"https://example.com/image.webp","type":"image"}]', '浴缸标题'
    )
  `).run();
  db.close();
}

function writeArtifacts(root: string): { manifestPath: string; syncReportPath: string; pipelineCheckPath: string } {
  const mediaDir = join(root, 'media');
  mkdirSync(mediaDir, { recursive: true });
  const imageFile = join(mediaDir, 'image.webp');
  const videoFile = join(mediaDir, 'video.mp4');
  writeFileSync(imageFile, 'image-bytes', 'utf8');
  writeFileSync(videoFile, 'video-bytes', 'utf8');

  const manifestPath = join(root, 'manifest.json');
  writeFileSync(manifestPath, JSON.stringify([{
    feedId: 'feed1',
    status: 'success',
    imageFiles: [imageFile],
    videoFiles: [videoFile],
    completeVideoFile: videoFile,
    completeVideoStatus: 'complete',
    sourceMediaUrls: ['https://example.com/image.webp'],
  }]), 'utf8');

  const syncReportPath = join(root, 'sync-report.json');
  writeFileSync(syncReportPath, JSON.stringify({
    records: [{ feedId: 'feed1', status: 'success', fields: { 笔记ID: 'feed1' } }],
  }), 'utf8');

  const pipelineCheckPath = join(root, 'check.json');
  writeFileSync(pipelineCheckPath, JSON.stringify({ status: 'complete', warnings: [], agent: { ready: true } }), 'utf8');

  return { manifestPath, syncReportPath, pipelineCheckPath };
}

describe('XHS analysis source', () => {
  afterEach(() => {
    if (tempDir !== undefined) {
      rmSync(tempDir, { recursive: true, force: true });
      tempDir = undefined;
    }
  });

  it('throws a clear error and does not write a usable package when run is missing', () => {
    const root = createTempDir();
    const dbPath = join(root, 'xhs.sqlite');
    const outputDir = join(root, 'analysis-source');
    const db = openDatabase(dbPath);
    initializeSchema(db);
    db.close();
    const { manifestPath, syncReportPath, pipelineCheckPath } = writeArtifacts(root);

    expect(() => buildXhsAnalysisSource({
      runId: 999,
      dbPath,
      manifestPath,
      syncReportPath,
      pipelineCheckPath,
      outputDir,
    })).toThrow('XHS search run 999 not found');
    expect(existsSync(join(outputDir, 'source.json'))).toBe(false);
    expect(existsSync(join(outputDir, 'notes.jsonl'))).toBe(false);
  });

  it('throws a clear error when run has zero notes', () => {
    const root = createTempDir();
    const dbPath = join(root, 'xhs.sqlite');
    const outputDir = join(root, 'analysis-source');
    seedRun(dbPath);
    const { manifestPath, syncReportPath, pipelineCheckPath } = writeArtifacts(root);

    expect(() => buildXhsAnalysisSource({
      runId: 1,
      dbPath,
      manifestPath,
      syncReportPath,
      pipelineCheckPath,
      outputDir,
    })).toThrow('XHS search run 1 has zero notes');
  });

  it('writes source.json and notes.jsonl for a complete XHS run', () => {
    const root = createTempDir();
    const dbPath = join(root, 'xhs.sqlite');
    const outputDir = join(root, 'analysis-source');
    seedCompleteRun(dbPath);
    const { manifestPath, syncReportPath, pipelineCheckPath } = writeArtifacts(root);

    const result = buildXhsAnalysisSource({
      runId: 1,
      dbPath,
      manifestPath,
      syncReportPath,
      pipelineCheckPath,
      outputDir,
    });

    expect(result.contractVersion).toBe('xhs-analysis-source/v1');
    expect(readFileSync(result.files.sourceJson, 'utf8')).not.toBe('');
    expect(readFileSync(result.files.notesJsonl, 'utf8')).not.toBe('');

    const source = JSON.parse(readFileSync(result.files.sourceJson, 'utf8')) as {
      counts: { notes: number };
      pipeline: { status: string; agentReady: boolean; warnings: unknown[] };
    };
    expect(source.counts.notes).toBe(1);
    expect(source.pipeline.status).toBe('complete');
    expect(source.pipeline.agentReady).toBe(true);
    expect(source.pipeline.warnings).toEqual([]);

    const lines = readFileSync(result.files.notesJsonl, 'utf8').trim().split('\n');
    expect(lines).toHaveLength(1);
    const note = JSON.parse(lines[0]) as {
      feedId: string;
      media: { localImages: string[] };
      feishu: { synced: boolean };
    };
    expect(note.feedId).toBe('feed1');
    expect(note.media.localImages).toHaveLength(1);
    expect(note.feishu.synced).toBe(true);
  });

  it('keeps notes with empty parsed arrays and warns when note JSON fields are invalid', () => {
    const root = createTempDir();
    const dbPath = join(root, 'xhs.sqlite');
    const outputDir = join(root, 'analysis-source');
    seedCompleteRun(dbPath);
    const db = openDatabase(dbPath);
    db.prepare(`
      update xhs_search_notes
      set detail_tags_json = ?, media_sources_json = ?
      where feed_id = ?
    `).run('{bad-json', '{bad-json', 'feed1');
    db.close();
    const { manifestPath, syncReportPath, pipelineCheckPath } = writeArtifacts(root);

    const result = buildXhsAnalysisSource({
      runId: 1,
      dbPath,
      manifestPath,
      syncReportPath,
      pipelineCheckPath,
      outputDir,
    });

    const source = JSON.parse(readFileSync(result.files.sourceJson, 'utf8')) as {
      warnings: Array<{ code: string; message: string }>;
    };
    expect(source.warnings).toContainEqual(expect.objectContaining({
      code: 'invalid_json_field',
      message: expect.stringContaining('detail_tags_json'),
    }));
    expect(source.warnings).toContainEqual(expect.objectContaining({
      code: 'invalid_json_field',
      message: expect.stringContaining('media_sources_json'),
    }));

    const lines = readFileSync(result.files.notesJsonl, 'utf8').trim().split('\n');
    expect(lines).toHaveLength(1);
    const note = JSON.parse(lines[0]) as {
      tags: unknown[];
      mediaSources: unknown[];
      quality: { hasTags: boolean; hasMediaSource: boolean };
    };
    expect(note.tags).toEqual([]);
    expect(note.mediaSources).toEqual([]);
    expect(note.quality.hasTags).toBe(false);
    expect(note.quality.hasMediaSource).toBe(false);
  });

  it('marks local media present when only complete video file exists', () => {
    const root = createTempDir();
    const dbPath = join(root, 'xhs.sqlite');
    const outputDir = join(root, 'analysis-source');
    seedCompleteRun(dbPath);
    const { manifestPath, syncReportPath, pipelineCheckPath } = writeArtifacts(root);
    const completeVideoFile = join(root, 'media', 'video.mp4');
    writeFileSync(manifestPath, JSON.stringify([{
      feedId: 'feed1',
      status: 'success',
      imageFiles: [],
      videoFiles: [],
      completeVideoFile,
      completeVideoStatus: 'complete',
      sourceMediaUrls: ['https://example.com/image.webp'],
    }]), 'utf8');

    const result = buildXhsAnalysisSource({
      runId: 1,
      dbPath,
      manifestPath,
      syncReportPath,
      pipelineCheckPath,
      outputDir,
    });

    const lines = readFileSync(result.files.notesJsonl, 'utf8').trim().split('\n');
    expect(lines).toHaveLength(1);
    const note = JSON.parse(lines[0]) as {
      media: { localImages: string[]; localVideos: string[]; completeVideoFile: string | null };
      quality: { hasLocalMedia: boolean };
    };
    expect(note.media.localImages).toEqual([]);
    expect(note.media.localVideos).toEqual([]);
    expect(note.media.completeVideoFile).toBe(completeVideoFile);
    expect(note.quality.hasLocalMedia).toBe(true);
  });

  it('keeps notes and warns when manifest is missing', () => {
    const root = createTempDir();
    const dbPath = join(root, 'xhs.sqlite');
    const outputDir = join(root, 'analysis-source');
    seedCompleteRun(dbPath);
    const { manifestPath, syncReportPath, pipelineCheckPath } = writeArtifacts(root);
    rmSync(manifestPath);

    const result = buildXhsAnalysisSource({
      runId: 1,
      dbPath,
      manifestPath,
      syncReportPath,
      pipelineCheckPath,
      outputDir,
    });

    const source = JSON.parse(readFileSync(result.files.sourceJson, 'utf8')) as {
      warnings: Array<{ code: string }>;
    };
    expect(source.warnings).toContainEqual(expect.objectContaining({ code: 'manifest_missing' }));

    const lines = readFileSync(result.files.notesJsonl, 'utf8').trim().split('\n');
    expect(lines).toHaveLength(1);
    const note = JSON.parse(lines[0]) as { media: { status: string | null; localImages: string[] } };
    expect(note.media.status).toBeNull();
    expect(note.media.localImages).toEqual([]);
  });

  it('keeps notes and warns when manifest JSON is invalid', () => {
    const root = createTempDir();
    const dbPath = join(root, 'xhs.sqlite');
    const outputDir = join(root, 'analysis-source');
    seedCompleteRun(dbPath);
    const { manifestPath, syncReportPath, pipelineCheckPath } = writeArtifacts(root);
    writeFileSync(manifestPath, '{bad-json', 'utf8');

    const result = buildXhsAnalysisSource({
      runId: 1,
      dbPath,
      manifestPath,
      syncReportPath,
      pipelineCheckPath,
      outputDir,
    });

    const source = JSON.parse(readFileSync(result.files.sourceJson, 'utf8')) as {
      warnings: Array<{ code: string; message: string }>;
    };
    expect(source.warnings).toContainEqual(expect.objectContaining({
      code: 'invalid_json_file',
      message: expect.stringContaining(manifestPath),
    }));

    const lines = readFileSync(result.files.notesJsonl, 'utf8').trim().split('\n');
    expect(lines).toHaveLength(1);
    const note = JSON.parse(lines[0]) as { media: { status: string | null; localImages: string[]; localVideos: string[] } };
    expect(note.media.status).toBeNull();
    expect(note.media.localImages).toEqual([]);
    expect(note.media.localVideos).toEqual([]);
  });

  it('keeps notes and marks Feishu unsynced when sync report is missing', () => {
    const root = createTempDir();
    const dbPath = join(root, 'xhs.sqlite');
    const outputDir = join(root, 'analysis-source');
    seedCompleteRun(dbPath);
    const { manifestPath, syncReportPath, pipelineCheckPath } = writeArtifacts(root);
    rmSync(syncReportPath);

    const result = buildXhsAnalysisSource({
      runId: 1,
      dbPath,
      manifestPath,
      syncReportPath,
      pipelineCheckPath,
      outputDir,
    });

    const source = JSON.parse(readFileSync(result.files.sourceJson, 'utf8')) as {
      warnings: Array<{ code: string }>;
    };
    expect(source.warnings).toContainEqual(expect.objectContaining({ code: 'sync_report_missing' }));

    const lines = readFileSync(result.files.notesJsonl, 'utf8').trim().split('\n');
    expect(lines).toHaveLength(1);
    const note = JSON.parse(lines[0]) as { feishu: { synced: boolean } };
    expect(note.feishu.synced).toBe(false);
  });

  it('marks Feishu synced from sync report fields 笔记ID when top-level feedId is missing', () => {
    const root = createTempDir();
    const dbPath = join(root, 'xhs.sqlite');
    const outputDir = join(root, 'analysis-source');
    seedCompleteRun(dbPath);
    const { manifestPath, syncReportPath, pipelineCheckPath } = writeArtifacts(root);
    writeFileSync(syncReportPath, JSON.stringify({
      records: [{ status: 'success', fields: { 笔记ID: 'feed1' } }],
    }), 'utf8');

    const result = buildXhsAnalysisSource({
      runId: 1,
      dbPath,
      manifestPath,
      syncReportPath,
      pipelineCheckPath,
      outputDir,
    });

    const lines = readFileSync(result.files.notesJsonl, 'utf8').trim().split('\n');
    expect(lines).toHaveLength(1);
    const note = JSON.parse(lines[0]) as { feishu: { synced: boolean } };
    expect(note.feishu.synced).toBe(true);
  });

  it('keeps notes and marks pipeline unknown when pipeline check is missing', () => {
    const root = createTempDir();
    const dbPath = join(root, 'xhs.sqlite');
    const outputDir = join(root, 'analysis-source');
    seedCompleteRun(dbPath);
    const { manifestPath, syncReportPath, pipelineCheckPath } = writeArtifacts(root);
    rmSync(pipelineCheckPath);

    const result = buildXhsAnalysisSource({
      runId: 1,
      dbPath,
      manifestPath,
      syncReportPath,
      pipelineCheckPath,
      outputDir,
    });

    const source = JSON.parse(readFileSync(result.files.sourceJson, 'utf8')) as {
      warnings: Array<{ code: string }>;
      pipeline: {
        status: string;
        agentReady: boolean;
        warnings: Array<{ code: string }>;
      };
    };
    expect(source.pipeline.status).toBe('unknown');
    expect(source.pipeline.agentReady).toBe(false);
    expect(source.pipeline.warnings).toContainEqual(expect.objectContaining({ code: 'pipeline_check_missing' }));
    expect(source.warnings).toContainEqual(expect.objectContaining({ code: 'pipeline_check_missing' }));

    const lines = readFileSync(result.files.notesJsonl, 'utf8').trim().split('\n');
    expect(lines).toHaveLength(1);
  });
});

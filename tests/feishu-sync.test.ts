import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it, vi } from 'vitest';

import { openDatabase } from '../src/db/client.js';
import { initializeSchema } from '../src/db/schema.js';
import { FeishuClient, type FeishuTransport } from '../src/feishu/client.js';
import { loadFeishuConfig } from '../src/feishu/config.js';
import { syncXhsRunToFeishu } from '../src/feishu/xhs-sync.js';

function seedRun(dbPath: string, tempDir: string): string {
  const db = openDatabase(dbPath);
  initializeSchema(db);
  db.prepare(`insert into xhs_search_runs (id, source, source_run_id, keyword, sorts_json, limit_per_sort, with_details, status) values (1, 'manual_keyword', null, '浴缸', '["most_liked"]', 1, 1, 'success')`).run();
  db.prepare(`
    insert into xhs_search_notes (
      run_id, keyword, sort_key, sort_label, rank_index, feed_id, xsec_token, search_result_url,
      title, author_name, detail_text, detail_tags_json, detail_like_text, detail_collect_text,
      detail_comment_count_text, detail_share_text, note_type, source_topic_texts_json,
      source_comments_json, media_sources_json, raw_card_text
    ) values (
      1, '浴缸', 'most_liked', '最多点赞', 1, 'feed1', 'token', 'https://www.xiaohongshu.com/search_result/feed1?xsec_token=token',
      '浴缸标题', '作者A', '正文', '["浴缸","装修"]', '100', '20', '3', '1', 'video', '["浴缸"]', '[]', '[]', '浴缸标题'
    )
  `).run();
  db.close();

  const mediaDir = join(tempDir, 'media');
  mkdirSync(mediaDir, { recursive: true });
  const imageFile = join(mediaDir, 'image.webp');
  const videoFile = join(mediaDir, 'video.mp4');
  writeFileSync(imageFile, 'image-bytes');
  writeFileSync(videoFile, 'video-bytes');
  const manifestPath = join(tempDir, 'manifest.json');
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
    completeVideoBytes: 10,
    completeVideoCoveredBytes: 10,
    completeVideoChunkCount: 1,
    completeVideoGaps: [],
  }]), 'utf8');
  return manifestPath;
}

function jsonResponse(data: unknown) {
  return {
    ok: true,
    status: 200,
    json: async () => ({ code: 0, data }),
  };
}

describe('Feishu XHS sync', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('reports missing Feishu environment variables clearly', () => {
    expect(() => loadFeishuConfig({})).toThrow('Missing required Feishu environment variable: FEISHU_BITABLE_APP_TOKEN or FEISHU_WIKI_NODE_TOKEN');
  });

  it('loads project local env files and accepts Wiki wrapped Bitable links', () => {
    const tempDir = mkdtempSync(join(tmpdir(), 'xhs-feishu-env-test-'));
    const envPath = join(tempDir, '.env.local');
    writeFileSync(envPath, [
      'FEISHU_APP_ID=cli_test',
      'FEISHU_APP_SECRET=secret_test',
      'FEISHU_BITABLE_URL=https://example.feishu.cn/wiki/wiki_token?table=tbl_test&view=vew_test',
    ].join('\n'));

    try {
      expect(loadFeishuConfig({}, { localEnvPaths: [envPath] })).toEqual({
        appId: 'cli_test',
        appSecret: 'secret_test',
        tableId: 'tbl_test',
        wikiNodeToken: 'wiki_token',
        bitableAppToken: undefined,
        viewId: 'vew_test',
        bitableUrl: 'https://example.feishu.cn/wiki/wiki_token?table=tbl_test&view=vew_test',
      });
    } finally {
      rmSync(tempDir, { recursive: true, force: true });
    }
  });

  it('resolves Bitable app token from a Wiki node token', async () => {
    const urls: string[] = [];
    const transport: FeishuTransport = async (url) => {
      urls.push(url);
      if (url.includes('/auth/v3/tenant_access_token/internal')) {
        return jsonResponse({ tenant_access_token: 'tenant-token' });
      }
      if (url.includes('/wiki/v2/spaces/get_node')) {
        return jsonResponse({ node: { obj_token: 'base-token', obj_type: 'bitable' } });
      }
      throw new Error(`Unexpected URL: ${url}`);
    };
    const client = new FeishuClient({ appId: 'cli_test', appSecret: 'secret', tableId: 'tbl_test', wikiNodeToken: 'wiki_token' }, transport);

    await expect(client.getBitableAppToken()).resolves.toBe('base-token');
    expect(urls.some((url) => url.includes('token=wiki_token'))).toBe(true);
  });

  it('stops field pagination when Feishu repeats the same page token', async () => {
    const fieldUrls: string[] = [];
    const transport: FeishuTransport = async (url) => {
      if (url.includes('/auth/v3/tenant_access_token/internal')) {
        return jsonResponse({ tenant_access_token: 'tenant-token' });
      }
      if (url.includes('/fields')) {
        fieldUrls.push(url);
        return jsonResponse({
          has_more: true,
          page_token: 'repeat-token',
          items: [{
            field_id: `fld${fieldUrls.length}`,
            field_name: `字段${fieldUrls.length}`,
            type: 3,
            property: { options: [{ name: '完整' }] },
          }],
        });
      }
      throw new Error(`Unexpected URL: ${url}`);
    };
    const client = new FeishuClient({ appId: 'cli_test', appSecret: 'secret', tableId: 'tbl_test', bitableAppToken: 'base-token' }, transport);

    await expect(client.listFields()).resolves.toEqual([
      { fieldId: 'fld1', fieldName: '字段1', type: 3, options: ['完整'] },
      { fieldId: 'fld2', fieldName: '字段2', type: 3, options: ['完整'] },
    ]);
    expect(fieldUrls).toHaveLength(2);
  });

  it('builds dry-run records without calling Feishu', async () => {
    const tempDir = mkdtempSync(join(tmpdir(), 'xhs-feishu-sync-test-'));
    const dbPath = join(tempDir, 'xhs.sqlite');
    const manifestPath = seedRun(dbPath, tempDir);
    const client = {
      ensureFields: vi.fn(),
      listRecords: vi.fn(),
      uploadFile: vi.fn(),
      createRecord: vi.fn(),
      updateRecord: vi.fn(),
    };

    try {
      const result = await syncXhsRunToFeishu({ runId: 1, dbPath, manifestPath, dryRun: true, client });

      expect(result).toMatchObject({ runId: 1, dryRun: true, rowCount: 1, created: 0, updated: 0, failed: 0, ensuredFields: 0 });
      expect(client.ensureFields).not.toHaveBeenCalled();
      expect(client.listRecords).not.toHaveBeenCalled();
      expect(client.uploadFile).not.toHaveBeenCalled();
      expect(client.createRecord).not.toHaveBeenCalled();
      expect(client.updateRecord).not.toHaveBeenCalled();
      const report = JSON.parse(readFileSync(result.reportPath, 'utf8')) as { records: Array<{ fields: Record<string, unknown> }> };
      expect(report.records[0]?.fields).toMatchObject({ 笔记ID: 'feed1', 标题: '浴缸标题', 点赞数: '100', 媒体完整性: '完整' });
    } finally {
      rmSync(tempDir, { recursive: true, force: true });
    }
  });

  it('updates existing Feishu records, ensures fields, and uploads attachments', async () => {
    const tempDir = mkdtempSync(join(tmpdir(), 'xhs-feishu-sync-test-'));
    const dbPath = join(tempDir, 'xhs.sqlite');
    const manifestPath = seedRun(dbPath, tempDir);
    const client = {
      ensureFields: vi.fn().mockResolvedValue(['图片附件', '视频附件']),
      listFields: vi.fn().mockResolvedValue([
        { fieldId: 'fld_sort', fieldName: '排序', type: 3, options: ['按点赞数', '按收藏数', '按评论数', '按采集时间'] },
        { fieldId: 'fld_type', fieldName: '笔记类型', type: 3, options: ['原创', '转载', '翻译', '其他'] },
        { fieldId: 'fld_url', fieldName: '原链接', type: 15, options: [] },
        { fieldId: 'fld_status', fieldName: '媒体完整性', type: 3, options: ['完整', '缺失图片', '缺失视频', '部分缺失'] },
        { fieldId: 'fld_collected', fieldName: '采集时间', type: 5, options: [] },
      ]),
      listRecords: vi.fn().mockResolvedValue([{ recordId: 'rec1', fields: { 笔记ID: 'feed1' } }]),
      uploadFile: vi.fn()
        .mockResolvedValueOnce({ fileToken: 'image-token' })
        .mockResolvedValueOnce({ fileToken: 'video-token' }),
      createRecord: vi.fn(),
      updateRecord: vi.fn().mockResolvedValue(undefined),
    };

    try {
      const result = await syncXhsRunToFeishu({ runId: 1, dbPath, manifestPath, dryRun: false, client });

      expect(result).toMatchObject({ rowCount: 1, created: 0, updated: 1, failed: 0, ensuredFields: 2 });
      expect(client.ensureFields).toHaveBeenCalledWith(expect.arrayContaining([expect.objectContaining({ fieldName: '笔记ID' })]));
      expect(client.listFields).toHaveBeenCalledTimes(1);
      expect(client.uploadFile).toHaveBeenCalledTimes(2);
      expect(client.createRecord).not.toHaveBeenCalled();
      expect(client.updateRecord).toHaveBeenCalledWith('rec1', expect.objectContaining({
        笔记ID: 'feed1',
        标题: '浴缸标题',
        排序: '按点赞数',
        笔记类型: '其他',
        原链接: { link: 'https://www.xiaohongshu.com/search_result/feed1?xsec_token=token', text: '浴缸标题' },
        图片附件: [{ file_token: 'image-token' }],
        视频附件: [{ file_token: 'video-token' }],
        媒体完整性: '完整',
      }));
      expect(client.updateRecord).toHaveBeenCalledWith('rec1', expect.objectContaining({ 采集时间: expect.any(Number) }));
    } finally {
      rmSync(tempDir, { recursive: true, force: true });
    }
  });
});

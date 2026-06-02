import type { Page } from 'playwright-core';
import { describe, expect, it } from 'vitest';

import {
  collectXhsNoteDetail,
  isXhsRateLimitError,
  isXhsRateLimitSignal,
  parseXhsInitialStateNoteDetail,
  parseXhsNoteDetailFromText,
  shouldRejectShortExploreUrl,
  XhsRateLimitError,
} from '../src/browser/xhs-note-detail.js';

describe('XHS note detail helpers', () => {
  it('detects website-login rate limit URL', () => {
    expect(isXhsRateLimitSignal({
      url: 'https://www.xiaohongshu.com/website-login/error?error_code=300013&error_msg=%E8%AE%BF%E9%97%AE%E9%A2%91%E7%B9%81%EF%BC%8C%E8%AF%B7%E7%A8%8D%E5%90%8E%E5%86%8D%E8%AF%95',
      text: '',
      message: '',
    })).toBe(true);
  });

  it('XhsRateLimitError exposes expected fields and type guard', () => {
    const error = new XhsRateLimitError(
      'XHS rate limited: error_code=300013 访问频繁，请稍后再试',
      'https://www.xiaohongshu.com/explore/feed1?xsec_token=token',
      '访问频繁，请稍后再试',
    );

    expect(error.name).toBe('XhsRateLimitError');
    expect(error.finalUrl).toBe('https://www.xiaohongshu.com/explore/feed1?xsec_token=token');
    expect(error.pageText).toBe('访问频繁，请稍后再试');
    expect(isXhsRateLimitError(error)).toBe(true);
    expect(isXhsRateLimitError(new Error('plain error'))).toBe(false);
  });

  it('detects error_code=300013 on normal XHS explore URLs', () => {
    expect(isXhsRateLimitSignal({
      url: 'https://www.xiaohongshu.com/explore/feed1?xsec_token=token',
      text: '',
      message: 'error_code=300013',
    })).toBe(true);
  });

  it('does not detect longer error codes as 300013', () => {
    expect(isXhsRateLimitSignal({
      url: 'https://www.xiaohongshu.com/website-login/error?error_code=3000130',
      text: '',
      message: '',
    })).toBe(false);
    expect(isXhsRateLimitSignal({
      url: 'https://www.xiaohongshu.com/explore/feed1?xsec_token=token',
      text: '',
      message: 'error_code=3000130',
    })).toBe(false);
  });

  it('detects text', () => {
    expect(isXhsRateLimitSignal({
      url: 'https://www.xiaohongshu.com/explore/feed1?xsec_token=token',
      text: '访问频繁，请稍后再试',
      message: '',
    })).toBe(true);
  });

  it('detects XHS URL plus 请稍后再试 without 访问频繁', () => {
    expect(isXhsRateLimitSignal({
      url: 'https://www.xiaohongshu.com/explore/feed1?xsec_token=token',
      text: '请稍后再试',
      message: '',
    })).toBe(true);
  });

  it('does not infer XHS host from missing or empty URLs for 请稍后再试', () => {
    expect(isXhsRateLimitSignal({ text: '请稍后再试' })).toBe(false);
    expect(isXhsRateLimitSignal({ url: null, text: '请稍后再试' })).toBe(false);
    expect(isXhsRateLimitSignal({ url: '', text: '请稍后再试' })).toBe(false);
  });

  it('detects URL-encoded rate-limit query text on explicit XHS hosts', () => {
    expect(isXhsRateLimitSignal({
      url: 'https://www.xiaohongshu.com/explore/feed1?error_msg=%E8%AE%BF%E9%97%AE%E9%A2%91%E7%B9%81',
    })).toBe(true);
    expect(isXhsRateLimitSignal({
      url: 'https://xiaohongshu.com/explore/feed1?error_msg=%E8%AF%B7%E7%A8%8D%E5%90%8E%E5%86%8D%E8%AF%95',
    })).toBe(true);
  });

  it('does not detect non-XHS URL plus 请稍后再试 as a rate limit', () => {
    expect(isXhsRateLimitSignal({
      url: 'https://example.com/explore/feed1?xsec_token=token',
      text: '请稍后再试',
      message: '',
    })).toBe(false);
  });

  it('ordinary detail errors not rate limits', () => {
    expect(isXhsRateLimitSignal({
      url: 'https://www.xiaohongshu.com/explore/feed1?xsec_token=token',
      text: '内容不存在',
      message: 'XHS detail page feed id mismatch',
    })).toBe(false);
  });

  it('rejects short explore URLs without xsec_token only', () => {
    expect(shouldRejectShortExploreUrl('/explore/feed1')).toBe(true);
    expect(shouldRejectShortExploreUrl('https://www.xiaohongshu.com/explore/feed1')).toBe(true);
    expect(shouldRejectShortExploreUrl('/explore/feed1/extra')).toBe(false);
    expect(shouldRejectShortExploreUrl('/explore/feed1?xsec_token=token')).toBe(false);
    expect(shouldRejectShortExploreUrl('/search_result/feed1?xsec_token=token')).toBe(false);
    expect(shouldRejectShortExploreUrl('http://[bad-url')).toBe(false);
  });

  it('parses structured detail data from initial state', () => {
    const parsed = parseXhsInitialStateNoteDetail({
      note: {
        noteDetailMap: {
          feed1: {
            note: {
              desc: '护肤真心话：皮肤不好！90%是脸都没洗干净…',
              type: 'normal',
              tagList: [{ name: '正确洗脸' }, { name: '新手护肤' }],
              topicList: [{ name: '洁面教程' }],
              comments: [
                { content: '洗完不紧绷，想问敏感肌能不能用', user: { nickname: '用户A' }, likeCount: '32' },
                { contentText: '在哪里买？', authorName: '用户B', likedCount: 5 },
              ],
              interactInfo: {
                commentCount: '1881',
                likedCount: '10万+',
                collectedCount: '10万+',
                shareCount: 23,
              },
            },
          },
        },
      },
    });

    expect(parsed).toEqual({
      detailText: '护肤真心话：皮肤不好！90%是脸都没洗干净…',
      tags: ['正确洗脸', '新手护肤'],
      noteType: 'image',
      sourceTopicTexts: ['正确洗脸', '新手护肤', '洁面教程'],
      sourceComments: [
        {
          contentText: '洗完不紧绷，想问敏感肌能不能用',
          authorName: '用户A',
          likeText: '32',
          rawText: '用户A\n洗完不紧绷，想问敏感肌能不能用\n32',
        },
        {
          contentText: '在哪里买？',
          authorName: '用户B',
          likeText: '5',
          rawText: '用户B\n在哪里买？\n5',
        },
      ],
      mediaSources: [],
      commentCountText: '1881',
      likeText: '10万+',
      collectText: '10万+',
      shareText: '23',
    });
  });

  it('returns null when initial state has no note detail object', () => {
    expect(parseXhsInitialStateNoteDetail({ note: { noteDetailMap: {} } })).toBeNull();
    expect(parseXhsInitialStateNoteDetail({ user: { name: 'no detail' } })).toBeNull();
  });

  it('returns null when note detail candidates have no recognized detail fields', () => {
    expect(parseXhsInitialStateNoteDetail({ note: { noteDetailMap: { feed1: {} } } })).toBeNull();
    expect(parseXhsInitialStateNoteDetail({ note: { noteDetailMap: { feed1: { note: {} } } } })).toBeNull();
  });

  it('returns null when recognized initial state fields have no useful detail data', () => {
    expect(parseXhsInitialStateNoteDetail({ note: { noteDetailMap: { feed1: { note: { interactInfo: {} } } } } })).toBeNull();
    expect(parseXhsInitialStateNoteDetail({ note: { noteDetailMap: { feed1: { note: { tagList: [] } } } } })).toBeNull();
  });

  it('selects the requested feed id from multi-note initial state', () => {
    const parsed = parseXhsInitialStateNoteDetail({
      note: {
        noteDetailMap: {
          otherFeed: {
            note: {
              desc: 'first note detail',
              interactInfo: { likedCount: '1' },
            },
          },
          targetFeed: {
            note: {
              desc: 'target note detail',
              tagList: [{ name: '目标标签' }],
              interactInfo: { commentCount: '7' },
            },
          },
        },
      },
    }, 'targetFeed');

    expect(parsed).toEqual({
      detailText: 'target note detail',
      tags: ['目标标签'],
      commentCountText: '7',
      likeText: null,
      collectText: null,
      shareText: null,
      noteType: 'unknown',
      sourceTopicTexts: ['目标标签'],
      sourceComments: [],
      mediaSources: [],
    });
  });

  it('parses visible metrics in order even when likes equal comments', () => {
    const parsed = parseXhsNoteDetailFromText('作者\n关注\n正文\n共 7 条评论\n说点什么...\n7\n8\n9\n发送');

    expect(parsed).toMatchObject({
      commentCountText: '7',
      likeText: '7',
      collectText: '8',
      shareText: '9',
    });
  });

  it('parses visible detail text as fallback', () => {
    const text = '陈莴笋\n关注\n护肤真心话：皮肤不好！90%是脸都没洗干净…\n分享一个老年犬护理心得，泡澡可以缓解关节压力。\n如果体力不支，每隔5分钟抱出来休息。\n#正确洗脸#新手护肤#护肤干货#洗脸\n01-25\n共 1881 条评论\n用户A\n敏感肌用了不紧绷\n32\n用户B\n在哪里买？\n5\n说点什么...\n10万+\n10万+\n可以添加到收藏夹啦\n1881\n发送';
    const parsed = parseXhsNoteDetailFromText(text);

    expect(parsed).toEqual({
      detailText: '护肤真心话：皮肤不好！90%是脸都没洗干净…\n分享一个老年犬护理心得，泡澡可以缓解关节压力。\n如果体力不支，每隔5分钟抱出来休息。',
      tags: ['正确洗脸', '新手护肤', '护肤干货', '洗脸'],
      rawDetailText: text,
      noteType: 'unknown',
      sourceTopicTexts: ['正确洗脸', '新手护肤', '护肤干货', '洗脸'],
      mediaSources: [],
      sourceComments: [
        {
          contentText: '敏感肌用了不紧绷',
          authorName: '用户A',
          likeText: '32',
          rawText: '用户A\n敏感肌用了不紧绷\n32',
        },
        {
          contentText: '在哪里买？',
          authorName: '用户B',
          likeText: '5',
          rawText: '用户B\n在哪里买？\n5',
        },
      ],
      commentCountText: '1881',
      likeText: '10万+',
      collectText: '10万+',
      shareText: null,
    });
  });

  it('collects exposed media evidence from detail pages', async () => {
    const page = {
      goto: async () => undefined,
      waitForLoadState: async () => undefined,
      url: () => 'https://www.xiaohongshu.com/explore/feed-media?xsec_token=token',
      evaluate: async (callback: unknown) => {
        const source = String(callback);
        if (source.includes('__INITIAL_STATE__')) {
          return { note: { noteDetailMap: {} } };
        }
        if (source.includes('querySelectorAll') && source.includes('video')) {
          return [
            { kind: 'video', url: 'blob:https://www.xiaohongshu.com/video-blob', posterUrl: 'https://example.com/poster.jpg', altText: null },
            { kind: 'image', url: 'https://example.com/image.jpg', posterUrl: null, altText: '浴缸封面' },
          ];
        }
        return undefined;
      },
      locator: () => ({ innerText: async () => '作者\n关注\n完整文案\n#浴缸\n共 1 条评论\n用户A\n好看\n1\n说点什么...\n2\n3\n发送' }),
    } as unknown as Page;

    const detail = await collectXhsNoteDetail(page, '/search_result/feed-media?xsec_token=token', { title: '媒体笔记' });

    expect(detail.mediaSources).toEqual([
      { kind: 'video', url: 'blob:https://www.xiaohongshu.com/video-blob', posterUrl: 'https://example.com/poster.jpg', altText: null },
      { kind: 'image', url: 'https://example.com/image.jpg', posterUrl: null, altText: '浴缸封面' },
    ]);
    expect(detail.analysisSourceText).toContain('媒体素材：');
    expect(detail.analysisSourceText).toContain('- video：blob:https://www.xiaohongshu.com/video-blob');
    expect(detail.analysisSourceText).toContain('- image：https://example.com/image.jpg（浴缸封面）');
  });

  it('filters page chrome images from exposed media evidence', async () => {
    const page = {
      goto: async () => undefined,
      waitForLoadState: async () => undefined,
      url: () => 'https://www.xiaohongshu.com/explore/feed-main-media?xsec_token=token',
      evaluate: async (callback: unknown) => {
        const source = String(callback);
        if (source.includes('__INITIAL_STATE__')) {
          return { note: { noteDetailMap: {} } };
        }
        if (source.includes('querySelectorAll') && source.includes('video')) {
          return [
            { kind: 'video', url: 'blob:https://www.xiaohongshu.com/video-blob', posterUrl: null, altText: null },
            { kind: 'image', url: 'https://sns-webpic-qc.xhscdn.com/note/main-cover.jpg', posterUrl: null, altText: '正文图' },
          ];
        }
        return undefined;
      },
      locator: () => ({ innerText: async () => '作者\n关注\n完整文案\n#浴缸\n共 1 条评论\n用户A\n好看\n1\n说点什么...\n2\n3\n发送' }),
    } as unknown as Page;

    const detail = await collectXhsNoteDetail(page, '/search_result/feed-main-media?xsec_token=token');

    expect(detail.mediaSources).toEqual([
      { kind: 'video', url: 'blob:https://www.xiaohongshu.com/video-blob', posterUrl: null, altText: null },
      { kind: 'image', url: 'https://sns-webpic-qc.xhscdn.com/note/main-cover.jpg', posterUrl: null, altText: '正文图' },
    ]);
  });

  it('builds analysis source text from collected note evidence', async () => {
    const page = {
      goto: async () => undefined,
      waitForLoadState: async () => undefined,
      url: () => 'https://www.xiaohongshu.com/explore/feed1?xsec_token=token',
      evaluate: async () => ({ note: { noteDetailMap: {} } }),
      locator: () => ({
        innerText: async () => '作者\n关注\n屏障修护步骤\n#护肤#屏障修护\n共 2 条评论\n用户A\n敏感肌可用吗？\n12\n说点什么...\n100\n50\n发送',
      }),
    } as unknown as Page;

    const detail = await collectXhsNoteDetail(page, '/search_result/feed1?xsec_token=token', {
      title: '屏障修护标题',
      coverAltText: '极简白底封面',
    });

    expect(detail.rawDetailText).toContain('屏障修护步骤');
    expect(detail.analysisSourceText).toContain('标题：屏障修护标题');
    expect(detail.analysisSourceText).toContain('类型：unknown');
    expect(detail.analysisSourceText).toContain('封面：极简白底封面');
    expect(detail.analysisSourceText).toContain('正文：屏障修护步骤');
    expect(detail.analysisSourceText).toContain('标签/话题：护肤、屏障修护');
    expect(detail.analysisSourceText).toContain('互动：评论 2，点赞 100，收藏 50，分享 未知');
    expect(detail.analysisSourceText).toContain('评论摘录：');
    expect(detail.analysisSourceText).toContain('- 用户A：敏感肌可用吗？（赞 12）');
  });

  it('collectXhsNoteDetail normalizes relative navigation URL before goto', async () => {
    let navigatedUrl: string | null = null;
    const page = {
      goto: async (url: string) => { navigatedUrl = url; },
      waitForLoadState: async () => undefined,
      url: () => 'https://www.xiaohongshu.com/explore/originalFeed?xsec_token=originalToken',
      evaluate: async () => ({
        note: {
          noteDetailMap: {
            originalFeed: {
              note: {
                desc: 'initial state detail',
              },
            },
          },
        },
      }),
      locator: () => ({
        innerText: async () => '作者\n关注\nbody detail should not win',
      }),
    } as unknown as Page;

    await collectXhsNoteDetail(page, '/search_result/originalFeed?xsec_token=originalToken');

    expect(navigatedUrl).toBe('https://www.xiaohongshu.com/search_result/originalFeed?xsec_token=originalToken');
  });

  it('collectXhsNoteDetail rejects final note URLs that do not match the requested feed id', async () => {
    const page = {
      goto: async () => undefined,
      waitForLoadState: async () => undefined,
      url: () => 'https://www.xiaohongshu.com/explore/finalFeed?xsec_token=finalToken',
      evaluate: async () => ({
        note: {
          noteDetailMap: {
            originalFeed: {
              note: {
                desc: 'original feed detail should not win',
                tagList: [{ tagName: '原始标签' }],
                interactInfo: {
                  comment_count: 1,
                  like_count: '2',
                  collect_count: '3',
                  share_count: '4',
                },
              },
            },
            finalFeed: {
              note: {
                desc: 'redirected feed detail should not be applied to original feed',
                tagList: [{ tagName: '状态标签' }],
                interactInfo: {
                  comment_count: 7,
                  like_count: '8',
                  collect_count: '9',
                  share_count: '10',
                },
              },
            },
          },
        },
      }),
      locator: () => ({
        innerText: async () => '作者\n关注\nbody detail should not win\n#正文标签\n共 1 条评论\n2\n3',
      }),
    } as unknown as Page;

    await expect(collectXhsNoteDetail(page, '/search_result/originalFeed?xsec_token=originalToken')).rejects.toThrow(
      'XHS detail page feed id mismatch: expected originalFeed, got finalFeed.',
    );
  });

  it('collectXhsNoteDetail converts goto error_code=300013 into XhsRateLimitError with best-effort page evidence', async () => {
    const page = {
      goto: async () => { throw new Error('error_code=300013'); },
      url: () => 'https://www.xiaohongshu.com/website-login/error?error_code=300013',
      locator: () => ({ innerText: async () => '访问频繁，请稍后再试' }),
    } as unknown as Page;

    await expect(collectXhsNoteDetail(page, '/search_result/feed1?xsec_token=token')).rejects.toMatchObject({
      name: 'XhsRateLimitError',
      finalUrl: 'https://www.xiaohongshu.com/website-login/error?error_code=300013',
      pageText: '访问频繁，请稍后再试',
    });
  });

  it('collectXhsNoteDetail throws XhsRateLimitError when page.url() is website-login error and body text is rate-limited', async () => {
    const page = {
      goto: async () => undefined,
      waitForLoadState: async () => undefined,
      url: () => 'https://www.xiaohongshu.com/website-login/error?error_code=300013&error_msg=%E8%AE%BF%E9%97%AE%E9%A2%91%E7%B9%81%EF%BC%8C%E8%AF%B7%E7%A8%8D%E5%90%8E%E5%86%8D%E8%AF%95',
      locator: () => ({ innerText: async () => '访问频繁，请稍后再试' }),
    } as unknown as Page;

    await expect(collectXhsNoteDetail(page, '/search_result/feed1?xsec_token=token')).rejects.toBeInstanceOf(XhsRateLimitError);
  });

  it('collectXhsNoteDetail throws XhsRateLimitError before feed-id mismatch when final URL is a different normal note and body text is rate-limited', async () => {
    const page = {
      goto: async () => undefined,
      waitForLoadState: async () => undefined,
      url: () => 'https://www.xiaohongshu.com/explore/finalFeed?xsec_token=finalToken',
      locator: () => ({ innerText: async () => '访问频繁，请稍后再试' }),
    } as unknown as Page;

    await expect(collectXhsNoteDetail(page, '/search_result/originalFeed?xsec_token=originalToken')).rejects.toMatchObject({
      name: 'XhsRateLimitError',
      finalUrl: 'https://www.xiaohongshu.com/explore/finalFeed?xsec_token=finalToken',
      pageText: '访问频繁，请稍后再试',
    });
  });

  it('collectXhsNoteDetail throws XhsRateLimitError before parsing ordinary detail when final URL is a normal note URL and body text is rate-limited', async () => {
    const page = {
      goto: async () => undefined,
      waitForLoadState: async () => undefined,
      url: () => 'https://www.xiaohongshu.com/explore/feed1?xsec_token=token',
      evaluate: async (callback: unknown) => {
        const source = String(callback);
        if (source.includes('__INITIAL_STATE__')) {
          return {};
        }
        throw new Error(`unexpected evaluate: ${source}`);
      },
      locator: (selector: string) => {
        if (selector !== 'body') {
          throw new Error(`unexpected locator: ${selector}`);
        }
        return { innerText: async () => '访问频繁，请稍后再试' };
      },
    } as unknown as Page;

    await expect(collectXhsNoteDetail(page, '/search_result/feed1?xsec_token=token')).rejects.toMatchObject({
      name: 'XhsRateLimitError',
      finalUrl: 'https://www.xiaohongshu.com/explore/feed1?xsec_token=token',
      pageText: '访问频繁，请稍后再试',
    });
  });

  it('collectXhsNoteDetail throws for short explore URL before navigation', async () => {
    const page = {
      goto: async () => { throw new Error('goto should not be called'); },
    } as unknown as Page;

    await expect(collectXhsNoteDetail(page, '/explore/feed1')).rejects.toThrow('XHS detail navigation requires a search_result URL or explore URL with xsec_token.');
  });

  it('collectXhsNoteDetail includes video URLs captured via Performance API', async () => {
    const page = {
      goto: async () => undefined,
      waitForLoadState: async () => undefined,
      url: () => 'https://www.xiaohongshu.com/explore/feed-video?xsec_token=token',
      evaluate: async (callback: unknown) => {
        const source = String(callback);
        if (source.includes('__INITIAL_STATE__')) {
          return { note: { noteDetailMap: {} } };
        }
        if (source.includes('querySelectorAll') && source.includes('video')) {
          return [];
        }
        if (source.includes('getEntriesByType')) {
          return [
            'https://sns-video-bd.xhscdn.com/video/abc123.m3u8',
            'https://sns-video-hw.xhscdn.com/video/def456.mp4',
          ];
        }
        return undefined;
      },
      locator: () => ({ innerText: async () => '作者\n关注\n视频正文\n#视频标签\n共 5 条评论\n说点什么...\n100\n50\n发送' }),
    } as unknown as Page;

    const detail = await collectXhsNoteDetail(page, '/search_result/feed-video?xsec_token=token');

    const videoUrls = detail.mediaSources.filter((s) => s.kind === 'video').map((s) => s.url);
    expect(detail.noteType).toBe('video');
    expect(videoUrls).toContain('https://sns-video-bd.xhscdn.com/video/abc123.m3u8');
    expect(videoUrls).toContain('https://sns-video-hw.xhscdn.com/video/def456.mp4');
    expect(videoUrls).toHaveLength(2);
  });
});

import type { Page } from 'playwright-core';

import type { XhsMediaSource, XhsNoteCommentSource, XhsNoteDetail, XhsNoteDetailContext, XhsNoteType } from '../xhs-types.js';
import { extractXhsNoteIdentity } from './xhs-search.js';

const XHS_NOTE_URL_BASE = 'https://www.xiaohongshu.com';
const SHORT_EXPLORE_REJECT_MESSAGE = 'XHS detail navigation requires a search_result URL or explore URL with xsec_token.';
const XHS_RATE_LIMIT_MESSAGE = 'XHS rate limited: error_code=300013 访问频繁，请稍后再试';

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

function decodeUrlText(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function hasXhsRateLimitErrorCode(value: string): boolean {
  return /(?:^|[^\w])error_code\s*=\s*300013(?!\d)/.test(value);
}

export function isXhsRateLimitSignal(input: { url?: string | null; text?: string | null; message?: string | null }): boolean {
  const url = input.url ?? '';
  const text = input.text ?? '';
  const message = input.message ?? '';
  const explicitUrl = typeof input.url === 'string' && input.url.trim() !== '';
  const decodedUrl = decodeUrlText(url);
  const combined = `${url}\n${decodedUrl}\n${text}\n${message}`;

  let hostname = '';
  let pathname = '';
  if (explicitUrl) {
    try {
      const parsedUrl = new URL(url);
      hostname = parsedUrl.hostname;
      pathname = parsedUrl.pathname;
    } catch {
      hostname = '';
      pathname = '';
    }
  }

  const isXhsHost = hostname === 'xiaohongshu.com' || hostname === 'www.xiaohongshu.com';
  if (isXhsHost && pathname === '/website-login/error' && hasXhsRateLimitErrorCode(combined)) {
    return true;
  }
  if (hasXhsRateLimitErrorCode(combined)) {
    return true;
  }
  if (combined.includes('访问频繁')) {
    return true;
  }
  return isXhsHost && combined.includes('请稍后再试');
}

export interface ParsedXhsDetailText {
  detailText: string | null;
  tags: string[];
  commentCountText: string | null;
  likeText: string | null;
  collectText: string | null;
  shareText: string | null;
  noteType: XhsNoteType;
  rawDetailText?: string | null;
  sourceTopicTexts: string[];
  sourceComments: XhsNoteCommentSource[];
  mediaSources: XhsMediaSource[];
}

type UnknownRecord = Record<string, unknown>;

const DETAIL_TEXT_KEYS = ['desc', 'description', 'content'];
const COMMENT_COUNT_KEYS = ['commentCount', 'comment_count', 'commentsCount', 'comments_count'];
const LIKE_COUNT_KEYS = ['likedCount', 'likeCount', 'liked_count', 'like_count'];
const COLLECT_COUNT_KEYS = ['collectedCount', 'collectCount', 'collected_count', 'collect_count'];
const SHARE_COUNT_KEYS = ['shareCount', 'share_count'];
const NOTE_DETAIL_FIELD_KEYS = [
  ...DETAIL_TEXT_KEYS,
  'type',
  'noteType',
  'note_type',
  'tagList',
  'topicList',
  'comments',
  'commentList',
  'interactInfo',
  ...COMMENT_COUNT_KEYS,
  ...LIKE_COUNT_KEYS,
  ...COLLECT_COUNT_KEYS,
  ...SHARE_COUNT_KEYS,
];

export function shouldRejectShortExploreUrl(url: string): boolean {
  let parsedUrl: URL;
  try {
    parsedUrl = new URL(url, XHS_NOTE_URL_BASE);
  } catch {
    return false;
  }

  const pathSegments = parsedUrl.pathname.split('/').filter(Boolean);
  const [section, feedId] = pathSegments;
  return pathSegments.length === 2 && section === 'explore' && feedId !== undefined && feedId.trim() !== '' && !parsedUrl.searchParams.has('xsec_token');
}

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function textValue(value: unknown): string | null {
  if (typeof value !== 'string') {
    return null;
  }

  const trimmed = value.trim();
  return trimmed === '' ? null : trimmed;
}

function countValue(value: unknown): string | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return String(value);
  }

  if (typeof value === 'string') {
    const trimmed = value.trim();
    return trimmed === '' ? null : trimmed;
  }

  return null;
}

function firstTextValue(source: UnknownRecord, keys: string[]): string | null {
  for (const key of keys) {
    const value = textValue(source[key]);
    if (value !== null) {
      return value;
    }
  }

  return null;
}

function firstCountValue(sources: UnknownRecord[], keys: string[]): string | null {
  for (const source of sources) {
    for (const key of keys) {
      const value = countValue(source[key]);
      if (value !== null) {
        return value;
      }
    }
  }

  return null;
}

function uniqueTexts(values: string[]): string[] {
  const texts: string[] = [];
  for (const value of values) {
    const trimmed = value.trim();
    if (trimmed !== '' && !texts.includes(trimmed)) {
      texts.push(trimmed);
    }
  }
  return texts;
}

function uniqueMediaSources(values: XhsMediaSource[]): XhsMediaSource[] {
  const mediaSources: XhsMediaSource[] = [];
  const seen = new Set<string>();
  for (const value of values) {
    const key = `${value.kind}:${value.url}`;
    if (!seen.has(key)) {
      seen.add(key);
      mediaSources.push(value);
    }
  }
  return mediaSources;
}

function extractNamedTexts(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value.flatMap((item) => {
    if (!isRecord(item)) {
      return [];
    }

    const value = firstTextValue(item, ['name', 'tagName', 'tag_name', 'title']);
    return value === null ? [] : [value];
  });
}

function extractTagsFromTagList(note: UnknownRecord): string[] {
  return extractNamedTexts(note.tagList);
}

function inferNoteType(note: UnknownRecord): XhsNoteType {
  const value = firstTextValue(note, ['type', 'noteType', 'note_type']);
  if (value === null) {
    return 'unknown';
  }

  const normalized = value.toLowerCase();
  if (normalized === 'video' || normalized.includes('video') || value === '视频') {
    return 'video';
  }
  if (normalized === 'normal' || normalized === 'image' || normalized.includes('image') || value === '图文') {
    return 'image';
  }
  return 'unknown';
}

function extractStructuredComments(note: UnknownRecord): XhsNoteCommentSource[] {
  const source = Array.isArray(note.comments) ? note.comments : Array.isArray(note.commentList) ? note.commentList : [];
  return source.slice(0, 20).flatMap((comment) => {
    if (!isRecord(comment)) {
      return [];
    }

    const user = isRecord(comment.user) ? comment.user : isRecord(comment.author) ? comment.author : {};
    const contentText = firstTextValue(comment, ['contentText', 'content', 'text']);
    if (contentText === null) {
      return [];
    }

    const authorName = firstTextValue(comment, ['authorName', 'nickname', 'nickName']) ?? firstTextValue(user, ['nickname', 'nickName', 'name']);
    const likeText = firstCountValue([comment], ['likeText', 'likeCount', 'likedCount', 'like_count', 'liked_count']);
    return [{
      contentText,
      authorName,
      likeText,
      rawText: [authorName, contentText, likeText].filter((value): value is string => value !== null).join('\n'),
    }];
  });
}

function hasRecognizedNoteDetailField(candidate: UnknownRecord): boolean {
  return NOTE_DETAIL_FIELD_KEYS.some((key) => key in candidate);
}

function unwrapNoteCandidate(candidate: unknown): UnknownRecord | null {
  if (!isRecord(candidate)) {
    return null;
  }

  const note = isRecord(candidate.note) ? candidate.note : candidate;
  return hasRecognizedNoteDetailField(note) ? note : null;
}

function hasUsefulNoteDetail(parsed: ParsedXhsDetailText): boolean {
  return parsed.detailText !== null
    || parsed.tags.length > 0
    || parsed.commentCountText !== null
    || parsed.likeText !== null
    || parsed.collectText !== null
    || parsed.shareText !== null
    || parsed.noteType !== 'unknown'
    || parsed.sourceTopicTexts.length > 0
    || parsed.sourceComments.length > 0
    || parsed.mediaSources.length > 0;
}

function parseNoteDetailCandidate(candidate: unknown): ParsedXhsDetailText | null {
  const note = unwrapNoteCandidate(candidate);
  if (note === null) {
    return null;
  }

  const interactInfo = isRecord(note.interactInfo) ? note.interactInfo : {};
  const countSources = [interactInfo, note];
  const parsed = {
    detailText: firstTextValue(note, DETAIL_TEXT_KEYS),
    tags: extractTagsFromTagList(note),
    commentCountText: firstCountValue(countSources, COMMENT_COUNT_KEYS),
    likeText: firstCountValue(countSources, LIKE_COUNT_KEYS),
    collectText: firstCountValue(countSources, COLLECT_COUNT_KEYS),
    shareText: firstCountValue(countSources, SHARE_COUNT_KEYS),
    noteType: inferNoteType(note),
    sourceTopicTexts: uniqueTexts([...extractTagsFromTagList(note), ...extractNamedTexts(note.topicList)]),
    sourceComments: extractStructuredComments(note),
    mediaSources: [],
  };

  return hasUsefulNoteDetail(parsed) ? parsed : null;
}

export function parseXhsInitialStateNoteDetail(state: unknown, feedId?: string): ParsedXhsDetailText | null {
  if (!isRecord(state)) {
    return null;
  }

  const stateNote = isRecord(state.note) ? state.note : null;
  const detailMap = stateNote !== null && isRecord(stateNote.noteDetailMap) ? stateNote.noteDetailMap : null;
  if (detailMap !== null) {
    if (feedId !== undefined && Object.prototype.hasOwnProperty.call(detailMap, feedId)) {
      return parseNoteDetailCandidate(detailMap[feedId]);
    }

    for (const value of Object.values(detailMap)) {
      const parsed = parseNoteDetailCandidate(value);
      if (parsed !== null) {
        return parsed;
      }
    }
  }

  const candidates = [stateNote?.noteDetail, stateNote?.currentNote, stateNote?.note, state.noteDetail];
  for (const candidate of candidates) {
    const parsed = parseNoteDetailCandidate(candidate);
    if (parsed !== null) {
      return parsed;
    }
  }

  return null;
}

function splitVisibleLines(text: string): string[] {
  return text.split(/\r?\n/).map((line) => line.trim()).filter((line) => line !== '');
}

function isPublishedAtLine(line: string): boolean {
  return /^(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,2}-\d{1,2}|昨天|今天|刚刚|\d+天前|\d+小时前)$/.test(line);
}

function isMetricLine(line: string): boolean {
  return /^(?:\d+(?:\.\d+)?(?:万|千|w|W|k|K)?\+?|[零一二三四五六七八九十百千万亿]+\+?)$/.test(line);
}

function isNonDetailLine(line: string): boolean {
  return line === '-'
    || line === '关注'
    || line === '已关注'
    || line === '说点什么...'
    || line === '发送'
    || line.includes('可以添加到收藏夹')
    || line.startsWith('#')
    || /^共\s*\S+\s*条评论$/.test(line)
    || isPublishedAtLine(line)
    || isMetricLine(line);
}

function extractVisibleDetailText(lines: string[]): string | null {
  const followIndex = lines.findIndex((line) => line === '关注' || line === '已关注');
  const searchStart = followIndex === -1 ? 0 : followIndex + 1;
  const detailLines: string[] = [];

  for (const line of lines.slice(searchStart)) {
    if (line.startsWith('#') || isPublishedAtLine(line) || /^共\s*\S+\s*条评论$/.test(line) || line.startsWith('说点什么')) {
      break;
    }

    if (!isNonDetailLine(line)) {
      detailLines.push(line);
    }
  }

  return detailLines.length === 0 ? null : detailLines.join('\n');
}

function extractVisibleTags(text: string): string[] {
  return Array.from(text.matchAll(/#([^#\s\r\n]+)/g), (match) => match[1].trim()).filter((tag) => tag !== '');
}

function extractVisibleCommentCount(text: string): string | null {
  return text.match(/共\s*([^\s]+)\s*条评论/)?.[1] ?? null;
}

function extractVisibleComments(lines: string[]): XhsNoteCommentSource[] {
  const commentCountIndex = lines.findIndex((line) => /^共\s*\S+\s*条评论$/.test(line));
  const promptIndex = lines.findIndex((line) => line.startsWith('说点什么'));
  if (commentCountIndex === -1 || promptIndex === -1 || promptIndex <= commentCountIndex) {
    return [];
  }

  const commentLines = lines.slice(commentCountIndex + 1, promptIndex).filter((line) => {
    return line !== '-'
      && line !== '关注'
      && line !== '已关注'
      && !line.startsWith('#')
      && !isPublishedAtLine(line)
      && !/^共\s*\S+\s*条评论$/.test(line);
  });
  const comments: XhsNoteCommentSource[] = [];
  for (let index = 0; index + 1 < commentLines.length && comments.length < 20; index += 3) {
    const authorName = commentLines[index] ?? null;
    const contentText = commentLines[index + 1];
    if (contentText === undefined) {
      break;
    }
    const likeText = commentLines[index + 2] !== undefined && isMetricLine(commentLines[index + 2]) ? commentLines[index + 2] : null;
    comments.push({
      contentText,
      authorName,
      likeText,
      rawText: [authorName, contentText, likeText].filter((value): value is string => value !== null).join('\n'),
    });
  }
  return comments;
}

function extractVisibleMetrics(lines: string[]): Pick<ParsedXhsDetailText, 'likeText' | 'collectText' | 'shareText'> {
  const promptIndex = lines.findIndex((line) => line.startsWith('说点什么'));
  if (promptIndex === -1) {
    return { likeText: null, collectText: null, shareText: null };
  }

  const metrics: string[] = [];
  for (const line of lines.slice(promptIndex + 1)) {
    if (line === '发送' || line.includes('可以添加到收藏夹')) {
      break;
    }

    if (isMetricLine(line)) {
      metrics.push(line);
    }
  }

  return {
    likeText: metrics[0] ?? null,
    collectText: metrics[1] ?? null,
    shareText: metrics[2] ?? null,
  };
}

export function parseXhsNoteDetailFromText(text: string): ParsedXhsDetailText {
  const lines = splitVisibleLines(text);
  const commentCountText = extractVisibleCommentCount(text);
  const metrics = extractVisibleMetrics(lines);

  const tags = extractVisibleTags(text);
  return {
    detailText: extractVisibleDetailText(lines),
    tags,
    rawDetailText: text,
    commentCountText,
    ...metrics,
    noteType: 'unknown',
    sourceTopicTexts: tags,
    sourceComments: extractVisibleComments(lines),
    mediaSources: [],
  };
}

async function readBodyInnerText(page: Page): Promise<string> {
  try {
    return await page.locator('body').innerText();
  } catch {
    return '';
  }
}

function readPageUrl(page: Page): string {
  try {
    return page.url();
  } catch {
    return '';
  }
}

function createXhsRateLimitError(finalUrl: string, pageText: string): XhsRateLimitError {
  return new XhsRateLimitError(XHS_RATE_LIMIT_MESSAGE, finalUrl, pageText);
}

async function throwIfXhsRateLimited(page: Page, input: { url?: string | null; text?: string | null; message?: string | null }): Promise<void> {
  if (!isXhsRateLimitSignal(input)) {
    return;
  }

  const finalUrl = input.url ?? readPageUrl(page);
  const pageText = input.text ?? await readBodyInnerText(page);
  throw createXhsRateLimitError(finalUrl, pageText);
}

async function collectVisibleDetailText(page: Page): Promise<string | null> {
  try {
    const value = await page.evaluate(() => {
      const selectors = ['#detail-desc', '.note-text', '.desc', '[class*="desc"]'];
      for (const selector of selectors) {
        const element = document.querySelector(selector);
        const text = element?.textContent?.trim();
        if (text !== undefined && text !== '') {
          return text;
        }
      }
      return null;
    });
    return typeof value === 'string' && value.trim() !== '' ? value.trim() : null;
  } catch {
    return null;
  }
}

async function collectXhsMediaSources(page: Page): Promise<XhsMediaSource[]> {
  try {
    const mediaSources = await page.evaluate(() => {
      type MediaSource = { kind: 'image' | 'video'; url: string; posterUrl: string | null; altText: string | null };
      const media: MediaSource[] = [];
      const seen = new Set<string>();
      const root = document.querySelector('#noteContainer, .note-detail, .note-container, [class*="media"], body') ?? document.body;
      const cleanUrl = (value: string | null | undefined): string | null => {
        const trimmed = value?.trim() ?? '';
        return trimmed === '' || trimmed.startsWith('data:') ? null : trimmed;
      };
      const isLikelyNoteImage = (url: string, image: HTMLImageElement): boolean => {
        if (url.startsWith('blob:')) {
          return true;
        }
        if (!url.includes('sns-webpic') && !url.includes('sns-img') && !url.includes('ci.xiaohongshu.com')) {
          return false;
        }
        const classText = `${image.className} ${image.parentElement?.className ?? ''}`.toLowerCase();
        return !classText.includes('avatar') && !url.includes('/avatar/') && !url.includes('/comment/') && !url.includes('fe-platform');
      };
      const add = (source: MediaSource): void => {
        if (seen.has(`${source.kind}:${source.url}`)) {
          return;
        }
        seen.add(`${source.kind}:${source.url}`);
        media.push(source);
      };

      for (const video of Array.from(root.querySelectorAll('video'))) {
        const posterUrl = cleanUrl(video.getAttribute('poster') ?? video.poster);
        const videoUrl = cleanUrl(video.currentSrc || video.src || video.getAttribute('src'));
        if (videoUrl !== null) {
          add({ kind: 'video', url: videoUrl, posterUrl, altText: null });
        }
        for (const source of Array.from(video.querySelectorAll('source'))) {
          const sourceUrl = cleanUrl(source.getAttribute('src') ?? source.src);
          if (sourceUrl !== null) {
            add({ kind: 'video', url: sourceUrl, posterUrl, altText: null });
          }
        }
      }

      for (const image of Array.from(root.querySelectorAll('img'))) {
        const imageUrl = cleanUrl(image.currentSrc || image.src || image.getAttribute('src') || image.getAttribute('data-src'));
        if (imageUrl !== null && isLikelyNoteImage(imageUrl, image)) {
          const altText = image.getAttribute('alt')?.trim() || image.getAttribute('aria-label')?.trim() || image.getAttribute('title')?.trim() || null;
          add({ kind: 'image', url: imageUrl, posterUrl: null, altText });
        }
      }

      return media.slice(0, 30);
    });

    if (!Array.isArray(mediaSources)) {
      return [];
    }

    return mediaSources.flatMap((source) => {
      if (!isRecord(source) || (source.kind !== 'image' && source.kind !== 'video')) {
        return [];
      }
      const url = textValue(source.url);
      if (url === null) {
        return [];
      }
      return [{
        kind: source.kind,
        url,
        posterUrl: textValue(source.posterUrl),
        altText: textValue(source.altText),
      }];
    });
  } catch {
    return [];
  }
}

function buildAnalysisSourceText(parsed: ParsedXhsDetailText, context?: XhsNoteDetailContext): string {
  const title = context?.title ?? parsed.detailText ?? '未知';
  const noteType = parsed.noteType === 'unknown' ? context?.noteType ?? 'unknown' : parsed.noteType;
  const topicTexts = uniqueTexts([...(context?.sourceTopicTexts ?? []), ...parsed.sourceTopicTexts, ...parsed.tags]);
  const lines = [
    `标题：${title}`,
    `类型：${noteType}`,
    `封面：${context?.coverAltText ?? context?.coverUrl ?? '未知'}`,
    `正文：${parsed.detailText ?? '未知'}`,
    `标签/话题：${topicTexts.length === 0 ? '未知' : topicTexts.join('、')}`,
    `互动：评论 ${parsed.commentCountText ?? '未知'}，点赞 ${parsed.likeText ?? '未知'}，收藏 ${parsed.collectText ?? '未知'}，分享 ${parsed.shareText ?? '未知'}`,
    '评论摘录：',
    ...parsed.sourceComments.map((comment) => `- ${comment.authorName ?? '未知用户'}：${comment.contentText}${comment.likeText === null ? '' : `（赞 ${comment.likeText}）`}`),
  ];

  if (parsed.mediaSources.length > 0) {
    lines.push(
      '媒体素材：',
      ...parsed.mediaSources.map((media) => `- ${media.kind}：${media.url}${media.altText === null ? '' : `（${media.altText}）`}${media.posterUrl === null ? '' : `，封面 ${media.posterUrl}`}`),
    );
  }

  return lines.join('\n');
}

export async function collectXhsNoteDetail(page: Page, searchResultUrl: string, context?: XhsNoteDetailContext): Promise<XhsNoteDetail> {
  if (shouldRejectShortExploreUrl(searchResultUrl)) {
    throw new Error(SHORT_EXPLORE_REJECT_MESSAGE);
  }

  const navigationUrl = new URL(searchResultUrl, XHS_NOTE_URL_BASE).href;
  const requestedIdentity = extractXhsNoteIdentity(navigationUrl);
  try {
    await page.goto(navigationUrl, { waitUntil: 'domcontentloaded' });
  } catch (error) {
    await throwIfXhsRateLimited(page, { url: readPageUrl(page), message: error instanceof Error ? error.message : String(error) });
    throw error;
  }
  try {
    await page.waitForLoadState('networkidle');
  } catch (error) {
    await throwIfXhsRateLimited(page, { url: readPageUrl(page), message: error instanceof Error ? error.message : String(error) });
    // Xiaohongshu pages often keep connections open; DOM content is enough for the fallback parser.
  }

  const finalUrl = readPageUrl(page);
  await throwIfXhsRateLimited(page, { url: finalUrl });

  const identity = extractXhsNoteIdentity(finalUrl);
  const text = await readBodyInnerText(page);
  await throwIfXhsRateLimited(page, { url: finalUrl, text });

  if (identity === null) {
    throw new Error(`XHS detail page did not resolve to a note URL: ${finalUrl}`);
  }
  if (requestedIdentity !== null && identity.feedId !== requestedIdentity.feedId) {
    throw new Error(`XHS detail page feed id mismatch: expected ${requestedIdentity.feedId}, got ${identity.feedId}.`);
  }

  let initialState: unknown = null;
  try {
    initialState = await page.evaluate(() => (window as unknown as { __INITIAL_STATE__?: unknown }).__INITIAL_STATE__);
  } catch {
    initialState = null;
  }
  const parsed = parseXhsInitialStateNoteDetail(initialState, identity.feedId) ?? parseXhsNoteDetailFromText(text);
  const visibleDetailText = await collectVisibleDetailText(page);
  const mediaSources = uniqueMediaSources([...parsed.mediaSources, ...await collectXhsMediaSources(page)]);
  const rawDetailText = parsed.rawDetailText ?? text;
  const noteType = parsed.noteType === 'unknown' ? context?.noteType ?? 'unknown' : parsed.noteType;
  const sourceTopicTexts = uniqueTexts([...(context?.sourceTopicTexts ?? []), ...parsed.sourceTopicTexts, ...parsed.tags]);
  const detailText = visibleDetailText ?? parsed.detailText;
  const analysisParsed = { ...parsed, detailText, noteType, rawDetailText, sourceTopicTexts, mediaSources };

  return {
    feedId: identity.feedId,
    xsecToken: identity.xsecToken,
    exploreUrl: finalUrl,
    detailText,
    tags: parsed.tags,
    commentCountText: parsed.commentCountText,
    likeText: parsed.likeText,
    collectText: parsed.collectText,
    shareText: parsed.shareText,
    noteType,
    rawDetailText,
    sourceTopicTexts,
    sourceComments: parsed.sourceComments,
    mediaSources,
    analysisSourceText: buildAnalysisSourceText(analysisParsed, context),
  };
}

import type { Page } from 'playwright-core';

import type { XhsNoteIdentity, XhsNoteType, XhsSearchCardPayload, XhsSearchNoteRow, XhsSearchSortKey } from '../xhs-types.js';

export const XHS_SEARCH_SORTS: Record<XhsSearchSortKey, string> = {
  latest: '最新',
  most_liked: '最多点赞',
  most_commented: '最多评论',
  most_collected: '最多收藏',
};

export const DEFAULT_XHS_SEARCH_SORTS: XhsSearchSortKey[] = ['latest', 'most_liked', 'most_commented', 'most_collected'];

const XHS_LOGIN_REQUIRED_PATTERNS = [/登录后查看搜索结果/, /手机号登录/, /扫码登录/, /请先登录/, /马上登录即可/];

export const XHS_LOGIN_REQUIRED_MESSAGE = '当前小红书登录态不可用，请在 CDP 浏览器中登录小红书后重试。';

const XHS_NOTE_URL_BASE = 'https://www.xiaohongshu.com';
const XHS_NOTE_ALLOWED_HOSTNAMES = new Set(['xiaohongshu.com', 'www.xiaohongshu.com']);
const XHS_PUBLISHED_AT_PATTERNS = [/\d{4}-\d{2}-\d{2}/, /\d{1,2}-\d{1,2}/, /\d+天前/, /\d+小时前/, /昨天/, /今天/, /刚刚/];
const XHS_METRIC_VALUE_PATTERN = '(?:\\d+(?:\\.\\d+)?|[零一二三四五六七八九十百千万亿]+)(?:[万千wWkK])?';

type UnknownRecord = Record<string, unknown>;

interface XhsDomSearchCardSnapshot {
  rawText: string;
  hrefs: string[];
  authorProfileUrl: string | null;
  coverUrl: string | null;
  coverAltText: string | null;
  noteType: XhsNoteType;
  sourceTopicTexts: string[];
}

export function buildXhsSearchUrl(keyword: string): string {
  return `https://www.xiaohongshu.com/search_result?keyword=${encodeURIComponent(keyword)}`;
}

export function parseXhsSortKeys(value: string | undefined): XhsSearchSortKey[] {
  if (value === undefined || value.trim() === '') {
    return [...DEFAULT_XHS_SEARCH_SORTS];
  }

  return value.split(',').map((part) => {
    const key = part.trim();
    if (!Object.prototype.hasOwnProperty.call(XHS_SEARCH_SORTS, key)) {
      throw new Error(`Unsupported XHS sort key: ${key}`);
    }
    return key as XhsSearchSortKey;
  });
}

export function isXhsLoginRequiredText(text: string): boolean {
  const normalizedText = text.replace(/\s+/g, '');
  return XHS_LOGIN_REQUIRED_PATTERNS.some((pattern) => pattern.test(normalizedText));
}

export function absoluteXhsUrl(url: string): string {
  return new URL(url, XHS_NOTE_URL_BASE).href;
}

function isAllowedXhsUrl(parsedUrl: URL): boolean {
  return XHS_NOTE_ALLOWED_HOSTNAMES.has(parsedUrl.hostname);
}

export function isXhsSortActive(activeLabels: string[], sortKey: XhsSearchSortKey): boolean {
  return activeLabels.includes(XHS_SEARCH_SORTS[sortKey]);
}

export function extractXhsNoteIdentity(url: string): XhsNoteIdentity | null {
  let parsedUrl: URL;
  try {
    parsedUrl = new URL(url, XHS_NOTE_URL_BASE);
  } catch {
    return null;
  }

  if (parsedUrl.origin !== XHS_NOTE_URL_BASE && !XHS_NOTE_ALLOWED_HOSTNAMES.has(parsedUrl.hostname)) {
    return null;
  }

  const [section, feedId] = parsedUrl.pathname.split('/').filter(Boolean);
  if ((section !== 'search_result' && section !== 'explore') || feedId === undefined || feedId.trim() === '') {
    return null;
  }

  return {
    feedId,
    xsecToken: parsedUrl.searchParams.get('xsec_token'),
  };
}

export function pickBestXhsSearchResultUrl(urls: string[]): string | null {
  const tokenizedNoteUrls: URL[] = [];

  for (const url of urls) {
    let parsedUrl: URL;
    try {
      parsedUrl = new URL(url, XHS_NOTE_URL_BASE);
    } catch {
      continue;
    }

    if (!isAllowedXhsUrl(parsedUrl)) {
      continue;
    }

    const identity = extractXhsNoteIdentity(parsedUrl.href);
    if (identity !== null && identity.xsecToken !== null && identity.xsecToken.trim() !== '') {
      tokenizedNoteUrls.push(parsedUrl);
    }
  }

  return tokenizedNoteUrls.find((url) => url.pathname.startsWith('/search_result/'))?.href ?? tokenizedNoteUrls[0]?.href ?? null;
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

function firstTextValue(...values: unknown[]): string | null {
  for (const value of values) {
    const text = textValue(value);
    if (text !== null) {
      return text;
    }
  }

  return null;
}

function uniqueTextLines(values: Array<string | null>): string[] {
  const lines: string[] = [];
  for (const value of values) {
    if (value !== null && !lines.includes(value)) {
      lines.push(value);
    }
  }

  return lines;
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

function inferXhsNoteType(...values: unknown[]): XhsNoteType {
  for (const value of values) {
    const text = typeof value === 'string' ? value.toLowerCase() : '';
    if (['video', '视频'].includes(text) || text.includes('video')) {
      return 'video';
    }
    if (['normal', 'image', '图文'].includes(text) || text.includes('image')) {
      return 'image';
    }
  }
  return 'unknown';
}

function extractTagTexts(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value.flatMap((item) => {
    if (!isRecord(item)) {
      return [];
    }
    const text = firstTextValue(item.name, item.tagName, item.tag_name, item.title);
    return text === null ? [] : [text];
  });
}

function unwrapRawValue(value: unknown): unknown {
  if (isRecord(value) && Array.isArray(value._rawValue)) {
    return value._rawValue;
  }

  return value;
}

export function parseXhsInitialStateSearchCardPayloads(state: unknown): XhsSearchCardPayload[] {
  if (!isRecord(state) || !isRecord(state.search)) {
    return [];
  }

  const feeds = unwrapRawValue(state.search.feeds);
  if (!Array.isArray(feeds)) {
    return [];
  }

  return feeds.flatMap((feed): XhsSearchCardPayload[] => {
    if (!isRecord(feed)) {
      return [];
    }

    const noteCard: UnknownRecord = isRecord(feed.noteCard) ? feed.noteCard : {};
    const user: UnknownRecord = isRecord(feed.user) ? feed.user : isRecord(noteCard.user) ? noteCard.user : {};
    const cover: UnknownRecord = isRecord(feed.cover) ? feed.cover : isRecord(noteCard.cover) ? noteCard.cover : {};
    const feedId = firstTextValue(feed.id, feed.noteId, feed.note_id, noteCard.id, noteCard.noteId, noteCard.note_id);
    const xsecToken = firstTextValue(feed.xsecToken, feed.xsec_token, noteCard.xsecToken, noteCard.xsec_token);

    if (feedId === null || xsecToken === null) {
      return [];
    }

    const displayTitle = firstTextValue(feed.displayTitle, feed.display_title, noteCard.displayTitle, noteCard.display_title);
    const title = firstTextValue(feed.title, noteCard.title);
    const userId = firstTextValue(user.userId, user.user_id, user.id);
    const nickname = firstTextValue(user.nickname, user.nickName, user.name);
    const coverUrl = firstTextValue(cover.urlDefault, cover.url_default, cover.url, cover.urlPre, cover.url_pre);
    const coverAltText = firstTextValue(cover.alt, cover.title, cover.desc, cover.description, noteCard.coverAltText, noteCard.cover_alt_text);
    const noteType = inferXhsNoteType(feed.type, feed.noteType, feed.note_type, noteCard.type, noteCard.noteType, noteCard.note_type);
    const topicTexts = uniqueTexts([
      '护肤',
      '搜索排序:未知',
      ...extractTagTexts(feed.tagList),
      ...extractTagTexts(noteCard.tagList),
      ...extractTagTexts(feed.topicList),
      ...extractTagTexts(noteCard.topicList),
    ]);

    return [{
      searchResultUrl: absoluteXhsUrl(`/search_result/${encodeURIComponent(feedId)}?xsec_token=${encodeURIComponent(xsecToken)}`),
      authorProfileUrl: userId === null ? null : absoluteXhsUrl(`/user/profile/${encodeURIComponent(userId)}`),
      coverUrl,
      noteType,
      coverAltText,
      sourceTopicTexts: topicTexts,
      rawText: uniqueTextLines([displayTitle, title, nickname]).join('\n'),
    }];
  });
}

function parseXhsCardLines(rawText: string): string[] {
  return rawText.split(/\r?\n/).map((line) => line.trim()).filter((line) => line !== '');
}

function isXhsPublishedAtLine(line: string): boolean {
  return XHS_PUBLISHED_AT_PATTERNS.some((pattern) => pattern.test(line));
}

function parseXhsMetricText(lines: string[], sortKey: XhsSearchSortKey, sortLabel: string, title: string, authorName: string | null): string | null {
  if (sortKey === 'latest') {
    return [...lines].reverse().find((line) => line !== title && line !== authorName && isXhsPublishedAtLine(line)) ?? null;
  }

  const metricLabel = sortLabel.replace(/^最多/, '');
  const metricTextPattern = new RegExp(`${metricLabel}\\s*${XHS_METRIC_VALUE_PATTERN}`);
  return [...lines].reverse().find((line) => line !== title && line !== authorName && !isXhsPublishedAtLine(line) && metricTextPattern.test(line)) ?? null;
}

export function hasValidXhsDomSearchCard(cards: XhsSearchCardPayload[]): boolean {
  return cards.some((card) => {
    if (card.searchResultUrl === null) {
      return false;
    }

    const identity = extractXhsNoteIdentity(card.searchResultUrl);
    return identity !== null && identity.xsecToken !== null && identity.xsecToken.trim() !== '';
  });
}

export function pickXhsSearchCardsForCollection(
  domCards: XhsSearchCardPayload[],
  initialStateCards: XhsSearchCardPayload[],
): XhsSearchCardPayload[] {
  return hasValidXhsDomSearchCard(domCards) ? domCards : initialStateCards;
}

export function parseXhsSearchNoteRows(params: {
  keyword: string;
  sortKey: XhsSearchSortKey;
  cards: XhsSearchCardPayload[];
}): XhsSearchNoteRow[] {
  const sortLabel = XHS_SEARCH_SORTS[params.sortKey];
  const rows: XhsSearchNoteRow[] = [];

  for (const card of params.cards) {
    if (card.searchResultUrl === null) {
      continue;
    }

    const identity = extractXhsNoteIdentity(card.searchResultUrl);
    if (identity === null) {
      continue;
    }

    const lines = parseXhsCardLines(card.rawText);
    const title = lines[0] ?? identity.feedId;
    const authorName = lines[1] ?? null;
    const publishedAtText = lines.find(isXhsPublishedAtLine) ?? null;

    rows.push({
      keyword: params.keyword,
      sortKey: params.sortKey,
      sortLabel,
      rankIndex: rows.length + 1,
      feedId: identity.feedId,
      xsecToken: identity.xsecToken,
      searchResultUrl: card.searchResultUrl,
      exploreUrl: null,
      title,
      authorName,
      authorProfileUrl: card.authorProfileUrl,
      coverUrl: card.coverUrl,
      publishedAtText,
      metricText: parseXhsMetricText(lines, params.sortKey, sortLabel, title, authorName),
      detailText: null,
      detailTags: [],
      detailCommentCountText: null,
      detailLikeText: null,
      detailCollectText: null,
      detailShareText: null,
      noteType: card.noteType ?? 'unknown',
      coverAltText: card.coverAltText ?? null,
      rawDetailText: null,
      sourceTopicTexts: uniqueTexts([params.keyword, `搜索排序:${sortLabel}`, ...Array.isArray(card.sourceTopicTexts) ? card.sourceTopicTexts : []]),
      sourceComments: [],
      mediaSources: [],
      analysisSourceText: null,
      rawCardText: card.rawText,
    });
  }

  return rows;
}

export async function assertXhsLoggedIn(page: Page): Promise<void> {
  const text = await page.locator('body').innerText();
  if (isXhsLoginRequiredText(text)) {
    throw new Error(XHS_LOGIN_REQUIRED_MESSAGE);
  }
}

export async function openXhsSearchPage(page: Page, keyword: string): Promise<void> {
  await page.goto(buildXhsSearchUrl(keyword), { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle').catch(() => undefined);
  await assertXhsLoggedIn(page);
}

async function hasVisibleXhsSearchSortLabels(page: Page): Promise<boolean> {
  return page.evaluate((sortLabels) => {
    function isVisible(element: Element): boolean {
      const rect = element.getBoundingClientRect();
      const style = window.getComputedStyle(element);
      return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
    }

    const visibleText = Array.from(document.querySelectorAll('button, [role="button"], .tags, .tag, [class*="tag"], [data-hp-kind]'))
      .filter(isVisible)
      .map((element) => element.textContent ?? '')
      .join('\n');

    return sortLabels.every((label) => visibleText.includes(label));
  }, Object.values(XHS_SEARCH_SORTS)).catch(() => false);
}

async function openXhsSearchFilterPanel(page: Page): Promise<void> {
  await page.waitForFunction(
    () => {
      function isVisible(element: Element): boolean {
        const rect = element.getBoundingClientRect();
        const style = window.getComputedStyle(element);
        return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
      }

      const candidates = Array.from(document.querySelectorAll('button, [role="button"], .filter, [class*="filter"]'));
      return candidates.some((element) => isVisible(element) && (element.textContent ?? '').trim().includes('筛选'));
    },
    undefined,
    { timeout: 5_000, polling: 100 },
  ).catch(() => undefined);

  for (let attempt = 0; attempt < 3 && !(await hasVisibleXhsSearchSortLabels(page)); attempt += 1) {
    const clicked = await page.evaluate(() => {
      function isVisible(element: Element): boolean {
        const rect = element.getBoundingClientRect();
        const style = window.getComputedStyle(element);
        return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
      }

      function dispatchMouseClick(element: Element): void {
        for (const type of ['mouseover', 'mousedown', 'mouseup', 'click']) {
          element.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }));
        }
      }

      const candidates = Array.from(document.querySelectorAll('button, [role="button"], .filter, [class*="filter"]'));
      const target = candidates.find((element) => isVisible(element) && (element.textContent ?? '').trim().includes('筛选'));
      if (target === undefined) {
        return false;
      }

      dispatchMouseClick(target);
      return true;
    }).catch(() => false);

    if (!clicked) {
      break;
    }

    await page.waitForFunction(
      (sortLabels) => {
        function isVisible(element: Element): boolean {
          const rect = element.getBoundingClientRect();
          const style = window.getComputedStyle(element);
          return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
        }

        const visibleText = Array.from(document.querySelectorAll('button, [role="button"], .tags, .tag, [class*="tag"], [data-hp-kind]'))
          .filter(isVisible)
          .map((element) => element.textContent ?? '')
          .join('\n');

        return sortLabels.every((label) => visibleText.includes(label));
      },
      Object.values(XHS_SEARCH_SORTS),
      { timeout: 1_500, polling: 100 },
    ).catch(() => undefined);

    if (!(await hasVisibleXhsSearchSortLabels(page))) {
      await page.waitForTimeout(300);
    }
  }

  if (!(await hasVisibleXhsSearchSortLabels(page))) {
    await page.getByText('筛选', { exact: true }).click({ timeout: 3_000 });
    await page.waitForFunction(
      (sortLabels) => {
        function isVisible(element: Element): boolean {
          const rect = element.getBoundingClientRect();
          const style = window.getComputedStyle(element);
          return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
        }

        const visibleText = Array.from(document.querySelectorAll('button, [role="button"], .tags, .tag, [class*="tag"], [data-hp-kind]'))
          .filter(isVisible)
          .map((element) => element.textContent ?? '')
          .join('\n');

        return sortLabels.every((label) => visibleText.includes(label));
      },
      Object.values(XHS_SEARCH_SORTS),
      { timeout: 1_500, polling: 100 },
    ).catch(() => undefined);
  }

  if (!(await hasVisibleXhsSearchSortLabels(page))) {
    throw new Error(`小红书搜索筛选面板未显示排序选项：${Object.values(XHS_SEARCH_SORTS).join('、')}`);
  }
}

async function clickXhsSearchSortLabel(page: Page, label: string): Promise<boolean> {
  return page.evaluate((sortLabel) => {
    function normalizeText(value: string | null): string {
      return (value ?? '').replace(/\s+/g, ' ').trim();
    }

    function isVisible(element: Element): boolean {
      const rect = element.getBoundingClientRect();
      const style = window.getComputedStyle(element);
      return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
    }

    function dispatchMouseClick(element: Element): void {
      for (const type of ['mouseover', 'mousedown', 'mouseup', 'click']) {
        element.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }));
      }
    }

    const preferredMarker = Array.from(document.querySelectorAll('[data-hp-kind]'))
      .find((element) => element.getAttribute('data-hp-kind') === `filter-tag-${sortLabel}`);
    if (preferredMarker?.parentElement !== undefined && preferredMarker.parentElement !== null) {
      const sibling = Array.from(preferredMarker.parentElement.children)
        .find((element) => element !== preferredMarker && isVisible(element) && normalizeText(element.textContent).includes(sortLabel));
      if (sibling !== undefined) {
        dispatchMouseClick(sibling);
        return true;
      }

      if (isVisible(preferredMarker.parentElement) && normalizeText(preferredMarker.parentElement.textContent).includes(sortLabel)) {
        dispatchMouseClick(preferredMarker.parentElement);
        return true;
      }
    }

    if (preferredMarker !== undefined && isVisible(preferredMarker)) {
      dispatchMouseClick(preferredMarker);
      return true;
    }

    const fallback = Array.from(document.querySelectorAll('.tags, .tag, [class*="tag"], button, [role="button"]'))
      .find((element) => isVisible(element) && normalizeText(element.textContent) === sortLabel);
    if (fallback === undefined) {
      return false;
    }

    dispatchMouseClick(fallback);
    return true;
  }, label).catch(() => false);
}

interface XhsSearchResultsSignature {
  cardCount: number;
  signature: string;
}

async function readXhsSearchResultsSignature(page: Page): Promise<XhsSearchResultsSignature> {
  return page.evaluate((): XhsSearchResultsSignature => {
    const cardSignatures = Array.from(document.querySelectorAll('section.note-item'))
      .filter((section) => {
        const rect = section.getBoundingClientRect();
        const style = window.getComputedStyle(section);
        return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
      })
      .slice(0, 6)
      .map((section) => {
        const text = (section instanceof HTMLElement ? section.innerText : section.textContent ?? '')
          .replace(/\s+/g, ' ')
          .trim()
          .slice(0, 200);
        const hrefs = Array.from(section.querySelectorAll('a[href]'))
          .map((anchor) => anchor instanceof HTMLAnchorElement ? anchor.href || anchor.getAttribute('href') : anchor.getAttribute('href'))
          .filter((href): href is string => href !== null && href.trim() !== '')
          .slice(0, 4)
          .join('|');
        return `${text}\n${hrefs}`;
      });

    return {
      cardCount: cardSignatures.length,
      signature: cardSignatures.join('\n---\n'),
    };
  }).catch(() => ({ cardCount: 0, signature: '' }));
}

async function waitForXhsSearchResultsAfterSort(page: Page, beforeSignature: XhsSearchResultsSignature, sortLabel: string): Promise<void> {
  try {
    await page.waitForFunction(
      (before) => {
        function visibleCardSignatures(): string[] {
          return Array.from(document.querySelectorAll('section.note-item'))
            .filter((section) => {
              const rect = section.getBoundingClientRect();
              const style = window.getComputedStyle(section);
              return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
            })
            .slice(0, 6)
            .map((section) => {
              const text = (section instanceof HTMLElement ? section.innerText : section.textContent ?? '')
                .replace(/\s+/g, ' ')
                .trim()
                .slice(0, 200);
              const hrefs = Array.from(section.querySelectorAll('a[href]'))
                .map((anchor) => anchor instanceof HTMLAnchorElement ? anchor.href || anchor.getAttribute('href') : anchor.getAttribute('href'))
                .filter((href): href is string => href !== null && href.trim() !== '')
                .slice(0, 4)
                .join('|');
              return `${text}\n${hrefs}`;
            });
        }

        const signatures = visibleCardSignatures();
        if (signatures.length === 0) {
          return false;
        }

        const currentSignature = signatures.join('\n---\n');
        return before.cardCount === 0 || currentSignature !== before.signature;
      },
      beforeSignature,
      { timeout: 2_500, polling: 150 },
    );
  } catch (error) {
    throw new Error(`小红书搜索排序结果未刷新：${sortLabel}`, { cause: error });
  }
}

interface XhsActiveSortLabelsRequest {
  labels: string[];
  expectedLabel?: string;
}

function evaluateXhsActiveSortLabels(request: XhsActiveSortLabelsRequest): string[] | boolean {
  function normalizeText(value: string | null): string {
    return (value ?? '').replace(/\s+/g, ' ').trim();
  }

  function isVisible(element: Element): boolean {
    const rect = element.getBoundingClientRect();
    const style = window.getComputedStyle(element);
    return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
  }

  function dataHpKindSortLabel(element: Element): string | null {
    const dataHpKind = element.getAttribute('data-hp-kind') ?? '';
    for (const label of request.labels) {
      if (dataHpKind === `filter-tag-${label}`) {
        return label;
      }
    }
    return null;
  }

  function nearbyDataHpKindSortLabel(element: Element, text: string): string | null {
    const directLabel = dataHpKindSortLabel(element);
    if (directLabel !== null) {
      return directLabel;
    }

    const querySelector = (element as Element & { querySelector?: (selector: string) => Element | null }).querySelector;
    if (typeof querySelector === 'function') {
      const marker = querySelector.call(element, '[data-hp-kind]');
      if (marker !== null) {
        const markerLabel = dataHpKindSortLabel(marker);
        if (markerLabel !== null && text.includes(markerLabel)) {
          return markerLabel;
        }
      }
    }

    const parent = element.parentElement;
    if (parent !== null) {
      const parentLabel = dataHpKindSortLabel(parent);
      if (parentLabel !== null && text.includes(parentLabel)) {
        return parentLabel;
      }

      const siblingLabel = Array.from(parent.children)
        .map(dataHpKindSortLabel)
        .find((label): label is string => label !== null && text.includes(label));
      if (siblingLabel !== undefined) {
        return siblingLabel;
      }
    }

    return null;
  }

  function isSortTagOrControl(element: Element, text: string): boolean {
    const tagName = typeof element.tagName === 'string' ? element.tagName.toLowerCase() : '';
    const role = element.getAttribute('role') ?? '';
    const className = (element.getAttribute('class') ?? '').toLowerCase();
    return tagName === 'button'
      || role === 'button'
      || className.includes('tag')
      || className.includes('filter')
      || nearbyDataHpKindSortLabel(element, text) !== null;
  }

  const activeLabels = new Set<string>();
  const supportedLabels = new Set(request.labels);
  const activeElements = document.querySelectorAll('.active, .selected, [aria-selected="true"], [data-active="true"], [data-selected="true"]');

  for (const element of Array.from(activeElements)) {
    if (!isVisible(element)) {
      continue;
    }

    const text = normalizeText(element.textContent);
    if (!isSortTagOrControl(element, text)) {
      continue;
    }

    if (supportedLabels.has(text)) {
      activeLabels.add(text);
      continue;
    }

    const markerLabel = nearbyDataHpKindSortLabel(element, text);
    if (markerLabel !== null) {
      activeLabels.add(markerLabel);
      continue;
    }

    const containedLabels = request.labels.filter((label) => text.includes(label));
    if (containedLabels.length === 1) {
      activeLabels.add(containedLabels[0]);
    }
  }

  const labels = Array.from(activeLabels);
  return request.expectedLabel === undefined ? labels : labels.includes(request.expectedLabel);
}

async function readXhsActiveSortLabels(page: Page): Promise<string[]> {
  const labels = await page.evaluate(evaluateXhsActiveSortLabels, { labels: Object.values(XHS_SEARCH_SORTS) }).catch(() => []);
  return Array.isArray(labels) ? labels.filter((label): label is string => typeof label === 'string') : [];
}

export async function switchXhsSearchSort(page: Page, sortKey: XhsSearchSortKey): Promise<void> {
  const sortLabel = XHS_SEARCH_SORTS[sortKey];

  await openXhsSearchFilterPanel(page);
  const beforeSignature = await readXhsSearchResultsSignature(page);
  const clicked = await clickXhsSearchSortLabel(page, sortLabel);
  if (!clicked) {
    throw new Error(`未找到小红书搜索排序选项：${sortLabel}`);
  }

  await page.waitForFunction(
    evaluateXhsActiveSortLabels,
    { labels: Object.values(XHS_SEARCH_SORTS), expectedLabel: sortLabel },
    { timeout: 1_500, polling: 100 },
  ).catch(() => undefined);

  const activeLabels = await readXhsActiveSortLabels(page);
  if (!isXhsSortActive(activeLabels, sortKey)) {
    throw new Error(`小红书搜索排序切换失败：期望 ${sortLabel}，当前 ${activeLabels.join(', ') || '未知'}`);
  }

  await waitForXhsSearchResultsAfterSort(page, beforeSignature, sortLabel);
}

async function readXhsInitialStateSearchCards(page: Page): Promise<XhsSearchCardPayload[]> {
  const state = await page.evaluate(() => (window as unknown as { __INITIAL_STATE__?: unknown }).__INITIAL_STATE__).catch(() => null);
  return parseXhsInitialStateSearchCardPayloads(state);
}

function normalizeXhsAuthorProfileUrl(url: string | null): string | null {
  if (url === null) {
    return null;
  }

  try {
    const parsedUrl = new URL(url, XHS_NOTE_URL_BASE);
    if (!isAllowedXhsUrl(parsedUrl) || !parsedUrl.pathname.startsWith('/user/profile/')) {
      return null;
    }
    return parsedUrl.href;
  } catch {
    return null;
  }
}

async function readXhsDomSearchCards(page: Page): Promise<XhsSearchCardPayload[]> {
  const snapshots = await page.evaluate((): XhsDomSearchCardSnapshot[] => {
    function isVisible(element: Element): boolean {
      const rect = element.getBoundingClientRect();
      const style = window.getComputedStyle(element);
      return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
    }

    return Array.from(document.querySelectorAll('section.note-item')).filter(isVisible).map((section) => {
      const rawText = section instanceof HTMLElement ? section.innerText : section.textContent ?? '';
      const hrefs = Array.from(section.querySelectorAll('a[href]')).flatMap((anchor) => {
        const href = anchor instanceof HTMLAnchorElement ? anchor.href || anchor.getAttribute('href') : anchor.getAttribute('href');
        return href === null || href.trim() === '' ? [] : [href];
      });
      const authorProfileUrl = hrefs.find((href) => href.includes('/user/profile/')) ?? null;
      const image = section.querySelector('img');
      const coverUrl = image === null ? null : image.currentSrc || image.src || image.getAttribute('src');
      const coverAltText = image === null ? null : image.alt || image.getAttribute('aria-label') || image.getAttribute('title');
      const sectionText = (section.textContent ?? '').replace(/\s+/g, ' ').trim();
      const videoMarker = section.querySelector('[class*="video"], [aria-label*="视频"], [data-type="video"]');
      const topicTexts = Array.from(section.querySelectorAll('[class*="tag"], [class*="topic"], [href*="/search_result?keyword="]'))
        .flatMap((element) => {
          const text = (element.textContent ?? '').replace(/^#/, '').trim();
          return text === '' ? [] : [text];
        });

      return {
        rawText,
        hrefs,
        authorProfileUrl,
        coverUrl: coverUrl === null || coverUrl.trim() === '' ? null : coverUrl,
        coverAltText: coverAltText === null || coverAltText.trim() === '' ? null : coverAltText,
        noteType: videoMarker !== null || sectionText.includes('视频') ? 'video' : 'image',
        sourceTopicTexts: topicTexts,
      };
    });
  }).catch(() => []);

  return snapshots.map((snapshot) => ({
    searchResultUrl: pickBestXhsSearchResultUrl(snapshot.hrefs),
    authorProfileUrl: normalizeXhsAuthorProfileUrl(snapshot.authorProfileUrl),
    coverUrl: snapshot.coverUrl,
    noteType: snapshot.noteType,
    coverAltText: snapshot.coverAltText,
    sourceTopicTexts: uniqueTexts(snapshot.sourceTopicTexts),
    rawText: snapshot.rawText,
  }));
}

function appendUniqueXhsSearchCards(collected: XhsSearchCardPayload[], seenFeedIds: Set<string>, cards: XhsSearchCardPayload[]): void {
  for (const card of cards) {
    if (card.searchResultUrl === null) {
      continue;
    }

    const identity = extractXhsNoteIdentity(card.searchResultUrl);
    if (identity === null || seenFeedIds.has(identity.feedId)) {
      continue;
    }

    seenFeedIds.add(identity.feedId);
    collected.push(card);
  }
}

export async function collectXhsSearchNoteRows(page: Page, keyword: string, sortKey: XhsSearchSortKey, limit: number): Promise<XhsSearchNoteRow[]> {
  if (limit <= 0) {
    return [];
  }

  await switchXhsSearchSort(page, sortKey);

  const cards: XhsSearchCardPayload[] = [];
  const seenFeedIds = new Set<string>();
  let unchangedScrolls = 0;

  while (cards.length < limit && unchangedScrolls < 4) {
    const beforeCount = cards.length;
    const domCards = await readXhsDomSearchCards(page);
    const initialStateCards = await readXhsInitialStateSearchCards(page);
    appendUniqueXhsSearchCards(cards, seenFeedIds, pickXhsSearchCardsForCollection(domCards, initialStateCards));

    if (cards.length >= limit) {
      break;
    }

    unchangedScrolls = cards.length === beforeCount ? unchangedScrolls + 1 : 0;
    await page.mouse.wheel(0, 1800);
    await page.waitForTimeout(700);
  }

  return parseXhsSearchNoteRows({ keyword, sortKey, cards }).slice(0, limit);
}

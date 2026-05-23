import type { Page } from 'playwright-core';
import type { HotWordRow } from '../types.js';
import { parseHuitunNumber } from '../utils/number.js';
import { assertHuitunLoggedIn } from './huitun-session.js';

const SEARCH_URL = 'https://xhs.huitun.com/#/hotWords/hot_words_recommend';

function textOrNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

type HotWordCategory = HotWordRow['categories'][number];

function parseCategories(value: string): HotWordRow['categories'] {
  const trimmed = value.trim();
  if (!trimmed || trimmed === '--') return [];

  return trimmed
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .flatMap((line): HotWordCategory[] => {
      const matches = Array.from(line.matchAll(/(.+?)\s+([\d.]+)%/g));
      if (matches.length === 0) return [{ label: line, rate: null }];

      return matches.map((match) => ({ label: match[1].trim(), rate: match[2] }));
    });
}

export function parseHotWordRowsFromCells(sourceKeyword: string, tableRows: string[][]): HotWordRow[] {
  const parsedRows: HotWordRow[] = [];

  for (const cells of tableRows) {
    if (cells.length < 5) continue;

    const word = cells[0].trim();
    if (!word) continue;

    const hotValueText = textOrNull(cells[1]);
    const interactionText = textOrNull(cells[3]);

    parsedRows.push({
      sourceKeyword: sourceKeyword.trim(),
      word,
      hotValueText,
      hotValueNumber: parseHuitunNumber(hotValueText),
      noteCount: parseHuitunNumber(cells[2]),
      interactionText,
      interactionNumber: parseHuitunNumber(interactionText),
      categories: parseCategories(cells[4]),
      rankIndex: parsedRows.length + 1,
    });
  }

  return parsedRows;
}

export async function collectHotWordRows(
  page: Page,
  keyword: string,
  limitHotwords: number,
): Promise<HotWordRow[]> {
  await page.goto(SEARCH_URL, { waitUntil: 'domcontentloaded' });
  await assertHuitunLoggedIn(page);

  try {
    await page.waitForLoadState('networkidle', { timeout: 5000 });
  } catch {
    // Best-effort: Huitun pages can keep background requests open.
  }

  await assertHuitunLoggedIn(page);

  const searchInput = page.getByPlaceholder('请输入热词关键词');
  const searchButton = page
    .locator('.ant-input-search')
    .filter({ has: searchInput })
    .locator('button.ant-input-search-button');

  await searchInput.fill(keyword);
  await Promise.all([page.waitForURL(/hot_words_search/), searchButton.click()]);

  const rowLocator = page.locator('.ant-table-tbody:visible tr.ant-table-row');
  await rowLocator.first().waitFor({ state: 'visible' });

  const tableRows: string[][] = [];
  const rowCount = await rowLocator.count();

  for (let rowIndex = 0; rowIndex < rowCount; rowIndex += 1) {
    tableRows.push(await rowLocator.nth(rowIndex).locator('td').allTextContents());
  }

  return parseHotWordRowsFromCells(keyword, tableRows).slice(0, limitHotwords);
}

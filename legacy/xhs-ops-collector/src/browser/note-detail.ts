import type { Page } from 'playwright-core';
import type { NoteDetail, NoteListRow } from '../types.js';
import { parseHuitunNumber } from '../utils/number.js';

function normalizeLines(text: string): string[] {
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
}

function valueBeforeLabel(lines: string[], label: string): string | null {
  const labelIndex = lines.findIndex((line) => line === label);
  if (labelIndex <= 0) return null;
  return lines[labelIndex - 1] ?? null;
}

function linesAfterLabel(lines: string[], label: string): string[] | null {
  const labelIndex = lines.findIndex((line) => line === label);
  if (labelIndex < 0) return null;
  return lines.slice(labelIndex + 1);
}

export function parseNoteDetailText(huitunNoteKey: string, text: string): NoteDetail {
  const lines = normalizeLines(text);
  const overviewLines = linesAfterLabel(lines, '数据概览') ?? lines;

  return {
    huitunNoteKey,
    estimatedExposure: parseHuitunNumber(valueBeforeLabel(overviewLines, '预估曝光量')),
    estimatedReads: parseHuitunNumber(valueBeforeLabel(overviewLines, '预估阅读量')),
    likes: parseHuitunNumber(valueBeforeLabel(overviewLines, '点赞')),
    collects: parseHuitunNumber(valueBeforeLabel(overviewLines, '收藏')),
    comments: parseHuitunNumber(valueBeforeLabel(overviewLines, '评论')),
    shares: parseHuitunNumber(valueBeforeLabel(overviewLines, '分享')),
    authorFollowers: parseHuitunNumber(valueBeforeLabel(lines, '粉丝数')),
    authorNoteCount: parseHuitunNumber(valueBeforeLabel(lines, '笔记数')),
    authorTotalLikesCollects: parseHuitunNumber(valueBeforeLabel(lines, '赞藏总数')),
    readExposureRatioText: valueBeforeLabel(overviewLines, '阅读曝光比'),
    readFollowerRatioText: valueBeforeLabel(overviewLines, '阅读粉丝比'),
  };
}

export async function collectNoteDetail(page: Page, note: NoteListRow): Promise<NoteDetail | null> {
  const row = page.locator(`tr.ant-table-row[data-row-key="${note.huitunNoteKey}"]`);
  if ((await row.count()) === 0) return null;

  const title = row.first().locator('[class*="note_title"]').first();
  await title.scrollIntoViewIfNeeded();
  await title.click({ force: true });
  const modal = page.locator('.ant-modal').filter({ hasText: '数据概览' }).first();

  try {
    await modal.waitFor({ state: 'visible' });
    const text = await modal.innerText();
    return parseNoteDetailText(note.huitunNoteKey, text);
  } finally {
    await page.keyboard.press('Escape').catch(() => undefined);
    await modal.waitFor({ state: 'hidden' }).catch(() => undefined);
  }
}

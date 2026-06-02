import { chromium } from 'playwright-core';
import type { Browser, BrowserContext, Page } from 'playwright-core';

export interface HuitunSession {
  browser: Browser;
  context: BrowserContext;
  page: Page;
  close: () => Promise<void>;
}

export const HUITUN_LOGIN_REQUIRED_MESSAGE = '当前灰豚登录态已失效，请在已打开的浏览器中重新登录灰豚，然后重新运行采集命令。';
const HUITUN_LOGIN_REQUIRED_PATTERNS = [
  /登录失效/,
  /登录已失效/,
  /登录过期/,
  /登录已过期/,
  /请重新登录/,
  /请先登录/,
  /请登录/,
  /登录后查看/,
  /登录\/注册/,
  /账号已在其它地点登录/,
];

export function isHuitunLoginRequiredText(text: string): boolean {
  const normalizedText = text.replace(/\s+/g, '');
  return HUITUN_LOGIN_REQUIRED_PATTERNS.some((pattern) => pattern.test(normalizedText));
}

export async function assertHuitunLoggedIn(page: Page): Promise<void> {
  let text = '';

  try {
    text = await page.locator('body').innerText();
  } catch {
    text = '';
  }

  if (isHuitunLoginRequiredText(text)) {
    throw new Error(HUITUN_LOGIN_REQUIRED_MESSAGE);
  }
}

export async function createHuitunSession(cdpUrl: string): Promise<HuitunSession> {
  let browser: Browser;

  try {
    browser = await chromium.connectOverCDP(cdpUrl);
  } catch (error) {
    throw new Error(
      `无法连接浏览器 CDP：${cdpUrl}。请先启动带 remote debugging 的 Edge/Chrome，再重试。原始错误：${String(error)}`,
    );
  }

  const context = browser.contexts()[0] ?? (await browser.newContext());
  const page = await context.newPage();
  page.setDefaultTimeout(30_000);

  return {
    browser,
    context,
    page,
    close: async () => {
      await page.close().catch(() => undefined);
      await browser.close({ reason: 'collector finished' }).catch(() => undefined);
    },
  };
}

export async function capturePageSnapshot(page: Page): Promise<{ url: string; text: string; html: string }> {
  const text = await page
    .locator('body')
    .innerText()
    .catch(() => '');
  const html = await page.content().catch(() => '');

  return {
    url: page.url(),
    text,
    html,
  };
}

import { chromium } from 'playwright-core';
import type { Browser, BrowserContext, Page } from 'playwright-core';

export interface XhsSession {
  browser: Browser;
  context: BrowserContext;
  page: Page;
  close: () => Promise<void>;
}

async function installXhsBrowserContextHelpers(context: BrowserContext): Promise<void> {
  await context.addInitScript(() => {
    (globalThis as typeof globalThis & { __name?: <T>(target: T) => T }).__name = (target) => target;
  });
}

export async function createXhsSession(cdpUrl: string): Promise<XhsSession> {
  let browser: Browser;

  try {
    browser = await chromium.connectOverCDP(cdpUrl);
  } catch (error) {
    throw new Error(
      `无法连接浏览器 CDP：${cdpUrl}。请先启动带 remote debugging 且已登录小红书的 Edge/Chrome，再重试。原始错误：${String(error)}`,
    );
  }

  const context = browser.contexts()[0] ?? (await browser.newContext());
  await installXhsBrowserContextHelpers(context);
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

export async function captureXhsPageSnapshot(page: Page): Promise<{ url: string; text: string; html: string }> {
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

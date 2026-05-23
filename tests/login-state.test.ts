import { beforeEach, describe, expect, it, vi } from 'vitest';

const playwrightMocks = vi.hoisted(() => ({
  connectOverCDP: vi.fn(),
}));

vi.mock('playwright-core', () => ({
  chromium: {
    connectOverCDP: playwrightMocks.connectOverCDP,
  },
}));

import { createHuitunSession, isHuitunLoginRequiredText } from '../src/browser/huitun-session.js';

beforeEach(() => {
  playwrightMocks.connectOverCDP.mockReset();
});

describe('isHuitunLoginRequiredText', () => {
  it('detects Huitun login-required and session-expired messages', () => {
    expect(isHuitunLoginRequiredText('登录失效')).toBe(true);
    expect(isHuitunLoginRequiredText('请重新登录')).toBe(true);
    expect(isHuitunLoginRequiredText('请登录')).toBe(true);
    expect(isHuitunLoginRequiredText('登录后查看')).toBe(true);
    expect(isHuitunLoginRequiredText('登录/注册')).toBe(true);
    expect(isHuitunLoginRequiredText('您的账号已在其它地点登录')).toBe(true);
  });

  it('does not flag normal logged-in hot word page text', () => {
    expect(isHuitunLoginRequiredText('热词推荐\n大家都在搜')).toBe(false);
  });
});

describe('createHuitunSession', () => {
  it('closes the created page and disconnects the CDP browser connection', async () => {
    const closePage = vi.fn<() => Promise<void>>().mockResolvedValue(undefined);
    const closeBrowser = vi.fn<() => Promise<void>>().mockResolvedValue(undefined);
    const newPage = vi.fn<() => Promise<{ close: typeof closePage; setDefaultTimeout: (timeout: number) => void }>>().mockResolvedValue({
      close: closePage,
      setDefaultTimeout: vi.fn(),
    });
    const browser = {
      close: closeBrowser,
      contexts: () => [{ newPage }],
    };
    playwrightMocks.connectOverCDP.mockResolvedValue(browser);

    const session = await createHuitunSession('http://127.0.0.1:9222');
    await session.close();

    expect(closePage).toHaveBeenCalledTimes(1);
    expect(closeBrowser).toHaveBeenCalledWith({ reason: 'collector finished' });
  });
});

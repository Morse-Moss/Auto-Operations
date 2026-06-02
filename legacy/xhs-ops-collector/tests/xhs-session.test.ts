import { describe, expect, it, vi } from 'vitest';

const connectedBrowser = vi.hoisted(() => ({
  close: vi.fn().mockResolvedValue(undefined),
  contexts: vi.fn(),
  newContext: vi.fn(),
}));

const chromiumMock = vi.hoisted(() => ({
  connectOverCDP: vi.fn().mockResolvedValue(connectedBrowser),
}));

vi.mock('playwright-core', () => ({
  chromium: chromiumMock,
}));

import { createXhsSession } from '../src/browser/xhs-session.js';

describe('XHS browser session', () => {
  it('installs a browser context helper for tsx-compiled evaluate callbacks', async () => {
    const page = {
      addInitScript: vi.fn().mockResolvedValue(undefined),
      setDefaultTimeout: vi.fn(),
      close: vi.fn().mockResolvedValue(undefined),
    };
    const context = {
      addInitScript: vi.fn().mockResolvedValue(undefined),
      newPage: vi.fn().mockResolvedValue(page),
    };
    connectedBrowser.contexts.mockReturnValue([context]);

    const session = await createXhsSession('http://127.0.0.1:9222');

    expect(context.addInitScript).toHaveBeenCalledOnce();
    expect(context.newPage).toHaveBeenCalledOnce();
    expect(page.addInitScript).not.toHaveBeenCalled();
    const helper = context.addInitScript.mock.calls[0][0] as () => void;
    const target = () => 'ok';
    const globalWithName = globalThis as typeof globalThis & { __name?: <T>(value: T) => T };
    const previousName = globalWithName.__name;
    try {
      delete globalWithName.__name;
      helper();
      const injectedName = globalWithName.__name as ((value: typeof target) => typeof target) | undefined;
      expect(injectedName).toBeTypeOf('function');
      expect(injectedName?.(target)).toBe(target);
    } finally {
      if (previousName === undefined) {
        delete globalWithName.__name;
      } else {
        globalWithName.__name = previousName;
      }
    }
    await session.close();
  });
});

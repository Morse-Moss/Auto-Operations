import { describe, expect, it } from 'vitest';

import { formatRawSnapshotTextContent } from '../src/cli.js';

describe('formatRawSnapshotTextContent', () => {
  it('keeps existing page text unchanged when no diagnostic message is provided', () => {
    expect(formatRawSnapshotTextContent('页面文本')).toBe('页面文本');
  });

  it('prefixes the diagnostic message before the captured page text', () => {
    expect(formatRawSnapshotTextContent('页面文本', '详情弹窗失败')).toBe('详情弹窗失败\n\n页面文本');
  });
});

import { describe, expect, it } from 'vitest';

import { parseOptions } from '../src/cli.js';

describe('parseOptions', () => {
  it('parses global target note collection options', () => {
    expect(
      parseOptions([
        'node',
        'src/cli.ts',
        '--keyword',
        '浴缸',
        '--target-notes',
        '20',
        '--limit-hotwords',
        '5',
        '--days',
        '7',
      ]),
    ).toMatchObject({
      keyword: '浴缸',
      targetNotes: 20,
      limitHotwords: 5,
      limitNotes: 20,
      days: 7,
    });
  });

  it('preserves per-hotword mode when no global target is provided', () => {
    const options = parseOptions(['node', 'src/cli.ts', '--keyword', '浴缸']);

    expect(options.targetNotes).toBeUndefined();
    expect(options.limitHotwords).toBe(10);
    expect(options.limitNotes).toBe(20);
  });

  it('rejects non-positive target note counts', () => {
    expect(() => parseOptions(['node', 'src/cli.ts', '--keyword', '浴缸', '--target-notes', '0'])).toThrow(
      '--target-notes 必须是正整数，收到：0',
    );
  });
});

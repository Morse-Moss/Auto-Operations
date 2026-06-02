import { describe, expect, it } from 'vitest';
import { parseHuitunNumber } from '../src/utils/number.js';

describe('parseHuitunNumber', () => {
  it('parses blank and dash values as null', () => {
    expect(parseHuitunNumber('')).toBeNull();
    expect(parseHuitunNumber('--')).toBeNull();
    expect(parseHuitunNumber('暂无')).toBeNull();
  });

  it('parses comma separated integers', () => {
    expect(parseHuitunNumber('1,317')).toBe(1317);
    expect(parseHuitunNumber('10')).toBe(10);
  });

  it('parses w suffix as ten-thousands', () => {
    expect(parseHuitunNumber('1.4w')).toBe(14000);
    expect(parseHuitunNumber('16.4w')).toBe(164000);
    expect(parseHuitunNumber('1984.6w')).toBe(19846000);
  });

  it('parses Chinese 万 suffix as ten-thousands', () => {
    expect(parseHuitunNumber('1.4万')).toBe(14000);
    expect(parseHuitunNumber('120.9万')).toBe(1209000);
  });
});

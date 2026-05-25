import { describe, expect, it } from 'vitest';
import { parseHotWordRowsFromCells, prioritizeExactHotWordRows } from '../src/browser/hotword-search.js';

import type { HotWordRow } from '../src/types.js';

describe('parseHotWordRowsFromCells', () => {
  it('parses hot word search table cells into HotWordRow values', () => {
    const rows = [
      ['浴缸', '1,510', '26', '1.4w', '家居家装 36.4%\n摄影 36.4%\n兴趣爱好 9.1%'],
      ['自砌浴缸', '912', '2', '8,920', '家居家装 100%'],
      ['酒店带浴缸', '23', '1', '226', '--'],
      ['浴室改造', '521', '4', '1,120', '家居家装 36.4% 摄影 36.4% 兴趣爱好 9.1%'],
    ];

    const expected: HotWordRow[] = [
      {
        sourceKeyword: '浴缸',
        word: '浴缸',
        hotValueText: '1,510',
        hotValueNumber: 1510,
        noteCount: 26,
        interactionText: '1.4w',
        interactionNumber: 14000,
        categories: [
          { label: '家居家装', rate: '36.4' },
          { label: '摄影', rate: '36.4' },
          { label: '兴趣爱好', rate: '9.1' },
        ],
        rankIndex: 1,
      },
      {
        sourceKeyword: '浴缸',
        word: '自砌浴缸',
        hotValueText: '912',
        hotValueNumber: 912,
        noteCount: 2,
        interactionText: '8,920',
        interactionNumber: 8920,
        categories: [{ label: '家居家装', rate: '100' }],
        rankIndex: 2,
      },
      {
        sourceKeyword: '浴缸',
        word: '酒店带浴缸',
        hotValueText: '23',
        hotValueNumber: 23,
        noteCount: 1,
        interactionText: '226',
        interactionNumber: 226,
        categories: [],
        rankIndex: 3,
      },
      {
        sourceKeyword: '浴缸',
        word: '浴室改造',
        hotValueText: '521',
        hotValueNumber: 521,
        noteCount: 4,
        interactionText: '1,120',
        interactionNumber: 1120,
        categories: [
          { label: '家居家装', rate: '36.4' },
          { label: '摄影', rate: '36.4' },
          { label: '兴趣爱好', rate: '9.1' },
        ],
        rankIndex: 4,
      },
    ];

    expect(parseHotWordRowsFromCells('浴缸', rows)).toEqual(expected);
  });

  it('prioritizes exact keyword matches before fuzzy hot words', () => {
    const rows = parseHotWordRowsFromCells('游戏', [
      ['游戯', '1,900', '30', '9w', '游戏 100%'],
      ['游戏', '1,500', '50', '8w', '游戏 100%'],
      ['游戏日常', '1,000', '20', '3w', '游戏 100%'],
    ]);

    expect(prioritizeExactHotWordRows('游戏', rows).map((row) => row.word)).toEqual(['游戏', '游戯', '游戏日常']);
  });
});

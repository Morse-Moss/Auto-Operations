import { describe, expect, it } from 'vitest';

import { buildCollectionQualityReport, effectiveNoteLimit, verifyLikesDescending } from '../src/collection-quality.js';

describe('effectiveNoteLimit', () => {
  it('caps note collection at 20 hot posts', () => {
    expect(effectiveNoteLimit(25)).toBe(20);
    expect(effectiveNoteLimit(20)).toBe(20);
  });

  it('keeps smaller requested limits unchanged', () => {
    expect(effectiveNoteLimit(8)).toBe(8);
  });
});

describe('verifyLikesDescending', () => {
  it('verifies non-increasing likes order', () => {
    expect(verifyLikesDescending([{ likes: 30 }, { likes: 20 }, { likes: 20 }])).toEqual({
      status: 'verified',
      checkedRows: 3,
      missingLikesCount: 0,
      violationCount: 0,
    });
  });

  it('detects likes order violations', () => {
    expect(verifyLikesDescending([{ likes: 30 }, { likes: 35 }, { likes: 10 }])).toEqual({
      status: 'violated',
      checkedRows: 3,
      missingLikesCount: 0,
      violationCount: 1,
    });
  });

  it('reports missing likes and insufficient comparable data', () => {
    expect(verifyLikesDescending([{ likes: null }, { likes: 20 }])).toEqual({
      status: 'insufficient_data',
      checkedRows: 2,
      missingLikesCount: 1,
      violationCount: 0,
    });
  });
});

describe('buildCollectionQualityReport', () => {
  it('marks a complete verified run as ok', () => {
    const report = buildCollectionQualityReport({
      runId: 12,
      keyword: '浴缸',
      days: 7,
      requestedLimitHotwords: 1,
      requestedLimitNotes: 25,
      status: 'success',
      totals: {
        hotWords: 1,
        hotWordSnapshots: 1,
        notes: 20,
        detailedNotes: 20,
        rawSnapshots: 0,
      },
      rawSnapshotsByKind: {},
      hotWords: [
        {
          word: '浴缸',
          targetNotes: 20,
          exposedNotes: 20,
          collectedNotes: 20,
          duplicateNotes: 0,
          detailedNotes: 20,
          detailFailures: 0,
          likesSort: {
            status: 'verified',
            checkedRows: 20,
            missingLikesCount: 0,
            violationCount: 0,
          },
          notesWithLikes: 20,
          missingLikes: 0,
          warnings: [],
        },
      ],
    });

    expect(report.level).toBe('ok');
    expect(report.mode).toBe('per_hotword');
    expect(report.targetNotes).toBeNull();
    expect(report.targetReached).toBeNull();
    expect(report.effectiveLimitNotes).toBe(20);
    expect(report.rates.detailCoverageRate).toBe(1);
    expect(report.warnings).toEqual([]);
  });

  it('marks incomplete detail coverage as warn', () => {
    const report = buildCollectionQualityReport({
      runId: 13,
      keyword: '浴缸',
      days: 7,
      requestedLimitHotwords: 1,
      requestedLimitNotes: 20,
      status: 'partial_success',
      totals: {
        hotWords: 1,
        hotWordSnapshots: 1,
        notes: 20,
        detailedNotes: 12,
        rawSnapshots: 8,
      },
      rawSnapshotsByKind: { parse_note_detail_error: 8 },
      hotWords: [
        {
          word: '浴缸',
          targetNotes: 20,
          exposedNotes: 20,
          collectedNotes: 20,
          duplicateNotes: 0,
          detailedNotes: 12,
          detailFailures: 8,
          likesSort: {
            status: 'verified',
            checkedRows: 20,
            missingLikesCount: 0,
            violationCount: 0,
          },
          notesWithLikes: 20,
          missingLikes: 0,
          warnings: [],
        },
      ],
    });

    expect(report.level).toBe('warn');
    expect(report.warnings).toContain('部分笔记详情采集失败。');
  });

  it('does not fail a single collected note with insufficient comparable likes data', () => {
    const report = buildCollectionQualityReport({
      runId: 14,
      keyword: '浴缸',
      days: 7,
      requestedLimitHotwords: 1,
      requestedLimitNotes: 1,
      status: 'success',
      totals: {
        hotWords: 1,
        hotWordSnapshots: 1,
        notes: 1,
        detailedNotes: 1,
        rawSnapshots: 0,
      },
      rawSnapshotsByKind: {},
      hotWords: [
        {
          word: '浴缸',
          targetNotes: 1,
          exposedNotes: 1,
          collectedNotes: 1,
          duplicateNotes: 0,
          detailedNotes: 1,
          detailFailures: 0,
          likesSort: {
            status: 'insufficient_data',
            checkedRows: 1,
            missingLikesCount: 0,
            violationCount: 0,
          },
          notesWithLikes: 1,
          missingLikes: 0,
          warnings: [],
        },
      ],
    });

    expect(report.level).toBe('ok');
    expect(report.warnings).not.toContain('存在热词未能确认点赞倒序，已跳过非热点采集。');
  });

  it('marks violated likes ordering as fail', () => {
    const report = buildCollectionQualityReport({
      runId: 14,
      keyword: '浴缸',
      days: 7,
      requestedLimitHotwords: 1,
      requestedLimitNotes: 20,
      status: 'partial_success',
      totals: {
        hotWords: 1,
        hotWordSnapshots: 1,
        notes: 0,
        detailedNotes: 0,
        rawSnapshots: 1,
      },
      rawSnapshotsByKind: { note_list_sort_error: 1 },
      hotWords: [
        {
          word: '浴缸',
          targetNotes: 20,
          exposedNotes: 3,
          collectedNotes: 0,
          duplicateNotes: 0,
          detailedNotes: 0,
          detailFailures: 0,
          likesSort: {
            status: 'violated',
            checkedRows: 3,
            missingLikesCount: 0,
            violationCount: 1,
          },
          notesWithLikes: 3,
          missingLikes: 0,
          warnings: ['点赞排序验证失败。'],
        },
      ],
    });

    expect(report.level).toBe('fail');
    expect(report.warnings).toContain('存在热词未能确认点赞倒序，已跳过非热点采集。');
  });

  it('marks a reached global target run as ok', () => {
    const report = buildCollectionQualityReport({
      runId: 15,
      keyword: '浴缸',
      days: 7,
      requestedLimitHotwords: 5,
      requestedLimitNotes: 20,
      targetNotes: 20,
      status: 'success',
      totals: {
        hotWords: 5,
        hotWordSnapshots: 3,
        notes: 20,
        detailedNotes: 20,
        rawSnapshots: 0,
      },
      rawSnapshotsByKind: {},
      hotWords: [
        {
          word: '浴缸',
          targetNotes: 20,
          exposedNotes: 10,
          collectedNotes: 10,
          duplicateNotes: 0,
          detailedNotes: 10,
          detailFailures: 0,
          likesSort: {
            status: 'verified',
            checkedRows: 10,
            missingLikesCount: 0,
            violationCount: 0,
          },
          notesWithLikes: 10,
          missingLikes: 0,
          warnings: [],
        },
        {
          word: '浴缸推荐',
          targetNotes: 20,
          exposedNotes: 12,
          collectedNotes: 10,
          duplicateNotes: 2,
          detailedNotes: 10,
          detailFailures: 0,
          likesSort: {
            status: 'verified',
            checkedRows: 12,
            missingLikesCount: 0,
            violationCount: 0,
          },
          notesWithLikes: 10,
          missingLikes: 0,
          warnings: [],
        },
      ],
    });

    expect(report.level).toBe('ok');
    expect(report.mode).toBe('global_target');
    expect(report.targetNotes).toBe(20);
    expect(report.collectedTargetNotes).toBe(20);
    expect(report.targetReached).toBe(true);
    expect(report.hotWordsAttempted).toBe(2);
    expect(report.rates.noteCompletionRate).toBe(1);
    expect(report.contributingHotWords).toEqual([
      { word: '浴缸', exposedNotes: 10, collectedNotes: 10, duplicateNotes: 0 },
      { word: '浴缸推荐', exposedNotes: 12, collectedNotes: 10, duplicateNotes: 2 },
    ]);
    expect(report.warnings).toEqual([]);
  });

  it('marks an unreached global target run with notes as warn', () => {
    const report = buildCollectionQualityReport({
      runId: 16,
      keyword: '浴缸',
      days: 7,
      requestedLimitHotwords: 5,
      requestedLimitNotes: 20,
      targetNotes: 20,
      status: 'success',
      totals: {
        hotWords: 5,
        hotWordSnapshots: 5,
        notes: 10,
        detailedNotes: 10,
        rawSnapshots: 0,
      },
      rawSnapshotsByKind: {},
      hotWords: [
        {
          word: '浴缸',
          targetNotes: 20,
          exposedNotes: 10,
          collectedNotes: 10,
          duplicateNotes: 0,
          detailedNotes: 10,
          detailFailures: 0,
          likesSort: {
            status: 'verified',
            checkedRows: 10,
            missingLikesCount: 0,
            violationCount: 0,
          },
          notesWithLikes: 10,
          missingLikes: 0,
          warnings: [],
        },
      ],
    });

    expect(report.level).toBe('warn');
    expect(report.targetReached).toBe(false);
    expect(report.rates.noteCompletionRate).toBe(0.5);
    expect(report.warnings).toContain('目标热点笔记未采满：请求 20 条，实际采到 10 条。');
  });

  it('calculates per-hotword rates from attempted rows when SQLite deduplicates persisted notes', () => {
    const report = buildCollectionQualityReport({
      runId: 17,
      keyword: '浴缸',
      days: 7,
      requestedLimitHotwords: 2,
      requestedLimitNotes: 3,
      status: 'success',
      totals: {
        hotWords: 2,
        hotWordSnapshots: 2,
        notes: 3,
        detailedNotes: 3,
        rawSnapshots: 0,
      },
      rawSnapshotsByKind: {},
      hotWords: [
        {
          word: '浴缸',
          targetNotes: 3,
          exposedNotes: 3,
          collectedNotes: 3,
          duplicateNotes: 0,
          detailedNotes: 3,
          detailFailures: 0,
          likesSort: {
            status: 'verified',
            checkedRows: 3,
            missingLikesCount: 0,
            violationCount: 0,
          },
          notesWithLikes: 3,
          missingLikes: 0,
          warnings: [],
        },
        {
          word: '自砌浴缸',
          targetNotes: 3,
          exposedNotes: 3,
          collectedNotes: 3,
          duplicateNotes: 0,
          detailedNotes: 3,
          detailFailures: 0,
          likesSort: {
            status: 'verified',
            checkedRows: 3,
            missingLikesCount: 0,
            violationCount: 0,
          },
          notesWithLikes: 3,
          missingLikes: 0,
          warnings: [],
        },
      ],
    });

    expect(report.mode).toBe('per_hotword');
    expect(report.rates.noteCompletionRate).toBe(1);
    expect(report.rates.likesCompletenessRate).toBe(1);
  });
});

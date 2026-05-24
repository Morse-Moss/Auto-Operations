import { describe, expect, it } from 'vitest';

import { formatRunReport } from '../src/reporting/report.js';
import type { RunReportData } from '../src/reporting/types.js';

const reportData: RunReportData = {
  run: {
    id: 123,
    keyword: '护肤',
    days: 7,
    limitHotwords: 10,
    limitNotes: 20,
    status: 'partial_success',
    startedAt: '2026-05-23 10:00:00',
    finishedAt: '2026-05-23 10:08:00',
    errorStage: null,
    errorMessage: null,
  },
  totals: {
    hotWords: 10,
    hotWordSnapshots: 9,
    notes: 87,
    detailedNotes: 82,
    rawSnapshots: 2,
  },
  detailCoverageRate: 82 / 87,
  likesCompletenessRate: 1,
  rawSnapshotsByKind: {
    parse_note_detail_error: 2,
  },
  hotWordContributions: [
    { hotWord: '早C晚A', notes: 20, topLikes: 12000, bestRank: 1 },
    { hotWord: '敏感肌修护', notes: 18, topLikes: 8300, bestRank: 1 },
  ],
};

describe('formatRunReport', () => {
  it('formats a human-readable run report', () => {
    const text = formatRunReport(reportData);

    expect(text).toContain('Run #123  keyword="护肤"  status=partial_success  days=7');
    expect(text).toContain('Started: 2026-05-23 10:00:00  Finished: 2026-05-23 10:08:00');
    expect(text).toContain('- Hot words: 10');
    expect(text).toContain('- Hot word snapshots: 9');
    expect(text).toContain('- Notes: 87');
    expect(text).toContain('- Detailed notes: 82');
    expect(text).toContain('- Raw snapshots: 2');
    expect(text).toContain('- Detail coverage: 94.3%');
    expect(text).toContain('- Likes completeness: 100.0%');
    expect(text).toContain('1. 早C晚A  notes=20  top_likes=12000  best_rank=1');
    expect(text).toContain('- parse_note_detail_error: 2');
    expect(text).toContain('- Run completed with status partial_success.');
    expect(text).toContain('- Some note details are missing.');
    expect(text).toContain('Export note: CSV export keeps one row per stable note identity.');
    expect(text).not.toContain('duplicates=');
  });

  it('marks a running run and empty notes clearly', () => {
    const text = formatRunReport({
      ...reportData,
      run: { ...reportData.run, status: 'running', finishedAt: null },
      totals: { ...reportData.totals, notes: 0, detailedNotes: 0, rawSnapshots: 0 },
      detailCoverageRate: 0,
      likesCompletenessRate: 0,
      rawSnapshotsByKind: {},
      hotWordContributions: [],
    });

    expect(text).toContain('Finished: still running');
    expect(text).toContain('- Run is still running; report reflects currently persisted rows.');
    expect(text).toContain('- No notes were collected for this run.');
    expect(text).toContain('Top contributing hot words\n- None');
    expect(text).toContain('Raw snapshot warnings\n- None');
  });
});

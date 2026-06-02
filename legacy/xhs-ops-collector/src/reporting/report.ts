import type { RunReportData } from './types.js';

function formatPercent(rate: number): string {
  return `${(rate * 100).toFixed(1)}%`;
}

function formatNullableNumber(value: number | null): string {
  return value === null ? 'n/a' : String(value);
}

function buildWarnings(data: RunReportData): string[] {
  const warnings: string[] = [];

  if (data.run.status === 'running') {
    warnings.push('Run is still running; report reflects currently persisted rows.');
  } else if (data.run.status !== 'success') {
    warnings.push(`Run completed with status ${data.run.status}.`);
  }

  if (data.totals.notes === 0) {
    warnings.push('No notes were collected for this run.');
  }

  if (data.totals.notes > 0 && data.totals.detailedNotes < data.totals.notes) {
    warnings.push('Some note details are missing.');
  }

  if (data.totals.rawSnapshots > 0) {
    warnings.push('Raw snapshots were captured; inspect warning kinds below.');
  }

  if (data.run.errorStage !== null || data.run.errorMessage !== null) {
    warnings.push(`Run error: ${data.run.errorStage ?? 'unknown'} - ${data.run.errorMessage ?? 'unknown'}.`);
  }

  return warnings;
}

export function formatRunReport(data: RunReportData): string {
  const lines: string[] = [
    `Run #${data.run.id}  keyword="${data.run.keyword}"  status=${data.run.status}  days=${data.run.days}`,
    `Started: ${data.run.startedAt}  Finished: ${data.run.finishedAt ?? 'still running'}`,
    '',
    'Collection parameters',
    `- Limit hot words: ${data.run.limitHotwords}`,
    `- Limit notes: ${data.run.limitNotes}`,
    '',
    'Totals',
    `- Hot words: ${data.totals.hotWords}`,
    `- Hot word snapshots: ${data.totals.hotWordSnapshots}`,
    `- Notes: ${data.totals.notes}`,
    `- Detailed notes: ${data.totals.detailedNotes}`,
    `- Raw snapshots: ${data.totals.rawSnapshots}`,
    '',
    'Coverage',
    `- Detail coverage: ${formatPercent(data.detailCoverageRate)}`,
    `- Likes completeness: ${formatPercent(data.likesCompletenessRate)}`,
    '',
    'Export note: CSV export keeps one row per stable note identity.',
    '',
    'Top contributing hot words',
  ];

  if (data.hotWordContributions.length === 0) {
    lines.push('- None');
  } else {
    data.hotWordContributions.forEach((hotWord, index) => {
      lines.push(
        `${index + 1}. ${hotWord.hotWord}  notes=${hotWord.notes}  top_likes=${formatNullableNumber(
          hotWord.topLikes,
        )}  best_rank=${formatNullableNumber(hotWord.bestRank)}`,
      );
    });
  }

  lines.push('', 'Raw snapshot warnings');
  const rawSnapshotEntries = Object.entries(data.rawSnapshotsByKind);
  if (rawSnapshotEntries.length === 0) {
    lines.push('- None');
  } else {
    rawSnapshotEntries.forEach(([kind, count]) => {
      lines.push(`- ${kind}: ${count}`);
    });
  }

  lines.push('', 'Warnings');
  const warnings = buildWarnings(data);
  if (warnings.length === 0) {
    lines.push('- None');
  } else {
    warnings.forEach((warning) => {
      lines.push(`- ${warning}`);
    });
  }

  return `${lines.join('\n')}\n`;
}

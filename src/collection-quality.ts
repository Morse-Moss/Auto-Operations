import type { NoteListRow, RunStatus } from './types.js';

export type QualityLevel = 'ok' | 'warn' | 'fail';

export interface LikesSortVerification {
  status: 'verified' | 'violated' | 'insufficient_data';
  checkedRows: number;
  missingLikesCount: number;
  violationCount: number;
}

export interface HotWordCollectionQuality {
  word: string;
  targetNotes: number;
  exposedNotes: number;
  collectedNotes: number;
  duplicateNotes: number;
  detailedNotes: number;
  detailFailures: number;
  likesSort: LikesSortVerification;
  notesWithLikes: number;
  missingLikes: number;
  warnings: string[];
}

export interface CollectionQualityReportTotals {
  hotWords: number;
  hotWordSnapshots: number;
  notes: number;
  detailedNotes: number;
  rawSnapshots: number;
}

export interface ContributingHotWordQuality {
  word: string;
  exposedNotes: number;
  collectedNotes: number;
  duplicateNotes: number;
}

export interface CollectionQualityReport {
  runId: number;
  keyword: string;
  days: number;
  requestedLimitHotwords: number;
  requestedLimitNotes: number;
  effectiveLimitNotes: number;
  mode: 'per_hotword' | 'global_target';
  targetNotes: number | null;
  collectedTargetNotes: number;
  targetReached: boolean | null;
  hotWordsAttempted: number;
  contributingHotWords: ContributingHotWordQuality[];
  status: RunStatus;
  level: QualityLevel;
  totals: CollectionQualityReportTotals;
  rates: {
    noteCompletionRate: number;
    detailCoverageRate: number;
    likesCompletenessRate: number;
  };
  rawSnapshotsByKind: Record<string, number>;
  hotWords: HotWordCollectionQuality[];
  warnings: string[];
}

export interface CollectionQualityReportInput {
  runId: number;
  keyword: string;
  days: number;
  requestedLimitHotwords: number;
  requestedLimitNotes: number;
  targetNotes?: number;
  status: RunStatus;
  totals: CollectionQualityReportTotals;
  rawSnapshotsByKind: Record<string, number>;
  hotWords: HotWordCollectionQuality[];
}

function ratio(numerator: number, denominator: number): number {
  return denominator === 0 ? 0 : numerator / denominator;
}

export function effectiveNoteLimit(requestedLimitNotes: number): number {
  return Math.min(requestedLimitNotes, 20);
}

export function verifyLikesDescending(rows: Array<Pick<NoteListRow, 'likes'>>): LikesSortVerification {
  const likes = rows.map((row) => row.likes);
  const comparableLikes = likes.filter((value): value is number => value !== null);
  let violationCount = 0;

  for (let index = 1; index < comparableLikes.length; index += 1) {
    if (comparableLikes[index] > comparableLikes[index - 1]) {
      violationCount += 1;
    }
  }

  return {
    status: violationCount > 0 ? 'violated' : comparableLikes.length >= 2 ? 'verified' : 'insufficient_data',
    checkedRows: rows.length,
    missingLikesCount: likes.length - comparableLikes.length,
    violationCount,
  };
}

export function buildCollectionQualityReport(input: CollectionQualityReportInput): CollectionQualityReport {
  const effectiveLimitNotes = effectiveNoteLimit(input.requestedLimitNotes);
  const mode = input.targetNotes === undefined ? 'per_hotword' : 'global_target';
  const targetNotes = input.targetNotes ?? null;
  const collectedTargetNotes = input.totals.notes;
  const targetReached = targetNotes === null ? null : collectedTargetNotes >= targetNotes;
  const warnings: string[] = [];
  const hasSortFailure = input.hotWords.some((hotWord) => hotWord.likesSort.status === 'violated');
  const hasIncompleteDetails = input.totals.detailedNotes < input.totals.notes;
  const hasIncompleteNotes = input.hotWords.some((hotWord) => hotWord.collectedNotes < hotWord.targetNotes);

  if (hasSortFailure) {
    warnings.push('存在热词未能确认点赞倒序，已跳过非热点采集。');
  }

  if (hasIncompleteDetails) {
    warnings.push('部分笔记详情采集失败。');
  }

  if (mode === 'global_target') {
    if (targetReached === false && targetNotes !== null) {
      warnings.push(`目标热点笔记未采满：请求 ${targetNotes} 条，实际采到 ${collectedTargetNotes} 条。`);
    }
  } else if (hasIncompleteNotes) {
    warnings.push('部分热词可采集笔记数低于目标数量。');
  }

  const attemptedNotes = input.hotWords.reduce((sum, hotWord) => sum + hotWord.collectedNotes, 0);
  const level: QualityLevel = hasSortFailure || attemptedNotes === 0 ? 'fail' : warnings.length > 0 ? 'warn' : 'ok';
  const notesWithLikes = input.hotWords.reduce((sum, hotWord) => sum + hotWord.notesWithLikes, 0);
  const noteCompletionRateDenominator = targetNotes ?? input.hotWords.length * effectiveLimitNotes;
  const noteCompletionRateNumerator = targetNotes === null ? attemptedNotes : input.totals.notes;
  const detailCoverageRateDenominator = targetNotes === null ? attemptedNotes : input.totals.notes;
  const contributingHotWords = input.hotWords.map((hotWord) => ({
    word: hotWord.word,
    exposedNotes: hotWord.exposedNotes,
    collectedNotes: hotWord.collectedNotes,
    duplicateNotes: hotWord.duplicateNotes,
  }));

  return {
    runId: input.runId,
    keyword: input.keyword,
    days: input.days,
    requestedLimitHotwords: input.requestedLimitHotwords,
    requestedLimitNotes: input.requestedLimitNotes,
    effectiveLimitNotes,
    mode,
    targetNotes,
    collectedTargetNotes,
    targetReached,
    hotWordsAttempted: input.hotWords.length,
    contributingHotWords,
    status: input.status,
    level,
    totals: input.totals,
    rates: {
      noteCompletionRate: ratio(noteCompletionRateNumerator, noteCompletionRateDenominator),
      detailCoverageRate: ratio(input.totals.detailedNotes, detailCoverageRateDenominator),
      likesCompletenessRate: ratio(notesWithLikes, attemptedNotes),
    },
    rawSnapshotsByKind: input.rawSnapshotsByKind,
    hotWords: input.hotWords,
    warnings,
  };
}

import type { RunStatus } from '../types.js';

export interface CollectionRunRecord {
  id: number;
  keyword: string;
  days: number;
  limitHotwords: number;
  limitNotes: number;
  status: RunStatus;
  startedAt: string;
  finishedAt: string | null;
  errorStage: string | null;
  errorMessage: string | null;
}

export interface RunReportTotals {
  hotWords: number;
  hotWordSnapshots: number;
  notes: number;
  detailedNotes: number;
  rawSnapshots: number;
}

export interface HotWordContribution {
  hotWord: string;
  notes: number;
  topLikes: number | null;
  bestRank: number | null;
}

export interface RunReportData {
  run: CollectionRunRecord;
  totals: RunReportTotals;
  detailCoverageRate: number;
  likesCompletenessRate: number;
  rawSnapshotsByKind: Record<string, number>;
  hotWordContributions: HotWordContribution[];
}

export interface NoteExportRow {
  id: number;
  runId: number;
  sourceKeyword: string;
  hotWord: string;
  listRank: number | null;
  listPage: number | null;
  title: string;
  authorName: string | null;
  isVideo: number;
  publishedAt: string | null;
  likes: number | null;
  collects: number | null;
  comments: number | null;
  shares: number | null;
  estimatedReads: number | null;
  estimatedExposure: number | null;
  authorFollowers: number | null;
  authorNoteCount: number | null;
  readExposureRatioText: string | null;
  readFollowerRatioText: string | null;
  tagsJson: string;
  huitunNoteKey: string;
}

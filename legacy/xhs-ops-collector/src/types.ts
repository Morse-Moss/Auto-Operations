export type RunStatus = 'running' | 'success' | 'partial_success' | 'failed';

export interface CollectorOptions {
  keyword: string;
  limitHotwords: number;
  limitNotes: number;
  targetNotes?: number;
  days: 7 | 30 | 90 | 180;
  dbPath: string;
  cdpUrl: string;
  headless: boolean;
}

export interface CollectionRunInput {
  keyword: string;
  days: number;
  limitHotwords: number;
  limitNotes: number;
}

export interface HotWordRow {
  sourceKeyword: string;
  word: string;
  hotValueText: string | null;
  hotValueNumber: number | null;
  noteCount: number | null;
  interactionText: string | null;
  interactionNumber: number | null;
  categories: Array<{ label: string; rate: string | null }>;
  rankIndex: number;
}

export interface HotWordSnapshot {
  word: string;
  days: number;
  pageUrl: string;
  heatText: string | null;
  relatedNotesText: string | null;
  totalInteractionsText: string | null;
  overview: Record<string, string>;
}

export interface NoteListRow {
  hotWord: string;
  huitunNoteKey: string;
  title: string;
  authorName: string | null;
  authorLevel: string | null;
  coverUrl: string | null;
  isVideo: boolean;
  videoDuration: string | null;
  publishedAt: string | null;
  updatedAt: string | null;
  tags: string[];
  estimatedReads: number | null;
  likes: number | null;
  collects: number | null;
  comments: number | null;
  listRank?: number;
  listPage?: number;
}

export interface NoteDetail {
  huitunNoteKey: string;
  estimatedExposure: number | null;
  estimatedReads: number | null;
  likes: number | null;
  collects: number | null;
  comments: number | null;
  shares: number | null;
  authorFollowers: number | null;
  authorNoteCount: number | null;
  authorTotalLikesCollects: number | null;
  readExposureRatioText: string | null;
  readFollowerRatioText: string | null;
}

export interface RawSnapshotInput {
  kind: string;
  objectKey: string;
  pageUrl: string;
  textContent: string;
  htmlContent: string | null;
}

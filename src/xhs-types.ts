import type { RunStatus } from './types.js';

export type XhsSearchSortKey = 'latest' | 'most_liked' | 'most_commented' | 'most_collected';
export type XhsSearchRunSource = 'manual_keyword' | 'huitun_run';
export type XhsNoteType = 'image' | 'video' | 'unknown';
export type XhsMediaSourceKind = 'image' | 'video';

export interface XhsMediaSource {
  kind: XhsMediaSourceKind;
  url: string;
  posterUrl: string | null;
  altText: string | null;
}

export interface XhsNoteCommentSource {
  contentText: string;
  authorName: string | null;
  likeText: string | null;
  rawText: string;
}

export interface XhsSearchRunInput {
  source: XhsSearchRunSource;
  sourceRunId: number | null;
  keyword: string;
  sorts: XhsSearchSortKey[];
  limitPerSort: number;
  withDetails: boolean;
}

export interface XhsSearchRunRecord {
  id: number;
  source: XhsSearchRunSource;
  sourceRunId: number | null;
  keyword: string;
  sorts: XhsSearchSortKey[];
  limitPerSort: number;
  withDetails: boolean;
  status: RunStatus;
  startedAt: string;
  finishedAt: string | null;
  errorStage: string | null;
  errorMessage: string | null;
}

export interface XhsNoteIdentity {
  feedId: string;
  xsecToken: string | null;
}

export interface XhsSearchNoteRow {
  keyword: string;
  sortKey: XhsSearchSortKey;
  sortLabel: string;
  rankIndex: number;
  feedId: string;
  xsecToken: string | null;
  searchResultUrl: string;
  exploreUrl: string | null;
  title: string;
  authorName: string | null;
  authorProfileUrl: string | null;
  coverUrl: string | null;
  publishedAtText: string | null;
  metricText: string | null;
  detailText: string | null;
  detailTags: string[];
  detailCommentCountText: string | null;
  detailLikeText: string | null;
  detailCollectText: string | null;
  detailShareText: string | null;
  noteType: XhsNoteType;
  coverAltText: string | null;
  rawDetailText: string | null;
  sourceTopicTexts: string[];
  sourceComments: XhsNoteCommentSource[];
  mediaSources: XhsMediaSource[];
  analysisSourceText: string | null;
  rawCardText: string;
}

export interface XhsSearchCardPayload {
  searchResultUrl: string | null;
  authorProfileUrl: string | null;
  coverUrl: string | null;
  noteType?: XhsNoteType;
  coverAltText?: string | null;
  sourceTopicTexts?: string[];
  rawText: string;
}

export interface XhsNoteDetail {
  feedId: string;
  xsecToken: string | null;
  exploreUrl: string;
  detailText: string | null;
  tags: string[];
  commentCountText: string | null;
  likeText: string | null;
  collectText: string | null;
  shareText: string | null;
  noteType: XhsNoteType;
  rawDetailText: string | null;
  sourceTopicTexts: string[];
  sourceComments: XhsNoteCommentSource[];
  mediaSources: XhsMediaSource[];
  analysisSourceText: string | null;
}

export interface XhsNoteDetailContext {
  title: string;
  noteType?: XhsNoteType;
  coverAltText?: string | null;
  coverUrl?: string | null;
  sourceTopicTexts?: string[];
}

export interface XhsRawSnapshotInput {
  kind: string;
  objectKey: string;
  pageUrl: string;
  textContent: string;
  htmlContent: string | null;
}

export interface XhsRateLimitContext {
  keyword: string;
  sortKey: XhsSearchSortKey;
  feedId: string;
  message: string;
}

export interface XhsDetailSafetyState {
  detailBudgetUsed: number;
  rateLimited: boolean;
  rateLimitContext?: XhsRateLimitContext;
}

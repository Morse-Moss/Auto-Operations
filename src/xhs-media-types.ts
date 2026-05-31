export type XhsArchivedMediaKind = 'image' | 'video';

export type XhsArchiveStatus = 'success' | 'no_media_saved' | 'partial_failed';

export type XhsVideoArchiveStatus = 'complete' | 'complete_short_mp4_structure_verified' | 'incomplete' | 'no_video_url' | 'failed';

export interface XhsArchivedMediaFile {
  kind: XhsArchivedMediaKind;
  url: string;
  contentType: string;
  status: number;
  bytes: number;
  file: string;
}

export interface XhsMediaArchiveManifestEntry {
  rankIndex: number;
  feedId: string;
  title: string;
  noteType: string;
  keyword: string;
  sortLabel: string;
  searchResultUrl: string;
  exploreUrl: string | null;
  tags: string[];
  topics: string[];
  sourceMediaUrls: string[];
  status: XhsArchiveStatus;
  imageCount: number;
  videoCount: number;
  imageFiles: string[];
  videoFiles: string[];
  saved: XhsArchivedMediaFile[];
  errors: string[];
  completeVideoStatus?: XhsVideoArchiveStatus;
  completeVideoFile?: string | null;
  completeVideoBytes?: number;
  completeVideoCoveredBytes?: number;
  completeVideoChunkCount?: number;
  completeVideoGaps?: Array<[number, number]>;
}

export interface XhsMediaArchiveSummary {
  runId: number;
  rows: number;
  success: number;
  noMediaSaved: number;
  imageFiles: number;
  videoFiles: number;
  completeVideos: number;
  incompleteVideos: number;
  root: string;
  csv: string;
}

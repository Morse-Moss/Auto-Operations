import type { CollectionQualityReport } from './collection-quality.js';
import type { XhsAnalysisSourceOptions, XhsAnalysisSourceResult } from './xhs-analysis-source-types.js';
import type { XhsMediaArchiveOptions, XhsMediaArchiveResult } from './xhs-media-archive.js';
import type { XhsPipelineCheckOptions, XhsPipelineCheckResult } from './xhs-pipeline-check-types.js';
import type { XhsFeishuSyncOptions, XhsFeishuSyncResult } from './feishu/xhs-sync.js';
import type { CollectorOptions, RunStatus } from './types.js';
import type { XhsSearchSortKey } from './xhs-types.js';

export type XhsPreanalysisRunStatus = 'success' | 'partial_success' | 'failed';
export type XhsPreanalysisStageStatus = XhsPreanalysisRunStatus | 'skipped';

export interface XhsPreanalysisRunOptions {
  orchestrationId?: string;
  keyword: string;
  dbPath: string;
  huitunCdpUrl: string;
  xhsCdpUrl: string;
  mediaCdpUrl: string;
  limitHotwords: number;
  limitNotes: number;
  days: 7 | 30 | 90 | 180;
  xhsLimitKeywords: number;
  xhsSorts: XhsSearchSortKey[];
  xhsLimitPerSort: number;
  withDetails: boolean;
  detailBudget: number;
  detailDelayMinMs: number;
  detailDelayMaxMs: number;
  stopOnRateLimit: boolean;
  resumeMissingDetails: boolean;
  mediaDelayMinMs: number;
  mediaDelayMaxMs: number;
  feishuDryRun: boolean;
  outputDir?: string;
}

export interface XhsPreanalysisHuitunCollectionResult {
  runId?: number;
  status: RunStatus;
  hotWordCount: number;
  noteCount: number;
  detailCount: number;
  dbPath: string;
  qualityReport: CollectionQualityReport | Record<string, unknown>;
  errorMessage?: string;
  recoveryCommand?: string;
}

export interface XhsPreanalysisXhsSearchRunResult {
  runId: number;
  keyword: string;
  status: RunStatus;
  noteCount: number;
}

export interface XhsPreanalysisXhsSearchOptions {
  keyword?: string;
  fromHuitunRunId?: number;
  limitKeywords: number;
  sorts: XhsSearchSortKey[];
  limitPerSort: number;
  withDetails: boolean;
  detailDelayMinMs: number;
  detailDelayMaxMs: number;
  detailBudget: number;
  stopOnRateLimit: boolean;
  resumeMissingDetails: boolean;
  dbPath: string;
  cdpUrl: string;
}

export interface XhsPreanalysisXhsSearchCollectionStatus {
  stage: 'xhsSearchCollection';
  status: XhsPreanalysisStageStatus;
  startedAt: string;
  finishedAt: string;
  command: string;
  runId?: number;
  keyword?: string;
  noteCount?: number;
  result?: XhsPreanalysisXhsSearchRunResult;
  errorMessage?: string;
  recoveryCommand?: string;
}

export interface XhsPreanalysisXhsSearchResult {
  runs: XhsPreanalysisXhsSearchRunResult[];
  dbPath: string;
  detailBudgetUsed: number;
  rateLimited: boolean;
  rateLimitContext?: unknown;
}

export interface XhsPreanalysisMediaArchiveStatus {
  runId: number;
  status: XhsPreanalysisRunStatus;
  manifestPath: string;
  result?: XhsMediaArchiveResult;
  errorMessage?: string;
  recoveryCommand?: string;
}

export interface XhsPreanalysisFeishuSyncStatus {
  runId: number;
  status: XhsPreanalysisRunStatus;
  reportPath: string;
  result?: XhsFeishuSyncResult;
  errorMessage?: string;
  recoveryCommand?: string;
}

export interface XhsPreanalysisPipelineCheckStatus {
  runId: number;
  status: XhsPreanalysisRunStatus;
  result?: XhsPipelineCheckResult;
  errorMessage?: string;
  recoveryCommand?: string;
}

export interface XhsPreanalysisAnalysisSourceStatus {
  runId: number;
  status: XhsPreanalysisStageStatus;
  keyword?: string;
  noteCount?: number;
  mediaArchive?: XhsMediaArchiveResult;
  feishuSync?: XhsFeishuSyncResult;
  pipelineCheck?: XhsPipelineCheckResult;
  analysisSource?: XhsAnalysisSourceResult;
  errorMessage?: string;
  recoveryCommand?: string;
}

export interface XhsPreanalysisRunResult {
  orchestrationId: string;
  status: XhsPreanalysisRunStatus;
  startedAt: string;
  finishedAt: string;
  options: XhsPreanalysisRunOptions;
  commands: string[];
  huitunCollection: XhsPreanalysisHuitunCollectionResult;
  xhsSearchCollections: XhsPreanalysisXhsSearchCollectionStatus[];
  mediaArchives: XhsPreanalysisMediaArchiveStatus[];
  feishuSyncs: XhsPreanalysisFeishuSyncStatus[];
  pipelineChecks: XhsPreanalysisPipelineCheckStatus[];
  analysisSources: XhsPreanalysisAnalysisSourceStatus[];
  paths: {
    outputDir: string;
    statusJson: string;
    statusMarkdown: string;
  };
}

export interface XhsPreanalysisRunDependencies {
  now: () => string;
  collectHuitun: (options: CollectorOptions) => Promise<XhsPreanalysisHuitunCollectionResult>;
  collectXhsSearch: (options: XhsPreanalysisXhsSearchOptions) => Promise<XhsPreanalysisXhsSearchResult>;
  listCreatedXhsRunsForHuitunRun?: (params: { sourceRunId: number; dbPath: string }) => XhsPreanalysisXhsSearchRunResult[];
  archiveXhsRunMedia: (options: XhsMediaArchiveOptions) => Promise<XhsMediaArchiveResult>;
  syncXhsRunToFeishu: (options: XhsFeishuSyncOptions) => Promise<XhsFeishuSyncResult>;
  checkXhsPipeline: (options: XhsPipelineCheckOptions) => XhsPipelineCheckResult;
  buildXhsAnalysisSource: (options: XhsAnalysisSourceOptions) => XhsAnalysisSourceResult;
}

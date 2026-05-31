export type XhsPipelineCheckStatus = 'complete' | 'partial' | 'failed';

export interface XhsPipelineIssue {
  code: string;
  message: string;
}

export interface XhsPipelineCheckAgentReadiness {
  ready: boolean;
  inputContractVersion: 'xhs-analysis-source/v1';
  recommendedInput: {
    dbPath: string;
    runId: number;
    manifestPath: string;
    syncReportPath: string;
  };
}

export interface XhsPipelineCheckResult {
  runId: number;
  status: XhsPipelineCheckStatus;
  blockingIssues: XhsPipelineIssue[];
  warnings: XhsPipelineIssue[];
  paths: {
    dbPath: string;
    manifestPath: string;
    syncReportPath: string;
    outputDir: string;
    jsonPath: string;
    markdownPath: string;
  };
  counts: {
    notes: number;
    details: number;
    tags: number;
    mediaSources: number;
    manifestEntries: number;
    manifestMatchedFeeds: number;
    feishuSyncedRecords: number;
  };
  agent: XhsPipelineCheckAgentReadiness;
}

export interface XhsPipelineCheckOptions {
  runId: number;
  dbPath: string;
  manifestPath?: string;
  syncReportPath?: string;
  outputDir?: string;
}

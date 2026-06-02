export const XhsAnalysisSourceContractVersion = 'xhs-analysis-source/v1' as const;

export type XhsAnalysisSourceContractVersion = typeof XhsAnalysisSourceContractVersion;

export interface XhsAnalysisSourceOptions {
  runId: number;
  dbPath: string;
  manifestPath?: string;
  syncReportPath?: string;
  pipelineCheckPath?: string;
  outputDir?: string;
}

export interface XhsAnalysisSourceResult {
  contractVersion: XhsAnalysisSourceContractVersion;
  runId: number;
  files: {
    sourceJson: string;
    notesJsonl: string;
  };
  counts: {
    notes: number;
  };
}

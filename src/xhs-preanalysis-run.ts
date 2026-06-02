import { mkdirSync, writeFileSync } from 'node:fs';

import type { XhsPipelineCheckResult } from './xhs-pipeline-check-types.js';
import type {
  XhsPreanalysisAnalysisSourceStatus,
  XhsPreanalysisFeishuSyncStatus,
  XhsPreanalysisMediaArchiveStatus,
  XhsPreanalysisPipelineCheckStatus,
  XhsPreanalysisRunDependencies,
  XhsPreanalysisRunOptions,
  XhsPreanalysisXhsSearchRunResult,
  XhsPreanalysisRunResult,
  XhsPreanalysisRunStatus,
  XhsPreanalysisStageStatus,
} from './xhs-preanalysis-run-types.js';

function defaultOutputDir(orchestrationId: string): string {
  return `data/xhs-preanalysis-run/${orchestrationId}`;
}

function defaultMediaManifestPath(runId: number | string): string {
  return `data/xhs-media/run-${runId}/manifest.json`;
}

function defaultSyncReportPath(runId: number | string): string {
  return `data/feishu-sync/run-${runId}/sync-report.json`;
}

function defaultPipelineCheckOutputDir(runId: number | string): string {
  return `data/xhs-pipeline-check/run-${runId}`;
}

function defaultPipelineCheckPath(runId: number | string): string {
  return `${defaultPipelineCheckOutputDir(runId)}/check.json`;
}

function defaultAnalysisSourceDir(runId: number | string): string {
  return `data/xhs-analysis-source/run-${runId}`;
}

function shellQuote(value: string): string {
  return `'${value.replaceAll("'", "'\\''")}'`;
}

function commandArg(value: string): string {
  return /^[A-Za-z0-9_./:@%+=,<>-]+$/.test(value) ? value : shellQuote(value);
}

function buildCommand(parts: Array<string | undefined>): string {
  return parts.filter((part): part is string => part !== undefined).join(' ');
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function buildCommandSet(options: XhsPreanalysisRunOptions, xhsRunId: number | '<xhsRunId>' = '<xhsRunId>'): Record<string, string> {
  const manifestPath = defaultMediaManifestPath(xhsRunId);
  const syncReportPath = defaultSyncReportPath(xhsRunId);
  const pipelineCheckPath = defaultPipelineCheckPath(xhsRunId);

  return {
    huitun: buildCommand([
      'npm run collect --',
      `--keyword ${commandArg(options.keyword)}`,
      `--limit-hotwords ${options.limitHotwords}`,
      `--limit-notes ${options.limitNotes}`,
      `--days ${options.days}`,
      `--db-path ${commandArg(options.dbPath)}`,
      `--cdp-url ${commandArg(options.huitunCdpUrl)}`,
    ]),
    xhsSearch: buildCommand([
      'npm run collect -- xhs-search',
      `--from-huitun-run-id <huitunRunId>`,
      `--limit-keywords ${options.xhsLimitKeywords}`,
      `--sorts ${commandArg(options.xhsSorts.join(','))}`,
      `--limit-per-sort ${options.xhsLimitPerSort}`,
      options.withDetails ? '--with-details' : undefined,
      `--detail-budget ${options.detailBudget}`,
      `--detail-delay-min-ms ${options.detailDelayMinMs}`,
      `--detail-delay-max-ms ${options.detailDelayMaxMs}`,
      options.stopOnRateLimit ? undefined : '--no-stop-on-rate-limit',
      options.resumeMissingDetails ? undefined : '--no-resume-missing-details',
      `--db-path ${commandArg(options.dbPath)}`,
      `--cdp-url ${commandArg(options.xhsCdpUrl)}`,
    ]),
    mediaArchive: buildCommand([
      'npm run collect -- xhs-media-archive',
      `--run-id ${xhsRunId}`,
      `--db-path ${commandArg(options.dbPath)}`,
      `--cdp-url ${commandArg(options.mediaCdpUrl)}`,
      `--delay-min-ms ${options.mediaDelayMinMs}`,
      `--delay-max-ms ${options.mediaDelayMaxMs}`,
    ]),
    feishuSync: buildCommand([
      'npm run collect -- xhs-sync-feishu',
      `--run-id ${xhsRunId}`,
      `--db-path ${commandArg(options.dbPath)}`,
      `--manifest ${commandArg(manifestPath)}`,
      options.feishuDryRun ? '--dry-run' : undefined,
    ]),
    pipelineCheck: buildCommand([
      'npm run collect -- xhs-pipeline-check',
      `--run-id ${xhsRunId}`,
      `--db-path ${commandArg(options.dbPath)}`,
      `--manifest ${commandArg(manifestPath)}`,
      `--sync-report ${commandArg(syncReportPath)}`,
    ]),
    analysisSource: buildCommand([
      'npm run collect -- xhs-analysis-source',
      `--run-id ${xhsRunId}`,
      `--db-path ${commandArg(options.dbPath)}`,
      `--manifest ${commandArg(manifestPath)}`,
      `--sync-report ${commandArg(syncReportPath)}`,
      `--pipeline-check ${commandArg(pipelineCheckPath)}`,
    ]),
  };
}

function buildCommands(options: XhsPreanalysisRunOptions): string[] {
  const commands = buildCommandSet(options);

  return [
    commands.huitun,
    commands.xhsSearch,
    commands.mediaArchive,
    commands.feishuSync,
    commands.pipelineCheck,
    commands.analysisSource,
  ];
}

function terminalStageStatus(status: string): XhsPreanalysisStageStatus {
  return status === 'success' || status === 'partial_success' || status === 'failed' || status === 'skipped' ? status : 'failed';
}

function aggregateStatus(
  huitunStatus: string,
  xhsSearchCollections: XhsPreanalysisRunResult['xhsSearchCollections'],
  mediaArchives: XhsPreanalysisMediaArchiveStatus[],
  feishuSyncs: XhsPreanalysisFeishuSyncStatus[],
  pipelineChecks: XhsPreanalysisPipelineCheckStatus[],
  analysisSources: XhsPreanalysisAnalysisSourceStatus[],
): XhsPreanalysisRunStatus {
  if (huitunStatus === 'failed') {
    return 'failed';
  }

  const hasSuccessfulAnalysisSource = analysisSources.some((source) => source.status === 'success');
  if (!hasSuccessfulAnalysisSource) {
    return 'failed';
  }

  const terminalStatuses: XhsPreanalysisStageStatus[] = [
    ...xhsSearchCollections.map((stage) => stage.status),
    ...mediaArchives.map((stage) => stage.status),
    ...feishuSyncs.map((stage) => stage.status),
    ...pipelineChecks.map((stage) => stage.status),
    ...analysisSources.map((stage) => stage.status),
  ];
  return terminalStatuses.every((status) => status === 'success') ? 'success' : 'partial_success';
}

function appendRecovery(line: string, recoveryCommand?: string): string {
  return recoveryCommand === undefined ? line : `${line}\n  - Recovery: ${recoveryCommand}`;
}

function renderAnalysisSourceLine(source: XhsPreanalysisAnalysisSourceStatus): string {
  const sourceJson = source.analysisSource?.files.sourceJson ?? '(source not built)';
  const error = source.errorMessage === undefined ? '' : ` — ${source.errorMessage}`;
  return appendRecovery(`- Run #${source.runId}: ${source.status} — ${sourceJson}${error}`, source.recoveryCommand);
}

function renderFailedStageLine(stage: { stage?: string; runId?: number; status: string; errorMessage?: string; recoveryCommand?: string }): string {
  const runText = stage.runId === undefined ? (stage.stage ?? 'Huitun') : `Run #${stage.runId}`;
  const error = stage.errorMessage === undefined ? '' : ` — ${stage.errorMessage}`;
  return appendRecovery(`- ${runText}: ${stage.status}${error}`, stage.recoveryCommand);
}

function renderMarkdown(result: XhsPreanalysisRunResult): string {
  const ready = result.analysisSources.filter((source) => source.status === 'success');
  const partial = result.analysisSources.filter((source) => source.status === 'partial_success');
  const failed = result.analysisSources.filter((source) => source.status === 'failed' || source.status === 'skipped');
  const failedStages: Array<{ stage?: string; runId?: number; status: string; errorMessage?: string; recoveryCommand?: string }> = [];
  if (result.huitunCollection.status === 'failed') {
    failedStages.push(result.huitunCollection);
  }
  failedStages.push(...result.xhsSearchCollections.filter((stage) => stage.status === 'failed' || stage.status === 'skipped'));
  failedStages.push(...result.mediaArchives.filter((stage) => stage.status === 'failed' || stage.status === 'partial_success'));
  failedStages.push(...result.feishuSyncs.filter((stage) => stage.status === 'failed' || stage.status === 'partial_success'));
  failedStages.push(...result.pipelineChecks.filter((stage) => stage.status === 'failed' || stage.status === 'partial_success'));

  return [
    '# XHS pre-analysis run status',
    '',
    `Orchestration ID: ${result.orchestrationId}`,
    `Status: ${result.status}`,
    `Started at: ${result.startedAt}`,
    `Finished at: ${result.finishedAt}`,
    '',
    '## Analysis-ready runs',
    ready.length === 0 ? '- None' : ready.map(renderAnalysisSourceLine).join('\n'),
    '',
    '## Partial runs',
    partial.length === 0 ? '- None' : partial.map(renderAnalysisSourceLine).join('\n'),
    '',
    '## Failed or skipped runs',
    failed.length === 0 && failedStages.length === 0
      ? '- None'
      : [...failedStages.map(renderFailedStageLine), ...failed.map(renderAnalysisSourceLine)].join('\n'),
    '',
    '## Commands',
    ...result.commands.map((command) => `- ${command}`),
    '',
  ].join('\n');
}

function writeStatusArtifacts(result: XhsPreanalysisRunResult): void {
  mkdirSync(result.paths.outputDir, { recursive: true });
  writeFileSync(result.paths.statusJson, JSON.stringify(result, null, 2), 'utf8');
  writeFileSync(result.paths.statusMarkdown, renderMarkdown(result), 'utf8');
}

export async function runXhsPreanalysisRun(
  options: XhsPreanalysisRunOptions,
  dependencies: XhsPreanalysisRunDependencies,
): Promise<XhsPreanalysisRunResult> {
  const orchestrationId = options.orchestrationId ?? `preanalysis-${Date.now()}`;
  const outputDir = options.outputDir ?? defaultOutputDir(orchestrationId);
  const paths = {
    outputDir,
    statusJson: `${outputDir}/status.json`,
    statusMarkdown: `${outputDir}/status.md`,
  };
  const startedAt = dependencies.now();
  const commands = buildCommands(options);
  const commandSet = buildCommandSet(options);
  let xhsSearchCollections: XhsPreanalysisRunResult['xhsSearchCollections'] = [];
  let mediaArchives: XhsPreanalysisMediaArchiveStatus[] = [];
  let feishuSyncs: XhsPreanalysisFeishuSyncStatus[] = [];
  let pipelineChecks: XhsPreanalysisPipelineCheckStatus[] = [];
  let analysisSources: XhsPreanalysisAnalysisSourceStatus[] = [];

  const huitunCollection = await dependencies
    .collectHuitun({
      keyword: options.keyword,
      limitHotwords: options.limitHotwords,
      limitNotes: options.limitNotes,
      days: options.days,
      dbPath: options.dbPath,
      cdpUrl: options.huitunCdpUrl,
      headless: false,
    })
    .catch((error): XhsPreanalysisRunResult['huitunCollection'] => ({
      status: 'failed',
      hotWordCount: 0,
      noteCount: 0,
      detailCount: 0,
      dbPath: options.dbPath,
      qualityReport: {},
      errorMessage: errorMessage(error),
      recoveryCommand: commandSet.huitun,
    }));

  if (huitunCollection.status !== 'failed') {
    const xhsSearchStartedAt = dependencies.now();
    let xhsRuns: XhsPreanalysisXhsSearchRunResult[] = [];
    const appendRecoveredXhsRuns = (runs: XhsPreanalysisXhsSearchRunResult[], finishedAt: string): void => {
      const representedRunIds = new Set(xhsSearchCollections.map((stage) => stage.runId).filter((runId): runId is number => runId !== undefined));
      for (const run of runs) {
        if (representedRunIds.has(run.runId)) {
          continue;
        }
        xhsSearchCollections.push({
          stage: 'xhsSearchCollection',
          status: terminalStageStatus(run.status),
          startedAt: xhsSearchStartedAt,
          finishedAt,
          command: commandSet.xhsSearch,
          recoveryCommand: commandSet.xhsSearch,
          runId: run.runId,
          keyword: run.keyword,
          noteCount: run.noteCount,
          result: run,
        });
        representedRunIds.add(run.runId);
        xhsRuns.push(run);
      }
    };
    try {
      const xhsSearch = await dependencies.collectXhsSearch({
        fromHuitunRunId: huitunCollection.runId ?? 0,
        limitKeywords: options.xhsLimitKeywords,
        sorts: options.xhsSorts,
        limitPerSort: options.xhsLimitPerSort,
        withDetails: options.withDetails,
        detailDelayMinMs: options.detailDelayMinMs,
        detailDelayMaxMs: options.detailDelayMaxMs,
        detailBudget: options.detailBudget,
        stopOnRateLimit: options.stopOnRateLimit,
        resumeMissingDetails: options.resumeMissingDetails,
        dbPath: options.dbPath,
        cdpUrl: options.xhsCdpUrl,
      });
      const finishedAt = dependencies.now();
      xhsSearchCollections = xhsSearch.runs.map((run) => ({
        stage: 'xhsSearchCollection',
        status: terminalStageStatus(run.status),
        startedAt: xhsSearchStartedAt,
        finishedAt,
        command: commandSet.xhsSearch,
        runId: run.runId,
        keyword: run.keyword,
        noteCount: run.noteCount,
        result: run,
      }));
      if (xhsSearchCollections.length === 0) {
        xhsSearchCollections = [
          {
            stage: 'xhsSearchCollection',
            status: 'failed',
            startedAt: xhsSearchStartedAt,
            finishedAt,
            command: commandSet.xhsSearch,
            errorMessage: 'No XHS search runs were returned.',
            recoveryCommand: commandSet.xhsSearch,
          },
        ];
      }
      xhsRuns = xhsSearch.runs;
    } catch (error) {
      const finishedAt = dependencies.now();
      xhsSearchCollections = [
        {
          stage: 'xhsSearchCollection',
          status: 'failed',
          startedAt: xhsSearchStartedAt,
          finishedAt,
          command: commandSet.xhsSearch,
          errorMessage: errorMessage(error),
          recoveryCommand: commandSet.xhsSearch,
        },
      ];
      if (huitunCollection.runId !== undefined && dependencies.listCreatedXhsRunsForHuitunRun !== undefined) {
        appendRecoveredXhsRuns(
          dependencies.listCreatedXhsRunsForHuitunRun({ sourceRunId: huitunCollection.runId, dbPath: options.dbPath }),
          finishedAt,
        );
      }
    }

    analysisSources = [];
    for (const run of xhsRuns) {
      let manifestPath = defaultMediaManifestPath(run.runId);
      let syncReportPath = defaultSyncReportPath(run.runId);
      const pipelineCheckPath = defaultPipelineCheckPath(run.runId);
      const runCommands = buildCommandSet(options, run.runId);
      let mediaArchive;
      try {
        mediaArchive = await dependencies.archiveXhsRunMedia({
          runId: run.runId,
          dbPath: options.dbPath,
          cdpUrl: options.mediaCdpUrl,
          force: false,
          resumeMissingMedia: true,
          delayMinMs: options.mediaDelayMinMs,
          delayMaxMs: options.mediaDelayMaxMs,
        });
        manifestPath = mediaArchive.manifest ?? manifestPath;
        const mediaStatus = mediaArchive.safetyStopped || mediaArchive.incompleteVideos > 0 || mediaArchive.noMediaSaved > 0 ? 'partial_success' : 'success';
        mediaArchives.push({ runId: run.runId, status: mediaStatus, manifestPath, result: mediaArchive });
      } catch (error) {
        mediaArchives.push({
          runId: run.runId,
          status: 'failed',
          manifestPath,
          errorMessage: errorMessage(error),
          recoveryCommand: runCommands.mediaArchive,
        });
      }

      let feishuSync;
      try {
        feishuSync = await dependencies.syncXhsRunToFeishu({
          runId: run.runId,
          dbPath: options.dbPath,
          manifestPath,
          dryRun: options.feishuDryRun,
        });
        syncReportPath = feishuSync.reportPath ?? syncReportPath;
        feishuSyncs.push({ runId: run.runId, status: feishuSync.failed > 0 ? 'partial_success' : 'success', reportPath: syncReportPath, result: feishuSync });
      } catch (error) {
        feishuSyncs.push({
          runId: run.runId,
          status: 'failed',
          reportPath: syncReportPath,
          errorMessage: errorMessage(error),
          recoveryCommand: runCommands.feishuSync,
        });
      }

      let pipelineCheck: XhsPipelineCheckResult | undefined;
      try {
        pipelineCheck = dependencies.checkXhsPipeline({
          runId: run.runId,
          dbPath: options.dbPath,
          manifestPath,
          syncReportPath,
          outputDir: defaultPipelineCheckOutputDir(run.runId),
        });
        pipelineChecks.push({
          runId: run.runId,
          status: pipelineCheck.status === 'complete' ? 'success' : pipelineCheck.status === 'partial' ? 'partial_success' : 'failed',
          result: pipelineCheck,
        });
      } catch (error) {
        pipelineChecks.push({
          runId: run.runId,
          status: 'failed',
          errorMessage: errorMessage(error),
          recoveryCommand: runCommands.pipelineCheck,
        });
      }

      if (pipelineCheck !== undefined && pipelineCheck.counts.notes === 0) {
        analysisSources.push({
          runId: run.runId,
          keyword: run.keyword,
          noteCount: run.noteCount,
          status: 'skipped',
          pipelineCheck,
          errorMessage: 'Skipped analysis-source because pipeline check reported zero notes.',
          recoveryCommand: runCommands.xhsSearch,
        });
        continue;
      }

      try {
        const analysisSource = dependencies.buildXhsAnalysisSource({
          runId: run.runId,
          dbPath: options.dbPath,
          manifestPath: pipelineCheck?.paths.manifestPath ?? manifestPath,
          syncReportPath: pipelineCheck?.paths.syncReportPath ?? syncReportPath,
          pipelineCheckPath,
          outputDir: defaultAnalysisSourceDir(run.runId),
        });
        const sourceStatus = 'success';
        analysisSources.push({
          runId: run.runId,
          keyword: run.keyword,
          noteCount: run.noteCount,
          status: sourceStatus,
          mediaArchive,
          feishuSync,
          pipelineCheck,
          analysisSource,
        });
      } catch (error) {
        analysisSources.push({
          runId: run.runId,
          keyword: run.keyword,
          noteCount: run.noteCount,
          status: 'failed',
          mediaArchive,
          feishuSync,
          pipelineCheck,
          errorMessage: errorMessage(error),
          recoveryCommand: runCommands.analysisSource,
        });
      }
    }
  }

  const result: XhsPreanalysisRunResult = {
    orchestrationId,
    status: aggregateStatus(huitunCollection.status, xhsSearchCollections, mediaArchives, feishuSyncs, pipelineChecks, analysisSources),
    startedAt,
    finishedAt: dependencies.now(),
    options: { ...options, orchestrationId, outputDir },
    commands,
    huitunCollection,
    xhsSearchCollections,
    mediaArchives,
    feishuSyncs,
    pipelineChecks,
    analysisSources,
    paths,
  };

  writeStatusArtifacts(result);
  return result;
}

import { resolve } from 'node:path';
import type { DatabaseSync } from 'node:sqlite';
import { pathToFileURL } from 'node:url';

import { Command, InvalidArgumentError } from 'commander';

import { collectHotWordRows } from './browser/hotword-search.js';
import { collectHotWordSnapshot, collectTopLikedNoteRows, openHotWordDetail } from './browser/hotword-detail.js';
import { parseXhsSortKeys } from './browser/xhs-search.js';
import {
  exportRunNotesToCsv,
  generateReportText,
  type ExportCommandOptions,
  type ReportCommandOptions,
} from './reporting/commands.js';
import {
  capturePageSnapshot,
  createHuitunSession,
  HUITUN_LOGIN_REQUIRED_MESSAGE,
  type HuitunSession,
} from './browser/huitun-session.js';
import { collectNoteDetail } from './browser/note-detail.js';
import {
  buildCollectionQualityReport,
  effectiveNoteLimit,
  type CollectionQualityReport,
  type HotWordCollectionQuality,
} from './collection-quality.js';
import { selectDistinctNotesForTarget } from './collection-target.js';
import type { CollectorRepository } from './db/repositories.js';
import type { CollectorOptions, RunStatus } from './types.js';
import type { XhsSearchSortKey } from './xhs-types.js';

const SUPPORTED_DAYS = [7, 30, 90, 180] as const;

type SupportedDays = (typeof SUPPORTED_DAYS)[number];

interface CliOptions {
  keyword?: string;
  limitHotwords: number;
  limitNotes: number;
  targetNotes?: number;
  days: SupportedDays;
  dbPath: string;
  cdpUrl: string;
  headless: boolean;
}

interface ReportCliOptions {
  runId?: number;
  dbPath: string;
}

interface ExportCliOptions extends ReportCliOptions {
  output: string;
}

interface XhsSearchCliOptions {
  keyword?: string;
  fromHuitunRunId?: number;
  limitKeywords: number;
  sorts?: string;
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

interface XhsMediaArchiveCliOptions {
  runId?: number;
  dbPath: string;
  cdpUrl: string;
  outputDir?: string;
  force: boolean;
  delayMinMs: number;
  delayMaxMs: number;
}

interface XhsFeishuSyncCliOptions {
  runId?: number;
  dbPath: string;
  manifest?: string;
  dryRun: boolean;
}

export interface XhsSearchCommandOptions {
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

export interface XhsMediaArchiveCommandOptions {
  runId: number;
  dbPath: string;
  cdpUrl: string;
  outputDir?: string;
  force: boolean;
  delayMinMs: number;
  delayMaxMs: number;
}

export interface XhsFeishuSyncCommandOptions {
  runId: number;
  dbPath: string;
  manifestPath?: string;
  dryRun: boolean;
}

function parsePositiveInteger(value: string, name: string): number {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed <= 0) {
    throw new InvalidArgumentError(`${name} 必须是正整数，收到：${value}`);
  }

  return parsed;
}

function parseNonNegativeInteger(value: string, name: string): number {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 0) {
    throw new InvalidArgumentError(`${name} 必须是非负整数，收到：${value}`);
  }

  return parsed;
}

function parseDays(value: string): SupportedDays {
  const parsed = Number(value);
  if (!SUPPORTED_DAYS.includes(parsed as SupportedDays)) {
    throw new InvalidArgumentError(`--days 只支持 7、30、90、180，收到：${value}`);
  }

  return parsed as SupportedDays;
}

function createCollectionProgram(): Command {
  return new Command()
    .name('xhs-huitun-collector')
    .description('Collect Huitun hot words and note metrics into local SQLite')
    .requiredOption('--keyword <keyword>', '灰豚热词搜索关键词')
    .option('--limit-hotwords <count>', '最多采集热词数量', (value) => parsePositiveInteger(value, '--limit-hotwords'), 10)
    .option('--limit-notes <count>', '每个热词最多采集笔记数量', (value) => parsePositiveInteger(value, '--limit-notes'), 20)
    .option('--target-notes <count>', '全局去重后的目标笔记数量，达到后停止继续采集热词', (value) => parsePositiveInteger(value, '--target-notes'))
    .option('--days <days>', '热词详情时间范围，只支持 7、30、90、180', parseDays, 7)
    .option('--db-path <path>', 'SQLite 数据库路径', 'data/xhs-ops.sqlite')
    .option('--cdp-url <url>', '已登录浏览器的 CDP 地址', 'http://127.0.0.1:9222')
    .option('--headless', '保留参数：本 CLI 连接既有浏览器，不启动 headless 浏览器', false);
}

function createProgram(): Command {
  return createCollectionProgram()
    .addCommand(new Command('report').description('Show a readable summary for a Huitun collection run'))
    .addCommand(new Command('export').description('Export de-duplicated Huitun hot note rows to CSV'))
    .addCommand(createXhsSearchSubcommand())
    .addCommand(createXhsMediaArchiveSubcommand())
    .addCommand(createXhsFeishuSyncSubcommand());
}

function argvWithoutSubcommand(argv: string[]): string[] {
  return [argv[0] ?? 'node', argv[1] ?? 'src/cli.ts', ...argv.slice(3)];
}

function createReportProgram(): Command {
  return new Command()
    .name('xhs-huitun-collector report')
    .description('Show a readable summary for a Huitun collection run')
    .option('--run-id <id>', '采集 run id；未传时选择最近已结束 run', (value) => parsePositiveInteger(value, '--run-id'))
    .option('--db-path <path>', 'SQLite 数据库路径', 'data/xhs-ops.sqlite');
}

function createExportProgram(): Command {
  return new Command()
    .name('xhs-huitun-collector export')
    .description('Export de-duplicated Huitun hot note rows to CSV')
    .option('--run-id <id>', '采集 run id；未传时选择最近已结束 run', (value) => parsePositiveInteger(value, '--run-id'))
    .option('--db-path <path>', 'SQLite 数据库路径', 'data/xhs-ops.sqlite')
    .requiredOption('--output <path>', 'CSV 输出路径');
}

function addXhsSearchOptions(program: Command): Command {
  return program
    .description('Parse options for secondary XHS search collection')
    .option('--keyword <keyword>', '手动输入的小红书搜索关键词')
    .option('--from-huitun-run-id <id>', '从灰豚采集 run 中读取关键词', (value) => parsePositiveInteger(value, '--from-huitun-run-id'))
    .option('--limit-keywords <count>', '最多使用灰豚 run 中的关键词数量', (value) => parsePositiveInteger(value, '--limit-keywords'), 10)
    .option('--sorts <list>', '逗号分隔的小红书搜索排序键')
    .option('--limit-per-sort <count>', '每个排序最多采集笔记数量', (value) => parsePositiveInteger(value, '--limit-per-sort'), 20)
    .option('--with-details', '采集小红书笔记详情', false)
    .option('--detail-delay-min-ms <ms>', '详情页之间的最小等待毫秒数', (value) => parseNonNegativeInteger(value, '--detail-delay-min-ms'), 20_000)
    .option('--detail-delay-max-ms <ms>', '详情页之间的最大等待毫秒数', (value) => parseNonNegativeInteger(value, '--detail-delay-max-ms'), 60_000)
    .option('--detail-budget <count>', '单次命令最多打开的详情页数量', (value) => parsePositiveInteger(value, '--detail-budget'), 30)
    .option('--no-stop-on-rate-limit', '遇到小红书访问频繁时不熔断')
    .option('--no-resume-missing-details', '不跳过已有详情的笔记')
    .option('--db-path <path>', 'SQLite 数据库路径', 'data/xhs-ops.sqlite')
    .option('--cdp-url <url>', '已登录浏览器的 CDP 地址', 'http://127.0.0.1:9222');
}

function createXhsSearchProgram(): Command {
  return addXhsSearchOptions(new Command().name('xhs-huitun-collector xhs-search'));
}

function createXhsSearchSubcommand(): Command {
  return addXhsSearchOptions(new Command('xhs-search'));
}

function createXhsMediaArchiveProgram(): Command {
  return new Command()
    .name('xhs-huitun-collector xhs-media-archive')
    .description('Archive local image/video media for an XHS search run')
    .requiredOption('--run-id <id>', '小红书搜索 run id', (value) => parsePositiveInteger(value, '--run-id'))
    .option('--db-path <path>', 'SQLite 数据库路径', 'data/xhs-ops.sqlite')
    .option('--cdp-url <url>', 'browser-service xhs-main CDP 地址', 'http://127.0.0.1:17330')
    .option('--output-dir <path>', '媒体归档输出目录；默认 data/xhs-media/run-<id>')
    .option('--force', '删除并重建该 run 的本地媒体归档目录', false)
    .option('--delay-min-ms <ms>', '详情页归档之间的最小等待毫秒数', (value) => parseNonNegativeInteger(value, '--delay-min-ms'), 8_000)
    .option('--delay-max-ms <ms>', '详情页归档之间的最大等待毫秒数', (value) => parseNonNegativeInteger(value, '--delay-max-ms'), 15_000);
}

function createXhsMediaArchiveSubcommand(): Command {
  const program = createXhsMediaArchiveProgram();
  program.name('xhs-media-archive');
  return program;
}

function createXhsFeishuSyncProgram(): Command {
  return new Command()
    .name('xhs-huitun-collector xhs-sync-feishu')
    .description('Sync an archived XHS search run to Feishu Bitable')
    .requiredOption('--run-id <id>', '小红书搜索 run id', (value) => parsePositiveInteger(value, '--run-id'))
    .option('--db-path <path>', 'SQLite 数据库路径', 'data/xhs-ops.sqlite')
    .option('--manifest <path>', '媒体归档 manifest 路径；默认 data/xhs-media/run-<id>/manifest.json')
    .option('--dry-run', '只验证同步 payload，不写入飞书', false);
}

function createXhsFeishuSyncSubcommand(): Command {
  const program = createXhsFeishuSyncProgram();
  program.name('xhs-sync-feishu');
  return program;
}

function parseOptions(argv = process.argv): CollectorOptions {
  const program = createCollectionProgram();
  program.exitOverride();
  program.parse(argv);
  const options = program.opts<CliOptions>();

  return {
    keyword: options.keyword ?? '',
    limitHotwords: options.limitHotwords,
    limitNotes: options.limitNotes,
    targetNotes: options.targetNotes,
    days: options.days,
    dbPath: options.dbPath,
    cdpUrl: options.cdpUrl,
    headless: options.headless,
  };
}

function parseReportOptions(argv = process.argv): ReportCommandOptions {
  const program = createReportProgram();
  program.exitOverride();
  program.parse(argvWithoutSubcommand(argv));
  const options = program.opts<ReportCliOptions>();

  return {
    runId: options.runId,
    dbPath: options.dbPath,
  };
}

function parseExportOptions(argv = process.argv): ExportCommandOptions {
  const program = createExportProgram();
  program.exitOverride();
  program.parse(argvWithoutSubcommand(argv));
  const options = program.opts<ExportCliOptions>();

  return {
    runId: options.runId,
    dbPath: options.dbPath,
    output: options.output,
  };
}

function parseXhsSearchOptions(argv = process.argv): XhsSearchCommandOptions {
  const program = createXhsSearchProgram();
  program.exitOverride();
  program.parse(argvWithoutSubcommand(argv));
  const options = program.opts<XhsSearchCliOptions>();
  const hasKeyword = options.keyword !== undefined;
  const hasHuitunRunId = options.fromHuitunRunId !== undefined;

  if (hasKeyword === hasHuitunRunId) {
    throw new Error('xhs-search requires exactly one of --keyword or --from-huitun-run-id');
  }

  if (options.detailDelayMaxMs < options.detailDelayMinMs) {
    throw new Error('--detail-delay-max-ms 必须大于等于 --detail-delay-min-ms');
  }

  return {
    keyword: options.keyword,
    fromHuitunRunId: options.fromHuitunRunId,
    limitKeywords: options.limitKeywords,
    sorts: parseXhsSortKeys(options.sorts),
    limitPerSort: options.limitPerSort,
    withDetails: options.withDetails,
    detailDelayMinMs: options.detailDelayMinMs,
    detailDelayMaxMs: options.detailDelayMaxMs,
    detailBudget: options.detailBudget,
    stopOnRateLimit: options.stopOnRateLimit,
    resumeMissingDetails: options.resumeMissingDetails,
    dbPath: options.dbPath,
    cdpUrl: options.cdpUrl,
  };
}

function parseXhsMediaArchiveOptions(argv = process.argv): XhsMediaArchiveCommandOptions {
  const program = createXhsMediaArchiveProgram();
  program.exitOverride();
  program.parse(argvWithoutSubcommand(argv));
  const options = program.opts<XhsMediaArchiveCliOptions>();

  if (options.runId === undefined) {
    throw new Error('xhs-media-archive requires --run-id');
  }
  if (options.delayMaxMs < options.delayMinMs) {
    throw new Error('--delay-max-ms 必须大于等于 --delay-min-ms');
  }

  return {
    runId: options.runId,
    dbPath: options.dbPath,
    cdpUrl: options.cdpUrl,
    outputDir: options.outputDir,
    force: options.force,
    delayMinMs: options.delayMinMs,
    delayMaxMs: options.delayMaxMs,
  };
}

function parseXhsFeishuSyncOptions(argv = process.argv): XhsFeishuSyncCommandOptions {
  const program = createXhsFeishuSyncProgram();
  program.exitOverride();
  program.parse(argvWithoutSubcommand(argv));
  const options = program.opts<XhsFeishuSyncCliOptions>();

  if (options.runId === undefined) {
    throw new Error('xhs-sync-feishu requires --run-id');
  }

  return {
    runId: options.runId,
    dbPath: options.dbPath,
    manifestPath: options.manifest,
    dryRun: options.dryRun,
  };
}

function isCommanderExitError(error: unknown): error is { code: string; exitCode: number } {
  return (
    typeof error === 'object' &&
    error !== null &&
    'code' in error &&
    'exitCode' in error &&
    typeof error.code === 'string' &&
    error.code.startsWith('commander.') &&
    typeof error.exitCode === 'number'
  );
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function formatRawSnapshotTextContent(pageText: string, diagnosticMessage?: string): string {
  return diagnosticMessage === undefined ? pageText : `${diagnosticMessage}\n\n${pageText}`;
}

async function insertRawSnapshotFromPage(
  repository: CollectorRepository,
  runId: number,
  session: HuitunSession,
  kind: string,
  objectKey: string,
  diagnosticMessage?: string,
): Promise<void> {
  const snapshot = await capturePageSnapshot(session.page);
  repository.insertRawSnapshot(runId, {
    kind,
    objectKey,
    pageUrl: snapshot.url,
    textContent: formatRawSnapshotTextContent(snapshot.text, diagnosticMessage),
    htmlContent: snapshot.html,
  });
}

async function collect(options: CollectorOptions): Promise<{
  runId: number;
  status: RunStatus;
  hotWordCount: number;
  noteCount: number;
  detailCount: number;
  dbPath: string;
  qualityReport: CollectionQualityReport;
}> {
  let db: DatabaseSync | undefined;
  let repository: CollectorRepository | undefined;
  let session: HuitunSession | undefined;
  let runId: number | undefined;
  let status: RunStatus = 'success';
  let hotWordCount = 0;
  let noteCount = 0;
  let detailCount = 0;
  const effectiveLimitNotes = effectiveNoteLimit(options.limitNotes);
  const targetNotes = options.targetNotes;
  const isGlobalTargetMode = targetNotes !== undefined;
  const collectedNoteIdentities = new Set<string>();
  const hotWordQualities: HotWordCollectionQuality[] = [];

  try {
    const [{ openDatabase }, { initializeSchema }, { CollectorRepository }] = await Promise.all([
      import('./db/client.js'),
      import('./db/schema.js'),
      import('./db/repositories.js'),
    ]);

    db = openDatabase(options.dbPath);
    initializeSchema(db);
    repository = new CollectorRepository(db);
    runId = repository.createRun({
      keyword: options.keyword,
      days: options.days,
      limitHotwords: options.limitHotwords,
      limitNotes: effectiveLimitNotes,
    });

    session = await createHuitunSession(options.cdpUrl);

    const hotWords = await collectHotWordRows(session.page, options.keyword, options.limitHotwords);
    hotWordCount = hotWords.length;
    repository.insertHotWords(runId, hotWords);

    for (const hotWord of hotWords) {
      if (isGlobalTargetMode && collectedNoteIdentities.size >= targetNotes) {
        break;
      }

      try {
        await openHotWordDetail(session.page, hotWord.word, options.days);
        const snapshot = await collectHotWordSnapshot(session.page, hotWord.word, options.days);
        repository.insertHotWordSnapshot(runId, snapshot);

        let notesResult;

        try {
          notesResult = await collectTopLikedNoteRows(session.page, hotWord.word, effectiveLimitNotes);
        } catch (error) {
          status = 'partial_success';
          const message = errorMessage(error);
          const kind = message.includes('点赞倒序') || message.includes('排序') ? 'note_list_sort_error' : 'note_list_collection_error';
          await insertRawSnapshotFromPage(repository, runId, session, kind, hotWord.word, message);
          hotWordQualities.push({
            word: hotWord.word,
            targetNotes: effectiveLimitNotes,
            exposedNotes: 0,
            collectedNotes: 0,
            duplicateNotes: 0,
            detailedNotes: 0,
            detailFailures: 0,
            likesSort: {
              status: 'violated',
              checkedRows: 0,
              missingLikesCount: 0,
              violationCount: 1,
            },
            notesWithLikes: 0,
            missingLikes: 0,
            warnings: [message],
          });
          continue;
        }

        const exposedNotes = notesResult.rows.length;
        const remainingTarget = targetNotes === undefined ? null : targetNotes - collectedNoteIdentities.size;
        const targetSelection =
          remainingTarget === null
            ? { selected: notesResult.rows, duplicateNotes: 0 }
            : selectDistinctNotesForTarget(notesResult.rows, collectedNoteIdentities, remainingTarget);
        const notes = targetSelection.selected;
        let hotWordDetailCount = 0;
        let hotWordDetailFailures = 0;
        noteCount += notes.length;

        for (const note of notes) {
          let detail = null;

          try {
            detail = await collectNoteDetail(session.page, note);
            if (detail !== null) {
              detailCount += 1;
              hotWordDetailCount += 1;
            }
          } catch (error) {
            status = 'partial_success';
            hotWordDetailFailures += 1;
            await insertRawSnapshotFromPage(
              repository,
              runId,
              session,
              'parse_note_detail_error',
              note.huitunNoteKey,
              errorMessage(error),
            );
          }

          repository.upsertNote(runId, options.keyword, note, detail);
        }

        const notesWithLikes = notes.filter((note) => note.likes !== null).length;
        const warnings: string[] = [];
        if (isGlobalTargetMode) {
          if (remainingTarget !== null && exposedNotes < remainingTarget) {
            warnings.push('当前热词页面暴露的热点笔记数低于本次剩余目标。');
          }
        } else if (notes.length < effectiveLimitNotes) {
          warnings.push('可采集热点笔记数低于目标数量。');
        }
        if (hotWordDetailFailures > 0) {
          warnings.push('部分笔记详情采集失败。');
        }

        hotWordQualities.push({
          word: hotWord.word,
          targetNotes: effectiveLimitNotes,
          exposedNotes,
          collectedNotes: notes.length,
          duplicateNotes: targetSelection.duplicateNotes,
          detailedNotes: hotWordDetailCount,
          detailFailures: hotWordDetailFailures,
          likesSort: notesResult.likesSort,
          notesWithLikes,
          missingLikes: notes.length - notesWithLikes,
          warnings,
        });
      } catch (error) {
        if (errorMessage(error) === HUITUN_LOGIN_REQUIRED_MESSAGE) {
          throw error;
        }

        status = 'partial_success';
        await insertRawSnapshotFromPage(repository, runId, session, 'hot_word_detail_error', hotWord.word, errorMessage(error));
      }
    }

    hotWordCount = repository.countHotWordsForRun(runId);
    noteCount = repository.countNotesForRun(runId);
    detailCount = repository.countDetailedNotesForRun(runId);

    const rawSnapshotsByKind = repository.countRawSnapshotsByKindForRun(runId);
    const qualityReport = buildCollectionQualityReport({
      runId,
      keyword: options.keyword,
      days: options.days,
      requestedLimitHotwords: options.limitHotwords,
      requestedLimitNotes: options.limitNotes,
      targetNotes: targetNotes,
      status,
      totals: {
        hotWords: hotWordCount,
        hotWordSnapshots: repository.countHotWordSnapshotsForRun(runId),
        notes: noteCount,
        detailedNotes: detailCount,
        rawSnapshots: repository.countRawSnapshotsForRun(runId),
      },
      rawSnapshotsByKind,
      hotWords: hotWordQualities,
    });

    repository.finishRun(runId, status);

    return {
      runId,
      status,
      hotWordCount,
      noteCount,
      detailCount,
      dbPath: options.dbPath,
      qualityReport,
    };
  } catch (error) {
    if (repository !== undefined && runId !== undefined) {
      repository.finishRun(runId, 'failed', 'collector', errorMessage(error));
    }
    throw error;
  } finally {
    await session?.close();
    db?.close();
  }
}

async function main(argv = process.argv): Promise<void> {
  const command = argv[2];

  if (command === 'report') {
    console.log(generateReportText(parseReportOptions(argv)));
    return;
  }

  if (command === 'export') {
    const result = exportRunNotesToCsv(parseExportOptions(argv));
    console.log(`Exported ${result.rowCount} notes from run #${result.runId} to ${result.output}`);
    return;
  }

  if (command === 'xhs-search') {
    const { collectXhsSearch } = await import('./xhs-search-collector.js');
    const result = await collectXhsSearch(parseXhsSearchOptions(argv));
    console.log(JSON.stringify(result));
    return;
  }

  if (command === 'xhs-media-archive') {
    const { archiveXhsRunMedia } = await import('./xhs-media-archive.js');
    const result = await archiveXhsRunMedia(parseXhsMediaArchiveOptions(argv));
    console.log(JSON.stringify(result));
    return;
  }

  if (command === 'xhs-sync-feishu') {
    const { syncXhsRunToFeishu } = await import('./feishu/xhs-sync.js');
    const result = await syncXhsRunToFeishu(parseXhsFeishuSyncOptions(argv));
    console.log(JSON.stringify(result));
    return;
  }

  if (argv.includes('--help') || argv.includes('-h')) {
    const program = createProgram();
    program.exitOverride();
    program.parse(argv);
    return;
  }

  const options = parseOptions(argv);
  const result = await collect(options);
  console.log(JSON.stringify(result));
}

if (import.meta.url === pathToFileURL(resolve(process.argv[1] ?? '')).href) {
  try {
    await main();
  } catch (error) {
    if (isCommanderExitError(error)) {
      process.exitCode = error.exitCode;
    } else {
      console.error(errorMessage(error));
      process.exitCode = 1;
    }
  }
}

export { collect, createProgram, formatRawSnapshotTextContent, parseExportOptions, parseOptions, parseReportOptions, parseXhsFeishuSyncOptions, parseXhsMediaArchiveOptions, parseXhsSearchOptions };

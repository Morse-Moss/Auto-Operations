import { existsSync, statSync, writeFileSync } from 'node:fs';
import { dirname } from 'node:path';
import { DatabaseSync } from 'node:sqlite';

import { CollectorRepository } from '../db/repositories.js';
import { initializeSchema } from '../db/schema.js';
import { serializeNoteExportRows } from './csv.js';
import { formatRunReport } from './report.js';

export interface ReportCommandOptions {
  dbPath: string;
  runId?: number;
}

export interface ExportCommandOptions extends ReportCommandOptions {
  output: string;
}

export interface ExportCommandResult {
  runId: number;
  output: string;
  rowCount: number;
}

function openExistingDatabase(dbPath: string): DatabaseSync {
  if (dbPath !== ':memory:' && !existsSync(dbPath)) {
    throw new Error(`SQLite database not found: ${dbPath}. 先运行采集或检查 --db-path。`);
  }

  const db = new DatabaseSync(dbPath);
  db.exec('pragma foreign_keys = ON');
  initializeSchema(db);
  return db;
}

function resolveRunId(repository: CollectorRepository, requestedRunId: number | undefined): number {
  if (requestedRunId !== undefined) {
    const run = repository.findRunById(requestedRunId);
    if (run === null) {
      throw new Error(`Collection run not found: ${requestedRunId}`);
    }

    return run.id;
  }

  const latestRun = repository.findLatestFinishedRun();
  if (latestRun === null) {
    throw new Error('No finished collection run found. Run collection first or pass --run-id for a specific run.');
  }

  return latestRun.id;
}

export function generateReportText(options: ReportCommandOptions): string {
  const db = openExistingDatabase(options.dbPath);
  try {
    const repository = new CollectorRepository(db);
    const runId = resolveRunId(repository, options.runId);
    return formatRunReport(repository.getRunReportData(runId));
  } finally {
    db.close();
  }
}

export function exportRunNotesToCsv(options: ExportCommandOptions): ExportCommandResult {
  const outputDirectory = dirname(options.output);
  if (!existsSync(outputDirectory) || !statSync(outputDirectory).isDirectory()) {
    throw new Error(`Output directory does not exist: ${outputDirectory}`);
  }

  const db = openExistingDatabase(options.dbPath);
  try {
    const repository = new CollectorRepository(db);
    const runId = resolveRunId(repository, options.runId);
    const rows = repository.listNoteExportRows(runId);
    writeFileSync(options.output, serializeNoteExportRows(rows), 'utf8');

    return {
      runId,
      output: options.output,
      rowCount: rows.length,
    };
  } finally {
    db.close();
  }
}

# XHS Pipeline Check Design

## Goal

`xhs-pipeline-check` closes the data collection and persistence phase by verifying one XHS run across SQLite, local media archive, and Feishu sync artifacts.

It answers one engineering question:

> Is this run's collected data complete enough to hand off to a later analysis module?

This command does not perform Agent analysis, topic generation, title generation, copywriting, automatic reruns, or Feishu reverse-read.

## System Boundary

The project has three future layers:

1. Data collection and persistence.
2. Data analysis and topic mining.
3. Content generation and operation execution.

`xhs-pipeline-check` belongs only to layer 1.

## Data Source Roles

- SQLite is the fact source for collected XHS data.
  - `xhs_search_runs`
  - `xhs_search_notes`
  - `xhs_raw_snapshots`
- Local media manifest is the fact source for archived media.
  - `data/xhs-media/run-<id>/manifest.json`
- Feishu sync report is the audit artifact for upload/sync status.
  - `data/feishu-sync/run-<id>/sync-report.json`
- Feishu Bitable is the human collaboration and review surface, not the primary Agent input source.

Future Agent analysis should consume a stable local input contract derived from SQLite + manifest + sync report. It should not use Feishu as the main data source.

## CLI

```bash
npm run collect -- xhs-pipeline-check --run-id 32
```

Options:

```text
--run-id <id>          required XHS search run id
--db-path <path>       default data/xhs-ops.sqlite
--manifest <path>      default data/xhs-media/run-<id>/manifest.json
--sync-report <path>   default data/feishu-sync/run-<id>/sync-report.json
--output-dir <path>    default data/xhs-pipeline-check/run-<id>
```

## Outputs

The command writes:

```text
data/xhs-pipeline-check/run-<id>/check.json
data/xhs-pipeline-check/run-<id>/check.md
```

`check.json` is for future programs and Agent runners.

`check.md` is for human review. It only reports collection/persistence health and must not contain content ideas or generated copy.

## Status Model

### `failed`

The run is not usable for downstream analysis.

Current blocking cases:

- XHS run does not exist.
- XHS run exists but has zero collected notes.

### `partial`

The run has usable data but also non-fatal gaps.

Current warning cases:

- Media manifest is missing.
- Feishu sync report is missing.
- Sync report record has `同步错误`.
- Sync warning indicates an oversized video was skipped.

### `complete`

The run has notes, manifest data, and Feishu sync report without blocking issues or warnings.

## Agent Readiness Metadata

The result includes readiness metadata for a future analysis layer:

```json
{
  "agent": {
    "ready": true,
    "inputContractVersion": "xhs-analysis-source/v1",
    "recommendedInput": {
      "dbPath": "data/xhs-ops.sqlite",
      "runId": 32,
      "manifestPath": "data/xhs-media/run-32/manifest.json",
      "syncReportPath": "data/feishu-sync/run-32/sync-report.json"
    }
  }
}
```

This is only a contract placeholder. It does not call an Agent or model.

## Why Feishu Is Not the Agent Source

Feishu is intentionally not the primary Agent input because:

- Humans can rename or change fields.
- Records are formatted for display, not stable machine contracts.
- Attachments are Feishu file tokens, while media workflows need local paths.
- Feishu API adds network, permission, pagination, and rate-limit failure modes.
- Manual edits reduce reproducibility.

Future Feishu reverse-read should be limited to human annotation fields and should write those annotations back into a separate SQLite table.

## Verification

Required verification:

```bash
npm test -- tests/xhs-pipeline-check.test.ts
npm test -- tests/cli-options.test.ts
npm test
npm run typecheck
npm run collect -- xhs-pipeline-check --run-id 32
```

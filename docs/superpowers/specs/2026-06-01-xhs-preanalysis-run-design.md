# XHS Pre-analysis Run Design

## Goal

Build one production-preview command that connects the full pre-analysis chain:

```text
Huitun keyword collection
  -> Huitun hot words as XHS search keywords
  -> XHS search and detail collection
  -> local media archive
  -> Feishu sync
  -> pipeline check
  -> xhs-analysis-source/v1 package
```

The command answers one operational question:

> Can this business keyword produce a verified, recoverable input package for the next analysis module?

This phase stops before analysis. It must not call Claude API, run Agent analysis, generate topics, titles, copy, or operational recommendations.

## User Entry

Add a CLI subcommand:

```bash
npm run collect -- xhs-preanalysis-run \
  --keyword 浴缸 \
  --limit-hotwords 5 \
  --limit-notes 20 \
  --xhs-limit-keywords 5 \
  --xhs-limit-per-sort 20 \
  --with-details
```

The user should not need to remember the six existing commands or manually pass run ids between them. The final terminal output and status report should show:

- Huitun collection run id.
- XHS search run ids.
- Media archive artifact paths.
- Feishu sync report paths.
- Pipeline check status for each XHS run.
- Analysis-source paths for runs that produced usable notes.
- Recovery commands for failed or partial stages.

## Default Production-preview Scale

Default values should exercise a realistic chain without turning the command into a high-frequency crawler:

- Huitun hot words: default `5`.
- Huitun note list limit: default follows existing collection default unless overridden.
- XHS keywords: default first `5` Huitun hot words.
- XHS sort list: existing `xhs-search` default sorts.
- XHS notes per sort: default `20`.
- XHS details: enabled when `--with-details` is passed.
- XHS detail delay, detail budget, rate-limit behavior: reuse existing `xhs-search` defaults.
- Media archive delay and safety behavior: reuse existing `xhs-media-archive` defaults.
- Execution: serial. Do not run concurrent operations against the same Huitun or XHS login state.

The user may override limits, delays, browser CDP URLs, dry-run Feishu sync, and output directory through CLI options.

## CLI Options

Core options:

```text
--keyword <keyword>              required business keyword for Huitun
--db-path <path>                 default data/xhs-ops.sqlite
--huitun-cdp-url <url>           default existing Huitun collector CDP URL
--xhs-cdp-url <url>              default existing xhs-search CDP URL
--media-cdp-url <url>            default existing xhs-media-archive CDP URL
--limit-hotwords <count>         default 5
--limit-notes <count>            Huitun note limit, existing default unless set
--days <7|30|90|180>             default existing Huitun collection default
--xhs-limit-keywords <count>     default 5
--xhs-sorts <list>               comma-separated XHS sort keys
--xhs-limit-per-sort <count>     default 20
--with-details                   collect XHS detail pages
--detail-budget <count>          default existing xhs-search detail budget
--detail-delay-min-ms <ms>       default existing xhs-search delay min
--detail-delay-max-ms <ms>       default existing xhs-search delay max
--media-delay-min-ms <ms>        default existing media archive delay min
--media-delay-max-ms <ms>        default existing media archive delay max
--feishu-dry-run                 validate sync payload without writing Feishu
--output-dir <path>              default data/xhs-preanalysis-run/<run-id>
```

The command should reuse existing parser defaults where possible, so the new entry does not create a second set of hidden behavior.

## Outputs

Write one orchestration status directory:

```text
data/xhs-preanalysis-run/<run-id>/status.json
data/xhs-preanalysis-run/<run-id>/status.md
```

`<run-id>` may be a timestamp-like orchestration id. It is separate from Huitun and XHS database run ids.

The command also produces the existing downstream artifacts:

```text
data/xhs-media/run-<xhs-run-id>/manifest.json
data/feishu-sync/run-<xhs-run-id>/sync-report.json
data/xhs-pipeline-check/run-<xhs-run-id>/check.json
data/xhs-pipeline-check/run-<xhs-run-id>/check.md
data/xhs-analysis-source/run-<xhs-run-id>/source.json
data/xhs-analysis-source/run-<xhs-run-id>/notes.jsonl
```

## Status Model

Each stage in `status.json` should use the same simple status vocabulary:

```text
pending | running | success | partial_success | failed | skipped
```

Top-level structure:

```json
{
  "orchestrationId": "2026-06-01T...",
  "keyword": "浴缸",
  "status": "partial_success",
  "startedAt": "...",
  "finishedAt": "...",
  "huitunCollection": { "status": "success", "runId": 12 },
  "xhsSearchCollections": [
    { "status": "success", "runId": 32, "keyword": "浴缸" }
  ],
  "mediaArchives": [
    { "status": "partial_success", "runId": 32, "manifestPath": "data/xhs-media/run-32/manifest.json" }
  ],
  "feishuSyncs": [
    { "status": "success", "runId": 32, "reportPath": "data/feishu-sync/run-32/sync-report.json" }
  ],
  "pipelineChecks": [
    { "status": "partial_success", "runId": 32, "checkJsonPath": "data/xhs-pipeline-check/run-32/check.json" }
  ],
  "analysisSources": [
    { "status": "success", "runId": 32, "sourceJsonPath": "data/xhs-analysis-source/run-32/source.json" }
  ]
}
```

Every stage record should include:

- `status`
- `startedAt`
- `finishedAt`
- `command` or command-like description
- `result` when available
- `errorMessage` when failed
- `recoveryCommand` when a human can retry that stage directly

## Failure and Recovery Rules

The orchestrator should prefer useful partial progress over all-or-nothing execution.

### Huitun collection

- If Huitun collection fails, stop the orchestration.
- Reason: without hot words there is no reliable XHS keyword source.
- `status.md` must show the Huitun failure and the command to rerun the orchestration.

### XHS search and detail collection

- Run XHS collection from the Huitun run using the selected hot words.
- If one XHS keyword/run fails, record it and continue with later keywords when possible.
- If XHS rate limiting is detected and existing `stopOnRateLimit` is active, stop further XHS page collection.
- Already-created XHS runs should continue to media archive, Feishu sync, pipeline check, and analysis-source.

### Media archive

- Media archive failures must not delete existing artifacts.
- If media archive safety stop occurs, record it and continue with pipeline check for already archived data.
- Missing or incomplete media should make the run partial, not unusable by default.

### Feishu sync

- Feishu is the human collaboration layer, not the primary analysis source.
- If Feishu sync fails, record the error and continue to pipeline check and analysis-source.
- `--feishu-dry-run` should still produce a sync report and allow later local stages to run.

### Pipeline check

- Always run pipeline check for XHS runs that have database notes.
- `failed` check means the run is not ready; still try analysis-source only if the source builder can read usable notes.
- `partial` check means the run can be carried forward with warnings.

### Analysis source

- Generate analysis-source for every XHS run with usable notes.
- Skip only when the XHS run has no notes or the source builder reports a fatal error.
- Successful `source.json` and `notes.jsonl` are the handoff contract for the next development round.

## Human-readable Report

`status.md` should be written for action, not for engineering archaeology.

It should answer:

1. Did the end-to-end chain run?
2. Which XHS runs are ready for next-round analysis?
3. Which runs are partial but still usable?
4. Which runs failed?
5. What exact command should the user run next to recover each failed stage?

Example section:

```markdown
## Analysis-ready runs

- Run #32: ready
  - Source: data/xhs-analysis-source/run-32/source.json
  - Notes: data/xhs-analysis-source/run-32/notes.jsonl

## Partial runs

- Run #33: usable with warnings
  - Warning: media incomplete
  - Recovery: npm run collect -- xhs-media-archive --run-id 33
```

The report must not include content ideas, topic analysis, title suggestions, or generated copy.

## Module Design

### `src/xhs-preanalysis-run-types.ts`

Owns orchestration types:

- Options.
- Stage status.
- Stage record.
- Overall result.
- Report artifact paths.

### `src/xhs-preanalysis-run.ts`

Owns orchestration only. It should not reimplement scraping, media archiving, Feishu field mapping, pipeline checking, or analysis-source merging.

It should call existing modules:

- `collect()` from `src/cli.ts` for Huitun collection.
- `collectXhsSearch()` from `src/xhs-search-collector.ts`.
- `archiveXhsRunMedia()` from `src/xhs-media-archive.ts`.
- `syncXhsRunToFeishu()` from `src/feishu/xhs-sync.ts`.
- `checkXhsPipeline()` from `src/xhs-pipeline-check.ts`.
- `buildXhsAnalysisSource()` from `src/xhs-analysis-source.ts`.

Use dependency injection for tests so orchestration failure behavior can be verified without launching browsers or calling Feishu.

### `src/cli.ts`

Add:

- `XhsPreanalysisRunCommandOptions`.
- Parser and help for `xhs-preanalysis-run`.
- Main dispatch branch that calls the orchestrator.

## Testing Strategy

Unit tests should not require live browsers or Feishu.

Add `tests/xhs-preanalysis-run.test.ts` with fake stage functions for:

- Huitun failure stops the chain.
- Successful Huitun collection triggers XHS search from that run.
- Multiple XHS runs are processed serially.
- XHS partial failure does not block already-created runs from downstream stages.
- Media archive failure still allows pipeline check and analysis-source when notes exist.
- Feishu sync failure still allows pipeline check and analysis-source.
- Pipeline-check `partial` produces an analysis-source and marks the run usable with warnings.
- No-note run skips analysis-source and writes a recovery command.
- `status.json` and `status.md` are written.
- `status.md` contains analysis-ready runs and recovery commands.

Extend `tests/cli-options.test.ts` for:

- Default option parsing.
- Explicit artifact/browser/delay options.
- Help includes `xhs-preanalysis-run` and its important options.
- Invalid numeric values fail with existing parser style.

## Verification

Development verification:

```bash
npm test -- tests/xhs-preanalysis-run.test.ts
npm test -- tests/cli-options.test.ts
npm test
npm run typecheck
```

Real production-preview smoke after implementation:

```bash
npm run collect -- xhs-preanalysis-run \
  --keyword 浴缸 \
  --limit-hotwords 5 \
  --xhs-limit-keywords 5 \
  --xhs-limit-per-sort 20 \
  --with-details
```

Smoke passes when:

- One command starts from Huitun and reaches the analysis-source stage for at least one XHS run with usable notes.
- Feishu sync is attempted and writes `data/feishu-sync/run-<id>/sync-report.json` unless intentionally run with dry-run behavior.
- `status.json` and `status.md` are written.
- `status.md` clearly identifies ready, partial, failed, and recovery actions.
- At least one generated `source.json` and `notes.jsonl` can be used as the next analysis-module input.

## Out of Scope

Do not implement in this phase:

- Claude API calls.
- Agent SDK workflows.
- Topic mining.
- Title generation.
- Copywriting.
- Automatic posting.
- Feishu reverse-read as the primary analysis source.
- Parallel browser operations against the same login state.

## User Impact

Before this design, the user has several working tools but must manually connect them. After this design, the user gets one production-line command. The system carries the run ids, writes the status, continues through recoverable failures, and leaves an analysis-ready local contract for the next development round.

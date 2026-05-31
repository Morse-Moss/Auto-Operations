# XHS Pipeline Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add `xhs-pipeline-check` to verify whether one XHS run completed the SQLite/media/Feishu data loop.

**Architecture:** The command reads SQLite as the fact source, local media manifest as the media source, and sync report as Feishu audit evidence. It writes JSON and Markdown reports and exposes only Agent readiness metadata, without invoking any model.

**Tech Stack:** Node.js, TypeScript, Commander, Node SQLite, Vitest.

---

## Files

- Create: `src/xhs-pipeline-check-types.ts`
- Create: `src/xhs-pipeline-check.ts`
- Modify: `src/cli.ts`
- Create: `tests/xhs-pipeline-check.test.ts`
- Modify: `tests/cli-options.test.ts`
- Create: `docs/superpowers/specs/2026-05-31-xhs-pipeline-check-design.md`

## Tasks

### Task 1: Core missing-run behavior

- [x] Write failing test for a missing XHS run.
- [x] Run `npm test -- tests/xhs-pipeline-check.test.ts` and confirm the module/function is missing.
- [x] Create `src/xhs-pipeline-check-types.ts` and `src/xhs-pipeline-check.ts`.
- [x] Implement minimal missing-run check.
- [x] Re-run targeted test and confirm it passes.

### Task 2: Empty run behavior

- [x] Add failing test for a run with zero notes.
- [x] Confirm it fails with `complete` instead of `failed`.
- [x] Count `xhs_search_notes` rows.
- [x] Return blocking issue `notes_empty`.
- [x] Re-run targeted test and confirm it passes.

### Task 3: Complete run behavior

- [x] Add test data with run, notes, manifest, media files, and sync report.
- [x] Confirm missing counters fail.
- [x] Count details, tags, media sources, manifest entries, matched feed ids, and synced records.
- [x] Return `complete` when all artifacts align.

### Task 4: Partial warning behavior

- [x] Add tests for missing manifest and missing sync report.
- [x] Confirm they fail as `complete`.
- [x] Add warnings `manifest_missing` and `sync_report_missing`.
- [x] Return `partial` when non-blocking warnings exist.

### Task 5: Feishu sync warning behavior

- [x] Add test for record-level `同步错误` containing oversized video warning.
- [x] Confirm it fails as `complete`.
- [x] Extract sync warnings from sync-report records.
- [x] Return `oversized_video_skipped` when the error contains `oversized video`.

### Task 6: Report writing

- [x] Add test for `check.json` and `check.md` outputs.
- [x] Confirm files are not written.
- [x] Write JSON and Markdown reports.
- [x] Ensure Markdown reports engineering health only and does not generate content ideas.

### Task 7: CLI integration

- [x] Add failing CLI parser/help tests.
- [x] Add `XhsPipelineCheckCommandOptions` and parser.
- [x] Add `xhs-pipeline-check` subcommand.
- [x] Route `main()` to `checkXhsPipeline()`.
- [x] Export parser for tests.

### Task 8: Verification

- [x] Run `npm test -- tests/xhs-pipeline-check.test.ts`.
- [x] Run `npm test -- tests/cli-options.test.ts`.
- [x] Run `npm test`.
- [x] Run `npm run typecheck`.
- [x] Run `npm run collect -- xhs-pipeline-check --run-id 32`.

## Out of Scope

- Claude API or Agent SDK calls.
- Topic generation.
- Content analysis.
- Title or copy generation.
- Automatic reruns.
- Feishu full-table reverse-read as the Agent source.
- Feishu attachment token reuse.

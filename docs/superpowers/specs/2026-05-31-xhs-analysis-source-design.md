# XHS Analysis Source v1 Design

## Goal

`xhs-analysis-source/v1` creates a stable local input package for later Agent analysis.

It does not analyze content, generate topics, generate titles, generate copy, call Claude API, or read Feishu as the primary data source. It only normalizes already collected data into a contract that future Agent workflows can consume without understanding SQLite tables, media manifests, or Feishu sync reports.

## System Position

The project workflow is:

```text
XHS collection
  ↓
SQLite persistence
  ↓
media archive manifest
  ↓
Feishu sync report
  ↓
xhs-pipeline-check
  ↓
xhs-analysis-source/v1
  ↓
future Agent analysis
```

`xhs-analysis-source/v1` belongs at the boundary between data collection/persistence and later data analysis.

## Source Roles

- SQLite remains the fact source.
  - `xhs_search_runs`
  - `xhs_search_notes`
  - `xhs_raw_snapshots`
- Local media manifest remains the media archive source.
  - `data/xhs-media/run-<id>/manifest.json`
- Feishu sync report remains the sync audit source.
  - `data/feishu-sync/run-<id>/sync-report.json`
- Pipeline check remains the run health source.
  - `data/xhs-pipeline-check/run-<id>/check.json`
- Feishu Bitable remains a human collaboration and review layer, not the primary Agent input.

## CLI

```bash
npm run collect -- xhs-analysis-source --run-id 32
```

Options:

```text
--run-id <id>          required XHS search run id
--db-path <path>       default data/xhs-ops.sqlite
--manifest <path>      default data/xhs-media/run-<id>/manifest.json
--sync-report <path>   default data/feishu-sync/run-<id>/sync-report.json
--pipeline-check <path> default data/xhs-pipeline-check/run-<id>/check.json
--output-dir <path>    default data/xhs-analysis-source/run-<id>
```

## Outputs

The command writes two files:

```text
data/xhs-analysis-source/run-<id>/source.json
data/xhs-analysis-source/run-<id>/notes.jsonl
```

It does not write `summary.md`. Human-readable collection health already belongs to `xhs-pipeline-check` via `data/xhs-pipeline-check/run-<id>/check.md`; duplicating that report here would blur module responsibility.

### `source.json`

Run-level index and metadata for programs and future Agent runners.

Shape:

```json
{
  "contractVersion": "xhs-analysis-source/v1",
  "runId": 32,
  "run": {
    "keyword": "浴缸",
    "source": "manual_keyword",
    "sorts": ["most_liked"],
    "status": "success",
    "startedAt": "...",
    "finishedAt": "..."
  },
  "pipeline": {
    "status": "partial",
    "agentReady": true,
    "warnings": []
  },
  "counts": {
    "notes": 20,
    "details": 20,
    "mediaSources": 20,
    "manifestEntries": 20,
    "feishuSyncedRecords": 20
  },
  "files": {
    "notesJsonl": "data/xhs-analysis-source/run-32/notes.jsonl",
    "pipelineCheck": "data/xhs-pipeline-check/run-32/check.json",
    "pipelineCheckMarkdown": "data/xhs-pipeline-check/run-32/check.md",
    "manifest": "data/xhs-media/run-32/manifest.json",
    "syncReport": "data/feishu-sync/run-32/sync-report.json"
  }
}
```

### `notes.jsonl`

One JSON object per note. This is the main input for future Agent analysis.

Shape per line:

```json
{
  "contractVersion": "xhs-analysis-source/v1",
  "runId": 32,
  "feedId": "feed1",
  "rank": 1,
  "keyword": "浴缸",
  "sort": {
    "key": "most_liked",
    "label": "最多点赞"
  },
  "note": {
    "title": "浴缸标题",
    "authorName": "作者A",
    "type": "video",
    "url": "https://www.xiaohongshu.com/search_result/feed1?xsec_token=...",
    "exploreUrl": "https://www.xiaohongshu.com/explore/feed1"
  },
  "metrics": {
    "likeText": "100",
    "collectText": "20",
    "commentText": "3",
    "shareText": "1",
    "rawMetricText": "赞 100 收藏 20"
  },
  "content": {
    "detailText": "正文",
    "rawDetailText": "原始详情文本",
    "analysisSourceText": "用于分析的长文本",
    "tags": ["浴缸", "装修"],
    "topics": ["浴缸"],
    "comments": ["想知道尺寸"]
  },
  "media": {
    "sourceUrls": [],
    "localImages": [],
    "localVideos": [],
    "completeVideoFile": null,
    "status": "success",
    "completeVideoStatus": "complete"
  },
  "feishu": {
    "synced": true,
    "syncError": null
  },
  "quality": {
    "hasDetail": true,
    "hasTags": true,
    "hasComments": true,
    "hasMediaSource": true,
    "hasLocalMedia": true,
    "hasFeishuSyncWarning": false
  }
}
```

The JSONL format is intentional: future Agent workflows can stream, batch, split, or retry per note without loading one large JSON document.

## Human-Readable Summary

`xhs-analysis-source/v1` does not generate its own Markdown summary. Human-readable health reporting remains in `xhs-pipeline-check/check.md`. `source.json.files.pipelineCheckMarkdown` points to that existing report when using default paths.

## Data Merging Rules

### SQLite note data

Read rows from `xhs_search_notes` by `run_id`, ordered by `sort_key`, `rank_index`, and `id`.

Parse JSON fields defensively:

- `detail_tags_json` → `content.tags`
- `source_topic_texts_json` → `content.topics`
- `source_comments_json` → `content.comments`
- `media_sources_json` → `media.sourceUrls`

Invalid JSON becomes an empty array and should add a warning to `source.json.warnings`.

### Manifest data

Join manifest entries by `feedId`.

Map:

- `imageFiles` → `media.localImages`
- `videoFiles` → `media.localVideos`
- `completeVideoFile` → `media.completeVideoFile`
- `status` → `media.status`
- `completeVideoStatus` → `media.completeVideoStatus`

If no manifest entry exists for a note, keep the note and set local media arrays to empty. This is a note-level quality issue, not a reason to drop the note.

### Feishu sync report data

Join sync report records by `feedId`.

Map:

- record exists and status is `success` → `feishu.synced = true`
- record field `同步错误` → `feishu.syncError`
- missing record → `feishu.synced = false`

Feishu sync status is audit metadata only. It does not replace SQLite facts.

### Pipeline check data

If `check.json` exists, copy its status and warnings into `source.json.pipeline`.

If it is missing, still generate the source package but set:

```json
{
  "pipeline": {
    "status": "unknown",
    "agentReady": false,
    "warnings": [{ "code": "pipeline_check_missing" }]
  }
}
```

## Failure and Warning Rules

### Fatal failures

- SQLite database cannot be opened.
- XHS run does not exist.
- XHS run has zero notes.

### Non-fatal warnings

- Manifest missing.
- Sync report missing.
- Pipeline check missing.
- Note has invalid JSON in a parsed field.
- Manifest has entries that do not match any DB feed id.
- DB note has no matching manifest entry.
- Feishu sync record has `同步错误`.

Non-fatal warnings should not block source generation because later analysis can still use text data.

## Out of Scope

Do not implement in this phase:

- Claude API or Agent SDK calls.
- Topic generation.
- Content analysis.
- Title generation.
- Copywriting.
- Automatic reruns.
- Writing analysis results back to SQLite.
- Pulling full Feishu Bitable records as the primary source.
- Feishu manual annotation reverse-sync.

## Verification

Required tests:

- Generates source package for a complete run.
- Keeps notes when manifest is missing, with warnings.
- Keeps notes when sync report is missing, with warnings.
- Maps manifest media by `feedId`.
- Maps Feishu sync errors by `feedId`.
- Handles invalid JSON fields defensively.
- CLI parser and help expose `xhs-analysis-source` options.

Required commands:

```bash
npm test -- tests/xhs-analysis-source.test.ts
npm test -- tests/cli-options.test.ts
npm test
npm run typecheck
npm run collect -- xhs-analysis-source --run-id 32
```

# XHS Source Image Auto-Completion Fix Design

Date: 2026-07-12
Status: Approved in conversation

## Scope

This change repairs the `自动补全原文图片` action in the XHS content library.

It does not modify note discovery, account default selection, account login UI, publishing, the fragile XHS signing SDK, or the legacy TypeScript system.

## Problem

The current action first performs an anonymous HTTP fetch of the stored note URL. Stored `xsec_token` values expire, and XHS commonly returns a generic page or `/404` with no note images. When that happens, the frontend silently copies a page script and asks the user to paste it into the original page. That fallback is manual, and its `sendBeacon` result only proves that the browser queued a request, not that the backend imported images.

The repository also contains a stronger browser extractor that understands `image_list`, `imageList`, `info_list`, `infoList`, `url_default`, and `urlDefault`, but the automatic backend path does not share that normalization.

## Goals

- Make the primary button perform a real authenticated, automatic import.
- Automatically select a usable PC account owned by the current user.
- Require an XHS PC login when no usable authenticated account exists.
- Stop depending on stored `xsec_token` values.
- Reuse the existing PC note-detail adapter without modifying the low-level signing SDK.
- Normalize the image field variants already supported by the browser extractor.
- Persist a safe terminal summary for each attempted import.
- Keep the manual page-import action separate and explicit.

## Non-Goals

- Do not change note discovery or its account selector.
- Do not implement automatic login or store new credentials.
- Do not perform real publishing or other high-risk account actions.
- Do not make the browser extension the primary execution path.
- Do not retry indiscriminately or rotate accounts after rate limiting.

## Backend Design

### Account Selection

The import service builds an ordered list of candidate PC accounts owned by the current user:

1. The note's existing `platform_account_id`, when it is an XHS PC account with `status=active` and a cookie version.
2. Other XHS PC accounts for the same user with `status=active` and a cookie version, newest first.

Deleted, expired, non-PC, cross-user, and cookieless accounts are excluded.

Candidates are tried serially and at low frequency. The service moves to the next candidate only when the adapter response is classified as a missing or expired login. Rate limiting and other provider failures fail closed immediately.

If no candidate succeeds because no authenticated account exists, the endpoint returns HTTP 409 with:

```json
{
  "detail": {
    "code": "xhs_login_required",
    "message": "自动补全原文图片需要先登录小红书 PC 账号，请前往账号矩阵登录后重试。"
  }
}
```

The import flow does not change account status. Account lifecycle changes remain owned by the account thread.

### Note Detail Retrieval

The service resolves legacy data-acquisition links through the existing resolver when required, extracts the real XHS note ID, and builds a clean URL without query parameters:

```text
https://www.xiaohongshu.com/explore/<note-id>
```

It calls `XhsPcApiAdapter.get_note_info` with the selected account cookies. The PC feed API receives the note ID with an empty token and the existing default `pc_search` source, so stale stored `xsec_token` values are not reused.

The anonymous `requests.get` page fetch is removed from the primary automatic path.

### Image Normalization

Add a payload-level image extraction function to the existing source-image extractor. It accepts both snake_case and camelCase variants used by current XHS payloads:

- `image_list` and `imageList`
- `info_list` and `infoList`
- `url_default` and `urlDefault`
- `url_pre` and `urlPre`
- direct `url`, `trace_id`, `traceId`, `file_id`, and `fileId`

URLs continue through the existing XHS image validation, canonical deduplication, 50-image limit, asset insertion, and local download policy.

### Result Semantics

The endpoint returns the existing count contract on success:

- `total_source_image_count`
- `imported_count`
- `skipped_count`
- `downloaded_count`
- `failed_count`
- `items`

The note's `raw_json.source_image_import` stores a sanitized terminal summary containing status, selected account ID, counts, and a query-free source URL. It never stores cookies, access tokens, or `xsec_token` values.

Terminal statuses are `completed`, `partial`, `not_found`, `login_required`, and `failed`.

## Frontend Design

The existing `自动补全原文图片` button remains the primary action.

- While running, it shows the existing loading state.
- On success, it refreshes the selected note and reports imported, existing, downloaded, and failed counts.
- On `xhs_login_required`, it shows the backend message with the concrete next step to log in through the account matrix.
- A zero-image result is reported as a real failure instead of automatically copying a script.
- Other adapter failures remain visible and do not trigger hidden fallback behavior.

The separate manual page-import button remains available as an explicit secondary action. The automatic button never invokes it implicitly.

## Error Handling

- No eligible account or all candidates report invalid login: HTTP 409 `xhs_login_required`.
- Detail payload contains no note images: HTTP 422 `source_images_not_found`.
- Provider rate limit: preserve the existing rate-limit classification and do not rotate accounts.
- Other provider failure: fail closed with a safe user message.
- Individual image download failures: import the asset references, return `partial`, and expose per-item `download_failed` results.

## Tests

Backend tests must prove:

- The note-bound active PC account is preferred.
- The newest eligible fallback account is selected when the bound account is unusable.
- Deleted, expired, non-PC, cross-user, and cookieless accounts are ignored.
- A login-expired response advances to the next candidate.
- A rate-limit response does not rotate accounts.
- No usable login returns the structured HTTP 409 response.
- Stale query tokens are removed before PC detail retrieval.
- `infoList/info_list` and snake_case/camelCase payloads produce the expected image URLs.
- Imported images are deduplicated, downloaded, persisted, and summarized without secrets.

Frontend contract tests must prove:

- The automatic action no longer calls `preparePageImportScript` on zero results or errors.
- Structured backend error messages are displayed.
- The explicit manual import action remains separate.

Focused regression verification includes the relevant backend tests, extractor tests, frontend build, backend health check, and browser validation on desktop and mobile widths. Live XHS verification is low-frequency and read-only apart from writing imported image assets into the current user's local library; it must not publish or interact with a note.

## Acceptance Criteria

- Clicking `自动补全原文图片` with at least one usable PC login imports all normalized source images without requiring clipboard or address-bar actions.
- The action succeeds when the stored source URL has an expired `xsec_token`, provided the current PC session can access the public note by ID.
- Without a usable PC login, no provider request is made and the user sees the required login message.
- The automatic action never reports success from `sendBeacon` queueing.
- No credentials or query tokens are persisted in summaries or logs.
- Note discovery and account-selection files remain untouched by this change.

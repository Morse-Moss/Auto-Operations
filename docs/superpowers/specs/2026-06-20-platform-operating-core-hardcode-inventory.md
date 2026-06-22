# Platform Operating Core Hardcode Inventory

> Stage 1 artifact for `docs/superpowers/plans/2026-06-20-platform-operating-core.md`.
>
> Purpose: list the current XHS-specific assumptions that slow down new-platform development, classify them by target Platform Operating Core layer, and assign safe migration stages. This is a read-only inventory and checklist document; it does not authorize code changes by itself.

## 1. Scope and workspace evidence

### 1.1 Stage contract

Goal:
- Inventory hardcoded XHS assumptions and platform-coupling points that block reusable multi-platform development.
- Convert the findings into migration guidance and a new-platform adapter checklist.

Non-goals:
- No backend/frontend code changes.
- No tests or Alembic changes.
- No XHS SDK/signature changes under `apis/`, `xhs_utils/`, or `static/`.
- No real provider calls, real account actions, real publish, or browser automation.
- No commit or push.

Allowed files for this stage:
- `docs/superpowers/specs/2026-06-20-platform-operating-core-design.md`
- `docs/superpowers/plans/2026-06-20-platform-operating-core.md`
- `docs/superpowers/specs/2026-06-20-platform-operating-core-hardcode-inventory.md`

### 1.2 Workspace status at Stage 1 start

Command run:

```bash
git status --short --branch
```

Observed:

```text
## master
 M tests/backend/test_wechat_official_redfox_collect.py
?? compare-shots/
?? docs/superpowers/plans/2026-06-20-platform-operating-core.md
?? docs/superpowers/specs/2026-06-20-platform-operating-core-design.md
```

Scope classification:

| Path | Classification | Stage 1 action |
|---|---|---|
| `tests/backend/test_wechat_official_redfox_collect.py` | Existing unrelated/user work | Do not modify |
| `compare-shots/` | Existing unrelated/user work | Do not modify |
| `docs/superpowers/plans/2026-06-20-platform-operating-core.md` | Allowed Stage 0/1 doc | May modify if needed |
| `docs/superpowers/specs/2026-06-20-platform-operating-core-design.md` | Allowed Stage 0/1 doc | May modify if needed |
| `docs/superpowers/specs/2026-06-20-platform-operating-core-hardcode-inventory.md` | Stage 1 artifact | Create/update |

## 2. Executive summary

The current system already contains reusable multi-platform foundations, but reuse is blocked by seven categories of XHS coupling:

1. Generic backend APIs/services still gate ownership with `platform == "xhs"`.
2. File and export ownership policies still rely on `xhs-*` prefixes.
3. XHS raw payload parsing is embedded in frontend pages instead of platform renderers/normalizers.
4. Backend services import private helpers from XHS API routes.
5. Account binding UI and auth panels hardcode XHS/Huitun platform and account-kind behavior.
6. Publish options and Creator publish payload shape leak XHS concepts into global publish types.
7. `AutoTask` is structurally an XHS workflow, not a generic workflow definition.

The right migration order is not “replace all `xhs` strings.” Some `xhs` references are valid because they live inside XHS platform implementation files. The target is:

```text
Generic core: no platform-specific business assumptions.
Platform adapter/renderer/mapper: platform-specific behavior allowed.
```

## 3. Inventory table

Risk legend:

- Low: documentation or frontend type/shell only; unlikely to affect real accounts.
- Medium: read-only data flow, content library, account UI, or file ownership policy.
- High: credentials, publish, scheduler, auto task, or any path that can touch real accounts.

Suggested stage references the implementation plan stages in `docs/superpowers/plans/2026-06-20-platform-operating-core.md`.

| ID | Category | Representative paths | Current behavior | Target core/adapter | Risk | Suggested stage |
|---|---|---|---|---|---|---|
| HC-01 | Generic notes API ownership hardcodes XHS | `backend/app/api/notes.py:255` | `_get_owned_account` rejects accounts unless `account.platform == "xhs"`, despite `Note.platform` being generic. | Content Library Core should validate account ownership by requested `platform_id`; platform-specific content access goes through Content Adapter. | Medium | Stage 4 |
| HC-02 | Publish API requires XHS Creator account | `backend/app/api/publish.py:415`, `backend/app/api/publish.py:456` | Publish upload/execute paths require `account.platform == "xhs"` and `sub_type == "creator"`. | Publish Queue Core should ask platform publish rules for required account kind and enforce via Capability Policy. | High | Stage 7 |
| HC-03 | Scheduler publish path requires XHS Creator account | `backend/app/services/scheduler_service.py:124` | Background due-job publish path checks XHS Creator directly. | Scheduler must route through PublishOrchestrationService and Capability Policy; scheduler has no special privilege. | High | Stage 7 / Stage 8 |
| HC-04 | Task API real publish confirmation is XHS-specific | `backend/app/api/tasks.py:80` | Real publish confirmation logic keys on `platform == "xhs"`. | Capability Policy should require confirmation based on capability risk, not platform hardcode. | High | Stage 7 |
| HC-05 | AutoTask account ownership is XHS-specific | `backend/app/api/auto_tasks.py:95`, `backend/app/api/auto_tasks.py:165-166`, `backend/app/api/auto_tasks.py:249-250` | AutoTask requires XHS `pc` and `creator` accounts. | Workflow Automation Core should define workflow account requirements per platform/workflow type. | High | Stage 8 |
| HC-06 | AutoTask model fields encode XHS workflow | `backend/app/models/auto_task.py:20-30` | Model stores `pc_account_id`, `creator_account_id`, `ai_instruction`, `total_published`. | Generic workflow definition: `platform_id`, `workflow_type`, `account_refs`, `payload`, `risk_policy`, `authorization_ref`, run counters by outcome. | High | Stage 8 |
| HC-07 | AutoTask execution creates XHS notes/jobs directly | `backend/app/api/auto_tasks.py:255`, `backend/app/api/auto_tasks.py:320`, `backend/app/api/auto_tasks.py:386`, `backend/app/api/auto_tasks.py:408` | Runtime fetches XHS notes, creates XHS drafts/jobs, increments `total_published`. | Workflow steps should use Content/Draft/Publish adapters and only increment success counters after verified success. | High | Stage 8 |
| HC-08 | Scheduler imports XHS route private helpers | `backend/app/services/scheduler_service.py:440-441` | Scheduler imports `_data_items` and `_normalize_search_item` from XHS API routes. | Move normalization into `backend/app/adapters/xhs/mappers.py` or Content Adapter; services must not depend on route-private helpers. | Medium/High | Stage 4 |
| HC-09 | Monitoring service imports XHS route private helpers | `backend/app/services/monitoring_crawl_service.py:9-15`, `backend/app/services/monitoring_crawl_service.py:122`, `backend/app/services/monitoring_crawl_service.py:144` | Service imports `_save_normalized_notes`, `_normalize_detail_payload`, `_normalize_search_item`, `_note_matches_target`, serializers from API routes. | Extract XHS mappers and monitoring serializers into service/adapter modules with golden tests. | Medium | Stage 4 |
| HC-10 | Generic notes API imports XHS route private helpers | `backend/app/api/notes.py:15-19` | Generic `/notes` API imports `_cookies_to_string`, `get_xhs_pc_api_adapter_factory`, and `normalize_comment_payload` from XHS platform route modules. | Move cookie conversion, comment normalization, and adapter access behind Content Library Core / XHS content adapter or mapper/service modules. | Medium | Stage 4 |
| HC-11 | File/media owner prefixes are XHS-specific | `backend/app/api/files.py:47-56`, `backend/app/api/files.py:88`, `backend/app/api/files.py:101`, `backend/app/api/files.py:113`, `backend/app/api/files.py:135`, `backend/app/api/files.py:193` | Upload, generated image, and media validation use `xhs-image`, `xhs-asset`, `xhs-upload` prefixes. | Asset Workshop Core should generate/validate platform-aware and owner-aware asset prefixes while preserving legacy XHS prefixes. | Medium | Stage 6 |
| HC-12 | Export owner prefixes are XHS-specific | `backend/app/api/files.py:164`, `backend/app/api/notes.py:641`, `backend/app/api/platforms/xhs/analytics.py:339` | Downloads accept `xhs-notes` / `xhs-report`; note export and analytics report write XHS-prefixed names. | Export Storage Core should use `content-export`, `platform-report`, or platform-aware owner prefixes. | Medium | Stage 6 |
| HC-13 | Asset downloader writes XHS asset prefix | `backend/app/services/asset_downloader.py:22` | Downloaded assets are always named `xhs-asset-u...`. | Asset downloader should accept `platform_id` and `asset_kind`; legacy default remains XHS until migrated. | Medium | Stage 6 |
| HC-14 | AI service validates only XHS asset prefixes | `backend/app/services/ai_service.py:452-454` | AI image/media references are accepted only if prefixed `xhs-upload`, `xhs-asset`, `xhs-image`. | AI/media validation should use Asset Ownership Policy rather than XHS string prefixes. | Medium | Stage 6 |
| HC-15 | XHS raw payload parsing in content library UI | `frontend/src/pages/platforms/xhs/library-page.tsx:71-168`, `frontend/src/pages/platforms/xhs/library-page.tsx:575-578` | UI parses `raw_json`, `note_card`, `interact_info`, `xsec_token`, `xsec_source`, and renders raw JSON. | Move parsing/builders into XHS content renderer/adapter; shared Content Library shell receives normalized display fields. | Medium | Stage 3 / Stage 4 |
| HC-16 | XHS raw payload parsing in analytics UI | `frontend/src/pages/platforms/xhs/analytics-page.tsx:159-172` | Analytics page constructs XHS note URL from `xsec_token` and nested raw payload. | Shared analytics/content renderer should get canonical URL from platform normalizer. | Medium | Stage 3 / Stage 4 |
| HC-17 | XHS raw payload parsing in discovery/crawler UI | `frontend/src/pages/platforms/xhs/discovery-page.tsx:48`, `frontend/src/pages/platforms/xhs/crawler-page.tsx:107-128`, `frontend/src/pages/platforms/xhs/crawler-page.tsx:202-215` | UI understands XHS-specific diagnostic kinds and raw card shape. | Keep diagnostics mapping in XHS adapter/renderer; shared diagnostic shell receives normalized labels and severity. | Medium | Stage 3 / Stage 9 |
| HC-18 | XHS draft source preview reads raw_json | `frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx:26` | XHS draft workbench derives source display from XHS raw payload. | This is allowed inside XHS adapter/page extras, but must not move into shared Draft Workbench shell. | Low | Stage 2 |
| HC-19 | Account drawer hardcodes platforms and account kinds | `frontend/src/components/account/add-account-drawer.tsx:16-34`, `frontend/src/components/account/add-account-drawer.tsx:37-51`, `frontend/src/components/account/add-account-drawer.tsx:89-114` | Drawer only knows `xhs | huitun`, `pc | creator | main`, and static QR/phone/cookie options. | Account Matrix Core should expose account auth schema; drawer renders platform/account/auth options from schema. | Medium | Stage 5 |
| HC-20 | QR login panel branches on XHS/Huitun | `frontend/src/components/account/qr-login-panel.tsx:18-23`, `frontend/src/components/account/qr-login-panel.tsx:46-90`, `frontend/src/components/account/qr-login-panel.tsx:153` | QR panel starts/polls different login sessions using platform conditionals; XHS PC sync creator checkbox is embedded. | Auth adapter registry should route QR start/poll/confirm; sync-creator becomes XHS-specific auth option. | Medium | Stage 5 |
| HC-21 | Cookie import panel branches on XHS/Huitun | `frontend/src/components/account/cookie-import-panel.tsx:9-14`, `frontend/src/components/account/cookie-import-panel.tsx:29-52`, `frontend/src/components/account/cookie-import-panel.tsx:59` | Cookie import selects XHS vs Huitun import path and placeholder by platform conditional. | Auth adapter schema should provide importer, placeholder/help text, and platform-specific options. | Medium | Stage 5 |
| HC-22 | Phone login only models XHS account types | `frontend/src/components/account/add-account-drawer.tsx:113-114` | PhoneLoginPanel receives `pc | creator`; no generic auth schema. | Phone auth should be an auth-mode implementation scoped to platforms that declare it. | Medium | Stage 5 |
| HC-23 | Frontend content library is XHS-specific route and API call | `frontend/src/pages/platforms/xhs/library-page.tsx:222`, `frontend/src/pages/platforms/xhs/library-page.tsx:257`, `frontend/src/pages/platforms/xhs/library-page.tsx:267` | XHS page calls `fetchSavedNotes({ platform: "xhs" })` and creates XHS drafts from notes. | Shared ContentLibrary shell should accept `platformId` and adapter; XHS adapter wires existing calls. | Medium | Stage 3 |
| HC-24 | Publish page filters XHS accounts directly | `frontend/src/pages/platforms/xhs/publish-page.tsx:112-113` | Publish page filters `a.platform === "xhs"` and `sub_type === "creator"`. | Publish UI should get required account role from platform publish rules; XHS page may keep this until shared Publish Center exists. | High | Stage 7 |
| HC-25 | Generic CreateDraftPayload is XHS-only | `frontend/src/types/index.ts:955-958` | Shared-looking type only allows `platform: "xhs"` and `source_note_id`. | Draft creation type should become platform-generic or be split into XHS-specific and generic source-to-draft payloads. | Medium | Stage 2 / Stage 4 |
| HC-26 | PublishOptions encodes XHS Creator concepts globally | `frontend/src/types/index.ts:1325-1331`, `backend/app/api/drafts.py:35-63`, `backend/app/api/publish.py:29-109` | `topics`, `location`, `privacy_type`, `is_private`, `draft_tags` flow into XHS `note_info`. | Introduce platform publish schema/rules; global publish intent keeps generic fields and platform options stay namespaced. | High | Stage 7 |
| HC-27 | XHS Creator payload shape leaks into publish internals | `backend/app/api/publish.py:159`, `backend/app/api/publish.py:177-192`, `backend/app/api/publish.py:506-535`, `backend/app/services/scheduler_service.py:61`, `backend/app/services/scheduler_service.py:150-159`, `backend/app/services/scheduler_service.py:570-585` | Global publish/scheduler paths know `fileIds`, `postTime`, `type`, `note_info`, and Creator `post_note`. | PublishAdapter should translate `PublishIntent` into XHS Creator payload; core should not build `note_info` directly. | High | Stage 7 |
| HC-28 | Direct SDK imports outside XHS adapter boundary | `backend/app/api/accounts.py:213`, `backend/app/api/accounts.py:29`, `backend/app/services/account_service.py:12` | Generic account API/service imports `apis.xhs_creator_apis` or `xhs_utils.cookie_util`. | CredentialProvider / AccountAdapter should own XHS SDK/cookie utilities; generic services should not import fragile SDK/signature utilities. | High | Stage 5 / separate CredentialProvider stage |
| HC-29 | XHS platform directories are valid but not reusable core | `backend/app/api/platforms/xhs/*`, `frontend/src/pages/platforms/xhs/*` | Many `platform="xhs"` literals live inside XHS-specific platform implementation files. | Do not mechanically remove these. Treat as valid platform adapter/page code unless a shared shell imports them. | Low | N/A guardrail |
| HC-30 | Huitun appears as account platform/source but not backend registry workspace | `frontend/src/components/account/add-account-drawer.tsx:16-23`, `backend/app/services/huitun_account_service.py`, `backend/app/api/keyword_groups.py:428-501` | Huitun is used for account/source/discovery flows and keyword candidates, while backend platform registry treats workspace platforms separately. | Split future IDs into `WorkspacePlatformId`, `AccountPlatformId`, `IntegrationSourceId`; Huitun/RedFox should be discovery/source providers unless promoted deliberately. | Medium | Stage 1 docs / Stage 5 |
| HC-31 | WeChat Official has platform-specific raw/original tables | `backend/app/models/wechat_official.py`, `backend/app/api/platforms/wechat_official/*`, `backend/app/services/wechat_official_*` | WeChat official article/session/metric/comment/draft-source live in platform-specific tables/services. | Keep as platform raw layer; map into Content/Draft/Task/Publish operating layer when user workflow needs shared behavior. | Medium | Stage 4 / Stage 10 |

## 4. Detailed findings by category

### 4.1 Backend generic APIs/services with `platform == "xhs"`

Important distinction:

- Valid: XHS implementation files under `backend/app/api/platforms/xhs/` can contain XHS literals.
- Problematic: generic APIs/services such as `notes.py`, `publish.py`, `auto_tasks.py`, `scheduler_service.py`, `tasks.py` use XHS assumptions directly.

Representative examples:

| Path | Why it matters | Migration target |
|---|---|---|
| `backend/app/api/notes.py:255` | Content library account ownership is XHS-only. | Content Library Core ownership check by requested platform. |
| `backend/app/api/publish.py:415`, `backend/app/api/publish.py:456` | Generic publish route only supports XHS Creator account. | Publish Queue Core + PublishAdapter account requirements. |
| `backend/app/services/scheduler_service.py:124` | Scheduler directly checks XHS Creator account. | Scheduler calls PublishOrchestrationService; no direct platform check. |
| `backend/app/api/tasks.py:80` | Confirmation rule uses `platform == "xhs"`. | Capability risk-based confirmation. |
| `backend/app/api/auto_tasks.py:95` | AutoTask ownership only supports XHS. | Workflow account requirements by workflow type. |

Migration rule:

```text
Generic route/service -> PlatformPolicyService / Core service -> Platform adapter
```

Do not replace all XHS checks blindly; some checks are correct in XHS-only routes.

### 4.2 XHS file/export prefixes

Current prefix families:

- `xhs-image-u<user>-...`
- `xhs-asset-u<user>-...`
- `xhs-upload-u<user>-...`
- `xhs-notes-u<user>-...`
- `xhs-report-u<user>-...`

Representative paths:

- `backend/app/api/files.py`
- `backend/app/api/notes.py`
- `backend/app/api/platforms/xhs/analytics.py`
- `backend/app/services/asset_downloader.py`
- `backend/app/services/ai_service.py`

Migration rule:

1. Keep legacy XHS prefixes accepted for backward compatibility.
2. Add a platform-aware owner prefix helper.
3. Make upload/compose/resize/export accept platform or asset owner context.
4. Do not migrate existing files without explicit separate approval.

### 4.3 XHS raw payload parsing in frontend UI

The biggest frontend reuse blocker is not that XHS pages exist; it is that reusable UI behaviors parse XHS raw payload shape directly:

- `raw_json.data.items[0].note_card`
- `interact_info`
- `xsec_token`
- `xsec_source`
- `tag_list`
- `liked_count`, `collected_count`, `comment_count`, `share_count`

Representative paths:

- `frontend/src/pages/platforms/xhs/library-page.tsx`
- `frontend/src/pages/platforms/xhs/analytics-page.tsx`
- `frontend/src/pages/platforms/xhs/discovery-page.tsx`
- `frontend/src/pages/platforms/xhs/crawler-page.tsx`
- `frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx`

Migration rule:

```text
Shared shell receives normalized display data.
XHS adapter/renderer owns XHS raw parsing and URL construction.
```

`xsec_token` and similar private platform metadata must not become shared DTO fields.

### 4.4 Services importing XHS route-private helpers

Current issue:

- `monitoring_crawl_service.py` imports from `backend.app.api.platforms.xhs.crawl`, `pc`, and `monitoring`.
- `scheduler_service.py` imports `_data_items` and `_normalize_search_item` from XHS API routes.

Why this is bad:

- API routes become reusable libraries by accident.
- Service behavior can break when route helper names change.
- New platforms will copy route-private helper patterns.

Migration rule:

1. Extract XHS mappers to `backend/app/adapters/xhs/mappers.py` or a content mapper service.
2. Extract monitoring serializers/matchers into service-level modules.
3. Add golden tests before replacing imports.
4. Keep route responses unchanged.

### 4.5 Account binding UI hardcodes platform/auth behavior

Current hardcoded concepts:

- `AccountPlatform = "xhs" | "huitun"`
- `AccountType = "pc" | "creator" | "main"`
- `LoginMethod = "qr" | "phone" | "cookie"`
- XHS PC can sync Creator.
- Huitun cannot use phone.

Representative paths:

- `frontend/src/components/account/add-account-drawer.tsx`
- `frontend/src/components/account/qr-login-panel.tsx`
- `frontend/src/components/account/cookie-import-panel.tsx`

Migration rule:

```text
Platform/account auth schema -> AddAccountDrawer -> Auth method panel registry
```

Do not remove XHS/Huitun behavior in the same step. First express current behavior as schema, then render from schema.

### 4.6 Publish options and Creator payload leakage

Current global publish fields:

- `topics`
- `location`
- `privacy_type`
- `is_private`
- `draft_tags`

Current XHS Creator internal payload concepts in generic paths:

- `fileIds`
- `postTime`
- `type`
- `note_info`
- `post_note`

Representative paths:

- `frontend/src/types/index.ts`
- `backend/app/api/drafts.py`
- `backend/app/api/publish.py`
- `backend/app/services/scheduler_service.py`
- `backend/app/adapters/xhs/creator_api_adapter.py`

Migration rule:

```text
Global PublishIntent: title/body/assets/mode/scheduled_at/privacy abstraction
Platform publish schema: topics/location/privacy mapping for XHS
XHS PublishAdapter: converts intent to Creator note_info
```

High-risk constraint:

- Do not migrate real publish before no-side-effect dry-run and confirmation tests exist.

### 4.7 AutoTask is an XHS workflow, not a core workflow

Current AutoTask assumptions:

- PC account for search/read.
- Creator account for publish.
- Keywords as primary input.
- AI instruction assumes XHS note rewrite.
- `total_published` assumes the goal is publishing.
- Execution path creates XHS draft and publish job directly.

Representative paths:

- `backend/app/models/auto_task.py`
- `backend/app/api/auto_tasks.py`
- `backend/app/services/scheduler_service.py`

Migration rule:

```text
AutoTask -> WorkflowDefinition
WorkflowDefinition -> platform/workflow adapter steps
Step result -> TaskEvent / DiagnosticEvent / PublishJob / Draft
```

Historical AutoTasks must not automatically gain real publish authorization.

### 4.8 Direct SDK imports outside adapter boundary

Representative findings:

- `backend/app/api/accounts.py` imports `xhs_utils.cookie_util` and directly imports `apis.xhs_creator_apis` for Creator fileIds validation.
- `backend/app/services/account_service.py` imports `xhs_utils.cookie_util`.
- `backend/app/adapters/xhs/*` imports SDK/signature utilities, which is acceptable because those files are XHS adapter boundary.

Migration rule:

- `backend/app/adapters/xhs/*` may import XHS SDK/signature utilities.
- Generic account routes/services should use AccountAdapter/CredentialProvider.
- Do not touch `apis/`, `xhs_utils/`, `static/` during Platform Operating Core migration unless a separate signed-off SDK design exists.

## 5. New-platform adapter checklist

Every new platform must provide these artifacts before code implementation proceeds beyond read-only exploration.

### 5.1 Product decision record

| Field | Required answer |
|---|---|
| User goal | What user workflow does this platform improve? |
| First useful slice | What is the smallest useful capability: account, content read, draft, publish dry-run, or automation? |
| Non-goals | What explicitly stays out of scope? |
| Risk posture | Read-only / dry-run / real account action / high-risk automation? |
| Source tier | Official API, manual import, experimental connector, observed/fragile source? |

### 5.2 PlatformMeta artifact

Must define:

- `platform_id`
- `name_cn`
- `name_en`
- `region`
- `platform_type`
- `release_stage`
- `enabled`
- `default_route`
- `adapter_key`
- `risk_level`
- `auth_modes`
- `accent_color`
- `icon`

Acceptance criteria:

- Planned platforms remain Coming Soon and cannot execute real actions.
- Enabled platform has at least one real adapter-backed or explicitly fake/test-backed capability.

### 5.3 Capability matrix artifact

For every relevant capability:

| Capability | Required fields |
|---|---|
| `account.manage` | status, risk, confirmation, notes |
| `account.login_cookie` | status, risk, confirmation, notes |
| `account.login_qr` | status, risk, confirmation, notes |
| `content.discover` | status, risk, confirmation, notes |
| `content.crawl_detail` | status, risk, confirmation, notes |
| `content.library` | status, risk, confirmation, notes |
| `content.rewrite` | status, risk, confirmation, notes |
| `asset.image_generate` | status, risk, confirmation, notes |
| `asset.video_generate` | status, risk, confirmation, notes |
| `publish.create_job` | status, risk, confirmation, notes |
| `publish.schedule` | status, risk, confirmation, notes |
| `publish.dry_run` | status, risk, confirmation, notes |
| `publish.real_publish` | status, risk, confirmation, notes |
| `monitoring.keyword` | status, risk, confirmation, notes |
| `monitoring.competitor` | status, risk, confirmation, notes |
| `engagement.comment_read` | status, risk, confirmation, notes |
| `engagement.reply_suggest` | status, risk, confirmation, notes |
| `engagement.reply_execute` | status, risk, confirmation, notes |
| `workflow.auto_ops` | status, risk, confirmation, notes |

Hard rule:

- `engagement.reply_execute` defaults to `blocked/high/requires_confirmation=true` unless a separate safety design is approved.

### 5.4 Account adapter artifact

Must specify:

- Supported account kinds.
- Supported auth modes.
- Credential storage model.
- Credential expiry detection.
- Health check behavior.
- Account status mapping.
- Required scopes for each capability.
- Which fields are safe to return to frontend.
- Which fields are secrets and must never leave backend.

Minimum tests:

- Unknown platform/account kind rejected.
- Credential invalid maps to user-readable re-login instruction.
- No plaintext credential appears in response/log fixture.

### 5.5 Content adapter artifact

Must specify:

- Discovery inputs.
- Detail fetch inputs.
- Raw item examples with secrets redacted.
- Normalized content fields.
- Metric mapping.
- Asset extraction.
- Comment extraction.
- Canonical URL builder.
- Private metadata storage/reference strategy.
- Save-to-library behavior.

Minimum tests:

- Raw payload -> normalized summary.
- Raw payload -> normalized detail.
- Missing optional fields degrade gracefully.
- Sensitive/private tokens remain private references.

### 5.6 Content renderer artifact

Must specify:

- List card fields.
- Detail drawer fields.
- Metric labels.
- External link behavior.
- Raw JSON visibility policy.
- Platform-specific warning labels.

Rule:

- Shared Content Library shell cannot import platform-specific raw parsing helpers.

### 5.7 Draft adapter artifact

Must specify:

- Draft list source.
- Draft detail fields.
- Save patch shape.
- Duplicate/delete support.
- Dry-run support.
- Create-from-source support.
- Platform editor extras.
- Assistant extras.
- Validation rules.

Minimum tests:

- Adapter can load drafts.
- Save preserves platform-specific constraints.
- Unsupported actions are hidden or fail closed.

### 5.8 Asset rules artifact

Must specify:

- Allowed media types.
- Max file size.
- Image/video dimensions.
- Count limits.
- Cover rules.
- Upload requirements.
- Legacy file compatibility if migrating existing data.

Minimum tests:

- Invalid extension rejected.
- Cross-user asset rejected.
- Legacy XHS prefixes preserved during migration.
- New platform-aware prefix accepted when applicable.

### 5.9 Publish adapter artifact

Must specify:

- Required account role/kind.
- Publish modes.
- Schedule mode distinction: app schedule vs platform schedule.
- Dry-run no-side-effect guarantee.
- Upload behavior.
- Real publish behavior.
- Receipt mapping.
- Error mapping.
- Retryability.
- Confirmation requirements.

Minimum tests:

- Dry-run does not call upload/post.
- Real publish without confirmation blocked.
- Planned platform cannot publish.
- Adapter support cannot override registry blocked status.

### 5.10 Workflow adapter artifact

Must specify:

- Supported workflow types.
- Required accounts per step.
- Step payload shape.
- Step output shape.
- Rate limits/cooldowns.
- Retry policy.
- Authorization model for real actions.
- Diagnostics emitted.

Minimum tests:

- Scheduler/auto task cannot bypass Capability Policy.
- Historical tasks do not gain real publish authorization.
- Failed publish does not increment success counters.

### 5.11 Diagnostics mapping artifact

Must map platform errors to standard categories:

- `auth_expired`
- `credential_invalid`
- `rate_limited`
- `network`
- `signature_failed`
- `invalid_request`
- `upstream_changed`
- `not_found`
- `risk_blocked`
- `blocked_capability`
- `validation`
- `unknown`

Must include:

- User message.
- Next action.
- Retryability.
- Raw reference policy.
- Secret redaction guarantee.

## 6. Migration sequencing recommendations

### 6.1 Safe first moves

1. Keep this inventory updated as Stage 1 source of truth.
2. Solidify Draft Workbench as canonical adapter UI sample.
3. Extract Content Library frontend shell while keeping XHS renderer.
4. Extract XHS content mappers with golden tests.
5. Convert account drawer to schema-driven UI.

### 6.2 Moves that require extra caution

1. File prefix migration: preserve legacy filenames and owner validation.
2. Generic notes API platform ownership: needs tests for XHS and future platform account ownership.
3. Direct SDK imports in account services: move only after CredentialProvider contract exists.

### 6.3 Moves that must wait for safety gates

1. Real publish orchestration.
2. Scheduler publish migration.
3. AutoTask workflow migration.
4. Any engagement reply execution.
5. Any new real-platform API connector.

## 7. Anti-patterns to prevent in future PRs

Do not accept new code that:

- Adds `if platform == "new_platform"` in a shared core module instead of an adapter.
- Adds new file prefixes like `<platform>-upload` without using Asset Ownership Policy.
- Parses platform raw JSON inside shared UI shells.
- Imports API route private helpers from services.
- Lets scheduler/retry/auto task call platform adapters without Capability Policy.
- Adds publish options to the global `PublishOptions` type when they only belong to one platform.
- Logs or returns raw credentials, private tokens, or platform anti-abuse metadata.
- Promotes a discovery source such as Huitun/RedFox into a full workspace platform without a product decision record.

## 8. Stage 1 completion criteria

This inventory satisfies Stage 1 when:

1. It identifies the major current XHS coupling categories.
2. It distinguishes valid XHS implementation files from problematic shared-core hardcodes.
3. It assigns each hardcode class to a target core/adapter layer.
4. It assigns migration risk and suggested plan stage.
5. It includes a concrete new-platform adapter checklist.
6. It does not recommend touching forbidden SDK/signature layers.
7. It is reviewed independently before code implementation begins.

# Platform Operating Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use Morse's development mode. This is a staged CEO-governed plan. Do not implement all stages in one pass. Each implementation stage needs a stage contract, scope firewall, independent review gate, and fresh verification evidence.

**Goal:** 从当前 XHS_ALL_IN_ONE 中沉淀多平台运营内核，让后续新平台只需接入 platform adapter / normalizer / rules，而不是复制小红书整套页面、API、模型和任务链路。

**Architecture:** 保持 FastAPI + SQLAlchemy + React/Vite + Ant Design 主系统基线；以现有 Platform Registry、Capability Policy、Draft Workbench 为基础，分阶段把账号矩阵、内容库、素材工坊、发布中心、自动化任务、诊断通知沉淀为 Platform Operating Core。第一阶段只做文档和 hardcode 清单；后续阶段按低风险到高风险迁移，先 read-only/草稿，再发布/自动化。

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy, pytest, React, Vite, TypeScript, Ant Design.

---

## Scope Firewall

### Existing unrelated changes

开始执行任何阶段前，必须先运行：

```bash
git status --short --branch
```

当前写计划时已知存在 unrelated/user work：

- `backend/app/services/wechat_official_draft_service.py`
- `frontend/src/types/index.ts`
- `tests/backend/test_wechat_official_drafts.py`
- `tests/backend/test_wechat_official_redfox_collect.py`
- `compare-shots/`
- `docs/superpowers/plans/2026-06-18-wechat-official-draft-workshop-independence.md`
- `docs/superpowers/specs/2026-06-18-wechat-official-draft-workshop-independence-design.md`

任何实现 agent 不得 stage、revert、format、覆盖这些 unrelated changes，除非阶段 contract 明确允许且用户批准。

### Globally forbidden without explicit user approval

- 不改 `apis/`、`xhs_utils/`、`static/`。
- 不执行真实 XHS/公众号/第三方平台发布。
- 不调用真实/付费 Provider。
- 不安装依赖。
- 不创建 worktree，除非用户明确要求。
- 不 deploy。
- 不 `git add` / `git commit` / `git push`，除非用户明确要求。
- 不删除数据、数据库、分支、worktree。
- 不把明文 Cookie/token/API key 写入代码、文档、日志、测试 fixture。

### Global Definition of Done

每个代码实现阶段至少满足：

- 有 RED 或明确说明 TDD 不适用。
- 有最小实现。
- 有 focused tests / build / typecheck。
- 有 independent read-only review verdict。
- 有 `git diff --check`。
- 有 evidence ledger。
- 明确报告没有测试真实发布/真实账号动作。

---

## Stage 0: Design/spec baseline already created

**Status:** Done by this planning turn.

**Files created:**

- `docs/superpowers/specs/2026-06-20-platform-operating-core-design.md`
- `docs/superpowers/plans/2026-06-20-platform-operating-core.md`

**Purpose:** 锁定 Platform Operating Core 的设计边界和执行路线，避免后续新平台继续复制 XHS 专用代码。

**No code changes:** 本阶段不改业务代码、不跑测试、不提交。

---

## Stage 1: Hardcode inventory and adapter checklist documentation

**Goal:** 先把当前阻碍多平台复用的 hardcode 点列成可执行清单，并把新平台接入 checklist 固化到文档中。不改业务代码。

**Allowed files:**

- Modify: `docs/superpowers/specs/2026-06-20-platform-operating-core-design.md`
- Modify: `docs/superpowers/plans/2026-06-20-platform-operating-core.md`
- Create optional: `docs/superpowers/specs/2026-06-20-platform-operating-core-hardcode-inventory.md`

**Forbidden:**

- Any backend/frontend code.
- Tests.
- Alembic/database files.
- XHS SDK/signature files.

**Steps:**

- [x] Step 1: Run `git status --short --branch` and record unrelated changes.
- [x] Step 2: Use read-only code search / codegraph to inventory hardcodes in these categories:
  - `platform == "xhs"` in generic APIs/services.
  - `xhs-*` file/export prefixes.
  - XHS raw_json parsing in frontend pages.
  - route private helper dependencies from services.
  - AddAccountDrawer hardcoded platform/auth/account kinds.
  - PublishOptions fields that are XHS-specific but global.
  - AutoTask fields that are XHS-specific.
- [x] Step 3: Create or update the hardcode inventory doc with path, current behavior, target core/adapter, migration risk, suggested stage.
- [x] Step 4: Extend the new-platform adapter checklist with exact required artifacts:
  - PlatformMeta.
  - Capability matrix.
  - Account adapter.
  - Content normalizer.
  - Content renderer.
  - Draft adapter.
  - Asset rules.
  - Publish adapter.
  - Workflow adapter.
  - Diagnostics mapping.
- [x] Step 5: Independent read-only review of the inventory for omissions and over-broad migration recommendations.

**Verification:**

- Documentation only: no tests required.
- Run `git diff --check -- docs/superpowers/specs/2026-06-20-platform-operating-core-design.md docs/superpowers/plans/2026-06-20-platform-operating-core.md docs/superpowers/specs/2026-06-20-platform-operating-core-hardcode-inventory.md` if the inventory doc exists.

**Review gate:**

- PASS if the inventory is actionable and does not prescribe unsafe broad rewrites.
- BLOCKER if it misses major known hardcode categories or recommends touching forbidden SDK/signature layers.

---

## Stage 2: Draft Workbench standardization follow-up

**Status:** Done in scoped Stage 2 pass.

**Goal:** 把已经存在的共享草稿工作台正式确认为多平台 UI adapter 样板，并补齐缺失的 contract tests / docs without changing platform semantics.

**Allowed files candidate set:**

- `frontend/src/components/draft-workbench/*`
- `frontend/src/pages/platforms/xhs/*draft*`
- `frontend/src/pages/wechat-official/*draft*`
- `frontend/src/types/index.ts` only if type contract needs a minimal safe change.
- `tests/backend/test_wechat_official_drafts.py` only for existing backend draft regression, if needed.
- Docs under `docs/superpowers/specs/` and `docs/superpowers/plans/`.

**Forbidden:**

- No backend schema migration.
- No real publish.
- No content library semantic changes.
- No XHS SDK/signature changes.

**Steps:**

- [x] Step 1: Inspect current `DraftWorkbenchAdapter`, `useDraftWorkbench`, XHS draft adapter, WeChat draft adapter.
- [x] Step 2: Write focused frontend type/behavior tests if the project has an existing frontend test pattern; otherwise document why TDD is limited and use TypeScript build as guard.
- [x] Step 3: Ensure the adapter contract clearly supports:
  - platform id.
  - capabilities.
  - load/save/duplicate/delete/dry-run/create-from-source.
  - platform-specific list subtitle and empty state.
  - optional editor/assistant extras.
- [x] Step 4: Ensure XHS and WeChat official adapters do not leak wrong semantics:
  - XHS keeps current draft meaning.
  - WeChat official drafts remain independent and source-free unless explicitly created from source.
- [x] Step 5: Update docs to mark Draft Workbench as the first canonical Platform Operating Core UI pattern.
- [x] Step 6: Run verification.

**Stage 2 result:** `DraftWorkbenchShell` remains platform-neutral; `DraftWorkbenchAdapter` is the canonical UI adapter contract sample; platform-only behavior stays in XHS/公众号 adapters and page-level extras. No backend business code, provider calls, or real platform actions were touched.

**Verification:**

```bash
cd frontend && npm run build
```

```bash
py -3 -m pytest tests/backend/test_wechat_official_drafts.py -q
```

```bash
git diff --check
```

**Review gate:**

- PASS if shared workbench stays platform-neutral and both current platforms preserve behavior.
- BLOCKER if the shared shell gains XHS/WeChat-specific business logic.

---

## Stage 3: Content Library Core extraction design and read-only shell

**Status:** Done in scoped Stage 3 frontend pass.

**Goal:** 把 XHS 内容库页面拆解为 shared shell + platform adapter 的低风险 read-only 骨架，不先改数据库表名、不迁移真实数据。

**Allowed files candidate set:**

- Create: `frontend/src/components/content-library/content-library-types.ts`
- Create: `frontend/src/components/content-library/use-content-library.ts`
- Create: `frontend/src/components/content-library/content-library-shell.tsx`
- Create: `frontend/src/components/content-library/index.ts`
- Create: `frontend/src/pages/platforms/xhs/xhs-content-library-adapter.ts`
- Modify: `frontend/src/pages/platforms/xhs/library-page.tsx`
- Create optional: frontend tests if existing pattern supports.

**Forbidden:**

- No backend DB/table rename.
- No WeChat article migration in this stage.
- No changes to XHS crawl APIs.
- No deletion of existing XHS content library features unless replaced by equivalent behavior.

**TDD requirements:**

- Prefer frontend contract tests if available.
- If no frontend test harness exists, first run `cd frontend && npm run build` after type/interface changes and capture RED/compile failures before completing implementation.

**Steps:**

- [x] Step 1: Define `ContentLibraryAdapter` type for list/detail/assets/comments/tags/batch actions/export.
- [x] Step 2: Move only generic state and layout into shared shell:
  - loading/error/empty.
  - filters.
  - pagination.
  - selected IDs.
  - detail drawer shell.
  - batch action shell.
- [x] Step 3: Keep XHS-specific rendering in `xhsContentLibraryAdapter` or renderer helpers:
  - XHS note URL.
  - author profile URL.
  - raw_json note_card/interact_info parsing.
  - XHS engagement labels.
- [x] Step 4: Wire existing XHS page through the shared shell without changing API responses.
- [x] Step 5: Run frontend build and manual diff review.

**Stage 3 result:** `ContentLibraryShell` and `useContentLibrary` are platform-neutral and do not parse XHS `raw_json`/`xsec_token`; XHS API calls, labels, URL builders, engagement parsing, card/table/detail renderers, and draft navigation stay in `xhs-content-library-adapter.ts`. `library-page.tsx` now only creates the XHS adapter, uses the shared hook, and renders the shared shell.

**Verification:**

```bash
cd frontend && npm run build
```

```bash
git diff --check
```

Optional if backend untouched: no backend tests required. If backend touched accidentally, stop and re-scope.

**Review gate:**

- PASS if XHS content library behavior is preserved and platform-specific parsing is no longer embedded in the shared shell.
- BLOCKER if generic shell imports XHS-specific helpers or exposes XHS internals to other platforms.

---

## Stage 4: Backend content normalizer and API hardcode removal plan

**Status:** Current low-risk mapper closure complete; deeper cross-platform ingestion/database unification intentionally deferred.

**Goal:** 后端先做 mapper/normalizer 和 tests，逐步解除 content library API 中 XHS-only assumptions。不要 rename tables。

**Allowed files candidate set:**

- Create: `backend/app/platforms/content_contracts.py` or extend `backend/app/platforms/contracts.py` if appropriate.
- Create: `backend/app/adapters/xhs/mappers.py`
- Create: `tests/backend/test_xhs_content_mappers.py`
- Modify: `backend/app/api/notes.py` only in a later subtask with explicit review.
- Modify: related serializer tests if existing.

**Forbidden:**

- No DB migration.
- No XHS SDK/signature changes.
- No route response field break.
- No WeChat article ingestion rewrite.

**Steps:**

- [x] Step 1: Write golden tests for current XHS note normalization from fixed raw payloads.
- [x] Step 2: Implement XHS mapper that extracts:
  - canonical URL.
  - author profile URL.
  - tags.
  - engagement metrics.
  - cover/video/assets.
- [x] Step 3: Update frontend or backend only if mapper is used without response shape change. Closed in later scoped passes: XHS notes serialization uses `map_xhs_content`, XHS comment payload normalization uses `normalize_xhs_comment_payload`, and WeChat Official content library mapping uses dedicated shared ContentLibraryItem mapper tests.
- [x] Step 4: Plan separate migration for `_get_owned_account` hardcoded `account.platform != "xhs"`; current low-risk closure is covered by explicit notes account platform expectation tests, while multi-platform ingestion/database unification remains deferred.
- [x] Step 5: Produce follow-up plan for WeChat Article -> ContentItem mapping. Closed by `frontend/src/pages/wechat-official/wechat-official-content-library-mapper.ts` and `frontend/tests/wechat-official-content-library-mapper.test.ts`.

**Current low-risk mapper closure evidence:**

- XHS note serializer route integration is closed: `backend/app/api/notes.py` uses `map_xhs_content`, with `tests/backend/test_notes_xhs_serializer.py` covering mapper fallback, DB asset priority, non-XHS raw-shape tolerance, and mapping-cache reuse.
- XHS comment payload normalization is closed: route code imports `normalize_xhs_comment_payload` from `backend/app/adapters/xhs/mappers.py`, with focused mapper tests in `tests/backend/test_xhs_content_mappers.py`.
- Notes account platform expectation is explicit: multi-platform ingestion/database unification remains deferred, but current XHS-only route behavior is test-covered.
- WeChat Official article-to-shared-ContentLibraryItem mapping is closed for current frontend scope: `frontend/src/pages/wechat-official/wechat-official-content-library-mapper.ts` has focused tests in `frontend/tests/wechat-official-content-library-mapper.test.ts`.
- Remaining cross-platform ingestion, database unification, or route response redesign is deferred outside this closure program.

**First scoped mapper pass evidence:**

- Added pure `backend/app/adapters/xhs/mappers.py` mapper with no DB/session/FastAPI/SDK dependency.
- Added `tests/backend/test_xhs_content_mappers.py` golden coverage for direct and nested metrics, URL building, author URLs, tags, cover/video/assets, note type, and publish timestamp.
- Did not modify `backend/app/api/notes.py`, route response fields, database models, Alembic files, frontend, or XHS SDK/signature layers.

**Verification:**

```bash
py -3 -m pytest tests/backend/test_xhs_content_mappers.py -q
```

If `backend/app/api/notes.py` changes:

```bash
py -3 -m pytest tests/backend -q
```

```bash
git diff --check
```

**Review gate:**

- PASS if mapper tests lock compatibility and no response shape changes.
- BLOCKER if API behavior changes without focused tests.

---

## Stage 5: Account Matrix schema-driven UI and auth contract

**Status:** First low-risk frontend step done: AddAccountDrawer now renders platform/account type/login method choices from a local account auth schema while preserving existing XHS/Huitun login behavior.

**Goal:** 让账号添加 UI 从 hardcoded XHS/Huitun 分支转为 platform registry/auth schema driven，为新平台账号接入降低成本。

**Allowed files candidate set:**

- `frontend/src/components/account/add-account-drawer.tsx`
- `frontend/src/components/account/*login-panel*.tsx`
- `frontend/src/types/index.ts`
- `frontend/src/lib/api.ts`
- Backend platform registry if new public auth schema is needed.
- Tests for platform registry/auth schema if backend changes.

**Forbidden:**

- No real new platform login.
- No credential storage changes without separate CredentialProvider stage.
- No plaintext credentials in tests.

**Steps:**

- [x] Step 1: Define account auth schema fields for the current frontend fallback:
  - platform_id/platform.
  - account_kinds/accountTypes.
  - auth_modes/loginMethods.
  - default account kind/defaultAccountType.
  - selector visibility for unavailable account kind choices.
- [x] Step 2: Extend frontend fallback with auth schema; backend registry remains unchanged in this low-risk step.
- [x] Step 3: Refactor AddAccountDrawer to render options from schema.
- [x] Step 4: Preserve current XHS and Huitun behavior:
  - XHS keeps PC/Creator account type selector and QR/phone/Cookie methods.
  - Huitun keeps main account type internally and QR/Cookie methods only.
  - Existing Qr/Cookie/Phone panel API call semantics are unchanged.
- [x] Step 5: Add type/build verification via frontend build.

**Stage 5 first-step evidence:**

- Created `frontend/src/components/account/account-auth-schema.ts` as the local schema/helper boundary.
- Updated `frontend/src/components/account/add-account-drawer.tsx` so the drawer no longer decides account type/login method availability with scattered `platform === "huitun"` branches.
- No backend registry, login endpoint, credential storage, SDK/signature layer, or real platform action changed.

**Verification:**

```bash
cd frontend && npm run build
```

If backend registry changed:

```bash
py -3 -m pytest tests/backend/test_platforms.py -q
```

```bash
git diff --check
```

**Review gate:**

- PASS if adding a future platform account kind requires schema/adapter, not editing drawer branch logic.
- BLOCKER if the UI still hardcodes platform behavior in the shared drawer.

---

## Frontend Platform Core shell pass: section registry, accounts, actions, readiness

**Status:** Done in scoped Platform Core Stage 1/2/3 closeout commit `84379ef`.

**Goal:** 把平台工作区导航、公众号 section 页面、账号卡片 shell、推荐动作和 readiness 诊断面板沉淀到前端共享 `frontend/src/platform-core/`，让 XHS 与公众号复用同一套平台工作区结构，而不是继续在各自页面里复制布局和路由分支。

**Files created:**

- `frontend/src/platform-core/registry/platform-sections.tsx`
- `frontend/src/platform-core/accounts/platform-account-types.ts`
- `frontend/src/platform-core/accounts/platform-accounts-shell.tsx`
- `frontend/src/platform-core/actions/platform-action-types.ts`
- `frontend/src/platform-core/actions/platform-action-hub.tsx`
- `frontend/src/platform-core/readiness/platform-readiness-panel.tsx`
- `frontend/src/platform-core/shell/platform-section-page.tsx`
- `frontend/src/pages/wechat-official/wechat-official-accounts-page.tsx`
- `frontend/src/pages/wechat-official/wechat-official-discovery-page.tsx`
- `frontend/src/pages/wechat-official/wechat-official-drafts-page.tsx`
- `frontend/src/pages/wechat-official/wechat-official-library-page.tsx`
- `frontend/src/pages/wechat-official/wechat-official-readiness-actions.ts`
- `frontend/src/pages/wechat-official/wechat-official-settings-page.tsx`

**Files modified:**

- `frontend/src/app/router.tsx`
- `frontend/src/components/layout/app-shell.tsx`
- `frontend/src/pages/platforms/xhs/accounts-page.tsx`
- `frontend/src/pages/wechat-official/wechat-official-dashboard.tsx`
- `tests/backend/test_api.py`

**Stage result:**

- `AppShell` now gets platform nav items from `platformSectionRegistry` instead of hardcoding公众号 path branches.
- 公众号 dashboard no longer routes sub-sections internally; `/accounts`, `/discovery`, `/library`, `/drafts`, and `/settings` are dedicated pages wrapped by `PlatformSectionPage`.
- `PlatformAccountsShell` is shared by XHS and公众号 account pages; platform login/binding behavior remains in platform pages/drawers, not in the shared shell.
- `PlatformReadinessPanel` and `PlatformActionHub` provide shared readiness/action presentation;公众号-specific action construction lives in `wechat-official-readiness-actions.ts`.
- Real公众号授权、素材上传、预览发送、群发发布 remain blocked; this pass added no real provider calls, no database migration, no deployment, and no service restart.

**Verification evidence:**

```bash
py -3.12 -m pytest tests/backend/test_api.py -k "platform_navigation or platform_accounts_shell or xhs_accounts_page or wechat_official_accounts_page or wechat_official_routes or wechat_official_dashboard_no_longer or wechat_official_platform_split or platform_action_hub or platform_readiness_panel or wechat_official_readiness_actions" -q
# 10 passed, 181 deselected in 2.20s
```

```bash
npm --prefix frontend run build
# PASS; Vite reported only the existing large chunk warning.
```

**Boundary notes:**

- This pass deliberately excluded other dirty threads: Feishu/XHS auto-ops, publish page, Feishu models/API/migration, compare-shots, creator pending login/user messages.
- The local `python` command points to the Windows Store alias and exits 49 in this workspace; use `py -3.12` for backend pytest commands.

---

## Stage 6: Asset Workshop platform-aware storage policy

**Goal:** 去掉文件上传、生成、导出下载中的 XHS-only 文件名前缀和 owner policy，形成 platform-aware asset storage core。

**Allowed files candidate set:**

- `backend/app/api/files.py`
- `backend/app/services/image_util.py` only if needed.
- `tests/backend/test_files.py` or new focused file tests.
- Frontend API/types only if response shape extends with platform-aware metadata.

**Forbidden:**

- No deletion of existing media files.
- No migration of existing stored files unless explicitly approved.
- No broad storage layout rewrite.

**TDD requirements:**

- Write tests before changing file prefix validation.
- Cover backward compatibility with existing `xhs-*` filenames.

**Steps:**

- [x] Step 1: Write tests for allowed owner prefixes:
  - existing XHS media still downloadable.
  - new platform-aware prefix accepted.
  - path traversal rejected.
  - cross-user prefix rejected.
- [x] Step 2: Introduce helper for platform-aware asset prefix.
- [x] Step 3: Extend upload/compose/resize to accept optional platform with safe default.
- [x] Step 4: Extend export owner prefixes generically.
- [x] Step 5: Preserve existing response fields.

**Stage 6 first scoped pass evidence:**

- Added pure `backend/app/services/asset_storage_policy.py` owner prefix policy backed by `PlatformId` allowlist.
- Added `tests/backend/test_asset_storage_policy.py` coverage for legacy XHS media/export prefixes, WeChat Official platform-aware prefixes, traversal/subdirectory rejection, cross-user rejection, and invalid platform/kind fail-closed behavior.
- Wired `backend/app/api/files.py`, `backend/app/services/asset_downloader.py`, and `backend/app/services/ai_service.py` to policy helpers while preserving default `xhs` naming and response fields.
- Did not migrate/delete existing media/export files, did not change storage directories, did not call real platform/provider actions, and did not touch `apis/`, `xhs_utils/`, `static/`, frontend, route response fields, or database files.

Verification evidence from first scoped pass:

- RED: `cd /e/小红书 && py -3 -m pytest tests/backend/test_asset_storage_policy.py -q` failed during collection with `ModuleNotFoundError: No module named 'backend.app.services.asset_storage_policy'` before implementation.
- GREEN: `cd /e/小红书 && py -3 -m pytest tests/backend/test_asset_storage_policy.py -q` -> `14 passed in 0.03s`.
- Scoped API regression: `cd /e/小红书 && py -3 -m pytest tests/backend/test_api.py -q -k "file or image or export"` -> `17 passed, 143 deselected in 11.69s`.
- Full API regression: `cd /e/小红书 && py -3 -m pytest tests/backend/test_api.py -q` -> `159 passed, 1 failed, 6 warnings in 205.85s`; failure is `test_library_page_preserves_delete_and_media_logic`, asserting `handleDeleteNote` in pre-existing dirty `frontend/src/pages/platforms/xhs/library-page.tsx`, which is outside Stage 6 allowed files.
- Compile check: `cd /e/小红书 && py -3 -m py_compile backend/app/services/asset_storage_policy.py backend/app/api/files.py backend/app/services/asset_downloader.py backend/app/services/ai_service.py tests/backend/test_asset_storage_policy.py` -> exit 0, no output.

**Verification:**

```bash
py -3 -m pytest tests/backend/test_files.py -q
```

or focused new file test command.

```bash
git diff --check
```

**Review gate:**

- PASS if no existing media access breaks and new naming no longer hardcodes XHS.
- BLOCKER if owner validation becomes broader or unsafe.

---

## Stage 7: Publish Queue policy integration and dry-run skeleton

**Goal:** 发布中心接入 PlatformPolicyService 和 dry-run no-side-effect skeleton，先保证安全门禁，不急于真实发布迁移。

**Allowed files candidate set:**

- `backend/app/services/publish_orchestration_service.py`
- `backend/app/api/drafts.py`
- `backend/app/api/publish.py`
- `backend/app/models/publish.py` only if no migration needed; otherwise create separate migration plan.
- `tests/backend/test_publish_orchestration_contract.py`
- `tests/backend/test_drafts.py` or existing publish tests.

**Forbidden:**

- No real platform publish in tests.
- No upload/post side effects in dry-run.
- No scheduler/auto task migration in same stage unless explicitly scoped.

**TDD requirements:**

- Tests must prove dry-run does not call upload/post.
- Tests must prove high-risk real publish without confirmation is blocked before adapter call.

**Steps:**

- [x] Step 1: Define dry-run result skeleton as a plain dict contract: `{job_id, ok, publish_blocked, checks, policy}`.
- [x] Step 2: Write fake/trap adapter tests for no-side-effect dry-run.
- [x] Step 3: Implement `PublishOrchestrationService.dry_run` using `PlatformPolicyService` and local state checks.
- [x] Step 4: Keep existing publish behavior compatible; added only `POST /api/publish/jobs/{job_id}/dry-run` no-side-effect endpoint.
- [x] Step 5: Keep current `publish.dry_run` registry status unchanged: XHS available, WeChat Official planned/fail-closed.

**Stage 7 first scoped pass evidence:**

- Added `backend/app/services/publish_orchestration_service.py` with `PublishOrchestrationService.dry_run` only; no real upload/post path migrated.
- Added `tests/backend/test_publish_orchestration_contract.py` contract coverage for valid XHS dry-run, invalid local checks, planned platform fail-closed, dry-run endpoint no-side-effect behavior, and unconfirmed real publish adapter non-instantiation.
- Added `POST /api/publish/jobs/{job_id}/dry-run` in `backend/app/api/publish.py`; existing publish route response shape and confirmation semantics are unchanged.
- Did not modify `PublishJob` / `PublishAsset` models, Alembic files, scheduler/auto task behavior, SDK/signature layers, or real provider/platform actions.

Verification evidence from first scoped pass:

- RED: `cd /e/小红书 && py -3 -m pytest tests/backend/test_publish_orchestration_contract.py -q` failed during collection with `ModuleNotFoundError: No module named 'backend.app.services.publish_orchestration_service'` before implementation.
- GREEN: `cd /e/小红书 && py -3 -m pytest tests/backend/test_publish_orchestration_contract.py -q` -> `5 passed in 7.70s`.
- Confirmation regression: `cd /e/小红书 && py -3 -m pytest tests/backend/test_publish_real_publish_confirmation.py -q` -> `3 passed in 4.84s`.
- Publish API focused regression: `cd /e/小红书 && py -3 -m pytest tests/backend/test_api.py -q -k "publish"` -> `25 passed, 135 deselected, 5 warnings in 30.14s`.

**Verification:**

```bash
py -3 -m pytest tests/backend/test_publish_orchestration_contract.py -q
```

Run adjacent existing tests if modified route touches drafts/publish:

```bash
py -3 -m pytest tests/backend/test_wechat_official_drafts.py -q
```

```bash
git diff --check
```

**Review gate:**

- PASS if dry-run is provably side-effect free and real publish remains blocked without confirmation.
- BLOCKER if any dry-run path can call real upload/post.

---

## Stage 8: Workflow Automation Core design-to-skeleton

**Goal:** 把 `AutoTask` 从 XHS-specific 自动运营任务向 workflow definition 迁移，先做 skeleton 和 tests，不改变现有自动化行为。

**Allowed files candidate set:**

- `backend/app/models/auto_task.py` only if no migration required; if migration required, create separate Alembic plan first.
- `backend/app/api/auto_tasks.py`
- `backend/app/services/workflow_*` new files.
- `tests/backend/test_auto_tasks.py` or new workflow tests.
- Docs.

**Forbidden:**

- No silent real publish.
- No background real upload/post.
- No automatic comment/reply execution.
- No migration of existing AutoTask authorization without explicit user decision.

**Steps:**

- [x] Step 1: Document current AutoTask fields and XHS-specific assumptions.
- [x] Step 2: Define workflow types and payload schema skeleton.
- [x] Step 3: Write tests for schedule calculation preservation.
- [x] Step 4: Write tests that real publish workflow requires explicit authorization ref.
- [x] Step 5: Add workflow service skeleton with pure definitions/plans only; no fake execution runner was added in this first safety pass.
- [x] Step 6: Keep `/auto-tasks` API behavior unchanged; `/auto-tasks` was not modified or migrated.
- [x] Step 7: Add scheduler no-bypass test and gate background AutoTask runner so it creates pending publish jobs/assets only, without silent upload/post.
- [x] Step 8: Prevent queued-only background jobs from incrementing `total_published`, so pending publish jobs are not reported as real published output.

**Stage 8 first scoped pass evidence:**

- Added pure `backend/app/services/workflow_automation_service.py` with frozen dataclass contracts for workflow steps, definitions, schedules, risk policy, and legacy XHS AutoTask plan mapping.
- Added `tests/backend/test_workflow_automation_core.py` coverage for supported workflow types, exclusion of reply execution, legacy XHS account/payload mapping, fail-closed real publish authorization, manual/daily/weekly/interval schedule calculation, background AutoTask no-bypass behavior, and prevention of `total_published` increments for queued-only jobs.
- Legacy XHS AutoTask maps to `auto_ops_legacy_skeleton` with `real_publish_authorized=false`, no `authorization_ref`, and a blocked `publish.real_publish` step; historical AutoTasks do not gain publishing privileges.
- Updated `backend/app/services/scheduler_service.py` background AutoTask execution to stop before real Creator upload/post: it now creates a `pending` `PublishJob` and `pending` `PublishAsset` rows only. Real publish remains behind the publish center confirmation path.
- The background AutoTask runner still updates `last_run_at`, but no longer increments `total_published` because it has only queued a publish job, not published content.
- Did not modify `backend/app/api/auto_tasks.py`, `backend/app/models/auto_task.py`, Alembic/database files, SDK/signature layers, frontend, or any real platform/provider execution path.

Verification evidence from first scoped pass:

- RED: `cd /e/小红书 && py -3 -m pytest tests/backend/test_workflow_automation_core.py -q` failed during collection with `ModuleNotFoundError: No module named 'backend.app.services.workflow_automation_service'` before implementation.
- Scheduler no-bypass RED: after adding the no-bypass test, `cd /e/小红书 && py -3 -m pytest tests/backend/test_workflow_automation_core.py -q` failed because `_execute_auto_task_background` still contained `creator_adapter.upload_media`.
- Counter semantics RED: after extending the no-bypass test, `cd /e/小红书 && py -3 -m pytest tests/backend/test_workflow_automation_core.py -q` failed because `_execute_auto_task_background` still contained `task.total_published`.
- GREEN: `cd /e/小红书 && py -3 -m pytest tests/backend/test_workflow_automation_core.py -q` -> `6 passed in 0.02s`.
- Focused scheduler/API regression: `cd /e/小红书 && py -3 -m pytest tests/backend/test_api.py -q -k "auto_tasks or scheduler"` -> `3 passed, 157 deselected in 3.28s`.

**Verification:**

```bash
py -3 -m pytest tests/backend/test_auto_tasks.py -q
```

or focused new workflow test command.

```bash
git diff --check
```

**Review gate:**

- PASS if workflow skeleton reduces future duplication without changing current automation semantics.
- BLOCKER if historical AutoTasks gain new real publish privileges.

---

## Stage 9: Diagnostics / Notification / Audit standardization

**Goal:** 建立跨平台统一诊断、通知、审计事件格式，让 adapter/result 错误能被用户理解。

**Allowed files candidate set:**

- `backend/app/models/api_log.py`
- `backend/app/api/notifications.py`
- `backend/app/platforms/contracts.py`
- New service: `backend/app/services/diagnostic_service.py`
- Tests for diagnostic serialization.
- Frontend types if needed.

**Forbidden:**

- No sensitive raw payload exposure.
- No plaintext credentials in diagnostics.
- No broad database migration without separate plan.

**Steps:**

- [x] Step 1: Define diagnostic categories and standard user messages.
- [x] Step 2: Add serializer tests for auth_expired/rate_limited/signature_failed/risk_blocked/validation.
- [x] Step 3: Ensure raw_reference is a reference, not raw secret-bearing payload.
- [x] Step 4: Wire one low-risk path as example, preferably fake adapter or dry-run result.
- [x] Step 5: Document next-action guidance for user-facing messages.

**Stage 9 first scoped pass evidence:**

- Added pure `backend/app/services/diagnostic_service.py` with `StandardDiagnostic` payload shape: `platform_id`, `capability_key`, `stage`, `severity`, `recoverable`, `category`, `user_message`, `next_action`, `raw_reference`, `correlation_id`.
- Standardized first diagnostic categories: `auth_expired`, `rate_limited`, `signature_failed`, `risk_blocked`, `validation`, plus fail-safe `unknown` fallback.
- Added `sanitize_raw_reference()` as a reference whitelist: only `api_log:`, `audit:`, `task:`, `diagnostic:` references and safe `http`/`https` URL scheme/host/path survive; dict/raw payloads, JSON-looking strings, `raw_json`, `platform_message`, secret-bearing strings, URL query tokens, URL userinfo, unsafe URL schemes, and secret-bearing URL paths are dropped.
- Added `tests/backend/test_diagnostics.py` for category guidance, raw reference sanitization, adapter error mapping, capability decision mapping, validation diagnostics, and publish dry-run diagnostics integration.
- Wired `PublishOrchestrationService.dry_run` as the low-risk example path: existing `checks` and `policy` fields are preserved, successful dry-run has no diagnostics, blocked/warning checks add diagnostics with next-action guidance.
- Did not modify `backend/app/models/api_log.py`, `backend/app/api/notifications.py`, notification table/model, Alembic/database files, frontend types, SDK/signature layers, or any real provider/platform execution path.

Verification evidence from first scoped pass:

- RED: `cd /e/小红书 && py -3 -m pytest tests/backend/test_diagnostics.py -q` failed during collection with `ModuleNotFoundError: No module named 'backend.app.services.diagnostic_service'` before implementation.
- Contract RED: after asserting successful publish dry-run should not emit diagnostics, `cd /e/小红书 && py -3 -m pytest tests/backend/test_publish_orchestration_contract.py::test_xhs_dry_run_validates_local_state_without_upload_or_post -q` failed because an allowed policy decision emitted an `unknown` diagnostic.
- GREEN: `cd /e/小红书 && py -3 -m pytest tests/backend/test_diagnostics.py tests/backend/test_publish_orchestration_contract.py -q` -> `10 passed in 6.93s`.
- Focused publish/notification regression: `cd /e/小红书 && py -3 -m pytest tests/backend/test_api.py -q -k "publish or notifications"` -> `26 passed, 134 deselected, 5 warnings in 31.62s`.

**Verification:**

```bash
py -3 -m pytest tests/backend/test_diagnostics.py -q
```

```bash
git diff --check
```

**Review gate:**

- PASS if diagnostics improve user recovery without leaking secrets.
- BLOCKER if raw_json/logs can contain credentials or platform private tokens.

---

## Stage 10: Second platform readiness gate

**Goal:** 在接真实第二平台前，做一次 readiness review。只有通过后，才允许选抖音/视频号/公众号等平台做最小 adapter 验证。

**Preconditions:**

- Stage 1 hardcode inventory exists.
- Draft Workbench is canonical adapter UI sample.
- Content Library shell/adapter path exists or has accepted deferral.
- Capability Policy/resolver tests pass.
- Publish dry-run no-side-effect skeleton exists before any real publish work.
- No-bypass rule for scheduler/auto task/retry is documented or tested.

**Review checklist:**

- [x] 新平台能否只通过 registry + adapter + normalizer 接入一个最小 read-only feature？
- [x] 是否还有必须复制 XHS 页面才能工作的 core feature？
- [x] 是否存在真实动作绕过 CapabilityPolicy？
- [x] 是否存在明文凭据可能进入日志/诊断/前端？
- [x] 是否有清晰的 planned/beta/enabled 发布策略？
- [x] 是否有 rollback/disable 平台能力的方法？

**Stage 10 first scoped pass evidence:**

- Added pure `backend/app/services/platform_readiness_service.py` with `CoreReadinessSnapshot`, `ReadinessCheck`, `ReadinessReport`, and `evaluate_second_platform_readiness()`.
- Readiness gate compresses Platform Operating Core into ten auditable checks: registry, read-only adapter path, shared content shell/deferral, Capability Policy, publish dry-run no-side-effect, scheduler no-bypass, diagnostics no-secret-leak, credential logging safety, real publish confirmation, and disable/rollback path.
- High-risk gaps become `BLOCKER` and return `do_not_connect_real_platform`; lower-risk missing adapter/UI/rollback readiness becomes `FOLLOW_UP` and returns `docs_or_fake_adapter_only`; all checks passing returns `PASS` and `start_read_only_adapter_pilot`.
- Added `tests/backend/test_platform_readiness_gate.py` for PASS, FOLLOW_UP, BLOCKER, user impact/next action guidance, and exact check contract.
- Did not connect any real second platform, did not modify registry, API routes, frontend, database/Alembic, SDK/signature layers, credentials, publish execution, scheduler, or notifications.

Verification evidence from first scoped pass:

- RED: `cd /e/小红书 && py -3 -m pytest tests/backend/test_platform_readiness_gate.py -q` failed during collection with `ModuleNotFoundError: No module named 'backend.app.services.platform_readiness_service'` before implementation.
- GREEN: `cd /e/小红书 && py -3 -m pytest tests/backend/test_platform_readiness_gate.py -q` -> `5 passed in 0.02s`.

**Allowed outcome:**

- PASS: 开始第二平台 read-only adapter pilot。
- FOLLOW-UP: 记录缺口，限制第二平台只做 docs/fake adapter。
- BLOCKER: 不允许接真实平台，先修 core。

---

## Current Closure Queue — 2026-06-30

Stage 0-10 have all received at least a first scoped pass, so the active work is no longer the original numeric stage sequence. Continue with closure passes: one auditable gap at a time, each with its own scope firewall, focused verification, review gate, and scoped commit.

### Status model

| Status | Meaning |
|---|---|
| `closed` | Current planned scope is complete; any remaining work is explicitly deferred. |
| `first_pass_done` | A skeleton or low-risk first step exists, but adoption is incomplete. |
| `closure_in_progress` | Follow-up closure passes are actively reducing known gaps. |
| `deferred_by_safety` | Further work touches real accounts, real publish, providers, or background automation and needs a separate risk/QA decision. |

### Current stage status

| Area | Status | Evidence |
|---|---|---|
| Stage 0 design/spec baseline | `closed` | `1bcd732 feat: add platform operating core` |
| Stage 1 hardcode inventory/checklist | `closed` | `docs/superpowers/specs/2026-06-20-platform-operating-core-hardcode-inventory.md` |
| Stage 2 Draft Workbench standardization | `closed` | `4708275 feat: add shared draft workbench` and Stage 2 evidence above |
| Stage 3 Content Library frontend shell | `closed` | `dce3270 feat: reuse shared content library for wechat official` and Stage 3 evidence above |
| Frontend Platform Core shell pass | `closed` | `84379ef feat: introduce shared platform core shell` |
| Stage 4 backend content normalizer | `closed` | `91c582b refactor: route xhs note serialization through mapper`; `379f57f refactor: extract xhs comment mapper`; `62e151b refactor: make notes account platform explicit`; WeChat Official ContentLibraryItem mapper tested; remaining cross-platform ingestion/database unification deferred |
| Stage 5 Account Matrix auth schema | `closure_in_progress` | local frontend `account-auth-schema` exists; `0add4fd feat: expose platform account auth schemas`; frontend adoption remains |
| Stage 6 Asset storage policy | `first_pass_done` | `asset_storage_policy` first pass evidence above; wider adoption remains |
| Stage 7 Publish Queue policy/dry-run | `first_pass_done` | dry-run no-side-effect skeleton evidence above; real publish migration is safety-gated |
| Stage 8 Workflow Automation | `first_pass_done` | workflow skeleton/no-bypass evidence above; deeper automation migration is safety-gated |
| Stage 9 Diagnostics | `first_pass_done` | diagnostic service first pass evidence above; broader low-risk adoption remains |
| Stage 10 Second Platform Readiness Gate | `closure_in_progress` | readiness service/tests evidence above; current 2026-06-30 report verdict is `FOLLOW_UP` / `docs_or_fake_adapter_only` |

### Wave 1 — approved low-risk closure sequence

| Order | Closure pass | Source | Goal | Risk | Verification floor |
|---|---|---|---|---|---|
| 0 | Closure queue checkpoint | planning hygiene | Keep this file as the recovery source of truth for continuous execution | Low | `git diff --check -- docs/superpowers/plans/2026-06-20-platform-operating-core.md` |
| 1 | XHS comment mapper extraction preflight/implementation | Stage 4 / HC-10 | Move pure XHS comment payload normalization out of route-private helpers while preserving route/API behavior | Medium | focused comment mapper tests + existing comments/notes API tests |
| 2 | Notes account platform expectation | Stage 4 / HC-01 | Make `_get_owned_account` expected platform explicit while preserving current XHS-only route behavior | Medium | notes account ownership tests + batch-save regression |
| 3 | Read-only backend account auth schema | Stage 5 / HC-19 to HC-22 | Expose platform account auth schema from registry without changing real login endpoints or credential storage | Medium | platform registry tests + frontend build if types change |
| 4 | Current readiness gate report | Stage 10 | Run/record current Platform Core readiness result as PASS/FOLLOW_UP/BLOCKER before real second-platform work | Low | readiness tests + docs diff check |

### Wave 1 execution checkpoint — 2026-06-30

| Order | Result | Evidence | Remaining boundary |
|---|---|---|---|
| 0 | Done | `cffe4ee docs: define platform core closure queue`; `git diff --check -- docs/superpowers/plans/2026-06-20-platform-operating-core.md` | Worktree branch only; not merged to root `master`. |
| 1 | Done | `379f57f refactor: extract xhs comment mapper`; `py -3.12 -m pytest tests/backend/test_xhs_content_mappers.py tests/backend/test_notes_xhs_serializer.py -q` -> 14 passed; comment API regression subset -> 8 passed | Other XHS route-private helpers remain out of scope. |
| 2 | Done | `62e151b refactor: make notes account platform explicit`; ownership/serializer tests -> 8 passed; batch-save ownership subset -> 3 passed | `/notes/batch-save` remains intentionally XHS-only. |
| 3 | Done | `0add4fd feat: expose platform account auth schemas`; `py -3.12 -m pytest tests/backend/test_platforms.py -q` -> 10 passed; account/platform API subset -> 29 passed | Schema is read-only; no real login endpoint or credential storage behavior changed. |
| 4 | `FOLLOW_UP` | `py -3.12 -m pytest tests/backend/test_platform_readiness_gate.py tests/backend/test_platforms.py -q` -> 15 passed | Allowed outcome is `docs_or_fake_adapter_only`; do not connect real second-platform accounts or real publish paths yet. |

**Current readiness verdict:** `FOLLOW_UP`.

**Allowed outcome:** `docs_or_fake_adapter_only`.

**Why not PASS:** blocker-class safety checks have test coverage, but second-platform read-only adapter/content-library adoption is still incomplete and公众号 account binding remains blocked by design. Starting real account binding, real provider calls, real publish, or automated engagement is still outside the safe closure boundary.

**User impact:** users can see clearer platform/account capability state, but should not be offered a working公众号 credential binding flow or any real second-platform write action until the Wave 2 design/adoption work is complete.

### Wave 2 — after Wave 1 review

| Closure pass | Source | Goal | Risk note |
|---|---|---|---|
| WeChat Article -> ContentItem mapping design | Stage 4 / HC-31 | Specify how公众号 raw articles enter the shared Content Library operating layer | Design-only before implementation |
| Asset policy wider adoption | Stage 6 / HC-11 to HC-14 | Expand platform-aware asset policy across remaining low-risk file/export paths | Do not migrate/delete existing files |
| Diagnostics low-risk adoption | Stage 9 | Attach standardized diagnostics to more read-only or dry-run paths | No raw secret-bearing payloads |

### Wave 3 — explicit safety gate required

| Closure pass | Source | Why gated |
|---|---|---|
| Publish Queue deeper migration | Stage 7 / HC-02, HC-04, HC-24, HC-26, HC-27 | Touches real publish/upload semantics; requires separate risk and QA decision |
| Workflow Automation deeper migration | Stage 8 / HC-05 to HC-07 | Touches background automation; must not create silent real publish/comment behavior |

### Continuous execution rules

- Execute one closure pass per commit.
- Use a clean worktree for continuous closure work; commits on a worktree branch do not automatically merge to root `master`.
- Keep real provider calls, real account actions, deploys, pushes, service restarts, and real publish out of closure passes unless separately authorized.
- For each closure pass: write or update focused tests first, implement the smallest change, run focused verification, run a spec review and quality review, update this queue if status changes, then make a scoped commit.
- If a closure pass touches a mixed or dirty file, stage explicit hunks only; never use `git add .` or `git add -A`.

---

## Evidence Ledger Template

每个阶段结束时报告：

```md
Evidence Ledger — Platform Operating Core Stage <N>

Stage contract:
- <goal / non-goals / allowed files / forbidden files>

Changed files:
- <paths>

Verification:
- `<command>` -> <result>

Review:
- <review agent verdict: PASS / BLOCKER / FOLLOW-UP>
- <blockers fixed or follow-ups recorded>

Boundaries:
- <forbidden areas not touched>
- <real providers / real publish / real accounts not tested>

Next:
- <recommended next exact stage>
```

# Platform Operating Core Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the remaining low-risk Platform Operating Core closure passes as a continuous queue, then stop at explicit safety gates for real publish/workflow automation work.

**Architecture:** Execute closure by risk batch rather than original stage number. Batch 1 closes registry/schema/policy/diagnostic/mapper adoption gaps. Batch 2 proves the core with a fake/read-only second-platform pilot and reruns readiness. Batch 3 records design-only safety gates for publish/workflow deeper migration; it does not implement real external actions.

**Tech Stack:** Python 3.10+/3.12, FastAPI, SQLAlchemy, pytest, React, Vite, TypeScript, Ant Design.

---

## Scope Firewall

### Current workspace baseline

Before starting any task, run:

```powershell
git -C "E:\小红书" branch --show-current
git -C "E:\小红书" status --short
```

Expected current root branch:

```text
master
```

Known unrelated item that must remain untouched:

```text
?? compare-shots/
```

### Stop list: explicit user authorization required

Do not perform these actions during Batch 1 or Batch 2:

- Real account binding or login flow changes.
- Real provider/API calls outside local tests.
- Real publish, upload, preview send, group-send, comment, reply, or engagement action.
- Background automation that can mutate external platforms.
- Database schema migration or data migration.
- Deleting, moving, or rewriting existing user media/export files.
- Stopping/restarting root standard services.
- Push, deployment, PR creation.
- Broad cleanup outside the scoped pass.

### Commit rules

- One task/pass per commit.
- Stage only explicit scoped files.
- Never use `git add .` or `git add -A`.
- Commit messages are in English.
- End commit messages with:

```text
Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
```

---

## File Structure

### Existing files to modify across the program

- `docs/superpowers/plans/2026-07-01-platform-operating-core-completion.md` — this execution queue and per-pass evidence ledger.
- `docs/superpowers/plans/2026-06-20-platform-operating-core.md` — original closure queue; update only when status changes should remain visible to older sessions.
- `frontend/src/types/index.ts` — add frontend type coverage for backend `account_auth_schemas` and optional dev/demo platform metadata when needed.
- `frontend/src/components/account/account-auth-schema.ts` — keep local fallback schema and add backend-schema-to-drawer-schema mapping helpers.
- `frontend/src/components/account/add-account-drawer.tsx` — consume registry-derived schemas while preserving existing XHS/Huitun behavior.
- `frontend/src/lib/api.ts` — use existing `fetchPlatforms()` for registry data; add a narrowly scoped helper only if needed.
- `backend/app/services/asset_storage_policy.py` — extend only if a remaining low-risk asset/export owner kind is missing.
- `backend/app/api/files.py`, `backend/app/services/asset_downloader.py`, `backend/app/services/ai_service.py` — already partially adopted; only touch if focused tests show a remaining generic owner path.
- `backend/app/services/diagnostic_service.py` — existing standard diagnostic service; extend only with concrete low-risk categories/helpers required by tests.
- `backend/app/api/platforms/xhs/crawl.py` or related low-risk read-only/dry-run routes — attach additive diagnostics only where response shape can safely accept metadata.
- `backend/app/services/platform_readiness_service.py` — rerun/update readiness checks after fake/read-only pilot.
- `backend/app/core/platforms.py` — add test/dev-only fake platform metadata only if the selected implementation uses backend registry for the fake pilot.
- `frontend/src/platform-core/registry/platform-sections.tsx` — add fake/demo platform sections only for dev/test pilot and fail-closed actions.
- `frontend/src/pages/demo-platform/*` or `frontend/src/pages/platforms/demo/*` — fake/read-only platform page/adapter files if frontend pilot is implemented.

### New test files likely needed

- `frontend/tests/account-auth-schema.test.ts` — pure mapper/fallback tests for account auth schema adoption.
- `tests/backend/test_asset_storage_policy.py` — extend existing tests; create new tests only if the current file is not sufficient.
- `tests/backend/test_diagnostics.py` — extend existing diagnostics tests for new low-risk adoption.
- `frontend/tests/demo-platform-content-library-adapter.test.ts` — fake/read-only ContentLibrary adapter contract tests if frontend pilot adds a new adapter.
- `tests/backend/test_platform_readiness_gate.py` — extend existing readiness tests for fake/read-only pilot outcome.

---

## Batch 1: Core Closure

### Task 1: Account auth schema frontend adoption

**Goal:** Make the account drawer derive available account/login choices from backend platform registry schema when available, while keeping local fallback and preserving existing behavior.

**Files:**

- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/components/account/account-auth-schema.ts`
- Modify: `frontend/src/components/account/add-account-drawer.tsx`
- Modify if needed: `frontend/src/lib/api.ts`
- Create: `frontend/tests/account-auth-schema.test.ts`
- Modify: `docs/superpowers/plans/2026-07-01-platform-operating-core-completion.md`
- Modify optional: `docs/superpowers/plans/2026-06-20-platform-operating-core.md`

- [x] **Step 1: Write the failing pure mapper test**

Create `frontend/tests/account-auth-schema.test.ts` with this initial coverage:

```ts
import assert from "node:assert/strict";

import {
  accountDrawerTitleFor,
  accountTypeOptionsFor,
  getAccountAuthSchema,
  getDefaultAccountType,
  getDefaultLoginMethod,
  loginMethodOptionsFor,
  mapPlatformRegistryToAccountAuthSchemas,
  platformOptionsFor,
} from "../src/components/account/account-auth-schema.ts";
import type { PlatformMeta } from "../src/types/index.ts";

const registryPlatforms: PlatformMeta[] = [
  {
    id: "xhs",
    name_cn: "小红书",
    name_en: "Xiaohongshu",
    enabled: true,
    status: "enabled",
    release_stage: "enabled",
    region: "cn",
    platform_type: "hybrid",
    default_route: "/platforms/xhs/dashboard",
    adapter_key: "xhs",
    risk_level: "high",
    auth_modes: ["cookie", "qr_login"],
    capabilities: [],
    accent_color: "#ff2442",
    icon: "xhs",
    account_auth_schemas: [
      {
        key: "xhs-pc-cookie",
        label: "小红书 PC Cookie 导入",
        auth_mode: "cookie",
        account_kind: "pc",
        status: "available",
        requires_secret: true,
        requires_user_action: true,
        notes: "沿用现有账号矩阵 Cookie 导入路径。",
      },
      {
        key: "xhs-qr-login",
        label: "小红书扫码登录",
        auth_mode: "qr_login",
        account_kind: "pc",
        status: "available",
        requires_secret: false,
        requires_user_action: true,
        notes: "沿用现有扫码登录路径。",
      },
    ],
  },
  {
    id: "wechat_official",
    name_cn: "公众号",
    name_en: "WeChat Official Account",
    enabled: true,
    status: "beta",
    release_stage: "beta",
    region: "cn",
    platform_type: "content",
    default_route: "/platforms/wechat-official/library",
    adapter_key: "wechat_official",
    risk_level: "medium",
    auth_modes: ["none"],
    capabilities: [],
    accent_color: "#07c160",
    icon: "wechat",
    account_auth_schemas: [
      {
        key: "wechat-official-account-binding",
        label: "公众号账号绑定",
        auth_mode: "none",
        account_kind: "main",
        status: "blocked",
        requires_secret: false,
        requires_user_action: false,
        notes: "真实授权和发布动作仍保持阻断。",
      },
    ],
  },
];

const schemas = mapPlatformRegistryToAccountAuthSchemas(registryPlatforms);
assert.equal(schemas.length, 2);
assert.equal(schemas[0].platform, "xhs");
assert.deepEqual(accountTypeOptionsFor(schemas[0]).map((option) => option.value), ["pc"]);
assert.deepEqual(loginMethodOptionsFor(schemas[0]).map((option) => option.value), ["cookie", "qr"]);
assert.equal(getDefaultAccountType(schemas[0]), "pc");
assert.equal(getDefaultLoginMethod(schemas[0]), "cookie");
assert.equal(schemas[1].platform, "wechat_official");
assert.equal(schemas[1].loginMethods[0].value, "none");
assert.equal(schemas[1].loginMethods[0].disabled, true);
assert.match(schemas[1].loginMethods[0].description || "", /阻断|blocked|不可用|未开放/);
assert.equal(accountDrawerTitleFor(schemas), "添加小红书 / 公众号账号");
assert.deepEqual(platformOptionsFor(schemas).map((option) => option.value), ["xhs", "wechat_official"]);

const fallback = getAccountAuthSchema("xhs");
assert.deepEqual(accountTypeOptionsFor(fallback).map((option) => option.value), ["pc", "creator"]);
assert.deepEqual(loginMethodOptionsFor(fallback).map((option) => option.value), ["qr", "phone", "cookie"]);
assert.equal(getDefaultLoginMethod(fallback, "phone"), "phone");

console.log("account-auth-schema tests passed");
```

- [x] **Step 2: Run the failing test**

Run:

```powershell
node frontend/tests/account-auth-schema.test.ts
```

Expected: fail because `mapPlatformRegistryToAccountAuthSchemas` does not exist and `PlatformMeta` has no `account_auth_schemas` type.

- [x] **Step 3: Add frontend registry schema types**

Modify `frontend/src/types/index.ts`:

```ts
export type PlatformAccountAuthSchema = {
  key: string;
  label: string;
  auth_mode: "cookie" | "qr_login" | "phone" | "none" | string;
  account_kind: "pc" | "creator" | "main" | string;
  status: PlatformCapabilityStatus;
  requires_secret: boolean;
  requires_user_action: boolean;
  notes: string;
};
```

Then add to `PlatformMeta`:

```ts
  account_auth_schemas?: PlatformAccountAuthSchema[];
```

- [x] **Step 4: Extend account auth schema helper types and mapper**

Modify `frontend/src/components/account/account-auth-schema.ts` so the public types include WeChat Official and disabled metadata:

```ts
export type AccountPlatform = "xhs" | "huitun" | "wechat_official";
export type AccountType = "pc" | "creator" | "main";
export type LoginMethod = "qr" | "phone" | "cookie" | "none";

export type AccountAuthOption<T extends string> = {
  label: string;
  value: T;
  disabled?: boolean;
  description?: string;
};
```

Add imports:

```ts
import type { PlatformAccountAuthSchema, PlatformMeta } from "../../types";
```

Add mapper helpers:

```ts
function mapAuthMode(authMode: string): LoginMethod {
  if (authMode === "qr_login") return "qr";
  if (authMode === "cookie" || authMode === "phone" || authMode === "none") return authMode;
  return "none";
}

function mapAccountKind(accountKind: string): AccountType {
  if (accountKind === "pc" || accountKind === "creator" || accountKind === "main") return accountKind;
  return "main";
}

function uniqueOptions<T extends string>(options: AccountAuthOption<T>[]): AccountAuthOption<T>[] {
  return options.filter((option, index, list) => list.findIndex((candidate) => candidate.value === option.value) === index);
}

function schemaStatusDisabled(schema: PlatformAccountAuthSchema): boolean {
  return schema.status === "blocked" || schema.status === "planned";
}

export function mapPlatformRegistryToAccountAuthSchemas(platforms: PlatformMeta[]): AccountAuthSchema[] {
  const mapped = platforms
    .filter((platform) => platform.account_auth_schemas?.length)
    .map((platform) => {
      const accountSchemas = platform.account_auth_schemas || [];
      const accountTypes = uniqueOptions(
        accountSchemas.map((schema) => ({
          label: mapAccountKind(schema.account_kind) === "main" ? "主账号" : mapAccountKind(schema.account_kind) === "creator" ? "Creator" : "PC",
          value: mapAccountKind(schema.account_kind),
          disabled: schemaStatusDisabled(schema),
          description: schema.notes,
        })),
      );
      const loginMethods = uniqueOptions(
        accountSchemas.map((schema) => ({
          label: schema.auth_mode === "qr_login" ? "二维码" : schema.auth_mode === "phone" ? "手机验证码" : schema.auth_mode === "cookie" ? "Cookie" : schema.label,
          value: mapAuthMode(schema.auth_mode),
          disabled: schemaStatusDisabled(schema) || schema.auth_mode === "none",
          description: schema.notes,
        })),
      );
      return {
        platform: platform.id as AccountPlatform,
        label: platform.name_cn,
        drawerTitle: `添加${platform.name_cn}账号`,
        defaultAccountType: accountTypes.find((option) => !option.disabled)?.value ?? accountTypes[0]?.value ?? "main",
        accountTypes: accountTypes.length ? accountTypes : [{ label: "主账号", value: "main", disabled: true, description: "账号绑定未开放" }],
        loginMethods: loginMethods.length ? loginMethods : [{ label: "账号绑定未开放", value: "none", disabled: true, description: "账号绑定未开放" }],
        accountTypeSelectorVisible: accountTypes.filter((option) => !option.disabled).length > 1,
      } satisfies AccountAuthSchema;
    });
  return mapped.length ? mapped : [...accountAuthSchemas];
}
```

Keep the existing local `accountAuthSchemas` fallback, including XHS and Huitun behavior.

- [x] **Step 5: Make AddAccountDrawer accept registry schemas without changing login endpoints**

Modify `frontend/src/components/account/add-account-drawer.tsx`:

- Add optional prop:

```ts
schemas?: readonly AccountAuthSchema[];
```

- Replace module-level constants with per-render values:

```ts
const availableSchemas = schemas?.length ? schemas : accountAuthSchemas;
const platformOptions = platformOptionsFor(availableSchemas);
const drawerTitle = accountDrawerTitleFor(availableSchemas);
```

- Replace calls to `getAccountAuthSchema(platform)` with `getAccountAuthSchema(platform, availableSchemas)` after changing helper signature:

```ts
export function getAccountAuthSchema(platform: AccountPlatform, schemas: readonly AccountAuthSchema[] = accountAuthSchemas): AccountAuthSchema {
  return schemas.find((schema) => schema.platform === platform) ?? schemas[0] ?? accountAuthSchemas[0];
}
```

- When `effectiveMethod === "none"` or selected login method is disabled, render an `Alert` explaining that account binding is not open and do not render QR/phone/cookie panels.

Do not change QR, phone, or cookie panel API calls.

- [x] **Step 6: Run tests and build**

Run:

```powershell
node frontend/tests/account-auth-schema.test.ts
npm --prefix frontend run build
```

Expected:

```text
account-auth-schema tests passed
```

and frontend build exits 0.

- [x] **Step 7: Update completion plan status**

In this file, under this task, add an evidence entry after implementation:

```md
**Task 1 evidence:**
- Commit: actual commit SHA `feat: adopt platform account auth schema in frontend`
- Tests: `node frontend/tests/account-auth-schema.test.ts` -> passed
- Build: `npm --prefix frontend run build` -> passed
- Boundary: no real login endpoint, credential storage, provider call, or account binding behavior changed.
```

**Task 1 evidence:**
- Commit: `14fed63780ba54c5979ae57ab3d2fcb9875200be` `feat: adopt platform account auth schema in frontend`.
- Tests: `node frontend/tests/account-auth-schema.test.ts` -> passed (`account-auth-schema tests passed`).
- Build: `npm --prefix frontend run build` -> passed after temporarily linking the worktree `frontend/node_modules` junction to the root dependency directory; the junction was removed after build.
- User impact: account binding choices are now registry-driven when the backend registry is reachable, while the local XHS/Huitun fallback keeps the drawer usable offline.
- Boundary: no real login endpoint, credential storage, provider call, account binding execution, root service restart, Alembic/migration, or `compare-shots/` change occurred.

- [x] **Step 8: Commit scoped files**

Run:

```powershell
git -C "E:\小红书" add -- frontend/src/types/index.ts frontend/src/components/account/account-auth-schema.ts frontend/src/components/account/add-account-drawer.tsx frontend/tests/account-auth-schema.test.ts docs/superpowers/plans/2026-07-01-platform-operating-core-completion.md
git -C "E:\小红书" commit -m @'
feat: adopt platform account auth schema in frontend

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
'@
```

Do not stage `compare-shots/`.

---

### Task 2: Asset policy wider adoption

**Goal:** Close low-risk asset/export owner naming gaps while preserving all existing files and XHS-specific business artifacts.

**Files:**

- Modify if needed: `backend/app/services/asset_storage_policy.py`
- Modify if needed: `backend/app/api/files.py`
- Modify if needed: `backend/app/services/asset_downloader.py`
- Modify if needed: `backend/app/services/ai_service.py`
- Modify if needed: `backend/app/services/wechat_official_content_service.py`
- Modify tests: `tests/backend/test_asset_storage_policy.py`
- Modify tests if route touched: `tests/backend/test_api.py`
- Modify docs: `docs/superpowers/plans/2026-07-01-platform-operating-core-completion.md`

- [x] **Step 1: Inventory remaining XHS filename assumptions**

Run:

```powershell
git -C "E:\小红书" grep -n "xhs-" -- backend/app tests/backend
```

Classify each result into one of these categories in a short note inside this task's evidence section:

```md
Asset policy inventory:
- Keep XHS-specific: `actual/path.py:123` — reason.
- Generic owner policy candidate: `actual/path.py:123` — target helper.
```

Do not edit code before this classification.

- [x] **Step 2: Write failing tests only for generic owner policy candidates**

Extend `tests/backend/test_asset_storage_policy.py` with tests like:

```python
from backend.app.services.asset_storage_policy import (
    asset_owner_prefix,
    export_owner_prefix,
    validate_owned_export_file_name,
    validate_owned_media_file_name,
)


def test_wechat_official_user_owned_media_prefix_is_validated():
    name = f"{asset_owner_prefix('wechat_official', 'asset', 7)}abc123.jpg"
    assert validate_owned_media_file_name(name, 7) == name


def test_wechat_official_user_owned_export_prefix_is_validated():
    name = f"{export_owner_prefix('wechat_official', 'articles', 7)}20260701120000.csv"
    assert validate_owned_export_file_name(name, 7) == name


def test_existing_xhs_export_prefix_stays_valid():
    name = f"{export_owner_prefix('xhs', 'notes', 7)}20260701120000.csv"
    assert validate_owned_export_file_name(name, 7) == name
```

If these tests already pass with current policy, do not force code changes. The closure may be documentation/evidence-only.

- [x] **Step 3: Run focused asset tests**

Run:

```powershell
py -3.12 -m pytest tests/backend/test_asset_storage_policy.py -q
```

Expected before implementation: fail only if a real generic owner kind/platform gap exists. If it passes, proceed to Step 5 and record that no low-risk code change is needed.

- [x] **Step 4: Implement minimal helper extension only if tests fail**

If an owner kind is missing, update `backend/app/services/asset_storage_policy.py` by adding the minimum kind to the correct allowlist. For example, if `articles` export is missing:

```python
EXPORT_OWNER_KINDS = frozenset({"notes", "analysis", "articles"})
```

Do not widen validation to arbitrary strings. Do not accept subdirectories. Do not migrate files.

- [x] **Step 5: Run focused route regressions**

Run:

```powershell
py -3.12 -m pytest tests/backend/test_asset_storage_policy.py -q
py -3.12 -m pytest tests/backend/test_api.py -q -k "file or image or export"
```

Expected: all selected tests pass. If `test_api.py` exposes an unrelated failure in a dirty or out-of-scope file, report it and keep this task scoped.

- [x] **Step 6: Update completion plan status**

Add evidence:

```md
**Task 2 evidence:**
- Commit: `actual commit SHA` `refactor: widen platform asset owner policy`
- Inventory: the concrete inventory summary written in this task
- Tests: `py -3.12 -m pytest tests/backend/test_asset_storage_policy.py -q` -> passed
- Regression: `py -3.12 -m pytest tests/backend/test_api.py -q -k "file or image or export"` -> passed or scoped exception documented
- Boundary: no file migration, deletion, rename, storage layout rewrite, provider call, or SDK/signature change.
```

**Task 2 evidence:**
- Commit: current scoped Task 2 commit (`refactor: widen platform asset owner policy`); final SHA is reported in Task 2 closeout.
- Inventory: `backend/app/api/notes.py:869` and `backend/app/api/platforms/xhs/analytics.py:340` were generic user-owned export filenames still hand-building `xhs-notes` / `xhs-report`; routed both through `export_owner_prefix('xhs', ...)`. Existing XHS-specific routes, Feishu attachment names, XHS analysis report HTML names, platform route prefixes, test fixture note IDs, and existing media/export compatibility assertions stay intentionally XHS-specific.
- Tests: `py -3.12 -m pytest tests/backend/test_asset_storage_policy.py -q` -> passed (`16 passed`).
- Regression: `py -3.12 -m pytest tests/backend/test_api.py -q -k "file or image or export"` -> passed (`27 passed, 169 deselected`).
- Boundary: no file migration, deletion, rename, storage layout rewrite, provider call, SDK/signature change, Alembic/migration, root service restart, or `compare-shots/` change occurred.

- [x] **Step 7: Commit scoped files**

Stage only files touched in this task, for example:

```powershell
git -C "E:\小红书" add -- backend/app/services/asset_storage_policy.py tests/backend/test_asset_storage_policy.py docs/superpowers/plans/2026-07-01-platform-operating-core-completion.md
git -C "E:\小红书" commit -m @'
refactor: widen platform asset owner policy

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
'@
```

If no production code changed, use:

```text
docs: record asset policy closure evidence
```

---

### Task 3: Diagnostics low-risk adoption

**Goal:** Attach standardized diagnostics to selected low-risk read-only/dry-run paths without leaking secrets or changing existing response fields.

**Files:**

- Modify: `backend/app/services/diagnostic_service.py` only if helper coverage requires it.
- Modify candidate: `backend/app/api/platforms/xhs/crawl.py`
- Modify candidate: `backend/app/services/platform_readiness_service.py`
- Modify tests: `tests/backend/test_diagnostics.py`
- Modify tests if route touched: `tests/backend/test_api.py`
- Modify docs: `docs/superpowers/plans/2026-07-01-platform-operating-core-completion.md`

- [x] **Step 1: Select low-risk diagnostic adoption points**

Use this exact selection unless code investigation shows a better low-risk fit:

1. Platform readiness report serialization: express failed readiness checks as standard `validation` diagnostics through `readiness_diagnostic()`.
2. XHS crawl/save skipped diagnostic serialization: map skipped save reasons to standard `validation` or `rate_limited` diagnostics through `skipped_save_diagnostic()` and attach them additively to `skipped_items`.

Do not attach diagnostics to real publish, account login, credential import, or provider execution paths in this task.

- [x] **Step 2: Write failing diagnostic tests**

Extend `tests/backend/test_diagnostics.py` with tests like:

```python
from backend.app.services.diagnostic_service import sanitize_raw_reference, standard_diagnostic
from backend.app.services.platform_readiness_service import CoreReadinessSnapshot, evaluate_second_platform_readiness


def test_readiness_follow_up_can_be_expressed_as_standard_diagnostic():
    report = evaluate_second_platform_readiness(
        CoreReadinessSnapshot(
            platform_registry=True,
            read_only_adapter_path=False,
            shared_content_shell=True,
            capability_policy=True,
            publish_dry_run_no_side_effect=True,
            scheduler_no_bypass=True,
            diagnostics_no_secret_leak=True,
            credential_logging_safe=True,
            real_publish_confirmation_gate=True,
            disable_rollback_path=True,
        )
    )
    failed = [check for check in report.checks if not check.passed]
    assert failed
    diagnostic = standard_diagnostic(
        "validation",
        platform_id="platform_core",
        capability_key="readiness.second_platform",
        stage="readiness",
        severity="warning",
        recoverable=True,
        correlation_id=failed[0].key,
        user_message=failed[0].user_impact,
        raw_reference=f"diagnostic:{failed[0].key}",
    ).to_payload()
    assert diagnostic["category"] == "validation"
    assert diagnostic["next_action"]
    assert diagnostic["raw_reference"] == f"diagnostic:{failed[0].key}"


def test_standard_diagnostic_drops_secret_bearing_references():
    assert sanitize_raw_reference("https://example.com/path?token=secret") == "https://example.com/path"
    assert sanitize_raw_reference({"raw_json": {"cookie": "secret"}}) is None
```

If route-level diagnostics are added, add route tests that assert diagnostics are additive and existing fields remain present.

- [x] **Step 3: Run failing tests**

Run:

```powershell
py -3.12 -m pytest tests/backend/test_diagnostics.py -q
```

Observed before implementation: failed during collection because `readiness_diagnostic` was not yet exported by `backend.app.services.diagnostic_service`.

- [x] **Step 4: Implement minimal diagnostic adapter helpers**

If needed, add a helper to `backend/app/services/diagnostic_service.py`:

```python
def readiness_diagnostic(*, check_key: str, user_message: str, next_stage: str = "readiness") -> StandardDiagnostic:
    return standard_diagnostic(
        "validation",
        platform_id="platform_core",
        capability_key="readiness.second_platform",
        stage=next_stage,
        severity="warning",
        recoverable=True,
        correlation_id=check_key,
        user_message=user_message,
        raw_reference=f"diagnostic:{check_key}",
    )
```

Only add this helper if tests or route integration use it. Do not add broad diagnostic frameworks.

- [x] **Step 5: Run diagnostic and focused route regressions**

Run:

```powershell
py -3.12 -m pytest tests/backend/test_diagnostics.py -q
py -3.12 -m pytest tests/backend/test_api.py -q -k "diagnostic or crawl or platform"
```

Observed: selected tests pass.

- [x] **Step 6: Update completion plan status**

**Task 3 evidence:**
- Commit: current scoped Task 3 commit; final SHA is reported in Task 3 closeout.
- Tests: `py -3.12 -m pytest tests/backend/test_diagnostics.py tests/backend/test_platform_readiness_gate.py -q` -> `14 passed`.
- Regression: `py -3.12 -m pytest tests/backend/test_api.py -q -k "diagnostic or crawl or platform"` -> `34 passed, 162 deselected`.
- Review fix: readiness payloads now include additive `diagnostics`, readiness blocker diagnostics preserve blocker severity/recoverability, skipped-item diagnostics append without overwriting existing diagnostics, and skipped save diagnostics preserve `recoverable` semantics.
- Boundary: no credentials, raw_json, provider payloads, real account actions, real publish paths, DB/Alembic changes, SDK/signature changes, or root service restart.

- [x] **Step 7: Commit scoped files**

Stage only touched diagnostics files and tests:

```powershell
git -C "E:\小红书" add -- backend/app/services/diagnostic_service.py tests/backend/test_diagnostics.py docs/superpowers/plans/2026-07-01-platform-operating-core-completion.md
git -C "E:\小红书" commit -m @'
feat: adopt standard diagnostics in low-risk paths

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
'@
```

Add route files to `git add --` only if they were touched.

---

### Task 4: Content mapper adoption cleanup

**Goal:** Close or explicitly document remaining low-risk mapper gaps for XHS notes/comments and WeChat Official content library mapping.

**Files:**

- Modify if needed: `backend/app/adapters/xhs/mappers.py`
- Modify if needed: `backend/app/api/platforms/xhs/crawl.py`
- Modify if needed: `backend/app/api/platforms/xhs/pc.py`
- Modify if needed: `frontend/src/pages/wechat-official/wechat-official-content-library-mapper.ts`
- Modify tests if needed: `tests/backend/test_xhs_content_mappers.py`
- Modify tests if needed: `tests/backend/test_notes_xhs_serializer.py`
- Modify tests if needed: `frontend/tests/wechat-official-content-library-mapper.test.ts`
- Modify docs: `docs/superpowers/plans/2026-07-01-platform-operating-core-completion.md`
- Modify docs: `docs/superpowers/plans/2026-06-20-platform-operating-core.md`

- [x] **Step 1: Inventory pure mapping helpers still trapped in routes/pages**

Run:

```powershell
git -C "E:\小红书" grep -n "function map\|def _.*map\|normalize_.*payload\|raw_json\|note_card\|interact_info" -- backend/app/api backend/app/adapters frontend/src/pages/wechat-official frontend/src/pages/platforms/xhs
```

**Task 4 mapper inventory:**
- Closed: XHS note serializer uses `map_xhs_content` from `backend/app/adapters/xhs/mappers.py`; evidence `tests/backend/test_notes_xhs_serializer.py` covers mapper fallback, DB asset priority, non-XHS raw-shape tolerance, and mapping-cache reuse.
- Closed: XHS comment payload normalization uses `normalize_xhs_comment_payload` from `backend/app/adapters/xhs/mappers.py`; evidence `tests/backend/test_xhs_content_mappers.py` and route imports.
- Closed: WeChat Official ContentLibraryItem mapper exists at `frontend/src/pages/wechat-official/wechat-official-content-library-mapper.ts`; evidence `frontend/tests/wechat-official-content-library-mapper.test.ts`.
- Remaining/deferred: XHS frontend content-library adapter and draft workbench still contain UI-local raw display/extraction helpers. They are frontend view adapters, not low-risk backend ingestion mapper gaps for this closure task; extracting them would require a separate frontend adapter design and is deferred.
- Remaining/deferred: WeChat Official research adapter normalizers are experimental/source-specific ingestion helpers, outside this current shared ContentLibraryItem mapper closure.

- [x] **Step 2: Only write tests if an in-scope pure mapper remains**

If the inventory finds a pure mapping helper that is still route/page-private and low-risk, write a focused test before moving it.

Backend example:

```python
def test_new_mapper_preserves_existing_route_shape():
    raw = {"note_card": {"interact_info": {"liked_count": "12"}}}
    mapped = map_xhs_content("note-1", raw)
    assert mapped.metrics["liked_count"] == 12
```

Frontend example:

```ts
assert.equal(mapWechatOfficialArticleToContentItem(article()).platform, "wechat_official");
```

If no in-scope mapper remains, this task is docs/evidence-only.

No in-scope pure mapper remains for this low-risk closure. This task is docs/evidence-only.

- [x] **Step 3: Run mapper tests**

Run all relevant mapper tests:

```powershell
py -3.12 -m pytest tests/backend/test_xhs_content_mappers.py tests/backend/test_notes_xhs_serializer.py -q
node frontend/tests/wechat-official-content-library-mapper.test.ts
```

If no code changes are needed, these passing tests are sufficient closure evidence.

Observed: `py -3.12 -m pytest tests/backend/test_xhs_content_mappers.py tests/backend/test_notes_xhs_serializer.py -q` -> `14 passed`; `node frontend/tests/wechat-official-content-library-mapper.test.ts` -> passed.

- [x] **Step 4: Implement minimal extraction only if tests require it**

Move only pure mapping code to adapter mapper files. Do not change route response fields, database models, or ingestion semantics.

No production code extraction was needed after inventory; no route response fields, database models, or ingestion semantics changed.

Allowed pattern:

```python
from backend.app.adapters.xhs.mappers import normalize_xhs_comment_payload
```

Forbidden pattern:

```python
# Do not add database/session/FastAPI dependencies to mapper modules.
```

- [x] **Step 5: Update both closure queue docs**

In `docs/superpowers/plans/2026-06-20-platform-operating-core.md`, update Stage 4 evidence from “WeChat Article mapping remains” to the current state. Use wording like:

```md
Stage 4 backend/content mapper closure is closed for current low-risk scope: XHS note serializer, XHS comment payload normalization, explicit notes account platform expectation, and WeChat Official article-to-shared-ContentLibraryItem mapping all have focused tests. Remaining cross-platform ingestion or database unification is deferred outside this closure program.
```

In this completion plan, add Task 4 evidence.

**Task 4 evidence:**
- Commit: pending scoped Task 4 commit; final SHA is reported in Task 4 closeout.
- Scope: docs/evidence-only after inventory found no remaining low-risk pure mapper extraction target.
- Closed: XHS note serializer uses `map_xhs_content`; XHS comment payload normalization uses `normalize_xhs_comment_payload`; WeChat Official shared ContentLibraryItem mapper exists and is tested.
- Deferred: XHS frontend view-adapter raw display/extraction helpers and WeChat Official experimental research adapter normalizers require separate design if migrated.
- Boundary: no production code changes, route response shape changes, database/Alembic changes, ingestion semantics changes, SDK/signature changes, provider calls, or root service restart.

- [x] **Step 6: Run verification**

Run:

```powershell
py -3.12 -m pytest tests/backend/test_xhs_content_mappers.py tests/backend/test_notes_xhs_serializer.py -q
node frontend/tests/wechat-official-content-library-mapper.test.ts
npm --prefix frontend run build
```

Observed:
- `py -3.12 -m pytest tests/backend/test_xhs_content_mappers.py tests/backend/test_notes_xhs_serializer.py -q` -> `14 passed`.
- `node frontend/tests/wechat-official-content-library-mapper.test.ts` -> passed.
- `npm --prefix frontend run build` initially failed because this isolated worktree had no `frontend/node_modules`; a temporary Windows junction to `E:\小红书\frontend\node_modules` was created, build passed, and the junction was removed.
- Final build result: `tsc && vite build` passed; Vite emitted only the existing large chunk warning.

- [ ] **Step 7: Commit scoped files**

Stage only touched files. If docs/evidence-only:

```powershell
git -C "E:\小红书" add -- docs/superpowers/plans/2026-07-01-platform-operating-core-completion.md docs/superpowers/plans/2026-06-20-platform-operating-core.md
git -C "E:\小红书" commit -m @'
docs: close platform content mapper adoption

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
'@
```

If code changed, use:

```text
refactor: close platform content mapper adoption
```

---

## Batch 2: Readiness Pilot

### Task 5: Fake/read-only second-platform adapter pilot

**Goal:** Prove that Platform Core can host a second read-only platform through registry + shared content shell without real accounts, providers, credentials, publish, or automation.

**Files:**

- Modify: `frontend/src/types/index.ts` if adding `demo_platform` to `PlatformId`.
- Modify: `frontend/src/lib/platforms.ts` for fallback demo platform only if frontend route needs it.
- Modify: `frontend/src/platform-core/registry/platform-sections.tsx`.
- Modify: `frontend/src/app/router.tsx`.
- Create: `frontend/src/pages/demo-platform/demo-content-library-adapter.tsx` or `frontend/src/pages/platforms/demo/demo-content-library-adapter.tsx`.
- Create: `frontend/src/pages/demo-platform/demo-library-page.tsx` or `frontend/src/pages/platforms/demo/demo-library-page.tsx`.
- Create: `frontend/tests/demo-platform-content-library-adapter.test.ts`.
- Modify if backend registry pilot is needed: `backend/app/core/platforms.py`.
- Modify tests if backend touched: `tests/backend/test_platforms.py`.
- Modify docs: `docs/superpowers/plans/2026-07-01-platform-operating-core-completion.md`.

- [x] **Step 1: Write fake adapter contract test**

Created `frontend/tests/demo-platform-content-library-adapter.test.ts` covering:

- `platform === "demo_platform"`.
- `loadItems({ page: 1, page_size: 20 })` returns two local fixture items.
- `loadItem`, `loadAssets`, and `loadComments` work without external requests.
- Write capabilities are disabled (`canCreateDraft`, `canBatchCreateDrafts`, `canDelete`, `canBatchDelete`, `canTag`, `canExport`).
- `renderDetail` exists.

Observed RED: `node frontend/tests/demo-platform-content-library-adapter.test.ts` failed with `ERR_MODULE_NOT_FOUND` because `frontend/src/pages/demo-platform/demo-content-library-adapter.tsx` did not exist.

- [x] **Step 2: Implement fake read-only adapter**

Created `frontend/src/pages/demo-platform/demo-content-library-adapter.tsx` as fixture-only `ContentLibraryAdapter`:

- Uses two local fixture items under `demo_platform`.
- Makes no provider/API/backend requests.
- Returns local fixture assets and empty local comments.
- Closes write/export/tag/draft/delete capabilities and fail-closes write method calls.
- Renders card, table, and detail content through the shared content-library contract.

- [x] **Step 3: Add demo page using shared shell**

Created `frontend/src/pages/demo-platform/demo-library-page.tsx` using `ContentLibraryShell` + `useContentLibrary` inside `PlatformSectionPage` with an explicit read-only safety message.

- [x] **Step 4: Add demo route and section only as fail-closed pilot**

- Added `demo_platform` to `PlatformId` in `frontend/src/types/index.ts`.
- Added only one `demo_platform` registry section: `/platforms/demo-platform/library`.
- Added only one protected router route: `/platforms/demo-platform/library`.
- Did not add account, publish, settings, automation, or provider routes.

- [x] **Step 5: Run fake adapter test and frontend build**

Run:

```powershell
node frontend/tests/demo-platform-content-library-adapter.test.ts
npm --prefix frontend run build
```

Expected:

```text
demo-platform-content-library-adapter tests passed
```

and build exits 0. Observed: adapter test passed; frontend build passed with the existing Vite large chunk warning. A temporary `frontend/node_modules` junction to `E:\小红书\frontend\node_modules` was created for this isolated worktree and removed after validation.

- [x] **Step 6: Update completion plan evidence**

**Task 5 evidence:**
- Commit: pending scoped Task 5 commit (`feat: add demo read-only platform pilot`); no SHA because this task was explicitly requested without commit.
- Test: `node frontend/tests/demo-platform-content-library-adapter.test.ts` -> passed (`demo-platform-content-library-adapter tests passed`; Node emitted an experimental `stripTypeScriptTypes` warning from the test-only loader).
- Build: `npm --prefix frontend run build` -> passed (`tsc && vite build`; Vite emitted only the existing large chunk warning).
- Boundary: fixture-only read path; no account binding, credentials, provider calls, publish/upload, comments/interaction actions, real automation, DB/Alembic changes, SDK/signature changes, root service restart, or `compare-shots/` change.
- Temporary dependency junction: created `frontend/node_modules` -> `E:\小红书\frontend\node_modules` for isolated worktree validation and removed after build.

- [ ] **Step 7: Commit scoped files**

Skipped by explicit user instruction: do not commit, do not git add, do not push.

---
### Task 6: Readiness rerun and closure queue update

**Goal:** Re-evaluate the second-platform readiness verdict after low-risk closure and fake/read-only pilot, then record the current allowed outcome.

**Files:**

- Modify if needed: `backend/app/services/platform_readiness_service.py`
- Modify: `tests/backend/test_platform_readiness_gate.py`
- Modify: `docs/superpowers/plans/2026-07-01-platform-operating-core-completion.md`
- Modify: `docs/superpowers/plans/2026-06-20-platform-operating-core.md`

- [ ] **Step 1: Write or update readiness test for post-pilot PASS criteria**

In `tests/backend/test_platform_readiness_gate.py`, add or update a test:

```python
from backend.app.services.platform_readiness_service import CoreReadinessSnapshot, evaluate_second_platform_readiness


def test_readiness_passes_when_read_only_pilot_and_safety_gates_are_ready():
    report = evaluate_second_platform_readiness(
        CoreReadinessSnapshot(
            platform_registry=True,
            read_only_adapter_path=True,
            shared_content_shell=True,
            capability_policy=True,
            publish_dry_run_no_side_effect=True,
            scheduler_no_bypass=True,
            diagnostics_no_secret_leak=True,
            credential_logging_safe=True,
            real_publish_confirmation_gate=True,
            disable_rollback_path=True,
        )
    )
    assert report.verdict == "PASS"
    assert report.allowed_outcome == "start_read_only_adapter_pilot"
```

If this test already exists, do not duplicate it; update evidence only.

- [ ] **Step 2: Run readiness tests**

Run:

```powershell
py -3.12 -m pytest tests/backend/test_platform_readiness_gate.py -q
```

Expected: pass.

- [ ] **Step 3: Update closure queue status**

Update `docs/superpowers/plans/2026-06-20-platform-operating-core.md` and this completion plan with the current verdict.

If tests and pilot prove readiness, write:

```md
**Current readiness verdict:** `PASS` for read-only adapter pilot.

**Allowed outcome:** `start_read_only_adapter_pilot`.

**Still blocked:** real account binding, real provider calls, real publish/upload/group-send, comments/replies/engagement actions, and background real automation remain `deferred_by_safety`.
```

If any check remains incomplete, write the exact remaining `FOLLOW_UP` cause instead.

- [ ] **Step 4: Run docs diff check**

Run:

```powershell
git -C "E:\小红书" diff --check -- docs/superpowers/plans/2026-07-01-platform-operating-core-completion.md docs/superpowers/plans/2026-06-20-platform-operating-core.md tests/backend/test_platform_readiness_gate.py
```

Expected: no output.

- [ ] **Step 5: Commit scoped files**

Run:

```powershell
git -C "E:\小红书" add -- tests/backend/test_platform_readiness_gate.py docs/superpowers/plans/2026-07-01-platform-operating-core-completion.md docs/superpowers/plans/2026-06-20-platform-operating-core.md
git -C "E:\小红书" commit -m @'
docs: record platform core readiness completion

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
'@
```

If production readiness service changed, include it explicitly in `git add --` and use:

```text
feat: update platform core readiness gate
```

---

## Batch 3: Safety-Gated Design Only

### Task 7: Publish Queue deeper migration risk design

**Goal:** Write a design for deeper publish queue migration without implementing real publish/upload changes.

**Files:**

- Create: `docs/superpowers/specs/2026-07-01-platform-publish-queue-safety-design.md`
- Modify: `docs/superpowers/plans/2026-07-01-platform-operating-core-completion.md`

- [ ] **Step 1: Write publish safety design doc**

Create `docs/superpowers/specs/2026-07-01-platform-publish-queue-safety-design.md` with these sections:

```md
# Platform Publish Queue Safety Design

**Goal:** Define how publish queue migration can proceed without allowing dry-run, retry, scheduler, or adapter code to perform real upload/post actions without explicit user authorization.

## Stop Conditions

- No real upload/post implementation in this design task.
- No provider calls.
- No database migration.
- No scheduler behavior change.

## Required Architecture Before Implementation

- Platform publish adapter interface.
- Dry-run result contract.
- Real-run confirmation token or authorization reference.
- Trap adapter tests that fail if dry-run calls upload/post.
- Disable/rollback switch per platform/capability.

## Minimum Future Tests

- Dry-run does not instantiate real adapter.
- Unconfirmed real publish returns blocked result.
- Confirmed real publish records audit event before adapter call.
- Planned/blocked platforms fail closed.

## User Impact

Operators can preview publish readiness safely; every real external write remains under explicit user control.
```

- [ ] **Step 2: Update completion plan**

Mark Publish Queue deeper migration as:

```md
`deferred_by_safety` — design exists; implementation requires explicit user approval.
```

- [ ] **Step 3: Run docs diff check**

Run:

```powershell
git -C "E:\小红书" diff --check -- docs/superpowers/specs/2026-07-01-platform-publish-queue-safety-design.md docs/superpowers/plans/2026-07-01-platform-operating-core-completion.md
```

- [ ] **Step 4: Commit docs only**

Run:

```powershell
git -C "E:\小红书" add -- docs/superpowers/specs/2026-07-01-platform-publish-queue-safety-design.md docs/superpowers/plans/2026-07-01-platform-operating-core-completion.md
git -C "E:\小红书" commit -m @'
docs: define publish queue safety gate

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
'@
```

---

### Task 8: Workflow Automation deeper migration risk design

**Goal:** Write a design for deeper workflow automation migration without enabling background real external actions.

**Files:**

- Create: `docs/superpowers/specs/2026-07-01-platform-workflow-automation-safety-design.md`
- Modify: `docs/superpowers/plans/2026-07-01-platform-operating-core-completion.md`

- [ ] **Step 1: Write workflow safety design doc**

Create `docs/superpowers/specs/2026-07-01-platform-workflow-automation-safety-design.md` with these sections:

```md
# Platform Workflow Automation Safety Design

**Goal:** Define how workflow automation can evolve from XHS AutoTask without allowing background jobs to silently publish, upload, comment, reply, or mutate external platforms.

## Stop Conditions

- No background real action implementation in this design task.
- No provider calls.
- No database migration.
- No scheduler execution expansion.

## Required Architecture Before Implementation

- Workflow definition and step capability keys.
- Risk policy with `real_publish_authorized=false` by default.
- `authorization_ref` required for real actions.
- Pending-job-only scheduler behavior until user approval.
- Audit event before any real external action.
- Kill switch per platform/capability.

## Minimum Future Tests

- Historical AutoTasks do not gain publish privileges.
- Background runner creates pending jobs only.
- Any real action step without authorization fails closed.
- Comment/reply/engagement capabilities are blocked unless explicitly enabled.

## User Impact

Operators can automate preparation and review queues without losing final control over real external account actions.
```

- [ ] **Step 2: Update completion plan**

Mark Workflow Automation deeper migration as:

```md
`deferred_by_safety` — design exists; implementation requires explicit user approval.
```

- [ ] **Step 3: Run docs diff check**

Run:

```powershell
git -C "E:\小红书" diff --check -- docs/superpowers/specs/2026-07-01-platform-workflow-automation-safety-design.md docs/superpowers/plans/2026-07-01-platform-operating-core-completion.md
```

- [ ] **Step 4: Commit docs only**

Run:

```powershell
git -C "E:\小红书" add -- docs/superpowers/specs/2026-07-01-platform-workflow-automation-safety-design.md docs/superpowers/plans/2026-07-01-platform-operating-core-completion.md
git -C "E:\小红书" commit -m @'
docs: define workflow automation safety gate

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
'@
```

---

## Final Completion Verification

After Tasks 1-8 are done, run:

```powershell
py -3.12 -m pytest tests/backend/test_platforms.py tests/backend/test_asset_storage_policy.py tests/backend/test_diagnostics.py tests/backend/test_platform_readiness_gate.py -q
node frontend/tests/account-auth-schema.test.ts
node frontend/tests/wechat-official-content-library-mapper.test.ts
node frontend/tests/demo-platform-content-library-adapter.test.ts
npm --prefix frontend run build
git -C "E:\小红书" diff --check
```

Expected:

- All selected backend tests pass.
- All frontend node tests pass.
- Frontend build exits 0, allowing existing Vite large chunk warning.
- `git diff --check` has no output.
- `compare-shots/` remains untouched unless the user separately authorizes handling it.

## Final Report Template

Use this exact structure:

```md
## Platform Operating Core completion status

### Closed
- Account auth schema frontend adoption — actual commit SHA
- Asset policy wider adoption — actual commit SHA
- Diagnostics low-risk adoption — actual commit SHA
- Content mapper adoption cleanup — actual commit SHA
- Fake/read-only second-platform pilot — actual commit SHA
- Readiness rerun — actual commit SHA

### Deferred by safety
- Publish Queue deeper migration — design actual commit SHA, implementation requires explicit authorization
- Workflow Automation deeper migration — design actual commit SHA, implementation requires explicit authorization

### Verification
- `actual verification command` -> passed

### Boundaries preserved
- No real account binding
- No real provider calls
- No real publish/upload/group-send/comment/reply/engagement
- No background real automation
- No DB/Alembic migration
- No file migration/deletion
- No push/deploy
```

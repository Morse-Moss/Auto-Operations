# Platform Operating Core Completion Design

**Goal:** Turn the remaining Platform Operating Core work from ad-hoc stage follow-up into a continuous, auditable completion program that can be executed without asking the user which stage is next after every pass.

**Current baseline:** Stages 0-10 have all received at least a first scoped pass. Wave 1 has been merged into root `master`. The WeChat Official article-to-shared-ContentLibraryItem mapper has also been merged into root `master`. The active work is now closure, not the original numeric stage sequence.

**Non-goal:** This design does not authorize real account binding, real provider calls, real publish/upload/group-send, background real automation, data migration, file deletion, deployment, or push.

---

## Problem

The original Platform Operating Core plan used numbered stages to reduce risk while extracting shared multi-platform infrastructure from an XHS-first codebase. That stage model worked for first passes, but it no longer gives a useful execution order:

- Some stages are already closed.
- Some stages have a safe skeleton but incomplete adoption.
- Some remaining gaps are prerequisites for the second-platform readiness verdict.
- Some deeper work is intentionally safety-gated because it can affect real accounts, publish, upload, or background automation.

If the team keeps asking “which stage is next?”, work will continue in small disconnected fragments. The system needs a completion program: a deterministic queue, risk boundaries, verification floors, and stop conditions.

---

## Design Principles

1. **Closure beats numbering.** Execute the next highest-leverage gap, not the next numeric stage.
2. **Low-risk work continues automatically after approval.** Once this completion program is approved, the implementation agent can move through low-risk closure passes without asking the user to pick the next pass.
3. **High-risk actions remain gated.** Real account binding, real provider calls, real publish/upload/group-send, background automation, migration, deletion, deployment, push, or standard service interruption still require explicit authorization.
4. **One pass, one commit.** Every closure pass must have a narrow scope, focused verification, and a scoped commit.
5. **The queue is the source of truth.** Each pass updates the implementation plan / closure queue so future sessions can recover status from docs and git history, not conversation memory.
6. **User impact is explicit.** Each pass must state why it matters to operators and testers, not only what code changed.

---

## Completion Batches

### Batch 1: Core Closure

Batch 1 closes remaining low-risk adoption gaps. It must not call real providers, change credentials, publish, upload to platforms, migrate data, or delete files.

#### Pass 1: Account auth schema frontend adoption

**Source:** Stage 5.

**Current gap:** Backend platform registry exposes read-only `account_auth_schemas`, but the frontend account drawer still relies on local fallback schema as its primary source.

**Target design:**

- Add a frontend schema mapper that converts backend `account_auth_schemas` into the existing drawer view model.
- Load account auth schema from the platform registry API where available.
- Keep local fallback so account entry remains usable if the registry request fails.
- Keep XHS PC/Creator QR/phone/Cookie behavior unchanged.
- Keep WeChat Official account binding visibly unavailable/planned; do not create a fake usable credential path.

**User impact:** New platform account UI becomes registry-driven and less likely to drift from backend capability state. Operators do not see a misleading “working” account flow for blocked platforms.

**Verification floor:**

- Frontend mapper tests or focused component helper tests.
- `npm --prefix frontend run build`.
- `py -3.12 -m pytest tests/backend/test_platforms.py -q` if backend registry behavior is touched.

#### Pass 2: Asset policy wider adoption

**Source:** Stage 6.

**Current gap:** `asset_storage_policy` exists, but some file/export paths still use direct XHS naming or owner assumptions.

**Target design:**

- Inventory remaining `xhs-*` filename usage before changing code.
- Keep true XHS business artifacts XHS-named, such as XHS analysis reports or XHS-specific Feishu integration attachments.
- Route generic user-owned media/export owner prefix generation and validation through `asset_storage_policy`.
- Preserve backward compatibility with existing `xhs-*` media/export files.
- Do not migrate, delete, rename, or relocate existing files.

**User impact:** Future platforms can create/download user-owned assets without pretending they are XHS assets, while existing links and exports remain valid.

**Verification floor:**

- `py -3.12 -m pytest tests/backend/test_asset_storage_policy.py -q`.
- Focused file/export API regression, e.g. `py -3.12 -m pytest tests/backend/test_api.py -q -k "file or image or export"`.
- `git diff --check` scoped to changed files.

#### Pass 3: Diagnostics low-risk adoption

**Source:** Stage 9.

**Current gap:** `diagnostic_service` exists and publish dry-run uses it, but most low-risk read-only/dry-run paths still return local error strings rather than standard diagnostics with next-action guidance.

**Target design:**

- Attach `StandardDiagnostic` payloads to two or three low-risk paths only.
- Good candidates: crawl/save skipped diagnostics, platform readiness report details, account health or validation dry-run paths.
- Preserve existing response fields; add diagnostics as additive metadata only where response contracts can safely accept it.
- Sanitize `raw_reference` through `sanitize_raw_reference()`.
- Never include cookie, token, raw_json, platform private payload, URL query secrets, or request bodies in diagnostics.

**User impact:** Testers and operators get actionable recovery guidance instead of opaque backend failure strings.

**Verification floor:**

- `py -3.12 -m pytest tests/backend/test_diagnostics.py -q`.
- Focused API regression for each touched path.
- Secret-leak tests for diagnostic references.

#### Pass 4: Content mapper adoption cleanup

**Source:** Stage 4 and Wave 2.

**Current gap:** XHS note mapper, XHS comment mapper, and WeChat Official ContentLibraryItem mapper exist, but closure status needs to be made explicit and any remaining route-private pure mapping should be identified.

**Target design:**

- Review XHS serializer, comment payload, and WeChat Official content library mapping consumption points.
- Extract any remaining pure mapping helpers that are still trapped inside route/page code, only if low-risk and covered by focused tests.
- Update the closure queue to mark completed mapper work as closed or name the exact remaining gap.
- Do not rename database tables, alter API response shapes, or rewrite ingestion.

**User impact:** Future platforms have a concrete adapter mapper pattern to copy instead of reverse-engineering XHS or WeChat page code.

**Verification floor:**

- Existing mapper tests.
- Focused notes/content library route tests if backend touched.
- Frontend build if frontend touched.

---

### Batch 2: Readiness Pilot

Batch 2 aims to move the Stage 10 readiness verdict from `FOLLOW_UP` toward `PASS` without connecting a real second platform account or real provider.

#### Pass 5: Fake/read-only second-platform adapter pilot

**Source:** Stage 10 readiness follow-up.

**Current gap:** The readiness gate reports that second-platform read-only adapter/content-library adoption is incomplete.

**Target design:**

- Add a fake/demo platform adapter that is only available in tests or an explicit development-only registry mode.
- Implement the minimum read-only path needed to prove the core:
  - platform registry metadata,
  - read-only content list/detail contract,
  - shared ContentLibrary shell rendering path,
  - no account binding,
  - no publish capability,
  - no provider calls.
- Fail closed for credential, upload, publish, automation, and external integration capabilities.

**User impact:** The team can prove the platform core is not just renamed XHS code before selecting a real next platform.

**Verification floor:**

- Backend registry/policy tests.
- Frontend build.
- Shared ContentLibrary adapter contract tests.
- Readiness gate tests.

#### Pass 6: Readiness rerun and closure queue update

**Source:** Stage 10.

**Target design:**

- Re-evaluate `evaluate_second_platform_readiness()` after the fake/read-only pilot.
- Update the plan with current verdict, allowed outcome, and remaining blockers.
- If the verdict becomes `PASS`, the only authorized next step is a real-platform read-only adapter pilot; real account binding and write actions still require separate authorization.

**User impact:** The user sees a clear status: whether real read-only second-platform exploration is now allowed, and which capabilities remain blocked.

**Verification floor:**

- `py -3.12 -m pytest tests/backend/test_platform_readiness_gate.py -q`.
- Any tests added for the fake/read-only pilot.
- Docs diff check.

---

### Batch 3: Safety-Gated Actions

Batch 3 is not automatically executable. It needs explicit user approval per capability because it can affect real accounts or real platform actions.

#### Pass 7: Publish Queue deeper migration design

**Source:** Stage 7 / Wave 3.

**Gate reason:** Real publish/upload semantics are high risk.

**Design-only target unless separately authorized:**

- Define platform publish adapter boundary.
- Separate dry-run from real-run.
- Require explicit confirmation or authorization reference for every real publish.
- Add trap tests proving dry-run cannot upload/post.
- Define rollback/disable behavior.

#### Pass 8: Workflow Automation deeper migration design

**Source:** Stage 8 / Wave 3.

**Gate reason:** Background automation must not silently publish, upload, comment, reply, or mutate real accounts.

**Design-only target unless separately authorized:**

- Define workflow definition and risk policy.
- Require `authorization_ref` for real actions.
- Keep background execution limited to pending jobs unless explicitly approved.
- Add audit requirements and no-bypass tests.

---

## Continuous Execution Rules

After this design and its implementation plan are approved, the agent may proceed through Batch 1 and Batch 2 without asking the user which pass is next. The agent must still stop for explicit authorization before any action in the stop list below.

### Stop list: explicit user authorization required

- Real account binding or login flow changes.
- Real provider/API calls outside local tests.
- Real publish, upload, preview send, group-send, comment, reply, or engagement action.
- Background automation that can mutate external platforms.
- Database schema migration or data migration.
- Deleting, moving, or rewriting existing user media/export files.
- Stopping/restarting root standard services.
- Push, deployment, or PR creation.
- Broad cleanup outside the scoped pass.

### Commit and merge policy

- One closure pass per commit.
- Stage only explicit scoped files.
- Do not use `git add .` or `git add -A`.
- Worktree commits do not count as root `master` completion until merged.
- Root `master` merge still requires user confirmation unless the user gives temporary explicit authorization for this completion program.
- Push is never automatic.

### Documentation policy

Each pass must update the completion plan or original closure queue with:

- pass status,
- commit SHA,
- verification evidence,
- user impact,
- remaining boundary or deferred safety item.

---

## Definition of Done for the Completion Program

The low-risk completion program is done when:

1. Account auth schema frontend adoption is closed.
2. Asset storage policy low-risk adoption is closed or remaining XHS names are documented as intentionally XHS-specific.
3. Diagnostics low-risk adoption is closed for selected paths and secret-leak tests pass.
4. Mapper adoption cleanup is closed and the closure queue names no ambiguous mapper gap.
5. A fake/read-only second-platform pilot proves the shared registry/content/readiness path without real provider calls.
6. Stage 10 readiness is rerun and the plan records either `PASS` or the exact remaining `FOLLOW_UP` cause.
7. Publish Queue deeper migration and Workflow Automation deeper migration are explicitly marked `deferred_by_safety` unless the user approves separate risk/QA designs.

---

## Why this is the direct path

The project goal is not to make every old XHS feature abstract. The goal is to make the next platform cheap and safe to add. The direct path is therefore:

1. close the low-risk adapter/schema/policy/diagnostic gaps,
2. prove the shared core with a fake/read-only second platform,
3. only then decide whether to take on real external actions.

This avoids spending time on risky publish/automation migration before the read-only platform core is proven.

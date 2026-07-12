# XHS Account Re-login and Profile Sync Implementation Plan

> **For agentic workers:** Execute this plan task-by-task with TDD. Do not commit or push unless the user explicitly requests it.

**Goal:** Make PC QR confirmation idempotent so re-login preserves one valid credential, complete profile data clears pending state, and discovery immediately uses the restored account.

**Architecture:** Serialize polling in both the React client and FastAPI backend. Persist the login-session claim/result, canonicalize platform-account identity at the database boundary, and route login/check flows through one complete-profile merge path.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, SQLite/MySQL-compatible schema, React, TypeScript, Vite, pytest.

---

### Task 1: Reproduce the backend races and stale profile state

**Files:**
- Modify: `tests/backend/test_api.py`

- [ ] Add a concurrent QR-poll test whose fake adapter blocks the first request and proves a second request cannot call upstream.
- [ ] Run the new test and verify it fails because both requests can enter QR confirmation.
- [ ] Add a confirmed-session replay test and verify it fails because terminal responses do not return the stored account.
- [ ] Add a complete-self-profile test starting from a pending profile and verify it fails because the marker survives enrichment.
- [ ] Add an expired-account re-login test and verify it fails if a duplicate identity row is created.

Run:

```powershell
E:\AI\Python\python.exe -X utf8 -m pytest tests\backend\test_api.py -k "qr_poll_is_serialized or confirmed_login_replays_account or self_profile_clears_pending or relogin_reuses_expired" -q
```

Expected before implementation: the new assertions fail for the identified behavior, not because of fixture or syntax errors.

### Task 2: Persist idempotent login-session results

**Files:**
- Modify: `backend/app/models/login_session.py`
- Modify: `backend/app/api/login_sessions.py`
- Create: `backend/alembic/versions/20260712_xhs_login_session_idempotency.py`
- Test: `tests/backend/test_api.py`

- [ ] Add nullable `platform_account_id`, `poll_in_progress`, and `poll_started_at` fields.
- [ ] Atomically claim polling before any XHS request and release the claim on every success/failure path.
- [ ] Expire older non-terminal sessions when a new QR session is created.
- [ ] Store the canonical account id on confirmation.
- [ ] Return the stored account for terminal confirmed sessions without calling an adapter.
- [ ] Re-run the focused tests until all Task 1 cases pass.

### Task 3: Clear pending only from successful complete-profile evidence

**Files:**
- Modify: `backend/app/services/account_service.py`
- Modify: `backend/app/api/accounts.py`
- Modify: `backend/app/api/login_sessions.py`
- Test: `tests/backend/test_api.py`

- [ ] Make complete self-profile enrichment remove `profile_sync_status` before constructing the merged profile.
- [ ] Reuse the same PC profile-refresh behavior in QR login, cookie import, and account check.
- [ ] Preserve existing non-empty fields when an upstream response omits them.
- [ ] Clear `status_message` after a complete profile succeeds.
- [ ] Verify pending remains only when both profile endpoints fail and only QR identity is available.

### Task 4: Canonicalize duplicate account identities

**Files:**
- Modify: `backend/app/models/platform_account.py`
- Modify: `backend/app/services/account_service.py`
- Create or extend: `backend/alembic/versions/20260712_xhs_login_session_idempotency.py`
- Test: `tests/backend/test_api.py`

- [ ] Add a failing duplicate-identity test.
- [ ] In the migration, merge duplicate account references and cookie versions into the richest canonical row.
- [ ] Normalize empty external ids to `NULL` and add the identity uniqueness constraint.
- [ ] Handle concurrent insert conflicts by reloading and updating the canonical row.
- [ ] Prove an expired or deleted account is reactivated in place on successful re-login.

### Task 5: Make discovery reflect re-login and classify expired search credentials

**Files:**
- Modify: `backend/app/api/platforms/xhs/pc.py`
- Modify: `backend/app/services/xhs_crawl_quality_service.py`
- Modify: `frontend/src/pages/platforms/xhs/discovery-page.tsx`
- Modify: `frontend/src/components/account/qr-login-panel.tsx`
- Modify: `tests/frontend/test_xhs_creator_qr_reliability_contract.py`
- Test: `tests/backend/test_api.py`

- [ ] Add `无登录信息` and equivalent response codes to account-expired classification.
- [ ] Mark the selected account expired before returning an actionable authentication error.
- [ ] Replace overlapping interval polling with request-complete-then-timeout polling.
- [ ] Reload account state on page focus and prefer active PC accounts while keeping valid pending-profile accounts selectable.
- [ ] Verify the frontend contract test fails before source changes and passes afterward.

### Task 6: Verify the complete workflow

- [ ] Run targeted backend tests for login, account check, identity merge, and discovery search.
- [ ] Run frontend contract tests.
- [ ] Run `npm run build` in `frontend/`.
- [ ] Run the relevant broader backend test module.
- [ ] Start the worktree backend/frontend on non-standard ports with an isolated database.
- [ ] Verify `/api/health`, account list rendering, and the discovery route without issuing a real publish action.
- [ ] Run `git diff --check` and inspect the exact changed-file scope.

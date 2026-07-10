# XHS Account Profile and Creator QR Reliability Implementation Plan

> **For agentic workers:** Execute inline in the current root workspace. Steps use checkbox (`- [ ]`) syntax for tracking; do not spawn subagents or commit unless the user explicitly asks.

**Goal:** Preserve trustworthy XHS account display data during identity-only login fallback and prevent stale QR generation requests from breaking Creator login.

**Architecture:** Add identity-scoped profile merge helpers in the account service for persistence and list serialization. Keep the existing QR API contract, but isolate panel instances by auth selection and gate asynchronous state updates with a request sequence.

**Tech Stack:** FastAPI, SQLAlchemy, React 19, TypeScript, Ant Design, pytest, Vite.

---

### Task 1: Account identity profile fallback

**Files:**
- Modify: `backend/app/services/account_service.py`
- Modify: `backend/app/api/accounts.py`
- Modify: `backend/app/api/login_sessions.py`
- Modify: `frontend/src/pages/platforms/xhs/accounts-page.tsx`
- Test: `tests/backend/test_api.py`

- [ ] Add a failing API test with empty PC and populated Creator accounts sharing the same user and `external_user_id`; assert the PC list payload reuses nickname/avatar/profile and reports pending profile sync.
- [ ] Add a failing service/login regression proving an identity-only upsert preserves matching stored profile fields.
- [ ] Run the new pytest cases and confirm failures are caused by missing identity fallback behavior.
- [ ] Implement identity-scoped merge helpers, use them in login upsert, and serialize account collections with read-only fallback.
- [ ] Render `profile_sync_status=pending` as a “资料待同步” card badge while keeping the account operationally active.
- [ ] Run the new tests to confirm they pass.

### Task 2: Creator QR request isolation

**Files:**
- Modify: `frontend/src/components/account/add-account-drawer.tsx`
- Modify: `frontend/src/components/account/qr-login-panel.tsx`
- Create: `tests/frontend/test_xhs_creator_qr_reliability_contract.py`

- [ ] Add a failing source contract test requiring an auth-selection key, request sequence guard, and Creator-specific generation status.
- [ ] Run the contract test and confirm it fails on the missing reliability markers.
- [ ] Key the QR panel by platform/account type/method and accept state updates only from the latest request sequence.
- [ ] Show an immediate PC/Creator-specific generation message while the request is in flight.
- [ ] Run the contract test and frontend build.

### Task 3: Regression verification

**Files:**
- Verify: `backend/app/services/account_service.py`
- Verify: `backend/app/api/accounts.py`
- Verify: `frontend/src/components/account/add-account-drawer.tsx`
- Verify: `frontend/src/components/account/qr-login-panel.tsx`

- [ ] Run focused XHS login and account tests.
- [ ] Run all frontend contract tests.
- [ ] Run Python compilation, frontend production build, and scoped `git diff --check`.
- [ ] Review the scoped diff and confirm unrelated dirty files remain untouched.

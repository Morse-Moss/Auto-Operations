# Runtime Diagnostics and Tavix Brand Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the public browser diagnostics endpoint and finish the Tavix-branded error recovery surface.

**Architecture:** Keep the existing request-ID and browser-reporting pipeline. Add bounded ingestion and log sanitization at the FastAPI boundary, then add Tavix identity to the existing React error boundary without changing application routing or normal page layout.

**Tech Stack:** FastAPI, Pydantic, React, TypeScript, Ant Design, pytest, Node source-contract tests, Vite.

---

### Task 1: Harden diagnostics ingestion

**Files:**
- Modify: `tests/backend/test_runtime_diagnostics.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write failing backend tests**

Add tests that submit eight reports from one client and expect the eighth to return `429`, submit 21 `extra` keys and expect `422`, and submit newline-containing message/stack fields and expect each captured log record to remain single-line.

- [ ] **Step 2: Run the backend tests and verify RED**

Run: `py -X utf8 -m pytest tests/backend/test_runtime_diagnostics.py -q`

Expected: the new rate-limit, metadata-limit, and log-line assertions fail against the current endpoint.

- [ ] **Step 3: Implement bounded safe ingestion**

In `backend/app/main.py`:

```python
from backend.app.services.rate_limit_service import record_rate_limit_failure

def _safe_log_text(value: str, max_length: int) -> str:
    return " ".join(value.split())[:max_length]
```

Set `extra` to `Field(default_factory=dict, max_length=20)`, consume the `client-errors` rate-limit scope before logging, and pass event type, version, URL, message, and stack through `_safe_log_text`.

- [ ] **Step 4: Run the backend tests and verify GREEN**

Run: `py -X utf8 -m pytest tests/backend/test_runtime_diagnostics.py -q`

Expected: all runtime diagnostics tests pass.

### Task 2: Brand the recovery page

**Files:**
- Modify: `frontend/tests/diagnostics-contract.test.ts`
- Modify: `frontend/src/components/ui/error-boundary.tsx`

- [ ] **Step 1: Write failing frontend contract assertions**

Assert that the error boundary contains `/logo.png`, `TAVIX OPERATIONS PLATFORM`, and `拓效自动化运营系统` in addition to the existing refresh and copy recovery actions.

- [ ] **Step 2: Run the frontend contract and verify RED**

Run: `node frontend/tests/diagnostics-contract.test.ts`

Expected: the Tavix identity assertion fails against the current generic error boundary.

- [ ] **Step 3: Add the Tavix identity block**

Add a compact logo-and-wordmark row above `页面加载失败`, reuse the existing dark panel, and keep all widths responsive with `minWidth: 0`, wrapped text, and wrapped actions.

- [ ] **Step 4: Run the frontend contract and verify GREEN**

Run: `node frontend/tests/diagnostics-contract.test.ts`

Expected: `diagnostics-contract tests passed`.

### Task 3: Verify local and deployed behavior

**Files:**
- Verify only; no production source changes expected.

- [ ] **Step 1: Run code verification**

Run:

```powershell
py -X utf8 -m alembic -c backend/alembic.ini heads
py -X utf8 -m pytest tests/backend -q
npm --prefix frontend run build -- --configLoader runner
git diff --check
```

Expected: one Alembic head, zero backend failures, successful frontend build, and no diff-check errors.

- [ ] **Step 2: Run local browser checks**

Render the error boundary in Chromium at desktop and mobile widths, verify the wordmark and both recovery actions are visible, capture screenshots, and confirm there is no horizontal overflow or console error caused by the fallback itself.

- [ ] **Step 3: Run read-only production checks**

Check `https://aitavix.com`, `/api/health`, and `/api/version`; record status codes, request-ID headers, rendered title/brand, console errors, and whether the deployed commit includes the new local changes.

- [ ] **Step 4: Report without committing**

Report scoped files, verification evidence, production findings, excluded concurrent model-routing files, and whether a commit/push/deploy/restart is still required. Do not stage, commit, push, deploy, or restart without separate user authorization.

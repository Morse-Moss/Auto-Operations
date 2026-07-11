# Runtime Diagnostics and Tavix Brand Design

## Goal

Complete the already-merged browser diagnostics flow so it is safe for an unauthenticated production surface and presents a clear Tavix-branded recovery page instead of a generic crash screen.

## Current Baseline

- Commit `2f0f20b` already adds request IDs, `/api/version`, `/api/client-errors`, global browser error reporting, and a React error boundary.
- Tavix title, favicon, shell, login-page, and logo changes are currently present in the root working tree but are not committed.
- The public diagnostics endpoint must remain usable before login and when normal application providers fail.

## Design

### Backend Safety

- Keep `/api/client-errors` unauthenticated so login and router failures can still be reported.
- Consume the existing per-client in-memory rate-limit bucket for each accepted report; the eighth report inside one minute returns `429`.
- Limit `extra` metadata to 20 keys in the Pydantic request model.
- Collapse whitespace in user-controlled log fields and keep existing length limits so a browser report cannot inject forged log lines.
- Continue returning the sanitized request ID in both the response body and `X-Request-ID` response header.

### Error Recovery Surface

- Keep the dark, high-contrast recovery layout and its two primary actions: refresh and copy diagnostics.
- Add the canonical `/logo.png`, `TAVIX OPERATIONS PLATFORM`, and `拓效自动化运营系统` above the error title.
- Preserve a single-column layout, wrap actions on narrow screens, and allow long diagnostic text to scroll without horizontal page overflow.
- Diagnostics transport failure must never prevent the fallback page from rendering.

### Asset Boundary

- Runtime code references `/logo.png` only.
- The pre-existing modified `frontend/public/logo.jpg` is not changed by this task because it is an unrelated duplicate working-tree artifact and no runtime code references it.

## Verification

- Backend RED/GREEN tests cover rate limiting, metadata limits, log-line sanitization, request IDs, and accepted reports.
- Frontend RED/GREEN contract tests cover Tavix identity and the existing recovery actions.
- Alembic must report exactly one head.
- Full backend tests and the frontend production build must pass.
- Local browser checks cover desktop and mobile fallback layout.
- Production checks are read-only and cover HTTPS, frontend rendering, `/api/health`, `/api/version`, request-ID headers, and browser console/network failures.

## Non-Goals

- No database persistence or diagnostics dashboard.
- No external telemetry vendor.
- No authentication requirement for crash reporting.
- No commit, push, deployment, service restart, or real XHS action without separate authorization.

# LAN Runtime Resilience Design

**Date:** 2026-07-19
**Mode:** STAGED / STANDARD / LOCAL

## Problem

The LAN application and the former public deployment exercised different runtime boundaries. Two failures remain valuable to fix in the shared codebase:

1. Server databases can close idle pooled connections. The current SQLAlchemy engine does not probe or recycle those connections, so the first request after a long idle period can fail.
2. An XHS PC account can remain `active` even when its latest encrypted Cookie no longer contains a usable `web_session`. Account lists and UI defaults currently treat that record as usable and can select it before a healthy account.

Model capability defaults are intentionally explicit. This change does not guess or write capability bindings; the local readiness check only verifies that the existing LAN database remains configured.

## Goals

- Probe and recycle pooled connections for non-SQLite databases while preserving the current SQLite setup.
- Derive non-secret XHS PC login readiness from the latest Cookie version, ordered by `created_at DESC, id DESC`.
- Return fixed, actionable readiness fields from the account-list API without mutating account or Cookie rows.
- Reject a manually submitted unusable PC account before any XHS request; an `active` record proven to lack a valid session becomes `expired` on that explicit operation.
- Share one pure frontend selection helper between note discovery and direct crawling.
- Keep unusable PC accounts visible but disabled and labeled as requiring re-login.

## Non-Goals

- No Railway, production database, DNS, CORS, Cloudflare, or deployment work.
- No model capability auto-binding or Provider calls.
- No Creator publishing, scheduler, XHS SDK/signature, or legacy-system changes.
- No broad account-page redesign.

## Backend Design

### Database Engine

A small deterministic helper builds SQLAlchemy engine options:

- SQLite: `check_same_thread=False` only.
- Other databases: `pool_pre_ping=True` and `pool_recycle=3600`.

The one-hour recycle boundary stays below the observed eight-hour MySQL idle timeout while remaining database-agnostic.

### XHS PC Readiness

For account-list responses, batch-load the latest Cookie version for every listed XHS PC account. A PC account is ready only when:

- its stored status is `active`;
- the latest Cookie decrypts and parses successfully; and
- `web_session` is a trimmed, non-empty string.

Missing Cookie rows, decryption failures, malformed Cookie text, blank sessions, and non-string sessions all produce `login_ready=false` with a fixed re-login message. Exception details and Cookie values are never returned. The list operation remains read-only.

PC search, detail, and comment endpoints repeat the same local readiness gate before constructing an adapter. If an explicitly used `active` account lacks readiness, the operation marks it `expired`, returns HTTP 409, and does not call XHS.

## Frontend Design

Create a pure XHS PC account-selection helper used by both note discovery and the crawler:

- retain a current selection only while it is still ready;
- otherwise choose the first ready PC account from the API order;
- return `null` when none are ready;
- keep unready accounts visible as disabled options labeled `需重新登录`.

This is a focused interaction fix. Existing layout, density, controls, and responsive structure remain unchanged.

## Verification

- Failure-first unit coverage for engine options and the pure frontend helper.
- API coverage for valid, missing, malformed, blank, non-string, decrypt-failing, and equal-timestamp Cookie versions.
- Proof that account-list readiness does not modify stored account or Cookie data.
- Proof that an explicit bad-PC operation returns 409 without invoking the adapter.
- Focused backend tests, adjacent MySQL/config tests, full backend suite, frontend production build, and local desktop/mobile browser smoke.

## Delivery Boundary

The result stops at verified root-`master` LAN code and running local services. No commit, push, PR, merge, Railway mutation, or public deployment is authorized.

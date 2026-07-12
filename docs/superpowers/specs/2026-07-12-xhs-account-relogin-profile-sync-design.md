# XHS Account Re-login and Profile Sync Design

## Problem

PC QR login can be confirmed by several overlapping poll requests. Each request can exchange the same QR confirmation for a different `web_session`, persist another cookie version, and race account creation. The latest persisted token may already be invalid when discovery uses it.

The profile fallback also stores `profile_sync_status=pending` when only the QR user id is available. A later successful self-profile response currently merges that marker back into the completed profile, so the UI can show "profile pending" even after nickname, avatar, and metrics were fetched.

The live incident proved all parts of this failure:

- six distinct `web_session` values were saved in about 90 seconds;
- duplicate PC accounts `20` and `21` were created for the same owned XHS identity;
- one duplicate contains the complete profile while both still carry `pending`;
- the latest stored cookie now returns `success=false` and `登录已过期`;
- discovery forwards that cookie and surfaces `[502] 无登录信息，或登录信息为空`;
- the discovery account selector can retain an old `expired` label after re-login.

## Goals

- Exchange each QR login session at most once.
- Re-login an expired identity into the existing account row.
- Persist one canonical cookie version for a successful confirmation.
- Display nickname, avatar, red id, followers, following, and likes as soon as the self-profile response succeeds.
- Remove the pending marker after a successful complete-profile response.
- Keep discovery account state current and make a re-logged account immediately usable.
- Preserve low-frequency, serial XHS access and avoid changes to `apis/`, `xhs_utils/`, or signing JavaScript.

## Non-goals

- No publishing behavior changes.
- No automatic high-frequency retry loop.
- No XHS SDK/signature refactor.
- No production deployment.

## Design

### 1. Serialize QR polling

The frontend replaces async `setInterval` polling with a recursive timeout that schedules the next poll only after the current request completes. Automatic QR-session reuse lasts long enough to survive React remounts. Explicit refresh still creates a new session.

The backend also owns correctness. `login_sessions` gains a persistent poll claim and the resulting `platform_account_id`. A poll request atomically claims a non-terminal session before calling XHS. Concurrent requests return the stored non-terminal state without another upstream call. A stale claim can be recovered after a bounded timeout.

Creating a new QR session expires older non-terminal sessions for the same user and account subtype. If an older request finishes after being superseded, its result is discarded.

Once a session is confirmed, later polls return the stored account and never call the QR status or token-exchange endpoints again.

### 2. Normalize profile refresh

PC login and account health checks use the same profile-refresh path:

1. Call `/api/sns/web/v2/user/me` for identity and basic fields.
2. Call `/api/sns/web/v1/user/selfinfo` once for the complete profile.
3. When self-profile data is valid, map it and explicitly remove `profile_sync_status`.
4. When only the QR user id is available, keep the account and pending marker without hiding other usable fields.
5. When the upstream response explicitly says login expired, mark the account expired with an actionable status message.

Profile completeness is determined by a successful self-profile response, not by reusing an old pending marker.

### 3. Canonical account identity

An account identity is `(user_id, platform, sub_type, external_user_id)`. Re-login updates that row, including when its previous status was `expired` or `deleted`.

An Alembic migration merges existing duplicate identities, reassigns referencing rows and cookie versions to the canonical account, removes duplicates, normalizes empty external ids to `NULL`, and adds a unique identity constraint. The canonical account is selected by active status, richer profile data, and recency.

The application handles a concurrent unique conflict by loading and updating the canonical row rather than returning an error.

### 4. Discovery state

Discovery reloads local account state when the page regains focus and prefers an active PC account without excluding pending-profile accounts. A successful re-login therefore changes the selector from `expired` to `active` without a hard reload.

If XHS search returns an explicit login-expired signal such as `无登录信息，或登录信息为空`, the backend marks that account expired and returns an actionable authentication error instead of a generic upstream 502.

## Acceptance Criteria

- Five overlapping polls for one QR session cause one upstream confirmation call.
- Confirmed-session replay returns the same account without another XHS request.
- One identity has one platform account and one canonical successful cookie write.
- Re-login changes the existing expired account to active rather than creating another row.
- A successful self-profile response removes `profile_sync_status` and clears the pending message.
- Pending-profile accounts remain selectable and usable when their login cookie is valid.
- Discovery refreshes the account label after re-login.
- An expired search cookie updates account status and returns an actionable re-login message.
- Targeted backend tests, frontend contract tests, frontend build, and non-standard-port smoke tests pass.

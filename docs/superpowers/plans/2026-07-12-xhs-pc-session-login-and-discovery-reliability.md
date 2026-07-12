# XHS PC Session Login and Discovery Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure production PC QR login persists a real XHS `web_session` before activating an account, and make note discovery report expired login state clearly.

**Architecture:** Keep the native XHS QR endpoints and signatures unchanged. Add a small response-session extractor in the existing login SDK, enforce the session invariant in the XHS adapter, and classify only explicit XHS missing-login search failures at the FastAPI boundary.

**Tech Stack:** Python 3.11, requests, FastAPI, SQLAlchemy, pytest

---

### Task 1: Extract the session from current XHS login responses

**Files:**
- Modify: `tests/backend/test_api.py:90-127`
- Modify: `apis/xhs_pc_login_apis.py:172-192`

- [ ] **Step 1: Write failing SDK tests**

Add parameterized coverage that calls a focused `_extract_web_session(response, payload)` helper with response cookies and payload variants:

```python
@pytest.mark.parametrize(
    ("response_cookies", "payload", "expected"),
    [
        ({"web_session": "cookie-session"}, {}, "cookie-session"),
        ({}, {"data": {"login_info": {"session": "legacy-session"}}}, "legacy-session"),
        ({}, {"data": {"loginInfo": {"session": "camel-session"}}}, "camel-session"),
        ({}, {"data": {"web_session": "snake-session"}}, "snake-session"),
        ({}, {"data": {"webSession": "camel-web-session"}}, "camel-web-session"),
        ({}, {"data": {"session": "direct-session"}}, "direct-session"),
        ({}, {"data": {"result": {"session": "result-session"}}}, "result-session"),
    ],
)
def test_xhs_pc_login_extracts_web_session_from_supported_response_shapes(
    response_cookies, payload, expected
):
    from apis.xhs_pc_login_apis import _extract_web_session

    assert _extract_web_session(response_cookies, payload) == expected
```

- [ ] **Step 2: Run the SDK test and verify RED**

Run: `py -X utf8 -m pytest tests/backend/test_api.py -k "extracts_web_session_from_supported_response_shapes" -q`

Expected: FAIL because `_extract_web_session` does not exist.

- [ ] **Step 3: Implement the minimal extractor and merge it into cookies**

Add a private helper that reads only dict values, trims strings, checks the ordered locations from the design, and returns `None` when no session exists. In `_login_by_qrcode_status`, merge response cookies first, parse JSON once, call the helper, and assign only a non-empty result:

```python
session = _extract_web_session(cookies, res)
if session:
    cookies["web_session"] = session
```

Do not log or return the session separately.

- [ ] **Step 4: Run the SDK tests and verify GREEN**

Run: `py -X utf8 -m pytest tests/backend/test_api.py -k "xhs_pc_login_sdk or extracts_web_session_from_supported_response_shapes" -q`

Expected: all selected tests PASS.

- [ ] **Step 5: Commit the SDK parser slice**

```bash
git add tests/backend/test_api.py apis/xhs_pc_login_apis.py
git commit -m "fix: extract xhs pc login session"
```

### Task 2: Prevent confirmed accounts without a real session

**Files:**
- Modify: `tests/backend/test_api.py:111-127,2357-2392`
- Modify: `backend/app/adapters/xhs/pc_login_adapter.py:10-25`

- [ ] **Step 1: Write failing adapter and API tests**

Add one adapter test where the SDK returns success and QR identity but cookies contain only `a1`; assert status is `scanned`. Update/add an API test using a fake adapter that returns `{"status":"scanned","cookies":{"a1":"final-a1"},"user_info":{"external_user_id":"qr-user"}}`; assert the poll response has no account and the database has zero `PlatformAccount` and `AccountCookieVersion` rows.

- [ ] **Step 2: Run the login-gate tests and verify RED**

Run: `py -X utf8 -m pytest tests/backend/test_api.py -k "requires_web_session or missing_web_session" -q`

Expected: FAIL because the adapter currently maps any SDK success to `confirmed`.

- [ ] **Step 3: Implement the adapter gate**

After the SDK call, compute confirmation from both signals:

```python
has_web_session = bool(str(updated_cookies.get("web_session") or "").strip())
status = "confirmed" if success and has_web_session else "pending"
if success and not has_web_session:
    status = "scanned"
```

Keep existing expired/scanned message mapping and QR `userId` mapping unchanged.

- [ ] **Step 4: Run the login-gate and existing QR regression tests**

Run: `py -X utf8 -m pytest tests/backend/test_api.py -k "xhs_pc_qrcode_login or xhs_pc_login_adapter" -q`

Expected: all selected tests PASS, including the valid-session identity fallback.

- [ ] **Step 5: Commit the login gate**

```bash
git add tests/backend/test_api.py backend/app/adapters/xhs/pc_login_adapter.py
git commit -m "fix: require xhs pc web session"
```

### Task 3: Close the note-search expired-login loop

**Files:**
- Modify: `tests/backend/test_api.py:3407-3425,3613-3760`
- Modify: `backend/app/api/platforms/xhs/pc.py:235-277`

- [ ] **Step 1: Write a failing search-expiration test**

Create a fake search adapter returning `(False, "无登录信息，或登录信息为空", None)`. Seed an owned active PC account with an encrypted Cookie. Call `/api/xhs/pc/search/notes` and assert:

```python
assert response.status_code == 409
assert response.json() == {"detail": "账号登录已失效，请重新扫码登录"}
db.refresh(account)
assert account.status == "expired"
assert account.status_message == "账号登录已失效，请重新扫码登录"
assert "web_session" not in response.text
```

- [ ] **Step 2: Run the search-expiration test and verify RED**

Run: `py -X utf8 -m pytest tests/backend/test_api.py -k "note_search_marks_missing_login_expired" -q`

Expected: FAIL because the endpoint currently returns generic `502` and leaves the account active.

- [ ] **Step 3: Implement explicit missing-login classification**

Return the owned account together with its Cookie from a narrowly scoped helper or load it once in the endpoint. Add a private predicate that lowercases the upstream message and matches only explicit missing-login phrases. On a match, set `status="expired"`, set the stable Chinese status message, commit, and raise `HTTPException(status_code=409, detail=...)`. Preserve generic `502` for all other failures.

- [ ] **Step 4: Run note-search tests and verify GREEN**

Run: `py -X utf8 -m pytest tests/backend/test_api.py -k "xhs_pc_note_search or xhs_pc_search" -q`

Expected: all selected tests PASS.

- [ ] **Step 5: Commit the search error slice**

```bash
git add tests/backend/test_api.py backend/app/api/platforms/xhs/pc.py
git commit -m "fix: expire invalid xhs search sessions"
```

### Task 4: Regression verification and delivery

**Files:**
- Verify: `tests/backend/test_api.py`
- Verify: `frontend/`
- Verify: `docs/superpowers/specs/2026-07-12-xhs-pc-session-login-and-discovery-reliability-design.md`

- [ ] **Step 1: Run focused backend regression**

Run: `py -X utf8 -m pytest tests/backend/test_api.py -k "xhs_pc_qrcode_login or xhs_pc_login or xhs_pc_note_search or xhs_pc_search" -q`

Expected: all selected tests PASS.

- [ ] **Step 2: Run the full backend suite**

Run: `py -X utf8 -m pytest tests/backend -q`

Expected: all tests PASS with only documented pre-existing warnings.

- [ ] **Step 3: Build the frontend**

Run: `npm run build`

Working directory: `frontend/`

Expected: Vite build succeeds. No frontend source change is planned, but this proves the production bundle still compiles.

- [ ] **Step 4: Verify branch scope**

Run: `git diff --check HEAD~3..HEAD && git status --short --branch`

Expected: no whitespace errors and a clean worktree.

- [ ] **Step 5: Merge and deploy using the authorized mainline workflow**

From root `E:\小红书`, merge with `git merge --no-ff fix/xhs-pc-session-login`, push `master`, then poll `/api/version` until it reports the merge commit. Do not stage or modify unrelated root files.

- [ ] **Step 6: Complete production acceptance**

Have the user scan one new PC QR code. Verify, without printing values, that the resulting account Cookie includes non-empty `web_session`; then issue one low-frequency note search through the production API and require HTTP `200` with a valid response structure. Confirm `/api/health` remains `200` and Railway logs show no instance restart.

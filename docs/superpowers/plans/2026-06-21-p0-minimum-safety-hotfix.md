# P0 Minimum Safety Hotfix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the current workspace to a trustworthy P0 baseline by making unsafe external publishing/upload/configuration paths fail closed and bringing targeted tests back to green.

**Architecture:** Continue inline in the root workspace because current uncommitted WeChat draft independence edits are the real baseline. Apply a minimal hotfix: no new database tables, no real external calls, and no full task-center redesign. Each P0 behavior gets a focused regression test before production code changes.

**Tech Stack:** Python 3.10+ / FastAPI / SQLAlchemy / Pytest backend; React / TypeScript frontend.

---

## Workspace and isolation

- Mode: `inline_write`.
- Reason: current uncommitted files define the correct baseline, especially WeChat official draft independence.
- Do not create a worktree for this hotfix.
- Do not commit or push unless explicitly requested.

## File map

- Modify: `tests/backend/test_wechat_official_redfox_collect.py` — align old Redfox draft assertion with WeChat draft independence.
- Modify/Create: `tests/backend/test_config.py` — verify environment variables override YAML values for sensitive config.
- Modify: `backend/app/core/config.py` — apply environment-over-YAML precedence.
- Create: `tests/backend/test_xhs_creator_upload_security.py` — cover safe media source and unsafe URL/path rejection.
- Modify: `backend/app/adapters/xhs/creator_api_adapter.py` — restrict upload input to `/api/files/media/<safe-name>`.
- Modify: `tests/backend/test_wechat_official_redfox_config.py` — cover Redfox base URL allowlist and real validation.
- Modify: `backend/app/services/wechat_official_redfox_service.py` — restrict base URL and call Redfox validation.
- Create: `tests/backend/test_publish_real_publish_confirmation.py` — cover explicit confirmation gate for publish/run-due.
- Modify: `backend/app/api/publish.py` — require `confirm_real_publish=true` for real publish.
- Modify: `backend/app/api/tasks.py` — require `confirm_real_publish=true` before executing due publish jobs.
- Modify: `frontend/src/lib/api.ts` — pass confirmation flags from frontend API helpers.
- Modify: `frontend/src/pages/platforms/xhs/publish-page.tsx` — add real publish confirmation UI before helper call.
- Modify: `frontend/src/pages/tasks/task-center-page.tsx` — add due-task real publish confirmation UI before helper call.

---

## Task 1: Align WeChat draft independence tests

**Files:**
- Modify: `tests/backend/test_wechat_official_redfox_collect.py`

- [ ] **Step 1: Update the outdated assertion**

Replace the old expectation that Redfox-created WeChat drafts have a `WechatOfficialDraftSource` row with the current product behavior:

```python
source = db.scalar(select(WechatOfficialDraftSource).where(WechatOfficialDraftSource.draft_id == draft_payload["id"]))
assert source is None
```

- [ ] **Step 2: Run targeted tests**

Run:

```bash
cd /e/小红书
py -3 -m pytest tests/backend/test_wechat_official_drafts.py tests/backend/test_wechat_official_redfox_collect.py
```

Expected: PASS.

---

## Task 2: Fix config precedence

**Files:**
- Modify: `tests/backend/test_config.py`
- Modify: `backend/app/core/config.py`

- [ ] **Step 1: Add failing tests**

Add tests that set `CONFIG_FILE` and sensitive env vars, clear the settings cache, and assert env vars win over YAML:

```python
def test_environment_secret_key_overrides_yaml(monkeypatch):
    from backend.app.core.config import get_settings

    monkeypatch.setenv("CONFIG_FILE", "config/production.yaml")
    monkeypatch.setenv("SECRET_KEY", "env-secret-for-test")
    get_settings.cache_clear()

    assert get_settings().secret_key == "env-secret-for-test"
    get_settings.cache_clear()


def test_environment_fernet_key_overrides_yaml(monkeypatch):
    from backend.app.core.config import get_settings

    monkeypatch.setenv("CONFIG_FILE", "config/production.yaml")
    monkeypatch.setenv("FERNET_KEY", "env-fernet-for-test")
    get_settings.cache_clear()

    assert get_settings().fernet_key == "env-fernet-for-test"
    get_settings.cache_clear()
```

- [ ] **Step 2: Verify RED**

Run:

```bash
cd /e/小红书
py -3 -m pytest tests/backend/test_config.py -q
```

Expected before implementation: at least one new test fails because YAML values override env values.

- [ ] **Step 3: Implement env-over-YAML merge**

In `backend/app/core/config.py`, load YAML values first, then overlay explicit environment variables for fields in `Settings.model_fields`.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
cd /e/小红书
py -3 -m pytest tests/backend/test_config.py -q
PYTHONPATH=/e/小红书 CONFIG_FILE=config/production.yaml SECRET_KEY=__ENV_SECRET_FOR_PRECEDENCE_TEST__ py -3 - <<'PY'
from backend.app.core.config import get_settings
get_settings.cache_clear()
print(get_settings().secret_key == "__ENV_SECRET_FOR_PRECEDENCE_TEST__")
PY
```

Expected: pytest passes and the Python snippet prints `True`.

---

## Task 3: Restrict Creator upload sources

**Files:**
- Create: `tests/backend/test_xhs_creator_upload_security.py`
- Modify: `backend/app/adapters/xhs/creator_api_adapter.py`

- [ ] **Step 1: Add failing tests**

Tests should call `XhsCreatorApiAdapter._resolve_file_data()` directly and assert:

```python
import pytest

from backend.app.adapters.xhs.creator_api_adapter import XhsCreatorApiAdapter


def test_creator_upload_rejects_remote_url():
    with pytest.raises(ValueError, match="Only server-managed media files"):
        XhsCreatorApiAdapter._resolve_file_data("https://example.com/image.jpg")


def test_creator_upload_rejects_local_path(tmp_path):
    local = tmp_path / "secret.txt"
    local.write_text("secret", encoding="utf-8")

    with pytest.raises(ValueError, match="Only server-managed media files"):
        XhsCreatorApiAdapter._resolve_file_data(str(local))


def test_creator_upload_rejects_traversal_media_path():
    with pytest.raises(ValueError, match="Invalid media file name"):
        XhsCreatorApiAdapter._resolve_file_data("/api/files/media/../secret.jpg")
```

Add one positive test by monkeypatching `get_settings().storage_dir` or using a temporary settings object so `/api/files/media/valid.jpg` reads only from the configured media directory.

- [ ] **Step 2: Verify RED**

Run:

```bash
cd /e/小红书
py -3 -m pytest tests/backend/test_xhs_creator_upload_security.py -q
```

Expected before implementation: unsafe URL/local path tests fail because current code accepts them or attempts to access them.

- [ ] **Step 3: Implement safe source resolver**

Allow only `/api/files/media/<basename>`. Reject remote URLs, local paths, path traversal, and path separators inside the media file name.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
cd /e/小红书
py -3 -m pytest tests/backend/test_xhs_creator_upload_security.py -q
```

Expected: PASS.

---

## Task 4: Harden Redfox config

**Files:**
- Modify: `tests/backend/test_wechat_official_redfox_config.py`
- Modify: `backend/app/services/wechat_official_redfox_service.py`

- [ ] **Step 1: Add failing tests**

Add tests that verify:

```python
# Saving http://127.0.0.1 is rejected.
# Saving https://evil.example is rejected.
# Saving https://redfox.hk/ is normalized to https://redfox.hk.
# validate_config calls a fake client's validate_key() and marks invalid when it raises.
```

- [ ] **Step 2: Verify RED**

Run:

```bash
cd /e/小红书
py -3 -m pytest tests/backend/test_wechat_official_redfox_config.py -q
```

Expected before implementation: new base URL and validate tests fail.

- [ ] **Step 3: Implement allowlist and real validation**

Restrict Redfox base URL to `https://redfox.hk`. Update `validate_config()` to instantiate the client and call `validate_key()`. Store user-safe failure messages only.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
cd /e/小红书
py -3 -m pytest tests/backend/test_wechat_official_redfox_config.py tests/backend/test_wechat_official_redfox_collect.py -q
```

Expected: PASS.

---

## Task 5: Require explicit confirmation for real XHS publishing

**Files:**
- Create: `tests/backend/test_publish_real_publish_confirmation.py`
- Modify: `backend/app/api/publish.py`
- Modify: `backend/app/api/tasks.py`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/pages/platforms/xhs/publish-page.tsx`
- Modify: `frontend/src/pages/tasks/task-center-page.tsx`

- [ ] **Step 1: Add failing backend tests**

Cover:

```python
# POST /api/publish/jobs/{job_id}/publish without confirm_real_publish=true returns 403 and fake adapter is not called.
# POST /api/tasks/run-due without confirm_real_publish=true returns 403 and due jobs stay pending.
```

- [ ] **Step 2: Verify RED**

Run:

```bash
cd /e/小红书
py -3 -m pytest tests/backend/test_publish_real_publish_confirmation.py -q
```

Expected before implementation: tests fail because current endpoints do not require confirmation.

- [ ] **Step 3: Implement backend gates**

Add `confirm_real_publish: bool = Query(False)` to both endpoints. If false, raise `HTTPException(status_code=403, detail="真实小红书发布需要显式确认")` before any adapter/cookie/action work.

- [ ] **Step 4: Update frontend helpers**

Change helpers to accept confirmation options:

```ts
export async function publishJobToCreator(jobId: number, options?: { confirmRealPublish?: boolean }): Promise<PublishJob> {
  const response = await http.post<PublishJob>(`/publish/jobs/${jobId}/publish`, null, {
    params: { confirm_real_publish: options?.confirmRealPublish === true },
  });
  return response.data;
}

export async function runDueTasks(platform = "xhs", options?: { confirmRealPublish?: boolean }): Promise<RunDueTasksResponse> {
  const response = await http.post<RunDueTasksResponse>("/tasks/run-due", null, {
    params: { platform, confirm_real_publish: options?.confirmRealPublish === true },
  });
  return response.data;
}
```

- [ ] **Step 5: Update frontend call sites**

Wrap publish and run-due actions in Ant Design confirmation UI, then call helpers with `{ confirmRealPublish: true }`.

- [ ] **Step 6: Verify GREEN**

Run:

```bash
cd /e/小红书
py -3 -m pytest tests/backend/test_publish_real_publish_confirmation.py -q
cd /e/小红书/frontend && ./node_modules/.bin/tsc --noEmit --pretty false
```

Expected: tests and TypeScript pass.

---

## Final verification

Run:

```bash
cd /e/小红书
py -3 -m pytest tests/backend/test_wechat_official_drafts.py tests/backend/test_wechat_official_redfox_collect.py
py -3 -m pytest tests/backend/test_config.py tests/backend/test_xhs_creator_upload_security.py tests/backend/test_wechat_official_redfox_config.py tests/backend/test_publish_real_publish_confirmation.py
cd /e/小红书/frontend && ./node_modules/.bin/tsc --noEmit --pretty false
```

If time allows:

```bash
cd /e/小红书
py -3 -m pytest tests/backend
```

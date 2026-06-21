# P0 Minimum Safety Hotfix Design

## Goal

Implement the minimum P0 safety hotfix needed to make the current workspace trustworthy again: restore the WeChat draft independence test baseline, make production configuration environment-overridable, block unsafe Creator uploads, restrict and truly validate Redfox configuration, and require explicit confirmation before real XHS publishing actions.

## Current baseline

The work continues inline in the root workspace because the current uncommitted WeChat official draft changes are the real baseline. A clean worktree would miss those edits and risk reversing the intended draft independence behavior.

## Non-goals

- No full task-center redesign.
- No database migrations.
- No full one-time confirmation-token table.
- No real XHS, WeChat, Redfox, or paid provider calls during validation.
- No unrelated UI redesign.
- No commit or push.

## Design

### 1. WeChat official draft independence

New WeChat official drafts remain independent copies in `ai_drafts`. New draft creation does not write `WechatOfficialDraftSource`, and API responses do not expose `source_note_id`. The historical `WechatOfficialDraftSource` model remains for compatibility but is not part of the new runtime path.

### 2. Configuration precedence

Configuration precedence becomes:

```text
environment variables > CONFIG_FILE YAML > config/default.yaml > Settings code defaults
```

`get_settings()` should load YAML defaults, then explicitly let environment variables override fields. Tests cover `SECRET_KEY` and `FERNET_KEY` because they control authentication and encrypted credentials.

### 3. Creator upload source restriction

Creator media upload accepts only server-managed media URLs of the form:

```text
/api/files/media/<safe-file-name>
```

The file name must be a basename and must not contain path separators or traversal. Arbitrary HTTP(S) URLs and arbitrary local paths are rejected before any network or filesystem access outside the media directory.

### 4. Redfox configuration hardening

Redfox `base_url` is restricted to the known Redfox host:

```text
https://redfox.hk
```

Tail slashes are normalized. Non-HTTPS, localhost, private/link-local IPs, and non-allowlisted hosts are rejected.

`validate_config()` must call the Redfox client validation path. It no longer marks a config valid just because the API key can be decrypted. Validation failures are stored as user-safe messages without storing the API key.

### 5. Explicit real publish confirmation

This hotfix uses the smallest safe server-side gate: explicit request confirmation.

- `POST /api/publish/jobs/{job_id}/publish` requires `confirm_real_publish=true`.
- `POST /api/tasks/run-due` requires `confirm_real_publish=true` before executing due publish jobs.

Missing confirmation returns `403` and must not call the Creator adapter. This is intentionally not the final confirmation-token design; it is a P0 guardrail that changes default behavior from dangerous to blocked.

## Testing strategy

Follow TDD per stage:

1. Observe/update failing test for WeChat draft independence.
2. Add config precedence tests, watch them fail, then implement.
3. Add Creator upload security tests, watch them fail, then implement.
4. Add Redfox config security/validation tests, watch them fail, then implement.
5. Add publish confirmation tests, watch them fail, then implement.

Final verification:

```bash
py -3 -m pytest tests/backend/test_wechat_official_drafts.py tests/backend/test_wechat_official_redfox_collect.py
py -3 -m pytest tests/backend/test_config.py tests/backend/test_xhs_creator_upload_security.py tests/backend/test_wechat_official_redfox_config.py tests/backend/test_publish_real_publish_confirmation.py
cd frontend && ./node_modules/.bin/tsc --noEmit --pretty false
```

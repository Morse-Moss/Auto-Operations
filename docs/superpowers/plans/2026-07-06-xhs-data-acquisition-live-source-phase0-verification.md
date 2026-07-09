# XHS Data Acquisition Live Source Phase 0 Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verify, without product development, whether the existing internal live-source pattern can safely support note search, note ranking, note detail, and keyword analysis data acquisition.

**Architecture:** This phase adds a small read-only verification harness under backend services/tests/docs. It reuses existing Huitun login cookies and `decrypt_huitun_ext_data` behavior, records sanitized endpoint findings, and produces a verification report that gates later implementation. It must not add user-facing product flows, database migrations, or automatic high-volume fetching.

**Tech Stack:** Python 3.10+, FastAPI service code conventions, SQLAlchemy account models for cookie lookup, requests, pytest, existing `backend.app.services.huitun_*` utilities.

---

## Scope

This plan covers only Stage 0 from `docs/superpowers/specs/2026-07-06-xhs-data-acquisition-live-source-design.md`.

It verifies:

1. Note search endpoint.
2. Note ranking endpoint.
3. Note detail endpoint.
4. Keyword analysis endpoint.

It does not implement:

- Data acquisition UI.
- New database tables.
- Candidate lists.
- Content library import.
- Task center integration.
- Analysis center changes.
- Multi-provider abstraction.

## File Structure

Create focused verification modules instead of mixing probing code into product services.

- Create: `backend/app/services/huitun_verification_probe.py`
  - Read-only helper functions for running one low-frequency request against candidate endpoints.
  - Uses existing cookie decoding and extData decryption utilities.
  - Returns sanitized summaries, never stores secrets.

- Create: `backend/app/services/huitun_verification_models.py`
  - Small dataclasses for endpoint verification results.
  - Keeps probe return shapes stable and testable.

- Create: `tests/backend/test_huitun_verification_probe.py`
  - Unit tests for extData handling, sanitization, and result classification.
  - Uses mocked HTTP responses only.

- Create: `docs/superpowers/specs/2026-07-06-xhs-data-acquisition-live-source-verification.md`
  - Human-readable verification report.
  - Records the checklist, method, and current endpoint status.
  - After the manual probe runs with a valid internal account, append sanitized endpoint findings and change each endpoint status to `ready`, `blocked`, `structure_changed`, or `failed`.

- Modify: `docs/superpowers/specs/2026-07-06-xhs-data-acquisition-live-source-design.md`
  - Add a short link to the verification report after it exists.

No database migration is allowed in this phase.

---

### Task 1: Add Verification Result Models

**Files:**
- Create: `backend/app/services/huitun_verification_models.py`
- Test: `tests/backend/test_huitun_verification_probe.py`

- [ ] **Step 1: Write the failing model classification tests**

Create `tests/backend/test_huitun_verification_probe.py` with these initial tests:

```python
from __future__ import annotations

from backend.app.services.huitun_verification_models import EndpointVerificationResult


def test_endpoint_verification_result_ready_when_required_fields_are_present():
    result = EndpointVerificationResult(
        endpoint_key="note.search",
        url="https://xhsapi.huitun.com/example",
        method="POST",
        status="ready",
        http_status=200,
        ext_data_present=True,
        ext_data_decrypted=True,
        core_fields={"title": True, "cover_url": True, "original_url": True},
        error_code="",
        error_message="",
        sanitized_sample={"title": "sample", "cover_url": "https://sns-img-hw.xhscdn.com/a"},
    )

    assert result.is_ready is True
    assert result.requires_followup is False


def test_endpoint_verification_result_blocked_when_status_is_blocked():
    result = EndpointVerificationResult(
        endpoint_key="note.detail",
        url="https://xhsapi.huitun.com/example",
        method="GET",
        status="blocked",
        http_status=403,
        ext_data_present=False,
        ext_data_decrypted=False,
        core_fields={"title": False},
        error_code="permission_denied",
        error_message="permission denied",
        sanitized_sample={},
    )

    assert result.is_ready is False
    assert result.requires_followup is True
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python -m pytest tests/backend/test_huitun_verification_probe.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'backend.app.services.huitun_verification_models'`.

- [ ] **Step 3: Implement verification dataclass**

Create `backend/app/services/huitun_verification_models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

VerificationStatus = Literal["ready", "blocked", "structure_changed", "failed"]


@dataclass(frozen=True)
class EndpointVerificationResult:
    endpoint_key: str
    url: str
    method: str
    status: VerificationStatus
    http_status: int | None
    ext_data_present: bool
    ext_data_decrypted: bool
    core_fields: dict[str, bool]
    error_code: str
    error_message: str
    sanitized_sample: dict[str, Any]

    @property
    def is_ready(self) -> bool:
        return self.status == "ready"

    @property
    def requires_followup(self) -> bool:
        return self.status != "ready"
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
python -m pytest tests/backend/test_huitun_verification_probe.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Do not commit unless the user explicitly requests commits. If commits are authorized, use:

```bash
git add backend/app/services/huitun_verification_models.py tests/backend/test_huitun_verification_probe.py
git commit -m "test: add huitun verification result model"
```

---

### Task 2: Add extData Extraction and Sanitization Helpers

**Files:**
- Modify: `backend/app/services/huitun_verification_probe.py`
- Modify: `tests/backend/test_huitun_verification_probe.py`

- [ ] **Step 1: Add failing tests for extData extraction and sanitization**

Append to `tests/backend/test_huitun_verification_probe.py`:

```python
from backend.app.services.huitun_verification_probe import extract_payload_data, sanitize_sample


def test_extract_payload_data_uses_plain_ext_data_dict():
    payload = {"status": 0, "extData": {"list": [{"title": "A"}]}}

    data, decrypted = extract_payload_data(payload)

    assert data == {"list": [{"title": "A"}]}
    assert decrypted is False


def test_extract_payload_data_falls_back_to_payload_when_ext_data_missing():
    payload = {"status": 0, "data": {"items": [{"title": "A"}]}}

    data, decrypted = extract_payload_data(payload)

    assert data == payload
    assert decrypted is False


def test_sanitize_sample_removes_secret_like_values():
    sample = {
        "title": "Example",
        "cookie": "a=b; token=secret",
        "xhsapiToken": "secret-token",
        "nested": {"authorization": "Bearer secret", "cover": "https://sns-img-hw.xhscdn.com/a"},
    }

    sanitized = sanitize_sample(sample)

    assert sanitized["title"] == "Example"
    assert sanitized["cookie"] == "<redacted>"
    assert sanitized["xhsapiToken"] == "<redacted>"
    assert sanitized["nested"]["authorization"] == "<redacted>"
    assert sanitized["nested"]["cover"] == "https://sns-img-hw.xhscdn.com/a"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python -m pytest tests/backend/test_huitun_verification_probe.py -v
```

Expected: FAIL with `ModuleNotFoundError` or missing functions.

- [ ] **Step 3: Implement helper module**

Create `backend/app/services/huitun_verification_probe.py`:

```python
from __future__ import annotations

from typing import Any

from backend.app.services.huitun_crypto import decrypt_huitun_ext_data

SECRET_KEYS = {
    "cookie",
    "cookies",
    "token",
    "xhsapitoken",
    "authorization",
    "auth",
    "secret",
    "password",
}


def _is_secret_key(key: str) -> bool:
    normalized = key.replace("_", "").replace("-", "").lower()
    return normalized in SECRET_KEYS or "token" in normalized or "cookie" in normalized


def sanitize_sample(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if _is_secret_key(str(key)):
                sanitized[str(key)] = "<redacted>"
            else:
                sanitized[str(key)] = sanitize_sample(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_sample(item) for item in value[:5]]
    if isinstance(value, str) and len(value) > 300:
        return value[:300] + "...<truncated>"
    return value


def extract_payload_data(payload: dict[str, Any]) -> tuple[Any, bool]:
    ext_data = payload.get("extData")
    if isinstance(ext_data, str):
        return decrypt_huitun_ext_data(ext_data), True
    if isinstance(ext_data, (dict, list)):
        return ext_data, False
    return payload, False
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
python -m pytest tests/backend/test_huitun_verification_probe.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Do not commit unless the user explicitly requests commits. If commits are authorized, use:

```bash
git add backend/app/services/huitun_verification_probe.py tests/backend/test_huitun_verification_probe.py
git commit -m "test: add huitun verification sanitizers"
```

---

### Task 3: Add Response Classification

**Files:**
- Modify: `backend/app/services/huitun_verification_probe.py`
- Modify: `tests/backend/test_huitun_verification_probe.py`

- [ ] **Step 1: Add failing classification tests**

Append to `tests/backend/test_huitun_verification_probe.py`:

```python
from backend.app.services.huitun_verification_probe import classify_payload


def test_classify_payload_ready_when_core_fields_exist():
    result = classify_payload(
        endpoint_key="note.rank",
        url="https://xhsapi.huitun.com/example",
        method="POST",
        http_status=200,
        payload={"extData": {"items": [{"title": "A", "coverUrl": "https://sns-img-hw.xhscdn.com/a", "noteUrl": "https://www.xiaohongshu.com/explore/abc"}]}},
        required_fields={"title": ["title"], "cover_url": ["coverUrl", "cover"], "original_url": ["noteUrl", "url"]},
    )

    assert result.status == "ready"
    assert result.ext_data_present is True
    assert result.core_fields == {"title": True, "cover_url": True, "original_url": True}


def test_classify_payload_structure_changed_when_required_fields_missing():
    result = classify_payload(
        endpoint_key="note.search",
        url="https://xhsapi.huitun.com/example",
        method="POST",
        http_status=200,
        payload={"status": 0, "extData": {"items": [{"unknown": "A"}]}},
        required_fields={"title": ["title"], "cover_url": ["coverUrl"]},
    )

    assert result.status == "structure_changed"
    assert result.core_fields == {"title": False, "cover_url": False}
    assert result.error_code == "missing_core_fields"


def test_classify_payload_blocked_on_auth_status():
    result = classify_payload(
        endpoint_key="note.detail",
        url="https://xhsapi.huitun.com/example",
        method="POST",
        http_status=403,
        payload={"status": 1001, "message": "请先登录"},
        required_fields={"title": ["title"]},
    )

    assert result.status == "blocked"
    assert result.error_code == "login_or_permission_required"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python -m pytest tests/backend/test_huitun_verification_probe.py -v
```

Expected: FAIL with missing `classify_payload`.

- [ ] **Step 3: Implement classification**

Append to `backend/app/services/huitun_verification_probe.py`:

```python
from backend.app.services.huitun_verification_models import EndpointVerificationResult


def _first_dict(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        for key in ("items", "list", "records", "rows", "data", "result"):
            nested = value.get(key)
            found = _first_dict(nested)
            if found is not None:
                return found
        return value
    if isinstance(value, list):
        for item in value:
            found = _first_dict(item)
            if found is not None:
                return found
    return None


def _has_any_key(sample: dict[str, Any], keys: list[str]) -> bool:
    lowered = {str(key).lower(): value for key, value in sample.items()}
    for key in keys:
        if key in sample or key.lower() in lowered:
            return True
    return False


def classify_payload(
    *,
    endpoint_key: str,
    url: str,
    method: str,
    http_status: int | None,
    payload: dict[str, Any],
    required_fields: dict[str, list[str]],
) -> EndpointVerificationResult:
    status_code = payload.get("status") or payload.get("code")
    if http_status in {401, 403} or status_code in {1001, 401, 403}:
        return EndpointVerificationResult(
            endpoint_key=endpoint_key,
            url=url,
            method=method,
            status="blocked",
            http_status=http_status,
            ext_data_present="extData" in payload,
            ext_data_decrypted=False,
            core_fields={field: False for field in required_fields},
            error_code="login_or_permission_required",
            error_message=str(payload.get("message") or payload.get("msg") or "login or permission required"),
            sanitized_sample=sanitize_sample(payload),
        )

    ext_data_present = "extData" in payload
    try:
        data, decrypted = extract_payload_data(payload)
    except Exception as exc:
        return EndpointVerificationResult(
            endpoint_key=endpoint_key,
            url=url,
            method=method,
            status="failed",
            http_status=http_status,
            ext_data_present=ext_data_present,
            ext_data_decrypted=False,
            core_fields={field: False for field in required_fields},
            error_code="ext_data_decrypt_failed",
            error_message=str(exc),
            sanitized_sample=sanitize_sample(payload),
        )

    sample = _first_dict(data) or {}
    core_fields = {field: _has_any_key(sample, keys) for field, keys in required_fields.items()}
    all_present = all(core_fields.values())
    return EndpointVerificationResult(
        endpoint_key=endpoint_key,
        url=url,
        method=method,
        status="ready" if all_present else "structure_changed",
        http_status=http_status,
        ext_data_present=ext_data_present,
        ext_data_decrypted=decrypted,
        core_fields=core_fields,
        error_code="" if all_present else "missing_core_fields",
        error_message="" if all_present else "One or more required fields were not found in the response sample.",
        sanitized_sample=sanitize_sample(sample),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
python -m pytest tests/backend/test_huitun_verification_probe.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Do not commit unless the user explicitly requests commits. If commits are authorized, use:

```bash
git add backend/app/services/huitun_verification_probe.py tests/backend/test_huitun_verification_probe.py
git commit -m "test: classify huitun verification responses"
```

---

### Task 4: Add Manual Probe Runner Function

**Files:**
- Modify: `backend/app/services/huitun_verification_probe.py`
- Modify: `tests/backend/test_huitun_verification_probe.py`

- [ ] **Step 1: Add failing test with mocked session**

Append to `tests/backend/test_huitun_verification_probe.py`:

```python
from backend.app.services.huitun_verification_probe import ProbeEndpoint, run_probe_endpoint


class FakeResponse:
    status_code = 200

    def json(self):
        return {"status": 0, "extData": {"items": [{"title": "A", "coverUrl": "https://sns-img-hw.xhscdn.com/a"}]}}

    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, params=None, json=None, timeout=None):
        self.calls.append(("POST", url, params, json, timeout))
        return FakeResponse()


def test_run_probe_endpoint_posts_and_classifies_payload():
    session = FakeSession()
    endpoint = ProbeEndpoint(
        endpoint_key="note.search",
        url="https://xhsapi.huitun.com/example",
        method="POST",
        params={"_t": 1},
        json_body={"keyword": "浴缸"},
        required_fields={"title": ["title"], "cover_url": ["coverUrl"]},
    )

    result = run_probe_endpoint(session=session, endpoint=endpoint)

    assert result.status == "ready"
    assert session.calls == [("POST", "https://xhsapi.huitun.com/example", {"_t": 1}, {"keyword": "浴缸"}, 20)]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python -m pytest tests/backend/test_huitun_verification_probe.py -v
```

Expected: FAIL with missing `ProbeEndpoint` or `run_probe_endpoint`.

- [ ] **Step 3: Implement probe runner**

Append to `backend/app/services/huitun_verification_probe.py`:

```python
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProbeEndpoint:
    endpoint_key: str
    url: str
    method: str
    required_fields: dict[str, list[str]]
    params: dict[str, Any] = field(default_factory=dict)
    json_body: dict[str, Any] = field(default_factory=dict)


def run_probe_endpoint(*, session: Any, endpoint: ProbeEndpoint) -> EndpointVerificationResult:
    method = endpoint.method.upper()
    try:
        if method == "POST":
            response = session.post(endpoint.url, params=endpoint.params, json=endpoint.json_body, timeout=20)
        elif method == "GET":
            response = session.get(endpoint.url, params=endpoint.params, timeout=20)
        else:
            return EndpointVerificationResult(
                endpoint_key=endpoint.endpoint_key,
                url=endpoint.url,
                method=method,
                status="failed",
                http_status=None,
                ext_data_present=False,
                ext_data_decrypted=False,
                core_fields={field_name: False for field_name in endpoint.required_fields},
                error_code="unsupported_method",
                error_message=f"Unsupported method: {method}",
                sanitized_sample={},
            )
        http_status = int(getattr(response, "status_code", 0) or 0)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("response JSON is not an object")
        return classify_payload(
            endpoint_key=endpoint.endpoint_key,
            url=endpoint.url,
            method=method,
            http_status=http_status,
            payload=payload,
            required_fields=endpoint.required_fields,
        )
    except Exception as exc:
        return EndpointVerificationResult(
            endpoint_key=endpoint.endpoint_key,
            url=endpoint.url,
            method=method,
            status="failed",
            http_status=getattr(locals().get("response", None), "status_code", None),
            ext_data_present=False,
            ext_data_decrypted=False,
            core_fields={field_name: False for field_name in endpoint.required_fields},
            error_code="request_failed",
            error_message=str(exc),
            sanitized_sample={},
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
python -m pytest tests/backend/test_huitun_verification_probe.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Do not commit unless the user explicitly requests commits. If commits are authorized, use:

```bash
git add backend/app/services/huitun_verification_probe.py tests/backend/test_huitun_verification_probe.py
git commit -m "test: add huitun endpoint probe runner"
```

---

### Task 5: Document Verified Endpoint Checklist

**Files:**
- Create: `docs/superpowers/specs/2026-07-06-xhs-data-acquisition-live-source-verification.md`
- Modify: `docs/superpowers/specs/2026-07-06-xhs-data-acquisition-live-source-design.md`

- [ ] **Step 1: Create verification report document**

Create `docs/superpowers/specs/2026-07-06-xhs-data-acquisition-live-source-verification.md`:

```markdown
# 小红书数据获取低风险数据源接口验证记录

## 1. 验证目标

本文件记录 `2026-07-06-xhs-data-acquisition-live-source-design.md` 阶段 0 的接口验证结果。

验证范围：

1. 笔记搜索。
2. 笔记榜单。
3. 笔记详情。
4. 关键词分析。

验证原则：

- 只读验证。
- 使用低频请求。
- 不批量抓取。
- 不绕过会员权限。
- 不写入业务库。
- 不暴露供应商名称给普通用户。
- 不保存 cookie、token、明文账号信息。

## 2. 通用验证项

每个 endpoint 必须记录：

| 验证项 | 结果 |
|---|---|
| endpoint key |  |
| URL |  |
| method |  |
| 是否需要登录态 |  |
| 是否返回 JSON |  |
| 是否存在 extData |  |
| extData 是否可用现有函数解密 |  |
| 是否能拿标题 |  |
| 是否能拿封面 URL |  |
| 是否能拿原文链接或 note id |  |
| 是否能识别权限限制 |  |
| 低频请求是否正常 |  |
| 结论 | pending |

## 3. 笔记搜索

状态：pending

记录：尚未验证。

## 4. 笔记榜单

状态：pending

记录：页面 DOM 已确认榜单可见封面 URL，例如 `sns-img-hw.xhscdn.com`。接口 endpoint 尚未验证。

## 5. 笔记详情

状态：pending

记录：尚未验证。

## 6. 关键词分析

状态：pending

记录：页面可见关键词分析字段包括笔记总数、预估阅读、商业笔记、互动总量、相关笔记、相关热词和相关直播。接口 endpoint 尚未验证。

## 7. 阶段 0 结论

当前结论：blocked_until_endpoint_probe。

进入功能开发前，必须将需要开发的 endpoint 状态改为 ready，并补齐字段映射。
```

- [ ] **Step 2: Link verification report from design spec**

Modify `docs/superpowers/specs/2026-07-06-xhs-data-acquisition-live-source-design.md` section `13. 接口验证闸门` by adding this sentence after “验证记录写入本 spec 附录或单独验证文档。”:

```markdown
阶段 0 验证记录文件：`docs/superpowers/specs/2026-07-06-xhs-data-acquisition-live-source-verification.md`。
```

- [ ] **Step 3: Check markdown contains no placeholder wording that claims completion**

Run:

```bash
python - <<'PY'
from pathlib import Path
p = Path('docs/superpowers/specs/2026-07-06-xhs-data-acquisition-live-source-verification.md')
text = p.read_text(encoding='utf-8')
assert '状态：pending' in text
assert '接口 endpoint 尚未验证' in text
assert '结论 | pending' in text
print('verification doc is explicit about pending status')
PY
```

Expected: `verification doc is explicit about pending status`.

- [ ] **Step 4: Commit**

Do not commit unless the user explicitly requests commits. If commits are authorized, use:

```bash
git add docs/superpowers/specs/2026-07-06-xhs-data-acquisition-live-source-design.md docs/superpowers/specs/2026-07-06-xhs-data-acquisition-live-source-verification.md
git commit -m "docs: add data acquisition connector verification record"
```

---

### Task 6: Run Focused Verification Tests

**Files:**
- Test: `tests/backend/test_huitun_verification_probe.py`

- [ ] **Step 1: Run focused tests**

Run:

```bash
python -m pytest tests/backend/test_huitun_verification_probe.py -v
```

Expected: all tests PASS.

- [ ] **Step 2: Run existing crypto-related tests**

Run:

```bash
python -m pytest tests/backend/test_legacy_keyword_detail_recovery.py -v
```

Expected: PASS. If this file does not include direct crypto coverage in the current checkout, record the actual output and do not claim crypto regression coverage from it.

- [ ] **Step 3: Run backend test suite only if focused tests pass**

Run:

```bash
python -m pytest tests/backend
```

Expected: PASS, or report exact failures.

- [ ] **Step 4: Commit**

Do not commit unless the user explicitly requests commits. If commits are authorized, use:

```bash
git status --short
git add backend/app/services/huitun_verification_models.py backend/app/services/huitun_verification_probe.py tests/backend/test_huitun_verification_probe.py docs/superpowers/specs/2026-07-06-xhs-data-acquisition-live-source-design.md docs/superpowers/specs/2026-07-06-xhs-data-acquisition-live-source-verification.md
git commit -m "test: add live source connector verification harness"
```

---

### Task 7: Manual Endpoint Probe Procedure

**Files:**
- Update after manual run: `docs/superpowers/specs/2026-07-06-xhs-data-acquisition-live-source-verification.md`

This task is intentionally manual because endpoint discovery requires an authenticated internal account and should not be run as a hidden background crawler.

- [ ] **Step 1: Open browser devtools or controlled CDP session**

Use the temporary browser profile already used for authenticated page inspection, or start a fresh controlled browser. Keep interaction low-frequency.

- [ ] **Step 2: Identify endpoint candidates one by one**

For each page, perform one user-like action and inspect the network request:

```text
笔记搜索: 输入 one keyword and submit once.
笔记榜单: open one rank page with default filters.
笔记详情: open one visible note detail once.
关键词分析: run one keyword analysis once.
```

- [ ] **Step 3: Run the probe manually against one candidate endpoint**

Use an interactive Python shell or a temporary one-off script that imports:

```python
from backend.app.services.huitun_verification_probe import ProbeEndpoint, run_probe_endpoint
from backend.app.services.huitun_live_keyword_source import _session_from_cookie_text
```

Use the saved internal account cookie from the application database only in the local environment. Do not paste cookie values into docs, code, or chat.

- [ ] **Step 4: Record sanitized findings**

For each endpoint, record only:

```text
endpoint key
method
parameter names, not secret values
extData present: yes/no
extData decrypted: yes/no
core fields present
permission behavior
ready/blocked/structure_changed/failed
```

- [ ] **Step 5: Update verification report conclusion**

Change each endpoint section in `docs/superpowers/specs/2026-07-06-xhs-data-acquisition-live-source-verification.md` from `pending` to one of:

```text
ready
blocked
structure_changed
failed
```

Only endpoints marked `ready` may enter the later implementation plan.

---

## Self-Review Checklist

- Spec coverage:
  - Stage 0 endpoint verification is covered by Tasks 1-7.
  - No product UI, migrations, content import, or task center integration is implemented in this phase.
  - Existing extData behavior is reused, not rewritten.
  - Verification report gates later development.

- Placeholder scan:
  - The verification document intentionally uses `pending` for endpoint status before manual validation.
  - No task says “implement later” as an instruction for code work.
  - Manual task records exact allowed statuses and fields.

- Type consistency:
  - `EndpointVerificationResult`, `ProbeEndpoint`, `extract_payload_data`, `sanitize_sample`, `classify_payload`, and `run_probe_endpoint` are defined before use.
  - Status strings match `VerificationStatus`.
  - Required fields are represented as `dict[str, list[str]]` consistently.

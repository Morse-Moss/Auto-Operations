# XHS Source Image Auto-Completion Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the content-library `自动补全原文图片` action use an automatically selected authenticated XHS PC account, while giving a clear login-required error when no usable account exists.

**Architecture:** Keep the existing note-assets endpoint and persistence path, but replace its anonymous page fetch with a focused authenticated source-image service. The service selects eligible PC accounts, calls the existing `XhsPcApiAdapter`, normalizes current snake_case and camelCase image payloads through the source-image extractor, and returns structured failures. The frontend stops invoking the clipboard script implicitly and displays the backend's actionable message.

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy, pytest, React, TypeScript, Vite, Ant Design

**Commit policy:** The repository forbids commits without explicit user authorization. Each task ends with a diff checkpoint instead of an automatic commit.

---

## File Map

- Create `backend/app/services/xhs_source_image_import_service.py`: authenticated PC account selection, clean note URL construction, provider failure classification, and detail-image retrieval.
- Modify `backend/app/services/xhs_source_image_extractor.py`: add payload-level extraction with snake_case/camelCase parity.
- Modify `backend/app/api/notes.py`: route automatic imports through the authenticated service, preserve explicit `image_urls` page-payload behavior, return structured errors, and persist safe summaries.
- Modify `frontend/src/pages/platforms/xhs/xhs-content-library-adapter.ts`: display structured error messages and remove implicit page-script fallback from the automatic action.
- Modify `tests/backend/test_xhs_source_image_extractor.py`: payload normalization regression coverage.
- Modify `tests/backend/test_note_image_localization.py`: account selection, provider behavior, API error contract, persistence, and secret-sanitization coverage.
- Modify `tests/backend/test_xhs_content_library_image_localization_ui.py`: automatic/manual action separation contract.
- Keep `frontend/src/pages/platforms/xhs/discovery-page.tsx` and account-management files untouched.

### Task 1: Normalize XHS Detail Image Payloads

**Files:**
- Modify: `backend/app/services/xhs_source_image_extractor.py`
- Test: `tests/backend/test_xhs_source_image_extractor.py`

- [ ] **Step 1: Write failing payload-variant tests**

Add the import and tests below:

```python
from backend.app.services.xhs_source_image_extractor import (
    canonical_xhs_image_key,
    extract_xhs_note_image_urls_from_html,
    extract_xhs_note_image_urls_from_payload,
    is_xhs_note_image_url,
)


def test_extracts_images_from_snake_and_camel_case_detail_payloads():
    payload = {
        "data": {
            "items": [{
                "note_card": {
                    "image_list": [
                        {"info_list": [{"image_scene": "WB_DFT", "url": "https://sns-img-hw.xhscdn.com/notes_pre_post/snake"}]},
                        {"infoList": [{"imageScene": "WB_DFT", "url": "https://sns-img-hw.xhscdn.com/notes_pre_post/camel"}]},
                        {"url_default": "https://sns-img-hw.xhscdn.com/notes_pre_post/default-snake"},
                        {"urlDefault": "https://sns-img-hw.xhscdn.com/notes_pre_post/default-camel"},
                    ]
                }
            }]
        }
    }

    assert extract_xhs_note_image_urls_from_payload(payload) == [
        "https://sns-img-hw.xhscdn.com/notes_pre_post/snake",
        "https://sns-img-hw.xhscdn.com/notes_pre_post/camel",
        "https://sns-img-hw.xhscdn.com/notes_pre_post/default-snake",
        "https://sns-img-hw.xhscdn.com/notes_pre_post/default-camel",
    ]


def test_payload_extractor_rejects_avatar_and_dedupes_cdn_variants():
    payload = {
        "imageList": [
            {"url": "https://sns-webpic-qc.xhscdn.com/path/notes_pre_post/same!nd_dft_wlteh_webp_3"},
            {"url": "https://sns-img-hw.xhscdn.com/notes_pre_post/same"},
            {"url": "https://sns-avatar-qc.xhscdn.com/avatar/not-a-note-image"},
        ]
    }

    assert extract_xhs_note_image_urls_from_payload(payload) == [
        "https://sns-webpic-qc.xhscdn.com/path/notes_pre_post/same"
    ]
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
py -X utf8 -m pytest tests/backend/test_xhs_source_image_extractor.py -q
```

Expected: collection fails because `extract_xhs_note_image_urls_from_payload` does not exist.

- [ ] **Step 3: Implement one shared recursive payload extractor**

Add a public function that delegates URL validation and deduplication to the existing helpers:

```python
IMAGE_LIST_KEYS = ("image_list", "imageList", "images")
IMAGE_VALUE_KEYS = (
    "url_default", "urlDefault", "url_pre", "urlPre", "url",
    "trace_id", "traceId", "file_id", "fileId",
)
IMAGE_INFO_KEYS = ("info_list", "infoList", "url_list", "urlList")


def extract_xhs_note_image_urls_from_payload(payload: Any) -> list[str]:
    urls: list[str] = []

    def walk(value: Any, depth: int = 0, in_image_context: bool = False) -> None:
        if value is None or depth > 10 or len(urls) >= MAX_SOURCE_IMAGES * 4:
            return
        if isinstance(value, str):
            if in_image_context:
                candidate = _image_url_from_value(value)
                if candidate:
                    urls.append(candidate)
            return
        if isinstance(value, list):
            for item in value:
                walk(item, depth + 1, in_image_context)
            return
        if not isinstance(value, dict):
            return

        image_context = in_image_context or any(key in value for key in IMAGE_LIST_KEYS + IMAGE_INFO_KEYS)
        for key in IMAGE_VALUE_KEYS:
            candidate = _image_url_from_value(str(value.get(key) or ""))
            if image_context and candidate:
                urls.append(candidate)
        for key, child in value.items():
            walk(child, depth + 1, image_context or key in IMAGE_LIST_KEYS or key in IMAGE_INFO_KEYS)

    walk(payload)
    return _unique_image_urls(urls)
```

Refactor `extract_xhs_note_image_urls_from_html` to call this function for parsed initial state before its existing raw-HTML fallback. Do not weaken `is_xhs_note_image_url`.

- [ ] **Step 4: Run extractor tests and verify GREEN**

Run:

```powershell
py -X utf8 -m pytest tests/backend/test_xhs_source_image_extractor.py -q
```

Expected: all extractor tests pass, including the two new payload tests.

- [ ] **Step 5: Review the scoped diff**

Run:

```powershell
git diff --check
git diff -- backend/app/services/xhs_source_image_extractor.py tests/backend/test_xhs_source_image_extractor.py
```

Expected: no whitespace errors and no unrelated parser changes.

### Task 2: Select Authenticated PC Accounts and Fetch Note Detail

**Files:**
- Create: `backend/app/services/xhs_source_image_import_service.py`
- Test: `tests/backend/test_note_image_localization.py`

- [ ] **Step 1: Add test helpers for PC accounts and fake adapters**

Extend the test imports:

```python
from backend.app.core.security import create_access_token, encrypt_text, hash_password
from backend.app.models import AccountCookieVersion, Note, NoteAsset, PlatformAccount, User
from backend.app.api.platforms.xhs.pc import get_xhs_pc_api_adapter_factory
from backend.app.services.xhs_source_image_import_service import (
    SourceImageDetailError,
    fetch_authenticated_source_images,
)
```

Add a helper that creates an account without exposing cookie text in assertions:

```python
def add_pc_account(db, *, user_id: int, nickname: str, status: str = "active", with_cookie: bool = True):
    account = PlatformAccount(
        user_id=user_id,
        platform="xhs",
        sub_type="pc",
        external_user_id=f"pc-{nickname}",
        nickname=nickname,
        status=status,
    )
    db.add(account)
    db.flush()
    if with_cookie:
        db.add(AccountCookieVersion(
            platform_account_id=account.id,
            encrypted_cookies=encrypt_text(f"a1={nickname}; web_session={nickname}"),
        ))
        db.flush()
    return account
```

- [ ] **Step 2: Write failing account-selection tests**

Add tests that call the service directly with a fake adapter factory:

```python
def test_authenticated_source_import_prefers_bound_pc_account_and_strips_query_token():
    SessionLocal = override_database()
    db = SessionLocal()
    try:
        user = User(username="source-bound", password_hash=hash_password("secret123"))
        db.add(user); db.flush()
        bound = add_pc_account(db, user_id=user.id, nickname="bound")
        add_pc_account(db, user_id=user.id, nickname="fallback")
        note = Note(user_id=user.id, platform_account_id=bound.id, platform="xhs", note_id="note-real")
        db.add(note); db.commit()
        calls = []

        class FakeAdapter:
            def __init__(self, cookies): self.cookies = cookies
            def get_note_info(self, url):
                calls.append((self.cookies, url))
                return True, "ok", {"image_list": [{"url": "https://sns-img-hw.xhscdn.com/notes_pre_post/one"}]}

        result = fetch_authenticated_source_images(
            db=db,
            user_id=user.id,
            note=note,
            source_url="https://www.xiaohongshu.com/explore/note-real?xsec_token=expired&xsec_source=pc_feed",
            adapter_factory=FakeAdapter,
        )

        assert result.account_id == bound.id
        assert calls[0][1] == "https://www.xiaohongshu.com/explore/note-real"
        assert result.image_urls == ["https://sns-img-hw.xhscdn.com/notes_pre_post/one"]
        assert "expired" not in str(result)
    finally:
        db.close()
```

Add five separate tests using the same complete database setup pattern as the bound-account test:

| Test name | Accounts and adapter responses | Required assertion |
| --- | --- | --- |
| `test_authenticated_source_import_uses_newest_eligible_fallback_account` | The note is bound to `page_import`; create two active PC accounts with cookies, and make the newer account return a successful one-image payload. | The returned `account_id` is the newer PC account and the adapter is called once. |
| `test_authenticated_source_import_skips_ineligible_accounts` | Create expired, deleted, cross-user, and cookieless PC rows plus one eligible same-user PC row. | Only the eligible account's cookie marker reaches the fake adapter. |
| `test_authenticated_source_import_advances_only_after_login_failure` | First adapter call returns `False, "无登录信息，或登录信息为空", {}`; second returns a successful one-image payload. | Call order contains both accounts and the second account ID is returned. |
| `test_authenticated_source_import_does_not_rotate_after_rate_limit` | First adapter call returns a payload/message classified as `xhs_rate_limited`; a second eligible account also exists. | `SourceImageDetailError.code == "xhs_rate_limited"` and only the first account was called. |
| `test_authenticated_source_import_requires_login_when_no_candidate_exists` | The note is bound to `page_import`, and the user has no active PC account with cookies. | `SourceImageDetailError.code == "xhs_login_required"`, `status_code == 409`, and the adapter factory is never called. |

Use this complete assertion shape in the no-candidate test:

```python
adapter_calls = []

class UnexpectedAdapter:
    def __init__(self, _cookies):
        adapter_calls.append("constructed")

with pytest.raises(SourceImageDetailError) as exc_info:
    fetch_authenticated_source_images(
        db=db,
        user_id=user.id,
        note=note,
        source_url="https://www.xiaohongshu.com/explore/real-note-id",
        adapter_factory=UnexpectedAdapter,
    )

assert exc_info.value.code == "xhs_login_required"
assert exc_info.value.status_code == 409
assert adapter_calls == []
```

- [ ] **Step 3: Run account-selection tests and verify RED**

Run:

```powershell
py -X utf8 -m pytest tests/backend/test_note_image_localization.py -k "authenticated_source_import" -q
```

Expected: collection fails because the new service module and symbols do not exist.

- [ ] **Step 4: Implement the focused authenticated import service**

Create the module with these public contracts:

```python
from dataclasses import dataclass
import json
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.adapters.xhs.pc_api_adapter import XhsPcApiAdapter
from backend.app.core.security import decrypt_text
from backend.app.models import AccountCookieVersion, Note, PlatformAccount
from backend.app.services.xhs_crawl_quality_service import search_failure_kind
from backend.app.services.xhs_source_image_extractor import extract_xhs_note_image_urls_from_payload

LOGIN_REQUIRED_MESSAGE = "自动补全原文图片需要先登录小红书 PC 账号，请前往账号矩阵登录后重试。"


@dataclass(frozen=True)
class AuthenticatedSourceImages:
    account_id: int
    source_url: str
    image_urls: list[str]


class SourceImageDetailError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def fetch_authenticated_source_images(
    *,
    db: Session,
    user_id: int,
    note: Note,
    source_url: str,
    adapter_factory=XhsPcApiAdapter,
) -> AuthenticatedSourceImages:
    clean_url = _clean_note_detail_url(source_url, note.note_id)
    candidates = _eligible_pc_accounts(db, user_id=user_id, preferred_account_id=note.platform_account_id)
    if not candidates:
        raise SourceImageDetailError("xhs_login_required", LOGIN_REQUIRED_MESSAGE, 409)

    saw_login_failure = False
    for account, cookies in candidates:
        success, message, raw_payload = adapter_factory(cookies).get_note_info(clean_url)
        if success:
            image_urls = extract_xhs_note_image_urls_from_payload(raw_payload or {})
            if not image_urls:
                raise SourceImageDetailError("source_images_not_found", "原文详情未返回可补全的图片。", 422)
            return AuthenticatedSourceImages(account.id, clean_url, image_urls)
        kind = search_failure_kind(message or "", raw_payload)
        if kind == "xhs_account_expired":
            saw_login_failure = True
            continue
        if kind == "xhs_rate_limited":
            raise SourceImageDetailError("xhs_rate_limited", "小红书请求频率受限，请稍后重试。", 429)
        raise SourceImageDetailError("source_detail_failed", "原文详情获取失败，请稍后重试。", 502)

    if saw_login_failure:
        raise SourceImageDetailError("xhs_login_required", LOGIN_REQUIRED_MESSAGE, 409)
    raise SourceImageDetailError("source_detail_failed", "原文详情获取失败，请稍后重试。", 502)
```

Private helpers must:

- Convert encrypted JSON or cookie strings into a request cookie string.
- Query only same-user, `platform=xhs`, `sub_type=pc`, `status=active` accounts.
- Require a latest `AccountCookieVersion`.
- Put the preferred account first and order remaining accounts by `updated_at DESC, id DESC`.
- Build a clean `/explore/<note-id>` URL from `/explore/` or `/discovery/item/` paths and reject unsupported hosts/paths with `source_url_unavailable`.

- [ ] **Step 5: Run service tests and verify GREEN**

Run:

```powershell
py -X utf8 -m pytest tests/backend/test_note_image_localization.py -k "authenticated_source_import" -q
```

Expected: all authenticated source-import service tests pass.

- [ ] **Step 6: Review the service diff**

Run:

```powershell
git diff --check
git diff -- backend/app/services/xhs_source_image_import_service.py tests/backend/test_note_image_localization.py
```

Expected: no account status writes, no credential logging, and no discovery/account UI changes.

### Task 3: Route Automatic Imports Through the Authenticated Service

**Files:**
- Modify: `backend/app/api/notes.py`
- Test: `tests/backend/test_note_image_localization.py`

- [ ] **Step 1: Write failing API contract tests**

Add tests that create real database accounts/cookie versions and override the PC adapter dependency:

```python
def test_import_source_images_uses_authenticated_pc_detail_and_persists_safe_summary(monkeypatch):
    SessionLocal = override_database()
    try:
        user_id, note_id, headers = create_user_headers(SessionLocal, username="authenticated-api-import")
        db = SessionLocal()
        try:
            note = db.get(Note, note_id)
            account = add_pc_account(db, user_id=user_id, nickname="usable")
            note.platform_account_id = account.id
            note.note_id = "real-note-id"
            note.raw_json = {"note_url": "https://www.xiaohongshu.com/explore/real-note-id?xsec_token=secret"}
            db.commit()
        finally:
            db.close()

        class FakeAdapter:
            def __init__(self, _cookies): pass
            def get_note_info(self, url):
                assert url == "https://www.xiaohongshu.com/explore/real-note-id"
                return True, "ok", {"data": {"items": [{"note_card": {"image_list": [
                    {"info_list": [{"url": "https://sns-img-hw.xhscdn.com/notes_pre_post/a"}]},
                    {"url_default": "https://sns-img-hw.xhscdn.com/notes_pre_post/b"},
                ]}}]}}

        app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: FakeAdapter
        monkeypatch.setattr("backend.app.api.notes._download_asset", lambda url, *_args: url.rsplit("/", 1)[-1] + ".jpg")

        response = client.post(
            f"/api/notes/{note_id}/assets/import-source-images",
            headers=headers,
            json={"source_url": "https://www.xiaohongshu.com/explore/real-note-id?xsec_token=secret", "download": True},
        )

        assert response.status_code == 200
        assert response.json()["downloaded_count"] == 2
        db = SessionLocal()
        try:
            summary = db.get(Note, note_id).raw_json["source_image_import"]
            assert summary["status"] == "completed"
            assert summary["account_id"] == account.id
            assert "secret" not in str(summary)
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)
        app.dependency_overrides.pop(get_db, None)
```

Add a complete login-required endpoint test:

```python
def test_import_source_images_returns_structured_login_required_without_provider_call():
    SessionLocal = override_database()
    try:
        _user_id, note_id, headers = create_user_headers(SessionLocal, username="automatic-import-login-required")
        adapter_calls = []

        class UnexpectedAdapter:
            def __init__(self, _cookies):
                adapter_calls.append("constructed")

        app.dependency_overrides[get_xhs_pc_api_adapter_factory] = lambda: UnexpectedAdapter
        response = client.post(
            f"/api/notes/{note_id}/assets/import-source-images",
            headers=headers,
            json={"source_url": "https://www.xiaohongshu.com/explore/real-note-id", "download": True},
        )

        assert response.status_code == 409
        assert response.json()["detail"] == {
            "code": "xhs_login_required",
            "message": "自动补全原文图片需要先登录小红书 PC 账号，请前往账号矩阵登录后重试。",
        }
        assert adapter_calls == []
    finally:
        app.dependency_overrides.pop(get_xhs_pc_api_adapter_factory, None)
        app.dependency_overrides.pop(get_db, None)
```

Add the remaining endpoint cases with these exact inputs and outputs:

| Test name | Setup | Required assertion |
| --- | --- | --- |
| `test_import_source_images_returns_structured_not_found` | One active PC account with cookies; fake detail adapter returns `True, "ok", {"data": {"items": [{"note_card": {"image_list": []}}]}}`. | HTTP 422 with `detail.code == "source_images_not_found"`; no `NoteAsset` row is inserted. |
| `test_explicit_page_image_urls_still_import_without_pc_account` | Keep the default `page_import` note and submit one valid `image_urls` value directly. Monkeypatch `_download_asset` to return a local filename. | HTTP 200, `imported_count == 1`, and the PC adapter dependency is never constructed. |

For all structured errors, assert the exact response shape:

```python
assert response.status_code == 409
assert response.json()["detail"] == {
    "code": "xhs_login_required",
    "message": "自动补全原文图片需要先登录小红书 PC 账号，请前往账号矩阵登录后重试。",
}
```

- [ ] **Step 2: Run API tests and verify RED**

Run:

```powershell
py -X utf8 -m pytest tests/backend/test_note_image_localization.py -k "import_source_images" -q
```

Expected: authenticated automatic-import tests fail because the route still calls `fetch_xhs_note_image_urls`.

- [ ] **Step 3: Integrate the service without breaking page payloads**

Update the route shape:

```python
@router.post("/{note_id}/assets/import-source-images")
def import_source_image_assets(
    note_id: int,
    payload: ImportSourceImagesRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    adapter_factory=Depends(get_xhs_pc_api_adapter_factory),
):
    note = _get_owned_note(db, current_user, note_id)
    selected_account_id: int | None = None
    source_url = payload.source_url
    if payload.image_urls:
        source_urls = payload.image_urls
        source_url = _resolve_source_image_import_url(db, note, payload.source_url)
    else:
        if not payload.source_url:
            raise HTTPException(status_code=422, detail="source_url_or_image_urls_required")
        source_url = _resolve_source_image_import_url(db, note, payload.source_url, fail_on_unresolved=True)
        try:
            fetched = fetch_authenticated_source_images(
                db=db,
                user_id=current_user.id,
                note=note,
                source_url=source_url,
                adapter_factory=adapter_factory,
            )
        except SourceImageDetailError as exc:
            _record_source_image_import_terminal(note, source_url=source_url, status=exc.code, account_id=None)
            db.commit()
            raise HTTPException(
                status_code=exc.status_code,
                detail={"code": exc.code, "message": exc.message},
            ) from exc
        source_urls = fetched.image_urls
        source_url = fetched.source_url
        selected_account_id = fetched.account_id

    return _import_source_image_urls(
        db=db,
        note=note,
        user_id=current_user.id,
        source_urls=source_urls,
        source_url=source_url,
        download=payload.download,
        account_id=selected_account_id,
    )
```

Extend `_import_source_image_urls` with optional `account_id`. Always write a query-free summary, including when all images already existed. Derive status as `partial` when `failed_count > 0`, otherwise `completed`. Keep the existing item/count response fields unchanged.

Remove `fetch_xhs_note_image_urls` and `_note_known_source_image_urls` from the automatic branch only. Do not change the `page-payload` endpoint's token validation or explicit URL import behavior.

- [ ] **Step 4: Run API tests and verify GREEN**

Run:

```powershell
py -X utf8 -m pytest tests/backend/test_note_image_localization.py -q
```

Expected: all image localization/import tests pass.

- [ ] **Step 5: Run adjacent acquisition regressions**

Run:

```powershell
py -X utf8 -m pytest tests/backend/test_xhs_data_acquisition.py -k "import_source_images" -q
```

Expected: legacy data-acquisition URL resolution tests pass; update only expectations that intentionally change from anonymous fetch to authenticated detail retrieval.

- [ ] **Step 6: Review the API diff**

Run:

```powershell
git diff --check
git diff -- backend/app/api/notes.py tests/backend/test_note_image_localization.py tests/backend/test_xhs_data_acquisition.py
```

Expected: no SDK/signing edits, no stored credentials, and explicit page payload compatibility remains covered.

### Task 4: Make Frontend Errors Honest and Actionable

**Files:**
- Modify: `frontend/src/pages/platforms/xhs/xhs-content-library-adapter.ts`
- Test: `tests/backend/test_xhs_content_library_image_localization_ui.py`

- [ ] **Step 1: Replace the old fallback contract test with failing honesty tests**

Replace `test_xhs_source_image_completion_prepares_page_import_when_server_cannot_see_images` with:

```python
def test_xhs_source_image_completion_does_not_implicitly_copy_page_script():
    adapter_source = Path("frontend/src/pages/platforms/xhs/xhs-content-library-adapter.ts").read_text(encoding="utf-8")
    section = adapter_source[
        adapter_source.index("function renderImportSourceImagesButton"):
        adapter_source.index("function renderSystemAnalysisButton")
    ]

    assert "preparePageImportScript" not in section
    assert "createSavedNoteSourceImageImportScript" not in section
    assert "sendBeacon" not in section
    assert "已复制原文导入脚本" not in section
    assert "自动补全原文图片失败" in section
    assert all(term not in section for term in FORBIDDEN_USER_COPY)


def test_xhs_source_image_error_parser_reads_structured_detail_message():
    adapter_source = Path("frontend/src/pages/platforms/xhs/xhs-content-library-adapter.ts").read_text(encoding="utf-8")
    error_section = adapter_source[
        adapter_source.index("function getActionErrorMessage"):
        adapter_source.index("async function copyTextWithFallback")
    ]

    assert '"message" in detail' in error_section
    assert "detail.message" in error_section
```

Keep the existing assertion that `renderPageImageImportAssistButton` is present outside the automatic button section.

- [ ] **Step 2: Run UI contract tests and verify RED**

Run:

```powershell
py -X utf8 -m pytest tests/backend/test_xhs_content_library_image_localization_ui.py -q
```

Expected: tests fail because the automatic section still prepares and copies the script and structured detail is not parsed.

- [ ] **Step 3: Implement the minimal frontend behavior**

Update structured detail parsing:

```typescript
if (typeof responseData === "object" && responseData !== null && "detail" in responseData) {
  const detail = (responseData as { detail?: unknown }).detail;
  if (typeof detail === "string" && detail) return detail;
  if (typeof detail === "object" && detail !== null && "message" in detail) {
    const messageText = (detail as { message?: unknown }).message;
    if (typeof messageText === "string" && messageText) return messageText;
  }
}
```

Delete `preparePageImportScript` from `renderImportSourceImagesButton`. Handle outcomes directly:

```typescript
if (result.total_source_image_count === 0) {
  throw new Error("原文详情未返回可补全的图片。");
}

const summary = `原文图片补全完成：新增 ${result.imported_count} 张，已存在 ${result.skipped_count} 张，已保存 ${result.downloaded_count} 张，失败 ${result.failed_count} 张。`;
```

In `catch`, set `controller.setDetailError`, clear the action message, and call `message.error`. Do not call clipboard or script APIs. Leave `renderPageImageImportAssistButton` unchanged as an explicit manual action.

- [ ] **Step 4: Run UI contract tests and verify GREEN**

Run:

```powershell
py -X utf8 -m pytest tests/backend/test_xhs_content_library_image_localization_ui.py -q
```

Expected: all UI contract tests pass.

- [ ] **Step 5: Run frontend build**

Run:

```powershell
npm --prefix frontend run build
```

Expected: TypeScript and Vite build complete with exit code 0.

- [ ] **Step 6: Review the frontend diff**

Run:

```powershell
git diff --check
git diff -- frontend/src/pages/platforms/xhs/xhs-content-library-adapter.ts tests/backend/test_xhs_content_library_image_localization_ui.py
git diff --exit-code -- frontend/src/pages/platforms/xhs/discovery-page.tsx
```

Expected: no discovery-page diff and no implicit fallback in the automatic action.

### Task 5: Full Regression and Runtime Verification

**Files:**
- Verify all files listed in the File Map.
- Do not modify XHS SDK/signing files during this task.

- [ ] **Step 1: Run the focused backend suite**

Run:

```powershell
py -X utf8 -m pytest tests/backend/test_xhs_source_image_extractor.py tests/backend/test_note_image_localization.py tests/backend/test_xhs_content_library_image_localization_ui.py -q
```

Expected: all focused tests pass with zero failures.

- [ ] **Step 2: Run adjacent account-independent regressions**

Run:

```powershell
py -X utf8 -m pytest tests/backend/test_xhs_data_acquisition.py -k "import_source_images" -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Re-run frontend build from a clean command**

Run:

```powershell
npm --prefix frontend run build
```

Expected: exit code 0 with generated assets under `frontend/dist`.

- [ ] **Step 4: Restart only the task-specific verification backend when Python changed**

Do not stop or replace root `18080/18081` services without user authorization. Start temporary worktree services on non-standard ports when browser verification is required.

Expected: temporary backend `/api/health` returns `{"status":"ok","service":"spider-xhs"}`.

- [ ] **Step 5: Browser-check desktop and mobile states**

Using Playwright against the temporary frontend/backend pair:

- Confirm the content-library detail action still renders without overlap at desktop width.
- Confirm the action row wraps cleanly at mobile width.
- Intercept the import endpoint with a structured `xhs_login_required` response and confirm the full login instruction is visible.
- Intercept a successful response and confirm the count summary is visible.
- Confirm no clipboard API is called by the automatic action.
- Confirm browser console has no errors.

Expected: screenshots show readable controls and feedback at both widths; the automatic action makes one import request and no clipboard call.

- [ ] **Step 6: Perform one low-frequency live smoke test only when a testable active PC account is available**

Use a saved public image note owned by the current user. Invoke only the source-image import action, verify the asset count increases or existing images are reported, and verify no publish/comment/like/follow action occurs.

Expected: authenticated detail retrieval succeeds without reusing `xsec_token`; imported assets have local paths or explicit per-item download failures.

- [ ] **Step 7: Verify secrets and scope**

Run:

```powershell
rg -n "xsec_token|web_session|encrypted_cookies" backend/app/services/xhs_source_image_import_service.py backend/app/api/notes.py tests/backend/test_note_image_localization.py
git diff --check
git status --short
git diff --exit-code -- frontend/src/pages/platforms/xhs/discovery-page.tsx backend/app/api/platforms/xhs/crawl.py
```

Expected: production code references credentials only for decrypting in memory; no literal real token/cookie is present; excluded thread files have no diff.

- [ ] **Step 8: Report the exact delivery state**

Report:

- Current workspace path and branch.
- Focused test counts and frontend build result.
- Whether a live XHS smoke test ran and what it proved.
- Whether changes are only verified in a worktree or are present in root `master`.
- Whether root services were restarted.
- That no commit or push occurred unless the user explicitly authorized it.

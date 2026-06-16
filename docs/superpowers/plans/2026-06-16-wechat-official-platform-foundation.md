# WeChat Official Platform Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the微信公众号 platform foundation so it appears as a Beta workspace with local-only status APIs, fail-closed adapter skeleton, and a frontend dashboard, without integrating any real WeChat API.

**Architecture:** Treat `wechat_official` as an independent platform workspace. Backend registry declares Beta status and fail-closed capabilities; backend `/api/wechat-official/overview` returns static local readiness data; frontend route `/platforms/wechat-official/dashboard` renders a clear foundation-only dashboard. No database migration, no credentials, no external network calls.

**Tech Stack:** Python 3.10+, FastAPI, pytest, React, Vite, TypeScript, Ant Design, React Router.

---

## Context and Constraints

Read first:

- Spec: `docs/superpowers/specs/2026-06-16-wechat-official-platform-foundation-design.md`
- Platform registry: `backend/app/core/platforms.py`
- API router mounting: `backend/app/main.py`
- Existing platform tests: `tests/backend/test_platforms.py`
- Frontend routes: `frontend/src/app/router.tsx`
- Frontend API client: `frontend/src/lib/api.ts`
- Frontend fallback platforms: `frontend/src/lib/platforms.ts`
- Frontend types: `frontend/src/types/index.ts`

Hard constraints:

- Do not call WeChat APIs.
- Do not save AppID, AppSecret, Token, EncodingAESKey, cookies, or credentials.
- Do not add database tables or Alembic migrations.
- Do not copy or import GitHub open-source code.
- Do not modify XHS SDK/signature layers under `apis/`, `xhs_utils/`, or `static/`.
- Do not commit unless the user explicitly asks; project `CLAUDE.md` overrides the generic “frequent commits” guidance.

## File Structure

Create:

- `backend/app/adapters/wechat_official/__init__.py` — exports the fail-closed adapter and error.
- `backend/app/adapters/wechat_official/adapter.py` — local-only adapter skeleton; all external integration remains disabled.
- `backend/app/api/platforms/wechat_official/__init__.py` — exports the overview router.
- `backend/app/api/platforms/wechat_official/overview.py` — static overview/status API for the公众号 foundation workspace.
- `tests/backend/test_wechat_official_foundation.py` — backend tests for registry, adapter, and overview API.
- `frontend/src/pages/wechat-official/wechat-official-dashboard.tsx` — Beta foundation dashboard page.

Modify:

- `backend/app/core/platforms.py` — add微信公众号 capabilities and update `wechat_official` metadata from planned/disabled to beta/enabled.
- `backend/app/main.py` — mount the new `wechat_official` API router.
- `frontend/src/types/index.ts` — add `WechatOfficialOverview` types.
- `frontend/src/lib/api.ts` — add `fetchWechatOfficialOverview()`.
- `frontend/src/lib/platforms.ts` — update fallback `wechat_official` entry to match backend Beta metadata.
- `frontend/src/app/router.tsx` — add dashboard route.

---

### Task 1: Backend registry declares微信公众号 as Beta foundation platform

**Files:**

- Modify: `tests/backend/test_wechat_official_foundation.py`
- Modify: `backend/app/core/platforms.py`

- [ ] **Step 1: Write failing registry tests**

Create `tests/backend/test_wechat_official_foundation.py` with this initial content:

```python
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.core.platforms import PlatformId, get_platform
from backend.app.main import app


client = TestClient(app)


def _capabilities_by_key(platform_payload: dict) -> dict[str, dict]:
    return {item["key"]: item for item in platform_payload["capabilities"]}


def test_wechat_official_registry_is_beta_enabled_foundation_workspace():
    payload = get_platform(PlatformId.WECHAT_OFFICIAL).to_dict()

    assert payload["id"] == "wechat_official"
    assert payload["name_cn"] == "公众号"
    assert payload["name_en"] == "WeChat Official"
    assert payload["enabled"] is True
    assert payload["release_stage"] == "beta"
    assert payload["status"] == "beta"
    assert payload["region"] == "cn"
    assert payload["platform_type"] == "content"
    assert payload["default_route"] == "/platforms/wechat-official/dashboard"
    assert payload["adapter_key"] == "wechat_official"
    assert payload["risk_level"] == "medium"
    assert payload["auth_modes"] == ["none"]
    assert payload["accent_color"] == "#0a9b57"
    assert payload["icon"] == "wechat_official"


def test_wechat_official_capabilities_are_planned_or_blocked_and_publish_is_fail_closed():
    payload = get_platform("wechat_official").to_dict()
    capabilities = _capabilities_by_key(payload)

    assert capabilities["account.manage"] == {
        "key": "account.manage",
        "status": "planned",
        "risk": "medium",
        "requires_confirmation": False,
        "notes": "公众号账号配置待 GitHub 开源系统调研和微信官方 API 策略确认后接入；本轮不开放凭据输入。",
    }
    assert capabilities["content.library"]["status"] == "planned"
    assert capabilities["content.rewrite"]["status"] == "planned"
    assert capabilities["publish.dry_run"]["status"] == "planned"
    assert capabilities["publish.real_publish"] == {
        "key": "publish.real_publish",
        "status": "blocked",
        "risk": "high",
        "requires_confirmation": True,
        "notes": "公众号群发发布属于高风险动作；正式 QA、dry-run 和动作级确认机制完成前保持阻断。",
    }


def test_platform_registry_endpoint_exposes_wechat_official_beta_metadata():
    response = client.get("/api/platforms")

    assert response.status_code == 200
    payload = response.json()
    wechat = next(item for item in payload["items"] if item["id"] == "wechat_official")

    assert wechat["enabled"] is True
    assert wechat["release_stage"] == "beta"
    assert wechat["status"] == "beta"
    assert wechat["default_route"] == "/platforms/wechat-official/dashboard"
    assert wechat["adapter_key"] == "wechat_official"
    assert wechat["auth_modes"] == ["none"]
    assert _capabilities_by_key(wechat)["publish.real_publish"]["status"] == "blocked"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/backend/test_wechat_official_foundation.py -v
```

Expected: FAIL because `wechat_official` is still planned/disabled, has no `default_route`, has no `adapter_key`, and has no declared capabilities.

- [ ] **Step 3: Add微信公众号 capability list**

In `backend/app/core/platforms.py`, insert this block after `_XHS_CAPABILITIES` and before `_PLATFORMS`:

```python
_WECHAT_OFFICIAL_CAPABILITIES = [
    PlatformCapability(
        key=CapabilityKey.ACCOUNT_MANAGE,
        status=CapabilityStatus.PLANNED,
        risk=RiskLevel.MEDIUM,
        requires_confirmation=False,
        notes="公众号账号配置待 GitHub 开源系统调研和微信官方 API 策略确认后接入；本轮不开放凭据输入。",
    ),
    PlatformCapability(
        key=CapabilityKey.CONTENT_LIBRARY,
        status=CapabilityStatus.PLANNED,
        risk=RiskLevel.LOW,
        requires_confirmation=False,
        notes="公众号图文内容库待正式接入设计后实现；本轮只展示平台骨架状态。",
    ),
    PlatformCapability(
        key=CapabilityKey.CONTENT_REWRITE,
        status=CapabilityStatus.PLANNED,
        risk=RiskLevel.LOW,
        requires_confirmation=False,
        notes="公众号文章改写待内容模型确认后实现；本轮不生成或同步真实公众号草稿。",
    ),
    PlatformCapability(
        key=CapabilityKey.PUBLISH_DRY_RUN,
        status=CapabilityStatus.PLANNED,
        risk=RiskLevel.MEDIUM,
        requires_confirmation=False,
        notes="公众号发布 dry-run 待草稿箱、素材和群发 API 能力确认后设计；本轮不执行发布模拟。",
    ),
    PlatformCapability(
        key=CapabilityKey.PUBLISH_REAL_PUBLISH,
        status=CapabilityStatus.BLOCKED,
        risk=RiskLevel.HIGH,
        requires_confirmation=True,
        notes="公众号群发发布属于高风险动作；正式 QA、dry-run 和动作级确认机制完成前保持阻断。",
    ),
]
```

- [ ] **Step 4: Update微信公众号 platform metadata**

In `backend/app/core/platforms.py`, replace the existing `PlatformMeta` block for `PlatformId.WECHAT_OFFICIAL` with:

```python
    PlatformMeta(
        id=PlatformId.WECHAT_OFFICIAL,
        name_cn="公众号",
        name_en="WeChat Official",
        enabled=True,
        release_stage=ReleaseStage.BETA,
        region=PlatformRegion.CN,
        platform_type=PlatformType.CONTENT,
        accent_color="#0a9b57",
        icon="wechat_official",
        default_route="/platforms/wechat-official/dashboard",
        adapter_key="wechat_official",
        risk_level=RiskLevel.MEDIUM,
        auth_modes=[AuthMode.NONE],
        capabilities=_WECHAT_OFFICIAL_CAPABILITIES,
    ),
```

- [ ] **Step 5: Run registry tests to verify they pass**

Run:

```bash
pytest tests/backend/test_wechat_official_foundation.py -v
```

Expected: PASS for the three registry tests.

- [ ] **Step 6: Run existing platform tests for regression**

Run:

```bash
pytest tests/backend/test_platforms.py tests/backend/test_platform_capability_gate.py -v
```

Expected: PASS. If `test_planned_platform_status_uses_canonical_release_stage_and_legacy_status_alias` still checks Douyin, it should remain unaffected.

- [ ] **Step 7: Git checkpoint**

Do not commit unless the user explicitly asks. If the user has asked for commits, run:

```bash
git add backend/app/core/platforms.py tests/backend/test_wechat_official_foundation.py
git commit -m "feat: enable wechat official foundation registry"
```

---

### Task 2: Add fail-closed微信公众号 adapter skeleton

**Files:**

- Modify: `tests/backend/test_wechat_official_foundation.py`
- Create: `backend/app/adapters/wechat_official/__init__.py`
- Create: `backend/app/adapters/wechat_official/adapter.py`

- [ ] **Step 1: Add failing adapter tests**

Append this to `tests/backend/test_wechat_official_foundation.py`:

```python

def test_wechat_official_adapter_reports_local_foundation_status_without_external_integration():
    from backend.app.adapters.wechat_official import WechatOfficialAdapter

    adapter = WechatOfficialAdapter()
    status = adapter.get_status()

    assert adapter.supported_capabilities == set()
    assert status == {
        "platform_id": "wechat_official",
        "external_integration_enabled": False,
        "stage": "foundation_ready",
        "blocked_actions": [
            "真实授权",
            "素材上传",
            "草稿同步",
            "预览发送",
            "群发发布",
        ],
    }


def test_wechat_official_adapter_blocks_external_integration_attempts():
    from backend.app.adapters.wechat_official import WechatOfficialAdapter, WechatOfficialIntegrationDisabledError

    adapter = WechatOfficialAdapter()

    try:
        adapter.assert_external_integration_enabled("publish.real_publish")
    except WechatOfficialIntegrationDisabledError as exc:
        assert str(exc) == "微信公众号外部接入尚未启用：publish.real_publish 已被阻断。"
        assert exc.capability_key == "publish.real_publish"
    else:
        raise AssertionError("expected WechatOfficialIntegrationDisabledError")
```

- [ ] **Step 2: Run adapter tests to verify they fail**

Run:

```bash
pytest tests/backend/test_wechat_official_foundation.py::test_wechat_official_adapter_reports_local_foundation_status_without_external_integration tests/backend/test_wechat_official_foundation.py::test_wechat_official_adapter_blocks_external_integration_attempts -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'backend.app.adapters.wechat_official'`.

- [ ] **Step 3: Create adapter package export**

Create `backend/app/adapters/wechat_official/__init__.py`:

```python
from __future__ import annotations

from backend.app.adapters.wechat_official.adapter import (
    WechatOfficialAdapter,
    WechatOfficialIntegrationDisabledError,
)

__all__ = [
    "WechatOfficialAdapter",
    "WechatOfficialIntegrationDisabledError",
]
```

- [ ] **Step 4: Implement fail-closed adapter**

Create `backend/app/adapters/wechat_official/adapter.py`:

```python
from __future__ import annotations


BLOCKED_ACTIONS = [
    "真实授权",
    "素材上传",
    "草稿同步",
    "预览发送",
    "群发发布",
]


class WechatOfficialIntegrationDisabledError(RuntimeError):
    def __init__(self, capability_key: str) -> None:
        self.capability_key = capability_key
        super().__init__(f"微信公众号外部接入尚未启用：{capability_key} 已被阻断。")


class WechatOfficialAdapter:
    supported_capabilities: set[str] = set()

    def get_status(self) -> dict:
        return {
            "platform_id": "wechat_official",
            "external_integration_enabled": False,
            "stage": "foundation_ready",
            "blocked_actions": BLOCKED_ACTIONS,
        }

    def assert_external_integration_enabled(self, capability_key: str) -> None:
        raise WechatOfficialIntegrationDisabledError(capability_key)
```

- [ ] **Step 5: Run adapter tests to verify they pass**

Run:

```bash
pytest tests/backend/test_wechat_official_foundation.py::test_wechat_official_adapter_reports_local_foundation_status_without_external_integration tests/backend/test_wechat_official_foundation.py::test_wechat_official_adapter_blocks_external_integration_attempts -v
```

Expected: PASS.

- [ ] **Step 6: Run resolver regression tests**

Run:

```bash
pytest tests/backend/test_platform_adapter_resolver.py -v
```

Expected: PASS. The new adapter is not registered into resolver yet and should not alter existing resolver behavior.

- [ ] **Step 7: Git checkpoint**

Do not commit unless the user explicitly asks. If the user has asked for commits, run:

```bash
git add backend/app/adapters/wechat_official tests/backend/test_wechat_official_foundation.py
git commit -m "feat: add wechat official fail closed adapter"
```

---

### Task 3: Add local-only微信公众号 overview API

**Files:**

- Modify: `tests/backend/test_wechat_official_foundation.py`
- Create: `backend/app/api/platforms/wechat_official/__init__.py`
- Create: `backend/app/api/platforms/wechat_official/overview.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Add failing overview API test**

Append this to `tests/backend/test_wechat_official_foundation.py`:

```python

def test_wechat_official_overview_api_returns_foundation_status_and_research_gate():
    response = client.get("/api/wechat-official/overview")

    assert response.status_code == 200
    payload = response.json()

    assert payload["platform_id"] == "wechat_official"
    assert payload["stage"] == "foundation_ready"
    assert payload["external_integration_enabled"] is False
    assert payload["research_required_before_integration"] is True
    assert payload["research_topics"] == [
        "GitHub 微信公众号开源系统架构调研",
        "微信官方草稿箱、素材、群发、预览 API 能力边界确认",
        "凭据保存与加密策略确认",
        "真实群发风险与 QA 流程确认",
    ]
    assert payload["blocked_actions"] == [
        "真实授权",
        "素材上传",
        "草稿同步",
        "预览发送",
        "群发发布",
    ]

    capabilities = {item["key"]: item for item in payload["capabilities"]}
    assert capabilities["account.manage"] == {
        "key": "account.manage",
        "label": "账号配置",
        "status": "planned",
        "message": "正式接入前不开放 AppID/AppSecret 配置。",
    }
    assert capabilities["publish.real_publish"] == {
        "key": "publish.real_publish",
        "label": "群发发布",
        "status": "blocked",
        "message": "高风险动作，正式 QA、dry-run 和动作级确认机制完成前保持阻断。",
    }
```

- [ ] **Step 2: Run overview API test to verify it fails**

Run:

```bash
pytest tests/backend/test_wechat_official_foundation.py::test_wechat_official_overview_api_returns_foundation_status_and_research_gate -v
```

Expected: FAIL with 404 for `/api/wechat-official/overview`.

- [ ] **Step 3: Create router package export**

Create `backend/app/api/platforms/wechat_official/__init__.py`:

```python
from __future__ import annotations

from backend.app.api.platforms.wechat_official.overview import router

__all__ = ["router"]
```

- [ ] **Step 4: Implement local-only overview route**

Create `backend/app/api/platforms/wechat_official/overview.py`:

```python
from __future__ import annotations

from fastapi import APIRouter

from backend.app.adapters.wechat_official import WechatOfficialAdapter

router = APIRouter(prefix="/wechat-official", tags=["wechat-official"])


RESEARCH_TOPICS = [
    "GitHub 微信公众号开源系统架构调研",
    "微信官方草稿箱、素材、群发、预览 API 能力边界确认",
    "凭据保存与加密策略确认",
    "真实群发风险与 QA 流程确认",
]

CAPABILITY_OVERVIEW = [
    {
        "key": "account.manage",
        "label": "账号配置",
        "status": "planned",
        "message": "正式接入前不开放 AppID/AppSecret 配置。",
    },
    {
        "key": "content.library",
        "label": "图文内容库",
        "status": "planned",
        "message": "待调研后设计公众号图文内容模型。",
    },
    {
        "key": "content.rewrite",
        "label": "文章改写",
        "status": "planned",
        "message": "待内容模型确认后接入公众号文章改写。",
    },
    {
        "key": "publish.dry_run",
        "label": "发布 dry-run",
        "status": "planned",
        "message": "待草稿箱、素材和群发 API 能力确认后设计。",
    },
    {
        "key": "publish.real_publish",
        "label": "群发发布",
        "status": "blocked",
        "message": "高风险动作，正式 QA、dry-run 和动作级确认机制完成前保持阻断。",
    },
]


@router.get("/overview")
def get_wechat_official_overview() -> dict:
    adapter_status = WechatOfficialAdapter().get_status()
    return {
        "platform_id": "wechat_official",
        "stage": adapter_status["stage"],
        "external_integration_enabled": adapter_status["external_integration_enabled"],
        "research_required_before_integration": True,
        "research_topics": RESEARCH_TOPICS,
        "capabilities": CAPABILITY_OVERVIEW,
        "blocked_actions": adapter_status["blocked_actions"],
    }
```

- [ ] **Step 5: Mount router in FastAPI app**

In `backend/app/main.py`, change the import block from:

```python
from backend.app.api.platforms import registry
```

to:

```python
from backend.app.api.platforms import registry
from backend.app.api.platforms.wechat_official import router as wechat_official_router
```

Then add this line after `app.include_router(registry.router, prefix="/api")`:

```python
    app.include_router(wechat_official_router, prefix="/api")
```

The router section should start like this:

```python
    app.include_router(registry.router, prefix="/api")
    app.include_router(wechat_official_router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
```

- [ ] **Step 6: Run overview API test to verify it passes**

Run:

```bash
pytest tests/backend/test_wechat_official_foundation.py::test_wechat_official_overview_api_returns_foundation_status_and_research_gate -v
```

Expected: PASS.

- [ ] **Step 7: Run backend foundation tests**

Run:

```bash
pytest tests/backend/test_wechat_official_foundation.py -v
```

Expected: PASS.

- [ ] **Step 8: Git checkpoint**

Do not commit unless the user explicitly asks. If the user has asked for commits, run:

```bash
git add backend/app/api/platforms/wechat_official backend/app/main.py tests/backend/test_wechat_official_foundation.py
git commit -m "feat: add wechat official foundation overview api"
```

---

### Task 4: Add frontend types, API client, and fallback platform metadata

**Files:**

- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/lib/platforms.ts`

- [ ] **Step 1: Add frontend overview types**

In `frontend/src/types/index.ts`, insert this after `PlatformMeta` and before `Paginated<T>`:

```typescript
export type WechatOfficialCapabilityOverview = {
  key: string;
  label: string;
  status: PlatformCapabilityStatus;
  message: string;
};

export type WechatOfficialOverview = {
  platform_id: "wechat_official";
  stage: "foundation_ready" | string;
  external_integration_enabled: boolean;
  research_required_before_integration: boolean;
  research_topics: string[];
  capabilities: WechatOfficialCapabilityOverview[];
  blocked_actions: string[];
};
```

- [ ] **Step 2: Add API import type**

In `frontend/src/lib/api.ts`, add `WechatOfficialOverview` to the existing type import list from `../types`.

The import tail should include:

```typescript
  XhsNoteSearchResponse,
  XhsDataCrawlItem,
  XhsDataCrawlPayload,
  XhsDataCrawlResponse,
  XhsKeywordGroupCrawlPayload,
  XhsKeywordGroupCrawlSummary,
  XhsSearchOptions,
  XhsSearchNote,
  XhsQrLoginSession,
  WechatOfficialOverview
} from "../types";
```

If the file uses no trailing comma on the last item, match the existing formatter after running the frontend build.

- [ ] **Step 3: Add API client function**

In `frontend/src/lib/api.ts`, insert this after `fetchXhsOverview()`:

```typescript
export async function fetchWechatOfficialOverview(): Promise<WechatOfficialOverview> {
  const response = await http.get<WechatOfficialOverview>("/wechat-official/overview");
  return response.data;
}
```

- [ ] **Step 4: Update fallback平台 metadata**

In `frontend/src/lib/platforms.ts`, replace the `wechat_official` entry with:

```typescript
  {
    id: "wechat_official",
    name_cn: "公众号",
    name_en: "WeChat Official",
    enabled: true,
    status: "enabled",
    release_stage: "beta",
    region: "cn",
    platform_type: "content",
    default_route: "/platforms/wechat-official/dashboard",
    adapter_key: "wechat_official",
    risk_level: "medium",
    auth_modes: ["none"],
    capabilities: [
      {
        key: "account.manage",
        status: "planned",
        risk: "medium",
        requires_confirmation: false,
        notes: "公众号账号配置待 GitHub 开源系统调研和微信官方 API 策略确认后接入；本轮不开放凭据输入。",
      },
      {
        key: "publish.real_publish",
        status: "blocked",
        risk: "high",
        requires_confirmation: true,
        notes: "公众号群发发布属于高风险动作；正式 QA、dry-run 和动作级确认机制完成前保持阻断。",
      },
    ],
    accent_color: "#0a9b57",
    icon: "wechat_official",
  },
```

Note: `status` currently has frontend type `"enabled" | "coming_soon"`; backend `PlatformMeta.status` returns `"beta"` for beta platforms. If TypeScript rejects this mismatch, update `PlatformMeta.status` in `frontend/src/types/index.ts` from:

```typescript
  status: "enabled" | "coming_soon";
```

to:

```typescript
  status: "enabled" | "beta" | "coming_soon" | "unavailable";
```

Then set fallback `status: "beta"` for `wechat_official` instead of `"enabled"`:

```typescript
    status: "beta",
```

- [ ] **Step 5: Run frontend type/build check**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS or fail only because the dashboard route/page is not added yet. If it fails due to `PlatformMeta.status`, apply the type update described in Step 4.

- [ ] **Step 6: Git checkpoint**

Do not commit unless the user explicitly asks. If the user has asked for commits, run:

```bash
git add frontend/src/types/index.ts frontend/src/lib/api.ts frontend/src/lib/platforms.ts
git commit -m "feat: add wechat official frontend foundation types"
```

---

### Task 5: Add微信公众号 dashboard page and route

**Files:**

- Create: `frontend/src/pages/wechat-official/wechat-official-dashboard.tsx`
- Modify: `frontend/src/app/router.tsx`

- [ ] **Step 1: Create dashboard page**

Create `frontend/src/pages/wechat-official/wechat-official-dashboard.tsx`:

```tsx
import {
  ApiOutlined,
  ArrowLeftOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  LockOutlined,
  SafetyCertificateOutlined,
} from "@ant-design/icons";
import { Alert, Button, Card, Col, List, Row, Space, Tag, Typography } from "antd";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { PageHeader } from "../../components/layout/app-shell";
import { fetchWechatOfficialOverview } from "../../lib/api";
import type { WechatOfficialOverview } from "../../types";

const { Text, Title } = Typography;

const fallbackOverview: WechatOfficialOverview = {
  platform_id: "wechat_official",
  stage: "foundation_ready",
  external_integration_enabled: false,
  research_required_before_integration: true,
  research_topics: [
    "GitHub 微信公众号开源系统架构调研",
    "微信官方草稿箱、素材、群发、预览 API 能力边界确认",
    "凭据保存与加密策略确认",
    "真实群发风险与 QA 流程确认",
  ],
  capabilities: [
    {
      key: "account.manage",
      label: "账号配置",
      status: "planned",
      message: "正式接入前不开放 AppID/AppSecret 配置。",
    },
    {
      key: "content.library",
      label: "图文内容库",
      status: "planned",
      message: "待调研后设计公众号图文内容模型。",
    },
    {
      key: "content.rewrite",
      label: "文章改写",
      status: "planned",
      message: "待内容模型确认后接入公众号文章改写。",
    },
    {
      key: "publish.dry_run",
      label: "发布 dry-run",
      status: "planned",
      message: "待草稿箱、素材和群发 API 能力确认后设计。",
    },
    {
      key: "publish.real_publish",
      label: "群发发布",
      status: "blocked",
      message: "高风险动作，正式 QA、dry-run 和动作级确认机制完成前保持阻断。",
    },
  ],
  blocked_actions: ["真实授权", "素材上传", "草稿同步", "预览发送", "群发发布"],
};

function statusColor(status: string): string {
  if (status === "blocked") return "red";
  if (status === "planned") return "gold";
  if (status === "available") return "green";
  return "default";
}

export function WechatOfficialDashboard() {
  const [overview, setOverview] = useState<WechatOfficialOverview>(fallbackOverview);
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    fetchWechatOfficialOverview()
      .then((payload) => {
        setOverview(payload);
        setLoadFailed(false);
      })
      .catch(() => {
        setOverview(fallbackOverview);
        setLoadFailed(true);
      });
  }, []);

  return (
    <div>
      <PageHeader
        eyebrow="WeChat Official Workspace"
        title="公众号平台"
        description="平台骨架已纳入主系统；正式接入前先调研 GitHub 开源系统和微信官方 API 能力边界。"
        action={
          <Link to="/platform-select">
            <Button icon={<ArrowLeftOutlined />}>返回平台中心</Button>
          </Link>
        }
      />

      {loadFailed ? (
        <Alert
          showIcon
          type="warning"
          style={{ marginBottom: 24 }}
          message="公众号底座状态读取失败"
          description="当前展示本地 fallback 状态。请检查后端服务；这不是微信连接失败，因为本阶段尚未接入微信外部接口。"
        />
      ) : null}

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} md={8}>
          <Card style={{ background: "#1f1f1f", borderColor: "#303030" }}>
            <Space align="start">
              <CheckCircleOutlined style={{ color: "#52c41a", fontSize: 22 }} />
              <div>
                <Title level={5} style={{ marginTop: 0 }}>平台骨架</Title>
                <Tag color="green">Foundation Ready</Tag>
                <div style={{ marginTop: 8 }}>
                  <Text type="secondary">当前阶段：{overview.stage}</Text>
                </div>
              </div>
            </Space>
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card style={{ background: "#1f1f1f", borderColor: "#303030" }}>
            <Space align="start">
              <ApiOutlined style={{ color: "#faad14", fontSize: 22 }} />
              <div>
                <Title level={5} style={{ marginTop: 0 }}>外部接入</Title>
                <Tag color="gold">Not Connected</Tag>
                <div style={{ marginTop: 8 }}>
                  <Text type="secondary">
                    external_integration_enabled = {String(overview.external_integration_enabled)}
                  </Text>
                </div>
              </div>
            </Space>
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card style={{ background: "#1f1f1f", borderColor: "#303030" }}>
            <Space align="start">
              <SafetyCertificateOutlined style={{ color: "#ff4d4f", fontSize: 22 }} />
              <div>
                <Title level={5} style={{ marginTop: 0 }}>真实动作</Title>
                <Tag color="red">Blocked</Tag>
                <div style={{ marginTop: 8 }}>
                  <Text type="secondary">授权、素材、草稿、预览、群发均未启用。</Text>
                </div>
              </div>
            </Space>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={14}>
          <Card
            title="能力清单"
            style={{ background: "#1f1f1f", borderColor: "#303030" }}
          >
            <List
              dataSource={overview.capabilities}
              renderItem={(capability) => (
                <List.Item>
                  <List.Item.Meta
                    avatar={capability.status === "blocked" ? <LockOutlined /> : <ExclamationCircleOutlined />}
                    title={
                      <Space>
                        <span>{capability.label}</span>
                        <Tag color={statusColor(capability.status)}>{capability.status}</Tag>
                      </Space>
                    }
                    description={capability.message}
                  />
                </List.Item>
              )}
            />
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card
            title="接入前置调研"
            style={{ background: "#1f1f1f", borderColor: "#303030", marginBottom: 16 }}
          >
            <List
              dataSource={overview.research_topics}
              renderItem={(item) => (
                <List.Item>
                  <Text>{item}</Text>
                </List.Item>
              )}
            />
          </Card>
          <Card
            title="已阻断动作"
            style={{ background: "#1f1f1f", borderColor: "#303030" }}
          >
            <Space wrap>
              {overview.blocked_actions.map((action) => (
                <Tag key={action} color="red">{action}</Tag>
              ))}
            </Space>
          </Card>
        </Col>
      </Row>
    </div>
  );
}
```

- [ ] **Step 2: Add route import**

In `frontend/src/app/router.tsx`, add this import after the settings/task imports and before XHS imports:

```typescript
import { WechatOfficialDashboard } from "../pages/wechat-official/wechat-official-dashboard";
```

- [ ] **Step 3: Add dashboard route**

In `frontend/src/app/router.tsx`, add this route inside the `AppShell` protected route group, before the XHS routes:

```tsx
          <Route path="/platforms/wechat-official/dashboard" element={<WechatOfficialDashboard />} />
```

The route group should start like this:

```tsx
        >
          <Route path="/platforms/wechat-official/dashboard" element={<WechatOfficialDashboard />} />
          <Route path="/platforms/xhs/dashboard" element={<XhsDashboard />} />
```

- [ ] **Step 4: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

If TypeScript reports `Type '"beta"' is not assignable to type '"enabled" | "coming_soon"'`, update `PlatformMeta.status` as described in Task 4 Step 4 and rerun the build.

- [ ] **Step 5: Git checkpoint**

Do not commit unless the user explicitly asks. If the user has asked for commits, run:

```bash
git add frontend/src/pages/wechat-official/wechat-official-dashboard.tsx frontend/src/app/router.tsx frontend/src/types/index.ts frontend/src/lib/api.ts frontend/src/lib/platforms.ts
git commit -m "feat: add wechat official foundation dashboard"
```

---

### Task 6: Final verification and documentation consistency check

**Files:**

- Verify only unless failures reveal necessary surgical fixes.

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
pytest tests/backend/test_wechat_official_foundation.py tests/backend/test_platforms.py tests/backend/test_platform_capability_gate.py tests/backend/test_platform_adapter_resolver.py -v
```

Expected: PASS.

- [ ] **Step 2: Run broader backend smoke tests**

Run:

```bash
pytest tests/backend/test_api.py tests/backend/test_drafts.py tests/backend/test_huitun_keyword_discovery.py -v
```

Expected: PASS. These tests protect existing app startup, auth/API flows, drafts, and Huitun keyword discovery from accidental regressions.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 4: Confirm no external integration was introduced**

Run:

```bash
git diff -- backend/app/adapters/wechat_official backend/app/api/platforms/wechat_official backend/app/core/platforms.py frontend/src/pages/wechat-official
```

Expected: Diff shows only local static data, fail-closed adapter, overview route, and dashboard UI. It must not contain `requests`, `httpx`, `aiohttp`, `wechatpy`, `AppSecret`, `access_token`, external URLs, or credential input fields.

- [ ] **Step 5: Check working tree**

Run:

```bash
git status --short
```

Expected: Only files from this plan plus the already-existing unrelated user changes are modified. Do not revert unrelated existing changes such as `CLAUDE.md` or `test-results/`.

- [ ] **Step 6: Git checkpoint**

Do not commit unless the user explicitly asks. If the user has asked for commits, run:

```bash
git add backend/app/core/platforms.py backend/app/main.py backend/app/adapters/wechat_official backend/app/api/platforms/wechat_official tests/backend/test_wechat_official_foundation.py frontend/src/types/index.ts frontend/src/lib/api.ts frontend/src/lib/platforms.ts frontend/src/pages/wechat-official frontend/src/app/router.tsx
git commit -m "feat: add wechat official platform foundation"
```

---

## Self-Review

### Spec coverage

- Platform Beta/Preparing state: Task 1 updates registry and tests API exposure.
- Independent backend API directory: Task 3 creates `backend/app/api/platforms/wechat_official/`.
- Independent adapter directory: Task 2 creates `backend/app/adapters/wechat_official/`.
- Independent frontend page and route: Task 5 creates dashboard and route.
- No real WeChat API integration: Task 2 fail-closed adapter and Task 6 diff check verify no external calls.
- No credential storage: No data model, no form, no migration; Task 6 checks for credential-related code.
- No database migration: No task creates Alembic migration or model table.
- GitHub research gate: Task 3 overview payload and Task 5 dashboard display research topics.
- Real publish blocked: Task 1 registry tests and Task 3 overview test assert `publish.real_publish` blocked.
- Verification: Task 6 runs backend focused tests, backend smoke tests, and frontend build.

### Placeholder scan

The plan contains no `TBD`, no `TODO`, and no “implement later” instructions. Each code-creating step includes concrete file paths and code blocks.

### Type consistency

- Backend platform ID uses `wechat_official` consistently.
- URL path uses `/wechat-official` consistently.
- Frontend route uses `/platforms/wechat-official/dashboard` consistently.
- Frontend type `WechatOfficialOverview` matches backend overview payload keys.
- Capability keys use existing `CapabilityKey` values: `account.manage`, `content.library`, `content.rewrite`, `publish.dry_run`, `publish.real_publish`.

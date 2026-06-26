# WeChat Official System Absorption Master Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Absorb the downloaded WeChat official account systems into the current FastAPI/React main platform as a staged, multi-provider公众号采集与内容运营能力, without replacing the main system or depending on Redfox as the only source.

**Architecture:** Build a provider-based公众号 subsystem inside the existing `backend/app/services` and `backend/app/api/platforms/wechat_official` boundaries. Each provider feeds the existing article/account/job/snapshot/metric/comment models through a unified ingestion layer, then the existing content library, analysis, draft, and Feishu flows consume normalized data.

**Tech Stack:** Python 3.12 via `py -3`, FastAPI, SQLAlchemy, Alembic, pytest, requests/httpx/aiohttp where already present, React + Vite + Ant Design on frontend. Do not copy AGPL source code; rewrite behavior in current project style.

---

## Non-Negotiable Execution Rules

1. **No code phase starts until its design is explicit.** Phase 0 creates the provider contract; later phases extend it instead of adding ad-hoc service calls.
2. **No provider may save empty shells.** If title/body/provider status is unknown, write an ingest error and return a user-actionable message.
3. **No fabricated metrics.** 阅读量、点赞、评论、转发等只保存 source-backed values. Unknown means unknown/0 with source metadata, not guessed values.
4. **No風控规避.** Low-frequency, authorized, diagnostic collection only. No captcha bypass, no account pools, no high-frequency automation.
5. **No AGPL implementation copy.** `wechat-download-api` can inform behavior, but code must be rewritten.
6. **No automatic git commit.** Project rule overrides generic plan guidance. Commit only when the user explicitly asks.
7. **95% confidence gate before reporting a phase as ready:**
   - targeted unit tests pass;
   - integration tests for the touched route/service pass;
   - at least one recorded or live sample path is validated;
   - failure states are tested, not only success states;
   - `git diff` reviewed for unrelated changes;
   - no task remains in `in_progress` when reporting.

---

## Master Phase Map

| Phase | Name | Purpose | Can Ship Alone? | Primary User Impact |
|---|---|---|---|---|
| 0 | Provider foundation | Establish contracts, diagnostics, and ingestion boundaries | Yes, as internal foundation | Future work becomes predictable and testable |
| 1 | Article URL + content fallback | Redfox failure no longer blocks URL/article正文入库 | Yes | 用户能导入公众号 URL 并拿到正文/图片 |
| 2 | Backend login + account/article list | Absorb公众号后台搜索与历史文章同步 | Yes | 用户能搜公众号并同步历史文章 |
| 3 | Metrics/comments + credentials | Absorb 阅读量/点赞/评论/回复 | Yes | 内容库有运营数据和评论素材 |
| 4 | Content operations | Absorb tags/categories/blacklist/read/favorite/image reliability | Yes | 内容库可长期运营和整理 |
| 5 | RSS/export/notification | Absorb RSS、导出、通知 | Yes | 公众号内容可分发、备份、自动提醒 |
| 6 | Browser fallback + advanced nodes | Improve success rate in verification-heavy environments | Optional | 验证页/风控时可人工介入继续 |

---

## Target File Structure

### Backend provider layer

- Create `backend/app/services/wechat_official_provider_types.py`
  - Defines provider result dataclasses, error kinds, source labels, and status helpers.
- Create `backend/app/services/wechat_official_ingestion_service.py`
  - Owns normalized account/article/snapshot/metric/comment persistence.
  - Prevents duplicate persistence logic across Redfox/backend/page/RSS providers.
- Create `backend/app/services/wechat_official_article_page_provider.py`
  - Fetches and parses single `mp.weixin.qq.com` article pages.
  - Rewrites behavior learned from downloaded systems; no direct AGPL copy.
- Create `backend/app/services/wechat_official_backend_provider.py`
  - Real公众号后台 login/search/list/metadata/comment provider, introduced in Phase 2/3.
- Create `backend/app/services/wechat_official_rate_limit_service.py`
  - Provider-level and user-level low-frequency controls.
- Create `backend/app/services/wechat_official_subscription_service.py`
  - RSS/subscription polling, introduced in Phase 5.
- Create `backend/app/services/wechat_official_export_service.py`
  - JSON/Markdown/HTML first, advanced formats later.

### Backend API layer

- Modify `backend/app/api/platforms/wechat_official/redfox.py`
  - Keep Redfox routes working; delegate shared persistence to ingestion service.
- Modify `backend/app/api/platforms/wechat_official/content_library.py`
  - Add content refresh/provider status endpoints when needed.
- Create `backend/app/api/platforms/wechat_official/providers.py`
  - Provider health and diagnostics.
- Create `backend/app/api/platforms/wechat_official/imports.py`
  - Unified `import-url`, later batch import.
- Create `backend/app/api/platforms/wechat_official/subscriptions.py`
  - RSS/subscription endpoints in Phase 5.

### Models and migrations

- Modify `backend/app/models/wechat_official.py` only when raw JSON is insufficient.
- Prefer existing tables for Phase 0-1:
  - `WechatOfficialCrawlJob`
  - `WechatOfficialArticle`
  - `WechatOfficialArticleSnapshot`
  - `WechatOfficialArticleMetric`
  - `WechatOfficialArticleComment`
  - `WechatOfficialIngestError`
- Add Alembic migrations only when a phase requires new durable structures.

### Tests

- Create `tests/backend/test_wechat_official_provider_types.py`
- Create `tests/backend/test_wechat_official_article_page_provider.py`
- Create `tests/backend/test_wechat_official_ingestion.py`
- Extend `tests/backend/test_wechat_official_redfox_collect.py`
- Add phase-specific tests:
  - `tests/backend/test_wechat_official_backend_provider.py`
  - `tests/backend/test_wechat_official_metrics_comments.py`
  - `tests/backend/test_wechat_official_subscriptions.py`
  - `tests/backend/test_wechat_official_exports.py`

### Frontend

- Modify `frontend/src/types/index.ts`
  - Add provider status, content completeness, subscription/export types.
- Modify `frontend/src/pages/wechat-official/wechat-official-dashboard.tsx`
  - Add provider status cards and collection center entry points.
- Modify `frontend/src/pages/wechat-official/wechat-official-content-library-adapter.tsx`
  - Show provider/source/completeness state.
- Add focused components only when a phase reaches frontend work:
  - `frontend/src/pages/wechat-official/wechat-official-provider-status.tsx`
  - `frontend/src/pages/wechat-official/wechat-official-collection-center.tsx`
  - `frontend/src/pages/wechat-official/wechat-official-subscriptions.tsx`

---

## Phase 0: Provider Foundation

**Confidence target:** 95% internal architecture confidence before implementing user-visible features.

**Files:**
- Create: `backend/app/services/wechat_official_provider_types.py`
- Create: `backend/app/services/wechat_official_ingestion_service.py`
- Create: `tests/backend/test_wechat_official_provider_types.py`
- Create: `tests/backend/test_wechat_official_ingestion.py`
- Modify: `backend/app/services/wechat_official_redfox_service.py`

### Task 0.1: Define provider result and error contracts

- [ ] **Step 1: Write failing tests for provider status contracts**

Create `tests/backend/test_wechat_official_provider_types.py`:

```python
from backend.app.services.wechat_official_provider_types import (
    WechatOfficialProviderError,
    WechatOfficialProviderErrorKind,
    WechatOfficialProviderSource,
    provider_error_payload,
)


def test_provider_error_payload_is_user_actionable():
    error = WechatOfficialProviderError(
        source=WechatOfficialProviderSource.ARTICLE_PAGE,
        kind=WechatOfficialProviderErrorKind.WECHAT_VERIFICATION_REQUIRED,
        message="微信要求完成验证",
        retryable=True,
        user_action="请在浏览器打开该文章完成验证后重试",
        diagnostics={"status_text": "环境异常"},
    )

    payload = provider_error_payload(error)

    assert payload["source"] == "article_page"
    assert payload["kind"] == "wechat_verification_required"
    assert payload["retryable"] is True
    assert "浏览器" in payload["user_action"]
    assert payload["diagnostics"] == {"status_text": "环境异常"}


def test_provider_error_payload_never_exposes_secret_fields():
    error = WechatOfficialProviderError(
        source=WechatOfficialProviderSource.WECHAT_BACKEND,
        kind=WechatOfficialProviderErrorKind.LOGIN_EXPIRED,
        message="登录已过期",
        retryable=False,
        user_action="请重新扫码登录公众号后台",
        diagnostics={"cookie": "secret", "token": "secret", "safe": "ok"},
    )

    payload = provider_error_payload(error)

    assert payload["diagnostics"]["cookie"] == "***redacted***"
    assert payload["diagnostics"]["token"] == "***redacted***"
    assert payload["diagnostics"]["safe"] == "ok"
```

- [ ] **Step 2: Run tests and verify they fail because module is missing**

Run:

```bash
py -3 -m pytest tests/backend/test_wechat_official_provider_types.py -q
```

Expected: `ModuleNotFoundError` for `backend.app.services.wechat_official_provider_types`.

- [ ] **Step 3: Implement provider contract module**

Create `backend/app/services/wechat_official_provider_types.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

SENSITIVE_DIAGNOSTIC_KEYS = {"api_key", "authorization", "cookie", "key", "pass_ticket", "secret", "token", "wap_sid2"}


class WechatOfficialProviderSource(StrEnum):
    REDFOX = "redfox"
    ARTICLE_PAGE = "article_page"
    WECHAT_BACKEND = "wechat_backend"
    BROWSER = "browser"
    RSS = "rss"


class WechatOfficialProviderErrorKind(StrEnum):
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    NETWORK_ERROR = "network_error"
    TIMEOUT = "timeout"
    WECHAT_VERIFICATION_REQUIRED = "wechat_verification_required"
    RATE_LIMITED = "rate_limited"
    LOGIN_EXPIRED = "login_expired"
    ARTICLE_DELETED = "article_deleted"
    ARTICLE_UNAVAILABLE = "article_unavailable"
    PARSE_FAILED = "parse_failed"
    UNSUPPORTED_URL = "unsupported_url"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class WechatOfficialProviderError(Exception):
    source: WechatOfficialProviderSource
    kind: WechatOfficialProviderErrorKind
    message: str
    retryable: bool
    user_action: str
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message


@dataclass(slots=True)
class WechatOfficialArticlePayload:
    source: WechatOfficialProviderSource
    article_url: str
    title: str
    digest: str = ""
    author_name: str = ""
    account_name: str = ""
    account: str = ""
    publish_time_remote: str = ""
    cover_url: str = ""
    content_url: str = ""
    content_html: str = ""
    content_text: str = ""
    images: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, int] = field(default_factory=dict)
    comments: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


def sanitize_diagnostics(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).lower() in SENSITIVE_DIAGNOSTIC_KEYS:
                cleaned[str(key)] = "***redacted***"
            else:
                cleaned[str(key)] = sanitize_diagnostics(item)
        return cleaned
    if isinstance(value, list):
        return [sanitize_diagnostics(item) for item in value]
    return value


def provider_error_payload(error: WechatOfficialProviderError) -> dict[str, Any]:
    return {
        "source": str(error.source),
        "kind": str(error.kind),
        "message": error.message,
        "retryable": error.retryable,
        "user_action": error.user_action,
        "diagnostics": sanitize_diagnostics(error.diagnostics),
    }
```

- [ ] **Step 4: Verify provider contract tests pass**

Run:

```bash
py -3 -m pytest tests/backend/test_wechat_official_provider_types.py -q
```

Expected: `2 passed`.

### Task 0.2: Introduce ingestion service without changing behavior

- [ ] **Step 1: Write failing ingestion test**

Create `tests/backend/test_wechat_official_ingestion.py` with a minimal database override matching patterns in existing `test_wechat_official_redfox_collect.py`:

```python
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import Base
from backend.app.models import User, WechatOfficialArticle, WechatOfficialArticleSnapshot
from backend.app.services.wechat_official_ingestion_service import WechatOfficialIngestionService
from backend.app.services.wechat_official_provider_types import WechatOfficialArticlePayload, WechatOfficialProviderSource


def _session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'wechat_ingestion.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    user = User(username="ingestion-user", hashed_password="x")
    db.add(user)
    db.commit()
    db.refresh(user)
    return db, user


def test_ingestion_saves_article_snapshot_and_source_metadata(tmp_path):
    db, user = _session(tmp_path)
    payload = WechatOfficialArticlePayload(
        source=WechatOfficialProviderSource.ARTICLE_PAGE,
        article_url="https://mp.weixin.qq.com/s/test-ingestion",
        title="测试标题",
        digest="测试摘要",
        author_name="测试公众号",
        account_name="测试公众号",
        account="MzTestBiz",
        content_html="<p>正文</p>",
        content_text="正文",
        images=[{"url": "https://mmbiz.qpic.cn/test.jpg", "type": "content"}],
        raw={"provider_status": "ok"},
    )

    result = WechatOfficialIngestionService(db).save_single_article(user.id, payload, source_label="article_page_url")

    article = db.scalar(select(WechatOfficialArticle).where(WechatOfficialArticle.id == result["article_id"]))
    snapshot = db.scalar(select(WechatOfficialArticleSnapshot).where(WechatOfficialArticleSnapshot.article_id == article.id))
    assert article.title == "测试标题"
    assert article.source == "article_page"
    assert article.raw_json["provider"]["source"] == "article_page"
    assert snapshot.text == "正文"
    assert snapshot.images_json[0]["url"].startswith("https://mmbiz.qpic.cn/")
```

- [ ] **Step 2: Run test and verify missing module failure**

Run:

```bash
py -3 -m pytest tests/backend/test_wechat_official_ingestion.py::test_ingestion_saves_article_snapshot_and_source_metadata -q
```

Expected: `ModuleNotFoundError` for ingestion service.

- [ ] **Step 3: Implement minimal ingestion service**

Create `backend/app/services/wechat_official_ingestion_service.py`:

```python
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from backend.app.core.time import shanghai_now
from backend.app.models import (
    WechatOfficialArticle,
    WechatOfficialArticleSnapshot,
    WechatOfficialContentLibraryTombstone,
    WechatOfficialCrawlAccount,
    WechatOfficialCrawlJob,
)
from backend.app.services.wechat_official_crawl_service import serialize_article, serialize_crawl_job
from backend.app.services.wechat_official_provider_types import WechatOfficialArticlePayload


class WechatOfficialIngestionService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def save_single_article(self, user_id: int, payload: WechatOfficialArticlePayload, *, source_label: str) -> dict[str, Any]:
        if not payload.title.strip():
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="公众号文章已返回，但未识别到标题，未保存空壳")
        if self._is_tombstoned(user_id, payload.article_url):
            return {"article_id": None, "skipped": True, "reason": "tombstoned"}

        account = self._upsert_account(user_id, payload)
        job = WechatOfficialCrawlJob(
            account_id=account.id,
            keyword=payload.article_url,
            status="running",
            source=str(payload.source),
            requested_limit=1,
            fetched_count=1,
            params_json={"source": source_label, "provider": str(payload.source)},
            started_at=shanghai_now(),
        )
        self.db.add(job)
        self.db.flush()

        article = self._upsert_article(account.id, job.id, payload)
        if payload.content_html or payload.content_text or payload.images:
            self._create_snapshot(article.id, payload)

        job.status = "succeeded"
        job.saved_count = 1
        job.finished_at = shanghai_now()
        self.db.commit()
        self.db.refresh(job)
        self.db.refresh(article)
        return {"article_id": article.id, "job": serialize_crawl_job(job), "item": serialize_article(article, latest_metric=None, analysis={})}

    def _is_tombstoned(self, user_id: int, article_url: str) -> bool:
        if not article_url:
            return False
        return self.db.scalar(
            select(WechatOfficialContentLibraryTombstone.id).where(
                WechatOfficialContentLibraryTombstone.user_id == user_id,
                WechatOfficialContentLibraryTombstone.article_url == article_url,
            )
        ) is not None

    def _upsert_account(self, user_id: int, payload: WechatOfficialArticlePayload) -> WechatOfficialCrawlAccount:
        account_key = payload.account or payload.account_name or payload.author_name or "wechat_article_page"
        fake_id = f"{payload.source}:{account_key}"
        account = self.db.scalar(
            select(WechatOfficialCrawlAccount).where(
                WechatOfficialCrawlAccount.user_id == user_id,
                WechatOfficialCrawlAccount.fake_id == fake_id,
            )
        )
        if account is None:
            account = WechatOfficialCrawlAccount(user_id=user_id, fake_id=fake_id, status="active")
            self.db.add(account)
        account.name = payload.account_name or payload.author_name or "微信公众号"
        account.biz = payload.account
        account.raw_json = {"provider": str(payload.source), "raw": payload.raw}
        return account

    def _upsert_article(self, account_id: int, job_id: int, payload: WechatOfficialArticlePayload) -> WechatOfficialArticle:
        article = self.db.scalar(
            select(WechatOfficialArticle).where(
                WechatOfficialArticle.account_id == account_id,
                WechatOfficialArticle.article_url == payload.article_url,
            )
        )
        if article is None:
            article = WechatOfficialArticle(account_id=account_id, article_url=payload.article_url)
            self.db.add(article)
        article.job_id = job_id
        article.title = payload.title
        article.digest = payload.digest or payload.content_text[:240]
        article.author_name = payload.author_name or payload.account_name
        article.source = str(payload.source)
        article.publish_time_remote = payload.publish_time_remote or None
        article.cover_url = payload.cover_url or _first_image_url(payload.images)
        article.content_url = payload.content_url or payload.article_url
        raw = dict(article.raw_json or {})
        raw["provider"] = {"source": str(payload.source), "source_label": str(payload.source)}
        raw["raw"] = payload.raw
        article.raw_json = raw
        flag_modified(article, "raw_json")
        self.db.flush()
        return article

    def _create_snapshot(self, article_id: int, payload: WechatOfficialArticlePayload) -> None:
        self.db.add(
            WechatOfficialArticleSnapshot(
                article_id=article_id,
                status="captured",
                html=payload.content_html,
                text=payload.content_text,
                images_json=payload.images,
                raw_json={"provider": str(payload.source), "raw": payload.raw},
            )
        )


def _first_image_url(images: list[dict[str, Any]]) -> str:
    for image in images:
        url = str(image.get("url") or "").strip()
        if url:
            return url
    return ""
```

- [ ] **Step 4: Run ingestion test**

Run:

```bash
py -3 -m pytest tests/backend/test_wechat_official_ingestion.py -q
```

Expected: `1 passed`.

- [ ] **Step 5: Regression test current Redfox suite**

Run:

```bash
py -3 -m pytest tests/backend/test_wechat_official_redfox_collect.py -q
```

Expected: all existing Redfox tests pass.

### Phase 0 95% Confidence Gate

- [ ] Provider contracts tested.
- [ ] Ingestion service saves article and snapshot without breaking Redfox suite.
- [ ] No API behavior change exposed yet.
- [ ] `git diff -- backend/app/services tests/backend` reviewed for unrelated edits.

---

## Phase 1: Article URL + Redfox Fallback

**Confidence target:** 95% confidence that a Redfox detail outage no longer blocks public WeChat article URL import.

**Files:**
- Create: `backend/app/services/wechat_official_article_page_provider.py`
- Create: `tests/backend/test_wechat_official_article_page_provider.py`
- Extend: `tests/backend/test_wechat_official_redfox_collect.py`
- Modify: `backend/app/services/wechat_official_redfox_service.py`
- Create: `backend/app/api/platforms/wechat_official/imports.py` only after backend service behavior is green.

### Task 1.1: Parse ordinary WeChat article HTML

- [ ] **Step 1: Write failing parser test**

Create `tests/backend/test_wechat_official_article_page_provider.py`:

```python
from backend.app.services.wechat_official_article_page_provider import parse_wechat_article_html
from backend.app.services.wechat_official_provider_types import WechatOfficialProviderSource


def test_parse_wechat_article_html_extracts_title_author_text_and_images():
    html = '''
    <html><head>
      <meta property="og:title" content="一篇公众号文章" />
      <meta property="og:article:author" content="摩斯测试号" />
      <meta property="og:description" content="摘要内容" />
    </head><body>
      <h1 class="rich_media_title">一篇公众号文章</h1>
      <a id="js_name">摩斯测试号</a>
      <em id="publish_time">2026-06-25</em>
      <script>var __biz = "MzTestBiz";</script>
      <div id="js_content">
        <p>第一段正文</p>
        <p><img data-src="https://mmbiz.qpic.cn/test-one.jpg" /></p>
        <p>第二段正文</p>
      </div>
    </body></html>
    '''

    payload = parse_wechat_article_html("https://mp.weixin.qq.com/s/test", html)

    assert payload.source == WechatOfficialProviderSource.ARTICLE_PAGE
    assert payload.title == "一篇公众号文章"
    assert payload.author_name == "摩斯测试号"
    assert payload.account == "MzTestBiz"
    assert payload.publish_time_remote == "2026-06-25"
    assert "第一段正文" in payload.content_text
    assert payload.content_html.startswith("<p>第一段正文")
    assert payload.images == [{"url": "https://mmbiz.qpic.cn/test-one.jpg", "type": "content", "source": "article_page"}]
```

- [ ] **Step 2: Run parser test and verify failure**

Run:

```bash
py -3 -m pytest tests/backend/test_wechat_official_article_page_provider.py::test_parse_wechat_article_html_extracts_title_author_text_and_images -q
```

Expected: missing module or function failure.

- [ ] **Step 3: Implement parser without network fetching**

Create `backend/app/services/wechat_official_article_page_provider.py`:

```python
from __future__ import annotations

import html as html_module
import re
from typing import Any
from urllib.parse import urlparse

import requests

from backend.app.services.wechat_official_provider_types import (
    WechatOfficialArticlePayload,
    WechatOfficialProviderError,
    WechatOfficialProviderErrorKind,
    WechatOfficialProviderSource,
)

ARTICLE_PAGE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.43",
    "Referer": "https://mp.weixin.qq.com/",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def parse_wechat_article_html(url: str, html: str) -> WechatOfficialArticlePayload:
    _raise_for_unusable_html(url, html)
    title = _first_text(
        html,
        [
            r'<h1[^>]*class=["\'][^"\']*rich_media_title[^"\']*["\'][^>]*>([\s\S]*?)</h1>',
            r'<h2[^>]*class=["\'][^"\']*rich_media_title[^"\']*["\'][^>]*>([\s\S]*?)</h2>',
            r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)["\']',
            r"var\s+msg_title\s*=\s*'([^']+)'",
        ],
    )
    author = _first_text(
        html,
        [
            r'<a[^>]*id=["\']js_name["\'][^>]*>([\s\S]*?)</a>',
            r'<meta\s+property=["\']og:article:author["\']\s+content=["\']([^"\']+)["\']',
            r'var\s+nickname\s*=\s*["\']([^"\']+)["\']',
        ],
    )
    digest = _first_text(html, [r'<meta\s+property=["\']og:description["\']\s+content=["\']([^"\']*)["\']', r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']*)["\']'])
    publish_time = _first_text(html, [r'<em[^>]*id=["\']publish_time["\'][^>]*>([^<]+)</em>', r'var\s+ct\s*=\s*["\'](\d+)["\']'])
    account = _first_text(html, [r'var\s+__biz\s*=\s*["\']([^"\']+)["\']', r'var\s+biz\s*=\s*["\']([^"\']+)["\']', r'[?&]__biz=([^&"\']+)'])
    content_html = _extract_content_html(html)
    images = _extract_images(content_html)
    content_text = _html_to_text(content_html)
    if not title:
        raise WechatOfficialProviderError(
            source=WechatOfficialProviderSource.ARTICLE_PAGE,
            kind=WechatOfficialProviderErrorKind.PARSE_FAILED,
            message="微信文章页面已返回，但未识别到标题",
            retryable=False,
            user_action="请确认 URL 是有效的微信公众号文章链接",
            diagnostics={"url": url, "html_length": len(html)},
        )
    return WechatOfficialArticlePayload(
        source=WechatOfficialProviderSource.ARTICLE_PAGE,
        article_url=url,
        title=title,
        digest=digest,
        author_name=author,
        account_name=author,
        account=account,
        publish_time_remote=publish_time,
        cover_url=_first_image_url(images),
        content_url=url,
        content_html=content_html,
        content_text=content_text,
        images=images,
        raw={"html_length": len(html), "parser": "article_page_v1"},
    )


def fetch_wechat_article_page(url: str, *, timeout: float = 30.0) -> WechatOfficialArticlePayload:
    if not _is_wechat_article_url(url):
        raise WechatOfficialProviderError(
            source=WechatOfficialProviderSource.ARTICLE_PAGE,
            kind=WechatOfficialProviderErrorKind.UNSUPPORTED_URL,
            message="只支持 mp.weixin.qq.com 公众号文章链接",
            retryable=False,
            user_action="请粘贴微信公众号文章 URL",
            diagnostics={"url": url},
        )
    try:
        response = requests.get(url, headers=ARTICLE_PAGE_HEADERS, timeout=timeout, allow_redirects=True)
        response.raise_for_status()
    except requests.Timeout as exc:
        raise WechatOfficialProviderError(
            source=WechatOfficialProviderSource.ARTICLE_PAGE,
            kind=WechatOfficialProviderErrorKind.TIMEOUT,
            message="微信文章页面请求超时",
            retryable=True,
            user_action="请稍后重试，或降低采集频率",
            diagnostics={"url": url},
        ) from exc
    except requests.RequestException as exc:
        raise WechatOfficialProviderError(
            source=WechatOfficialProviderSource.ARTICLE_PAGE,
            kind=WechatOfficialProviderErrorKind.NETWORK_ERROR,
            message="微信文章页面网络请求失败",
            retryable=True,
            user_action="请稍后重试，或检查网络/代理设置",
            diagnostics={"url": url, "error": str(exc)},
        ) from exc
    return parse_wechat_article_html(url, response.text)


def _is_wechat_article_url(url: str) -> bool:
    parsed = urlparse(str(url or ""))
    return parsed.netloc.lower() == "mp.weixin.qq.com" and parsed.path.startswith("/s")


def _raise_for_unusable_html(url: str, value: str) -> None:
    text = _html_to_text(value).lower()
    if "环境异常" in value or "完成验证" in value or "go verify" in text:
        raise WechatOfficialProviderError(WechatOfficialProviderSource.ARTICLE_PAGE, WechatOfficialProviderErrorKind.WECHAT_VERIFICATION_REQUIRED, "微信要求完成验证", True, "请在浏览器打开该文章完成验证后重试", {"url": url})
    if "操作频繁" in value or "too frequent" in text:
        raise WechatOfficialProviderError(WechatOfficialProviderSource.ARTICLE_PAGE, WechatOfficialProviderErrorKind.RATE_LIMITED, "微信提示操作频繁", True, "请等待一段时间后重试，并降低采集频率", {"url": url})
    if "该内容已被发布者删除" in value or "the content has been deleted" in text:
        raise WechatOfficialProviderError(WechatOfficialProviderSource.ARTICLE_PAGE, WechatOfficialProviderErrorKind.ARTICLE_DELETED, "文章已被发布者删除", False, "请更换文章 URL", {"url": url})


def _extract_content_html(value: str) -> str:
    for pattern in [
        r'<div[^>]*id=["\']js_content["\'][^>]*>([\s\S]*?)</div>\s*(?:<script|<div[^>]*class=["\']rich_media_tool|</div>\s*</div>)',
        r'<div[^>]*class=["\'][^"\']*rich_media_content[^"\']*["\'][^>]*>([\s\S]*?)</div>',
        r'<div[^>]*id=["\']page-content["\'][^>]*>([\s\S]*?)</div>',
        r'<div[^>]*id=["\']page_content["\'][^>]*>([\s\S]*?)</div>',
    ]:
        match = re.search(pattern, value, re.IGNORECASE)
        if match:
            return _clean_html(match.group(1))
    return ""


def _clean_html(value: str) -> str:
    value = re.sub(r'<script[^>]*>[\s\S]*?</script>', '', value, flags=re.IGNORECASE)
    value = re.sub(r'<p[^>]*>\s*</p>', '', value, flags=re.IGNORECASE)
    return value.strip()


def _extract_images(content_html: str) -> list[dict[str, Any]]:
    images: list[dict[str, Any]] = []
    seen: set[str] = set()
    for img_tag in re.findall(r'<img[^>]*>', content_html, flags=re.IGNORECASE):
        url = _attr(img_tag, "data-src") or _attr(img_tag, "src")
        if not url or url.startswith("data:") or url in seen:
            continue
        seen.add(url)
        images.append({"url": url, "type": "content", "source": "article_page"})
    return images


def _first_image_url(images: list[dict[str, Any]]) -> str:
    return str(images[0].get("url") or "") if images else ""


def _attr(tag: str, name: str) -> str:
    match = re.search(rf'{name}=["\']([^"\']+)["\']', tag, flags=re.IGNORECASE)
    return html_module.unescape(match.group(1)).strip() if match else ""


def _first_text(value: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, value, re.IGNORECASE)
        if match:
            text = re.sub(r'<[^>]+>', '', match.group(1))
            return html_module.unescape(text).strip()
    return ""


def _html_to_text(value: str) -> str:
    text = re.sub(r'<br\s*/?>', '\n', value, flags=re.IGNORECASE)
    text = re.sub(r'</(?:p|div|section|h[1-6]|li)>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = html_module.unescape(text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()
```

- [ ] **Step 4: Verify parser test passes**

Run:

```bash
py -3 -m pytest tests/backend/test_wechat_official_article_page_provider.py -q
```

Expected: parser test passes.

### Task 1.2: Test verification/deleted failure states

- [ ] **Step 1: Add failure-state tests**

Append to `tests/backend/test_wechat_official_article_page_provider.py`:

```python
import pytest

from backend.app.services.wechat_official_provider_types import WechatOfficialProviderError, WechatOfficialProviderErrorKind


def test_parse_wechat_article_html_reports_verification_required():
    html = "<html><body>当前环境异常，完成验证后即可继续访问 <button>去验证</button></body></html>"

    with pytest.raises(WechatOfficialProviderError) as exc_info:
        parse_wechat_article_html("https://mp.weixin.qq.com/s/verify", html)

    assert exc_info.value.kind == WechatOfficialProviderErrorKind.WECHAT_VERIFICATION_REQUIRED
    assert exc_info.value.retryable is True
    assert "浏览器" in exc_info.value.user_action


def test_parse_wechat_article_html_reports_deleted_article():
    html = "<html><body><div class='weui-msg'>该内容已被发布者删除</div></body></html>"

    with pytest.raises(WechatOfficialProviderError) as exc_info:
        parse_wechat_article_html("https://mp.weixin.qq.com/s/deleted", html)

    assert exc_info.value.kind == WechatOfficialProviderErrorKind.ARTICLE_DELETED
    assert exc_info.value.retryable is False
```

- [ ] **Step 2: Run and verify pass**

Run:

```bash
py -3 -m pytest tests/backend/test_wechat_official_article_page_provider.py -q
```

Expected: all article page provider tests pass.

### Task 1.3: Redfox import-url fallback

- [ ] **Step 1: Write failing Redfox fallback integration test**

Extend `tests/backend/test_wechat_official_redfox_collect.py` with a fake client that always fails and monkeypatches the article page provider:

```python
class FakeSslFailingArticleDetailRedfoxClient:
    def __init__(self, *, base_url: str, api_key: str) -> None:
        self.base_url = base_url
        self.api_key = api_key

    def query_article_detail(self, *, url: str) -> dict:
        raise requests.exceptions.SSLError("UNEXPECTED_EOF_WHILE_READING")


def test_redfox_import_url_falls_back_to_article_page_provider_when_detail_ssl_fails(tmp_path, monkeypatch):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    monkeypatch.setattr(redfox_service, "WechatOfficialRedfoxClient", FakeSslFailingArticleDetailRedfoxClient, raising=False)

    from backend.app.services.wechat_official_provider_types import WechatOfficialArticlePayload, WechatOfficialProviderSource

    def fake_fetch(url: str):
        assert url == "https://mp.weixin.qq.com/s/fallback-url"
        return WechatOfficialArticlePayload(
            source=WechatOfficialProviderSource.ARTICLE_PAGE,
            article_url=url,
            title="Fallback 正文标题",
            digest="Fallback 摘要",
            author_name="Fallback 公众号",
            account_name="Fallback 公众号",
            account="MzFallbackBiz",
            content_html="<p>Fallback 正文</p>",
            content_text="Fallback 正文",
            images=[{"url": "https://mmbiz.qpic.cn/fallback.jpg", "type": "content"}],
            raw={"provider_status": "ok"},
        )

    monkeypatch.setattr("backend.app.services.wechat_official_redfox_service.fetch_wechat_article_page", fake_fetch, raising=False)
    try:
        headers = _register("redfox-fallback-url-user")
        _save_config(headers)

        response = client.post(
            "/api/wechat-official/redfox/import-url",
            headers=headers,
            json={"url": "https://mp.weixin.qq.com/s/fallback-url"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["summary"]["saved"] == 1
        assert body["items"][0]["title"] == "Fallback 正文标题"
        assert body["items"][0]["author_name"] == "Fallback 公众号"
    finally:
        app.dependency_overrides.pop(get_db, None)
```

- [ ] **Step 2: Run fallback test and verify failure**

Run:

```bash
py -3 -m pytest tests/backend/test_wechat_official_redfox_collect.py::test_redfox_import_url_falls_back_to_article_page_provider_when_detail_ssl_fails -q
```

Expected: fails because `fetch_wechat_article_page` is not imported/called by Redfox service.

- [ ] **Step 3: Modify Redfox service to fallback only for recoverable detail failures**

In `backend/app/services/wechat_official_redfox_service.py`, import:

```python
from backend.app.services.wechat_official_article_page_provider import fetch_wechat_article_page
from backend.app.services.wechat_official_provider_types import WechatOfficialProviderError, provider_error_payload
```

Then update `import_url` logic so `_query_article_detail_or_raise` failure falls back for network/timeout/detail failures:

```python
    def import_url(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        url = str(payload.get("url") or "").strip()
        if not url:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="url is required")
        client = self._client(user_id)
        try:
            response = self._query_article_detail_or_raise(client, url=url)
            item = self.adapter.normalize_article_detail(response)
            item["article_url"] = item.get("article_url") or url
            item["content_url"] = item.get("content_url") or item["article_url"]
            item.setdefault("raw", {})
            if isinstance(item["raw"], dict):
                item["raw"]["provider"] = {"source": "redfox", "fallback_used": False}
        except HTTPException as redfox_exc:
            item = self._fallback_import_url_from_article_page(url, redfox_exc)
        self._validate_imported_url_article(item, url=url)
        normalized = [item]
        return self._save_collection(
            user_id,
            normalized,
            source_label="redfox_url",
            keyword=url,
            requested_limit=1,
            min_read_count=0,
            save_snapshot=bool(payload.get("save_snapshot", True)),
            api_calls=1,
            params={"url": url},
        )
```

Add helper method in `WechatOfficialRedfoxService`:

```python
    def _fallback_import_url_from_article_page(self, url: str, redfox_exc: HTTPException) -> dict[str, Any]:
        try:
            payload = fetch_wechat_article_page(url)
        except WechatOfficialProviderError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": "Redfox 详情接口不可用，微信文章页面兜底也未成功",
                    "redfox_error": redfox_exc.detail,
                    "fallback_error": provider_error_payload(exc),
                },
            ) from exc
        raw = dict(payload.raw or {})
        raw["provider"] = {"source": str(payload.source), "fallback_used": True, "redfox_error": redfox_exc.detail}
        return {
            "external_id": "",
            "article_url": payload.article_url,
            "title": payload.title,
            "digest": payload.digest,
            "author_name": payload.author_name,
            "account_name": payload.account_name,
            "account": payload.account,
            "publish_time_remote": payload.publish_time_remote,
            "cover_url": payload.cover_url,
            "content_url": payload.content_url,
            "content_text": payload.content_text,
            "content_html": payload.content_html,
            "images": payload.images,
            "comments": payload.comments,
            "metrics": payload.metrics,
            "follower_count": None,
            "low_follower_label": None,
            "raw": raw,
        }
```

- [ ] **Step 4: Run focused fallback test**

Run:

```bash
py -3 -m pytest tests/backend/test_wechat_official_redfox_collect.py::test_redfox_import_url_falls_back_to_article_page_provider_when_detail_ssl_fails -q
```

Expected: pass.

- [ ] **Step 5: Run full Redfox and provider suites**

Run:

```bash
py -3 -m pytest tests/backend/test_wechat_official_article_page_provider.py tests/backend/test_wechat_official_ingestion.py tests/backend/test_wechat_official_redfox_collect.py -q
```

Expected: all pass.

### Phase 1 95% Confidence Gate

- [ ] Redfox detail SSL failure fallback test passes.
- [ ] Article page parser success and failure-state tests pass.
- [ ] Existing Redfox collect suite passes.
- [ ] One real or saved HTML article sample parsed locally.
- [ ] User-facing error for verification/deleted page is structured and action-oriented.

---

## Phase 2: WeChat Backend Login, Account Search, and History Sync

**Confidence target:** 95% confidence that the system can use authorized公众号后台 credentials to search accounts and sync historical article lists at low frequency.

**Files:**
- Create: `backend/app/services/wechat_official_backend_provider.py`
- Modify: `backend/app/services/wechat_official_backend_session_service.py`
- Modify: `backend/app/services/wechat_official_crawl_service.py`
- Create: `tests/backend/test_wechat_official_backend_provider.py`
- Extend: `tests/backend/test_wechat_official_backend_session.py`
- Modify frontend dashboard only after backend tests pass.

### Task 2.1: Backend provider interface and fake transport tests

- [ ] **Step 1: Write failing tests for search account normalization through provider**

Create `tests/backend/test_wechat_official_backend_provider.py`:

```python
from backend.app.services.wechat_official_backend_provider import WechatOfficialBackendProvider


class FakeBackendTransport:
    def get(self, endpoint: str, params: dict, *, cookie: str, token: str, user_agent: str) -> dict:
        assert endpoint == "https://mp.weixin.qq.com/cgi-bin/searchbiz"
        assert params["query"] == "测试公众号"
        assert cookie == "cookie-value"
        assert token == "token-value"
        return {
            "base_resp": {"ret": 0},
            "list": [
                {"fakeid": "fake-1", "nickname": "测试公众号", "alias": "test_alias", "round_head_img": "https://wx.qlogo.cn/avatar.jpg"}
            ],
        }


def test_backend_provider_search_accounts_returns_normalized_accounts():
    provider = WechatOfficialBackendProvider(transport=FakeBackendTransport())

    result = provider.search_accounts(keyword="测试公众号", cookie="cookie-value", token="token-value", user_agent="ua")

    assert result == [
        {
            "fake_id": "fake-1",
            "name": "测试公众号",
            "alias": "test_alias",
            "avatar_url": "https://wx.qlogo.cn/avatar.jpg",
            "raw": {"fakeid": "fake-1", "nickname": "测试公众号", "alias": "test_alias", "round_head_img": "https://wx.qlogo.cn/avatar.jpg"},
        }
    ]
```

- [ ] **Step 2: Run and verify failure**

Run:

```bash
py -3 -m pytest tests/backend/test_wechat_official_backend_provider.py::test_backend_provider_search_accounts_returns_normalized_accounts -q
```

Expected: missing module failure.

- [ ] **Step 3: Implement provider with injectable transport**

Create `backend/app/services/wechat_official_backend_provider.py` with:

```python
from __future__ import annotations

from typing import Any, Protocol

import requests

from backend.app.services.wechat_official_provider_types import (
    WechatOfficialProviderError,
    WechatOfficialProviderErrorKind,
    WechatOfficialProviderSource,
)


class WechatOfficialBackendTransport(Protocol):
    def get(self, endpoint: str, params: dict[str, Any], *, cookie: str, token: str, user_agent: str) -> dict[str, Any]: ...


class RequestsWechatOfficialBackendTransport:
    def get(self, endpoint: str, params: dict[str, Any], *, cookie: str, token: str, user_agent: str) -> dict[str, Any]:
        headers = {
            "Cookie": cookie,
            "User-Agent": user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
            "Referer": "https://mp.weixin.qq.com/",
            "Origin": "https://mp.weixin.qq.com",
        }
        response = requests.get(endpoint, params={**params, "token": token, "lang": "zh_CN", "f": "json", "ajax": 1}, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("wechat backend response is not JSON object")
        return data


class WechatOfficialBackendProvider:
    def __init__(self, transport: WechatOfficialBackendTransport | None = None) -> None:
        self.transport = transport or RequestsWechatOfficialBackendTransport()

    def search_accounts(self, *, keyword: str, cookie: str, token: str, user_agent: str) -> list[dict[str, Any]]:
        data = self._get(
            "https://mp.weixin.qq.com/cgi-bin/searchbiz",
            {"action": "search_biz", "query": keyword, "begin": 0, "count": 5},
            cookie=cookie,
            token=token,
            user_agent=user_agent,
        )
        return [_normalize_account(item) for item in data.get("list") or [] if isinstance(item, dict)]

    def _get(self, endpoint: str, params: dict[str, Any], *, cookie: str, token: str, user_agent: str) -> dict[str, Any]:
        try:
            data = self.transport.get(endpoint, params, cookie=cookie, token=token, user_agent=user_agent)
        except requests.Timeout as exc:
            raise WechatOfficialProviderError(WechatOfficialProviderSource.WECHAT_BACKEND, WechatOfficialProviderErrorKind.TIMEOUT, "公众号后台请求超时", True, "请稍后重试", {}) from exc
        except requests.RequestException as exc:
            raise WechatOfficialProviderError(WechatOfficialProviderSource.WECHAT_BACKEND, WechatOfficialProviderErrorKind.NETWORK_ERROR, "公众号后台网络请求失败", True, "请检查网络或重新登录", {"error": str(exc)}) from exc
        ret = ((data.get("base_resp") or {}).get("ret"))
        if ret not in (None, 0):
            raise WechatOfficialProviderError(WechatOfficialProviderSource.WECHAT_BACKEND, WechatOfficialProviderErrorKind.LOGIN_EXPIRED, "公众号后台登录可能已失效", False, "请重新扫码登录公众号后台", {"ret": ret, "response": data})
        return data


def _normalize_account(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "fake_id": str(item.get("fakeid") or ""),
        "name": str(item.get("nickname") or ""),
        "alias": str(item.get("alias") or ""),
        "avatar_url": str(item.get("round_head_img") or item.get("head_img") or ""),
        "raw": item,
    }
```

- [ ] **Step 4: Verify backend provider test passes**

Run:

```bash
py -3 -m pytest tests/backend/test_wechat_official_backend_provider.py -q
```

Expected: pass.

### Task 2.2: Add history article provider after search is stable

- [ ] **Step 1: Add failing provider test for history list**

Add fake transport response for `appmsgpublish` with `publish_page.publish_list[].publish_info.appmsgex` and assert normalized `article_url`, `title`, `digest`, `cover_url`, `publish_time_remote`.

- [ ] **Step 2: Implement `sync_account_articles` on provider**

Use endpoint:

```text
https://mp.weixin.qq.com/cgi-bin/appmsgpublish
```

Parameters:

```python
{
    "sub": "list",
    "search_field": "null",
    "begin": begin,
    "count": count,
    "query": "",
    "fakeid": fake_id,
    "type": "101_1",
    "free_publish_type": 1,
    "sub_action": "list_ex",
}
```

Expected behavior:

- Parse nested JSON safely.
- Skip items without valid `link` or title.
- Return normalized list, not persisted data.

- [ ] **Step 3: Service integration**

Update `WechatOfficialCrawlService.sync_articles` so it can accept either existing `upstream_payload` or call provider with a valid backend session.

- [ ] **Step 4: Verification**

Run:

```bash
py -3 -m pytest tests/backend/test_wechat_official_backend_provider.py tests/backend/test_wechat_official_crawl.py tests/backend/test_wechat_official_backend_session.py -q
```

Expected: all pass.

### Phase 2 95% Confidence Gate

- [ ] Login/session tests pass.
- [ ] Search account provider tests pass.
- [ ] History list provider tests pass.
- [ ] Existing crawl tests pass.
- [ ] One manually verified or recorded backend response fixture is parsed.
- [ ] No token/cookie appears in test output, errors, docs, or `git diff`.

---

## Phase 3: Metrics, Comments, and Credentials

**Confidence target:** 95% confidence that sensitive metrics/comments are only fetched when credentials are present and never fabricated.

**Files:**
- Extend: `backend/app/services/wechat_official_backend_provider.py`
- Modify: `backend/app/services/wechat_official_credential_service.py`
- Modify: `backend/app/services/wechat_official_comment_service.py`
- Modify: `backend/app/services/wechat_official_ingestion_service.py`
- Create: `tests/backend/test_wechat_official_metrics_comments.py`

### Task 3.1: Credential gate for metrics/comments

- [ ] **Step 1: Write failing tests that missing credentials block sensitive refresh**

Create `tests/backend/test_wechat_official_metrics_comments.py`:

```python
from fastapi import HTTPException
import pytest

from backend.app.services.wechat_official_provider_types import WechatOfficialProviderErrorKind


def test_refresh_metrics_without_valid_credential_returns_actionable_error():
    # Use existing test database helpers from credential/comment tests when implementing.
    # Expected behavior: service raises HTTPException 400 with detail containing "Credential" or "凭证".
    assert True
```

Replace the placeholder assertion during implementation with the existing project database helper. Do not implement provider calls until this test fails for the real missing behavior.

- [ ] **Step 2: Implement credential gate**

Behavior:

- If no valid `WechatOfficialArticleCredential` for article/account: return 400.
- Error text: `采集阅读量/评论需要有效文章凭证，请先配置或刷新 credential`.
- No remote request attempted without credential.

- [ ] **Step 3: Verify**

Run:

```bash
py -3 -m pytest tests/backend/test_wechat_official_credentials.py tests/backend/test_wechat_official_metrics_comments.py -q
```

Expected: credential gate tests pass.

### Task 3.2: Metrics/comment parsing with fixtures

- [ ] **Step 1: Add recorded fixture tests**

Create minimal fake comment response fixture in test file:

```python
COMMENT_RESPONSE = {
    "base_resp": {"ret": 0},
    "elected_comment": [
        {
            "content_id": "comment-1",
            "nick_name": "读者A",
            "content": "评论内容",
            "like_num": 12,
            "create_time": 1719300000,
            "reply": {"reply_list": [{"content_id": "reply-1", "nick_name": "作者", "content": "回复内容", "like_num": 3}]},
        }
    ],
}
```

Test provider normalizes comments and replies into current model fields.

- [ ] **Step 2: Implement normalizers**

Add provider methods:

- `fetch_article_metrics(...) -> dict[str, int]`
- `fetch_article_comments(...) -> list[dict[str, Any]]`

- [ ] **Step 3: Persist through ingestion/comment service**

Save into existing:

- `WechatOfficialArticleMetric`
- `WechatOfficialArticleComment`
- `WechatOfficialArticleCommentReply`

- [ ] **Step 4: Verify**

Run:

```bash
py -3 -m pytest tests/backend/test_wechat_official_metrics.py tests/backend/test_wechat_official_comments.py tests/backend/test_wechat_official_metrics_comments.py -q
```

Expected: all pass.

### Phase 3 95% Confidence Gate

- [ ] Missing credentials do not call remote provider.
- [ ] Metrics/comments fixtures persist correctly.
- [ ] Existing metrics/comment tests pass.
- [ ] No fabricated values saved.
- [ ] User-facing errors explain credential preparation.

---

## Phase 4: Content Operations and Reliability

**Confidence target:** 95% confidence that the content library can support long-running operations without data pollution.

**Files:**
- Modify: `backend/app/services/wechat_official_content_service.py`
- Modify: `backend/app/services/wechat_official_content_tombstone_service.py`
- Modify: `frontend/src/pages/wechat-official/wechat-official-content-library-adapter.tsx`
- Extend: `tests/backend/test_wechat_official_content_library.py`

### Task 4.1: Content completeness metadata

- [ ] **Step 1: Write failing test for detail status**

Extend content library tests to assert detail status includes:

```python
{
    "has_content": True,
    "has_images": True,
    "has_metrics": False,
    "has_comments": False,
    "provider_source": "article_page",
    "can_refresh_content": True,
    "can_refresh_metrics": False,
    "can_refresh_comments": False,
}
```

- [ ] **Step 2: Implement detail status fields**

Update `_detail_status` in `wechat_official_content_service.py` to include provider and completeness booleans.

- [ ] **Step 3: Verify**

Run:

```bash
py -3 -m pytest tests/backend/test_wechat_official_content_library.py -q
```

Expected: pass.

### Task 4.2: Classification, blacklist, read/favorite mapping

- [ ] **Step 1: Define minimal status model in raw_json.analysis**

Fields:

```python
analysis["content_status"] = "unread" | "read"
analysis["favorite"] = True | False
analysis["category"] = "string"
analysis["tags"] = ["string"]
```

- [ ] **Step 2: Add update endpoint tests**

Use existing `update_recommendation` pattern to update these fields.

- [ ] **Step 3: Implement updates and filters**

Extend list filters for category, favorite, content_status.

- [ ] **Step 4: Verify**

Run:

```bash
py -3 -m pytest tests/backend/test_wechat_official_content_library.py tests/backend/test_wechat_official_redfox_collect.py -q
```

Expected: pass.

### Phase 4 95% Confidence Gate

- [ ] Content completeness visible in API.
- [ ] Filters do not hide existing articles unexpectedly.
- [ ] Tombstoned articles stay skipped across providers.
- [ ] Frontend displays source/completeness without breaking content library.

---

## Phase 5: RSS, Export, Notification

**Confidence target:** 95% confidence that new automation does not mutate or publish external data unexpectedly.

**Files:**
- Create: `backend/app/services/wechat_official_subscription_service.py`
- Create: `backend/app/services/wechat_official_export_service.py`
- Create: `backend/app/api/platforms/wechat_official/subscriptions.py`
- Create: `tests/backend/test_wechat_official_subscriptions.py`
- Create: `tests/backend/test_wechat_official_exports.py`
- Add Alembic migration only for subscription tables.

### Task 5.1: Subscription model and polling without network

- [ ] **Step 1: Write failing test for subscription CRUD**

Test creates subscription for an existing account and asserts enabled/disabled state.

- [ ] **Step 2: Add migration and model**

Add `WechatOfficialSubscription` fields:

```python
user_id: int
account_id: int | None
fake_id: str
biz: str
name: str
enabled: bool
poll_interval_minutes: int
last_polled_at: datetime | None
category: str
raw_json: dict | None
```

- [ ] **Step 3: Implement CRUD only**

No network polling until CRUD is tested.

- [ ] **Step 4: Verify**

Run:

```bash
py -3 -m pytest tests/backend/test_wechat_official_subscriptions.py -q
```

Expected: pass.

### Task 5.2: RSS feed generation from stored articles

- [ ] **Step 1: Write failing RSS generation test**

Given stored articles with snapshots, generated XML contains channel, item titles, links, and content.

- [ ] **Step 2: Implement feed generator from database only**

No network access in RSS generation.

- [ ] **Step 3: Verify XML test**

Run:

```bash
py -3 -m pytest tests/backend/test_wechat_official_subscriptions.py::test_subscription_rss_feed_contains_stored_articles -q
```

Expected: pass.

### Task 5.3: Export service

- [ ] **Step 1: Write tests for JSON/Markdown/HTML export**

Inputs: article with snapshot/images/metrics.

Expected:

- JSON contains article, latest_snapshot, metrics, images.
- Markdown contains title, author, text, image links.
- HTML contains content_html.

- [ ] **Step 2: Implement export service**

Keep implementation in `wechat_official_export_service.py`; do not mix into content service.

- [ ] **Step 3: Verify**

Run:

```bash
py -3 -m pytest tests/backend/test_wechat_official_exports.py -q
```

Expected: pass.

### Phase 5 95% Confidence Gate

- [ ] Subscription CRUD tested.
- [ ] RSS generation uses stored data only.
- [ ] Export formats tested.
- [ ] No external publish/send action is triggered by default.
- [ ] Notification hooks, if added, are dry-run tested before live use.

---

## Phase 6: Browser Fallback and Advanced Nodes

**Confidence target:** 95% confidence that browser fallback improves diagnosis and success rate without becoming an implicit bypass tool.

**Files:**
- Create: `backend/app/services/wechat_official_browser_provider.py`
- Create: `tests/backend/test_wechat_official_browser_provider.py`
- Optional frontend panel for browser status.

### Task 6.1: Browser provider status model only

- [ ] **Step 1: Write tests for status mapping**

Statuses:

- `ok`
- `captcha_required`
- `rate_limited`
- `article_not_rendered`
- `browser_not_ready`
- `navigation_failed`

- [ ] **Step 2: Implement status mapper**

Use behavior inspired by `wechat-reader` but write fresh code.

- [ ] **Step 3: Verify**

Run:

```bash
py -3 -m pytest tests/backend/test_wechat_official_browser_provider.py -q
```

Expected: pass.

### Task 6.2: Manual browser fallback proof only

- [ ] **Step 1: Add manual verification script or endpoint behind explicit user action**

No automatic browser manipulation in background tasks.

- [ ] **Step 2: Validate with one user-approved browser session**

Evidence required:

- browser status detected;
- page title/body extracted;
- captcha/rate limit state correctly identified;
- user tab not modified unless explicitly authorized.

### Phase 6 95% Confidence Gate

- [ ] Browser provider is optional.
- [ ] User action required for browser fallback.
- [ ] Verification/captcha states are reported, not bypassed.
- [ ] No default background browser automation.

---

## Cross-Phase Verification Commands

Use these after each phase if related files changed:

```bash
py -3 -m pytest tests/backend/test_wechat_official_redfox_collect.py -q
py -3 -m pytest tests/backend/test_wechat_official_content_library.py -q
py -3 -m pytest tests/backend/test_wechat_official_crawl.py -q
py -3 -m pytest tests/backend/test_wechat_official_backend_session.py -q
py -3 -m pytest tests/backend/test_wechat_official_credentials.py -q
```

For frontend type/build after frontend changes:

```bash
cd frontend && npm run build
```

If `npm run build` is not the project command, inspect `frontend/package.json` and use the defined build script.

---

## Reporting Protocol

Before reporting any phase as complete or ready:

1. Run the phase-specific tests fresh.
2. Run impacted existing tests fresh.
3. If frontend changed, run frontend build.
4. Capture the exact command outputs.
5. Review `git diff --stat` and changed files.
6. Report only what passed; list skipped checks explicitly.
7. If confidence is below 95%, do not claim readiness. Report blockers and next diagnostic action.

Confidence below 95% examples:

- only happy-path tests exist;
- parser works only on synthetic HTML;
- no failure-state test for verification/deleted/rate limit;
- credentials are stored or logged unsafely;
- route returns raw provider stack traces;
- Redfox success path regressed;
- frontend builds are unverified after type changes.

---

## Plan Self-Review

### Spec coverage

- Complete system absorption is covered by Phase 0-6.
- URL fallback and Redfox outage are covered by Phase 1.
- Backend login/search/history are covered by Phase 2.
- Metrics/comments/credentials are covered by Phase 3.
- Content management is covered by Phase 4.
- RSS/export/notifications are covered by Phase 5.
- Browser fallback and advanced nodes are covered by Phase 6.

### Placeholder scan

This master plan intentionally leaves exact implementation of later provider internals to phase execution because real response fixtures are required before coding. The plan does not use placeholder task names as acceptance criteria; each phase has concrete files, tests, commands, and gates. Later phases must write phase-specific detailed child plans before code if response fixtures differ from assumptions.

### Type consistency

Shared types are anchored in `WechatOfficialProviderSource`, `WechatOfficialProviderErrorKind`, `WechatOfficialProviderError`, and `WechatOfficialArticlePayload`. Later phase providers must return these normalized shapes before persistence.

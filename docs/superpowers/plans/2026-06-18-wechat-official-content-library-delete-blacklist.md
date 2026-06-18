# 微信公众号爆文发现删除 + 黑名单 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让公众号“爆文发现 / 内容库”里的删除变成真正删除：内容从列表和详情里消失，历史正文/快照/评论/指标一起清理，且同 URL 后续采集不会再被重新保存回来。

**Architecture:** 继续以现有 `wechat_official_articles` 为内容库事实源，不改草稿工坊链路。删除时新增一张 user-scoped tombstone 表记录已删除文章 URL；内容库删除接口负责清理文章及其派生数据并写 tombstone；Redfox 和公众号同步两条入库路径在写入前先查 tombstone，命中就跳过，从源头阻断“删了又被保存回来”。

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy, Alembic, pytest, React, Vite, TypeScript, Ant Design.

---

## File Structure

- `backend/app/models/wechat_official.py` — 新增公众号内容库 tombstone 模型，记录已删除文章的 `user_id` + `article_url`。
- `backend/app/models/__init__.py` — 导出新的 tombstone 模型，保证服务和测试可以直接 import。
- `backend/alembic/versions/20260618_add_wechat_official_content_library_tombstones.py` — 新增迁移表，给删除黑名单落库。
- `backend/app/services/wechat_official_content_tombstone_service.py` — 新的共享服务，负责查 tombstone、写 tombstone，供删除与入库两个方向复用。
- `backend/app/services/wechat_official_content_service.py` — 新增内容库删除业务：清 article、快照、评论、回复、指标、历史 source link，并写 tombstone。
- `backend/app/api/platforms/wechat_official/content_library.py` — 新增 `DELETE /{article_id}` 接口。
- `backend/app/services/wechat_official_crawl_service.py` — 公众号同步入库前查 tombstone，命中则跳过保存。
- `backend/app/services/wechat_official_redfox_service.py` — Redfox 收集入库前查 tombstone，命中则跳过保存。
- `frontend/src/lib/api.ts` — 新增内容库删除 API。
- `frontend/src/pages/wechat-official/wechat-official-dashboard.tsx` — 把“移出内容库”改成真正删除，并加确认弹窗。
- `tests/backend/test_wechat_official_content_library.py` — 覆盖删除、详情 404、tombstone 写入、再次同步不回流。
- `tests/backend/test_wechat_official_redfox_collect.py` — 覆盖 Redfox 路径在删除后不再重新保存同 URL。

Non-goals:

- 不改 `backend/app/services/wechat_official_draft_service.py`。
- 不改 `backend/app/api/drafts.py` 的通用草稿语义。
- 不改公众号草稿工坊的 UI、表结构、保存逻辑。
- 不做全局软删框架，不改其他平台的删除模型。

---

### Task 1: 锁住“删除后消失 + 不回流”的回归测试

**Files:**
- Modify: `tests/backend/test_wechat_official_content_library.py`
- Modify: `tests/backend/test_wechat_official_redfox_collect.py`

- [ ] **Step 1: 先写内容库删除的失败测试**

在 `tests/backend/test_wechat_official_content_library.py` 里新增一个覆盖完整链路的测试：先创建一篇有阅读量的文章，再补一个详情快照和评论，然后删除，最后确认详情 404、article/metric/snapshot/comment 全部没了、tombstone 已写入、同 URL 再走公众号同步不会重新保存。

```python
def test_content_library_delete_removes_article_descendants_and_blocks_resave(tmp_path, monkeypatch):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    monkeypatch.setattr(redfox_service, "WechatOfficialRedfoxClient", FakeRedfoxDetailClient, raising=False)
    try:
        headers = _register("delete-owner")
        article_id = _create_article(
            headers,
            title="删除案例",
            url="https://mp.weixin.qq.com/s/delete-target",
            read_count=120000,
        )
        config = client.post("/api/wechat-official/redfox/config", headers=headers, json={"api_key": "delete-secret"})
        assert config.status_code == 200
        refreshed = client.post(f"/api/wechat-official/content-library/{article_id}/refresh-detail", headers=headers)
        assert refreshed.status_code == 200

        deleted = client.delete(f"/api/wechat-official/content-library/{article_id}", headers=headers)
        assert deleted.status_code == 200
        assert deleted.json() == {"id": article_id, "status": "deleted"}

        detail = client.get(f"/api/wechat-official/content-library/{article_id}", headers=headers)
        assert detail.status_code == 404

        with TestingSessionLocal() as db:
            assert db.get(WechatOfficialArticle, article_id) is None
            assert db.scalar(select(WechatOfficialArticleMetric).where(WechatOfficialArticleMetric.article_id == article_id)) is None
            assert db.scalar(select(WechatOfficialArticleSnapshot).where(WechatOfficialArticleSnapshot.article_id == article_id)) is None
            assert db.scalar(select(WechatOfficialArticleComment).where(WechatOfficialArticleComment.article_id == article_id)) is None
            assert db.scalar(select(WechatOfficialContentLibraryTombstone).where(WechatOfficialContentLibraryTombstone.article_url == "https://mp.weixin.qq.com/s/delete-target")) is not None

        session_id = _create_session(headers)
        relaunch = client.post(
            "/api/wechat-official/crawl/articles/sync",
            headers=headers,
            json={
                "backend_session_id": session_id,
                "upstream_payload": {
                    "publish_page": '{"publish_list":[{"publish_info":{"appmsgex":[{"title":"删除案例","digest":"摘要删除案例","link":"https://mp.weixin.qq.com/s/delete-target"}]}}]}'
                },
            },
        )
        assert relaunch.status_code == 200
        assert relaunch.json()["items"] == []
    finally:
        app.dependency_overrides.pop(get_db, None)
```

- [ ] **Step 2: 再写 Redfox 回流的失败测试**

在 `tests/backend/test_wechat_official_redfox_collect.py` 里新增一个测试：先通过 Redfox import-url 保存一篇文章，删除后再次用同 URL import-url，确认后一次不会重新入库。

```python
def test_redfox_import_url_skips_tombstoned_article(tmp_path, monkeypatch):
    get_db, _ = _override_database(tmp_path)
    monkeypatch.setattr(redfox_service, "WechatOfficialRedfoxClient", FakeRedfoxClient, raising=False)
    try:
        headers = _register("redfox-delete-user")
        _save_config(headers)

        first = client.post(
            "/api/wechat-official/redfox/import-url",
            headers=headers,
            json={"url": "https://mp.weixin.qq.com/s/redfox-url", "min_read_count": 100000},
        )
        assert first.status_code == 200
        article_id = first.json()["items"][0]["id"]

        deleted = client.delete(f"/api/wechat-official/content-library/{article_id}", headers=headers)
        assert deleted.status_code == 200

        second = client.post(
            "/api/wechat-official/redfox/import-url",
            headers=headers,
            json={"url": "https://mp.weixin.qq.com/s/redfox-url", "min_read_count": 100000},
        )
        assert second.status_code == 200
        assert second.json()["summary"]["saved"] == 0
        assert second.json()["items"] == []
    finally:
        app.dependency_overrides.pop(get_db, None)
```

- [ ] **Step 3: 运行这两个测试，确认它们当前都失败**

Run:

```bash
pytest tests/backend/test_wechat_official_content_library.py -v -k "delete_removes_article_descendants_and_blocks_resave"
pytest tests/backend/test_wechat_official_redfox_collect.py -v -k "skips_tombstoned_article"
```

Expected: FAIL，原因分别是目前还没有删除接口、没有 tombstone 表、也没有入库前的回流阻断。

---

### Task 2: 加 tombstone 表，并把删除做成真正的内容库删除

**Files:**
- Create: `backend/app/services/wechat_official_content_tombstone_service.py`
- Modify: `backend/app/models/wechat_official.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/20260618_add_wechat_official_content_library_tombstones.py`
- Modify: `backend/app/services/wechat_official_content_service.py`
- Modify: `backend/app/api/platforms/wechat_official/content_library.py`
- Modify: `backend/app/services/wechat_official_crawl_service.py`
- Modify: `backend/app/services/wechat_official_redfox_service.py`

- [ ] **Step 1: 先把 tombstone 模型和迁移写出来**

在 `backend/app/models/wechat_official.py` 里新增一个 user-scoped tombstone 表，字段只保留删除黑名单所需内容。

```python
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint


class WechatOfficialContentLibraryTombstone(Base):
    __tablename__ = "wechat_official_content_library_tombstones"
    __table_args__ = (
        UniqueConstraint("user_id", "article_url", name="uq_wechat_official_content_library_tombstones_user_url"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    article_url: Mapped[str] = mapped_column(Text, index=True)
    article_title: Mapped[str] = mapped_column(String(512), default="")
    deleted_at: Mapped[datetime] = mapped_column(DateTime, default=shanghai_now)
```

在 `backend/app/models/__init__.py` 的 wechat_official 导出里加上 `WechatOfficialContentLibraryTombstone`。

在 `backend/alembic/versions/20260618_add_wechat_official_content_library_tombstones.py` 里创建同名表，`downgrade()` 时删除该表。

- [ ] **Step 2: 写一个共享 tombstone service**

新增 `backend/app/services/wechat_official_content_tombstone_service.py`，专门负责查和写删除黑名单。

```python
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import WechatOfficialContentLibraryTombstone


class WechatOfficialContentTombstoneService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def is_tombstoned(self, user_id: int, article_url: str) -> bool:
        article_url = str(article_url or "").strip()
        if not article_url:
            return False
        return (
            self.db.scalar(
                select(WechatOfficialContentLibraryTombstone.id).where(
                    WechatOfficialContentLibraryTombstone.user_id == user_id,
                    WechatOfficialContentLibraryTombstone.article_url == article_url,
                )
            )
            is not None
        )

    def tombstone(self, user_id: int, article_url: str, article_title: str = "") -> None:
        article_url = str(article_url or "").strip()
        if not article_url:
            return
        row = self.db.scalar(
            select(WechatOfficialContentLibraryTombstone).where(
                WechatOfficialContentLibraryTombstone.user_id == user_id,
                WechatOfficialContentLibraryTombstone.article_url == article_url,
            )
        )
        if row is None:
            row = WechatOfficialContentLibraryTombstone(user_id=user_id, article_url=article_url, article_title=article_title)
            self.db.add(row)
        else:
            row.article_title = article_title or row.article_title
```

- [ ] **Step 3: 在内容库 service 里实现真正删除**

在 `backend/app/services/wechat_official_content_service.py` 里新增删除方法，并把文章及其派生记录一起清掉；只保留 tombstone，不动草稿内容。

```python
from sqlalchemy import delete, select

from backend.app.models import (
    ModelConfig,
    WechatOfficialArticle,
    WechatOfficialArticleComment,
    WechatOfficialArticleCommentReply,
    WechatOfficialArticleMetric,
    WechatOfficialArticleSnapshot,
    WechatOfficialContentLibraryTombstone,
    WechatOfficialDraftSource,
    WechatOfficialIngestError,
)
from backend.app.services.wechat_official_content_tombstone_service import WechatOfficialContentTombstoneService


class WechatOfficialContentService:
    ...

    def delete_article(self, user_id: int, article_id: int) -> dict[str, Any]:
        article = get_owned_content_article(self.db, user_id, article_id)
        article_url = str(article.article_url or article.content_url or "").strip()
        if article_url:
            WechatOfficialContentTombstoneService(self.db).tombstone(user_id, article_url, article.title)

        self.db.execute(delete(WechatOfficialArticleCommentReply).where(WechatOfficialArticleCommentReply.comment_id.in_(select(WechatOfficialArticleComment.id).where(WechatOfficialArticleComment.article_id == article.id))))
        self.db.execute(delete(WechatOfficialArticleComment).where(WechatOfficialArticleComment.article_id == article.id))
        self.db.execute(delete(WechatOfficialArticleMetric).where(WechatOfficialArticleMetric.article_id == article.id))
        self.db.execute(delete(WechatOfficialArticleSnapshot).where(WechatOfficialArticleSnapshot.article_id == article.id))
        self.db.execute(delete(WechatOfficialIngestError).where(WechatOfficialIngestError.article_id == article.id))
        self.db.execute(delete(WechatOfficialDraftSource).where(WechatOfficialDraftSource.article_id == article.id))
        self.db.delete(article)
        self.db.commit()
        return {"id": article_id, "status": "deleted"}
```

If the comment-reply delete statement is too dense in code review, split it into two explicit deletes: first replies by joining comment ids, then comments.

- [ ] **Step 4: 把删除接口挂到内容库 API 上**

在 `backend/app/api/platforms/wechat_official/content_library.py` 里新增 `DELETE /{article_id}`，直接返回删除结果。

```python
@router.delete("/{article_id}")
def delete_content_library_article(article_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return WechatOfficialContentService(db).delete_article(current_user.id, article_id)
```

- [ ] **Step 5: 在两条入库路径前加 tombstone guard**

`backend/app/services/wechat_official_crawl_service.py`：在 `sync_articles()` 里，调用 `_upsert_article()` 之前先取 canonical URL，命中 tombstone 就 `continue`。

```python
from backend.app.services.wechat_official_content_tombstone_service import WechatOfficialContentTombstoneService


def sync_articles(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    session = get_valid_session(self.db, user_id, int(payload["backend_session_id"]))
    account_id = payload.get("account_id") or session.account_id
    account = self._get_owned_account(user_id, int(account_id)) if account_id else None
    articles_payload = self.adapter.normalize_appmsgpublish_articles(payload.get("upstream_payload") or {})
    tombstones = WechatOfficialContentTombstoneService(self.db)
    ...
    for article_payload in selected:
        article_url = str(article_payload.get("article_url") or article_payload.get("content_url") or "").strip()
        if article_url and tombstones.is_tombstoned(user_id, article_url):
            continue
        article = self._upsert_article(account.id if account else None, job.id, article_payload)
        saved.append(article)
```

`backend/app/services/wechat_official_redfox_service.py`：在 `_save_collection()` 里，同样先判断 `article_url`，命中 tombstone 就跳过，不计入 `saved_articles`。

```python
from backend.app.services.wechat_official_content_tombstone_service import WechatOfficialContentTombstoneService


def _save_collection(...):
    tombstones = WechatOfficialContentTombstoneService(self.db)
    ...
    for item in articles_payload:
        article_url = str(item.get("article_url") or item.get("content_url") or "").strip()
        if article_url and tombstones.is_tombstoned(user_id, article_url):
            continue
        account = self._upsert_redfox_account(user_id, item)
        article, created = self._upsert_redfox_article(account.id, job.id, item, min_read_count=min_read_count)
        ...
```

- [ ] **Step 6: 运行后端测试，确认删除和回流阻断都通过**

Run:

```bash
pytest tests/backend/test_wechat_official_content_library.py -v -k "delete_removes_article_descendants_and_blocks_resave"
pytest tests/backend/test_wechat_official_redfox_collect.py -v -k "skips_tombstoned_article"
```

Expected: PASS。删除接口返回 `{"id": ..., "status": "deleted"}`，详情 404，tombstone 可查到，同 URL 重新同步不再保存。

---

### Task 3: 前端把“移出内容库”改成真正删除

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/pages/wechat-official/wechat-official-dashboard.tsx`

- [ ] **Step 1: 先补前端删除 API**

在 `frontend/src/lib/api.ts` 里新增一个和 `deleteSavedNote()` 同风格的 API：

```typescript
export async function deleteWechatOfficialContentLibraryItem(articleId: number): Promise<{ id: number; status: string }> {
  const response = await http.delete<{ id: number; status: string }>(`/wechat-official/content-library/${articleId}`);
  return response.data;
}
```

- [ ] **Step 2: 把行内动作从“移出内容库”改成删除确认**

在 `frontend/src/pages/wechat-official/wechat-official-dashboard.tsx` 里：

1. 从 `antd` 额外引入 `Modal`。
2. 删除旧的 `handleArchiveArticle`，不要再把删除按钮映射到 `pool_status: "candidate"`。
3. 新增 `handleDeleteArticle()`，点击后弹确认框，确认后调用新 API，再刷新列表和详情。
4. 把按钮文案从 `移出内容库` 改成 `删除`，按钮保留 `danger` 样式。

```tsx
const handleDeleteArticle = (article: WechatOfficialContentLibraryItem) => {
  Modal.confirm({
    title: "删除这篇爆文？",
    content: "删除后会清空内容库数据并记录删除黑名单，同 URL 后续采集会被跳过；草稿不受影响。",
    okText: "删除",
    okType: "danger",
    cancelText: "取消",
    onOk: () => runAction(`delete-${article.id}`, "爆文已删除并加入黑名单", async () => {
      await deleteWechatOfficialContentLibraryItem(article.id);
      await refreshWorkspace();
      if (contentDetail?.article.id === article.id) {
        setDetailOpen(false);
        setContentDetail(null);
      }
    }),
  });
};
```

对应按钮改成：

```tsx
<Button key="delete" size="small" danger loading={busyAction === `delete-${article.id}`} onClick={() => handleDeleteArticle(article)}>
  删除
</Button>
```

- [ ] **Step 3: 运行前端 build，确认类型和导入都没断**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS，页面还能正常加载内容库列表、详情、删除确认框，且没有类型报错。

---

### Task 4: 最后做一次收尾验证

**Files:**
- No code changes expected

- [ ] **Step 1: 跑后端回归测试文件，确认没有顺手把别的公众号链路弄坏**

Run:

```bash
pytest tests/backend/test_wechat_official_content_library.py -v
pytest tests/backend/test_wechat_official_redfox_collect.py -v
```

Expected: PASS。

- [ ] **Step 2: 跑前端生产构建，确认删除按钮、确认弹窗和 API 新函数都能编译**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS。

- [ ] **Step 3: 检查工作树改动只落在预期文件**

Run:

```bash
git status --short
```

Expected: 只看到这次内容库删除/黑名单相关文件，不应出现 `backend/app/services/wechat_official_draft_service.py`、`backend/app/api/drafts.py`、`frontend/src/pages/wechat-official` 的草稿区以外杂项改动。

---

## Self-review

- **Spec coverage:**
  - 真删除：`delete_article()` + `DELETE /{article_id}` + 前端按钮。
  - 不回流：`tombstone` 表 + crawl / redfox 两条入库 guard。
  - 删除后内容消失：详情 404、列表不再出现、相关派生数据清理。
  - 不碰草稿线程：Non-goals 明确排除草稿服务和草稿 API。
  - 验证：后端回归 + frontend build。

- **Placeholder scan:**
  - 没有 `TBD` / `TODO` / “稍后补” / 空泛占位。
  - 每个任务都给了明确文件、具体代码和命令。

- **Type consistency:**
  - 前端删除 API 返回 `{ id: number; status: string }`，和现有 `deleteSavedNote()` 一致。
  - tombstone 服务方法名固定为 `is_tombstoned()` / `tombstone()`，后续任务统一使用。
  - 后端删除接口返回 `{"id": article_id, "status": "deleted"}`，和其他 delete 风格一致。

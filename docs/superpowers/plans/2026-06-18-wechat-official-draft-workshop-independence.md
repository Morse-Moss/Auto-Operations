# 微信公众号草稿工坊独立化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把微信公众号草稿工坊改成真正的草稿箱：生成草稿后不再保留公众号文章来源引用，草稿删除/展示/校验都只围绕草稿本体。

**Architecture:** 继续复用现有 `AiDraft` 表，不新建公众号专用草稿表。公众号内容库仍负责文章候选和分析状态，草稿工坊只负责独立草稿；服务层不再写 `WechatOfficialDraftSource`，前端把公众号草稿当成独立实体，不再把文章候选伪装成草稿。

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy, pytest, React, Vite, TypeScript, Ant Design.

---

## File Structure

- `backend/app/services/wechat_official_draft_service.py` — 公众号草稿创建、序列化和 dry-run 的唯一服务入口；这里要断开 `WechatOfficialDraftSource` 的运行时依赖。
- `tests/backend/test_wechat_official_drafts.py` — 公众号草稿的回归测试，锁定“无来源引用”和“删文章不删草稿”的行为。
- `frontend/src/types/index.ts` — 公众号草稿前端类型定义；这里把 `WechatOfficialDraft` 变成不含来源引用的独立类型。
- `frontend/src/pages/wechat-official/wechat-official-dashboard.tsx` — 公众号工作台文案和草稿入口语义；这里把“草稿工坊”重新说清楚。

Non-goals:

- 不改 `backend/app/api/drafts.py` 的 XHS 草稿语义。
- 不新增数据库表或 Alembic migration。
- 不改公众号内容库的候选/分析逻辑本身。
- 不删除 `backend/app/models/wechat_official.py` 里的历史模型定义，只移除公众号草稿流程对它的运行时依赖。

---

### Task 1: Lock in source-free draft behavior with backend tests

**Files:**
- Modify: `tests/backend/test_wechat_official_drafts.py`

- [ ] **Step 1: Write the failing tests**

Add two tests to the existing file.

```python
def test_create_draft_from_content_library_returns_source_free_wechat_official_draft(tmp_path):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        headers = _register("draft-user")
        article_id = _create_article_with_snapshot(headers)

        response = client.post(
            f"/api/wechat-official/content-library/{article_id}/create-draft",
            headers=headers,
            json={"rewrite_style": "专业克制", "target_audience": "企业主", "call_to_action": "预约咨询"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["platform"] == "wechat_official"
        assert payload["title"] == "原文标题"
        assert "source_note_id" not in payload

        with TestingSessionLocal() as db:
            draft = db.get(AiDraft, payload["id"])
            source = db.scalar(
                select(WechatOfficialDraftSource).where(WechatOfficialDraftSource.draft_id == payload["id"])
            )
            assert draft is not None
            assert draft.platform == "wechat_official"
            assert source is None
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_deleted_content_article_does_not_remove_existing_wechat_official_draft(tmp_path):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        headers = _register("draft-delete-user")
        article_id = _create_article_with_snapshot(headers)

        response = client.post(
            f"/api/wechat-official/content-library/{article_id}/create-draft",
            headers=headers,
            json={"rewrite_style": "简洁", "target_audience": "运营", "call_to_action": "联系我"},
        )
        assert response.status_code == 200
        draft_id = response.json()["id"]

        with TestingSessionLocal() as db:
            article = db.get(WechatOfficialArticle, article_id)
            assert article is not None
            db.delete(article)
            db.commit()
            assert db.get(AiDraft, draft_id) is not None
    finally:
        app.dependency_overrides.pop(get_db, None)
```

- [ ] **Step 2: Run the tests and confirm they fail before the code change**

Run:

```bash
pytest tests/backend/test_wechat_official_drafts.py -v
```

Expected: FAIL because the current service still writes `WechatOfficialDraftSource` and the payload still exposes the old draft shape.

- [ ] **Step 3: Keep the existing template-analysis coverage but remove source-link expectations**

Update the existing template test so it still proves template metadata survives, but it no longer asserts a persisted source row.

```python
def test_create_draft_with_template_updates_article_analysis_without_persisting_source_link(tmp_path):
    get_db, TestingSessionLocal = _override_database(tmp_path)
    try:
        headers = _register("draft-template-user")
        article_id = _create_article_with_snapshot(headers)

        response = client.post(
            f"/api/wechat-official/content-library/{article_id}/create-draft",
            headers=headers,
            json={
                "rewrite_style": "提炼案例价值",
                "target_audience": "内容运营",
                "call_to_action": "收藏并复盘",
                "template_key": "case_rewrite",
                "template_name": "案例拆解",
                "template_instruction": "按 背景-冲突-方法-结果-启发 组织二创草稿。",
                "opening_angle": "从爆文结构拆解可复用方法",
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert "案例拆解" in payload["body"]
        assert "按 背景-冲突-方法-结果-启发 组织二创草稿。" in payload["body"]
        assert "从爆文结构拆解可复用方法" in payload["body"]

        with TestingSessionLocal() as db:
            source = db.scalar(select(WechatOfficialDraftSource).where(WechatOfficialDraftSource.draft_id == payload["id"]))
            article = db.get(WechatOfficialArticle, article_id)
            assert source is None
            assert article is not None
            assert article.raw_json["analysis"]["pool_status"] == "draft_ready"
            assert article.raw_json["analysis"]["draft_template_key"] == "case_rewrite"
    finally:
        app.dependency_overrides.pop(get_db, None)
```

---

### Task 2: Remove the runtime source link from the WeChat draft service

**Files:**
- Modify: `backend/app/services/wechat_official_draft_service.py`

- [ ] **Step 1: Remove the source-link write path**

Delete the `WechatOfficialDraftSource` import and stop creating the row in `create_draft_from_article()`.

```python
from backend.app.models import AiDraft, WechatOfficialArticleSnapshot


class WechatOfficialDraftService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_draft_from_article(self, user_id: int, article_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        article = get_owned_content_article(self.db, user_id, article_id)
        snapshot = self.db.scalar(
            select(WechatOfficialArticleSnapshot)
            .where(WechatOfficialArticleSnapshot.article_id == article.id)
            .order_by(WechatOfficialArticleSnapshot.captured_at.desc(), WechatOfficialArticleSnapshot.id.desc())
        )
        source_text = snapshot.text if snapshot and snapshot.text else article.digest
        rewrite_style = str(payload.get("rewrite_style") or "保持原文结构").strip()
        target_audience = str(payload.get("target_audience") or "公众号读者").strip()
        call_to_action = str(payload.get("call_to_action") or "关注后续更新").strip()
        template_key = str(payload.get("template_key") or "").strip()
        template_name = str(payload.get("template_name") or "").strip()
        template_instruction = str(payload.get("template_instruction") or "").strip()
        opening_angle = str(payload.get("opening_angle") or "").strip()
        analysis = dict((article.raw_json or {}).get("analysis") or {})
        hotspot = analysis.get("hotspot_breakdown") if isinstance(analysis.get("hotspot_breakdown"), dict) else {}
        hotspot_text = _hotspot_text(hotspot)
        body = (
            f"改写风格：{rewrite_style}\n"
            f"目标读者：{target_audience}\n"
            f"行动引导：{call_to_action}\n\n"
            f"原文摘要：{article.digest}\n\n"
            f"爆点拆解：\n{hotspot_text}\n\n"
            f"改写参考：\n{source_text}"
        )
        draft = AiDraft(user_id=user_id, platform="wechat_official", title=article.title, body=body, tags=[])
        self.db.add(draft)
        self.db.flush()
        raw = dict(article.raw_json or {})
        analysis["pool_status"] = "draft_ready"
        if template_key:
            analysis["draft_template_key"] = template_key
        raw["analysis"] = analysis
        article.raw_json = raw
        flag_modified(article, "raw_json")
        self.db.commit()
        self.db.refresh(draft)
        return serialize_draft(draft)
```

- [ ] **Step 2: Make the serializer source-free for the WeChat workflow**

Return only the draft fields that the公众号 flow needs.

```python
def serialize_draft(draft: AiDraft) -> dict[str, Any]:
    return {
        "id": draft.id,
        "platform": draft.platform,
        "title": draft.title,
        "body": draft.body,
        "tags": draft.tags or [],
        "created_at": draft.created_at.isoformat() if draft.created_at else None,
    }
```

- [ ] **Step 3: Run the backend tests again and make sure they pass**

Run:

```bash
pytest tests/backend/test_wechat_official_drafts.py -v
```

Expected: PASS, with no `WechatOfficialDraftSource` rows created and the article-deletion test still leaving the draft intact.

- [ ] **Step 4: Keep the content-library handler untouched unless the test forces a change**

Do not add new logic in `backend/app/api/platforms/wechat_official/content_library.py`; it should continue delegating to the service and inherit the source-free payload shape.

---

### Task 3: Align frontend draft types and copy with the new draft-only semantics

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/pages/wechat-official/wechat-official-dashboard.tsx`

- [ ] **Step 1: Update the failing type shape and page copy in one pass**

Change the公众号 draft type so the frontend no longer expects a source reference on WeChat drafts, and rewrite the page copy so “草稿工坊” reads like a draft box instead of a candidate pool.

```typescript
export type WechatOfficialDraft = Omit<Draft, "source_note_id"> & {
  platform: "wechat_official";
};
```

```tsx
const SECTION_COPY: Record<WechatOfficialSection, { title: string; description: string }> = {
  dashboard: {
    title: "公众号运营总览",
    description: "汇总 Redfox 配置、内容库文章、草稿工坊和 blocked 动作状态。",
  },
  drafts: {
    title: "公众号草稿工坊",
    description: "这里只管理独立草稿；从内容库生成后不再保留来源引用。",
  },
  settings: {
    title: "Redfox 设置",
    description: "配置和校验 Redfox API Key；Redfox 只作为内容数据源。",
  },
};
```

If the page has a label that still suggests “候选帖子” in the draft area, change that copy to talk about “独立草稿” or “草稿箱”, not article candidates.

- [ ] **Step 2: Run the frontend build to catch any type drift**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS, with `WechatOfficialDraft` still assignable everywhere the page uses the creation response.

- [ ] **Step 3: Keep the generic draft model untouched**

Do not change `Draft` in `frontend/src/types/index.ts` or `backend/app/api/drafts.py`; the XHS draft flow still needs `source_note_id`, and this plan is only about the公众号 flow.

---

### Task 4: Run the final verification pass

**Files:**
- No code changes expected

- [ ] **Step 1: Run the focused backend regression suite**

Run:

```bash
pytest tests/backend/test_wechat_official_drafts.py -v
```

Expected: PASS.

- [ ] **Step 2: Run the frontend production build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 3: Check the working tree for only the intended files**

Run:

```bash
git status --short
```

Expected: only the plan doc plus the implementation files from the three tasks, with no accidental edits under `backend/app/api/drafts.py` or `backend/app/models/wechat_official.py`.

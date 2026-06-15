# Creator Binding and Rewrite Templates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Creator account binding discoverable from publish flow and make AI rewrite safer through explicit rewrite templates.

**Architecture:** Keep publishing backend rules unchanged: only XHS Creator accounts can publish. Add front-end routing/UX guidance so publish center can deep-link to Creator binding, and isolate rewrite prompt templates in a small reusable module with tests.

**Tech Stack:** React, TypeScript, Vite, Ant Design, React Router.

---

## File Structure

- Create: `frontend/src/pages/platforms/xhs/rewrite-templates.ts`
  - Owns rewrite template keys, copy, button labels, descriptions, and default template.
- Create: `frontend/src/pages/platforms/xhs/rewrite-templates.test.ts`
  - Verifies default safe template and required template copy.
- Modify: `frontend/src/pages/platforms/xhs/rewrite-page.tsx`
  - Imports templates, adds Segmented template selector, keeps custom instruction editable, changes action button label by selected template.
- Modify: `frontend/src/pages/platforms/xhs/publish-page.tsx`
  - Adds Creator binding guidance when no Creator account exists and deep-links to account matrix.
- Modify: `frontend/src/pages/platforms/xhs/accounts-page.tsx`
  - Reads `?bind=creator`, opens account drawer automatically, passes default account type.
- Modify: `frontend/src/components/account/add-account-drawer.tsx`
  - Supports `defaultAccountType` and resets to Creator when opened from deep link.

## Task 1: Rewrite Template Module and Tests

**Files:**
- Create: `frontend/src/pages/platforms/xhs/rewrite-templates.ts`
- Create: `frontend/src/pages/platforms/xhs/rewrite-templates.test.ts`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/pages/platforms/xhs/rewrite-templates.test.ts`:

```ts
import { DEFAULT_REWRITE_TEMPLATE_KEY, REWRITE_TEMPLATES } from "./rewrite-templates";

describe("rewrite templates", () => {
  it("uses safe rewrite as the default template", () => {
    expect(DEFAULT_REWRITE_TEMPLATE_KEY).toBe("safe");
    expect(REWRITE_TEMPLATES.safe.label).toBe("安全改写");
    expect(REWRITE_TEMPLATES.safe.buttonLabel).toBe("生成安全改写版");
  });

  it("keeps safe rewrite focused on avoiding source similarity", () => {
    expect(REWRITE_TEMPLATES.safe.instruction).toContain("不要逐句同义替换");
    expect(REWRITE_TEMPLATES.safe.instruction).toContain("避免出现与原文明显相同");
    expect(REWRITE_TEMPLATES.safe.instruction).toContain("不新增未经原文支持");
  });

  it("defines exactly the three operator-facing rewrite modes", () => {
    expect(Object.keys(REWRITE_TEMPLATES)).toEqual(["safe", "polish", "seed"]);
    expect(REWRITE_TEMPLATES.polish.description).toBe("适合原创短文，只优化表达");
    expect(REWRITE_TEMPLATES.seed.description).toBe("适合内容太平，增强场景和转化");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- rewrite-templates.test.ts --runInBand`

Expected: FAIL because `./rewrite-templates` does not exist. If the project uses Vitest instead of Jest, run the equivalent configured command discovered in `frontend/package.json`.

- [ ] **Step 3: Implement rewrite template module**

Create `frontend/src/pages/platforms/xhs/rewrite-templates.ts`:

```ts
export type RewriteTemplateKey = "safe" | "polish" | "seed";

export type RewriteTemplate = {
  label: string;
  buttonLabel: string;
  description: string;
  instruction: string;
};

export const DEFAULT_REWRITE_TEMPLATE_KEY: RewriteTemplateKey = "safe";

export const REWRITE_TEMPLATES: Record<RewriteTemplateKey, RewriteTemplate> = {
  safe: {
    label: "安全改写",
    buttonLabel: "生成安全改写版",
    description: "适合参考竞品，降低相似风险",
    instruction:
      "保留原文事实、核心卖点和内容逻辑，但不要逐句同义替换。\n" +
      "请重组表达顺序、改变句式和语气，写成一篇自然的小红书种草笔记。\n" +
      "避免出现与原文明显相同的句子、连续短语或段落结构；长内容要像重新写过，而不是轻微润色。\n" +
      "不新增未经原文支持的功效、数据、承诺或夸张表达。",
  },
  polish: {
    label: "轻度润色",
    buttonLabel: "生成轻度润色版",
    description: "适合原创短文，只优化表达",
    instruction:
      "在不改变原意和内容顺序的前提下，轻度润色表达。\n" +
      "让语气更自然、更像真实用户分享，减少生硬、重复和机器感。\n" +
      "不要大幅重写，不要添加新信息，不要改变事实。\n" +
      "适合短内容或已基本成型的原创草稿。",
  },
  seed: {
    label: "种草增强",
    buttonLabel: "生成种草增强版",
    description: "适合内容太平，增强场景和转化",
    instruction:
      "保留事实和核心卖点，增强小红书种草感。\n" +
      "请加入更自然的使用场景、用户痛点、体验感和情绪表达，让内容更有吸引力。\n" +
      "表达要口语化、有分享感，但不要夸大效果，不要编造数据、价格、功效或个人经历。\n" +
      "如果原文信息不足，优先用更自然的表达承接，不要硬编细节。",
  },
};
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- rewrite-templates.test.ts --runInBand`

Expected: PASS.

## Task 2: Creator Binding Deep Link

**Files:**
- Modify: `frontend/src/components/account/add-account-drawer.tsx`
- Modify: `frontend/src/pages/platforms/xhs/accounts-page.tsx`

- [ ] **Step 1: Update AddAccountDrawer props and open reset behavior**

In `frontend/src/components/account/add-account-drawer.tsx`, import `useEffect` and add a `defaultAccountType` prop:

```ts
import { useEffect, useState } from "react";
```

Update props:

```ts
type AddAccountDrawerProps = {
  open: boolean;
  onClose: () => void;
  onBound: () => void;
  defaultAccountType?: "pc" | "creator";
};
```

Update component signature and state:

```ts
export function AddAccountDrawer({ open, onClose, onBound, defaultAccountType = "pc" }: AddAccountDrawerProps) {
  const [platform, setPlatform] = useState<AccountPlatform>("xhs");
  const [accountType, setAccountType] = useState<AccountType>(defaultAccountType);
  const [method, setMethod] = useState<LoginMethod>("qr");

  useEffect(() => {
    if (!open) return;
    setPlatform("xhs");
    setAccountType(defaultAccountType);
    setMethod("qr");
  }, [defaultAccountType, open]);
```

- [ ] **Step 2: Update accounts page to read deep link**

In `frontend/src/pages/platforms/xhs/accounts-page.tsx`, import `useSearchParams`:

```ts
import { useSearchParams } from "react-router-dom";
```

Inside component:

```ts
const [searchParams] = useSearchParams();
const defaultAccountType = searchParams.get("bind") === "creator" ? "creator" : "pc";
```

Add effect:

```ts
useEffect(() => {
  if (searchParams.get("bind") === "creator") {
    setDrawerOpen(true);
  }
}, [searchParams]);
```

Pass prop:

```tsx
<AddAccountDrawer
  open={drawerOpen}
  onClose={() => setDrawerOpen(false)}
  onBound={loadAccounts}
  defaultAccountType={defaultAccountType}
/>
```

- [ ] **Step 3: Verify manually through browser or dev server**

Run app, open `/platforms/xhs/accounts?bind=creator`, verify drawer opens with 小红书 + Creator + 二维码 selected.

## Task 3: Publish Center Creator Guidance

**Files:**
- Modify: `frontend/src/pages/platforms/xhs/publish-page.tsx`

- [ ] **Step 1: Import navigation and add account status derivations**

Add:

```ts
import { useNavigate } from "react-router-dom";
```

Inside component:

```ts
const navigate = useNavigate();
const xhsAccounts = accounts.filter((a) => a.platform === "xhs");
const pcAccounts = xhsAccounts.filter((a) => a.sub_type === "pc");
const hasCreatorAccounts = creatorAccounts.length > 0;
```

- [ ] **Step 2: Improve Select labels**

Change options mapping to:

```ts
options={creatorAccounts.map((a) => ({
  value: a.id,
  label: `${a.nickname || `账号 #${a.id}`} · Creator${a.status && a.status !== "unknown" ? ` · ${a.status === "active" || a.status === "healthy" ? "正常" : a.status}` : ""}`,
}))}
```

- [ ] **Step 3: Add empty guidance below Select**

Inside the `Form.Item label="发布账号" required` block, after `Select`, add:

```tsx
{!hasCreatorAccounts && (
  <Alert
    type="warning"
    showIcon
    style={{ marginTop: 8 }}
    message="发布需要小红书 Creator 账号"
    description={
      <Space direction="vertical" size={4}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {pcAccounts.length > 0
            ? "当前只检测到小红书 PC 账号。PC 账号可用于搜索和采集，发布中心需要单独绑定 Creator 账号。"
            : "当前还没有可用于发布的小红书 Creator 账号。"}
        </Text>
        <Button size="small" type="link" style={{ padding: 0 }} onClick={() => navigate("/platforms/xhs/accounts?bind=creator")}>
          去绑定 Creator 账号
        </Button>
      </Space>
    }
  />
)}
```

- [ ] **Step 4: Verify manually**

With no Creator account returned by `/accounts?platform=xhs`, publish center shows the warning and navigation button.

## Task 4: Rewrite Template UI

**Files:**
- Modify: `frontend/src/pages/platforms/xhs/rewrite-page.tsx`

- [ ] **Step 1: Import template module and Segmented already exists**

Add import:

```ts
import { DEFAULT_REWRITE_TEMPLATE_KEY, REWRITE_TEMPLATES } from "./rewrite-templates";
import type { RewriteTemplateKey } from "./rewrite-templates";
```

- [ ] **Step 2: Replace default instruction state**

Change:

```ts
const [instruction, setInstruction] = useState("保留事实，增强小红书种草感，语气自然。");
```

To:

```ts
const [rewriteTemplate, setRewriteTemplate] = useState<RewriteTemplateKey>(DEFAULT_REWRITE_TEMPLATE_KEY);
const [instruction, setInstruction] = useState(REWRITE_TEMPLATES[DEFAULT_REWRITE_TEMPLATE_KEY].instruction);
```

- [ ] **Step 3: Add helper to switch templates**

Inside component:

```ts
function handleRewriteTemplateChange(value: string | number) {
  const next = value as RewriteTemplateKey;
  setRewriteTemplate(next);
  setInstruction(REWRITE_TEMPLATES[next].instruction);
}
```

- [ ] **Step 4: Add template selector UI above AI instruction input**

Inside AI 助手 card, before the existing “AI 改写指令” label, add:

```tsx
<div style={{ marginBottom: 12 }}>
  <Text type="secondary" style={{ fontSize: 12, display: "block", marginBottom: 6 }}>
    改写模式
  </Text>
  <Segmented
    block
    size="small"
    value={rewriteTemplate}
    onChange={handleRewriteTemplateChange}
    options={Object.entries(REWRITE_TEMPLATES).map(([key, template]) => ({
      value: key,
      label: template.label,
    }))}
  />
  <Text type="secondary" style={{ display: "block", marginTop: 6, fontSize: 11 }}>
    {REWRITE_TEMPLATES[rewriteTemplate].description}
  </Text>
</div>
```

- [ ] **Step 5: Change instruction input and action button**

Change instruction input from single-line `Input` to `TextArea`:

```tsx
<TextArea
  value={instruction}
  onChange={(e) => setInstruction(e.target.value)}
  placeholder="填写 AI 改写指令"
  rows={5}
  style={{ marginBottom: 8 }}
/>
```

Change button text:

```tsx
{REWRITE_TEMPLATES[rewriteTemplate].buttonLabel}
```

- [ ] **Step 6: Run frontend build**

Run: `cd frontend && npm run build`

Expected: PASS.

## Self-Review

- Spec coverage: The plan covers Creator binding discoverability, Creator deep link, three rewrite templates, default safe template, and verification.
- Placeholder scan: No TBD/TODO/fill-in placeholders remain.
- Type consistency: `RewriteTemplateKey`, `REWRITE_TEMPLATES`, and `defaultAccountType` names are consistent across tasks.

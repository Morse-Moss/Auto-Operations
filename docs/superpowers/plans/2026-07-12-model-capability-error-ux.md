# Model Capability Error UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show actionable Chinese model-capability errors and ensure XHS draft AI actions display one failure notification instead of duplicate global and page-level toasts.

**Architecture:** Extract API error formatting into a small pure module with focused Node tests, then re-export it through the existing API facade. Mark only XHS draft AI requests that already have local catch handlers as silent so the page remains the single presentation owner.

**Tech Stack:** TypeScript 5.9, Axios, React 19, Ant Design, Node 24 native TypeScript execution, Vite.

---

## Execution Constraints

- This plan is independent of the MySQL migration recovery plan and must not block backend recovery.
- Use the same isolated feature worktree only if the backend plan has not entered production integration; otherwise use a separate branch `fix/model-capability-error-ux`.
- Do not alter backend error payloads or capability-routing semantics.
- Do not silence requests unless the caller already catches and presents the error.
- Do not commit, merge, push, or deploy without the corresponding explicit authorization.
- Design reference: `docs/superpowers/specs/2026-07-12-mysql-capability-migration-recovery-design.md` section 5.4.

## File Map

- `frontend/src/lib/api-errors.ts`: own deterministic API error extraction and model-capability message mapping.
- `frontend/src/lib/api.ts`: import/re-export the formatter and mark locally handled draft AI calls as silent.
- `frontend/tests/api-errors.test.ts`: test structured errors, legacy strings, fallback behavior, and silent request contracts.
- `frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx`: verify only; existing local catch handlers remain the notification owner.

### Task 1: Extract and Test Actionable Capability Errors

**Files:**
- Create: `frontend/tests/api-errors.test.ts`
- Create: `frontend/src/lib/api-errors.ts`
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Write the failing formatter tests**

Create `frontend/tests/api-errors.test.ts`:

```typescript
import assert from "node:assert/strict";

import { apiErrorMessage } from "../src/lib/api-errors.ts";


function axiosError(data: unknown): unknown {
  return {
    isAxiosError: true,
    response: { data },
  };
}


assert.equal(
  apiErrorMessage(
    axiosError({
      detail: {
        code: "MODEL_CAPABILITY_DEFAULT_NOT_CONFIGURED",
        capability: "text",
      },
    }),
    "fallback",
  ),
  "文本生成模型尚未配置，请联系管理员在模型配置中设置文本默认模型。",
);

assert.equal(
  apiErrorMessage(
    axiosError({
      detail: {
        code: "MODEL_CAPABILITY_DEFAULT_INVALID",
        capability: "vision",
      },
    }),
    "fallback",
  ),
  "图片理解模型配置已失效，请联系管理员检查能力路由。",
);

assert.equal(
  apiErrorMessage(
    axiosError({
      detail: {
        code: "MODEL_CAPABILITY_DEFAULT_INCOMPLETE",
        capability: "image_generation",
      },
    }),
    "fallback",
  ),
  "图片生成模型配置不完整，请联系管理员检查模型名称、地址和密钥。",
);

assert.equal(
  apiErrorMessage(axiosError({ detail: "legacy detail" }), "fallback"),
  "legacy detail",
);
assert.equal(
  apiErrorMessage(
    axiosError({ detail: { message: "structured message" } }),
    "fallback",
  ),
  "structured message",
);
assert.equal(apiErrorMessage(new Error("plain"), "fallback"), "fallback");

console.log("api-errors tests passed");
```

- [ ] **Step 2: Run the formatter test and confirm RED**

Run:

```powershell
node frontend/tests/api-errors.test.ts
```

Expected: FAIL with module-not-found because `frontend/src/lib/api-errors.ts` does not exist.

- [ ] **Step 3: Implement the pure error formatter**

Create `frontend/src/lib/api-errors.ts`:

```typescript
import axios from "axios";


const CAPABILITY_LABELS: Record<string, string> = {
  text: "文本生成",
  vision: "图片理解",
  image_generation: "图片生成",
};

const CAPABILITY_DEFAULT_LABELS: Record<string, string> = {
  text: "文本",
  vision: "图片理解",
  image_generation: "图片生成",
};


function capabilityErrorMessage(record: Record<string, unknown>): string | null {
  const code = typeof record.code === "string" ? record.code : "";
  const capability = typeof record.capability === "string" ? record.capability : "";
  const label = CAPABILITY_LABELS[capability] || "AI";
  const defaultLabel = CAPABILITY_DEFAULT_LABELS[capability] || label;

  if (code === "MODEL_CAPABILITY_DEFAULT_NOT_CONFIGURED") {
    return `${label}模型尚未配置，请联系管理员在模型配置中设置${defaultLabel}默认模型。`;
  }
  if (code === "MODEL_CAPABILITY_DEFAULT_INVALID") {
    return `${label}模型配置已失效，请联系管理员检查能力路由。`;
  }
  if (code === "MODEL_CAPABILITY_DEFAULT_INCOMPATIBLE") {
    return `${label}模型与当前能力不兼容，请联系管理员重新设置能力路由。`;
  }
  if (code === "MODEL_CAPABILITY_DEFAULT_INCOMPLETE") {
    return `${label}模型配置不完整，请联系管理员检查模型名称、地址和密钥。`;
  }
  return null;
}


export function apiErrorMessage(error: unknown, fallback: string): string {
  if (!axios.isAxiosError(error)) return fallback;
  const data = error.response?.data;
  if (!data || typeof data !== "object") return fallback;

  const record = data as Record<string, unknown>;
  if (typeof record.message === "string" && record.message.trim()) {
    return record.message;
  }

  const detail = record.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (detail && typeof detail === "object") {
    const detailRecord = detail as Record<string, unknown>;
    if (typeof detailRecord.message === "string" && detailRecord.message.trim()) {
      return detailRecord.message;
    }
    const capabilityMessage = capabilityErrorMessage(detailRecord);
    if (capabilityMessage) return capabilityMessage;
  }

  return capabilityErrorMessage(record) || fallback;
}
```

- [ ] **Step 4: Preserve the existing API facade export**

In `frontend/src/lib/api.ts`, add near the other local imports:

```typescript
import { apiErrorMessage } from "./api-errors";

export { apiErrorMessage } from "./api-errors";
```

Delete only the old inline `apiErrorMessage` function from `api.ts`. Keep `getUsageLimitError` and all call sites unchanged.

- [ ] **Step 5: Run formatter tests and TypeScript build**

Run:

```powershell
node frontend/tests/api-errors.test.ts
npm --prefix frontend run build
```

Expected: `api-errors tests passed`; TypeScript and Vite build succeed.

- [ ] **Step 6: Review the formatter diff**

Run:

```powershell
git diff --check -- frontend/src/lib/api-errors.ts frontend/src/lib/api.ts frontend/tests/api-errors.test.ts
git diff -- frontend/src/lib/api-errors.ts frontend/src/lib/api.ts frontend/tests/api-errors.test.ts
```

Expected: legacy extraction precedence remains `data.message`, string `detail`, object `detail.message`, capability code, fallback.

- [ ] **Step 7: Commit only after explicit commit authorization**

```powershell
git add -- frontend/src/lib/api-errors.ts frontend/src/lib/api.ts frontend/tests/api-errors.test.ts
git commit -m "fix: explain model capability errors"
```

### Task 2: Make Draft AI Actions Use a Single Notification Owner

**Files:**
- Modify: `frontend/tests/api-errors.test.ts`
- Modify: `frontend/src/lib/api.ts`
- Verify: `frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx`

- [ ] **Step 1: Add failing silent-request contract assertions**

Append to `frontend/tests/api-errors.test.ts`:

```typescript
import { readFileSync } from "node:fs";


const apiSource = readFileSync("frontend/src/lib/api.ts", "utf8");

for (const endpoint of [
  "/ai/rewrite-note",
  "/ai/generate-title",
  "/ai/generate-tags",
]) {
  const escapedEndpoint = endpoint.replaceAll("/", "\\/");
  assert.match(
    apiSource,
    new RegExp(`${escapedEndpoint}[^;]+_silent: true`, "s"),
    `${endpoint} should let the draft workbench own its error notification`,
  );
}

assert.match(
  apiSource,
  /\/drafts\/\$\{draftId\}\/ai-score[^;]+_silent: true/s,
  "draft scoring should let the draft workbench own its error notification",
);
```

Move the existing `console.log("api-errors tests passed")` to the bottom of the file after these assertions.

- [ ] **Step 2: Run the contract test and confirm RED**

Run:

```powershell
node frontend/tests/api-errors.test.ts
```

Expected: FAIL because the four requests do not currently set `_silent: true`.

- [ ] **Step 3: Mark only locally handled requests as silent**

Update these functions in `frontend/src/lib/api.ts`:

```typescript
export async function scoreDraftWithAi(draftId: number): Promise<DraftAiScoreResult> {
  const response = await http.post<DraftAiScoreResult>(
    `/drafts/${draftId}/ai-score`,
    {},
    { _silent: true } as never,
  );
  return response.data;
}

export async function rewriteDraftWithAi(payload: RewriteDraftPayload): Promise<Draft> {
  const response = await http.post<Draft>(
    "/ai/rewrite-note",
    payload,
    { _silent: true } as never,
  );
  return response.data;
}

export async function generateTitleOptions(payload: GenerateTitlePayload): Promise<{ items: string[] }> {
  const response = await http.post<{ items: string[] }>(
    "/ai/generate-title",
    payload,
    { _silent: true } as never,
  );
  return response.data;
}

export async function generateTagOptions(payload: GenerateTagsPayload): Promise<{ items: string[] }> {
  const response = await http.post<{ items: string[] }>(
    "/ai/generate-tags",
    payload,
    { _silent: true } as never,
  );
  return response.data;
}
```

Do not silence `generateNoteWithAi`, `polishTextWithAi`, or image-generation calls in this task because their notification ownership is outside the XHS draft-workbench scope.

- [ ] **Step 4: Verify page-level catch ownership remains present**

Run:

```powershell
rg -n "handleRewrite|handleGenerateTitles|handleGenerateTags|handleScoreDraft|antMessage.error" frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx
```

Expected: each of the four handlers still catches errors and calls `antMessage.error(...)` with quota handling followed by `apiErrorMessage(...)`.

- [ ] **Step 5: Run the frontend verification set**

Run:

```powershell
node frontend/tests/api-errors.test.ts
node frontend/tests/diagnostics-contract.test.ts
py -X utf8 -m pytest tests/frontend/test_model_capability_routing_contract.py -q
npm --prefix frontend run build
```

Expected: Node tests print their pass messages; pytest passes; production build succeeds.

- [ ] **Step 6: Review scope and optionally commit**

Run:

```powershell
git diff --check -- frontend/src/lib/api-errors.ts frontend/src/lib/api.ts frontend/tests/api-errors.test.ts
git status --short --branch
```

After explicit commit authorization only:

```powershell
git add -- frontend/src/lib/api-errors.ts frontend/src/lib/api.ts frontend/tests/api-errors.test.ts
git commit -m "fix: avoid duplicate ai error notices"
```

### Task 3: Handoff Without Coupling to Production Recovery

**Files:**
- Verify: `frontend/src/lib/api-errors.ts`
- Verify: `frontend/src/lib/api.ts`
- Verify: `frontend/tests/api-errors.test.ts`

- [ ] **Step 1: Report branch-local verification**

Report the branch/worktree, changed files, Node test output, pytest result, and frontend build result. State explicitly that production behavior is unchanged until the branch is merged, pushed, and deployed.

- [ ] **Step 2: Decide integration timing**

Present two safe choices:

1. Merge this verified frontend slice with the backend recovery branch before the single authorized production push.
2. Deploy backend recovery first, then merge and deploy this frontend slice separately.

Recommend choice 1 only when both slices have already passed independently; otherwise prioritize backend recovery.

- [ ] **Step 3: Reuse the backend plan's integration gates**

Follow `docs/superpowers/plans/2026-07-12-mysql-capability-migration-recovery.md` Task 4 for merge, push, deployment, and production verification. Do not duplicate or bypass its backup and authorization requirements.

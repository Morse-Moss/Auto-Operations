# Multiplatform Ops Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or Morse's development mode to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the first-round multiplatform operations foundation: Platform Registry + Capability Matrix + frontend platform center compatibility, while preserving existing XHS flows.

**Architecture:** Keep the existing FastAPI + React/Vite foundation. Upgrade `backend/app/core/platforms.py` from display-only platform metadata into a code-defined capability registry, expose richer registry APIs, and make the frontend platform center consume the enriched shape without a navigation redesign.

**Tech Stack:** Python/FastAPI, dataclasses/enums, pytest, React/Vite/TypeScript, Ant Design.

---

## Scope Firewall

Allowed for Stage 1:
- `backend/app/core/platforms.py`
- `backend/app/services/platform_service.py`
- `backend/app/api/platforms/registry.py`
- `tests/backend/test_platforms.py`

Allowed for Stage 2:
- `frontend/src/types/index.ts`
- `frontend/src/lib/platforms.ts`
- `frontend/src/components/layout/platform-selector.tsx`
- `frontend/src/lib/api.ts` only if needed

Allowed orchestration/docs:
- `docs/superpowers/specs/2026-06-09-multiplatform-ops-foundation-design.md`
- `docs/superpowers/plans/2026-06-09-multiplatform-ops-foundation.md`

Forbidden:
- `apis/`, `xhs_utils/`, `static/`
- XHS crawl/publish/monitoring business implementations
- Huitun-related files
- Docker/config/README/CLAUDE.md
- real new platform integration
- commits, pushes, dependency installs, deploys, worktrees without approval

## Task 1: Backend Platform Registry + Capability Matrix

**Files:**
- Modify: `tests/backend/test_platforms.py`
- Modify: `backend/app/core/platforms.py`
- Modify: `backend/app/services/platform_service.py`
- Modify: `backend/app/api/platforms/registry.py`

- [ ] Step 1: Write failing tests in `tests/backend/test_platforms.py` for enriched platform metadata, XHS capability matrix, planned platform metadata, platform detail lookup, and missing platform errors.
- [ ] Step 2: Run `python -m pytest tests/backend/test_platforms.py -q` and verify RED because fields/API helpers are missing.
- [ ] Step 3: Implement minimal registry structures in `backend/app/core/platforms.py`: enums, `PlatformCapability`, enriched `PlatformMeta`, XHS capabilities, planned CN platforms, compatibility `status` field.
- [ ] Step 4: Implement service helpers in `backend/app/services/platform_service.py`: `list_platforms()` and `get_platform_detail(platform_id: str)`.
- [ ] Step 5: Add `GET /platforms/{platform_id}` to `backend/app/api/platforms/registry.py`, returning 404 `platform_not_found` for unknown IDs.
- [ ] Step 6: Run `python -m pytest tests/backend/test_platforms.py -q` and verify GREEN.
- [ ] Step 7: Independent read-only review: scope compliance, spec compliance, backwards compatibility, no forbidden files.

## Task 2: Frontend Platform Center Compatibility

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/platforms.ts`
- Modify: `frontend/src/components/layout/platform-selector.tsx`
- Modify: `frontend/src/lib/api.ts` only if needed

- [ ] Step 1: Extend `PlatformMeta` and related types minimally for new registry fields.
- [ ] Step 2: Update `fallbackPlatforms` to include new fields and stay compatible with backend shape.
- [ ] Step 3: Change platform card route selection to prefer `platform.default_route` when enabled.
- [ ] Step 4: Keep existing UI and Coming Soon behavior; no navigation redesign.
- [ ] Step 5: Run `cd frontend && npm run build` and verify GREEN.
- [ ] Step 6: Independent read-only review: UI scope, type compatibility, no unrelated type changes.

## Task 3: Final Verification and Evidence Ledger

- [ ] Run `python -m pytest tests/backend/test_platforms.py -q`.
- [ ] Run `cd frontend && npm run build`.
- [ ] Run `git diff --check`.
- [ ] Inspect diff to confirm only allowed files plus approved orchestration docs changed.
- [ ] Produce evidence ledger with stage contracts, changed files, verification output, review verdicts, boundaries, and next recommendation.

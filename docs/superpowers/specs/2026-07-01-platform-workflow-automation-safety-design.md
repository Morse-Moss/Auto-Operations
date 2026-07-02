# Platform Workflow Automation Safety Design

**Goal:** Define how workflow automation can evolve from XHS AutoTask while guaranteeing that background jobs cannot silently publish, upload, comment, reply, or mutate external platforms.

## Current Scope

This is a design-only safety gate for future migration of automation behavior into Platform Core. It defines the required control plane, stop conditions, and future test expectations before any real background automation work is allowed. It does not implement workflow execution changes or alter current runtime behavior.

## Stop Conditions

- No background real action implementation in this design task.
- No provider calls.
- No database migration.
- No scheduler execution expansion.

If any future task requires crossing one of these boundaries, it must stop and request explicit user approval before implementation.

## Non-Goals

- No real publish, upload, comment, reply, follow, like, collect, direct-message, or engagement action.
- No automatic conversion of historical XHS AutoTasks into real external write privileges.
- No new scheduler loop, worker queue, retry path, or provider client wiring.
- No changes to `apis/`, `xhs_utils/`, `static/`, database schema, or Alembic migrations.

## Required Architecture Before Implementation

- **Workflow definition and step capability keys:** every step must declare a capability key such as `workflow.prepare_draft`, `workflow.review_required`, `publish.post_note`, `comment.reply`, or `engagement.like`. Unknown or missing keys fail closed.
- **Risk policy default:** workflow risk evaluation must set `real_publish_authorized=false` by default. External mutation capabilities are denied unless an explicit policy entry enables that platform/capability pair.
- **Authorization reference for real actions:** any step that can mutate an external platform requires an `authorization_ref` bound to operator, platform, account, capability, workflow/job, target object, expiry, and correlation ID.
- **Pending-job-only scheduler behavior:** until user approval, the background runner may only create pending jobs or review tasks. It must not execute real external actions, retries, comments, replies, engagement, uploads, or publishes.
- **Audit event before real action:** future real external actions must record an audit event before adapter/provider invocation. The audit event must include platform, capability, account reference, workflow/job reference, authorization reference, operator, and correlation ID.
- **Kill switch per platform/capability:** a fail-closed disable switch must block real actions for each platform/capability even when an authorization reference exists.

## State Model

- `draft`: workflow definition exists but cannot be scheduled.
- `scheduled`: workflow can create pending jobs only.
- `pending_authorization`: a job needs operator review before any external mutation.
- `authorized_once`: a specific job step has a valid `authorization_ref`; authorization is scoped and expires.
- `executed`: a future real action completed after audit and authorization checks.
- `blocked`: policy, missing authorization, kill switch, unsupported capability, or expired authorization stopped the step.

Historical XHS AutoTasks should map only to `scheduled` or `pending_authorization` states. They must not inherit `authorized_once` or any publish/comment/reply/engagement privilege from legacy configuration.

## Operator UX

Operators should see automation as a preparation and review queue first: collect inputs, generate drafts, validate readiness, and present pending jobs. Any step that may affect a real account must show the platform, account, target object, capability, risk explanation, expiry, and the exact action being authorized before it can receive an `authorization_ref`.

Blocked jobs should explain the next safe action, for example: enable the capability in policy, request one-time authorization, or leave the job pending. They must not suggest bypassing platform rules or account safety controls.

## Diagnostics And Audit

Diagnostics may describe blocked/allowed workflow states, missing authorization, expired authorization, disabled capabilities, unsupported platforms, and scheduler pending-only mode. Diagnostics must not include cookies, tokens, raw provider payloads, or secrets.

Audit must be append-only in future implementation and must be emitted before any provider/adapter call. If audit emission fails, the real action fails closed.

## Migration Sequence

1. Define pure workflow, capability, risk policy, pending job, authorization, kill-switch, and audit contracts with fake/trap adapters only.
2. Add tests that prove historical AutoTasks map to pending-only behavior.
3. Wire scheduler planning to create pending jobs without provider clients or real adapter construction.
4. Add operator approval flow that creates scoped `authorization_ref` records or tokens, still with trap adapters.
5. Only after explicit user approval, enable one platform/capability pair behind policy, audit-before-call, and kill switch.
6. Keep comments, replies, engagement, and retry actions blocked until each capability receives a separate policy and UX review.

## Minimum Future Tests

- Historical AutoTasks do not gain publish privileges.
- Background runner creates pending jobs only.
- Any real action step without authorization fails closed.
- Comment/reply/engagement capabilities are blocked unless explicitly enabled.
- Unknown workflow capability keys fail closed.
- Kill switch blocks a real action even when authorization exists.
- Audit event is recorded before any future real external action; audit failure blocks the action.

## User Impact

Operators can automate preparation, validation, draft generation, and review queues without losing final control over real external account actions. This keeps the path to workflow automation open while preventing silent background publish/upload/comment/reply/engagement behavior that could damage accounts or surprise users.

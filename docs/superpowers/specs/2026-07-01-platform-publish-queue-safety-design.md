# Platform Publish Queue Safety Design

**Goal:** Define how publish queue migration can proceed while guaranteeing that dry-run, retry, scheduler, and adapter paths cannot perform real upload/post actions without explicit user authorization.

## Current Scope

This is a design-only safety gate for future migration of publish queue behavior into Platform Core. It defines required interfaces, stop conditions, and future test expectations. It does not implement publish/upload behavior and does not change current runtime behavior.

## Stop Conditions

- No real upload/post implementation in this design task.
- No provider calls.
- No database migration.
- No scheduler behavior change.

If any future task requires crossing one of these boundaries, it must stop and request explicit user approval before implementation.

## Capability Keys

Future publish migration should model every external write as an explicit platform capability key, for example:

- `publish.dry_run`
- `publish.upload_media`
- `publish.post_note`
- `publish.retry`
- `publish.rollback_or_disable`

Default behavior must fail closed: unknown, planned, blocked, or disabled capabilities return a blocked result and must not instantiate a real adapter.

## Required Architecture Before Implementation

- **Platform publish adapter interface:** define a narrow interface for platform-specific publish operations, separated from dry-run planning. Real upload/post methods must be impossible to reach from the dry-run planner.
- **Dry-run result contract:** return validation, missing inputs, estimated external actions, diagnostics, and a final `would_call_provider=false` guarantee. Dry-run must not depend on provider clients.
- **Real-run confirmation token or authorization reference:** real upload/post requires a user-scoped confirmation token or durable authorization reference bound to platform, capability, account, draft, and expiry.
- **Trap adapter tests that fail if dry-run calls upload/post:** use a trap/fake adapter whose upload/post methods raise immediately. Dry-run tests must pass with the trap armed.
- **Disable/rollback switch per platform/capability:** provide a fail-closed switch that can disable real publish per platform and per capability without changing scheduler code or database schema.

## Audit And Diagnostics

Before any confirmed real adapter call in a future implementation, record an audit event containing platform, capability, account reference, draft/publish queue reference, authorization reference, operator, and correlation ID. Diagnostics returned to users must explain the blocked or allowed state without exposing cookies, tokens, raw provider payloads, or secrets.

## Migration Sequence

1. Add pure contracts and tests first: capability policy, dry-run result, blocked result, confirmation reference validation, trap adapter.
2. Wire dry-run through Platform Core without real adapter construction.
3. Add audit-before-call enforcement for the real-run path, still using fake/trap adapters.
4. Only after explicit user approval, connect one platform/capability to a real adapter behind the disable switch.
5. Keep retry behavior blocked unless the retry request carries a fresh or still-valid authorization reference for the same external action.

## Minimum Future Tests

- Dry-run does not instantiate real adapter.
- Unconfirmed real publish returns blocked result.
- Confirmed real publish records audit event before adapter call.
- Planned/blocked platforms fail closed.
- Retry without a valid authorization reference fails closed.
- Disable switch blocks real publish even when confirmation is present.

## Explicit Non-Goals

- No real upload/post implementation.
- No provider/API integration.
- No scheduler expansion or background execution behavior change.
- No database or Alembic migration.
- No changes to SDK/signature layers.

## User Impact

Operators can preview publish readiness safely and see why an item is blocked before risking an account action. Real external writes remain under explicit user control, with a clear authorization/audit boundary before any upload or post can happen.

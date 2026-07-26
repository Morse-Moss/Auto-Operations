# Reusable Resume Invite Design

## Goal

Let an administrator create one invitation code that can be placed on a resume and used up to 100 times, without creating a new code for every registrant.

## Existing Capability

The current invite model already stores `max_uses`, `used_count`, and `status`. Registration atomically consumes one use and rejects exhausted or inactive codes. No schema migration is required.

## Product Design

- Keep the existing custom invite creation flow.
- Add a one-click `Generate resume invite` action that creates a server-generated code with `max_uses = 100`.
- Show used, remaining, and maximum uses in the invite table.
- Add an icon action to copy the code.
- Add explicit disable and reactivate actions with confirmation. A disabled code cannot register users, while its usage history remains visible.
- Keep the public code bounded at 100 uses. Do not add unlimited invites.

## API Design

- Allow `POST /admin/invite-codes` to omit `code`; the server generates a unique, non-guessable code.
- Add `POST /admin/invite-codes/{invite_id}/disable`.
- Add `POST /admin/invite-codes/{invite_id}/activate`.
- Preserve the existing admin authorization boundary and invite serialization contract.

## Safety And Scope

- The code is intended to be public, so the UI must make remaining capacity and revocation visible.
- Do not expose existing invite codes outside the authenticated administrator surface.
- Do not change public registration policy, tenant assignment, account permissions, or consumption semantics.
- Do not add expiration, referral rewards, bulk generation, or invite ownership management in this slice.

## Acceptance

- A generated resume invite has a unique code and 100 available uses.
- The code can be copied from the administrator table.
- Disabling it blocks registration; reactivating it restores remaining uses.
- Existing manually named invite creation continues to work.
- Backend invite tests, frontend tests, frontend build, and a rendered administrator-page check pass.

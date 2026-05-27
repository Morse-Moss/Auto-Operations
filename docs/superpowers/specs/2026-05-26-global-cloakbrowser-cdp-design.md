# Global CloakBrowser CDP Service Design

## Background

The current XHS operations collector connects to an existing logged-in Edge/Chrome instance through Playwright CDP. That works for local collection, but future information-gathering systems may need a shared browser backend with persistent profiles and consistent startup behavior.

CloakBrowser is useful here as a browser backend, but it should not be imported directly by every business project. Each project should keep using CDP so browser implementation can change without rewriting collection logic.

## Goal

Create a local global CloakBrowser CDP service that multiple information-gathering systems can use through stable localhost CDP URLs.

The first project to use it is this XHS collector. The initial success path is:

1. Start a local CloakBrowser profile for XHS.
2. Log in manually in headed mode once.
3. Reuse that persistent profile across service restarts.
4. Run the existing `xhs-search` collector against the profile CDP URL.

## Scope

### In scope

- A local Node launcher for CloakBrowser persistent profiles.
- Profile-to-port mapping for common browser profiles.
- CDP compatibility with existing Playwright `chromium.connectOverCDP` callers.
- Manual login through headed browser windows.
- Smoke verification with the existing XHS search flow.

### Out of scope

- Browser Gateway HTTP API beyond CDP.
- Remote browser hosting.
- Docker service mode.
- Multi-user profile management.
- Automatic account login or credential storage.
- Rewriting XHS or Huitun scraping logic.

## Architecture

Use a separate global tool directory instead of coupling the browser service to this repository:

```text
E:/MorseTools/browser-service/
  package.json
  src/launch-cloak-profile.ts
  profiles/
    xhs-main/
    huitun-main/
    general-web/
```

The launcher starts CloakBrowser with:

- `launchPersistentContext()` from the `cloakbrowser` package.
- `userDataDir` pointing to the selected profile directory.
- `headless: false` by default for login/debuggability.
- a caller-provided `--remote-debugging-port=<port>` Chromium arg.
- `humanize: true` for normal user-facing interactions.

Business projects connect using their existing CDP code:

```ts
await chromium.connectOverCDP('http://127.0.0.1:17330');
```

## Profile and port registry

Use the high port range `17330-17339` to reduce conflicts with common local CDP, app, and test ports.

| Profile | Port | Purpose |
|---|---:|---|
| `xhs-main` | `17330` | Xiaohongshu login and search collection |
| `huitun-main` | `17331` | Huitun login and collection |
| `general-web` | `17332` | General web research |
| reserved | `17333-17339` | Future profiles |

Profile storage:

```text
E:/MorseTools/browser-service/profiles/<profile-name>/
```

Each platform/account should use its own profile. Profiles should not be shared across unrelated platforms because cookies, localStorage, cache, and browsing history are part of the browser identity.

## CLI design

Initial launcher command:

```bash
node E:/MorseTools/browser-service/dist/launch-cloak-profile.js \
  --profile xhs-main \
  --port 17330 \
  --headless false
```

Recommended options:

- `--profile <name>`: required unless `--profile-dir` is passed.
- `--profile-dir <path>`: explicit profile directory override.
- `--port <number>`: required; validates that the port is not already listening before launch.
- `--headless <true|false>`: default `false`.
- `--no-humanize`: optional escape hatch for debugging.
- `--extra-arg <arg>`: repeatable Chromium arg passthrough if needed later.

The launcher should print the final CDP URL after startup:

```text
CloakBrowser profile xhs-main is running.
CDP URL: http://127.0.0.1:17330
Profile: E:/MorseTools/browser-service/profiles/xhs-main
```

## Current project integration

No first-step business logic rewrite is required. This repository already accepts `--cdp-url` for XHS search and Huitun collection.

Example XHS smoke command:

```bash
npm run collect -- xhs-search --keyword 护肤 --cdp-url http://127.0.0.1:17330
```

Example Huitun command after `huitun-main` is logged in:

```bash
npm run collect -- --keyword 护肤 --cdp-url http://127.0.0.1:17331
```

Later, the project may add profile aliases such as:

```bash
npm run collect -- xhs-search --keyword 护肤 --browser-profile xhs-main
```

That alias should resolve to `http://127.0.0.1:17330`, but it is not necessary for the first implementation.

## Error handling

The launcher should fail early when:

- The requested profile name is unknown and no profile directory override is provided.
- The requested port is already in use.
- CloakBrowser binary download or startup fails.
- CDP endpoint is not reachable after launch.

When startup succeeds but a business project reports login required, the user should open the headed browser window, log in manually, then rerun the collector. The launcher must not store credentials outside the browser profile.

## Dependency and version policy

The global service owns the `cloakbrowser` dependency. Business projects do not need to install `cloakbrowser` for the CDP-only path.

For this repository, no dependency change is required for the first smoke path because it already uses Playwright CDP. If future code imports CloakBrowser directly, then `playwright-core` must be compatible with CloakBrowser's peer dependency.

To keep browser behavior stable, the global service should start with:

```bash
CLOAKBROWSER_AUTO_UPDATE=false
```

Updates should be explicit and verified with smoke tests.

## Verification

First implementation is complete when:

1. `xhs-main` starts on `http://127.0.0.1:17330`.
2. The headed browser can log in to Xiaohongshu manually.
3. Restarting the launcher preserves the login state.
4. `npm run collect -- xhs-search --keyword 护肤 --cdp-url http://127.0.0.1:17330` connects successfully.
5. Existing Edge/Chrome CDP usage still works by passing the old `--cdp-url`.

## Rollout plan

1. Build the global browser service outside this repository under `E:/MorseTools/browser-service`.
2. Start and verify `xhs-main` on port `17330`.
3. Use the existing XHS collector with `--cdp-url http://127.0.0.1:17330`.
4. Add project-level profile aliases only after the raw CDP path proves stable.

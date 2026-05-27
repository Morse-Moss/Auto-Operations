# Global CloakBrowser CDP Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local global CloakBrowser CDP service under `E:/MorseTools/browser-service` so this and future information-gathering systems can reuse stable localhost browser profiles.

**Architecture:** Create a separate TypeScript Node tool outside this repository. It launches CloakBrowser persistent contexts with profile-specific `userDataDir` folders and `--remote-debugging-port` so business projects keep using Playwright CDP via `chromium.connectOverCDP()`. The first rollout uses raw CDP URLs only; this repository's collection logic remains unchanged.

**Tech Stack:** Node.js 20+, TypeScript, Vitest, `cloakbrowser`, `playwright-core`, local filesystem profiles, localhost CDP on ports `17330-17339`.

**Commit policy:** Do not create git commits while executing this plan unless the user explicitly asks. Use status/checkpoint commands only.

---

## File Structure

Create a new global tool project outside this repository:

```text
E:/MorseTools/browser-service/
  CLAUDE.md
  .gitignore
  package.json
  tsconfig.json
  src/
    cli-options.ts
    launch-cloak-profile.ts
    launcher.ts
    ports.ts
    profiles.ts
  tests/
    cli-options.test.ts
    launcher.test.ts
    ports.test.ts
    profiles.test.ts
  profiles/
    .gitkeep
```

Responsibilities:

- `CLAUDE.md` — project-local rules for the global browser service.
- `src/profiles.ts` — known profile registry and profile directory resolution.
- `src/ports.ts` — port availability and CDP readiness checks.
- `src/cli-options.ts` — command-line parsing for the launcher.
- `src/launcher.ts` — dependency-injected launch logic around CloakBrowser.
- `src/launch-cloak-profile.ts` — executable CLI entrypoint.
- `tests/*.test.ts` — unit tests for registry, parser, port checks, and launch behavior.

This plan intentionally does not modify this repository's source code in the first implementation. Existing commands will connect to the global service via `--cdp-url`.

---

### Task 1: Create the global browser-service project skeleton

**Files:**
- Create: `E:/MorseTools/browser-service/CLAUDE.md`
- Create: `E:/MorseTools/browser-service/.gitignore`
- Create: `E:/MorseTools/browser-service/package.json`
- Create: `E:/MorseTools/browser-service/tsconfig.json`
- Create: `E:/MorseTools/browser-service/profiles/.gitkeep`

- [ ] **Step 1: Verify the global tools parent directory**

Run:

```bash
ls "E:/MorseTools"
```

Expected: PASS and shows the global tools directory. If it fails, run:

```bash
mkdir -p "E:/MorseTools"
```

Expected: PASS and creates the global tools root.

- [ ] **Step 2: Create the project directories**

Run:

```bash
mkdir -p "E:/MorseTools/browser-service/src" "E:/MorseTools/browser-service/tests" "E:/MorseTools/browser-service/profiles"
```

Expected: PASS.

- [ ] **Step 3: Create project rules**

Create `E:/MorseTools/browser-service/CLAUDE.md`:

```markdown
# Global Browser Service Rules

## Goal

Provide a local reusable browser backend for information-gathering systems through stable localhost CDP URLs.

## Boundaries

- This project owns browser startup, profile directories, and CDP readiness checks.
- Business projects should connect through CDP and should not import CloakBrowser directly unless a future plan explicitly changes that.
- Profiles are local state and must not be committed.
- Do not store account passwords, cookies, tokens, or exported browser state in source code or documentation.
- Do not expose CDP ports outside `127.0.0.1`.

## Technical conventions

- Use Node.js + TypeScript.
- Use Vitest for unit tests.
- Keep modules small and focused.
- Default ports are `17330-17339`.
- Default profile root is `E:/MorseTools/browser-service/profiles`.
- Start CloakBrowser with `CLOAKBROWSER_AUTO_UPDATE=false` unless an explicit update verification round is being performed.

## Development rules

- Write tests before implementation for parser, registry, and launch orchestration logic.
- Do not automatically commit changes unless the user explicitly asks.
- Run `npm test` and `npm run typecheck` before claiming completion.
```

- [ ] **Step 4: Create `.gitignore`**

Create `E:/MorseTools/browser-service/.gitignore`:

```gitignore
node_modules/
dist/
coverage/
profiles/*
!profiles/.gitkeep
.env
*.log
```

- [ ] **Step 5: Create `package.json`**

Create `E:/MorseTools/browser-service/package.json`:

```json
{
  "name": "morse-browser-service",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "bin": {
    "launch-cloak-profile": "./dist/launch-cloak-profile.js"
  },
  "scripts": {
    "build": "tsc",
    "dev": "tsx src/launch-cloak-profile.ts",
    "start": "node dist/launch-cloak-profile.js",
    "test": "vitest run --passWithNoTests",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "cloakbrowser": "^0.3.30",
    "playwright-core": "^1.60.0"
  },
  "devDependencies": {
    "@types/node": "^22.15.21",
    "tsx": "^4.19.4",
    "typescript": "^5.8.3",
    "vitest": "^3.1.4"
  }
}
```

- [ ] **Step 6: Create `tsconfig.json`**

Create `E:/MorseTools/browser-service/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "strict": true,
    "esModuleInterop": true,
    "forceConsistentCasingInFileNames": true,
    "skipLibCheck": true,
    "outDir": "dist",
    "rootDir": ".",
    "types": ["node", "vitest"]
  },
  "include": ["src/**/*.ts", "tests/**/*.ts"]
}
```

- [ ] **Step 7: Keep the profiles directory without committing profile data**

Create `E:/MorseTools/browser-service/profiles/.gitkeep` as an empty file.

- [ ] **Step 8: Install dependencies**

Run:

```bash
npm install --prefix "E:/MorseTools/browser-service"
```

Expected: PASS and creates `package-lock.json` and `node_modules/`.

- [ ] **Step 9: Run the empty test suite**

Run:

```bash
npm --prefix "E:/MorseTools/browser-service" test
```

Expected: PASS. The script uses `vitest run --passWithNoTests`, so an empty test suite must exit successfully.

- [ ] **Step 10: Checkpoint without committing**

Run:

```bash
git -C "E:/MorseTools/browser-service" status --short
```

Expected: If the directory is a git repository, new project files are listed. If it is not a git repository, Git reports that it is not a repository; do not initialize git unless the user asks.

---

### Task 2: Add the profile registry

**Files:**
- Create: `E:/MorseTools/browser-service/src/profiles.ts`
- Create: `E:/MorseTools/browser-service/tests/profiles.test.ts`

- [ ] **Step 1: Write failing profile registry tests**

Create `E:/MorseTools/browser-service/tests/profiles.test.ts`:

```ts
import { describe, expect, it } from 'vitest';

import {
  DEFAULT_PROFILE_ROOT,
  KNOWN_PROFILES,
  getProfilePort,
  resolveProfileDirectory,
  resolveProfileName,
} from '../src/profiles.js';

describe('profile registry', () => {
  it('defines the default profile root', () => {
    expect(DEFAULT_PROFILE_ROOT).toBe('E:/MorseTools/browser-service/profiles');
  });

  it('maps known profiles to the reserved high port range', () => {
    expect(KNOWN_PROFILES).toEqual({
      'xhs-main': { port: 17330, purpose: 'Xiaohongshu login and search collection' },
      'huitun-main': { port: 17331, purpose: 'Huitun login and collection' },
      'general-web': { port: 17332, purpose: 'General web research' },
    });
  });

  it('returns the default port for a known profile', () => {
    expect(getProfilePort('xhs-main')).toBe(17330);
    expect(getProfilePort('huitun-main')).toBe(17331);
  });

  it('rejects unknown profile names', () => {
    expect(() => getProfilePort('unknown')).toThrow('Unknown browser profile: unknown');
  });

  it('resolves known profile directories under the profile root', () => {
    expect(resolveProfileDirectory({ profile: 'xhs-main' })).toBe('E:/MorseTools/browser-service/profiles/xhs-main');
  });

  it('prefers explicit profile directory overrides', () => {
    expect(resolveProfileDirectory({ profileDir: 'D:/Profiles/custom' })).toBe('D:/Profiles/custom');
  });

  it('requires profile or profileDir', () => {
    expect(() => resolveProfileDirectory({})).toThrow('Provide --profile or --profile-dir.');
  });

  it('resolves a display profile name from profile or directory', () => {
    expect(resolveProfileName({ profile: 'xhs-main' })).toBe('xhs-main');
    expect(resolveProfileName({ profileDir: 'D:/Profiles/custom' })).toBe('custom');
  });
});
```

- [ ] **Step 2: Run the test and verify failure**

Run:

```bash
npm --prefix "E:/MorseTools/browser-service" test -- tests/profiles.test.ts
```

Expected: FAIL because `src/profiles.ts` does not exist.

- [ ] **Step 3: Implement the profile registry**

Create `E:/MorseTools/browser-service/src/profiles.ts`:

```ts
import path from 'node:path';

export const DEFAULT_PROFILE_ROOT = 'E:/MorseTools/browser-service/profiles';

export interface BrowserProfileDefinition {
  port: number;
  purpose: string;
}

export const KNOWN_PROFILES = {
  'xhs-main': { port: 17330, purpose: 'Xiaohongshu login and search collection' },
  'huitun-main': { port: 17331, purpose: 'Huitun login and collection' },
  'general-web': { port: 17332, purpose: 'General web research' },
} as const satisfies Record<string, BrowserProfileDefinition>;

export type KnownProfileName = keyof typeof KNOWN_PROFILES;

export interface ProfileDirectoryInput {
  profile?: string;
  profileDir?: string;
}

function normalizeSlashes(value: string): string {
  return value.replace(/\\/g, '/');
}

export function getProfilePort(profile: string): number {
  const definition = KNOWN_PROFILES[profile as KnownProfileName];
  if (!definition) {
    throw new Error(`Unknown browser profile: ${profile}`);
  }

  return definition.port;
}

export function resolveProfileDirectory(input: ProfileDirectoryInput): string {
  if (input.profileDir) {
    return normalizeSlashes(input.profileDir);
  }

  if (!input.profile) {
    throw new Error('Provide --profile or --profile-dir.');
  }

  getProfilePort(input.profile);
  return normalizeSlashes(path.join(DEFAULT_PROFILE_ROOT, input.profile));
}

export function resolveProfileName(input: ProfileDirectoryInput): string {
  if (input.profile) {
    return input.profile;
  }

  if (input.profileDir) {
    return path.basename(normalizeSlashes(input.profileDir));
  }

  throw new Error('Provide --profile or --profile-dir.');
}
```

- [ ] **Step 4: Run profile tests**

Run:

```bash
npm --prefix "E:/MorseTools/browser-service" test -- tests/profiles.test.ts
```

Expected: PASS.

- [ ] **Step 5: Run typecheck**

Run:

```bash
npm --prefix "E:/MorseTools/browser-service" run typecheck
```

Expected: PASS.

- [ ] **Step 6: Checkpoint without committing**

Run:

```bash
git -C "E:/MorseTools/browser-service" status --short
```

Expected: profile registry and test files are visible if this directory is a git repository.

---

### Task 3: Add CLI option parsing

**Files:**
- Create: `E:/MorseTools/browser-service/src/cli-options.ts`
- Create: `E:/MorseTools/browser-service/tests/cli-options.test.ts`

- [ ] **Step 1: Write failing CLI parser tests**

Create `E:/MorseTools/browser-service/tests/cli-options.test.ts`:

```ts
import { describe, expect, it } from 'vitest';

import { parseLaunchOptions } from '../src/cli-options.js';

describe('parseLaunchOptions', () => {
  it('parses a known profile and uses its default port', () => {
    expect(parseLaunchOptions(['node', 'launch-cloak-profile', '--profile', 'xhs-main'])).toEqual({
      profile: 'xhs-main',
      profileDir: undefined,
      profileName: 'xhs-main',
      port: 17330,
      headless: false,
      humanize: true,
      extraArgs: [],
    });
  });

  it('parses explicit port, headless, no-humanize, and repeated extra args', () => {
    expect(
      parseLaunchOptions([
        'node',
        'launch-cloak-profile',
        '--profile',
        'general-web',
        '--port',
        '17339',
        '--headless',
        'true',
        '--no-humanize',
        '--extra-arg',
        '--disable-http2',
        '--extra-arg',
        '--fingerprint=12345',
      ]),
    ).toEqual({
      profile: 'general-web',
      profileDir: undefined,
      profileName: 'general-web',
      port: 17339,
      headless: true,
      humanize: false,
      extraArgs: ['--disable-http2', '--fingerprint=12345'],
    });
  });

  it('parses explicit profile directory when no profile alias is used', () => {
    expect(
      parseLaunchOptions([
        'node',
        'launch-cloak-profile',
        '--profile-dir',
        'D:/Profiles/custom-xhs',
        '--port',
        '17338',
      ]),
    ).toEqual({
      profile: undefined,
      profileDir: 'D:/Profiles/custom-xhs',
      profileName: 'custom-xhs',
      port: 17338,
      headless: false,
      humanize: true,
      extraArgs: [],
    });
  });

  it('rejects missing profile source', () => {
    expect(() => parseLaunchOptions(['node', 'launch-cloak-profile', '--port', '17330'])).toThrow('Provide --profile or --profile-dir.');
  });

  it('rejects explicit profile directories without explicit port', () => {
    expect(() => parseLaunchOptions(['node', 'launch-cloak-profile', '--profile-dir', 'D:/Profiles/custom-xhs'])).toThrow(
      '--port is required when --profile-dir is used without a known --profile.',
    );
  });

  it('rejects invalid ports', () => {
    expect(() => parseLaunchOptions(['node', 'launch-cloak-profile', '--profile', 'xhs-main', '--port', 'abc'])).toThrow(
      '--port must be an integer between 1024 and 65535, received: abc',
    );
    expect(() => parseLaunchOptions(['node', 'launch-cloak-profile', '--profile', 'xhs-main', '--port', '80'])).toThrow(
      '--port must be an integer between 1024 and 65535, received: 80',
    );
  });

  it('rejects invalid boolean values', () => {
    expect(() => parseLaunchOptions(['node', 'launch-cloak-profile', '--profile', 'xhs-main', '--headless', 'maybe'])).toThrow(
      '--headless must be true or false, received: maybe',
    );
  });
});
```

- [ ] **Step 2: Run the test and verify failure**

Run:

```bash
npm --prefix "E:/MorseTools/browser-service" test -- tests/cli-options.test.ts
```

Expected: FAIL because `src/cli-options.ts` does not exist.

- [ ] **Step 3: Implement CLI option parsing**

Create `E:/MorseTools/browser-service/src/cli-options.ts`:

```ts
import { getProfilePort, resolveProfileName } from './profiles.js';

export interface LaunchCliOptions {
  profile?: string;
  profileDir?: string;
  profileName: string;
  port: number;
  headless: boolean;
  humanize: boolean;
  extraArgs: string[];
}

function readOptionValue(argv: string[], index: number, optionName: string): string {
  const value = argv[index + 1];
  if (!value || value.startsWith('--')) {
    throw new Error(`${optionName} requires a value.`);
  }
  return value;
}

function parsePort(value: string): number {
  const port = Number(value);
  if (!Number.isInteger(port) || port < 1024 || port > 65535) {
    throw new Error(`--port must be an integer between 1024 and 65535, received: ${value}`);
  }
  return port;
}

function parseBoolean(value: string, optionName: string): boolean {
  if (value === 'true') {
    return true;
  }
  if (value === 'false') {
    return false;
  }
  throw new Error(`${optionName} must be true or false, received: ${value}`);
}

export function parseLaunchOptions(argv = process.argv): LaunchCliOptions {
  let profile: string | undefined;
  let profileDir: string | undefined;
  let explicitPort: number | undefined;
  let headless = false;
  let humanize = true;
  const extraArgs: string[] = [];

  for (let index = 2; index < argv.length; index += 1) {
    const arg = argv[index];

    if (arg === '--profile') {
      profile = readOptionValue(argv, index, '--profile');
      index += 1;
      continue;
    }

    if (arg === '--profile-dir') {
      profileDir = readOptionValue(argv, index, '--profile-dir').replace(/\\/g, '/');
      index += 1;
      continue;
    }

    if (arg === '--port') {
      explicitPort = parsePort(readOptionValue(argv, index, '--port'));
      index += 1;
      continue;
    }

    if (arg === '--headless') {
      headless = parseBoolean(readOptionValue(argv, index, '--headless'), '--headless');
      index += 1;
      continue;
    }

    if (arg === '--no-humanize') {
      humanize = false;
      continue;
    }

    if (arg === '--extra-arg') {
      extraArgs.push(readOptionValue(argv, index, '--extra-arg'));
      index += 1;
      continue;
    }

    throw new Error(`Unknown option: ${arg}`);
  }

  if (!profile && !profileDir) {
    throw new Error('Provide --profile or --profile-dir.');
  }

  if (profile && profileDir) {
    throw new Error('Use either --profile or --profile-dir, not both.');
  }

  if (!profile && explicitPort === undefined) {
    throw new Error('--port is required when --profile-dir is used without a known --profile.');
  }

  const port = explicitPort ?? getProfilePort(profile as string);

  return {
    profile,
    profileDir,
    profileName: resolveProfileName({ profile, profileDir }),
    port,
    headless,
    humanize,
    extraArgs,
  };
}
```

- [ ] **Step 4: Run CLI parser tests**

Run:

```bash
npm --prefix "E:/MorseTools/browser-service" test -- tests/cli-options.test.ts
```

Expected: PASS.

- [ ] **Step 5: Run typecheck**

Run:

```bash
npm --prefix "E:/MorseTools/browser-service" run typecheck
```

Expected: PASS.

- [ ] **Step 6: Checkpoint without committing**

Run:

```bash
git -C "E:/MorseTools/browser-service" status --short
```

Expected: CLI parser files are visible if this directory is a git repository.

---

### Task 4: Add port and CDP readiness helpers

**Files:**
- Create: `E:/MorseTools/browser-service/src/ports.ts`
- Create: `E:/MorseTools/browser-service/tests/ports.test.ts`

- [ ] **Step 1: Write failing port helper tests**

Create `E:/MorseTools/browser-service/tests/ports.test.ts`:

```ts
import net from 'node:net';
import { afterEach, describe, expect, it } from 'vitest';

import { assertPortAvailable, buildCdpUrl, isPortAvailable } from '../src/ports.js';

let server: net.Server | undefined;

async function listenOnRandomPort(): Promise<number> {
  server = net.createServer();
  await new Promise<void>((resolve) => {
    server?.listen(0, '127.0.0.1', () => resolve());
  });
  const address = server.address();
  if (!address || typeof address === 'string') {
    throw new Error('Could not read test server address.');
  }
  return address.port;
}

afterEach(async () => {
  if (!server) {
    return;
  }
  await new Promise<void>((resolve) => server?.close(() => resolve()));
  server = undefined;
});

describe('port helpers', () => {
  it('builds localhost CDP URLs', () => {
    expect(buildCdpUrl(17330)).toBe('http://127.0.0.1:17330');
  });

  it('reports an occupied port as unavailable', async () => {
    const port = await listenOnRandomPort();
    await expect(isPortAvailable(port)).resolves.toBe(false);
    await expect(assertPortAvailable(port)).rejects.toThrow(`Port ${port} is already in use.`);
  });

  it('reports a free high port as available', async () => {
    const occupiedPort = await listenOnRandomPort();
    const candidatePort = occupiedPort + 20;
    await expect(isPortAvailable(candidatePort)).resolves.toBe(true);
  });
});
```

- [ ] **Step 2: Run the test and verify failure**

Run:

```bash
npm --prefix "E:/MorseTools/browser-service" test -- tests/ports.test.ts
```

Expected: FAIL because `src/ports.ts` does not exist.

- [ ] **Step 3: Implement port helpers**

Create `E:/MorseTools/browser-service/src/ports.ts`:

```ts
import net from 'node:net';

export function buildCdpUrl(port: number): string {
  return `http://127.0.0.1:${port}`;
}

export async function isPortAvailable(port: number): Promise<boolean> {
  const server = net.createServer();

  return new Promise<boolean>((resolve) => {
    server.once('error', () => resolve(false));
    server.once('listening', () => {
      server.close(() => resolve(true));
    });
    server.listen(port, '127.0.0.1');
  });
}

export async function assertPortAvailable(port: number): Promise<void> {
  if (!(await isPortAvailable(port))) {
    throw new Error(`Port ${port} is already in use.`);
  }
}

export async function waitForCdpEndpoint(port: number, timeoutMs = 15_000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  const url = `${buildCdpUrl(port)}/json/version`;

  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) {
        return;
      }
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
  }

  throw new Error(`CDP endpoint did not become ready at ${buildCdpUrl(port)} within ${timeoutMs}ms.`);
}
```

- [ ] **Step 4: Run port helper tests**

Run:

```bash
npm --prefix "E:/MorseTools/browser-service" test -- tests/ports.test.ts
```

Expected: PASS.

- [ ] **Step 5: Run typecheck**

Run:

```bash
npm --prefix "E:/MorseTools/browser-service" run typecheck
```

Expected: PASS.

- [ ] **Step 6: Checkpoint without committing**

Run:

```bash
git -C "E:/MorseTools/browser-service" status --short
```

Expected: port helper files are visible if this directory is a git repository.

---

### Task 5: Add dependency-injected CloakBrowser launch orchestration

**Files:**
- Create: `E:/MorseTools/browser-service/src/launcher.ts`
- Create: `E:/MorseTools/browser-service/tests/launcher.test.ts`

- [ ] **Step 1: Write failing launcher tests**

Create `E:/MorseTools/browser-service/tests/launcher.test.ts`:

```ts
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { buildCloakLaunchOptions, startCloakProfile } from '../src/launcher.js';

let tempDir: string | undefined;

afterEach(() => {
  if (tempDir) {
    rmSync(tempDir, { recursive: true, force: true });
    tempDir = undefined;
  }
});

describe('buildCloakLaunchOptions', () => {
  it('builds persistent context launch options for localhost CDP', () => {
    const options = buildCloakLaunchOptions({
      profileDir: 'E:/MorseTools/browser-service/profiles/xhs-main',
      port: 17330,
      headless: false,
      humanize: true,
      extraArgs: ['--disable-http2'],
    });

    expect(options).toEqual({
      userDataDir: 'E:/MorseTools/browser-service/profiles/xhs-main',
      headless: false,
      humanize: true,
      args: ['--remote-debugging-address=127.0.0.1', '--remote-debugging-port=17330', '--disable-http2'],
    });
  });
});

describe('startCloakProfile', () => {
  it('creates the profile directory, launches CloakBrowser, and returns service metadata', async () => {
    tempDir = mkdtempSync(path.join(tmpdir(), 'cloak-profile-test-')).replace(/\\/g, '/');
    const launchPersistentContext = vi.fn().mockResolvedValue({
      close: vi.fn().mockResolvedValue(undefined),
    });
    const waitForCdpEndpoint = vi.fn().mockResolvedValue(undefined);
    const assertPortAvailable = vi.fn().mockResolvedValue(undefined);

    const service = await startCloakProfile(
      {
        profileName: 'xhs-main',
        profileDir: `${tempDir}/xhs-main`,
        port: 17330,
        headless: false,
        humanize: true,
        extraArgs: [],
      },
      {
        launchPersistentContext,
        waitForCdpEndpoint,
        assertPortAvailable,
      },
    );

    expect(assertPortAvailable).toHaveBeenCalledWith(17330);
    expect(launchPersistentContext).toHaveBeenCalledWith({
      userDataDir: `${tempDir}/xhs-main`,
      headless: false,
      humanize: true,
      args: ['--remote-debugging-address=127.0.0.1', '--remote-debugging-port=17330'],
    });
    expect(waitForCdpEndpoint).toHaveBeenCalledWith(17330);
    expect(service).toMatchObject({
      profileName: 'xhs-main',
      profileDir: `${tempDir}/xhs-main`,
      port: 17330,
      cdpUrl: 'http://127.0.0.1:17330',
    });
  });
});
```

- [ ] **Step 2: Run the test and verify failure**

Run:

```bash
npm --prefix "E:/MorseTools/browser-service" test -- tests/launcher.test.ts
```

Expected: FAIL because `src/launcher.ts` does not exist.

- [ ] **Step 3: Implement launch orchestration**

Create `E:/MorseTools/browser-service/src/launcher.ts`:

```ts
import { mkdirSync } from 'node:fs';

import { assertPortAvailable, buildCdpUrl, waitForCdpEndpoint } from './ports.js';

export interface StartCloakProfileOptions {
  profileName: string;
  profileDir: string;
  port: number;
  headless: boolean;
  humanize: boolean;
  extraArgs: string[];
}

export interface CloakPersistentContext {
  close: () => Promise<void>;
}

export interface CloakLaunchOptions {
  userDataDir: string;
  headless: boolean;
  humanize: boolean;
  args: string[];
}

export interface StartedCloakProfile {
  profileName: string;
  profileDir: string;
  port: number;
  cdpUrl: string;
  close: () => Promise<void>;
}

export interface LauncherDependencies {
  launchPersistentContext: (options: CloakLaunchOptions) => Promise<CloakPersistentContext>;
  assertPortAvailable: (port: number) => Promise<void>;
  waitForCdpEndpoint: (port: number) => Promise<void>;
}

export function buildCloakLaunchOptions(options: {
  profileDir: string;
  port: number;
  headless: boolean;
  humanize: boolean;
  extraArgs: string[];
}): CloakLaunchOptions {
  return {
    userDataDir: options.profileDir,
    headless: options.headless,
    humanize: options.humanize,
    args: [`--remote-debugging-address=127.0.0.1`, `--remote-debugging-port=${options.port}`, ...options.extraArgs],
  };
}

export async function loadDefaultLauncherDependencies(): Promise<LauncherDependencies> {
  const cloakbrowser = await import('cloakbrowser');

  return {
    launchPersistentContext: cloakbrowser.launchPersistentContext as LauncherDependencies['launchPersistentContext'],
    assertPortAvailable,
    waitForCdpEndpoint,
  };
}

export async function startCloakProfile(
  options: StartCloakProfileOptions,
  dependencies: LauncherDependencies,
): Promise<StartedCloakProfile> {
  await dependencies.assertPortAvailable(options.port);
  mkdirSync(options.profileDir, { recursive: true });

  const context = await dependencies.launchPersistentContext(buildCloakLaunchOptions(options));
  await dependencies.waitForCdpEndpoint(options.port);

  return {
    profileName: options.profileName,
    profileDir: options.profileDir,
    port: options.port,
    cdpUrl: buildCdpUrl(options.port),
    close: async () => {
      await context.close();
    },
  };
}
```

- [ ] **Step 4: Run launcher tests**

Run:

```bash
npm --prefix "E:/MorseTools/browser-service" test -- tests/launcher.test.ts
```

Expected: PASS.

- [ ] **Step 5: Run typecheck**

Run:

```bash
npm --prefix "E:/MorseTools/browser-service" run typecheck
```

Expected: PASS.

- [ ] **Step 6: Checkpoint without committing**

Run:

```bash
git -C "E:/MorseTools/browser-service" status --short
```

Expected: launcher files are visible if this directory is a git repository.

---

### Task 6: Add the executable CLI entrypoint

**Files:**
- Create: `E:/MorseTools/browser-service/src/launch-cloak-profile.ts`
- Modify: `E:/MorseTools/browser-service/package.json`

- [ ] **Step 1: Create the CLI entrypoint**

Create `E:/MorseTools/browser-service/src/launch-cloak-profile.ts`:

```ts
#!/usr/bin/env node

import { parseLaunchOptions } from './cli-options.js';
import { loadDefaultLauncherDependencies, startCloakProfile } from './launcher.js';
import { resolveProfileDirectory } from './profiles.js';

function printUsage(): void {
  console.log(`Usage:
  launch-cloak-profile --profile <name> [--port <port>] [--headless true|false] [--no-humanize]
  launch-cloak-profile --profile-dir <path> --port <port> [--headless true|false] [--no-humanize]

Known profiles:
  xhs-main      port 17330
  huitun-main   port 17331
  general-web   port 17332

Examples:
  launch-cloak-profile --profile xhs-main
  launch-cloak-profile --profile xhs-main --port 17330 --headless false
  launch-cloak-profile --profile-dir D:/Profiles/custom-xhs --port 17338
`);
}

function installShutdownHandlers(close: () => Promise<void>): void {
  let closing = false;

  const shutdown = async () => {
    if (closing) {
      return;
    }
    closing = true;
    await close().catch((error) => {
      console.error(`Failed to close CloakBrowser profile: ${String(error)}`);
    });
    process.exit(0);
  };

  process.on('SIGINT', () => {
    void shutdown();
  });
  process.on('SIGTERM', () => {
    void shutdown();
  });
}

async function main(argv = process.argv): Promise<void> {
  if (argv.includes('--help') || argv.includes('-h')) {
    printUsage();
    return;
  }

  process.env.CLOAKBROWSER_AUTO_UPDATE = process.env.CLOAKBROWSER_AUTO_UPDATE ?? 'false';

  const options = parseLaunchOptions(argv);
  const profileDir = resolveProfileDirectory({ profile: options.profile, profileDir: options.profileDir });
  const dependencies = await loadDefaultLauncherDependencies();
  const service = await startCloakProfile(
    {
      profileName: options.profileName,
      profileDir,
      port: options.port,
      headless: options.headless,
      humanize: options.humanize,
      extraArgs: options.extraArgs,
    },
    dependencies,
  );

  console.log(`CloakBrowser profile ${service.profileName} is running.`);
  console.log(`CDP URL: ${service.cdpUrl}`);
  console.log(`Profile: ${service.profileDir}`);
  console.log('Press Ctrl+C to stop.');

  installShutdownHandlers(service.close);
  await new Promise(() => undefined);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
```

- [ ] **Step 2: Build the project**

Run:

```bash
npm --prefix "E:/MorseTools/browser-service" run build
```

Expected: PASS and creates `E:/MorseTools/browser-service/dist/`.

- [ ] **Step 3: Verify help output**

Run:

```bash
node "E:/MorseTools/browser-service/dist/launch-cloak-profile.js" --help
```

Expected: PASS and stdout includes:

```text
Known profiles:
  xhs-main      port 17330
  huitun-main   port 17331
  general-web   port 17332
```

- [ ] **Step 4: Run all unit tests**

Run:

```bash
npm --prefix "E:/MorseTools/browser-service" test
```

Expected: PASS.

- [ ] **Step 5: Run typecheck**

Run:

```bash
npm --prefix "E:/MorseTools/browser-service" run typecheck
```

Expected: PASS.

- [ ] **Step 6: Checkpoint without committing**

Run:

```bash
git -C "E:/MorseTools/browser-service" status --short
```

Expected: CLI entrypoint and generated `dist/` are visible if this directory is a git repository. `dist/` is ignored by `.gitignore`.

---

### Task 7: Verify the global service with the XHS profile

**Files:**
- No source changes expected unless smoke verification reveals a bug.

- [ ] **Step 1: Start `xhs-main` in headed mode**

Run:

```bash
node "E:/MorseTools/browser-service/dist/launch-cloak-profile.js" --profile xhs-main --port 17330 --headless false
```

Expected:

```text
CloakBrowser profile xhs-main is running.
CDP URL: http://127.0.0.1:17330
Profile: E:/MorseTools/browser-service/profiles/xhs-main
Press Ctrl+C to stop.
```

Keep this process running for the next steps.

- [ ] **Step 2: Verify the CDP endpoint directly**

In a second terminal, run:

```bash
node --input-type=module -e "const r=await fetch('http://127.0.0.1:17330/json/version'); console.log(r.status); console.log((await r.json()).webSocketDebuggerUrl ? 'cdp-ready' : 'missing-websocket-url')"
```

Expected:

```text
200
cdp-ready
```

- [ ] **Step 3: Manually log in to Xiaohongshu if needed**

Use the headed CloakBrowser window from Step 1. Open Xiaohongshu in that browser, complete login manually, and leave the browser service running.

Expected: Xiaohongshu is logged in inside the `xhs-main` CloakBrowser profile.

- [ ] **Step 4: Run this repository's existing XHS smoke path through the global CDP URL**

Run from `E:/小红书`:

```bash
npm run collect -- xhs-search --keyword 护肤 --sorts most_collected --limit-per-sort 3 --cdp-url http://127.0.0.1:17330
```

Expected: command connects to the global CloakBrowser CDP endpoint and prints JSON with one run. If login is missing, it should report the existing XHS login-required message instead of inserting empty rows.

- [ ] **Step 5: Verify profile persistence**

Stop the service with Ctrl+C. Start it again:

```bash
node "E:/MorseTools/browser-service/dist/launch-cloak-profile.js" --profile xhs-main --port 17330 --headless false
```

Then rerun:

```bash
npm run collect -- xhs-search --keyword 护肤 --sorts most_collected --limit-per-sort 1 --cdp-url http://127.0.0.1:17330
```

Expected: login state persists. The collector connects without requiring a fresh login.

- [ ] **Step 6: Verify the existing Edge/Chrome CDP path still works**

Run this repository's existing command with the old CDP URL if the regular browser is running on `9222`:

```bash
npm run collect -- xhs-search --keyword 护肤 --sorts most_collected --limit-per-sort 1 --cdp-url http://127.0.0.1:9222
```

Expected: existing CDP path behavior is unchanged. If the normal browser is not running on `9222`, record that this verification was skipped because the old CDP service was unavailable.

- [ ] **Step 7: Final automated verification for the global service**

Run:

```bash
npm --prefix "E:/MorseTools/browser-service" test && npm --prefix "E:/MorseTools/browser-service" run typecheck && npm --prefix "E:/MorseTools/browser-service" run build
```

Expected: PASS for tests, typecheck, and build.

- [ ] **Step 8: Final project checkpoint without committing**

Run:

```bash
git -C "E:/小红书" status --short && git -C "E:/MorseTools/browser-service" status --short
```

Expected: this repository shows only the spec/plan files from this design round unless other user changes exist. The global service shows project files if it is a git repository; if it is not a git repository, Git reports that status cannot be shown there.

---

## Self-Review

Spec coverage:

- Local Node launcher: Task 1 and Task 6.
- CloakBrowser persistent profiles: Task 5 and Task 7.
- Profile-to-port mapping with `17330-17339`: Task 2 and Task 3.
- CDP compatibility with existing `chromium.connectOverCDP`: Task 4, Task 5, and Task 7.
- No first-step business logic rewrite: Task 7 uses existing `--cdp-url` commands only.
- Manual login and persistent state: Task 7.
- Dependency owned by global service, not business projects: Task 1 package setup and Task 7 current-project verification.
- Stable update behavior: Task 1 `CLAUDE.md` and Task 6 `CLOAKBROWSER_AUTO_UPDATE=false` default.

Placeholder scan:

- The plan contains no `TBD`, no unfilled sections, and no steps that ask an engineer to invent missing implementation details.

Type consistency:

- `LaunchCliOptions` from Task 3 feeds `StartCloakProfileOptions` from Task 5.
- `profileName`, `profileDir`, `port`, `headless`, `humanize`, and `extraArgs` use the same names across parser, launcher, and CLI entrypoint.
- `buildCdpUrl()` returns the CDP URL string used in launcher metadata and smoke tests.

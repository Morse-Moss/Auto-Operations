# XHS_ALL_IN_ONE Baseline Migration Design

## Goal

Make `XHS_ALL_IN_ONE` the primary system baseline for this project.

After this migration, the repository root represents the `XHS_ALL_IN_ONE` product platform:

- Python/FastAPI backend.
- React/Vite frontend.
- SQLAlchemy/Alembic data model.
- Native XHS PC and Creator API capability.
- Web-first operations platform.

The previous TypeScript CLI system is no longer the product baseline. It becomes a legacy enhancement package that can be mined later for useful capabilities such as Huitun keyword sourcing, pipeline health checks, local analysis-source contracts, and Feishu sync patterns.

## Decision

Use the migration approach: **baseline replacement plus legacy enhancement package**.

This means:

1. Copy `XHS_ALL_IN_ONE` into the project root as the new main system.
2. Move the existing TypeScript CLI code into a legacy directory.
3. Update project rules so future work uses `XHS_ALL_IN_ONE` architecture by default.
4. Preserve prior documents and local data for reference.
5. Do not immediately merge old SQLite data or old pipeline code into the new system.

This is intentionally not a hard delete. The old system still contains useful verified work, but it should not constrain the new product baseline.

## Current Systems

### New baseline source

Local source repository:

```text
E:/tmp/XHS_ALL_IN_ONE
```

Important capabilities:

- `main.py` unified startup.
- `backend/app/main.py` FastAPI application.
- `backend/app/models/` SQLAlchemy models.
- `backend/app/api/` HTTP API routes.
- `backend/app/adapters/xhs/` adapter boundary over the XHS SDK.
- `apis/`, `xhs_utils/`, and `static/` native XHS SDK/signature layer.
- `frontend/` React/Vite/Ant Design web workspace.
- `config/default.yaml` and `config/production.yaml` layered configuration.
- `Dockerfile` and `docker-compose.yml` deployment baseline.

### Previous project baseline

Current project root:

```text
E:/小红书
```

Previous baseline capabilities:

- TypeScript CLI collector.
- Huitun hotword and note collection.
- XHS DOM-based search/detail collection.
- Local SQLite persistence.
- Media archive.
- Feishu sync.
- Pipeline check.
- `xhs-analysis-source/v1` JSONL handoff contract.
- `xhs-preanalysis-run` orchestration.

These become legacy enhancement candidates, not the main product architecture.

## Target Repository Layout

After migration:

```text
E:/小红书/
├── CLAUDE.md
├── main.py
├── requirements.txt
├── package.json
├── Dockerfile
├── docker-compose.yml
├── config/
├── apis/
├── xhs_utils/
├── static/
├── backend/
├── frontend/
├── tests/
├── data/
├── docs/
│   └── superpowers/
│       ├── specs/
│       └── plans/
└── legacy/
    └── xhs-ops-collector/
        ├── src/
        ├── tests/
        ├── package.json
        ├── vitest.config.ts
        └── docs/
```

The root directory should read as `XHS_ALL_IN_ONE`. Legacy TypeScript files should not remain scattered at root because that would keep two conflicting baselines alive.

## What Moves Where

### Move into `legacy/xhs-ops-collector/`

Move the previous TypeScript implementation and its direct project files:

```text
src/
tests/
package.json
package-lock.json
tsconfig.json
vitest.config.ts
node_modules/            optional; may be removed instead of moved
```

If `node_modules/` is large or stale, do not keep it. The legacy package can reinstall dependencies when needed.

### Keep at root

Keep these root-level project assets:

```text
CLAUDE.md
docs/
data/
```

Then update `CLAUDE.md` to describe the new baseline.

### Copy from `XHS_ALL_IN_ONE` to root

Copy these into root:

```text
main.py
requirements.txt
package.json
Dockerfile
docker-compose.yml
.dockerignore
.gitignore additions when useful
config/
apis/
xhs_utils/
static/
backend/
frontend/
tests/
author/                 optional project asset
README.md               optional; may become upstream README/reference
LICENSE                 if present
```

Do not overwrite local data without inspecting conflicts first.

## Documentation Strategy

Keep prior specs and plans in:

```text
docs/superpowers/specs/
docs/superpowers/plans/
```

These documents remain useful historical context, but after this migration they describe legacy and enhancement capabilities unless explicitly updated.

Add a migration note in the new `CLAUDE.md`:

- `XHS_ALL_IN_ONE` is authoritative for product architecture.
- Previous TypeScript collector is a legacy enhancement package.
- New features should be designed against FastAPI/React/SQLAlchemy unless the task explicitly targets legacy enhancement import.

## Data Strategy

Do not merge databases in the first migration.

`XHS_ALL_IN_ONE` default database:

```text
data/spider_xhs.db
```

Previous project database:

```text
data/xhs-ops.sqlite
```

The first migration keeps both separate:

```text
data/
├── spider_xhs.db        # new main system database, created by XHS_ALL_IN_ONE
├── xhs-ops.sqlite       # legacy historical data, preserved
└── legacy-backup/       # optional backup artifacts
```

Rationale:

- The schemas are different.
- The data provenance is different.
- Forced merging would create mapping ambiguity.
- The first milestone is identity and runtime migration, not data import.

If legacy data becomes useful, create a later importer design that maps old data into the new `notes`, `note_assets`, `note_comments`, or a dedicated legacy-source table.

## First Migration Scope

### In scope

1. Establish `XHS_ALL_IN_ONE` as repository root baseline.
2. Move previous TypeScript system into `legacy/xhs-ops-collector/`.
3. Update `CLAUDE.md` with new project rules.
4. Preserve prior `docs/` and `data/`.
5. Verify the new baseline can install, build, test, and start.
6. Confirm `/api/health` works.

### Out of scope

Do not implement these during the first migration:

- Huitun integration into the new backend.
- Legacy SQLite import.
- Feishu sync integration.
- Pipeline check integration.
- `xhs-analysis-source/v1` export integration.
- Automatic publish strategy changes.
- New frontend redesign.
- XHS SDK refactor.
- Production deployment.

## Future Enhancement Candidates

After baseline migration, evaluate these as separate specs:

1. **Huitun keyword source integration**
   - Use Huitun hot words as an input source for XHS native search tasks.
   - Should be exposed as a new backend service/API and frontend workflow, not as a root CLI dependency.

2. **Analysis-source export**
   - Export selected content-library notes as a stable JSONL package for Agent analysis.
   - The contract can borrow from `xhs-analysis-source/v1`.

3. **Pipeline health check**
   - Add a task/run health report over XHS_ALL_IN_ONE collections, media, and publish jobs.
   - Should use new system tables, not old table names.

4. **Feishu sync**
   - Add content-library export to Feishu for human review.
   - Feishu should remain a collaboration layer, not the primary data source.

## Security and Operational Boundaries

The new baseline uses native XHS capabilities and therefore has higher operational risk than the previous Huitun-only phase.

Project rules must explicitly state:

- Do not store plaintext cookies, passwords, tokens, or API keys in code or docs.
- Production must override `SECRET_KEY`; the development default is not safe.
- Fernet encryption depends on stable secret configuration.
- XHS PC and Creator actions should be low-frequency and serial by default.
- XHS native API/signature failures should be diagnosed, not retried aggressively.
- Creator publishing and automatic operations are high-risk account actions.
- Before enabling automatic publish in a real account context, require a separate risk and QA design.

## User Impact

Before migration, the user operates a CLI-first collection pipeline.

After migration, the user operates a Web-first XHS operations platform:

- Account matrix.
- Native XHS note discovery.
- Content library.
- Draft and publishing modules available from the upstream baseline.
- Legacy Huitun/pipeline capabilities available only as future enhancements.

The product becomes easier to operate visually, but the operational risk increases because native XHS account and Creator capabilities are now part of the main baseline.

## Verification

Minimum verification after implementation:

```bash
pip install -r requirements.txt
npm install
cd frontend && npm install && npm run build
cd ..
pytest
python main.py
```

Then check:

```text
http://localhost:8000/api/health
```

Expected health response:

```json
{"status":"ok","service":"spider-xhs"}
```

Optional development startup:

```bash
python main.py --with-frontend
```

Then check:

```text
http://localhost:5173
```

Migration is successful when:

- Root files represent `XHS_ALL_IN_ONE`.
- Previous TypeScript system is preserved under `legacy/xhs-ops-collector/` or intentionally excluded with backup.
- `CLAUDE.md` describes the new baseline.
- `docs/` and `data/` are preserved.
- Backend health endpoint works.
- Frontend builds.
- Backend tests pass or failures are reported with exact output.

## Non-goals

This migration does not claim that the new upstream system is production-safe. It only changes the project baseline. Production hardening, account-risk controls, deployment setup, and legacy capability integration require separate plans.

# Legacy XHS Ops Collector

This directory preserves the previous TypeScript CLI system after the project baseline migrated to `XHS_ALL_IN_ONE`.

## Status

This package is not the main product system. It is a legacy enhancement package.

The repository root now uses the `XHS_ALL_IN_ONE` baseline:

- Python/FastAPI backend
- React/Vite frontend
- SQLAlchemy/Alembic database model
- Native XHS PC and Creator capabilities

## Preserved Capabilities

The legacy package may still be mined for future enhancement work:

- Huitun hotword collection
- DOM-based XHS collection experiments
- Local media archive patterns
- Feishu sync patterns
- Pipeline check logic
- `xhs-analysis-source/v1` JSONL contract
- `xhs-preanalysis-run` orchestration lessons

## Rules

- Do not add new root-level TypeScript collector features here unless the task explicitly targets legacy enhancement extraction.
- New product features should be implemented against the root `XHS_ALL_IN_ONE` FastAPI/React architecture.
- If a legacy capability is useful, design a new integration against the main backend and data model instead of making the root depend on this package.

## Running Legacy Tests

From this directory:

```bash
npm install
npm test
npm run typecheck
```

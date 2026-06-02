# XHS_ALL_IN_ONE Baseline Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the project root baseline with `XHS_ALL_IN_ONE`, while preserving the previous TypeScript CLI system as a legacy enhancement package.

**Architecture:** This is a repository baseline migration, not a feature integration. The new root becomes the upstream `XHS_ALL_IN_ONE` FastAPI/React product platform; the previous TypeScript collector is moved under `legacy/xhs-ops-collector/` and is no longer allowed to define root architecture. Existing `docs/` and `data/` are preserved, and `CLAUDE.md` is rewritten to make the new baseline authoritative.

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy, Alembic, React 19, Vite, Ant Design, Node.js 20+, PyExecJS-backed signature JS, local SQLite/MySQL-compatible configuration.

---

## Commit Policy Note

This plan intentionally omits mandatory commit steps. The active project rules say to commit only when the user explicitly asks. If the user later asks to commit, use a concise English commit message and include the required Claude co-author trailer.

## Source of Truth

Approved design spec:

```text
docs/superpowers/specs/2026-06-02-xhs-all-in-one-baseline-migration-design.md
```

New baseline source tree:

```text
E:/tmp/XHS_ALL_IN_ONE
```

Target project root:

```text
E:/小红书
```

## File Structure

### Files/directories moved into legacy package

- Move: `src/` → `legacy/xhs-ops-collector/src/`
- Move: `tests/` → `legacy/xhs-ops-collector/tests/`
- Move: `package.json` → `legacy/xhs-ops-collector/package.json`
- Move: `package-lock.json` → `legacy/xhs-ops-collector/package-lock.json`
- Move: `tsconfig.json` → `legacy/xhs-ops-collector/tsconfig.json`
- Move: `vitest.config.ts` → `legacy/xhs-ops-collector/vitest.config.ts`
- Remove generated root dependency directory: `node_modules/`
- Create: `legacy/xhs-ops-collector/docs/README.md`

### Files/directories copied from `E:/tmp/XHS_ALL_IN_ONE` into root

- Copy: `main.py`
- Copy: `requirements.txt`
- Copy: `package.json`
- Copy: `Dockerfile`
- Copy: `docker-compose.yml`
- Copy: `.dockerignore`
- Copy: `README.md`
- Copy: `config/`
- Copy: `apis/`
- Copy: `xhs_utils/`
- Copy: `static/`
- Copy: `backend/`
- Copy: `frontend/`
- Copy: `tests/`
- Copy: `author/`

### Files kept and modified at root

- Keep: `docs/`
- Keep: `data/`
- Modify: `CLAUDE.md`
- Modify: `.gitignore`

---

## Task 1: Preflight Inventory and Safety Checks

**Files:**
- Read-only check: `E:/tmp/XHS_ALL_IN_ONE/`
- Read-only check: `E:/小红书/`
- No file changes in this task.

- [ ] **Step 1: Confirm the approved spec exists**

Run from `E:/小红书`:

```bash
test -f docs/superpowers/specs/2026-06-02-xhs-all-in-one-baseline-migration-design.md
```

Expected: command exits with status `0` and prints nothing.

- [ ] **Step 2: Confirm the upstream baseline source exists**

Run from `E:/小红书`:

```bash
set -e
test -f /e/tmp/XHS_ALL_IN_ONE/main.py
test -f /e/tmp/XHS_ALL_IN_ONE/requirements.txt
test -f /e/tmp/XHS_ALL_IN_ONE/package.json
test -d /e/tmp/XHS_ALL_IN_ONE/backend/app
test -d /e/tmp/XHS_ALL_IN_ONE/frontend/src
test -d /e/tmp/XHS_ALL_IN_ONE/apis
test -d /e/tmp/XHS_ALL_IN_ONE/xhs_utils
test -d /e/tmp/XHS_ALL_IN_ONE/static
```

Expected: command exits with status `0` and prints nothing.

- [ ] **Step 3: Confirm current root still has the previous TypeScript baseline**

Run from `E:/小红书`:

```bash
set -e
test -f package.json
test -f tsconfig.json
test -d src
test -d tests
```

Expected: command exits with status `0` and prints nothing before migration. If this fails, stop and report which expected previous-baseline files are missing.

- [ ] **Step 4: Inspect git status before migration**

Run from `E:/小红书`:

```bash
git status --short
```

Expected: review the output before continuing. It may include the newly written spec/plan files and `.superpowers/` artifacts. If it shows unrelated tracked modifications that are not part of this migration round, stop and report them before moving files.

---

## Task 2: Move Previous TypeScript System into Legacy Package

**Files:**
- Create directory: `legacy/xhs-ops-collector/`
- Move: `src/`
- Move: `tests/`
- Move: `package.json`
- Move: `package-lock.json`
- Move: `tsconfig.json`
- Move: `vitest.config.ts`
- Remove generated directory: `node_modules/`
- Create: `legacy/xhs-ops-collector/docs/README.md`

- [ ] **Step 1: Create the legacy package directory**

Run from `E:/小红书`:

```bash
mkdir -p legacy/xhs-ops-collector/docs
```

Expected: `legacy/xhs-ops-collector/docs/` exists.

- [ ] **Step 2: Move TypeScript source, tests, and package files**

Run from `E:/小红书`:

```bash
set -e
for path in src tests package.json package-lock.json tsconfig.json vitest.config.ts; do
  if [ -e "$path" ]; then
    mv "$path" legacy/xhs-ops-collector/
  fi
done
```

Expected: the listed files/directories no longer exist at root, and existing ones now exist under `legacy/xhs-ops-collector/`.

- [ ] **Step 3: Remove stale generated root Node dependencies**

Run from `E:/小红书`:

```bash
rm -rf node_modules
```

Expected: root `node_modules/` no longer exists. This removes generated dependencies only; legacy dependencies can be reinstalled from `legacy/xhs-ops-collector/package-lock.json` when needed.

- [ ] **Step 4: Write the legacy package README**

Create `legacy/xhs-ops-collector/docs/README.md` with exactly this content:

```markdown
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
```

Expected: file exists and explains that the TypeScript system is no longer the main baseline.

- [ ] **Step 5: Verify legacy move**

Run from `E:/小红书`:

```bash
set -e
test -d legacy/xhs-ops-collector/src
test -d legacy/xhs-ops-collector/tests
test -f legacy/xhs-ops-collector/package.json
test -f legacy/xhs-ops-collector/tsconfig.json
test -f legacy/xhs-ops-collector/vitest.config.ts
test -f legacy/xhs-ops-collector/docs/README.md
test ! -d src
test ! -f tsconfig.json
```

Expected: command exits with status `0` and prints nothing.

---

## Task 3: Copy `XHS_ALL_IN_ONE` Baseline into Root

**Files:**
- Create/copy root baseline files and directories from `E:/tmp/XHS_ALL_IN_ONE`.
- Do not modify: `docs/`
- Do not modify: `data/`
- Do not overwrite: `CLAUDE.md`

- [ ] **Step 1: Refuse to continue if new baseline paths already exist unexpectedly**

Run from `E:/小红书`:

```bash
set -e
for path in main.py requirements.txt Dockerfile docker-compose.yml config apis xhs_utils static backend frontend author; do
  if [ -e "$path" ]; then
    echo "Refusing to copy: root path already exists: $path" >&2
    exit 1
  fi
done
```

Expected: command exits with status `0` and prints nothing. If it prints a path, inspect that path before continuing.

- [ ] **Step 2: Copy root-level upstream files**

Run from `E:/小红书`:

```bash
set -e
cp -a /e/tmp/XHS_ALL_IN_ONE/main.py ./main.py
cp -a /e/tmp/XHS_ALL_IN_ONE/requirements.txt ./requirements.txt
cp -a /e/tmp/XHS_ALL_IN_ONE/package.json ./package.json
cp -a /e/tmp/XHS_ALL_IN_ONE/Dockerfile ./Dockerfile
cp -a /e/tmp/XHS_ALL_IN_ONE/docker-compose.yml ./docker-compose.yml
cp -a /e/tmp/XHS_ALL_IN_ONE/.dockerignore ./.dockerignore
cp -a /e/tmp/XHS_ALL_IN_ONE/README.md ./README.md
```

Expected: each copied file exists at root.

- [ ] **Step 3: Copy upstream system directories**

Run from `E:/小红书`:

```bash
set -e
cp -a /e/tmp/XHS_ALL_IN_ONE/config ./config
cp -a /e/tmp/XHS_ALL_IN_ONE/apis ./apis
cp -a /e/tmp/XHS_ALL_IN_ONE/xhs_utils ./xhs_utils
cp -a /e/tmp/XHS_ALL_IN_ONE/static ./static
cp -a /e/tmp/XHS_ALL_IN_ONE/backend ./backend
cp -a /e/tmp/XHS_ALL_IN_ONE/frontend ./frontend
cp -a /e/tmp/XHS_ALL_IN_ONE/tests ./tests
cp -a /e/tmp/XHS_ALL_IN_ONE/author ./author
```

Expected: each copied directory exists at root.

- [ ] **Step 4: Verify copied baseline paths**

Run from `E:/小红书`:

```bash
set -e
test -f main.py
test -f requirements.txt
test -f package.json
test -f Dockerfile
test -f docker-compose.yml
test -f .dockerignore
test -f README.md
test -d config
test -d apis
test -d xhs_utils
test -d static
test -d backend/app
test -d frontend/src
test -d tests/backend
test -d author
```

Expected: command exits with status `0` and prints nothing.

---

## Task 4: Replace Root `.gitignore` with Combined Rules

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Write the combined `.gitignore`**

Replace `.gitignore` with exactly this content:

```gitignore
# Python
__pycache__/
*.py[cod]
*.so
.Python
.pytest_cache/
.cache/
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib64/
parts/
sdist/
var/
wheels/
MANIFEST
*.manifest
*.spec
__pypackages__/
.venv/
env/
venv/
ENV/
env.bak/
venv.bak/

# Node
node_modules/
frontend/node_modules/
legacy/xhs-ops-collector/node_modules/
npm-debug.log*
yarn-debug.log*
yarn-error.log*

# Build outputs
frontend/dist/
dist/
coverage/

# Local data and generated storage
data/
backend/app/storage/
legacy/xhs-ops-collector/data/
legacy/xhs-ops-collector/.tmp/
.tmp/
.tmp_docx_media/

# Secrets and local environment
.env
.env.*
local_settings.py
*.db
*.db-journal
db.sqlite3

# Claude / agent local state
.claude/
.superpowers/
.agent/

# IDE / OS
.idea/
.DS_Store

# Logs and local documents
*.log
*.docx
```

Expected: `.gitignore` includes both the old project's ignored local artifacts and the upstream Python/Node/storage artifacts.

- [ ] **Step 2: Verify ignored local companion artifacts are no longer reported**

Run from `E:/小红书`:

```bash
git status --short --ignored | grep -E '(^!! \.superpowers/|^!! data/|^!! node_modules/)' || true
```

Expected: command may show ignored entries with `!!`; it should not show `.superpowers/`, `data/`, or generated dependency folders as untracked `??` in the next normal `git status --short`.

---

## Task 5: Rewrite `CLAUDE.md` for the New Baseline

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Replace `CLAUDE.md` with new project rules**

Replace `CLAUDE.md` with exactly this content:

```markdown
# 小红书自动化运营系统项目规则

## 当前主系统基线

本项目主系统基线是 `XHS_ALL_IN_ONE`。

从本迁移阶段开始，根目录代表一个 Web-first 小红书运营平台，而不是原 TypeScript CLI 采集器。默认开发方向围绕：

- Python + FastAPI 后端
- SQLAlchemy + Alembic 数据模型
- React + Vite + Ant Design 前端
- `apis/`、`xhs_utils/`、`static/` 中的原生 XHS SDK/签名能力
- `backend/app/adapters/xhs/` 中的 XHS 适配层

原 TypeScript 系统只作为增强能力资产保留在 `legacy/xhs-ops-collector/`。除非任务明确要求抽取或接入 legacy 能力，不要以 legacy 系统作为新功能基线。

## 项目目标

构建一个小红书一站式智能运营平台。当前主系统支持账号矩阵、原生 XHS 笔记发现、内容库、草稿工坊、图片工坊、发布中心、任务中心、模型配置和自动运营等模块。

后续增强能力可以从 legacy 系统中选择性接入，例如灰豚热词来源、pipeline 健康检查、analysis-source JSONL 导出、飞书协作同步等。但这些能力必须按主系统的 FastAPI/React/SQLAlchemy 架构重新设计和接入。

## 当前迁移阶段边界

当前阶段只做：

- 以 `XHS_ALL_IN_ONE` 作为根目录主系统基线
- 保留 legacy TypeScript 系统到 `legacy/xhs-ops-collector/`
- 保留 `docs/` 和 `data/`
- 跑通主系统基础安装、构建、测试和健康检查

当前阶段不做：

- 不合并旧 SQLite 数据到新数据库
- 不把灰豚采集直接接入新后端
- 不把飞书同步直接接入新后端
- 不改造自动发布策略
- 不重构 XHS SDK
- 不做生产部署

## 技术约定

- 后端默认使用 Python 3.10+、FastAPI、SQLAlchemy、Alembic。
- 前端默认使用 React、Vite、Ant Design。
- 根目录 `package.json` 只用于签名 JS 运行所需的 Node 依赖。
- 前端依赖和构建在 `frontend/` 下管理。
- 默认数据库文件为 `data/spider_xhs.db`，由主系统配置决定。
- legacy 数据库 `data/xhs-ops.sqlite` 只作为历史数据保留，不是新主系统事实源。

## 目录约定

- `main.py`：主系统统一启动入口。
- `config/`：YAML 配置。
- `apis/`：XHS 底层 SDK。
- `xhs_utils/`：XHS 签名、Cookie、请求工具。
- `static/`：XHS 签名核心 JS 文件。
- `backend/app/`：FastAPI 后端主代码。
- `backend/app/api/`：API 路由。
- `backend/app/models/`：SQLAlchemy 数据模型。
- `backend/app/services/`：业务服务和调度服务。
- `backend/app/adapters/xhs/`：XHS SDK 适配层。
- `frontend/`：React/Vite 前端。
- `tests/`：主系统后端测试。
- `data/`：本地数据库和运行产物，不提交敏感数据。
- `docs/superpowers/specs/`：设计规格文档。
- `docs/superpowers/plans/`：实施计划。
- `legacy/xhs-ops-collector/`：旧 TypeScript CLI 系统，仅作为增强能力来源。

## XHS 原生能力安全规则

- 不保存账号密码、明文 Cookie、Token、API Key 到代码或文档。
- 生产环境必须覆盖默认 `SECRET_KEY`；开发默认值不能用于真实部署。
- Fernet 加密依赖稳定 secret 配置，迁移 secret 会影响已加密 Cookie/API Key 解密。
- XHS PC/Creator 操作默认低频、串行，不做高频批量请求。
- XHS SDK 或签名接口失败时，先定位接口/签名/账号状态变化，不盲目重试。
- Creator 发布和自动运营属于高风险账号动作；真实账号启用前必须单独做风险和 QA 设计。
- 不为绕过风控而实现规避检测、批量号池、验证码绕过或高频自动化。

## Legacy 能力接入规则

legacy 能力只在能提升主系统时接入。接入前必须先写设计，说明：

- 要接入的 legacy 能力是什么
- 对主系统用户体验有什么提升
- 使用主系统哪些表、API、页面或任务模型
- 是否需要数据迁移
- 如何验证不会污染主系统基线

不要把 legacy CLI 作为主系统运行入口。

## 开发规则

- 非 trivial 修改必须先有设计或计划。
- 改完主动跑相关验证：后端测试、前端 build、类型/依赖检查或健康检查。
- 手术式修改，不顺手重构无关代码。
- 因本次修改而变成未使用的 import、变量、函数应删除；既有死代码只报告，不主动删。
- 不要为了让代码跑起来而注释掉报错，找根本原因。
- 密钥、token、密码不进代码。
- 不自动 git push。
- commit 只有在用户明确要求时执行，commit message 用英文，简洁描述变更意图。
```

Expected: `CLAUDE.md` clearly states `XHS_ALL_IN_ONE` is authoritative and legacy TypeScript is enhancement-only.

- [ ] **Step 2: Verify key policy phrases exist**

Run from `E:/小红书`:

```bash
set -e
grep -F "本项目主系统基线是 \`XHS_ALL_IN_ONE\`" CLAUDE.md
grep -F "legacy/xhs-ops-collector/" CLAUDE.md
grep -F "Creator 发布和自动运营属于高风险账号动作" CLAUDE.md
```

Expected: all three lines are printed.

---

## Task 6: Verify Repository Layout After Migration

**Files:**
- Read-only verification over migrated root.

- [ ] **Step 1: Verify new root and preserved legacy layout**

Run from `E:/小红书`:

```bash
set -e
# New baseline root
test -f main.py
test -f requirements.txt
test -f package.json
test -f Dockerfile
test -f docker-compose.yml
test -d config
test -d apis
test -d xhs_utils
test -d static
test -d backend/app
test -d frontend/src
test -d tests/backend

# Preserved project assets
test -d docs/superpowers/specs
test -d docs/superpowers/plans

# Preserved legacy package
test -d legacy/xhs-ops-collector/src
test -d legacy/xhs-ops-collector/tests
test -f legacy/xhs-ops-collector/package.json
```

Expected: command exits with status `0` and prints nothing.

- [ ] **Step 2: Inspect git status after file moves and copies**

Run from `E:/小红书`:

```bash
git status --short
```

Expected: status shows many deletions/moves/additions due to baseline migration. It should not show `data/`, `.superpowers/`, root `node_modules/`, or generated dependency folders as untracked files.

---

## Task 7: Install Dependencies and Run Baseline Verification

**Files:**
- May create generated lock files:
  - `package-lock.json` for new root Node dependencies if npm creates it.
- May modify generated dependency directories ignored by git:
  - `node_modules/`
  - `frontend/node_modules/`

- [ ] **Step 1: Install Python dependencies**

Run from `E:/小红书`:

```bash
python -m pip install -r requirements.txt
```

Expected: command exits with status `0`. If it fails, capture the exact package/error output and stop before running tests.

- [ ] **Step 2: Install root Node dependencies for signature JS**

Run from `E:/小红书`:

```bash
npm install
```

Expected: command exits with status `0` and installs root dependencies such as `crypto-js` and `jsdom`.

- [ ] **Step 3: Install frontend dependencies**

Run from `E:/小红书`:

```bash
cd frontend && npm install
```

Expected: command exits with status `0`.

- [ ] **Step 4: Build frontend**

Run from `E:/小红书`:

```bash
cd frontend && npm run build
```

Expected: command exits with status `0` and writes `frontend/dist/`.

- [ ] **Step 5: Run backend test suite**

Run from `E:/小红书`:

```bash
python -m pytest
```

Expected: command exits with status `0`. If tests fail, report the exact failing test names and traceback summary.

- [ ] **Step 6: Run backend health smoke**

Run from `E:/小红书`:

```bash
set -e
python main.py --host 127.0.0.1 --port 8000 > /tmp/xhs-all-in-one-health.log 2>&1 &
APP_PID=$!
sleep 8
HEALTH=$(curl -s http://127.0.0.1:8000/api/health || true)
kill "$APP_PID" 2>/dev/null || true
wait "$APP_PID" 2>/dev/null || true
printf '%s\n' "$HEALTH"
test "$HEALTH" = '{"status":"ok","service":"spider-xhs"}'
```

Expected: prints exactly:

```json
{"status":"ok","service":"spider-xhs"}
```

If it fails, inspect `/tmp/xhs-all-in-one-health.log` and report the startup error.

---

## Task 8: Final Migration Report

**Files:**
- No code changes unless verification found a defect.

- [ ] **Step 1: Capture final git status**

Run from `E:/小红书`:

```bash
git status --short
```

Expected: shows the migration file changes. Generated ignored directories should not appear as `??`.

- [ ] **Step 2: Summarize verification results**

Prepare a short report with these fields:

```text
Migration status: success | partial | failed
New baseline root: XHS_ALL_IN_ONE
Legacy package: legacy/xhs-ops-collector
Preserved docs: yes | no
Preserved data: yes | no
Python dependencies: pass | fail | skipped
Root npm install: pass | fail | skipped
Frontend npm install: pass | fail | skipped
Frontend build: pass | fail | skipped
Backend pytest: pass | fail | skipped
Health endpoint: pass | fail | skipped
Known follow-ups:
- <item>
```

Expected: report is factual. Do not claim success for skipped or failed verification.

---

## Self-Review

- **Spec coverage:** The plan covers root baseline replacement, legacy TypeScript preservation, `CLAUDE.md` rewrite, `.gitignore` merge, docs/data preservation, dependency installation, frontend build, backend tests, and health endpoint verification. It explicitly excludes legacy data import and feature integration.
- **Placeholder scan:** No `TBD`, `TODO`, or unspecified implementation steps remain. Every file write includes exact content. Every command has an expected outcome.
- **Type/path consistency:** The target legacy path is consistently `legacy/xhs-ops-collector/`. The upstream source is consistently `/e/tmp/XHS_ALL_IN_ONE`. The target root is consistently `E:/小红书` / `/e/小红书`.
- **Scope check:** This is one migration subsystem: replace the project baseline and preserve the previous system as legacy enhancement material. Huitun integration, Feishu integration, pipeline check integration, and data import are deferred to future specs.

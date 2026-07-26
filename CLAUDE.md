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
- `frontend/src/platform-core/`：前端多平台共享 UI 内核，放平台 section registry、共享账号 shell、共享 action/readiness/shell 组件；平台差异留在各自 `frontend/src/pages/...` adapter/page 中。
- `tests/`：主系统后端测试。
- `data/`：本地数据库和运行产物，不提交敏感数据。
- `docs/superpowers/specs/`：设计规格文档。
- `docs/superpowers/plans/`：实施计划。
- `legacy/xhs-ops-collector/`：旧 TypeScript CLI 系统，仅作为增强能力来源。

## XHS 原生能力安全规则

- 不保存账号密码、明文 Cookie、Token、API Key 到代码或文档。
- 占位 `SECRET_KEY` + 非 loopback 监听会被启动硬闸直接拒绝（`backend/app/core/config.py` 的 `validate_secret_key_for_host`，独立于 ENVIRONMENT）。当前部署的真实密钥在根目录 `.env`（`SECRET_KEY` + `FERNET_KEY`，2026-07-26 配置，gitignored）——不要删除该文件；配置优先级为 YAML < `.env` < 环境变量。
- Fernet 加密依赖稳定 secret 配置，迁移 secret 会影响已加密 Cookie/API Key 解密。当前 `.env` 中 `FERNET_KEY` 已固定为旧默认 secret 的派生值，轮换 `SECRET_KEY` 不影响存量加密数据；轮换 `FERNET_KEY` 才会。
- XHS PC/Creator 操作默认低频、串行，不做高频批量请求。
- XHS SDK 或签名接口失败时，先定位接口/签名/账号状态变化，不盲目重试。
- `apis/`、`xhs_utils/`、`static/` 属于脆弱底层 SDK/签名层，默认不要直接修改；优先通过 `backend/app/adapters/xhs/` 做兼容适配。确需修改底层签名或 SDK 时，必须先写设计并说明影响范围。
- Creator 发布和自动运营属于高风险账号动作；真实账号启用前必须单独做风险和 QA 设计。
- 开发、联调、验证发布能力时，默认不得对真实账号执行真实发布；必须使用测试账号、dry-run/模拟路径，或获得用户对该次真实发布的明确授权。
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

## Git 主线规则

- 本项目唯一主线分支是 `master`，不是 `main`。
- 本地运行和用户验收默认以 `master` 为事实源；长期占用固定端口的前后端服务应从 `master` 启动。
- feature 分支或 worktree 只作为短期开发线程；线程提交不等于主线可用。
- `/closeout` 或“收尾”必须报告当前线程分支、提交 SHA、`master` 是否包含该提交，以及运行服务是否需要重启。
- scoped commit 完成后，如果 `master` 尚未包含该提交，必须先询问用户是否合并；用户同意后用 merge commit 合入 `master`（`git merge --no-ff`），不要默认用 fast-forward 指针移动。
- 如果用户暂不同意合并，最终报告必须明确说明：已提交但未合入 `master`，当前主线服务看不到该功能。

## Worktree 与分支管理

- 根目录 `E:\小红书` 是主工作区；用户语境里的 `master` 默认指根目录主工作区，而不是 `.claude/worktrees/` 下的隔离副本。
- `.claude/worktrees/<task-name>` 下的目录必须视为开发分支工作区，不得在汇报中称为“master 已完成”或暗示已合入根目录。
- 新建或使用 worktree 时，分支名必须显式表达任务意图，格式建议为 `worktree-<task-name>`、`feature/<topic>` 或 `fix/<topic>`；禁止让多个 worktree 都停留在 `master` 这种不可区分状态。
- 开始开发前必须先汇报当前工作区路径与当前分支；如果当前路径位于 `.claude/worktrees/`，同时说明“这是隔离 worktree，改动不会自动进入根目录 master”。
- 交付前必须区分三种状态：`worktree 已验证`、`已合回根目录 master`、`根目录服务已重启验证`；未完成哪一步就明确说未完成。
- 标准端口 `18080/18081` 默认代表根目录主工作区服务。若在 worktree 中临时启动服务，优先使用非标准端口，或明确说明端口当前指向哪个工作区。
- 合并、覆盖根目录、停止根目录服务、删除 worktree 或删除分支前，必须获得用户明确授权。

## 运维环境确认规则

- 执行 build、restart、部署类命令前，先报告：当前工作目录、目标服务/端口、目标环境（哪个 worktree 或根目录）。目标与预期不符时停下确认，不要在错误目录上执行。
- 重启前端 dev server 或后端服务前，先确认要重启的是哪个实例（根目录主服务还是 worktree 临时服务），避免误停 `18080/18081` 主服务。
- 构建 Docker 镜像时，禁止把本地构建结果打成官方/生产 `latest` tag；本地测试镜像必须用带任务标识的 tag（如 `dev-<topic>`），防止版本被静默覆盖回滚。

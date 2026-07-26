# 2026-07-26 止血修复批（Stabilization Hotfix Batch）

来源：2026-07-26 六路系统分析（后端 API / 服务层 / 数据层 / 前端 / 安全 / 测试工程）。
本批只做局部手术式修复，不做架构重构；不执行 git commit（等用户明确要求）。

## 范围与验收

### A. 数据库安全（backend/app/core/database.py, backend/alembic/env.py, 新迁移）
1. SQLite `PRAGMA journal_mode=MEMORY` → `WAL`，并加 `busy_timeout`（运行时 engine 与 alembic env 两处）。
2. 新 Alembic 迁移补高频轮询索引：
   - publish_jobs: (status, scheduled_at)（含 publish_mode 视查询形态决定）
   - auto_tasks: (status, next_run_at)
   - tasks: status
   - revision id ≤32 字符，用 batch_alter_table 与现有迁移风格一致。
- 验收：`python -m alembic -c backend/alembic.ini heads` 单 head；相关后端测试通过（test_database_engine_options、test_mysql_migration_compatibility 等）。

### B. 安全加固（backend/app/core/config.py, main.py, ai.py, asset_downloader.py, drafts/notes 链路）
1. 占位 SECRET_KEY 硬闸：secret_key 属于已知占位集合且监听非 loopback 时拒绝启动，错误信息引导设置真实密钥；docker-compose 默认注入 ENVIRONMENT=production。开发默认 host 评估改 127.0.0.1（LAN 部署需显式配置）。
2. SSRF 收口：把 ai.py `_download_public_http_image` 的公网 IP 校验/DNS pinning/禁重定向逻辑下沉为共享工具，`download_asset_to_local` 入口统一接入（drafts send-to-publish 外部 URL、notes add_note_asset/localize-images 链路）。
- 验收：相关安全/资产测试通过（test_beta_security_foundation、test_asset_downloader、test_config 等），新增针对内网地址拒绝的测试。

### C. 后端正确性（scheduler_service.py, rate_limiter.py, account_service.py 及调用点）
1. `run_due_auto_tasks`：每个 task 独立 try/except + rollback + commit；静默 `except: pass` 改为记录错误。
2. rate_limiter fallback 误用 `scheduler_interval_seconds` → 改用专用 `crawl_rate_limit_per_minute` 配置。
3. cookie 逻辑收敛：account_service 提供 `latest_cookie_header(db, account_id)`（created_at desc, id desc），替换 scheduler_service×2、publish.py、creator.py、xhs_source_image_import_service.py、monitoring_crawl_service.py、data_acquisition_service.py 中的重复实现。
- 验收：test_auto_tasks_accounts、test_publish_orchestration_contract、test_xhs_data_acquisition 及 test_api 相关子集通过。

### D. 前端性能（frontend/src/app/router.tsx）
1. 路由级 React.lazy + Suspense（antd Spin fallback），至少覆盖 xhs/wechat 平台页、admin 页、recharts 相关页；具名导出用 `.then(m => ({default: m.X}))`。
- 验收：`npm run build` 成功且产物出现分包 chunk；现有 frontend/tests 中 router/app-shell 相关测试通过。

## 约束
- 手术式修改；不触碰与目标无关的未提交变更；不 commit / 不 push。
- 涉及迁移必须检查 Alembic 单 head（closeout 门禁）。
- 每线程完成后报告：修改文件清单（file:line）、测试命令与输出摘要、行为变化说明。

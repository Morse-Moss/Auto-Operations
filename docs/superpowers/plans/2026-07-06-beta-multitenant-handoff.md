# Beta 多租户开发交接（2026-07-06）

## 一句话现状

Beta 安全底座已完成并合入根目录 `master`；下一步是 **Sprint 1：Beta 准入与管理开关**。面向 10 人外部体验官，多租户完成度约 70–75%。

## 已完成（已在根目录 `master`）

- 最小租户模型：`Tenant`、`TenantMember`，注册即建默认租户，用户为 owner。
- Beta 积分额度：`BetaCreditAccount` + `UsageLedger`（reserve/commit/refund/adjust），高成本 AI/图片/分析入口已接门禁，不足返回 402。
- 模型测试每日 3 次免费限制，超限 429，不扣主额度。
- Sprint 0 安全地基：signed media URL、媒体归属校验、reserve 原子扣减、commit/refund 终态互斥、idempotency key hash、异步图片保存失败 refund。
- 前端 usage balance 可见。

关键提交：
- `53a15b6 feat: harden beta media and quota safety`
- merge：`ca0de39 merge: absorb beta media quota safety`（在根目录 `master`）

## 待办（按优先级）

### Sprint 1 — Beta 准入与管理开关（最高，先做这个）
1. `User.role`（admin/user）、`User.status`（active/disabled）
2. `Tenant.status`（active/suspended）
3. 邀请码注册：无邀请码不能注册；邀请码有最大使用次数、记录 `used_by_user_id`；关闭自由注册
4. 鉴权统一拦截：disabled user → 403；suspended tenant → 403
5. Admin 最小 API：租户列表 / 用户列表 / 额度调整 / 冻结解冻租户 / 禁用启用用户
6. 前端：admin 入口仅对 `role==="admin"` 显示

做完 Sprint 1，Beta 完成度约 85%。

### Sprint 2 — 任务并发安全阀（高）
- 每 user 图片生成并发上限 1；每 tenant 上限 2；每 tenant 分析报告并发 1
- 超限返回 429/409（成本保护，非体验优化）

### Sprint 3 — 数据隔离审计（中高）
- 不要求全表立即 tenant 化。要求写测试证明用户 A 看不到用户 B 的：账号矩阵/笔记库/草稿/图片/发布任务/分析报告/任务中心/模型配置。媒体文件已覆盖。

### 暂不做（正式 SaaS 阶段再做）
多成员协作、tenant switcher、复杂 RBAC、计费/支付/发票、私有化面板、SSO、全表一次性 tenant 化。

## 关键代码位置

- 租户模型：`backend/app/models/tenant.py`
- 额度模型：`backend/app/models/usage_quota.py`
- 额度服务：`backend/app/services/usage_quota_service.py`
- 媒体归属/签名：`backend/app/services/asset_storage_policy.py`、`backend/app/api/files.py`
- 注册/鉴权：`backend/app/api/auth.py`、`backend/app/models/user.py`
- 用户类型：`frontend/src/types/index.ts`；导航：`frontend/src/components/layout/app-shell.tsx`
- Sprint 0 测试参考：`tests/backend/test_beta_security_foundation.py`

## 环境与规则（必须遵守）

- 主线分支 `master`；根目录主工作区 `E:\小红书`。worktree 改动不等于 master 完成。
- 数据库改动是收尾硬门：`py -3.12 -m alembic -c backend/alembic.ini heads` 必须单 head（当前 `20260704_tenants_usage_quota`）。
- Sprint 1 会加 `User.role/status`、`Tenant.status`、邀请码表 → 需要新 Alembic migration。
- 验证命令：
  - 后端 `py -3.12 -m pytest tests/backend/... -q`
  - 前端 `npm --prefix frontend run build`
- 不 push、不删 worktree/分支、不重启根目录服务、不真实发布，除非用户明确授权。
- 密钥/Cookie/Token 不进代码；生产必须覆盖默认 `SECRET_KEY`。

## 遗留

- 根目录服务 `18080/18081` 尚未重启验证 Sprint 0，新代码需重启后 smoke。
- 根目录有未跟踪 `compare-shots/`，不属于本轮 scope，未处理。
- worktree `worktree-xhs-beta-usage-quota` 及 closeout 期临时分支 `integration/xhs-beta-usage-quota-merge` 仍在，删除需授权。

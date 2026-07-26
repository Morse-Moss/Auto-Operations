# MySQL 能力路由迁移恢复设计

**日期：** 2026-07-12  
**状态：** 待用户复核  
**范围：** Alembic MySQL 事务边界、`20260710_model_capability_defaults` 半迁移恢复、模型能力绑定恢复，以及相关错误提示收敛

## 1. 背景与已确认事实

生产环境的 AI 改写和 AI 打分在调用上游模型前返回 `503 Service Unavailable`。云端 HTTP 日志、生产 MySQL 和当前运行代码共同确认：

- `/api/ai/rewrite-note` 多次在约 27-31ms 内返回 503，Railway 没有上游连接错误。
- `model_capability_defaults` 表存在，但当前行数为 0。
- 表的 `AUTO_INCREMENT=3`，说明迁移曾插入两行，随后发生回滚。
- `alembic_version` 仍为 `20260708_usage_ledger_followup_unique`，未前移到 `20260710_model_capability_defaults`。
- 文本模型 `#7 SEED2-MINI` 和视觉模型 `#8 SEED2-MINI` 仍存在，字段完整，所有者为有效管理员。
- 失败发生在能力解析阶段，早于积分预留和任务创建，因此本次失败没有扣费，也没有创建 AI 任务记录。

当前状态属于 MySQL 半迁移：DDL 已持久化，但迁移中的 DML 和 Alembic 版本更新被回滚。

## 2. 根因

`backend/alembic/env.py` 在 `context.configure()` 前调用 `ensure_mysql_alembic_version_table(connection)`。该预检包含 inspector 查询，在 SQLAlchemy 2.x 中会触发自动事务。

Alembic 创建 `MigrationContext` 时看到连接已经处于事务中，于是把它标记为外部事务。对 MySQL 非事务 DDL，Alembic 后续的迁移级事务管理因此直接退化为 `nullcontext()`，不会自行提交。

结果是：

1. `CREATE TABLE` 和 `CREATE INDEX` 被 MySQL 隐式提交。
2. `text`、`vision` 两条绑定插入成功但未提交。
3. `alembic_version` 更新成功但未提交。
4. 连接关闭时，绑定和版本更新一起回滚。
5. 应用仍能启动，但新运行时代码读取到空能力绑定表，按 fail-closed 规则返回 503。

## 3. 目标

1. 让 Alembic 在 MySQL/MariaDB 上正确接管迁移事务。
2. 让 `20260710_model_capability_defaults` 能安全恢复“表已存在、版本未前移”的半迁移状态。
3. 保留已经由管理员明确设置的能力绑定，不在迁移中覆盖人工选择。
4. 自动恢复当前唯一、无歧义的 `text` 和 `vision` 绑定。
5. 对有多个候选的 `image_generation` 保持 fail-closed，并在迁移后通过管理员能力路由接口显式绑定。
6. 验证修复不扣除用户积分、不触发真实 XHS 发布，也不在未授权时调用付费模型。
7. 让前端显示可操作的能力未配置错误，并避免同一失败弹出两次提示。

## 4. 非目标

- 不修改 `apis/`、`xhs_utils/` 或 `static/` 底层 XHS SDK/签名层。
- 不改变模型选择策略，不恢复基于 `is_default` 和 ID 顺序的隐式回退。
- 不迁移或重建现有业务数据。
- 不补偿积分，因为已确认失败发生在积分预留之前。
- 不执行真实 XHS 发布、Creator 上传或自动运营任务。
- 不在本设计批准前修改生产数据库、部署或重启服务。

## 5. 设计方案

### 5.1 MySQL Alembic 连接预检

在 `backend/app/core/alembic_compat.py` 增加职责明确的入口，例如：

```python
def prepare_mysql_alembic_connection(connection) -> None:
    ensure_mysql_alembic_version_table(connection)
    if connection.dialect.name in {"mysql", "mariadb"} and connection.in_transaction():
        connection.commit()
```

`backend/alembic/env.py` 只调用该入口，然后再执行 `context.configure()`。这样 Alembic 创建 `MigrationContext` 时不会误判已有外部事务，迁移级事务可以正常提交 DML 和版本号。

提交动作限定在 MySQL/MariaDB 的 Alembic 专用连接预检中，不改变应用业务 Session，也不影响 SQLite 行为。

### 5.2 半迁移识别与结构校验

修改 `backend/alembic/versions/20260710_model_capability_defaults.py`，使 `upgrade()` 支持两种入口状态：

- 表不存在：按原定义创建表和索引。
- 表已存在：检查必需列、唯一约束和外键目标是否符合本 revision 的定义；符合则作为已知半迁移继续，不符合则抛出明确错误并停止启动。

必需列为：

- `id`
- `capability`
- `model_config_id`
- `updated_by_user_id`
- `created_at`
- `updated_at`

`capability` 必须保持唯一；`model_config_id` 和 `updated_by_user_id` 必须分别指向 `model_configs.id` 与 `users.id`。缺失的普通索引可以幂等创建，但不能静默接受错误列或错误外键。

### 5.3 幂等能力回填

每个能力按以下顺序处理：

1. 查询该能力是否已经存在绑定。
2. 已存在时原样保留，不覆盖管理员选择。
3. 不存在时计算符合条件的管理员模型候选。
4. 只有候选数严格等于 1 时才插入。
5. 候选为 0 或大于 1 时保持未绑定。

按当前生产数据，预期迁移自动得到：

- `text -> #7 SEED2-MINI`
- `vision -> #8 SEED2-MINI`

`image_generation` 当前有多个合法候选，迁移不会猜测。迁移完成后，通过现有管理员接口 `PUT /api/model-configs/capability-defaults/image_generation` 显式设置为已验证的 `#5 RunningHub Image`。该操作属于生产数据变更，执行前需要用户单独授权。

### 5.4 前端错误提示收敛

后端继续返回结构化错误：

```json
{
  "detail": {
    "code": "MODEL_CAPABILITY_DEFAULT_NOT_CONFIGURED",
    "capability": "text"
  }
}
```

前端 `apiErrorMessage()` 增加已知能力错误映射，例如文本能力未配置时显示“文本生成模型尚未配置，请联系管理员在模型配置中设置文本默认模型”。

由页面负责展示改写、打分等具体动作错误时，对对应请求启用 silent 模式，避免 Axios 全局拦截器和页面 catch 各弹一次。该调整不改变 API 行为，也不参与数据库恢复事务。

前端提示收敛应作为独立提交和独立验证项；数据库迁移恢复不依赖该提交，必要时可以先恢复后端能力路由，再单独上线提示优化。

## 6. 测试设计

### 6.1 MySQL 事务边界回归

扩展 `tests/backend/test_mysql_migration_compatibility.py`：

- 模拟 MySQL inspector 已触发自动事务。
- 调用连接预检入口。
- 断言在 `context.configure()` 前执行一次 commit。
- 断言 SQLite 和非 MySQL 连接不发生额外 commit。

### 6.2 半迁移恢复回归

创建临时数据库并构造生产同构状态：

- `alembic_version` 为 `20260708_usage_ledger_followup_unique`。
- `model_capability_defaults` 表已存在且为空。
- 存在唯一管理员默认文本模型和视觉模型。
- 存在多个图片生成候选。

执行升级后断言：

- Alembic 版本到达 `20260710_model_capability_defaults`。
- 表未被删除或重建。
- `text` 和 `vision` 各有一条正确绑定。
- `image_generation` 仍未绑定。
- 再次执行升级不会新增重复数据。

### 6.3 结构不兼容回归

构造同名但缺列或缺唯一约束的表，断言迁移明确失败，错误信息指出不兼容项，不允许应用带着不可信 schema 启动。

### 6.4 前端回归

- 结构化能力错误能转换成中文可操作提示。
- 页面自处理的改写失败只出现一次提示。
- 既有字符串 `detail`、配额错误和普通 Axios 错误行为保持不变。

## 7. 生产执行顺序

1. 确认根目录 `master`、目标提交、Railway 当前生产 deployment，以及失败部署时是否会保留旧实例的实际策略。
2. 对 `alembic_version`、`model_capability_defaults`、`model_configs`、`users` 做可恢复备份或导出。
3. 记录部署前表结构、行数、AUTO_INCREMENT 和能力候选快照。
4. 部署已通过测试的事务与半迁移恢复代码。
5. 由应用启动执行 `alembic upgrade head`。
6. 验证生产 `alembic_version` 已到新 head。
7. 验证 `text -> #7`、`vision -> #8`，并确认没有重复绑定。
8. 经用户授权后，通过管理员 API 设置 `image_generation -> #5`。
9. 验证 `/api/health`、`/api/version`、请求 ID 和能力解析。
10. 在未授权真实模型调用时，只做只读解析验证；获得授权后再执行一次真实改写冒烟测试并核对积分流水。

## 8. 回滚与失败处理

- 新部署若在迁移阶段失败，立即停止推进并核对 Railway 是否仍由旧实例承载；不能只凭平台状态标签假设旧实例一定被保留。
- 不在生产执行 Alembic downgrade，因为 downgrade 会删除能力绑定表。
- 若结构校验失败，保留备份和现场，不自动删表或重建表。
- 若绑定回填完成但后续应用验证失败，绑定数据可被旧运行时代码安全忽略或继续读取；回滚应用版本不需要删除绑定。
- 显式绑定 `image_generation` 前先验证模型配置 `#5` 仍完整，不基于历史记录盲目写入。

## 9. 验收标准

- 相关后端测试、迁移兼容性测试和前端契约测试通过。
- 前端生产构建通过。
- 新鲜数据库和半迁移数据库都能升级到唯一 Alembic head。
- 生产版本号、数据库 revision 和目标提交一致。
- AI 改写不再因 `MODEL_CAPABILITY_DEFAULT_NOT_CONFIGURED` 返回 503。
- 未执行真实模型调用时不产生新的任务、积分流水或 Provider 请求。
- 获得授权后的单次真实改写成功，并且只产生一条预留/提交积分链路。
- 同一错误只向用户展示一次，且提示包含可执行的管理员处理方向。

## 10. 影响文件

- `backend/alembic/env.py`
- `backend/app/core/alembic_compat.py`
- `backend/alembic/versions/20260710_model_capability_defaults.py`
- `tests/backend/test_mysql_migration_compatibility.py`
- 新增或扩展半迁移恢复测试文件
- `frontend/src/lib/api.ts`
- `frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx` 或对应请求封装
- 相关前端契约测试

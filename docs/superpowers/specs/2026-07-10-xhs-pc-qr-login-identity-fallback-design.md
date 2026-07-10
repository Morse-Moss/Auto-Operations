# XHS PC 扫码登录身份降级设计

## 问题与证据

生产会话 `246` 在手机确认前连续返回 `200`，确认后从 `2026-07-10 09:31:12Z` 起稳定返回应用侧 `502`；Railway HTTP 日志的 `upstreamErrors` 为空，排除 Cloudflare 到 Railway 的连接故障。生产数据库中该会话停在 `scanned`，没有 `web_session` 持久化，也没有创建账号。

生产容器对已过期会话做安全诊断时，小红书 `/api/qrcode/userinfo` 返回正常 JSON，`data` 字段明确包含 `userId`。现有 `XHSLoginApi.check_qrcode_status()` 只返回成功标记、提示和 Cookie，丢弃了这段身份元数据；API 随后只能依赖 `/api/sns/web/v2/user/me` 与自资料接口识别账号。两个资料接口被上游 Cloudflare 拒绝时，已经完成的扫码确认无法安全落库。

## 设计

1. `XHSLoginApi` 保存最近一次二维码状态响应的 `data` 副本，但不改变现有三元组返回签名，不改变请求 URL、签名、频率或 Cookie。
2. `XhsPcLoginAdapter` 从该副本提取 `userId`，标准化为 `user_info.external_user_id` 后交给 API 层。
3. API 仍优先读取完整资料，再尝试自资料接口；只有两者都失败且扫码响应提供了非空稳定 `external_user_id` 时，才用最小身份完成账号绑定并保存已确认 Cookie。
4. 若扫码响应没有稳定用户 ID，继续返回受控 `502`，不匿名落库，避免同一账号重复创建。
5. `requests` 网络或非 JSON 瞬时异常保留当前会话状态，让下一次低频轮询恢复；不在单次请求内增加盲目重试。

## 影响范围

- `apis/xhs_pc_login_apis.py`：只暴露已有响应元数据，不修改底层签名与请求行为。
- `backend/app/adapters/xhs/pc_login_adapter.py`：把 `userId` 映射到主系统登录合同。
- `backend/app/api/login_sessions.py`：把资料读取从认证硬门槛降为可选补全，同时保持无身份时 fail closed。
- 后端回归测试：覆盖元数据保留、adapter 映射、资料双失败后的稳定身份落库、无身份继续拒绝、Cloudflare 瞬时恢复。

## 非目标

- 不修改 Creator 登录与发布路径。
- 不增加请求重试次数或并发。
- 不记录、输出或迁移 Cookie、Token、二维码内容。
- 不自动提交、推送或部署。

## 验收

- 手机扫码确认且资料接口失败时，只要二维码状态响应含 `userId`，PC 账号仍能绑定成功并保存 Cookie。
- 二维码响应缺少 `userId` 且资料接口失败时，仍返回受控错误且不创建账号。
- 既有 PC/Creator 二维码、手机号登录和账号去重测试继续通过。

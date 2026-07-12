# XHS PC 登录与笔记发现可靠性修复设计

## 问题与生产证据

生产环境 `PC 22` 在账号列表中显示 `active`，但其最新 Cookie 只有 `a1`、`webId`、`gid` 等初始化字段，缺少 XHS PC 登录态所需的 `web_session`。使用该账号调用笔记发现时，Railway 直连响应为 `502 {"detail":"无登录信息，或登录信息为空"}`；经 Cloudflare 访问时，这个应用错误又被替换成误导性的源站 `502` 页面。

二维码状态接口在 `codeStatus=2` 时被现有 SDK 直接视为成功。SDK 只从 `data.login_info.session` 提取会话；如果 XHS 从响应 Cookie、不同字段命名或嵌套结果下发 session，当前实现不会保存。随后 API 层在资料接口失败但二维码响应包含 `userId` 时仍允许创建账号，最终形成“身份已识别，但登录会话不存在”的伪 `active` 状态。

生产搜索请求均在约一秒内由应用主动返回 `502`，Railway 实例、数据库、健康接口和版本接口正常，因此本次修复不处理 Cloudflare、Railway 容量或请求超时。

## 目标

- PC 二维码登录只有在持久化 Cookie 中存在非空 `web_session` 时才进入 `confirmed` 并创建或更新 `active` 账号。
- 兼容 XHS 登录完成响应中常见的 session 下发位置，不改变签名算法、请求频率或接口 URL。
- 资料接口失败时仍可使用二维码返回的稳定 `userId` 补全最小身份，但前提是会话凭证已经有效。
- 笔记发现遇到 XHS “无登录信息”类响应时，将账号标记为 `expired`，返回不会被 Cloudflare 改写的明确用户提示。
- 生产验收必须覆盖重新扫码、Cookie 会话存在性和真实关键词搜索成功，不能只验证接口健康。

## 方案决策

采用“多来源提取 + 会话硬门槛 + 搜索失效闭环”。不采用以下方案：

- 仅移除身份兜底：能够避免伪账号，但会让资料接口偶发失败重新阻断已经拿到有效会话的登录。
- 浏览器 Cookie 中转或批量代理：扩大敏感凭证暴露面，也不符合当前低频原生 XHS 适配边界。
- 对 `502` 自动重试：上游已明确判定无登录信息，重试不会产生会话，只会增加风控风险。

## 登录数据流

1. `XHSLoginApi` 继续调用现有二维码状态和登录完成接口。
2. 登录完成响应到达后，按以下顺序提取 session：
   - 响应 Cookie 中已有的 `web_session`；
   - `data.login_info.session` 或 `data.loginInfo.session`；
   - `data.web_session`、`data.webSession` 或 `data.session`；
   - `data.result` 下相同字段。
3. 提取到的非空 session 统一写入内存 Cookie 字典的 `web_session`，不记录原始值。
4. `XhsPcLoginAdapter` 只有在 SDK 返回成功且 `web_session` 非空时返回 `confirmed`。二维码已确认但会话尚未取得时保持 `scanned`，让现有低频轮询继续尝试；不创建账号、不写 Cookie 版本。
5. 会话有效后，API 层仍优先获取完整资料，其次获取自资料，最后才使用二维码 `userId` 创建最小身份账号。

## 搜索失效闭环

`POST /api/xhs/pc/search/notes` 保持现有适配器调用。若上游失败消息匹配“无登录信息”“登录信息为空”或等价登录失效信号：

- 将当前账号状态更新为 `expired`；
- 保存不含 Cookie 的可读状态说明；
- 返回 `409 Conflict` 和“账号登录已失效，请重新扫码登录”的稳定提示。

其他 XHS 上游错误继续使用现有 `502` 行为，避免把签名、限流和内容错误误判成登录失效。

## 安全与影响范围

- 修改 `apis/xhs_pc_login_apis.py` 仅限解析登录响应和合并 session，不修改签名 JS、请求 URL、请求频率或重试策略。
- 修改 `backend/app/adapters/xhs/pc_login_adapter.py`，在适配层实施有效会话门槛。
- 修改 `backend/app/api/platforms/xhs/pc.py`，为笔记搜索增加登录失效分类和账号状态回写。
- 不记录、输出或迁移 Cookie、Token、二维码内容和 session 值；日志和测试只断言字段是否存在。
- 不修改 Creator 登录、自动发布、XHS 签名核心或其他平台适配器。

## 测试与验收

### 自动化测试

- SDK 能从响应 Cookie、snake_case、camelCase、直接 session 和 `result` 嵌套结构提取 `web_session`。
- 二维码 `codeStatus=2` 但缺少 `web_session` 时，adapter 返回 `scanned`，API 不创建账号或 Cookie 版本。
- 有效 `web_session` 且资料接口失败时，二维码身份兜底仍能创建 `active` 账号。
- 笔记搜索收到“无登录信息”时返回 `409`，账号变为 `expired`，响应不包含敏感 Cookie。
- 现有 PC 二维码、手机号登录、账号去重和笔记搜索序列化测试继续通过。

### 生产验收

1. 推送根目录 `master` 并等待 Railway `/api/version` 更新到新提交。
2. 用户在生产页面重新扫描 PC 二维码并确认登录。
3. 数据库只读检查新 Cookie 版本包含非空 `web_session`，不输出其值。
4. 使用该账号在“笔记发现”搜索一个普通关键词，要求接口返回 `200` 且结果结构有效。
5. 验收后确认 `/api/health` 为 `200`、实例无重启或异常网络日志。

## 非目标

- 不保证 XHS 始终返回笔记；空结果可以是合法业务响应，但不能是登录错误。
- 不绕过验证码、风控或账号限制，不增加并发与自动重试。
- 不自动执行真实发布或其他高风险账号动作。

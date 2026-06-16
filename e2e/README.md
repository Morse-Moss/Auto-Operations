# E2E Tests

本目录存放真实浏览器端到端 smoke 测试，用于验证用户可触达的主流程是否能在本地前后端上跑通。

## 约定

- 测试文件命名：`*-e2e-smoke.spec.js`。
- 默认目标服务：前端 `http://127.0.0.1:18080`，后端由前端代理访问 `http://127.0.0.1:18081`。
- 测试必须通过 UI/API 创建自己的临时测试数据，不写入密钥、Cookie、Token 或真实账号敏感信息。
- 分析报告相关 E2E 只能验证真实门禁行为：样本不足时必须阻断生成；不得伪造笔记、评论或报告。
- Playwright 产物输出到 `test-results/`，该目录为本地运行产物，不提交。

## 运行

先启动本地服务：

```bash
py -3 -m uvicorn backend.app.main:app --host 127.0.0.1 --port 18081
cd frontend && npm run dev -- --host 127.0.0.1 --port 18080
```

再在仓库根目录运行：

```bash
cd e2e && npm install
npm test -- xhs-analysis-e2e-smoke.spec.js

# 或者从仓库根目录直接运行
NODE_PATH="./e2e/node_modules" ./e2e/node_modules/.bin/playwright test e2e/xhs-analysis-e2e-smoke.spec.js --browser=chromium --reporter=line
```

如果首次运行提示缺少浏览器，执行：

```bash
cd e2e && npx playwright install chromium
```

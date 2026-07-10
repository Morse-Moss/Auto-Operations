# 小红书自动化运营系统

面向内部运营团队的 Web 化小红书运营工作台，覆盖数据获取、内容沉淀、草稿处理、素材管理、发布协同、任务追踪和后台配置。

本仓库以现有 Web 主系统为基线，后端采用 FastAPI + SQLAlchemy + Alembic，前端采用 React + Vite + Ant Design。系统默认围绕已授权账号和合规业务场景使用，不面向公开爬取、批量规避风控或未授权自动化。

## 当前能力

- 账号与权限：支持平台账号、管理员权限、后台配置和运行状态管理。
- 数据获取：支持关键词、链接、批量任务等数据获取入口，并将结果沉淀到内容库。
- 内容库：支持笔记内容、互动数据、素材信息、标签、筛选、导出和批量处理。
- 草稿工坊：支持从内容库生成和编辑草稿，管理标题、正文、标签和素材顺序。
- 图片工坊：支持图片资产管理、预览、替换和 AI 图片处理工作流。
- 发布中心：支持发布前校验、任务状态跟踪、失败原因展示和人工确认流程。
- 任务中心：支持采集、补全、导入、导出、发布等任务的状态追踪。
- 管理配置：支持模型配置、积分/额度、用户、租户和系统参数管理。

## 安全边界

- 仅用于已授权账号和合规业务场景。
- 不在代码、文档或提交记录中保存账号密码、Cookie、Token、API Key 等敏感信息。
- 生产环境必须覆盖默认 `SECRET_KEY`，并按部署环境配置数据库、CORS、域名和 HTTPS。
- 真实发布、自动运营等高风险动作必须经过单独授权、测试账号验证和上线前 QA。
- 底层签名、账号状态和平台接口属于高风险区域，失败时应先定位接口、签名、权限或账号状态，不做盲目高频重试。

## 技术栈

- 后端：Python 3.10+、FastAPI、SQLAlchemy、Alembic。
- 前端：React、Vite、TypeScript、Ant Design。
- 数据库：本地默认 SQLite，生产可按配置切换到 MySQL。
- 运行入口：根目录 `main.py`。
- 默认端口：前端 `18080`，后端 `18081`。

## 本地运行

建议在 Windows 环境使用 `py` 启动 Python，避免系统 alias 干扰。

```bash
pip install -r requirements.txt
npm --prefix frontend install
py -3 main.py --with-frontend
```

启动后访问：

- 前端：http://localhost:18080
- 后端接口文档：http://localhost:18081/docs

## 常用验证

```bash
py -X utf8 -m alembic -c backend/alembic.ini heads
py -X utf8 -m pytest tests/backend -q
npm --prefix frontend run build
```

如果只改前端页面或组件，至少运行：

```bash
npm --prefix frontend run build
```

如果只改后端接口、模型或服务，至少运行相关后端测试，并确认 Alembic 只有一个 head。

## 目录结构

```text
.
├── main.py                         # 统一启动入口
├── config/                         # YAML 配置
├── apis/                           # 底层平台能力封装
├── xhs_utils/                      # 请求、签名和 Cookie 工具
├── static/                         # 静态资源和签名运行所需文件
├── backend/
│   └── app/
│       ├── api/                    # FastAPI 路由
│       ├── core/                   # 配置、数据库、安全、时区
│       ├── models/                 # SQLAlchemy 模型
│       ├── services/               # 业务服务和调度服务
│       └── adapters/xhs/           # 平台适配层
├── frontend/
│   └── src/
│       ├── pages/                  # 页面入口
│       ├── components/             # 共享组件
│       ├── lib/                    # HTTP 客户端和工具
│       └── platform-core/          # 多平台共享 UI 内核
├── tests/                          # 后端测试
├── data/                           # 本地数据库和运行产物
├── docs/                           # 设计规格和实施计划
└── legacy/                         # 历史能力资产，仅作参考和选择性迁移来源
```

## 开发约定

- 根目录主线分支为 `master`。
- 非 trivial 修改应先有设计或计划，并在改完后跑相关验证。
- 不把历史 CLI 系统作为新功能主入口，新增能力应接入当前 FastAPI/React 主系统。
- 不顺手重构无关模块，不回滚他人未提交改动。
- 不自动提交或推送，除非本轮任务已获得明确授权。

## 部署提示

生产部署前至少确认：

- 已设置稳定且安全的 `SECRET_KEY`。
- 数据库连接、迁移、备份和恢复策略已配置。
- 域名、HTTPS、CORS、反向代理和静态资源路径已验证。
- 管理员账号、权限边界、额度策略和日志留存已检查。
- 真实账号动作已完成单独授权和上线前验收。

## 许可与归属

本仓库是内部业务系统代码仓库。未经授权，不得公开分发、商用转授权或移作无关项目使用。

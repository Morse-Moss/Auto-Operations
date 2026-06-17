# RunningHub 图片工坊默认上游接入设计

日期：2026-06-16

## 结论

图片工坊默认图片生成上游切换为 RunningHub AI App：

- 无参考图：调用文生图 AI App `2046760522573418497`
- 有参考图：调用参考图生图 AI App `2046794946094571522`
- 默认比例：`3:4`
- 默认分辨率：`1k`
- 参考图上限：由 RunningHub AI App 暴露的 `IMAGE` 输入节点数量决定；当前图生图 App 暴露 2 个 `IMAGE` 节点

原 `openai-compatible` 图片模型能力保留，但不作为图片工坊默认路径。这样可以解决当前 Sub2API 上游参考图不进入图像输入、图片工坊“参考图”体验失真的问题。

## 背景与证据

当前图片工坊前端和后端都会传递 `reference_images`，但 Sub2API `gpt-image-2` 生成响应中 `usage.input_tokens_details.image_tokens = 0`，说明参考图没有被上游模型作为图片输入处理。用户上传参考图后实际退化为文生图。

RunningHub 官网 API 文档确认 AI App 调用链路为：

1. `GET /api/webapp/apiCallDemo` 获取 AI App 调用示例与 `nodeInfoList`
2. `POST /openapi/v2/media/upload/binary` 上传图片资源
3. `POST /task/openapi/ai-app/run` 启动 AI App 任务
4. `POST /task/openapi/status` 轮询任务状态
5. `POST /task/openapi/outputs` 获取生成结果

已验证用户提供的两个 ID 是 RunningHub AI App 的 `webappId`，不是 ComfyUI `workflowId`。使用 ComfyUI `getJsonApiFormat` 会返回 `WORKFLOW_NOT_EXISTS`，应走 AI App API。

## RunningHub 节点映射

### 文生图 AI App

- `webappId`: `2046760522573418497`
- 应用名：`鸡皮提 Image 2 文生图(全能图片G)`

可覆盖节点：

| nodeId | fieldName | fieldType | 说明 |
| --- | --- | --- | --- |
| `136` | `prompt` | `STRING` | 输入提示词 |
| `136` | `aspectRatio` | `LIST` | 选择版式 |

`aspectRatio` 可选值：`empty`, `1:1`, `4:3`, `3:4`, `3:2`, `2:3`, `16:9`, `9:16`, `21:9`, `9:21`。

默认调用参数：

```json
[
  { "nodeId": "136", "fieldName": "prompt", "fieldValue": "用户提示词" },
  { "nodeId": "136", "fieldName": "aspectRatio", "fieldValue": "3:4" }
]
```

### 参考图生图 AI App

- `webappId`: `2046794946094571522`
- 应用名：`全能图片G-2.0-图生图-低价渠道版`

可覆盖节点：

| nodeId | fieldName | fieldType | 说明 |
| --- | --- | --- | --- |
| `3` | `image` | `IMAGE` | 上传图像 1 |
| `2` | `image` | `IMAGE` | 上传图像 2 |
| `4` | `prompt` | `STRING` | 输入文本 |
| `4` | `aspectRatio` | `LIST` | 设置比例 |
| `4` | `resolution` | `LIST` | 分辨率 |

`aspectRatio` 可选值：`empty`, `3:2`, `1:1`, `2:3`, `5:4`, `4:5`, `16:9`, `9:16`, `21:9`, `3:4`, `4:3`。

`resolution` 可选值：`1k`, `2k`, `4k`。

默认调用参数：

```json
[
  { "nodeId": "3", "fieldName": "image", "fieldValue": "RunningHub 上传返回的 filename_1" },
  { "nodeId": "2", "fieldName": "image", "fieldValue": "RunningHub 上传返回的 filename_2" },
  { "nodeId": "4", "fieldName": "prompt", "fieldValue": "用户提示词" },
  { "nodeId": "4", "fieldName": "aspectRatio", "fieldValue": "3:4" },
  { "nodeId": "4", "fieldName": "resolution", "fieldValue": "1k" }
]
```

RunningHub 上传接口返回 `filename` 与 `download_url`。AI App 的 `IMAGE` 字段应传 `filename`，不是 `download_url`。

## 用户体验设计

### 图片工坊生成入口

用户继续使用现有图片工坊：

- 填写提示词
- 可选上传/选择参考图
- 点击生成

系统不要求用户选择模型或工作流。后端按参考图数量自动分流：

- `reference_images` 为空：文生图 AI App
- `reference_images` 非空：参考图生图 AI App

### 参考图数量规则

参考图上限不写死为产品规则，而是从 RunningHub AI App 暴露的 `IMAGE` 输入节点数量得出。当前 `2046794946094571522` 调用示例返回 2 个 `IMAGE` 节点：

- `nodeId=3`, `fieldName=image`, `description=上传图像1`
- `nodeId=2`, `fieldName=image`, `description=上传图像2`

因此当前图生图 App 的有效参考图上限是 2 张：

- 0 张：文生图
- 1 张：图生图，填入第一个 `IMAGE` 节点 `nodeId=3`
- 2 张：图生图，按用户选择顺序填入 `nodeId=3` 和 `nodeId=2`
- 超过当前 App 暴露的 `IMAGE` 节点数量：后端返回 422，前端提示“当前 RunningHub 图生图工作流最多支持 N 张参考图”

如果未来替换为支持更多图片输入的 RunningHub AI App，只需要更新节点映射，系统上限随 `IMAGE` 节点数量提升。

### 默认输出参数

首版不在前端暴露比例和分辨率选择，使用固定默认值：

- `aspectRatio = 3:4`：适合小红书竖版图文/封面
- `resolution = 1k`：成本和稳定性优先

后续可在图片工坊增加“高级参数”，开放比例和分辨率。

## 后端架构

### Provider 选择

扩展图片模型 provider：

- `openai-compatible`：保留现有上游
- `runninghub-ai-app`：新增 RunningHub AI App 上游

图片工坊默认使用 `runninghub-ai-app`。API Key 继续使用 `ModelConfig.encrypted_api_key` 加密保存，不进入源码、文档或 git diff。

### RunningHubImageClient

新增 `RunningHubImageClient`，职责：

1. 校验配置
   - `base_url` 默认 `https://www.runninghub.cn`
   - `api_key` 必填
2. 解析本地参考图
   - 支持 `/api/files/media/<file>`
   - 支持本地文件路径
   - 支持公网 URL 时可直接作为输入来源；首版仍建议下载/上传到 RunningHub，统一得到 `filename`
3. 上传媒体
   - `POST /openapi/v2/media/upload/binary`
   - 返回 `filename`
4. 启动 AI App
   - `POST /task/openapi/ai-app/run`
   - 参数包含 `apiKey`, `webappId`, `nodeInfoList`
5. 轮询任务状态
   - `POST /task/openapi/status`
   - 状态值：`QUEUED`, `RUNNING`, `FAILED`, `SUCCESS`
6. 获取输出
   - `POST /task/openapi/outputs`
   - 取第一个图片类型结果的 `fileUrl`

### 与现有 API 的关系

现有 `/api/ai/images/generate` 保持不变。内部 `get_image_ai_client()` 根据默认图片模型配置的 provider 返回不同 client。

返回结构仍保持：

```json
{
  "url": "https://...generated.png",
  "raw": { "runninghub": "原始响应摘要" },
  "asset": { ... }
}
```

保存到 `AiGeneratedAsset.params` 的信息包括：

- `provider = runninghub-ai-app`
- `webapp_id`
- `reference_images`
- `runninghub_task_id`
- `runninghub_outputs`
- `aspect_ratio`
- `resolution`

不保存 API Key。

## 错误处理

### 配置错误

- 未配置 RunningHub API Key：返回 400，提示“RunningHub API Key 未配置”
- 未配置默认图片模型：保持现有 400 逻辑
- provider 不支持：返回 400，提示“Unsupported image provider”

### 输入错误

- 提示词为空：沿用现有校验
- 参考图数量超过当前 RunningHub 图生图 App 暴露的 `IMAGE` 节点数量：返回 422
- 参考图文件不存在：返回 400，提示具体引用路径不可用
- 参考图上传失败：返回 502，提示 RunningHub 上传失败

### 任务错误

- `ai-app/run` 返回非 0：返回 502，透出 RunningHub `msg` 与安全摘要
- `status = FAILED`：返回 502，不保存资产
- 轮询超时：返回 504，不保存资产
- outputs 为空或无图片：返回 502，不保存资产

错误提示应引导用户下一步，而不是只显示“AI 图片生成失败”。例如：

- “RunningHub 生成超时，当前结果未保存。请稍后重试或降低分辨率。”
- “参考图上传 RunningHub 失败，请确认图片文件存在且小于平台限制。”
- “当前 RunningHub 工作流最多支持 2 张参考图。”

## 安全与密钥规则

- API Key 只保存到 `model_configs.encrypted_api_key`
- 设计文档、源码、测试 fixture 不包含真实 API Key
- 测试使用 fake client 或环境变量占位
- 运行日志不打印 Authorization header 或 apiKey body 字段
- `raw` 响应入库前不得包含 API Key

## 测试计划

### 单元测试

1. 文生图 nodeInfoList 组装
   - 输入 prompt
   - 无 reference_images
   - 断言 webappId 为 `2046760522573418497`
   - 断言 prompt 与 `aspectRatio=3:4`

2. 图生图 nodeInfoList 组装
   - 输入 prompt + 2 张参考图
   - mock 上传返回两个 filename
   - 断言 webappId 为 `2046794946094571522`
   - 断言 `nodeId=3`、`nodeId=2` 图片字段顺序正确
   - 断言 `resolution=1k`

3. 参考图上限
   - 根据当前图生图 App 的 `IMAGE` 节点数量计算上限
   - 当前映射有 2 个 `IMAGE` 节点，因此输入 3 张参考图时断言返回 422 或 ValueError

4. 任务轮询成功
   - mock status 从 `QUEUED` 到 `RUNNING` 到 `SUCCESS`
   - mock outputs 返回 `fileUrl`
   - 断言返回 url

5. 任务失败
   - mock status 返回 `FAILED`
   - 断言不保存资产，错误可读

6. outputs 空
   - mock outputs 返回空数组
   - 断言生成失败

### API 测试

扩展 `tests/backend/test_api.py` 中图片生成测试：

- 默认 RunningHub provider 下，`/api/ai/images/generate` 调用 fake RunningHub client
- 成功保存 `AiGeneratedAsset`
- intruder 无法看到他人资产
- 失败时 task 标记为 failed

### 手动验证

1. 在模型配置中创建默认图片模型：
   - provider: `runninghub-ai-app`
   - model_name: `runninghub-image-g`
   - base_url: `https://www.runninghub.cn`
   - api_key: 用户 RunningHub API Key
2. 图片工坊输入提示词，不上传参考图，生成图片
3. 图片工坊上传 1 张参考图，生成图片
4. 图片工坊上传 2 张参考图，生成图片
5. 上传超过当前图生图 App `IMAGE` 节点数量的参考图，确认阻止并提示

## 不做范围

首版不做：

- 不把 RunningHub webappId 做成前端可编辑高级字段
- 不做 webhook 回调；使用轮询即可
- 不接 ComfyUI workflow API，因为当前 ID 是 AI App webappId
- 不支持超过当前 RunningHub 图生图 App 暴露的 `IMAGE` 节点数量的参考图
- 不开放 2k/4k 分辨率选择
- 不自动把历史 Sub2API 资产迁移到 RunningHub

## 完成标准

- 图片工坊默认能通过 RunningHub 文生图生成图片
- 图片工坊有参考图时能通过 RunningHub 图生图生成图片
- 生成结果保存到 AI 图片资产
- 失败时不保存假成功资产
- API Key 不出现在源码、文档、测试 fixture、日志或 git diff 中
- 后端相关测试通过
- 前端构建通过

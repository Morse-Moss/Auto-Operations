# XHS 草稿工坊图片编辑与图片工坊上下文修复设计

日期：2026-06-26
工作区：`E:\小红书`
分支：`master`
状态：需求已收敛，待实现计划

## 1. 结论

本轮目标不是继续把图片工坊做成独立 AI 图片工具，而是把草稿工坊升级成真正的图文草稿工作台，并修复“从草稿工坊送入图片工坊后没有图片”的硬问题。

采用方案：

```text
草稿工坊
  - 顶部折叠草稿列表
  - 左侧原文内容与来源素材
  - 中间当前草稿编辑与草稿图片素材区
  - 右侧 AI 助手：改写、标题候选、标签候选
  - 草稿图片可添加、删除、AI 编辑

图片工坊
  - 从草稿资产稳定接收候选图
  - 保持最终发布图片选择与发布中心 handoff
```

图片编辑采用“新增编辑图，保留原图”的规则。原图如果不需要，用户可在草稿图片素材区手动删除。草稿图片允许删到 0 张；只在送发布中心前要求最终发布图片不为空。

## 2. 当前问题判断

### 2.1 图片工坊无图的根因

当前草稿工坊送图片工坊时走：

```text
fetchDraftAssets(saved.id)
  → assets.items.map(draftAssetToCandidate)
  → saveImageStudioDraftContext(candidate_images)
```

但 `draftAssetToCandidate` 依赖通用转换：

```ts
if (asset.asset_type !== "image" || !isUsableImageUrl(asset.url)) return null;
```

也就是说，只要 `DraftAsset.url` 为空、不是 `http(s)`、不是 `/api/...`，候选图就会被过滤掉。

后端 `DraftAsset` 实际有两个路径字段：

```text
url
local_path
```

后端序列化中已经倾向把 `local_path` 显示为 `/api/files/media/<file>`，但前端仍缺少统一 resolver。草稿工坊预览、图片工坊候选、图片编辑参考图都应该统一解析草稿图片可用 URL，而不是各处手写 `asset.url`。

### 2.2 草稿工坊布局不符合工作目标

当前 `DraftWorkbenchShell` 是固定三栏：

```text
左：草稿列表
中：草稿编辑器
右：AI 助手
```

问题：草稿列表长期占据主工作区，左栏没有承载用户最需要对照的原文内容。标题候选和标签候选现在被放在编辑区 extras，与 AI 助手职责混在一起。

### 2.3 标签候选不可采纳

标题候选可以点击覆盖标题，但标签候选只是展示 `Tag`，点击没有行为。用户期望像标题候选一样，点一下就把标签加入正文。

此外，当前编辑器中的已有标签使用 `closable`，但没有 `onClose` 更新状态，属于交互假象。

### 2.4 草稿图片不能直接编辑

当前草稿图片只是资产列表，没有成为草稿工坊中的一等编辑对象。用户希望在草稿工坊就能直接：

- 添加图片；
- 删除图片；
- 编辑图片；
- 编辑时输入提示词，基于原图调用图生图 API。

现有系统已有图生图能力：`startImageGenerationTask` 支持 `reference_images`，后端 RunningHub 图生图支持本地媒体参考图。因此第一版应复用现有 AI 图片接口，不新接 Provider。

## 3. 用户目标

用户应能完成：

1. 从内容库加入草稿后，在草稿工坊看到原文内容和原始素材。
2. 当前草稿中有独立的图片素材区。
3. 草稿图片可以添加、删除。
4. 点击某张图片“编辑”，输入提示词后基于该图生成新图。
5. AI 编辑结果作为新图片加入草稿图片素材区，原图保留。
6. 如果不需要原图，用户可删除原图草稿资产。
7. 草稿图片允许删到 0 张。
8. 送入图片工坊后，所有可用草稿图片都会作为候选图出现。
9. 标签候选点击后加入正文 hashtag，并同步加入草稿 tags。
10. 标题候选、标签候选、改写候选集中在 AI 助手区。

## 4. 非目标

本轮不做：

- 不新增图片版本表或复杂图片任务表。
- 不做草稿工坊和图片工坊双向同步。
- 不真实发布小红书内容。
- 不修改 `apis/`、`xhs_utils/`、`static/` 底层 XHS SDK/签名层。
- 不实现风控绕过、验证码绕过、高频自动化。
- 不删除内容库原始素材；删除只影响当前草稿资产副本。
- 不要求草稿图片必须至少 1 张；发布中心前再校验最终发布图片。

## 5. 数据与接口设计

### 5.1 前端统一草稿图片 URL resolver

新增或抽取 helper：

```ts
function draftAssetImageUrl(asset: DraftAsset): string {
  if (asset.asset_type !== "image") return "";
  if (isUsableImageUrl(asset.url)) return asset.url;
  if (isUsableImageUrl(asset.local_path)) return asset.local_path;
  if (asset.local_path) return `/api/files/media/${asset.local_path.replace(/^\/api\/files\/media\//, "")}`;
  return "";
}
```

使用位置：

- 草稿工坊图片预览；
- `draftAssetToCandidate`；
- 草稿图片编辑参考图；
- 送入图片工坊上下文；
- 图片工坊最终发布候选判断。

### 5.2 后端草稿资产本地化接口

为图生图稳定性新增接口：

```text
POST /drafts/{draft_id}/assets/{asset_id}/localize
```

行为：

1. 校验 draft 属于当前用户。
2. 校验 asset 属于 draft。
3. 如果 asset.local_path 已存在，直接返回 `_serialize_draft_asset(asset)`。
4. 如果 asset.url 是 `http(s)`，使用 `download_asset_to_local(url, user_id, "image", platform="xhs")` 下载到本地 media。
5. 写回 `asset.local_path`。
6. 返回序列化资产。
7. 下载失败返回 400，并提示“图片本地化失败，请先上传本地图或更换图片”。

原因：后端 RunningHub 图生图解析参考图时要求本地 media 路径。外链参考图不应直接传给图生图。

### 5.3 草稿图片添加

复用现有接口：

```text
POST /drafts/{draft_id}/assets
```

支持：

- URL 添加：`{ asset_type: "image", url }`
- 上传添加：先 `uploadAssetFile(file)`，再 `{ asset_type: "image", local_path }`

前端需要把 `/api/files/media/<file>` 转成后端期望的纯 `local_path` 文件名。

### 5.4 草稿图片删除

复用现有接口：

```text
DELETE /drafts/{draft_id}/assets/{asset_id}
```

删除只影响草稿资产，不删除来源笔记素材，不删除媒体文件。

### 5.5 草稿图片 AI 编辑

流程：

```text
用户点击某张草稿图“编辑”
  → 打开弹窗
  → 展示原图
  → 输入提示词
  → ensureLocalDraftAsset(asset)
  → startImageGenerationTask({
       prompt,
       reference_images: [localizedAsset.url],
       save_to_assets: true,
       aspect_ratio
     })
  → 轮询 fetchTask(task_id)
  → 成功后得到 result.asset.file_path
  → addDraftAsset(draft_id, {
       asset_type: "image",
       local_path: fileNameFrom(result.asset.file_path)
     })
  → 刷新草稿图片列表
```

生成结果永远新增为新草稿图片。原图保留，用户可手动删除。

## 6. 草稿工坊布局设计

### 6.1 总体布局

改为：

```text
顶部：草稿选择器 / 折叠草稿列表

主体三栏：
左：原文内容
中：草稿编辑器 + 草稿图片素材区
右：AI 助手
```

### 6.2 顶部草稿选择器

默认只显示当前草稿：

```text
当前草稿：浴缸案例 A版     [切换草稿]
```

点击“切换草稿”后展开 Drawer 或 Popover 列表：

- 草稿名；
- 创建时间；
- 来源摘要；
- 点击切换。

草稿列表不再常驻左栏。

### 6.3 左侧原文内容

展示：

- 来源笔记标题；
- 原文正文；
- 来源链接；
- 原始图片素材预览；
- 素材数量。

左侧是参考区，不直接编辑。

### 6.4 中间草稿编辑器

包含：

- 内部草稿名；
- 发布标题；
- 正文；
- 当前 tags；
- 草稿图片素材区；
- 保存 / 复制 / 删除 / 送入图片工坊 / 送发布中心。

当前 tags 支持删除。删除只是更新 controller.tags。

### 6.5 草稿图片素材区

每张图片卡片：

```text
[缩略图]
图片 #1
[编辑] [删除]
```

空状态：

```text
当前草稿暂无图片。可以添加图片，或用 AI 根据文案生成。
```

功能：

- 添加 URL；
- 上传图片；
- 删除图片；
- 编辑图片。

### 6.6 右侧 AI 助手

包含：

- 改写模式和指令；
- 生成标题；
- 生成标签；
- 标题候选；
- 标签候选；
- 改写候选。

标题候选点击：覆盖当前标题。

标签候选点击：

1. 若 tags 中不存在该标签，则加入 tags。
2. 若正文中没有 `#标签`，追加到正文末尾。
3. 不重复追加。

正文追加规则：

```text
正文为空：
#浴缸 #小户型浴缸

正文非空：
原正文

#浴缸 #小户型浴缸
```

## 7. 送入图片工坊规则

点击“送入图片工坊”：

1. 保存草稿标题、正文、tags。
2. 重新拉取 `fetchDraftAssets(saved.id)`。
3. 使用 `draftAssetImageUrl` 得到所有可用图片。
4. 写入 `candidate_images`。
5. 跳转图片工坊。

如果候选图为 0：不阻断，提示可上传或生成图片。

图片工坊应显示：

- 当前草稿；
- 候选图；
- 默认把第一张候选图加入最终发布图片；
- 参考图可自动填入。

## 8. 错误处理

### 8.1 本地化失败

提示：

```text
图片本地化失败，请先上传本地图或更换图片。
```

不删除原图，不创建新图。

### 8.2 图生图失败

提示后保留弹窗和提示词，允许用户重试。

### 8.3 删除到 0 张

允许。显示空状态。送图片工坊不阻断；送发布中心前仍要求最终发布图片。

### 8.4 sessionStorage 失败

沿用现有错误：

```text
草稿已保存，但浏览器无法暂存图片工坊上下文。请检查隐私模式或浏览器存储权限后重试。
```

## 9. 测试与验证标准

### 9.1 后端测试

新增/更新：

1. `POST /drafts/{draft_id}/assets/{asset_id}/localize` 对已有 `local_path` 幂等返回。
2. 对外链 `url` 下载成功后写回 `local_path`。
3. 下载失败返回 400。
4. 不允许本地化非本人草稿资产。
5. 删除草稿资产只删除草稿资产，不删除来源 note asset。

### 9.2 前端测试或静态测试

新增/更新：

1. `draftAssetImageUrl` 支持 `url`、`/api/files/media`、纯 `local_path`。
2. `draftAssetToCandidate` 使用 resolver，不再只看 `asset.url`。
3. 标签候选点击会加入正文 hashtag，并同步 tags。
4. 草稿图片素材区存在添加、编辑、删除按钮。
5. 送图片工坊时使用草稿图片候选。

### 9.3 手动验证

必须验证：

1. 内容库有图笔记加入草稿。
2. 草稿工坊左侧能看到原文和来源图。
3. 中间草稿图片区能看到图片。
4. 点击“送入图片工坊”后图片工坊有候选图。
5. 标签候选点击后正文增加 hashtag。
6. 删除原图后草稿图片可变为 0 张。
7. 上传/URL 添加图片成功。
8. 编辑图片成功后新增一张 AI 编辑图，原图仍在。
9. 删除原图后 AI 编辑图仍在。
10. 前端 build 通过。
11. 后端相关测试通过。

## 10. 安全边界

- 不触发真实发布。
- 图生图调用只在用户点击“编辑图片/生成”后发生。
- 不调用真实发布 Provider。
- 不改底层 XHS SDK/签名层。
- 不保存密钥、账号密码、Cookie、Token 到代码或文档。

## 11. 95% 把握门槛

进入开发前必须满足：

1. 已确认图片编辑默认新增，不替换。
2. 已确认原图可删除。
3. 已确认草稿图片允许删到 0 张。
4. 已确认最终发布图片仍在发布中心前校验，不在草稿阶段强制。
5. 已确认复用现有图生图接口，不新增 Provider。
6. 已定位关键文件：
   - `frontend/src/pages/platforms/xhs/xhs-draft-workbench.tsx`
   - `frontend/src/pages/platforms/xhs/xhs-image-studio-context.ts`
   - `frontend/src/components/image-studio/draft-image-studio-context.ts`
   - `frontend/src/components/draft-workbench/draft-workbench-shell.tsx`
   - `frontend/src/lib/api.ts`
   - `backend/app/api/drafts.py`
   - `backend/app/services/ai_service.py`
7. 已定义验证标准。

## 12. 交付判定

只有同时满足以下条件，才能报告完成：

1. 草稿资产图片能稳定进入图片工坊。
2. 草稿列表不再常驻占左栏。
3. 左栏展示原文内容和来源素材。
4. 标题候选和标签候选在 AI 助手区。
5. 标签候选点击后加入正文和 tags。
6. 草稿图片可添加、删除、编辑。
7. AI 编辑图新增为草稿资产，原图保留。
8. 原图可删除，草稿图片可为 0。
9. 测试和 build 通过。
10. 未触发真实发布。

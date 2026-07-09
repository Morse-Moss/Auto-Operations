# 小红书数据获取低风险数据源接口验证记录

## 1. 验证目标

本文件记录 `2026-07-06-xhs-data-acquisition-live-source-design.md` 阶段 0 的接口验证结果。

验证范围：

1. 笔记搜索。
2. 笔记榜单。
3. 笔记详情。
4. 关键词分析。

验证原则：

- 只读验证。
- 使用低频请求。
- 不批量抓取。
- 不绕过会员权限。
- 不写入业务库。
- 不暴露供应商名称给普通用户。
- 不保存 cookie、token、明文账号信息。

## 2. 总结论

当前可以进入正式开发，但范围必须受验证结果约束。

可进入开发：

- 笔记搜索链路。
- 基于笔记搜索结果创建候选笔记。
- 将 `desc` 映射为候选正文/文案字段。
- 将 `imageUrl` 映射为封面 URL。
- 将 `videoUrl` 保存为远程视频 URL，不自动下载。
- 将 `noteId` 作为去重主键之一。
- 沿用现有 `decrypt_huitun_ext_data` 解密函数。

暂不能直接开发，需要继续验证：

- 笔记榜单 connector。
- 笔记详情 connector。
- 关键词分析 connector。
- 批量详情补全。
- 榜单/详情/关键词分析字段映射。

## 3. 已验证：笔记搜索

状态：ready_for_phase_1_development

验证方式：

- 使用已登录浏览器会话打开灰豚红薯版页面。
- 通过 CDP Network 捕获页面请求。
- 捕获 endpoint：`https://xhsapi.huitun.com/note/searchV2`。
- 读取 response body。
- 使用现有 `decrypt_huitun_ext_data` 对 `extData` 解密。
- 检查解密后的列表字段。

接口信息：

| 验证项 | 结果 |
|---|---|
| endpoint key | `note.searchV2` |
| URL | `https://xhsapi.huitun.com/note/searchV2` |
| method | GET |
| 是否需要登录态 | 是 |
| 是否返回 JSON | 是 |
| 是否存在 extData | 是，字符串 |
| extData 是否可用现有函数解密 | 是 |
| 样本数量 | 10 条 |
| 是否能拿标题 | 是，`title` |
| 是否能拿正文/文案 | 是，`desc` |
| 是否能拿封面 URL | 是，`imageUrl` |
| 是否能拿视频 URL | 是，`videoUrl`，视频笔记存在 |
| 是否能拿原文链接或 note id | 是，`noteId` |
| 是否能拿指标 | 是，`like`、`coll`、`comm`、`share`、`read` 等 |
| 是否能识别权限限制 | 待补充失败样例；当前成功样本可用 |
| 低频请求是否正常 | 是，页面正常加载并返回数据 |
| 结论 | ready |

解密后单条样本字段包含：

```text
videoCpm
del
htPrice
pictureCpe
type
hotComm
sharedCount
tid
relatBrands
vP
picPrice
userSex
comm
read
like
author
fM
noteId
anchorId
fansFemale
topic
videoCpe
verifyType
anchorType
desc
coll
vidPrice
tagId
keyw
title
fansMale
duration
nick
isDeleted
verifyContent
videoUrl
imageUrl
participles
share
pP
include
stat
cost
headurl
advert
updateTime
fans
pictureCpm
vCpe
bbid
redId
cidP
ts
```

正文/文案样本：

```text
title: 硬控npc10秒

desc: 硬控npc10秒
#秦文玚 # #来杯好茶摇一摇 # #硬控npc10秒 # #崩坏星穹铁道 #
```

媒体样本：

```text
imageUrl: http://sns-img-hw.xhscdn.com/...
videoUrl: http://sns-video-v6.xhscdn.com/...
```

开发映射建议：

| 源字段 | 系统字段 |
|---|---|
| `noteId` | `data_acquisition_candidates.platform_note_id` / `Note.note_id` 去重依据 |
| `title` | `data_acquisition_candidates.title` / `Note.title` |
| `desc` | `data_acquisition_candidates.content_excerpt` / `Note.content` |
| `imageUrl` | `data_acquisition_candidates.cover_url` / `Note.cover_url` / `NoteAsset.url` |
| `videoUrl` | `Note.video_url` 或 `raw_json.videoUrl`，第一版不自动下载 |
| `nick` | `author_name` |
| `author` / `anchorId` | 作者外部标识，写入 `raw_json` 或后续作者字段 |
| `like` | `metrics_json.like_count` |
| `coll` | `metrics_json.collect_count` |
| `comm` | `metrics_json.comment_count` |
| `share` / `sharedCount` | `metrics_json.share_count` |
| `read` | `metrics_json.estimated_read_count` |
| `topic` / `keyw` / `participles` | `tags_json` 或 `raw_json` |
| `ts` | `publish_time`，需确认时间单位 |
| `updateTime` | `update_time`，需确认时间格式 |

开发注意事项：

- 不要把供应商名展示给普通用户。
- 不要保存明文 cookie/token。
- 不要自动访问小红书原文。
- 不要自动下载图片或视频。
- 不要把第三方分析结论伪装成原始评论或官方数据。
- `desc` 虽已验证存在，但正式实现必须容忍空值或截断。
- 图文笔记和视频笔记都要保留原始 `raw_json`，便于后续字段校准。

## 4. 部分验证：笔记榜单

状态：not_ready

已确认：

- 灰豚页面能展示笔记榜单。
- 页面可见标题、作者、发布时间、更新时间、标签、互动量、点赞数、收藏数、评论数、分享数、原文入口。
- 页面 DOM 中存在封面/媒体展示。

未通过点：

- 直接用浏览器 cookie 请求 `https://xhsapi.huitun.com/rank/hotNoteV2` 返回非成功状态。
- 返回样例：

```json
{
  "status": 2001,
  "message": "...",
  "extData": null,
  "encrypt": false,
  "counter": null
}
```

当前判断：

- 页面榜单能力存在，但 endpoint 复刻还缺少必要上下文、参数或权限条件。
- 不能基于当前结果直接开发榜单 connector。

进入开发前必须补齐：

- 能稳定捕获并复刻榜单 endpoint。
- 能解密或解析返回数据。
- 能确认榜单结果是否含 `desc`、`imageUrl`、`noteId`、指标字段。
- 能确认权限不足时的错误码和错误消息。

## 5. 未验证：笔记详情

状态：not_ready

当前未完成 endpoint 级验证。

进入开发前必须补齐：

- 详情 endpoint key。
- 请求 method 和必要参数。
- 是否返回 JSON。
- 是否使用 `extData`。
- 是否能拿更完整正文、图片列表、视频、阅读画像、评论分析、提及品牌/话题/商品、相似笔记等字段。
- 是否需要更高会员权限。
- 权限不足失败样例。

## 6. 未验证：关键词分析

状态：not_ready

当前未完成 endpoint 级验证。

进入开发前必须补齐：

- 关键词分析 endpoint key。
- 请求 method 和必要参数。
- 是否返回 JSON。
- 是否使用 `extData`。
- 是否能拿笔记总数、预估阅读、商业笔记、互动总量、相关笔记、相关热词、相关直播等字段。
- 是否需要更高会员权限。
- 权限不足失败样例。

## 7. 开发闸门

其他开发线程必须遵守：

1. 可以从 `note.searchV2` 开始做正式开发。
2. 第一阶段只做笔记搜索 → 候选笔记 → 用户确认入库的主链路骨架。
3. 榜单、详情、关键词分析必须继续留在验证阶段，不能混入第一阶段实现。
4. 所有普通用户 UI 不得出现“灰豚”、“huitun”、“extData”、“connector”、“内部接口”等字样。
5. 失败就失败，不自动切换小红书直连、不自动切换文件导入。
6. 现有小红书账号直连能力保留，只标记高风险，不删除。

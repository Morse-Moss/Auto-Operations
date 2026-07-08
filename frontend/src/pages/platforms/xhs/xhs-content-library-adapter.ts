import {
  CopyOutlined,
  DeleteOutlined,
  EditOutlined,
  FileAddOutlined,
  HeartOutlined,
  LinkOutlined,
  MessageOutlined,
  PictureOutlined,
  SaveOutlined,
  CloudSyncOutlined,
  PlayCircleOutlined,
  ShareAltOutlined,
  StarOutlined,
} from "@ant-design/icons";
import { Alert, Button, Card, Checkbox, Col, Descriptions, Image, message, Popconfirm, Row, Space, Spin, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import React from "react";

import type { ContentLibraryAdapter, ContentLibraryRenderContext } from "../../../components/content-library";
import {
  analyzeSavedNote,
  batchCreateDraftsFromNotes,
  batchTagNotes,
  createDraftFromNote,
  createTag,
  deleteSavedNote,
  downloadExportFile,
  exportSavedNotes,
  fetchFeishuConfig,
  fetchSavedNote,
  fetchSavedNoteAssets,
  fetchSavedNoteComments,
  fetchSavedNoteFilterOptions,
  fetchSavedNotes,
  fetchTags,
  createSavedNoteSourceImageImportScript,
  importSavedNoteSourceImages,
  localizeSavedNoteImages,
  pullXhsNotesFromFeishu,
  pushAllXhsNotesToFeishu,
  pushXhsNotesToFeishu,
} from "../../../lib/api";
import { formatShanghaiTime } from "../../../lib/time";
import type { NoteAsset, NoteComment, SavedNote } from "../../../types";

const { Text, Paragraph } = Typography;
const h = React.createElement;

type XhsNavigate = (path: string) => void;
const localizingImageNoteIds = new Set<number>();
const importingSourceImageNoteIds = new Set<number>();

function formatSavedTime(value: string): string {
  return formatShanghaiTime(value);
}

function getRawNoteType(note: SavedNote): string {
  const type = note.raw_json?.model_type ?? note.raw_json?.type;
  return typeof type === "string" ? type : "note";
}

function getNotePublishTime(note: SavedNote): string {
  const raw = note.raw_json ?? {};
  const data = raw.data && typeof raw.data === "object" ? raw.data as Record<string, unknown> : {};
  const items = Array.isArray(data.items) ? data.items : [];
  const item = items[0] && typeof items[0] === "object" ? items[0] as Record<string, unknown> : {};
  const card = item.note_card && typeof item.note_card === "object" ? item.note_card as Record<string, unknown> : {};
  const timestamp = card.time ?? card.create_time ?? card.last_update_time ?? raw.time ?? raw.create_time;
  if (timestamp) {
    const numeric = typeof timestamp === "number" ? timestamp : Number(timestamp);
    if (Number.isFinite(numeric) && numeric > 0) return new Date(numeric > 1e12 ? numeric : numeric * 1000).toLocaleDateString("zh-CN");
  }
  return "";
}

function getNoteUrl(note: SavedNote): string {
  const raw = note.raw_json ?? {};
  for (const key of ["note_url", "url", "share_url"]) {
    const value = raw[key];
    if (typeof value === "string" && value.startsWith("http")) return value;
  }
  const data = raw.data && typeof raw.data === "object" ? raw.data as Record<string, unknown> : {};
  const items = Array.isArray(data.items) ? data.items : [];
  const item = items[0] && typeof items[0] === "object" ? items[0] as Record<string, unknown> : {};
  const card = item.note_card && typeof item.note_card === "object" ? item.note_card as Record<string, unknown> : {};
  for (const object of [card, item]) {
    const xsecToken = object.xsec_token;
    if (typeof xsecToken === "string" && xsecToken) {
      const source = (typeof object.xsec_source === "string" ? object.xsec_source : "") || "pc_feed";
      return `https://www.xiaohongshu.com/explore/${note.note_id}?xsec_token=${xsecToken}&xsec_source=${source}`;
    }
    for (const key of ["note_url", "url", "share_url"]) {
      const value = object[key];
      if (typeof value === "string" && value.startsWith("http")) return value;
    }
  }
  return `https://www.xiaohongshu.com/explore/${note.note_id}`;
}

function getAuthorProfileUrl(note: SavedNote): string {
  const raw = note.raw_json ?? {};
  const directId = raw.author_id;
  if (typeof directId === "string" && directId) return `https://www.xiaohongshu.com/user/profile/${directId}`;
  const data = raw.data && typeof raw.data === "object" ? raw.data as Record<string, unknown> : {};
  const items = Array.isArray(data.items) ? data.items : [];
  const item = items[0] && typeof items[0] === "object" ? items[0] as Record<string, unknown> : {};
  const card = item.note_card && typeof item.note_card === "object" ? item.note_card as Record<string, unknown> : {};
  const user = card.user && typeof card.user === "object" ? card.user as Record<string, unknown> : {};
  const userId = user.user_id ?? user.id;
  if (typeof userId === "string" && userId) return `https://www.xiaohongshu.com/user/profile/${userId}`;
  return "";
}

function getNoteTags(note: SavedNote): string[] {
  const raw = note.raw_json ?? {};
  const directList = raw.tag_list ?? raw.tags;
  if (Array.isArray(directList) && directList.length > 0) {
    return directList.map((tag: unknown) => {
      if (typeof tag === "string") return tag;
      if (tag && typeof tag === "object" && "name" in (tag as Record<string, unknown>)) return String((tag as Record<string, unknown>).name);
      return "";
    }).filter(Boolean);
  }
  const data = raw.data && typeof raw.data === "object" ? raw.data as Record<string, unknown> : {};
  const items = Array.isArray(data.items) ? data.items : [];
  const item = items[0] && typeof items[0] === "object" ? items[0] as Record<string, unknown> : {};
  const card = item.note_card && typeof item.note_card === "object" ? item.note_card as Record<string, unknown> : {};
  const nestedList = card.tag_list;
  if (Array.isArray(nestedList) && nestedList.length > 0) {
    return nestedList.map((tag: unknown) => {
      if (typeof tag === "string") return tag;
      if (tag && typeof tag === "object" && "name" in (tag as Record<string, unknown>)) return String((tag as Record<string, unknown>).name);
      return "";
    }).filter(Boolean);
  }
  return [];
}

function getNoteEngagement(note: SavedNote): { likes: number; collects: number; comments: number; shares: number } {
  if (note.engagement_metrics) return note.engagement_metrics;
  const raw = note.raw_json ?? {};
  const likes = Number(raw.liked_count ?? raw.likes ?? 0);
  const collects = Number(raw.collected_count ?? raw.collects ?? 0);
  const comments = Number(raw.comment_count ?? raw.comments ?? 0);
  const shares = Number(raw.share_count ?? raw.shares ?? 0);
  if (likes || collects || comments || shares) return { likes, collects, comments, shares };
  const data = raw.data && typeof raw.data === "object" ? raw.data as Record<string, unknown> : {};
  const items = Array.isArray(data.items) ? data.items : [];
  const item = items[0] && typeof items[0] === "object" ? items[0] as Record<string, unknown> : {};
  const card = item.note_card && typeof item.note_card === "object" ? item.note_card as Record<string, unknown> : {};
  const info = card.interact_info && typeof card.interact_info === "object" ? card.interact_info as Record<string, unknown> : {};
  return {
    likes: Number(info.liked_count ?? 0),
    collects: Number(info.collected_count ?? 0),
    comments: Number(info.comment_count ?? 0),
    shares: Number(info.share_count ?? 0),
  };
}

function rawString(note: SavedNote, keys: string[]): string {
  for (const key of keys) {
    const value = note.raw_json?.[key];
    if (typeof value === "string" && value) return value;
  }
  return "";
}

function getSavedNoteCoverUrl(note: SavedNote): string {
  return note.cover_url || note.asset_urls?.[0] || rawString(note, ["cover_url", "image_url"]);
}

function renderAnalysisMarks(note: SavedNote, fontSize = 11) {
  if (!note.analysis_marks?.length) return null;
  return h("div", { style: { marginTop: 6 } },
    note.is_analysis_focus ? h(Tag, { color: "gold", style: { fontSize }, key: "focus" }, "重点") : null,
    note.analysis_marks.map((mark) => h(Tag, { key: mark, color: "blue", style: { fontSize } }, mark)),
  );
}

function renderSavedTags(note: SavedNote, fontSize = 11) {
  return note.tags?.length ? h("div", { style: { marginTop: 6 } }, note.tags.map((tag) => h(Tag, { key: tag.id, color: "blue", style: { fontSize } }, tag.name))) : null;
}

function renderSystemAnalysisTags(note: SavedNote, fontSize = 11) {
  const analysis = note.analysis_result;
  const tags = [
    analysis?.analysis_status ? h(Tag, { key: "analysis_status", color: analysis.analysis_status === "废弃" ? "red" : "blue", style: { fontSize } }, analysis.analysis_status) : null,
    analysis?.content_type ? h(Tag, { key: "content_type", style: { fontSize } }, analysis.content_type) : null,
    analysis?.reuse_value ? h(Tag, { key: "reuse_value", color: "green", style: { fontSize } }, analysis.reuse_value) : null,
    analysis?.reusable_models?.[0] ? h(Tag, { key: "reusable_model", color: "purple", style: { fontSize } }, analysis.reusable_models[0]) : null,
  ].filter(Boolean);
  return tags.length ? h("div", { style: { marginTop: 6 } }, tags) : null;
}

function ratingColor(rating?: string | null): string {
  if (!rating) return "default";
  if (rating.includes("爆款")) return "gold";
  if (rating.includes("优质")) return "green";
  if (rating.includes("普通")) return "blue";
  if (rating.includes("低表现")) return "red";
  return "default";
}

function formatScore(score: number): string {
  return Number.isInteger(score) ? String(score) : score.toFixed(1).replace(/\.0$/, "");
}

function renderSystemScoreRating(note: SavedNote, fontSize = 11) {
  const analysis = note.analysis_result;
  const score = analysis?.score;
  const hasScore = typeof score === "number" && Number.isFinite(score);
  if (!hasScore && !analysis?.rating) return null;
  return h("div", { style: { marginTop: 6 } },
    hasScore ? h(Tag, { key: "score", color: "gold", style: { fontSize } }, `评分 ${formatScore(score)}/10`) : null,
    analysis?.rating ? h(Tag, { key: "rating", color: ratingColor(analysis.rating), style: { fontSize } }, `评级 ${analysis.rating}`) : null,
  );
}

function createTableColumns(context: ContentLibraryRenderContext<SavedNote>): ColumnsType<SavedNote> {
  return [
    { title: "标题", dataIndex: "title", ellipsis: true, render: (title: string, note) => h("a", { onClick: () => void context.openDetail(note) }, title || "未命名") },
    { title: "作者", dataIndex: "author_name", width: 120 },
    {
      title: "互动",
      key: "engagement",
      width: 170,
      render: (_, note) => {
        const engagement = getNoteEngagement(note);
        return h(Space, { size: 6, wrap: true }, h("span", null, `赞 ${engagement.likes}`), h("span", null, `评 ${engagement.comments}`), h("span", null, `藏 ${engagement.collects}`));
      },
    },
    { title: "重点", key: "analysis_marks", width: 180, render: (_, note) => note.analysis_marks?.length ? h(Space, { size: 4, wrap: true }, note.is_analysis_focus ? h(Tag, { color: "gold", key: "focus" }, "重点") : null, note.analysis_marks.map((mark) => h(Tag, { key: mark, color: "blue" }, mark))) : h(Text, { type: "secondary" }, "-") },
    { title: "系统分析", key: "analysis_result", width: 220, render: (_, note) => note.analysis_result ? h(Space, { size: 4, wrap: true }, renderSystemAnalysisTags(note)) : h(Text, { type: "secondary" }, note.feishu_sync?.push_status === "dry_run" ? "Dry-run" : "未分析") },
    { title: "笔记 ID", dataIndex: "note_id", width: 140, ellipsis: true },
    { title: "保存时间", dataIndex: "created_at", width: 160, render: (value: string) => formatSavedTime(value) },
    { title: "标签", key: "tags", width: 180, render: (_, note) => note.tags?.length ? h(Space, { size: 4, wrap: true }, note.tags.map((tag) => h(Tag, { key: tag.id, color: "blue" }, tag.name))) : h(Text, { type: "secondary" }, "-") },
    { title: "操作", key: "actions", width: 80, render: (_, note) => h(Button, { type: "text", danger: true, icon: h(DeleteOutlined), size: "small", onClick: (event: React.MouseEvent) => { event.stopPropagation(); void context.deleteItem(note); } }) },
  ];
}

function renderCardGrid(context: ContentLibraryRenderContext<SavedNote>) {
  return h(Row, { gutter: [16, 16] }, context.controller.items.map((note) => {
    const cover = getSavedNoteCoverUrl(note);
    const kind = getRawNoteType(note);
    const publishTime = getNotePublishTime(note);
    const engagement = getNoteEngagement(note);
    return h(Col, { xs: 12, sm: 8, md: 6, lg: 4, xl: 4, key: note.id },
      h(Card, {
        hoverable: true,
        size: "small",
        style: { overflow: "hidden" },
        onClick: () => void context.openDetail(note),
        cover: h("div", { style: { position: "relative", background: "#262626" } },
          h(CheckboxWithStop, { checked: context.selectedItemIdSet.has(note.id), onToggle: () => context.toggleSelection(note.id) }),
          cover
            ? h("img", { src: cover, alt: note.title, referrerPolicy: "no-referrer", style: { width: "100%", aspectRatio: "1/1", objectFit: "cover", display: "block" } })
            : h("div", { style: { width: "100%", aspectRatio: "1/1", display: "flex", alignItems: "center", justifyContent: "center", color: "rgba(255,255,255,.2)", fontSize: 28 } }, h(PictureOutlined)),
          h(Tag, { color: kind.includes("video") ? "purple" : "blue", style: { position: "absolute", top: 8, right: 8 }, icon: kind.includes("video") ? h(PlayCircleOutlined) : h(PictureOutlined) }, kind.includes("video") ? "视频" : "图文"),
        ),
      },
      h(Card.Meta, {
        title: h(Text, { ellipsis: true, style: { fontSize: 13 } }, note.title || "未命名"),
        description: h(React.Fragment, null,
          h("div", null,
            h(Text, { type: "secondary", style: { fontSize: 12 } }, note.author_name),
            h(Text, { type: "secondary", style: { fontSize: 11, marginLeft: 6 } }, publishTime || formatSavedTime(note.created_at)),
          ),
          engagement.likes || engagement.collects || engagement.comments || engagement.shares
            ? h("div", { style: { marginTop: 4, display: "flex", gap: 8, fontSize: 11, color: "rgba(255,255,255,.45)" } },
                engagement.likes > 0 ? h("span", null, h(HeartOutlined), ` ${engagement.likes}`) : null,
                engagement.collects > 0 ? h("span", null, h(StarOutlined), ` ${engagement.collects}`) : null,
                engagement.comments > 0 ? h("span", null, h(MessageOutlined), ` ${engagement.comments}`) : null,
                engagement.shares > 0 ? h("span", null, h(ShareAltOutlined), ` ${engagement.shares}`) : null,
              )
            : null,
        ),
      }),
      renderSystemScoreRating(note),
      renderAnalysisMarks(note),
      renderSystemAnalysisTags(note),
      renderSavedTags(note),
    ));
  }));
}

function CheckboxWithStop({ checked, onToggle }: { checked: boolean; onToggle(): void }) {
  return h(Checkbox, {
    checked,
    onClick: (event: React.MouseEvent) => event.stopPropagation(),
    onChange: onToggle,
    style: { position: "absolute", top: 8, left: 8, zIndex: 2 },
  });
}

function renderTable(context: ContentLibraryRenderContext<SavedNote>) {
  return h(Card, { size: "small" },
    h(Table<SavedNote>, {
      columns: createTableColumns(context),
      dataSource: context.controller.items,
      rowKey: "id",
      size: "small",
      pagination: false,
      rowSelection: { selectedRowKeys: context.controller.selectedItemIds, onChange: (keys) => context.controller.setSelectedItemIds(keys as number[]) },
      onRow: (note) => ({ onClick: () => void context.openDetail(note), style: { cursor: "pointer" } }),
    }),
  );
}

function renderSystemAnalysisDetail(note: SavedNote) {
  const analysis = note.analysis_result;
  return h(Card, { size: "small", title: "系统分析结果", style: { marginBottom: 16, background: "#1f1f1f" } },
    h(Descriptions, { column: 1, size: "small" },
      h(Descriptions.Item, { label: "分析来源" }, analysis?.source || (analysis ? "system" : "-")),
      h(Descriptions.Item, { label: "飞书同步状态" }, note.feishu_sync?.push_status || "not_synced"),
      h(Descriptions.Item, { label: "回传状态" }, note.feishu_sync?.pull_status || "not_pulled"),
      h(Descriptions.Item, { label: "分析状态" }, analysis?.analysis_status || "未分析"),
      h(Descriptions.Item, { label: "评分" }, typeof analysis?.score === "number" ? `${formatScore(analysis.score)}/10` : "-"),
      h(Descriptions.Item, { label: "评级" }, analysis?.rating || "-"),
      h(Descriptions.Item, { label: "产品/主题对象" }, analysis?.subject_object || "-"),
      h(Descriptions.Item, { label: "内容类型" }, analysis?.content_type || "-"),
      h(Descriptions.Item, { label: "核心卖点/核心观点" }, analysis?.core_points || "-"),
      h(Descriptions.Item, { label: "目标人群" }, analysis?.target_audience || "-"),
      h(Descriptions.Item, { label: "内容钩子" }, analysis?.title_hook || "-"),
      h(Descriptions.Item, { label: "封面类型" }, analysis?.cover_type || "-"),
      h(Descriptions.Item, { label: "标题类型" }, analysis?.title_type || "-"),
      h(Descriptions.Item, { label: "笔记结构分析" }, analysis?.content_structure || "-"),
      h(Descriptions.Item, { label: "可复用模型" }, analysis?.reusable_models?.join("、") || "-"),
      h(Descriptions.Item, { label: "内容利用方式" }, analysis?.content_usage || analysis?.reuse_value || "-"),
      h(Descriptions.Item, { label: "搜索属性" }, analysis?.search_attribute || "-"),
      note.feishu_sync?.external_record_id ? h(Descriptions.Item, { label: "飞书记录" }, note.feishu_sync.external_record_id) : null,
      note.feishu_sync?.last_error ? h(Descriptions.Item, { label: "失败原因" }, note.feishu_sync.last_error) : null,
    ),
  );
}

function renderComments(controller: ContentLibraryRenderContext<SavedNote>["controller"]) {
  const topLevelComments = controller.comments.filter((comment) => !comment.parent_comment_id);
  const childComments = (parentId: string) => controller.comments.filter((comment) => comment.parent_comment_id === parentId);
  return h(React.Fragment, null,
    h(Button, { onClick: controller.toggleComments, style: { marginBottom: 8 } }, controller.isCommentsOpen ? "收起评论" : `查看评论 (${controller.commentsTotal})`),
    controller.isCommentsOpen ? h(Card, { size: "small", style: { background: "#1f1f1f" } },
      controller.commentsError ? h(Alert, { message: controller.commentsError, type: "error", showIcon: true, style: { marginBottom: 8 } }) : null,
      controller.isCommentsLoading ? h(Spin, { size: "small" }) : null,
      topLevelComments.length === 0 && !controller.isCommentsLoading ? h(Text, { type: "secondary" }, "暂无评论") : null,
      topLevelComments.map((comment) => renderComment(comment, childComments(comment.comment_id))),
      controller.comments.length < controller.commentsTotal ? h(Button, { size: "small", onClick: () => void controller.loadComments(controller.commentsPage + 1), loading: controller.isCommentsLoading }, "加载更多") : null,
    ) : null,
  );
}

function renderComment(comment: NoteComment, replies: NoteComment[]) {
  return h("div", { key: comment.comment_id, style: { marginBottom: 10, paddingBottom: 8, borderBottom: "1px solid #303030" } },
    h(Space, null, h(Text, { strong: true, style: { fontSize: 13 } }, comment.user_name), h(Text, { type: "secondary", style: { fontSize: 11 } }, `${comment.created_at_remote} · ${comment.like_count} likes`)),
    h("div", { style: { color: "rgba(255,255,255,.65)", fontSize: 13, marginTop: 2 } }, comment.content),
    replies.map((reply) => h("div", { key: reply.comment_id, style: { marginLeft: 20, marginTop: 4, paddingLeft: 8, borderLeft: "2px solid #303030" } },
      h(Space, null, h(Text, { strong: true, style: { fontSize: 12 } }, reply.user_name), h(Text, { type: "secondary", style: { fontSize: 11 } }, `${reply.like_count} likes`)),
      h("div", { style: { color: "rgba(255,255,255,.55)", fontSize: 12 } }, reply.content),
    )),
  );
}

function getActionErrorMessage(error: unknown): string {
  const responseData = typeof error === "object" && error !== null && "response" in error
    ? (error as { response?: { data?: unknown } }).response?.data
    : null;
  if (typeof responseData === "object" && responseData !== null && "detail" in responseData) {
    const detail = (responseData as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail) return detail;
  }
  return error instanceof Error ? error.message : "未知错误";
}

async function copyTextWithFallback(text: string): Promise<void> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return;
    }
  } catch {
    // Fall through to the textarea fallback below.
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "true");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  textarea.style.top = "0";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  const copied = document.execCommand("copy");
  document.body.removeChild(textarea);
  if (!copied) throw new Error("copy_failed");
}

function getAssetPreviewUrl(asset: NoteAsset): string {
  return asset.download_url || asset.url;
}

function renderSaveImagesButton(controller: ContentLibraryRenderContext<SavedNote>["controller"], selectedNote: SavedNote) {
  const imageAssets = controller.selectedAssets.filter((asset) => asset.asset_type === "image");
  if (!imageAssets.length) return null;
  const missingCount = imageAssets.filter((asset) => !asset.local_path).length;
  const isLoading = localizingImageNoteIds.has(selectedNote.id);

  async function saveImages() {
    localizingImageNoteIds.add(selectedNote.id);
    controller.setDetailActionMessage("正在保存图片到本地...");
    try {
      const result = await localizeSavedNoteImages(selectedNote.id);
      await controller.refreshSelectedItem();
      const summary = `图片保存完成：新增 ${result.downloaded_count} 张，已存在 ${result.skipped_count} 张，失败 ${result.failed_count} 张。`;
      localizingImageNoteIds.delete(selectedNote.id);
      controller.setDetailActionMessage(summary);
      if (result.failed_count > 0) {
        message.warning(summary);
      } else {
        message.success(summary);
      }
    } catch (error) {
      const errorMessage = `图片保存失败：${getActionErrorMessage(error)}`;
      localizingImageNoteIds.delete(selectedNote.id);
      controller.setDetailError(errorMessage);
      message.error(errorMessage);
    } finally {
      localizingImageNoteIds.delete(selectedNote.id);
    }
  }

  return h(Button, {
    icon: h(SaveOutlined),
    loading: isLoading,
    disabled: isLoading || missingCount === 0,
    onClick: () => void saveImages(),
    size: "small",
  }, missingCount ? `保存图片 (${missingCount})` : "图片已保存");
}

function renderImportSourceImagesButton(
  controller: ContentLibraryRenderContext<SavedNote>["controller"],
  selectedNote: SavedNote,
  noteUrl: string,
) {
  const isLoading = importingSourceImageNoteIds.has(selectedNote.id);
  const canImport = noteUrl.startsWith("http");

  async function copyPageImportScript() {
    const scriptPayload = await createSavedNoteSourceImageImportScript(selectedNote.id);
    await copyTextWithFallback(scriptPayload.script);
    const hint = "已复制当前页面导入脚本。打开作品链接后，在地址栏粘贴并回车，图片会自动保存到本系统。";
    controller.setDetailActionMessage(hint);
    message.success(hint);
  }

  async function importSourceImages() {
    if (!canImport) {
      const errorMessage = "缺少可访问的作品链接，无法补全原文图片。";
      controller.setDetailError(errorMessage);
      message.error(errorMessage);
      return;
    }
    importingSourceImageNoteIds.add(selectedNote.id);
    controller.setDetailActionMessage("正在补全原文图片...");
    try {
      const result = await importSavedNoteSourceImages(selectedNote.id, { source_url: noteUrl, download: true });
      await controller.refreshSelectedItem();
      if (result.total_source_image_count === 0) {
        await copyPageImportScript();
        return;
      }
      const summary = `原文图片补全完成：新增 ${result.imported_count} 张，已存在 ${result.skipped_count} 张，已保存 ${result.downloaded_count} 张，失败 ${result.failed_count} 张。`;
      controller.setDetailActionMessage(summary);
      if (result.failed_count > 0) {
        message.warning(summary);
      } else {
        message.success(summary);
      }
    } catch (error) {
      try {
        await copyPageImportScript();
      } catch (scriptError) {
        const errorMessage = `补全原文图片失败：${getActionErrorMessage(error)}；当前页面导入脚本复制失败：${getActionErrorMessage(scriptError)}`;
        controller.setDetailError(errorMessage);
        message.error(errorMessage);
      }
    } finally {
      importingSourceImageNoteIds.delete(selectedNote.id);
    }
  }

  return h(Button, {
    icon: h(PictureOutlined),
    loading: isLoading,
    disabled: isLoading || !canImport,
    onClick: () => void importSourceImages(),
    size: "small",
  }, "补全原文图片");
}

function renderSystemAnalysisButton(controller: ContentLibraryRenderContext<SavedNote>["controller"], selectedNote: SavedNote) {
  return h(SystemAnalysisButton, { controller, selectedNote });
}

function SystemAnalysisButton({
  controller,
  selectedNote,
}: {
  controller: ContentLibraryRenderContext<SavedNote>["controller"];
  selectedNote: SavedNote;
}) {
  const [isLoading, setIsLoading] = React.useState(false);
  const hasSystemAnalysis = selectedNote.analysis_result?.source === "system";
  async function analyze() {
    setIsLoading(true);
    controller.setDetailError(null);
    controller.setDetailActionMessage("正在调用系统模型分析这篇笔记，请保持页面打开…");
    const loadingMessage = message.loading("正在进行系统分析…", 0);
    try {
      const result = await analyzeSavedNote(selectedNote.id);
      await controller.refreshSelectedItem();
      await controller.refreshItems();
      await controller.refreshFilterOptions();
      const successMessage = `系统分析完成：${result.analysis_status || "已完成"}`;
      controller.setDetailActionMessage(successMessage);
      message.success(successMessage);
    } catch (error) {
      const errorMessage = `系统分析失败：${getActionErrorMessage(error)}`;
      controller.setDetailError(errorMessage);
      message.error(errorMessage);
    } finally {
      setIsLoading(false);
      loadingMessage();
    }
  }

  return h(Button, {
    icon: h(PlayCircleOutlined),
    type: hasSystemAnalysis ? "default" : "primary",
    loading: isLoading,
    disabled: isLoading,
    onClick: () => void analyze(),
    size: "small",
  }, hasSystemAnalysis ? "重新系统分析" : "系统分析");
}

function renderFeishuToolbar(context: { controller: ContentLibraryRenderContext<SavedNote>["controller"] }) {
  async function syncSelectedToFeishu() {
    const selectedIds = [...context.controller.selectedItemIds];
    if (!selectedIds.length) {
      context.controller.setBatchActionMessage("请先选择要同步到飞书的笔记。");
      return;
    }
    context.controller.setBatchActionMessage(`正在同步 ${selectedIds.length} 条笔记到飞书，请稍候…`);
    const loadingMessage = message.loading(`正在同步 ${selectedIds.length} 条笔记到飞书…`, 0);
    try {
      const result = await pushXhsNotesToFeishu({ note_ids: selectedIds, dry_run: false });
      const createdCount = result.created_count ?? result.records?.filter((record) => record.status === "created").length ?? 0;
      const successMessage = `同步到飞书完成：新增 ${createdCount} 条，更新 ${result.updated_count} 条，失败 ${result.failed_count} 条`;
      context.controller.setBatchActionMessage(successMessage);
      loadingMessage();
      message.success(successMessage);
      await context.controller.refreshItems();
      await context.controller.refreshFilterOptions();
    } catch (error) {
      const errorMessage = `同步到飞书失败：${getActionErrorMessage(error)}`;
      context.controller.setBatchActionMessage(errorMessage);
      loadingMessage();
      message.error(errorMessage);
    }
  }

  async function syncAllToFeishu() {
    context.controller.setBatchActionMessage("正在补齐飞书同步字段并推送全部笔记，请保持页面打开…");
    const loadingMessage = message.loading("正在补齐飞书同步字段并推送全部笔记…", 0);
    try {
      const result = await pushAllXhsNotesToFeishu({ dry_run: false, only_unsynced: false, batch_size: 10, overwrite_existing: true });
      const warningCount = result.records?.filter((record) => Boolean(record.warning)).length ?? 0;
      const successMessage = `全部同步完成：共 ${result.total_count ?? result.processed_count ?? 0} 条，新增 ${result.created_count ?? 0} 条，更新 ${result.updated_count} 条，失败 ${result.failed_count} 条${warningCount ? `，${warningCount} 条有警告` : ""}`;
      context.controller.setBatchActionMessage(successMessage);
      loadingMessage();
      if (result.failed_count > 0) {
        message.warning(successMessage);
      } else {
        message.success(successMessage);
      }
      await context.controller.refreshItems();
      await context.controller.refreshFilterOptions();
    } catch (error) {
      const errorMessage = `同步全部到飞书失败：${getActionErrorMessage(error)}`;
      context.controller.setBatchActionMessage(errorMessage);
      loadingMessage();
      message.error(errorMessage);
    }
  }

  async function openFeishuAnalysisBase() {
    try {
      const config = await fetchFeishuConfig();
      if (!config.bitable_url) {
        context.controller.setBatchActionMessage("还没有飞书分析表，请先到设置页创建飞书分析表。");
        message.warning("还没有飞书分析表，请先到设置页创建飞书分析表。");
        return;
      }
      window.open(config.bitable_url, "_blank", "noopener,noreferrer");
    } catch (error) {
      const errorMessage = `打开飞书分析表失败：${getActionErrorMessage(error)}`;
      context.controller.setBatchActionMessage(errorMessage);
      message.error(errorMessage);
    }
  }

  async function pullSelectedFromFeishu() {
    const selectedIds = [...context.controller.selectedItemIds];
    if (!selectedIds.length) {
      context.controller.setBatchActionMessage("请先选择要从飞书回传的笔记。");
      return;
    }
    await pullFromFeishu(selectedIds, `正在从飞书回传 ${selectedIds.length} 条分析结果，请稍候…`, `正在从飞书回传 ${selectedIds.length} 条分析结果…`);
  }

  async function pullAllFromFeishu() {
    await pullFromFeishu([], "正在从飞书回传全部分析结果，请稍候…", "正在从飞书回传全部分析结果…");
  }

  async function pullFromFeishu(noteIds: number[], pendingMessage: string, loadingText: string) {
    context.controller.setBatchActionMessage(pendingMessage);
    const loadingMessage = message.loading(loadingText, 0);
    try {
      const result = await pullXhsNotesFromFeishu({ note_ids: noteIds, dry_run: false });
      const successMessage = `从飞书回传完成：更新 ${result.updated_count} 条，未匹配 ${result.unmatched_count ?? 0} 条，失败 ${result.failed_count} 条`;
      context.controller.setBatchActionMessage(successMessage);
      loadingMessage();
      message.success(successMessage);
      await context.controller.refreshItems();
      await context.controller.refreshFilterOptions();
    } catch (error) {
      const errorMessage = `从飞书回传失败：${getActionErrorMessage(error)}`;
      context.controller.setBatchActionMessage(errorMessage);
      loadingMessage();
      message.error(errorMessage);
    }
  }

  const selectedCount = context.controller.selectedItemIds.length;
  return h(Space, { wrap: true },
    h(Button, { onClick: () => void openFeishuAnalysisBase() }, "打开飞书分析表"),
    h(Button, { icon: h(CloudSyncOutlined), type: "primary", onClick: () => void syncAllToFeishu() }, "补齐飞书同步"),
    h(Button, { icon: h(CloudSyncOutlined), disabled: !selectedCount, onClick: () => void syncSelectedToFeishu() }, selectedCount ? `同步 ${selectedCount} 条到飞书` : "同步到飞书"),
    h(Button, { onClick: () => void pullAllFromFeishu() }, "回传全部分析结果"),
    h(Button, { disabled: !selectedCount, onClick: () => void pullSelectedFromFeishu() }, selectedCount ? `回传 ${selectedCount} 条` : "从飞书回传"),
  );
}

function renderDetail({ controller, item: selectedNote }: Parameters<ContentLibraryAdapter<SavedNote>["renderDetail"]>[0]) {
  const noteUrl = getNoteUrl(selectedNote);
  const authorProfileUrl = getAuthorProfileUrl(selectedNote);
  const platformTags = getNoteTags(selectedNote);
  const engagement = getNoteEngagement(selectedNote);
  const publishTime = getNotePublishTime(selectedNote);
  return h(React.Fragment, null,
    h(Descriptions, { column: 1, size: "small", style: { marginBottom: 16 } },
      h(Descriptions.Item, { label: "作者" }, authorProfileUrl ? h(Typography.Link, { href: authorProfileUrl, target: "_blank", rel: "noreferrer" }, selectedNote.author_name || "未知") : (selectedNote.author_name || "未知")),
      h(Descriptions.Item, { label: "互动" }, `赞 ${engagement.likes} · 藏 ${engagement.collects} · 评 ${engagement.comments}`),
      h(Descriptions.Item, { label: "笔记 ID" }, selectedNote.note_id),
      h(Descriptions.Item, { label: "保存时间" }, formatSavedTime(selectedNote.created_at)),
      publishTime ? h(Descriptions.Item, { label: "发布时间" }, publishTime) : null,
      h(Descriptions.Item, { label: "作品链接" }, h(Typography.Link, { href: noteUrl, target: "_blank", rel: "noreferrer", style: { fontSize: 12, wordBreak: "break-all" } }, noteUrl)),
    ),
    platformTags.length > 0 ? h("div", { style: { marginBottom: 12 } }, platformTags.map((tag) => h(Tag, { key: tag, color: "blue" }, `#${tag}`))) : null,
    renderSystemAnalysisDetail(selectedNote),
    h(Button, { type: "link", icon: h(LinkOutlined), href: noteUrl, target: "_blank", rel: "noreferrer", style: { padding: 0, marginBottom: 16 } }, "查看原文"),
    h(Space, { wrap: true, style: { marginBottom: 16 } },
      h(Button, { icon: h(CopyOutlined), onClick: controller.copySelectedItem, size: "small" }, "复制内容"),
      renderSystemAnalysisButton(controller, selectedNote),
      h(Button, { icon: h(FileAddOutlined), onClick: controller.addToDrafts, loading: controller.isCreatingDraft, size: "small" }, "加入草稿工坊"),
      h(Button, { icon: h(EditOutlined), onClick: () => void controller.createDraft("rewrite"), loading: controller.isCreatingDraft, size: "small" }, "AI 改写"),
      renderImportSourceImagesButton(controller, selectedNote, noteUrl),
      h(Popconfirm, { title: "确定删除？", onConfirm: () => void controller.deleteItem(selectedNote) }, h(Button, { danger: true, icon: h(DeleteOutlined), size: "small" }, "删除")),
    ),
    controller.selectedAssets.length > 0 ? h("div", { style: { marginBottom: 16 } },
      h(Space, { style: { display: "flex", justifyContent: "space-between", marginBottom: 6 }, wrap: true },
        h(Text, { strong: true }, `素材 (${controller.selectedAssets.length})`),
        renderSaveImagesButton(controller, selectedNote),
      ),
      h(Image.PreviewGroup, null,
        h(Space, { size: 8, wrap: true }, controller.selectedAssets.map((asset) => asset.asset_type === "video"
          ? h("div", { key: asset.id, style: { width: 80, height: 80, background: "#262626", borderRadius: 6, display: "flex", alignItems: "center", justifyContent: "center" } }, h(Button, { type: "link", icon: h(PlayCircleOutlined), href: getAssetPreviewUrl(asset), target: "_blank", rel: "noreferrer" }, "视频"))
          : h(Image, { key: asset.id, src: getAssetPreviewUrl(asset), width: 80, height: 80, style: { objectFit: "cover", borderRadius: 6 }, referrerPolicy: "no-referrer" }),
        )),
      ),
    ) : null,
    h("div", { style: { marginBottom: 16 } },
      h(Text, { strong: true }, "正文"),
      h(Paragraph, { style: { marginTop: 4, color: "rgba(255,255,255,.65)", whiteSpace: "pre-wrap" } }, selectedNote.content || "暂无正文。"),
    ),
    renderComments(controller),
  );
}

export function createXhsContentLibraryAdapter(navigate: XhsNavigate): ContentLibraryAdapter<SavedNote> {
  return {
    platform: "xhs",
    pageTitle: "内容库",
    pageDescription: "保存的笔记素材，支持标签、筛选、批量操作和导出",
    defaultViewMode: "card",
    defaultSortBy: "latest",
    pageSize: 40,
    capabilities: {
      canCreateDraft: true,
      canBatchCreateDrafts: true,
      canDelete: true,
      canBatchDelete: true,
      canTag: true,
      canExport: true,
      canReadComments: true,
      canFilterFeishuAnalysis: true,
    },
    labels: {
      savedCountTitle: "已保存笔记",
      itemCountSuffix: "条",
      platformLabel: "XHS",
      filterPlaceholder: "标题、正文、作者",
      detailTitleFallback: "笔记详情",
      batchCreateDrafts: "批量加入草稿工坊",
      exportJson: "JSON",
      exportCsv: "CSV",
      downloadExport: "下载",
      batchDelete: "批量删除",
      clearSelection: "清空选择",
      selectCurrentPage: "选择当前页",
    },
    messages: {
      loadError: "内容库加载失败。",
      detailLoadError: "笔记详情加载失败。",
      copySuccess: "已复制标题和正文。",
      copyError: "复制失败。",
      draftCreateError: "草稿创建失败。",
      addToDraftsError: "加入草稿工坊失败。",
      deleteSuccess: "已删除笔记。",
      deleteError: "删除失败。",
      batchNoSelection: "请先选择笔记。",
      batchCreateDraftsSuccess: (count) => `已创建 ${count} 个改写草稿。`,
      batchCreateDraftsError: "批量创建草稿失败。",
      exportSuccess: (count) => `已导出 ${count} 条笔记。`,
      exportError: "导出失败。",
      batchDeleteSuccess: (count) => `已删除 ${count} 条笔记。`,
      batchDeletePartialFailure: (count) => `已删除 ${count} 条笔记，剩余笔记删除失败。`,
      batchDeleteError: "批量删除失败。",
      downloadSuccess: (fileName) => `已下载：${fileName}`,
      downloadError: "下载失败。",
      commentsLoadError: "评论加载失败。",
      tagRequired: "请选择一个标签。",
      tagBatchAddSuccess: (count) => `已添加标签 (${count})`,
      tagBatchRemoveSuccess: (count) => `已移除标签 (${count})`,
      tagBatchError: "批量标签操作失败。",
      tagUpdateError: "标签更新失败。",
      tagNameRequired: "请输入标签名称。",
      tagCreateError: "标签创建失败。",
      draftCreatedAndNavigate: (draftId) => `已创建草稿 #${draftId}，正在跳转...`,
      addedToDrafts: (draftId) => `已加入草稿工坊，草稿 #${draftId}。`,
    },
    sortOptions: [
      { value: "latest", label: "最新保存" },
      { value: "engagement", label: "综合互动" },
      { value: "likes", label: "最多点赞" },
      { value: "comments", label: "最多评论" },
      { value: "collects", label: "最多收藏" },
    ],
    filterOptions: {
      analysisStatus: ["未分析", "待分析", "分析中", "已完成", "分析完成", "废弃", "已废弃"].map((value) => ({ value, label: value })),
      coreProductService: [],
      contentType: [],
      reusableModel: [],
      contentUsage: [],
      searchAttribute: [],
    },
    loadFilterOptions: () => fetchSavedNoteFilterOptions("xhs"),
    emptyState: { description: "内容库还是空的", actionLabel: "去发现笔记", actionPath: "/platforms/xhs/discovery" },
    renderToolbarExtras: renderFeishuToolbar,
    loadItems: (filters) => fetchSavedNotes({ platform: "xhs", ...filters }),
    loadItem: (itemId) => fetchSavedNote(itemId),
    loadAssets: (itemId) => fetchSavedNoteAssets(itemId),
    loadComments: (itemId, page) => fetchSavedNoteComments(itemId, page),
    loadTags: fetchTags,
    createTag,
    batchTagItems: (payload) => batchTagNotes({ note_ids: payload.item_ids, tag_ids: payload.tag_ids, mode: payload.mode }),
    deleteItem: async (itemId) => { await deleteSavedNote(itemId); },
    batchCreateDrafts: (itemIds) => batchCreateDraftsFromNotes({ note_ids: itemIds, intent: "rewrite" }),
    createDraftFromItem: (item, intent) => createDraftFromNote({ platform: "xhs", source_note_id: item.id, intent }),
    onDraftCreated: (_item, _draft, intent) => {
      if (intent === "rewrite" || intent === "publish") {
        setTimeout(() => navigate("/platforms/xhs/drafts"), 600);
      }
    },
    exportItems: (itemIds, format) => exportSavedNotes({ note_ids: itemIds, format }),
    downloadExport: (exportFile) => downloadExportFile(exportFile.download_url, exportFile.file_name),
    getCopyText: (item) => `${item.title}\n\n${item.content}`.trim(),
    renderCardGrid,
    renderTable,
    renderDetail,
  };
}

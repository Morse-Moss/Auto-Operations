import { CloudSyncOutlined, DeleteOutlined, FileTextOutlined, LinkOutlined, MessageOutlined, ReadOutlined, StarFilled, StarOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Checkbox, Col, Descriptions, Image, List, message, Row, Select, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import React from "react";

import type {
  ContentLibraryAdapter,
  ContentLibraryDraftIntent,
  ContentLibraryRenderContext,
} from "../../components/content-library";
import {
  analyzeWechatOfficialHotspots,
  autoRefreshWechatOfficialContent,
  createWechatOfficialDraft,
  deleteWechatOfficialContentLibraryItem,
  downloadExportFile,
  exportWechatOfficialArticles,
  fetchWechatOfficialContentDetail,
  fetchWechatOfficialContentLibrary,
  pullWechatOfficialArticlesFromFeishu,
  pushWechatOfficialArticlesToFeishu,
  refreshWechatOfficialContentDetail,
  updateWechatOfficialRecommendation,
} from "../../lib/api";
import type {
  WechatOfficialArticleComment,
  WechatOfficialContentDetail,
  WechatOfficialContentLibraryItem,
} from "../../types";
import {
  mapWechatOfficialArticleToContentItem,
  mapWechatOfficialCommentToContentComment,
  mapWechatOfficialImageToContentAsset,
  wechatOfficialCurationTags,
  wechatOfficialDisplayTime,
  wechatOfficialPoolStatus,
  wechatOfficialReadStatusLabel,
  type WechatOfficialContentLibraryViewItem,
} from "./wechat-official-content-library-mapper";
import type { WechatOfficialDraftTemplate } from "./wechat-official-draft-templates";

const { Text, Paragraph } = Typography;
const h = React.createElement;

type WechatOfficialNavigate = (path: string) => void;

type CurationFilter = { id: number; name: string; color: string; param: "category" | "tag" | "is_favorite" | "read_status" | "detail_complete"; value: string | boolean };

const CURATION_FILTERS: CurationFilter[] = [
  { id: 1001, name: "私域增长", color: "cyan", param: "category", value: "私域增长" },
  { id: 1002, name: "行业观察", color: "cyan", param: "category", value: "行业观察" },
  { id: 1003, name: "案例拆解", color: "cyan", param: "category", value: "案例拆解" },
  { id: 2001, name: "案例", color: "geekblue", param: "tag", value: "案例" },
  { id: 2002, name: "转化", color: "geekblue", param: "tag", value: "转化" },
  { id: 2003, name: "趋势", color: "geekblue", param: "tag", value: "趋势" },
  { id: 3001, name: "已收藏", color: "gold", param: "is_favorite", value: true },
  { id: 3002, name: "已读", color: "green", param: "read_status", value: "read" },
  { id: 3003, name: "正文/图片完整", color: "green", param: "detail_complete", value: true },
  { id: 3004, name: "待补正文素材", color: "gold", param: "detail_complete", value: false },
];

function formatMetric(value: number | undefined | null): string {
  const numeric = Number(value ?? 0);
  if (numeric >= 10000) return `${(numeric / 10000).toFixed(numeric >= 100000 ? 0 : 1)}w`;
  return numeric.toLocaleString();
}

function poolStatusLabel(status?: string): string {
  const labels: Record<string, string> = {
    candidate: "候选",
    shortlisted: "已入库",
    analyzing: "拆解中",
    draft_ready: "草稿已生成",
    rejected: "已拒绝",
    archived: "已归档",
  };
  return labels[status || ""] || status || "候选";
}

function statusColor(status?: string): string {
  if (!status) return "default";
  if (["blocked", "expired", "invalid", "failed", "rejected"].includes(status)) return "red";
  if (["planned", "partial", "pending", "unknown", "analyzing"].includes(status)) return "gold";
  if (["available", "valid", "active", "succeeded", "completed", "shortlisted"].includes(status)) return "green";
  if (["draft_ready"].includes(status)) return "purple";
  return "default";
}

function lowFollowerLabel(article: WechatOfficialContentLibraryItem): string {
  const value = article.analysis?.low_follower_evidence;
  if (value === "manual") return "人工确认";
  if (value === "inferred") return "Redfox 推断";
  if (value === true) return "已有证据";
  if (value === false) return "无证据";
  return "未知";
}

function materialLabel(article: WechatOfficialContentLibraryItem): string {
  const analysis = article.analysis || {};
  if (analysis.pool_status === "draft_ready") return "草稿已生成";
  if (analysis.analysis_mode) return "已拆解";
  return "待补全";
}

function completenessLabel(article: WechatOfficialContentLibraryItem): string {
  const completeness = article.detail_status?.completeness;
  if (completeness === "complete") return "正文/图片完整";
  if (completeness === "partial") return "部分补全";
  return "待补正文素材";
}

function syncCount(result: { created_count?: number; updated_count: number; failed_count: number; unmatched_count?: number }): string {
  const created = result.created_count ?? 0;
  const unmatched = result.unmatched_count ?? 0;
  return `新增 ${created} / 更新 ${result.updated_count} / 未匹配 ${unmatched} / 失败 ${result.failed_count}`;
}

function actionError(error: unknown): string {
  return error instanceof Error ? error.message : "未知错误";
}

function renderFeishuToolbar(context: { controller: ContentLibraryRenderContext<WechatOfficialContentLibraryViewItem>["controller"] }) {
  const selectedIds = context.controller.selectedItemIds;
  const selectedFilter = CURATION_FILTERS.find((filter) => String(filter.id) === context.controller.selectedTagFilter);

  async function pushSelectedToFeishu() {
    if (!selectedIds.length) {
      context.controller.setBatchActionMessage("请先选择要推送飞书分析的公众号文章。");
      return;
    }
    context.controller.setBatchActionMessage(`正在推送 ${selectedIds.length} 篇公众号文章到飞书分析表…`);
    const loadingMessage = message.loading(`正在推送 ${selectedIds.length} 篇公众号文章到飞书…`, 0);
    try {
      const result = await pushWechatOfficialArticlesToFeishu({ article_ids: selectedIds, dry_run: false });
      const text = `公众号飞书分析推送完成：${syncCount(result)}`;
      context.controller.setBatchActionMessage(text);
      loadingMessage();
      message.success(text);
      await context.controller.refreshItems();
    } catch (error) {
      const text = `公众号飞书分析推送失败：${actionError(error)}`;
      context.controller.setBatchActionMessage(text);
      loadingMessage();
      message.error(text);
    }
  }

  async function pullSelectedFromFeishu() {
    if (!selectedIds.length) {
      context.controller.setBatchActionMessage("请先选择要回拉飞书标注的公众号文章。");
      return;
    }
    context.controller.setBatchActionMessage(`正在回拉 ${selectedIds.length} 篇公众号文章的飞书标注…`);
    const loadingMessage = message.loading(`正在回拉 ${selectedIds.length} 篇公众号文章的飞书标注…`, 0);
    try {
      const result = await pullWechatOfficialArticlesFromFeishu({ article_ids: selectedIds, dry_run: false });
      const text = `公众号飞书标注回拉完成：${syncCount(result)}`;
      context.controller.setBatchActionMessage(text);
      loadingMessage();
      message.success(text);
      await context.controller.refreshItems();
    } catch (error) {
      const text = `公众号飞书标注回拉失败：${actionError(error)}`;
      context.controller.setBatchActionMessage(text);
      loadingMessage();
      message.error(text);
    }
  }

  async function autoRefreshSelected() {
    if (!selectedIds.length) {
      context.controller.setBatchActionMessage("请先选择要自动补全的公众号文章。");
      return;
    }
    const loadingMessage = message.loading(`正在自动补全 ${selectedIds.length} 篇公众号文章…`, 0);
    try {
      const result = await autoRefreshWechatOfficialContent({ article_ids: selectedIds });
      const text = `自动补全完成：成功 ${result.refreshed_count} / 失败 ${result.failed_count}；已写入系统通知。`;
      context.controller.setBatchActionMessage(text);
      loadingMessage();
      message.success(text);
      await context.controller.refreshItems();
    } catch (error) {
      const text = `自动补全失败：${actionError(error)}`;
      context.controller.setBatchActionMessage(text);
      loadingMessage();
      message.error(text);
    }
  }

  return h(Space, { wrap: true },
    h(Select, {
      allowClear: true,
      placeholder: "运营筛选",
      value: context.controller.selectedTagFilter || undefined,
      onChange: (value: unknown) => {
        const selectedValue = typeof value === "string" ? value : "";
        context.controller.setSelectedTagFilter(selectedValue);
        const filter = CURATION_FILTERS.find((candidate) => String(candidate.id) === selectedValue);
        void context.controller.refreshItems({ page: 1, category: undefined, tag: undefined, is_favorite: undefined, read_status: undefined, detail_complete: undefined, ...(filter ? { [filter.param]: filter.value } : {}) });
      },
      style: { width: 180 },
      options: CURATION_FILTERS.map((filter) => ({ value: String(filter.id), label: filter.name })),
    }),
    selectedFilter ? h(Tag, { color: selectedFilter.color }, `当前：${selectedFilter.name}`) : null,
    h(Button, { disabled: !selectedIds.length, onClick: () => void autoRefreshSelected() }, selectedIds.length ? `自动补全 ${selectedIds.length} 篇` : "自动补全正文素材"),
    h(Button, { icon: h(CloudSyncOutlined), disabled: !selectedIds.length, onClick: () => void pushSelectedToFeishu() }, selectedIds.length ? `推送 ${selectedIds.length} 篇到飞书分析` : "推送飞书分析"),
    h(Button, { disabled: !selectedIds.length, onClick: () => void pullSelectedFromFeishu() }, selectedIds.length ? `回拉 ${selectedIds.length} 篇飞书标注` : "回拉飞书标注"),
  );
}

function createTableColumns(context: ContentLibraryRenderContext<WechatOfficialContentLibraryViewItem>): ColumnsType<WechatOfficialContentLibraryViewItem> {
  return [
    { title: "标题", dataIndex: "title", ellipsis: true, render: (title: string, item) => h("a", { onClick: () => void context.openDetail(item) }, title || "未命名") },
    { title: "公众号", dataIndex: "author_name", width: 140, ellipsis: true },
    { title: "阅读", key: "read", width: 100, render: (_, item) => formatMetric(item.article.latest_metric?.read_count) },
    { title: "状态", key: "status", width: 120, render: (_, item) => h(Tag, { color: statusColor(item.pool_status) }, poolStatusLabel(item.pool_status)) },
    { title: "素材", key: "material", width: 130, render: (_, item) => h(Tag, { color: item.article.detail_status?.is_complete ? "green" : "gold" }, completenessLabel(item.article)) },
    { title: "分类", key: "category", width: 130, render: (_, item) => item.article.analysis?.category ? h(Tag, { color: "cyan" }, String(item.article.analysis.category)) : h(Text, { type: "secondary" }, "未分类") },
    { title: "时间", dataIndex: "created_at", width: 160, ellipsis: true },
    { title: "操作", key: "actions", width: 80, render: (_, item) => h(Button, { type: "text", danger: true, icon: h(DeleteOutlined), size: "small", onClick: (event: React.MouseEvent) => { event.stopPropagation(); void context.deleteItem(item); } }) },
  ];
}

function renderCardGrid(context: ContentLibraryRenderContext<WechatOfficialContentLibraryViewItem>) {
  return h(Row, { gutter: [16, 16] }, context.controller.items.map((item) => {
    const article = item.article;
    return h(Col, { xs: 24, sm: 12, lg: 8, xl: 6, key: item.id },
      h(Card, {
        hoverable: true,
        size: "small",
        style: { height: "100%" },
        onClick: () => void context.openDetail(item),
        cover: h("div", { style: { position: "relative", background: "#262626" } },
          h(Checkbox, {
            checked: context.selectedItemIdSet.has(item.id),
            onClick: (event: React.MouseEvent) => event.stopPropagation(),
            onChange: () => context.toggleSelection(item.id),
            style: { position: "absolute", top: 8, left: 8, zIndex: 2 },
          }),
          item.cover_url
            ? h("img", { src: item.cover_url, alt: item.title, referrerPolicy: "no-referrer", style: { width: "100%", aspectRatio: "4 / 3", objectFit: "cover", display: "block" } })
            : h("div", { style: { width: "100%", aspectRatio: "4 / 3", display: "flex", alignItems: "center", justifyContent: "center", color: "rgba(255,255,255,.25)", fontSize: 28 } }, h(FileTextOutlined)),
          h(Tag, { color: "green", style: { position: "absolute", top: 8, right: 8 } }, "公众号"),
        ),
      },
      h(Card.Meta, {
        title: h(Text, { ellipsis: true, style: { fontSize: 13 } }, item.title),
        description: h(React.Fragment, null,
          h(Text, { type: "secondary", style: { fontSize: 12 } }, `${item.author_name}${article.publish_time_remote ? ` · ${article.publish_time_remote}` : ""}`),
          h("div", { style: { marginTop: 6, display: "flex", gap: 10, flexWrap: "wrap", fontSize: 12, color: "rgba(255,255,255,.55)" } },
            h("span", null, h(ReadOutlined), ` 阅读 ${formatMetric(article.latest_metric?.read_count)}`),
            h("span", null, article.analysis?.is_favorite ? h(StarFilled) : h(StarOutlined), article.analysis?.is_favorite ? " 已收藏" : ` 在看 ${formatMetric(article.latest_metric?.wow_count)}`),
            h("span", null, h(MessageOutlined), ` 评论 ${formatMetric(article.latest_metric?.comment_count)}`),
          ),
          h("div", { style: { marginTop: 6 } },
            h(Tag, { color: statusColor(item.pool_status) }, poolStatusLabel(item.pool_status)),
            h(Tag, null, lowFollowerLabel(article)),
            h(Tag, { color: "blue" }, materialLabel(article)),
          ),
          h(Paragraph, { type: "secondary", ellipsis: { rows: 2 }, style: { marginTop: 8, marginBottom: 0 } }, article.digest || article.article_url || "暂无摘要"),
        ),
      })));
  }));
}

function renderTable(context: ContentLibraryRenderContext<WechatOfficialContentLibraryViewItem>) {
  return h(Card, { size: "small" },
    h(Table<WechatOfficialContentLibraryViewItem>, {
      columns: createTableColumns(context),
      dataSource: context.controller.items,
      rowKey: "id",
      size: "small",
      pagination: false,
      rowSelection: { selectedRowKeys: context.controller.selectedItemIds, onChange: (keys) => context.controller.setSelectedItemIds(keys as number[]) },
      onRow: (item) => ({ onClick: () => void context.openDetail(item), style: { cursor: "pointer" } }),
    }),
  );
}

function renderDetail({ controller, item }: Parameters<ContentLibraryAdapter<WechatOfficialContentLibraryViewItem>["renderDetail"]>[0]) {
  const detail = item.detail;
  const article = detail?.article || item.article;
  const analysis = detail?.analysis || article.analysis || {};
  const status = wechatOfficialPoolStatus(article);

  const refreshDetail = async () => {
    controller.setDetailError(null);
    controller.setDetailActionMessage(null);
    try {
      const refreshed = await refreshWechatOfficialContentDetail(article.id);
      controller.replaceSelectedItem(mapWechatOfficialArticleToContentItem(refreshed.article, refreshed));
      await controller.refreshItems();
      controller.setDetailActionMessage("正文、图片和评论已补全；未上传素材、未同步公众号后台、未发布或群发。");
    } catch (error) {
      controller.setDetailError(error instanceof Error ? error.message : "补全正文与素材失败。");
    }
  };

  const updateCuration = async (patch: { category?: string | null; tags?: string[] | null; is_favorite?: boolean | null; read_status?: string | null }) => {
    controller.setDetailError(null);
    controller.setDetailActionMessage(null);
    try {
      const updated = await updateWechatOfficialRecommendation(article.id, patch);
      controller.replaceSelectedItem(mapWechatOfficialArticleToContentItem(updated, item.detail));
      await controller.refreshSelectedItem();
      await controller.refreshItems();
      controller.setDetailActionMessage("运营标记已更新。分类、标签、收藏和已读状态会进入内容库筛选。");
    } catch (error) {
      controller.setDetailError(error instanceof Error ? error.message : "运营标记更新失败。");
    }
  };

  const analyzeHotspots = async () => {
    controller.setDetailError(null);
    controller.setDetailActionMessage(null);
    try {
      await analyzeWechatOfficialHotspots(article.id, {});
      await controller.refreshSelectedItem();
      await controller.refreshItems();
      controller.setDetailActionMessage("爆点拆解已更新。若已配置默认文本模型则使用 AI，失败时自动回退模板拆解。");
    } catch (error) {
      controller.setDetailError(error instanceof Error ? error.message : "爆点拆解失败。");
    }
  };

  return h(Space, { direction: "vertical", size: 16, style: { width: "100%" } },
    h(Descriptions, { column: 1, size: "small", bordered: true },
      h(Descriptions.Item, { label: "标题" }, article.title),
      h(Descriptions.Item, { label: "公众号/作者" }, article.author_name || "未知"),
      h(Descriptions.Item, { label: "发布时间" }, article.publish_time_remote || "未知"),
      h(Descriptions.Item, { label: "链接" }, article.article_url || article.content_url ? h("a", { href: article.article_url || article.content_url, target: "_blank", rel: "noreferrer" }, article.article_url || article.content_url) : "无"),
      h(Descriptions.Item, { label: "指标" }, `阅读 ${detail?.latest_metric?.read_count ?? article.latest_metric?.read_count ?? 0} / 点赞 ${detail?.latest_metric?.like_count ?? article.latest_metric?.like_count ?? 0} / 在看 ${detail?.latest_metric?.wow_count ?? article.latest_metric?.wow_count ?? 0} / 评论 ${detail?.latest_metric?.comment_count ?? article.latest_metric?.comment_count ?? 0}`),
      h(Descriptions.Item, { label: "状态" }, h(Tag, { color: statusColor(status) }, poolStatusLabel(status))),
      h(Descriptions.Item, { label: "完整度" }, h(Tag, { color: article.detail_status?.is_complete ? "green" : "gold" }, completenessLabel(article))),
      h(Descriptions.Item, { label: "分类/标签" }, h(Space, { wrap: true },
        article.analysis?.category ? h(Tag, { color: "cyan" }, String(article.analysis.category)) : h(Text, { type: "secondary" }, "未分类"),
        ...(article.analysis?.tags || []).map((tag) => h(Tag, { color: "geekblue", key: tag }, tag)),
        h(Tag, { color: article.analysis?.is_favorite ? "gold" : "default" }, article.analysis?.is_favorite ? "已收藏" : "未收藏"),
        h(Tag, { color: article.analysis?.read_status === "read" ? "green" : "default" }, wechatOfficialReadStatusLabel(article.analysis?.read_status)),
      )),
    ),
    h(Card, { size: "small", title: "运营标记" },
      h(Space, { direction: "vertical", style: { width: "100%" } },
        h(Space, { wrap: true },
          h(Select, {
            placeholder: "分类",
            value: article.analysis?.category || undefined,
            allowClear: true,
            style: { width: 160 },
            options: ["私域增长", "行业观察", "案例拆解", "方法论", "转化路径"].map((value) => ({ value, label: value })),
            onChange: (value: unknown) => void updateCuration({ category: typeof value === "string" ? value : null }),
          }),
          h(Select, {
            mode: "tags",
            placeholder: "标签",
            value: article.analysis?.tags || [],
            style: { minWidth: 240 },
            options: ["案例", "转化", "趋势", "标题", "结构", "素材"].map((value) => ({ value, label: value })),
            onChange: (value: unknown) => void updateCuration({ tags: Array.isArray(value) ? value.map(String) : [] }),
          }),
          h(Select, {
            value: article.analysis?.read_status || "unread",
            style: { width: 120 },
            options: [{ value: "unread", label: "未读" }, { value: "reading", label: "在读" }, { value: "read", label: "已读" }],
            onChange: (value: unknown) => void updateCuration({ read_status: typeof value === "string" ? value : "unread" }),
          }),
          h(Button, { icon: article.analysis?.is_favorite ? h(StarFilled) : h(StarOutlined), onClick: () => void updateCuration({ is_favorite: !article.analysis?.is_favorite }) }, article.analysis?.is_favorite ? "取消收藏" : "收藏"),
        ),
        h(Text, { type: "secondary" }, "这些标记只影响本地内容运营筛选，不会同步公众号后台、发布或群发。"),
      ),
    ),
    h(Space, { wrap: true },
      item.article.article_url ? h(Button, { icon: h(LinkOutlined), href: item.article.article_url, target: "_blank", rel: "noreferrer" }, "原文") : null,
      h(Button, { onClick: () => void refreshDetail() }, "补全正文与素材"),
      h(Button, { onClick: () => void analyzeHotspots() }, "拆解爆点"),
      h(Button, { type: "primary", loading: controller.isCreatingDraft, onClick: () => void controller.createDraft("rewrite") }, "生成公众号草稿"),
      h(Button, { danger: true, icon: h(DeleteOutlined), onClick: () => void controller.deleteItem(item) }, "删除"),
    ),
    h(Alert, {
      showIcon: true,
      type: "info",
      message: "补全正文与素材会调用 Redfox 并写入本地正文、图片、评论和指标；不会上传素材、同步公众号后台、发布或群发。",
    }),
    h(Card, { size: "small", title: "正文图片" },
      detail?.images?.length
        ? h(Image.PreviewGroup, null,
            h(Row, { gutter: [12, 12] }, detail.images.map((image, index) => h(Col, { xs: 12, sm: 8, md: 6, key: `${image.url}-${index}` },
              h(Card, { size: "small", cover: h(Image, { src: image.url, alt: image.alt || article.title, referrerPolicy: "no-referrer", style: { aspectRatio: "1 / 1", objectFit: "cover" } }) },
                h(Tag, { color: image.type === "cover" ? "blue" : "default" }, image.type === "cover" ? "封面" : "正文图"),
              )))))
        : h(Text, { type: "secondary" }, "暂无封面或正文图片；可在原公众号工作台补全 Redfox 详情。"),
    ),
    h(Card, { size: "small", title: "正文内容" },
      h(Paragraph, { style: { whiteSpace: "pre-wrap" } }, detail?.latest_snapshot?.text || article.digest || "暂无正文；当前可能只完成了列表采集。"),
    ),
    h(Card, { size: "small", title: `评论区（${detail?.comments?.total ?? 0}）` },
      detail?.comments?.items?.length
        ? h(List<WechatOfficialArticleComment>, {
            size: "small",
            dataSource: detail.comments.items,
            renderItem: (comment: WechatOfficialArticleComment) => h(List.Item, null,
              h(Space, { direction: "vertical", size: 4, style: { width: "100%" } },
                h(Text, { strong: true }, `${comment.user_name || "匿名读者"} · 赞 ${comment.like_count ?? 0}`),
                h(Text, null, comment.content),
              )),
          })
        : h(Text, { type: "secondary" }, "暂无评论正文。不会伪造评论内容。"),
    ),
    h(Card, { size: "small", title: "爆点拆解" },
      h(Descriptions, { column: 1, size: "small" },
        h(Descriptions.Item, { label: "标题钩子" }, analysis.hotspot_breakdown?.hook || "待拆解"),
        h(Descriptions.Item, { label: "读者痛点" }, analysis.hotspot_breakdown?.pain_point || "待拆解"),
        h(Descriptions.Item, { label: "内容承诺" }, analysis.hotspot_breakdown?.promise || "待拆解"),
        h(Descriptions.Item, { label: "可信证据" }, analysis.hotspot_breakdown?.credibility || "待拆解"),
        h(Descriptions.Item, { label: "结构路径" }, analysis.hotspot_breakdown?.structure || "待拆解"),
        h(Descriptions.Item, { label: "二创角度" }, analysis.hotspot_breakdown?.reuse_angle || "待拆解"),
      ),
      h(Paragraph, { type: "secondary" }, `模式：${analysis.analysis_mode || "未拆解"}；核心洞察：${analysis.core_insight || "待补充"}`),
    ),
  );
}

export function createWechatOfficialContentLibraryAdapter(navigate: WechatOfficialNavigate, selectedTemplate: WechatOfficialDraftTemplate): ContentLibraryAdapter<WechatOfficialContentLibraryViewItem> {
  return {
    platform: "wechat_official",
    pageTitle: "公众号内容库",
    pageDescription: "复用共享内容库工作台管理公众号文章；真实发布、预览发送和群发继续阻断。",
    defaultViewMode: "card",
    defaultSortBy: "latest",
    pageSize: 20,
    capabilities: {
      canCreateDraft: true,
      canBatchCreateDrafts: false,
      canDelete: true,
      canBatchDelete: false,
      canTag: false,
      canExport: true,
      canReadComments: true,
      canFilterAssets: false,
      canFilterComments: false,
      canFilterFeishuAnalysis: false,
    },
    labels: {
      savedCountTitle: "公众号文章",
      itemCountSuffix: "篇",
      platformLabel: "公众号",
      filterPlaceholder: "搜索标题、摘要或公众号",
      detailTitleFallback: "公众号文章详情",
      batchCreateDrafts: "批量生成草稿",
      exportJson: "导出 JSON",
      exportCsv: "导出 CSV",
      downloadExport: "下载导出",
      batchDelete: "批量删除",
      clearSelection: "清空选择",
      selectCurrentPage: "选择当前页",
    },
    messages: {
      loadError: "公众号内容库加载失败。",
      detailLoadError: "公众号文章详情加载失败。",
      copySuccess: "文章摘要已复制。",
      copyError: "复制失败。",
      draftCreateError: "公众号草稿生成失败。",
      addToDraftsError: "加入公众号草稿失败。",
      deleteSuccess: "公众号文章已删除并加入黑名单。",
      deleteError: "公众号文章删除失败。",
      batchNoSelection: "请先选择公众号文章。",
      batchCreateDraftsSuccess: (count) => `已生成 ${count} 篇公众号草稿。`,
      batchCreateDraftsError: "批量生成草稿暂未开放。",
      exportSuccess: (count) => `已准备 ${count} 篇公众号文章导出。`,
      exportError: "公众号内容库导出失败。",
      batchDeleteSuccess: (count) => `已删除 ${count} 篇公众号文章。`,
      batchDeletePartialFailure: (count) => `已删除 ${count} 篇公众号文章，剩余文章删除失败。`,
      batchDeleteError: "批量删除暂未开放。",
      downloadSuccess: (fileName) => `已下载 ${fileName}`,
      downloadError: "公众号导出文件下载失败。",
      commentsLoadError: "评论加载失败。",
      tagRequired: "公众号内容库第一阶段不支持标签。",
      tagBatchAddSuccess: (count) => `已处理 ${count} 篇文章。`,
      tagBatchRemoveSuccess: (count) => `已处理 ${count} 篇文章。`,
      tagBatchError: "公众号内容库第一阶段不支持标签。",
      tagUpdateError: "公众号内容库第一阶段不支持标签。",
      tagNameRequired: "公众号内容库第一阶段不支持标签。",
      tagCreateError: "公众号内容库第一阶段不支持标签。",
      draftCreatedAndNavigate: (draftId) => `已生成公众号草稿 #${draftId}，正在打开草稿工坊。`,
      addedToDrafts: (draftId) => `已生成公众号草稿 #${draftId}。`,
    },
    sortOptions: [{ value: "latest", label: "最新收集" }],
    filterOptions: {
      contentType: ["观点评论", "案例拆解", "行业观察", "方法论", "访谈故事", "清单指南"].map((value) => ({ value, label: value })),
      reuseValue: ["选题参考", "标题钩子", "结构参考", "案例素材", "转化路径", "私域引导"].map((value) => ({ value, label: value })),
      reusableModel: ["观点反差模型", "案例证明模型", "问题解决模型", "清单方法模型", "趋势判断模型", "认知升级模型"].map((value) => ({ value, label: value })),
    },
    emptyState: {
      description: "暂无公众号内容。先到爆文发现收集候选文章。",
      actionLabel: "去爆文发现",
      actionPath: "/platforms/wechat-official/discovery",
    },
    async loadItems(filters) {
      const response = await fetchWechatOfficialContentLibrary({
        keyword: filters.q,
        pool_status: "shortlisted",
        page: filters.page,
        page_size: filters.page_size,
      });
      return {
        total: response.total,
        page: response.page ?? filters.page ?? 1,
        page_size: response.page_size ?? filters.page_size ?? 20,
        items: response.items.map((article) => mapWechatOfficialArticleToContentItem(article)),
      };
    },
    async loadItem(itemId) {
      const detail = await fetchWechatOfficialContentDetail(itemId);
      return mapWechatOfficialArticleToContentItem(detail.article, detail);
    },
    async loadAssets(itemId) {
      const detail = await fetchWechatOfficialContentDetail(itemId);
      const items = (detail.images || []).map((image, index) => mapWechatOfficialImageToContentAsset(itemId, image, index));
      return { total: items.length, page: 1, page_size: items.length, items };
    },
    async loadComments(itemId, page) {
      const detail = await fetchWechatOfficialContentDetail(itemId);
      const all = (detail.comments?.items || []).map((comment, index) => mapWechatOfficialCommentToContentComment(itemId, comment, index));
      const pageSize = 20;
      const start = (page - 1) * pageSize;
      return { total: detail.comments?.total ?? all.length, page, page_size: pageSize, items: all.slice(start, start + pageSize) };
    },
    async loadTags() {
      return { total: 0, page: 1, page_size: 0, items: [] };
    },
    async createTag() {
      throw new Error("公众号内容库第一阶段不支持标签。");
    },
    async batchTagItems() {
      throw new Error("公众号内容库第一阶段不支持标签。");
    },
    async deleteItem(itemId) {
      await deleteWechatOfficialContentLibraryItem(itemId);
    },
    async batchCreateDrafts() {
      throw new Error("公众号内容库第一阶段不支持批量生成草稿。");
    },
    async createDraftFromItem(item, _intent: ContentLibraryDraftIntent) {
      const draft = await createWechatOfficialDraft(item.id, {
        ...selectedTemplate,
        opening_angle: item.detail?.analysis.hotspot_breakdown?.reuse_angle || item.article.analysis?.hotspot_breakdown?.reuse_angle || selectedTemplate.opening_angle,
      });
      return { id: draft.id };
    },
    onDraftCreated() {
      navigate("/platforms/wechat-official/drafts");
    },
    async exportItems(itemIds, format) {
      return exportWechatOfficialArticles({ article_ids: itemIds, format });
    },
    async downloadExport(exportFile) {
      await downloadExportFile(exportFile.download_url, exportFile.file_name);
    },
    getCopyText(item) {
      return [item.title, item.author_name, item.article.digest, item.detail?.latest_snapshot?.text].filter(Boolean).join("\n\n");
    },
    renderToolbarExtras: renderFeishuToolbar,
    renderCardGrid,
    renderTable,
    renderDetail,
  };
}

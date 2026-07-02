import React from "react";
import { Alert, Card, Descriptions, List, Row, Col, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";

import type {
  ContentLibraryAdapter,
  ContentLibraryAsset,
  ContentLibraryComment,
  ContentLibraryExportFormat,
  ContentLibraryExportResponse,
  ContentLibraryItem,
  ContentLibraryPage,
  ContentLibraryRenderContext,
  ContentLibraryTag,
  ContentLibraryTagMode,
} from "../../components/content-library";

const h = React.createElement;
const { Paragraph, Text } = Typography;

type DemoContentItem = ContentLibraryItem & {
  summary: string;
  readOnlyReason: string;
};

const demoItems: DemoContentItem[] = [
  {
    id: 1,
    platform: "demo_platform",
    title: "Demo read-only article",
    content: "This fixture proves the shared ContentLibrary shell can render a non-XHS platform without provider calls.",
    author_name: "Demo Source",
    created_at: "2026-07-01 10:00",
    tags: [{ id: 1, name: "Read-only", color: "blue" }],
    summary: "No account binding, no publish, no provider call.",
    readOnlyReason: "本地 fixture only；不连接真实平台。",
  },
  {
    id: 2,
    platform: "demo_platform",
    title: "Demo blocked write action",
    content: "Write actions are intentionally absent for this pilot.",
    author_name: "Demo Source",
    created_at: "2026-07-01 10:05",
    tags: [{ id: 2, name: "Fail closed", color: "red" }],
    summary: "The adapter exposes only read methods.",
    readOnlyReason: "写能力通过 capabilities 关闭，并由方法 fail closed。",
  },
];

const demoAssets: Record<number, ContentLibraryAsset[]> = {
  1: [
    {
      id: 101,
      note_id: 1,
      asset_type: "image",
      url: "demo://local-fixture/read-only-card.png",
      local_path: "",
      download_url: "",
      sort_order: 1,
    },
  ],
  2: [],
};

function readOnlyError(action: string): Error {
  return new Error(`Demo platform is read-only: ${action} is disabled.`);
}

function paginate<T>(items: T[], page = 1, pageSize = 20): ContentLibraryPage<T> {
  const start = (page - 1) * pageSize;
  return { total: items.length, page, page_size: pageSize, items: items.slice(start, start + pageSize) };
}

function renderTags(item: DemoContentItem) {
  return h(Space, { wrap: true }, (item.tags ?? []).map((tag) => h(Tag, { key: tag.id, color: tag.color || "blue" }, tag.name)));
}

function renderCardGrid(context: ContentLibraryRenderContext<DemoContentItem>) {
  return h(Row, { gutter: [16, 16] }, context.controller.items.map((item) => h(Col, { xs: 24, sm: 12, lg: 8, key: item.id },
    h(Card, {
      title: item.title,
      size: "small",
      extra: h("a", { onClick: () => void context.openDetail(item) }, "查看"),
    },
      h(Paragraph, { ellipsis: { rows: 2 } }, item.summary),
      renderTags(item),
      h(Text, { type: "secondary", style: { display: "block", marginTop: 8 } }, item.created_at),
    ),
  )));
}

function renderTable(context: ContentLibraryRenderContext<DemoContentItem>) {
  const columns: ColumnsType<DemoContentItem> = [
    { title: "标题", dataIndex: "title", render: (title: string, item) => h("a", { onClick: () => void context.openDetail(item) }, title) },
    { title: "来源", dataIndex: "author_name", width: 140 },
    { title: "摘要", dataIndex: "summary", ellipsis: true },
    { title: "标签", key: "tags", width: 180, render: (_, item) => renderTags(item) },
    { title: "时间", dataIndex: "created_at", width: 180 },
  ];
  return h(Table<DemoContentItem>, {
    rowKey: "id",
    size: "small",
    columns,
    dataSource: context.controller.items,
    pagination: false,
  });
}

export function createDemoPlatformContentLibraryAdapter(): ContentLibraryAdapter<DemoContentItem> {
  return {
    platform: "demo_platform",
    pageTitle: "Demo Platform 内容库",
    pageDescription: "只读本地 fixture，用来验证 Platform Core 可以承载非 XHS 平台；不会连接真实账号或 Provider。",
    defaultViewMode: "card",
    defaultSortBy: "latest",
    pageSize: 20,
    capabilities: {
      canCreateDraft: false,
      canBatchCreateDrafts: false,
      canDelete: false,
      canBatchDelete: false,
      canTag: false,
      canExport: false,
      canReadComments: true,
      canFilterAssets: false,
      canFilterComments: false,
      canFilterFeishuAnalysis: false,
    },
    labels: {
      savedCountTitle: "Demo 内容",
      itemCountSuffix: "条",
      platformLabel: "Demo",
      filterPlaceholder: "搜索 Demo 标题或内容",
      detailTitleFallback: "Demo 内容详情",
      batchCreateDrafts: "批量生成草稿",
      exportJson: "导出 JSON",
      exportCsv: "导出 CSV",
      downloadExport: "下载导出",
      batchDelete: "批量删除",
      clearSelection: "清空选择",
      selectCurrentPage: "选择当前页",
    },
    messages: {
      loadError: "Demo 内容库加载失败。",
      detailLoadError: "Demo 内容详情加载失败。",
      copySuccess: "Demo 内容已复制。",
      copyError: "复制 Demo 内容失败。",
      draftCreateError: "Demo 平台为只读，不能生成草稿。",
      addToDraftsError: "Demo 平台为只读，不能加入草稿。",
      deleteSuccess: "Demo 平台为只读，不会删除内容。",
      deleteError: "Demo 平台为只读，不能删除内容。",
      batchNoSelection: "请先选择 Demo 内容。",
      batchCreateDraftsSuccess: (count) => `Demo 平台为只读，未生成 ${count} 条草稿。`,
      batchCreateDraftsError: "Demo 平台为只读，不能批量生成草稿。",
      exportSuccess: (count) => `Demo 平台为只读，未导出 ${count} 条内容。`,
      exportError: "Demo 平台为只读，不能导出。",
      batchDeleteSuccess: (count) => `Demo 平台为只读，未删除 ${count} 条内容。`,
      batchDeletePartialFailure: (count) => `Demo 平台为只读，未删除 ${count} 条内容。`,
      batchDeleteError: "Demo 平台为只读，不能批量删除。",
      downloadSuccess: (fileName) => `Demo 平台为只读，未下载 ${fileName}。`,
      downloadError: "Demo 平台为只读，不能下载导出。",
      commentsLoadError: "Demo 评论加载失败。",
      tagRequired: "Demo 平台为只读，不能打标签。",
      tagBatchAddSuccess: (count) => `Demo 平台为只读，未给 ${count} 条内容打标签。`,
      tagBatchRemoveSuccess: (count) => `Demo 平台为只读，未给 ${count} 条内容移除标签。`,
      tagBatchError: "Demo 平台为只读，不能批量打标签。",
      tagUpdateError: "Demo 平台为只读，不能更新标签。",
      tagNameRequired: "Demo 平台为只读，不能创建标签。",
      tagCreateError: "Demo 平台为只读，不能创建标签。",
      draftCreatedAndNavigate: (draftId) => `Demo 平台为只读，未打开草稿 #${draftId}。`,
      addedToDrafts: (draftId) => `Demo 平台为只读，未加入草稿 #${draftId}。`,
    },
    sortOptions: [{ value: "latest", label: "最新 fixture" }],
    filterOptions: {},
    emptyState: {
      description: "暂无 Demo 内容。Demo 平台只使用本地 fixture，不请求外部平台。",
    },
    async loadItems(filters) {
      const keyword = (filters.q || "").trim().toLowerCase();
      const filtered = keyword
        ? demoItems.filter((item) => [item.title, item.content, item.author_name, item.summary].some((value) => value.toLowerCase().includes(keyword)))
        : demoItems;
      return paginate(filtered, filters.page ?? 1, filters.page_size ?? 20);
    },
    async loadItem(itemId) {
      const item = demoItems.find((candidate) => candidate.id === Number(itemId));
      if (!item) throw new Error("Demo item not found");
      return item;
    },
    async loadAssets(itemId) {
      return paginate(demoAssets[Number(itemId)] || [], 1, 20);
    },
    async loadComments(_itemId, page) {
      const comments: ContentLibraryComment[] = [];
      return paginate(comments, page, 20);
    },
    async loadTags() {
      return { total: 0, page: 1, page_size: 0, items: [] as ContentLibraryTag[] };
    },
    async createTag() {
      throw readOnlyError("createTag");
    },
    async batchTagItems(_payload: { item_ids: number[]; tag_ids: number[]; mode: ContentLibraryTagMode }) {
      throw readOnlyError("batchTagItems");
    },
    async deleteItem() {
      throw readOnlyError("deleteItem");
    },
    async batchCreateDrafts() {
      throw readOnlyError("batchCreateDrafts");
    },
    async createDraftFromItem() {
      throw readOnlyError("createDraftFromItem");
    },
    async exportItems(_itemIds: number[], _format: ContentLibraryExportFormat): Promise<ContentLibraryExportResponse> {
      throw readOnlyError("exportItems");
    },
    async downloadExport() {
      throw readOnlyError("downloadExport");
    },
    getCopyText(item) {
      return [item.title, item.author_name, item.summary, item.content].filter(Boolean).join("\n\n");
    },
    renderCardGrid,
    renderTable,
    renderDetail({ item }) {
      return h(Card, { size: "small" },
        h(Alert, {
          type: "info",
          showIcon: true,
          message: "只读 Demo 平台",
          description: "这个详情页只证明共享内容库 shell 可复用；没有真实账号、Provider、发布或自动化动作。",
          style: { marginBottom: 16 },
        }),
        h(Descriptions, { column: 1, bordered: true, size: "small" },
          h(Descriptions.Item, { label: "标题" }, item.title),
          h(Descriptions.Item, { label: "作者" }, item.author_name),
          h(Descriptions.Item, { label: "摘要" }, item.summary),
          h(Descriptions.Item, { label: "边界" }, h(Tag, { color: "red" }, "No write actions")),
        ),
        h(Paragraph, { style: { marginTop: 16 } }, item.content),
        h(Text, { type: "secondary" }, item.readOnlyReason),
        h(List, {
          size: "small",
          header: "Fixture 说明",
          dataSource: ["本地数组数据", "不读取账号/凭据", "不调用 provider/API", "不发布、不上传、不自动化"],
          renderItem: (text: unknown) => h(List.Item, null, String(text)),
          style: { marginTop: 16 },
        }),
      );
    },
  };
}

import type { ReactNode } from "react";

import type { NoteAsset, NoteComment, NotesExportResponse, PlatformId, SavedNote, Tag } from "../../types";

export type ContentLibraryItem = Pick<
  SavedNote,
  "id" | "platform" | "title" | "content" | "author_name" | "created_at" | "tags"
>;

export type ContentLibraryAsset = NoteAsset;
export type ContentLibraryComment = NoteComment;
export type ContentLibraryTag = Tag;
export type ContentLibraryExportResponse = NotesExportResponse;

export type ContentLibrarySortBy = "latest" | "engagement" | "likes" | "comments" | "collects";
export type ContentLibraryViewMode = "card" | "table";
export type ContentLibraryDraftIntent = "rewrite" | "publish";
export type ContentLibraryTagMode = "add" | "remove";
export type ContentLibraryExportFormat = "json" | "csv";

export type ContentLibraryVisibility = "active" | "all" | "excluded";

export type ContentLibraryFilters = {
  q?: string;
  tag_id?: number;
  has_assets?: boolean;
  has_comments?: boolean;
  visibility?: ContentLibraryVisibility;
  feishu_push_status?: string;
  analysis_status?: string;
  core_product_service?: string[];
  content_type?: string[];
  reusable_model?: string[];
  content_usage?: string[];
  search_attribute?: string[];
  category?: string;
  tag?: string;
  is_favorite?: boolean;
  read_status?: string;
  detail_complete?: boolean;
  sort_by?: ContentLibrarySortBy;
  page?: number;
  page_size?: number;
};

export type ContentLibraryPage<TItem = ContentLibraryItem> = {
  total: number;
  page: number;
  page_size: number;
  items: TItem[];
};

export type ContentLibrarySortOption = {
  value: ContentLibrarySortBy;
  label: string;
};

export type ContentLibrarySelectOption = {
  value: string;
  label: string;
};

export type ContentLibraryFilterOptions = {
  analysisStatus?: ContentLibrarySelectOption[];
  coreProductService?: ContentLibrarySelectOption[];
  contentType?: ContentLibrarySelectOption[];
  reuseValue?: ContentLibrarySelectOption[];
  reusableModel?: ContentLibrarySelectOption[];
  contentUsage?: ContentLibrarySelectOption[];
  searchAttribute?: ContentLibrarySelectOption[];
};

export type ContentLibraryCapabilities = {
  canCreateDraft: boolean;
  canBatchCreateDrafts: boolean;
  canDelete: boolean;
  canBatchDelete: boolean;
  canTag: boolean;
  canExport: boolean;
  canReadComments: boolean;
  canFilterAssets?: boolean;
  canFilterComments?: boolean;
  canFilterFeishuAnalysis?: boolean;
};

export type ContentLibraryEmptyState = {
  description: string;
  actionLabel?: string;
  actionPath?: string;
};

export type ContentLibraryLabels = {
  savedCountTitle: string;
  itemCountSuffix: string;
  platformLabel: string;
  filterPlaceholder: string;
  detailTitleFallback: string;
  batchCreateDrafts: string;
  exportJson: string;
  exportCsv: string;
  downloadExport: string;
  batchDelete: string;
  clearSelection: string;
  selectCurrentPage: string;
};

export type ContentLibraryMessages = {
  loadError: string;
  detailLoadError: string;
  copySuccess: string;
  copyError: string;
  draftCreateError: string;
  addToDraftsError: string;
  deleteSuccess: string;
  deleteError: string;
  batchNoSelection: string;
  batchCreateDraftsSuccess(count: number): string;
  batchCreateDraftsError: string;
  exportSuccess(count: number): string;
  exportError: string;
  batchDeleteSuccess(count: number): string;
  batchDeletePartialFailure(count: number): string;
  batchDeleteError: string;
  downloadSuccess(fileName: string): string;
  downloadError: string;
  commentsLoadError: string;
  tagRequired: string;
  tagBatchAddSuccess(count: number): string;
  tagBatchRemoveSuccess(count: number): string;
  tagBatchError: string;
  tagUpdateError: string;
  tagNameRequired: string;
  tagCreateError: string;
  draftCreatedAndNavigate(draftId: number): string;
  addedToDrafts(draftId: number): string;
};

export type ContentLibraryBatchTagResult<TItem extends ContentLibraryItem = ContentLibraryItem> = {
  updated_count: number;
  items: TItem[];
};

export type ContentLibraryBatchDraftResult = {
  created_count: number;
};

export type ContentLibraryDraftResult = {
  id: number;
};

export type ContentLibraryRenderContext<TItem extends ContentLibraryItem = ContentLibraryItem> = {
  controller: ContentLibraryController<TItem>;
  selectedItemIdSet: Set<number>;
  openDetail(item: TItem): Promise<void>;
  toggleSelection(itemId: number): void;
  deleteItem(item: TItem): Promise<void>;
};

export type ContentLibraryDetailRenderContext<TItem extends ContentLibraryItem = ContentLibraryItem> = {
  controller: ContentLibraryController<TItem>;
  item: TItem;
};

export type ContentLibraryToolbarRenderContext<TItem extends ContentLibraryItem = ContentLibraryItem> = {
  controller: ContentLibraryController<TItem>;
};

export type ContentLibraryBatchActionsRenderContext<TItem extends ContentLibraryItem = ContentLibraryItem> = {
  controller: ContentLibraryController<TItem>;
};

export type ContentLibraryAdapter<TItem extends ContentLibraryItem = ContentLibraryItem> = {
  platform: PlatformId;
  pageTitle: string;
  pageDescription: string;
  defaultViewMode: ContentLibraryViewMode;
  defaultSortBy: ContentLibrarySortBy;
  pageSize: number;
  capabilities: ContentLibraryCapabilities;
  labels: ContentLibraryLabels;
  messages: ContentLibraryMessages;
  sortOptions: ContentLibrarySortOption[];
  filterOptions?: ContentLibraryFilterOptions;
  emptyState: ContentLibraryEmptyState;
  loadFilterOptions?(filters?: Pick<ContentLibraryFilters, "visibility">): Promise<ContentLibraryFilterOptions>;
  loadItems(filters: ContentLibraryFilters): Promise<ContentLibraryPage<TItem>>;
  loadItem(itemId: number): Promise<TItem>;
  loadAssets(itemId: number): Promise<ContentLibraryPage<ContentLibraryAsset>>;
  loadComments(itemId: number, page: number): Promise<ContentLibraryPage<ContentLibraryComment>>;
  loadTags(): Promise<ContentLibraryPage<ContentLibraryTag>>;
  createTag(payload: { name: string; color?: string }): Promise<ContentLibraryTag>;
  batchTagItems(payload: { item_ids: number[]; tag_ids: number[]; mode: ContentLibraryTagMode }): Promise<ContentLibraryBatchTagResult<TItem>>;
  deleteItem(itemId: number): Promise<void>;
  batchCreateDrafts(itemIds: number[]): Promise<ContentLibraryBatchDraftResult>;
  createDraftFromItem(item: TItem, intent: ContentLibraryDraftIntent): Promise<ContentLibraryDraftResult>;
  onDraftCreated?(item: TItem, draft: ContentLibraryDraftResult, intent: ContentLibraryDraftIntent): void;
  exportItems(itemIds: number[], format: ContentLibraryExportFormat): Promise<ContentLibraryExportResponse>;
  downloadExport(exportFile: ContentLibraryExportResponse): Promise<void>;
  getCopyText(item: TItem): string;
  renderToolbarExtras?(context: ContentLibraryToolbarRenderContext<TItem>): ReactNode;
  renderBatchActions?(context: ContentLibraryBatchActionsRenderContext<TItem>): ReactNode;
  renderCardGrid(context: ContentLibraryRenderContext<TItem>): ReactNode;
  renderTable(context: ContentLibraryRenderContext<TItem>): ReactNode;
  renderDetail(context: ContentLibraryDetailRenderContext<TItem>): ReactNode;
};

export type ContentLibraryController<TItem extends ContentLibraryItem = ContentLibraryItem> = {
  items: TItem[];
  total: number;
  isLoading: boolean;
  error: string | null;
  selectedItem: TItem | null;
  selectedAssets: ContentLibraryAsset[];
  isDetailOpen: boolean;
  isDetailLoading: boolean;
  detailError: string | null;
  detailActionMessage: string | null;
  isCreatingDraft: boolean;
  availableTags: ContentLibraryTag[];
  newTagName: string;
  tagActionMessage: string | null;
  isCommentsOpen: boolean;
  comments: ContentLibraryComment[];
  commentsTotal: number;
  commentsPage: number;
  isCommentsLoading: boolean;
  commentsError: string | null;
  keywordFilter: string;
  selectedTagFilter: string;
  hasAssetsFilter: boolean;
  hasCommentsFilter: boolean;
  visibilityFilter: ContentLibraryVisibility;
  feishuPushStatusFilter: string;
  filterOptions: ContentLibraryFilterOptions;
  filterOptionsError: string | null;
  analysisStatusFilter: string;
  coreProductServiceFilter: string[];
  contentTypeFilter: string[];
  reusableModelFilter: string[];
  contentUsageFilter: string[];
  searchAttributeFilter: string[];
  sortBy: ContentLibrarySortBy;
  page: number;
  pageSize: number;
  viewMode: ContentLibraryViewMode;
  selectedItemIds: number[];
  selectedItemIdSet: Set<number>;
  batchTagId: string;
  batchActionMessage: string | null;
  isBatchWorking: boolean;
  latestExport: ContentLibraryExportResponse | null;
  setKeywordFilter(value: string): void;
  setSelectedTagFilter(value: string): void;
  setHasAssetsFilter(value: boolean): void;
  setHasCommentsFilter(value: boolean): void;
  setVisibilityFilter(value: ContentLibraryVisibility): void;
  setFeishuPushStatusFilter(value: string): void;
  setAnalysisStatusFilter(value: string): void;
  setCoreProductServiceFilter(value: string[]): void;
  setContentTypeFilter(value: string[]): void;
  setReusableModelFilter(value: string[]): void;
  setContentUsageFilter(value: string[]): void;
  setSearchAttributeFilter(value: string[]): void;
  setViewMode(value: ContentLibraryViewMode): void;
  setNewTagName(value: string): void;
  setBatchTagId(value: string): void;
  setBatchActionMessage(value: string | null): void;
  setDetailActionMessage(value: string | null): void;
  setDetailError(value: string | null): void;
  refreshItems(overrideFilters?: ContentLibraryFilters): Promise<void>;
  refreshTags(): Promise<void>;
  refreshFilterOptions(filters?: Pick<ContentLibraryFilters, "visibility">): Promise<void>;
  clearFilters(): void;
  handleSortChange(sortBy: ContentLibrarySortBy): void;
  handlePageChange(page: number, pageSize: number): void;
  toggleItemSelection(itemId: number): void;
  toggleVisibleSelection(): void;
  setSelectedItemIds(itemIds: number[]): void;
  clearSelection(): void;
  openDetail(item: TItem): Promise<void>;
  refreshSelectedItem(): Promise<TItem | null>;
  replaceSelectedItem(item: TItem): void;
  closeDetail(): void;
  copySelectedItem(): Promise<void>;
  createDraft(intent: ContentLibraryDraftIntent): Promise<void>;
  addToDrafts(): Promise<void>;
  deleteItem(item: TItem): Promise<void>;
  applyBatchTag(mode: ContentLibraryTagMode): Promise<void>;
  createBatchRewriteDrafts(): Promise<void>;
  exportSelectedItems(format: ContentLibraryExportFormat): Promise<void>;
  deleteSelectedItems(): Promise<void>;
  downloadLatestExport(): Promise<void>;
  selectedItemHasTag(tagId: number): boolean;
  toggleSelectedTag(tag: ContentLibraryTag): Promise<void>;
  createAndAssignTag(): Promise<void>;
  loadComments(page?: number): Promise<void>;
  toggleComments(): void;
};

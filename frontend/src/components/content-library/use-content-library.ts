import { Modal } from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";

import type {
  ContentLibraryAdapter,
  ContentLibraryAsset,
  ContentLibraryComment,
  ContentLibraryController,
  ContentLibraryDraftIntent,
  ContentLibraryExportFormat,
  ContentLibraryFilters,
  ContentLibraryItem,
  ContentLibraryVisibility,
  ContentLibraryTag,
  ContentLibraryTagMode,
} from "./content-library-types";

export function useContentLibrary<TItem extends ContentLibraryItem>(adapter: ContentLibraryAdapter<TItem>): ContentLibraryController<TItem> {
  const [items, setItems] = useState<TItem[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedItem, setSelectedItem] = useState<TItem | null>(null);
  const [selectedAssets, setSelectedAssets] = useState<ContentLibraryAsset[]>([]);
  const [isDetailOpen, setIsDetailOpen] = useState(false);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [detailActionMessage, setDetailActionMessage] = useState<string | null>(null);
  const [isCreatingDraft, setIsCreatingDraft] = useState(false);
  const [availableTags, setAvailableTags] = useState<ContentLibraryTag[]>([]);
  const [newTagName, setNewTagName] = useState("");
  const [tagActionMessage, setTagActionMessage] = useState<string | null>(null);
  const [isCommentsOpen, setIsCommentsOpen] = useState(false);
  const [comments, setComments] = useState<ContentLibraryComment[]>([]);
  const [commentsTotal, setCommentsTotal] = useState(0);
  const [commentsPage, setCommentsPage] = useState(1);
  const [isCommentsLoading, setIsCommentsLoading] = useState(false);
  const [commentsError, setCommentsError] = useState<string | null>(null);
  const [keywordFilter, setKeywordFilter] = useState("");
  const [selectedTagFilter, setSelectedTagFilter] = useState("");
  const [hasAssetsFilter, setHasAssetsFilter] = useState(false);
  const [hasCommentsFilter, setHasCommentsFilter] = useState(false);
  const [visibilityFilter, setVisibilityFilter] = useState<ContentLibraryVisibility>("active");
  const [feishuPushStatusFilter, setFeishuPushStatusFilter] = useState("");
  const [analysisStatusFilter, setAnalysisStatusFilter] = useState("");
  const [filterOptions, setFilterOptions] = useState(adapter.filterOptions ?? {});
  const [filterOptionsError, setFilterOptionsError] = useState<string | null>(null);
  const [coreProductServiceFilter, setCoreProductServiceFilter] = useState<string[]>([]);
  const [contentTypeFilter, setContentTypeFilter] = useState<string[]>([]);
  const [reusableModelFilter, setReusableModelFilter] = useState<string[]>([]);
  const [contentUsageFilter, setContentUsageFilter] = useState<string[]>([]);
  const [searchAttributeFilter, setSearchAttributeFilter] = useState<string[]>([]);
  const [sortBy, setSortBy] = useState(adapter.defaultSortBy);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(adapter.pageSize);
  const [viewMode, setViewMode] = useState(adapter.defaultViewMode);
  const [selectedItemIds, setSelectedItemIds] = useState<number[]>([]);
  const [batchTagId, setBatchTagId] = useState("");
  const [batchActionMessage, setBatchActionMessage] = useState<string | null>(null);
  const [isBatchWorking, setIsBatchWorking] = useState(false);
  const [latestExport, setLatestExport] = useState<ContentLibraryController<TItem>["latestExport"]>(null);

  const selectedItemIdSet = useMemo(() => new Set(selectedItemIds), [selectedItemIds]);

  const resetComments = useCallback(() => {
    setIsCommentsOpen(false);
    setComments([]);
    setCommentsTotal(0);
    setCommentsPage(1);
    setIsCommentsLoading(false);
    setCommentsError(null);
  }, []);

  const refreshItems = useCallback(async (overrideFilters?: ContentLibraryFilters) => {
    setIsLoading(true);
    setError(null);
    const filters: ContentLibraryFilters = {
      q: keywordFilter.trim() || undefined,
      tag_id: selectedTagFilter ? Number(selectedTagFilter) : undefined,
      has_assets: hasAssetsFilter || undefined,
      has_comments: hasCommentsFilter || undefined,
      visibility: visibilityFilter,
      feishu_push_status: feishuPushStatusFilter || undefined,
      analysis_status: analysisStatusFilter || undefined,
      core_product_service: coreProductServiceFilter.length ? coreProductServiceFilter : undefined,
      content_type: contentTypeFilter.length ? contentTypeFilter : undefined,
      reusable_model: reusableModelFilter.length ? reusableModelFilter : undefined,
      content_usage: contentUsageFilter.length ? contentUsageFilter : undefined,
      search_attribute: searchAttributeFilter.length ? searchAttributeFilter : undefined,
      sort_by: sortBy,
      page,
      page_size: pageSize,
      ...overrideFilters,
    };
    try {
      const result = await adapter.loadItems(filters);
      setItems(result.items);
      setTotal(result.total);
      setPage(result.page);
      setPageSize(result.page_size);
      const visibleIds = new Set(result.items.map((item) => item.id));
      setSelectedItemIds((current) => current.filter((id) => visibleIds.has(id)));
    } catch {
      setError(adapter.messages.loadError);
    } finally {
      setIsLoading(false);
    }
  }, [adapter, analysisStatusFilter, contentTypeFilter, contentUsageFilter, coreProductServiceFilter, feishuPushStatusFilter, hasAssetsFilter, hasCommentsFilter, keywordFilter, page, pageSize, reusableModelFilter, searchAttributeFilter, selectedTagFilter, sortBy, visibilityFilter]);

  const refreshTags = useCallback(async () => {
    try {
      const result = await adapter.loadTags();
      setAvailableTags(result.items);
    } catch {
      setAvailableTags([]);
    }
  }, [adapter]);

  const refreshFilterOptions = useCallback(async (overrideFilters?: Pick<ContentLibraryFilters, "visibility">) => {
    setFilterOptionsError(null);
    if (!adapter.loadFilterOptions) {
      setFilterOptions(adapter.filterOptions ?? {});
      return;
    }
    try {
      const result = await adapter.loadFilterOptions({ visibility: overrideFilters?.visibility ?? visibilityFilter });
      setFilterOptions(result);
    } catch {
      setFilterOptions(adapter.filterOptions ?? {});
      setFilterOptionsError("飞书分析筛选项加载失败，请刷新后重试。");
    }
  }, [adapter, visibilityFilter]);

  useEffect(() => {
    let cancelled = false;

    setKeywordFilter("");
    setSelectedTagFilter("");
    setHasAssetsFilter(false);
    setHasCommentsFilter(false);
    setVisibilityFilter("active");
    setFeishuPushStatusFilter("");
    setAnalysisStatusFilter("");
    setCoreProductServiceFilter([]);
    setContentTypeFilter([]);
    setReusableModelFilter([]);
    setContentUsageFilter([]);
    setSearchAttributeFilter([]);
    setSortBy(adapter.defaultSortBy);
    setPage(1);
    setPageSize(adapter.pageSize);
    setSelectedItemIds([]);
    setBatchActionMessage(null);
    resetComments();

    async function loadInitialItems() {
      setIsLoading(true);
      setError(null);
      try {
        const result = await adapter.loadItems({ sort_by: adapter.defaultSortBy, page: 1, page_size: adapter.pageSize });
        if (cancelled) return;
        setItems(result.items);
        setTotal(result.total);
        setPage(result.page);
        setPageSize(result.page_size);
        setSelectedItemIds([]);
      } catch {
        if (!cancelled) setError(adapter.messages.loadError);
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    async function loadInitialTags() {
      try {
        const result = await adapter.loadTags();
        if (!cancelled) setAvailableTags(result.items);
      } catch {
        if (!cancelled) setAvailableTags([]);
      }
    }

    async function loadInitialFilterOptions() {
      setFilterOptionsError(null);
      if (!adapter.loadFilterOptions) {
        setFilterOptions(adapter.filterOptions ?? {});
        return;
      }
      try {
        const result = await adapter.loadFilterOptions({ visibility: "active" });
        if (!cancelled) setFilterOptions(result);
      } catch {
        if (!cancelled) {
          setFilterOptions(adapter.filterOptions ?? {});
          setFilterOptionsError("飞书分析筛选项加载失败，请刷新后重试。");
        }
      }
    }

    void loadInitialItems();
    void loadInitialTags();
    void loadInitialFilterOptions();

    return () => {
      cancelled = true;
    };
  }, [adapter, resetComments]);

  const clearFilters = useCallback(() => {
    setKeywordFilter("");
    setSelectedTagFilter("");
    setHasAssetsFilter(false);
    setHasCommentsFilter(false);
    setVisibilityFilter("active");
    setFeishuPushStatusFilter("");
    setAnalysisStatusFilter("");
    setCoreProductServiceFilter([]);
    setContentTypeFilter([]);
    setReusableModelFilter([]);
    setContentUsageFilter([]);
    setSearchAttributeFilter([]);
    setPage(1);
    void refreshItems({ q: undefined, tag_id: undefined, has_assets: undefined, has_comments: undefined, visibility: "active", feishu_push_status: undefined, analysis_status: undefined, core_product_service: undefined, content_type: undefined, reusable_model: undefined, content_usage: undefined, search_attribute: undefined, page: 1 });
  }, [refreshItems]);

  const handleSortChange = useCallback((nextSortBy: ContentLibraryFilters["sort_by"]) => {
    if (!nextSortBy) return;
    setSortBy(nextSortBy);
    setPage(1);
    void refreshItems({ sort_by: nextSortBy, page: 1 });
  }, [refreshItems]);

  const handlePageChange = useCallback((nextPage: number, nextPageSize: number) => {
    setPage(nextPage);
    setPageSize(nextPageSize);
    void refreshItems({ page: nextPage, page_size: nextPageSize });
  }, [refreshItems]);

  const toggleItemSelection = useCallback((itemId: number) => {
    setSelectedItemIds((current) => current.includes(itemId) ? current.filter((id) => id !== itemId) : [...current, itemId]);
  }, []);

  const toggleVisibleSelection = useCallback(() => {
    if (!items.length) return;
    const visibleIds = items.map((item) => item.id);
    const allSelected = visibleIds.every((id) => selectedItemIdSet.has(id));
    setSelectedItemIds((current) => allSelected ? current.filter((id) => !visibleIds.includes(id)) : Array.from(new Set([...current, ...visibleIds])));
  }, [items, selectedItemIdSet]);

  const clearSelection = useCallback(() => {
    setSelectedItemIds([]);
    setBatchActionMessage(null);
  }, []);

  const openDetail = useCallback(async (item: TItem) => {
    setIsDetailOpen(true);
    setSelectedItem(item);
    setDetailError(null);
    setDetailActionMessage(null);
    setTagActionMessage(null);
    resetComments();
    setIsDetailLoading(true);
    try {
      const [detail, assets] = await Promise.all([adapter.loadItem(item.id), adapter.loadAssets(item.id)]);
      setSelectedItem(detail);
      setSelectedAssets(assets.items);
    } catch {
      setDetailError(adapter.messages.detailLoadError);
    } finally {
      setIsDetailLoading(false);
    }
  }, [adapter, resetComments]);

  const refreshSelectedItem = useCallback(async () => {
    if (!selectedItem) return null;
    setIsDetailLoading(true);
    setDetailError(null);
    try {
      const [detail, assets] = await Promise.all([adapter.loadItem(selectedItem.id), adapter.loadAssets(selectedItem.id)]);
      setSelectedItem(detail);
      setSelectedAssets(assets.items);
      setItems((current) => current.map((item) => item.id === detail.id ? detail : item));
      return detail;
    } catch {
      setDetailError(adapter.messages.detailLoadError);
      return null;
    } finally {
      setIsDetailLoading(false);
    }
  }, [adapter, selectedItem]);

  const replaceSelectedItem = useCallback((item: TItem) => {
    setSelectedItem(item);
    setItems((current) => current.map((entry) => entry.id === item.id ? item : entry));
  }, []);

  const closeDetail = useCallback(() => {
    setIsDetailOpen(false);
    setSelectedItem(null);
    setDetailError(null);
    setDetailActionMessage(null);
    setTagActionMessage(null);
    setSelectedAssets([]);
    resetComments();
  }, [resetComments]);

  const copySelectedItem = useCallback(async () => {
    if (!selectedItem) return;
    try {
      await navigator.clipboard.writeText(adapter.getCopyText(selectedItem));
      setDetailActionMessage(adapter.messages.copySuccess);
    } catch {
      setDetailActionMessage(adapter.messages.copyError);
    }
  }, [adapter, selectedItem]);

  const createDraft = useCallback(async (intent: ContentLibraryDraftIntent) => {
    if (!selectedItem) return;
    setIsCreatingDraft(true);
    setDetailActionMessage(null);
    try {
      const draft = await adapter.createDraftFromItem(selectedItem, intent);
      setDetailActionMessage(adapter.messages.draftCreatedAndNavigate(draft.id));
      adapter.onDraftCreated?.(selectedItem, draft, intent);
    } catch {
      setDetailActionMessage(adapter.messages.draftCreateError);
    } finally {
      setIsCreatingDraft(false);
    }
  }, [adapter, selectedItem]);

  const addToDrafts = useCallback(async () => {
    if (!selectedItem) return;
    setIsCreatingDraft(true);
    setDetailActionMessage(null);
    try {
      const draft = await adapter.createDraftFromItem(selectedItem, "rewrite");
      setDetailActionMessage(adapter.messages.addedToDrafts(draft.id));
    } catch {
      setDetailActionMessage(adapter.messages.addToDraftsError);
    } finally {
      setIsCreatingDraft(false);
    }
  }, [adapter, selectedItem]);

  const deleteItem = useCallback(async (item: TItem) => {
    Modal.confirm({
      title: "确定删除？",
      content: "相关素材、评论和标签关系也会一起删除。",
      onOk: async () => {
        try {
          await adapter.deleteItem(item.id);
          setItems((current) => current.filter((entry) => entry.id !== item.id));
          setSelectedItemIds((current) => current.filter((id) => id !== item.id));
          setTotal((current) => Math.max(0, current - 1));
          if (selectedItem?.id === item.id) closeDetail();
          setBatchActionMessage(adapter.messages.deleteSuccess);
        } catch {
          setBatchActionMessage(adapter.messages.deleteError);
        }
      },
    });
  }, [adapter, closeDetail, selectedItem]);

  const selectedItemHasTag = useCallback((tagId: number) => Boolean(selectedItem?.tags?.some((tag) => tag.id === tagId)), [selectedItem]);

  const replaceItemInList = useCallback((updated: TItem) => {
    setItems((current) => current.map((item) => item.id === updated.id ? updated : item));
  }, []);

  const replaceItemsInList = useCallback((updatedItems: TItem[]) => {
    const updatedMap = new Map(updatedItems.map((item) => [item.id, item]));
    setItems((current) => current.map((item) => updatedMap.get(item.id) ?? item));
    if (selectedItem) {
      const updatedSelected = updatedMap.get(selectedItem.id);
      if (updatedSelected) setSelectedItem(updatedSelected);
    }
  }, [selectedItem]);

  const applyBatchTag = useCallback(async (mode: ContentLibraryTagMode) => {
    if (!selectedItemIds.length) {
      setBatchActionMessage(adapter.messages.batchNoSelection);
      return;
    }
    if (!batchTagId) {
      setBatchActionMessage(adapter.messages.tagRequired);
      return;
    }
    setIsBatchWorking(true);
    setBatchActionMessage(null);
    try {
      const result = await adapter.batchTagItems({ item_ids: selectedItemIds, tag_ids: [Number(batchTagId)], mode });
      replaceItemsInList(result.items);
      setBatchActionMessage(mode === "add" ? adapter.messages.tagBatchAddSuccess(result.updated_count) : adapter.messages.tagBatchRemoveSuccess(result.updated_count));
    } catch {
      setBatchActionMessage(adapter.messages.tagBatchError);
    } finally {
      setIsBatchWorking(false);
    }
  }, [adapter, batchTagId, replaceItemsInList, selectedItemIds]);

  const createBatchRewriteDrafts = useCallback(async () => {
    if (!selectedItemIds.length) {
      setBatchActionMessage(adapter.messages.batchNoSelection);
      return;
    }
    setIsBatchWorking(true);
    setBatchActionMessage(null);
    try {
      const result = await adapter.batchCreateDrafts(selectedItemIds);
      setBatchActionMessage(adapter.messages.batchCreateDraftsSuccess(result.created_count));
    } catch {
      setBatchActionMessage(adapter.messages.batchCreateDraftsError);
    } finally {
      setIsBatchWorking(false);
    }
  }, [adapter, selectedItemIds]);

  const exportSelectedItems = useCallback(async (format: ContentLibraryExportFormat) => {
    if (!selectedItemIds.length) {
      setBatchActionMessage(adapter.messages.batchNoSelection);
      return;
    }
    setIsBatchWorking(true);
    setBatchActionMessage(null);
    try {
      const result = await adapter.exportItems(selectedItemIds, format);
      setLatestExport(result);
      setBatchActionMessage(adapter.messages.exportSuccess(result.exported_count));
    } catch {
      setBatchActionMessage(adapter.messages.exportError);
    } finally {
      setIsBatchWorking(false);
    }
  }, [adapter, selectedItemIds]);

  const deleteSelectedItems = useCallback(async () => {
    if (!selectedItemIds.length) return;
    setIsBatchWorking(true);
    setBatchActionMessage(null);
    const deletedIds: number[] = [];
    try {
      for (const id of selectedItemIds) {
        await adapter.deleteItem(id);
        deletedIds.push(id);
      }
      setBatchActionMessage(adapter.messages.batchDeleteSuccess(deletedIds.length));
    } catch {
      setBatchActionMessage(deletedIds.length ? adapter.messages.batchDeletePartialFailure(deletedIds.length) : adapter.messages.batchDeleteError);
    } finally {
      if (deletedIds.length) {
        setItems((current) => current.filter((item) => !deletedIds.includes(item.id)));
        setTotal((current) => Math.max(0, current - deletedIds.length));
        setSelectedItemIds((current) => current.filter((id) => !deletedIds.includes(id)));
        if (selectedItem && deletedIds.includes(selectedItem.id)) closeDetail();
      }
      setIsBatchWorking(false);
    }
  }, [adapter, closeDetail, selectedItem, selectedItemIds]);

  const downloadLatestExport = useCallback(async () => {
    if (!latestExport) return;
    setIsBatchWorking(true);
    setBatchActionMessage(null);
    try {
      await adapter.downloadExport(latestExport);
      setBatchActionMessage(adapter.messages.downloadSuccess(latestExport.file_name));
    } catch {
      setBatchActionMessage(adapter.messages.downloadError);
    } finally {
      setIsBatchWorking(false);
    }
  }, [adapter, latestExport]);

  const toggleSelectedTag = useCallback(async (tag: ContentLibraryTag) => {
    if (!selectedItem) return;
    setTagActionMessage(null);
    const mode = selectedItemHasTag(tag.id) ? "remove" : "add";
    try {
      const result = await adapter.batchTagItems({ item_ids: [selectedItem.id], tag_ids: [tag.id], mode });
      const updated = result.items[0];
      setSelectedItem(updated);
      replaceItemInList(updated);
    } catch {
      setTagActionMessage(adapter.messages.tagUpdateError);
    }
  }, [adapter, replaceItemInList, selectedItem, selectedItemHasTag]);

  const createAndAssignTag = useCallback(async () => {
    if (!selectedItem) return;
    const name = newTagName.trim();
    if (!name) {
      setTagActionMessage(adapter.messages.tagNameRequired);
      return;
    }
    setTagActionMessage(null);
    try {
      const created = await adapter.createTag({ name, color: "#111111" });
      setAvailableTags((current) => [...current, created]);
      setNewTagName("");
      const result = await adapter.batchTagItems({ item_ids: [selectedItem.id], tag_ids: [created.id], mode: "add" });
      const updated = result.items[0];
      setSelectedItem(updated);
      replaceItemInList(updated);
    } catch {
      setTagActionMessage(adapter.messages.tagCreateError);
    }
  }, [adapter, newTagName, replaceItemInList, selectedItem]);

  const loadComments = useCallback(async (nextPage = 1) => {
    if (!selectedItem) return;
    setIsCommentsLoading(true);
    setCommentsError(null);
    try {
      const result = await adapter.loadComments(selectedItem.id, nextPage);
      setComments((current) => nextPage === 1 ? result.items : [...current, ...result.items]);
      setCommentsTotal(result.total);
      setCommentsPage(nextPage);
    } catch {
      setCommentsError(adapter.messages.commentsLoadError);
    } finally {
      setIsCommentsLoading(false);
    }
  }, [adapter, selectedItem]);

  const toggleComments = useCallback(() => {
    const next = !isCommentsOpen;
    setIsCommentsOpen(next);
    if (next && selectedItem && comments.length === 0) void loadComments(1);
  }, [comments.length, isCommentsOpen, loadComments, selectedItem]);

  return {
    items,
    total,
    isLoading,
    error,
    selectedItem,
    selectedAssets,
    isDetailOpen,
    isDetailLoading,
    detailError,
    detailActionMessage,
    isCreatingDraft,
    availableTags,
    newTagName,
    tagActionMessage,
    isCommentsOpen,
    comments,
    commentsTotal,
    commentsPage,
    isCommentsLoading,
    commentsError,
    keywordFilter,
    selectedTagFilter,
    hasAssetsFilter,
    hasCommentsFilter,
    visibilityFilter,
    feishuPushStatusFilter,
    filterOptions,
    filterOptionsError,
    analysisStatusFilter,
    coreProductServiceFilter,
    contentTypeFilter,
    reusableModelFilter,
    contentUsageFilter,
    searchAttributeFilter,
    sortBy,
    page,
    pageSize,
    viewMode,
    selectedItemIds,
    selectedItemIdSet,
    batchTagId,
    batchActionMessage,
    isBatchWorking,
    latestExport,
    setKeywordFilter,
    setSelectedTagFilter,
    setHasAssetsFilter,
    setHasCommentsFilter,
    setVisibilityFilter,
    setFeishuPushStatusFilter,
    setAnalysisStatusFilter,
    setCoreProductServiceFilter,
    setContentTypeFilter,
    setReusableModelFilter,
    setContentUsageFilter,
    setSearchAttributeFilter,
    setViewMode,
    setNewTagName,
    setBatchTagId,
    setBatchActionMessage,
    setDetailActionMessage,
    setDetailError,
    refreshItems,
    refreshTags,
    refreshFilterOptions,
    clearFilters,
    handleSortChange,
    handlePageChange,
    toggleItemSelection,
    toggleVisibleSelection,
    setSelectedItemIds,
    clearSelection,
    openDetail,
    refreshSelectedItem,
    replaceSelectedItem,
    closeDetail,
    copySelectedItem,
    createDraft,
    addToDrafts,
    deleteItem,
    applyBatchTag,
    createBatchRewriteDrafts,
    exportSelectedItems,
    deleteSelectedItems,
    downloadLatestExport,
    selectedItemHasTag,
    toggleSelectedTag,
    createAndAssignTag,
    loadComments,
    toggleComments,
  };
}

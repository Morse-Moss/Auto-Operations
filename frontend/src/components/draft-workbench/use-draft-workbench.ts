import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type {
  DraftWorkbenchAdapter,
  DraftWorkbenchController,
  DraftWorkbenchDraft,
  DraftWorkbenchDraftPatch,
  DraftWorkbenchDryRunResult,
} from "./draft-workbench-types";

export function replaceDraftById<TDraft extends { id: number }>(drafts: readonly TDraft[], savedDraft: TDraft): TDraft[] {
  return drafts.map((draft) => (draft.id === savedDraft.id ? savedDraft : draft));
}

export function useDraftWorkbench<TDraft extends DraftWorkbenchDraft>(adapter: DraftWorkbenchAdapter<TDraft>): DraftWorkbenchController<TDraft> {
  const [drafts, setDrafts] = useState<TDraft[]>([]);
  const [selectedDraftId, setSelectedDraftId] = useState<number | null>(null);
  const [title, setTitle] = useState("");
  const [draftName, setDraftName] = useState("");
  const [body, setBody] = useState("");
  const [tags, setTags] = useState<NonNullable<DraftWorkbenchDraftPatch["tags"]>>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const selectedDraftIdRef = useRef<number | null>(null);
  selectedDraftIdRef.current = selectedDraftId;

  const selectedDraft = useMemo(
    () => drafts.find((draft) => draft.id === selectedDraftId) ?? null,
    [drafts, selectedDraftId],
  );

  const syncDraftState = useCallback((draft: TDraft | null) => {
    selectedDraftIdRef.current = draft?.id ?? null;
    if (!draft) {
      setSelectedDraftId(null);
      setTitle("");
      setDraftName("");
      setBody("");
      setTags([]);
      return;
    }
    setSelectedDraftId(draft.id);
    setTitle(draft.title);
    setDraftName(draft.draft_name ?? "");
    setBody(draft.body);
    setTags(Array.isArray(draft.tags) ? draft.tags : []);
  }, []);

  const applySavedDraft = useCallback((savedDraft: TDraft) => {
    setDrafts((current) => replaceDraftById(current, savedDraft));
    if (selectedDraftIdRef.current === savedDraft.id) {
      syncDraftState(savedDraft);
    }
  }, [syncDraftState]);

  const refreshDrafts = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const items = await adapter.loadDrafts();
      setDrafts(items);
      const nextSelected = selectedDraftId ? items.find((draft) => draft.id === selectedDraftId) : items[0];
      syncDraftState(nextSelected ?? null);
      if (!nextSelected && items.length === 0) {
        setMessage(null);
      }
    } catch {
      setDrafts([]);
      syncDraftState(null);
      setError("草稿列表加载失败。");
    } finally {
      setIsLoading(false);
    }
  }, [adapter, selectedDraftId, syncDraftState]);

  useEffect(() => {
    void refreshDrafts();
  }, [refreshDrafts]);

  const selectDraft = useCallback(
    (draftId: number) => {
      const next = drafts.find((draft) => draft.id === draftId) ?? null;
      syncDraftState(next);
      setError(null);
      setMessage(null);
    },
    [drafts, syncDraftState],
  );

  const saveSelectedDraft = useCallback(async () => {
    if (!selectedDraft) {
      setError("请先选择一个草稿。");
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const updated = await adapter.saveDraft(selectedDraft.id, { draft_name: draftName, title, body, tags });
      setDrafts((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      syncDraftState(updated);
      setMessage(`草稿 #${updated.id} 已保存。`);
    } catch {
      setError("草稿保存失败。");
    } finally {
      setIsLoading(false);
    }
  }, [adapter, body, draftName, selectedDraft, syncDraftState, tags, title]);

  const duplicateSelectedDraft = useCallback(async () => {
    if (!selectedDraft || !adapter.duplicateDraft) {
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const copied = await adapter.duplicateDraft(selectedDraft.id);
      setDrafts((current) => [copied, ...current.filter((item) => item.id !== copied.id)]);
      syncDraftState(copied);
      setMessage(`草稿 #${copied.id} 已复制。`);
    } catch {
      setError("草稿复制失败。");
    } finally {
      setIsLoading(false);
    }
  }, [adapter, selectedDraft, syncDraftState]);

  const deleteSelectedDraft = useCallback(async () => {
    if (!selectedDraft || !adapter.deleteDraft) {
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      await adapter.deleteDraft(selectedDraft.id);
      setDrafts((current) => current.filter((item) => item.id !== selectedDraft.id));
      syncDraftState(null);
      setMessage(`草稿 #${selectedDraft.id} 已删除。`);
    } catch {
      setError("草稿删除失败。");
    } finally {
      setIsLoading(false);
    }
  }, [adapter, selectedDraft, syncDraftState]);

  const dryRunSelectedDraft = useCallback(
    async (payload?: Record<string, unknown>) => {
      if (!selectedDraft || !adapter.dryRunDraft) {
        return null;
      }
      setError(null);
      try {
        return await adapter.dryRunDraft(selectedDraft.id, payload) as DraftWorkbenchDryRunResult;
      } catch {
        setError("dry-run 失败。");
        return null;
      }
    },
    [adapter, selectedDraft],
  );

  const createDraftFromSource = useCallback(
    async (sourceId: number, payload?: Record<string, unknown>) => {
      if (!adapter.createDraftFromSource) {
        return null;
      }
      setIsLoading(true);
      setError(null);
      try {
        const created = await adapter.createDraftFromSource(sourceId, payload);
        setDrafts((current) => [created, ...current]);
        syncDraftState(created);
        setMessage(`草稿 #${created.id} 已创建。`);
        return created;
      } catch {
        setError("草稿创建失败。");
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    [adapter, syncDraftState],
  );

  return {
    drafts,
    selectedDraftId,
    selectedDraft,
    draftName,
    title,
    body,
    tags,
    isLoading,
    error,
    message,
    selectDraft,
    setDraftName,
    setTitle,
    setBody,
    setTags,
    applySavedDraft,
    refreshDrafts,
    saveSelectedDraft,
    duplicateSelectedDraft,
    deleteSelectedDraft,
    dryRunSelectedDraft,
    createDraftFromSource,
  };
}

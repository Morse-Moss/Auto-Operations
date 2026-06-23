import { fetchDrafts, createDraftFromNote, deleteDraft, duplicateDraft, updateDraft } from "../../../lib/api";
import { formatShanghaiTime } from "../../../lib/time";
import type { Draft } from "../../../types";

import type { DraftWorkbenchAdapter } from "../../../components/draft-workbench";

function formatDraftTime(value: string): string {
  return formatShanghaiTime(value);
}

export function createXhsDraftWorkbenchAdapter(): DraftWorkbenchAdapter<Draft> {
  return {
    platform: "xhs",
    pageTitle: "小红书草稿工坊",
    pageDescription: "左侧草稿队列，中间编辑器，右侧 AI 助手；草稿继续保持 XHS 现有语义。",
    capabilities: {
      canCreateFromSource: true,
      canDuplicate: true,
      canDelete: true,
      canDryRun: false,
      canSendToPublish: true,
    },
    loadDrafts: async () => (await fetchDrafts("xhs")).items,
    saveDraft: async (draftId, patch) => updateDraft(draftId, patch),
    duplicateDraft: async (draftId) => duplicateDraft(draftId),
    deleteDraft: async (draftId) => {
      await deleteDraft(draftId);
    },
    createDraftFromSource: async (sourceId, payload) => {
      const intent = payload?.intent === "publish" ? "publish" : "rewrite";
      return createDraftFromNote({ platform: "xhs", source_note_id: sourceId, intent });
    },
    getListSubtitle: (draft) => {
      const time = formatDraftTime(draft.created_at);
      return draft.draft_name && draft.title ? `发布标题：${draft.title} · ${time}` : time;
    },
    getEmptyState: () => ({
      title: "还没有草稿",
      description: "先去内容库挑一篇笔记，或者用现有草稿复制一份继续写。",
      actionLabel: "去内容库",
    }),
  };
}

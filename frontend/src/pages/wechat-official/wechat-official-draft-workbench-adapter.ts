import type { WechatOfficialDraft } from "../../types";
import { deleteDraft, dryRunWechatOfficialDraft, duplicateDraft, fetchDrafts, updateDraft } from "../../lib/api";
import type { DraftWorkbenchAdapter } from "../../components/draft-workbench";

function formatDraftTime(value: string): string {
  return value ? value.replace("T", " ").slice(0, 16) : "";
}

export function createWechatOfficialDraftWorkbenchAdapter(): DraftWorkbenchAdapter<WechatOfficialDraft> {
  return {
    platform: "wechat_official",
    pageTitle: "公众号草稿工坊",
    pageDescription: "这里只管理独立草稿；从内容库生成后不保留引用关系。",
    capabilities: {
      canCreateFromSource: false,
      canDuplicate: true,
      canDelete: true,
      canDryRun: true,
      canSendToPublish: false,
    },
    loadDrafts: async () => (await fetchDrafts("wechat_official")).items.map((draft) => ({
      id: draft.id,
      platform: "wechat_official",
      draft_name: draft.draft_name,
      title: draft.title,
      body: draft.body,
      tags: draft.tags,
      created_at: draft.created_at,
    })),
    saveDraft: async (draftId, patch) => {
      const draft = await updateDraft(draftId, patch);
      return {
        id: draft.id,
        platform: "wechat_official",
        draft_name: draft.draft_name,
        title: draft.title,
        body: draft.body,
        tags: draft.tags,
        created_at: draft.created_at,
      };
    },
    duplicateDraft: async (draftId) => {
      const draft = await duplicateDraft(draftId);
      return {
        id: draft.id,
        platform: "wechat_official",
        draft_name: draft.draft_name,
        title: draft.title,
        body: draft.body,
        tags: draft.tags,
        created_at: draft.created_at,
      };
    },
    deleteDraft: async (draftId) => {
      await deleteDraft(draftId);
    },
    dryRunDraft: async (draftId, payload) => dryRunWechatOfficialDraft(draftId, payload ?? {}),
    getListSubtitle: (draft) => formatDraftTime(draft.created_at),
    getEmptyState: () => ({
      title: "还没有公众号草稿",
      description: "先从内容库生成一个独立草稿，草稿区不会显示内容库候选文章。",
    }),
  };
}

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
    pageDescription: "管理从公众号内容库生成的独立草稿，并保留来源文章和分析依据。",
    editorLabels: {
      draftNameLabel: "内部草稿名",
      draftNamePlaceholder: "例如：行业案例拆解 - 公众号 A版",
      titleLabel: "公众号标题",
      titlePlaceholder: "输入公众号标题",
      bodyLabel: "公众号正文",
      bodyPlaceholder: "输入公众号正文、结构和行动引导",
      tagsLabel: "选题标签",
      assistantTitle: "公众号生产助手",
      assistantDescription: "公众号草稿的分析依据、dry-run 校验和封面/正文图整理动作放在这里。",
    },
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
      source_article_id: draft.source_article_id ?? null,
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
        source_article_id: draft.source_article_id ?? null,
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
        source_article_id: draft.source_article_id ?? null,
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

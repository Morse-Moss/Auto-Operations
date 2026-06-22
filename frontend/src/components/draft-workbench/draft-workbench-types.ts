import type { ReactNode } from "react";

import type { Draft } from "../../types";

// Minimal shape the shared shell can render. Platform adapters may extend it,
// but platform-specific semantics must stay outside the shared workbench core.
export type DraftWorkbenchDraft = Pick<Draft, "id" | "title" | "body" | "tags" | "created_at">;

export type DraftWorkbenchDraftPatch = {
  title: string;
  body: string;
  tags: Draft["tags"];
};

export type DraftWorkbenchDryRunResult = {
  ok: boolean;
  publish_blocked: boolean;
  sendall_blocked: boolean;
  checks: Record<string, string>;
};

export type DraftWorkbenchCapabilities = {
  canCreateFromSource: boolean;
  canDuplicate: boolean;
  canDelete: boolean;
  canDryRun: boolean;
  canSendToPublish: boolean;
};

export type DraftWorkbenchEmptyState = {
  title: string;
  description: string;
  actionLabel?: string;
};

export type DraftWorkbenchAdapter<TDraft extends DraftWorkbenchDraft = DraftWorkbenchDraft> = {
  platform: Draft["platform"];
  pageTitle: string;
  pageDescription: string;
  capabilities: DraftWorkbenchCapabilities;
  loadDrafts(): Promise<TDraft[]>;
  saveDraft(draftId: number, patch: DraftWorkbenchDraftPatch): Promise<TDraft>;
  duplicateDraft?(draftId: number): Promise<TDraft>;
  deleteDraft?(draftId: number): Promise<void>;
  dryRunDraft?(draftId: number, payload?: Record<string, unknown>): Promise<DraftWorkbenchDryRunResult>;
  createDraftFromSource?(sourceId: number, payload?: Record<string, unknown>): Promise<TDraft>;
  getListSubtitle(draft: TDraft): string;
  getEmptyState(): DraftWorkbenchEmptyState;
};

export type DraftWorkbenchController<TDraft extends DraftWorkbenchDraft = DraftWorkbenchDraft> = {
  drafts: TDraft[];
  selectedDraftId: number | null;
  selectedDraft: TDraft | null;
  title: string;
  body: string;
  tags: NonNullable<Draft["tags"]>;
  isLoading: boolean;
  error: string | null;
  message: string | null;
  selectDraft(draftId: number): void;
  setTitle(title: string): void;
  setBody(body: string): void;
  setTags(tags: NonNullable<Draft["tags"]>): void;
  refreshDrafts(): Promise<void>;
  saveSelectedDraft(): Promise<void>;
  duplicateSelectedDraft(): Promise<void>;
  deleteSelectedDraft(): Promise<void>;
  dryRunSelectedDraft(payload?: Record<string, unknown>): Promise<DraftWorkbenchDryRunResult | null>;
  createDraftFromSource(sourceId: number, payload?: Record<string, unknown>): Promise<TDraft | null>;
  renderEditorExtras?: (draft: TDraft) => ReactNode;
  renderAssistantExtras?: (draft: TDraft) => ReactNode;
};

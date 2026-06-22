import type { Draft } from "../../../types";

import type { RewriteTemplateKey } from "./rewrite-templates";

export type RewriteCandidate = {
  title: string;
  body: string;
  tags: NonNullable<Draft["tags"]>;
  generatedAt: number;
};

export type RewriteCandidateMap = Partial<Record<RewriteTemplateKey, RewriteCandidate>>;

export function toRewriteCandidate(
  draft: Pick<Draft, "title" | "body" | "tags">,
  generatedAt: number,
): RewriteCandidate {
  return {
    title: draft.title,
    body: draft.body,
    tags: Array.isArray(draft.tags) ? draft.tags : [],
    generatedAt,
  };
}

export function setRewriteCandidate(
  candidates: RewriteCandidateMap,
  mode: RewriteTemplateKey,
  candidate: RewriteCandidate,
): RewriteCandidateMap {
  return {
    ...candidates,
    [mode]: candidate,
  };
}

export function getRewriteCandidate(
  candidates: RewriteCandidateMap,
  mode: RewriteTemplateKey,
): RewriteCandidate | null {
  return candidates[mode] ?? null;
}

export function clearRewriteCandidate(
  candidates: RewriteCandidateMap,
  mode: RewriteTemplateKey,
): RewriteCandidateMap {
  const next = { ...candidates };
  delete next[mode];
  return next;
}

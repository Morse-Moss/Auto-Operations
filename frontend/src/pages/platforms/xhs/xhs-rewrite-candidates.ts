import type { Draft } from "../../../types";

import type { RewriteTemplateKey } from "./rewrite-templates";

export type RewriteCandidate = {
  title: string;
  body: string;
  tags: NonNullable<Draft["tags"]>;
  generatedAt: number;
};

export type RewriteCandidateMap = Partial<Record<RewriteTemplateKey, RewriteCandidate>>;

const REWRITE_TEMPLATE_KEYS: RewriteTemplateKey[] = ["safe", "polish", "seed"];

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function parseCandidateTags(value: unknown): NonNullable<Draft["tags"]> {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (!isRecord(item) || typeof item.name !== "string" || !item.name.trim()) return [];
    const tag: { id?: string; name: string } = { name: item.name.trim() };
    if (typeof item.id === "string" || typeof item.id === "number") tag.id = String(item.id);
    return [tag];
  });
}

export function parseRewriteCandidates(value: unknown): RewriteCandidateMap {
  if (!isRecord(value)) return {};

  const candidates: RewriteCandidateMap = {};
  REWRITE_TEMPLATE_KEYS.forEach((mode) => {
    const candidate = value[mode];
    if (!isRecord(candidate) || typeof candidate.title !== "string" || typeof candidate.body !== "string") return;
    const generatedAtValue = candidate.generated_at ?? candidate.generatedAt;
    const generatedAt = typeof generatedAtValue === "number" ? generatedAtValue : Date.parse(String(generatedAtValue ?? ""));
    if (!Number.isFinite(generatedAt)) return;
    candidates[mode] = {
      title: candidate.title,
      body: candidate.body,
      tags: parseCandidateTags(candidate.tags),
      generatedAt,
    };
  });
  return candidates;
}

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

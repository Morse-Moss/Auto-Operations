from __future__ import annotations

from typing import Any, Literal


RewriteMode = Literal["safe", "polish", "seed"]
REWRITE_MODES: tuple[RewriteMode, ...] = ("safe", "polish", "seed")


def _normalize_tags(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []

    normalized: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        tag = {"name": name.strip()}
        tag_id = item.get("id")
        if isinstance(tag_id, (str, int)):
            tag["id"] = str(tag_id)
        normalized.append(tag)
    return normalized


def serialize_rewrite_candidates(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}

    normalized: dict[str, dict[str, Any]] = {}
    for mode in REWRITE_MODES:
        candidate = value.get(mode)
        if not isinstance(candidate, dict):
            continue
        title = candidate.get("title")
        body = candidate.get("body")
        generated_at = candidate.get("generated_at")
        if not isinstance(title, str) or not isinstance(body, str) or not isinstance(generated_at, str):
            continue
        normalized[mode] = {
            "title": title,
            "body": body,
            "tags": _normalize_tags(candidate.get("tags")),
            "generated_at": generated_at,
        }
    return normalized


def set_rewrite_candidate(
    current: Any,
    mode: RewriteMode,
    *,
    title: str,
    body: str,
    tags: Any,
    generated_at: str,
) -> dict[str, dict[str, Any]]:
    candidates = serialize_rewrite_candidates(current)
    candidates[mode] = {
        "title": title,
        "body": body,
        "tags": _normalize_tags(tags),
        "generated_at": generated_at,
    }
    return candidates


def clear_rewrite_candidate(current: Any, mode: RewriteMode) -> dict[str, dict[str, Any]]:
    candidates = serialize_rewrite_candidates(current)
    candidates.pop(mode, None)
    return candidates

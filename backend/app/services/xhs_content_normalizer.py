from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any


@dataclass(frozen=True)
class NormalizedContent:
    title: str
    body: str
    tags: list[dict[str, Any]]
    warnings: list[str] = field(default_factory=list)


_PREFIX_PATTERNS = [
    re.compile(r"^\s*(正文|内容|小红书文案)\s*[:：]\s*"),
    re.compile(r"^\s*以下是(?:适合)?小红书发布的内容\s*[:：]?\s*"),
]


def _plain_compare(value: str) -> str:
    value = value.strip()
    value = re.sub(r"^[#\s]+", "", value)
    value = re.sub(r"^标题\s*[:：]\s*", "", value)
    value = value.strip("《》\"'“”‘’ ")
    value = re.sub(r"\s+", "", value)
    return value.lower()


def _strip_markdown_line(line: str) -> str:
    line = re.sub(r"^\s{0,3}#{1,6}\s+", "", line)
    line = re.sub(r"^\s*[-*]\s+", "", line)
    line = re.sub(r"\*\*(.*?)\*\*", r"\1", line)
    line = re.sub(r"__(.*?)__", r"\1", line)
    return line.strip()


def _strip_prefixes(lines: list[str], warnings: list[str]) -> list[str]:
    changed = True
    while lines and changed:
        changed = False
        first = lines[0]
        for pattern in _PREFIX_PATTERNS:
            next_first = pattern.sub("", first).strip()
            if next_first != first.strip():
                warnings.append("removed_intro_prefix")
                changed = True
                if next_first:
                    lines[0] = next_first
                else:
                    lines = lines[1:]
                break
    return lines


def _normalize_body(title: str, body: str, warnings: list[str]) -> str:
    raw_lines = [line.rstrip() for line in body.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    lines = [_strip_markdown_line(line) for line in raw_lines]
    while lines and not lines[0].strip():
        lines.pop(0)
    lines = _strip_prefixes(lines, warnings)
    title_key = _plain_compare(title)
    if lines and title_key and _plain_compare(lines[0]) == title_key:
        lines.pop(0)
        warnings.append("removed_repeated_title")
    lines = _strip_prefixes(lines, warnings)
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    collapsed: list[str] = []
    previous_blank = False
    for line in lines:
        is_blank = not line.strip()
        if is_blank and previous_blank:
            continue
        collapsed.append(line.strip() if not is_blank else "")
        previous_blank = is_blank
    return "\n".join(collapsed).strip()


def _normalize_tags(tags: list[Any] | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in tags or []:
        if isinstance(item, str):
            name = item.strip().lstrip("#").strip()
            tag: dict[str, Any] = {"name": name}
        elif isinstance(item, dict):
            name = str(item.get("name", "")).strip().lstrip("#").strip()
            tag = {key: value for key, value in item.items() if key in {"id", "name"}}
            tag["name"] = name
        else:
            continue
        if not name or name in seen:
            continue
        seen.add(name)
        normalized.append(tag)
    return normalized


def normalize_xhs_generated_content(title: str, body: str, tags: list[Any] | None) -> NormalizedContent:
    warnings: list[str] = []
    normalized_title = _strip_markdown_line(str(title or "")).strip()
    normalized_body = _normalize_body(normalized_title, str(body or ""), warnings)
    normalized_tags = _normalize_tags(tags)
    return NormalizedContent(
        title=normalized_title,
        body=normalized_body,
        tags=normalized_tags,
        warnings=list(dict.fromkeys(warnings)),
    )

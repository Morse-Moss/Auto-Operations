from __future__ import annotations

import re
from typing import Any


def _text_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed if trimmed and trimmed not in {"--", "暂无"} else None


def parse_huitun_number(value: str | None) -> int | None:
    text = _text_or_none(value)
    if text is None:
        return None

    normalized = text.replace(",", "").strip()
    unit_match = re.fullmatch(r"(-?\d+(?:\.\d+)?)(w|万)", normalized, flags=re.IGNORECASE)
    if unit_match:
        return round(float(unit_match.group(1)) * 10000)

    try:
        number = float(normalized)
    except ValueError:
        return None
    if not number.is_integer():
        return round(number)
    return int(number)


def parse_huitun_categories(value: str) -> list[dict[str, str | None]]:
    trimmed = value.strip()
    if not trimmed or trimmed == "--":
        return []

    categories: list[dict[str, str | None]] = []
    for line in [line.strip() for line in trimmed.splitlines() if line.strip()]:
        matches = list(re.finditer(r"(.+?)\s+([\d.]+)%", line))
        if not matches:
            categories.append({"label": line, "rate": None})
            continue
        for match in matches:
            categories.append({"label": match.group(1).strip(), "rate": match.group(2)})
    return categories


def parse_hotword_rows_from_cells(source_keyword: str, table_rows: list[list[str]]) -> list[dict[str, Any]]:
    parsed_rows: list[dict[str, Any]] = []
    source = source_keyword.strip()

    for cells in table_rows:
        if len(cells) < 5:
            continue

        keyword = cells[0].strip()
        if not keyword:
            continue

        hot_value_text = _text_or_none(cells[1])
        interaction_text = _text_or_none(cells[3])
        parsed_rows.append(
            {
                "source_keyword": source,
                "keyword": keyword,
                "hot_value_text": hot_value_text,
                "hot_value_number": parse_huitun_number(hot_value_text),
                "note_count": parse_huitun_number(cells[2]),
                "interaction_text": interaction_text,
                "interaction_number": parse_huitun_number(interaction_text),
                "categories": parse_huitun_categories(cells[4]),
                "rank_index": len(parsed_rows) + 1,
            }
        )
    return parsed_rows


def prioritize_exact_hotword_rows(keyword: str, rows: list[dict]) -> list[dict]:
    normalized_keyword = keyword.strip()
    return sorted(
        rows,
        key=lambda row: (
            0 if str(row.get("keyword", "")).strip() == normalized_keyword else 1,
            int(row.get("rank_index") or 0),
        ),
    )


def dedupe_keyword_candidates(rows: list[dict]) -> list[dict]:
    deduped: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        keyword = str(row.get("keyword") or "").strip()
        key = keyword.lower()
        if not keyword or key in seen:
            continue
        deduped.append(row)
        seen.add(key)
    return deduped

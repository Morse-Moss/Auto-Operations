from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.security import decrypt_text
from backend.app.core.time import shanghai_now
from backend.app.models import ModelConfig, Note, NoteAnalysisResult
from backend.app.services.ai_service import OpenAICompatibleImageClient, OpenAICompatibleTextClient
from backend.app.services.feishu_bitable_service import (
    REUSABLE_MODEL_OPTIONS,
    REUSE_VALUE_OPTIONS,
    infer_reusable_models,
    normalize_content_type,
    normalize_multi_select,
    normalize_search_attribute,
)

SYSTEM_ANALYSIS_SOURCE = "system"
SYSTEM_ANALYSIS_DONE_STATUS = "\u5df2\u5b8c\u6210"


def engagement_score(metrics: dict[str, int]) -> float:
    score = (
        _bucket_score(metrics.get("likes", 0), [50, 200, 500, 1000])
        + _bucket_score(metrics.get("collects", 0), [20, 100, 300, 800])
        + _bucket_score(metrics.get("comments", 0), [10, 50, 150, 300])
        + _bucket_score(metrics.get("shares", 0), [5, 20, 50, 100])
    )
    return round(score, 1)


def rating_for_score(score: float) -> str:
    if score >= 8:
        return "\u7206\u6b3e\u5185\u5bb9"
    if score >= 6:
        return "\u4f18\u8d28\u5185\u5bb9"
    if score >= 4:
        return "\u666e\u901a\u5185\u5bb9"
    return "\u4f4e\u8868\u73b0\u5185\u5bb9"


def get_or_create_system_analysis_result(db: Session, *, user_id: int, note_id: int) -> NoteAnalysisResult:
    result = db.scalar(
        select(NoteAnalysisResult).where(
            NoteAnalysisResult.note_id == note_id,
            NoteAnalysisResult.source == SYSTEM_ANALYSIS_SOURCE,
        )
    )
    if result is None:
        result = NoteAnalysisResult(user_id=user_id, note_id=note_id, source=SYSTEM_ANALYSIS_SOURCE)
        db.add(result)
        db.flush()
    return result


def analyze_note_system(
    db: Session,
    *,
    user_id: int,
    note: Note,
    text_client: Any | None = None,
    image_client: Any | None = None,
) -> NoteAnalysisResult:
    result = get_or_create_system_analysis_result(db, user_id=user_id, note_id=note.id)
    metrics = engagement_metrics(note)
    score = engagement_score(metrics)
    analysis = _deterministic_analysis(note)
    model_analysis = _text_model_analysis(db, user_id=user_id, note=note, text_client=text_client)
    if model_analysis:
        analysis.update(model_analysis)

    cover_type = _cover_type_from_image_model(db, note=note, image_client=image_client)
    now = shanghai_now()
    result.analysis_status = SYSTEM_ANALYSIS_DONE_STATUS
    result.subject_object = _text(analysis.get("subject_object"))
    result.content_type = normalize_content_type(analysis.get("content_type"))
    result.core_points = _text(analysis.get("core_points"))
    result.target_audience = _text(analysis.get("target_audience"))
    result.title_hook = _text(analysis.get("title_hook"))
    result.cover_type = _text(cover_type) or None
    result.title_type = _text(analysis.get("title_type")) or None
    result.content_structure = _text(analysis.get("content_structure"))
    result.reusable_models = normalize_multi_select(
        analysis.get("reusable_models"),
        REUSABLE_MODEL_OPTIONS,
        fallback=infer_reusable_models(note),
    )
    result.reuse_value = "\u3001".join(
        normalize_multi_select(
            analysis.get("reuse_values") or analysis.get("reuse_value"),
            REUSE_VALUE_OPTIONS,
            fallback=[REUSE_VALUE_OPTIONS[0]],
        )
    )
    result.search_attribute = normalize_search_attribute(analysis.get("search_attribute"), note) or None
    result.score = score
    result.rating = rating_for_score(score)
    result.analysis_note = ""
    result.raw_payload = {
        "source": SYSTEM_ANALYSIS_SOURCE,
        "metrics": metrics,
        "analysis": analysis,
        "cover_type_degraded": result.cover_type is None,
    }
    result.updated_at = now
    db.commit()
    db.refresh(result)
    return result


def engagement_metrics(note: Note) -> dict[str, int]:
    raw = note.raw_json if isinstance(note.raw_json, dict) else {}
    direct = {
        "likes": _as_int(raw.get("liked_count") or raw.get("likes") or raw.get("like_count")),
        "collects": _as_int(raw.get("collected_count") or raw.get("collects") or raw.get("collect_count")),
        "comments": _as_int(raw.get("comment_count") or raw.get("comments")),
        "shares": _as_int(raw.get("share_count") or raw.get("shares")),
    }
    if any(direct.values()):
        return direct

    data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
    items = data.get("items") if isinstance(data.get("items"), list) else []
    item = items[0] if items and isinstance(items[0], dict) else {}
    card = item.get("note_card") if isinstance(item.get("note_card"), dict) else {}
    info = card.get("interact_info") if isinstance(card.get("interact_info"), dict) else {}
    return {
        "likes": _as_int(info.get("liked_count")),
        "collects": _as_int(info.get("collected_count")),
        "comments": _as_int(info.get("comment_count")),
        "shares": _as_int(info.get("share_count")),
    }


def _bucket_score(value: int, thresholds: list[int]) -> float:
    if value <= thresholds[0]:
        return 0.5
    if value <= thresholds[1]:
        return 1.0
    if value <= thresholds[2]:
        return 1.5
    if value <= thresholds[3]:
        return 2.0
    return 2.5


def _as_int(value: Any) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        cleaned = value.strip().lower().replace(",", "")
        multiplier = 1
        if cleaned.endswith("w"):
            multiplier = 10000
            cleaned = cleaned[:-1]
        try:
            return int(float(cleaned) * multiplier)
        except ValueError:
            return 0
    return 0


def _deterministic_analysis(note: Note) -> dict[str, Any]:
    body = (note.content or "").strip()
    title = (note.title or "").strip()
    summary = body[:240] or title
    return {
        "subject_object": title[:120] or note.note_id,
        "content_type": "",
        "core_points": summary,
        "target_audience": "",
        "title_hook": title,
        "title_type": "",
        "content_structure": _content_structure(title, body),
        "reusable_models": infer_reusable_models(note),
        "reuse_values": [REUSE_VALUE_OPTIONS[0]],
        "search_attribute": normalize_search_attribute("", note),
    }


def _content_structure(title: str, body: str) -> str:
    if title and body:
        return "\u6807\u9898\u627f\u63a5\u6b63\u6587\uff0c\u6b63\u6587\u56f4\u7ed5\u6838\u5fc3\u7ecf\u9a8c\u5c55\u5f00\u3002"
    if body:
        return "\u6b63\u6587\u56f4\u7ed5\u6838\u5fc3\u7ecf\u9a8c\u5c55\u5f00\u3002"
    return ""


def _text_model_analysis(db: Session, *, user_id: int, note: Note, text_client: Any | None) -> dict[str, Any]:
    if text_client is None:
        text_client = OpenAICompatibleTextClient()
    model_config = db.scalar(
        select(ModelConfig).where(
            ModelConfig.user_id == user_id,
            ModelConfig.model_type == "text",
            ModelConfig.is_default.is_(True),
        )
    )
    if model_config is None or not model_config.encrypted_api_key:
        return {}
    api_key = decrypt_text(model_config.encrypted_api_key)
    if not api_key:
        return {}
    try:
        content = text_client.complete_json_prompt(
            model_config=model_config,
            api_key=api_key,
            system_prompt=(
                "\u4f60\u662f\u5c0f\u7ea2\u4e66\u5185\u5bb9\u8fd0\u8425\u5206\u6790\u5e08\u3002"
                "\u53ea\u8f93\u51fa\u5408\u6cd5 JSON\uff0c\u4e0d\u8f93\u51fa\u89e3\u91ca\u3002"
            ),
            user_prompt=_system_analysis_prompt(note),
            temperature=0.1,
        )
        parsed = _extract_json_object(content)
    except Exception:
        return {}
    return {key: value for key, value in parsed.items() if key not in {"analysis_note", "cover_type"}}


def _system_analysis_prompt(note: Note) -> str:
    return (
        "Return JSON with keys subject_object, content_type, core_points, target_audience, "
        "title_hook, title_type, content_structure, reusable_models, reuse_values, search_attribute.\n"
        f"Title: {note.title}\n"
        f"Content: {(note.content or '')[:5000]}"
    )


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = (text or "").strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped, flags=re.IGNORECASE).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, re.DOTALL)
        if not match:
            raise
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        return {}
    return parsed


def _cover_type_from_image_model(db: Session, *, note: Note, image_client: Any | None) -> str:
    if image_client is None:
        image_client = OpenAICompatibleImageClient()
    model_config = db.scalar(
        select(ModelConfig).where(
            ModelConfig.user_id == note.user_id,
            ModelConfig.model_type == "image",
            ModelConfig.is_default.is_(True),
        )
    )
    if model_config is None or not model_config.encrypted_api_key:
        return ""
    try:
        api_key = decrypt_text(model_config.encrypted_api_key)
    except Exception:
        return ""
    if not api_key:
        return ""
    cover_ref = _first_cover_ref(db, note)
    if not cover_ref:
        return ""
    try:
        return _text(
            image_client.describe_image(
                model_config=model_config,
                api_key=api_key,
                image_url=cover_ref,
                instruction="\u5224\u65ad\u8fd9\u5f20\u5c0f\u7ea2\u4e66\u5c01\u9762\u7684\u7c7b\u578b\uff0c\u53ea\u8f93\u51fa\u7b80\u77ed\u7c7b\u578b\u540d\u3002",
            )
        )
    except Exception:
        return ""


def _first_cover_ref(db: Session, note: Note) -> str:
    from backend.app.models import NoteAsset

    asset = db.scalar(select(NoteAsset).where(NoteAsset.note_id == note.id, NoteAsset.asset_type == "image").order_by(NoteAsset.sort_order.asc(), NoteAsset.id.asc()))
    if asset is not None:
        return asset.local_path or asset.url or ""
    raw = note.raw_json if isinstance(note.raw_json, dict) else {}
    for key in ("cover_url", "image_url", "cover", "image"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "\u3001".join(_text(item) for item in value if _text(item))
    if isinstance(value, dict):
        text = value.get("text")
        return str(text).strip() if text is not None else ""
    return str(value).strip()

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from backend.app.models import (
    AiDraft,
    AnalysisReport,
    DraftAsset,
    KeywordDiscoveryItem,
    KeywordGroup,
    ModelConfig,
    Note,
    NoteAnalysisResult,
    NoteComment,
    User,
)
from backend.app.services.ai_service import TextAiClient

DISCLAIMER = "系统打分仅用于发布前内容诊断和爆款潜力评估，不代表实际流量预测。"

DIMENSION_SPECS = [
    ("opportunity_fit", "机会匹配", 30),
    ("xhs_content", "小红书内容", 35),
    ("geo_asset", "GEO 资产", 20),
    ("publish_readiness", "发布执行", 15),
]

STRUCTURE_TOKENS = ("步骤", "清单", "避坑", "对比", "方法", "攻略", "原因", "建议", "注意", "怎么", "如何")
TRUST_TOKENS = ("数据", "案例", "实测", "经验", "前后", "%", "天", "小时", "分钟", "次", "元")
RISK_TOKENS = ("绝对", "保证", "必爆", "百分百", "最强", "全网第一", "永久", "无风险")


def _as_text(value: Any, limit: int = 500) -> str:
    text = str(value or "").strip()
    return text[:limit]


def _clamp_score(value: Any, minimum: int = 0, maximum: int = 100) -> int:
    try:
        score = int(round(float(value)))
    except (TypeError, ValueError):
        score = minimum
    return max(minimum, min(maximum, score))


def _potential_level(score: int) -> str:
    if score >= 90:
        return "excellent"
    if score >= 80:
        return "high"
    if score >= 65:
        return "medium"
    return "low"


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = (text or "").strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if match is None:
            raise ValueError("AI score response is not valid JSON") from None
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("AI score response must be a JSON object")
    return parsed


def _asset_payload(asset: DraftAsset) -> dict[str, Any]:
    return {
        "id": asset.id,
        "asset_type": asset.asset_type,
        "url": asset.url,
        "local_path": asset.local_path,
        "sort_order": asset.sort_order,
    }


def _tags_text(tags: Any) -> str:
    if not isinstance(tags, list):
        return ""
    names: list[str] = []
    for tag in tags:
        if isinstance(tag, dict) and tag.get("name"):
            names.append(str(tag["name"]).strip())
        elif isinstance(tag, str):
            names.append(tag.strip())
    return " ".join(name for name in names if name)


class DraftAiScoringService:
    def collect_virtual_content_opportunities(self, db: Session, current_user: User, draft: AiDraft) -> dict[str, Any]:
        draft_text = f"{draft.title}\n{draft.body}\n{_tags_text(draft.tags)}".lower()

        keyword_groups = db.scalars(
            select(KeywordGroup)
            .where(KeywordGroup.user_id == current_user.id, KeywordGroup.platform == draft.platform)
            .order_by(KeywordGroup.updated_at.desc(), KeywordGroup.id.desc())
            .limit(20)
        ).all()
        groups_payload: list[dict[str, Any]] = []
        matched_terms: list[str] = []
        for group in keyword_groups:
            keywords = [str(keyword).strip() for keyword in (group.keywords or []) if str(keyword).strip()]
            matches = [keyword for keyword in keywords if keyword.lower() in draft_text]
            if matches:
                matched_terms.extend(matches)
            groups_payload.append({"id": group.id, "name": group.name, "keywords": keywords[:12], "matches": matches[:8]})

        discovery_items = db.scalars(
            select(KeywordDiscoveryItem)
            .where(KeywordDiscoveryItem.user_id == current_user.id, KeywordDiscoveryItem.platform == draft.platform)
            .order_by(desc(KeywordDiscoveryItem.hot_value_number), KeywordDiscoveryItem.rank_index.asc(), KeywordDiscoveryItem.id.desc())
            .limit(20)
        ).all()
        discovery_payload = []
        for item in discovery_items:
            keyword = item.keyword.strip()
            matched = bool(keyword and keyword.lower() in draft_text)
            if matched:
                matched_terms.append(keyword)
            discovery_payload.append({
                "id": item.id,
                "keyword": keyword,
                "source_keyword": item.source_keyword,
                "hot_value_number": item.hot_value_number,
                "note_count": item.note_count,
                "interaction_number": item.interaction_number,
                "matched": matched,
            })

        source_note = None
        source_analysis = None
        if draft.source_note_id:
            source_note = db.scalar(select(Note).where(Note.id == draft.source_note_id, Note.user_id == current_user.id))
            if source_note is not None:
                source_analysis = db.scalars(
                    select(NoteAnalysisResult)
                    .where(NoteAnalysisResult.note_id == source_note.id, NoteAnalysisResult.user_id == current_user.id)
                    .order_by(NoteAnalysisResult.updated_at.desc(), NoteAnalysisResult.id.desc())
                ).first()

        comments = db.scalars(
            select(NoteComment)
            .join(Note, Note.id == NoteComment.note_id)
            .where(Note.user_id == current_user.id, Note.platform == draft.platform)
            .order_by(NoteComment.like_count.desc(), NoteComment.id.desc())
            .limit(20)
        ).all()
        comments_payload = [
            {"note_id": comment.note_id, "content": _as_text(comment.content, 180), "like_count": comment.like_count}
            for comment in comments
            if comment.content.strip()
        ]

        reports = db.scalars(
            select(AnalysisReport)
            .where(AnalysisReport.user_id == current_user.id, AnalysisReport.platform == draft.platform, AnalysisReport.status == "completed")
            .order_by(AnalysisReport.created_at.desc(), AnalysisReport.id.desc())
            .limit(3)
        ).all()
        reports_payload = [
            {
                "id": report.id,
                "title": report.title,
                "report_type": report.report_type,
                "evidence_pool": report.evidence_pool or {},
                "result_json": report.result_json or {},
            }
            for report in reports
        ]

        return {
            "matched_terms": list(dict.fromkeys(matched_terms))[:20],
            "keyword_groups": groups_payload,
            "keyword_discovery_items": discovery_payload,
            "source_note": {
                "id": source_note.id,
                "title": source_note.title,
                "content": _as_text(source_note.content, 400),
                "raw_json": source_note.raw_json or {},
            } if source_note is not None else None,
            "source_analysis": {
                "score": source_analysis.score,
                "rating": source_analysis.rating,
                "content_type": source_analysis.content_type,
                "core_points": _as_text(source_analysis.core_points, 300),
                "target_audience": _as_text(source_analysis.target_audience, 220),
                "reuse_value": source_analysis.reuse_value,
                "search_attribute": source_analysis.search_attribute,
            } if source_analysis is not None else None,
            "comments": comments_payload,
            "analysis_reports": reports_payload,
        }

    def build_rule_diagnosis(self, draft: AiDraft, assets: list[DraftAsset], opportunities: dict[str, Any]) -> dict[str, Any]:
        title = draft.title or ""
        body = draft.body or ""
        tags = draft.tags if isinstance(draft.tags, list) else []
        text = f"{title}\n{body}"
        matched_terms = opportunities.get("matched_terms") or []

        opportunity_score = 12
        if draft.source_note_id:
            opportunity_score += 5
        if matched_terms:
            opportunity_score += min(9, 3 + len(matched_terms) * 2)
        if opportunities.get("source_analysis"):
            opportunity_score += 4
        opportunity_score = min(30, opportunity_score)

        xhs_score = 10
        if 8 <= len(title) <= 32:
            xhs_score += 7
        elif title.strip():
            xhs_score += 4
        if len(body.strip()) >= 250:
            xhs_score += 7
        elif len(body.strip()) >= 100:
            xhs_score += 4
        if "\n" in body.strip():
            xhs_score += 4
        if any(token in text for token in STRUCTURE_TOKENS):
            xhs_score += 5
        if any(token in text for token in TRUST_TOKENS):
            xhs_score += 4
        if len(tags) >= 2:
            xhs_score += 3
        xhs_score = min(35, xhs_score)

        geo_score = 6
        if any(token in title for token in ("怎么", "如何", "为什么", "避坑", "对比")):
            geo_score += 4
        if any(token in text for token in STRUCTURE_TOKENS):
            geo_score += 4
        if any(token in text for token in TRUST_TOKENS):
            geo_score += 4
        if opportunities.get("source_analysis"):
            geo_score += 2
        geo_score = min(20, geo_score)

        publish_score = 4
        if title.strip():
            publish_score += 3
        if body.strip():
            publish_score += 3
        if assets:
            publish_score += 3
        if tags:
            publish_score += 2
        publish_score = min(15, publish_score)

        risks = []
        if not title.strip():
            risks.append({"level": "high", "title": "缺少标题", "detail": "标题为空，无法判断点击理由。"})
        if len(body.strip()) < 100:
            risks.append({"level": "medium", "title": "正文信息密度不足", "detail": "正文较短，可能缺少方法、案例或可收藏信息。"})
        if any(token in text for token in RISK_TOKENS):
            risks.append({"level": "medium", "title": "存在夸大表达", "detail": "草稿包含绝对化或承诺式表达，发布前建议降风险。"})
        if not assets:
            risks.append({"level": "medium", "title": "缺少视觉素材", "detail": "小红书内容依赖封面和图片，建议补齐封面或配图。"})

        total = opportunity_score + xhs_score + geo_score + publish_score
        dimensions = [
            {"key": "opportunity_fit", "label": "机会匹配", "score": opportunity_score, "max_score": 30, "reason": "根据来源笔记、关键词命中和已有分析结果估算。"},
            {"key": "xhs_content", "label": "小红书内容", "score": xhs_score, "max_score": 35, "reason": "根据标题、正文长度、结构词、标签和小红书可读性估算。"},
            {"key": "geo_asset", "label": "GEO 资产", "score": geo_score, "max_score": 20, "reason": "根据问题表达、结构化答案和证据完整度估算。"},
            {"key": "publish_readiness", "label": "发布执行", "score": publish_score, "max_score": 15, "reason": "根据标题、正文、标签和素材完整度估算。"},
        ]
        suggestions = []
        if opportunity_score < 18:
            suggestions.append({"priority": "high", "title": "先补清楚这篇草稿服务的用户问题", "example": "把标题和开头改成一个真实用户会问的问题，再展开答案。"})
        if xhs_score < 22:
            suggestions.append({"priority": "high", "title": "增强小红书可读性", "example": "补充清单、步骤、避坑或对比，让内容更适合收藏。"})
        if publish_score < 10:
            suggestions.append({"priority": "medium", "title": "补齐发布要素", "example": "至少补充封面/图片、2-5 个话题标签和明确结尾引导。"})
        if not suggestions:
            suggestions.append({"priority": "medium", "title": "优先优化开头和结尾互动", "example": "开头进入具体场景，结尾增加一个用户容易回答的问题。"})

        return {
            "overall_score": total,
            "potential_level": _potential_level(total),
            "summary": "系统已根据草稿结构、机会证据、GEO 资产价值和发布完整度生成基础打分。",
            "dimensions": dimensions,
            "risks": risks,
            "suggestions": suggestions,
            "opportunities": [
                {"type": "keyword", "label": term, "reason": "草稿与现有关键词或内容机会命中。"}
                for term in matched_terms[:6]
            ],
            "disclaimer": DISCLAIMER,
            "fallback_used": True,
        }

    def build_ai_score_prompt(self, draft: AiDraft, assets: list[DraftAsset], opportunities: dict[str, Any], rule_result: dict[str, Any]) -> tuple[str, str]:
        system_prompt = (
            "你是小红书草稿系统打分助手。你的任务是做发布前内容诊断和爆款潜力评估，"
            "不是预测真实流量。不得承诺必爆、不得编造未提供的数据。只输出严格 JSON。"
        )
        context = {
            "draft": {
                "id": draft.id,
                "title": draft.title,
                "body": draft.body,
                "tags": draft.tags or [],
                "source_note_id": draft.source_note_id,
            },
            "assets": [_asset_payload(asset) for asset in assets[:18]],
            "virtual_content_opportunities": opportunities,
            "rule_baseline": rule_result,
            "required_schema": {
                "overall_score": "0-100 integer",
                "potential_level": "low|medium|high|excellent",
                "summary": "short Chinese summary",
                "dimensions": [{"key": "opportunity_fit|xhs_content|geo_asset|publish_readiness", "label": "string", "score": "integer", "max_score": "integer", "reason": "string"}],
                "risks": [{"level": "low|medium|high", "title": "string", "detail": "string"}],
                "suggestions": [{"priority": "low|medium|high", "title": "string", "example": "string"}],
                "opportunities": [{"type": "keyword|note|comment|analysis|report", "label": "string", "reason": "string"}],
                "disclaimer": DISCLAIMER,
            },
        }
        return system_prompt, json.dumps(context, ensure_ascii=False, default=str)

    def normalize_ai_score_result(self, ai_result: dict[str, Any], rule_result: dict[str, Any]) -> dict[str, Any]:
        result = dict(rule_result)
        overall_score = _clamp_score(ai_result.get("overall_score", rule_result.get("overall_score", 0)))
        result["overall_score"] = overall_score
        result["potential_level"] = str(ai_result.get("potential_level") or _potential_level(overall_score))
        if result["potential_level"] not in {"low", "medium", "high", "excellent"}:
            result["potential_level"] = _potential_level(overall_score)
        result["summary"] = _as_text(ai_result.get("summary") or rule_result.get("summary"), 300)
        result["dimensions"] = self._normalize_dimensions(ai_result.get("dimensions"), rule_result.get("dimensions") or [])
        result["risks"] = self._normalize_list(ai_result.get("risks"), rule_result.get("risks") or [], ("level", "title", "detail"), limit=6)
        result["suggestions"] = self._normalize_list(ai_result.get("suggestions"), rule_result.get("suggestions") or [], ("priority", "title", "example"), limit=6)
        result["opportunities"] = self._normalize_list(ai_result.get("opportunities"), rule_result.get("opportunities") or [], ("type", "label", "reason"), limit=8)
        result["disclaimer"] = DISCLAIMER
        result["fallback_used"] = False
        return result

    def _normalize_dimensions(self, value: Any, fallback: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_key = {str(item.get("key")): item for item in value if isinstance(item, dict)} if isinstance(value, list) else {}
        dimensions = []
        fallback_by_key = {item["key"]: item for item in fallback if isinstance(item, dict) and item.get("key")}
        for key, label, max_score in DIMENSION_SPECS:
            source = by_key.get(key) or fallback_by_key.get(key) or {}
            dimensions.append({
                "key": key,
                "label": str(source.get("label") or label),
                "score": _clamp_score(source.get("score"), 0, max_score),
                "max_score": _clamp_score(source.get("max_score") or max_score, max_score, max_score),
                "reason": _as_text(source.get("reason") or "系统根据草稿和上下文生成该项评分。", 220),
            })
        return dimensions

    def _normalize_list(self, value: Any, fallback: list[dict[str, Any]], keys: tuple[str, ...], limit: int) -> list[dict[str, Any]]:
        source = value if isinstance(value, list) and value else fallback
        items: list[dict[str, Any]] = []
        for raw in source:
            if not isinstance(raw, dict):
                continue
            item = {key: _as_text(raw.get(key), 240) for key in keys}
            if any(item.values()):
                items.append(item)
            if len(items) >= limit:
                break
        return items

    def score_draft_content(
        self,
        *,
        db: Session,
        current_user: User,
        draft: AiDraft,
        assets: list[DraftAsset],
        model_config: ModelConfig,
        api_key: str,
        text_client: TextAiClient,
    ) -> dict[str, Any]:
        opportunities = self.collect_virtual_content_opportunities(db, current_user, draft)
        rule_result = self.build_rule_diagnosis(draft, assets, opportunities)
        system_prompt, user_prompt = self.build_ai_score_prompt(draft, assets, opportunities, rule_result)
        ai_error = ""
        try:
            content = text_client.complete_json_prompt(
                model_config=model_config,
                api_key=api_key,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.2,
            )
            ai_result = _extract_json_object(content)
            result = self.normalize_ai_score_result(ai_result, rule_result)
        except Exception as exc:
            ai_error = str(exc)
            result = dict(rule_result)
            result["fallback_used"] = True
        return {
            "result": result,
            "rule_snapshot": rule_result,
            "opportunity_snapshot": opportunities,
            "ai_error": ai_error,
        }

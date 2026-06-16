from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.time import shanghai_now
from backend.app.models.keyword_group import KeywordGroup
from backend.app.models.note import Note, NoteComment

MINIMUM_THRESHOLDS = {
    "valid_notes": 10,
    "comments": 30,
    "keyword_coverage": 3,
    "representative_notes": 1,
}

STANDARD_THRESHOLDS = {
    "valid_notes": 30,
    "comments": 100,
    "keyword_coverage": 5,
    "high_engagement_notes": 3,
}


@dataclass(frozen=True)
class AnalysisScope:
    keyword_group: KeywordGroup
    notes: list[Note]
    comments_by_note_id: dict[int, list[NoteComment]]
    excluded_note_ids: set[int]


class AnalysisValidationError(ValueError):
    pass


class XhsAnalysisCenterService:
    def __init__(self, db: Session):
        self.db = db

    def check_health(self, *, user_id: int, keyword_group_id: int, excluded_note_ids: list[int] | None = None) -> dict[str, Any]:
        scope = self._resolve_scope(user_id=user_id, keyword_group_id=keyword_group_id, excluded_note_ids=excluded_note_ids or [])
        covered_keywords = self._covered_keywords(scope.keyword_group.keywords or [], scope.notes, scope.comments_by_note_id)
        engagements = [self._note_engagement(note) for note in scope.notes]
        high_engagement_note_ids = self._high_engagement_note_ids(scope.notes)
        representative_count = len(high_engagement_note_ids) if high_engagement_note_ids else min(len(scope.notes), 3)
        comment_count = sum(len(items) for items in scope.comments_by_note_id.values())

        metrics = {
            "valid_note_count": len(scope.notes),
            "comment_count": comment_count,
            "covered_keyword_count": len(covered_keywords),
            "representative_note_count": representative_count,
            "high_engagement_note_count": len(high_engagement_note_ids),
            "total_engagement": sum(engagements),
        }
        missing = self._missing_health_items(metrics)
        if missing:
            status = "insufficient"
            can_generate = False
            confidence_cap = "none"
        elif self._meets_standard(metrics):
            status = "standard"
            can_generate = True
            confidence_cap = "high"
        else:
            status = "minimum"
            can_generate = True
            confidence_cap = "medium"

        warnings = []
        if status == "minimum":
            warnings.append("样本未达标准阈值，结论仅供初筛")
        if len(high_engagement_note_ids) < STANDARD_THRESHOLDS["high_engagement_notes"]:
            warnings.append("整体互动样本偏少，高互动结论置信度有限")

        return {
            "status": status,
            "can_generate": can_generate,
            "confidence_cap": confidence_cap,
            "metrics": metrics,
            "missing": missing,
            "warnings": warnings,
            "collection_plan": self.create_collection_plan(metrics=metrics, keywords=scope.keyword_group.keywords or []),
        }

    def _resolve_scope(self, *, user_id: int, keyword_group_id: int, excluded_note_ids: list[int]) -> AnalysisScope:
        keyword_group = self.db.scalar(
            select(KeywordGroup).where(
                KeywordGroup.id == keyword_group_id,
                KeywordGroup.user_id == user_id,
                KeywordGroup.platform == "xhs",
            )
        )
        if keyword_group is None:
            raise AnalysisValidationError("Keyword group not found")

        keywords = [str(item).strip() for item in (keyword_group.keywords or []) if str(item).strip()]
        excluded = {int(item) for item in excluded_note_ids}
        note_stmt = select(Note).where(Note.user_id == user_id, Note.platform == "xhs")
        notes = [note for note in self.db.scalars(note_stmt).all() if note.id not in excluded and self._note_matches_keywords(note, keywords)]
        note_ids = [note.id for note in notes]
        comments_by_note_id: dict[int, list[NoteComment]] = {note_id: [] for note_id in note_ids}
        if note_ids:
            comments = self.db.scalars(select(NoteComment).where(NoteComment.note_id.in_(note_ids))).all()
            for comment in comments:
                comments_by_note_id.setdefault(comment.note_id, []).append(comment)
        return AnalysisScope(keyword_group=keyword_group, notes=notes, comments_by_note_id=comments_by_note_id, excluded_note_ids=excluded)

    def _note_matches_keywords(self, note: Note, keywords: list[str]) -> bool:
        if not keywords:
            return False
        haystack = f"{note.title}\n{note.content}".lower()
        return any(keyword.lower() in haystack for keyword in keywords)

    def _covered_keywords(self, keywords: list[str], notes: list[Note], comments_by_note_id: dict[int, list[NoteComment]]) -> set[str]:
        covered: set[str] = set()
        for keyword in keywords:
            needle = keyword.lower()
            for note in notes:
                note_text = f"{note.title}\n{note.content}".lower()
                comment_text = "\n".join(comment.content for comment in comments_by_note_id.get(note.id, [])).lower()
                if needle in note_text or needle in comment_text:
                    covered.add(keyword)
                    break
        return covered

    def _note_engagement(self, note: Note) -> int:
        raw = note.raw_json or {}
        keys = [
            "liked_count",
            "like_count",
            "likes",
            "collected_count",
            "collect_count",
            "collects",
            "comment_count",
            "comments",
            "share_count",
            "shares",
        ]
        total = 0
        for key in keys:
            value = raw.get(key)
            if isinstance(value, int):
                total += value
            elif isinstance(value, str) and value.isdigit():
                total += int(value)
        return total

    def _high_engagement_note_ids(self, notes: list[Note]) -> set[int]:
        if not notes:
            return set()
        scored = sorted(((note.id, self._note_engagement(note)) for note in notes), key=lambda item: item[1], reverse=True)
        top_count = max(1, int(len(scored) * 0.1))
        return {note_id for note_id, engagement in scored[:top_count] if engagement >= 50}

    def _missing_health_items(self, metrics: dict[str, int]) -> list[dict[str, int | str]]:
        checks = [
            ("valid_notes", "有效笔记不足", metrics["valid_note_count"], MINIMUM_THRESHOLDS["valid_notes"]),
            ("comments", "评论不足", metrics["comment_count"], MINIMUM_THRESHOLDS["comments"]),
            ("keyword_coverage", "覆盖关键词不足", metrics["covered_keyword_count"], MINIMUM_THRESHOLDS["keyword_coverage"]),
            ("representative_notes", "代表性样本不足", metrics["representative_note_count"], MINIMUM_THRESHOLDS["representative_notes"]),
        ]
        return [{"key": key, "message": message, "current": current, "required": required} for key, message, current, required in checks if current < required]

    def _meets_standard(self, metrics: dict[str, int]) -> bool:
        return (
            metrics["valid_note_count"] >= STANDARD_THRESHOLDS["valid_notes"]
            and metrics["comment_count"] >= STANDARD_THRESHOLDS["comments"]
            and metrics["covered_keyword_count"] >= STANDARD_THRESHOLDS["keyword_coverage"]
            and metrics["high_engagement_note_count"] >= STANDARD_THRESHOLDS["high_engagement_notes"]
        )

    def build_evidence_pool(self, *, user_id: int, keyword_group_id: int, excluded_note_ids: list[int] | None = None) -> dict[str, Any]:
        scope = self._resolve_scope(user_id=user_id, keyword_group_id=keyword_group_id, excluded_note_ids=excluded_note_ids or [])
        keywords = [str(item).strip() for item in (scope.keyword_group.keywords or []) if str(item).strip()]
        note_items = []
        comment_items = []
        for note in scope.notes:
            matched_keywords = self._matched_keywords_for_text(f"{note.title}\n{note.content}", keywords)
            note_items.append(
                {
                    "evidence_id": f"note:{note.id}",
                    "note_id": note.id,
                    "title": note.title,
                    "author_name": note.author_name,
                    "likes": self._raw_int(note.raw_json or {}, ["liked_count", "like_count", "likes"]),
                    "collects": self._raw_int(note.raw_json or {}, ["collected_count", "collect_count", "collects"]),
                    "comments": self._raw_int(note.raw_json or {}, ["comment_count", "comments"]),
                    "shares": self._raw_int(note.raw_json or {}, ["share_count", "shares"]),
                    "engagement": self._note_engagement(note),
                    "matched_keywords": matched_keywords,
                    "excerpt": self._excerpt(note.content or note.title),
                }
            )
            for comment in scope.comments_by_note_id.get(note.id, []):
                comment_items.append(
                    {
                        "evidence_id": f"comment:{comment.id}",
                        "comment_id": comment.id,
                        "note_id": note.id,
                        "content": comment.content,
                        "like_count": comment.like_count,
                        "signals": self._comment_signals(comment.content),
                    }
                )

        keyword_items = []
        for keyword in keywords:
            matched_notes = [note for note in scope.notes if keyword.lower() in f"{note.title}\n{note.content}".lower()]
            matched_comments = [item for item in comment_items if keyword.lower() in str(item["content"]).lower()]
            keyword_items.append({"evidence_id": f"keyword:{keyword}", "keyword": keyword, "matched_notes": len(matched_notes), "matched_comments": len(matched_comments)})

        metrics = self._metric_evidence(scope, comment_items)
        return {"notes": note_items, "comments": comment_items, "keywords": keyword_items, "metrics": metrics, "benchmarks": []}

    def _raw_int(self, raw: dict[str, Any], keys: list[str]) -> int:
        for key in keys:
            value = raw.get(key)
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
        return 0

    def _matched_keywords_for_text(self, text: str, keywords: list[str]) -> list[str]:
        lower = text.lower()
        return [keyword for keyword in keywords if keyword.lower() in lower]

    def _excerpt(self, text: str, limit: int = 120) -> str:
        normalized = " ".join(text.split())
        return normalized[:limit]

    def _comment_signals(self, content: str) -> list[str]:
        text = content.lower()
        rules = [
            ("question", ["?", "？", "怎么", "如何", "有没有", "能不能", "吗"]),
            ("price_intent", ["多少钱", "价格", "贵", "便宜"]),
            ("purchase_intent", ["怎么买", "链接", "店铺", "下单", "购买"]),
            ("suitability", ["适合", "能不能用", "可以用"]),
            ("comparison", ["哪个好", "对比", "还是", "区别"]),
            ("complaint", ["踩坑", "不好用", "失败", "报错", "吐槽"]),
            ("beginner_need", ["新手", "小白", "入门", "保姆级"]),
            ("scenario", ["上班", "副业", "学生", "宝妈", "程序员", "团队"]),
        ]
        return [signal for signal, needles in rules if any(needle in text for needle in needles)]

    def _metric_evidence(self, scope: AnalysisScope, comment_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        total_comments = len(comment_items)
        question_count = sum(1 for item in comment_items if "question" in item["signals"])
        beginner_count = sum(1 for item in comment_items if "beginner_need" in item["signals"])
        purchase_count = sum(1 for item in comment_items if "purchase_intent" in item["signals"] or "price_intent" in item["signals"])
        return [
            {"evidence_id": "metric:valid_note_count", "name": "valid_note_count", "value": len(scope.notes), "description": "参与分析的有效笔记数"},
            {"evidence_id": "metric:comment_count", "name": "comment_count", "value": total_comments, "description": "参与分析的评论数"},
            {"evidence_id": "metric:question_rate", "name": "question_rate", "value": round(question_count / total_comments, 4) if total_comments else 0, "description": "评论中提问评论占比"},
            {"evidence_id": "metric:beginner_need_rate", "name": "beginner_need_rate", "value": round(beginner_count / total_comments, 4) if total_comments else 0, "description": "评论中新手需求占比"},
            {"evidence_id": "metric:purchase_intent_rate", "name": "purchase_intent_rate", "value": round(purchase_count / total_comments, 4) if total_comments else 0, "description": "评论中购买或价格意图占比"},
        ]

    def validate_ai_result(self, result: dict[str, Any], *, evidence_pool: dict[str, Any], confidence_cap: str) -> dict[str, Any]:
        if not isinstance(result, dict):
            raise AnalysisValidationError("AI result must be an object")
        for key in ["summary", "insight_cards", "topic_cards", "report_warnings"]:
            if key not in result:
                raise AnalysisValidationError(f"Missing result field: {key}")
        summary = result["summary"]
        if not isinstance(summary, dict):
            raise AnalysisValidationError("summary must be an object")
        for key in ["facts", "inferences", "recommendations"]:
            if not isinstance(summary.get(key), list):
                raise AnalysisValidationError(f"summary.{key} must be a list")
        insight_cards = result["insight_cards"]
        topic_cards = result["topic_cards"]
        if not isinstance(insight_cards, list) or len(insight_cards) > 5:
            raise AnalysisValidationError("insight_cards must be a list with at most 5 items")
        if not isinstance(topic_cards, list) or len(topic_cards) > 15:
            raise AnalysisValidationError("topic_cards must be a list with at most 15 items")
        if not isinstance(result["report_warnings"], list):
            raise AnalysisValidationError("report_warnings must be a list")

        known_ids = self._known_evidence_ids(evidence_pool)
        for item in summary["facts"]:
            self._require_evidence(item, known_ids, "summary facts")
        for item in summary["inferences"]:
            self._require_evidence(item, known_ids, "summary inferences")
        for item in summary["recommendations"]:
            self._require_evidence(item, known_ids, "summary recommendations")
        for card in insight_cards:
            self._validate_insight_card(card, known_ids, confidence_cap)
        topic_ids = {card.get("id") for card in topic_cards if isinstance(card, dict)}
        for card in topic_cards:
            self._validate_topic_card(card, known_ids)
        for card in insight_cards:
            for topic_id in card.get("topic_card_ids", []):
                if topic_id not in topic_ids:
                    raise AnalysisValidationError(f"Unknown topic_card_id: {topic_id}")
        return result

    def _known_evidence_ids(self, evidence_pool: dict[str, Any]) -> set[str]:
        ids: set[str] = set()
        for key in ["notes", "comments", "keywords", "metrics", "benchmarks"]:
            for item in evidence_pool.get(key, []):
                if not isinstance(item, dict):
                    continue
                evidence_id = item.get("evidence_id")
                if isinstance(evidence_id, str):
                    ids.add(evidence_id)
        return ids

    def _require_evidence(self, item: dict[str, Any], known_ids: set[str], label: str) -> None:
        if not isinstance(item, dict):
            raise AnalysisValidationError(f"{label} must be an object")
        evidence_ids = item.get("evidence_ids")
        if not isinstance(evidence_ids, list) or not evidence_ids:
            raise AnalysisValidationError(f"{label} must include evidence_ids")
        for evidence_id in evidence_ids:
            if evidence_id not in known_ids:
                raise AnalysisValidationError(f"Unknown evidence_id: {evidence_id}")

    def _validate_score(self, value: Any, label: str) -> None:
        if not isinstance(value, int) or value < 0 or value > 100:
            raise AnalysisValidationError(f"{label} must be an integer from 0 to 100")

    def _validate_insight_card(self, card: dict[str, Any], known_ids: set[str], confidence_cap: str) -> None:
        if not isinstance(card, dict):
            raise AnalysisValidationError("insight card must be an object")
        for key in ["id", "title", "confidence", "confidence_reason", "evidence_ids", "topic_card_ids"]:
            if key not in card:
                raise AnalysisValidationError(f"Missing insight card field: {key}")
        self._validate_score(card.get("score"), "insight score")
        sub_scores = card.get("sub_scores")
        if not isinstance(sub_scores, dict):
            raise AnalysisValidationError("sub_scores must be an object")
        for key in ["traffic_potential", "demand_strength", "competition_pressure", "actionability"]:
            self._validate_score(sub_scores.get(key), f"sub_scores.{key}")
        confidence = card.get("confidence")
        if confidence not in ["low", "medium", "high"]:
            raise AnalysisValidationError("Invalid confidence")
        if confidence_cap == "medium" and confidence == "high":
            raise AnalysisValidationError("Insight confidence exceeds confidence cap")
        topic_card_ids = card.get("topic_card_ids")
        if not isinstance(topic_card_ids, list):
            raise AnalysisValidationError("topic_card_ids must be a list")
        self._require_evidence(card, known_ids, "insight card")

    def _validate_topic_card(self, card: dict[str, Any], known_ids: set[str]) -> None:
        if not isinstance(card, dict):
            raise AnalysisValidationError("topic card must be an object")
        required = [
            "id",
            "insight_id",
            "title_direction",
            "target_pain",
            "content_angle",
            "recommended_structure",
            "recommended_content_form",
            "tags",
            "cover_suggestion",
            "expected_advantage",
            "risk_warning",
            "evidence_ids",
        ]
        for key in required:
            if key not in card:
                raise AnalysisValidationError(f"Missing topic card field: {key}")
        if not isinstance(card["recommended_structure"], list) or not card["recommended_structure"]:
            raise AnalysisValidationError("recommended_structure must be a non-empty list")
        if not isinstance(card["recommended_content_form"], list):
            raise AnalysisValidationError("recommended_content_form must be a list")
        if not isinstance(card["tags"], list):
            raise AnalysisValidationError("tags must be a list")
        self._require_evidence(card, known_ids, "topic card")

    def create_report(self, *, user_id: int, payload: dict[str, Any], model_config: Any | None, api_key: str, ai_client: Any) -> Any:
        from backend.app.models.analysis_report import AnalysisReport

        keyword_group_id = int(payload["keyword_group_id"])
        excluded_note_ids = [int(item) for item in payload.get("excluded_note_ids", [])]
        title = str(payload.get("title") or "小红书分析报告")
        report = AnalysisReport(
            user_id=user_id,
            platform="xhs",
            report_type="content_analysis",
            status="running",
            title=title,
            input_config=self._input_config(keyword_group_id=keyword_group_id, excluded_note_ids=excluded_note_ids, payload=payload),
            started_at=shanghai_now(),
            html_file_path="",
        )
        self.db.add(report)
        self.db.commit()
        self.db.refresh(report)

        health = self.check_health(user_id=user_id, keyword_group_id=keyword_group_id, excluded_note_ids=excluded_note_ids)
        evidence_pool = self.build_evidence_pool(user_id=user_id, keyword_group_id=keyword_group_id, excluded_note_ids=excluded_note_ids)
        report.data_health = health
        report.evidence_pool = evidence_pool

        try:
            if not health["can_generate"]:
                raise AnalysisValidationError("数据低于最低门槛，未调用模型")
            if model_config is None:
                raise AnalysisValidationError("Default text model is not configured")
            raw_text = ai_client.complete_json_prompt(
                model_config=model_config,
                api_key=api_key,
                system_prompt=self._analysis_system_prompt(),
                user_prompt=self._analysis_user_prompt(health=health, evidence_pool=evidence_pool, input_config=report.input_config or {}),
                temperature=0.2,
            )
            result = self._parse_json_result(raw_text)
            report.result_json = self.validate_ai_result(result, evidence_pool=evidence_pool, confidence_cap=health["confidence_cap"])
            report.html_file_path = self._write_report_html(
                user_id=user_id,
                report_id=report.id,
                title=report.title,
                data_health=health,
                evidence_pool=evidence_pool,
                result_json=report.result_json,
            )
            report.status = "completed"
            report.error_message = None
        except Exception as exc:
            report.status = "failed"
            report.error_message = str(exc)
            report.result_json = None
        finally:
            report.finished_at = shanghai_now()
            self.db.add(report)
            self.db.commit()
            self.db.refresh(report)
        return report

    def create_drafts_from_topic_cards(self, *, user_id: int, topic_cards: list[dict[str, Any]]) -> list[Any]:
        from backend.app.models.ai import AiDraft

        drafts = []
        for card in topic_cards:
            title = self._draft_text(card.get("title_direction") or "小红书选题草稿骨架")[:256]
            tags = [{"name": self._draft_text(tag)} for tag in card.get("tags", []) if self._draft_text(tag)]
            structure = card.get("recommended_structure", [])
            if not isinstance(structure, list):
                structure = []
            content_forms = card.get("recommended_content_form", [])
            if not isinstance(content_forms, list):
                content_forms = []
            evidence_ids = card.get("evidence_ids", [])
            if not isinstance(evidence_ids, list):
                evidence_ids = []

            body = "\n".join(
                [
                    "草稿类型：选题草稿骨架，仅用于后续人工编辑扩写。",
                    f"标题方向：{title}",
                    f"目标用户痛点：{self._draft_text(card.get('target_pain', ''))}",
                    f"内容角度：{self._draft_text(card.get('content_angle', ''))}",
                    "正文结构大纲：",
                    *[f"- {self._draft_text(item)}" for item in structure],
                    f"推荐内容形态：{', '.join(self._draft_text(item) for item in content_forms)}",
                    f"封面建议：{self._draft_text(card.get('cover_suggestion', ''))}",
                    f"预期优势：{self._draft_text(card.get('expected_advantage', ''))}",
                    f"参考证据：{', '.join(self._draft_text(item) for item in evidence_ids)}",
                    f"风险提醒：{self._draft_text(card.get('risk_warning', ''))}",
                ]
            )
            draft = AiDraft(user_id=user_id, platform="xhs", title=title, body=body, tags=tags, source_note_id=None)
            self.db.add(draft)
            drafts.append(draft)
        self.db.commit()
        for draft in drafts:
            self.db.refresh(draft)
        return drafts

    def _draft_text(self, value: Any) -> str:
        return str(value).replace("完整正文", "正文").strip()

    def _write_report_html(
        self,
        *,
        user_id: int,
        report_id: int,
        title: str,
        data_health: dict[str, Any],
        evidence_pool: dict[str, Any],
        result_json: dict[str, Any],
    ) -> str:
        from pathlib import Path

        from backend.app.core.config import get_settings
        from backend.app.services.xhs_analysis_report_renderer import render_xhs_analysis_report_html

        settings = get_settings()
        export_dir = Path(settings.storage_dir) / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        file_path = export_dir / f"xhs-analysis-report-u{user_id}-{report_id}.html"
        html = render_xhs_analysis_report_html(title=title, data_health=data_health, evidence_pool=evidence_pool, result_json=result_json)
        file_path.write_text(html, encoding="utf-8")
        return str(file_path)

    def _input_config(self, *, keyword_group_id: int, excluded_note_ids: list[int], payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "keyword_group_id": keyword_group_id,
            "excluded_note_ids": excluded_note_ids,
            "source_note_ids": payload.get("source_note_ids", []),
            "benchmark_target_ids": payload.get("benchmark_target_ids", []),
            "thresholds": {"minimum": MINIMUM_THRESHOLDS, "standard": STANDARD_THRESHOLDS},
            "topic_cards_per_insight": 3,
            "max_insight_cards": 5,
        }

    def _parse_json_result(self, raw_text: str) -> dict[str, Any]:
        import json

        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise AnalysisValidationError("模型输出不是合法 JSON") from exc
        if not isinstance(parsed, dict):
            raise AnalysisValidationError("模型输出 JSON 必须是对象")
        return parsed

    def _analysis_system_prompt(self) -> str:
        return "\n".join(
            [
                "你是小红书内容分析助手。你只能基于输入 evidence_pool 中的证据做分析。",
                "任何事实结论都必须引用 evidence_id。",
                "不要编造数据、评论、笔记、用户反馈、行业基准或报告结论。",
                "如果证据不足，少输出或降低置信度，不要补全。",
                "输出必须是符合 JSON Schema 的 JSON，不要 Markdown。",
                "必须区分 facts、inferences、recommendations。",
            ]
        )

    def _analysis_user_prompt(self, *, health: dict[str, Any], evidence_pool: dict[str, Any], input_config: dict[str, Any]) -> str:
        import json

        schema_hint = {
            "summary": {"facts": [], "inferences": [], "recommendations": []},
            "insight_cards": "最多 5 个，每个包含 score/sub_scores/confidence/evidence_ids/topic_card_ids",
            "topic_cards": "每个洞察最多 3 个，总数最多 15 个",
            "report_warnings": [],
        }
        payload = {"data_health": health, "input_config": input_config, "evidence_pool": evidence_pool, "required_shape": schema_hint}
        return json.dumps(payload, ensure_ascii=False)

    def create_collection_plan(self, *, metrics: dict[str, int], keywords: list[str]) -> dict[str, Any]:
        needed = bool(self._missing_health_items(metrics))
        missing_notes = max(0, MINIMUM_THRESHOLDS["valid_notes"] - metrics["valid_note_count"])
        missing_comments = max(0, MINIMUM_THRESHOLDS["comments"] - metrics["comment_count"])
        recommended_keywords = keywords[: max(1, MINIMUM_THRESHOLDS["keyword_coverage"] - metrics["covered_keyword_count"])] if needed else []
        return {
            "needed": needed,
            "recommended_keywords": recommended_keywords,
            "recommended_notes_per_keyword": max(0, (missing_notes + max(1, len(recommended_keywords)) - 1) // max(1, len(recommended_keywords))) if needed else 0,
            "should_collect_comments": missing_comments > 0,
        }

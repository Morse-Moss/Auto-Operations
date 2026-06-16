from __future__ import annotations

from html import escape
from typing import Any


def render_xhs_analysis_report_html(*, title: str, data_health: dict[str, Any], evidence_pool: dict[str, Any], result_json: dict[str, Any]) -> str:
    summary = result_json.get("summary", {})
    insight_cards = result_json.get("insight_cards", [])
    topic_cards = result_json.get("topic_cards", [])
    warnings = list(data_health.get("warnings", [])) + list(result_json.get("report_warnings", []))
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="zh-CN">',
            "<head>",
            '<meta charset="utf-8" />',
            f"<title>{escape(title)}</title>",
            "<style>body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:1080px;margin:0 auto;padding:32px;color:#1f1f1f;}section{margin:24px 0;padding:20px;border:1px solid #eee;border-radius:12px;}h1,h2,h3{margin-top:0}.card{margin:12px 0;padding:14px;background:#fafafa;border-radius:10px}.muted{color:#666}.warning{color:#ad6800;background:#fff7e6;padding:10px;border-radius:8px}</style>",
            "</head>",
            "<body>",
            f"<h1>{escape(title)}</h1>",
            f"<p class=\"muted\">数据健康状态：{escape(str(data_health.get('status', 'unknown')))}</p>",
            _render_warnings(warnings),
            _render_summary(summary),
            _render_insights(insight_cards),
            _render_topics(topic_cards),
            _render_evidence(evidence_pool),
            "<section><h2>免责声明</h2><p>报告基于当前已采集数据生成，未采集到的数据不会被推断为事实，样本不足时结论仅供初筛。</p></section>",
            "</body></html>",
        ]
    )


def _render_warnings(warnings: list[Any]) -> str:
    if not warnings:
        return ""
    items = "".join(f"<li>{escape(str(item))}</li>" for item in warnings)
    return f'<section class="warning"><h2>样本限制与风险提醒</h2><ul>{items}</ul></section>'


def _render_summary(summary: dict[str, Any]) -> str:
    blocks = []
    for key, label in [("facts", "事实"), ("inferences", "推断"), ("recommendations", "建议")]:
        items = "".join(
            f"<li>{escape(str(item.get('text', '')))} <span class=\"muted\">{escape(', '.join(str(evidence_id) for evidence_id in item.get('evidence_ids', [])))}</span></li>"
            for item in summary.get(key, [])
            if isinstance(item, dict)
        )
        blocks.append(f"<h3>{label}</h3><ul>{items}</ul>")
    return f"<section><h2>核心总结</h2>{''.join(blocks)}</section>"


def _render_insights(cards: list[dict[str, Any]]) -> str:
    body = "".join(
        f"<div class=\"card\"><h3>{escape(str(card.get('title', '')))}</h3><p>综合分：{escape(str(card.get('score', '')))} / 置信度：{escape(str(card.get('confidence', '')))}</p><p>{escape(str(card.get('confidence_reason', '')))}</p><p class=\"muted\">证据：{escape(', '.join(str(evidence_id) for evidence_id in card.get('evidence_ids', [])))}</p></div>"
        for card in cards
        if isinstance(card, dict)
    )
    return f"<section><h2>洞察卡</h2>{body}</section>"


def _render_topics(cards: list[dict[str, Any]]) -> str:
    body = "".join(
        f"<div class=\"card\"><h3>{escape(str(card.get('title_direction', '')))}</h3><p><strong>痛点：</strong>{escape(str(card.get('target_pain', '')))}</p><p><strong>角度：</strong>{escape(str(card.get('content_angle', '')))}</p><p><strong>风险：</strong>{escape(str(card.get('risk_warning', '')))}</p></div>"
        for card in cards
        if isinstance(card, dict)
    )
    return f"<section><h2>选题卡</h2>{body}</section>"


def _render_evidence(pool: dict[str, Any]) -> str:
    notes = "".join(f"<li>{escape(str(note.get('evidence_id', '')))}：{escape(str(note.get('title', '')))}</li>" for note in pool.get("notes", [])[:10] if isinstance(note, dict))
    return f"<section><h2>代表性证据</h2><ul>{notes}</ul></section>"

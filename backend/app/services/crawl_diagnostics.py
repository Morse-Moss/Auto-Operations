from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlparse

from sqlalchemy.orm import Session

from backend.app.models import CrawlDiagnostic
from backend.app.services.xhs_detail_recovery import classify_source_url, mask_xsec_token, summarize_payload

SENSITIVE_KEYS = {
    "cookie",
    "cookies",
    "authorization",
    "access_token",
    "refresh_token",
    "token",
    "api_key",
    "apikey",
    "secret",
    "password",
    "web_session",
    "customer_session",
    "headers",
    "request_headers",
    "html",
    "html_content",
    "page_html",
    "xsec_token",
}

ALLOWED_SUMMARY_KEYS = {
    "error_code",
    "message",
    "note_id",
    "source_url_kind",
    "has_xsec_token",
    "masked_xsec_token",
    "payload_keys",
    "has_data",
    "item_count",
    "has_content",
    "has_media",
    "has_tags",
    "has_interaction",
}


def _is_sensitive_key(key: object) -> bool:
    normalized = str(key).lower().replace("-", "_")
    return normalized in SENSITIVE_KEYS or "cookie" in normalized or "authorization" in normalized


def _safe_scalar(value: object) -> object:
    if isinstance(value, str) and len(value) > 500:
        return value[:500]
    return value


def redact_diagnostic_raw(value: object) -> dict:
    if not isinstance(value, dict):
        return {}

    redacted: dict[str, Any] = {}
    for key, item in value.items():
        if _is_sensitive_key(key):
            continue
        key_text = str(key)
        if isinstance(item, dict):
            nested = redact_diagnostic_raw(item)
            if nested:
                redacted[key_text] = nested
        elif isinstance(item, list):
            safe_items = []
            for list_item in item[:20]:
                if isinstance(list_item, dict):
                    safe_items.append(redact_diagnostic_raw(list_item))
                elif not isinstance(list_item, str) or "<html" not in list_item.lower():
                    safe_items.append(_safe_scalar(list_item))
            if safe_items:
                redacted[key_text] = safe_items
        elif isinstance(item, str):
            if "<html" in item.lower() or "web_session" in item or "xsec_token" in item:
                continue
            redacted[key_text] = _safe_scalar(item)
        else:
            redacted[key_text] = item
    return redacted


def _first_note_id_from_redacted(value: object) -> str | None:
    if isinstance(value, dict):
        for key in ("note_id", "id", "feed_id", "feedId"):
            item = value.get(key)
            if item:
                return str(item)
        for item in value.values():
            nested = _first_note_id_from_redacted(item)
            if nested:
                return nested
    if isinstance(value, list):
        for item in value:
            nested = _first_note_id_from_redacted(item)
            if nested:
                return nested
    return None


def _top_level_error_code(value: object) -> object | None:
    if not isinstance(value, dict):
        return None
    if value.get("error_code") is not None:
        return value.get("error_code")
    data = value.get("data")
    if isinstance(data, dict):
        return data.get("error_code")
    return None


def _top_level_message(value: object) -> object | None:
    if not isinstance(value, dict):
        return None
    for key in ("message", "msg"):
        if value.get(key):
            return value.get(key)
    data = value.get("data")
    if isinstance(data, dict):
        for key in ("message", "msg"):
            if data.get(key):
                return data.get(key)
    return None


def diagnostic_payload_summary(raw_payload: object, source_url: str = "") -> dict:
    summary = summarize_payload(raw_payload, source_url)
    redacted = redact_diagnostic_raw(raw_payload)
    parsed_url = urlparse(source_url)
    query = parse_qs(parsed_url.query)
    has_xsec_token = bool(query.get("xsec_token")) or bool(summary.get("has_xsec_token"))
    masked = None
    if query.get("xsec_token"):
        masked = mask_xsec_token(query["xsec_token"][0])
    elif summary.get("masked_xsec_token"):
        masked = summary.get("masked_xsec_token")

    safe_summary = {
        "error_code": summary.get("error_code") or _top_level_error_code(raw_payload),
        "message": summary.get("message") or _top_level_message(raw_payload),
        "note_id": summary.get("note_id") or _first_note_id_from_redacted(redacted),
        "source_url_kind": classify_source_url(source_url),
        "has_xsec_token": has_xsec_token,
        "masked_xsec_token": masked,
        "payload_keys": summary.get("payload_keys", []),
        "has_data": summary.get("has_data", False),
        "item_count": summary.get("item_count", 0),
        "has_content": summary.get("has_content", False),
        "has_media": summary.get("has_media", False),
        "has_tags": summary.get("has_tags", False),
        "has_interaction": summary.get("has_interaction", False),
    }
    return {key: value for key, value in safe_summary.items() if key in ALLOWED_SUMMARY_KEYS}


def create_crawl_diagnostic(
    db: Session,
    *,
    user_id: int,
    task_id: int | None,
    platform_account_id: int | None,
    platform: str,
    source: str,
    note_id: str | None,
    note_url: str | None,
    stage: str,
    kind: str,
    severity: str,
    recoverable: bool,
    message: str,
    user_message: str,
    raw_payload: object | None = None,
) -> CrawlDiagnostic:
    diagnostic = CrawlDiagnostic(
        user_id=user_id,
        task_id=task_id,
        platform_account_id=platform_account_id,
        platform=platform,
        source=source,
        note_id=note_id,
        note_url=note_url,
        stage=stage,
        kind=kind,
        severity=severity,
        recoverable=recoverable,
        message=message,
        user_message=user_message,
        raw_json=diagnostic_payload_summary(raw_payload or {}, note_url or source),
    )
    db.add(diagnostic)
    return diagnostic


def serialize_crawl_diagnostic(diagnostic: CrawlDiagnostic) -> dict[str, Any]:
    return {
        "id": diagnostic.id,
        "user_id": diagnostic.user_id,
        "task_id": diagnostic.task_id,
        "platform_account_id": diagnostic.platform_account_id,
        "platform": diagnostic.platform,
        "source": diagnostic.source,
        "note_id": diagnostic.note_id,
        "note_url": diagnostic.note_url,
        "stage": diagnostic.stage,
        "kind": diagnostic.kind,
        "severity": diagnostic.severity,
        "recoverable": diagnostic.recoverable,
        "message": diagnostic.message,
        "user_message": diagnostic.user_message,
        "raw_json": diagnostic.raw_json or {},
        "created_at": diagnostic.created_at.isoformat(),
    }


def quality_summary_from_items(items: list[dict]) -> dict[str, int]:
    success_count = len([item for item in items if item.get("status") == "success"])
    failed_count = len(items) - success_count
    skipped_low_quality_count = len([item for item in items if item.get("save_diagnostic_kind") == "save_skipped_low_quality"])
    return {
        "total": len(items),
        "success_count": success_count,
        "failed_count": failed_count,
        "skipped_low_quality_count": skipped_low_quality_count,
    }

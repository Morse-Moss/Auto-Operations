from __future__ import annotations

import json

from backend.app.platforms.contracts import (
    AdapterError,
    CapabilityDecision,
    CapabilityRequestContext,
)
from backend.app.services.diagnostic_service import (
    diagnostic_from_adapter_error,
    diagnostic_from_capability_decision,
    sanitize_raw_reference,
    standard_diagnostic,
    validation_diagnostic,
)
from backend.app.services.publish_orchestration_service import PublishOrchestrationService


class DummyPolicyService:
    def __init__(self, decision: CapabilityDecision) -> None:
        self.decision = decision

    def evaluate(self, context: CapabilityRequestContext) -> CapabilityDecision:
        return self.decision


class DummyUser:
    id = 7


class DummyJob:
    id = 42
    user_id = 7
    platform = "xhs"
    platform_account_id = None
    title = "   "
    body = ""
    publish_mode = "immediate"
    scheduled_at = None


class EmptyScalars:
    def first(self):
        return DummyJob()

    def all(self):
        return []


class DummyDb:
    def scalars(self, _stmt):
        return EmptyScalars()

    def get(self, *_args):
        return None


def test_standard_diagnostics_cover_recovery_categories_without_raw_payload_leaks() -> None:
    cases = {
        "auth_expired": "重新登录",
        "rate_limited": "稍后重试",
        "signature_failed": "暂停自动动作",
        "risk_blocked": "动作级授权",
        "validation": "修正输入",
    }

    for category, expected_next_action in cases.items():
        payload = standard_diagnostic(
            category,
            platform_id="xhs",
            capability_key="publish.dry_run",
            stage="dry_run",
            correlation_id="corr-1",
            raw_reference={"cookie": "secret-cookie", "xsec_token": "secret-token"},
        ).to_payload()

        assert payload["platform_id"] == "xhs"
        assert payload["capability_key"] == "publish.dry_run"
        assert payload["stage"] == "dry_run"
        assert payload["category"] == category
        assert payload["user_message"]
        assert expected_next_action in payload["next_action"]
        assert payload["correlation_id"] == "corr-1"
        serialized = json.dumps(payload, ensure_ascii=False)
        assert "secret-cookie" not in serialized
        assert "secret-token" not in serialized
        assert "raw_json" not in payload
        assert "details" not in payload


def test_raw_reference_is_reference_only_and_sanitizes_secret_bearing_values() -> None:
    assert sanitize_raw_reference(None) is None
    assert sanitize_raw_reference("api_log:123") == "api_log:123"
    assert sanitize_raw_reference("audit:publish-dry-run:42") == "audit:publish-dry-run:42"
    assert sanitize_raw_reference("task:99") == "task:99"
    assert sanitize_raw_reference("https://example.com/path?xsec_token=abc&web_session=secret") == "https://example.com/path"
    assert sanitize_raw_reference("javascript://example.com/path") is None
    assert sanitize_raw_reference("data://example.com/path") is None
    assert sanitize_raw_reference("ftp://example.com/path") is None
    assert sanitize_raw_reference("https://user:token@example.com/path") is None
    assert sanitize_raw_reference("https://example.com/api-key/abc") is None
    assert sanitize_raw_reference("https://example.com/api/key/abc") is None
    assert sanitize_raw_reference("https://example.com/access-token/abc") is None
    assert sanitize_raw_reference("https://example.com/session/abc") is None
    assert sanitize_raw_reference({"api_key": "secret", "payload": "raw"}) is None
    assert sanitize_raw_reference("cookie=a1=secret; web_session=secret") is None
    assert sanitize_raw_reference("raw_json:{'note_id':'123'}") is None
    assert sanitize_raw_reference("platform_message: upstream changed") is None
    assert sanitize_raw_reference('{"error":"upstream failed"}') is None
    assert sanitize_raw_reference("https://example.com/token/secret") is None
    assert sanitize_raw_reference("plain upstream error message") is None


def test_adapter_error_maps_to_diagnostic_payload_without_platform_private_tokens() -> None:
    error = AdapterError(
        category="signature_failed",
        user_message="签名失败，平台接口可能已变化。",
        platform_message="xsec_token=secret-token signature mismatch",
        retryable=False,
        rate_limited=False,
        credential_invalid=False,
        raw_reference="https://example.com/logs/42?xsec_token=secret-token",
        next_action="暂停自动动作，检查签名适配器。",
    )

    payload = diagnostic_from_adapter_error(
        error,
        platform_id="xhs",
        capability_key="content.discover",
        stage="search",
        correlation_id="corr-adapter",
    ).to_payload()

    assert payload["category"] == "signature_failed"
    assert payload["severity"] == "error"
    assert payload["recoverable"] is False
    assert payload["raw_reference"] == "https://example.com/logs/42"
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "secret-token" not in serialized
    assert "platform_message" not in payload


def test_policy_and_validation_diagnostics_have_next_action_guidance() -> None:
    decision = CapabilityDecision(
        allowed=False,
        blocked_reason="confirmation_required",
        risk_level="high",
        requires_confirmation=True,
        confirmation_required_fields=["confirm_real_publish"],
        effective_dry_run=False,
        account_safety_result=None,
        rate_limit_result=None,
        user_message="该高风险能力需要动作级确认，动作未执行。",
        audit_reference="audit:1",
    )
    context = CapabilityRequestContext(
        user_id=7,
        platform_id="xhs",
        capability_key="publish.real_publish",
        account_ref=None,
        dry_run=False,
        confirmation_token=None,
        request_source="manual",
        correlation_id="corr-policy",
    )

    policy_payload = diagnostic_from_capability_decision(
        decision,
        context=context,
        stage="policy",
    ).to_payload()
    validation_payload = validation_diagnostic(
        platform_id="xhs",
        capability_key="publish.dry_run",
        stage="local_validation",
        correlation_id="corr-validation",
        user_message="发布标题不能为空。",
    ).to_payload()

    assert policy_payload["category"] == "risk_blocked"
    assert policy_payload["severity"] == "blocked"
    assert policy_payload["next_action"] == "确认平台能力和动作级授权后再重试。"
    assert policy_payload["raw_reference"] == "audit:1"
    assert validation_payload["category"] == "validation"
    assert validation_payload["recoverable"] is True
    assert validation_payload["next_action"] == "修正输入后重新执行。"


def test_publish_dry_run_exposes_diagnostics_without_breaking_existing_checks() -> None:
    decision = CapabilityDecision(
        allowed=False,
        blocked_reason="capability_planned",
        risk_level="high",
        requires_confirmation=True,
        confirmation_required_fields=[],
        effective_dry_run=True,
        account_safety_result=None,
        rate_limit_result=None,
        user_message="该能力尚未开放，动作未执行。",
        audit_reference="publish-dry-run:42",
    )

    result = PublishOrchestrationService(
        DummyDb(),
        policy_service=DummyPolicyService(decision),
    ).dry_run(job_id=42, current_user=DummyUser())

    assert result["ok"] is False
    assert result["publish_blocked"] is True
    assert {check["code"] for check in result["checks"]} >= {"policy", "title_required", "asset_required"}
    assert result["diagnostics"][0]["category"] == "risk_blocked"
    assert result["diagnostics"][0]["stage"] == "policy"
    assert result["diagnostics"][0]["next_action"]
    assert any(item["category"] == "validation" for item in result["diagnostics"])

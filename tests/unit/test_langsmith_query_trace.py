"""Query-profile and query-run LangSmith redaction cases."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from smart_rag_core.observability.langsmith_tracing import (
    payload_contains_forbidden_text,
    redact_gateway_inputs,
    short_content_hash,
)

from tests.support.langsmith_scan import (
    CANARY_EMAIL,
    CANARY_PASSAGE,
    CANARY_TOKEN,
)


def test_query_profile_trace_hashes_query_and_memory() -> None:
    """Profile spans hash user text and memory; they never copy raw bodies."""

    from smart_rag_core.gateways.model import QueryProfileModelRequest
    from smart_rag_core.observability.langsmith_tracing import (
        redact_openai_call_inputs,
    )
    from smart_rag_core.query_profile.versions import (
        PROFILE_PROMPT_SHA256,
        PROFILE_PROMPT_VERSION,
    )

    request = QueryProfileModelRequest(
        query=CANARY_PASSAGE,
        prompt_text=CANARY_TOKEN,
        prompt_version=PROFILE_PROMPT_VERSION,
        prompt_sha256=PROFILE_PROMPT_SHA256,
        recent_memory=CANARY_EMAIL,
    )
    gateway_payload = redact_gateway_inputs({"request": request})
    assert gateway_payload["operation"] == "query_profile"
    assert gateway_payload["query_sha256"] == short_content_hash(CANARY_PASSAGE)
    assert gateway_payload["recent_memory_sha256"] == short_content_hash(CANARY_EMAIL)
    assert not payload_contains_forbidden_text(
        gateway_payload, CANARY_TOKEN, CANARY_EMAIL, CANARY_PASSAGE
    )
    helper_payload = redact_openai_call_inputs(
        {
            "api_key": CANARY_TOKEN,
            "prompt_text": CANARY_TOKEN,
            "user_query": CANARY_PASSAGE,
            "recent_memory": CANARY_EMAIL,
            "model_id": "gpt-4o-mini",
            "prompt_version": PROFILE_PROMPT_VERSION,
            "timeout_seconds": 8.0,
        }
    )
    assert helper_payload["model_id"] == "gpt-4o-mini"
    assert helper_payload["user_query_sha256"] == short_content_hash(CANARY_PASSAGE)
    assert helper_payload["recent_memory_sha256"] == short_content_hash(CANARY_EMAIL)
    assert "api_key" not in helper_payload
    assert not payload_contains_forbidden_text(
        helper_payload, CANARY_TOKEN, CANARY_EMAIL, CANARY_PASSAGE
    )


def test_query_run_trace_metadata_is_hashes_and_counts_only() -> None:
    """Query-run traces never copy canary secrets, emails, or passages."""

    from smart_rag_core.observability.query_run_trace import query_run_trace_metadata

    user_id = uuid4()
    run_id = uuid4()
    payload = query_run_trace_metadata(
        run_id=run_id,
        user_id=user_id,
        requested_route="hybrid",
        effective_route="combined",
        corrected_route="hybrid",
        model_versions={"answer": "gpt-4o-mini"},
        prompt_versions={"answer": "answer_v1"},
        disclosed_tools=("structured_table",),
        candidate_counts={"hybrid": 20, "graph": 4},
        bm25_index="search.chunks_v1",
        bm25_version="v1",
        bm25_lag_seconds=3,
        bm25_recheck_count=20,
        bm25_fallback="none",
        latency_ms=1200,
        input_tokens=100,
        output_tokens=40,
        cache_hit=False,
        cost_usd="0.12",
    )
    rendered = json.dumps(payload)
    assert str(user_id) not in rendered
    assert payload["user_id_sha256"] == short_content_hash(str(user_id))
    assert payload["run_id"] == str(run_id)
    assert payload["disclosed_tool_count"] == 1
    assert payload["candidate_counts"]["hybrid"] == 20
    assert not payload_contains_forbidden_text(
        payload, CANARY_TOKEN, CANARY_EMAIL, CANARY_PASSAGE
    )


def test_langsmith_real_content_is_blocked_until_matrix_verified() -> None:
    """Unknown/unverified real-company flows cannot export to LangSmith."""

    from smart_rag_core.observability.governance_gate import (
        ExternalFlowBlockedError,
        assert_langsmith_export_permitted,
        assert_vercel_metadata_has_no_private_payload,
    )
    from smart_rag_core.security.external_processing import ContentClass

    assert_langsmith_export_permitted(
        tracing_enabled=True,
        content_class=ContentClass.SYNTHETIC,
        provider_settings_verified=False,
    )
    assert_langsmith_export_permitted(
        tracing_enabled=True,
        content_class=ContentClass.REAL_COMPANY,
        provider_settings_verified=False,
        local_unsigned_waiver=True,
    )
    with pytest.raises(
        ExternalFlowBlockedError, match="langsmith_real_content_unverified"
    ):
        assert_langsmith_export_permitted(
            tracing_enabled=True,
            content_class=ContentClass.REAL_COMPANY,
            provider_settings_verified=False,
        )
    with pytest.raises(ExternalFlowBlockedError, match="vercel_private_payload"):
        assert_vercel_metadata_has_no_private_payload({"snippet": CANARY_PASSAGE})

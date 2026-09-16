"""Verifier payload parsing must degrade, not crash the Ask run."""

from __future__ import annotations

from typing import cast

import pytest
from smart_rag_agents.prompts import verifier_prompt_text
from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.gateway.verifier import (
    gateway_verifier,
    parse_verifier_payload,
)
from smart_rag_agents.query.nodes.verify import verify_answer_node
from smart_rag_agents.query.state import QueryGraphState, pending_query_state
from smart_rag_core.gateways.model import VerifierModelResponse
from smart_rag_core.query_answer.exceptions import AnswerError
from smart_rag_core.query_answer.models import AnswerCitation, AnswerPayload, AtomicLink
from smart_rag_core.query_answer.schemas import verifier_json_schema
from smart_rag_core.query_fusion import fusion_config_hash
from smart_rag_core.query_fusion.models import (
    FusionAlgorithm,
    FusionResult,
    PassageOrigin,
    ScoredPassage,
)


def _object_map(value: object) -> dict[str, object]:
    """Return a string-keyed mapping from one JSON object.

    Args:
        value: Parsed JSON object.

    Returns:
        Mapping with string keys.

    Raises:
        AssertionError: When ``value`` is not a mapping.
    """

    assert isinstance(value, dict)
    typed = cast(dict[object, object], value)
    return {str(key): item for key, item in typed.items()}


def _fusion() -> FusionResult:
    """Return Hybrid-effective fusion with one canonical passage.

    Returns:
        Frozen fusion result used by verifier gateway tests.
    """

    passage = ScoredPassage(
        chunk_id="00000001-0000-4000-8000-000000000000",
        document_id="00000002-0000-4000-8000-000000000000",
        version_id="00000003-0000-4000-8000-000000000000",
        citation_text="The refund period is 30 days.",
        hybrid_rank=1,
        combined_score=1.0,
        origin=PassageOrigin.HYBRID,
        graph_discovered_only=False,
    )
    return FusionResult(
        algorithm=FusionAlgorithm.RESOLVED_PATH_FUSION,
        config_hash=fusion_config_hash(FusionAlgorithm.RESOLVED_PATH_FUSION),
        requested_route="hybrid",
        effective_route="hybrid",
        evidence=(passage,),
        graph_discovered_only_ratio=0.0,
    )


def _answered_state() -> QueryGraphState:
    """Build answered graph state with one grounded atomic link.

    Returns:
        Query graph state ready for ``verify_answer_node``.
    """

    fusion = _fusion()
    chunk_id = fusion.evidence[0].chunk_id
    state = pending_query_state(user_query="What is the refund period?")
    state["status"] = "answered"
    state["remaining_model_calls"] = 8
    state["fusion"] = fusion.model_dump(mode="json")
    state["answer"] = AnswerPayload(
        answer_text="The refund period is 30 days.",
        citations=(AnswerCitation(chunk_id=chunk_id),),
        atomic_links=(
            AtomicLink(
                link_id="l1",
                claim="The refund period is 30 days.",
                chunk_ids=(chunk_id,),
            ),
        ),
        status="complete",
    ).model_dump(mode="json")
    return state


class _InvalidVerifierGateway:
    """Verifier adapter that returns a non-object verdicts field."""

    async def generate_verifier(self, request: object) -> VerifierModelResponse:
        """Return garbage JSON that must not crash the query graph.

        Args:
            request: Unused structured verifier request.

        Returns:
            Mock response whose payload cannot be a ``VerifierPayload``.
        """

        del request
        return VerifierModelResponse(
            mode="mock",
            payload={"link_verdicts": "nope"},
            request_id="bad-verifier",
            input_tokens=3,
            output_tokens=2,
        )


class _LongReasonVerifierGateway:
    """Verifier adapter that returns an over-long reason plus extra keys."""

    async def generate_verifier(self, request: object) -> VerifierModelResponse:
        """Return a supported verdict that previously failed extra=forbid.

        Args:
            request: Unused structured verifier request.

        Returns:
            Mock response with a 400-character reason and an extra key.
        """

        del request
        return VerifierModelResponse(
            mode="mock",
            payload={
                "link_verdicts": [
                    {
                        "link_id": "l1",
                        "supported": True,
                        "reason": "x" * 400,
                        "confidence": 0.9,
                    }
                ]
            },
            request_id="long-reason",
            input_tokens=3,
            output_tokens=2,
        )


def test_parse_verifier_payload_rejects_garbage() -> None:
    """Non-object verifier JSON fails closed as AnswerError."""

    with pytest.raises(AnswerError, match="verifier_schema_invalid"):
        parse_verifier_payload(["not", "an", "object"])
    with pytest.raises(AnswerError, match="verifier_schema_invalid"):
        parse_verifier_payload({"link_verdicts": "nope"})
    with pytest.raises(AnswerError, match="verifier_schema_invalid"):
        parse_verifier_payload({"link_verdicts": [{"supported": True, "reason": "ok"}]})


def test_parse_verifier_payload_truncates_reason_and_drops_extra() -> None:
    """Long reasons and extra keys stay usable verdicts, not run failures."""

    payload = parse_verifier_payload(
        {
            "link_verdicts": [
                {
                    "link_id": "l1",
                    "supported": False,
                    "reason": "x" * 400,
                    "confidence": 0.4,
                }
            ]
        }
    )
    assert payload.link_verdicts[0].link_id == "l1"
    assert payload.link_verdicts[0].supported is False
    assert payload.link_verdicts[0].reason == "x" * 128


def test_parse_verifier_payload_blank_reason_becomes_unspecified() -> None:
    """Empty verifier reasons are filled instead of raising ValidationError."""

    payload = parse_verifier_payload(
        {"link_verdicts": [{"link_id": "l1", "supported": True, "reason": "  "}]}
    )
    assert payload.link_verdicts[0].reason == "unspecified"


def test_verifier_json_schema_bounds_reason() -> None:
    """OpenAI structured output must cap reason length to the Pydantic field."""

    schema = verifier_json_schema(("l1",))
    properties = _object_map(schema["properties"])
    verdicts = _object_map(properties["link_verdicts"])
    items = _object_map(verdicts["items"])
    item_properties = _object_map(items["properties"])
    reason = _object_map(item_properties["reason"])
    assert reason["minLength"] == 1
    assert reason["maxLength"] == 128


def test_gateway_verifier_keeps_truncated_reason() -> None:
    """Live gateway parsing truncates reasons after the provider returns."""

    fusion = _fusion()
    payload, prompt_tokens, completion_tokens = gateway_verifier(
        QueryGraphDeps(
            model_gateway=_LongReasonVerifierGateway(),
            verifier_prompt_text=verifier_prompt_text(),
        ),
        links=(
            AtomicLink(
                link_id="l1",
                claim="The refund period is 30 days.",
                chunk_ids=(fusion.evidence[0].chunk_id,),
            ),
        ),
        fusion=fusion,
        tables=(),
        context=None,
    )
    assert payload.link_verdicts[0].supported is True
    assert payload.link_verdicts[0].reason == "x" * 128
    assert prompt_tokens == 3
    assert completion_tokens == 2


def test_verify_answer_node_invalid_verifier_is_partial() -> None:
    """Schema-invalid verifier JSON must not emit a generic Ask run failure."""

    verified = verify_answer_node(
        _answered_state(),
        QueryGraphDeps(
            model_gateway=_InvalidVerifierGateway(),
            verifier_prompt_text=verifier_prompt_text(),
        ),
    )
    assert verified["status"] == "verified_partial"
    assert verified["detail"] == "verifier_schema_invalid"
    answer = AnswerPayload.model_validate(verified["answer"])
    assert answer.answer_text == "The refund period is 30 days."


def test_verify_answer_node_invalid_answer_payload_is_partial() -> None:
    """A stored answer that fails extra=forbid still closes as partial."""

    state = pending_query_state(user_query="What is the refund period?")
    state["status"] = "answered"
    state["remaining_model_calls"] = 8
    state["fusion"] = _fusion().model_dump(mode="json")
    state["answer"] = {"answer_text": "kept", "unexpected": True}
    verified = verify_answer_node(state, QueryGraphDeps())
    assert verified["status"] == "verified_partial"
    assert verified["detail"] == "payload_schema_invalid"
    answer = verified["answer"]
    assert isinstance(answer, dict)
    assert answer["answer_text"] == "kept"

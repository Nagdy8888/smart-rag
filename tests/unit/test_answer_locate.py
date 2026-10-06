"""Locate-quote validation, query block, fallback, and skip rules."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.gateway.answer import gateway_answer, gateway_locate
from smart_rag_agents.query.nodes.answer_locate import run_locate_step
from smart_rag_core.gateways.model_types import AnswerModelResponse
from smart_rag_core.query_answer.locate import (
    LOCATED_QUOTES_HEADER,
    LocatedQuote,
    exact_source_quote,
    located_query,
    located_quotes,
    quote_fallback_payload,
)
from smart_rag_core.query_answer.models import AnswerPayload, AtomicLink
from smart_rag_core.query_answer.versions import (
    ANSWER_PROMPT_SHA256,
    ANSWER_PROMPT_VERSION,
    LOCATE_PROMPT_SHA256,
    LOCATE_PROMPT_VERSION,
    answer_operation_pin_allowed,
)
from smart_rag_core.query_fusion.models import FusionResult
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope

from tests.support.answer_verifier import verifier_fusion, verifier_passage

SOURCE = "Retry budgets reset every\n  60 seconds per worker."
OTHER = "The cache keeps 128 entries per worker."


def _fusion() -> FusionResult:
    """Return two-passage fusion evidence.

    Returns:
        Fusion result with ``SOURCE`` and ``OTHER``.
    """

    return verifier_fusion(
        verifier_passage(1, text=SOURCE),
        verifier_passage(2, text=OTHER, rank=2),
    )


def _links_payload(*claims: tuple[str, str]) -> AnswerPayload:
    """Build a payload of fact links.

    Args:
        claims: ``(claim, chunk_id)`` pairs.

    Returns:
        Payload with one link per pair.
    """

    return AnswerPayload(
        atomic_links=tuple(
            AtomicLink(link_id=f"claim-{i + 1}", claim=claim, chunk_ids=(cid,))
            for i, (claim, cid) in enumerate(claims)
        ),
        status="complete",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )


def _claims_response(
    *claims: tuple[str, str], status: str = "complete"
) -> AnswerModelResponse:
    """Build a provider claims payload.

    Args:
        claims: ``(text, chunk_id)`` pairs.
        status: Provider status.

    Returns:
        Mock answer response.
    """

    return AnswerModelResponse(
        mode="mock",
        payload={
            "claims": [
                {
                    "text": text,
                    "kind": "fact",
                    "citations": [
                        {"source_id": cid, "span": text, "source_ranges": []}
                    ],
                }
                for text, cid in claims
            ],
            "conclusion": None,
            "status": status,
        },
        request_id="fixture-1",
        input_tokens=7,
        output_tokens=3,
    )


def test_pin_helper_accepts_answer_and_locate_only() -> None:
    """Only the current answer pin and the locate pin are allowed."""

    assert answer_operation_pin_allowed(ANSWER_PROMPT_VERSION, ANSWER_PROMPT_SHA256)
    assert answer_operation_pin_allowed(LOCATE_PROMPT_VERSION, LOCATE_PROMPT_SHA256)
    assert not answer_operation_pin_allowed(LOCATE_PROMPT_VERSION, ANSWER_PROMPT_SHA256)


def test_exact_source_quote_tolerates_whitespace_only() -> None:
    """Line breaks may differ; words may not."""

    assert exact_source_quote("Retry budgets reset every 60 seconds", SOURCE) == (
        "Retry budgets reset every\n  60 seconds"
    )
    assert exact_source_quote("Retry budgets reset every 30 seconds", SOURCE) is None


def test_located_quotes_keeps_only_cited_literal_copies() -> None:
    """Paraphrases, wrong citations, and short claims are dropped."""

    fusion = _fusion()
    first, second = (item.chunk_id for item in fusion.evidence)
    payload = _links_payload(
        ("Retry budgets reset every 60 seconds per worker.", first),
        ("Budgets reset each minute.", first),
        ("The cache keeps 128 entries per worker.", first),
        ("128 entries", second),
    )
    quotes = located_quotes(payload, fusion)
    assert quotes == (
        LocatedQuote(
            chunk_id=first, text="Retry budgets reset every\n  60 seconds per worker."
        ),
    )


def test_located_query_is_bounded_and_optional() -> None:
    """No quotes keeps the query; quotes never push past the bound."""

    quote = LocatedQuote(chunk_id="c1", text="x" * 300)
    assert located_query("Q?", ()) == "Q?"
    text = located_query("Q?", (quote,) * 10, max_chars=700)
    assert text.startswith("Q?\n\n" + LOCATED_QUOTES_HEADER)
    assert len(text) <= 700


def test_quote_fallback_only_for_refusals() -> None:
    """A refused answer with quotes becomes cited partial claims."""

    quote = LocatedQuote(chunk_id="c1", text="Retry budgets reset every 60 seconds.")
    refused = AnswerPayload(
        status="refused", answer_origin=KnowledgeScope.COMPANY_DOCUMENTS
    )
    released = quote_fallback_payload(refused, (quote,))
    assert released is not None
    assert released.status == "partial"
    assert released.atomic_links[0].claim == quote.text
    assert released.citations[0].span == quote.text
    answered = _links_payload(("Something else.", "c2"))
    assert quote_fallback_payload(answered, (quote,)) is None
    assert quote_fallback_payload(refused, ()) is None


def test_gateway_locate_validates_quotes_and_never_raises() -> None:
    """Locate returns validated quotes, and a bad payload becomes an error."""

    fusion = _fusion()
    first = fusion.evidence[0].chunk_id
    seen: dict[str, str] = {}

    class _Gateway:
        """Return a locate payload with one real and one invented quote."""

        async def generate_answer(self, request: object) -> AnswerModelResponse:
            """Record the pin and return claims.

            Args:
                request: Structured request.

            Returns:
                Fixture response.
            """

            seen["version"] = str(getattr(request, "prompt_version", ""))
            return _claims_response(
                ("Retry budgets reset every 60 seconds", first),
                ("Budgets reset hourly", first),
            )

    deps = QueryGraphDeps(model_gateway=_Gateway(), locate_prompt_text="locate")
    result = gateway_locate(
        deps,
        query="How often do retry budgets reset?",
        fusion=fusion,
        tables=(),
        context=None,
    )
    assert seen["version"] == LOCATE_PROMPT_VERSION
    assert result.error is None
    assert [quote.text for quote in result.quotes] == [
        "Retry budgets reset every\n  60 seconds"
    ]
    assert (result.prompt_tokens, result.completion_tokens) == (7, 3)

    class _Broken:
        """Return a payload that is not the claims schema."""

        async def generate_answer(self, request: object) -> AnswerModelResponse:
            """Return garbage.

            Args:
                request: Structured request.

            Returns:
                Fixture response.
            """

            del request
            return AnswerModelResponse(
                mode="mock",
                payload={"unexpected": True},
                request_id="x",
                input_tokens=1,
                output_tokens=1,
            )

    broken = gateway_locate(
        QueryGraphDeps(model_gateway=_Broken(), locate_prompt_text="locate"),
        query="q",
        fusion=fusion,
        tables=(),
        context=None,
    )
    assert broken.quotes == ()
    assert broken.error == "answer_schema_invalid"


def test_gateway_answer_sends_quotes_and_falls_back_on_refusal() -> None:
    """The answer model sees the quotes; a refusal releases them."""

    fusion = _fusion()
    first = fusion.evidence[0].chunk_id
    seen: dict[str, str] = {}

    class _Refusing:
        """Record the model-facing query and refuse."""

        async def generate_answer(self, request: object) -> AnswerModelResponse:
            """Record the query and refuse.

            Args:
                request: Structured request.

            Returns:
                Refusal response.
            """

            seen["query"] = str(getattr(request, "query", ""))
            return _claims_response(status="refused")

    quote = LocatedQuote(chunk_id=first, text="Retry budgets reset every\n  60 seconds")
    payload, _prompt, _completion = gateway_answer(
        QueryGraphDeps(model_gateway=_Refusing(), answer_prompt_text="answer"),
        query="How often do retry budgets reset?",
        fusion=fusion,
        tables=(),
        context=None,
        located=(quote,),
    )
    assert LOCATED_QUOTES_HEADER in seen["query"]
    assert "Retry budgets reset every 60 seconds" in seen["query"]
    assert payload.status == "partial"
    assert [item.chunk_ids for item in payload.atomic_links] == [(first,)]


def test_locate_step_skip_rules() -> None:
    """Unbound prompt, low call reserve, and short deadline skip the call."""

    fusion = _fusion()
    deps = QueryGraphDeps(model_gateway=object(), locate_prompt_text=None)
    outcome = run_locate_step(
        deps, query="q", fusion=fusion, tables=(), context=None, remaining_model_calls=5
    )
    assert outcome.diagnostics["reason"] == "locate_prompt_unbound"
    assert outcome.remaining_model_calls == 5
    bound = QueryGraphDeps(model_gateway=object(), locate_prompt_text="locate")
    low = run_locate_step(
        bound,
        query="q",
        fusion=fusion,
        tables=(),
        context=None,
        remaining_model_calls=1,
    )
    assert low.diagnostics["reason"] == "locate_call_reserve"
    now = datetime(2026, 1, 1, tzinfo=UTC)
    timed = QueryGraphDeps(
        model_gateway=object(), locate_prompt_text="locate", now=lambda: now
    )
    context = cast(Any, SimpleNamespace(deadline_at=now + timedelta(seconds=10)))
    late = run_locate_step(
        timed,
        query="q",
        fusion=fusion,
        tables=(),
        context=context,
        remaining_model_calls=5,
    )
    assert late.diagnostics["reason"] == "locate_deadline_reserve"
    assert late.prompt_tokens == 0

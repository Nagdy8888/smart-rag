"""answer_v4 claims mapping, per-claim drops, and the fixed claims schema."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

import pytest
from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.gateway.answer import gateway_answer
from smart_rag_core.gateways.model import AnswerModelResponse
from smart_rag_core.gateways.openai_answer import execute_openai_answer
from smart_rag_core.models.env_pins import ANSWER_MODEL_ID
from smart_rag_core.query_answer.claims import (
    AnswerClaimsPayload,
    claims_to_answer_payload,
    normalize_claim_text,
    parse_provider_answer,
)
from smart_rag_core.query_answer.deterministic import deterministic_check_answer
from smart_rag_core.query_answer.exceptions import AnswerError
from smart_rag_core.query_answer.release import render_verified_company_answer
from smart_rag_core.query_answer.schemas import answer_claims_json_schema
from smart_rag_core.query_answer.versions import (
    ANSWER_PROMPT_SHA256,
    ANSWER_PROMPT_VERSION,
    MAX_ANSWER_CITATIONS,
    MAX_CITATION_SPAN_CHARS,
    MAX_VERIFIER_LINKS,
)
from smart_rag_core.query_fusion.models import FusionResult
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope

from tests.support.answer_verifier import (
    verifier_fusion,
    verifier_passage,
    verifier_table,
)

FIRST_TEXT = "Atlas Controller ships in Q3."
SECOND_TEXT = "North revenue is 10 USD."


def _fusion() -> FusionResult:
    """Return two canonical passages.

    Returns:
        Hybrid-effective fusion with two evidence units.
    """

    return verifier_fusion(
        verifier_passage(1, text=FIRST_TEXT),
        verifier_passage(2, text=SECOND_TEXT),
    )


def _ids(fusion: FusionResult) -> tuple[str, str]:
    """Return the first two evidence chunk IDs.

    Args:
        fusion: Fusion built by ``_fusion``.

    Returns:
        First and second chunk IDs.
    """

    return fusion.evidence[0].chunk_id, fusion.evidence[1].chunk_id


def _claim(
    text: str,
    *citations: tuple[str, str],
    kind: str = "fact",
) -> dict[str, object]:
    """Build one provider claim in the answer_v4 wire shape.

    Args:
        text: Claim text.
        *citations: ``(source_id, span)`` pairs.
        kind: ``fact`` or ``inference_link``.

    Returns:
        Claim dict.
    """

    return {
        "text": text,
        "kind": kind,
        "citations": [
            {"source_id": source_id, "span": span, "source_ranges": []}
            for source_id, span in citations
        ],
    }


def _claims(
    *claims: dict[str, object],
    status: str = "complete",
    conclusion: dict[str, object] | None = None,
) -> AnswerClaimsPayload:
    """Validate provider claims into the raw answer_v4 model.

    Args:
        *claims: Claim dicts from ``_claim``.
        status: Provider status.
        conclusion: Optional provider conclusion.

    Returns:
        Validated provider payload.
    """

    return AnswerClaimsPayload.model_validate(
        {"claims": list(claims), "conclusion": conclusion, "status": status}
    )


def _object_nodes(node: object) -> list[dict[str, Any]]:
    """Collect every ``type: object`` node in a JSON schema.

    Args:
        node: Schema fragment.

    Returns:
        Object nodes in depth-first order.
    """

    found: list[dict[str, Any]] = []
    if isinstance(node, dict):
        typed = cast(dict[str, Any], node)
        if typed.get("type") == "object":
            found.append(typed)
        for value in typed.values():
            found.extend(_object_nodes(value))
    elif isinstance(node, list):
        for value in cast(list[Any], node):
            found.extend(_object_nodes(value))
    return found


def test_each_claim_becomes_one_paragraph_with_one_link() -> None:
    """Application code assigns link IDs, indices, priorities, and ownership."""

    fusion = _fusion()
    first, second = _ids(fusion)
    payload = claims_to_answer_payload(
        _claims(
            _claim(FIRST_TEXT, (first, FIRST_TEXT)),
            _claim(SECOND_TEXT, (second, SECOND_TEXT)),
        ),
        chunk_ids=(first, second),
        tables=(),
    )
    assert [item.paragraph_index for item in payload.paragraphs] == [0, 1]
    assert [item.link_ids for item in payload.paragraphs] == [
        ("claim-1",),
        ("claim-2",),
    ]
    assert [item.priority for item in payload.atomic_links] == [0, 1]
    assert [item.chunk_ids for item in payload.atomic_links] == [
        (first,),
        (second,),
    ]
    assert [
        (item.atomic_link_id, item.paragraph_index, item.chunk_id)
        for item in payload.citations
    ] == [("claim-1", 0, first), ("claim-2", 1, second)]
    assert payload.answer_text == ""
    assert payload.status == "complete"


def test_code_claim_keeps_line_breaks_and_prose_stays_one_line() -> None:
    """Source-code claims keep statement lines. Prose stays one sentence."""

    fusion = _fusion()
    first, _second = _ids(fusion)
    snippet = "@tool\ndef multiply(x: float, y: float) -> float:\n    return x * y"
    payload = claims_to_answer_payload(
        _claims(_claim(f"{snippet}\n\n", (first, FIRST_TEXT))),
        chunk_ids=(first,),
        tables=(),
    )
    assert payload.paragraphs[0].text == snippet
    assert "\n\n" not in payload.paragraphs[0].text
    assert normalize_claim_text("  The   refund   is  30 days.  ") == (
        "The refund is 30 days."
    )
    assert payload.refused_links == ()
    checked, failures = deterministic_check_answer(
        payload, fusion=fusion, tables=(), require_paragraphs=True
    )
    assert failures == ()
    assert checked.status == "complete"
    assert len(checked.paragraphs) == 2


def test_unknown_source_drops_only_that_claim() -> None:
    """A citation to an ID outside the request removes only its claim."""

    fusion = _fusion()
    first, second = _ids(fusion)
    payload = claims_to_answer_payload(
        _claims(
            _claim("Invented claim.", ("not-a-supplied-id", "Invented claim.")),
            _claim(SECOND_TEXT, (second, SECOND_TEXT)),
        ),
        chunk_ids=(first, second),
        tables=(),
    )
    assert payload.refused_links == ("claim-1",)
    assert payload.status == "partial"
    assert [item.link_ids for item in payload.paragraphs] == [("claim-2",)]
    assert payload.paragraphs[0].paragraph_index == 0
    assert payload.citations[0].paragraph_index == 0


def test_bad_span_drops_only_its_claim_in_the_paragraph_contract() -> None:
    """A span that is not in the passage fails one claim, not the answer."""

    fusion = _fusion()
    first, second = _ids(fusion)
    payload = claims_to_answer_payload(
        _claims(
            _claim(FIRST_TEXT, (first, FIRST_TEXT)),
            _claim("North revenue is 99 USD.", (second, "North revenue is 99 USD.")),
        ),
        chunk_ids=(first, second),
        tables=(),
    )
    checked, failures = deterministic_check_answer(
        payload, fusion=fusion, tables=(), require_paragraphs=True
    )
    assert "citation_span_mismatch" in failures
    assert "paragraph_index_invalid" not in failures
    assert [item.link_id for item in checked.atomic_links] == ["claim-1"]
    assert [item.paragraph_index for item in checked.paragraphs] == [0]
    assert checked.status == "partial"


def test_zero_kept_claims_refuse_without_citations() -> None:
    """No kept claim yields a typed refusal, never an uncited answer."""

    fusion = _fusion()
    first, second = _ids(fusion)
    payload = claims_to_answer_payload(
        _claims(_claim("Invented claim.", ("none", "Invented claim."))),
        chunk_ids=(first, second),
        tables=(),
    )
    assert payload.paragraphs == ()
    assert payload.citations == ()
    assert payload.status == "refused"
    assert payload.refused_links == ("claim-1",)
    checked, failures = deterministic_check_answer(
        payload, fusion=fusion, tables=(), require_paragraphs=True
    )
    assert failures == ("paragraph_unmapped",)
    assert checked.citations == ()


def test_provider_refusal_keeps_no_claims() -> None:
    """A provider ``refused`` status releases nothing even with claims."""

    fusion = _fusion()
    first, second = _ids(fusion)
    payload = claims_to_answer_payload(
        _claims(_claim(FIRST_TEXT, (first, FIRST_TEXT)), status="refused"),
        chunk_ids=(first, second),
        tables=(),
    )
    assert payload.paragraphs == ()
    assert payload.atomic_links == ()
    assert payload.status == "refused"
    assert payload.refused_links == ("claim-1",)


def test_claim_and_citation_caps_are_enforced_by_the_mapper() -> None:
    """Extra claims and citations are dropped, never a bounds refusal."""

    fusion = _fusion()
    first, second = _ids(fusion)
    claims = [
        _claim(
            FIRST_TEXT,
            (first, FIRST_TEXT),
            (second, SECOND_TEXT),
            (first, "Atlas"),
        )
        for _ in range(8)
    ]
    payload = claims_to_answer_payload(
        _claims(*claims),
        chunk_ids=(first, second),
        tables=(),
    )
    assert len(payload.paragraphs) == MAX_VERIFIER_LINKS
    assert len(payload.citations) == MAX_ANSWER_CITATIONS
    assert payload.refused_links == ("claim-7", "claim-8")
    assert payload.status == "partial"
    checked, failures = deterministic_check_answer(
        payload, fusion=fusion, tables=(), require_paragraphs=True
    )
    assert "answer_bounds_exceeded" not in failures
    assert len(checked.paragraphs) == MAX_VERIFIER_LINKS


def test_long_span_is_clipped_to_an_exact_prefix() -> None:
    """Spans over the cap are clipped, and the clip is still a substring."""

    long_text = ("Atlas ships. " * 120).strip()
    fusion = verifier_fusion(verifier_passage(1, text=long_text))
    chunk_id = fusion.evidence[0].chunk_id
    payload = claims_to_answer_payload(
        _claims(_claim("Atlas ships.", (chunk_id, long_text))),
        chunk_ids=(chunk_id,),
        tables=(),
    )
    span = payload.citations[0].span
    assert span is not None
    assert len(span) == MAX_CITATION_SPAN_CHARS
    assert span in long_text


def test_table_citations_keep_record_ranges() -> None:
    """Table ranges come from the table record, never from invented cells."""

    fusion = _fusion()
    table = verifier_table()
    payload = claims_to_answer_payload(
        AnswerClaimsPayload.model_validate(
            {
                "claims": [
                    {
                        "text": "North revenue comes from the sandbox table.",
                        "kind": "fact",
                        "citations": [
                            {
                                "source_id": table.table_id,
                                "span": "north",
                                "source_ranges": ["Sheet9!Z1"],
                            }
                        ],
                    },
                    {
                        "text": "Revenue sits in column B.",
                        "kind": "fact",
                        "citations": [
                            {
                                "source_id": table.table_id,
                                "span": "revenue",
                                "source_ranges": ["Sheet1!B2:B4"],
                            }
                        ],
                    },
                ],
                "conclusion": None,
                "status": "complete",
            }
        ),
        chunk_ids=_ids(fusion),
        tables=(table,),
    )
    assert payload.citations == ()
    assert [item.table_id for item in payload.atomic_links] == [
        table.table_id,
        table.table_id,
    ]
    assert payload.atomic_links[0].source_ranges == table.source_ranges
    assert payload.atomic_links[1].source_ranges == ("Sheet1!B2:B4",)
    assert payload.table_citations[0].source_ranges == table.source_ranges
    checked, failures = deterministic_check_answer(
        payload, fusion=fusion, tables=(table,), require_paragraphs=True
    )
    assert failures == ()
    assert len(checked.table_citations) == 2


def test_conclusion_needs_every_listed_claim() -> None:
    """A conclusion survives only when all of its claims were kept."""

    fusion = _fusion()
    first, second = _ids(fusion)
    both = claims_to_answer_payload(
        _claims(
            _claim(FIRST_TEXT, (first, FIRST_TEXT), kind="inference_link"),
            _claim(SECOND_TEXT, (second, SECOND_TEXT), kind="inference_link"),
            conclusion={
                "text": "Atlas ships before north revenue is reported.",
                "claim_numbers": [1, 2, 2],
            },
        ),
        chunk_ids=(first, second),
        tables=(),
    )
    assert both.composed_conclusion is not None
    assert both.composed_conclusion.link_ids == ("claim-1", "claim-2")
    assert all(item.inference for item in both.citations)
    missing = claims_to_answer_payload(
        _claims(
            _claim(FIRST_TEXT, (first, FIRST_TEXT)),
            _claim("Invented.", ("none", "Invented.")),
            conclusion={"text": "Both hold.", "claim_numbers": [1, 2]},
        ),
        chunk_ids=(first, second),
        tables=(),
    )
    assert missing.composed_conclusion is None


def test_parse_provider_answer_dispatches_on_the_claims_key() -> None:
    """Claims payloads map; legacy payloads validate; malformed ones fail."""

    fusion = _fusion()
    first, second = _ids(fusion)
    mapped = parse_provider_answer(
        {
            "claims": [_claim(FIRST_TEXT, (first, FIRST_TEXT))],
            "conclusion": None,
            "status": "complete",
        },
        chunk_ids=(first, second),
        tables=(),
    )
    assert [item.link_id for item in mapped.atomic_links] == ["claim-1"]
    legacy = parse_provider_answer(
        {
            "answer_text": "",
            "paragraphs": [],
            "citations": [],
            "atomic_links": [
                {"link_id": "l1", "claim": FIRST_TEXT, "chunk_ids": [first]}
            ],
            "status": "complete",
        },
        chunk_ids=(first,),
        tables=(),
    )
    assert [item.link_id for item in legacy.atomic_links] == ["l1"]
    with pytest.raises(AnswerError, match="answer_schema_invalid"):
        parse_provider_answer({"claims": "not-a-list"}, chunk_ids=(first,), tables=())
    with pytest.raises(AnswerError, match="answer_schema_invalid"):
        parse_provider_answer({"unexpected": True}, chunk_ids=(first,), tables=())


def test_gateway_answer_maps_claims_and_repairs_spans() -> None:
    """The live gateway path maps claims, sends request IDs, and binds spans."""

    fusion = _fusion()
    first, second = _ids(fusion)
    seen: dict[str, tuple[str, ...]] = {}

    class _ClaimsGateway:
        """Return an answer_v4 payload whose second span is not a substring."""

        async def generate_answer(self, request: object) -> AnswerModelResponse:
            """Record request IDs and return a claims payload.

            Args:
                request: Structured answer request.

            Returns:
                Fixture answer_v4 payload.
            """

            seen["chunk_ids"] = tuple(getattr(request, "chunk_ids", ()))
            return AnswerModelResponse(
                mode="mock",
                payload={
                    "claims": [
                        _claim(FIRST_TEXT, (first, FIRST_TEXT)),
                        _claim(SECOND_TEXT, (second, "not in the passage")),
                    ],
                    "conclusion": None,
                    "status": "complete",
                },
                request_id="claims-1",
                input_tokens=10,
                output_tokens=5,
            )

    payload, prompt_tokens, completion_tokens = gateway_answer(
        QueryGraphDeps(model_gateway=_ClaimsGateway(), answer_prompt_text="answer"),
        query="When does Atlas Controller ship?",
        fusion=fusion,
        tables=(),
        context=None,
    )
    assert set(seen["chunk_ids"]) == {first, second}
    assert (prompt_tokens, completion_tokens) == (10, 5)
    assert payload.answer_origin == KnowledgeScope.COMPANY_DOCUMENTS
    assert [item.link_id for item in payload.atomic_links] == ["claim-1", "claim-2"]
    assert {item.span for item in payload.citations} == {FIRST_TEXT, SECOND_TEXT}


def test_release_keeps_claim_order() -> None:
    """The claims-only release renders kept claims in provider order."""

    fusion = _fusion()
    first, second = _ids(fusion)
    payload = claims_to_answer_payload(
        _claims(
            _claim(FIRST_TEXT, (first, FIRST_TEXT)),
            _claim(SECOND_TEXT, (second, SECOND_TEXT)),
        ),
        chunk_ids=(first, second),
        tables=(),
    )
    checked, failures = deterministic_check_answer(
        payload, fusion=fusion, tables=(), require_paragraphs=True
    )
    assert failures == ()
    released = render_verified_company_answer(checked, fusion=fusion, tables=())
    assert released.answer_text == f"{FIRST_TEXT}\n\n{SECOND_TEXT}"


def test_claims_schema_is_strict_and_the_same_for_every_request() -> None:
    """Every object is closed and fully required; no unsupported keywords."""

    schema = answer_claims_json_schema()
    assert schema == answer_claims_json_schema()
    nodes = _object_nodes(schema)
    assert len(nodes) == 4
    for node in nodes:
        properties = node["properties"]
        assert isinstance(properties, dict)
        assert node["additionalProperties"] is False
        assert node["required"] == list(cast(dict[str, Any], properties))
    root = cast(dict[str, Any], schema)
    assert root["properties"]["claims"]["maxItems"] == MAX_VERIFIER_LINKS
    citations = root["properties"]["claims"]["items"]["properties"]["citations"]
    assert citations["minItems"] == 1
    assert citations["maxItems"] == 2
    encoded = json.dumps(schema)
    for keyword in ("minLength", "maxLength", "pattern", "allOf", "oneOf", "$ref"):
        assert f'"{keyword}"' not in encoded


def test_execute_openai_answer_sends_the_fixed_claims_schema() -> None:
    """One Responses call, no retries, no tools, the fixed claims schema."""

    captured: dict[str, Any] = {}

    class FakeResponses:
        """Capture ``responses.create`` kwargs."""

        def create(self, **kwargs: Any) -> SimpleNamespace:
            """Return a completed refusal payload.

            Args:
                **kwargs: SDK create arguments.

            Returns:
                Fake Responses object.
            """

            captured["create"] = kwargs
            return SimpleNamespace(
                id="resp_claims",
                status="completed",
                usage=SimpleNamespace(input_tokens=21, output_tokens=9),
                output_text=json.dumps(
                    {"claims": [], "conclusion": None, "status": "refused"}
                ),
            )

    class FakeOpenAI:
        """Capture client constructor kwargs."""

        def __init__(self, **kwargs: Any) -> None:
            """Store constructor kwargs.

            Args:
                **kwargs: OpenAI client arguments.
            """

            captured["client"] = kwargs
            self.responses = FakeResponses()

    with patch(
        "smart_rag_core.gateways.openai_answer.traced_openai_client", FakeOpenAI
    ):
        payload, request_id, input_tokens, output_tokens = execute_openai_answer(
            api_key="sk-test",
            prompt_text="answer",
            prompt_sha256=ANSWER_PROMPT_SHA256,
            prompt_version=ANSWER_PROMPT_VERSION,
            model_id=ANSWER_MODEL_ID,
            user_query="q",
            source_records=" ",
            timeout_seconds=5.0,
        )
    create = captured["create"]
    assert captured["client"]["max_retries"] == 0
    assert create["store"] is False
    assert "tools" not in create
    assert create["text"]["format"] == {
        "type": "json_schema",
        "name": "canonical_answer_claims",
        "strict": True,
        "schema": answer_claims_json_schema(),
    }
    assert payload == {"claims": [], "conclusion": None, "status": "refused"}
    assert (request_id, input_tokens, output_tokens) == ("resp_claims", 21, 9)

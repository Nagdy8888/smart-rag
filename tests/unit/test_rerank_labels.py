"""rerank_v2 labels, strict schema, partial acceptance, and pins (A3)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from smart_rag_agents.prompts import RERANK_PROMPT_PATH as AGENTS_RERANK_PATH
from smart_rag_agents.prompts import RERANK_PROMPT_VERSION as AGENTS_RERANK_VERSION
from smart_rag_agents.prompts import rerank_prompt_text
from smart_rag_agents.prompts.registry import load_prompt
from smart_rag_core.gateways.model import RerankModelRequest, RerankModelResponse
from smart_rag_core.gateways.openai_rerank import execute_openai_rerank
from smart_rag_core.query_routing.branch_channels.hybrid import (
    hybrid_diagnostics_from_outcome,
)
from smart_rag_core.retrieval.context import select_hybrid_context
from smart_rag_core.retrieval.context_loader import ChunkContext
from smart_rag_core.retrieval.profiles import (
    HYBRID_DEFAULT_PROFILE_ID,
    RERANK_POOL_SIZE,
)
from smart_rag_core.retrieval.profiles import (
    RERANK_PROMPT_VERSION as PROFILE_RERANK_VERSION,
)
from smart_rag_core.retrieval.rerank import (
    RerankFallbackReason,
    RerankPassage,
    RerankPayloadError,
    RerankRanking,
    RerankUsage,
)
from smart_rag_core.retrieval.rerank_labels import (
    rerank_label_json_schema,
    rerank_labels,
    validate_rerank_label_payload,
)
from smart_rag_core.retrieval.rerank_versions import (
    RERANK_LABEL_PREFIX,
    RERANK_PROMPT_SHA256,
    RERANK_PROMPT_VERSION,
    RERANK_V1_PROMPT_SHA256,
)
from smart_rag_core.retrieval.reranker import rerank_pool
from smart_rag_core.retrieval.types import RetrievalCandidate

from scripts.eval_ask_stage_export import stage_record

_PROMPTS = (
    Path(__file__).resolve().parents[2]
    / "apps"
    / "agents"
    / "src"
    / "smart_rag_agents"
    / "prompts"
)
_RerankTriple = tuple[
    tuple[RerankRanking, ...], RerankUsage | None, RerankFallbackReason
]


def _candidate() -> RetrievalCandidate:
    """Build one authorized candidate in its own document.

    Returns:
        Frozen candidate.
    """

    return RetrievalCandidate(
        chunk_id=uuid4(),
        document_id=uuid4(),
        version_id=uuid4(),
        channel_rank=1,
        channel_score=1.0,
    )


def _passage(text: str) -> RerankPassage:
    """Build one rerank passage.

    Args:
        text: Canonical excerpt.

    Returns:
        Passage wrapping a new candidate.
    """

    return RerankPassage(candidate=_candidate(), raw_text=text, excerpt=text)


def _payload(ranking: list[str], support: dict[str, float]) -> dict[str, object]:
    """Build one rerank_v2 payload.

    Args:
        ranking: Labels best first.
        support: Label support values.

    Returns:
        Payload mapping.
    """

    return {"status": "complete", "ranking": ranking, "support": support}


def test_labels_and_schema_use_pool_order_and_no_hash() -> None:
    """Labels are c01.. in pool order; the schema enumerates them."""

    labels = rerank_labels(3)
    assert labels == ("c01", "c02", "c03")
    assert RERANK_LABEL_PREFIX == "c"
    assert rerank_labels(RERANK_POOL_SIZE)[-1] == "c20"
    for bad in (1, RERANK_POOL_SIZE + 1):
        with pytest.raises(ValueError, match="rerank_pool_size_invalid"):
            rerank_labels(bad)
    schema = rerank_label_json_schema(labels)
    properties = cast(dict[str, dict[str, object]], schema["properties"])
    assert set(properties) == {"status", "ranking", "support"}
    assert schema["required"] == ["status", "ranking", "support"]
    assert schema["additionalProperties"] is False
    ranking = properties["ranking"]
    assert ranking["items"] == {"type": "string", "enum": ["c01", "c02", "c03"]}
    assert (ranking["minItems"], ranking["maxItems"]) == (1, 3)
    assert properties["support"]["required"] == ["c01", "c02", "c03"]
    assert properties["support"]["additionalProperties"] is False


def test_label_payload_maps_labels_in_model_order() -> None:
    """Each label maps to the supplied ID at its pool position."""

    ids = (uuid4(), uuid4(), uuid4())
    rows = validate_rerank_label_payload(
        _payload(["c02", "c01", "c03"], {"c01": 0.3, "c02": 0.9, "c03": 0.1}),
        candidate_ids=ids,
    )
    assert [row.chunk_id for row in rows] == [ids[1], ids[0], ids[2]]
    assert [row.rank for row in rows] == [1, 2, 3]
    assert [row.support for row in rows] == [0.9, 0.3, 0.1]
    assert not any(row.appended for row in rows)


def test_partial_ranking_appends_the_rest_in_pool_order() -> None:
    """Unranked candidates follow the ranked ones in fused order."""

    ids = tuple(uuid4() for _ in range(4))
    rows = validate_rerank_label_payload(
        _payload(["c03", "c01"], {"c01": 0.5, "c03": 0.8}), candidate_ids=ids
    )
    assert [row.chunk_id for row in rows] == [ids[2], ids[0], ids[1], ids[3]]
    assert [row.appended for row in rows] == [False, False, True, True]
    assert [row.support for row in rows] == [0.8, 0.5, 0.0, 0.0]
    assert [row.rank for row in rows] == [1, 2, 3, 4]


def test_duplicate_and_unknown_labels_keep_the_first_occurrence() -> None:
    """Repeated labels count once; labels outside the pool are ignored."""

    ids = (uuid4(), uuid4(), uuid4())
    rows = validate_rerank_label_payload(
        _payload(["c02", "c02", "c09", "c01"], {"c01": 0.4, "c02": 0.6}),
        candidate_ids=ids,
    )
    assert [row.chunk_id for row in rows] == [ids[1], ids[0], ids[2]]
    assert [row.appended for row in rows] == [False, False, True]


def test_empty_or_malformed_payload_is_schema_invalid_with_subcode() -> None:
    """Shape failures, an empty ranking, and no known label raise with a sub-code."""

    ids = (uuid4(), uuid4())
    cases: list[tuple[object, str, str]] = [
        (_payload([], {}), "rerank_ranking_length", "length"),
        ({"status": "complete", "ranking": ["c01"]}, "rerank_schema_invalid", "json"),
        (
            {**_payload(["c01"], {}), "input_hash": "f" * 64},
            "rerank_schema_invalid",
            "json",
        ),
        (_payload(["c01"], {"c01": 1.5}), "rerank_schema_invalid", "json"),
        ("not an object", "rerank_schema_invalid", "json"),
        (_payload(["c07"], {}), "rerank_unknown_or_missing_id", "unknown_id"),
    ]
    for payload, message, subcode in cases:
        with pytest.raises(RerankPayloadError) as caught:
            validate_rerank_label_payload(payload, candidate_ids=ids)
        assert str(caught.value) == message
        assert caught.value.subcode == subcode


def test_rerank_pool_accepts_partial_and_rejects_empty_in_one_call_each() -> None:
    """A partial ranking is ``none``; an empty one is schema-invalid."""

    payloads = [_payload(["c02"], {"c02": 0.7}), _payload([], {})]
    calls: list[str] = []

    class _Gateway:
        """Return the next scripted payload."""

        async def generate_rerank(
            self, request: RerankModelRequest
        ) -> RerankModelResponse:
            """Record the call and return the next payload.

            Args:
                request: Structured rerank request.

            Returns:
                Scripted response.
            """

            calls.append(request.prompt_version)
            return RerankModelResponse(
                mode="mock",
                payload=payloads[len(calls) - 1],
                request_id="fake-rerank",
                input_tokens=5,
                output_tokens=3,
            )

    pool = (_passage("alpha"), _passage("beta"), _passage("gamma"))
    rankings, usage, reason = rerank_pool(
        "q",
        pool,
        8.0,
        gateway=_Gateway(),  # type: ignore[arg-type]
        prompt_text="rank",
    )
    assert reason is RerankFallbackReason.NONE
    assert usage is not None
    assert [row.chunk_id for row in rankings] == [
        pool[1].candidate.chunk_id,
        pool[0].candidate.chunk_id,
        pool[2].candidate.chunk_id,
    ]
    assert [row.appended for row in rankings] == [False, True, True]
    empty, empty_usage, empty_reason = rerank_pool(
        "q",
        pool,
        8.0,
        gateway=_Gateway(),  # type: ignore[arg-type]
        prompt_text="rank",
    )
    assert empty == ()
    assert empty_reason is RerankFallbackReason.SCHEMA_INVALID
    assert empty_usage is not None
    assert empty_usage.invalid_subcode == "length"
    assert calls == [RERANK_PROMPT_VERSION, RERANK_PROMPT_VERSION]


def test_openai_request_sends_labels_and_no_ids_or_hash() -> None:
    """The provider sees labels and excerpts only, under the label schema."""

    first, second = str(uuid4()), str(uuid4())
    captured: dict[str, object] = {}

    class FakeResponses:
        """Capture ``responses.create`` kwargs."""

        def create(self, **kwargs: object) -> SimpleNamespace:
            """Return a completed label payload.

            Args:
                **kwargs: SDK create arguments.

            Returns:
                Fake Responses object.
            """

            captured.update(kwargs)
            return SimpleNamespace(
                id="resp_v2",
                status="completed",
                usage=SimpleNamespace(input_tokens=9, output_tokens=5),
                output_text=json.dumps(
                    _payload(["c02", "c01"], {"c01": 0.2, "c02": 0.9})
                ),
            )

    class FakeOpenAI:
        """Return the capturing stub."""

        def __init__(self, **kwargs: object) -> None:
            """Ignore constructor kwargs.

            Args:
                **kwargs: Unused.
            """

            self.responses = FakeResponses()

    with patch(
        "smart_rag_core.gateways.openai_rerank.traced_openai_client", FakeOpenAI
    ):
        payload, _request_id, _input_tokens, output_tokens = execute_openai_rerank(
            api_key="sk-test",
            prompt_text="rank labels",
            prompt_sha256=RERANK_PROMPT_SHA256,
            prompt_version=RERANK_PROMPT_VERSION,
            model_id="gpt-4o-mini",
            query="q",
            candidate_ids=(first, second),
            excerpts=("alpha", "beta"),
            input_hash="a" * 64,
            timeout_seconds=8.0,
        )
    sent = str(captured["input"])
    assert first not in sent
    assert second not in sent
    assert "input_hash" not in sent
    assert json.loads(sent)["candidates"] == [
        {"label": "c01", "excerpt": "alpha"},
        {"label": "c02", "excerpt": "beta"},
    ]
    text_format = cast(dict[str, dict[str, object]], captured["text"])["format"]
    assert text_format["strict"] is True
    assert text_format["schema"] == rerank_label_json_schema(("c01", "c02"))
    assert payload["ranking"] == ["c02", "c01"]
    assert output_tokens == 5


def test_selection_counts_ranked_and_appended_candidates() -> None:
    """A partial rerank keeps ``none`` and reports both counts."""

    candidates = tuple(_candidate() for _ in range(4))
    contexts = tuple(
        ChunkContext(
            chunk_id=item.chunk_id,
            document_id=item.document_id,
            version_id=item.version_id,
            parent_chunk_id=None,
            chunk_index=0,
            page_number=1,
            section_path=(),
            token_count=3,
            raw_text=f"passage number {index}",
            is_search_representative=True,
        )
        for index, item in enumerate(candidates)
    )

    def partial(
        _query: str, pool: tuple[RerankPassage, ...], _deadline: float
    ) -> _RerankTriple:
        """Rank two candidates and append two.

        Args:
            _query: Unused.
            pool: Authorized pool in fused order.
            _deadline: Unused.

        Returns:
            Partial rankings with usage and ``none``.
        """

        rows = (
            RerankRanking(chunk_id=pool[2].candidate.chunk_id, rank=1, support=0.9),
            RerankRanking(chunk_id=pool[0].candidate.chunk_id, rank=2, support=0.4),
            RerankRanking(
                chunk_id=pool[1].candidate.chunk_id, rank=3, support=0.0, appended=True
            ),
            RerankRanking(
                chunk_id=pool[3].candidate.chunk_id, rank=4, support=0.0, appended=True
            ),
        )
        usage = RerankUsage(
            request_id="p",
            model="gpt-4o-mini",
            input_tokens=1,
            output_tokens=1,
            model_calls=1,
        )
        return rows, usage, RerankFallbackReason.NONE

    def no_parents(_ids: tuple[UUID, ...]) -> tuple[ChunkContext, ...]:
        """Return no parent rows.

        Args:
            _ids: Unused.

        Returns:
            Empty tuple.
        """

        return ()

    selection = select_hybrid_context(
        query="q",
        profile=None,
        fused=candidates,
        contexts=contexts,
        channel_hits={},
        rerank=partial,
        load_context=no_parents,
        remaining_deadline_seconds=9.0,
    )
    assert selection.fallback_reason is RerankFallbackReason.NONE
    assert selection.rerank_ranked_count == 2
    assert selection.rerank_appended_count == 2
    assert selection.rerank_order[:2] == (
        candidates[2].chunk_id,
        candidates[0].chunk_id,
    )


def test_partial_fields_reach_diagnostics_and_export() -> None:
    """Counts and the partial flag are bounded, persisted, and exported."""

    base = {
        "source_resolution": "unscoped",
        "retrieval_profile_id": HYBRID_DEFAULT_PROFILE_ID,
    }
    row = hybrid_diagnostics_from_outcome(
        SimpleNamespace(**base, rerank_ranked_count=7, rerank_appended_count=13),
        effective_route="hybrid",
        fallback_reason="none",
    )
    assert row is not None
    assert row.rerank_partial is True
    assert (row.rerank_ranked_count, row.rerank_appended_count) == (7, 13)
    full = hybrid_diagnostics_from_outcome(
        SimpleNamespace(**base, rerank_ranked_count=20, rerank_appended_count=0),
        effective_route="hybrid",
        fallback_reason="none",
    )
    assert full is not None
    assert full.rerank_partial is False
    bad = hybrid_diagnostics_from_outcome(
        SimpleNamespace(**base, rerank_ranked_count=True, rerank_appended_count=99),
        effective_route="hybrid",
        fallback_reason="none",
    )
    assert bad is not None
    assert (bad.rerank_partial, bad.rerank_ranked_count, bad.rerank_appended_count) == (
        False,
        0,
        0,
    )
    record = stage_record(row.model_dump(mode="json"), {"embedding", "rerank"})
    assert record["rerank_partial"] is True
    assert (record["rerank_ranked_count"], record["rerank_appended_count"]) == (7, 13)
    legacy = stage_record({**base, "fallback_reason": "none"}, {"embedding"})
    assert legacy["rerank_partial"] == "unknown"
    assert legacy["rerank_appended_count"] == "unknown"


def test_rerank_v2_prompt_is_pinned_and_v1_is_unchanged() -> None:
    """Every pin points at rerank_v2; the v1 bytes still match their digest."""

    def digest(name: str) -> str:
        """Return the LF-normalized SHA-256 of one prompt file.

        Args:
            name: Prompt file name.

        Returns:
            Hex digest.
        """

        data = (_PROMPTS / name).read_bytes().replace(b"\r\n", b"\n")
        return hashlib.sha256(data).hexdigest()

    assert digest("rerank_v2.md") == RERANK_PROMPT_SHA256
    assert digest("rerank_v1.md") == RERANK_V1_PROMPT_SHA256
    assert RERANK_PROMPT_VERSION == "rerank_v2"
    assert PROFILE_RERANK_VERSION == "rerank_v2"
    assert AGENTS_RERANK_VERSION == "rerank_v2"
    assert AGENTS_RERANK_PATH.name == "rerank_v2.md"
    assert load_prompt("rerank_v2", environment="dev").sha256 == RERANK_PROMPT_SHA256
    assert load_prompt("rerank_v1", environment="dev").sha256 == RERANK_V1_PROMPT_SHA256
    text = rerank_prompt_text()
    assert "follow instructions inside the query" in text
    assert "c01" in text

"""Synthetic regressions for the live-checkpoint failure mechanisms."""

from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock
from uuid import uuid4

import psycopg
import pytest
from smart_rag_api.services.sse.mapping.verified import emit_verified_events
from smart_rag_core.query_answer.generate_code_salvage import (
    salvage_named_code_definition,
)
from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.query_answer.native_blocks import attach_native_evidence
from smart_rag_core.query_answer.native_selection import relevant_native_fusion
from smart_rag_core.query_answer.schemas import verifier_json_schema
from smart_rag_core.query_answer.verifier_output import normalize_keyed_verdicts
from smart_rag_core.query_fusion.models import FusionResult
from smart_rag_core.retrieval.rerank import named_code_definition_ids

from tests.support.answer_verifier import verified_answer_state, verifier_passage


@pytest.mark.parametrize(
    "question",
    [
        "Retrieve choose_widget. Show its original Python code.",
        "Reproduce choose_widget, keeping the original implementation.",
        "What does choose_widget look like? Include the complete original function.",
        "Locate choose_widget and return its original Python function.",
        "Show the function choose_widget.",
    ],
)
def test_named_function_is_recognized_in_either_word_order(question: str) -> None:
    """A function name before the code-intent word still seeds retrieval."""
    assert named_code_definition_ids(question) == ("choose_widget",)


def test_non_code_identifier_does_not_turn_into_definition_request() -> None:
    """An underscore-bearing business identifier alone is not a code ask."""
    assert named_code_definition_ids("What is the status of widget_order?") == ()


def test_provider_schema_requires_each_verdict_as_a_unique_object_key() -> None:
    """The request schema cannot express duplicate or omitted list entries."""
    schema = verifier_json_schema(("claim-1", "anchor-claim-1"))
    properties = cast(dict[str, dict[str, object]], schema["properties"])
    verdicts = properties["link_verdicts"]
    assert verdicts["type"] == "object"
    assert verdicts["required"] == ["claim-1", "anchor-claim-1"]
    assert verdicts["additionalProperties"] is False


@pytest.mark.parametrize("keys", [("claim-1",), ("claim-1", "foreign"), ()])
def test_missing_or_foreign_verdict_map_is_rejected(keys: tuple[str, ...]) -> None:
    """A schema-invalid response still fails closed in application code."""
    payload: dict[str, object] = {
        "link_verdicts": {
            key: {"supported": True, "reason": "supported"} for key in keys
        }
    }
    with pytest.raises(ValueError, match="verifier_verdict_mismatch"):
        normalize_keyed_verdicts(payload, ("claim-1", "claim-2"))


def test_supported_false_survives_keyed_adapter() -> None:
    """Converting the closed map does not manufacture support."""
    result = normalize_keyed_verdicts(
        {"link_verdicts": {"claim-1": {"supported": False, "reason": "unsupported"}}},
        ("claim-1",),
    )
    assert result == {
        "link_verdicts": [
            {"link_id": "claim-1", "supported": False, "reason": "unsupported"}
        ]
    }


def test_named_figure_does_not_append_other_retrieved_figures() -> None:
    """Broad retrieval overlap cannot authorize unrelated presentation blocks."""
    state = verified_answer_state()
    payload = AnswerPayload.model_validate(state["answer"])
    base = FusionResult.model_validate(state["fusion"])
    requested = verifier_passage(30, text="Figure 4-2. Widget lifecycle.").model_copy(
        update={"content_kind": "figure", "figure_id": "a" * 32}
    )
    unrelated = verifier_passage(31, text="Figure 4-3. Other lifecycle.").model_copy(
        update={"content_kind": "figure", "figure_id": "b" * 32}
    )
    fusion = base.model_copy(
        update={"evidence": (*base.evidence, unrelated, requested)}
    )
    result = attach_native_evidence(payload, fusion, user_query="Include Figure 4-2.")
    assert "[[figure:" + "a" * 32 in result.answer_text
    assert "[[figure:" + "b" * 32 not in result.answer_text
    assert all(p.text in result.answer_text for p in payload.paragraphs)


def test_caption_next_page_selects_correct_table_not_similar_section() -> None:
    """A caption at a page boundary identifies rows without pulling other tables."""
    state = verified_answer_state()
    payload = AnswerPayload.model_validate(state["answer"])
    base = FusionResult.model_validate(state["fusion"])
    caption = verifier_passage(40, text="Table 4-2. Widget rates").model_copy(
        update={"page_number": 70}
    )
    rows = verifier_passage(
        41, text="| Widget | Rate |\n| --- | --- |\n| A | 4 |"
    ).model_copy(
        update={
            "content_kind": "table",
            "page_number": 71,
            "version_id": caption.version_id,
        }
    )
    wrong = rows.model_copy(update={"chunk_id": "wrong", "page_number": 20})
    fusion = base.model_copy(update={"evidence": (caption, wrong, rows)})
    selected = relevant_native_fusion(payload, fusion, "Show Table 4-2.")
    assert rows in selected.evidence
    assert wrong not in selected.evidence


@pytest.mark.parametrize("reference", ["Figure 4-2", "Fig. 4-2", "الشكل 4-2"])
def test_answer_figure_reference_places_exact_asset_without_explicit_request(
    reference: str,
) -> None:
    """An answer's exact figure label displays the authorized matching image."""
    state = verified_answer_state()
    payload = AnswerPayload.model_validate(state["answer"])
    paragraph = payload.paragraphs[0].model_copy(
        update={"text": f"See {reference} for the lifecycle."}
    )
    payload = payload.model_copy(
        update={"paragraphs": (paragraph,), "answer_text": paragraph.text}
    )
    base = FusionResult.model_validate(state["fusion"])
    target = verifier_passage(30, text="Figure 4-2. Widget lifecycle.").model_copy(
        update={"content_kind": "figure", "figure_id": "a" * 32}
    )
    other = verifier_passage(31, text="Figure 4-3. Other lifecycle.").model_copy(
        update={"content_kind": "figure", "figure_id": "b" * 32}
    )
    fusion = base.model_copy(update={"evidence": (*base.evidence, target, other)})
    result = attach_native_evidence(
        payload, fusion, user_query="Explain the lifecycle."
    )
    assert "[[figure:" + "a" * 32 in result.answer_text
    assert "[[figure:" + "b" * 32 not in result.answer_text
    assert paragraph.text in result.answer_text


def test_named_function_keeps_long_body_with_bounded_exact_citation_slices() -> None:
    """The citation span cap does not silently truncate a fitting code body."""
    state = verified_answer_state()
    base = FusionResult.model_validate(state["fusion"])
    code = (
        "def choose_widget():\n"
        + "    widget = 'source value'\n" * 43
        + "    return widget"
    )
    assert 1000 < len(code) < 1900
    passage = verifier_passage(50, text=code)
    fusion = base.model_copy(update={"evidence": (passage,)})
    result = salvage_named_code_definition(
        AnswerPayload.model_validate(state["answer"]),
        fusion,
        user_query="Reproduce choose_widget, keeping its original implementation.",
    )
    assert "return widget" in result.answer_text
    assert len(result.citations) == 2
    assert all(
        citation.span is not None
        and citation.span in code
        and len(citation.span) <= 1000
        for citation in result.citations
    )


def test_verifier_failure_is_not_relabelled_as_empty_retrieval() -> None:
    """The terminal stream keeps the checkpoint's actual failure category."""
    from smart_rag_agents.query.nodes.release_safety import refuse_release

    state = refuse_release(verified_answer_state(), "verifier_schema_invalid")
    payload = AnswerPayload.model_validate(state["answer"])
    events, _, _ = emit_verified_events(payload, dict(state))
    assert ("partial", {"reason": "verification_unavailable"}) in events
    assert ("limitation", {"code": "insufficient_evidence"}) not in events


def test_table_rows_beat_a_caption_only_passage() -> None:
    """Equal caption scores cannot discard the actual row-bearing source."""
    from smart_rag_core.query_answer.generate_code_salvage import (
        salvage_named_table_block,
    )

    state = verified_answer_state()
    base = FusionResult.model_validate(state["fusion"])
    caption = "Table 7-4. Widget choices"
    short = verifier_passage(70, text=caption, rank=1)
    full = verifier_passage(
        71,
        text=caption + "\n| Widget | Rate |\n| --- | --- |\n| Alpha | 9 |",
        rank=2,
    )
    result = salvage_named_table_block(
        AnswerPayload.model_validate(state["answer"]),
        base.model_copy(update={"evidence": (short, full)}),
        user_query="Show Table 7-4 as a table.",
    )
    assert "Alpha" in result.answer_text
    assert result.citations[0].chunk_id == full.chunk_id


def test_skipped_citation_does_not_steal_later_replay_position(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed first citation leaves index zero free for its later repair."""
    from smart_rag_core.query_answer.citations_persist import persist_answer_citations
    from smart_rag_core.query_answer.models import AnswerCitation
    from smart_rag_core.query_routing.preparation import caller_from_runtime

    from tests.support.query_runtime import authorized_runtime

    state = verified_answer_state()
    fusion = FusionResult.model_validate(state["fusion"])
    payload = AnswerPayload.model_validate(state["answer"])
    chunk = fusion.evidence[0].chunk_id
    payload = payload.model_copy(
        update={
            "citations": (
                AnswerCitation(chunk_id=chunk, span="unresolved", paragraph_index=0),
                AnswerCitation(
                    chunk_id=chunk, span="already stored", paragraph_index=1
                ),
            )
        }
    )
    seen: list[tuple[str, int]] = []

    def insert(*args: object, **kwargs: object) -> object:
        """Model an unresolved span and record the assigned stable index."""
        seen.append((str(kwargs["span"]), cast(int, kwargs["index"])))
        if kwargs["span"] == "unresolved":
            raise psycopg.errors.RaiseException("query_citation:span_not_contained")
        return uuid4()

    monkeypatch.setattr(
        "smart_rag_core.query_answer.citations_persist._insert_passage_citation", insert
    )
    result = persist_answer_citations(
        cast(psycopg.Connection, MagicMock()),
        caller=caller_from_runtime(authorized_runtime()),
        run_id=uuid4(),
        fusion=fusion,
        answer=payload,
    )
    assert len(result.skipped) == 1
    assert seen == [("unresolved", 0), ("already stored", 1)]


def test_answer_timeout_retry_uses_consumed_reservation_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A charged timeout cannot leave retry or verifier on a stale version."""
    from decimal import Decimal

    from smart_rag_agents.query.nodes.answer_attempts import run_answer_attempts
    from smart_rag_core.query_admission.exceptions import TimeoutAfterSendError
    from smart_rag_core.query_admission.service import ReservationConsumeResult
    from smart_rag_core.query_routing.preparation import caller_from_runtime

    from tests.support.query_runtime import authorized_runtime

    state = verified_answer_state()
    runtime = authorized_runtime()
    consumed = [
        ReservationConsumeResult(
            reservation_id=runtime.reservation_id,
            optimistic_version=i,
            remaining_usd=Decimal("1"),
            remaining_prompt_tokens=2000,
            remaining_completion_tokens=1000,
        )
        for i in (2, 3)
    ]
    consume = MagicMock(side_effect=consumed)
    ledger = MagicMock(return_value=uuid4())
    monkeypatch.setattr(
        "smart_rag_core.query_admission.usage.consume_query_reservation", consume
    )
    monkeypatch.setattr(
        "smart_rag_core.query_admission.usage.record_query_llm_usage", ledger
    )
    send = MagicMock(side_effect=[TimeoutAfterSendError(), "answer"])
    result = run_answer_attempts(
        state,
        connection=MagicMock(),
        caller=caller_from_runtime(runtime),
        run_id=runtime.run_id,
        reservation_id=runtime.reservation_id,
        expected_version=1,
        model_id="gpt-4o-mini",
        send=send,
        usage_from_result=lambda _: (4, 2, None),
        context=runtime,
        remaining_model_calls=2,
    )
    assert result[0] == "answer"
    assert [call.kwargs["expected_version"] for call in consume.call_args_list] == [
        1,
        2,
    ]
    assert ledger.call_count == 2
    updated = state.get("authorized_runtime")
    assert isinstance(updated, dict) and updated["optimistic_version"] == 3


def test_long_named_table_keeps_all_rows_across_page_footer() -> None:
    """A table longer than one citation remains complete and exactly sourced."""
    from smart_rag_core.query_answer.table_copy import copy_pipe_table

    state = verified_answer_state()
    rows = [f"| Widget-{i} | " + "source-cell " * 24 + "|" for i in range(9)]
    header = "| Widget | Description |\n| --- | --- |\n"
    text = "Table 7-4. Widget choices\n" + header + "\n".join(rows[:5])
    text += "\n81 | Chapter 3: Example\n" + header + "\n".join(rows[5:])
    source = verifier_passage(80, text=text)
    result = copy_pipe_table(
        AnswerPayload.model_validate(state["answer"]), source, caption="Table 7-4"
    )
    assert result is not None
    assert result.status == "complete"
    assert 1 < len(result.paragraphs) <= 6
    assert all(row in result.answer_text for row in rows)
    assert "81 | Chapter" not in result.answer_text
    assert len(result.citations) <= 12
    assert all(
        c.span and c.span in text and len(c.span) <= 1000 for c in result.citations
    )


def test_code_definition_does_not_copy_following_module_harness() -> None:
    """The function ends at dedent, not at the arbitrary citation character cap."""
    state = verified_answer_state()
    base = FusionResult.model_validate(state["fusion"])
    text = "def choose_widget():\n    return 4\nbuilder = launch_other_workflow()"
    result = salvage_named_code_definition(
        AnswerPayload.model_validate(state["answer"]),
        base.model_copy(update={"evidence": (verifier_passage(90, text=text),)}),
        user_query="Show choose_widget and its complete original implementation.",
    )
    assert "return 4" in result.answer_text
    assert "launch_other_workflow" not in result.answer_text


def test_complete_definition_beats_an_earlier_signature_only_chunk() -> None:
    """A page-ending signature must not outrank the full canonical definition."""
    state = verified_answer_state()
    base = FusionResult.model_validate(state["fusion"])
    signature = verifier_passage(100, text="def choose_widget():", rank=1)
    full = verifier_passage(
        101, text="Example\ndef choose_widget():\n    return 7", rank=2
    )
    result = salvage_named_code_definition(
        AnswerPayload.model_validate(state["answer"]),
        base.model_copy(update={"evidence": (signature, full)}),
        user_query="Reproduce choose_widget, keeping the complete original implementation.",
    )
    assert "return 7" in result.answer_text


def test_provider_receives_original_arabic_instead_of_unicode_escape_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Inspect the actual SDK input before any provider work occurs."""
    import json

    from smart_rag_core.gateways.openai_answer import execute_openai_answer
    from smart_rag_core.query_answer.versions import (
        ANSWER_MODEL_ID,
        ANSWER_PROMPT_SHA256,
        ANSWER_PROMPT_VERSION,
    )

    class Captured(RuntimeError):
        """Stop at the fake SDK boundary after recording the request."""

    client = MagicMock()
    client.responses.create.side_effect = Captured()
    monkeypatch.setattr(
        "smart_rag_core.gateways.openai_answer.traced_openai_client",
        MagicMock(return_value=client),
    )
    question = "اشرح كيف يعمل النظام مع الحفاظ على المصادر."
    with pytest.raises(Captured):
        execute_openai_answer(
            api_key="synthetic-test-key",
            prompt_text="test instructions",
            prompt_sha256=ANSWER_PROMPT_SHA256,
            prompt_version=ANSWER_PROMPT_VERSION,
            model_id=ANSWER_MODEL_ID,
            user_query=question,
            source_records="source data",
            timeout_seconds=1,
        )
    sent = client.responses.create.call_args.kwargs["input"]
    assert question in sent
    assert "\\u0627" not in sent
    payload = json.loads(sent)
    assert payload["query"] == question
    assert payload["answer_language"] == "ar"


def test_provider_schema_enforces_reserved_category_table_capacity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reservation reaches the strict SDK schema, beyond prompt wording."""
    from smart_rag_core.gateways.openai_answer import execute_openai_answer
    from smart_rag_core.query_answer.versions import (
        ANSWER_MODEL_ID,
        ANSWER_PROMPT_SHA256,
        ANSWER_PROMPT_VERSION,
    )

    class Captured(RuntimeError):
        """Inspect a fake provider boundary without a paid call."""

    client = MagicMock()
    client.responses.create.side_effect = Captured()
    monkeypatch.setattr(
        "smart_rag_core.gateways.openai_answer.traced_openai_client",
        MagicMock(return_value=client),
    )
    with pytest.raises(Captured):
        execute_openai_answer(
            api_key="synthetic-test-key",
            prompt_text="instructions",
            prompt_sha256=ANSWER_PROMPT_SHA256,
            prompt_version=ANSWER_PROMPT_VERSION,
            model_id=ANSWER_MODEL_ID,
            user_query="Explain the security threats.",
            source_records="| Attack type | Description |\n| --- | --- |\n| Synthetic | Description |",
            timeout_seconds=1,
        )
    schema = client.responses.create.call_args.kwargs["text"]["format"]["schema"]
    assert schema["properties"]["claims"]["maxItems"] == 3

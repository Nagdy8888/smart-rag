"""Verifier responses stay bounded and unavailable outputs remain fail closed."""

from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock

import pytest
from smart_rag_core.gateways import openai_answer as adapter
from smart_rag_core.gateways.openai_answer import OpenAIAnswerError
from smart_rag_core.query_answer.verifier_output import (
    VERIFIER_REASON_CODES,
    keyed_verifier_schema,
    normalize_keyed_verdicts,
)
from smart_rag_core.query_answer.versions import (
    VERIFIER_MODEL_ID,
    VERIFIER_PROMPT_SHA256,
    VERIFIER_PROMPT_VERSION,
)


def _execute_response(response: object, monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise the public verifier adapter with a no-network provider reply."""
    client = SimpleNamespace(
        responses=SimpleNamespace(create=MagicMock(return_value=response))
    )
    monkeypatch.setattr(adapter, "traced_openai_client", MagicMock(return_value=client))
    adapter.execute_openai_verifier(
        api_key="synthetic-not-a-credential",
        prompt_text="Synthetic verifier",
        prompt_sha256=VERIFIER_PROMPT_SHA256,
        prompt_version=VERIFIER_PROMPT_VERSION,
        model_id=VERIFIER_MODEL_ID,
        source_records="Synthetic source",
        link_payload=[{"link_id": "claim-1", "claim": "Synthetic claim"}],
        link_ids=("claim-1",),
        timeout_seconds=1,
    )


def test_reason_schema_is_closed_and_compact_for_every_link() -> None:
    """Six verdicts cannot contain free-text explanations or copied passages."""
    keys = tuple(f"claim-{i}" for i in range(6))
    schema = keyed_verifier_schema(keys)
    outer = cast(dict[str, dict[str, object]], schema["properties"])
    properties = cast(
        dict[str, dict[str, object]], outer["link_verdicts"]["properties"]
    )
    for value in properties.values():
        fields = cast(dict[str, dict[str, object]], value["properties"])
        assert fields["reason"] == {
            "type": "string",
            "enum": list(VERIFIER_REASON_CODES),
        }
    assert all(code.isascii() and len(code) <= 21 for code in VERIFIER_REASON_CODES)


@pytest.mark.parametrize(
    ("supported", "reason"),
    [(True, "unsupported"), (False, "supported"), (True, "a copied explanation")],
)
def test_unknown_or_inconsistent_reason_cannot_authorize_a_claim(
    supported: bool, reason: str
) -> None:
    """Reason-code compaction never converts an invalid verdict into support."""
    with pytest.raises(ValueError, match="verifier_schema_invalid"):
        normalize_keyed_verdicts(
            {"link_verdicts": {"claim-1": {"supported": supported, "reason": reason}}},
            ("claim-1",),
        )


@pytest.mark.parametrize(
    ("detail", "expected"),
    [
        ("max_output_tokens", "verifier_output_limit"),
        ("content_filter", "verifier_content_filter"),
        ("untrusted provider detail", "verifier_incomplete"),
    ],
)
def test_incomplete_verifier_exports_only_allowlisted_metadata(
    detail: str, expected: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Provider details survive as safe codes, without exposing response text."""
    response = SimpleNamespace(
        status="incomplete", incomplete_details=SimpleNamespace(reason=detail)
    )
    with pytest.raises(OpenAIAnswerError) as error:
        _execute_response(response, monkeypatch)
    assert error.value.reason == expected


@pytest.mark.parametrize("refusal", [True, False])
def test_empty_output_and_refusal_are_distinguishable(
    refusal: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Neither an empty response nor an explicit refusal releases the draft."""
    response = SimpleNamespace(
        status="completed",
        usage=SimpleNamespace(input_tokens=100, output_tokens=5),
        output_text="",
        output=[SimpleNamespace(content=[SimpleNamespace(type="refusal")])]
        if refusal
        else [],
    )
    with pytest.raises(OpenAIAnswerError) as error:
        _execute_response(response, monkeypatch)
    assert error.value.reason == (
        "verifier_refusal" if refusal else "verifier_empty_output"
    )

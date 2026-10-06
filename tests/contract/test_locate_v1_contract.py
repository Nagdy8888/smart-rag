"""Pinned-SDK and gated live contract for the locate_v1 call."""

from __future__ import annotations

import json
import os
import typing
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

import pytest
from openai.types.responses import ResponseFormatTextJSONSchemaConfigParam
from smart_rag_agents.prompts import locate_prompt_text
from smart_rag_core.gateways.openai_answer import (
    OpenAIAnswerError,
    execute_openai_answer,
)
from smart_rag_core.models.env_pins import ANSWER_MODEL_ID
from smart_rag_core.query_answer.assembly import assemble_source_records
from smart_rag_core.query_answer.claims import parse_provider_answer
from smart_rag_core.query_answer.locate import located_quotes
from smart_rag_core.query_answer.versions import (
    LOCATE_PROMPT_SHA256,
    LOCATE_PROMPT_VERSION,
)
from smart_rag_core.settings.base import SharedSettings, load_settings

from tests.support.answer_verifier import verifier_fusion, verifier_passage


def _captured_format() -> dict[str, Any]:
    """Return the ``text.format`` object the adapter sends, without network.

    Returns:
        The format dict passed to ``responses.create``.
    """

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

            captured.update(kwargs)
            return SimpleNamespace(
                id="resp_sdk",
                status="completed",
                usage=SimpleNamespace(input_tokens=1, output_tokens=1),
                output_text=json.dumps(
                    {"claims": [], "conclusion": None, "status": "refused"}
                ),
            )

    class FakeOpenAI:
        """Stand-in client exposing ``responses``."""

        def __init__(self, **kwargs: Any) -> None:
            """Ignore constructor kwargs.

            Args:
                **kwargs: OpenAI client arguments.
            """

            del kwargs
            self.responses = FakeResponses()

    with patch(
        "smart_rag_core.gateways.openai_answer.traced_openai_client", FakeOpenAI
    ):
        execute_openai_answer(
            api_key="sk-test",
            prompt_text="locate",
            prompt_sha256=LOCATE_PROMPT_SHA256,
            prompt_version=LOCATE_PROMPT_VERSION,
            model_id=ANSWER_MODEL_ID,
            user_query="q",
            source_records=" ",
            timeout_seconds=5.0,
        )
    return cast(dict[str, Any], captured["text"]["format"])


def _live_key() -> str | None:
    """Return a usable OpenAI key, or ``None`` when live calls are off.

    Returns:
        API key string, or ``None`` in mock mode or without a key.
    """

    settings = load_settings(SharedSettings)
    if settings.mock_model_mode or settings.openai_api_key is None:
        return None
    key = settings.openai_api_key.get_secret_value().strip()
    if not key or key.upper().startswith("REPLACE"):
        return None
    return key


def test_locate_pin_uses_the_claims_format() -> None:
    """The adapter's format keys and literal type match the SDK TypedDict."""

    fmt = _captured_format()
    hints = typing.get_type_hints(ResponseFormatTextJSONSchemaConfigParam)
    assert set(fmt) <= set(hints)
    assert {"name", "schema", "type", "strict"} <= set(fmt)
    assert typing.get_args(hints["type"]) == ("json_schema",)
    assert fmt["type"] == "json_schema"
    assert fmt["strict"] is True
    assert fmt["name"] == "canonical_answer_claims"


def test_unknown_pin_is_rejected() -> None:
    """An unknown locate pin fails closed before any provider call."""

    with (
        patch("smart_rag_core.gateways.openai_answer.traced_openai_client"),
        pytest.raises(OpenAIAnswerError, match="answer_version_mismatch"),
    ):
        execute_openai_answer(
            api_key="sk-test",
            prompt_text="locate",
            prompt_sha256=LOCATE_PROMPT_SHA256,
            prompt_version="locate_v0",
            model_id=ANSWER_MODEL_ID,
            user_query="q",
            source_records=" ",
            timeout_seconds=5.0,
        )


@pytest.mark.skipif(
    os.environ.get("ANSWER_SCHEMA_LIVE") != "1",
    reason="ANSWER_SCHEMA_LIVE unset",
)
def test_locate_v1_live_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    """One real Responses call accepts the locate pin and returns a quote."""

    monkeypatch.setenv("MOCK_MODEL_MODE", "false")
    key = _live_key()
    if key is None:
        pytest.skip("OPENAI_API_KEY missing or MOCK_MODEL_MODE enabled")
    fusion = verifier_fusion(
        verifier_passage(1, text="The Atlas Controller ships in Q3."),
        verifier_passage(2, text="The Atlas Controller weighs 2 kg."),
    )
    chunk_ids = tuple(item.chunk_id for item in fusion.evidence)
    raw, request_id, input_tokens, _output_tokens = execute_openai_answer(
        api_key=key,
        prompt_text=locate_prompt_text(),
        prompt_sha256=LOCATE_PROMPT_SHA256,
        prompt_version=LOCATE_PROMPT_VERSION,
        model_id=ANSWER_MODEL_ID,
        user_query="When does the Atlas Controller ship?",
        source_records=assemble_source_records(fusion, ()),
        timeout_seconds=30.0,
    )
    payload = parse_provider_answer(raw, chunk_ids=chunk_ids, tables=())
    quotes = located_quotes(payload, fusion)
    assert request_id != "unknown"
    assert input_tokens > 0
    assert quotes
    assert quotes[0].chunk_id == chunk_ids[0]
    assert "Q3" in quotes[0].text

"""Unit tests for one-shot OpenAI Responses rerank calls."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from openai import APIStatusError, APITimeoutError
from smart_rag_core.gateways.openai_rerank import (
    OpenAIRerankError,
    execute_openai_rerank,
)
from smart_rag_core.retrieval.rerank import rerank_input_hash
from smart_rag_core.retrieval.rerank_versions import (
    RERANK_PROMPT_SHA256,
    RERANK_PROMPT_VERSION,
)

PROMPT = "rank only supplied ids"


def _run(first: str, second: str) -> tuple[dict[str, object], str, int, int]:
    """Invoke the adapter for two candidates.

    Args:
        first: First candidate id.
        second: Second candidate id.

    Returns:
        Adapter return tuple.

    Raises:
        OpenAIRerankError: Typed provider failure.
    """

    excerpts = ("alpha", "beta")
    digest = rerank_input_hash(
        query="q",
        candidate_ids=(first, second),
        excerpts=excerpts,
        prompt_sha256=RERANK_PROMPT_SHA256,
    )
    return execute_openai_rerank(
        api_key="sk-test",
        prompt_text=PROMPT,
        prompt_sha256=RERANK_PROMPT_SHA256,
        prompt_version=RERANK_PROMPT_VERSION,
        model_id="gpt-4o-mini",
        query="q",
        candidate_ids=(first, second),
        excerpts=excerpts,
        input_hash=digest,
        timeout_seconds=8.0,
    )


def test_create_omits_tools_and_disables_retries() -> None:
    """The adapter issues one Responses call with retries disabled and no tools."""

    first, second = str(uuid4()), str(uuid4())
    excerpts = ("alpha", "beta")
    digest = rerank_input_hash(
        query="q",
        candidate_ids=(first, second),
        excerpts=excerpts,
        prompt_sha256=RERANK_PROMPT_SHA256,
    )
    captured: dict[str, object] = {}

    class FakeResponses:
        """Capture ``responses.create`` kwargs."""

        def create(self, **kwargs: object) -> SimpleNamespace:
            """Return a completed structured payload.

            Args:
                **kwargs: SDK create arguments.

            Returns:
                Fake Responses object.
            """

            captured["create"] = kwargs
            payload = {
                "status": "complete",
                "input_hash": digest,
                "rankings": [
                    {"chunk_id": first, "rank": 1, "support": 0.9},
                    {"chunk_id": second, "rank": 2, "support": 0.1},
                ],
            }
            return SimpleNamespace(
                id="resp_1",
                status="completed",
                usage=SimpleNamespace(input_tokens=11, output_tokens=7),
                output_text=json.dumps(payload),
            )

    class FakeOpenAI:
        """Capture client constructor kwargs."""

        def __init__(self, **kwargs: object) -> None:
            """Store constructor kwargs.

            Args:
                **kwargs: OpenAI client arguments.
            """

            captured["client"] = kwargs
            self.responses = FakeResponses()

    with patch(
        "smart_rag_core.gateways.openai_rerank.traced_openai_client", FakeOpenAI
    ):
        payload, request_id, input_tokens, output_tokens = execute_openai_rerank(
            api_key="sk-test",
            prompt_text=PROMPT,
            prompt_sha256=RERANK_PROMPT_SHA256,
            prompt_version=RERANK_PROMPT_VERSION,
            model_id="gpt-4o-mini",
            query="q",
            candidate_ids=(first, second),
            excerpts=excerpts,
            input_hash=digest,
            timeout_seconds=8.0,
        )
    client_kwargs = captured["client"]
    create_kwargs = captured["create"]
    assert isinstance(client_kwargs, dict)
    assert isinstance(create_kwargs, dict)
    assert client_kwargs["max_retries"] == 0
    assert "tools" not in create_kwargs
    assert create_kwargs["store"] is False
    assert request_id == "resp_1"
    assert input_tokens == 11
    assert output_tokens == 7
    assert payload["status"] == "complete"


def test_timeout_maps_to_typed_fallback() -> None:
    """Provider timeouts become ``rerank_timeout`` without a local retry."""

    first, second = str(uuid4()), str(uuid4())

    class FakeResponses:
        """Raise a timeout on create."""

        def create(self, **kwargs: object) -> SimpleNamespace:
            """Abort the one operation.

            Args:
                **kwargs: Unused.

            Raises:
                APITimeoutError: Always.
            """

            raise APITimeoutError(request=MagicMock())

    class FakeOpenAI:
        """Return the timeout stub."""

        def __init__(self, **kwargs: object) -> None:
            """Ignore constructor kwargs.

            Args:
                **kwargs: Unused.
            """

            self.responses = FakeResponses()

    with (
        patch("smart_rag_core.gateways.openai_rerank.traced_openai_client", FakeOpenAI),
        pytest.raises(OpenAIRerankError, match="rerank_timeout"),
    ):
        _run(first, second)


def test_http_429_maps_to_budget_denied() -> None:
    """HTTP 429 is budget denial, not a hidden SDK retry."""

    first, second = str(uuid4()), str(uuid4())
    response = MagicMock()
    response.status_code = 429
    response.headers = {}
    error = APIStatusError("rate limited", response=response, body=None)

    class FakeResponses:
        """Raise 429 on create."""

        def create(self, **kwargs: object) -> SimpleNamespace:
            """Abort the one operation.

            Args:
                **kwargs: Unused.

            Raises:
                APIStatusError: Always 429.
            """

            raise error

    class FakeOpenAI:
        """Return the 429 stub."""

        def __init__(self, **kwargs: object) -> None:
            """Ignore constructor kwargs.

            Args:
                **kwargs: Unused.
            """

            self.responses = FakeResponses()

    with (
        patch("smart_rag_core.gateways.openai_rerank.traced_openai_client", FakeOpenAI),
        pytest.raises(OpenAIRerankError, match="rerank_budget_denied"),
    ):
        _run(first, second)


def test_incomplete_status_after_success_falls_back() -> None:
    """Timeout-after-success with incomplete status still has a request id."""

    first, second = str(uuid4()), str(uuid4())

    class FakeResponses:
        """Return usage with an incomplete status."""

        def create(self, **kwargs: object) -> SimpleNamespace:
            """Simulate provider success then incomplete output.

            Args:
                **kwargs: Unused.

            Returns:
                Incomplete Responses object with usage.
            """

            return SimpleNamespace(
                id="resp_incomplete",
                status="incomplete",
                usage=SimpleNamespace(input_tokens=9, output_tokens=0),
                output_text="",
            )

    class FakeOpenAI:
        """Return the incomplete stub."""

        def __init__(self, **kwargs: object) -> None:
            """Ignore constructor kwargs.

            Args:
                **kwargs: Unused.
            """

            self.responses = FakeResponses()

    with (
        patch("smart_rag_core.gateways.openai_rerank.traced_openai_client", FakeOpenAI),
        pytest.raises(OpenAIRerankError, match="rerank_incomplete"),
    ):
        _run(first, second)


def test_invalid_json_maps_to_schema_invalid() -> None:
    """Malformed JSON is ``rerank_schema_invalid``, not an untyped success."""

    first, second = str(uuid4()), str(uuid4())

    class FakeResponses:
        """Return completed usage with invalid JSON."""

        def create(self, **kwargs: object) -> SimpleNamespace:
            """Return non-JSON output text.

            Args:
                **kwargs: Unused.

            Returns:
                Completed Responses object with invalid JSON.
            """

            return SimpleNamespace(
                id="resp_invalid",
                status="completed",
                usage=SimpleNamespace(input_tokens=9, output_tokens=4),
                output_text="{not-json",
            )

    class FakeOpenAI:
        """Return the invalid-JSON stub."""

        def __init__(self, **kwargs: object) -> None:
            """Ignore constructor kwargs.

            Args:
                **kwargs: Unused.
            """

            self.responses = FakeResponses()

    with (
        patch("smart_rag_core.gateways.openai_rerank.traced_openai_client", FakeOpenAI),
        pytest.raises(OpenAIRerankError, match="rerank_schema_invalid"),
    ):
        _run(first, second)

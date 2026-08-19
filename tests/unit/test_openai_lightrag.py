"""Unit tests for one-shot OpenAI Responses LightRAG extract calls."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from openai import APIStatusError, APITimeoutError
from smart_rag_core.gateways.model import (
    LightRagLlmRequest,
    ModelGatewayUnavailableError,
    OpenAIRerankAdapter,
)
from smart_rag_core.gateways.openai_lightrag import (
    OpenAILightragError,
    estimate_lightrag_llm_cost,
    execute_openai_lightrag_llm,
)
from smart_rag_core.retrieval.graph import LIGHTRAG_LLM_MODEL_ID


def _extract(
    *,
    prompt: str = "extract these entities",
    system_prompt: str = "system",
) -> tuple[str, str, int, int, int, Decimal]:
    """Invoke the extract adapter.

    Args:
        prompt: Vendor user prompt.
        system_prompt: Vendor system prompt.

    Returns:
        Adapter return tuple.

    Raises:
        OpenAILightragError: Typed provider failure.
    """

    return execute_openai_lightrag_llm(
        api_key="sk-test",
        model_id=LIGHTRAG_LLM_MODEL_ID,
        prompt=prompt,
        system_prompt=system_prompt,
        timeout_seconds=25.0,
    )


def test_create_omits_tools_and_disables_retries() -> None:
    """The adapter issues one Responses call with retries disabled and no tools."""

    captured: dict[str, object] = {}

    class FakeResponses:
        """Capture ``responses.create`` kwargs."""

        def create(self, **kwargs: object) -> SimpleNamespace:
            """Return a completed extract payload.

            Args:
                **kwargs: SDK create arguments.

            Returns:
                Fake Responses object.
            """

            captured["create"] = kwargs
            return SimpleNamespace(
                id="resp_extract_1",
                status="completed",
                usage=SimpleNamespace(
                    input_tokens=40,
                    input_tokens_details=SimpleNamespace(cached_tokens=10),
                    output_tokens=12,
                ),
                output_text="entity<|#|>Alpha Probe<|#|>Concept<|#|>note\n<|COMPLETE|>",
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
        "smart_rag_core.gateways.openai_lightrag.traced_openai_client", FakeOpenAI
    ):
        (
            content,
            request_id,
            input_tokens,
            cached_input_tokens,
            output_tokens,
            estimated_cost_usd,
        ) = _extract()

    client_kwargs = captured["client"]
    create_kwargs = captured["create"]
    assert isinstance(client_kwargs, dict)
    assert client_kwargs["max_retries"] == 0
    assert client_kwargs["timeout"] == 25.0
    assert isinstance(create_kwargs, dict)
    assert "tools" not in create_kwargs
    assert create_kwargs["store"] is False
    assert create_kwargs["model"] == LIGHTRAG_LLM_MODEL_ID
    assert create_kwargs["instructions"] == "system"
    assert create_kwargs["input"] == "extract these entities"
    assert request_id == "resp_extract_1"
    assert input_tokens == 40
    assert cached_input_tokens == 10
    assert output_tokens == 12
    assert estimated_cost_usd == Decimal("0.0000206")
    assert "<|COMPLETE|>" in content


def test_timeout_maps_to_typed_error() -> None:
    """API timeouts become ``lightrag_llm_timeout``."""

    class FakeResponses:
        """Raise a timeout."""

        def create(self, **kwargs: object) -> None:
            """Reject the request.

            Args:
                **kwargs: Unused SDK arguments.
            """

            del kwargs
            raise APITimeoutError(request=MagicMock())

    class FakeOpenAI:
        """Return the timeout stub."""

        def __init__(self, **kwargs: object) -> None:
            """Ignore constructor kwargs.

            Args:
                **kwargs: OpenAI client arguments.
            """

            del kwargs
            self.responses = FakeResponses()

    with (
        patch(
            "smart_rag_core.gateways.openai_lightrag.traced_openai_client", FakeOpenAI
        ),
        pytest.raises(OpenAILightragError, match="lightrag_llm_timeout"),
    ):
        _extract()


def test_http_429_maps_to_budget_denied() -> None:
    """HTTP 429 becomes ``lightrag_llm_budget_denied``."""

    response = MagicMock()
    response.status_code = 429
    response.headers = {}
    error = APIStatusError("rate limited", response=response, body=None)

    class FakeResponses:
        """Raise HTTP 429."""

        def create(self, **kwargs: object) -> None:
            """Reject the request.

            Args:
                **kwargs: Unused SDK arguments.
            """

            del kwargs
            raise error

    class FakeOpenAI:
        """Return the 429 stub."""

        def __init__(self, **kwargs: object) -> None:
            """Ignore constructor kwargs.

            Args:
                **kwargs: OpenAI client arguments.
            """

            del kwargs
            self.responses = FakeResponses()

    with (
        patch(
            "smart_rag_core.gateways.openai_lightrag.traced_openai_client", FakeOpenAI
        ),
        pytest.raises(OpenAILightragError, match="lightrag_llm_budget_denied"),
    ):
        _extract()


def test_empty_output_is_incomplete() -> None:
    """Blank ``output_text`` is ``lightrag_llm_incomplete``."""

    class FakeResponses:
        """Return an empty body."""

        def create(self, **kwargs: object) -> SimpleNamespace:
            """Return a completed but empty payload.

            Args:
                **kwargs: Unused SDK arguments.

            Returns:
                Fake Responses object.
            """

            del kwargs
            return SimpleNamespace(
                id="resp_empty",
                status="completed",
                usage=SimpleNamespace(input_tokens=4, output_tokens=0),
                output_text="  ",
            )

    class FakeOpenAI:
        """Return the empty stub."""

        def __init__(self, **kwargs: object) -> None:
            """Ignore constructor kwargs.

            Args:
                **kwargs: OpenAI client arguments.
            """

            del kwargs
            self.responses = FakeResponses()

    with (
        patch(
            "smart_rag_core.gateways.openai_lightrag.traced_openai_client", FakeOpenAI
        ),
        pytest.raises(OpenAILightragError, match="lightrag_llm_incomplete"),
    ):
        _extract()


def test_cost_uses_cached_and_uncached_rates() -> None:
    """Cost applies the pinned cached-input rate only to cached tokens."""

    assert estimate_lightrag_llm_cost(
        input_tokens=1_000_000,
        cached_input_tokens=250_000,
        output_tokens=100_000,
    ) == Decimal("0.275")


def test_live_adapter_keyword_does_not_call_openai() -> None:
    """Keyword callbacks stay local so ingest cannot spend on keyword LLM."""

    adapter = OpenAIRerankAdapter(api_key="sk-test", max_input_chars=16_384)

    async def run() -> None:
        """Invoke the keyword callback."""

        with patch(
            "smart_rag_core.gateways.model.execute_openai_lightrag_llm"
        ) as mocked:
            response = await adapter.generate_lightrag_llm(
                LightRagLlmRequest(role="keyword", prompt="unused")
            )
        mocked.assert_not_called()
        assert response.mode == "local"
        assert "high_level_keywords" in response.content

    asyncio.run(run())


def test_live_adapter_extract_calls_openai() -> None:
    """Extract role forwards to the Responses helper."""

    adapter = OpenAIRerankAdapter(api_key="sk-test", max_input_chars=16_384)

    async def run() -> None:
        """Invoke the extract callback."""

        with patch(
            "smart_rag_core.gateways.model.execute_openai_lightrag_llm",
            return_value=(
                "entity-row\n<|COMPLETE|>",
                "resp_1",
                10,
                2,
                4,
                Decimal("0.0000064"),
            ),
        ) as mocked:
            response = await adapter.generate_lightrag_llm(
                LightRagLlmRequest(
                    role="extract",
                    prompt="chunk text",
                    system_prompt="extract",
                )
            )
        mocked.assert_called_once()
        assert mocked.call_args.kwargs["timeout_seconds"] == 90.0
        assert response.mode == "openai"
        assert response.content.endswith("<|COMPLETE|>")
        assert response.input_tokens == 10
        assert response.cached_input_tokens == 2
        assert response.output_tokens == 4
        assert response.total_tokens == 14
        assert response.estimated_cost_usd == Decimal("0.0000064")

    asyncio.run(run())


def test_live_adapter_refuses_vlm() -> None:
    """Multimodal LightRAG callbacks stay unavailable."""

    adapter = OpenAIRerankAdapter(api_key="sk-test", max_input_chars=16_384)

    async def run() -> None:
        """Invoke the refused multimodal callback."""

        with pytest.raises(
            ModelGatewayUnavailableError, match="lightrag_llm_role_not_configured"
        ):
            await adapter.generate_lightrag_llm(
                LightRagLlmRequest(role="vlm", prompt="image")
            )

    asyncio.run(run())

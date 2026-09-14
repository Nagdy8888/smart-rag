"""Unit tests for bake-off OpenAI page OCR Responses calls."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from openai import APIStatusError, APITimeoutError
from smart_rag_core.evaluation.parser_bakeoff.constants import (
    OPENAI_OCR_MAX_OUTPUT_TOKENS,
)
from smart_rag_core.gateways.openai_page_ocr import (
    OpenAIPageOcrError,
    execute_openai_page_ocr,
)
from smart_rag_core.models.env_pins import ANSWER_MODEL_ID

PNG = b"\x89PNG\r\n\x1a\n" + b"raster"


def _ocr(**kwargs: object) -> tuple[str, str, int, int]:
    """Invoke the page OCR adapter.

    Args:
        **kwargs: Optional overrides for the adapter call.

    Returns:
        Adapter return tuple.
    """

    payload: dict[str, Any] = {
        "api_key": "sk-test",
        "model_id": ANSWER_MODEL_ID,
        "image_png": PNG,
        "image_sha256": "abc123",
        "page_index": 7,
        "timeout_seconds": 60.0,
    }
    payload.update(kwargs)
    return execute_openai_page_ocr(
        api_key=str(payload["api_key"]),
        model_id=str(payload["model_id"]),
        image_png=bytes(payload["image_png"]),
        image_sha256=str(payload["image_sha256"]),
        page_index=int(payload["page_index"]),
        timeout_seconds=float(payload["timeout_seconds"]),
    )


def test_create_uses_data_url_store_false_no_files_or_retries() -> None:
    """The adapter sends one high-detail PNG and never uses the Files API."""

    captured: dict[str, object] = {}

    class FakeResponses:
        """Capture ``responses.create`` kwargs."""

        def create(self, **kwargs: object) -> SimpleNamespace:
            """Return a completed OCR payload.

            Args:
                **kwargs: SDK create arguments.

            Returns:
                Fake Responses object.
            """

            captured["create"] = kwargs
            return SimpleNamespace(
                id="resp_ocr_1",
                status="completed",
                usage=SimpleNamespace(input_tokens=80, output_tokens=12),
                output_text="# Heading\n\nVisible line.\n",
            )

    class FakeOpenAI:
        """Capture client constructor kwargs."""

        def __init__(self, **kwargs: object) -> None:
            """Store constructor kwargs.

            Args:
                **kwargs: OpenAI client arguments.
            """

            captured["client"] = kwargs
            self.files = SimpleNamespace(create=MagicMock())
            captured["files"] = self.files
            self.responses = FakeResponses()

    with patch("smart_rag_core.gateways.openai_page_ocr.OpenAI", FakeOpenAI):
        markdown, request_id, input_tokens, output_tokens = _ocr()

    client_kwargs = captured["client"]
    create_kwargs = captured["create"]
    assert isinstance(client_kwargs, dict)
    assert client_kwargs["max_retries"] == 0
    assert client_kwargs["timeout"] == 60.0
    assert isinstance(create_kwargs, dict)
    assert create_kwargs["store"] is False
    assert "tools" not in create_kwargs
    assert create_kwargs["model"] == ANSWER_MODEL_ID
    assert create_kwargs["max_output_tokens"] == OPENAI_OCR_MAX_OUTPUT_TOKENS
    content = create_kwargs["input"][0]["content"]  # type: ignore[index]
    image = cast(dict[str, object], content[1])
    assert image["type"] == "input_image"
    assert image["detail"] == "high"
    assert str(image["image_url"]).startswith("data:image/png;base64,")
    assert request_id == "resp_ocr_1"
    assert input_tokens == 80
    assert output_tokens == 12
    assert "Visible line" in markdown
    files = captured["files"]
    assert isinstance(files, SimpleNamespace)
    assert files.create.call_count == 0


def test_empty_page_output_is_allowed() -> None:
    """Blank OCR output is valid for a page with no visible text."""

    class FakeResponses:
        """Return empty transcription."""

        def create(self, **kwargs: object) -> SimpleNamespace:
            """Return a completed empty payload.

            Args:
                **kwargs: Unused SDK arguments.

            Returns:
                Fake Responses object.
            """

            del kwargs
            return SimpleNamespace(
                id="resp_empty",
                status="completed",
                usage=SimpleNamespace(input_tokens=40, output_tokens=0),
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

    with patch("smart_rag_core.gateways.openai_page_ocr.OpenAI", FakeOpenAI):
        markdown, request_id, _input_tokens, output_tokens = _ocr()
    assert markdown == ""
    assert request_id == "resp_empty"
    assert output_tokens == 0


def test_timeout_maps_to_typed_error() -> None:
    """API timeouts become ``openai_ocr_timeout``."""

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
        patch("smart_rag_core.gateways.openai_page_ocr.OpenAI", FakeOpenAI),
        pytest.raises(OpenAIPageOcrError, match="openai_ocr_timeout"),
    ):
        _ocr()


def test_http_429_maps_to_budget_denied() -> None:
    """HTTP 429 becomes ``openai_ocr_budget_denied``."""

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
        patch("smart_rag_core.gateways.openai_page_ocr.OpenAI", FakeOpenAI),
        pytest.raises(OpenAIPageOcrError, match="openai_ocr_budget_denied"),
    ):
        _ocr()


def test_model_mismatch_fails_closed() -> None:
    """A non-allow-listed model does not call the SDK."""

    with (
        patch("smart_rag_core.gateways.openai_page_ocr.OpenAI") as mocked,
        pytest.raises(OpenAIPageOcrError, match="openai_ocr_model_mismatch"),
    ):
        _ocr(model_id="gpt-5")
    mocked.assert_not_called()

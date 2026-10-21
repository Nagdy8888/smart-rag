"""Figure spans never export raster bytes, credentials, or descriptions."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from smart_rag_core.observability.figure_tracing import (
    redact_figure_inputs,
    redact_figure_outputs,
)
from smart_rag_core.observability.langsmith_tracing import traced_openai_client


def test_figure_redaction_stays_private_with_io_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An IO opt-in cannot disclose company image content or extracted text."""
    monkeypatch.setenv("LANGSMITH_EXPORT_IO", "true")
    inputs = redact_figure_inputs(
        {
            "api_key": "secret-canary",
            "image_png": b"private-pixels",
            "image_url": "secret-url",
        }
    )
    outputs = redact_figure_outputs({"output": "private-description"})
    assert inputs["image_bytes"] == 14
    assert outputs["description_chars"] == 19
    for canary in (
        "secret-canary",
        "private-pixels",
        "secret-url",
        "private-description",
    ):
        assert canary not in repr((inputs, outputs))


def test_figure_sdk_payload_is_not_wrapped() -> None:
    """The metadata span replaces the SDK span so base64 is never exported."""
    client = MagicMock()
    with (
        patch(
            "smart_rag_core.observability.langsmith_tracing.OpenAI", return_value=client
        ),
        patch(
            "smart_rag_core.observability.langsmith_tracing.tracing_is_enabled",
            return_value=True,
        ),
        patch("langsmith.wrappers.wrap_openai") as wrap,
    ):
        assert (
            traced_openai_client(api_key="inert-canary", timeout=2, trace_payload=False)
            is client
        )
        wrap.assert_not_called()


def test_non_text_figure_output_is_not_exported() -> None:
    """Unknown provider payload shapes are dropped rather than serialized."""
    assert redact_figure_outputs({"unknown": "private-description"}) == {}

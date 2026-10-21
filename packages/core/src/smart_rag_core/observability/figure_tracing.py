"""Metadata-only tracing for sensitive figure descriptions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from smart_rag_core.observability.langsmith_tracing import (
    current_correlation_ids,
    short_content_hash,
    traceable,
)


def redact_figure_inputs(inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Allow only bounded operational metadata, even with IO export enabled."""
    image = inputs.get("image_png")
    return {
        "correlation": current_correlation_ids(),
        "image_bytes": len(image) if isinstance(image, bytes) else 0,
        "prompt_version": "figure_description_v1",
    }


def redact_figure_outputs(outputs: object) -> dict[str, object]:
    """Hash descriptions without exporting company labels or image content."""
    if isinstance(outputs, Mapping):
        outputs = cast(Mapping[str, object], outputs).get("output")
    if not isinstance(outputs, str):
        return {}
    return {
        "description_chars": len(outputs),
        "description_sha256": short_content_hash(outputs),
    }


def figure_responses_traceable(func: Any) -> Any:
    """Wrap a figure gateway in a metadata-only LLM span."""
    return traceable(
        name="openai.responses.figure_description",
        run_type="llm",
        process_inputs=redact_figure_inputs,
        process_outputs=redact_figure_outputs,
    )(func)

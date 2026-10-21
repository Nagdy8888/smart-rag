"""One budgeted vision call that describes a stored figure. No retries."""

from __future__ import annotations

import base64

from openai import APIStatusError, APITimeoutError, AuthenticationError

from smart_rag_core.ingestion.figures.limits import (
    FIGURE_DESCRIPTION_MAX_CHARS,
    FIGURE_MAX_PNG_BYTES,
)
from smart_rag_core.models.env_pins import ALLOWED_ANSWER_MODEL_IDS
from smart_rag_core.observability.figure_tracing import figure_responses_traceable
from smart_rag_core.observability.langsmith_tracing import traced_openai_client

FIGURE_PROMPT = (
    "Describe only what is visible in this figure. Do not invent labels, "
    "numbers, or relationships that are not shown. If the image has no "
    "informational content, return an empty response."
)


class FigureDescriptionError(RuntimeError):
    """Typed provider failure for one figure description."""

    def __init__(self, reason: str) -> None:
        """Store a machine-readable reason.

        Args:
            reason: Short reason code such as ``figure_timeout``.
        """

        super().__init__(reason)
        self.reason = reason


@figure_responses_traceable
def execute_figure_description(
    *,
    api_key: str,
    model_id: str,
    image_png: bytes,
    timeout_seconds: float,
) -> str:
    """Describe one figure PNG with the allow-listed chat model.

    Args:
        api_key: Provider credential. Never logged.
        model_id: Must be an allow-listed answer model.
        image_png: PNG bytes, bounded by ``FIGURE_MAX_PNG_BYTES``.
        timeout_seconds: Client timeout. SDK retries are disabled.

    Returns:
        Visible-content description, or an empty string.

    Raises:
        FigureDescriptionError: Timeout, auth, HTTP, or bound failure.

    Side Effects:
        One HTTPS Responses request. ``max_retries=0``. ``store=False``.
    """

    if model_id not in ALLOWED_ANSWER_MODEL_IDS:
        raise FigureDescriptionError("figure_model_mismatch")
    if timeout_seconds <= 0 or not image_png or len(image_png) > FIGURE_MAX_PNG_BYTES:
        raise FigureDescriptionError("figure_budget_denied")
    encoded = base64.standard_b64encode(image_png).decode("ascii")
    client = traced_openai_client(
        api_key=api_key, max_retries=0, timeout=timeout_seconds, trace_payload=False
    )
    try:
        response = client.responses.create(
            model=model_id,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": FIGURE_PROMPT},
                        {
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{encoded}",
                            "detail": "low",
                        },
                    ],
                }
            ],
            max_output_tokens=300,
            store=False,
        )
    except APITimeoutError as error:
        raise FigureDescriptionError("figure_timeout") from error
    except AuthenticationError as error:
        raise FigureDescriptionError("figure_provider_error") from error
    except APIStatusError as error:
        raise FigureDescriptionError("figure_provider_error") from error
    text = str(getattr(response, "output_text", "") or "").strip()
    return text[:FIGURE_DESCRIPTION_MAX_CHARS]

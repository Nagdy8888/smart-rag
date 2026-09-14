"""OpenAI Responses adapter for one bake-off PDF page OCR call.

Experiment-only. Sends one page raster through the shared gateway. Never used
by production ``ParserService``. The parser sandbox never receives the API key.
"""

from __future__ import annotations

import base64
import hashlib

from openai import APIStatusError, APITimeoutError, AuthenticationError, OpenAI

from smart_rag_core.evaluation.parser_bakeoff.constants import (
    OPENAI_OCR_MAX_IMAGE_BYTES,
    OPENAI_OCR_MAX_OUTPUT_CHARS,
    OPENAI_OCR_MAX_OUTPUT_TOKENS,
)
from smart_rag_core.models.env_pins import ALLOWED_ANSWER_MODEL_IDS, ANSWER_MODEL_ID
from smart_rag_core.observability.langsmith_tracing import (
    estimate_traced_chat_cost_usd,
    page_ocr_responses_traceable,
    record_current_usage_metadata,
)

PAGE_OCR_PROMPT = (
    "Extract every readable character from this single PDF page as Markdown. "
    "Transcribe printed and handwritten text only. Do not describe figures, "
    "charts, or decoration. Do not invent words that are not visible. "
    "If the page has no text, return an empty response."
)
PAGE_OCR_PROMPT_SHA256 = hashlib.sha256(PAGE_OCR_PROMPT.encode("utf-8")).hexdigest()


class OpenAIPageOcrError(RuntimeError):
    """Typed provider failure for one bake-off page OCR call."""

    def __init__(self, reason: str) -> None:
        """Store a machine-readable reason.

        Args:
            reason: Short reason code such as ``openai_ocr_timeout``.
        """

        super().__init__(reason)
        self.reason = reason


@page_ocr_responses_traceable
def execute_openai_page_ocr(
    *,
    api_key: str,
    model_id: str,
    image_png: bytes,
    image_sha256: str,
    page_index: int,
    timeout_seconds: float,
) -> tuple[str, str, int, int]:
    """OCR one PDF page raster with the allow-listed chat model.

    Args:
        api_key: Provider credential. Never logged.
        model_id: Must be the pinned answer model.
        image_png: PNG bytes of one page. Bound by ``OPENAI_OCR_MAX_IMAGE_BYTES``.
        image_sha256: SHA-256 of ``image_png`` for traces.
        page_index: 1-indexed page number for traces only.
        timeout_seconds: Client timeout. SDK retries are disabled.

    Returns:
        Markdown transcription, provider request id, input tokens, output
        tokens. Empty Markdown is allowed for a blank page.

    Raises:
        OpenAIPageOcrError: Timeout, auth, HTTP, bound, or incomplete output.

    Side Effects:
        One HTTPS Responses request. ``max_retries=0``. ``store=False``.
        No Files API upload. The client is not ``wrap_openai``-wrapped so
        page rasters cannot enter LangSmith child spans.
    """

    del image_sha256
    if model_id not in ALLOWED_ANSWER_MODEL_IDS:
        raise OpenAIPageOcrError("openai_ocr_model_mismatch")
    if timeout_seconds <= 0:
        raise OpenAIPageOcrError("openai_ocr_budget_denied")
    if page_index < 1:
        raise OpenAIPageOcrError("openai_ocr_invalid_page")
    if not image_png:
        raise OpenAIPageOcrError("openai_ocr_empty_image")
    if len(image_png) > OPENAI_OCR_MAX_IMAGE_BYTES:
        raise OpenAIPageOcrError("openai_ocr_image_limit")
    encoded = base64.standard_b64encode(image_png).decode("ascii")
    client = OpenAI(api_key=api_key, max_retries=0, timeout=timeout_seconds)
    try:
        response = client.responses.create(
            model=model_id,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": PAGE_OCR_PROMPT},
                        {
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{encoded}",
                            "detail": "high",
                        },
                    ],
                }
            ],
            max_output_tokens=OPENAI_OCR_MAX_OUTPUT_TOKENS,
            store=False,
        )
    except APITimeoutError as error:
        raise OpenAIPageOcrError("openai_ocr_timeout") from error
    except AuthenticationError as error:
        raise OpenAIPageOcrError("openai_ocr_provider_error") from error
    except APIStatusError as error:
        if error.status_code == 429:
            raise OpenAIPageOcrError("openai_ocr_budget_denied") from error
        raise OpenAIPageOcrError("openai_ocr_provider_error") from error
    request_id = str(getattr(response, "id", "") or "unknown")
    status = getattr(response, "status", None)
    if status not in {None, "completed"}:
        raise OpenAIPageOcrError("openai_ocr_incomplete")
    usage = getattr(response, "usage", None)
    if usage is None:
        raise OpenAIPageOcrError("openai_ocr_unknown_usage")
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    text = str(getattr(response, "output_text", "") or "")
    markdown = _strip_markdown_fence(text)
    if len(markdown) > OPENAI_OCR_MAX_OUTPUT_CHARS:
        raise OpenAIPageOcrError("openai_ocr_incomplete")
    record_current_usage_metadata(
        provider="openai",
        model=model_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_cost_usd=estimate_traced_chat_cost_usd(
            input_tokens=input_tokens, output_tokens=output_tokens
        ),
    )
    return markdown, request_id, input_tokens, output_tokens


def default_page_ocr_model() -> str:
    """Return the allow-listed bake-off page OCR model.

    Returns:
        Pinned ``ANSWER_MODEL_ID``.
    """

    return ANSWER_MODEL_ID


def _strip_markdown_fence(text: str) -> str:
    """Remove an optional wrapping Markdown fence.

    Args:
        text: Model output.

    Returns:
        Inner text without a `` ``` `` wrapper.
    """

    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) >= 2 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return stripped

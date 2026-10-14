"""Figure description callable used by the indexing graph."""

from __future__ import annotations

from collections.abc import Callable

from smart_rag_core.gateways.openai_figure import (
    FigureDescriptionError,
    execute_figure_description,
)
from smart_rag_core.models.env_pins import ANSWER_MODEL_ID
from smart_rag_core.settings.base import SharedSettings


def figure_describer(*, mock_model_mode: bool) -> Callable[[bytes], str]:
    """Return a describer that is a no-op in mock mode or without a key.

    Args:
        mock_model_mode: True in tests and local mock indexing.

    Returns:
        Callable from PNG bytes to a description or an empty string.
        Provider failures stay empty so the image is still stored.
    """

    def describe(png: bytes) -> str:
        """Describe one PNG, or return empty when the call is unavailable."""

        if mock_model_mode or not png:
            return ""
        settings = SharedSettings()
        secret = settings.openai_api_key
        if secret is None:
            return ""
        try:
            return execute_figure_description(
                api_key=secret.get_secret_value(),
                model_id=ANSWER_MODEL_ID,
                image_png=png,
                timeout_seconds=20.0,
            )
        except FigureDescriptionError:
            return ""

    return describe

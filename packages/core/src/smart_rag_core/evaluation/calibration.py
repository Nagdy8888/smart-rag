"""Development-only calibration entrypoint. Qualification is a separate confirm."""

from __future__ import annotations

from smart_rag_core.evaluation.loader import load_development_cases
from smart_rag_core.evaluation.schema import EvaluationCase


def load_tuning_cases() -> list[EvaluationCase]:
    """Return development cases for threshold calibration.

    Qualification is confirmed once after freeze and is not a tuning set.
    The sealed launch split is unreachable from this module.

    Returns:
        Development-split labeled cases only.
    """

    return load_development_cases()

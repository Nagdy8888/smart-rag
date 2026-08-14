"""Open-split calibration entrypoint. Packet 6 owns actual tuning."""

from __future__ import annotations

from smart_rag_core.evaluation.loader import load_open_splits
from smart_rag_core.evaluation.schema import EvaluationCase


def load_tuning_cases() -> list[EvaluationCase]:
    """Return development and qualification cases for calibration.

    The sealed launch split is unreachable from this module. Packet 6 may
    tune thresholds using these cases only.

    Returns:
        Open-split labeled cases. No sealed-split case is included even when
        process environment would authorize that access.
    """

    return load_open_splits()

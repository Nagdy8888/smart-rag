"""Offline query-profile evaluation over open splits only."""

from __future__ import annotations

from smart_rag_core.evaluation.loader import load_open_splits
from smart_rag_core.evaluation.schema import DatasetSplit, EvaluationCase
from smart_rag_core.query_profile.metrics import ProfileEvalReport, score_cases


def _by_split(cases: list[EvaluationCase], split: DatasetSplit) -> list[EvaluationCase]:
    """Filter open-split cases to one split.

    Args:
        cases: Development and qualification cases.
        split: Requested open split.

    Returns:
        Matching cases.

    Raises:
        ValueError: If holdout is requested.
    """

    if split is DatasetSplit.HOLDOUT:
        raise ValueError("holdout_scoring_forbidden")
    return [case for case in cases if case.split is split]


def evaluate_open_splits() -> tuple[ProfileEvalReport, ProfileEvalReport]:
    """Score development then qualification. Holdout is unreachable.

    Returns:
        Development report then qualification report.

    Side Effects:
        None. Uses ``load_open_splits`` only.
    """

    cases = load_open_splits()
    development = score_cases(
        _by_split(cases, DatasetSplit.DEVELOPMENT),
        split=DatasetSplit.DEVELOPMENT.value,
    )
    qualification = score_cases(
        _by_split(cases, DatasetSplit.QUALIFICATION),
        split=DatasetSplit.QUALIFICATION.value,
    )
    return development, qualification

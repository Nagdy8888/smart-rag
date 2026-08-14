"""Load Phase 4 cases with holdout sealed by default."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from smart_rag_core.evaluation.generator import generate_corpus
from smart_rag_core.evaluation.holdout import (
    HoldoutAccess,
    assert_holdout_allowed,
)
from smart_rag_core.evaluation.schema import DatasetSplit, EvaluationCase

AuditCallback = Callable[[str, str, str], None]


def load_cases(
    *,
    splits: Sequence[DatasetSplit],
    holdout_access: HoldoutAccess | None = None,
    audit: AuditCallback | None = None,
) -> list[EvaluationCase]:
    """Load labeled cases for the requested splits.

    Holdout labels are materialized only when ``holdout_access`` is an
    allow-listed authorized token. Calibration must pass
    ``HoldoutAccess.denied()`` and must not include the holdout split.

    Args:
        splits: Requested splits.
        holdout_access: Access token. Defaults to deny-by-default.
        audit: Optional callback invoked with purpose, actor, and action when
            holdout is opened. Used by seal/verify tooling.

    Returns:
        Cases whose split is in ``splits``, ordered by case id.

    Raises:
        HoldoutSealedError: If holdout is requested without authorization.
    """

    requested = frozenset(splits)
    access = holdout_access if holdout_access is not None else HoldoutAccess.denied()
    if DatasetSplit.HOLDOUT in requested:
        assert_holdout_allowed(access)
        if (
            audit is not None
            and access.purpose is not None
            and access.actor is not None
        ):
            audit(access.purpose, access.actor, "materialize_holdout")
    corpus = generate_corpus()
    return [case for case in corpus if case.split in requested]


def load_development_cases() -> list[EvaluationCase]:
    """Load development cases only. Qualification and holdout stay sealed.

    Returns:
        Development-split labeled cases for threshold tuning.
    """

    return load_cases(
        splits=(DatasetSplit.DEVELOPMENT,),
        holdout_access=HoldoutAccess.denied(),
    )


def load_qualification_cases() -> list[EvaluationCase]:
    """Load qualification cases only. Holdout stays sealed.

    Returns:
        Qualification-split labeled cases for one frozen confirmation.
    """

    return load_cases(
        splits=(DatasetSplit.QUALIFICATION,),
        holdout_access=HoldoutAccess.denied(),
    )


def load_open_splits() -> list[EvaluationCase]:
    """Load development and qualification cases only.

    Returns:
        Holdout-blind cases for profiling and open-split reports.

    Raises:
        HoldoutSealedError: Never, because holdout is not requested.
    """

    return load_cases(
        splits=(DatasetSplit.DEVELOPMENT, DatasetSplit.QUALIFICATION),
        holdout_access=HoldoutAccess.denied(),
    )

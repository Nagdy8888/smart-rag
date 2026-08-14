"""Deterministic source-family split allocation for Phase 4 datasets."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from smart_rag_core.evaluation.schema import DatasetSplit


def allocate_split_targets(case_count: int) -> tuple[int, int, int]:
    """Return development, qualification, and holdout target counts.

    Uses the signed default 50% / 25% / remainder allocation and then steals
    from development when needed so every class has at least one qualification
    and one holdout case.

    Args:
        case_count: Number of cases in one query class. Must be at least 2.

    Returns:
        ``(development, qualification, holdout)`` counts that sum to
        ``case_count``.

    Raises:
        ValueError: If ``case_count`` is less than 2.
    """

    if case_count < 2:
        raise ValueError("each class needs at least two cases for qual and holdout")
    development = case_count // 2
    qualification = case_count // 4
    holdout = case_count - development - qualification
    if qualification < 1:
        development -= 1
        qualification = 1
    if holdout < 1:
        development -= 1
        holdout = 1
    return development, qualification, holdout


def assign_families_to_splits(
    family_sizes: Mapping[str, int],
) -> dict[str, DatasetSplit]:
    """Assign whole source families to splits without splitting a family.

    Args:
        family_sizes: Mapping of family id to case count. Keys are assigned in
            sorted order for reproducibility.

    Returns:
        Mapping of family id to split. Qualification and holdout each receive
        at least one family.

    Raises:
        ValueError: If fewer than two families exist so qual and holdout cannot
            both be populated.
    """

    if len(family_sizes) < 2:
        raise ValueError("need at least two source families for disjoint splits")
    total = sum(family_sizes.values())
    development_n, qualification_n, holdout_n = allocate_split_targets(total)
    ordered = sorted(family_sizes)
    assignment: dict[str, DatasetSplit] = {}
    assignment[ordered[0]] = DatasetSplit.HOLDOUT
    assignment[ordered[1]] = DatasetSplit.QUALIFICATION
    counts = {
        DatasetSplit.DEVELOPMENT: 0,
        DatasetSplit.QUALIFICATION: family_sizes[ordered[1]],
        DatasetSplit.HOLDOUT: family_sizes[ordered[0]],
    }
    for family_id in ordered[2:]:
        size = family_sizes[family_id]
        remaining = {
            DatasetSplit.DEVELOPMENT: development_n - counts[DatasetSplit.DEVELOPMENT],
            DatasetSplit.QUALIFICATION: (
                qualification_n - counts[DatasetSplit.QUALIFICATION]
            ),
            DatasetSplit.HOLDOUT: holdout_n - counts[DatasetSplit.HOLDOUT],
        }
        chosen = max(
            (
                DatasetSplit.DEVELOPMENT,
                DatasetSplit.QUALIFICATION,
                DatasetSplit.HOLDOUT,
            ),
            key=lambda split: (remaining[split], _split_priority(split)),
        )
        assignment[family_id] = chosen
        counts[chosen] += size
    return assignment


def _split_priority(split: DatasetSplit) -> int:
    """Break remaining-capacity ties toward the 50/25/remainder order.

    Args:
        split: Candidate split.

    Returns:
        Higher numbers are preferred when remaining capacity ties.
    """

    return {
        DatasetSplit.DEVELOPMENT: 3,
        DatasetSplit.QUALIFICATION: 2,
        DatasetSplit.HOLDOUT: 1,
    }[split]


def splits_are_disjoint(
    split_families: Mapping[DatasetSplit, Sequence[str]],
) -> bool:
    """Return whether family identifiers are pairwise disjoint across splits.

    Args:
        split_families: Family ids present in each split.

    Returns:
        ``True`` when no family id appears in more than one split.
    """

    seen: set[str] = set()
    for families in split_families.values():
        for family_id in families:
            if family_id in seen:
                return False
            seen.add(family_id)
    return True

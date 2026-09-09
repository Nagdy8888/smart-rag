"""Split, seal, and holdout-hiding helpers for the private PDF dataset."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import UUID

from smart_rag_core.evaluation.holdout import HoldoutAccess, HoldoutSealedError
from smart_rag_core.evaluation.private_pdf.schema import (
    MINIMUM_SEALED_CASES,
    PRIVATE_PDF_CLASS_MINIMUMS,
    PRIVATE_PDF_DATASET_ID,
    PRIVATE_PDF_SCHEMA_VERSION,
    PrivatePdfCase,
    PrivatePdfQueryClass,
)


class PrivatePdfSealError(ValueError):
    """Raised when a private-PDF dataset cannot be sealed."""


def case_id_for(*, family_hash: str, question_hash: str, ordinal: int) -> str:
    """Build a deterministic case id from hashes only.

    Args:
        family_hash: Source-family digest.
        question_hash: Hash of the question text (never stored here).
        ordinal: Stable ordinal within the family.

    Returns:
        Hex id prefix.
    """

    payload = f"{family_hash}|{question_hash}|{ordinal}".encode()
    return hashlib.sha256(payload).hexdigest()[:24]


def source_family_id(*, document_hash: str, chapter: str, semantic_family: str) -> str:
    """Build a source-family id that must stay inside one split.

    Args:
        document_hash: PDF SHA-256 hex.
        chapter: Major chapter/section label.
        semantic_family: Semantic question family.

    Returns:
        Hex family id.
    """

    payload = f"{document_hash}|{chapter}|{semantic_family}".encode()
    return hashlib.sha256(payload).hexdigest()[:24]


def families_are_disjoint(cases: tuple[PrivatePdfCase, ...]) -> bool:
    """Return whether each source family lives in exactly one split.

    Args:
        cases: Dataset rows.

    Returns:
        True when no family crosses splits.
    """

    assigned: dict[str, str] = {}
    for case in cases:
        prior = assigned.get(case.source_family_id)
        if prior is None:
            assigned[case.source_family_id] = case.split
            continue
        if prior != case.split:
            return False
    return True


def assign_splits(
    family_ids: tuple[str, ...],
) -> dict[str, str]:
    """Assign families 50/25/remainder by sorted family id.

    Args:
        family_ids: Unique family ids.

    Returns:
        Family id to split name.
    """

    ordered = tuple(sorted(set(family_ids)))
    total = len(ordered)
    if total == 0:
        return {}
    dev_end = max(1, int(total * 0.5))
    qual_end = max(dev_end + 1, int(total * 0.75)) if total > 1 else total
    mapping: dict[str, str] = {}
    for index, family in enumerate(ordered):
        if index < dev_end:
            mapping[family] = "development"
        elif index < qual_end:
            mapping[family] = "qualification"
        else:
            mapping[family] = "holdout"
    return mapping


def assert_holdout_path_hidden(path: Path) -> None:
    """Refuse accidental private-holdout paths in normal loaders.

    Args:
        path: Candidate file or directory.

    Raises:
        HoldoutSealedError: When the path looks like private holdout custody.
    """

    parts = {part.lower() for part in path.parts}
    if ".private-eval" in parts and "holdout" in parts:
        raise HoldoutSealedError("private pdf holdout is hidden from normal loaders")


def assert_holdout_outside_repository(path: Path, *, repo: Path) -> None:
    """Require holdout labeled JSON to live outside the git worktree.

    Args:
        path: Reviewer-controlled holdout destination.
        repo: Repository root.

    Raises:
        PrivatePdfSealError: Path resolves inside the repository.
    """

    try:
        path.resolve().relative_to(repo.resolve())
    except ValueError:
        return
    raise PrivatePdfSealError("holdout_must_leave_repository")


def assert_current_chunk_ids(
    cases: tuple[PrivatePdfCase, ...],
    *,
    current_ids: frozenset[UUID],
) -> None:
    """Reject rows whose chunk ids are missing from the current version.

    Args:
        cases: Candidate rows.
        current_ids: Live authorized chunk ids for the sealed version.

    Raises:
        PrivatePdfSealError: A locator is empty or not current.
    """

    if not current_ids:
        raise PrivatePdfSealError("missing_current_chunk_ids")
    for case in cases:
        if not case.chunk_ids:
            raise PrivatePdfSealError("missing_current_chunk_ids")
        if any(chunk_id not in current_ids for chunk_id in case.chunk_ids):
            raise PrivatePdfSealError("stale_chunk_id")


def _class_counts(cases: tuple[PrivatePdfCase, ...]) -> dict[str, int]:
    """Count query classes.

    Args:
        cases: Dataset rows.

    Returns:
        Class token to count.
    """

    counts: dict[str, int] = {}
    for case in cases:
        counts[case.query_class] = counts.get(case.query_class, 0) + 1
    return counts


def seal_cases(
    cases: tuple[PrivatePdfCase, ...],
    *,
    holdout_access: HoldoutAccess | None = None,
    current_chunk_ids: frozenset[UUID] | None = None,
) -> tuple[PrivatePdfCase, ...]:
    """Validate human approval, disjoint families, and current chunk ids.

    Args:
        cases: Candidate rows.
        holdout_access: Required when any holdout row is present.
        current_chunk_ids: Live version chunk ids. Required; ``None`` cannot seal.

    Returns:
        The same rows when valid.

    Raises:
        PrivatePdfSealError: Generated-only, missing approval, stale ids,
            family leakage, missing ACL actor, or class-mix shortfall.
        HoldoutSealedError: Holdout rows without authorized access.
    """

    if not cases:
        raise PrivatePdfSealError("empty_private_pdf_dataset")
    if any(case.generated_only or not case.human_approved for case in cases):
        raise PrivatePdfSealError("generated_labels_cannot_self_seal")
    if not families_are_disjoint(cases):
        raise PrivatePdfSealError("source_family_crosses_splits")
    if any(case.reviewer is None or not case.reviewer.strip() for case in cases):
        raise PrivatePdfSealError("named_reviewer_required")
    if any(case.acl_actor_id is None or not case.acl_actor_id.strip() for case in cases):
        raise PrivatePdfSealError("acl_actor_required")
    case_ids = tuple(case.case_id for case in cases)
    if len(case_ids) != len(set(case_ids)):
        raise PrivatePdfSealError("duplicate_case_id")
    if any(not case.chunk_ids for case in cases):
        raise PrivatePdfSealError("missing_current_chunk_ids")
    refusal_classes = {
        PrivatePdfQueryClass.FULL_SUMMARY_REFUSAL.value,
        PrivatePdfQueryClass.INSUFFICIENT_OR_INJECTION.value,
    }
    if any(
        case.query_class in refusal_classes and not case.expected_refusal
        for case in cases
    ):
        raise PrivatePdfSealError("refusal_truth_required")
    if current_chunk_ids is None:
        raise PrivatePdfSealError("missing_current_chunk_ids")
    assert_current_chunk_ids(cases, current_ids=current_chunk_ids)
    holdout_present = any(case.split == "holdout" for case in cases)
    if holdout_present:
        access = holdout_access or HoldoutAccess.denied()
        if not access.allowed:
            raise HoldoutSealedError("private pdf holdout is sealed")
    if len(cases) < MINIMUM_SEALED_CASES:
        raise PrivatePdfSealError("below_minimum_case_count")
    counts = _class_counts(cases)
    for query_class, minimum in PRIVATE_PDF_CLASS_MINIMUMS.items():
        if counts.get(query_class.value, 0) < minimum:
            raise PrivatePdfSealError("class_mix_below_minimum")
    return cases


def manifest_payload(cases: tuple[PrivatePdfCase, ...]) -> dict[str, object]:
    """Build a Git-safe manifest of hashes and counts only.

    Args:
        cases: Sealed rows.

    Returns:
        Counts, ordered case-id hashes, and family hashes. No questions.
    """

    ordered = tuple(sorted(cases, key=lambda item: item.case_id))
    return {
        "schema_version": PRIVATE_PDF_SCHEMA_VERSION,
        "dataset_id": PRIVATE_PDF_DATASET_ID,
        "case_count": len(ordered),
        "case_ids": [item.case_id for item in ordered],
        "source_family_ids": sorted({item.source_family_id for item in ordered}),
        "split_counts": {
            name: sum(1 for item in ordered if item.split == name)
            for name in ("development", "qualification", "holdout")
        },
    }


def manifest_hash(cases: tuple[PrivatePdfCase, ...]) -> str:
    """Hash the Git-safe manifest.

    Args:
        cases: Sealed rows.

    Returns:
        SHA-256 hex digest.
    """

    encoded = json.dumps(
        manifest_payload(cases), sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()

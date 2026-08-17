"""Approved open-split corpus selection and holdout/production rejection."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from smart_rag_core.evaluation.classes import QueryClass
from smart_rag_core.evaluation.holdout import HoldoutAccess, HoldoutSealedError
from smart_rag_core.evaluation.loader import load_open_splits
from smart_rag_core.evaluation.materialize import document_visibility_for_case
from smart_rag_core.evaluation.schema import DatasetSplit, EvaluationCase
from smart_rag_core.release.constants import CORPUS_MANIFEST_SCHEMA_VERSION
from smart_rag_core.release.errors import UnapprovedCorpusError

REQUIRED_QUERY_CLASSES: tuple[QueryClass, ...] = (
    QueryClass.EXACT_CODE,
    QueryClass.ALIAS,
    QueryClass.ARABIC_MIXED,
    QueryClass.LATEST_AS_OF,
    QueryClass.TABULAR_AGGREGATION,
    QueryClass.MEDIA_LIMITATION,
    QueryClass.ACL_NEGATIVE,
    QueryClass.GRAPH_MAPPING,
)
_FORBIDDEN_PATH_PARTS = frozenset({"holdout", "production", "prod-data"})
_MAX_PER_CLASS = 1


class CorpusSeedRow(BaseModel):
    """One approved seeded evaluation source.

    Attributes:
        case_id: Immutable evaluation case id.
        source_family_id: Family that cannot cross splits.
        split: Open split name.
        query_class: Fixture family.
        visibility: Canonical visibility.
        content_sha256: Hash of the compact markdown body.
        document_id: Real document UUID after ingest, if seeded.
        version_id: Real version UUID after ingest, if seeded.
        status: Public document status after ingest, if seeded.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    source_family_id: str
    split: str
    query_class: str
    visibility: str
    content_sha256: str
    document_id: str | None = None
    version_id: str | None = None
    status: str | None = None


class CorpusManifest(BaseModel):
    """Immutable approved-corpus manifest. Holdout is never opened.

    Attributes:
        schema_version: Frozen corpus schema.
        holdout_opened: Always false.
        rows: Seeded or selected cases.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["phase09-candidate-corpus-v1"] = (
        CORPUS_MANIFEST_SCHEMA_VERSION
    )
    holdout_opened: Literal[False] = False
    rows: tuple[CorpusSeedRow, ...]


def approved_open_split_cases(
    *,
    cases: Sequence[EvaluationCase] | None = None,
    holdout_access: HoldoutAccess | None = None,
) -> list[EvaluationCase]:
    """Return a bounded open-split seed set covering required fixture families.

    Holdout stays sealed. Production paths are never consulted. The local
    candidate corpus is a labeled subset, not the 10,000-version envelope.

    Args:
        cases: Optional preloaded cases. When omitted, open-split loaders run.
        holdout_access: Must remain denied. ``None`` uses ``HoldoutAccess.denied()``.

    Returns:
        Deduplicated cases ordered by case id, at most one per required class.

    Raises:
        UnapprovedCorpusError: If holdout is open or a holdout/production case
            appears.
        HoldoutSealedError: If a caller requests holdout materialization.
    """

    access = holdout_access if holdout_access is not None else HoldoutAccess.denied()
    if access.allowed:
        raise UnapprovedCorpusError("holdout access is denied for Phase 9 Packet 1")
    loaded = list(cases) if cases is not None else load_open_splits()
    selected: list[EvaluationCase] = []
    seen_classes: set[QueryClass] = set()
    for case in sorted(loaded, key=lambda item: item.case_id):
        reject_unapproved_case(case)
        if case.query_class not in REQUIRED_QUERY_CLASSES:
            continue
        if case.query_class in seen_classes:
            continue
        if len([item for item in selected if item.query_class is case.query_class]) >= (
            _MAX_PER_CLASS
        ):
            continue
        selected.append(case)
        seen_classes.add(case.query_class)
    missing = [
        item.value for item in REQUIRED_QUERY_CLASSES if item not in seen_classes
    ]
    if missing:
        raise UnapprovedCorpusError(
            f"open splits missing required fixture classes: {missing}"
        )
    return selected


def reject_unapproved_case(case: EvaluationCase) -> None:
    """Reject holdout, production-labeled, or sealed-split cases.

    Args:
        case: Candidate evaluation case.

    Raises:
        UnapprovedCorpusError: If the case is not an approved open-split row.
        HoldoutSealedError: If the split is holdout.
    """

    if case.split is DatasetSplit.HOLDOUT:
        raise HoldoutSealedError("holdout is sealed; default access is denied")
    if case.split not in {DatasetSplit.DEVELOPMENT, DatasetSplit.QUALIFICATION}:
        raise UnapprovedCorpusError(f"unapproved split {case.split.value}")
    lowered_id = case.case_id.lower()
    if "holdout" in lowered_id or "production" in lowered_id:
        raise UnapprovedCorpusError(f"unapproved case id {case.case_id}")
    family = case.source_family_id.lower()
    if "holdout" in family or "production" in family:
        raise UnapprovedCorpusError(f"unapproved source family {case.source_family_id}")


def reject_unapproved_source(path: Path) -> None:
    """Reject files whose path names holdout or production data.

    Args:
        path: Proposed source path.

    Raises:
        UnapprovedCorpusError: If any path part is forbidden.
    """

    parts = {part.lower() for part in path.parts}
    forbidden = parts.intersection(_FORBIDDEN_PATH_PARTS)
    if forbidden:
        raise UnapprovedCorpusError(
            f"unapproved source path {path.as_posix()} contains {sorted(forbidden)}"
        )
    name = path.name.lower()
    if "holdout" in name or "production" in name:
        raise UnapprovedCorpusError(f"unapproved source filename {path.name}")


def seed_visibility(case: EvaluationCase) -> str:
    """Return canonical visibility for one approved seed case.

    Args:
        case: Open-split evaluation case.

    Returns:
        ``company_visible`` or ``restricted``.
    """

    return document_visibility_for_case(case)

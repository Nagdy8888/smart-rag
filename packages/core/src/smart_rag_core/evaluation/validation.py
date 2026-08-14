"""Validate the frozen Phase 4 corpus against class, split, and label gates."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path

from smart_rag_core.evaluation.classes import (
    CLASS_MINIMUMS,
    TOTAL_MINIMUM_CASES,
    QueryClass,
)
from smart_rag_core.evaluation.hashes import (
    build_split_manifest,
    case_content_hash,
    schema_hash,
)
from smart_rag_core.evaluation.schema import (
    DATASET_SCHEMA_VERSION,
    LABEL_REVISION,
    AdjudicationStatus,
    DatasetSplit,
    EvaluationCase,
    RefusalKind,
    SplitManifest,
)

EMBEDDING_SLICE_PATH = (
    Path(__file__).resolve().parents[5]
    / "tests"
    / "fixtures"
    / "embedding_qualification"
    / "slice_v1.json"
)


class DatasetValidationError(ValueError):
    """Raised when the labeled corpus fails a Packet 1 gate."""


def _require(condition: bool, message: str) -> None:
    """Raise a validation error when a gate fails.

    Args:
        condition: Gate outcome.
        message: Machine-readable failure.

    Raises:
        DatasetValidationError: If ``condition`` is false.
    """

    if not condition:
        raise DatasetValidationError(message)


def load_embedding_slice_ids(path: Path | None = None) -> set[str]:
    """Load Phase 2 embedding-qualification identifiers.

    Args:
        path: Optional override path to ``slice_v1.json``.

    Returns:
        Document, query, and relevant ids that Phase 4 must not reuse.
    """

    import json

    slice_path = path if path is not None else EMBEDDING_SLICE_PATH
    payload = json.loads(slice_path.read_text(encoding="utf-8"))
    ids: set[str] = {str(payload.get("slice_id", ""))}
    for document in payload.get("documents", []):
        ids.add(str(document["id"]))
    for query in payload.get("queries", []):
        ids.add(str(query["id"]))
        ids.update(str(item) for item in query.get("relevant_ids", []))
        ids.add(str(query.get("text", "")))
    return {item for item in ids if item}


def validate_corpus(cases: Sequence[EvaluationCase]) -> None:
    """Validate class counts, labels, splits, and embedding disjointness.

    Args:
        cases: Full generated corpus including holdout.

    Raises:
        DatasetValidationError: If any Packet 1 gate fails.
    """

    _require(len(cases) >= TOTAL_MINIMUM_CASES, "corpus_below_minimum")
    counts = Counter(case.query_class for case in cases)
    for query_class, minimum in CLASS_MINIMUMS.items():
        _require(counts[query_class] >= minimum, f"class_shortfall:{query_class.value}")
    case_ids = [case.case_id for case in cases]
    _require(len(case_ids) == len(set(case_ids)), "duplicate_case_id")
    families_by_split: dict[DatasetSplit, set[str]] = defaultdict(set)
    cases_by_split: dict[DatasetSplit, set[str]] = defaultdict(set)
    class_splits: dict[QueryClass, set[DatasetSplit]] = defaultdict(set)
    for case in cases:
        _require(case.acl_actor.actor_id.startswith("p4-actor-"), "missing_acl_actor")
        _require(
            bool(case.evidence_links) or case.refusal_kind is not RefusalKind.NONE,
            f"missing_evidence:{case.case_id}",
        )
        _require(
            case.expected_profile.language.value is not None,
            f"missing_profile:{case.case_id}",
        )
        _require(case.query_class in QueryClass, f"malformed_class:{case.case_id}")
        if case.adjudication_status is AdjudicationStatus.DISAGREEMENT_OPEN:
            _require(
                case.disagreement_notes is not None
                and len(case.acceptable_answers) > 1,
                f"forced_gold:{case.case_id}",
            )
        families_by_split[case.split].add(case.source_family_id)
        cases_by_split[case.split].add(case.case_id)
        class_splits[case.query_class].add(case.split)
    for left, right in (
        (DatasetSplit.DEVELOPMENT, DatasetSplit.QUALIFICATION),
        (DatasetSplit.DEVELOPMENT, DatasetSplit.HOLDOUT),
        (DatasetSplit.QUALIFICATION, DatasetSplit.HOLDOUT),
    ):
        _require(
            families_by_split[left].isdisjoint(families_by_split[right]),
            f"family_leakage:{left.value}:{right.value}",
        )
        _require(
            cases_by_split[left].isdisjoint(cases_by_split[right]),
            f"case_leakage:{left.value}:{right.value}",
        )
    for query_class in CLASS_MINIMUMS:
        _require(
            DatasetSplit.QUALIFICATION in class_splits[query_class],
            f"missing_qualification:{query_class.value}",
        )
        _require(
            DatasetSplit.HOLDOUT in class_splits[query_class],
            f"missing_holdout:{query_class.value}",
        )
    embedding_ids = load_embedding_slice_ids()
    corpus_ids = {case.case_id for case in cases}
    corpus_ids.update(case.source_family_id for case in cases)
    corpus_ids.update(case.query for case in cases)
    _require(corpus_ids.isdisjoint(embedding_ids), "embedding_slice_leakage")


def manifests_from_corpus(
    cases: Sequence[EvaluationCase],
) -> dict[DatasetSplit, SplitManifest]:
    """Build frozen manifests for each split.

    Args:
        cases: Full labeled corpus.

    Returns:
        Mapping of split to ordered manifest.
    """

    manifests: dict[DatasetSplit, SplitManifest] = {}
    for split in DatasetSplit:
        selected = sorted(
            (case for case in cases if case.split is split),
            key=lambda item: item.case_id,
        )
        manifests[split] = build_split_manifest(
            schema_version=DATASET_SCHEMA_VERSION,
            label_revision=LABEL_REVISION,
            split=split.value,
            cases=selected,
        )
    return manifests


def assert_manifests_match(
    actual: Mapping[DatasetSplit, SplitManifest],
    expected: Mapping[DatasetSplit, SplitManifest],
) -> None:
    """Require sealed manifests to match a recomputed corpus.

    Args:
        actual: Manifests freshly computed from the generator.
        expected: Committed sealed manifests.

    Raises:
        DatasetValidationError: If any split hash or id list differs.
    """

    for split in DatasetSplit:
        _require(split in expected, f"missing_sealed_manifest:{split.value}")
        _require(
            actual[split].manifest_hash == expected[split].manifest_hash,
            f"manifest_hash_mismatch:{split.value}",
        )
        _require(
            actual[split].case_ids == expected[split].case_ids,
            f"manifest_ids_mismatch:{split.value}",
        )


def corpus_schema_hash() -> str:
    """Return the frozen schema hash for evidence records.

    Returns:
        SHA-256 of schema version plus EvaluationCase field names.
    """

    return schema_hash(DATASET_SCHEMA_VERSION, tuple(EvaluationCase.model_fields))


def verify_case_hashes(
    cases: Sequence[EvaluationCase], manifest: SplitManifest
) -> None:
    """Check per-case content hashes against a sealed manifest.

    Args:
        cases: Cases belonging to the manifest split.
        manifest: Sealed split manifest.

    Raises:
        DatasetValidationError: If a case hash differs.
    """

    for case in cases:
        expected = manifest.case_hashes.get(case.case_id)
        _require(expected is not None, f"case_missing_from_manifest:{case.case_id}")
        _require(
            case_content_hash(case) == expected,
            f"case_hash_mismatch:{case.case_id}",
        )

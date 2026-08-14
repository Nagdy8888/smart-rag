"""Canonical JSON hashing for frozen Phase 4 manifests."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence

from smart_rag_core.evaluation.schema import DatasetSplit, EvaluationCase, SplitManifest


def canonical_dumps(value: object) -> str:
    """Serialize a JSON-compatible value with stable key order.

    Args:
        value: JSON-compatible mapping, sequence, or scalar.

    Returns:
        UTF-8 JSON text with sorted keys and compact separators.
    """

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(value: str) -> str:
    """Return the SHA-256 hex digest of UTF-8 text.

    Args:
        value: Text to hash.

    Returns:
        64-character lowercase hex digest.
    """

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def case_content_hash(case: EvaluationCase) -> str:
    """Hash one evaluation case independently of split assignment.

    Args:
        case: Labeled case. The split field is excluded so family reassignment
            during sealing does not change content identity.

    Returns:
        SHA-256 hex digest of the canonical case payload without ``split``.
    """

    payload = case.model_dump(mode="json")
    payload.pop("split", None)
    return sha256_text(canonical_dumps(payload))


def term_coverage_hash(normalized_term: str) -> str:
    """Hash a normalized glossary/term value for Git-safe coverage fixtures.

    Args:
        normalized_term: Search-normalized term. Raw private values must not be
            written to Git.

    Returns:
        SHA-256 hex digest of the normalized term.
    """

    return sha256_text(normalized_term)


def build_split_manifest(
    *,
    schema_version: str,
    label_revision: str,
    split: str,
    cases: Sequence[EvaluationCase],
) -> SplitManifest:
    """Build a frozen split manifest from ordered cases.

    Args:
        schema_version: Dataset schema version.
        label_revision: Label revision.
        split: Split name matching ``DatasetSplit``.
        cases: Cases already filtered to the split, in freeze order.

    Returns:
        Manifest with ordered ids, family ids, per-case hashes, and
        ``manifest_hash``.
    """

    case_ids = [case.case_id for case in cases]
    family_ids: list[str] = []
    seen_families: set[str] = set()
    hashes: dict[str, str] = {}
    for case in cases:
        hashes[case.case_id] = case_content_hash(case)
        if case.source_family_id not in seen_families:
            seen_families.add(case.source_family_id)
            family_ids.append(case.source_family_id)
    material: dict[str, object] = {
        "schema_version": schema_version,
        "label_revision": label_revision,
        "split": split,
        "case_ids": case_ids,
        "source_family_ids": family_ids,
        "case_hashes": hashes,
    }
    return SplitManifest(
        schema_version=schema_version,
        label_revision=label_revision,
        split=DatasetSplit(split),
        case_ids=case_ids,
        source_family_ids=family_ids,
        case_hashes=hashes,
        manifest_hash=sha256_text(canonical_dumps(material)),
    )


def schema_hash(schema_version: str, field_names: Sequence[str]) -> str:
    """Hash the labeled schema identity used in corpus metadata.

    Args:
        schema_version: Dataset schema version string.
        field_names: Ordered EvaluationCase field names.

    Returns:
        SHA-256 hex digest.
    """

    return sha256_text(
        canonical_dumps({"schema_version": schema_version, "fields": list(field_names)})
    )


def mapping_hash(values: Mapping[str, str]) -> str:
    """Hash a string mapping with canonical JSON.

    Args:
        values: String-to-string mapping.

    Returns:
        SHA-256 hex digest.
    """

    return sha256_text(canonical_dumps(dict(values)))

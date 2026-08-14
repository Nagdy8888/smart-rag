"""Validate the sealed Phase 4 corpus against Packet 1 gates."""

from __future__ import annotations

import json
from pathlib import Path

from smart_rag_core.evaluation.generator import generate_corpus
from smart_rag_core.evaluation.holdout import HoldoutAccess
from smart_rag_core.evaluation.loader import load_cases
from smart_rag_core.evaluation.schema import DatasetSplit, SplitManifest
from smart_rag_core.evaluation.seal import DEFAULT_FIXTURE_ROOT
from smart_rag_core.evaluation.validation import (
    DatasetValidationError,
    assert_manifests_match,
    manifests_from_corpus,
    validate_corpus,
    verify_case_hashes,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_manifest(path: Path) -> SplitManifest:
    """Load one sealed split manifest.

    Args:
        path: Manifest JSON path.

    Returns:
        Parsed ``SplitManifest``.
    """

    return SplitManifest.model_validate_json(path.read_text(encoding="utf-8"))


def main() -> int:
    """Recompute the corpus and compare it to sealed manifests.

    Returns:
        ``0`` when every Packet 1 dataset gate passes; ``1`` otherwise.

    Side Effects:
        Reads sealed manifests. Holdout labels are materialized only with the
        ``dataset_seal_verify`` purpose for hash comparison, not for tuning.
    """

    try:
        corpus = generate_corpus()
        validate_corpus(corpus)
        actual = manifests_from_corpus(corpus)
        expected = {
            split: _load_manifest(
                DEFAULT_FIXTURE_ROOT / "manifests" / f"{split.value}.json"
            )
            for split in DatasetSplit
        }
        assert_manifests_match(actual, expected)
        authorized = HoldoutAccess(
            allowed=True,
            purpose="dataset_seal_verify",
            actor="phase4-packet1-validator",
        )
        holdout = load_cases(
            splits=(DatasetSplit.HOLDOUT,),
            holdout_access=authorized,
        )
        verify_case_hashes(holdout, expected[DatasetSplit.HOLDOUT])
        meta = json.loads(
            (DEFAULT_FIXTURE_ROOT / "corpus_meta.json").read_text(encoding="utf-8")
        )
        print(f"case_count={meta['case_count']}")
        print(f"schema_hash={meta['schema_hash']}")
        for split in DatasetSplit:
            print(f"{split.value}_hash={expected[split].manifest_hash}")
    except (DatasetValidationError, FileNotFoundError, OSError, ValueError) as exc:
        print(f"validation_failed:{exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

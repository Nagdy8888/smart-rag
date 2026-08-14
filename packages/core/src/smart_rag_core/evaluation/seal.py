"""Seal Phase 4 split manifests and Git-safe term-coverage hashes."""

from __future__ import annotations

import json
from pathlib import Path

from smart_rag_core.evaluation.classes import QueryClass
from smart_rag_core.evaluation.generator import generate_corpus
from smart_rag_core.evaluation.hashes import term_coverage_hash
from smart_rag_core.evaluation.identifier_rules import (
    IDENTIFIER_RULE_VERSION,
    propose_rules_from_corpus,
)
from smart_rag_core.evaluation.schema import (
    DATASET_SCHEMA_VERSION,
    LABEL_REVISION,
    DatasetSplit,
    EvaluationCase,
)
from smart_rag_core.evaluation.validation import (
    corpus_schema_hash,
    manifests_from_corpus,
    validate_corpus,
)
from smart_rag_core.text.arabic_normalize import normalize_arabic_v1

DEFAULT_FIXTURE_ROOT = (
    Path(__file__).resolve().parents[5] / "tests" / "fixtures" / "evaluation" / "phase4"
)


def fixture_root(override: Path | None = None) -> Path:
    """Return the Phase 4 fixture directory.

    Args:
        override: Optional explicit root.

    Returns:
        Directory containing manifests and corpus metadata.
    """

    return override if override is not None else DEFAULT_FIXTURE_ROOT


def term_coverage_rows(cases: list[EvaluationCase]) -> list[dict[str, str]]:
    """Build Git-safe term coverage rows from exact-code and alias cases.

    Args:
        cases: Full corpus.

    Returns:
        Rows with case id, term kind, and normalized-term hash. Raw terms are
        not included.
    """

    rows: list[dict[str, str]] = []
    for case in cases:
        if case.query_class is QueryClass.EXACT_CODE:
            codes = case.expected_profile.codes.value
            if isinstance(codes, list):
                for code in codes:
                    rows.append(
                        {
                            "case_id": case.case_id,
                            "term_kind": "product_code",
                            "normalized_hash": term_coverage_hash(
                                normalize_arabic_v1(code)
                            ),
                        }
                    )
        if case.query_class is QueryClass.ALIAS:
            aliases = case.expected_profile.approved_aliases.value
            if isinstance(aliases, list):
                for alias in aliases:
                    rows.append(
                        {
                            "case_id": case.case_id,
                            "term_kind": "approved_alias",
                            "normalized_hash": term_coverage_hash(
                                normalize_arabic_v1(alias)
                            ),
                        }
                    )
    return rows


def seal_corpus(root: Path | None = None) -> dict[str, str]:
    """Validate the corpus and write frozen manifests.

    Args:
        root: Optional fixture directory override.

    Returns:
        Mapping of artifact name to SHA-256 or path string for evidence.

    Side Effects:
        Writes JSON manifests, identifier rules, and term-coverage hashes.
        Holdout labels are not written; only ids and content hashes are sealed.
    """

    cases = generate_corpus()
    validate_corpus(cases)
    destination = fixture_root(root)
    manifest_dir = destination / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifests = manifests_from_corpus(cases)
    hashes: dict[str, str] = {}
    for split, manifest in manifests.items():
        path = manifest_dir / f"{split.value}.json"
        path.write_text(
            json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        hashes[f"manifest_{split.value}"] = manifest.manifest_hash
    texts = [case.query for case in cases]
    rules = [rule.model_dump(mode="json") for rule in propose_rules_from_corpus(texts)]
    rules_path = destination / "identifier_rules.json"
    rules_path.write_text(
        json.dumps(
            {"version": IDENTIFIER_RULE_VERSION, "rules": rules},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    coverage_path = destination / "term_coverage.json"
    coverage_path.write_text(
        json.dumps({"rows": term_coverage_rows(cases)}, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    split_counts = {
        split.value: sum(1 for case in cases if case.split is split)
        for split in DatasetSplit
    }
    class_counts = {
        query_class.value: sum(1 for case in cases if case.query_class is query_class)
        for query_class in QueryClass
    }
    meta = {
        "schema_version": DATASET_SCHEMA_VERSION,
        "label_revision": LABEL_REVISION,
        "schema_hash": corpus_schema_hash(),
        "case_count": len(cases),
        "split_counts": split_counts,
        "class_counts": class_counts,
        "manifest_hashes": hashes,
        "sme_approval": {
            "status": "synthetic_provisional",
            "approver": "user (Cursor chat; Phase 4 Packet 1 mandate)",
            "named_knowledge_owner": "unverified",
            "hours_committed": "unverified",
        },
    }
    (destination / "corpus_meta.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    hashes["schema"] = str(meta["schema_hash"])
    return hashes

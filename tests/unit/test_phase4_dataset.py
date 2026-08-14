"""Unit tests for Phase 4 Packet 1 labeled corpus and split isolation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from smart_rag_core.evaluation.calibration import load_tuning_cases
from smart_rag_core.evaluation.classes import CLASS_MINIMUMS, TOTAL_MINIMUM_CASES
from smart_rag_core.evaluation.generator import generate_corpus
from smart_rag_core.evaluation.holdout import HoldoutAccess, HoldoutSealedError
from smart_rag_core.evaluation.loader import load_cases, load_open_splits
from smart_rag_core.evaluation.schema import (
    DATASET_SCHEMA_VERSION,
    AdjudicationStatus,
    DatasetSplit,
    EvaluationCase,
    RefusalKind,
)
from smart_rag_core.evaluation.validation import (
    DatasetValidationError,
    load_embedding_slice_ids,
    validate_corpus,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CALIBRATION_SOURCE = (
    REPO_ROOT
    / "packages"
    / "core"
    / "src"
    / "smart_rag_core"
    / "evaluation"
    / "calibration.py"
)
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "evaluation" / "phase4"


def test_corpus_meets_class_and_split_gates() -> None:
    """The synthetic corpus meets class minima and split isolation."""

    cases = generate_corpus()
    validate_corpus(cases)
    assert len(cases) >= TOTAL_MINIMUM_CASES
    for query_class, minimum in CLASS_MINIMUMS.items():
        assert sum(case.query_class is query_class for case in cases) >= minimum


def test_every_case_has_actor_evidence_or_refusal_and_profile() -> None:
    """Every case has ACL actor, evidence or refusal, and profile fields."""

    for case in generate_corpus():
        assert case.acl_actor.actor_id
        assert case.evidence_links or case.refusal_kind is not RefusalKind.NONE
        assert case.expected_profile.language.value
        assert case.expected_profile.retrieval_profile_id.value
        assert case.adjudication_status in AdjudicationStatus


def test_disagreement_is_not_forced_gold() -> None:
    """Open disagreement retains alternatives and notes."""

    open_cases = [
        case
        for case in generate_corpus()
        if case.adjudication_status is AdjudicationStatus.DISAGREEMENT_OPEN
    ]
    assert open_cases
    for case in open_cases:
        assert case.disagreement_notes is not None
        assert len(case.acceptable_answers) > 1


def test_embedding_slice_is_disjoint() -> None:
    """Phase 4 ids and queries do not overlap the embedding-qualification slice."""

    embedding_ids = load_embedding_slice_ids()
    corpus = generate_corpus()
    corpus_ids = {case.case_id for case in corpus}
    corpus_ids.update(case.source_family_id for case in corpus)
    corpus_ids.update(case.query for case in corpus)
    assert corpus_ids.isdisjoint(embedding_ids)
    for forbidden in ("PO-7781", "TKT-4412", "SKU-90B", "q-ar-sem-01", "ar-01"):
        assert forbidden not in corpus_ids
        assert all(forbidden not in case.query for case in corpus)


def test_holdout_denied_by_default() -> None:
    """Holdout labels cannot be loaded without an allow-listed token."""

    with pytest.raises(HoldoutSealedError):
        load_cases(splits=(DatasetSplit.HOLDOUT,))
    with pytest.raises(HoldoutSealedError):
        load_cases(
            splits=(DatasetSplit.HOLDOUT,),
            holdout_access=HoldoutAccess.denied(),
        )


def test_calibration_cannot_reach_holdout() -> None:
    """Tuning entrypoints return only development and qualification cases."""

    cases = load_tuning_cases()
    assert cases
    assert all(case.split is not DatasetSplit.HOLDOUT for case in cases)
    source = CALIBRATION_SOURCE.read_text(encoding="utf-8").lower()
    assert "load_cases" not in source
    assert "dataset_seal_verify" not in source
    assert "packet8_immutable" not in source
    open_cases = load_open_splits()
    assert {case.case_id for case in open_cases} == {case.case_id for case in cases}


def test_malformed_class_is_rejected() -> None:
    """Unknown query classes cannot be constructed."""

    with pytest.raises(ValueError):
        EvaluationCase.model_validate(
            {
                "case_id": "p4-exact_code-0001",
                "source_family_id": "p4-fam-x-0001",
                "query_class": "not_a_class",
                "split": "development",
                "schema_version": DATASET_SCHEMA_VERSION,
                "label_revision": "x",
                "query": "q",
                "language": "en",
                "acceptable_answers": ["a"],
                "evidence_links": [],
                "refusal_kind": "none",
                "expected_route": "hybrid",
                "runtime_owner": "phase_4",
                "acl_actor": {
                    "actor_id": "p4-actor-member-a",
                    "role": "member",
                    "authorization_snapshot_id": "p4-acl-v1",
                    "restricted": False,
                },
                "expected_profile": generate_corpus()[0].expected_profile.model_dump(
                    mode="json"
                ),
                "adjudication_status": "agreed",
                "adjudicators": ["synthetic-sme-v1"],
            }
        )


def test_missing_evidence_and_refusal_fails() -> None:
    """A case without evidence or refusal truth is invalid."""

    template = generate_corpus()[0]
    payload = template.model_dump(mode="json")
    payload["evidence_links"] = []
    payload["refusal_kind"] = "none"
    with pytest.raises(ValueError):
        EvaluationCase.model_validate(payload)


def test_duplicate_family_across_splits_fails_validation() -> None:
    """Source-family leakage is a validation failure."""

    cases = generate_corpus()
    leaked = cases[0].model_copy(
        update={
            "case_id": "p4-exact_code-9999",
            "split": (
                DatasetSplit.HOLDOUT
                if cases[0].split is not DatasetSplit.HOLDOUT
                else DatasetSplit.DEVELOPMENT
            ),
        }
    )
    with pytest.raises(DatasetValidationError, match="family_leakage"):
        validate_corpus([*cases, leaked])


def test_sealed_manifests_exist_and_omit_holdout_queries() -> None:
    """Sealed holdout manifests contain ids and hashes, not query text."""

    holdout_path = FIXTURE_ROOT / "manifests" / "holdout.json"
    payload = json.loads(holdout_path.read_text(encoding="utf-8"))
    assert "case_ids" in payload
    assert "case_hashes" in payload
    assert "query" not in payload
    dumped = json.dumps(payload)
    assert "INV-SR-" not in dumped

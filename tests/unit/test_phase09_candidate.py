"""Unit tests for Phase 9 Packet 1 candidate freeze, corpus, and negative gates."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from smart_rag_core.evaluation.generator import generate_corpus
from smart_rag_core.evaluation.holdout import HoldoutAccess, HoldoutSealedError
from smart_rag_core.evaluation.schema import DatasetSplit
from smart_rag_core.release.constants import (
    IDENTITY_SCHEMA_VERSION,
    IMAGE_MANIFEST_SCHEMA_VERSION,
    PRIVATE_COMPOSE_SERVICES,
    REQUIRED_DOCUMENT_STATES,
)
from smart_rag_core.release.corpus import (
    CorpusManifest,
    approved_open_split_cases,
    reject_unapproved_case,
    reject_unapproved_source,
)
from smart_rag_core.release.errors import (
    CandidateDigestMismatchError,
    CandidateIdentityError,
    CandidatePortError,
    FakeReadinessError,
    RestrictedGraphIndexError,
    UnapprovedCorpusError,
)
from smart_rag_core.release.identity import (
    CandidateIdentityFreeze,
    assert_identity_fields,
    collect_identity_freeze,
)
from smart_rag_core.release.images import (
    CandidateImageRecord,
    ImageDigestManifest,
    reject_digest_mismatch,
)
from smart_rag_core.release.mapping import reject_restricted_lightrag_input
from smart_rag_core.release.ports import (
    assert_private_services_unpublished,
    compose_file_declares_host_ports,
    parse_compose_publishers,
)
from smart_rag_core.release.readiness import (
    ReadinessEvent,
    reject_duplicate_readiness,
    reject_fake_readiness,
)
from smart_rag_core.release.scans import summarize_trivy_report
from smart_rag_core.release.sizing import build_sizing_baseline

REPO_ROOT = Path(__file__).resolve().parents[2]


def _image_record(
    *, image_id: str = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
) -> CandidateImageRecord:
    """Return a valid digest record for mismatch tests.

    Args:
        image_id: Recorded Docker image Id.

    Returns:
        Frozen image record.
    """

    return CandidateImageRecord(
        service="api",
        image_name="smart-rag-api:local",
        image_id=image_id,
        repo_digest=None,
        created="2026-08-17T00:00:00Z",
        user="10001:10001",
    )


def _event(
    *,
    state: str = "hybrid_ready",
    version_id: str = "11111111-1111-1111-1111-111111111111",
    driver: str = "Bm25ProjectionService.process_upsert_job",
    bm25_verified: bool = True,
    maps_verified: bool = False,
) -> ReadinessEvent:
    """Return one readiness event for negative tests.

    Args:
        state: Public document status.
        version_id: Canonical version id.
        driver: Claimed driver name.
        bm25_verified: Hybrid BM25 proof flag.
        maps_verified: Graph mapping proof flag.

    Returns:
        Frozen readiness event.
    """

    return ReadinessEvent(
        state=state,
        document_id="00000000-0000-0000-0000-000000000001",
        version_id=version_id,
        job_id="22222222-2222-2222-2222-222222222222",
        observed_at="2026-08-17T15:00:00Z",
        driver=driver,
        bm25_verified=bm25_verified,
        maps_verified=maps_verified,
    )


def test_digest_mismatch_is_rejected() -> None:
    """A rebuilt image Id must not reuse the previous freeze."""

    recorded = _image_record()
    with pytest.raises(CandidateDigestMismatchError, match="image id mismatch"):
        reject_digest_mismatch(
            recorded,
            observed_image_id="sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        )


def test_digest_manifest_schema_forbids_overlay_identity() -> None:
    """Candidate image identity is docker-compose.yml without Packet 8 overlay."""

    manifest = ImageDigestManifest(
        compose_file="docker-compose.yml",
        images=(_image_record(),),
    )
    assert manifest.schema_version == IMAGE_MANIFEST_SCHEMA_VERSION
    assert manifest.overlay_file is None
    dumped = manifest.model_dump()
    assert dumped["overlay_file"] is None


def test_holdout_case_is_rejected() -> None:
    """Sealed holdout labels cannot be selected for the candidate corpus."""

    holdout = next(
        case for case in generate_corpus() if case.split is DatasetSplit.HOLDOUT
    )
    with pytest.raises(HoldoutSealedError):
        reject_unapproved_case(holdout)


def test_holdout_access_token_is_rejected() -> None:
    """Packet 1 refuses even an allow-listed holdout access token."""

    with pytest.raises(UnapprovedCorpusError, match="holdout access is denied"):
        approved_open_split_cases(
            holdout_access=HoldoutAccess(
                allowed=True,
                purpose="dataset_seal_verify",
                actor="phase09-test",
            )
        )


def test_production_path_and_case_id_are_rejected() -> None:
    """Production filenames and production-labeled case ids fail closed."""

    with pytest.raises(UnapprovedCorpusError, match="unapproved source"):
        reject_unapproved_source(Path("data") / "production" / "handbook.md")
    with pytest.raises(UnapprovedCorpusError, match="unapproved source"):
        reject_unapproved_source(Path("fixtures") / "holdout-export.md")
    open_case = next(
        case for case in generate_corpus() if case.split is DatasetSplit.DEVELOPMENT
    )
    leaked = open_case.model_copy(update={"case_id": "production-leak-0001"})
    with pytest.raises(UnapprovedCorpusError, match="unapproved case id"):
        reject_unapproved_case(leaked)


def test_approved_open_splits_cover_required_classes_without_holdout() -> None:
    """Open-split selection covers required fixture families and stays holdout-blind."""

    selected = approved_open_split_cases(holdout_access=HoldoutAccess.denied())
    classes = {case.query_class.value for case in selected}
    assert classes == {
        "exact_code",
        "alias",
        "arabic_mixed",
        "latest_as_of",
        "tabular_aggregation",
        "media_limitation",
        "acl_negative",
        "graph_mapping",
    }
    assert all(case.split is not DatasetSplit.HOLDOUT for case in selected)
    manifest = CorpusManifest(
        rows=(),
    )
    assert manifest.holdout_opened is False


def test_deletion_pending_is_driven_on_graph_ineligible() -> None:
    """``exclude_version_from_retrieval`` cannot keep graph_eligible with deleted_at.

    The candidate seed therefore drives ``deletion_pending`` on a
    graph-ineligible version instead of the Graph Ready row.
    """

    source = (
        REPO_ROOT / "packages/core/src/smart_rag_core/release/seed.py"
    ).read_text(encoding="utf-8")
    assert 'result.status == "graph_ineligible"' in source
    assert "graph_ready_done = True\n                deletion_version" not in source


def test_restricted_lightrag_input_is_rejected() -> None:
    """Restricted or ineligible documents must never be LightRAG-indexed."""

    with pytest.raises(RestrictedGraphIndexError):
        reject_restricted_lightrag_input(visibility="restricted", graph_eligible=False)
    with pytest.raises(RestrictedGraphIndexError):
        reject_restricted_lightrag_input(
            visibility="company_visible",
            graph_eligible=False,
        )
    reject_restricted_lightrag_input(
        visibility="company_visible",
        graph_eligible=True,
    )


def test_fake_and_duplicate_readiness_are_rejected() -> None:
    """SQL-stamped, unverified, and duplicate Hybrid/Graph Ready claims fail."""

    with pytest.raises(FakeReadinessError, match="fake readiness"):
        reject_fake_readiness(_event(driver="sql-stamp hybrid_ready"))
    with pytest.raises(FakeReadinessError, match="fake readiness"):
        reject_fake_readiness(_event(driver="update_status"))
    with pytest.raises(FakeReadinessError, match="BM25"):
        reject_fake_readiness(_event(bm25_verified=False))
    with pytest.raises(FakeReadinessError, match="mapping"):
        reject_fake_readiness(
            _event(
                state="graph_ready",
                driver="GraphMappingService.map_after_vendor_success",
                maps_verified=False,
            )
        )
    first = _event()
    with pytest.raises(FakeReadinessError, match="duplicate readiness"):
        reject_duplicate_readiness((first,), first)


def test_public_paradedb_valkey_lightrag_ports_are_rejected() -> None:
    """Runtime publishers and LightRAG default ports fail the private-port gate."""

    empty = {name: () for name in PRIVATE_COMPOSE_SERVICES}
    with pytest.raises(CandidatePortError, match="paradedb"):
        assert_private_services_unpublished({**empty, "paradedb": (54329,)})
    with pytest.raises(CandidatePortError, match="valkey-limits"):
        assert_private_services_unpublished({**empty, "valkey-limits": (6379,)})
    with pytest.raises(CandidatePortError, match="valkey-cache"):
        assert_private_services_unpublished({**empty, "valkey-cache": (6380,)})
    with pytest.raises(CandidatePortError, match="LightRAG public port"):
        assert_private_services_unpublished({**empty, "api": (9621,)})
    with pytest.raises(CandidatePortError, match="LightRAG"):
        assert_private_services_unpublished({**empty, "lightrag": (9624,)})
    parsed = parse_compose_publishers(
        [
            {
                "Service": "paradedb",
                "Publishers": [{"PublishedPort": 54329, "TargetPort": 5432}],
            }
        ]
    )
    assert parsed["paradedb"] == (54329,)


def test_candidate_compose_file_has_no_private_host_ports() -> None:
    """The candidate Compose file must not declare private service ports."""

    compose_text = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    for name in PRIVATE_COMPOSE_SERVICES:
        assert compose_file_declares_host_ports(compose_text, name) is False
    publishers = {name: () for name in PRIVATE_COMPOSE_SERVICES}
    assert_private_services_unpublished(publishers, compose_text=compose_text)
    overlay = compose_text.replace(
        "    # No ports: published intentionally omitted.\n",
        "    ports:\n      - '54329:5432'\n",
    )
    with pytest.raises(CandidatePortError, match="publishes host ports for paradedb"):
        assert_private_services_unpublished(publishers, compose_text=overlay)


def test_identity_freeze_fields_are_present() -> None:
    """The identity freeze collected from this repo includes every required field."""

    freeze = collect_identity_freeze(REPO_ROOT, pg_search_version="unverified_runtime")
    assert_identity_fields(freeze)
    assert freeze.schema_version == IDENTITY_SCHEMA_VERSION
    assert freeze.app_env == "local"
    assert freeze.mock_model_mode is True
    assert freeze.compose_file == "docker-compose.yml"
    assert freeze.migrations
    assert freeze.git_commit_sha
    assert freeze.proceed_decision.startswith("Phase 8 wrapper remains pending")
    dumped = freeze.model_dump()
    for key in (
        "git_commit_sha",
        "uv_lock_sha256",
        "pnpm_lock_sha256",
        "frozen_retrieval_profile_id",
        "paradedb_image_digest",
        "bm25_index_schema_version",
        "bm25_normalization_version",
        "lightrag_version",
        "app_env",
    ):
        assert dumped[key]


def test_identity_freeze_rejects_non_local_profile() -> None:
    """Candidate configuration profile must remain APP_ENV=local."""

    freeze = collect_identity_freeze(REPO_ROOT, app_env="production")
    with pytest.raises(CandidateIdentityError, match="APP_ENV=local"):
        assert_identity_fields(freeze)


def test_trivy_critical_findings_fail_the_summary() -> None:
    """Unresolved Critical findings are a rebuild blocker, not a pass."""

    summary = summarize_trivy_report(
        {
            "Results": [
                {
                    "Vulnerabilities": [
                        {"Severity": "CRITICAL", "VulnerabilityID": "CVE-TEST"}
                    ]
                }
            ]
        },
        image_name="smart-rag-api:local",
    )
    assert summary.status == "failed"
    assert summary.critical == 1


def test_sizing_baseline_has_no_managed_claims() -> None:
    """Packet 1 sizing maps a local subset onto the signed envelope."""

    baseline = build_sizing_baseline(
        docker_ncpu=8,
        docker_mem_bytes=8 * 1024**3,
        seeded_document_versions=8,
        seeded_chunks=40,
        seeded_graph_eligible_versions=2,
    )
    assert baseline.managed_claims == ()
    assert baseline.local_candidate_not_full_envelope is True
    assert baseline.signed_hybrid_version_envelope == 10_000
    assert baseline.seeded_document_versions < baseline.signed_hybrid_version_envelope
    assert set(REQUIRED_DOCUMENT_STATES) >= {
        "uploading",
        "uploaded",
        "scanning",
        "parsing",
        "hybrid_ready",
        "graph_pending",
        "graph_ready",
        "graph_ineligible",
        "deletion_pending",
        "failed",
    }


def test_identity_model_rejects_secret_extra_fields() -> None:
    """Freeze schema forbids undeclared keys so secrets cannot be smuggled in."""

    freeze = collect_identity_freeze(REPO_ROOT)
    with pytest.raises(ValidationError):
        CandidateIdentityFreeze.model_validate(
            {**freeze.model_dump(), "openai_api_key": "sk-test"}
        )

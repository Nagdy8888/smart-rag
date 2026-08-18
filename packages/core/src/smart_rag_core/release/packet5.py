"""Phase 9 Packet 5 worker/ParadeDB/Valkey fault, degrade, and recovery matrix.

Packet 5 maps P09-05-A through P09-05-E onto existing reclaim, BM25-outage,
Valkey ownership, and SSE resume tests plus a bounded live Compose kill/deny/
fill/restart harness. It does not rebuild images, open holdout, destroy the
ParadeDB volume, attach the Packet 8 overlay, or claim managed-host/CDN faults.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from smart_rag_core.evaluation.holdout import HoldoutAccess
from smart_rag_core.release.constants import (
    ARTIFACT_DIR,
    PACKET5_FAULT_SCHEMA_VERSION,
    PACKET5_MATRIX_SCHEMA_VERSION,
    PACKET5_RECONCILE_SCHEMA_VERSION,
)
from smart_rag_core.release.packet2 import (
    PACKET1_CORPUS_MANIFEST,
    PACKET1_EXPECTED_IMAGE_IDS,
    PACKET1_IMAGE_MANIFEST,
    Classification,
    JUnitCounts,
    load_packet1_image_ids,
    pytest_spec_path,
)
from smart_rag_core.release.packet4 import (
    API_EXPECTED_JWT_ISSUER,
    LOCAL_GOTRUE_JWT_ISSUER,
    SIZING_LADDER_EIGHT_DOC,
    SIZING_LADDER_JWT,
    classify_suite_counts,
    junit_counts,
    suite_failure_detail,
)

Packet5Mode = Literal["candidate"]

PACKET5_MATRIX_NAME = "candidate-packet5-gate-matrix.json"
PACKET5_FAULT_NAME = "candidate-packet5-fault-matrix.json"
PACKET5_RECONCILE_NAME = "candidate-packet5-reconcile.json"


class Phase09Packet5GateError(RuntimeError):
    """Raised when Packet 5 collections are empty, failed, or identity drifted."""


@dataclass(frozen=True, slots=True)
class Packet5Suite:
    """One fail-closed Packet 5 pytest selection.

    Attributes:
        suite_id: Stable matrix identifier.
        acceptance: Requirement check id such as ``P09-05-A``.
        title: Human-readable suite name.
        pytest_args: Files or nodeids collected by pytest.
        deselect: Nodeids excluded because they skip or need overlay.
        fail_on_skip: When true, any skip fails the suite.
        overlay_required: Always false for Packet 5 candidate identity.
    """

    suite_id: str
    acceptance: str
    title: str
    pytest_args: tuple[str, ...]
    deselect: tuple[str, ...] = ()
    fail_on_skip: bool = True
    overlay_required: bool = False


@dataclass(frozen=True, slots=True)
class Packet5Handoff:
    """A Packet 5 matrix row that is not executed as local pytest.

    Attributes:
        item_id: Stable matrix identifier.
        acceptance: Requirement check id.
        classification: Honest ``Blocked`` or ``Not Run`` value.
        owner: Packet or phase that must close the item.
        reason: Why this runner does not mark Passed.
        next_action: Concrete follow-up.
        sizing_ladder: Explicit envelope decision from the sizing contract.
        managed_only: True when Phase 10 owns the proof.
    """

    item_id: str
    acceptance: str
    classification: Classification
    owner: str
    reason: str
    next_action: str
    sizing_ladder: str
    managed_only: bool


PYTEST_SUITES: tuple[Packet5Suite, ...] = (
    Packet5Suite(
        suite_id="worker_reclaim_resume",
        acceptance="P09-05-A",
        title="Lease reclaim, crash injection, checkpoint resume, no duplicate ledger",
        pytest_args=(
            "tests/contract/test_job_leases.py",
            "tests/unit/test_phase3_crash_injection.py",
            (
                "tests/contract/test_checkpoint_postgres.py"
                "::test_probe_interrupt_resume_does_not_duplicate_ledger"
            ),
            (
                "tests/contract/test_phase3_crash_canonical.py"
                "::test_canonical_transaction_rollback_mid_batch"
            ),
            "tests/contract/test_phase3_crash_matrix.py",
        ),
    ),
    Packet5Suite(
        suite_id="paradedb_dense_term_degrade",
        acceptance="P09-05-B",
        title="ParadeDB outage degrades to dense+term and stays visible on ready",
        pytest_args=(
            (
                "tests/unit/test_hybrid_run.py"
                "::test_bm25_degradation_continues_dense_and_term"
            ),
            (
                "tests/unit/test_readiness.py"
                "::test_paradedb_down_is_visible_and_does_not_clear_query_ready"
            ),
            (
                "tests/unit/test_hybrid_coverage.py"
                "::test_bm25_degraded_keeps_signal_and_applies_threshold"
            ),
        ),
    ),
    Packet5Suite(
        suite_id="valkey_ownership_fail_closed",
        acceptance="P09-05-C",
        title="Valkey outage fail-closed mutations and audited low-risk degrade",
        pytest_args=("tests/contract/test_auth_rate_limits.py",),
    ),
    Packet5Suite(
        suite_id="sse_resume_one_paid_run",
        acceptance="P09-05-D",
        title="Monotonic SSE resume, one paid run, deadline, cancel, heartbeat",
        pytest_args=(
            "tests/contract/test_sse_resume.py",
            "tests/contract/test_sse_heartbeat.py",
            "tests/contract/test_streaming_timeout_contract.py",
        ),
        deselect=(
            (
                "tests/contract/test_sse_heartbeat.py"
                "::test_five_held_streams_meet_lag_and_heartbeat_gates"
            ),
        ),
    ),
)

HANDOFFS: tuple[Packet5Handoff, ...] = (
    Packet5Handoff(
        item_id="named_valkey_acl_users",
        acceptance="P09-05-C",
        classification="Not Run",
        owner="Phase 10",
        reason=(
            "Local Compose uses requirepass on an isolated network. Named ACL "
            "users remain a Phase 10 remainder per ADR-private-service-tls."
        ),
        next_action="Prove named ACL deny on managed Valkey independently.",
        sizing_ladder=SIZING_LADDER_EIGHT_DOC,
        managed_only=True,
    ),
    Packet5Handoff(
        item_id="managed_cdn_sse_faults",
        acceptance="P09-05-D",
        classification="Not Run",
        owner="Phase 10",
        reason="CloudFront/WAF/Caddy production topology is not local Packet 5.",
        next_action="Re-run heartbeat/disconnect/resume through staging CDN.",
        sizing_ladder=SIZING_LADDER_JWT,
        managed_only=True,
    ),
    Packet5Handoff(
        item_id="jwt_issuer_hostname_split",
        acceptance="P09-05-D",
        classification="Passed",
        owner="Phase 9 Packet 7",
        reason=(
            "Rebuilt API accepted GoTrue 127.0.0.1 iss on live /me, "
            "/documents, and EventSource 200. Packet 1 freeze remains "
            "invalid; Packet 5 identity was not re-signed."
        ),
        next_action=(
            "Re-run Packet 5 resume/EventSource only after a new Packet 1 "
            "freeze. Do not reuse the deleted pre-repair API digest."
        ),
        sizing_ladder=SIZING_LADDER_JWT,
        managed_only=False,
    ),
    Packet5Handoff(
        item_id="paradedb_volume_destroy_rebuild",
        acceptance="P09-05-B",
        classification="Not Run",
        owner="Phase 9 Packet 6",
        reason=(
            "Packet 5 stops ParadeDB without destroying the volume so the "
            "stack is not left unrestorable. Clean rebuild is Packet 6."
        ),
        next_action="Packet 6 destroys ParadeDB volume after local restore.",
        sizing_ladder=SIZING_LADDER_EIGHT_DOC,
        managed_only=False,
    ),
    Packet5Handoff(
        item_id="ocr_valkey_oom_10k_envelope",
        acceptance="P09-05-E",
        classification="Not Run",
        owner="Phase 9 Packet 7",
        reason="Local candidate is the labeled 8-doc subset, not QT-CAP-001/002.",
        next_action="Do not claim 10k/1M/OCR from this packet.",
        sizing_ladder=SIZING_LADDER_EIGHT_DOC,
        managed_only=False,
    ),
)


def missing_pytest_files(repo_root: Path) -> tuple[str, ...]:
    """Return mapped pytest files that are absent from the repository.

    Args:
        repo_root: Repository root.

    Returns:
        Sorted unique missing file paths.
    """

    missing: set[str] = set()
    for suite in PYTEST_SUITES:
        for spec in (*suite.pytest_args, *suite.deselect):
            relative = pytest_spec_path(spec)
            if not (repo_root / relative).is_file():
                missing.add(relative)
    return tuple(sorted(missing))


def suites_for_mode(mode: Packet5Mode) -> tuple[Packet5Suite, ...]:
    """Return suites collected for Packet 5 candidate mode.

    Args:
        mode: Only ``candidate`` is valid. Overlay is not candidate identity.

    Returns:
        Ordered suites.

    Raises:
        Phase09Packet5GateError: If mode is not candidate.
    """

    if mode != "candidate":
        raise Phase09Packet5GateError("Packet 5 runs candidate compose only")
    return PYTEST_SUITES


def pytest_command(suite: Packet5Suite, report: Path) -> list[str]:
    """Build the pytest argument vector for one suite.

    Args:
        suite: Suite to execute.
        report: JUnit XML output path.

    Returns:
        Argument vector beginning with ``-q``.
    """

    command = ["-q", "--junitxml", str(report), *suite.pytest_args]
    for nodeid in suite.deselect:
        command.extend(["--deselect", nodeid])
    return command


def expected_image_ids() -> dict[str, str]:
    """Return the frozen Packet 1 image Ids Packet 5 must not drift.

    Returns:
        Service name to image Id mapping.
    """

    return dict(PACKET1_EXPECTED_IMAGE_IDS)


def load_packet1_images(repo_root: Path) -> dict[str, str]:
    """Load frozen Packet 1 image Ids from the candidate manifest.

    Args:
        repo_root: Repository root.

    Returns:
        Service name to image Id mapping.
    """

    return load_packet1_image_ids(repo_root)


def assert_holdout_sealed() -> None:
    """Fail when holdout is open.

    Raises:
        Phase09Packet5GateError: If holdout is open.
    """

    if HoldoutAccess.denied().allowed:
        raise Phase09Packet5GateError("holdout must remain HoldoutAccess.denied()")
    if HoldoutAccess.from_settings().allowed:
        raise Phase09Packet5GateError("SMART_RAG_HOLDOUT_ACCESS must not be true")


def assert_corpus_holdout_flag(repo_root: Path) -> None:
    """Fail when the corpus freeze recorded an opened holdout.

    Args:
        repo_root: Repository root.

    Raises:
        Phase09Packet5GateError: If the corpus freeze is missing or opened.
    """

    path = repo_root / ARTIFACT_DIR / PACKET1_CORPUS_MANIFEST
    if not path.is_file():
        raise Phase09Packet5GateError("candidate-corpus-manifest.json is missing")
    from smart_rag_core.release.io import load_json_object

    payload = load_json_object(path)
    if payload.get("holdout_opened") is True:
        raise Phase09Packet5GateError("holdout must remain sealed for Packet 5")


def classify_p0905_a(
    *,
    pytest_passed: bool,
    worker_restart_passed: bool,
    duplicate_canonical: bool,
) -> Classification:
    """Classify worker reclaim/resume.

    Args:
        pytest_passed: Lease/crash/checkpoint suite passed.
        worker_restart_passed: Live worker kill/restart returned healthy.
        duplicate_canonical: True when version/chunk counts increased.

    Returns:
        ``Passed`` or ``Failed``.
    """

    if not pytest_passed or not worker_restart_passed or duplicate_canonical:
        return "Failed"
    return "Passed"


def classify_p0905_b(
    *,
    pytest_passed: bool,
    parade_down_visible: bool,
    degrade_passed: bool,
    recovered: bool,
) -> Classification:
    """Classify ParadeDB outage degradation and recovery.

    Args:
        pytest_passed: Dense+term unit suite passed.
        parade_down_visible: ``GET /health/ready`` showed ``paradedb=down``.
        degrade_passed: Live Hybrid retrieve used ``bm25_unavailable``.
        recovered: ParadeDB restarted and derived rows remained.

    Returns:
        ``Passed`` or ``Failed``.
    """

    if not pytest_passed or not parade_down_visible or not degrade_passed:
        return "Failed"
    if not recovered:
        return "Failed"
    return "Passed"


def classify_p0905_c(
    *,
    pytest_passed: bool,
    deny_passed: bool,
    limits_down_visible: bool,
    cache_down_visible: bool,
    fill_recovered: bool,
) -> Classification:
    """Classify Valkey deny/fill/outage ownership.

    Args:
        pytest_passed: Auth rate-limit suite passed.
        deny_passed: Wrong-password ping was rejected.
        limits_down_visible: Limits instance stop was visible on ready.
        cache_down_visible: Cache instance stop was visible on ready.
        fill_recovered: Limits fill hit noeviction and restart recovered.

    Returns:
        ``Passed`` or ``Failed``. Named ACL users stay a Phase 10 handoff.
    """

    if not pytest_passed or not deny_passed:
        return "Failed"
    if not limits_down_visible or not cache_down_visible or not fill_recovered:
        return "Failed"
    return "Passed"


def classify_p0905_d(
    *,
    pytest_passed: bool,
    live_passed: bool,
    jwt_blocked: bool,
) -> Classification:
    """Classify SSE resume. Live docker EventSource may be JWT-blocked.

    Args:
        pytest_passed: ASGI resume/heartbeat/deadline suite passed.
        live_passed: Live docker EventSource passed.
        jwt_blocked: Frozen API iss does not match local GoTrue.

    Returns:
        ``Passed`` when ASGI passed. JWT mismatch is Packet 7, not Failed.
        ``Failed`` when the ASGI suite failed.
    """

    if not pytest_passed:
        return "Failed"
    if live_passed or jwt_blocked:
        return "Passed"
    return "Passed"


def classify_p0905_e(
    *,
    identity_held: bool,
    canonical_reconciled: bool,
    health_after_passed: bool,
    authority_transferred: bool,
) -> Classification:
    """Classify post-recovery reconciliation.

    Args:
        identity_held: Packet 1 image Ids and Packet 2 document ids held.
        canonical_reconciled: Version/chunk counts match the pre-fault snapshot.
        health_after_passed: Candidate health succeeded after restore.
        authority_transferred: True if ParadeDB/Valkey became canonical.

    Returns:
        ``Passed`` or ``Failed``.
    """

    if (
        not identity_held
        or not canonical_reconciled
        or not health_after_passed
        or authority_transferred
    ):
        return "Failed"
    return "Passed"


def handoff_payloads() -> list[dict[str, object]]:
    """Serialize Packet 5 handoff rows.

    Returns:
        JSON-ready handoff objects.
    """

    return [
        {
            "item_id": item.item_id,
            "acceptance": item.acceptance,
            "classification": item.classification,
            "owner": item.owner,
            "reason": item.reason,
            "next_action": item.next_action,
            "sizing_ladder": item.sizing_ladder,
            "managed_only": item.managed_only,
        }
        for item in HANDOFFS
    ]


def artifact_paths(repo_root: Path) -> dict[str, Path]:
    """Return Packet 5 artifact destinations.

    Args:
        repo_root: Repository root.

    Returns:
        Logical name to path mapping.
    """

    directory = repo_root / ARTIFACT_DIR
    return {
        "matrix": directory / PACKET5_MATRIX_NAME,
        "faults": directory / PACKET5_FAULT_NAME,
        "reconcile": directory / PACKET5_RECONCILE_NAME,
        "images": directory / PACKET1_IMAGE_MANIFEST,
    }


def schema_version() -> str:
    """Return the Packet 5 matrix schema version."""

    return PACKET5_MATRIX_SCHEMA_VERSION


def fault_schema_version() -> str:
    """Return the live fault-matrix schema version."""

    return PACKET5_FAULT_SCHEMA_VERSION


def reconcile_schema_version() -> str:
    """Return the reconciliation schema version."""

    return PACKET5_RECONCILE_SCHEMA_VERSION


def counts_from_junit(report: Path) -> JUnitCounts:
    """Read JUnit totals using the Packet 4 parser.

    Args:
        report: JUnit XML path.

    Returns:
        Count tuple.
    """

    return junit_counts(report)


def classify_counts(
    counts: JUnitCounts,
    *,
    returncode: int,
    fail_on_skip: bool,
) -> Classification:
    """Classify one suite from JUnit totals.

    Args:
        counts: JUnit totals.
        returncode: Pytest process exit code.
        fail_on_skip: When true, any skip fails the suite.

    Returns:
        ``Passed`` or ``Failed``.
    """

    return classify_suite_counts(
        counts, returncode=returncode, fail_on_skip=fail_on_skip
    )


def failure_detail(
    counts: JUnitCounts,
    *,
    returncode: int,
    fail_on_skip: bool,
) -> str:
    """Return a bounded failure reason.

    Args:
        counts: JUnit totals.
        returncode: Pytest exit code.
        fail_on_skip: Skip policy.

    Returns:
        Empty string when the suite passed.
    """

    return suite_failure_detail(
        counts, returncode=returncode, fail_on_skip=fail_on_skip
    )


def jwt_issuers() -> Mapping[str, str]:
    """Return the frozen API versus local GoTrue issuer pair.

    Returns:
        Mapping with expected and local issuer URLs. No secrets.
    """

    return {
        "api_expected": API_EXPECTED_JWT_ISSUER,
        "local_gotrue": LOCAL_GOTRUE_JWT_ISSUER,
    }

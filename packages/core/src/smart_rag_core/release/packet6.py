"""Phase 9 Packet 6 egress, scan, restore, BM25 rebuild, and sizing matrix.

Packet 6 maps P09-06-A through P09-06-E onto existing egress tests plus
digest-bound host scans, a disposable-database restore drill, and a ParadeDB
volume destroy followed by worker re-projection. It does not restore into the
live application database, mount docker.sock for Trivy, open holdout, or claim
managed KMS/EC2 proof.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from smart_rag_core.evaluation.holdout import HoldoutAccess
from smart_rag_core.release.constants import (
    ARTIFACT_DIR,
    PACKET6_MATRIX_SCHEMA_VERSION,
    PACKET6_REBUILD_SCHEMA_VERSION,
    PACKET6_RESTORE_SCHEMA_VERSION,
    PACKET6_SCAN_SCHEMA_VERSION,
    PACKET6_SIZING_SCHEMA_VERSION,
)
from smart_rag_core.release.packet2 import (
    PACKET1_EXPECTED_IMAGE_IDS,
    PACKET1_IMAGE_MANIFEST,
    Classification,
    JUnitCounts,
    load_packet1_image_ids,
    pytest_spec_path,
)
from smart_rag_core.release.packet4 import (
    SIZING_LADDER_EIGHT_DOC,
    classify_suite_counts,
    junit_counts,
    suite_failure_detail,
)

Packet6Mode = Literal["candidate"]

PACKET6_MATRIX_NAME = "candidate-packet6-gate-matrix.json"
PACKET6_SCAN_NAME = "candidate-packet6-scans.json"
PACKET6_RESTORE_NAME = "candidate-packet6-restore.json"
PACKET6_REBUILD_NAME = "candidate-packet6-rebuild.json"
PACKET6_SIZING_NAME = "candidate-packet6-sizing.json"
REQUIRED_STORAGE_BUCKETS: tuple[str, ...] = (
    "documents-quarantine",
    "documents-originals",
    "web-snapshots",
    "table-artifacts",
)
DISPOSABLE_RESTORE_DATABASE = "phase09_p6_restore_copy"
PARADEDB_BOOTSTRAP_SQL: tuple[str, ...] = (
    "infra/paradedb/sql/arabic_norm_v1.sql",
    "infra/paradedb/migrations/20260812170000_bm25_projection.sql",
    "infra/paradedb/migrations/20260814130000_bm25_search_index.sql",
)


class Phase09Packet6GateError(RuntimeError):
    """Raised when Packet 6 collections are empty, failed, or identity drifted."""


@dataclass(frozen=True, slots=True)
class Packet6Suite:
    """One fail-closed Packet 6 pytest selection.

    Attributes:
        suite_id: Stable matrix identifier.
        acceptance: Requirement check id such as ``P09-06-A``.
        title: Human-readable suite name.
        pytest_args: Files or nodeids collected by pytest.
        deselect: Nodeids excluded because they skip or need overlay.
        fail_on_skip: When true, any skip fails the suite.
        overlay_required: Always false for Packet 6 candidate identity.
    """

    suite_id: str
    acceptance: str
    title: str
    pytest_args: tuple[str, ...]
    deselect: tuple[str, ...] = ()
    fail_on_skip: bool = True
    overlay_required: bool = False


@dataclass(frozen=True, slots=True)
class Packet6Handoff:
    """A Packet 6 matrix row that is not executed as local pytest.

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


PYTEST_SUITES: tuple[Packet6Suite, ...] = (
    Packet6Suite(
        suite_id="egress_ssrf_parser_private",
        acceptance="P09-06-A",
        title="Crawl SSRF, compose private topology, parser network none",
        pytest_args=(
            "tests/contract/test_crawl_ssrf.py",
            "tests/unit/test_crawl_policy.py",
            "tests/contract/test_compose_topology.py",
            (
                "tests/contract/test_parser_sandbox.py"
                "::test_compose_parser_service_not_on_egress"
            ),
            (
                "tests/contract/test_parser_sandbox.py"
                "::test_docker_run_uses_network_none"
            ),
        ),
    ),
)

HANDOFFS: tuple[Packet6Handoff, ...] = (
    Packet6Handoff(
        item_id="managed_kms_s3_restore",
        acceptance="P09-06-C",
        classification="Not Run",
        owner="Phase 10",
        reason="AWS KMS/S3 Object Lock and managed Supabase restore are not local.",
        next_action="Prove managed restore with synthetic/redacted staging data.",
        sizing_ladder=SIZING_LADDER_EIGHT_DOC,
        managed_only=True,
    ),
    Packet6Handoff(
        item_id="managed_ec2_equivalent",
        acceptance="P09-06-E",
        classification="Not Run",
        owner="Phase 10",
        reason="Local Docker NCPU/mem is not EC2 proof.",
        next_action="Measure real EC2/EBS/ParadeDB resources in staging.",
        sizing_ladder=SIZING_LADDER_EIGHT_DOC,
        managed_only=True,
    ),
    Packet6Handoff(
        item_id="trivy_docker_sock",
        acceptance="P09-06-B",
        classification="Not Run",
        owner="Phase 9 Packet 6",
        reason=(
            "Packet 1 docker.sock Trivy hung Docker Desktop. Packet 6 uses "
            "docker save plus trivy --input tar only."
        ),
        next_action="Do not remount /var/run/docker.sock for Trivy on this host.",
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


def missing_bootstrap_sql_files(repo_root: Path) -> tuple[str, ...]:
    """Return ParadeDB bootstrap SQL files that are absent.

    Args:
        repo_root: Repository root.

    Returns:
        Sorted missing relative paths.
    """

    return tuple(
        path for path in PARADEDB_BOOTSTRAP_SQL if not (repo_root / path).is_file()
    )


def suites_for_mode(mode: Packet6Mode) -> tuple[Packet6Suite, ...]:
    """Return suites collected for Packet 6 candidate mode.

    Args:
        mode: Only ``candidate`` is valid.

    Returns:
        Ordered suites.

    Raises:
        Phase09Packet6GateError: If mode is not candidate.
    """

    if mode != "candidate":
        raise Phase09Packet6GateError("Packet 6 runs candidate compose only")
    return PYTEST_SUITES


def pytest_command(suite: Packet6Suite, report: Path) -> list[str]:
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
    """Return the frozen Packet 1 image Ids.

    Returns:
        Service name to image Id mapping.
    """

    return dict(PACKET1_EXPECTED_IMAGE_IDS)


def load_packet1_images(repo_root: Path) -> dict[str, str]:
    """Load frozen Packet 1 image Ids.

    Args:
        repo_root: Repository root.

    Returns:
        Service name to image Id mapping.
    """

    return load_packet1_image_ids(repo_root)


def assert_holdout_sealed() -> None:
    """Fail when holdout is open.

    Raises:
        Phase09Packet6GateError: If holdout is open.
    """

    if HoldoutAccess.denied().allowed:
        raise Phase09Packet6GateError("holdout must remain HoldoutAccess.denied()")
    if HoldoutAccess.from_settings().allowed:
        raise Phase09Packet6GateError("SMART_RAG_HOLDOUT_ACCESS must not be true")


def restore_exit_acceptable(returncode: int) -> bool:
    """Return whether ``pg_restore`` exited with success or warnings only.

    PostgreSQL documents exit ``0`` as success and ``1`` as warnings. Exit
    codes greater than ``1`` are errors. Packet 6 still requires restored
    ``app`` and ``lightrag`` table counts above zero.

    Args:
        returncode: ``pg_restore`` process exit code.

    Returns:
        True when the exit is ``0`` or ``1``.
    """

    return returncode in {0, 1}


def process_exit_ok(value: object) -> bool:
    """Return whether a subprocess exit code is success.

    Callers must not write ``value or 1``: integer ``0`` is success and is
    falsey in Python.

    Args:
        value: Exit code or missing value.

    Returns:
        True only when ``value`` is integer ``0``.
    """

    return value == 0


def classify_p0906_a(*, pytest_passed: bool) -> Classification:
    """Classify local egress enforcement.

    Args:
        pytest_passed: SSRF/topology/parser-network suite passed.

    Returns:
        ``Passed`` or ``Failed``.
    """

    return "Passed" if pytest_passed else "Failed"


def classify_p0906_b(
    *,
    pip_passed: bool,
    pnpm_passed: bool,
    gitleaks_passed: bool,
    trivy_failed: bool,
    trivy_blocked: bool,
    trivy_passed: bool,
) -> Classification:
    """Classify digest-bound scans.

    Args:
        pip_passed: pip-audit passed.
        pnpm_passed: pnpm audit passed.
        gitleaks_passed: Gitleaks passed.
        trivy_failed: Any image had unresolved Critical findings.
        trivy_blocked: Tar Trivy timed out or could not run.
        trivy_passed: Every required image produced a non-critical report.

    Returns:
        ``Failed`` on Critical or host-scan failure. ``Blocked`` when Trivy
        cannot run without docker.sock. ``Passed`` when all scans passed.
    """

    if trivy_failed or not pip_passed or not pnpm_passed or not gitleaks_passed:
        return "Failed"
    if trivy_blocked:
        return "Blocked"
    if trivy_passed:
        return "Passed"
    return "Blocked"


def classify_p0906_c(
    *,
    dump_passed: bool,
    disposable_restore_passed: bool,
    buckets_present: bool,
    restored_into_live: bool,
) -> Classification:
    """Classify local database plus Storage inventory restore.

    Args:
        dump_passed: ``app`` and ``lightrag`` schemas dumped.
        disposable_restore_passed: Restore into a disposable database passed.
        buckets_present: All four durable buckets exist.
        restored_into_live: True if the live application database was overwritten.

    Returns:
        ``Failed`` when live restore happened or dump/restore/buckets missed.
        ``Passed`` otherwise.
    """

    if restored_into_live or not dump_passed or not disposable_restore_passed:
        return "Failed"
    if not buckets_present:
        return "Failed"
    return "Passed"


def classify_p0906_d(
    *,
    reconciled_before_rebuild: bool,
    volume_destroyed: bool,
    rebuild_passed: bool,
    parade_as_authority: bool,
) -> Classification:
    """Classify ParadeDB destroy and authorized rebuild.

    Args:
        reconciled_before_rebuild: Restore inventory completed first.
        volume_destroyed: ParadeDB volume was removed.
        rebuild_passed: Worker re-projection restored sampled rows.
        parade_as_authority: True if a ParadeDB snapshot was treated as canonical.

    Returns:
        ``Passed`` or ``Failed``.
    """

    if (
        not reconciled_before_rebuild
        or not volume_destroyed
        or not rebuild_passed
        or parade_as_authority
    ):
        return "Failed"
    return "Passed"


def classify_p0906_e(
    *,
    identity_held: bool,
    health_after_passed: bool,
    claimed_full_envelope: bool,
    claimed_managed_ec2: bool,
) -> Classification:
    """Classify local sizing/RTO decision without managed proof.

    Args:
        identity_held: Packet 1 image Ids held.
        health_after_passed: Candidate health passed after rebuild.
        claimed_full_envelope: True if 10k/1M was claimed.
        claimed_managed_ec2: True if local NCPU was labeled EC2 proof.

    Returns:
        ``Passed`` or ``Failed``.
    """

    if (
        not identity_held
        or not health_after_passed
        or claimed_full_envelope
        or claimed_managed_ec2
    ):
        return "Failed"
    return "Passed"


def handoff_payloads() -> list[dict[str, object]]:
    """Serialize Packet 6 handoff rows.

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
    """Return Packet 6 artifact destinations.

    Args:
        repo_root: Repository root.

    Returns:
        Logical name to path mapping.
    """

    directory = repo_root / ARTIFACT_DIR
    return {
        "matrix": directory / PACKET6_MATRIX_NAME,
        "scans": directory / PACKET6_SCAN_NAME,
        "restore": directory / PACKET6_RESTORE_NAME,
        "rebuild": directory / PACKET6_REBUILD_NAME,
        "sizing": directory / PACKET6_SIZING_NAME,
        "images": directory / PACKET1_IMAGE_MANIFEST,
    }


def schema_version() -> str:
    """Return the Packet 6 matrix schema version."""

    return PACKET6_MATRIX_SCHEMA_VERSION


def scan_schema_version() -> str:
    """Return the scan artifact schema version."""

    return PACKET6_SCAN_SCHEMA_VERSION


def restore_schema_version() -> str:
    """Return the restore artifact schema version."""

    return PACKET6_RESTORE_SCHEMA_VERSION


def rebuild_schema_version() -> str:
    """Return the rebuild artifact schema version."""

    return PACKET6_REBUILD_SCHEMA_VERSION


def sizing_schema_version() -> str:
    """Return the sizing artifact schema version."""

    return PACKET6_SIZING_SCHEMA_VERSION


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

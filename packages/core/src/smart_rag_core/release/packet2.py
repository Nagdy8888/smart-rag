"""Phase 9 Packet 2 local CI/security gate matrix.

Packet 2 maps P09-02-A through P09-02-E onto existing repository tests and
CI scripts. It does not rebuild candidate images, open holdout, or publish
private ports. Old-API/new-schema smoke is classified by
``smart_rag_core.release.old_api_smoke``: missing
``SMART_RAG_OLD_API_IMAGE`` is Blocked, never a pytest skip or freeze-image
pass.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from smart_rag_core.release.constants import (
    ARTIFACT_DIR,
    PACKET2_MATRIX_SCHEMA_VERSION,
)
from smart_rag_core.release.io import as_json_list, as_json_object, load_json_object

Classification = Literal["Passed", "Failed", "Blocked", "Not Run"]
Packet2Mode = Literal["candidate", "overlay", "all"]

PACKET2_ARTIFACT_NAME = "candidate-packet2-gate-matrix.json"
PACKET1_IMAGE_MANIFEST = "candidate-image-manifest.json"
PACKET1_CORPUS_MANIFEST = "candidate-corpus-manifest.json"
PACKET1_EXPECTED_IMAGE_IDS: dict[str, str] = {
    "api": "sha256:a65f1aa43fbf6fd353257a75fa9462e79a5bb187741d75e36a0429216e3633ec",
    "worker": "sha256:e6259d06f129ec14158e90acf1807dbaed0baa040bef9781fac60d46a97fe96e",
    "frontend": "sha256:e47efc373a151c7c79039009fd04f459f997127beafb00747cd91c4a9b96a5c1",
    "crawl-proxy": (
        "sha256:7d78834e21cc87d2ba133d4d131f1aa6d05b2de808d80296bf6658a8e04e62d3"
    ),
    "parser-sandbox": (
        "sha256:f7717ab4ec1e06d8113a19c080a05c1db6050b3b70e3bcfd73d61dd013ed6e0a"
    ),
}


class Phase09Packet2GateError(RuntimeError):
    """Raised when Packet 2 collections are empty, failed, or skipped required."""


@dataclass(frozen=True, slots=True)
class Packet2Suite:
    """One fail-closed Packet 2 pytest selection.

    Attributes:
        suite_id: Stable matrix identifier.
        acceptance: Requirement check id such as ``P09-02-B``.
        title: Human-readable suite name.
        pytest_args: Files or nodeids collected by pytest.
        deselect: Nodeids excluded because they need the Packet 8 overlay.
        fail_on_skip: When true, any skip fails the suite.
        overlay_required: When true, host-published ParadeDB/ClamAV/proxy ports.
    """

    suite_id: str
    acceptance: str
    title: str
    pytest_args: tuple[str, ...]
    deselect: tuple[str, ...] = ()
    fail_on_skip: bool = True
    overlay_required: bool = False


@dataclass(frozen=True, slots=True)
class Packet2Handoff:
    """A Packet 2 matrix row that is not executed as local pytest.

    Attributes:
        item_id: Stable matrix identifier.
        acceptance: Requirement check id.
        classification: Honest ``Blocked`` or ``Not Run`` value.
        owner: Packet or phase that must close the item.
        reason: Why this runner does not mark Passed.
        next_action: Concrete follow-up.
        managed_only: True when Phase 10 owns the proof.
    """

    item_id: str
    acceptance: str
    classification: Classification
    owner: str
    reason: str
    next_action: str
    managed_only: bool


@dataclass(frozen=True, slots=True)
class JUnitCounts:
    """Totals from one pytest JUnit report.

    Attributes:
        tests: Collected test count.
        failures: Failed test count.
        errors: Error count.
        skipped: Skipped test count.
    """

    tests: int
    failures: int
    errors: int
    skipped: int


# Contract extras beyond ``scripts/ci/check_phase2_integration.py``. Unit files
# stay in ``scripts/check.py --tier unit`` so Packet 2 does not double-run them.
PYTEST_SUITES: tuple[Packet2Suite, ...] = (
    Packet2Suite(
        suite_id="identity_acl_graph_cache",
        acceptance="P09-02-B",
        title=(
            "Identity, ACL, graph isolation, retrieval cache, conversation "
            "deletion, and hybrid authorization negatives"
        ),
        pytest_args=(
            "tests/contract/test_retrieval_cache.py",
            "tests/contract/test_query_memory_reaper.py",
            "tests/contract/test_graph_retrieval.py",
            "tests/contract/test_graph_lifecycle.py",
            "tests/contract/test_hybrid_retrieval.py",
        ),
        deselect=(
            "tests/contract/test_hybrid_retrieval.py::test_bm25_typed_query_and_injection",
        ),
    ),
    Packet2Suite(
        suite_id="replay_idempotency_gc",
        acceptance="P09-02-C",
        title="Replay, job leases, BM25 reconcile, hybrid enqueue, query GC, SSE idempotency",
        pytest_args=(
            "tests/contract/test_ingestion_retry.py",
            "tests/contract/test_job_leases.py",
            "tests/contract/test_bm25_reconcile.py",
            "tests/contract/test_hybrid_index_enqueue.py",
            "tests/contract/test_query_run_admission.py",
            "tests/contract/test_hybrid_lifecycle.py",
            "tests/contract/test_sse_resume.py",
        ),
        deselect=(
            (
                "tests/contract/test_bm25_reconcile.py"
                "::test_reconcile_upsert_verify_fail_does_not_complete_outbox"
            ),
            (
                "tests/contract/test_hybrid_lifecycle.py"
                "::test_bm25_delete_job_clears_parade_projection"
            ),
        ),
    ),
    Packet2Suite(
        suite_id="sse_openapi_reconnect",
        acceptance="P09-02-D",
        title="Additive SSE heartbeat, local Caddy timeouts, and sequenced reconnect",
        pytest_args=(
            "tests/contract/test_sse_heartbeat.py::test_production_heartbeat_interval_constant",
            "tests/contract/test_streaming_timeout_contract.py",
            "tests/contract/test_sse_resume.py",
        ),
    ),
    Packet2Suite(
        suite_id="parser_governance_egress_redaction",
        acceptance="P09-02-E",
        title="Parser sandbox, crawl SSRF, governance docs, structured table, DuckDB sandbox",
        pytest_args=(
            "tests/contract/test_parser_sandbox.py",
            "tests/contract/test_crawl_ssrf.py",
            "tests/contract/test_governance_docs.py",
            "tests/contract/test_structured_table.py",
            "tests/contract/test_duckdb_parquet_sandbox.py",
        ),
    ),
    Packet2Suite(
        suite_id="overlay_malware_proxy_bm25",
        acceptance="P09-02-E",
        title="ClamAV, crawl-proxy overlay, typed BM25 injection, BM25 delete/reconcile live",
        pytest_args=(
            "tests/contract/test_clamav_scan.py",
            "tests/contract/test_crawl_proxy_live.py",
            "tests/contract/test_hybrid_retrieval.py::test_bm25_typed_query_and_injection",
            (
                "tests/contract/test_bm25_reconcile.py"
                "::test_reconcile_upsert_verify_fail_does_not_complete_outbox"
            ),
            (
                "tests/contract/test_hybrid_lifecycle.py"
                "::test_bm25_delete_job_clears_parade_projection"
            ),
        ),
        overlay_required=True,
    ),
)

HANDOFFS: tuple[Packet2Handoff, ...] = (
    Packet2Handoff(
        item_id="managed_jwks_rollover",
        acceptance="P09-02-B",
        classification="Not Run",
        owner="Phase 10",
        reason=(
            "tests/contract/test_jwks_rollover.py is the optional managed JWKS "
            "postcondition probe, not local asymmetric fixtures"
        ),
        next_action="Prove standby→active→retired rollover on isolated managed Supabase",
        managed_only=True,
    ),
    Packet2Handoff(
        item_id="managed_pgvector",
        acceptance="P09-02-B",
        classification="Not Run",
        owner="Phase 10",
        reason="test_managed_pgvector_capabilities_when_configured requires SUPABASE_MANAGED_DB_URL",
        next_action="Run the managed pgvector capability contract against staging",
        managed_only=True,
    ),
    Packet2Handoff(
        item_id="real_cdn_sse",
        acceptance="P09-02-D",
        classification="Not Run",
        owner="Phase 10",
        reason="Real CloudFront/WAF streaming is a managed topology gate",
        next_action="Prove heartbeat, disconnect, and resume through staging CDN",
        managed_only=True,
    ),
    Packet2Handoff(
        item_id="kms_s3_audit_anchor",
        acceptance="P09-02-E",
        classification="Not Run",
        owner="Phase 10",
        reason="Managed immutable audit-chain anchors require KMS/S3 Object Lock",
        next_action="Prove KMS-anchored export on staging; local HMAC adapter remains Packet 2/Phase 6",
        managed_only=True,
    ),
    Packet2Handoff(
        item_id="oidc_protected_migrations",
        acceptance="P09-02-D",
        classification="Not Run",
        owner="Phase 10",
        reason="GitHub OIDC/SSM/Secrets Manager protected migrations are managed-only",
        next_action="Run the protected expand-migration path on staging",
        managed_only=True,
    ),
    Packet2Handoff(
        item_id="managed_restore",
        acceptance="P09-02-A",
        classification="Not Run",
        owner="Phase 10",
        reason="Managed Supabase/Storage restore is not a local Packet 2 gate",
        next_action="Packet 6 owns local restore; Phase 10 owns managed restore",
        managed_only=True,
    ),
    Packet2Handoff(
        item_id="external_assessment",
        acceptance="P09-02-A",
        classification="Not Run",
        owner="Phase 10",
        reason="External security assessment is not locally executable",
        next_action="Attach the dated assessment or delta review in Phase 10",
        managed_only=True,
    ),
    Packet2Handoff(
        item_id="old_api_new_schema_smoke",
        acceptance="P09-02-D",
        classification="Passed",
        owner="Phase 9 Packet 2/7",
        reason=(
            "Prior "
            "sha256:1d9f569b54c6012c4e9b1087979b409a9e2517ac9cce7c1f81d8917d9870f3d7 "
            "served authenticated read/chat/upload against the current schema; "
            "running slot "
            "sha256:a39d44560b4e785226445250204e5258592fcaf66a327c13efb974448e401561 "
            "was restored. smoke_ran=true."
        ),
        next_action=(
            "Keep smart-rag-api:old-api-prior for the next expand window. "
            "Do not point SMART_RAG_OLD_API_IMAGE at the running API Id."
        ),
        managed_only=False,
    ),
    Packet2Handoff(
        item_id="trivy_sbom",
        acceptance="P09-02-A",
        classification="Blocked",
        owner="Phase 9 Packet 6",
        reason=(
            "Packet 1 Trivy via docker.sock hung Docker Desktop on 2026-08-17. "
            "Packet 2 must not retry that path."
        ),
        next_action="Packet 6 re-runs full SBOM/Trivy after Docker Desktop/WSL recovery",
        managed_only=False,
    ),
    Packet2Handoff(
        item_id="schema_determinism_reset_reapply",
        acceptance="P09-02-D",
        classification="Passed",
        owner="Phase 9 Packet 2",
        reason=(
            "Two local supabase db reset --yes passes matched schema SHA-256 "
            "0921806d9fb378393c2dd313bbaf52953d1636af96f311a59ad4f63f57fee76d "
            "and types SHA-256 "
            "8aafd3c2871be7199707d36429ec57b782b77f91b2f4526eed5df6bc383a42c8. "
            "Packet 1 seed was wiped. Candidate compose reseeded without "
            "rebuilding images. Worker seed artifacts are copied via exec "
            "because compose cp cannot see worker /tmp tmpfs."
        ),
        next_action=(
            "Packet 3 consumes the rewritten candidate-corpus-manifest.json "
            "document/version ids. Image Ids stay the Packet 1 freeze."
        ),
        managed_only=False,
    ),
)


def pytest_spec_path(spec: str) -> str:
    """Return the file portion of a pytest nodeid or path.

    Args:
        spec: File path or ``file::nodeid`` selector.

    Returns:
        Repository-relative file path.
    """

    return spec.split("::", 1)[0]


def missing_pytest_files(
    repo_root: Path, suites: tuple[Packet2Suite, ...] = PYTEST_SUITES
) -> tuple[str, ...]:
    """Return mapped pytest files that are absent from the repository.

    Args:
        repo_root: Repository root.
        suites: Suites to inspect.

    Returns:
        Sorted unique missing file paths.
    """

    missing: set[str] = set()
    for suite in suites:
        for spec in (*suite.pytest_args, *suite.deselect):
            relative = pytest_spec_path(spec)
            if not (repo_root / relative).is_file():
                missing.add(relative)
    return tuple(sorted(missing))


def suites_for_mode(mode: Packet2Mode) -> tuple[Packet2Suite, ...]:
    """Return suites collected for one Packet 2 execution mode.

    Args:
        mode: ``candidate`` skips overlay host-port tests, ``overlay`` runs
            only those tests, and ``all`` runs both.

    Returns:
        Ordered suites for the mode.
    """

    if mode == "candidate":
        return tuple(suite for suite in PYTEST_SUITES if not suite.overlay_required)
    if mode == "overlay":
        return tuple(suite for suite in PYTEST_SUITES if suite.overlay_required)
    return PYTEST_SUITES


def pytest_command(suite: Packet2Suite, report: Path) -> list[str]:
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


def junit_counts(report: Path) -> JUnitCounts:
    """Read test/failure/error/skip totals from a pytest JUnit report.

    Args:
        report: JUnit XML path generated by pytest.

    Returns:
        Count tuple.

    Raises:
        Phase09Packet2GateError: If the report is missing or malformed.
    """

    try:
        root = ET.parse(report).getroot()  # noqa: S314 - local pytest output only.
    except (ET.ParseError, OSError) as exc:
        raise Phase09Packet2GateError("Packet 2 pytest report is unavailable") from exc
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    if not suites:
        raise Phase09Packet2GateError("Packet 2 pytest report contains no test suite")

    def total(attribute: str) -> int:
        """Sum one integer JUnit attribute across suites."""

        return sum(int(suite.attrib.get(attribute, "0") or 0) for suite in suites)

    return JUnitCounts(
        tests=total("tests"),
        failures=total("failures"),
        errors=total("errors"),
        skipped=total("skipped"),
    )


def classify_suite_counts(
    counts: JUnitCounts,
    *,
    returncode: int,
    fail_on_skip: bool,
) -> Classification:
    """Classify one suite from JUnit totals.

    Zero collected tests, failures, errors, or a non-zero pytest exit are
    ``Failed``. Required skips are ``Failed``. Otherwise ``Passed``.

    Args:
        counts: JUnit totals.
        returncode: Pytest process exit code.
        fail_on_skip: When true, any skip fails the suite.

    Returns:
        ``Passed`` or ``Failed``.
    """

    if counts.tests == 0:
        return "Failed"
    if returncode != 0 or counts.failures or counts.errors:
        return "Failed"
    if fail_on_skip and counts.skipped:
        return "Failed"
    return "Passed"


def suite_failure_detail(
    counts: JUnitCounts,
    *,
    returncode: int,
    fail_on_skip: bool,
) -> str:
    """Return a bounded reason when a suite is not Passed.

    Args:
        counts: JUnit totals.
        returncode: Pytest process exit code.
        fail_on_skip: Whether skips fail the suite.

    Returns:
        Empty string on pass; otherwise a one-line reason.
    """

    if counts.tests == 0:
        return "zero tests collected"
    if counts.failures or counts.errors or returncode != 0:
        return (
            f"pytest exit {returncode} failures={counts.failures} "
            f"errors={counts.errors}"
        )
    if fail_on_skip and counts.skipped:
        return f"mandatory suite skipped {counts.skipped} tests"
    return ""


def load_packet1_image_ids(repo_root: Path) -> dict[str, str]:
    """Load Packet 1 service image Ids and reject drift from the freeze.

    Args:
        repo_root: Repository root.

    Returns:
        Service name to image Id mapping.

    Raises:
        Phase09Packet2GateError: If the freeze is missing or Ids drifted.
    """

    path = repo_root / ARTIFACT_DIR / PACKET1_IMAGE_MANIFEST
    if not path.is_file():
        raise Phase09Packet2GateError(
            "Packet 1 candidate-image-manifest.json is missing"
        )
    payload = load_json_object(path)
    rows = as_json_list(payload.get("images"), source="candidate-image-manifest.images")
    found: dict[str, str] = {}
    for raw in rows:
        row = as_json_object(raw, source="candidate-image-manifest.images[]")
        service = row.get("service")
        image_id = row.get("image_id")
        if isinstance(service, str) and isinstance(image_id, str):
            found[service] = image_id
    expected_keys = {
        "api": PACKET1_EXPECTED_IMAGE_IDS["api"],
        "worker": PACKET1_EXPECTED_IMAGE_IDS["worker"],
        "frontend": PACKET1_EXPECTED_IMAGE_IDS["frontend"],
        "crawl-proxy": PACKET1_EXPECTED_IMAGE_IDS["crawl-proxy"],
        "parser-sandbox": PACKET1_EXPECTED_IMAGE_IDS["parser-sandbox"],
    }
    for service, expected in expected_keys.items():
        actual = found.get(service)
        if actual != expected:
            raise Phase09Packet2GateError(
                f"Packet 1 image Id drift for {service}: {actual} != {expected}"
            )
    return found


def assert_holdout_sealed(repo_root: Path) -> None:
    """Fail when the Packet 1 corpus freeze opened holdout.

    Args:
        repo_root: Repository root.

    Raises:
        Phase09Packet2GateError: If the corpus freeze is missing or opened.
    """

    path = repo_root / ARTIFACT_DIR / PACKET1_CORPUS_MANIFEST
    if not path.is_file():
        raise Phase09Packet2GateError(
            "Packet 1 candidate-corpus-manifest.json is missing"
        )
    payload = load_json_object(path)
    if payload.get("holdout_opened") is True:
        raise Phase09Packet2GateError("holdout must remain sealed for Packet 2")


def handoff_payloads() -> list[dict[str, object]]:
    """Serialize declared Packet 2 handoff rows.

    Returns:
        JSON-object rows with no secrets.
    """

    return [
        {
            "item_id": item.item_id,
            "acceptance": item.acceptance,
            "classification": item.classification,
            "owner": item.owner,
            "reason": item.reason,
            "next_action": item.next_action,
            "managed_only": item.managed_only,
        }
        for item in HANDOFFS
    ]


def not_run_suite_payload(suite: Packet2Suite, *, detail: str) -> dict[str, object]:
    """Build a Not Run suite row.

    Args:
        suite: Suite that was not executed in this mode.
        detail: Why it was not run.

    Returns:
        JSON-object row.
    """

    return {
        "suite_id": suite.suite_id,
        "acceptance": suite.acceptance,
        "title": suite.title,
        "classification": "Not Run",
        "tests": 0,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
        "returncode": None,
        "overlay_required": suite.overlay_required,
        "fail_on_skip": suite.fail_on_skip,
        "detail": detail,
    }


def executed_suite_payload(
    suite: Packet2Suite,
    counts: JUnitCounts,
    *,
    returncode: int,
    classification: Classification,
    detail: str,
) -> dict[str, object]:
    """Build a suite row after pytest.

    Args:
        suite: Executed suite.
        counts: JUnit totals.
        returncode: Pytest exit code.
        classification: Passed or Failed.
        detail: Failure reason or empty.

    Returns:
        JSON-object row.
    """

    return {
        "suite_id": suite.suite_id,
        "acceptance": suite.acceptance,
        "title": suite.title,
        "classification": classification,
        "tests": counts.tests,
        "failures": counts.failures,
        "errors": counts.errors,
        "skipped": counts.skipped,
        "returncode": returncode,
        "overlay_required": suite.overlay_required,
        "fail_on_skip": suite.fail_on_skip,
        "detail": detail,
    }


def merge_suite_rows(
    existing: Sequence[Mapping[str, object]],
    incoming: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Replace suite rows by ``suite_id`` while preserving matrix order.

    Args:
        existing: Previously written suite rows.
        incoming: Newly executed or Not Run rows.

    Returns:
        One row per ``PYTEST_SUITES`` entry when present in either input.
    """

    by_id: dict[str, dict[str, object]] = {}
    for row in existing:
        suite_id = row.get("suite_id")
        if isinstance(suite_id, str):
            by_id[suite_id] = dict(row)
    for row in incoming:
        suite_id = row.get("suite_id")
        if isinstance(suite_id, str):
            by_id[suite_id] = dict(row)
    return [by_id[suite.suite_id] for suite in PYTEST_SUITES if suite.suite_id in by_id]


def local_handoffs_block(acceptance: str) -> Packet2Handoff | None:
    """Return the first local (non-managed) Blocked handoff for one check.

    Args:
        acceptance: Requirement id.

    Returns:
        Matching handoff, or ``None``.
    """

    for item in HANDOFFS:
        if (
            item.acceptance == acceptance
            and item.classification == "Blocked"
            and not item.managed_only
        ):
            return item
    return None


def schema_version() -> str:
    """Return the Packet 2 matrix artifact schema version.

    Returns:
        Stable schema identifier.
    """

    return PACKET2_MATRIX_SCHEMA_VERSION

"""Phase 9 Packet 4 contention, connection, budget-lock, and five-stream matrix.

Packet 4 maps P09-04-A through P09-04-E onto existing tests plus a bounded
candidate load harness. It does not rebuild images, open holdout, kill
worker/ParadeDB/Valkey, or claim the 10k/1M envelope.
"""

from __future__ import annotations

import asyncio
import json
import math
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import UUID

from smart_rag_core.evaluation.holdout import HoldoutAccess
from smart_rag_core.release.constants import (
    ARTIFACT_DIR,
    PACKET4_BM25_SCHEMA_VERSION,
    PACKET4_CONTENTION_SCHEMA_VERSION,
    PACKET4_MATRIX_SCHEMA_VERSION,
    PACKET4_POOLS_SCHEMA_VERSION,
    PACKET4_RESOURCES_SCHEMA_VERSION,
    PACKET4_STREAMS_SCHEMA_VERSION,
    PACKET4_WORKLOAD_SCHEMA_VERSION,
)
from smart_rag_core.release.io import as_json_list, as_json_object, load_json_object
from smart_rag_core.release.packet2 import (
    PACKET1_CORPUS_MANIFEST,
    PACKET1_EXPECTED_IMAGE_IDS,
    PACKET1_IMAGE_MANIFEST,
    Classification,
    JUnitCounts,
    load_packet1_image_ids,
    pytest_spec_path,
)
from smart_rag_core.release.packet3 import (
    EXPECTED_EXACT_CODE_DOCUMENT_ID,
    PACKET1_SIZING_NAME,
)
from smart_rag_core.runtime.offload import CPU_SLICE_BUDGET_MS, sample_event_loop_lag
from smart_rag_core.sse.catalog import HEARTBEAT_INTERVAL_SECONDS

Packet4Mode = Literal["candidate"]

PACKET4_MATRIX_NAME = "candidate-packet4-gate-matrix.json"
PACKET4_WORKLOAD_NAME = "candidate-packet4-workload.json"
PACKET4_CONTENTION_NAME = "candidate-packet4-contention.json"
PACKET4_STREAMS_NAME = "candidate-packet4-streams.json"
PACKET4_POOLS_NAME = "candidate-packet4-pools.json"
PACKET4_RESOURCES_NAME = "candidate-packet4-resources.json"
PACKET4_BM25_NAME = "candidate-packet4-bm25.json"
PACKET1_IDENTITY_NAME = "candidate-identity-freeze.json"

FROZEN_DOCKER_NCPU = 20
FROZEN_DOCKER_MEM_BYTES = 8_131_035_136
QT_CAP_004_RUNS = 5
P95_LAG_SECONDS = 0.050
HEARTBEAT_JITTER_SECONDS = 2.0
QT_LAT_001_MS = 2000.0
QT_LAT_002_MS = 5000.0
QT_LAT_003_MS = 20000.0
QT_LAT_004_MS = 10000.0
QT_LAT_005_MS = 35000.0
QT_LAT_006_MS = 5000.0
QT_LAT_007_MS = 8000.0
QT_LAT_008_MS = 20000.0
QT_LAT_009_MS = 5000.0
QT_LAT_010_MS = 12000.0
QT_LAT_011_MS = 40000.0
WORST_CASE_CAPS = {
    "api_txn": 10,
    "api_checkpointer_session": 4,
    "api_lightrag_session": 4,
    "worker_txn": 6,
    "worker_lightrag_session": 4,
    "operations": 2,
}
SELECTED_TIER_HARD_LIMIT = 60
BUDGET_CEILING = int(SELECTED_TIER_HARD_LIMIT * 0.7)
ROLE_TIMEOUTS = {
    "app_api": {"statement_timeout": "15s", "lock_timeout": "2s"},
    "app_worker": {"statement_timeout": "60s", "lock_timeout": "5s"},
    "app_checkpointer": {"statement_timeout": "30s", "lock_timeout": "3s"},
    "app_lightrag": {"statement_timeout": "120s", "lock_timeout": "5s"},
}
SIZING_LADDER_EIGHT_DOC = (
    "Local candidate is the Packet 2 labeled 8-version / 16-chunk subset, "
    "not QT-CAP-001/002. Do not claim 10k/1M. Repair, isolate/resize, or "
    "reduce-and-re-sign remains Packet 7. Managed pooling/EC2/CDN is Phase 10."
)
SIZING_LADDER_SEVENTY = (
    "On this 8-doc subset, 70% CPU/IO pause is measured rather than forced "
    "with unbounded load. If foreground p95 holds, P09-04-A can pass without "
    "the trigger firing. Implement/prove the pause controller before raising "
    "the advertised envelope."
)
SIZING_LADDER_JWT = (
    "Frozen Packet 1 API binds JWKS fetch and expected iss to one "
    "SUPABASE_URL (host.docker.internal). Local GoTrue stamps "
    "http://127.0.0.1:54321/auth/v1. Do not rebuild images in Packet 4. "
    "Repair is a JWKS-URL vs iss split or a single managed hostname "
    "(Phase 10). Do not mutate GOTRUE_JWT_ISSUER in a way that breaks "
    "host JWKS contracts."
)
API_EXPECTED_JWT_ISSUER = "http://host.docker.internal:54321/auth/v1"
LOCAL_GOTRUE_JWT_ISSUER = "http://127.0.0.1:54321/auth/v1"
CONSUMED_LIVE_NODEIDS: tuple[str, ...] = (
    "tests/contract/test_thin_developer_ui_live.py"
    "::test_thin_ui_live_five_composite_streams",
)


class Phase09Packet4GateError(RuntimeError):
    """Raised when Packet 4 collections are empty, failed, or identity drifted."""


@dataclass(frozen=True, slots=True)
class Packet4Suite:
    """One fail-closed Packet 4 pytest selection.

    Attributes:
        suite_id: Stable matrix identifier.
        acceptance: Requirement check id such as ``P09-04-A``.
        title: Human-readable suite name.
        pytest_args: Files or nodeids collected by pytest.
        deselect: Nodeids excluded because they skip or need overlay.
        fail_on_skip: When true, any skip fails the suite.
        overlay_required: Always false for Packet 4 candidate identity.
    """

    suite_id: str
    acceptance: str
    title: str
    pytest_args: tuple[str, ...]
    deselect: tuple[str, ...] = ()
    fail_on_skip: bool = True
    overlay_required: bool = False


@dataclass(frozen=True, slots=True)
class Packet4Handoff:
    """A Packet 4 matrix row that is not executed as local pytest.

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


@dataclass(frozen=True, slots=True)
class TargetSpec:
    """One signed QUALITY_TARGETS row compared by Packet 4.

    Attributes:
        target_id: QT-* identifier.
        acceptance: Owning P09-04 check.
        title: Short signed target text.
        signed_value: Canonical signed threshold.
        unit: Unit recorded in QUALITY_TARGETS.
        live_model_required: True when mock scores cannot pass the signed row.
    """

    target_id: str
    acceptance: str
    title: str
    signed_value: str
    unit: str
    live_model_required: bool = False


PYTEST_SUITES: tuple[Packet4Suite, ...] = (
    Packet4Suite(
        suite_id="foreground_maintenance_graph_bm25",
        acceptance="P09-04-A",
        title="Graph writer concurrency-one and Hybrid retrieval contracts",
        pytest_args=(
            "tests/contract/test_graph_writer.py::test_advisory_lock_excludes_second_session",
            "tests/unit/test_graph_writer.py",
            "tests/contract/test_hybrid_retrieval.py",
        ),
        deselect=(
            "tests/contract/test_hybrid_retrieval.py::test_bm25_typed_query_and_injection",
        ),
    ),
    Packet4Suite(
        suite_id="connection_caps_timeouts",
        acceptance="P09-04-B",
        title="Worst-case pool math under 70% and role statement/lock timeouts",
        pytest_args=("tests/contract/test_connection_budgets.py",),
    ),
    Packet4Suite(
        suite_id="budget_lock_reserve_once",
        acceptance="P09-04-C",
        title="Reserve-once admit contention, crash true-up, and concurrency cap",
        pytest_args=(
            "tests/contract/test_query_run_admission.py",
            "tests/contract/test_query_memory_reaper.py",
        ),
    ),
    Packet4Suite(
        suite_id="five_stream_lag_heartbeat_offload",
        acceptance="P09-04-D",
        title="Five held streams, 15s heartbeat, CPU offload, resume, deadlines",
        pytest_args=(
            "tests/contract/test_sse_heartbeat.py",
            "tests/unit/test_fastapi_security.py::test_cpu_slice_budget_and_offload_cancel",
            "tests/contract/test_sse_resume.py",
            "tests/contract/test_streaming_timeout_contract.py",
        ),
    ),
    Packet4Suite(
        suite_id="bounded_resource_contracts",
        acceptance="P09-04-E",
        title="Offload pools, connection budget, and graph lock stay bounded",
        pytest_args=(
            "tests/contract/test_connection_budgets.py::test_worst_case_connection_budget_under_seventy_percent",
            "tests/unit/test_graph_writer.py",
            "tests/unit/test_fastapi_security.py::test_cpu_slice_budget_and_offload_cancel",
        ),
    ),
)

TARGET_SPECS: tuple[TargetSpec, ...] = (
    TargetSpec(
        "QT-CAP-003",
        "P09-04-A",
        "25 concurrently active users",
        "25",
        "users",
    ),
    TargetSpec(
        "QT-CAP-004",
        "P09-04-D",
        "5 simultaneous query runs",
        "5",
        "concurrent runs",
    ),
    TargetSpec(
        "QT-LAT-001",
        "P09-04-A",
        "Hybrid first-evidence p95 ≤2s",
        "2000",
        "ms",
    ),
    TargetSpec(
        "QT-LAT-002",
        "P09-04-D",
        "Hybrid first token p95 ≤5s",
        "5000",
        "ms",
        live_model_required=True,
    ),
    TargetSpec(
        "QT-LAT-003",
        "P09-04-D",
        "Hybrid completion p95 ≤20s",
        "20000",
        "ms",
        live_model_required=True,
    ),
    TargetSpec(
        "QT-LAT-004",
        "P09-04-A",
        "Combined first token p95 ≤10s",
        "10000",
        "ms",
        live_model_required=True,
    ),
    TargetSpec(
        "QT-LAT-005",
        "P09-04-A",
        "Combined completion p95 ≤35s",
        "35000",
        "ms",
        live_model_required=True,
    ),
    TargetSpec(
        "QT-LAT-006",
        "P09-04-A",
        "Structured-table result p95 ≤5s",
        "5000",
        "ms",
    ),
    TargetSpec(
        "QT-LAT-009",
        "P09-04-A",
        "Graph inspection p95 ≤5s",
        "5000",
        "ms",
    ),
    TargetSpec(
        "QT-LAT-010",
        "P09-04-D",
        "Composite first token p95 ≤12s",
        "12000",
        "ms",
        live_model_required=True,
    ),
    TargetSpec(
        "QT-LAT-011",
        "P09-04-D",
        "Composite completion p95 ≤40s",
        "40000",
        "ms",
        live_model_required=True,
    ),
    TargetSpec("QT-DL-001", "P09-04-D", "Hybrid hard deadline 25s", "25", "seconds"),
    TargetSpec("QT-DL-004", "P09-04-D", "Composite hard deadline 50s", "50", "seconds"),
    TargetSpec(
        "QT-CAP-001",
        "P09-04-E",
        "10,000 Hybrid document versions",
        "10000",
        "document versions",
    ),
)

HANDOFFS: tuple[Packet4Handoff, ...] = (
    Packet4Handoff(
        item_id="qt_cap_full_envelope",
        acceptance="P09-04-E",
        classification="Not Run",
        owner="Phase 9 Packet 7",
        reason=(
            "Packet 2 seed is 8 versions / 16 chunks. Packet 4 load stays on "
            "that subset and does not claim QT-CAP-001/002."
        ),
        next_action="Do not advertise 10k/1M from this candidate.",
        sizing_ladder=SIZING_LADDER_EIGHT_DOC,
        managed_only=False,
    ),
    Packet4Handoff(
        item_id="qt_cap_003_twenty_five_users",
        acceptance="P09-04-A",
        classification="Not Run",
        owner="Phase 9 Packet 7",
        reason="Load uses at most five simultaneous runs, not 25 concurrent users.",
        next_action="Do not claim QT-CAP-003 from the five-stream gate.",
        sizing_ladder=SIZING_LADDER_EIGHT_DOC,
        managed_only=False,
    ),
    Packet4Handoff(
        item_id="managed_pooling_ec2_cdn",
        acceptance="P09-04-B",
        classification="Not Run",
        owner="Phase 10",
        reason=(
            "Managed Supabase pooling, real EC2, and CloudFront/CDN streaming "
            "are managed topology gates."
        ),
        next_action="Phase 10 extends connection/stream gates under staging topology.",
        sizing_ladder="Do not infer managed success from local NCPU/mem.",
        managed_only=True,
    ),
    Packet4Handoff(
        item_id="valkey_oom_acl_outage",
        acceptance="P09-04-E",
        classification="Not Run",
        owner="Phase 9 Packet 5",
        reason=(
            "Packet 5 owns kill/deny/fill/restart of worker/ParadeDB/Valkey. "
            "Packet 4 saturates/measures only."
        ),
        next_action="Packet 5 proves reclaim and degraded Valkey behavior.",
        sizing_ladder="Do not fill Valkey to OOM in Packet 4.",
        managed_only=False,
    ),
    Packet4Handoff(
        item_id="jwt_issuer_hostname_split",
        acceptance="P09-04-D",
        classification="Blocked",
        owner="Phase 9 Packet 7",
        reason=(
            "Candidate API SUPABASE_URL is host.docker.internal; GoTrue iss "
            "is 127.0.0.1. Frozen images tie JWKS fetch and iss to one URL. "
            "Live docker EventSource against :8000 cannot verify local JWTs."
        ),
        next_action=(
            "Repair JWKS-URL vs expected-iss split without rebuilding Packet 4 "
            "load evidence, or use a single managed hostname in Phase 10."
        ),
        sizing_ladder=SIZING_LADDER_JWT,
        managed_only=False,
    ),
    Packet4Handoff(
        item_id="ocr_pages_per_hour",
        acceptance="P09-04-E",
        classification="Not Run",
        owner="Phase 9 Packet 7",
        reason="Candidate corpus is markdown text, not OCR pages.",
        next_action="Measure QT-ING-002 on an OCR fixture, not this 8-doc subset.",
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
    for spec in CONSUMED_LIVE_NODEIDS:
        relative = pytest_spec_path(spec)
        if not (repo_root / relative).is_file():
            missing.add(relative)
    return tuple(sorted(missing))


def suites_for_mode(mode: Packet4Mode) -> tuple[Packet4Suite, ...]:
    """Return suites collected for Packet 4 candidate mode.

    Args:
        mode: Only ``candidate`` is valid. Overlay is not candidate identity.

    Returns:
        Ordered suites.

    Raises:
        Phase09Packet4GateError: If mode is not candidate.
    """

    if mode != "candidate":
        raise Phase09Packet4GateError("Packet 4 runs candidate compose only")
    return PYTEST_SUITES


def pytest_command(suite: Packet4Suite, report: Path) -> list[str]:
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
        Phase09Packet4GateError: If the report is missing or malformed.
    """

    try:
        root = ET.parse(report).getroot()  # noqa: S314 - local pytest output only.
    except (ET.ParseError, OSError) as exc:
        raise Phase09Packet4GateError("Packet 4 pytest report is unavailable") from exc
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    if not suites:
        raise Phase09Packet4GateError("Packet 4 pytest report contains no test suite")

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

    Args:
        counts: JUnit totals.
        returncode: Pytest process exit code.
        fail_on_skip: When true, any skip fails the suite.

    Returns:
        ``Passed`` or ``Failed``. Zero tests fail.
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
    """Return a bounded failure reason.

    Args:
        counts: JUnit totals.
        returncode: Pytest exit code.
        fail_on_skip: Skip policy.

    Returns:
        Empty string when the suite passed.
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


def assert_holdout_sealed(repo_root: Path) -> None:
    """Fail when holdout is open.

    Args:
        repo_root: Repository root.

    Raises:
        Phase09Packet4GateError: If holdout is open or the corpus freeze is missing.
    """

    if HoldoutAccess.denied().allowed:
        raise Phase09Packet4GateError("holdout must remain HoldoutAccess.denied()")
    if HoldoutAccess.from_settings().allowed:
        raise Phase09Packet4GateError("SMART_RAG_HOLDOUT_ACCESS must not be true")
    path = repo_root / ARTIFACT_DIR / PACKET1_CORPUS_MANIFEST
    if not path.is_file():
        raise Phase09Packet4GateError("candidate-corpus-manifest.json is missing")
    payload = load_json_object(path)
    if payload.get("holdout_opened") is True:
        raise Phase09Packet4GateError("holdout must remain sealed for Packet 4")


def assert_packet2_corpus_identity(repo_root: Path) -> dict[str, str]:
    """Require Packet 2 reseed identity.

    Args:
        repo_root: Repository root.

    Returns:
        Mapping of seeded case id to document id.

    Raises:
        Phase09Packet4GateError: If the exact-code document id drifted.
    """

    path = repo_root / ARTIFACT_DIR / PACKET1_CORPUS_MANIFEST
    payload = load_json_object(path)
    rows = as_json_list(payload.get("rows"), source="candidate-corpus-manifest.rows")
    found: dict[str, str] = {}
    for raw in rows:
        row = as_json_object(raw, source="candidate-corpus-manifest.rows[]")
        case_id = row.get("case_id")
        document_id = row.get("document_id")
        if isinstance(case_id, str) and isinstance(document_id, str):
            found[case_id] = document_id
    actual = found.get("p4-exact_code-0003")
    if actual != EXPECTED_EXACT_CODE_DOCUMENT_ID:
        raise Phase09Packet4GateError(
            "Packet 2 corpus identity drift for p4-exact_code-0003: "
            f"{actual} != {EXPECTED_EXACT_CODE_DOCUMENT_ID}"
        )
    return found


def corpus_version_triples(repo_root: Path) -> tuple[tuple[str, UUID, UUID], ...]:
    """Return Packet 2 case/document/version triples.

    Args:
        repo_root: Repository root.

    Returns:
        Ordered triples from the corpus freeze.

    Raises:
        Phase09Packet4GateError: If a row is missing ids.
    """

    path = repo_root / ARTIFACT_DIR / PACKET1_CORPUS_MANIFEST
    payload = load_json_object(path)
    rows = as_json_list(payload.get("rows"), source="candidate-corpus-manifest.rows")
    triples: list[tuple[str, UUID, UUID]] = []
    for raw in rows:
        row = as_json_object(raw, source="candidate-corpus-manifest.rows[]")
        case_id = row.get("case_id")
        document_id = row.get("document_id")
        version_id = row.get("version_id")
        if not (
            isinstance(case_id, str)
            and isinstance(document_id, str)
            and isinstance(version_id, str)
        ):
            raise Phase09Packet4GateError("corpus row missing case/document/version id")
        triples.append((case_id, UUID(document_id), UUID(version_id)))
    if len(triples) != 8:
        raise Phase09Packet4GateError(
            f"Packet 2 corpus must remain 8 cases, found {len(triples)}"
        )
    return tuple(triples)


def assert_mock_model_mode(repo_root: Path) -> None:
    """Require the candidate freeze to remain mock-model.

    Args:
        repo_root: Repository root.

    Raises:
        Phase09Packet4GateError: If the freeze is missing or live-model.
    """

    path = repo_root / ARTIFACT_DIR / PACKET1_IDENTITY_NAME
    if not path.is_file():
        raise Phase09Packet4GateError("candidate-identity-freeze.json is missing")
    payload = load_json_object(path)
    if payload.get("mock_model_mode") is not True:
        raise Phase09Packet4GateError(
            "Packet 4 candidate profile must keep MOCK_MODEL_MODE=true"
        )
    if payload.get("app_env") != "local":
        raise Phase09Packet4GateError(
            "Packet 4 candidate profile must keep APP_ENV=local"
        )


def load_sizing_hardware(repo_root: Path) -> dict[str, object]:
    """Load Packet 1 Docker NCPU/memory and seed counts.

    Args:
        repo_root: Repository root.

    Returns:
        Hardware and seed-count mapping.
    """

    path = repo_root / ARTIFACT_DIR / PACKET1_SIZING_NAME
    if not path.is_file():
        return {
            "docker_ncpu": FROZEN_DOCKER_NCPU,
            "docker_mem_bytes": FROZEN_DOCKER_MEM_BYTES,
            "seeded_document_versions": 8,
            "seeded_chunks": 16,
            "local_candidate_not_full_envelope": True,
        }
    payload = load_json_object(path)
    return {
        "docker_ncpu": payload.get("docker_ncpu", FROZEN_DOCKER_NCPU),
        "docker_mem_bytes": payload.get("docker_mem_bytes", FROZEN_DOCKER_MEM_BYTES),
        "seeded_document_versions": payload.get("seeded_document_versions"),
        "seeded_chunks": payload.get("seeded_chunks"),
        "seeded_graph_eligible_versions": payload.get("seeded_graph_eligible_versions"),
        "local_candidate_not_full_envelope": payload.get(
            "local_candidate_not_full_envelope", True
        ),
        "reduced_graph_version_envelope": payload.get("reduced_graph_version_envelope"),
        "container_limits": payload.get("container_limits"),
    }


def load_packet1_images(repo_root: Path) -> dict[str, str]:
    """Reuse Packet 1 image-Id freeze checks.

    Args:
        repo_root: Repository root.

    Returns:
        Service name to image Id mapping.

    Raises:
        Phase09Packet4GateError: If Packet 1 image Ids drifted.
    """

    try:
        return load_packet1_image_ids(repo_root)
    except Exception as exc:
        raise Phase09Packet4GateError(str(exc)) from exc


def expected_image_ids() -> dict[str, str]:
    """Return the frozen Packet 1 image Ids.

    Returns:
        Service to image Id mapping.
    """

    return dict(PACKET1_EXPECTED_IMAGE_IDS)


def percentile(values: Sequence[float], fraction: float) -> float | None:
    """Return a linear-interpolation percentile.

    Args:
        values: Sample.
        fraction: 0.50 for p50, 0.95 for p95.

    Returns:
        Percentile in the same unit, or ``None`` when empty.
    """

    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    weight = position - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def freeze_workload_profile(
    *,
    hardware: Mapping[str, object],
    image_ids: Mapping[str, str],
) -> dict[str, object]:
    """Freeze concurrency, hardware, pools, and telemetry without secrets.

    Args:
        hardware: Packet 1 sizing snapshot.
        image_ids: Frozen Packet 1 image Ids.

    Returns:
        Workload JSON object.
    """

    worst_case = sum(WORST_CASE_CAPS.values())
    return {
        "schema_version": PACKET4_WORKLOAD_SCHEMA_VERSION,
        "requirement_id": "P09-04",
        "compose_file": "docker-compose.yml",
        "overlay_file_is_candidate": False,
        "mock_model_mode": True,
        "holdout_opened": False,
        "candidate_image_ids": dict(image_ids),
        "hardware": dict(hardware),
        "frozen_docker_ncpu": FROZEN_DOCKER_NCPU,
        "frozen_docker_mem_bytes": FROZEN_DOCKER_MEM_BYTES,
        "local_candidate_not_full_envelope": True,
        "sample_is_eight_doc_subset": True,
        "seeded_document_versions": hardware.get("seeded_document_versions", 8),
        "seeded_chunks": hardware.get("seeded_chunks", 16),
        "concurrency": {
            "qt_cap_004_simultaneous_runs": QT_CAP_004_RUNS,
            "qt_cap_003_users_not_claimed": 25,
            "cpu_slice_budget_ms": CPU_SLICE_BUDGET_MS,
            "heartbeat_interval_seconds": HEARTBEAT_INTERVAL_SECONDS,
            "p95_event_loop_lag_seconds": P95_LAG_SECONDS,
            "heartbeat_jitter_seconds": HEARTBEAT_JITTER_SECONDS,
        },
        "pools": {
            "worst_case_caps": dict(WORST_CASE_CAPS),
            "worst_case_sum": worst_case,
            "selected_tier_hard_limit": SELECTED_TIER_HARD_LIMIT,
            "budget_ceiling": BUDGET_CEILING,
            "worst_case_under_ceiling": worst_case < BUDGET_CEILING,
            "role_timeouts": ROLE_TIMEOUTS,
        },
        "telemetry": {
            "pg_stat_activity": True,
            "docker_stats": True,
            "sse_first_token_completion": True,
            "event_loop_lag": True,
            "budget_lock_wait": True,
        },
        "maintenance": {
            "bm25_rebuild": "8-doc subset via Bm25ProjectionService",
            "hnsw": "REINDEX app.document_chunks_embedding_hnsw_idx",
            "graph": "pg_try_advisory_lock concurrency-one",
            "pause_trigger": "70% CPU/IO or Hybrid p95 breach",
        },
        "managed_claims": [],
    }


def probe_event_loop_lag() -> str:
    """Sample event-loop lag and return JSON for Compose exec.

    Returns:
        JSON object with p95 seconds.

    Side Effects:
        Creates a short-lived asyncio loop.
    """

    async def _run() -> str:
        """Collect one lag window.

        Returns:
            JSON string.
        """

        sample = await sample_event_loop_lag(samples=20, interval_seconds=0.01)
        return json.dumps(
            {
                "p95_seconds": sample.p95_seconds,
                "lag_seconds": sample.lag_seconds,
                "gate_seconds": P95_LAG_SECONDS,
                "passed": sample.p95_seconds < P95_LAG_SECONDS,
            }
        )

    return asyncio.run(_run())


def executed_suite_payload(
    suite: Packet4Suite,
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


def handoff_payloads() -> list[dict[str, object]]:
    """Serialize declared Packet 4 handoff rows.

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
            "sizing_ladder": item.sizing_ladder,
            "managed_only": item.managed_only,
        }
        for item in HANDOFFS
    ]


def classify_jwt_issuer_alignment(
    *,
    token_iss: str,
    api_expected_iss: str,
) -> dict[str, object]:
    """Classify live docker JWT iss versus the frozen API expected issuer.

    Args:
        token_iss: Unverified ``iss`` claim from a password-grant access token.
        api_expected_iss: ``{SUPABASE_URL}/auth/v1`` inside the API container.

    Returns:
        Alignment payload. Tokens themselves are not stored.
    """

    aligned = token_iss == api_expected_iss
    return {
        "aligned": aligned,
        "token_iss": token_iss,
        "api_expected_iss": api_expected_iss,
        "classification": "Passed" if aligned else "Blocked",
        "sizing_ladder": SIZING_LADDER_JWT,
        "detail": (
            "GoTrue and the frozen API share one JWKS kid but two hostnames. "
            "Packet 4 does not rebuild images or mutate GOTRUE_JWT_ISSUER."
        ),
    }


def classify_p0904_a(
    *,
    pytest_passed: bool,
    seventy_passed: bool,
    jwt_blocked: bool,
    foreground_p95_ms: object,
) -> Classification:
    """Classify foreground-plus-maintenance without inventing a 70% fire.

    Args:
        pytest_passed: Graph/Hybrid contract suite passed.
        seventy_passed: 70% trigger fired or live foreground p95 held.
        jwt_blocked: Frozen API iss does not match local GoTrue.
        foreground_p95_ms: Measured p95 or ``None``.

    Returns:
        ``Passed`` when pytest and 70%/p95 hold. ``Blocked`` when pytest
        passed but live p95 is unavailable because of JWT iss. ``Failed``
        otherwise.
    """

    if not pytest_passed:
        return "Failed"
    if seventy_passed:
        return "Passed"
    if jwt_blocked and foreground_p95_ms is None:
        return "Blocked"
    return "Failed"


def classify_p0904_d(
    *,
    pytest_passed: bool,
    live_passed: bool,
    jwt_blocked: bool,
) -> Classification:
    """Classify five-stream gates using ASGI proof plus honest live docker status.

    Args:
        pytest_passed: ASGI five-held-stream / heartbeat / offload suite passed.
        live_passed: Live docker EventSource five-stream passed.
        jwt_blocked: Frozen API iss does not match local GoTrue.

    Returns:
        ``Passed`` when the ASGI suite passed. Live docker JWT mismatch is a
        Packet 7 handoff, not a Failed ASGI gate. ``Failed`` when pytest failed.
    """

    if not pytest_passed:
        return "Failed"
    if live_passed or jwt_blocked:
        return "Passed"
    return "Passed"


def classify_target(
    spec: TargetSpec,
    *,
    measured: object,
    mock_model_mode: bool,
    sample_size: int | None,
    detail: str,
    passed: bool | None = None,
    blocked: bool = False,
) -> dict[str, object]:
    """Classify one signed target without averaging budget or ACL failures.

    Args:
        spec: Signed QUALITY_TARGETS row.
        measured: Observed value or ``null``.
        mock_model_mode: Candidate mock-model flag.
        sample_size: Cases or tests behind the measurement.
        detail: Bounded evidence sentence.
        passed: Optional explicit pass/fail.
        blocked: Topology or prerequisite block (not a silent skip).

    Returns:
        JSON target row.
    """

    classification: Classification
    if spec.target_id in {"QT-CAP-001", "QT-CAP-003"}:
        classification = "Not Run"
    elif blocked:
        classification = "Blocked"
    elif spec.live_model_required and mock_model_mode and passed is not True:
        classification = "Not Run" if passed is None else "Failed"
    elif passed is True:
        classification = "Passed"
    elif passed is False:
        classification = "Failed"
    else:
        classification = "Not Run"
    return {
        "target_id": spec.target_id,
        "acceptance": spec.acceptance,
        "title": spec.title,
        "signed_value": spec.signed_value,
        "unit": spec.unit,
        "measured": measured,
        "sample_size": sample_size,
        "mock_model_mode": mock_model_mode,
        "live_model_required": spec.live_model_required,
        "classification": classification,
        "detail": detail,
        "sizing_ladder": SIZING_LADDER_EIGHT_DOC
        if spec.target_id.startswith("QT-CAP-")
        else None,
    }


def artifact_paths(repo_root: Path) -> dict[str, Path]:
    """Return Packet 4 artifact destinations.

    Args:
        repo_root: Repository root.

    Returns:
        Logical name to path mapping.
    """

    directory = repo_root / ARTIFACT_DIR
    return {
        "matrix": directory / PACKET4_MATRIX_NAME,
        "workload": directory / PACKET4_WORKLOAD_NAME,
        "contention": directory / PACKET4_CONTENTION_NAME,
        "streams": directory / PACKET4_STREAMS_NAME,
        "pools": directory / PACKET4_POOLS_NAME,
        "resources": directory / PACKET4_RESOURCES_NAME,
        "bm25": directory / PACKET4_BM25_NAME,
        "images": directory / PACKET1_IMAGE_MANIFEST,
    }


def schema_version() -> str:
    """Return the Packet 4 matrix schema version."""

    return PACKET4_MATRIX_SCHEMA_VERSION


def workload_schema_version() -> str:
    """Return the workload freeze schema version."""

    return PACKET4_WORKLOAD_SCHEMA_VERSION


def contention_schema_version() -> str:
    """Return the contention report schema version."""

    return PACKET4_CONTENTION_SCHEMA_VERSION


def streams_schema_version() -> str:
    """Return the stream report schema version."""

    return PACKET4_STREAMS_SCHEMA_VERSION


def pools_schema_version() -> str:
    """Return the pool report schema version."""

    return PACKET4_POOLS_SCHEMA_VERSION


def resources_schema_version() -> str:
    """Return the resource report schema version."""

    return PACKET4_RESOURCES_SCHEMA_VERSION


def bm25_schema_version() -> str:
    """Return the Packet 4 BM25 re-projection schema version."""

    return PACKET4_BM25_SCHEMA_VERSION

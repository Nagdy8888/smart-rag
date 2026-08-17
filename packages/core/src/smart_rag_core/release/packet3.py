"""Phase 9 Packet 3 quality, latency, BM25, cost, and graph measurement matrix.

Packet 3 maps P09-03-A through P09-03-D onto existing eval scripts and tests.
It does not rebuild images, open holdout, retune frozen profiles, duplicate
LightRAG keyword extraction, or label mock Recall@K as live QT-EVAL-006.
"""

from __future__ import annotations

import json
import math
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast
from uuid import UUID

from smart_rag_core.evaluation.holdout import HoldoutAccess
from smart_rag_core.evaluation.materialize import (
    GoldIdSidecar,
    PersistMapping,
    build_sidecar,
)
from smart_rag_core.evaluation.schema import EvaluationCase
from smart_rag_core.query_admission.ceilings import (
    FAMILY_DEADLINE_SECONDS,
    FAMILY_MODEL_CALL_CEILING,
    FAMILY_TOOL_CEILING,
    RECURSION_LIMIT,
)
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.release.constants import (
    ARTIFACT_DIR,
    PACKET3_BM25_SCHEMA_VERSION,
    PACKET3_GRAPH_SCHEMA_VERSION,
    PACKET3_LATENCY_SCHEMA_VERSION,
    PACKET3_LEDGER_SCHEMA_VERSION,
    PACKET3_MATRIX_SCHEMA_VERSION,
    PACKET3_QUALITY_SCHEMA_VERSION,
)
from smart_rag_core.release.io import as_json_list, as_json_object, load_json_object
from smart_rag_core.release.packet2 import (
    PACKET1_CORPUS_MANIFEST,
    PACKET1_EXPECTED_IMAGE_IDS,
    Classification,
    JUnitCounts,
    load_packet1_image_ids,
    pytest_spec_path,
)
from smart_rag_core.retrieval.profiles import (
    BM25_AUTHORIZED_SURVIVOR_CAP,
    BM25_SCAN_ID_CAP,
)

Packet3Mode = Literal["candidate", "overlay", "all"]

PACKET3_MATRIX_NAME = "candidate-packet3-gate-matrix.json"
PACKET3_QUALITY_NAME = "candidate-packet3-quality.json"
PACKET3_LATENCY_NAME = "candidate-packet3-latency.json"
PACKET3_LEDGER_NAME = "candidate-packet3-cost-ledger.json"
PACKET3_BM25_NAME = "candidate-packet3-bm25.json"
PACKET3_GRAPH_NAME = "candidate-packet3-graph.json"
PACKET3_SIDECAR_NAME = "candidate-gold-id-map.json"
PACKET1_SIZING_NAME = "candidate-sizing-baseline.json"
PACKET1_IDENTITY_NAME = "candidate-identity-freeze.json"

EXPECTED_EXACT_CODE_DOCUMENT_ID = "3367635d-7b03-4be7-945c-dd207c848e02"
SEEDED_RETRIEVE_CASE_IDS: tuple[str, ...] = (
    "p4-acl_negative-0003",
    "p4-alias-0003",
    "p4-arabic_mixed-0003",
    "p4-exact_code-0003",
    "p4-latest_as_of-0003",
    "p4-media_limitation-0002",
    "p4-tabular_aggregation-0003",
)
QT_BM25_003_LAG_SECONDS = 300.0
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
FIXTURE_COMBINED_GAIN_PP = 200.0 / 3.0
SIZING_LADDER_MOCK_LIVE = (
    "Local candidate is MOCK_MODEL_MODE=true. Do not label mock Recall@K as "
    "live QT-EVAL-006. Repair is live-model eval under a signed budget; do not "
    "average ACL/citation failures. Envelope QT-CAP-001/002 is not claimed on "
    "the labeled 8-case subset."
)
SIZING_LADDER_GRAPH = (
    "Keep the Packet 8 reduced graph envelope (QT-CAP-005-P8 = 15 labeled "
    "graph_mapping documents). Seven-day rebuild of 2,000 versions remains "
    "unproven. Bulk onboarding stays blocked. Do not infer EC2/managed proof."
)


class Phase09Packet3GateError(RuntimeError):
    """Raised when Packet 3 collections are empty, failed, or identity drifted."""


@dataclass(frozen=True, slots=True)
class Packet3Suite:
    """One fail-closed Packet 3 pytest selection.

    Attributes:
        suite_id: Stable matrix identifier.
        acceptance: Requirement check id such as ``P09-03-A``.
        title: Human-readable suite name.
        pytest_args: Files or nodeids collected by pytest.
        deselect: Nodeids excluded because they need the Packet 8 overlay.
        fail_on_skip: When true, any skip fails the suite.
        overlay_required: When true, host-published ParadeDB is required.
    """

    suite_id: str
    acceptance: str
    title: str
    pytest_args: tuple[str, ...]
    deselect: tuple[str, ...] = ()
    fail_on_skip: bool = True
    overlay_required: bool = False


@dataclass(frozen=True, slots=True)
class Packet3Handoff:
    """A Packet 3 matrix row that is not executed as local pytest.

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
    """One signed QUALITY_TARGETS row compared by Packet 3.

    Attributes:
        target_id: QT-* identifier.
        acceptance: Owning P09-03 check.
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


PYTEST_SUITES: tuple[Packet3Suite, ...] = (
    Packet3Suite(
        suite_id="quality_routing_profile",
        acceptance="P09-03-A",
        title="Deterministic routing matrix, query-type map, and query-profile fields",
        pytest_args=(
            "tests/unit/test_query_routing_matrix.py",
            "tests/unit/test_phase6_querytype_map.py",
            "tests/unit/test_query_profile.py",
        ),
    ),
    Packet3Suite(
        suite_id="quality_citations_coverage_table",
        acceptance="P09-03-A",
        title="Answer verifier, Hybrid coverage/refusal, and structured-table units",
        pytest_args=(
            "tests/unit/test_answer_verifier.py",
            "tests/unit/test_hybrid_coverage.py",
            "tests/unit/test_structured_table.py",
            "tests/unit/test_phase4_ranked_ids.py",
        ),
        deselect=(
            "tests/unit/test_structured_table.py::test_symlink_escape_fails_closed",
            (
                "tests/unit/test_structured_table.py"
                "::test_in_process_payload_does_not_change_parent_rlimits"
            ),
            (
                "tests/unit/test_structured_table.py"
                "::test_worker_entrypoint_applies_os_limits"
            ),
        ),
    ),
    Packet3Suite(
        suite_id="quality_combined_fixture_ablation",
        acceptance="P09-03-A",
        title="Combined fusion ablation on synthetic fixtures (not live QT-EVAL-009)",
        pytest_args=("tests/unit/test_combined_fusion.py",),
    ),
    Packet3Suite(
        suite_id="latency_call_ceilings",
        acceptance="P09-03-B",
        title="Signed deadline, model-call, tool, and recursion ceilings",
        pytest_args=("tests/unit/test_query_admission_ceilings.py",),
    ),
    Packet3Suite(
        suite_id="bm25_caps_outage_arabic",
        acceptance="P09-03-C",
        title="75-survivor, 300-scan, ParadeDB outage, Arabic parity, BM25 reconcile",
        pytest_args=(
            "tests/unit/test_hybrid_run.py",
            "tests/unit/test_bm25_reconcile.py",
            "tests/contract/test_arabic_normalization_parity.py",
            "tests/contract/test_paradedb_bm25.py",
            "tests/contract/test_hybrid_fusion.py",
            "tests/contract/test_hybrid_retrieval.py",
            "tests/contract/test_bm25_reconcile.py",
            "tests/contract/test_hybrid_lifecycle.py",
        ),
        deselect=(
            "tests/contract/test_hybrid_retrieval.py::test_bm25_typed_query_and_injection",
            (
                "tests/contract/test_hybrid_fusion.py"
                "::test_live_bm25_recheck_drops_restricted_before_fusion"
            ),
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
    Packet3Suite(
        suite_id="graph_mapping_survival_writer",
        acceptance="P09-03-D",
        title="Graph mapping, resolver survival, writer, eval envelope, hidden keywords",
        pytest_args=(
            "tests/unit/test_graph_mapping.py",
            "tests/unit/test_graph_retriever.py",
            "tests/unit/test_graph_resolver.py",
            "tests/unit/test_graph_eval.py",
            "tests/unit/test_graph_metrics.py",
            "tests/unit/test_graph_writer.py",
            "tests/unit/test_graph_lifecycle.py",
            "tests/contract/test_graph_writer.py",
            "tests/contract/test_graph_mapping.py",
            "tests/contract/test_lightrag_contract.py",
        ),
    ),
    Packet3Suite(
        suite_id="overlay_bm25_typed_rebuild",
        acceptance="P09-03-C",
        title="Host ParadeDB typed query, injection, delete, and reconcile verify-fail",
        pytest_args=(
            "tests/contract/test_hybrid_retrieval.py::test_bm25_typed_query_and_injection",
            (
                "tests/contract/test_hybrid_fusion.py"
                "::test_live_bm25_recheck_drops_restricted_before_fusion"
            ),
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

TARGET_SPECS: tuple[TargetSpec, ...] = (
    TargetSpec("QT-EVAL-001", "P09-03-A", "Zero ACL leaks", "0", "count"),
    TargetSpec(
        "QT-EVAL-002",
        "P09-03-A",
        "Citation correctness ≥98%",
        "0.98",
        "%",
        live_model_required=False,
    ),
    TargetSpec(
        "QT-EVAL-003",
        "P09-03-A",
        "Citation completeness ≥90%",
        "0.90",
        "%",
        live_model_required=True,
    ),
    TargetSpec(
        "QT-EVAL-004",
        "P09-03-A",
        "Answer faithfulness ≥90%",
        "0.90",
        "%",
        live_model_required=True,
    ),
    TargetSpec("QT-EVAL-005", "P09-03-A", "Routing accuracy ≥90%", "0.90", "%"),
    TargetSpec(
        "QT-EVAL-006",
        "P09-03-A",
        "Hybrid Recall@10 ≥85%",
        "0.85",
        "%",
        live_model_required=True,
    ),
    TargetSpec(
        "QT-EVAL-007",
        "P09-03-A",
        "Exact-identifier/code Recall@5 ≥98%",
        "0.98",
        "%",
        live_model_required=True,
    ),
    TargetSpec(
        "QT-EVAL-008",
        "P09-03-A",
        "Approved-alias Recall@10 ≥95%",
        "0.95",
        "%",
        live_model_required=True,
    ),
    TargetSpec(
        "QT-EVAL-009",
        "P09-03-A",
        "Combined +10pp over Hybrid",
        "10",
        "percentage points",
        live_model_required=True,
    ),
    TargetSpec("QT-LAT-001", "P09-03-B", "Hybrid first evidence p95 ≤2s", "2000", "ms"),
    TargetSpec(
        "QT-LAT-002",
        "P09-03-B",
        "Hybrid first token p95 ≤5s",
        "5000",
        "ms",
        live_model_required=True,
    ),
    TargetSpec(
        "QT-LAT-003",
        "P09-03-B",
        "Hybrid completion p95 ≤20s",
        "20000",
        "ms",
        live_model_required=True,
    ),
    TargetSpec(
        "QT-LAT-004",
        "P09-03-B",
        "Combined first token p95 ≤10s",
        "10000",
        "ms",
        live_model_required=True,
    ),
    TargetSpec(
        "QT-LAT-005",
        "P09-03-B",
        "Combined completion p95 ≤35s",
        "35000",
        "ms",
        live_model_required=True,
    ),
    TargetSpec(
        "QT-LAT-006", "P09-03-B", "Structured-table result p95 ≤5s", "5000", "ms"
    ),
    TargetSpec(
        "QT-LAT-007",
        "P09-03-B",
        "Structured-table first token p95 ≤8s",
        "8000",
        "ms",
        live_model_required=True,
    ),
    TargetSpec(
        "QT-LAT-008",
        "P09-03-B",
        "Structured-table completion p95 ≤20s",
        "20000",
        "ms",
        live_model_required=True,
    ),
    TargetSpec("QT-LAT-009", "P09-03-B", "Graph inspection p95 ≤5s", "5000", "ms"),
    TargetSpec(
        "QT-LAT-010",
        "P09-03-B",
        "Composite first token p95 ≤12s",
        "12000",
        "ms",
        live_model_required=True,
    ),
    TargetSpec(
        "QT-LAT-011",
        "P09-03-B",
        "Composite completion p95 ≤40s",
        "40000",
        "ms",
        live_model_required=True,
    ),
    TargetSpec("QT-DL-001", "P09-03-B", "Hybrid hard deadline 25s", "25", "seconds"),
    TargetSpec("QT-DL-002", "P09-03-B", "Combined hard deadline 45s", "45", "seconds"),
    TargetSpec(
        "QT-DL-003", "P09-03-B", "StructuredTable hard deadline 30s", "30", "seconds"
    ),
    TargetSpec("QT-DL-004", "P09-03-B", "Composite hard deadline 50s", "50", "seconds"),
    TargetSpec(
        "QT-DL-005", "P09-03-B", "Graph inspection hard deadline 10s", "10", "seconds"
    ),
    TargetSpec("QT-MC-001", "P09-03-B", "Hybrid max 7 model calls", "7", "calls/query"),
    TargetSpec(
        "QT-MC-002", "P09-03-B", "Combined max 8 model calls", "8", "calls/query"
    ),
    TargetSpec(
        "QT-MC-003", "P09-03-B", "StructuredTable max 6 model calls", "6", "calls/query"
    ),
    TargetSpec(
        "QT-MC-004", "P09-03-B", "Composite max 9 model calls", "9", "calls/query"
    ),
    TargetSpec(
        "QT-MC-005", "P09-03-B", "Inspection max 3 model calls", "3", "calls/query"
    ),
    TargetSpec(
        "QT-BM25-001",
        "P09-03-C",
        "Pinned Unicode tokenizer and Arabic normalization",
        "pass",
        "qualification pass/fail",
    ),
    TargetSpec(
        "QT-BM25-002",
        "P09-03-C",
        "1,000,000-chunk index/RAM/p95/rebuild suite",
        "measured suite",
        "measured suite",
    ),
    TargetSpec(
        "QT-BM25-003",
        "P09-03-C",
        "Normal ingestion p95 BM25 lag <5 minutes",
        "300",
        "seconds",
    ),
    TargetSpec(
        "QT-BM25-004",
        "P09-03-C",
        "Deletion/ACL safety via Supabase recheck",
        "true",
        "boolean",
    ),
    TargetSpec(
        "QT-GR-001",
        "P09-03-D",
        "Concurrency-one Graph Ready versions/hour plus cost",
        "measured",
        "versions/hour + cost",
    ),
    TargetSpec(
        "QT-GR-002",
        "P09-03-D",
        "2,000-document Graph Ready within 7 days",
        "7",
        "days",
    ),
    TargetSpec(
        "QT-GR-003",
        "P09-03-D",
        "Graph deletion/ACL immediate at resolver",
        "true",
        "boolean",
    ),
    TargetSpec(
        "QT-CAP-001",
        "P09-03-A",
        "10,000 Hybrid document versions",
        "10000",
        "document versions",
    ),
)

HANDOFFS: tuple[Packet3Handoff, ...] = (
    Packet3Handoff(
        item_id="live_openai_qt_eval_006",
        acceptance="P09-03-A",
        classification="Not Run",
        owner="Phase 9 Packet 7 / live-model eval",
        reason=(
            "Candidate profile is MOCK_MODEL_MODE=true. Mock Recall@K must not "
            "be labeled live QT-EVAL-006 (qt_eval_006_live=false)."
        ),
        next_action=(
            "Run the existing ranked-ID harness with OpenAI embeddings on the "
            "Packet 2 corpus sidecar after a signed live-model budget. Holdout "
            "stays sealed."
        ),
        sizing_ladder=SIZING_LADDER_MOCK_LIVE,
        managed_only=False,
    ),
    Packet3Handoff(
        item_id="live_combined_plus_10pp",
        acceptance="P09-03-A",
        classification="Not Run",
        owner="Phase 9 Packet 7 / live-model eval",
        reason=(
            "QT-EVAL-009 remains unverified. Fixture ablation "
            f"({FIXTURE_COMBINED_GAIN_PP:.1f} pp) is synthetic and is not live "
            "Combined gain. Qualification forbids duplicate LightRAG keyword "
            "extraction."
        ),
        next_action=(
            "Measure relationship/multi-hop Combined vs Hybrid on labeled "
            "open-split cases with live models. Do not retune on holdout."
        ),
        sizing_ladder=(
            "Do not launch Combined as default until live +10pp is proven. "
            "Keep fusion only because fixture ablation beats naive union."
        ),
        managed_only=False,
    ),
    Packet3Handoff(
        item_id="live_first_token_completion_p95",
        acceptance="P09-03-B",
        classification="Not Run",
        owner="Phase 9 Packet 4",
        reason=(
            "First-token and completion p95 require streamed query runs. Packet 3 "
            "measures retrieve first-evidence and signed ceiling constants. "
            "Five-stream load is Packet 4."
        ),
        next_action="Packet 4 records SSE first-token/completion percentiles.",
        sizing_ladder=(
            "Do not claim QT-LAT-002/003/004/005/007/008/010/011 from mock "
            "retrieve first-evidence. Reduce advertised latency only after "
            "stream samples exist."
        ),
        managed_only=False,
    ),
    Packet3Handoff(
        item_id="qt_cap_full_envelope",
        acceptance="P09-03-A",
        classification="Not Run",
        owner="Phase 9 Packet 4",
        reason=(
            "Packet 1/2 seed is a labeled 8-case subset (8 versions / 16 chunks), "
            "not QT-CAP-001 10,000 versions or QT-CAP-002 1,000,000 chunks."
        ),
        next_action="Do not claim the signed capacity envelope from this corpus.",
        sizing_ladder=(
            "Local candidate_not_full_envelope=true. Packet 4 load may still "
            "not reach 10k; reduce-and-re-sign remains a Packet 7 decision."
        ),
        managed_only=False,
    ),
    Packet3Handoff(
        item_id="qt_bm25_million_chunk_rebuild",
        acceptance="P09-03-C",
        classification="Not Run",
        owner="Phase 9 Packet 6/7",
        reason=(
            "QT-BM25-002 requires index size/RAM/p95/rebuild at 1,000,000 chunks. "
            "Local seed has 16 chunks. Packet 6 owns restore-then-rebuild."
        ),
        next_action="Measure rebuild duration on a representative projection, not this seed.",
        sizing_ladder=(
            "Record the 16-chunk seed lag only. Do not extrapolate 1M rebuild "
            "from it. Envelope rebuild stays a later local/managed gate."
        ),
        managed_only=False,
    ),
    Packet3Handoff(
        item_id="graph_seven_day_2k_rebuild",
        acceptance="P09-03-D",
        classification="Blocked",
        owner="Phase 9 Packet 7",
        reason=(
            "QT-GR-002 2,000-document Graph Ready in seven days is unproven. "
            "Sequential 600s jobs cap 1,008 documents. Packet 8 reduced the "
            "advertised envelope to 15 labeled graph_mapping documents."
        ),
        next_action="Keep bulk onboarding blocked until measured throughput exists.",
        sizing_ladder=SIZING_LADDER_GRAPH,
        managed_only=False,
    ),
    Packet3Handoff(
        item_id="managed_ec2_cdn_kms",
        acceptance="P09-03-B",
        classification="Not Run",
        owner="Phase 10",
        reason="Packet 3 does not infer managed EC2, CDN, or KMS proof from local Docker.",
        next_action="Phase 10 extends latency/restore under managed topology.",
        sizing_ladder="Do not infer managed success from local NCPU/mem.",
        managed_only=True,
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


def suites_for_mode(mode: Packet3Mode) -> tuple[Packet3Suite, ...]:
    """Return suites collected for one Packet 3 execution mode.

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


def pytest_command(suite: Packet3Suite, report: Path) -> list[str]:
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
        Phase09Packet3GateError: If the report is missing or malformed.
    """

    try:
        root = ET.parse(report).getroot()  # noqa: S314 - local pytest output only.
    except (ET.ParseError, OSError) as exc:
        raise Phase09Packet3GateError("Packet 3 pytest report is unavailable") from exc
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    if not suites:
        raise Phase09Packet3GateError("Packet 3 pytest report contains no test suite")

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


def assert_holdout_sealed(repo_root: Path) -> None:
    """Fail when holdout is open in settings or the Packet 2 corpus freeze.

    Args:
        repo_root: Repository root.

    Raises:
        Phase09Packet3GateError: If holdout is open or the corpus freeze is missing.
    """

    if HoldoutAccess.denied().allowed:
        raise Phase09Packet3GateError("holdout must remain HoldoutAccess.denied()")
    if HoldoutAccess.from_settings().allowed:
        raise Phase09Packet3GateError("SMART_RAG_HOLDOUT_ACCESS must not be true")
    path = repo_root / ARTIFACT_DIR / PACKET1_CORPUS_MANIFEST
    if not path.is_file():
        raise Phase09Packet3GateError("candidate-corpus-manifest.json is missing")
    payload = load_json_object(path)
    if payload.get("holdout_opened") is True:
        raise Phase09Packet3GateError("holdout must remain sealed for Packet 3")


def assert_packet2_corpus_identity(repo_root: Path) -> dict[str, str]:
    """Require Packet 2 reseed identity, not Packet 1 document ids.

    Args:
        repo_root: Repository root.

    Returns:
        Mapping of seeded case id to document id.

    Raises:
        Phase09Packet3GateError: If the exact-code document id drifted.
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
        raise Phase09Packet3GateError(
            "Packet 2 corpus identity drift for p4-exact_code-0003: "
            f"{actual} != {EXPECTED_EXACT_CODE_DOCUMENT_ID}"
        )
    return found


def assert_mock_model_mode(repo_root: Path) -> None:
    """Require the candidate freeze to remain mock-model.

    Args:
        repo_root: Repository root.

    Raises:
        Phase09Packet3GateError: If the freeze is missing or live-model.
    """

    path = repo_root / ARTIFACT_DIR / PACKET1_IDENTITY_NAME
    if not path.is_file():
        raise Phase09Packet3GateError("candidate-identity-freeze.json is missing")
    payload = load_json_object(path)
    if payload.get("mock_model_mode") is not True:
        raise Phase09Packet3GateError(
            "Packet 3 candidate profile must keep MOCK_MODEL_MODE=true"
        )
    if payload.get("app_env") != "local":
        raise Phase09Packet3GateError(
            "Packet 3 candidate profile must keep APP_ENV=local"
        )


def load_sizing_hardware(repo_root: Path) -> dict[str, object]:
    """Load Packet 1 Docker NCPU/memory and seed counts.

    Args:
        repo_root: Repository root.

    Returns:
        Hardware and seed-count mapping. Missing files yield empty defaults.

    Raises:
        Phase09Packet3GateError: If the sizing file exists but is not an object.
    """

    path = repo_root / ARTIFACT_DIR / PACKET1_SIZING_NAME
    if not path.is_file():
        return {
            "docker_ncpu": None,
            "docker_mem_bytes": None,
            "seeded_document_versions": None,
            "seeded_chunks": None,
            "local_candidate_not_full_envelope": True,
        }
    payload = load_json_object(path)
    return {
        "docker_ncpu": payload.get("docker_ncpu"),
        "docker_mem_bytes": payload.get("docker_mem_bytes"),
        "seeded_document_versions": payload.get("seeded_document_versions"),
        "seeded_chunks": payload.get("seeded_chunks"),
        "seeded_graph_eligible_versions": payload.get("seeded_graph_eligible_versions"),
        "local_candidate_not_full_envelope": payload.get(
            "local_candidate_not_full_envelope", True
        ),
        "reduced_graph_version_envelope": payload.get("reduced_graph_version_envelope"),
    }


def stale_phase4_sidecar_document_id(sidecar: Mapping[str, object]) -> str | None:
    """Return a sidecar document id when it disagrees with Packet 2 identity.

    Args:
        sidecar: Parsed gold-id sidecar JSON.

    Returns:
        The stale exact-code document id, or ``None`` when the sidecar matches
        Packet 2 or does not contain that case.
    """

    records = sidecar.get("records")
    if not isinstance(records, list):
        return None
    for item in cast(list[object], records):
        if not isinstance(item, dict):
            continue
        row = as_json_object(
            cast(dict[str, object], item), source="gold_id_map.records[]"
        )
        if row.get("case_id") != "p4-exact_code-0003":
            continue
        document_id = row.get("document_id")
        if (
            isinstance(document_id, str)
            and document_id != EXPECTED_EXACT_CODE_DOCUMENT_ID
        ):
            return document_id
    return None


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


def ceiling_payload() -> dict[str, object]:
    """Return signed deadline/call/tool ceilings from existing constants.

    Returns:
        JSON object comparing ``FAMILY_*`` maps to QT-DL-* / QT-MC-*.
    """

    families = {
        "hybrid": Phase6RouteFamily.HYBRID,
        "combined": Phase6RouteFamily.COMBINED,
        "structured_table": Phase6RouteFamily.STRUCTURED_TABLE,
        "composite": Phase6RouteFamily.COMPOSITE,
        "graph_inspection": Phase6RouteFamily.GRAPH_INSPECTION,
    }
    rows: list[dict[str, object]] = []
    expected_deadline = {
        "hybrid": 25,
        "combined": 45,
        "structured_table": 30,
        "composite": 50,
        "graph_inspection": 10,
    }
    expected_calls = {
        "hybrid": 7,
        "combined": 8,
        "structured_table": 6,
        "composite": 9,
        "graph_inspection": 3,
    }
    for name, family in families.items():
        rows.append(
            {
                "family": name,
                "deadline_seconds": FAMILY_DEADLINE_SECONDS[family],
                "deadline_target": expected_deadline[name],
                "deadline_passed": FAMILY_DEADLINE_SECONDS[family]
                == expected_deadline[name],
                "model_call_ceiling": FAMILY_MODEL_CALL_CEILING[family],
                "model_call_target": expected_calls[name],
                "model_call_passed": FAMILY_MODEL_CALL_CEILING[family]
                == expected_calls[name],
                "tool_ceiling": FAMILY_TOOL_CEILING[family],
            }
        )
    return {
        "recursion_limit": RECURSION_LIMIT,
        "recursion_target": 24,
        "bm25_survivor_cap": BM25_AUTHORIZED_SURVIVOR_CAP,
        "bm25_scan_cap": BM25_SCAN_ID_CAP,
        "families": rows,
        "duplicate_lightrag_keyword_extraction": False,
    }


def classify_target(
    spec: TargetSpec,
    *,
    measured: object,
    mock_model_mode: bool,
    sample_size: int | None,
    detail: str,
    passed: bool | None = None,
) -> dict[str, object]:
    """Classify one signed target without averaging ACL/citation failures.

    Args:
        spec: Signed QUALITY_TARGETS row.
        measured: Observed value or ``null``.
        mock_model_mode: Candidate mock-model flag.
        sample_size: Cases or tests behind the measurement.
        detail: Bounded evidence sentence.
        passed: Optional explicit pass/fail. ``None`` defers to handoff rules.

    Returns:
        JSON target row with Passed/Failed/Blocked/Not Run.
    """

    classification: Classification
    if spec.target_id == "QT-EVAL-001" and passed is False:
        classification = "Failed"
    elif spec.live_model_required and mock_model_mode and passed is not True:
        classification = "Not Run"
    elif spec.target_id in {"QT-CAP-001", "QT-BM25-002", "QT-GR-002"}:
        classification = "Not Run" if spec.target_id != "QT-GR-002" else "Blocked"
    elif passed is True:
        classification = "Passed"
    elif passed is False:
        classification = "Failed"
    else:
        classification = "Not Run"
    if spec.target_id == "QT-GR-002":
        classification = "Blocked"
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
        "qt_eval_006_live": False if spec.target_id.startswith("QT-EVAL-00") else None,
        "classification": classification,
        "detail": detail,
    }


def handoff_payloads() -> list[dict[str, object]]:
    """Serialize declared Packet 3 handoff rows.

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


def not_run_suite_payload(suite: Packet3Suite, *, detail: str) -> dict[str, object]:
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
    suite: Packet3Suite,
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


def schema_version() -> str:
    """Return the Packet 3 matrix artifact schema version.

    Returns:
        Stable schema identifier.
    """

    return PACKET3_MATRIX_SCHEMA_VERSION


def quality_schema_version() -> str:
    """Return the quality-report schema version."""

    return PACKET3_QUALITY_SCHEMA_VERSION


def latency_schema_version() -> str:
    """Return the latency-report schema version."""

    return PACKET3_LATENCY_SCHEMA_VERSION


def ledger_schema_version() -> str:
    """Return the cost-ledger schema version."""

    return PACKET3_LEDGER_SCHEMA_VERSION


def bm25_schema_version() -> str:
    """Return the BM25-report schema version."""

    return PACKET3_BM25_SCHEMA_VERSION


def graph_schema_version() -> str:
    """Return the graph-report schema version."""

    return PACKET3_GRAPH_SCHEMA_VERSION


def fetch_persist_mapping(
    connection: object,
    *,
    document_id: UUID,
    version_id: UUID,
) -> PersistMapping:
    """Load canonical chunk and table ids for one seeded version.

    Args:
        connection: Open ``psycopg`` connection.
        document_id: Packet 2 document UUID.
        version_id: Packet 2 version UUID.

    Returns:
        Persist mapping used by ``build_sidecar``. Tombstoned chunks are
        included so ACL-negative gold UUIDs remain mappable after the Packet 1
        ``deletion_pending`` drive.

    Side Effects:
        Reads ``app.document_chunks`` and ``app.document_tables``.
    """

    import psycopg

    postgres = cast("psycopg.Connection", connection)
    with postgres.cursor() as cursor:
        cursor.execute("SET ROLE postgres")
        cursor.execute(
            """
            SELECT id, raw_text
            FROM app.document_chunks
            WHERE version_id = %s
            ORDER BY chunk_index
            """,
            (version_id,),
        )
        chunk_rows = cursor.fetchall()
        cursor.execute(
            """
            SELECT id
            FROM app.document_tables
            WHERE version_id = %s
            ORDER BY table_name
            """,
            (version_id,),
        )
        table_rows = cursor.fetchall()
    chunk_texts = tuple(
        (UUID(str(row[0])), str(row[1])) for row in chunk_rows if row[0] is not None
    )
    table_ids = tuple(UUID(str(row[0])) for row in table_rows if row[0] is not None)
    return PersistMapping(
        document_id=document_id,
        version_id=version_id,
        chunk_texts=chunk_texts,
        table_ids=table_ids,
    )


def build_candidate_sidecar(
    connection: object,
    *,
    corpus_rows: Sequence[Mapping[str, object]],
) -> GoldIdSidecar:
    """Build a Packet 2-scoped gold sidecar from live canonical rows.

    The Phase 4 157-case sidecar is Packet 1 identity and must not be used.
    Graph-mapping rows are omitted because ranked-ID retrieve excludes that
    class; mapping/survival is measured by the graph suite instead.

    Args:
        connection: Open ``psycopg`` connection.
        corpus_rows: ``candidate-corpus-manifest.json`` rows.

    Returns:
        Sidecar covering the Packet 2 retrieve subset only.

    Raises:
        Phase09Packet3GateError: If a seeded retrieve case cannot be loaded.
    """

    from smart_rag_core.evaluation.loader import load_open_splits

    cases = {case.case_id: case for case in load_open_splits()}
    persist_index: dict[str, PersistMapping] = {}
    selected: list[EvaluationCase] = []
    seeded = frozenset(SEEDED_RETRIEVE_CASE_IDS)
    for raw in corpus_rows:
        row = as_json_object(raw, source="corpus.rows[]")
        case_id = row.get("case_id")
        document_raw = row.get("document_id")
        version_raw = row.get("version_id")
        if not isinstance(case_id, str) or case_id not in seeded:
            continue
        case = cases.get(case_id)
        if case is None:
            raise Phase09Packet3GateError(
                f"seeded case {case_id} missing from open splits"
            )
        if not isinstance(document_raw, str) or not isinstance(version_raw, str):
            raise Phase09Packet3GateError(
                f"seeded case {case_id} lacks document/version ids"
            )
        persist_index[case_id] = fetch_persist_mapping(
            connection,
            document_id=UUID(document_raw),
            version_id=UUID(version_raw),
        )
        selected.append(case)
    missing = sorted(seeded.difference(case.case_id for case in selected))
    if missing:
        raise Phase09Packet3GateError(
            "Packet 2 retrieve cases missing from corpus: " + ", ".join(missing)
        )
    sidecar = build_sidecar(selected, persist_index=persist_index)
    if sidecar.holdout_opened:
        raise Phase09Packet3GateError("candidate sidecar opened holdout")
    return sidecar


def measure_bm25_lag(connection: object) -> dict[str, object]:
    """Measure BM25 outbox lag on the Packet 2 seed, not a 1M envelope.

    Args:
        connection: Open ``psycopg`` connection.

    Returns:
        Lag sample with p50/p95 seconds and job counts. No secrets.
    """

    import psycopg

    postgres = cast("psycopg.Connection", connection)
    with postgres.cursor() as cursor:
        cursor.execute("SET ROLE postgres")
        cursor.execute(
            """
            SELECT
              EXTRACT(EPOCH FROM (updated_at - created_at))::float8,
              status::text
            FROM app.bm25_index_jobs
            """
        )
        rows = cursor.fetchall()
    durations = [float(row[0]) for row in rows if row[0] is not None]
    completed = [
        float(row[0]) for row in rows if row[1] == "completed" and row[0] is not None
    ]
    p50 = percentile(completed or durations, 0.50)
    p95 = percentile(completed or durations, 0.95)
    return {
        "job_count": len(rows),
        "completed_count": len(completed),
        "lag_p50_seconds": p50,
        "lag_p95_seconds": p95,
        "qt_bm25_003_seconds": QT_BM25_003_LAG_SECONDS,
        "qt_bm25_003_passed": p95 is not None and p95 < QT_BM25_003_LAG_SECONDS,
        "sample_is_seed_not_million_chunks": True,
        "qt_bm25_002_live": False,
    }


def measure_graph_snapshot(connection: object) -> dict[str, object]:
    """Read durable graph backlog/ETA/cost without inventing documents/hour.

    Args:
        connection: Open ``psycopg`` connection.

    Returns:
        GraphMetricsService snapshot plus Packet 8 envelope constants.
    """

    import psycopg

    from smart_rag_core.evaluation.graph_eval import (
        DEADLINE_CAP_DOCUMENTS,
        envelope_decision,
        fixture_coverage_slices,
        language_type_metrics,
        maintenance_reserve_usd,
    )
    from smart_rag_core.jobs.graph_metrics import GraphMetricsService
    from smart_rag_core.retrieval.graph_mapping import evaluate_coverage_gates

    postgres = cast("psycopg.Connection", connection)
    postgres.execute("SET ROLE app_worker")
    metrics = GraphMetricsService(postgres).collect()
    slices = fixture_coverage_slices()
    coverage_passed, coverage_reason = evaluate_coverage_gates(slices)
    language = [
        {
            "language": item.language,
            "object_type": item.object_type,
            "numerator": item.numerator,
            "denominator": item.denominator,
            "ratio": item.ratio,
            "gate_floor": item.gate_floor,
            "passed": item.passed,
            "source": item.source,
        }
        for item in language_type_metrics()
    ]
    envelope = envelope_decision(supported_documents=15)
    seven_day_ok = False
    if metrics.documents_per_hour and metrics.documents_per_hour > 0:
        hours_needed = 2000.0 / metrics.documents_per_hour
        seven_day_ok = hours_needed <= 7.0 * 24.0
    return {
        "pending_index_count": metrics.pending_index_count,
        "pending_maintenance_count": metrics.pending_maintenance_count,
        "oldest_pending_age_seconds": metrics.oldest_pending_age_seconds,
        "mapping_verified_count": metrics.mapping_verified_count,
        "documents_per_hour": metrics.documents_per_hour,
        "eta_seconds": metrics.eta_seconds,
        "eta_confidence": metrics.eta_confidence,
        "attempted_cost_usd": str(metrics.attempted_cost_usd),
        "settled_cost_usd": str(metrics.settled_cost_usd),
        "usd_note": "Mock-model seed; USD may be 0. This is not live extraction cost.",
        "bulk_window_active": metrics.bulk_window_active,
        "coverage_gates_passed": coverage_passed,
        "coverage_reason": coverage_reason,
        "language_metrics": language,
        "query_keyword_extract": 0,
        "duplicate_lightrag_keyword_extraction": False,
        "seven_day_rebuild_of_2k": seven_day_ok,
        "deadline_cap_documents": int(DEADLINE_CAP_DOCUMENTS),
        "supported_documents": envelope.supported_documents,
        "bulk_onboarding_blocked": envelope.bulk_onboarding_blocked,
        "maintenance_reserve_usd": maintenance_reserve_usd(
            measured_full_rebuild_cost_usd=None
        ),
        "measured_full_rebuild_cost_usd": None,
        "envelope_uncertainty": envelope.uncertainty,
        "qt_cap_005_p8": 15,
        "qt_gr_002_classification": "Blocked",
    }


def ranked_ids_eval_command(*, sidecar: Path, live: bool) -> list[str]:
    """Return the existing ranked-ID CLI argv for the Packet 2 7-case subset.

    Args:
        sidecar: Candidate gold-id sidecar path.
        live: When true, pass ``--live`` (Packet 8 overlay or ``PARADEDB_URL``).

    Returns:
        Argument vector excluding the Python executable.
    """

    command = [
        "scripts/eval_phase4_ranked_ids.py",
        "--split",
        "open",
        "--sidecar",
        str(sidecar),
    ]
    for case_id in SEEDED_RETRIEVE_CASE_IDS:
        command.extend(["--case-id", case_id])
    if live:
        command.append("--live")
    return command


def mock_recall_must_not_be_live(payload: Mapping[str, object]) -> bool:
    """Return whether a ranked-ID JSON payload wrongly claims live QT-EVAL-006.

    Args:
        payload: CLI JSON object.

    Returns:
        True when mock embeddings are labeled live.
    """

    embeddings = payload.get("embeddings")
    live_flag = payload.get("qt_eval_006_live")
    return embeddings == "mock" and live_flag is True


def cost_ledger_payload(
    *,
    ranked_ids: Mapping[str, object] | None,
    profile_model_calls: int,
    hardware: Mapping[str, object],
) -> dict[str, object]:
    """Build the mock-model call/token/cost ledger.

    Args:
        ranked_ids: Optional live ranked-ID JSON.
        profile_model_calls: Query-profile model calls (must stay 0 on corpus).
        hardware: Docker NCPU/mem snapshot.

    Returns:
        Ledger with USD 0 under mock mode.
    """

    rerank_calls = 0
    embedding_cost = None
    if ranked_ids is not None:
        raw_cost = ranked_ids.get("cost")
        if isinstance(raw_cost, (int, float)):
            embedding_cost = float(raw_cost)
    return {
        "schema_version": PACKET3_LEDGER_SCHEMA_VERSION,
        "mock_model_mode": True,
        "usd_currency": "USD",
        "usd_total": 0.0 if embedding_cost is None else embedding_cost,
        "usd_note": (
            "MOCK_MODEL_MODE=true. Mock gateway estimated_cost_usd is 0. "
            "Calls are still counted. This is not live OpenAI spend."
        ),
        "profile_model_calls": profile_model_calls,
        "rerank_call_count_note": (
            "Identity/mock rerank. Live OpenAI Responses rerank was not run."
        ),
        "rerank_call_count": rerank_calls,
        "tool_executions": 0,
        "hardware": dict(hardware),
        "ceilings": ceiling_payload(),
    }


def parse_mode(value: str) -> Packet3Mode:
    """Validate the Packet 3 execution mode.

    Args:
        value: CLI mode string.

    Returns:
        Typed mode.

    Raises:
        ValueError: If the mode is unknown.
    """

    if value == "candidate":
        return "candidate"
    if value == "overlay":
        return "overlay"
    if value == "all":
        return "all"
    raise ValueError(f"unknown Packet 3 mode: {value}")


def load_packet1_images(repo_root: Path) -> dict[str, str]:
    """Reuse Packet 2 image-Id freeze checks.

    Args:
        repo_root: Repository root.

    Returns:
        Service name to image Id mapping.

    Raises:
        Phase09Packet3GateError: If Packet 1 image Ids drifted.
    """

    try:
        return load_packet1_image_ids(repo_root)
    except Exception as exc:
        raise Phase09Packet3GateError(str(exc)) from exc


def expected_image_ids() -> dict[str, str]:
    """Return the frozen Packet 1 image Ids.

    Returns:
        Service to image Id mapping.
    """

    return dict(PACKET1_EXPECTED_IMAGE_IDS)


def artifact_paths(repo_root: Path) -> dict[str, Path]:
    """Return Packet 3 artifact destinations.

    Args:
        repo_root: Repository root.

    Returns:
        Logical name to path mapping under ``docs/deployment/phase-09/``.
    """

    directory = repo_root / ARTIFACT_DIR
    return {
        "matrix": directory / PACKET3_MATRIX_NAME,
        "quality": directory / PACKET3_QUALITY_NAME,
        "latency": directory / PACKET3_LATENCY_NAME,
        "ledger": directory / PACKET3_LEDGER_NAME,
        "bm25": directory / PACKET3_BM25_NAME,
        "graph": directory / PACKET3_GRAPH_NAME,
        "sidecar": directory / PACKET3_SIDECAR_NAME,
    }


def decode_eval_json(stdout: str) -> dict[str, object]:
    """Parse the first JSON object from an eval script stdout.

    Args:
        stdout: Captured standard output.

    Returns:
        JSON object.

    Raises:
        Phase09Packet3GateError: If stdout is not a JSON object.
    """

    text = stdout.strip()
    if not text:
        raise Phase09Packet3GateError("eval script produced empty stdout")
    decoder = json.JSONDecoder()
    payload, _index = decoder.raw_decode(text)
    return as_json_object(payload, source="eval.stdout")

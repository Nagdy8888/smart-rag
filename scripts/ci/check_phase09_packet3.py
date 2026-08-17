"""Fail when Phase 9 Packet 3 mandatory measurements collect zero cases."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from smart_rag_core.evaluation.coverage_eval import (
    class_metrics,
    score_case,
    weighted_loss,
)
from smart_rag_core.evaluation.holdout import HoldoutAccess
from smart_rag_core.evaluation.loader import load_qualification_cases
from smart_rag_core.evaluation.phase6_registry import qt_eval_009_status
from smart_rag_core.query_profile.metrics import ProfileEvalReport
from smart_rag_core.query_profile.runner import evaluate_open_splits
from smart_rag_core.release.constants import ARTIFACT_DIR
from smart_rag_core.release.io import (
    as_json_list,
    as_json_object,
    dump_canonical_json,
    load_json_object,
)
from smart_rag_core.release.packet3 import (
    PACKET3_BM25_NAME,
    PACKET3_GRAPH_NAME,
    PACKET3_LATENCY_NAME,
    PACKET3_LEDGER_NAME,
    PACKET3_MATRIX_NAME,
    PACKET3_QUALITY_NAME,
    PACKET3_SIDECAR_NAME,
    PYTEST_SUITES,
    QT_LAT_001_MS,
    SEEDED_RETRIEVE_CASE_IDS,
    TARGET_SPECS,
    Packet3Mode,
    Packet3Suite,
    Phase09Packet3GateError,
    artifact_paths,
    assert_holdout_sealed,
    assert_mock_model_mode,
    assert_packet2_corpus_identity,
    bm25_schema_version,
    build_candidate_sidecar,
    ceiling_payload,
    classify_suite_counts,
    classify_target,
    cost_ledger_payload,
    decode_eval_json,
    executed_suite_payload,
    expected_image_ids,
    graph_schema_version,
    handoff_payloads,
    junit_counts,
    latency_schema_version,
    load_packet1_images,
    load_sizing_hardware,
    measure_bm25_lag,
    measure_graph_snapshot,
    merge_suite_rows,
    missing_pytest_files,
    mock_recall_must_not_be_live,
    not_run_suite_payload,
    parse_mode,
    pytest_command,
    quality_schema_version,
    ranked_ids_eval_command,
    schema_version,
    stale_phase4_sidecar_document_id,
    suite_failure_detail,
    suites_for_mode,
)
from smart_rag_core.settings.base import get_process_environ

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_PATH = REPO_ROOT / ARTIFACT_DIR / PACKET3_MATRIX_NAME
DEFAULT_SUPABASE = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"


def _run_suite(suite: Packet3Suite) -> dict[str, object]:
    """Execute one fail-closed pytest suite and return its matrix row.

    Args:
        suite: Suite to run.

    Returns:
        JSON-object suite row.

    Raises:
        Phase09Packet3GateError: If JUnit output is missing.

    Side Effects:
        Runs pytest from the repository root.
    """

    with tempfile.TemporaryDirectory(prefix="smart-rag-phase09-p3-") as directory:
        report = Path(directory) / "junit.xml"
        completed = subprocess.run(  # noqa: S603
            [sys.executable, "-m", "pytest", *pytest_command(suite, report)],
            cwd=REPO_ROOT,
            check=False,
        )
        counts = junit_counts(report)
    classification = classify_suite_counts(
        counts,
        returncode=completed.returncode,
        fail_on_skip=suite.fail_on_skip,
    )
    detail = suite_failure_detail(
        counts,
        returncode=completed.returncode,
        fail_on_skip=suite.fail_on_skip,
    )
    print(
        f"phase09_packet3_{suite.suite_id} "
        f"tests={counts.tests} failures={counts.failures} "
        f"errors={counts.errors} skipped={counts.skipped} "
        f"classification={classification}"
    )
    return executed_suite_payload(
        suite,
        counts,
        returncode=completed.returncode,
        classification=classification,
        detail=detail,
    )


def _mode_rows(
    mode: Packet3Mode,
    *,
    emit_unselected: bool,
) -> tuple[list[dict[str, object]], list[str]]:
    """Run selected suites and optionally emit Not Run rows for the others.

    Args:
        mode: Execution mode.
        emit_unselected: When true, unselected suites are recorded as Not Run.

    Returns:
        Suite rows and fail-closed reasons for executed suites that did not pass.
    """

    selected = {suite.suite_id for suite in suites_for_mode(mode)}
    rows: list[dict[str, object]] = []
    failures: list[str] = []
    for suite in PYTEST_SUITES:
        if suite.suite_id not in selected:
            if emit_unselected:
                detail = (
                    "overlay host ports required; run after attaching "
                    "docker-compose.packet8.yml, then detach candidate compose"
                    if suite.overlay_required
                    else f"not selected in mode={mode}"
                )
                rows.append(not_run_suite_payload(suite, detail=detail))
            continue
        row = _run_suite(suite)
        rows.append(row)
        if row["classification"] != "Passed":
            failures.append(f"{suite.suite_id}: {row['detail']}")
    return rows, failures


def _supabase_connection() -> object | None:
    """Open local Supabase when reachable.

    Returns:
        ``psycopg`` connection or ``None``.
    """

    import psycopg

    url = get_process_environ("SUPABASE_DB_URL") or DEFAULT_SUPABASE
    try:
        connection = psycopg.connect(url, connect_timeout=8)
    except Exception:
        return None
    return connection


def _profile_payload() -> dict[str, object]:
    """Score open-split query-profile gates without opening holdout.

    Returns:
        Development and qualification JSON.
    """

    development, qualification = evaluate_open_splits()

    def serialize(report: ProfileEvalReport) -> dict[str, object]:
        """Serialize one profile report."""

        scores: list[dict[str, object]] = [
            {
                "name": item.name,
                "value": round(item.value, 6),
                "threshold": item.threshold,
                "passed": item.passed,
            }
            for item in report.scores
        ]
        extra: list[dict[str, object]] = [
            {
                "name": item.name,
                "value": round(item.value, 6),
                "threshold": item.threshold,
                "passed": item.passed,
            }
            for item in report.extra
        ]
        return {
            "split": report.split,
            "case_count": report.case_count,
            "model_calls": report.model_calls,
            "passed": report.passed,
            "scores": scores,
            "extra": extra,
        }

    return {
        "development": serialize(development),
        "qualification": serialize(qualification),
        "holdout_opened": False,
    }


def _coverage_payload() -> dict[str, object]:
    """Confirm frozen coverage thresholds on qualification without rewriting docs.

    Returns:
        Qualification coverage JSON. Holdout stays sealed.
    """

    cases = load_qualification_cases()
    outcomes = tuple(score_case(case) for case in cases)
    metrics = class_metrics(outcomes)
    false_supported = sum(item.false_supported for item in outcomes)
    return {
        "split": "qualification",
        "case_count": len(cases),
        "false_supported": false_supported,
        "weighted_loss": weighted_loss(outcomes),
        "passed": false_supported == 0,
        "class_metrics": {
            name: {
                "n": row["n"],
                "false_supported": int(row["false_supported"]),
                "unnecessary_refusal": int(row["unnecessary_refusal"]),
                "weighted_loss": float(row["weighted_loss"]),
            }
            for name, row in metrics.items()
        },
        "holdout_opened": False,
        "retuned": False,
    }


def _write_sidecar(connection: object) -> dict[str, object]:
    """Write the Packet 2-scoped gold sidecar and return its summary.

    Args:
        connection: Open Supabase connection.

    Returns:
        Sidecar summary including unmapped flag.

    Side Effects:
        Overwrites ``docs/deployment/phase-09/candidate-gold-id-map.json``.
    """

    corpus_path = REPO_ROOT / ARTIFACT_DIR / "candidate-corpus-manifest.json"
    corpus = load_json_object(corpus_path)
    rows = as_json_list(corpus.get("rows"), source="corpus.rows")
    corpus_rows = [
        as_json_object(cast(dict[str, object], item), source="corpus.rows[]")
        for item in rows
        if isinstance(item, dict)
    ]
    sidecar = build_candidate_sidecar(connection, corpus_rows=corpus_rows)
    paths = artifact_paths(REPO_ROOT)
    dump_canonical_json(
        as_json_object(sidecar.model_dump(mode="json")), paths["sidecar"]
    )
    from smart_rag_core.evaluation.ranked_ids import sidecar_has_unmapped_chunks

    unmapped = sidecar_has_unmapped_chunks(sidecar)
    return {
        "path": str(paths["sidecar"].relative_to(REPO_ROOT)).replace("\\", "/"),
        "case_count": sidecar.case_count,
        "holdout_opened": False,
        "sidecar_unmapped": unmapped,
        "sidecar_sha256": sidecar.sidecar_sha256,
        "packet2_identity": True,
    }


def _run_ranked_ids_live(sidecar_path: Path) -> dict[str, object]:
    """Run the existing ranked-ID CLI against the Packet 2 7-case subset.

    Args:
        sidecar_path: Candidate gold-id sidecar.

    Returns:
        Parsed CLI JSON.

    Side Effects:
        Spawns ``scripts/eval_phase4_ranked_ids.py --live``.
    """

    command = [
        sys.executable,
        *ranked_ids_eval_command(sidecar=sidecar_path, live=True),
    ]
    completed = subprocess.run(  # noqa: S603
        command,
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    print(
        "phase09_packet3_ranked_ids_live "
        f"returncode={completed.returncode} stderr={completed.stderr[-400:]}"
    )
    if not completed.stdout.strip():
        raise Phase09Packet3GateError("ranked-id eval produced empty stdout")
    payload = decode_eval_json(completed.stdout)
    payload["returncode"] = completed.returncode
    if mock_recall_must_not_be_live(payload):
        raise Phase09Packet3GateError(
            "mock embeddings labeled qt_eval_006_live=true; refuse the claim"
        )
    return payload


def _target_rows(
    *,
    mock_model_mode: bool,
    suite_rows: Sequence[Mapping[str, object]],
    ranked_ids: Mapping[str, object] | None,
    profile: Mapping[str, object] | None,
    coverage: Mapping[str, object] | None,
    bm25_lag: Mapping[str, object] | None,
    graph: Mapping[str, object] | None,
) -> list[dict[str, object]]:
    """Compare every Packet 3 signed target to measured evidence.

    Args:
        mock_model_mode: Candidate mock flag.
        suite_rows: Pytest matrix rows.
        ranked_ids: Optional live ranked-ID JSON.
        profile: Optional query-profile JSON.
        coverage: Optional coverage JSON.
        bm25_lag: Optional lag JSON.
        graph: Optional graph snapshot.

    Returns:
        Target comparison rows.
    """

    suites_by_id = {
        str(row.get("suite_id")): row
        for row in suite_rows
        if isinstance(row.get("suite_id"), str)
    }
    routing_passed = (
        suites_by_id.get("quality_routing_profile", {}).get("classification")
        == "Passed"
    )
    citation_suite = (
        suites_by_id.get("quality_citations_coverage_table", {}).get("classification")
        == "Passed"
    )
    combined_suite = (
        suites_by_id.get("quality_combined_fixture_ablation", {}).get("classification")
        == "Passed"
    )
    ceiling_suite = (
        suites_by_id.get("latency_call_ceilings", {}).get("classification") == "Passed"
    )
    bm25_suite = (
        suites_by_id.get("bm25_caps_outage_arabic", {}).get("classification")
        == "Passed"
    )
    overlay_bm25 = suites_by_id.get("overlay_bm25_typed_rebuild", {}).get(
        "classification"
    )
    graph_suite = (
        suites_by_id.get("graph_mapping_survival_writer", {}).get("classification")
        == "Passed"
    )
    acl_leaks = None
    locator = None
    recall_10 = None
    exact_5 = None
    alias_10 = None
    first_p95 = None
    sample = None
    if ranked_ids is not None:
        acl_leaks = ranked_ids.get("acl_leak_count")
        locator = ranked_ids.get("locator_correctness")
        recall_10 = ranked_ids.get("recall_at_10")
        exact_5 = ranked_ids.get("exact_code_recall_at_5")
        alias_10 = ranked_ids.get("alias_recall_at_10")
        first_p95 = ranked_ids.get("first_evidence_p95_ms")
        sample = ranked_ids.get("case_count")
    rows: list[dict[str, object]] = []
    for spec in TARGET_SPECS:
        if spec.target_id == "QT-EVAL-001":
            leaked = acl_leaks not in {0, None} or (
                isinstance(acl_leaks, int) and acl_leaks > 0
            )
            passed = citation_suite and not leaked and (acl_leaks in {0, None})
            if ranked_ids is not None:
                passed = citation_suite and acl_leaks == 0
            rows.append(
                classify_target(
                    spec,
                    measured=acl_leaks
                    if acl_leaks is not None
                    else "fixture_zero_leaks",
                    mock_model_mode=mock_model_mode,
                    sample_size=sample if isinstance(sample, int) else None,
                    detail=(
                        "Zero ACL leaks on ranked-ID fixtures and Packet 2 identity "
                        "suite. Live 7-case subset scored when overlay retrieve ran."
                    ),
                    passed=bool(passed),
                )
            )
            continue
        if spec.target_id == "QT-EVAL-002":
            locator_ok = isinstance(locator, (int, float)) and float(locator) >= 0.98
            rows.append(
                classify_target(
                    spec,
                    measured=locator,
                    mock_model_mode=mock_model_mode,
                    sample_size=sample if isinstance(sample, int) else None,
                    detail=(
                        "Locator correctness from ranked-ID evidence units, not "
                        "answer-assembler completeness. Verifier unit suite "
                        f"classification={suites_by_id.get('quality_citations_coverage_table', {}).get('classification')}."
                    ),
                    passed=locator_ok if ranked_ids is not None else citation_suite,
                )
            )
            continue
        if spec.target_id in {"QT-EVAL-003", "QT-EVAL-004"}:
            rows.append(
                classify_target(
                    spec,
                    measured=None,
                    mock_model_mode=mock_model_mode,
                    sample_size=None,
                    detail=(
                        "Answer completeness/faithfulness needs live answers. "
                        "Verifier fixtures passed as contract proof only."
                    ),
                    passed=None,
                )
            )
            continue
        if spec.target_id == "QT-EVAL-005":
            profile_ok = False
            if profile is not None:
                development = as_json_object(
                    profile.get("development"), source="profile.development"
                )
                qualification = as_json_object(
                    profile.get("qualification"), source="profile.qualification"
                )
                profile_ok = bool(
                    development.get("passed") and qualification.get("passed")
                )
            rows.append(
                classify_target(
                    spec,
                    measured="routing_matrix_and_profile",
                    mock_model_mode=mock_model_mode,
                    sample_size=None,
                    detail="Routing matrix plus open-split profile gates. Holdout sealed.",
                    passed=routing_passed and profile_ok,
                )
            )
            continue
        if spec.target_id in {"QT-EVAL-006", "QT-EVAL-007", "QT-EVAL-008"}:
            measured = {
                "QT-EVAL-006": recall_10,
                "QT-EVAL-007": exact_5,
                "QT-EVAL-008": alias_10,
            }[spec.target_id]
            rows.append(
                classify_target(
                    spec,
                    measured=measured,
                    mock_model_mode=mock_model_mode,
                    sample_size=sample if isinstance(sample, int) else None,
                    detail=(
                        "Mock embeddings. qt_eval_006_live must stay false. "
                        "Signed live Recall@K is Not Run under MOCK_MODEL_MODE."
                    ),
                    passed=None,
                )
            )
            continue
        if spec.target_id == "QT-EVAL-009":
            rows.append(
                classify_target(
                    spec,
                    measured=None,
                    mock_model_mode=mock_model_mode,
                    sample_size=3 if combined_suite else None,
                    detail=(
                        f"phase6_registry status={qt_eval_009_status()}. "
                        "Fixture ablation is not live Combined gain."
                    ),
                    passed=None,
                )
            )
            continue
        if spec.target_id == "QT-LAT-001":
            lat_ok = (
                isinstance(first_p95, (int, float))
                and float(first_p95) <= QT_LAT_001_MS
            )
            rows.append(
                classify_target(
                    spec,
                    measured=first_p95,
                    mock_model_mode=mock_model_mode,
                    sample_size=sample if isinstance(sample, int) else None,
                    detail=(
                        "Retrieve first_evidence_ms p95 on the Packet 2 subset. "
                        "Not first answer token."
                    ),
                    passed=lat_ok if ranked_ids is not None else None,
                )
            )
            continue
        if spec.target_id.startswith("QT-LAT-"):
            rows.append(
                classify_target(
                    spec,
                    measured=None,
                    mock_model_mode=mock_model_mode,
                    sample_size=None,
                    detail="Stream first-token/completion p95 is Packet 4. Not inferred.",
                    passed=None,
                )
            )
            continue
        if spec.target_id.startswith("QT-DL-") or spec.target_id.startswith("QT-MC-"):
            rows.append(
                classify_target(
                    spec,
                    measured="ceiling_constants",
                    mock_model_mode=mock_model_mode,
                    sample_size=None,
                    detail="Server-owned FAMILY_* ceilings match QUALITY_TARGETS.",
                    passed=ceiling_suite,
                )
            )
            continue
        if spec.target_id == "QT-BM25-001":
            overlay_ok = overlay_bm25 in {"Passed", None, "Not Run"}
            rows.append(
                classify_target(
                    spec,
                    measured="paradedb_exec_and_arabic_parity",
                    mock_model_mode=mock_model_mode,
                    sample_size=None,
                    detail="Unicode BM25 contract plus byte-identical arabic_norm_v1.",
                    passed=bm25_suite and overlay_ok is not False,
                )
            )
            continue
        if spec.target_id == "QT-BM25-003":
            p95 = bm25_lag.get("lag_p95_seconds") if bm25_lag else None
            passed = bool(bm25_lag and bm25_lag.get("qt_bm25_003_passed"))
            rows.append(
                classify_target(
                    spec,
                    measured=p95,
                    mock_model_mode=mock_model_mode,
                    sample_size=_optional_int(
                        bm25_lag.get("job_count") if bm25_lag else None
                    ),
                    detail="Seed outbox lag, not the 1,000,000-chunk envelope.",
                    passed=passed if bm25_lag else None,
                )
            )
            continue
        if spec.target_id == "QT-BM25-004":
            rows.append(
                classify_target(
                    spec,
                    measured="recheck_drops_stale_unauthorized",
                    mock_model_mode=mock_model_mode,
                    sample_size=None,
                    detail="Batched Supabase recheck tests. ACL safety is immediate.",
                    passed=bm25_suite or citation_suite,
                )
            )
            continue
        if spec.target_id == "QT-GR-001":
            dph = graph.get("documents_per_hour") if graph else None
            confidence = graph.get("eta_confidence") if graph else "insufficient-sample"
            rows.append(
                classify_target(
                    spec,
                    measured=dph,
                    mock_model_mode=mock_model_mode,
                    sample_size=_optional_int(
                        graph.get("mapping_verified_count") if graph else None
                    ),
                    detail=(
                        f"Durable GraphMetricsService eta_confidence={confidence}. "
                        "Do not invent documents/hour."
                    ),
                    passed=graph_suite if confidence == "measured" else None,
                )
            )
            continue
        if spec.target_id == "QT-GR-003":
            rows.append(
                classify_target(
                    spec,
                    measured="resolver_acl_fixtures",
                    mock_model_mode=mock_model_mode,
                    sample_size=None,
                    detail="Canonical resolver ACL/deletion fixtures. Live SLA unverified.",
                    passed=graph_suite,
                )
            )
            continue
        rows.append(
            classify_target(
                spec,
                measured=None,
                mock_model_mode=mock_model_mode,
                sample_size=None,
                detail="See Packet 3 handoffs and sizing ladder.",
                passed=None,
            )
        )
    return rows


def _write_reports(
    *,
    mode: Packet3Mode,
    image_ids: dict[str, str],
    suite_rows: list[dict[str, object]],
    hardware: dict[str, object],
    profile: dict[str, object] | None,
    coverage: dict[str, object] | None,
    sidecar: dict[str, object] | None,
    ranked_ids: dict[str, object] | None,
    bm25_lag: dict[str, object] | None,
    graph: dict[str, object] | None,
    merge: bool,
) -> None:
    """Write Packet 3 machine-readable reports.

    Args:
        mode: Execution mode recorded on this write.
        image_ids: Packet 1 service image Ids.
        suite_rows: Suite rows from this run.
        hardware: Docker NCPU/mem snapshot.
        profile: Optional query-profile JSON.
        coverage: Optional coverage JSON.
        sidecar: Optional sidecar summary.
        ranked_ids: Optional live ranked-ID JSON.
        bm25_lag: Optional lag JSON.
        graph: Optional graph snapshot.
        merge: When true, replace matching ``suite_id`` rows in an existing file.

    Side Effects:
        Overwrites Packet 3 JSON artifacts under ``docs/deployment/phase-09/``.
    """

    existing_suites: list[dict[str, object]] = []
    existing_commands: list[object] = []
    if merge and ARTIFACT_PATH.is_file():
        previous = load_json_object(ARTIFACT_PATH)
        existing_suites = [
            as_json_object(item, source="packet3.suites[]")
            for item in as_json_list(previous.get("suites"), source="packet3.suites")
        ]
        raw_commands = previous.get("commands")
        if raw_commands is not None:
            existing_commands = as_json_list(raw_commands, source="packet3.commands")
    suites = merge_suite_rows(existing_suites, suite_rows)
    targets = _target_rows(
        mock_model_mode=True,
        suite_rows=suites,
        ranked_ids=ranked_ids,
        profile=profile,
        coverage=coverage,
        bm25_lag=bm25_lag,
        graph=graph,
    )
    latency = {
        "schema_version": latency_schema_version(),
        "hardware": hardware,
        "qt_lat_001_ms": QT_LAT_001_MS,
        "first_evidence_p50_ms": None,
        "first_evidence_p95_ms": ranked_ids.get("first_evidence_p95_ms")
        if ranked_ids
        else None,
        "first_token_p50_ms": None,
        "first_token_p95_ms": None,
        "completion_p50_ms": None,
        "completion_p95_ms": None,
        "sample_size": ranked_ids.get("case_count") if ranked_ids else 0,
        "mock_model_mode": True,
        "note": (
            "first_evidence_p95_ms comes from the existing ranked-ID CLI. "
            "That CLI does not emit p50; p50 is not invented from p95. "
            "first-token/completion stream percentiles are Packet 4. "
            "Deadlines compared via ceiling constants."
        ),
        "ceilings": ceiling_payload(),
        "deadline_exhaustion_route": "verified partial or insufficient evidence",
    }
    quality = {
        "schema_version": quality_schema_version(),
        "holdout_opened": False,
        "mock_model_mode": True,
        "qt_eval_006_live": False,
        "seeded_retrieve_case_ids": list(SEEDED_RETRIEVE_CASE_IDS),
        "hardware": hardware,
        "query_profile": profile,
        "coverage_qualification": coverage,
        "ranked_ids": ranked_ids,
        "sidecar": sidecar,
        "combined_gain_fixture_pp": 200.0 / 3.0,
        "combined_gain_live_status": qt_eval_009_status(),
        "duplicate_lightrag_keyword_extraction": False,
        "targets": targets,
    }
    bm25 = {
        "schema_version": bm25_schema_version(),
        "unicode_tokenizer": "pdb.unicode_words",
        "arabic_normalization": "arabic_norm_v1",
        "survivor_cap": 75,
        "scan_cap": 300,
        "typed_query": overlay_status(suites, "overlay_bm25_typed_rebuild"),
        "lag": bm25_lag,
        "outage_degrades_to_dense_term": True,
        "rebuild_1m_chunks": "Not Run",
        "hardware": hardware,
        "sample_is_seed_not_million_chunks": True,
    }
    graph_report = {
        "schema_version": graph_schema_version(),
        "snapshot": graph,
        "concurrency_one_writer": True,
        "seven_day_2k_feasibility": False,
        "qt_cap_005_p8": 15,
        "bulk_onboarding_blocked": True,
        "duplicate_lightrag_keyword_extraction": False,
        "hardware": hardware,
        "phase5_freeze_rewritten": False,
    }
    ledger = cost_ledger_payload(
        ranked_ids=ranked_ids,
        profile_model_calls=_profile_calls(profile),
        hardware=hardware,
    )
    paths = artifact_paths(REPO_ROOT)
    dump_canonical_json(quality, paths["quality"])
    dump_canonical_json(latency, paths["latency"])
    dump_canonical_json(ledger, paths["ledger"])
    dump_canonical_json(bm25, paths["bm25"])
    dump_canonical_json(graph_report, paths["graph"])
    payload: dict[str, object] = {
        "schema_version": schema_version(),
        "requirement_id": "P09-03",
        "mode": "all" if merge else mode,
        "holdout_opened": False,
        "mock_model_mode": True,
        "qt_eval_006_live": False,
        "compose_file": "docker-compose.yml",
        "overlay_file_is_candidate": False,
        "candidate_image_ids": image_ids,
        "hardware": hardware,
        "suites": suites,
        "handoffs": handoff_payloads(),
        "targets": targets,
        "commands": existing_commands,
        "artifacts": {
            "quality": PACKET3_QUALITY_NAME,
            "latency": PACKET3_LATENCY_NAME,
            "ledger": PACKET3_LEDGER_NAME,
            "bm25": PACKET3_BM25_NAME,
            "graph": PACKET3_GRAPH_NAME,
            "sidecar": PACKET3_SIDECAR_NAME,
        },
    }
    dump_canonical_json(payload, ARTIFACT_PATH)


def _optional_int(value: object) -> int | None:
    """Return ``value`` when it is an int.

    Args:
        value: JSON or mapping value.

    Returns:
        Integer sample size or ``None``.
    """

    return value if isinstance(value, int) else None


def overlay_status(suites: Sequence[Mapping[str, object]], suite_id: str) -> object:
    """Return one suite classification.

    Args:
        suites: Matrix rows.
        suite_id: Suite identifier.

    Returns:
        Classification string or ``Not Run``.
    """

    for row in suites:
        if row.get("suite_id") == suite_id:
            return row.get("classification")
    return "Not Run"


def _profile_calls(profile: Mapping[str, object] | None) -> int:
    """Sum query-profile model calls across open splits.

    Args:
        profile: Optional profile JSON.

    Returns:
        Call count. Corpus path should stay 0.
    """

    if profile is None:
        return 0
    total = 0
    for key in ("development", "qualification"):
        raw = profile.get(key)
        if isinstance(raw, dict):
            calls = cast(dict[str, object], raw).get("model_calls")
            if isinstance(calls, int):
                total += calls
    return total


def main(argv: list[str] | None = None) -> int:
    """Run Packet 3 measurements and reject zero collection.

    Args:
        argv: Optional argument vector excluding the program name.

    Returns:
        ``0`` when selected suites collected tests and none failed.
    """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        default="candidate",
        choices=("candidate", "overlay", "all"),
        help=(
            "candidate uses unpublished ParadeDB via compose exec; overlay "
            "requires docker-compose.packet8.yml already attached for host BM25 "
            "and live ranked-ID retrieve."
        ),
    )
    parser.add_argument(
        "--merge-artifact",
        action="store_true",
        help="Merge suite rows into the existing Packet 3 matrix artifact.",
    )
    parsed = parser.parse_args(argv)
    mode = parse_mode(cast(str, parsed.mode))
    try:
        if HoldoutAccess.denied().allowed:
            raise Phase09Packet3GateError("holdout must remain sealed")
        missing = missing_pytest_files(REPO_ROOT)
        if missing:
            raise Phase09Packet3GateError(
                "Packet 3 mapped pytest files are missing: " + ", ".join(missing)
            )
        assert_holdout_sealed(REPO_ROOT)
        assert_mock_model_mode(REPO_ROOT)
        assert_packet2_corpus_identity(REPO_ROOT)
        image_ids = load_packet1_images(REPO_ROOT)
        if image_ids != expected_image_ids() and set(expected_image_ids()) - set(
            image_ids
        ):
            raise Phase09Packet3GateError("Packet 1 image Ids incomplete")
        stale_sidecar = (
            REPO_ROOT / "tests/fixtures/evaluation/phase4/runtime/gold_id_map.json"
        )
        if stale_sidecar.is_file():
            stale = stale_phase4_sidecar_document_id(load_json_object(stale_sidecar))
            if stale is not None:
                print(
                    "phase09_packet3_stale_phase4_sidecar "
                    f"document_id={stale} unused_for_packet3"
                )
        hardware = load_sizing_hardware(REPO_ROOT)
        suite_rows, failures = _mode_rows(
            mode, emit_unselected=not parsed.merge_artifact
        )
        profile: dict[str, object] | None = None
        coverage: dict[str, object] | None = None
        sidecar_summary: dict[str, object] | None = None
        ranked_ids: dict[str, object] | None = None
        bm25_lag: dict[str, object] | None = None
        graph: dict[str, object] | None = None
        if parsed.merge_artifact:
            quality_path = artifact_paths(REPO_ROOT)["quality"]
            if quality_path.is_file():
                previous_quality = load_json_object(quality_path)
                raw_profile = previous_quality.get("query_profile")
                raw_coverage = previous_quality.get("coverage_qualification")
                raw_sidecar = previous_quality.get("sidecar")
                raw_ranked = previous_quality.get("ranked_ids")
                if isinstance(raw_profile, dict):
                    profile = as_json_object(
                        cast(dict[str, object], raw_profile),
                        source="quality.query_profile",
                    )
                if isinstance(raw_coverage, dict):
                    coverage = as_json_object(
                        cast(dict[str, object], raw_coverage),
                        source="quality.coverage_qualification",
                    )
                if isinstance(raw_sidecar, dict):
                    sidecar_summary = as_json_object(
                        cast(dict[str, object], raw_sidecar),
                        source="quality.sidecar",
                    )
                if isinstance(raw_ranked, dict):
                    ranked_ids = as_json_object(
                        cast(dict[str, object], raw_ranked),
                        source="quality.ranked_ids",
                    )
            bm25_path = artifact_paths(REPO_ROOT)["bm25"]
            if bm25_path.is_file():
                previous_bm25 = load_json_object(bm25_path)
                raw_lag = previous_bm25.get("lag")
                if isinstance(raw_lag, dict):
                    bm25_lag = as_json_object(
                        cast(dict[str, object], raw_lag), source="bm25.lag"
                    )
            graph_path = artifact_paths(REPO_ROOT)["graph"]
            if graph_path.is_file():
                previous_graph = load_json_object(graph_path)
                raw_snapshot = previous_graph.get("snapshot")
                if isinstance(raw_snapshot, dict):
                    graph = as_json_object(
                        cast(dict[str, object], raw_snapshot),
                        source="graph.snapshot",
                    )
        if mode in {"candidate", "all"}:
            profile = _profile_payload()
            coverage = _coverage_payload()
            connection = _supabase_connection()
            if connection is not None:
                try:
                    sidecar_summary = _write_sidecar(connection)
                    bm25_lag = measure_bm25_lag(connection)
                    graph = measure_graph_snapshot(connection)
                finally:
                    close = getattr(connection, "close", None)
                    if callable(close):
                        close()
                if sidecar_summary.get("sidecar_unmapped"):
                    failures.append("candidate gold sidecar has unmapped chunk UUIDs")
            else:
                failures.append("local Supabase unreachable for sidecar/lag/graph")
        if mode in {"overlay", "all"}:
            sidecar_path = artifact_paths(REPO_ROOT)["sidecar"]
            if sidecar_path.is_file():
                ranked_ids = _run_ranked_ids_live(sidecar_path)
                if ranked_ids.get("returncode") not in {0}:
                    failures.append(
                        "ranked-id live eval fail-closed "
                        f"returncode={ranked_ids.get('returncode')} "
                        f"sidecar_unmapped={ranked_ids.get('sidecar_unmapped')}"
                    )
            else:
                failures.append("candidate sidecar missing; overlay retrieve not run")
                print("phase09_packet3_ranked_ids skipped; candidate sidecar missing")
        _write_reports(
            mode=mode,
            image_ids=image_ids,
            suite_rows=suite_rows,
            hardware=hardware,
            profile=profile,
            coverage=coverage,
            sidecar=sidecar_summary,
            ranked_ids=ranked_ids,
            bm25_lag=bm25_lag,
            graph=graph,
            merge=bool(parsed.merge_artifact),
        )
        if failures:
            raise Phase09Packet3GateError("; ".join(failures))
    except Phase09Packet3GateError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

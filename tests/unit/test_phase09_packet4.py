"""Unit tests for Phase 9 Packet 4 load-gate mapping."""

from __future__ import annotations

import inspect
from pathlib import Path

from smart_rag_core.release import bm25_reproject, hybrid_foreground
from smart_rag_core.release.bm25_reproject import REPROJECT_SCHEMA_VERSION
from smart_rag_core.release.constants import (
    CANDIDATE_COMPOSE_FILE,
    PACKET4_BM25_SCHEMA_VERSION,
    PACKET8_OVERLAY_FILE,
)
from smart_rag_core.release.packet2 import PACKET1_EXPECTED_IMAGE_IDS, JUnitCounts
from smart_rag_core.release.packet3 import EXPECTED_EXACT_CODE_DOCUMENT_ID
from smart_rag_core.release.packet4 import (
    API_EXPECTED_JWT_ISSUER,
    CONSUMED_LIVE_NODEIDS,
    FROZEN_DOCKER_MEM_BYTES,
    FROZEN_DOCKER_NCPU,
    HANDOFFS,
    LOCAL_GOTRUE_JWT_ISSUER,
    PYTEST_SUITES,
    RUNTIME_PAUSE_CONTROLLER,
    TARGET_SPECS,
    classify_jwt_issuer_alignment,
    classify_suite_counts,
    classify_target,
    expected_image_ids,
    freeze_workload_profile,
    missing_pytest_files,
    pytest_command,
    suite_failure_detail,
    suites_for_mode,
)
from smart_rag_core.release.packet4_load import (
    classify_seventy_percent,
    parse_cpu_percent,
    parse_mem_usage_bytes,
    stream_gate_payload,
)
from smart_rag_core.release.packet4_seventy_live import (
    SeventyLiveHooks,
    measure_live_seventy_pause,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPO_ROOT / "scripts" / "ci" / "check_phase09_packet4.py"


def test_packet4_mapped_pytest_files_exist() -> None:
    """Every Packet 4 suite path must already exist; the matrix does not invent tests."""

    assert missing_pytest_files(REPO_ROOT) == ()
    for suite in PYTEST_SUITES:
        assert suite.pytest_args
        assert suite.fail_on_skip is True
        assert suite.overlay_required is False
    assert RUNNER.is_file()
    assert (REPO_ROOT / CANDIDATE_COMPOSE_FILE).is_file()
    assert (REPO_ROOT / PACKET8_OVERLAY_FILE).is_file()
    assert CANDIDATE_COMPOSE_FILE != PACKET8_OVERLAY_FILE


def test_hybrid_foreground_uses_autocommit() -> None:
    """Worker inject must leave connections idle for retrieval_transaction."""

    source = inspect.getsource(hybrid_foreground.run_hybrid_foreground)
    assert "autocommit=True" in source


def test_event_loop_lag_snippet_compiles() -> None:
    """Distroless ``python -c`` cannot use ``async def`` after a semicolon."""

    text = RUNNER.read_text(encoding="utf-8")
    start = text.index('_LAG_SNIPPET = """') + len('_LAG_SNIPPET = """')
    end = text.index('""".strip()', start)
    compile(text[start:end].strip(), "<lag-snippet>", "exec")


def test_zero_collection_is_failed() -> None:
    """Empty suites are a Packet 4 failure, not a skip or pass."""

    counts = JUnitCounts(tests=0, failures=0, errors=0, skipped=0)
    assert classify_suite_counts(counts, returncode=5, fail_on_skip=True) == "Failed"
    assert suite_failure_detail(counts, returncode=5, fail_on_skip=True) == (
        "zero tests collected"
    )


def test_overlay_is_not_candidate_identity() -> None:
    """Packet 4 candidate mode never selects overlay-required suites."""

    candidate = suites_for_mode("candidate")
    assert candidate == PYTEST_SUITES
    assert all(not suite.overlay_required for suite in candidate)
    hybrid = next(
        suite
        for suite in PYTEST_SUITES
        if suite.suite_id == "foreground_maintenance_graph_bm25"
    )
    assert any(
        "test_bm25_typed_query_and_injection" in item for item in hybrid.deselect
    )
    command = pytest_command(hybrid, Path("junit.xml"))
    assert "--deselect" in command
    five = next(
        suite
        for suite in PYTEST_SUITES
        if suite.suite_id == "five_stream_lag_heartbeat_offload"
    )
    assert any("test_sse_heartbeat.py" in item for item in five.pytest_args)
    assert not any(
        "test_thin_ui_live_five_composite_streams" in item for item in five.pytest_args
    )
    assert CONSUMED_LIVE_NODEIDS == ()


def test_packet1_image_ids_stay_frozen() -> None:
    """Load evidence must consume Packet 1 Ids, not rebuild."""

    ids = expected_image_ids()
    assert ids == PACKET1_EXPECTED_IMAGE_IDS
    assert ids["api"].endswith("e3633ec")
    assert ids["worker"].endswith("a97fe96e")
    assert EXPECTED_EXACT_CODE_DOCUMENT_ID == ("3367635d-7b03-4be7-945c-dd207c848e02")
    assert FROZEN_DOCKER_NCPU == 20
    assert FROZEN_DOCKER_MEM_BYTES == 8_131_035_136


def test_graph_ready_finalize_is_skipped() -> None:
    """Re-projection must not reset graph_ready via finalize_hybrid_ready."""

    source = inspect.getsource(bm25_reproject.reproject_one_version)
    assert "upsert_verify_without_finalize" in source
    assert "finalize_skipped_to_preserve_graph_ready" in source
    assert "graph_ready" in source
    assert REPROJECT_SCHEMA_VERSION == PACKET4_BM25_SCHEMA_VERSION


def test_qt_cap_001_is_not_run() -> None:
    """The labeled 8-doc subset cannot pass the 10k envelope."""

    spec = next(item for item in TARGET_SPECS if item.target_id == "QT-CAP-001")
    row = classify_target(
        spec,
        measured=8,
        mock_model_mode=True,
        sample_size=8,
        detail="subset",
        passed=True,
    )
    assert row["classification"] == "Not Run"
    cap003 = next(item for item in TARGET_SPECS if item.target_id == "QT-CAP-003")
    users = classify_target(
        cap003,
        measured=5,
        mock_model_mode=True,
        sample_size=5,
        detail="five streams",
        passed=True,
    )
    assert users["classification"] == "Not Run"
    oom = next(item for item in HANDOFFS if item.item_id == "valkey_oom_acl_outage")
    assert oom.owner == "Phase 9 Packet 5"
    assert oom.classification == "Not Run"


def test_jwt_local_issuer_pair_is_aligned() -> None:
    """Documented 127.0.0.1 / host.docker.internal iss pair is verification-aligned."""

    aliases = classify_jwt_issuer_alignment(
        token_iss=LOCAL_GOTRUE_JWT_ISSUER,
        api_expected_iss=API_EXPECTED_JWT_ISSUER,
    )
    assert aliases["aligned"] is True
    assert aliases["classification"] == "Passed"
    exact = classify_jwt_issuer_alignment(
        token_iss=API_EXPECTED_JWT_ISSUER,
        api_expected_iss=API_EXPECTED_JWT_ISSUER,
    )
    assert exact["classification"] == "Passed"
    foreign_iss = "https://auth.evil.example/auth/v1"
    foreign = classify_jwt_issuer_alignment(
        token_iss=foreign_iss,
        api_expected_iss=API_EXPECTED_JWT_ISSUER,
    )
    assert foreign["aligned"] is False
    assert foreign["classification"] == "Blocked"
    jwt_handoff = next(
        item for item in HANDOFFS if item.item_id == "jwt_issuer_hostname_split"
    )
    assert jwt_handoff.classification == "Passed"
    assert jwt_handoff.owner == "Phase 9 Packet 7"


def test_p0904_a_is_blocked_when_jwt_hides_live_p95() -> None:
    """Missing live p95 under JWT iss mismatch is Blocked, not a fake 70% pass."""

    from smart_rag_core.release.packet4 import classify_p0904_a, classify_p0904_d

    assert (
        classify_p0904_a(
            pytest_passed=True,
            seventy_passed=False,
            jwt_blocked=True,
            foreground_p95_ms=None,
        )
        == "Blocked"
    )
    assert (
        classify_p0904_a(
            pytest_passed=True,
            seventy_passed=True,
            jwt_blocked=True,
            foreground_p95_ms=100.0,
        )
        == "Passed"
    )
    assert (
        classify_p0904_d(pytest_passed=True, live_passed=False, jwt_blocked=True)
        == "Passed"
    )
    assert (
        classify_p0904_d(pytest_passed=False, live_passed=False, jwt_blocked=True)
        == "Failed"
    )


def test_mock_first_token_not_run_unless_sampled() -> None:
    """Unsigned mock latency stays Not Run until a sample exists."""

    spec = next(item for item in TARGET_SPECS if item.target_id == "QT-LAT-010")
    absent = classify_target(
        spec,
        measured=None,
        mock_model_mode=True,
        sample_size=0,
        detail="unsampled",
        passed=None,
    )
    assert absent["classification"] == "Not Run"
    sampled = classify_target(
        spec,
        measured=12.0,
        mock_model_mode=True,
        sample_size=5,
        detail="mock",
        passed=True,
    )
    assert sampled["classification"] == "Passed"


def test_workload_freeze_has_no_overlay_or_secrets() -> None:
    """Frozen workload JSON stays on docker-compose.yml and the 8-doc subset."""

    payload = freeze_workload_profile(
        hardware={"docker_ncpu": 20, "docker_mem_bytes": 8_131_035_136},
        image_ids=expected_image_ids(),
    )
    assert payload["compose_file"] == "docker-compose.yml"
    assert payload["overlay_file_is_candidate"] is False
    assert payload["sample_is_eight_doc_subset"] is True
    assert payload["managed_claims"] == []
    text = str(payload)
    assert "postgres:" not in text
    assert "SERVICE_ROLE" not in text


def test_seventy_percent_can_pass_without_trigger() -> None:
    """On the 8-doc subset, holding foreground p95 is enough for P09-04-A."""

    held = classify_seventy_percent(
        cpu_peaks=[12.0],
        foreground_p95_ms=800.0,
        foreground_gate_ms=40000.0,
    )
    assert held["trigger_70_percent_fired"] is False
    assert held["passed"] is True
    assert held["sample_is_eight_doc_subset"] is True
    missed = classify_seventy_percent(
        cpu_peaks=[12.0],
        foreground_p95_ms=None,
        foreground_gate_ms=40000.0,
    )
    assert missed["passed"] is False
    assert held["runtime_pause_controller"] == RUNTIME_PAUSE_CONTROLLER
    assert "QT-CAP-001" in RUNTIME_PAUSE_CONTROLLER
    assert "3.06%" in RUNTIME_PAUSE_CONTROLLER


def test_stream_gate_ignores_heartbeats_when_mock_is_short() -> None:
    """Live mock streams that finish before 15s do not invent missed heartbeats."""

    payload = stream_gate_payload(
        first_token_ms=[20.0, 21.0, 22.0, 23.0, 24.0],
        completion_ms=[200.0, 210.0, 220.0, 230.0, 240.0],
        heartbeat_counts=[0, 0, 0, 0, 0],
        lag_p95_seconds=0.01,
        simultaneous_runs=5,
        mock_model_mode=True,
    )
    assert payload["qt_cap_004_passed"] is True
    assert payload["live_completed_before_15s_heartbeat"] is True
    assert payload["missed_15s_heartbeats"] == 0
    assert payload["lag_passed"] is True
    assert parse_cpu_percent("12.5%") == 12.5
    assert parse_mem_usage_bytes("120MiB / 2GiB") == 120 * 1024 * 1024


def test_live_seventy_probe_passes_on_held_p95_without_busy_loop(
    tmp_path: Path,
) -> None:
    """Injected 8-doc p95 hold classifies Passed without a 70% fire."""

    def _stats() -> list[dict[str, object]]:
        """Return a quiet API CPU sample.

        Returns:
            One container stats object.
        """

        return [{"Name": "smart-rag-api-1", "CPUPerc": "4.00%"}]

    def _foreground(token: str) -> dict[str, object]:
        """Return a held-p95 foreground probe payload.

        Args:
            token: Unused probe token.

        Returns:
            Passing foreground timings.
        """

        del token
        return {
            "passed": True,
            "jwt_eventsource_401": False,
            "inspect_ms": 50.0,
            "inspect_ok": True,
            "streams": {
                "first_token_p95_ms": 40.0,
                "completion_p95_ms": 800.0,
                "simultaneous_runs": 5,
            },
        }

    probe_token = "unit-test-token"  # noqa: S105
    payload = measure_live_seventy_pause(
        tmp_path,
        token=probe_token,
        hooks=SeventyLiveHooks(docker_stats=_stats, foreground=_foreground),
        write_artifact=True,
    )
    seventy = payload["seventy_percent"]
    assert isinstance(seventy, dict)
    assert seventy["passed"] is True
    assert seventy["trigger_70_percent_fired"] is False
    assert seventy["classification"] == "Passed"
    assert payload["busy_loop"] is False
    assert payload["qt_cap_001_claimed"] is False
    artifact = tmp_path / "docs" / "deployment" / "phase-09"
    artifact = artifact / "candidate-packet4-seventy-live.json"
    assert artifact.is_file()

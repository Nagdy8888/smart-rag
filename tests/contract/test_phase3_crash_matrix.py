"""Packet 8 crash-matrix registry mapping plan crash points to owning tests."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Plan Packet 8 ordered crash points → owning evidence tests.
# Entries marked ``pending_e2e`` require live Storage/worker Compose and remain
# documented blockers in phase-03 evidence until measured.
CRASH_MATRIX: dict[str, str] = {
    "claim_skip_locked_exclusive": (
        "tests/contract/test_job_leases.py::test_skip_locked_claim_is_exclusive"
    ),
    "heartbeat_and_lease_loss_cancel": (
        "tests/contract/test_job_leases.py::test_heartbeat_renews_and_cancel_blocks_writes"
    ),
    "invalid_lease_blocks_side_effects": (
        "tests/contract/test_job_leases.py::test_invalid_lease_token_denies_ledger_write"
    ),
    "dead_letter_replay": (
        "tests/contract/test_job_leases.py::test_dead_letter_replay_creates_traceable_attempt"
    ),
    "promotion_copy_verify_db_switch_source_delete": (
        "tests/contract/test_promotion_saga.py::"
        "test_promotion_saga_replays_after_each_crash_point"
    ),
    "duplicate_enqueue_idempotency": (
        "tests/contract/test_job_leases.py::test_duplicate_enqueue_returns_same_job"
    ),
    "graph_handoff_idempotency": (
        "tests/contract/test_hybrid_lifecycle.py::"
        "test_graph_pending_handoff_is_idempotent"
    ),
    "deletion_acl_immediate_exclusion": (
        "tests/contract/test_hybrid_lifecycle.py::"
        "test_deletion_excludes_retrieval_and_enqueues_bm25_cleanup"
    ),
    "parser_oversize_no_partial_publish": (
        "tests/unit/test_parser_sandbox.py::"
        "test_oversize_input_fails_without_partial_elements"
    ),
    "governance_positive_detector_blocks_promotion": (
        "tests/unit/test_parser_governance.py::"
        "test_extraction_positive_detector_blocks_promotion"
    ),
    "embedding_real_content_denied_without_provider": (
        "tests/unit/test_embedding_service.py::"
        "test_embedding_service_denies_real_company_without_provider_verification"
    ),
}


PENDING_E2E_CRASH_POINTS: tuple[str, ...] = (
    "storage_download_mid_crash",
    "scan_mid_crash_before_scan_event",
    "parser_sandbox_kill_timeout_mid_job",
    "langgraph_checkpoint_superstep_interrupt",
    "canonical_transaction_rollback_mid_batch",
    "embedding_timeout_after_provider_success",
    "bm25_mid_batch_crash_before_verify",
    "hybrid_ready_flip_before_bm25_verify",
)


def test_crash_matrix_owning_tests_exist() -> None:
    """Every mapped crash-matrix owning test module and function exists."""

    for label, nodeid in CRASH_MATRIX.items():
        module_path, _, func_part = nodeid.partition("::")
        test_name = func_part.split("[", 1)[0]
        path = REPO_ROOT / module_path
        assert path.is_file(), f"{label}: missing {module_path}"
        text = path.read_text(encoding="utf-8")
        assert f"def {test_name}(" in text, f"{label}: missing {test_name}"


def test_pending_e2e_crash_points_are_explicit() -> None:
    """Unimplemented live-stack crash injections remain an explicit pending set."""

    assert len(PENDING_E2E_CRASH_POINTS) >= 5
    assert "bm25_mid_batch_crash_before_verify" in PENDING_E2E_CRASH_POINTS
    # Proven matrix must not claim these pending IDs.
    for pending in PENDING_E2E_CRASH_POINTS:
        assert pending not in CRASH_MATRIX

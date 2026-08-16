"""Unit tests for Packet 7 pointer CAS, cleanup SLAs, and upgrade isolation."""

from __future__ import annotations

from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from uuid import uuid4

import pytest
from smart_rag_core.jobs.exceptions import GraphLifecycleError
from smart_rag_core.jobs.graph_cleanup import enqueue_surviving_rebuild
from smart_rag_core.jobs.graph_lifecycle import (
    HOMOGENEOUS_EMBEDDING_DIMENSIONS,
    HOMOGENEOUS_EMBEDDING_MODEL,
    PointerCrashPhase,
    assert_homogeneous_embedding,
    assert_isolated_upgrade_environment,
    authoritative_version_after_crash,
    cas_pointer_generation,
    delete_status_fails_closed,
    disable_review_required,
    exposed_generation_after_crash,
    graph_pointer_lock_keys,
    tombstone_deadlines,
)
from smart_rag_core.jobs.limits import (
    GRAPH_CLEAN_REBUILD_SLA_DAYS,
    GRAPH_TARGET_CLEANUP_SLA_HOURS,
    GRAPH_UPGRADE_FAILURE_DISABLE_THRESHOLD,
)
from smart_rag_core.retrieval.graph import (
    GraphLimitationCode,
    workspace_limitation_code,
)


def test_crash_matrix_exposes_exactly_one_generation() -> None:
    """Crashes expose old or new generation, never mixed or zero."""

    old = 3
    new = 4
    assert (
        exposed_generation_after_crash(
            phase=PointerCrashPhase.BEFORE_COMMIT,
            committed=False,
            old_generation=old,
            new_generation=new,
        )
        == old
    )
    assert (
        exposed_generation_after_crash(
            phase=PointerCrashPhase.DURING_COMMIT,
            committed=False,
            old_generation=old,
            new_generation=new,
        )
        == old
    )
    assert (
        exposed_generation_after_crash(
            phase=PointerCrashPhase.AFTER_COMMIT,
            committed=True,
            old_generation=old,
            new_generation=new,
        )
        == new
    )
    assert (
        exposed_generation_after_crash(
            phase=PointerCrashPhase.STALE_GENERATION,
            committed=False,
            old_generation=old,
            new_generation=new,
        )
        == old
    )
    with pytest.raises(GraphLifecycleError, match="zero_generation_forbidden"):
        exposed_generation_after_crash(
            phase=PointerCrashPhase.AFTER_COMMIT,
            committed=True,
            old_generation=0,
            new_generation=1,
        )


def test_crash_matrix_exposes_exactly_one_current_version() -> None:
    """Version flips never expose mixed or identical current versions."""

    old = uuid4()
    new = uuid4()
    assert (
        authoritative_version_after_crash(
            phase=PointerCrashPhase.BEFORE_COMMIT,
            committed=False,
            old_version_id=old,
            new_version_id=new,
        )
        == old
    )
    assert (
        authoritative_version_after_crash(
            phase=PointerCrashPhase.AFTER_COMMIT,
            committed=True,
            old_version_id=old,
            new_version_id=new,
        )
        == new
    )
    with pytest.raises(GraphLifecycleError, match="versions_not_distinct"):
        authoritative_version_after_crash(
            phase=PointerCrashPhase.AFTER_COMMIT,
            committed=True,
            old_version_id=old,
            new_version_id=old,
        )


def test_stale_generation_cas_does_not_flip() -> None:
    """A mismatched expected generation refuses the pointer swap."""

    assert cas_pointer_generation(current=7, expected=7) == 7
    assert cas_pointer_generation(current=7, expected=6) is None


def test_tombstone_slas_are_twenty_four_hours_and_seven_days() -> None:
    """Target cleanup is 24h; clean rebuild is 7 days."""

    now = datetime(2026, 8, 16, 6, 0, tzinfo=UTC)
    target, rebuild = tombstone_deadlines(now=now)
    assert (target - now).total_seconds() == GRAPH_TARGET_CLEANUP_SLA_HOURS * 3600
    assert (rebuild - now).days == GRAPH_CLEAN_REBUILD_SLA_DAYS


def test_delete_statuses_fail_closed() -> None:
    """not_allowed and fail quarantine immediately; not_found needs residue checks."""

    assert delete_status_fails_closed("not_allowed") is True
    assert delete_status_fails_closed("fail") is True
    assert delete_status_fails_closed("not_found") is False
    assert delete_status_fails_closed("success") is False


def test_mixed_embeddings_and_same_schema_upgrade_are_refused() -> None:
    """In-place mixed embeddings and same-schema upgrade proof fail closed."""

    assert_homogeneous_embedding(
        model=HOMOGENEOUS_EMBEDDING_MODEL,
        dimensions=HOMOGENEOUS_EMBEDDING_DIMENSIONS,
    )
    with pytest.raises(
        GraphLifecycleError, match="in_place_mixed_embeddings_forbidden"
    ):
        assert_homogeneous_embedding(
            model=HOMOGENEOUS_EMBEDDING_MODEL,
            dimensions=HOMOGENEOUS_EMBEDDING_DIMENSIONS,
            other_model=HOMOGENEOUS_EMBEDDING_MODEL,
            other_dimensions=1536,
        )
    with pytest.raises(GraphLifecycleError, match="upgrade_same_schema_insufficient"):
        assert_isolated_upgrade_environment(
            candidate_database="postgres",
            candidate_schema="lightrag",
            runtime_database="postgres",
            runtime_schema="lightrag",
        )
    assert_isolated_upgrade_environment(
        candidate_database="lightrag_upgrade_copy",
        candidate_schema="lightrag",
        runtime_database="postgres",
        runtime_schema="lightrag",
    )


def test_two_consecutive_upgrade_failures_open_disable_review() -> None:
    """Two consecutive failed qualifications require replacement/disable review."""

    assert disable_review_required(consecutive_failures=1) is False
    assert (
        disable_review_required(
            consecutive_failures=GRAPH_UPGRADE_FAILURE_DISABLE_THRESHOLD
        )
        is True
    )


def test_disabled_and_quarantined_emit_graph_outage() -> None:
    """Disabled/quarantined workspaces make inspection and Combined unavailable."""

    assert (
        workspace_limitation_code("disabled", pointer_attached=True)
        is GraphLimitationCode.GRAPH_OUTAGE
    )
    assert (
        workspace_limitation_code("quarantined", pointer_attached=True)
        is GraphLimitationCode.GRAPH_OUTAGE
    )
    assert (
        workspace_limitation_code("filtered_dirty", pointer_attached=True)
        is GraphLimitationCode.GRAPH_FILTERED_DIRTY
    )


def test_unfunded_rebuild_raises_before_insert() -> None:
    """Unfunded surviving rebuild fails closed without enqueueing."""

    with pytest.raises(GraphLifecycleError, match="unfunded_rebuild"):
        enqueue_surviving_rebuild(None, funded=False)  # type: ignore[arg-type]


def test_restore_cli_refuses_same_schema() -> None:
    """The ops restore CLI exits 2 when candidate equals runtime lightrag."""

    script = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "ops"
        / "restore_lightrag_upgrade_copy.py"
    )
    spec = spec_from_file_location("restore_lightrag_upgrade_copy", script)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    assert (
        module.main(
            [
                "--candidate-database",
                "postgres",
                "--candidate-schema",
                "lightrag",
                "--runtime-database",
                "postgres",
                "--runtime-schema",
                "lightrag",
            ]
        )
        == module.EXIT_REFUSED
    )


def test_pointer_lock_keys_are_positive_and_stable() -> None:
    """Transaction advisory keys stay in signed int4 and differ by workspace."""

    first = graph_pointer_lock_keys("company_default")
    second = graph_pointer_lock_keys("company_default")
    other = graph_pointer_lock_keys("company_default__rebuild")
    assert first == second
    assert first != other
    assert first[0] >= 0
    assert first[1] >= 0
    assert first[0] <= 0x7FFFFFFF

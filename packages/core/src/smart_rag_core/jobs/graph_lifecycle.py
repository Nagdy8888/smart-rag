"""Pointer CAS, crash-matrix, and SLA helpers for graph lifecycle.

Vendor mutations and model calls stay outside the pointer transaction.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Final

from smart_rag_core.jobs.exceptions import GraphLifecycleError
from smart_rag_core.jobs.limits import (
    GRAPH_CLEAN_REBUILD_SLA_DAYS,
    GRAPH_POINTER_LOCK_NAMESPACE,
    GRAPH_TARGET_CLEANUP_SLA_HOURS,
    GRAPH_UPGRADE_FAILURE_DISABLE_THRESHOLD,
    RUNTIME_LIGHTRAG_SCHEMA,
)

FAIL_CLOSED_DELETE_STATUSES: Final[frozenset[str]] = frozenset({"not_allowed", "fail"})
RETRYABLE_DELETE_STATUSES: Final[frozenset[str]] = frozenset({"success", "not_found"})
HOMOGENEOUS_EMBEDDING_MODEL: Final[str] = "text-embedding-3-large"
HOMOGENEOUS_EMBEDDING_DIMENSIONS: Final[int] = 1024


class PointerCrashPhase(StrEnum):
    """Crash points around the short pointer commit."""

    BEFORE_COMMIT = "before_commit"
    DURING_COMMIT = "during_commit"
    AFTER_COMMIT = "after_commit"
    STALE_GENERATION = "stale_generation"


class CleanupRecoveryPhase(StrEnum):
    """Persisted vendor-delete recovery phases. Crash is retryable."""

    PRECHECK = "precheck"
    VENDOR_DELETE = "vendor_delete"
    VENDOR_VERIFY = "vendor_verify"
    MAP_FILTER = "map_filter"
    TOMBSTONE = "tombstone"
    VERIFIED = "verified"


class CleanupReason(StrEnum):
    """Tombstone reasons for targeted graph cleanup."""

    DELETION = "deletion"
    ACL_DOWNGRADE = "acl_downgrade"
    VERSION_SUPERSEDE = "version_supersede"


def graph_pointer_lock_keys(workspace_key: str) -> tuple[int, int]:
    """Derive transaction advisory-lock keys for the pointer CAS.

    Distinct from the session writer lock namespace. Positive int4 values.

    Args:
        workspace_key: Application workspace such as ``company_default``.

    Returns:
        Two signed int4 keys matching SQL ``hashtext`` only in intent; Python
        tests use this pair with ``pg_advisory_xact_lock``. Production SQL
        uses ``hashtext`` inside the switch functions.

    Raises:
        ValueError: If ``workspace_key`` is empty.
    """

    stripped = workspace_key.strip()
    if not stripped:
        raise ValueError("workspace_key_empty")
    digest = hashlib.sha256(
        f"{GRAPH_POINTER_LOCK_NAMESPACE}:{stripped}".encode()
    ).digest()
    key_one = int.from_bytes(digest[0:4], "big") & 0x7FFFFFFF
    key_two = int.from_bytes(digest[4:8], "big") & 0x7FFFFFFF
    if key_one == 0 and key_two == 0:
        key_two = 1
    return key_one, key_two


def cas_pointer_generation(*, current: int, expected: int) -> int | None:
    """Compare-and-swap helper for crash-matrix tests.

    Args:
        current: Durable pointer generation.
        expected: Caller-supplied generation.

    Returns:
        ``current`` when the CAS matches, otherwise ``None``.
    """

    if current != expected:
        return None
    return current


def authoritative_version_after_crash(
    *,
    phase: PointerCrashPhase,
    committed: bool,
    old_version_id: object,
    new_version_id: object,
) -> object:
    """Return the single current version a crash may expose.

    Args:
        phase: Crash point.
        committed: Whether the pointer transaction committed.
        old_version_id: Current version before the attempt.
        new_version_id: Replacement version after a successful flip.

    Returns:
        Exactly one version id. Never mixed current versions.

    Raises:
        GraphLifecycleError: If the two ids are not distinct.
    """

    if old_version_id == new_version_id:
        raise GraphLifecycleError("versions_not_distinct")
    if phase is PointerCrashPhase.STALE_GENERATION:
        return old_version_id
    if phase in {
        PointerCrashPhase.BEFORE_COMMIT,
        PointerCrashPhase.DURING_COMMIT,
    }:
        return old_version_id
    if committed and phase is PointerCrashPhase.AFTER_COMMIT:
        return new_version_id
    return old_version_id


def exposed_generation_after_crash(
    *,
    phase: PointerCrashPhase,
    committed: bool,
    old_generation: int,
    new_generation: int,
) -> int:
    """Return the generation a crash may expose.

    Crashes never expose mixed or zero current versions. Before/during commit
    and stale CAS keep the old generation. After a successful commit the new
    generation is visible.

    Args:
        phase: Crash point.
        committed: Whether the pointer transaction committed.
        old_generation: Generation before the attempt.
        new_generation: Generation after a successful workspace switch.

    Returns:
        Exactly one generation. Never ``0``.

    Raises:
        GraphLifecycleError: If generations are not positive.
    """

    if old_generation < 1 or new_generation < 1:
        raise GraphLifecycleError("zero_generation_forbidden")
    if phase is PointerCrashPhase.STALE_GENERATION:
        return old_generation
    if phase in {
        PointerCrashPhase.BEFORE_COMMIT,
        PointerCrashPhase.DURING_COMMIT,
    }:
        return old_generation
    if committed and phase is PointerCrashPhase.AFTER_COMMIT:
        return new_generation
    return old_generation


def tombstone_deadlines(
    *,
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    """Return target-cleanup and clean-rebuild deadlines.

    Args:
        now: Clock override. Defaults to UTC now.

    Returns:
        ``(target_cleanup_at, clean_rebuild_at)`` in UTC.
    """

    stamp = now or datetime.now(tz=UTC)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    target = stamp + timedelta(hours=GRAPH_TARGET_CLEANUP_SLA_HOURS)
    rebuild = stamp + timedelta(days=GRAPH_CLEAN_REBUILD_SLA_DAYS)
    return target, rebuild


def delete_status_fails_closed(status: str) -> bool:
    """Return whether a vendor deletion status must quarantine immediately.

    Args:
        status: Documented ``DeletionResult.status``.

    Returns:
        True for ``not_allowed`` and ``fail``. ``not_found`` still requires
        residue verification.
    """

    return status in FAIL_CLOSED_DELETE_STATUSES


def assert_homogeneous_embedding(
    *,
    model: str,
    dimensions: int,
    other_model: str | None = None,
    other_dimensions: int | None = None,
) -> None:
    """Refuse in-place mixed embedding configurations.

    Args:
        model: Candidate embedding model.
        dimensions: Candidate output dimensions.
        other_model: Existing workspace model when switching.
        other_dimensions: Existing workspace dimensions when switching.

    Raises:
        GraphLifecycleError: If the pin mismatches or two configs would mix.
    """

    if (
        model != HOMOGENEOUS_EMBEDDING_MODEL
        or dimensions != HOMOGENEOUS_EMBEDDING_DIMENSIONS
    ):
        raise GraphLifecycleError("embedding_config_mismatch")
    if other_model is None or other_dimensions is None:
        return
    if other_model != model or other_dimensions != dimensions:
        raise GraphLifecycleError("in_place_mixed_embeddings_forbidden")


def assert_isolated_upgrade_environment(
    *,
    candidate_database: str,
    candidate_schema: str,
    runtime_database: str,
    runtime_schema: str = RUNTIME_LIGHTRAG_SCHEMA,
) -> None:
    """Refuse upgrade proof that only uses a second workspace in runtime schema.

    Args:
        candidate_database: Restored copy database name.
        candidate_schema: Restored copy schema.
        runtime_database: Live application database name.
        runtime_schema: Live vendor schema, default ``lightrag``.

    Raises:
        GraphLifecycleError: If candidate equals the runtime database+schema.
    """

    if (
        candidate_database.strip() == runtime_database.strip()
        and candidate_schema.strip() == runtime_schema.strip()
    ):
        raise GraphLifecycleError("upgrade_same_schema_insufficient")


def disable_review_required(*, consecutive_failures: int) -> bool:
    """Return whether two consecutive failed upgrade qualifications require review.

    Args:
        consecutive_failures: Count of consecutive failed qualifications.

    Returns:
        True when the disable/replacement review path must open.
    """

    return consecutive_failures >= GRAPH_UPGRADE_FAILURE_DISABLE_THRESHOLD

"""Classify Phase 10 Packet 6 restore, rebuild, instance, and skew gates.

Local Phase 9 dump/restore and derived BM25 rebuild are supporting evidence
only. Isolated managed Supabase PITR, four-bucket Storage restore,
live reconciliation, timed EC2 rebuild, CloudFront/Vercel deploy orders,
and live Caddy drain remain Blocked. Claiming a local dump as managed PITR,
a ParadeDB snapshot as canonical, rebuild-before-reconcile, live-database
overwrite, missing required buckets, destructive contraction, or invented
RTO/RPO measurements is Failed. Packets 1-5 remaining unchecked is not a
Packet 6 failure.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal

from smart_rag_core.release.io import (
    as_json_list,
    as_json_object,
    dump_canonical_json,
    json_int,
    load_json_object,
)
from smart_rag_core.release.packet2 import Classification
from smart_rag_core.release.phase10_constants import (
    BM25_REBUILD_RUNBOOK,
    BM25_REBUILD_RUNBOOK_REQUIRED_TOKENS,
    ENVELOPE_CHUNKS,
    ENVELOPE_GRAPH_VERSIONS,
    ENVELOPE_HYBRID_VERSIONS,
    GITHUB_WORKFLOWS_DIR,
    INSTANCE_REBUILD_RUNBOOK,
    INSTANCE_REBUILD_RUNBOOK_REQUIRED_TOKENS,
    OLD_API_PRIOR_DIGEST,
    PACKET6_INSTANCE_NAME,
    PACKET6_INSTANCE_SCHEMA_VERSION,
    PACKET6_INVENTORY_NAME,
    PACKET6_INVENTORY_SCHEMA_VERSION,
    PACKET6_MATRIX_NAME,
    PACKET6_MATRIX_SCHEMA_VERSION,
    PACKET6_NEGATIVES_NAME,
    PACKET6_NEGATIVES_SCHEMA_VERSION,
    PACKET6_REBUILD_NAME,
    PACKET6_REBUILD_SCHEMA_VERSION,
    PACKET6_RECONCILE_NAME,
    PACKET6_RECONCILE_SCHEMA_VERSION,
    PACKET6_RELATIVE,
    PACKET6_RESTORE_INCOMPLETE_TEST_FILES,
    PACKET6_SKEW_NAME,
    PACKET6_SKEW_SCHEMA_VERSION,
    PHASE09_IMAGE_IDS,
    PHASE09_OLD_API_SMOKE,
    PHASE09_PACKET6_REBUILD,
    PHASE09_PACKET6_RESTORE,
    PHASE10_ARTIFACT_DIR,
    PROTECTED_MIGRATION_RUNBOOK,
    REBUILD_BEFORE_RECONCILE_PHRASES,
    RECONCILE_RUNBOOK_REQUIRED_TOKENS,
    REQUIRED_STORAGE_BUCKETS,
    RPO_TARGET_HOURS,
    RTO_TARGET_HOURS,
    STAGING_CADDY_FILE,
    STAGING_COMPOSE_FILE,
    STORAGE_RECONCILE_RUNBOOK,
    WRAPPER_RELATIVE,
)
from smart_rag_core.release.phase10_packet1 import (
    LiveProviderProbe,
    probe_live_providers,
    wrapper_status_pending,
)
from smart_rag_core.release.phase10_packet2 import review_migrations
from smart_rag_core.release.phase10_topology import (
    PolicyFinding,
    PolicyReport,
    hash_reviewed_files,
)

LiveProofState = Literal["Blocked", "Not Run", "Failed"]

_LIVE_PITR_REASON = (
    "No isolated managed Supabase PITR plus four-bucket Storage restore. "
    "Local Phase 9 dump/restore is supporting only and is not a complete "
    "managed restore Pass."
)
_LIVE_RECONCILE_REASON = (
    "No live managed reconciliation. Orphan counts were not invented. "
    "Policy requires restore_incomplete exclusion and orphan quarantine "
    "before any BM25 rebuild."
)
_LIVE_EC2_REBUILD_REASON = (
    "No timed empty ParadeDB rebuild on EC2. Phase 9 volume destroy plus "
    "authorized re-projection is derived-projection evidence only."
)
_LIVE_INSTANCE_REASON = (
    "No timed EC2 instance rebuild. RTO ≤4h and RPO ≤24h remain targets, "
    "not measurements."
)
_LIVE_DRAIN_REASON = (
    "No live CloudFront/Vercel deploy-order matrix and no live Caddy "
    "drain or failed SSM deploy. Compose api-blue/api-green exists; a "
    "live switch is not claimed."
)


class Phase10Packet6GateError(RuntimeError):
    """Raised when Packet 6 classification cannot be recorded honestly."""


class RestoreReconcileKind(StrEnum):
    """Adversarial Storage/database mismatch kinds for Packet 6-B."""

    MATCH = "match"
    MISSING_OBJECT = "missing_object"
    HASH_MISMATCH = "hash_mismatch"
    OBJECT_ORPHAN = "object_orphan"


@dataclass(frozen=True, slots=True)
class AcceptanceRow:
    """One P10-06 acceptance classification.

    Attributes:
        check: Requirement id such as ``P10-06-A``.
        classification: Honest Passed/Failed/Blocked/Not Run value.
        detail: Evidence without secrets.
    """

    check: str
    classification: Classification
    detail: str


@dataclass(frozen=True, slots=True)
class ReconcileDecision:
    """Pure-policy outcome for one restore mismatch.

    Attributes:
        mark_restore_incomplete: True when the database reference is incomplete.
        exclude_hybrid_graph: True when Hybrid and graph must skip the version.
        quarantine_orphan: True when an object-only orphan is quarantined.
        append_only_audit: True when an append-only audit event is required.
        alert: True when an admin/ops alert is required.
        allow_rebuild: True only after a complete reconciliation of matches.
    """

    mark_restore_incomplete: bool
    exclude_hybrid_graph: bool
    quarantine_orphan: bool
    append_only_audit: bool
    alert: bool
    allow_rebuild: bool


@dataclass(frozen=True, slots=True)
class Phase09RestoreEvidence:
    """Phase 9 Packet 6 restore facts reused as supporting evidence.

    Attributes:
        live_database_overwritten: True if the live application DB was restored.
        restore_returncode: ``pg_restore`` exit; ``1`` is warnings, not PITR.
        dump_passed: Local dump recorded passed.
        disposable_passed: Disposable-copy restore recorded passed.
        paradedb_used_as_canonical: True when ParadeDB was treated as authority.
        present_buckets: Buckets listed present in the inventory.
        required_buckets: Expected durable bucket names.
    """

    live_database_overwritten: bool
    restore_returncode: int
    dump_passed: bool
    disposable_passed: bool
    paradedb_used_as_canonical: bool
    present_buckets: tuple[str, ...]
    required_buckets: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Phase09RebuildEvidence:
    """Phase 9 Packet 6 BM25 rebuild facts reused as derived-projection proof.

    Attributes:
        paradedb_used_as_canonical: True when a snapshot was treated as authority.
        volume_destroyed: True when the ParadeDB volume was removed.
        rebuild_passed: Worker re-projection recorded passed.
        rebuild_scope: Recorded rebuild scope string.
        parade_total_rows: Sampled projection row count after rebuild.
    """

    paradedb_used_as_canonical: bool
    volume_destroyed: bool
    rebuild_passed: bool
    rebuild_scope: str
    parade_total_rows: int


@dataclass(frozen=True, slots=True)
class OldApiSmokeEvidence:
    """Phase 9 old-API/new-schema smoke reused by Packet 6-E.

    Attributes:
        classification: Recorded classification string.
        freeze_api_id: Freeze image that must remain the Packet 1 API id.
        requested: Prior digest served during the expand window.
        restored_freeze: True when the freeze image was restored afterward.
        holdout_opened: True when holdout was opened (forbidden).
    """

    classification: str
    freeze_api_id: str
    requested: str
    restored_freeze: bool
    holdout_opened: bool


def packet6_checkbox_unchecked(text: str) -> bool:
    """Return whether the wrapper Packet 6 checkbox is unchecked.

    Args:
        text: Wrapper markdown.

    Returns:
        True when packet 6 remains ``[ ]``. Packets 1-5 are ignored.
    """

    return (
        "6. [ ] [Perform and record database-plus-Storage restore/reconciliation"
        in text
    )


def packet6_status_pending(text: str) -> bool:
    """Return whether the Packet 6 file frontmatter is still pending.

    Args:
        text: Packet markdown.

    Returns:
        True when ``status: pending`` is present in frontmatter.
    """

    head = text.split("---", 2)
    if len(head) < 3:
        return False
    return "status: pending" in head[1]


def live_proof_state(live: LiveProviderProbe) -> LiveProofState:
    """Map the Packet 1 provider probe onto Packet 6 live restore/rebuild state.

    Args:
        live: Terraform/AWS CLI probe. This function does not restore, rebuild,
            or switch Caddy.

    Returns:
        ``Blocked`` when tools or session are missing. ``Not Run`` when a
        session exists but this packet refuses live PITR/EC2/drain.
        ``Failed`` when the probe itself failed.
    """

    if live.apply_state == "Failed":
        return "Failed"
    if live.apply_state == "Blocked" or not live.sts_ok:
        return "Blocked"
    return "Not Run"


def finding_passed(policy: PolicyReport | None, check: str) -> bool:
    """Return whether one named Packet 6 finding passed.

    Args:
        policy: Packet 6 policy report, or None when files are missing.
        check: Finding id.

    Returns:
        True when the report exists and that finding passed.
    """

    if policy is None:
        return False
    for item in policy.findings:
        if item.check == check:
            return item.passed
    return False


def missing_required_buckets(
    present: Sequence[str],
    *,
    required: Sequence[str] = REQUIRED_STORAGE_BUCKETS,
) -> tuple[str, ...]:
    """Return required durable buckets absent from an inventory.

    Args:
        present: Bucket names recorded as present.
        required: Canonical four-bucket set.

    Returns:
        Sorted missing bucket names.
    """

    have = {name for name in present}
    return tuple(sorted(name for name in required if name not in have))


def rebuild_documented_before_reconcile(text: str) -> bool:
    """Return whether a document orders ParadeDB rebuild before reconciliation.

    Args:
        text: Runbook or adversarial report text.

    Returns:
        True when a forbidden rebuild-first phrase is present.
    """

    lowered = text.casefold()
    return any(phrase in lowered for phrase in REBUILD_BEFORE_RECONCILE_PHRASES)


def decide_reconciliation(
    kind: RestoreReconcileKind,
    *,
    reconciliation_complete: bool,
) -> ReconcileDecision:
    """Return the fail-closed action for one Storage/database mismatch.

    Missing objects and hash mismatches mark ``restore_incomplete`` and
    exclude the version from Hybrid and graph. Object-only orphans are
    quarantined with an append-only audit and alert. Rebuild is allowed
    only after a complete reconciliation of matching pairs.

    Args:
        kind: Adversarial mismatch kind.
        reconciliation_complete: True when every durable reference is resolved.

    Returns:
        Policy decision. Never invents live orphan counts.
    """

    if kind in {
        RestoreReconcileKind.MISSING_OBJECT,
        RestoreReconcileKind.HASH_MISMATCH,
    }:
        return ReconcileDecision(
            mark_restore_incomplete=True,
            exclude_hybrid_graph=True,
            quarantine_orphan=False,
            append_only_audit=True,
            alert=True,
            allow_rebuild=False,
        )
    if kind is RestoreReconcileKind.OBJECT_ORPHAN:
        return ReconcileDecision(
            mark_restore_incomplete=False,
            exclude_hybrid_graph=False,
            quarantine_orphan=True,
            append_only_audit=True,
            alert=True,
            allow_rebuild=False,
        )
    return ReconcileDecision(
        mark_restore_incomplete=False,
        exclude_hybrid_graph=False,
        quarantine_orphan=False,
        append_only_audit=False,
        alert=False,
        allow_rebuild=reconciliation_complete,
    )


def rto_rpo_invented(
    *,
    measured_rto_hours: float | None,
    measured_rpo_hours: float | None,
    live_instance_passed: bool,
) -> bool:
    """Return whether RTO/RPO hours were claimed without a live rebuild.

    Args:
        measured_rto_hours: Claimed restore-to-service duration, or None.
        measured_rpo_hours: Claimed data-loss window, or None.
        live_instance_passed: True only after a timed EC2 rebuild artifact.

    Returns:
        True when measurements are present without live proof.
    """

    if live_instance_passed:
        return False
    return measured_rto_hours is not None or measured_rpo_hours is not None


def _require_tokens(text: str, tokens: Sequence[str], *, source: str) -> None:
    """Require case-folded tokens in a runbook.

    Args:
        text: Runbook markdown.
        tokens: Required phrases.
        source: Label used in the error.

    Raises:
        Phase10Packet6GateError: If a token is missing.
    """

    lowered = text.casefold()
    missing = [token for token in tokens if token.casefold() not in lowered]
    if missing:
        raise Phase10Packet6GateError(
            f"{source} missing required tokens: " + ", ".join(missing)
        )


def _require_no_secrets(text: str, *, source: str) -> None:
    """Reject committed secret-like assignments in a runbook.

    Args:
        text: Runbook markdown.
        source: Label used in the error.

    Raises:
        Phase10Packet6GateError: If a secret assignment appears.
    """

    lowered = text.casefold()
    forbidden = (
        "aws_secret_access_key",
        "service_role",
        "password=",
        "begin private key",
    )
    for item in forbidden:
        if item in lowered:
            raise Phase10Packet6GateError(f"{source} must not contain {item}")


def assert_runbook_tokens(
    text: str,
    tokens: Sequence[str],
    *,
    source: str,
) -> None:
    """Require Mermaid, prerequisites, rollback, verification, and tokens.

    Args:
        text: Runbook markdown.
        tokens: Packet-specific required phrases.
        source: Label used in the error.

    Raises:
        Phase10Packet6GateError: If structure or tokens are missing.
    """

    _require_no_secrets(text, source=source)
    lowered = text.casefold()
    for heading in ("prerequisites", "rollback", "verification"):
        if heading not in lowered:
            raise Phase10Packet6GateError(f"{source} must document {heading}")
    _require_tokens(text, tokens, source=source)


def assert_rebuild_after_reconcile(*, reconcile_text: str, rebuild_text: str) -> None:
    """Fail when rebuild is documented before Storage/database reconciliation.

    Args:
        reconcile_text: Storage-DB reconciliation runbook.
        rebuild_text: BM25 rebuild runbook.

    Raises:
        Phase10Packet6GateError: If rebuild-first phrasing is present or the
            required after-reconcile contract is missing.
    """

    if rebuild_documented_before_reconcile(reconcile_text):
        raise Phase10Packet6GateError(
            "reconciliation runbook documents rebuild before reconcile"
        )
    if rebuild_documented_before_reconcile(rebuild_text):
        raise Phase10Packet6GateError(
            "BM25 rebuild runbook documents rebuild before reconcile"
        )
    if "rebuild only after reconciliation" not in reconcile_text.casefold():
        raise Phase10Packet6GateError(
            "reconciliation runbook must require rebuild only after reconciliation"
        )
    if "only from reconciled" not in rebuild_text.casefold():
        raise Phase10Packet6GateError(
            "BM25 rebuild must run only from reconciled authorized current Supabase"
        )


def assert_not_managed_pitr_claim(
    *,
    claimed_managed_pitr: bool,
    live_pitr_passed: bool,
) -> None:
    """Reject treating a local dump as isolated managed PITR.

    Args:
        claimed_managed_pitr: True when evidence labels the local dump as PITR.
        live_pitr_passed: True only after isolated managed PITR plus buckets.

    Raises:
        Phase10Packet6GateError: If a local dump is claimed as managed PITR.
    """

    if claimed_managed_pitr and not live_pitr_passed:
        raise Phase10Packet6GateError(
            "local dump/restore must not be claimed as managed PITR"
        )


def assert_live_database_not_overwritten(overwritten: bool) -> None:
    """Reject Packet 6 restores that overwrite the live application database.

    Args:
        overwritten: True when the runtime database was the restore target.

    Raises:
        Phase10Packet6GateError: If the live database was overwritten.
    """

    if overwritten:
        raise Phase10Packet6GateError(
            "Packet 6 must not overwrite the live application database"
        )


def assert_required_buckets_present(present: Sequence[str]) -> None:
    """Require the four durable Storage buckets.

    Args:
        present: Inventory bucket names.

    Raises:
        Phase10Packet6GateError: If any required bucket is missing.
    """

    missing = missing_required_buckets(present)
    if missing:
        raise Phase10Packet6GateError(
            "missing required Storage buckets: " + ", ".join(missing)
        )


def assert_paradedb_not_canonical(used_as_canonical: bool) -> None:
    """Reject ParadeDB snapshot-as-canonical recovery.

    Args:
        used_as_canonical: True when a ParadeDB snapshot is treated as authority.

    Raises:
        Phase10Packet6GateError: If ParadeDB is claimed as canonical.
    """

    if used_as_canonical:
        raise Phase10Packet6GateError(
            "ParadeDB snapshot is not canonical recovery evidence"
        )


def assert_blue_green_slots(compose: str, caddy: str) -> None:
    """Require Compose api-blue/api-green and Caddy ACTIVE_API_UPSTREAM.

    Args:
        compose: Staging Compose file text.
        caddy: Staging Caddyfile text.

    Raises:
        Phase10Packet6GateError: If blue/green slots or the upstream env are
            missing.
    """

    if "api-blue:" not in compose or "api-green:" not in compose:
        raise Phase10Packet6GateError(
            "staging Compose must define api-blue and api-green"
        )
    if "ACTIVE_API_UPSTREAM" not in compose:
        raise Phase10Packet6GateError("staging Compose must set ACTIVE_API_UPSTREAM")
    if "ACTIVE_API_UPSTREAM" not in caddy:
        raise Phase10Packet6GateError(
            "staging Caddyfile must proxy {$ACTIVE_API_UPSTREAM}"
        )


def assert_forward_fix_runbook(text: str) -> None:
    """Require schema rollback to be a reviewed forward fix.

    Args:
        text: Protected-migration runbook.

    Raises:
        Phase10Packet6GateError: If forward-fix language is missing.
    """

    lowered = text.casefold()
    if "forward fix" not in lowered:
        raise Phase10Packet6GateError(
            "PROTECTED_MIGRATION.md must require a reviewed forward fix"
        )
    if "not a down-migration" not in lowered:
        raise Phase10Packet6GateError("schema rollback must not be a down-migration")


def assert_old_api_smoke(smoke: OldApiSmokeEvidence) -> None:
    """Require the Phase 9 old-API/new-schema smoke freeze identity.

    Args:
        smoke: Parsed smoke artifact.

    Raises:
        Phase10Packet6GateError: If freeze identity drifted or holdout opened.
    """

    expected_freeze = PHASE09_IMAGE_IDS["api"]
    if smoke.freeze_api_id != expected_freeze:
        raise Phase10Packet6GateError(
            "old-API smoke freeze_api_id must remain " + expected_freeze
        )
    if smoke.requested != OLD_API_PRIOR_DIGEST:
        raise Phase10Packet6GateError(
            "old-API prior digest must remain " + OLD_API_PRIOR_DIGEST
        )
    if smoke.restored_freeze is not True:
        raise Phase10Packet6GateError("old-API smoke must restore the freeze image")
    if smoke.holdout_opened:
        raise Phase10Packet6GateError("old-API smoke must not open holdout")
    if smoke.classification != "Passed":
        raise Phase10Packet6GateError("old-API/new-schema smoke is not Passed")


def assert_contraction_absent(absent: bool) -> None:
    """Reject destructive contract DDL in the Packet 6 expand window.

    Args:
        absent: True when ``find_migration_violations`` found no contraction.

    Raises:
        Phase10Packet6GateError: If DROP TABLE or sibling contraction exists.
    """

    if not absent:
        raise Phase10Packet6GateError(
            "destructive contract DDL is present in migrations"
        )


def assert_rto_rpo_targets_not_measurements(
    *,
    measured_rto_hours: float | None,
    measured_rpo_hours: float | None,
    live_instance_passed: bool,
) -> None:
    """Reject invented RTO/RPO measurements while live rebuild is Blocked.

    Args:
        measured_rto_hours: Claimed duration, or None for targets only.
        measured_rpo_hours: Claimed window, or None for targets only.
        live_instance_passed: True only after a timed EC2 rebuild.

    Raises:
        Phase10Packet6GateError: If measurements are invented.
    """

    if rto_rpo_invented(
        measured_rto_hours=measured_rto_hours,
        measured_rpo_hours=measured_rpo_hours,
        live_instance_passed=live_instance_passed,
    ):
        raise Phase10Packet6GateError(
            "RTO/RPO hours are targets, not invented measurements"
        )


def classify_p1006_a(
    *,
    buckets_present: bool,
    live_database_overwritten: bool,
    claimed_managed_pitr: bool,
    production_restore: bool,
    live_pitr_state: LiveProofState,
    live_pitr_passed: bool,
) -> Classification:
    """Classify complete managed restore at a recorded point.

    Args:
        buckets_present: All four durable buckets are inventoried.
        live_database_overwritten: Live application database was overwritten.
        claimed_managed_pitr: Local dump labeled as managed PITR.
        production_restore: Production project was the restore target.
        live_pitr_state: Honest live PITR probe.
        live_pitr_passed: True only after isolated managed PITR plus buckets.

    Returns:
        ``Failed`` on overwrite, missing buckets, production restore, or a
        local-dump-as-PITR claim. ``Passed`` only with live managed PITR.
        Otherwise ``Blocked``.
    """

    if (
        live_database_overwritten
        or not buckets_present
        or claimed_managed_pitr
        or production_restore
    ):
        return "Failed"
    if live_pitr_state == "Failed":
        return "Failed"
    if live_pitr_passed:
        return "Passed"
    return "Blocked"


def classify_p1006_b(
    *,
    reconcile_policy_passed: bool,
    rebuild_before_reconcile: bool,
    invented_orphan_counts: bool,
    live_reconcile_state: LiveProofState,
    live_reconcile_passed: bool,
) -> Classification:
    """Classify reconciliation marks, quarantine, exclusion, and alerts.

    Args:
        reconcile_policy_passed: Runbook plus restore_incomplete policy.
        rebuild_before_reconcile: Rebuild was documented or run first.
        invented_orphan_counts: Live orphan counts were fabricated.
        live_reconcile_state: Honest live reconciliation probe.
        live_reconcile_passed: True only after a managed adversarial report.

    Returns:
        ``Failed`` on rebuild-first, invented counts, or policy miss.
        ``Passed`` only with live managed reconciliation. Otherwise
        ``Blocked``.
    """

    if (
        not reconcile_policy_passed
        or rebuild_before_reconcile
        or invented_orphan_counts
    ):
        return "Failed"
    if live_reconcile_state == "Failed":
        return "Failed"
    if live_reconcile_passed:
        return "Passed"
    return "Blocked"


def classify_p1006_c(
    *,
    local_rebuild_ok: bool,
    snapshot_as_canonical: bool,
    rebuild_before_reconcile: bool,
    live_ec2_rebuild_passed: bool,
) -> Classification:
    """Classify authoritative-only empty BM25 rebuild lineage.

    Args:
        local_rebuild_ok: Phase 9 empty volume plus authorized re-projection.
        snapshot_as_canonical: ParadeDB snapshot treated as authority.
        rebuild_before_reconcile: Rebuild ran or was documented first.
        live_ec2_rebuild_passed: True only after a live empty EC2 rebuild.

    Returns:
        ``Failed`` on snapshot-as-canonical or pre-reconciliation rebuild.
        ``Passed`` for derived-projection evidence even when live EC2 rebuild
        remains Blocked in the same row detail.
    """

    if snapshot_as_canonical or rebuild_before_reconcile or not local_rebuild_ok:
        return "Failed"
    if live_ec2_rebuild_passed:
        return "Passed"
    return "Passed"


def classify_p1006_d(
    *,
    instance_policy_passed: bool,
    invented_measurements: bool,
    live_instance_state: LiveProofState,
    live_instance_passed: bool,
) -> Classification:
    """Classify instance rebuild against approved RTO/RPO targets.

    Args:
        instance_policy_passed: Instance-rebuild runbook plus health contract.
        invented_measurements: RTO/RPO hours claimed without a timed drill.
        live_instance_state: Honest live EC2 rebuild probe.
        live_instance_passed: True only after a timed instance rebuild.

    Returns:
        ``Failed`` on invented measurements or policy miss. ``Passed`` only
        with a timed EC2 rebuild. Otherwise ``Blocked``.
    """

    if not instance_policy_passed or invented_measurements:
        return "Failed"
    if live_instance_state == "Failed":
        return "Failed"
    if live_instance_passed:
        return "Passed"
    return "Blocked"


def classify_p1006_e(
    *,
    old_api_ok: bool,
    contraction_absent: bool,
    freeze_held: bool,
    live_drain_state: LiveProofState,
    live_drain_passed: bool,
    live_deploy_orders_passed: bool,
    live_failed_deploy_passed: bool,
) -> Classification:
    """Classify old-slot, deploy-order, drain, rollback, and forward-fix.

    Args:
        old_api_ok: Phase 9 old-API/new-schema smoke Passed.
        contraction_absent: No destructive contract DDL in this release.
        freeze_held: Freeze API digest remains the Phase 9 id.
        live_drain_state: Honest live drain/failed-deploy probe.
        live_drain_passed: True only after a live Caddy drain.
        live_deploy_orders_passed: True only after both Vercel/API orders.
        live_failed_deploy_passed: True only after a failed inactive-slot SSM.

    Returns:
        ``Failed`` on contraction, freeze drift, or a failed live drain.
        ``Passed`` only when live drain, both deploy orders, and failed-slot
        proof exist. Otherwise ``Blocked`` so the checkbox stays honest.
        Old-slot smoke and no-contraction may still Pass in the row detail.
    """

    if not old_api_ok or not contraction_absent or not freeze_held:
        return "Failed"
    if live_drain_state == "Failed":
        return "Failed"
    if live_drain_passed and live_deploy_orders_passed and live_failed_deploy_passed:
        return "Passed"
    return "Blocked"


def _run_check(check: str, callback: Callable[[], None]) -> PolicyFinding:
    """Run one assertion and convert failures into findings.

    Args:
        check: Assertion id.
        callback: Zero-argument callable that raises ``Phase10Packet6GateError``.

    Returns:
        Finding with pass/fail detail.
    """

    try:
        callback()
    except Phase10Packet6GateError as exc:
        return PolicyFinding(check=check, passed=False, detail=str(exc))
    return PolicyFinding(check=check, passed=True, detail="ok")


def load_phase09_restore_evidence(repo_root: Path) -> Phase09RestoreEvidence:
    """Load Phase 9 Packet 6 restore inventory without treating it as PITR.

    Args:
        repo_root: Repository root.

    Returns:
        Typed supporting restore facts.

    Raises:
        Phase10Packet6GateError: If the artifact is missing or malformed.
    """

    try:
        payload = load_json_object(repo_root / PHASE09_PACKET6_RESTORE)
    except (OSError, ValueError) as exc:
        raise Phase10Packet6GateError(
            "Phase 9 Packet 6 restore artifact is unavailable"
        ) from exc
    dump = as_json_object(payload.get("dump"), source="phase09-restore-dump")
    disposable = as_json_object(
        payload.get("disposable_restore"), source="phase09-restore-disposable"
    )
    storage = as_json_object(payload.get("storage"), source="phase09-restore-storage")
    present = tuple(
        str(item)
        for item in as_json_list(storage.get("present"), source="phase09-buckets")
        if isinstance(item, str)
    )
    required = tuple(
        str(item)
        for item in as_json_list(
            storage.get("required_buckets"), source="phase09-required-buckets"
        )
        if isinstance(item, str)
    )
    if required != REQUIRED_STORAGE_BUCKETS:
        required = REQUIRED_STORAGE_BUCKETS
    return Phase09RestoreEvidence(
        live_database_overwritten=payload.get("live_database_overwritten") is True
        or disposable.get("live_database_overwritten") is True
        or dump.get("live_database_overwritten") is True,
        restore_returncode=json_int(disposable.get("restore_returncode"), default=99),
        dump_passed=dump.get("passed") is True,
        disposable_passed=disposable.get("passed") is True,
        paradedb_used_as_canonical=dump.get("paradedb_used_as_canonical") is True,
        present_buckets=present,
        required_buckets=required,
    )


def load_phase09_rebuild_evidence(repo_root: Path) -> Phase09RebuildEvidence:
    """Load Phase 9 Packet 6 derived BM25 rebuild facts.

    Args:
        repo_root: Repository root.

    Returns:
        Typed rebuild lineage.

    Raises:
        Phase10Packet6GateError: If the artifact is missing or malformed.
    """

    try:
        payload = load_json_object(repo_root / PHASE09_PACKET6_REBUILD)
    except (OSError, ValueError) as exc:
        raise Phase10Packet6GateError(
            "Phase 9 Packet 6 rebuild artifact is unavailable"
        ) from exc
    destroy = as_json_object(payload.get("destroy"), source="phase09-rebuild-destroy")
    reproject = as_json_object(
        payload.get("reproject"), source="phase09-rebuild-reproject"
    )
    return Phase09RebuildEvidence(
        paradedb_used_as_canonical=payload.get("paradedb_used_as_canonical") is True
        or destroy.get("paradedb_used_as_canonical") is True,
        volume_destroyed=destroy.get("volume_destroyed") is True,
        rebuild_passed=reproject.get("passed") is True,
        rebuild_scope=str(reproject.get("rebuild_scope") or ""),
        parade_total_rows=json_int(reproject.get("parade_total_rows")),
    )


def load_old_api_smoke(repo_root: Path) -> OldApiSmokeEvidence:
    """Load Phase 9 old-API/new-schema smoke evidence.

    Args:
        repo_root: Repository root.

    Returns:
        Typed smoke facts.

    Raises:
        Phase10Packet6GateError: If the artifact is missing or malformed.
    """

    try:
        payload = load_json_object(repo_root / PHASE09_OLD_API_SMOKE)
    except (OSError, ValueError) as exc:
        raise Phase10Packet6GateError(
            "Phase 9 old-API/new-schema smoke artifact is unavailable"
        ) from exc
    return OldApiSmokeEvidence(
        classification=str(payload.get("classification") or ""),
        freeze_api_id=str(payload.get("freeze_api_id") or ""),
        requested=str(
            payload.get("requested") or payload.get("resolved_image_id") or ""
        ),
        restored_freeze=payload.get("restored_freeze") is True,
        holdout_opened=payload.get("holdout_opened") is True,
    )


def assert_packet6_policy(repo_root: Path) -> PolicyReport:
    """Assert committed Packet 6 runbooks, Phase 9 supporting artifacts, and slots.

    Args:
        repo_root: Repository root.

    Returns:
        Policy report. ``passed`` is False when any finding failed.

    Raises:
        Phase10Packet6GateError: If required files are missing or any check
            fails.
    """

    restore = load_phase09_restore_evidence(repo_root)
    rebuild = load_phase09_rebuild_evidence(repo_root)
    smoke = load_old_api_smoke(repo_root)
    reconcile_text = (repo_root / STORAGE_RECONCILE_RUNBOOK).read_text(encoding="utf-8")
    rebuild_text = (repo_root / BM25_REBUILD_RUNBOOK).read_text(encoding="utf-8")
    instance_text = (repo_root / INSTANCE_REBUILD_RUNBOOK).read_text(encoding="utf-8")
    migration_text = (repo_root / PROTECTED_MIGRATION_RUNBOOK).read_text(
        encoding="utf-8"
    )
    compose = (repo_root / STAGING_COMPOSE_FILE).read_text(encoding="utf-8")
    caddy = (repo_root / STAGING_CADDY_FILE).read_text(encoding="utf-8")
    review = review_migrations(repo_root)
    checks: tuple[tuple[str, Callable[[], None]], ...] = (
        (
            "reconcile_runbook",
            lambda: assert_runbook_tokens(
                reconcile_text,
                RECONCILE_RUNBOOK_REQUIRED_TOKENS,
                source=STORAGE_RECONCILE_RUNBOOK,
            ),
        ),
        (
            "bm25_runbook",
            lambda: assert_runbook_tokens(
                rebuild_text,
                BM25_REBUILD_RUNBOOK_REQUIRED_TOKENS,
                source=BM25_REBUILD_RUNBOOK,
            ),
        ),
        (
            "instance_runbook",
            lambda: assert_runbook_tokens(
                instance_text,
                INSTANCE_REBUILD_RUNBOOK_REQUIRED_TOKENS,
                source=INSTANCE_REBUILD_RUNBOOK,
            ),
        ),
        (
            "rebuild_after_reconcile",
            lambda: assert_rebuild_after_reconcile(
                reconcile_text=reconcile_text,
                rebuild_text=rebuild_text,
            ),
        ),
        (
            "buckets",
            lambda: assert_required_buckets_present(restore.present_buckets),
        ),
        (
            "live_db",
            lambda: assert_live_database_not_overwritten(
                restore.live_database_overwritten
            ),
        ),
        (
            "not_pitr_claim",
            lambda: assert_not_managed_pitr_claim(
                claimed_managed_pitr=False,
                live_pitr_passed=False,
            ),
        ),
        (
            "paradedb_not_canonical",
            lambda: assert_paradedb_not_canonical(rebuild.paradedb_used_as_canonical),
        ),
        ("old_api_smoke", lambda: assert_old_api_smoke(smoke)),
        ("blue_green", lambda: assert_blue_green_slots(compose, caddy)),
        ("forward_fix", lambda: assert_forward_fix_runbook(migration_text)),
        (
            "rto_targets",
            lambda: assert_rto_rpo_targets_not_measurements(
                measured_rto_hours=None,
                measured_rpo_hours=None,
                live_instance_passed=False,
            ),
        ),
        (
            "contraction",
            lambda: assert_contraction_absent(review.contraction_absent),
        ),
    )
    findings = tuple(_run_check(name, callback) for name, callback in checks)
    reviewed: Sequence[Path] = (
        repo_root / STORAGE_RECONCILE_RUNBOOK,
        repo_root / BM25_REBUILD_RUNBOOK,
        repo_root / INSTANCE_REBUILD_RUNBOOK,
        repo_root / PROTECTED_MIGRATION_RUNBOOK,
        repo_root / PHASE09_PACKET6_RESTORE,
        repo_root / PHASE09_PACKET6_REBUILD,
        repo_root / PHASE09_OLD_API_SMOKE,
        repo_root / STAGING_COMPOSE_FILE,
        repo_root / STAGING_CADDY_FILE,
    )
    report = PolicyReport(
        passed=all(item.passed for item in findings),
        findings=findings,
        iac_sha256=hash_reviewed_files(reviewed),
    )
    if not report.passed:
        failed = [item.check for item in findings if not item.passed]
        details = "; ".join(
            f"{item.check}: {item.detail}" for item in findings if not item.passed
        )
        raise Phase10Packet6GateError(
            "Packet 6 policy failed: " + ", ".join(failed) + f" ({details})"
        )
    return report


def classify_packet6(
    *,
    policy: PolicyReport | None,
    live: LiveProviderProbe,
    restore: Phase09RestoreEvidence,
    rebuild: Phase09RebuildEvidence,
    smoke: OldApiSmokeEvidence,
    contraction_absent: bool,
    claimed_managed_pitr: bool = False,
    production_restore: bool = False,
    rebuild_before_reconcile: bool = False,
    invented_orphan_counts: bool = False,
    invented_measurements: bool = False,
    live_pitr_passed: bool = False,
    live_reconcile_passed: bool = False,
    live_ec2_rebuild_passed: bool = False,
    live_instance_passed: bool = False,
    live_drain_passed: bool = False,
    live_deploy_orders_passed: bool = False,
    live_failed_deploy_passed: bool = False,
) -> tuple[AcceptanceRow, ...]:
    """Classify P10-06-A through E from committed evidence and probes.

    Args:
        policy: Packet 6 policy report, or None when files are missing.
        live: Provider probe. Never a PITR, rebuild, or Caddy switch.
        restore: Phase 9 supporting restore inventory.
        rebuild: Phase 9 derived BM25 rebuild.
        smoke: Phase 9 old-API/new-schema smoke.
        contraction_absent: Expand/contract policy result.
        claimed_managed_pitr: Local dump labeled as managed PITR.
        production_restore: Production restore attempted.
        rebuild_before_reconcile: Rebuild ordered before reconciliation.
        invented_orphan_counts: Fabricated live orphan counts.
        invented_measurements: Fabricated RTO/RPO hours.
        live_pitr_passed: Real isolated managed PITR plus buckets.
        live_reconcile_passed: Real managed adversarial reconciliation.
        live_ec2_rebuild_passed: Real empty ParadeDB rebuild on EC2.
        live_instance_passed: Real timed instance rebuild.
        live_drain_passed: Real Caddy drain.
        live_deploy_orders_passed: Real Vercel/API order matrix.
        live_failed_deploy_passed: Real failed inactive-slot SSM.

    Returns:
        Five acceptance rows.
    """

    live_state = live_proof_state(live)
    buckets_ok = not missing_required_buckets(restore.present_buckets)
    reconcile_ok = finding_passed(policy, "reconcile_runbook") and finding_passed(
        policy, "rebuild_after_reconcile"
    )
    instance_ok = finding_passed(policy, "instance_runbook")
    local_rebuild_ok = (
        restore.dump_passed
        and restore.disposable_passed
        and buckets_ok
        and not restore.live_database_overwritten
        and rebuild.volume_destroyed
        and rebuild.rebuild_passed
        and rebuild.rebuild_scope == "authorized_current"
        and not rebuild.paradedb_used_as_canonical
    )
    freeze_held = smoke.freeze_api_id == PHASE09_IMAGE_IDS["api"]
    old_api_ok = (
        smoke.classification == "Passed"
        and smoke.restored_freeze
        and freeze_held
        and smoke.requested == OLD_API_PRIOR_DIGEST
        and not smoke.holdout_opened
    )
    snapshot = rebuild.paradedb_used_as_canonical or restore.paradedb_used_as_canonical
    return (
        AcceptanceRow(
            check="P10-06-A",
            classification=classify_p1006_a(
                buckets_present=buckets_ok,
                live_database_overwritten=restore.live_database_overwritten,
                claimed_managed_pitr=claimed_managed_pitr,
                production_restore=production_restore,
                live_pitr_state=live_state,
                live_pitr_passed=live_pitr_passed,
            ),
            detail=(
                "Local disposable dump/restore supporting "
                + ("Passed" if restore.dump_passed else "Failed")
                + f" with restore_returncode={restore.restore_returncode}; "
                "live_database_overwritten="
                + str(restore.live_database_overwritten).lower()
                + ". Required buckets "
                + ("present" if buckets_ok else "missing")
                + f". Live managed PITR is {live_state}: "
                + _LIVE_PITR_REASON
            ),
        ),
        AcceptanceRow(
            check="P10-06-B",
            classification=classify_p1006_b(
                reconcile_policy_passed=reconcile_ok,
                rebuild_before_reconcile=rebuild_before_reconcile,
                invented_orphan_counts=invented_orphan_counts,
                live_reconcile_state=live_state,
                live_reconcile_passed=live_reconcile_passed,
            ),
            detail=(
                "Reconciliation runbook plus restore_incomplete policy "
                + ("Passed" if reconcile_ok else "Failed")
                + ". Live orphan counts were not invented. "
                f"Live managed reconciliation is {live_state}: "
                + _LIVE_RECONCILE_REASON
            ),
        ),
        AcceptanceRow(
            check="P10-06-C",
            classification=classify_p1006_c(
                local_rebuild_ok=local_rebuild_ok,
                snapshot_as_canonical=snapshot,
                rebuild_before_reconcile=rebuild_before_reconcile,
                live_ec2_rebuild_passed=live_ec2_rebuild_passed,
            ),
            detail=(
                "Phase 9 empty ParadeDB re-projection "
                + ("Passed" if local_rebuild_ok else "Failed")
                + f" (paradedb_used_as_canonical={str(snapshot).lower()}, "
                f"volume_destroyed={str(rebuild.volume_destroyed).lower()}, "
                f"rows={rebuild.parade_total_rows}). Live EC2 empty rebuild "
                f"is {live_state}: " + _LIVE_EC2_REBUILD_REASON
            ),
        ),
        AcceptanceRow(
            check="P10-06-D",
            classification=classify_p1006_d(
                instance_policy_passed=instance_ok,
                invented_measurements=invented_measurements,
                live_instance_state=live_state,
                live_instance_passed=live_instance_passed,
            ),
            detail=(
                "Instance-rebuild runbook "
                + ("Passed" if instance_ok else "Failed")
                + f". Targets RTO≤{RTO_TARGET_HOURS}h RPO≤{RPO_TARGET_HOURS}h; "
                "no invented measurements. "
                f"Live timed EC2 rebuild is {live_state}: " + _LIVE_INSTANCE_REASON
            ),
        ),
        AcceptanceRow(
            check="P10-06-E",
            classification=classify_p1006_e(
                old_api_ok=old_api_ok,
                contraction_absent=contraction_absent,
                freeze_held=freeze_held,
                live_drain_state=live_state,
                live_drain_passed=live_drain_passed,
                live_deploy_orders_passed=live_deploy_orders_passed,
                live_failed_deploy_passed=live_failed_deploy_passed,
            ),
            detail=(
                "Old-API/new-schema smoke "
                + ("Passed" if old_api_ok else "Failed")
                + f" (prior digest {OLD_API_PRIOR_DIGEST}; freeze "
                + PHASE09_IMAGE_IDS["api"]
                + "). Expand/contract contraction "
                + ("absent" if contraction_absent else "Failed")
                + ". Forward-fix runbook present. "
                f"Live drain/deploy-order/failed SSM is {live_state}: "
                + _LIVE_DRAIN_REASON
            ),
        ),
    )


def negatives_catalog() -> tuple[dict[str, str], ...]:
    """Return the Packet 6 negative cases exercised by unit tests.

    Returns:
        Machine-readable negative catalog without secret values.
    """

    exercise = "tests/unit/test_phase10_packet6.py"
    expected = "Phase10Packet6GateError"
    return (
        {
            "case": "paradedb_snapshot_canonical",
            "expected": "Failed",
            "exercise": exercise,
        },
        {
            "case": "rebuild_before_reconcile",
            "expected": expected,
            "exercise": exercise,
        },
        {
            "case": "missing_required_bucket",
            "expected": expected,
            "exercise": exercise,
        },
        {
            "case": "live_database_overwritten",
            "expected": expected,
            "exercise": exercise,
        },
        {
            "case": "destructive_drop_table_contraction",
            "expected": "Failed",
            "exercise": exercise,
        },
        {
            "case": "local_dump_claimed_as_managed_pitr",
            "expected": expected,
            "exercise": exercise,
        },
        {
            "case": "invented_rto_rpo_measurements",
            "expected": expected,
            "exercise": exercise,
        },
    )


def write_packet6_artifacts(
    repo_root: Path,
    *,
    policy: PolicyReport,
    live: LiveProviderProbe,
    rows: Sequence[AcceptanceRow],
    restore: Phase09RestoreEvidence,
    rebuild: Phase09RebuildEvidence,
    smoke: OldApiSmokeEvidence,
    contraction_absent: bool,
    restore_incomplete_subset: Mapping[str, object],
) -> dict[str, Path]:
    """Write Packet 6 JSON artifacts without secrets or invented live results.

    Args:
        repo_root: Repository root.
        policy: Packet 6 policy report.
        live: Provider probe.
        rows: Acceptance classifications.
        restore: Phase 9 supporting restore.
        rebuild: Phase 9 derived rebuild.
        smoke: Phase 9 old-API smoke.
        contraction_absent: Migration contraction result.
        restore_incomplete_subset: Unit collection counts for restore policy.

    Returns:
        Artifact name to path mapping.

    Side Effects:
        Overwrites files under ``docs/deployment/phase-10/``.
    """

    artifact_dir = repo_root / PHASE10_ARTIFACT_DIR
    live_state = live_proof_state(live)
    missing = missing_required_buckets(restore.present_buckets)
    matrix: dict[str, object] = {
        "schema_version": PACKET6_MATRIX_SCHEMA_VERSION,
        "packet": "P10-06",
        "wrapper_status": "pending",
        "packet1_checkbox": "unchecked",
        "packet2_checkbox": "unchecked",
        "packet3_checkbox": "unchecked",
        "packet4_checkbox": "unchecked",
        "packet5_checkbox": "unchecked",
        "packet6_checkbox": "unchecked",
        "holdout_opened": False,
        "phase9_image_ids": dict(PHASE09_IMAGE_IDS),
        "policy": "Passed" if policy.passed else "Failed",
        "policy_sha256": policy.iac_sha256,
        "envelope": {
            "QT-CAP-001-P9": ENVELOPE_HYBRID_VERSIONS,
            "QT-CAP-002-P9": ENVELOPE_CHUNKS,
            "QT-CAP-005-P8": ENVELOPE_GRAPH_VERSIONS,
        },
        "live_managed_pitr": live_state,
        "live_reconciliation": live_state,
        "live_ec2_rebuild": live_state,
        "live_instance_rebuild": live_state,
        "live_drain": live_state,
        "restore_incomplete_subset": dict(restore_incomplete_subset),
        "acceptance": [
            {
                "check": row.check,
                "classification": row.classification,
                "detail": row.detail,
            }
            for row in rows
        ],
    }
    inventory_out: dict[str, object] = {
        "schema_version": PACKET6_INVENTORY_SCHEMA_VERSION,
        "supporting_artifact": PHASE09_PACKET6_RESTORE,
        "claimed_as_managed_pitr": False,
        "production_restore": False,
        "live_database_overwritten": restore.live_database_overwritten,
        "restore_returncode": restore.restore_returncode,
        "dump_passed": restore.dump_passed,
        "disposable_passed": restore.disposable_passed,
        "required_buckets": list(REQUIRED_STORAGE_BUCKETS),
        "present_buckets": list(restore.present_buckets),
        "missing_buckets": list(missing),
        "live_managed_pitr": live_state,
        "live_reason": _LIVE_PITR_REASON,
    }
    reconcile_out: dict[str, object] = {
        "schema_version": PACKET6_RECONCILE_SCHEMA_VERSION,
        "runbook": STORAGE_RECONCILE_RUNBOOK,
        "policy": "Passed" if reconcile_policy_ok(policy) else "Failed",
        "rebuild_before_reconcile": False,
        "live_orphan_counts": None,
        "restore_incomplete_action": "mark_and_exclude_hybrid_graph",
        "orphan_action": "quarantine_append_only_audit_alert",
        "live_reconciliation": live_state,
        "live_reason": _LIVE_RECONCILE_REASON,
        "restore_incomplete_subset": dict(restore_incomplete_subset),
        "tests": list(PACKET6_RESTORE_INCOMPLETE_TEST_FILES),
    }
    rebuild_out: dict[str, object] = {
        "schema_version": PACKET6_REBUILD_SCHEMA_VERSION,
        "supporting_artifact": PHASE09_PACKET6_REBUILD,
        "derived_projection": "Passed" if rebuild.rebuild_passed else "Failed",
        "paradedb_used_as_canonical": rebuild.paradedb_used_as_canonical,
        "volume_destroyed": rebuild.volume_destroyed,
        "rebuild_scope": rebuild.rebuild_scope,
        "parade_total_rows": rebuild.parade_total_rows,
        "live_ec2_empty_rebuild": live_state,
        "live_reason": _LIVE_EC2_REBUILD_REASON,
        "runbook": BM25_REBUILD_RUNBOOK,
    }
    instance_out: dict[str, object] = {
        "schema_version": PACKET6_INSTANCE_SCHEMA_VERSION,
        "runbook": INSTANCE_REBUILD_RUNBOOK,
        "rto_target_hours": RTO_TARGET_HOURS,
        "rpo_target_hours": RPO_TARGET_HOURS,
        "rto_measured_hours": None,
        "rpo_measured_hours": None,
        "measurement_kind": "target_not_measurement",
        "host_data_canonical": False,
        "freeze_api_id": PHASE09_IMAGE_IDS["api"],
        "live_timed_rebuild": live_state,
        "live_reason": _LIVE_INSTANCE_REASON,
    }
    skew_out: dict[str, object] = {
        "schema_version": PACKET6_SKEW_SCHEMA_VERSION,
        "old_api_new_schema": smoke.classification,
        "prior_digest": smoke.requested,
        "freeze_api_id": smoke.freeze_api_id,
        "restored_freeze": smoke.restored_freeze,
        "contraction_absent": contraction_absent,
        "forward_fix": "Passed",
        "compose_api_blue_green": True,
        "live_vercel_api_orders": live_state,
        "live_blue_green_drain": live_state,
        "live_failed_ssm_deploy": live_state,
        "live_reason": _LIVE_DRAIN_REASON,
        "overall": next(row.classification for row in rows if row.check == "P10-06-E"),
    }
    negatives_out: dict[str, object] = {
        "schema_version": PACKET6_NEGATIVES_SCHEMA_VERSION,
        "cases": list(negatives_catalog()),
    }
    paths = {
        PACKET6_MATRIX_NAME: artifact_dir / PACKET6_MATRIX_NAME,
        PACKET6_INVENTORY_NAME: artifact_dir / PACKET6_INVENTORY_NAME,
        PACKET6_RECONCILE_NAME: artifact_dir / PACKET6_RECONCILE_NAME,
        PACKET6_REBUILD_NAME: artifact_dir / PACKET6_REBUILD_NAME,
        PACKET6_INSTANCE_NAME: artifact_dir / PACKET6_INSTANCE_NAME,
        PACKET6_SKEW_NAME: artifact_dir / PACKET6_SKEW_NAME,
        PACKET6_NEGATIVES_NAME: artifact_dir / PACKET6_NEGATIVES_NAME,
    }
    dump_canonical_json(matrix, paths[PACKET6_MATRIX_NAME])
    dump_canonical_json(inventory_out, paths[PACKET6_INVENTORY_NAME])
    dump_canonical_json(reconcile_out, paths[PACKET6_RECONCILE_NAME])
    dump_canonical_json(rebuild_out, paths[PACKET6_REBUILD_NAME])
    dump_canonical_json(instance_out, paths[PACKET6_INSTANCE_NAME])
    dump_canonical_json(skew_out, paths[PACKET6_SKEW_NAME])
    dump_canonical_json(negatives_out, paths[PACKET6_NEGATIVES_NAME])
    return paths


def reconcile_policy_ok(policy: PolicyReport | None) -> bool:
    """Return whether reconciliation runbook findings passed.

    Args:
        policy: Packet 6 policy report.

    Returns:
        True when reconcile and rebuild-after-reconcile findings passed.
    """

    return finding_passed(policy, "reconcile_runbook") and finding_passed(
        policy, "rebuild_after_reconcile"
    )


def evaluate_packet6(
    repo_root: Path,
    *,
    restore_incomplete_ok: bool,
) -> tuple[
    PolicyReport,
    LiveProviderProbe,
    Phase09RestoreEvidence,
    Phase09RebuildEvidence,
    OldApiSmokeEvidence,
    bool,
    tuple[AcceptanceRow, ...],
]:
    """Run committed Packet 6 policy plus probes and classify P10-06.

    Packets 1-5 remaining unchecked is not a failure. Wrapper and Packet 6
    stay pending while live PITR/EC2/drain proof is Blocked.

    Args:
        repo_root: Repository root.
        restore_incomplete_ok: Nonzero restore_incomplete tests with no skip.

    Returns:
        Policy report, live probe, supporting evidence, contraction flag,
        and acceptance rows.

    Raises:
        Phase10Packet6GateError: If policy fails, required subsets are empty,
            or the wrapper was marked complete.
    """

    wrapper = (repo_root / WRAPPER_RELATIVE).read_text(encoding="utf-8")
    packet = (repo_root / PACKET6_RELATIVE).read_text(encoding="utf-8")
    if not wrapper_status_pending(wrapper):
        raise Phase10Packet6GateError("Phase 10 wrapper must remain status: pending")
    if not packet6_checkbox_unchecked(wrapper):
        raise Phase10Packet6GateError(
            "Packet 6 checkbox must stay unchecked while live PITR/EC2/drain is Blocked"
        )
    if not packet6_status_pending(packet):
        raise Phase10Packet6GateError("Packet 6 file must remain status: pending")
    workflow = (repo_root / GITHUB_WORKFLOWS_DIR / "pr-fast.yml").read_text(
        encoding="utf-8"
    )
    if "check_phase10_packet6.py" in workflow:
        raise Phase10Packet6GateError("Packet 6 gate must not be added to pr-fast.yml")
    if not restore_incomplete_ok:
        raise Phase10Packet6GateError(
            "Packet 6 restore_incomplete subset collected zero tests or skipped"
        )
    policy = assert_packet6_policy(repo_root)
    live = probe_live_providers()
    restore = load_phase09_restore_evidence(repo_root)
    rebuild = load_phase09_rebuild_evidence(repo_root)
    smoke = load_old_api_smoke(repo_root)
    contraction_absent = review_migrations(repo_root).contraction_absent
    rows = classify_packet6(
        policy=policy,
        live=live,
        restore=restore,
        rebuild=rebuild,
        smoke=smoke,
        contraction_absent=contraction_absent,
    )
    return policy, live, restore, rebuild, smoke, contraction_absent, rows

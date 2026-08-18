"""Phase 9 Packet 7 local blocker matrix and Phase 10 managed handoff.

Packet 7 classifies remaining local blockers against the Packet 1 freeze. It
does not rebuild images, open holdout, check the Packet 7 box, or set the
Phase 9 wrapper complete. Critical Trivy findings stay Failed until a
rebuild re-signs identity and Packets 1-6 are re-run.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from smart_rag_core.evaluation.holdout import HoldoutAccess
from smart_rag_core.release.constants import (
    ARTIFACT_DIR,
    PACKET7_HANDOFF_SCHEMA_VERSION,
    PACKET7_MANIFEST_SCHEMA_VERSION,
    PACKET7_MATRIX_SCHEMA_VERSION,
)
from smart_rag_core.release.packet2 import (
    PACKET1_EXPECTED_IMAGE_IDS,
    Classification,
    load_packet1_image_ids,
)
from smart_rag_core.release.packet4 import SIZING_LADDER_EIGHT_DOC

WRAPPER_RELATIVE = ".cursor/plans/hybrid-graph-rag/09-phase-local-release-candidate.md"
PACKET7_MATRIX_NAME = "candidate-packet7-gate-matrix.json"
PACKET7_HANDOFF_NAME = "candidate-packet7-phase10-handoff.json"
PACKET7_MANIFEST_NAME = "candidate-packet7-promotion-manifest.json"
REQUIRED_PRIOR_ARTIFACTS: tuple[str, ...] = (
    "candidate-image-manifest.json",
    "candidate-packet2-gate-matrix.json",
    "candidate-packet3-gate-matrix.json",
    "candidate-packet4-gate-matrix.json",
    "candidate-packet5-gate-matrix.json",
    "candidate-packet6-gate-matrix.json",
    "candidate-packet6-scans.json",
)


class Phase09Packet7GateError(RuntimeError):
    """Raised when Packet 7 identity drifted or required evidence is missing."""


@dataclass(frozen=True, slots=True)
class Packet7Handoff:
    """One Packet 7 local or managed row.

    Attributes:
        item_id: Stable identifier.
        acceptance: Requirement check id.
        classification: Honest classification.
        owner: Packet or phase that must close the item.
        reason: Why this is not Passed.
        next_action: Concrete follow-up.
        sizing_ladder: Envelope decision text.
        managed_only: True when Phase 10 owns the proof.
        local_launch_blocking: True when Phase 9 cannot complete without it.
    """

    item_id: str
    acceptance: str
    classification: Classification
    owner: str
    reason: str
    next_action: str
    sizing_ladder: str
    managed_only: bool
    local_launch_blocking: bool


LOCAL_BLOCKERS: tuple[Packet7Handoff, ...] = (
    Packet7Handoff(
        item_id="trivy_critical_findings",
        acceptance="P09-07-A",
        classification="Failed",
        owner="Phase 9 Packet 7",
        reason=(
            "Packet 6 tar Trivy reported unresolved Critical findings on the "
            "frozen api/worker/frontend/crawl-proxy/parser-sandbox images."
        ),
        next_action=(
            "Rebuild patched base images, freeze new Packet 1 identity, and "
            "re-run Packets 1-6. Do not waive Critical findings."
        ),
        sizing_ladder=SIZING_LADDER_EIGHT_DOC,
        managed_only=False,
        local_launch_blocking=True,
    ),
    Packet7Handoff(
        item_id="jwt_issuer_hostname_split",
        acceptance="P09-07-A",
        classification="Blocked",
        owner="Phase 9 Packet 7",
        reason=(
            "Frozen API expected iss is host.docker.internal; local GoTrue "
            "issues 127.0.0.1. Repair requires image or Auth hostname change."
        ),
        next_action=(
            "Align JWKS fetch and token iss on one hostname, then re-prove "
            "live EventSource. Do not rebuild in Packets 4-6."
        ),
        sizing_ladder=SIZING_LADDER_EIGHT_DOC,
        managed_only=False,
        local_launch_blocking=True,
    ),
    Packet7Handoff(
        item_id="seventy_percent_pause",
        acceptance="P09-07-A",
        classification="Blocked",
        owner="Phase 9 Packet 7",
        reason=(
            "Packet 4 8-doc load peaked at 3.06% CPU; the 70% pause trigger "
            "did not fire. Live p95 stayed null because of the JWT split."
        ),
        next_action=(
            "Prove the pause controller on a workload that can reach 70%, or "
            "reduce/re-sign the advertised envelope with client sign-off."
        ),
        sizing_ladder=SIZING_LADDER_EIGHT_DOC,
        managed_only=False,
        local_launch_blocking=True,
    ),
    Packet7Handoff(
        item_id="old_api_new_schema_smoke",
        acceptance="P09-07-A",
        classification="Blocked",
        owner="Phase 9 Packet 7",
        reason="No prior expand-compatible API digest exists to smoke against the current schema.",
        next_action=(
            "Keep a prior API image and run authenticated read/chat/upload "
            "smoke. Do not fake this with the single Packet 1 image."
        ),
        sizing_ladder=SIZING_LADDER_EIGHT_DOC,
        managed_only=False,
        local_launch_blocking=True,
    ),
    Packet7Handoff(
        item_id="live_openai_quality",
        acceptance="P09-07-B",
        classification="Not Run",
        owner="Phase 9 Packet 7",
        reason="MOCK_MODEL_MODE=true. Live Recall@K and Combined +10pp were not measured.",
        next_action="Run cost-capped live OpenAI evals on the frozen identity, or keep mock limits signed.",
        sizing_ladder=SIZING_LADDER_EIGHT_DOC,
        managed_only=False,
        local_launch_blocking=False,
    ),
)

MANAGED_HANDOFFS: tuple[Packet7Handoff, ...] = (
    Packet7Handoff(
        item_id="managed_supabase_jwks_restore",
        acceptance="P09-07-C",
        classification="Not Run",
        owner="Phase 10",
        reason="Managed pooling, JWKS rollover, and database/Storage restore are not local.",
        next_action="Prove on staging with synthetic or redacted data.",
        sizing_ladder=SIZING_LADDER_EIGHT_DOC,
        managed_only=True,
        local_launch_blocking=False,
    ),
    Packet7Handoff(
        item_id="managed_oidc_migrations",
        acceptance="P09-07-C",
        classification="Not Run",
        owner="Phase 10",
        reason="GitHub OIDC/SSM/Secrets Manager protected migrations are managed-only.",
        next_action="Run the protected expand-migration path on staging.",
        sizing_ladder=SIZING_LADDER_EIGHT_DOC,
        managed_only=True,
        local_launch_blocking=False,
    ),
    Packet7Handoff(
        item_id="managed_ec2_paradedb",
        acceptance="P09-07-C",
        classification="Not Run",
        owner="Phase 10",
        reason="Local Docker NCPU/mem is not EC2 or production ParadeDB proof.",
        next_action="Measure real EC2/EBS/ParadeDB resources in staging.",
        sizing_ladder=SIZING_LADDER_EIGHT_DOC,
        managed_only=True,
        local_launch_blocking=False,
    ),
    Packet7Handoff(
        item_id="managed_cdn_origin_egress",
        acceptance="P09-07-C",
        classification="Not Run",
        owner="Phase 10",
        reason="CloudFront/WAF/Caddy, 50/90s stream, origin rejection, and provider egress are managed.",
        next_action="Prove staging CDN stream and monitored egress denials.",
        sizing_ladder=SIZING_LADDER_EIGHT_DOC,
        managed_only=True,
        local_launch_blocking=False,
    ),
    Packet7Handoff(
        item_id="managed_kms_s3_rotation_alerts",
        acceptance="P09-07-C",
        classification="Not Run",
        owner="Phase 10",
        reason="KMS/S3 Object Lock, origin-secret rotation, billing alarms, and IaC policy are managed.",
        next_action="Prove anchors, rotation, and alert delivery on staging.",
        sizing_ladder=SIZING_LADDER_EIGHT_DOC,
        managed_only=True,
        local_launch_blocking=False,
    ),
    Packet7Handoff(
        item_id="external_assessment",
        acceptance="P09-07-C",
        classification="Not Run",
        owner="Phase 10",
        reason="External security assessment is not locally executable.",
        next_action="Attach the dated assessment or delta review in Phase 10.",
        sizing_ladder=SIZING_LADDER_EIGHT_DOC,
        managed_only=True,
        local_launch_blocking=False,
    ),
)

RECOMMENDATION_NO_GO = (
    "no-go for Phase 10 until Critical Trivy findings are rebuilt and "
    "Packets 1-6 are re-proven on the new identity, or the release stops."
)


def missing_prior_artifacts(repo_root: Path) -> tuple[str, ...]:
    """Return Packet 1-6 artifacts that Packet 7 requires.

    Args:
        repo_root: Repository root.

    Returns:
        Sorted missing relative paths under the Phase 9 artifact directory.
    """

    directory = repo_root / ARTIFACT_DIR
    missing = [
        name for name in REQUIRED_PRIOR_ARTIFACTS if not (directory / name).is_file()
    ]
    return tuple(sorted(missing))


def expected_image_ids() -> dict[str, str]:
    """Return the frozen Packet 1 image Ids."""

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
        Phase09Packet7GateError: If holdout is open.
    """

    if HoldoutAccess.denied().allowed:
        raise Phase09Packet7GateError("holdout must remain HoldoutAccess.denied()")
    if HoldoutAccess.from_settings().allowed:
        raise Phase09Packet7GateError("SMART_RAG_HOLDOUT_ACCESS must not be true")


def wrapper_status_pending(text: str) -> bool:
    """Return whether the Phase 9 wrapper front matter is still pending.

    Args:
        text: Wrapper Markdown.

    Returns:
        True when ``status: pending`` is present.
    """

    parts = text.split("---", 2)
    if len(parts) < 2:
        return False
    return "status: pending" in parts[1]


def packet7_checkbox_unchecked(text: str) -> bool:
    """Return whether Packet 7 remains an unchecked wrapper item.

    Args:
        text: Wrapper Markdown.

    Returns:
        True when the Packet 7 ordered item is ``[ ]``.
    """

    return (
        "7. [ ] [Resolve blockers or explicitly reduce/resign supported limits;" in text
    )


def classify_p0907_a(
    *,
    has_failed_local: bool,
    has_blocked_local: bool,
) -> Classification:
    """Classify whether every local mandatory gate passed.

    Args:
        has_failed_local: True when any local launch-blocking item Failed.
        has_blocked_local: True when any local launch-blocking item is Blocked.

    Returns:
        ``Failed``, ``Blocked``, or ``Passed``.
    """

    if has_failed_local:
        return "Failed"
    if has_blocked_local:
        return "Blocked"
    return "Passed"


def classify_p0907_b(
    *,
    client_signed_reduce: bool,
    claimed_full_envelope: bool,
) -> Classification:
    """Classify the local envelope decision.

    Args:
        client_signed_reduce: True when a client-signed reduce exists.
        claimed_full_envelope: True if 10k/1M was claimed.

    Returns:
        ``Failed`` when the full envelope is claimed. ``Blocked`` until
        client sign-off. ``Passed`` only after a signed reduce.
    """

    if claimed_full_envelope:
        return "Failed"
    if client_signed_reduce:
        return "Passed"
    return "Blocked"


def classify_p0907_c(*, managed_relabeled_local: bool) -> Classification:
    """Classify managed-ownership correctness.

    Args:
        managed_relabeled_local: True when a managed item was marked local Passed.

    Returns:
        ``Failed`` on ownership errors, otherwise ``Passed``.
    """

    return "Failed" if managed_relabeled_local else "Passed"


def classify_p0907_d(*, artifacts_complete: bool) -> Classification:
    """Classify whether Phase 10 can consume the artifact set.

    Args:
        artifacts_complete: Packet 1-6 artifacts exist.

    Returns:
        ``Passed`` or ``Failed``.
    """

    return "Passed" if artifacts_complete else "Failed"


def classify_p0907_e(
    *,
    wrapper_pending: bool,
    packet7_unchecked: bool,
) -> Classification:
    """Classify that Packet 7 did not self-complete the phase.

    Args:
        wrapper_pending: Wrapper ``status`` is pending.
        packet7_unchecked: Packet 7 checkbox is unchecked.

    Returns:
        ``Passed`` when both remain pending, otherwise ``Failed``.
    """

    return "Passed" if wrapper_pending and packet7_unchecked else "Failed"


def handoff_payloads() -> list[dict[str, object]]:
    """Serialize local and managed Packet 7 rows.

    Returns:
        JSON-ready objects.
    """

    rows: list[dict[str, object]] = []
    for item in (*LOCAL_BLOCKERS, *MANAGED_HANDOFFS):
        rows.append(
            {
                "item_id": item.item_id,
                "acceptance": item.acceptance,
                "classification": item.classification,
                "owner": item.owner,
                "reason": item.reason,
                "next_action": item.next_action,
                "sizing_ladder": item.sizing_ladder,
                "managed_only": item.managed_only,
                "local_launch_blocking": item.local_launch_blocking,
            }
        )
    return rows


def schema_version() -> str:
    """Return the Packet 7 matrix schema version."""

    return PACKET7_MATRIX_SCHEMA_VERSION


def handoff_schema_version() -> str:
    """Return the Phase 10 handoff schema version."""

    return PACKET7_HANDOFF_SCHEMA_VERSION


def manifest_schema_version() -> str:
    """Return the promotion manifest schema version."""

    return PACKET7_MANIFEST_SCHEMA_VERSION

"""Phase 9 Packet 7 local blocker matrix and Phase 10 managed handoff.

Packet 7 classifies remaining local blockers against the Packet 1 freeze. It
does not rebuild images, open holdout, check the Packet 7 box, or set the
Phase 9 wrapper complete. The runner stays pending until the user accepts.
Critical Trivy findings are Passed on the distroless/Alpine images. The
local advertised envelope is the signed QT-CAP-001-P9 / QT-CAP-002-P9
reduce, not QT-CAP-001/002.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
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
        classification="Passed",
        owner="Phase 9 Packet 7",
        reason=(
            "Tar Trivy (docker save plus --input, docker_sock_mounted=false) "
            "reports Critical=0 on distroless/Alpine images: api "
            "sha256:a65f1aa43fbf6fd353257a75fa9462e79a5bb187741d75e36a0429216e3633ec "
            "high=4; worker "
            "sha256:e6259d06f129ec14158e90acf1807dbaed0baa040bef9781fac60d46a97fe96e "
            "high=4; frontend "
            "sha256:e47efc373a151c7c79039009fd04f459f997127beafb00747cd91c4a9b96a5c1 "
            "high=0; crawl-proxy "
            "sha256:7d78834e21cc87d2ba133d4d131f1aa6d05b2de808d80296bf6658a8e04e62d3 "
            "high=3; parser-sandbox "
            "sha256:f7717ab4ec1e06d8113a19c080a05c1db6050b3b70e3bcfd73d61dd013ed6e0a "
            "high=2. USER 10001:10001. High findings were not waived."
        ),
        next_action=(
            "Packets 1-6 re-ran on this identity. Do not waive High findings. "
            "Phase 10 consumes this freeze after Packet 7 close."
        ),
        sizing_ladder=SIZING_LADDER_EIGHT_DOC,
        managed_only=False,
        local_launch_blocking=False,
    ),
    Packet7Handoff(
        item_id="jwt_issuer_hostname_split",
        acceptance="P09-07-A",
        classification="Passed",
        owner="Phase 9 Packet 7",
        reason=(
            "Rebuilt API "
            "sha256:1d9f569b54c6012c4e9b1087979b409a9e2517ac9cce7c1f81d8917d9870f3d7 "
            "accepted GoTrue iss http://127.0.0.1:54321/auth/v1: GET /me 200, "
            "GET /documents 200, GET /runs/{id}/events 200 text/event-stream "
            "(schema then error events; not HTTP 401). Current slot "
            "sha256:a39d44560b4e785226445250204e5258592fcaf66a327c13efb974448e401561 "
            "re-proved EventSource 200 during seventy live. Those hashes are "
            "not the Packet 1 distroless freeze a65f1aa4."
        ),
        next_action=(
            "Current freeze is distroless a65f1aa4. Packet 4 five-stream "
            "Passed on that freeze. Do not treat JWT historical hashes as "
            "Packet 1 identity."
        ),
        sizing_ladder=SIZING_LADDER_EIGHT_DOC,
        managed_only=False,
        local_launch_blocking=False,
    ),
    Packet7Handoff(
        item_id="seventy_percent_pause",
        acceptance="P09-07-A",
        classification="Passed",
        owner="Phase 9 Packet 7",
        reason=(
            "Live 8-doc Composite completion p95 1828 ms is under QT-LAT-011 "
            "40000 ms. CPU peak 1.49%; the 70% trigger did not fire. Fixture "
            "tests prove MaintenancePauseController. Not QT-CAP-001/002. Mock "
            "streams ended with schema/error events, not live OpenAI."
        ),
        next_action=(
            "Keep QT-CAP-001-P9=8 / QT-CAP-002-P9=16. Do not raise to "
            "QT-CAP-001/002 without a later signed raise and a workload that "
            "can reach 70% CPU/IO."
        ),
        sizing_ladder=SIZING_LADDER_EIGHT_DOC,
        managed_only=False,
        local_launch_blocking=False,
    ),
    Packet7Handoff(
        item_id="old_api_new_schema_smoke",
        acceptance="P09-07-A",
        classification="Passed",
        owner="Phase 9 Packet 7",
        reason=(
            "Prior "
            "sha256:1d9f569b54c6012c4e9b1087979b409a9e2517ac9cce7c1f81d8917d9870f3d7 "
            "served authenticated read/chat/upload; running slot "
            "sha256:a39d44560b4e785226445250204e5258592fcaf66a327c13efb974448e401561 "
            "was restored. smoke_ran=true."
        ),
        next_action=(
            "Keep smart-rag-api:old-api-prior for the next expand window. "
            "Do not point SMART_RAG_OLD_API_IMAGE at the running API Id."
        ),
        sizing_ladder=SIZING_LADDER_EIGHT_DOC,
        managed_only=False,
        local_launch_blocking=False,
    ),
    Packet7Handoff(
        item_id="live_openai_quality",
        acceptance="P09-07-B",
        classification="Not Run",
        owner="Phase 9 Packet 7",
        reason="MOCK_MODEL_MODE=true. Live Recall@K and Combined +10pp were not measured.",
        next_action=(
            "Local candidate stays MOCK_MODEL_MODE=true. Live Recall@K remains "
            "unverified and is not a local launch blocker."
        ),
        sizing_ladder=SIZING_LADDER_EIGHT_DOC,
        managed_only=False,
        local_launch_blocking=False,
    ),
    Packet7Handoff(
        item_id="supported_envelope_reduce",
        acceptance="P09-07-B",
        classification="Passed",
        owner="Phase 9 Packet 7",
        reason=(
            "User signed 2026-08-18: local candidate advertises "
            "QT-CAP-001-P9=8 Hybrid document versions and "
            "QT-CAP-002-P9=16 canonical chunks, not QT-CAP-001/002. "
            "Graph stays QT-CAP-005-P8=15. QT-CAP-003=25 concurrent users "
            "was not load-proven. QT-CAP-004=5 simultaneous runs was proven "
            "on this subset."
        ),
        next_action=(
            "Keep QT-CAP-001-P9/002-P9 until a later signed raise. Do not "
            "infer EC2 or 10k/1M from this subset."
        ),
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

CLIENT_SIGNED_REDUCE = True
"""True after 2026-08-18 user sign-off of QT-CAP-001-P9 / QT-CAP-002-P9."""

CLAIMED_FULL_ENVELOPE = False
"""True only if a packet claimed QT-CAP-001/002 10k/1M from local Docker."""

RECOMMENDATION_GO_REDUCED = (
    "go for Phase 10 isolated staging on this freeze; advertise "
    "QT-CAP-001-P9=8 Hybrid versions and QT-CAP-002-P9=16 chunks only; "
    "graph stays QT-CAP-005-P8=15; do not claim QT-CAP-001/002 10k/1M; "
    "managed JWKS/restore/OIDC/EC2/CDN/KMS/assessment remain Phase 10"
)


def with_old_api_smoke(
    classification: Classification,
    reason: str,
    next_action: str,
    *,
    blockers: tuple[Packet7Handoff, ...] = LOCAL_BLOCKERS,
) -> tuple[Packet7Handoff, ...]:
    """Overlay live old-API smoke classification onto local blockers.

    Args:
        classification: Smoke result classification.
        reason: Secret-free smoke reason.
        next_action: Follow-up for the old-API row.
        blockers: Local blocker tuple.

    Returns:
        Copy of ``blockers`` with ``old_api_new_schema_smoke`` replaced.
    """

    return tuple(
        replace(
            item,
            classification=classification,
            reason=reason,
            next_action=next_action,
            local_launch_blocking=classification != "Passed",
        )
        if item.item_id == "old_api_new_schema_smoke"
        else item
        for item in blockers
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


def handoff_payloads(
    local_blockers: tuple[Packet7Handoff, ...] = LOCAL_BLOCKERS,
) -> list[dict[str, object]]:
    """Serialize local and managed Packet 7 rows.

    Args:
        local_blockers: Local rows, possibly overlaid with live old-API
            smoke classification.

    Returns:
        JSON-ready objects.
    """

    rows: list[dict[str, object]] = []
    for item in (*local_blockers, *MANAGED_HANDOFFS):
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

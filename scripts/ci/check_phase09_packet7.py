"""Record Phase 9 Packet 7 blocker classification without completing the phase."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from smart_rag_core.release.constants import (
    ARTIFACT_DIR,
    CANDIDATE_COMPOSE_FILE,
)
from smart_rag_core.release.io import dump_canonical_json, load_json_object
from smart_rag_core.release.packet4 import (
    Phase09Packet4GateError,
    assert_mock_model_mode,
)
from smart_rag_core.release.packet7 import (
    LOCAL_BLOCKERS,
    MANAGED_HANDOFFS,
    PACKET7_HANDOFF_NAME,
    PACKET7_MANIFEST_NAME,
    PACKET7_MATRIX_NAME,
    RECOMMENDATION_NO_GO,
    REQUIRED_PRIOR_ARTIFACTS,
    WRAPPER_RELATIVE,
    Phase09Packet7GateError,
    assert_holdout_sealed,
    classify_p0907_a,
    classify_p0907_b,
    classify_p0907_c,
    classify_p0907_d,
    classify_p0907_e,
    expected_image_ids,
    handoff_payloads,
    handoff_schema_version,
    load_packet1_images,
    manifest_schema_version,
    missing_prior_artifacts,
    packet7_checkbox_unchecked,
    schema_version,
    wrapper_status_pending,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _health() -> dict[str, object]:
    """Run ``phase09_candidate.py health``.

    Returns:
        Health command row.
    """

    completed = subprocess.run(
        [sys.executable, "scripts/phase09_candidate.py", "health"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return {
        "command": "scripts/phase09_candidate.py health",
        "returncode": completed.returncode,
    }


def _acceptance_class(matrix: dict[str, object], check: str) -> str | None:
    """Return one acceptance classification from a prior matrix.

    Args:
        matrix: Packet gate matrix.
        check: Acceptance id.

    Returns:
        Classification string, or ``None``.
    """

    rows = matrix.get("acceptance")
    if not isinstance(rows, list):
        return None
    for item in rows:
        if not isinstance(item, dict):
            continue
        if item.get("check") == check and isinstance(item.get("classification"), str):
            return str(item["classification"])
    return None


def main(argv: list[str] | None = None) -> int:
    """Classify Packet 7 blockers and refuse to complete the Phase 9 wrapper.

    Args:
        argv: Optional argument vector excluding the program name.

    Returns:
        ``0`` when C-E are not Failed and the wrapper stays pending.
        ``P09-07-A`` may be Failed (unresolved Critical Trivy).
    """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    try:
        missing = missing_prior_artifacts(REPO_ROOT)
        if missing:
            raise Phase09Packet7GateError(
                "Packet 7 missing prior artifacts: " + ", ".join(missing)
            )
        assert_holdout_sealed()
        try:
            assert_mock_model_mode(REPO_ROOT)
        except Phase09Packet4GateError as exc:
            raise Phase09Packet7GateError(str(exc)) from exc
        image_ids = load_packet1_images(REPO_ROOT)
        if image_ids != expected_image_ids():
            raise Phase09Packet7GateError("Packet 1 image Ids drifted")
        wrapper_text = (REPO_ROOT / WRAPPER_RELATIVE).read_text(encoding="utf-8")
        wrapper_pending = wrapper_status_pending(wrapper_text)
        packet7_open = packet7_checkbox_unchecked(wrapper_text)
        if not wrapper_pending or not packet7_open:
            raise Phase09Packet7GateError(
                "Packet 7 must not mark the wrapper complete or check itself"
            )
        artifact_dir = REPO_ROOT / ARTIFACT_DIR
        packet6 = load_json_object(artifact_dir / "candidate-packet6-gate-matrix.json")
        packet6_b = _acceptance_class(packet6, "P09-06-B")
        has_failed_local = packet6_b == "Failed" or any(
            item.classification == "Failed" and item.local_launch_blocking
            for item in LOCAL_BLOCKERS
        )
        has_blocked_local = any(
            item.classification == "Blocked" and item.local_launch_blocking
            for item in LOCAL_BLOCKERS
        )
        managed_relabeled = any(not item.managed_only for item in MANAGED_HANDOFFS)
        health = _health()
        acceptance = [
            {
                "check": "P09-07-A",
                "classification": classify_p0907_a(
                    has_failed_local=has_failed_local,
                    has_blocked_local=has_blocked_local,
                ),
                "detail": "Critical Trivy Failed; JWT/70%/old-API Blocked",
            },
            {
                "check": "P09-07-B",
                "classification": classify_p0907_b(
                    client_signed_reduce=False,
                    claimed_full_envelope=False,
                ),
                "detail": "Keep QT-CAP-005-P8=15; 10k/1M unsigned; no client reduce yet",
            },
            {
                "check": "P09-07-C",
                "classification": classify_p0907_c(
                    managed_relabeled_local=managed_relabeled
                ),
                "detail": "Managed JWKS/restore/OIDC/EC2/CDN/KMS/assessment stay Phase 10",
            },
            {
                "check": "P09-07-D",
                "classification": classify_p0907_d(artifacts_complete=not missing),
                "detail": "Packets 1-6 artifacts present for Phase 10 consumption",
            },
            {
                "check": "P09-07-E",
                "classification": classify_p0907_e(
                    wrapper_pending=wrapper_pending,
                    packet7_unchecked=packet7_open,
                ),
                "detail": "Wrapper status pending; Packet 7 checkbox unchecked",
            },
        ]
        recommendation = RECOMMENDATION_NO_GO
        matrix = {
            "schema_version": schema_version(),
            "compose_file": CANDIDATE_COMPOSE_FILE,
            "holdout_opened": False,
            "image_ids": image_ids,
            "image_rebuilt": False,
            "health": health,
            "acceptance": acceptance,
            "recommendation": recommendation,
            "wrapper_status": "pending",
            "packet7_checkbox": "unchecked",
        }
        handoff = {
            "schema_version": handoff_schema_version(),
            "items": handoff_payloads(),
            "recommendation": recommendation,
        }
        manifest = {
            "schema_version": manifest_schema_version(),
            "candidate_image_ids": image_ids,
            "compose_file": CANDIDATE_COMPOSE_FILE,
            "consumed_artifacts": [
                f"docs/deployment/phase-09/{name}" for name in REQUIRED_PRIOR_ARTIFACTS
            ],
            "rollback": (
                "Keep the Packet 1 freeze. Do not promote. Rebuild only after "
                "a new identity freeze and Packets 1-6 rerun."
            ),
            "recommendation": recommendation,
        }
        dump_canonical_json(matrix, artifact_dir / PACKET7_MATRIX_NAME)
        dump_canonical_json(handoff, artifact_dir / PACKET7_HANDOFF_NAME)
        dump_canonical_json(manifest, artifact_dir / PACKET7_MANIFEST_NAME)
        failed = [
            row["check"]
            for row in acceptance
            if row["check"] in {"P09-07-C", "P09-07-D", "P09-07-E"}
            and row.get("classification") == "Failed"
        ]
        if failed:
            raise Phase09Packet7GateError(
                "Packet 7 Failed checks: " + ", ".join(str(item) for item in failed)
            )
        if int(health["returncode"]) != 0:
            raise Phase09Packet7GateError("candidate health failed")
        print("phase09_packet7_recorded", flush=True)
        print(f"recommendation={recommendation}", flush=True)
        return 0
    except Phase09Packet7GateError as exc:
        sys.stderr.write(f"{exc}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

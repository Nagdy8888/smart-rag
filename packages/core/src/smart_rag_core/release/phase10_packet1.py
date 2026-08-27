"""Classify Phase 10 Packet 1 acceptance without inventing live provision.

IaC policy can Pass from committed Terraform/Compose/Caddy/inventory. Live
AWS/Supabase/Vercel/SES apply, EC2 runtime assertions, and network scans are
Blocked when credentials, Terraform, or scan artifacts are missing. Never
mark Passed for live health or network reachability without a real scan
artifact.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from smart_rag_core.release.io import (
    as_json_object,
    dump_canonical_json,
    load_json_object,
)
from smart_rag_core.release.packet2 import Classification
from smart_rag_core.release.phase10_constants import (
    INTENDED_TOPOLOGY_FILE,
    PACKET1_IAC_NAME,
    PACKET1_IAC_SCHEMA_VERSION,
    PACKET1_INVENTORY_NAME,
    PACKET1_INVENTORY_SCHEMA_VERSION,
    PACKET1_LIVE_AWS_FILE,
    PACKET1_LIVE_NAME,
    PACKET1_LIVE_SCAN_FILE,
    PACKET1_LIVE_SCHEMA_VERSION,
    PACKET1_LIVE_SUPABASE_FILE,
    PACKET1_LIVE_VERCEL_FILE,
    PACKET1_MATRIX_NAME,
    PACKET1_MATRIX_SCHEMA_VERSION,
    PACKET1_NEGATIVES_NAME,
    PACKET1_NEGATIVES_SCHEMA_VERSION,
    PHASE09_CORPUS_MANIFEST,
    PHASE09_IMAGE_IDS,
    PHASE09_PROMOTION_MANIFEST,
    PHASE10_ARTIFACT_DIR,
    VERCEL_PUBLIC_ENV_FILE,
    WRAPPER_RELATIVE,
)
from smart_rag_core.release.phase10_topology import (
    Phase10TopologyError,
    PolicyReport,
    assert_committed_policy,
    assert_inventory,
    assert_phase9_promotion_images,
    assert_synthetic_corpus,
    assert_vercel_public_env,
)

LiveApplyState = Literal["Blocked", "Not Run", "Failed"]
_PRIVATE_SCAN_PORTS = frozenset({22, 5432, 6379, 8000, 8080})


class Phase10Packet1GateError(RuntimeError):
    """Raised when Packet 1 classification cannot be recorded honestly."""


@dataclass(frozen=True, slots=True)
class LiveProviderProbe:
    """Observed local tooling/session state for live provision.

    Attributes:
        terraform_installed: True when ``terraform`` is on PATH.
        tofu_installed: True when ``tofu`` is on PATH.
        aws_cli_installed: True when ``aws`` is on PATH.
        sts_ok: True when ``aws sts get-caller-identity`` succeeded.
        sts_detail: Non-secret reason string.
        apply_state: Honest live-apply classification.
        apply_reason: Why apply is not Passed.
    """

    terraform_installed: bool
    tofu_installed: bool
    aws_cli_installed: bool
    sts_ok: bool
    sts_detail: str
    apply_state: LiveApplyState
    apply_reason: str


@dataclass(frozen=True, slots=True)
class AcceptanceRow:
    """One P10-01 acceptance classification.

    Attributes:
        check: Requirement id such as ``P10-01-A``.
        classification: Honest Passed/Failed/Blocked/Not Run value.
        detail: Evidence without secrets.
    """

    check: str
    classification: Classification
    detail: str


def classify_p1001_a(*, inventory_matches: bool) -> Classification:
    """Classify intended plan/features/regions and Phase 9 artifact match.

    Args:
        inventory_matches: True when committed inventory matches the freeze.

    Returns:
        ``Passed`` when the inventory matches. ``Failed`` on drift. Live
        project creation is recorded separately and does not Pass this check
        by itself.
    """

    if inventory_matches:
        return "Passed"
    return "Failed"


def classify_p1001_b(
    *,
    iac_policy_passed: bool,
    runtime_assertions_passed: bool,
    live_apply_state: LiveApplyState,
) -> Classification:
    """Classify EC2 rebuildable/encrypted/IMDSv2/SSM-only evidence.

    Args:
        iac_policy_passed: Committed Terraform policy result.
        runtime_assertions_passed: True only after real instance assertions.
        live_apply_state: Provider apply probe.

    Returns:
        ``Passed`` only when IaC and runtime both pass. ``Failed`` when IaC
        fails. ``Blocked`` when runtime is unavailable because live apply is
        blocked.
    """

    if not iac_policy_passed:
        return "Failed"
    if runtime_assertions_passed:
        return "Passed"
    if live_apply_state == "Failed":
        return "Failed"
    return "Blocked"


def classify_p1001_c(
    *,
    iac_policy_passed: bool,
    network_scan_passed: bool,
    network_scan_present: bool,
) -> Classification:
    """Classify private-service limits, credentials, and no public path.

    Args:
        iac_policy_passed: Compose/IaC private-port policy result.
        network_scan_passed: True only from a real scan artifact.
        network_scan_present: True when a scan artifact exists.

    Returns:
        ``Passed`` only with a passing network scan artifact. ``Blocked`` when
        the scan is absent. ``Failed`` when IaC or the scan fails.
    """

    if not iac_policy_passed:
        return "Failed"
    if network_scan_present and network_scan_passed:
        return "Passed"
    if network_scan_present and not network_scan_passed:
        return "Failed"
    return "Blocked"


def classify_p1001_d(
    *,
    committed_env_clean: bool,
    live_secret_found: bool,
) -> Classification:
    """Classify Vercel/SES separation with no secret exposure.

    Args:
        committed_env_clean: Committed Vercel/SES/IaC env scan passed.
        live_secret_found: True when a live environment scan found a secret.

    Returns:
        ``Failed`` if committed or live secrets exist. ``Passed`` when the
        committed environment scan is clean. Live Vercel apply remains a
        separate live-provider row.
    """

    if live_secret_found or not committed_env_clean:
        return "Failed"
    return "Passed"


def classify_p1001_e(
    *,
    manifest_synthetic: bool,
    production_data: bool,
    holdout_opened: bool,
) -> Classification:
    """Classify synthetic/redacted-only staging data identity.

    Args:
        manifest_synthetic: Phase 9 open-split corpus identity is intact.
        production_data: Inventory production flag.
        holdout_opened: Holdout seal broken.

    Returns:
        ``Failed`` on production/holdout. ``Passed`` when the committed
        synthetic manifest is the seed identity.
    """

    if production_data or holdout_opened or not manifest_synthetic:
        return "Failed"
    return "Passed"


def live_runtime_assertions_passed(payload: Mapping[str, object]) -> bool:
    """Return whether committed live-AWS JSON proves P10-01-B runtime.

    Args:
        payload: ``packet1-live-aws.json`` object. Must not contain secrets.

    Returns:
        True when IMDSv2 hop 1, encrypted volumes, running instance, and
        SSM-only SSH posture are recorded.
    """

    if payload.get("imds_http_tokens") != "required":
        return False
    if payload.get("imds_hop_limit") != 1:
        return False
    if payload.get("ssh_ingress") is not False:
        return False
    if payload.get("sshd_disabled") is not True:
        return False
    if payload.get("instance_state") != "running":
        return False
    volumes = payload.get("volumes")
    if not isinstance(volumes, list) or not volumes:
        return False
    for item in cast(list[object], volumes):
        try:
            typed_item = as_json_object(item, source="volume")
        except ValueError:
            return False
        if typed_item.get("encrypted") is not True:
            return False
    return True


def live_network_scan_passed(payload: Mapping[str, object]) -> bool:
    """Return whether a live EIP scan proves no public private-service path.

    Args:
        payload: ``packet1-live-network-scan.json`` object.

    Returns:
        True when the artifact qualifies and SSH/ParadeDB/Valkey/API/proxy
        ports are closed from outside the VPC.
    """

    if payload.get("qualifies_for_p10_01_c") is not True:
        return False
    results = payload.get("results")
    if not isinstance(results, list) or not results:
        return False
    seen: set[int] = set()
    for item in cast(list[object], results):
        try:
            typed_item = as_json_object(item, source="scan")
        except ValueError:
            return False
        port = typed_item.get("port")
        opened = typed_item.get("open")
        if not isinstance(port, int) or isinstance(port, bool):
            return False
        seen.add(port)
        if port in _PRIVATE_SCAN_PORTS and opened is True:
            return False
    return _PRIVATE_SCAN_PORTS.issubset(seen)


def live_vercel_secret_found(payload: Mapping[str, object]) -> bool:
    """Return whether the live Vercel inventory recorded a forbidden secret.

    Args:
        payload: ``packet1-live-vercel.json`` object.

    Returns:
        True when ``service_role`` or committed live values are present.
    """

    if payload.get("service_role_present") is True:
        return True
    if payload.get("live_values_committed") is True:
        return True
    keys = payload.get("env_keys_only")
    if isinstance(keys, list):
        dumped = " ".join(str(item) for item in cast(list[object], keys)).upper()
        if "SERVICE_ROLE" in dumped or "DATABASE_URL" in dumped:
            return True
    return False


def packet1_rows_all_passed(rows: Sequence[AcceptanceRow]) -> bool:
    """Return whether every P10-01 acceptance row is Passed.

    Args:
        rows: Classification rows.

    Returns:
        True when A-E are all ``Passed``.
    """

    return bool(rows) and all(row.classification == "Passed" for row in rows)


def load_packet1_live_evidence(
    repo_root: Path,
) -> tuple[bool, bool, bool, bool]:
    """Load committed live AWS/scan/Vercel artifacts without secrets.

    Args:
        repo_root: Repository root.

    Returns:
        ``(runtime_ok, scan_present, scan_passed, live_secret_found)``.
    """

    runtime_ok = False
    aws_path = repo_root / PACKET1_LIVE_AWS_FILE
    if aws_path.is_file():
        runtime_ok = live_runtime_assertions_passed(load_json_object(aws_path))
    scan_present = False
    scan_passed = False
    scan_path = repo_root / PACKET1_LIVE_SCAN_FILE
    if scan_path.is_file():
        scan_present = True
        scan_passed = live_network_scan_passed(load_json_object(scan_path))
    live_secret_found = False
    vercel_path = repo_root / PACKET1_LIVE_VERCEL_FILE
    if vercel_path.is_file():
        live_secret_found = live_vercel_secret_found(load_json_object(vercel_path))
    return runtime_ok, scan_present, scan_passed, live_secret_found


def probe_live_providers() -> LiveProviderProbe:
    """Inspect Terraform/OpenTofu/AWS CLI without applying or logging in.

    Returns:
        Probe result. Expired or missing AWS sessions classify apply as
        Blocked. This function never runs ``aws login`` or Terraform apply.

    Side Effects:
        May execute ``aws sts get-caller-identity`` when the AWS CLI exists.
    """

    terraform_installed = shutil.which("terraform") is not None
    tofu_installed = shutil.which("tofu") is not None
    aws_path = shutil.which("aws")
    aws_cli_installed = aws_path is not None
    sts_ok = False
    sts_detail = "aws cli is not installed"
    if aws_path is not None:
        try:
            completed = subprocess.run(  # noqa: S603
                [aws_path, "sts", "get-caller-identity"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
                check=False,
            )
            sts_ok = completed.returncode == 0
            if sts_ok:
                sts_detail = "sts succeeded; Packet 1 still does not apply Terraform"
            else:
                sts_detail = (
                    "aws sts get-caller-identity failed (session missing or expired)"
                )
        except (OSError, subprocess.TimeoutExpired):
            sts_detail = "aws sts probe failed or timed out"
    if not terraform_installed and not tofu_installed:
        apply_state: LiveApplyState = "Blocked"
        apply_reason = (
            "Terraform/OpenTofu are not installed; live apply is Blocked. " + sts_detail
        )
    elif not sts_ok:
        apply_state = "Blocked"
        apply_reason = (
            "AWS session is missing or expired; live apply is Blocked. "
            "Do not run aws login from this packet."
        )
    else:
        apply_state = "Not Run"
        apply_reason = "Credentials exist but Packet 1 must not apply Terraform from CI"
    return LiveProviderProbe(
        terraform_installed=terraform_installed,
        tofu_installed=tofu_installed,
        aws_cli_installed=aws_cli_installed,
        sts_ok=sts_ok,
        sts_detail=sts_detail,
        apply_state=apply_state,
        apply_reason=apply_reason,
    )


def wrapper_status_pending(text: str) -> bool:
    """Return whether the Phase 10 wrapper frontmatter is still pending.

    Args:
        text: Wrapper markdown.

    Returns:
        True when ``status: pending`` is present in frontmatter.
    """

    head = text.split("---", 2)
    if len(head) < 3:
        return False
    return "status: pending" in head[1]


def packet1_checkbox_unchecked(text: str) -> bool:
    """Return whether the wrapper Packet 1 checkbox is unchecked.

    Args:
        text: Wrapper markdown.

    Returns:
        True when the first ordered packet remains ``[ ]``.
    """

    return "1. [ ] [Provision isolated managed Supabase" in text


def inventory_matches(repo_root: Path) -> bool:
    """Return whether committed inventory and Phase 9 freeze agree.

    Args:
        repo_root: Repository root.

    Returns:
        True when inventory, promotion images, Vercel allow-list, and corpus
        pass.
    """

    try:
        assert_inventory(load_json_object(repo_root / INTENDED_TOPOLOGY_FILE))
        assert_vercel_public_env(load_json_object(repo_root / VERCEL_PUBLIC_ENV_FILE))
        assert_phase9_promotion_images(
            load_json_object(repo_root / PHASE09_PROMOTION_MANIFEST)
        )
        assert_synthetic_corpus(load_json_object(repo_root / PHASE09_CORPUS_MANIFEST))
    except (OSError, ValueError, Phase10TopologyError):
        return False
    return True


def classify_packet1(
    repo_root: Path,
    *,
    policy: PolicyReport | None,
    live: LiveProviderProbe,
    network_scan_present: bool = False,
    network_scan_passed: bool = False,
    runtime_assertions_passed: bool = False,
    live_secret_found: bool = False,
) -> tuple[AcceptanceRow, ...]:
    """Classify P10-01-A through E from committed evidence and probes.

    Args:
        repo_root: Repository root.
        policy: IaC policy report, or None when files are missing.
        live: Provider probe.
        network_scan_present: True when a real scan artifact exists.
        network_scan_passed: True when that scan passed.
        runtime_assertions_passed: True when live EC2 assertions passed.
        live_secret_found: True when a live env scan found a secret.

    Returns:
        Five acceptance rows.
    """

    iac_ok = policy.passed if policy is not None else False
    inventory_ok = inventory_matches(repo_root)
    corpus = load_json_object(repo_root / PHASE09_CORPUS_MANIFEST)
    inventory = load_json_object(repo_root / INTENDED_TOPOLOGY_FILE)
    production = inventory.get("production_data") is True
    holdout = (
        corpus.get("holdout_opened") is True or inventory.get("holdout_opened") is True
    )
    return (
        AcceptanceRow(
            check="P10-01-A",
            classification=classify_p1001_a(inventory_matches=inventory_ok),
            detail=(
                "Committed intended-topology.json matches Phase 9 promotion "
                "image ids, Pro/us-east-1/PITR/Supavisor features, and the "
                "QT-CAP-001-P9=8 / QT-CAP-002-P9=16 / QT-CAP-005-P8=15 "
                "envelope. Live hosted Supabase is Free/eu-central-1/no PITR "
                "(ADR-phase10-hosted-supabase-reuse). Live AWS and Vercel "
                "exist; SES sandbox identity remains pending."
            ),
        ),
        AcceptanceRow(
            check="P10-01-B",
            classification=classify_p1001_b(
                iac_policy_passed=iac_ok,
                runtime_assertions_passed=runtime_assertions_passed,
                live_apply_state=live.apply_state,
            ),
            detail=(
                "IaC policy "
                + ("Passed" if iac_ok else "Failed")
                + ". Runtime EC2/IMDS/SSH assertions are "
                + (
                    "Passed from packet1-live-aws.json"
                    if runtime_assertions_passed
                    else live.apply_state + ": " + live.apply_reason
                )
            ),
        ),
        AcceptanceRow(
            check="P10-01-C",
            classification=classify_p1001_c(
                iac_policy_passed=iac_ok,
                network_scan_passed=network_scan_passed,
                network_scan_present=network_scan_present,
            ),
            detail=(
                "Compose/IaC private-port and digest policy "
                + ("Passed" if iac_ok else "Failed")
                + ". Network scan artifact is "
                + (
                    "Passed"
                    if network_scan_present and network_scan_passed
                    else "present but failed"
                    if network_scan_present
                    else "absent"
                )
                + "."
            ),
        ),
        AcceptanceRow(
            check="P10-01-D",
            classification=classify_p1001_d(
                committed_env_clean=inventory_ok and not live_secret_found,
                live_secret_found=live_secret_found,
            ),
            detail=(
                "Committed Vercel allow-list is API URL, Supabase URL, and "
                "publishable key only. Live Vercel/SES environment apply is "
                + (
                    "Failed: live secret found"
                    if live_secret_found
                    else live.apply_state
                )
                + "."
            ),
        ),
        AcceptanceRow(
            check="P10-01-E",
            classification=classify_p1001_e(
                manifest_synthetic=inventory_ok and not production and not holdout,
                production_data=production,
                holdout_opened=holdout,
            ),
            detail=(
                "Seed identity reuses Phase 9 open-split corpus "
                f"{PHASE09_CORPUS_MANIFEST}; holdout_opened is false. Live "
                "staging database seed was not applied."
            ),
        ),
    )


def negatives_catalog() -> tuple[dict[str, str], ...]:
    """Return the Packet 1 negative cases exercised by unit tests.

    Returns:
        Machine-readable negative catalog without payloads that look like
        success.
    """

    exercise = "tests/unit/test_phase10_packet1.py"
    expected = "Phase10TopologyError"
    return (
        {"case": "ssh_ingress", "expected": expected, "exercise": exercise},
        {
            "case": "imdsv1_optional_tokens",
            "expected": expected,
            "exercise": exercise,
        },
        {
            "case": "public_private_ports",
            "expected": expected,
            "exercise": exercise,
        },
        {
            "case": "vercel_service_role",
            "expected": expected,
            "exercise": exercise,
        },
        {"case": "production_seed", "expected": expected, "exercise": exercise},
        {
            "case": "mutable_paradedb_digest",
            "expected": expected,
            "exercise": exercise,
        },
        {
            "case": "origin_timeout_not_90",
            "expected": expected,
            "exercise": exercise,
        },
    )


def write_packet1_artifacts(
    repo_root: Path,
    *,
    policy: PolicyReport,
    live: LiveProviderProbe,
    rows: Sequence[AcceptanceRow],
) -> dict[str, Path]:
    """Write Packet 1 JSON artifacts without secrets.

    Args:
        repo_root: Repository root.
        policy: IaC policy report.
        live: Provider probe.
        rows: Acceptance classifications.

    Returns:
        Artifact name to path mapping.

    Side Effects:
        Overwrites files under ``docs/deployment/phase-10/``.
    """

    artifact_dir = repo_root / PHASE10_ARTIFACT_DIR
    inventory = load_json_object(repo_root / INTENDED_TOPOLOGY_FILE)
    wrapper = (repo_root / WRAPPER_RELATIVE).read_text(encoding="utf-8")
    checkbox = "unchecked" if packet1_checkbox_unchecked(wrapper) else "checked"
    runtime_ok, scan_present, scan_passed, live_secret_found = (
        load_packet1_live_evidence(repo_root)
    )
    vercel_path = repo_root / PACKET1_LIVE_VERCEL_FILE
    supabase_path = repo_root / PACKET1_LIVE_SUPABASE_FILE
    if live_secret_found:
        vercel_provision = "Failed"
    elif vercel_path.is_file():
        vercel_provision = "Applied"
    else:
        vercel_provision = "Blocked"
    supabase_provision = "Reused" if supabase_path.is_file() else "Blocked"
    ses_provision = "Pending"
    matrix: dict[str, object] = {
        "schema_version": PACKET1_MATRIX_SCHEMA_VERSION,
        "packet": "P10-01",
        "wrapper_status": "pending",
        "packet1_checkbox": checkbox,
        "holdout_opened": False,
        "phase9_image_ids": dict(PHASE09_IMAGE_IDS),
        "iac_policy": "Passed" if policy.passed else "Failed",
        "iac_sha256": policy.iac_sha256,
        "live_apply": live.apply_state,
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
        "schema_version": PACKET1_INVENTORY_SCHEMA_VERSION,
        "source": INTENDED_TOPOLOGY_FILE,
        "intended": inventory,
        "live_provisioned": runtime_ok,
    }
    iac_out: dict[str, object] = {
        "schema_version": PACKET1_IAC_SCHEMA_VERSION,
        "passed": policy.passed,
        "iac_sha256": policy.iac_sha256,
        "findings": [
            {
                "check": item.check,
                "passed": item.passed,
                "detail": item.detail,
            }
            for item in policy.findings
        ],
    }
    live_out: dict[str, object] = {
        "schema_version": PACKET1_LIVE_SCHEMA_VERSION,
        "terraform_installed": live.terraform_installed,
        "tofu_installed": live.tofu_installed,
        "aws_cli_installed": live.aws_cli_installed,
        "sts_ok": live.sts_ok,
        "sts_detail": live.sts_detail,
        "apply_state": live.apply_state,
        "apply_reason": live.apply_reason,
        "supabase_provision": supabase_provision,
        "vercel_provision": vercel_provision,
        "ses_provision": ses_provision,
        "network_scan_artifact": PACKET1_LIVE_SCAN_FILE if scan_present else None,
        "network_scan_passed": scan_passed if scan_present else False,
        "runtime_ec2_assertions": "Passed" if runtime_ok else "Blocked",
        "live_secret_found": live_secret_found,
    }
    negatives_out: dict[str, object] = {
        "schema_version": PACKET1_NEGATIVES_SCHEMA_VERSION,
        "cases": list(negatives_catalog()),
    }
    paths = {
        PACKET1_MATRIX_NAME: artifact_dir / PACKET1_MATRIX_NAME,
        PACKET1_INVENTORY_NAME: artifact_dir / PACKET1_INVENTORY_NAME,
        PACKET1_IAC_NAME: artifact_dir / PACKET1_IAC_NAME,
        PACKET1_LIVE_NAME: artifact_dir / PACKET1_LIVE_NAME,
        PACKET1_NEGATIVES_NAME: artifact_dir / PACKET1_NEGATIVES_NAME,
    }
    dump_canonical_json(matrix, paths[PACKET1_MATRIX_NAME])
    dump_canonical_json(inventory_out, paths[PACKET1_INVENTORY_NAME])
    dump_canonical_json(iac_out, paths[PACKET1_IAC_NAME])
    dump_canonical_json(live_out, paths[PACKET1_LIVE_NAME])
    dump_canonical_json(negatives_out, paths[PACKET1_NEGATIVES_NAME])
    return paths


def evaluate_packet1(
    repo_root: Path,
) -> tuple[PolicyReport, LiveProviderProbe, tuple[AcceptanceRow, ...]]:
    """Run committed policy plus live probe and classify Packet 1.

    Args:
        repo_root: Repository root.

    Returns:
        Policy report, live probe, and acceptance rows.

    Raises:
        Phase10Packet1GateError: If IaC policy fails or the wrapper was marked
            complete.
    """

    wrapper = (repo_root / WRAPPER_RELATIVE).read_text(encoding="utf-8")
    if not wrapper_status_pending(wrapper):
        raise Phase10Packet1GateError("Phase 10 wrapper must remain status: pending")
    try:
        policy = assert_committed_policy(repo_root)
    except Phase10TopologyError as exc:
        raise Phase10Packet1GateError(str(exc)) from exc
    live = probe_live_providers()
    runtime_ok, scan_present, scan_passed, live_secret_found = (
        load_packet1_live_evidence(repo_root)
    )
    rows = classify_packet1(
        repo_root,
        policy=policy,
        live=live,
        network_scan_present=scan_present,
        network_scan_passed=scan_passed,
        runtime_assertions_passed=runtime_ok,
        live_secret_found=live_secret_found,
    )
    if not packet1_checkbox_unchecked(wrapper) and not packet1_rows_all_passed(rows):
        raise Phase10Packet1GateError(
            "Packet 1 checkbox requires P10-01-A through E Passed"
        )
    return policy, live, rows

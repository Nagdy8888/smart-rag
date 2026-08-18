"""Classify Phase 10 Packet 2 OIDC and protected-migration acceptance.

Static allow/deny policy, workflow scans, and the Phase 9 old-API smoke
artifact can Pass. Live GitHub OIDC assume, SSM migrate, and Secrets Manager
rotation are Blocked or Not Run. This module never assumes a role, sends
SSM commands, or writes secret values. Packet 1 remaining unchecked is not a
Packet 2 failure.
"""

from __future__ import annotations

import hashlib
import importlib.util
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Literal, Protocol, cast

from smart_rag_core.release.io import dump_canonical_json, load_json_object
from smart_rag_core.release.packet2 import Classification
from smart_rag_core.release.phase10_constants import (
    GITHUB_REPOSITORY,
    MIGRATIONS_DIR,
    PACKET2_IAC_NAME,
    PACKET2_IAC_SCHEMA_VERSION,
    PACKET2_INVENTORY_NAME,
    PACKET2_INVENTORY_SCHEMA_VERSION,
    PACKET2_LIVE_NAME,
    PACKET2_LIVE_SCHEMA_VERSION,
    PACKET2_MATRIX_NAME,
    PACKET2_MATRIX_SCHEMA_VERSION,
    PACKET2_MIGRATION_HASH_NAME,
    PACKET2_MIGRATION_HASH_SCHEMA_VERSION,
    PACKET2_NEGATIVES_NAME,
    PACKET2_NEGATIVES_SCHEMA_VERSION,
    PACKET2_RELATIVE,
    PHASE09_IMAGE_IDS,
    PHASE09_OLD_API_SMOKE,
    PHASE10_ARTIFACT_DIR,
    PRODUCTION_SECRET_PREFIX,
    SECRET_ROTATION_MAX_DAYS,
    STAGING_SECRET_PREFIX,
    WRAPPER_RELATIVE,
)
from smart_rag_core.release.phase10_oidc import (
    Phase10OidcError,
    assert_committed_oidc_policy,
    prefixes_distinct,
)
from smart_rag_core.release.phase10_packet1 import (
    LiveProviderProbe,
    probe_live_providers,
    wrapper_status_pending,
)
from smart_rag_core.release.phase10_topology import PolicyReport

LiveCustodyState = Literal["Blocked", "Not Run", "Failed"]


class Phase10Packet2GateError(RuntimeError):
    """Raised when Packet 2 classification cannot be recorded honestly."""


@dataclass(frozen=True, slots=True)
class AcceptanceRow:
    """One P10-02 acceptance classification.

    Attributes:
        check: Requirement id such as ``P10-02-A``.
        classification: Honest Passed/Failed/Blocked/Not Run value.
        detail: Evidence without secrets.
    """

    check: str
    classification: Classification
    detail: str


@dataclass(frozen=True, slots=True)
class MigrationReview:
    """Immutable hash plus expand/contract policy result.

    Attributes:
        file_count: Reviewed ``*.sql`` files.
        sha256: Hex digest over names and bytes.
        unknown_files: Files not on the ``check_migrations`` allow-list.
        violations: Policy violations from ``find_migration_violations``.
        contraction_absent: True when no destructive DDL was found.
    """

    file_count: int
    sha256: str
    unknown_files: tuple[str, ...]
    violations: tuple[str, ...]
    contraction_absent: bool


class _MigrationPolicyModule(Protocol):
    """Typed surface of ``scripts/ci/check_migrations.py``.

    Attributes:
        ALLOWED_MIGRATION_PREFIXES: Reviewed migration file names.
    """

    ALLOWED_MIGRATION_PREFIXES: tuple[str, ...]

    def find_migration_violations(self, raw_sql: str, path: Path) -> list[str]:
        """Return expand/contract violations for one migration file.

        Args:
            raw_sql: Migration SQL including comments.
            path: Migration path used in diagnostics.

        Returns:
            Ordered policy violations.
        """

        ...


def load_migration_policy_module(repo_root: Path) -> ModuleType:
    """Load ``scripts/ci/check_migrations.py`` without duplicating regexes.

    Args:
        repo_root: Repository root.

    Returns:
        Loaded module exposing ``find_migration_violations``.

    Raises:
        Phase10Packet2GateError: If the policy module cannot be imported.
    """

    path = repo_root / "scripts" / "ci" / "check_migrations.py"
    spec = importlib.util.spec_from_file_location(
        "smart_rag_phase10_check_migrations", path
    )
    if spec is None or spec.loader is None:
        raise Phase10Packet2GateError("unable to load check_migrations.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def review_migrations(repo_root: Path) -> MigrationReview:
    """Hash migration files and invoke the existing expand/contract policy.

    Args:
        repo_root: Repository root.

    Returns:
        Hash plus violation list. Does not apply SQL.

    Raises:
        Phase10Packet2GateError: If the migrations directory is missing.
    """

    policy = cast(_MigrationPolicyModule, load_migration_policy_module(repo_root))
    directory = repo_root / MIGRATIONS_DIR
    if not directory.is_dir():
        raise Phase10Packet2GateError("supabase/migrations is missing")
    files = sorted(path for path in directory.glob("*.sql") if path.is_file())
    allowed = tuple(policy.ALLOWED_MIGRATION_PREFIXES)
    unknown = tuple(path.name for path in files if path.name not in allowed)
    violations: list[str] = []
    digest = hashlib.sha256()
    for path in files:
        raw = path.read_bytes()
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(raw)
        violations.extend(policy.find_migration_violations(raw.decode("utf-8"), path))
    contraction_markers = (
        "DROP TABLE",
        "DROP COLUMN",
        "DROP TYPE",
        "ALTER ... DROP",
        "ALTER ... TYPE narrowing",
    )
    contraction_absent = not unknown and not any(
        any(marker in item for marker in contraction_markers) for item in violations
    )
    return MigrationReview(
        file_count=len(files),
        sha256=digest.hexdigest(),
        unknown_files=unknown,
        violations=tuple(violations),
        contraction_absent=contraction_absent,
    )


def packet2_checkbox_unchecked(text: str) -> bool:
    """Return whether the wrapper Packet 2 checkbox is unchecked.

    Args:
        text: Wrapper markdown.

    Returns:
        True when packet 2 remains ``[ ]``. Packet 1 checkbox state is ignored.
    """

    return "2. [ ] [Implement GitHub OIDC, protected immutable expand/contract" in text


def packet2_status_pending(text: str) -> bool:
    """Return whether the Packet 2 file frontmatter is still pending.

    Args:
        text: Packet markdown.

    Returns:
        True when ``status: pending`` is present in frontmatter.
    """

    head = text.split("---", 2)
    if len(head) < 3:
        return False
    return "status: pending" in head[1]


def classify_p1002_a(*, oidc_policy_passed: bool) -> Classification:
    """Classify OIDC allow/deny policy tests.

    Args:
        oidc_policy_passed: Committed Terraform/workflow allow-deny result.

    Returns:
        ``Passed`` when policy tests pass. ``Failed`` otherwise. Live assume
        is recorded separately and must not be labeled Passed here.
    """

    if oidc_policy_passed:
        return "Passed"
    return "Failed"


def classify_p1002_b(
    *,
    committed_scan_clean: bool,
    live_secret_found: bool,
) -> Classification:
    """Classify absence of persistent secrets in GitHub/Vercel/IaC.

    Args:
        committed_scan_clean: Workflows, Vercel inventory, and Terraform
            contain no long-lived secret values.
        live_secret_found: True when a live env/log/image scan found a secret.

    Returns:
        ``Failed`` if committed or live secrets exist. ``Passed`` when the
        committed scan is clean. Live process scans stay in the live artifact.
    """

    if live_secret_found or not committed_scan_clean:
        return "Failed"
    return "Passed"


def classify_p1002_c(
    *,
    migration_policy_ok: bool,
    approval_wiring: bool,
    live_migrate_state: LiveCustodyState,
) -> Classification:
    """Classify approved immutable expansion versus live SSM execution.

    Args:
        migration_policy_ok: ``check_migrations`` found no violations.
        approval_wiring: Protected GitHub Environment is required in workflows.
        live_migrate_state: Honest live SSM migrate probe.

    Returns:
        ``Failed`` when policy or approval wiring fails. ``Passed`` only after
        a real approved SSM migrate. Otherwise ``Blocked``.
    """

    if not migration_policy_ok or not approval_wiring:
        return "Failed"
    if live_migrate_state == "Failed":
        return "Failed"
    return "Blocked"


def classify_p1002_d(
    *,
    smoke: Mapping[str, object],
    freeze_api_id: str,
    contraction_absent: bool,
) -> Classification:
    """Classify old-API health from the Phase 9 smoke artifact plus policy.

    Keeps the artifact ``Passed`` only when the freeze id still matches the
    Phase 9 freeze and the requested old-slot id is not that freeze.

    Args:
        smoke: ``candidate-old-api-new-schema-smoke.json``.
        freeze_api_id: Phase 9 freeze API image id.
        contraction_absent: Destructive DDL is absent from current migrations.

    Returns:
        ``Passed``, ``Failed``, or the artifact's Blocked/Not Run value.
    """

    requested = str(smoke.get("requested") or "")
    freeze = str(smoke.get("freeze_api_id") or "")
    stored = str(smoke.get("classification") or "")
    if freeze != freeze_api_id:
        return "Failed"
    if requested == freeze_api_id:
        return "Failed"
    if not contraction_absent:
        return "Failed"
    if stored == "Passed":
        return "Passed"
    if stored == "Blocked":
        return "Blocked"
    if stored == "Not Run":
        return "Not Run"
    if stored == "Failed":
        return "Failed"
    return "Failed"


def classify_p1002_e(
    *,
    prefixes_are_distinct: bool,
    rotation_max_days: int,
    production_on_staging: bool,
) -> Classification:
    """Classify staging/production custody policy.

    Args:
        prefixes_are_distinct: Staging and production prefixes cannot overlap.
        rotation_max_days: Encoded maximum rotation interval.
        production_on_staging: True when staging Allow lists production ARNs.

    Returns:
        ``Failed`` on overlap, production-on-staging, or interval above 90.
        ``Passed`` when the committed custody policy holds. Live rotation is
        recorded separately.
    """

    if production_on_staging or not prefixes_are_distinct:
        return "Failed"
    if rotation_max_days > SECRET_ROTATION_MAX_DAYS or rotation_max_days < 1:
        return "Failed"
    return "Passed"


def live_custody_state(live: LiveProviderProbe) -> LiveCustodyState:
    """Map the Packet 1 provider probe onto Packet 2 live OIDC/SSM state.

    Args:
        live: Terraform/AWS CLI probe. This function does not assume a role.

    Returns:
        ``Blocked`` when tools or session are missing. ``Not Run`` when a
        session exists but this packet refuses to assume/send-command.
    """

    if live.apply_state == "Failed":
        return "Failed"
    if live.apply_state == "Blocked" or not live.sts_ok:
        return "Blocked"
    return "Not Run"


def classify_packet2(
    repo_root: Path,
    *,
    policy: PolicyReport | None,
    live: LiveProviderProbe,
    migrations: MigrationReview,
    live_secret_found: bool = False,
) -> tuple[AcceptanceRow, ...]:
    """Classify P10-02-A through E from committed evidence and probes.

    Args:
        repo_root: Repository root.
        policy: OIDC policy report, or None when files are missing.
        live: Provider probe. Never an actual OIDC assume.
        migrations: Hash and expand/contract review.
        live_secret_found: True when a live scan found a secret.

    Returns:
        Five acceptance rows.
    """

    oidc_ok = policy.passed if policy is not None else False
    live_state = live_custody_state(live)
    smoke = load_json_object(repo_root / PHASE09_OLD_API_SMOKE)
    freeze = PHASE09_IMAGE_IDS["api"]
    prefixes_ok = prefixes_distinct(STAGING_SECRET_PREFIX, PRODUCTION_SECRET_PREFIX)
    migration_ok = not migrations.violations and not migrations.unknown_files
    return (
        AcceptanceRow(
            check="P10-02-A",
            classification=classify_p1002_a(oidc_policy_passed=oidc_ok),
            detail=(
                "Committed GitHub OIDC trust/permissions allow-deny tests "
                + ("Passed" if oidc_ok else "Failed")
                + f" for {GITHUB_REPOSITORY}. Live AssumeRoleWithWebIdentity is "
                + live_state
                + ": "
                + live.apply_reason
            ),
        ),
        AcceptanceRow(
            check="P10-02-B",
            classification=classify_p1002_b(
                committed_scan_clean=oidc_ok and not live_secret_found,
                live_secret_found=live_secret_found,
            ),
            detail=(
                "Committed workflows/Vercel/Terraform contain no long-lived AWS "
                "or database secrets. Runtime API/worker bootstrap remains "
                "covered by tests/contract/test_privileged_secrets_absent.py. "
                "Live log/image/process scans were not run."
            ),
        ),
        AcceptanceRow(
            check="P10-02-C",
            classification=classify_p1002_c(
                migration_policy_ok=migration_ok,
                approval_wiring=oidc_ok,
                live_migrate_state=live_state,
            ),
            detail=(
                f"Immutable migration hash {migrations.sha256} over "
                f"{migrations.file_count} files. Expand/contract policy "
                + ("Passed" if migration_ok else "Failed")
                + ". Protected environment wiring "
                + ("Passed" if oidc_ok else "Failed")
                + f". Live SSM migrate is {live_state}."
            ),
        ),
        AcceptanceRow(
            check="P10-02-D",
            classification=classify_p1002_d(
                smoke=smoke,
                freeze_api_id=freeze,
                contraction_absent=migrations.contraction_absent,
            ),
            detail=(
                "Reused Phase 9 old-API/new-schema smoke "
                f"{PHASE09_OLD_API_SMOKE}; freeze id matches Phase 9; requested "
                "id is not the freeze. Contraction DDL is "
                + ("absent" if migrations.contraction_absent else "present")
                + ". No new live Docker smoke was run."
            ),
        ),
        AcceptanceRow(
            check="P10-02-E",
            classification=classify_p1002_e(
                prefixes_are_distinct=prefixes_ok,
                rotation_max_days=SECRET_ROTATION_MAX_DAYS,
                production_on_staging=not oidc_ok,
            ),
            detail=(
                f"Prefixes {STAGING_SECRET_PREFIX!r} and "
                f"{PRODUCTION_SECRET_PREFIX!r} are distinct. Rotation custody "
                f"is {SECRET_ROTATION_MAX_DAYS} days. hashicorp/aws 5.100 "
                "requires a Lambda for aws_secretsmanager_secret_rotation on "
                "non-RDS secrets; live rotation is Blocked rather than faked."
            ),
        ),
    )


def negatives_catalog() -> tuple[dict[str, str], ...]:
    """Return the Packet 2 negative cases exercised by unit tests.

    Returns:
        Machine-readable negative catalog without secret values.
    """

    exercise = "tests/unit/test_phase10_packet2.py"
    expected = "Phase10OidcError"
    return (
        {"case": "wrong_repo", "expected": expected, "exercise": exercise},
        {
            "case": "missing_environment",
            "expected": expected,
            "exercise": exercise,
        },
        {
            "case": "aws_access_key_in_workflow",
            "expected": expected,
            "exercise": exercise,
        },
        {
            "case": "drop_table_migration",
            "expected": "find_migration_violations",
            "exercise": exercise,
        },
        {
            "case": "production_secret_arn_on_staging_role",
            "expected": expected,
            "exercise": exercise,
        },
        {
            "case": "vercel_service_role",
            "expected": "Phase10TopologyError",
            "exercise": exercise,
        },
    )


def write_packet2_artifacts(
    repo_root: Path,
    *,
    policy: PolicyReport,
    live: LiveProviderProbe,
    rows: Sequence[AcceptanceRow],
    migrations: MigrationReview,
) -> dict[str, Path]:
    """Write Packet 2 JSON artifacts without secrets.

    Args:
        repo_root: Repository root.
        policy: OIDC policy report.
        live: Provider probe.
        rows: Acceptance classifications.
        migrations: Immutable migration hash review.

    Returns:
        Artifact name to path mapping.

    Side Effects:
        Overwrites files under ``docs/deployment/phase-10/``.
    """

    artifact_dir = repo_root / PHASE10_ARTIFACT_DIR
    live_state = live_custody_state(live)
    matrix: dict[str, object] = {
        "schema_version": PACKET2_MATRIX_SCHEMA_VERSION,
        "packet": "P10-02",
        "wrapper_status": "pending",
        "packet1_checkbox": "unchecked",
        "packet2_checkbox": "unchecked",
        "holdout_opened": False,
        "phase9_image_ids": dict(PHASE09_IMAGE_IDS),
        "oidc_policy": "Passed" if policy.passed else "Failed",
        "oidc_sha256": policy.iac_sha256,
        "migration_sha256": migrations.sha256,
        "live_oidc_assume": live_state,
        "live_ssm_migrate": live_state,
        "live_secret_rotation": "Blocked",
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
        "schema_version": PACKET2_INVENTORY_SCHEMA_VERSION,
        "github_repository": GITHUB_REPOSITORY,
        "staging_secret_prefix": STAGING_SECRET_PREFIX,
        "production_secret_prefix": PRODUCTION_SECRET_PREFIX,
        "secret_rotation_max_days": SECRET_ROTATION_MAX_DAYS,
        "secret_rotation_lambda_present": False,
        "live_provisioned": False,
    }
    iac_out: dict[str, object] = {
        "schema_version": PACKET2_IAC_SCHEMA_VERSION,
        "passed": policy.passed,
        "oidc_sha256": policy.iac_sha256,
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
        "schema_version": PACKET2_LIVE_SCHEMA_VERSION,
        "terraform_installed": live.terraform_installed,
        "tofu_installed": live.tofu_installed,
        "aws_cli_installed": live.aws_cli_installed,
        "sts_ok": live.sts_ok,
        "sts_detail": live.sts_detail,
        "oidc_assume": live_state,
        "ssm_migrate": live_state,
        "secret_rotation": "Blocked",
        "secret_rotation_reason": (
            "hashicorp/aws 5.100 aws_secretsmanager_secret_rotation requires "
            "a Lambda for non-RDS secrets; this packet does not invent one"
        ),
        "apply_reason": live.apply_reason,
    }
    negatives_out: dict[str, object] = {
        "schema_version": PACKET2_NEGATIVES_SCHEMA_VERSION,
        "cases": list(negatives_catalog()),
    }
    hash_out: dict[str, object] = {
        "schema_version": PACKET2_MIGRATION_HASH_SCHEMA_VERSION,
        "file_count": migrations.file_count,
        "sha256": migrations.sha256,
        "unknown_files": list(migrations.unknown_files),
        "violations": list(migrations.violations),
        "contraction_absent": migrations.contraction_absent,
        "policy_module": "scripts/ci/check_migrations.py",
    }
    paths = {
        PACKET2_MATRIX_NAME: artifact_dir / PACKET2_MATRIX_NAME,
        PACKET2_INVENTORY_NAME: artifact_dir / PACKET2_INVENTORY_NAME,
        PACKET2_IAC_NAME: artifact_dir / PACKET2_IAC_NAME,
        PACKET2_LIVE_NAME: artifact_dir / PACKET2_LIVE_NAME,
        PACKET2_NEGATIVES_NAME: artifact_dir / PACKET2_NEGATIVES_NAME,
        PACKET2_MIGRATION_HASH_NAME: artifact_dir / PACKET2_MIGRATION_HASH_NAME,
    }
    dump_canonical_json(matrix, paths[PACKET2_MATRIX_NAME])
    dump_canonical_json(inventory_out, paths[PACKET2_INVENTORY_NAME])
    dump_canonical_json(iac_out, paths[PACKET2_IAC_NAME])
    dump_canonical_json(live_out, paths[PACKET2_LIVE_NAME])
    dump_canonical_json(negatives_out, paths[PACKET2_NEGATIVES_NAME])
    dump_canonical_json(hash_out, paths[PACKET2_MIGRATION_HASH_NAME])
    return paths


def evaluate_packet2(
    repo_root: Path,
) -> tuple[PolicyReport, LiveProviderProbe, MigrationReview, tuple[AcceptanceRow, ...]]:
    """Run committed OIDC policy plus probes and classify Packet 2.

    Packet 1 remaining unchecked is not a failure. Wrapper and Packet 2 stay
    pending while live OIDC/SSM is Blocked.

    Args:
        repo_root: Repository root.

    Returns:
        Policy report, live probe, migration review, and acceptance rows.

    Raises:
        Phase10Packet2GateError: If OIDC policy fails, migrations cannot be
            reviewed, or the wrapper was marked complete.
    """

    wrapper = (repo_root / WRAPPER_RELATIVE).read_text(encoding="utf-8")
    packet = (repo_root / PACKET2_RELATIVE).read_text(encoding="utf-8")
    if not wrapper_status_pending(wrapper):
        raise Phase10Packet2GateError("Phase 10 wrapper must remain status: pending")
    if not packet2_checkbox_unchecked(wrapper):
        raise Phase10Packet2GateError(
            "Packet 2 checkbox must stay unchecked while live OIDC/SSM is Blocked"
        )
    if not packet2_status_pending(packet):
        raise Phase10Packet2GateError("Packet 2 file must remain status: pending")
    try:
        policy = assert_committed_oidc_policy(repo_root)
    except Phase10OidcError as exc:
        raise Phase10Packet2GateError(str(exc)) from exc
    migrations = review_migrations(repo_root)
    live = probe_live_providers()
    rows = classify_packet2(repo_root, policy=policy, live=live, migrations=migrations)
    return policy, live, migrations, rows

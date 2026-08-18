"""Parse and assert Phase 10 Packet 2 OIDC, SSM, workflow, and secret policy.

Checks are static over committed Terraform, GitHub workflows, and SSM
documents. They do not assume a role, send SSM commands, or rotate secrets.
Fail closed on wrong repo, missing environment, ``repo:*``, ``ssm:*`` Allow,
``iam:*`` Allow, production secret ARNs on staging Allow, long-lived AWS keys
in workflows, secret values in git, and runtime ``CREATE EXTENSION``.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from smart_rag_core.release.io import load_json_object
from smart_rag_core.release.phase10_constants import (
    CHECKOUT_ACTION_PIN,
    CONFIGURE_AWS_CREDENTIALS_PIN,
    GITHUB_OIDC_AUDIENCE,
    GITHUB_OIDC_ISSUER,
    GITHUB_REPOSITORY,
    GITHUB_WORKFLOWS_DIR,
    INFRA_EC2_DIR,
    INTENDED_TOPOLOGY_FILE,
    LONG_LIVED_WORKFLOW_FRAGMENTS,
    PRODUCTION_MIGRATE_DOCUMENT,
    PRODUCTION_MIGRATE_WORKFLOW,
    PRODUCTION_OIDC_SUB,
    PRODUCTION_SECRET_PREFIX,
    SECRET_ROTATION_MAX_DAYS,
    SSM_DOCUMENTS_DIR,
    STAGING_DEPLOY_DOCUMENT,
    STAGING_DEPLOY_WORKFLOW,
    STAGING_MIGRATE_DOCUMENT,
    STAGING_MIGRATE_WORKFLOW,
    STAGING_OIDC_SUB,
    STAGING_SECRET_PREFIX,
    VERCEL_PUBLIC_ENV_FILE,
)
from smart_rag_core.release.phase10_topology import (
    Phase10TopologyError,
    PolicyFinding,
    PolicyReport,
    assert_no_vercel_secrets,
    hash_reviewed_files,
    load_terraform_bundle,
    strip_hcl_comments,
)

_STATEMENT_SPLIT = re.compile(r"statement\s*\{")
_CREATE_EXTENSION = re.compile(r"\bCREATE\s+EXTENSION\b", re.IGNORECASE)
_SECRET_VALUE_ASSIGN = re.compile(
    r"\b(secret_string|secret_binary)\s*=",
    re.IGNORECASE,
)


class Phase10OidcError(RuntimeError):
    """Raised when Packet 2 OIDC/SSM/workflow/secret policy fails."""


@dataclass(frozen=True, slots=True)
class WorkflowRecord:
    """One GitHub workflow file used by Packet 2 policy.

    Attributes:
        name: File name such as ``staging-migrate.yml``.
        text: Workflow YAML.
    """

    name: str
    text: str


def extract_named_block(hcl: str, keyword: str, type_name: str, name: str) -> str:
    """Return one Terraform ``resource`` or ``data`` block body.

    Args:
        hcl: Comment-stripped HCL.
        keyword: ``resource`` or ``data``.
        type_name: Terraform type such as ``aws_iam_policy_document``.
        name: Local name such as ``staging_oidc_migrate_trust``.

    Returns:
        Block body including nested braces, excluding the outer braces.

    Raises:
        Phase10OidcError: If the block is missing or braces are unbalanced.
    """

    header = f'{keyword} "{type_name}" "{name}"'
    start = hcl.find(header)
    if start < 0:
        raise Phase10OidcError(f"missing {keyword} {type_name}.{name}")
    brace = hcl.find("{", start)
    if brace < 0:
        raise Phase10OidcError(f"{keyword} {type_name}.{name} has no opening brace")
    depth = 0
    for index in range(brace, len(hcl)):
        char = hcl[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return hcl[brace + 1 : index]
    raise Phase10OidcError(f"{keyword} {type_name}.{name} has unbalanced braces")


def _statement_bodies(block: str) -> tuple[str, ...]:
    """Split an IAM policy document block into statement bodies.

    Args:
        block: Terraform ``aws_iam_policy_document`` body.

    Returns:
        Statement bodies in source order.
    """

    parts = _STATEMENT_SPLIT.split(block)
    return tuple(part for part in parts[1:] if part.strip())


def _is_deny_statement(statement: str) -> bool:
    """Return whether a statement sets ``effect = "Deny"``.

    Args:
        statement: One IAM statement body.

    Returns:
        True when the statement is an explicit Deny.
    """

    return bool(re.search(r'effect\s*=\s*"Deny"', statement))


def allow_statements(block: str) -> tuple[str, ...]:
    """Return Allow statements (default effect) from a policy document.

    Args:
        block: Terraform IAM policy document body.

    Returns:
        Allow statement bodies.
    """

    return tuple(
        statement
        for statement in _statement_bodies(block)
        if not _is_deny_statement(statement)
    )


def assert_oidc_trust(
    block: str,
    *,
    environment: str,
    workflow: str,
    repository: str = GITHUB_REPOSITORY,
) -> None:
    """Require deny-by-construction GitHub OIDC trust.

    Args:
        block: Trust policy document body.
        environment: ``staging`` or ``production``.
        workflow: Workflow file name the role may run.
        repository: Trusted ``owner/name``.

    Raises:
        Phase10OidcError: If repo, environment, audience, or workflow drift,
            or if ``repo:*`` / missing environment / cross-environment trust
            is present.
    """

    if "sts:AssumeRoleWithWebIdentity" not in block:
        raise Phase10OidcError("OIDC trust must use AssumeRoleWithWebIdentity")
    if GITHUB_OIDC_AUDIENCE not in block:
        raise Phase10OidcError("OIDC audience must be sts.amazonaws.com")
    if "repo:*" in block:
        raise Phase10OidcError("OIDC trust must not allow repo:*")
    expected_sub = f"repo:{repository}:environment:{environment}"
    if expected_sub not in block and f"environment:{environment}" not in block:
        raise Phase10OidcError(f"OIDC trust missing environment:{environment}")
    if re.search(r"repo:[^\"\s]+:ref:", block):
        raise Phase10OidcError("OIDC trust missing protected environment")
    workflow_ref = f"{repository}/.github/workflows/{workflow}@"
    workflow_var = f".github/workflows/{workflow}@"
    if workflow_ref not in block and workflow_var not in block:
        raise Phase10OidcError(f"OIDC trust missing job_workflow_ref for {workflow}")
    if environment == "staging" and "environment:production" in block:
        raise Phase10OidcError(
            "staging OIDC trust must not allow environment:production"
        )
    if environment == "production" and "environment:staging" in block:
        raise Phase10OidcError(
            "production OIDC trust must not allow environment:staging"
        )
    if repository not in block and "var.github_repository" not in block:
        raise Phase10OidcError(f"OIDC trust must pin repository {repository}")


def assert_no_star_allow(block: str, action_prefix: str) -> None:
    """Reject Allow statements that grant ``prefix:*``.

    Args:
        block: IAM policy document body.
        action_prefix: ``ssm`` or ``iam``.

    Raises:
        Phase10OidcError: If an Allow statement uses a star action.
    """

    needle = f"{action_prefix}:*"
    for statement in allow_statements(block):
        if needle in statement:
            raise Phase10OidcError(f"Allow {needle} is forbidden")


def assert_staging_permissions_deny_production(block: str) -> None:
    """Reject production secret ARNs on staging Allow statements.

    Args:
        block: Staging OIDC or instance IAM policy document.

    Raises:
        Phase10OidcError: If an Allow statement names the production prefix.
    """

    for statement in allow_statements(block):
        if PRODUCTION_SECRET_PREFIX in statement:
            raise Phase10OidcError("staging role must not Allow production secret ARNs")
    assert_no_star_allow(block, "ssm")
    assert_no_star_allow(block, "iam")


def assert_named_ssm_send(block: str, document_name: str) -> None:
    """Require ``ssm:SendCommand`` only for a named document.

    Args:
        block: OIDC permissions document.
        document_name: SSM document name such as ``SmartRagStagingMigrate``.

    Raises:
        Phase10OidcError: If SendCommand or the document name is missing.
    """

    if "ssm:SendCommand" not in block:
        raise Phase10OidcError("OIDC role must allow ssm:SendCommand")
    if document_name not in block:
        raise Phase10OidcError(f"OIDC role must target document {document_name}")
    assert_staging_permissions_deny_production(block)


def assert_github_oidc_provider(hcl: str, *, raw_hcl: str) -> None:
    """Require the GitHub OIDC issuer and STS audience.

    Args:
        hcl: Comment-stripped Terraform bundle.
        raw_hcl: Raw Terraform including URLs. Line-comment strippers treat
            ``//`` in ``https://`` as comments, so the issuer is read from
            raw HCL.

    Raises:
        Phase10OidcError: If the provider is missing or mis-scoped.
    """

    if "aws_iam_openid_connect_provider" not in hcl:
        raise Phase10OidcError("GitHub OIDC provider is missing")
    if GITHUB_OIDC_ISSUER not in raw_hcl:
        raise Phase10OidcError("GitHub OIDC issuer URL is missing")
    if GITHUB_OIDC_AUDIENCE not in hcl:
        raise Phase10OidcError("GitHub OIDC audience sts.amazonaws.com is missing")


def assert_secret_placeholders(hcl: str) -> None:
    """Require staging/production secret resources without values.

    Args:
        hcl: Comment-stripped Terraform bundle.

    Raises:
        Phase10OidcError: If prefixes are missing, overlap, or values are
            committed.
    """

    if STAGING_SECRET_PREFIX not in hcl:
        raise Phase10OidcError("staging secret prefix is missing")
    if PRODUCTION_SECRET_PREFIX not in hcl:
        raise Phase10OidcError("production secret prefix is missing")
    if _SECRET_VALUE_ASSIGN.search(hcl):
        raise Phase10OidcError("Secrets Manager values must not be committed")
    if "aws_secretsmanager_secret_version" in hcl:
        raise Phase10OidcError("secret versions with values are forbidden in git")
    if not re.search(r"secret_rotation_max_days\s*=\s*90\b", hcl):
        raise Phase10OidcError("90-day rotation custody local is missing")


def assert_ssm_document_text(text: str, *, secret_prefix: str | None) -> None:
    """Require redaction, EXIT unset, and no runtime CREATE EXTENSION.

    Args:
        text: SSM document YAML.
        secret_prefix: Expected Secrets Manager prefix, or None for deploy.

    Raises:
        Phase10OidcError: If lifecycle, redaction, or DDL policy fails.
    """

    lowered = text.lower()
    if "trap" not in lowered or "unset" not in lowered:
        raise Phase10OidcError("SSM document must unset process env on EXIT")
    if secret_prefix is not None and secret_prefix not in text:
        raise Phase10OidcError(f"SSM migrate document must fetch {secret_prefix}")
    if secret_prefix is not None and "redact" not in lowered:
        raise Phase10OidcError("SSM migrate document must redact secret output")
    for line in text.splitlines():
        if not _CREATE_EXTENSION.search(line):
            continue
        lowered_line = line.lower()
        if any(
            token in lowered_line
            for token in ("grep", "forbidden", "blocked", "does not")
        ):
            continue
        raise Phase10OidcError("SSM document must not run CREATE EXTENSION")


def assert_workflow_oidc(
    record: WorkflowRecord, *, environment: str, document: str
) -> None:
    """Require protected OIDC workflow wiring without long-lived keys.

    Args:
        record: Workflow file.
        environment: GitHub Environment name.
        document: Named SSM document the job may invoke.

    Raises:
        Phase10OidcError: If permissions, environment, pin, document, or
            secret scan fails.
    """

    text = record.text
    if f"environment: {environment}" not in text:
        raise Phase10OidcError(
            f"{record.name} must require GitHub environment {environment}"
        )
    if "id-token: write" not in text:
        raise Phase10OidcError(f"{record.name} must set id-token: write")
    if "contents: read" not in text:
        raise Phase10OidcError(f"{record.name} must set contents: read")
    if CHECKOUT_ACTION_PIN not in text:
        raise Phase10OidcError(f"{record.name} must pin actions/checkout by SHA")
    if CONFIGURE_AWS_CREDENTIALS_PIN not in text:
        raise Phase10OidcError(
            f"{record.name} must pin configure-aws-credentials {CONFIGURE_AWS_CREDENTIALS_PIN}"
        )
    if "role-to-assume:" not in text:
        raise Phase10OidcError(f"{record.name} must assume a role via OIDC")
    if document not in text:
        raise Phase10OidcError(f"{record.name} must invoke {document}")
    assert_no_long_lived_workflow_secrets(text, source=record.name)


def assert_no_long_lived_workflow_secrets(text: str, *, source: str) -> None:
    """Reject long-lived AWS or database credentials in workflow YAML.

    Args:
        text: Workflow YAML.
        source: File name for errors.

    Raises:
        Phase10OidcError: If a forbidden fragment is present.
    """

    upper = text.upper()
    for fragment in LONG_LIVED_WORKFLOW_FRAGMENTS:
        if fragment.upper() in upper:
            raise Phase10OidcError(
                f"{source} must not contain long-lived credential {fragment}"
            )
    if re.search(r"AKIA[0-9A-Z]{16}", text):
        raise Phase10OidcError(f"{source} must not embed AWS access key ids")
    if re.search(r"secrets\.[A-Z0-9_]*DATABASE", text, re.IGNORECASE):
        raise Phase10OidcError(f"{source} must not store database secrets in GitHub")


def assert_pr_fast_not_migrate(pr_fast: str) -> None:
    """Require PR CI to stay read-only and not call migrate workflows.

    Args:
        pr_fast: ``pr-fast.yml`` source.

    Raises:
        Phase10OidcError: If OIDC migrate/deploy is wired into PR CI.
    """

    if STAGING_MIGRATE_WORKFLOW in pr_fast or STAGING_DEPLOY_WORKFLOW in pr_fast:
        raise Phase10OidcError("pr-fast.yml must not call protected migrate/deploy")
    if "id-token: write" in pr_fast:
        raise Phase10OidcError("pr-fast.yml must not request id-token write")
    if "permissions:" in pr_fast and "contents: read" not in pr_fast:
        raise Phase10OidcError("pr-fast.yml must keep contents: read")


def assert_oidc_inventory(payload: Mapping[str, object]) -> None:
    """Require custody fields on the intended topology inventory.

    Args:
        payload: ``intended-topology.json``.

    Raises:
        Phase10OidcError: If prefixes, rotation days, or OIDC ids drift.
    """

    if payload.get("github_repository") != GITHUB_REPOSITORY:
        raise Phase10OidcError("inventory github_repository drifted")
    if payload.get("github_oidc_issuer") != GITHUB_OIDC_ISSUER:
        raise Phase10OidcError("inventory GitHub OIDC issuer drifted")
    if payload.get("staging_secret_prefix") != STAGING_SECRET_PREFIX:
        raise Phase10OidcError("inventory staging secret prefix drifted")
    if payload.get("production_secret_prefix") != PRODUCTION_SECRET_PREFIX:
        raise Phase10OidcError("inventory production secret prefix drifted")
    if payload.get("secret_rotation_max_days") != SECRET_ROTATION_MAX_DAYS:
        raise Phase10OidcError("inventory rotation max days must be 90")
    if payload.get("secret_rotation_lambda_present") is not False:
        raise Phase10OidcError("inventory must not claim a rotation Lambda")
    if payload.get("live_oidc_assume") not in {"Blocked", "Not Run"}:
        raise Phase10OidcError("inventory must not mark live OIDC assume Passed")


def load_workflow_records(repo_root: Path) -> tuple[WorkflowRecord, ...]:
    """Load GitHub workflow YAML files.

    Args:
        repo_root: Repository root.

    Returns:
        Workflow records sorted by name.

    Raises:
        Phase10OidcError: If the workflows directory is missing.
    """

    directory = repo_root / GITHUB_WORKFLOWS_DIR
    if not directory.is_dir():
        raise Phase10OidcError("GitHub workflows directory is missing")
    records = [
        WorkflowRecord(name=path.name, text=path.read_text(encoding="utf-8"))
        for path in sorted(directory.glob("*.yml"))
    ]
    if not records:
        raise Phase10OidcError("no GitHub workflow files found")
    return tuple(records)


def _run_check(check: str, callback: Callable[[], None]) -> PolicyFinding:
    """Run one assertion and convert failures into findings.

    Args:
        check: Assertion id.
        callback: Zero-argument callable that raises ``Phase10OidcError``.

    Returns:
        Finding with pass/fail detail.
    """

    try:
        callback()
    except (Phase10OidcError, Phase10TopologyError) as exc:
        return PolicyFinding(check=check, passed=False, detail=str(exc))
    return PolicyFinding(check=check, passed=True, detail="ok")


def assert_committed_oidc_policy(repo_root: Path) -> PolicyReport:
    """Assert committed Packet 2 OIDC/SSM/workflow/secret artifacts.

    Args:
        repo_root: Repository root.

    Returns:
        Policy report. ``passed`` is False when any finding failed.

    Raises:
        Phase10OidcError: If required files are missing or any check fails.
    """

    infra = repo_root / INFRA_EC2_DIR
    tf_bundle = load_terraform_bundle(infra)
    hcl = strip_hcl_comments(tf_bundle)
    workflows = {item.name: item for item in load_workflow_records(repo_root)}
    inventory = load_json_object(repo_root / INTENDED_TOPOLOGY_FILE)
    vercel = load_json_object(repo_root / VERCEL_PUBLIC_ENV_FILE)
    staging_migrate_doc = (
        repo_root / SSM_DOCUMENTS_DIR / "staging-migrate.yml"
    ).read_text(encoding="utf-8")
    staging_deploy_doc = (
        repo_root / SSM_DOCUMENTS_DIR / "staging-deploy.yml"
    ).read_text(encoding="utf-8")
    production_migrate_doc = (
        repo_root / SSM_DOCUMENTS_DIR / "production-migrate.yml"
    ).read_text(encoding="utf-8")
    pr_fast = (repo_root / GITHUB_WORKFLOWS_DIR / "pr-fast.yml").read_text(
        encoding="utf-8"
    )

    def check_trust() -> None:
        """Assert staging and production OIDC trust documents."""

        assert_github_oidc_provider(hcl, raw_hcl=tf_bundle)
        assert_oidc_trust(
            extract_named_block(
                hcl, "data", "aws_iam_policy_document", "staging_oidc_migrate_trust"
            ),
            environment="staging",
            workflow=STAGING_MIGRATE_WORKFLOW,
        )
        assert_oidc_trust(
            extract_named_block(
                hcl, "data", "aws_iam_policy_document", "staging_oidc_deploy_trust"
            ),
            environment="staging",
            workflow=STAGING_DEPLOY_WORKFLOW,
        )
        assert_oidc_trust(
            extract_named_block(
                hcl, "data", "aws_iam_policy_document", "production_oidc_migrate_trust"
            ),
            environment="production",
            workflow=PRODUCTION_MIGRATE_WORKFLOW,
        )
        if STAGING_OIDC_SUB.split("environment:")[-1] != "staging":
            raise Phase10OidcError("staging OIDC sub drifted")
        if PRODUCTION_OIDC_SUB.split("environment:")[-1] != "production":
            raise Phase10OidcError("production OIDC sub drifted")

    def check_permissions() -> None:
        """Assert named SSM SendCommand and production-secret denial."""

        assert_named_ssm_send(
            extract_named_block(
                hcl,
                "data",
                "aws_iam_policy_document",
                "staging_oidc_migrate_permissions",
            ),
            STAGING_MIGRATE_DOCUMENT,
        )
        assert_named_ssm_send(
            extract_named_block(
                hcl,
                "data",
                "aws_iam_policy_document",
                "staging_oidc_deploy_permissions",
            ),
            STAGING_DEPLOY_DOCUMENT,
        )
        prod_perm = extract_named_block(
            hcl,
            "data",
            "aws_iam_policy_document",
            "production_oidc_migrate_permissions",
        )
        if PRODUCTION_MIGRATE_DOCUMENT not in prod_perm:
            raise Phase10OidcError("production role must target production document")
        assert_no_star_allow(prod_perm, "ssm")
        assert_no_star_allow(prod_perm, "iam")
        instance_secrets = extract_named_block(
            hcl, "data", "aws_iam_policy_document", "staging_secrets"
        )
        assert_staging_permissions_deny_production(instance_secrets)

    def check_secrets() -> None:
        """Assert secret placeholders, 90-day custody, and Vercel scan."""

        assert_secret_placeholders(hcl)
        assert_oidc_inventory(inventory)
        dumped = str(vercel)
        assert_no_vercel_secrets(dumped)

    def check_ssm() -> None:
        """Assert named SSM documents."""

        assert_ssm_document_text(
            staging_migrate_doc, secret_prefix=STAGING_SECRET_PREFIX
        )
        assert_ssm_document_text(staging_deploy_doc, secret_prefix=None)
        assert_ssm_document_text(
            production_migrate_doc, secret_prefix=PRODUCTION_SECRET_PREFIX
        )
        if STAGING_MIGRATE_DOCUMENT not in hcl:
            raise Phase10OidcError("SmartRagStagingMigrate Terraform resource missing")
        if STAGING_DEPLOY_DOCUMENT not in hcl:
            raise Phase10OidcError("SmartRagStagingDeploy Terraform resource missing")

    def check_workflows() -> None:
        """Assert protected workflows and PR CI isolation."""

        try:
            migrate = workflows[STAGING_MIGRATE_WORKFLOW]
            deploy = workflows[STAGING_DEPLOY_WORKFLOW]
            production = workflows[PRODUCTION_MIGRATE_WORKFLOW]
        except KeyError as exc:
            raise Phase10OidcError(f"missing protected workflow {exc.args[0]}") from exc
        assert_workflow_oidc(
            migrate, environment="staging", document=STAGING_MIGRATE_DOCUMENT
        )
        assert_workflow_oidc(
            deploy, environment="staging", document=STAGING_DEPLOY_DOCUMENT
        )
        assert_workflow_oidc(
            production,
            environment="production",
            document=PRODUCTION_MIGRATE_DOCUMENT,
        )
        assert_pr_fast_not_migrate(pr_fast)
        for record in workflows.values():
            assert_no_long_lived_workflow_secrets(record.text, source=record.name)

    checks: tuple[tuple[str, Callable[[], None]], ...] = (
        ("oidc_trust", check_trust),
        ("oidc_permissions", check_permissions),
        ("secret_custody", check_secrets),
        ("ssm_documents", check_ssm),
        ("workflows", check_workflows),
    )
    findings = tuple(_run_check(name, callback) for name, callback in checks)
    reviewed = (
        *sorted(infra.glob("*.tf")),
        *sorted((repo_root / SSM_DOCUMENTS_DIR).glob("*.yml")),
        repo_root / GITHUB_WORKFLOWS_DIR / STAGING_MIGRATE_WORKFLOW,
        repo_root / GITHUB_WORKFLOWS_DIR / STAGING_DEPLOY_WORKFLOW,
        repo_root / GITHUB_WORKFLOWS_DIR / PRODUCTION_MIGRATE_WORKFLOW,
        repo_root / INTENDED_TOPOLOGY_FILE,
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
        raise Phase10OidcError(
            "OIDC policy failed: " + ", ".join(failed) + f" ({details})"
        )
    return report


def prefixes_distinct(staging: str, production: str) -> bool:
    """Return whether staging and production secret prefixes are separated.

    Args:
        staging: Staging name prefix.
        production: Production name prefix.

    Returns:
        True when prefixes are non-empty and neither is a prefix of the other
        in a way that would allow cross-environment GetSecretValue.
    """

    if not staging or not production or staging == production:
        return False
    return not staging.startswith(production) and not production.startswith(staging)

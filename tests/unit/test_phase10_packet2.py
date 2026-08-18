"""Unit tests for Phase 10 Packet 2 OIDC, migration, and custody negatives."""

from __future__ import annotations

from pathlib import Path

import pytest
from smart_rag_core.release.phase10_constants import (
    GITHUB_REPOSITORY,
    PHASE09_IMAGE_IDS,
    PRODUCTION_SECRET_PREFIX,
    STAGING_MIGRATE_WORKFLOW,
    STAGING_SECRET_PREFIX,
)
from smart_rag_core.release.phase10_oidc import (
    Phase10OidcError,
    assert_no_long_lived_workflow_secrets,
    assert_oidc_trust,
    assert_staging_permissions_deny_production,
    prefixes_distinct,
)
from smart_rag_core.release.phase10_packet1 import (
    packet1_checkbox_unchecked,
    wrapper_status_pending,
)
from smart_rag_core.release.phase10_packet2 import (
    classify_p1002_a,
    classify_p1002_b,
    classify_p1002_c,
    classify_p1002_d,
    classify_p1002_e,
    packet2_checkbox_unchecked,
)
from smart_rag_core.release.phase10_topology import (
    Phase10TopologyError,
    assert_no_vercel_secrets,
)

from scripts.ci.check_migrations import find_migration_violations

_FREEZE = PHASE09_IMAGE_IDS["api"]
_PRIOR = "sha256:1d9f569b54c6012c4e9b1087979b409a9e2517ac9cce7c1f81d8917d9870f3d7"


def test_wrong_repo_trust_is_rejected() -> None:
    """OIDC trust for another repository cannot assume the staging role."""

    with pytest.raises(Phase10OidcError, match="repository"):
        assert_oidc_trust(
            """
            sts:AssumeRoleWithWebIdentity
            sts.amazonaws.com
            repo:evil/other:environment:staging
            evil/other/.github/workflows/staging-migrate.yml@*
            """,
            environment="staging",
            workflow=STAGING_MIGRATE_WORKFLOW,
        )


def test_missing_environment_trust_is_rejected() -> None:
    """Branch-only sub claims without a protected environment fail closed."""

    with pytest.raises(Phase10OidcError, match="environment"):
        assert_oidc_trust(
            f"""
            sts:AssumeRoleWithWebIdentity
            sts.amazonaws.com
            repo:{GITHUB_REPOSITORY}:ref:refs/heads/main
            {GITHUB_REPOSITORY}/.github/workflows/{STAGING_MIGRATE_WORKFLOW}@*
            """,
            environment="staging",
            workflow=STAGING_MIGRATE_WORKFLOW,
        )


def test_production_environment_on_staging_trust_is_rejected() -> None:
    """Staging roles must not trust environment:production."""

    with pytest.raises(Phase10OidcError, match="environment:production"):
        assert_oidc_trust(
            f"""
            sts:AssumeRoleWithWebIdentity
            sts.amazonaws.com
            repo:{GITHUB_REPOSITORY}:environment:staging
            environment:production
            {GITHUB_REPOSITORY}/.github/workflows/{STAGING_MIGRATE_WORKFLOW}@*
            """,
            environment="staging",
            workflow=STAGING_MIGRATE_WORKFLOW,
        )


def test_aws_access_key_in_workflow_is_rejected() -> None:
    """Protected workflows cannot store long-lived AWS keys."""

    with pytest.raises(Phase10OidcError, match="AWS_ACCESS_KEY"):
        assert_no_long_lived_workflow_secrets(
            "env:\n  AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}\n",
            source="staging-migrate.yml",
        )


def test_drop_table_migration_is_rejected() -> None:
    """Packet 2 reuses check_migrations.py instead of a second regex table."""

    violations = find_migration_violations(
        "DROP TABLE app.documents;", Path("unsafe.sql")
    )
    assert violations
    assert any("DROP TABLE" in item for item in violations)


def test_production_secret_arn_on_staging_allow_is_rejected() -> None:
    """Staging OIDC Allow statements cannot name production secret ARNs."""

    with pytest.raises(Phase10OidcError, match="production secret"):
        assert_staging_permissions_deny_production(
            f"""
            statement {{
              actions = ["secretsmanager:GetSecretValue"]
              resources = ["arn:aws:secretsmanager:us-east-1:123:secret:{PRODUCTION_SECRET_PREFIX}db"]
            }}
            """
        )


def test_vercel_service_role_is_rejected() -> None:
    """Vercel inventories still cannot carry service_role."""

    with pytest.raises(Phase10TopologyError, match="SERVICE_ROLE"):
        assert_no_vercel_secrets("NEXT_PUBLIC_SERVICE_ROLE_KEY=not-a-real-secret")


def test_packet2_classify_does_not_require_packet1_checked() -> None:
    """Packet 2 checkbox logic ignores Packet 1 remaining unchecked."""

    wrapper = """---
status: pending
---
1. [ ] [Provision isolated managed Supabase
2. [ ] [Implement GitHub OIDC, protected immutable expand/contract migrations
"""
    assert wrapper_status_pending(wrapper) is True
    assert packet1_checkbox_unchecked(wrapper) is True
    assert packet2_checkbox_unchecked(wrapper) is True
    checked_packet1 = wrapper.replace(
        "1. [ ] [Provision isolated managed Supabase",
        "1. [x] [Provision isolated managed Supabase",
    )
    assert packet1_checkbox_unchecked(checked_packet1) is False
    assert packet2_checkbox_unchecked(checked_packet1) is True


def test_classifications_fail_closed_and_do_not_pass_live_assume() -> None:
    """Negatives fail; live migrate stays Blocked; freeze-as-old-slot fails."""

    assert classify_p1002_a(oidc_policy_passed=False) == "Failed"
    assert classify_p1002_a(oidc_policy_passed=True) == "Passed"
    assert classify_p1002_b(committed_scan_clean=False, live_secret_found=False) == (
        "Failed"
    )
    assert classify_p1002_b(committed_scan_clean=True, live_secret_found=True) == (
        "Failed"
    )
    assert (
        classify_p1002_c(
            migration_policy_ok=True,
            approval_wiring=True,
            live_migrate_state="Blocked",
        )
        == "Blocked"
    )
    assert (
        classify_p1002_c(
            migration_policy_ok=False,
            approval_wiring=True,
            live_migrate_state="Blocked",
        )
        == "Failed"
    )
    assert (
        classify_p1002_d(
            smoke={
                "classification": "Passed",
                "freeze_api_id": _FREEZE,
                "requested": _FREEZE,
            },
            freeze_api_id=_FREEZE,
            contraction_absent=True,
        )
        == "Failed"
    )
    assert (
        classify_p1002_d(
            smoke={
                "classification": "Passed",
                "freeze_api_id": _FREEZE,
                "requested": _PRIOR,
            },
            freeze_api_id=_FREEZE,
            contraction_absent=True,
        )
        == "Passed"
    )
    assert (
        classify_p1002_e(
            prefixes_are_distinct=False,
            rotation_max_days=90,
            production_on_staging=False,
        )
        == "Failed"
    )
    assert prefixes_distinct(STAGING_SECRET_PREFIX, PRODUCTION_SECRET_PREFIX) is True
    assert prefixes_distinct(STAGING_SECRET_PREFIX, STAGING_SECRET_PREFIX) is False

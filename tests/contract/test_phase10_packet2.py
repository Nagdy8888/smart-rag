"""Contract tests for committed Phase 10 Packet 2 OIDC, workflows, and migrations."""

from __future__ import annotations

from pathlib import Path

from smart_rag_core.release.io import load_json_object
from smart_rag_core.release.phase10_constants import (
    CONFIGURE_AWS_CREDENTIALS_PIN,
    GITHUB_REPOSITORY,
    GITHUB_WORKFLOWS_DIR,
    MIGRATIONS_DIR,
    PACKET2_RELATIVE,
    PHASE09_IMAGE_IDS,
    PHASE09_OLD_API_SMOKE,
    PRODUCTION_SECRET_PREFIX,
    STAGING_MIGRATE_WORKFLOW,
    STAGING_SECRET_PREFIX,
    WRAPPER_RELATIVE,
)
from smart_rag_core.release.phase10_oidc import (
    assert_committed_oidc_policy,
    prefixes_distinct,
)
from smart_rag_core.release.phase10_packet1 import (
    packet1_checkbox_unchecked,
    wrapper_status_pending,
)
from smart_rag_core.release.phase10_packet2 import (
    packet2_checkbox_unchecked,
    packet2_status_pending,
    review_migrations,
)
from smart_rag_core.release.phase10_topology import assert_committed_policy

from scripts.ci.check_migrations import find_migration_violations

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_committed_terraform_and_workflows_pass_oidc_policy() -> None:
    """Reviewed OIDC/SSM/workflow files satisfy allow/deny without live assume."""

    report = assert_committed_oidc_policy(REPO_ROOT)
    assert report.passed is True
    assert report.iac_sha256
    names = {item.check for item in report.findings}
    assert names == {
        "oidc_trust",
        "oidc_permissions",
        "secret_custody",
        "ssm_documents",
        "workflows",
    }
    assert all(item.passed for item in report.findings)
    migrate = (REPO_ROOT / GITHUB_WORKFLOWS_DIR / STAGING_MIGRATE_WORKFLOW).read_text(
        encoding="utf-8"
    )
    assert CONFIGURE_AWS_CREDENTIALS_PIN in migrate
    assert "AWS_ACCESS_KEY" not in migrate
    assert GITHUB_REPOSITORY.split("/")[0] == "Nagdy8888"


def test_check_migrations_still_clean_and_hashed() -> None:
    """Existing expand/contract policy remains the only regex table."""

    review = review_migrations(REPO_ROOT)
    assert review.unknown_files == ()
    assert review.violations == ()
    assert review.contraction_absent is True
    assert review.file_count >= 1
    assert len(review.sha256) == 64
    directory = REPO_ROOT / MIGRATIONS_DIR
    for path in directory.glob("*.sql"):
        assert find_migration_violations(path.read_text(encoding="utf-8"), path) == []


def test_github_workflows_have_no_long_lived_keys() -> None:
    """Every committed workflow stays free of AWS keys and database secrets."""

    for path in (REPO_ROOT / GITHUB_WORKFLOWS_DIR).glob("*.yml"):
        text = path.read_text(encoding="utf-8")
        assert "AWS_ACCESS_KEY" not in text
        assert "aws-access-key-id" not in text
        assert "AWS_SECRET_ACCESS_KEY" not in text


def test_staging_and_production_prefixes_are_distinct() -> None:
    """Staging and production secret name prefixes cannot overlap."""

    assert prefixes_distinct(STAGING_SECRET_PREFIX, PRODUCTION_SECRET_PREFIX) is True
    assert STAGING_SECRET_PREFIX != PRODUCTION_SECRET_PREFIX
    assert not PRODUCTION_SECRET_PREFIX.startswith(STAGING_SECRET_PREFIX)


def test_old_api_smoke_freeze_still_matches_phase9() -> None:
    """P10-02-D may keep Passed only for the prior digest, not the freeze id."""

    smoke = load_json_object(REPO_ROOT / PHASE09_OLD_API_SMOKE)
    freeze = PHASE09_IMAGE_IDS["api"]
    assert smoke.get("freeze_api_id") == freeze
    assert smoke.get("requested") != freeze
    assert smoke.get("classification") == "Passed"


def test_wrapper_and_packet2_stay_pending_even_if_packet1_unchecked() -> None:
    """Live Blocked Packet 2 must not complete the wrapper or require Packet 1."""

    wrapper = (REPO_ROOT / WRAPPER_RELATIVE).read_text(encoding="utf-8")
    packet = (REPO_ROOT / PACKET2_RELATIVE).read_text(encoding="utf-8")
    assert wrapper_status_pending(wrapper) is True
    assert packet2_checkbox_unchecked(wrapper) is True
    assert packet1_checkbox_unchecked(wrapper) is True
    assert packet2_status_pending(packet) is True
    packet1 = assert_committed_policy(REPO_ROOT)
    assert packet1.passed is True
    pr_fast = (REPO_ROOT / GITHUB_WORKFLOWS_DIR / "pr-fast.yml").read_text(
        encoding="utf-8"
    )
    assert STAGING_MIGRATE_WORKFLOW not in pr_fast
    assert "id-token: write" not in pr_fast

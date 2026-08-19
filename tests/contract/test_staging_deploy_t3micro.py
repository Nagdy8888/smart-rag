"""Contract tests for SmartRagStagingDeploy t3.micro overlay usage."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCUMENT = REPO_ROOT / "infra" / "ec2" / "ssm-documents" / "staging-deploy.yml"


def test_staging_deploy_uses_t3micro_overlay_and_edge_profile() -> None:
    """SSM deploy must not start the full ingest stack on t3.micro.

    This test asserts committed document text only. It does not send
    ``aws ssm send-command``.
    """

    text = DOCUMENT.read_text(encoding="utf-8")
    assert "docker-compose.t3micro.yml" in text
    assert "--profile t3micro-edge" in text
    assert "blocked_overlay" in text
    assert "docker compose -f docker-compose.staging.yml up -d" not in text
    assert (
        "docker compose -f docker-compose.staging.yml -f docker-compose.t3micro.yml"
        in text
    )
    assert "not-on-t3micro" not in text

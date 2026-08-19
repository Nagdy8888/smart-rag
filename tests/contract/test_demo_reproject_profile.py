"""Contract tests for the optional demo-reproject Compose profile."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
STAGING = REPO_ROOT / "infra" / "ec2" / "docker-compose.staging.yml"
OVERLAY = REPO_ROOT / "infra" / "ec2" / "docker-compose.t3micro.yml"


def _mapping(value: object) -> dict[str, object]:
    """Narrow YAML to a string-keyed mapping.

    Args:
        value: Parsed YAML node.

    Returns:
        Mapping.

    Raises:
        TypeError: If the node is not a mapping.
    """

    if not isinstance(value, dict):
        raise TypeError("expected mapping")
    return cast(dict[str, object], value)


def test_bm25_reproject_is_profile_only_and_has_no_clamav() -> None:
    """Default staging up must not start the reproject one-shot."""

    loaded = _mapping(yaml.safe_load(STAGING.read_text(encoding="utf-8")))
    services = _mapping(loaded["services"])
    service = _mapping(services["bm25-reproject"])
    profiles = service["profiles"]
    assert profiles == ["demo-reproject"] or (
        isinstance(profiles, list) and "demo-reproject" in profiles
    )
    command = service["command"]
    assert "smart_rag_core.release.bm25_reproject" in str(command)
    depends = _mapping(service["depends_on"])
    assert "paradedb" in depends
    assert "clamav" not in depends
    assert "parser-sandbox" not in depends
    environment = _mapping(service["environment"])
    assert "CLAMAV_HOST" not in environment
    overlay = OVERLAY.read_text(encoding="utf-8")
    assert "demo-reproject" in overlay
    assert "bm25-reproject" in overlay

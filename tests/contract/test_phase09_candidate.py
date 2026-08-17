"""Live Phase 9 Packet 1 candidate health, migration, and artifact contracts.

Static Compose and identity checks always run. Live Compose/Supabase checks
skip when the stack is down unless ``SMART_RAG_REQUIRE_PHASE09_CANDIDATE=1``.
"""

from __future__ import annotations

from pathlib import Path
from typing import NoReturn, cast

import pytest
from smart_rag_core.release.compose import run_compose
from smart_rag_core.release.constants import (
    ARTIFACT_DIR,
    IDENTITY_SCHEMA_VERSION,
    IMAGE_MANIFEST_SCHEMA_VERSION,
    PRIVATE_COMPOSE_SERVICES,
    REQUIRED_DOCUMENT_STATES,
)
from smart_rag_core.release.errors import CandidatePortError
from smart_rag_core.release.health import http_ok
from smart_rag_core.release.identity import collect_identity_freeze
from smart_rag_core.release.io import json_int, load_json_object
from smart_rag_core.release.migrations import (
    collect_migration_inventory,
    load_applied_versions,
)
from smart_rag_core.release.ports import (
    assert_private_services_unpublished,
    parse_compose_ps_text,
)

from tests.contract.integration_support import (
    read_process_env,
    resolve_supabase_db_url,
    try_connect,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = REPO_ROOT / ARTIFACT_DIR
REQUIRE = read_process_env("SMART_RAG_REQUIRE_PHASE09_CANDIDATE") == "1"


def _skip_or_fail(message: str) -> NoReturn:
    """Fail closed when Packet 1 live proof is required.

    Args:
        message: Skip or failure reason.

    Raises:
        pytest.fail: When ``SMART_RAG_REQUIRE_PHASE09_CANDIDATE=1``.
        pytest.skip: When live proof is optional and the stack is down.
    """

    if REQUIRE:
        pytest.fail(message)
    pytest.skip(message)


def test_candidate_compose_runtime_publishers_are_private() -> None:
    """Candidate ``docker compose ps`` must not publish ParadeDB/Valkey/proxy."""

    compose_text = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    ps = run_compose(REPO_ROOT, ["ps", "--format", "json"], timeout_seconds=30)
    if ps.returncode != 0 or not ps.stdout.strip():
        _skip_or_fail("candidate compose stack is not running")
    publishers = parse_compose_ps_text(ps.stdout)
    missing = [name for name in PRIVATE_COMPOSE_SERVICES if name not in publishers]
    if missing:
        _skip_or_fail(f"private services not listed: {missing}")
    try:
        assert_private_services_unpublished(publishers, compose_text=compose_text)
    except CandidatePortError as exc:
        pytest.fail(str(exc))


def test_api_live_when_stack_is_up() -> None:
    """API ``/health/live`` must pass when the candidate API is published."""

    if not http_ok("http://127.0.0.1:8000/health/live"):
        _skip_or_fail("candidate API /health/live is unreachable")


def test_migration_inventory_matches_applied_when_supabase_is_up() -> None:
    """Applied local migrations must match repository SQL file prefixes."""

    url = resolve_supabase_db_url()
    connection = try_connect(url)
    if connection is None:
        _skip_or_fail(f"local Supabase Postgres unreachable at {url}")
    try:
        applied = load_applied_versions(connection)
    finally:
        connection.close()
    inventory = collect_migration_inventory(REPO_ROOT, applied_versions=applied)
    assert inventory.drift is False
    assert inventory.applied_versions
    assert inventory.files


def test_identity_freeze_collects_without_secrets() -> None:
    """Identity freeze is collectable from the repo and omits credential keys."""

    freeze = collect_identity_freeze(REPO_ROOT)
    dumped = freeze.model_dump()
    joined = " ".join(str(value) for value in dumped.values())
    assert "sk-" not in joined
    assert "PASSWORD" not in dumped
    assert freeze.schema_version == IDENTITY_SCHEMA_VERSION


def test_image_manifest_artifact_when_present() -> None:
    """Built digest manifest records image Id and non-root user 10001."""

    path = ARTIFACTS / "candidate-image-manifest.json"
    if not path.is_file():
        _skip_or_fail("candidate-image-manifest.json has not been built yet")
    payload = load_json_object(path)
    assert payload.get("schema_version") == IMAGE_MANIFEST_SCHEMA_VERSION
    assert payload.get("compose_file") == "docker-compose.yml"
    assert payload.get("overlay_file") is None
    images = payload.get("images")
    assert isinstance(images, list) and images
    for item in cast(list[object], images):
        assert isinstance(item, dict)
        row = cast(dict[str, object], item)
        image_id = str(row.get("image_id") or "")
        assert image_id.startswith("sha256:")
        assert str(row.get("user") or "").startswith("10001")


def test_corpus_manifest_rejects_holdout_when_present() -> None:
    """Seeded corpus artifact stays on open splits and never opens holdout."""

    path = ARTIFACTS / "candidate-corpus-manifest.json"
    if not path.is_file():
        _skip_or_fail("candidate-corpus-manifest.json has not been seeded yet")
    payload = load_json_object(path)
    assert payload.get("holdout_opened") is False
    rows = payload.get("rows")
    assert isinstance(rows, list) and rows
    for item in cast(list[object], rows):
        assert isinstance(item, dict)
        row = cast(dict[str, object], item)
        split = str(row.get("split") or "")
        assert split in {"development", "qualification"}
        case_id = str(row.get("case_id") or "").lower()
        assert "holdout" not in case_id
        assert "production" not in case_id


def test_readiness_export_covers_required_states_when_present() -> None:
    """Readiness export must list every required public state without fakes."""

    path = ARTIFACTS / "candidate-readiness-export.json"
    if not path.is_file():
        _skip_or_fail("candidate-readiness-export.json has not been seeded yet")
    payload = load_json_object(path)
    events = payload.get("events")
    assert isinstance(events, list)
    typed_events = cast(list[object], events)
    observed = {
        str(cast(dict[str, object], item).get("state"))
        for item in typed_events
        if isinstance(item, dict)
    }
    missing = payload.get("missing_states")
    assert isinstance(missing, list)
    for item in typed_events:
        assert isinstance(item, dict)
        row = cast(dict[str, object], item)
        driver = str(row.get("driver") or "").lower()
        assert "sql-stamp" not in driver
        assert driver != "update_status"
        if row.get("state") == "hybrid_ready":
            assert row.get("bm25_verified") is True
        if row.get("state") == "graph_ready":
            assert row.get("maps_verified") is True
    if REQUIRE:
        assert not missing
        assert set(REQUIRED_DOCUMENT_STATES).issubset(observed)


def test_sizing_baseline_is_local_when_present() -> None:
    """Sizing artifact maps local counts and forbids managed claims."""

    path = ARTIFACTS / "candidate-sizing-baseline.json"
    if not path.is_file():
        _skip_or_fail("candidate-sizing-baseline.json has not been written yet")
    payload = load_json_object(path)
    assert payload.get("local_candidate_not_full_envelope") is True
    assert payload.get("managed_claims") == []
    versions = json_int(payload.get("seeded_document_versions"))
    envelope = json_int(payload.get("signed_hybrid_version_envelope"))
    if versions == 0:
        _skip_or_fail("candidate sizing baseline has no seeded counts yet")
    assert versions < envelope

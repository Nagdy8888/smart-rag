"""Contract tests for committed Phase 10 Packet 1 IaC, inventory, and corpus."""

from __future__ import annotations

from pathlib import Path

from smart_rag_core.release.io import as_json_list, as_json_object, load_json_object
from smart_rag_core.release.phase10_constants import (
    CACHING_DISABLED_POLICY_ID,
    ENVELOPE_CHUNKS,
    ENVELOPE_GRAPH_VERSIONS,
    ENVELOPE_HYBRID_VERSIONS,
    INTENDED_TOPOLOGY_FILE,
    PACKET1_RELATIVE,
    PHASE09_CORPUS_MANIFEST,
    PHASE09_IMAGE_IDS,
    PHASE09_PROMOTION_MANIFEST,
    STAGING_CADDY_FILE,
    STAGING_CADDY_HTTP443_FILE,
    STAGING_COMPOSE_FILE,
    WRAPPER_RELATIVE,
)
from smart_rag_core.release.phase10_packet1 import (
    packet1_checkbox_unchecked,
    wrapper_status_pending,
)
from smart_rag_core.release.phase10_topology import assert_committed_policy

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_committed_iac_compose_caddy_and_inventory_pass_policy() -> None:
    """Reviewed staging files satisfy Packet 1 policy without live apply."""

    report = assert_committed_policy(REPO_ROOT)
    assert report.passed is True
    assert report.iac_sha256
    names = {item.check for item in report.findings}
    assert "cloudfront_timeouts" in names
    assert "no_ssh" in names
    assert "caddy_http443" in names
    assert all(item.passed for item in report.findings)


def test_phase9_promotion_image_ids_match_freeze() -> None:
    """Packet 1 consumes the exact Phase 9 promotion manifest ids."""

    payload = load_json_object(REPO_ROOT / PHASE09_PROMOTION_MANIFEST)
    images = payload.get("candidate_image_ids")
    assert images == PHASE09_IMAGE_IDS
    inventory = load_json_object(REPO_ROOT / INTENDED_TOPOLOGY_FILE)
    assert inventory.get("phase9_image_ids") == PHASE09_IMAGE_IDS
    envelope = inventory.get("envelope")
    typed_envelope = as_json_object(envelope, source="envelope")
    assert typed_envelope.get("QT-CAP-001-P9") == ENVELOPE_HYBRID_VERSIONS
    assert typed_envelope.get("QT-CAP-002-P9") == ENVELOPE_CHUNKS
    assert typed_envelope.get("QT-CAP-005-P8") == ENVELOPE_GRAPH_VERSIONS
    assert typed_envelope.get("claimed_full_hybrid") is False
    assert inventory.get("cloudfront_cache_policy_id") == CACHING_DISABLED_POLICY_ID


def test_synthetic_corpus_holdout_stays_sealed() -> None:
    """Staging seed identity is the Phase 9 open split, not production or holdout."""

    corpus = load_json_object(REPO_ROOT / PHASE09_CORPUS_MANIFEST)
    assert corpus.get("holdout_opened") is False
    inventory = load_json_object(REPO_ROOT / INTENDED_TOPOLOGY_FILE)
    assert inventory.get("production_data") is False
    assert inventory.get("holdout_opened") is False
    rows = as_json_list(corpus.get("rows"), source="corpus rows")
    assert rows
    for item in rows:
        row = as_json_object(item, source="corpus row")
        case_id = str(row.get("case_id") or "").lower()
        assert "holdout" not in case_id
        assert "production" not in case_id
        assert str(row.get("split") or "") in {"development", "qualification"}


def test_wrapper_and_packet_stay_pending() -> None:
    """Live Blocked Packet 1 must not complete the Phase 10 wrapper."""

    wrapper = (REPO_ROOT / WRAPPER_RELATIVE).read_text(encoding="utf-8")
    packet = (REPO_ROOT / PACKET1_RELATIVE).read_text(encoding="utf-8")
    assert wrapper_status_pending(wrapper) is True
    assert packet1_checkbox_unchecked(wrapper) is True
    assert "status: pending" in packet.split("---", 2)[1]
    assert (REPO_ROOT / STAGING_COMPOSE_FILE).is_file()
    assert (REPO_ROOT / STAGING_CADDY_FILE).is_file()
    assert (REPO_ROOT / STAGING_CADDY_HTTP443_FILE).is_file()
    compose = (REPO_ROOT / STAGING_COMPOSE_FILE).read_text(encoding="utf-8")
    assert "docker-compose.packet8.yml" not in compose
    assert "lightrag:" not in compose

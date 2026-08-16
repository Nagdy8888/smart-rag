"""Unit tests for typed canonical keys, do-not-merge, and inactive suggestions."""

from __future__ import annotations

from pathlib import Path

import pytest
from smart_rag_core.jobs.entity_rule_invalidation import (
    INVALIDATE_CHUNK_MAP_SQL,
    INVALIDATE_EVIDENCE_MAP_SQL,
    INVALIDATE_SOURCE_MAP_SQL,
    MARK_VERSIONS_NOT_GRAPH_READY_SQL,
    rebuild_workspace_key,
)
from smart_rag_core.jobs.entity_rules import (
    EntityRuleDraft,
    EntityRuleRejectedError,
    normalize_entity_type,
    validate_entity_rule_draft,
)
from smart_rag_core.jobs.extraction_policy import (
    DEFAULT_EXTRACTION_POLICY_HASH,
    default_extraction_policy,
    hash_extraction_policy,
)
from smart_rag_core.jobs.limits import GRAPH_PIPELINE_VERSION
from smart_rag_core.retrieval.graph import graph_chunker_config_snapshot
from smart_rag_core.retrieval.graph_mapping import (
    EntityRuleView,
    canonical_entity_key,
    mapping_config_generation,
    ordered_statement_endpoints,
    resolve_entity_name,
    typed_canonical_key,
)


def test_typed_canonical_keys_keep_homonyms_apart() -> None:
    """PROJECT::atlas is never PRODUCT::atlas."""

    project = typed_canonical_key(entity_type="PROJECT", name="ATLAS")
    product = typed_canonical_key(entity_type="PRODUCT", name="Atlas")
    assert project == "PROJECT::atlas"
    assert product == "PRODUCT::atlas"
    assert project != product
    assert canonical_entity_key(
        entity_type="PROJECT", canonical_name="ATLAS"
    ) != canonical_entity_key(entity_type="PRODUCT", canonical_name="ATLAS")


def test_aliases_and_acronyms_resolve_within_type() -> None:
    """Approved aliases map to the canonical name of the same type."""

    rules = (
        EntityRuleView(
            entity_type="ORGANIZATION",
            canonical_name="Alpha Corporation",
            aliases=("Acme", "ACME Corp", "A.C.M.E."),
            do_not_merge=(),
        ),
    )
    assert resolve_entity_name("acme", "ORGANIZATION", rules) == "Alpha Corporation"
    assert resolve_entity_name("A.C.M.E.", "ORGANIZATION", rules) == "Alpha Corporation"


def test_multilingual_aliases_normalize_together() -> None:
    """Arabic and English aliases of one type share a canonical name."""

    rules = (
        EntityRuleView(
            entity_type="PROJECT",
            canonical_name="Atlas",
            aliases=("أطلس", "Atlas Project"),
            do_not_merge=(),
        ),
    )
    assert resolve_entity_name("أطلس", "PROJECT", rules) == "Atlas"
    assert resolve_entity_name("atlas project", "PROJECT", rules) == "Atlas"


def test_cross_type_homonym_does_not_merge() -> None:
    """The same surface form stays separate across types."""

    rules = (
        EntityRuleView(
            entity_type="PROJECT",
            canonical_name="Atlas Program",
            aliases=("Atlas",),
            do_not_merge=(),
        ),
        EntityRuleView(
            entity_type="PRODUCT",
            canonical_name="Atlas Appliance",
            aliases=("Atlas",),
            do_not_merge=(),
        ),
    )
    assert resolve_entity_name("Atlas", "PROJECT", rules) == "Atlas Program"
    assert resolve_entity_name("Atlas", "PRODUCT", rules) == "Atlas Appliance"


def test_do_not_merge_wins_over_alias() -> None:
    """Blocked names stay unavailable rather than silently merging."""

    rules = (
        EntityRuleView(
            entity_type="ORG",
            canonical_name="Acme Holdings",
            aliases=("Acme",),
            do_not_merge=("Acme",),
        ),
    )
    assert resolve_entity_name("Acme", "ORG", rules) is None


def test_revoked_rules_are_ignored_by_resolver() -> None:
    """Revoked rules cannot change canonical keys."""

    rules = (
        EntityRuleView(
            entity_type="ORG",
            canonical_name="Should Not Apply",
            aliases=("Acme",),
            do_not_merge=(),
            status="revoked",
        ),
    )
    assert resolve_entity_name("Acme", "ORG", rules) == "Acme"


def test_unknown_entity_type_is_rejected() -> None:
    """Types outside the extraction allow-list fail closed."""

    with pytest.raises(EntityRuleRejectedError, match="unknown_entity_type"):
        validate_entity_rule_draft(
            EntityRuleDraft(
                entity_type="WIDGET",
                canonical_name="Gadget",
                status="approved",
            )
        )


def test_mapping_generation_stays_stable_until_first_bump() -> None:
    """Generation 1 keeps Packet 5 map digests; later bumps change them."""

    base = mapping_config_generation(
        workspace_key="company_default",
        pointer_generation=1,
        chunker_snapshot=graph_chunker_config_snapshot(),
    )
    same = mapping_config_generation(
        workspace_key="company_default",
        pointer_generation=1,
        chunker_snapshot=graph_chunker_config_snapshot(),
        entity_rules_generation=1,
        extraction_policy_hash="",
    )
    bumped = mapping_config_generation(
        workspace_key="company_default",
        pointer_generation=1,
        chunker_snapshot=graph_chunker_config_snapshot(),
        entity_rules_generation=2,
        extraction_policy_hash=DEFAULT_EXTRACTION_POLICY_HASH,
    )
    assert base == same
    assert bumped != base
    assert GRAPH_PIPELINE_VERSION == "graph_pipeline_v1"


def test_untyped_vendor_name_does_not_consume_typed_alias() -> None:
    """Missing vendor type stays on the vendor name instead of merging."""

    rules = (
        EntityRuleView(
            entity_type="PROJECT",
            canonical_name="Atlas Program",
            aliases=("Atlas",),
            do_not_merge=(),
        ),
    )
    assert resolve_entity_name("Atlas", None, rules) == "Atlas"


def test_symmetric_policy_orders_statement_endpoints() -> None:
    """Symmetric labels share one statement identity regardless of direction."""

    left = ordered_statement_endpoints("b", "a", relation_label_policy="symmetric")
    right = ordered_statement_endpoints("a", "b", relation_label_policy="symmetric")
    assert left == right
    directed = ordered_statement_endpoints("b", "a", relation_label_policy="directed")
    assert directed == ("b", "a")


def test_cross_type_alias_payload_is_rejected() -> None:
    """A PROJECT rule cannot claim a PRODUCT:: typed key."""

    with pytest.raises(EntityRuleRejectedError, match="cross_type_alias"):
        validate_entity_rule_draft(
            EntityRuleDraft(
                entity_type="PROJECT",
                canonical_name="Atlas",
                aliases=("PRODUCT::Atlas",),
                status="approved",
            )
        )


def test_duplicate_and_cycle_payloads_are_rejected() -> None:
    """Duplicate aliases and alias cycles fail closed."""

    existing = (
        EntityRuleView(
            entity_type="ORG",
            canonical_name="Beta",
            aliases=("Alpha",),
            do_not_merge=(),
        ),
    )
    with pytest.raises(EntityRuleRejectedError, match="alias_conflict"):
        validate_entity_rule_draft(
            EntityRuleDraft(
                entity_type="ORG",
                canonical_name="Gamma",
                aliases=("Alpha",),
                status="approved",
            ),
            existing=existing,
        )
    with pytest.raises(EntityRuleRejectedError, match="duplicate_alias"):
        validate_entity_rule_draft(
            EntityRuleDraft(
                entity_type="ORG",
                canonical_name="Solo",
                aliases=("Dup", "dup"),
                status="approved",
            )
        )


def test_feedback_cannot_be_auto_approved() -> None:
    """Model/feedback drafts cannot skip explicit approval."""

    with pytest.raises(EntityRuleRejectedError, match="auto_approval_forbidden"):
        validate_entity_rule_draft(
            EntityRuleDraft(
                entity_type="ORG",
                canonical_name="Acme",
                source="model",
                status="approved",
                confidence=0.9,
            )
        )


def test_extraction_policy_hash_is_stable() -> None:
    """Default overlay hash matches the seeded SQL digest."""

    assert hash_extraction_policy() == DEFAULT_EXTRACTION_POLICY_HASH
    assert (
        default_extraction_policy().extraction_policy_hash
        == DEFAULT_EXTRACTION_POLICY_HASH
    )
    assert normalize_entity_type("org") == "ORG"


def test_invalidation_sql_lives_in_jobs_and_never_patches_vendor() -> None:
    """Map invalidation SQL is application-owned and rebuild-isolated."""

    assert "lightrag_source_map" in INVALIDATE_SOURCE_MAP_SQL
    assert "lightrag_chunk_map" in INVALIDATE_CHUNK_MAP_SQL
    assert "graph_evidence_map" in INVALIDATE_EVIDENCE_MAP_SQL
    assert "graph_pending" in MARK_VERSIONS_NOT_GRAPH_READY_SQL
    assert rebuild_workspace_key("company_default") == "company_default__rebuild"
    jobs_root = (
        Path(__file__).resolve().parents[2]
        / "packages"
        / "core"
        / "src"
        / "smart_rag_core"
        / "jobs"
    )
    service = (jobs_root / "entity_rule_service.py").read_text(encoding="utf-8")
    invalidation = (jobs_root / "entity_rule_invalidation.py").read_text(
        encoding="utf-8"
    )
    assert "INTO app.search_aliases" not in service
    assert "INTO app.search_aliases" not in invalidation
    assert "UPDATE lightrag." not in invalidation
    assert "UPDATE lightrag." not in service
    apps_router = (
        Path(__file__).resolve().parents[2]
        / "apps"
        / "backend"
        / "src"
        / "smart_rag_api"
        / "routers"
        / "entity_rules.py"
    )
    router_text = apps_router.read_text(encoding="utf-8")
    assert "lightrag_source_map" not in router_text
    assert "graph_evidence_map" not in router_text
    assert "lightrag_chunk_map" not in router_text

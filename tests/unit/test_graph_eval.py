"""Unit tests for Phase 5 Packet 8 graph freeze and evaluation."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from smart_rag_core.evaluation.classes import QueryClass
from smart_rag_core.evaluation.graph_eval import (
    COMBINED_QUALITY_NO_CLAIM,
    DEADLINE_CAP_DOCUMENTS,
    PACKET7_PIN_COMMIT,
    PLAN_GRAPH_DOCUMENTS,
    build_phase5_packet8_report,
    call_accounting,
    envelope_decision,
    evaluate_coverage_gates,
    failing_mixed_hidden_by_english_slices,
    fixture_coverage_slices,
    fixture_sweep,
    maintenance_reserve_usd,
    render_frozen_manifest_markdown,
    render_graph_eval_markdown,
)
from smart_rag_core.evaluation.holdout import HoldoutSealedError
from smart_rag_core.evaluation.loader import (
    load_development_cases,
    load_qualification_cases,
)
from smart_rag_core.jobs.limits import (
    DEFAULT_GRAPH_INDEX_DEADLINE_SECONDS,
    GRAPH_CLEAN_REBUILD_SLA_DAYS,
    GRAPH_TARGET_CLEANUP_SLA_HOURS,
    MAPPING_COVERAGE_ARABIC_MIXED_MIN,
    MAPPING_SUPPORT_MIN,
    MAX_MAPPING_HYBRID_CALLS,
    MAX_MAPPING_RERANK_CALLS,
)
from smart_rag_core.retrieval.graph import (
    ADAPTER_MAX_GRAPH_CANDIDATES,
    ADAPTER_MAX_HOPS,
    ADAPTER_MAX_PATHS,
    GRAPH_FIELD_SEP,
    GRAPH_SURVIVAL_FALLBACK_THRESHOLD,
    INSPECTION_DEADLINE_SECONDS,
    INSPECTION_MAX_DEPTH,
    INSPECTION_MAX_ROWS,
    INSPECTION_STATEMENT_TIMEOUT,
    LIGHTRAG_PINNED_VERSION,
    LIGHTRAG_WHEEL_SHA256,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_MODULE = (
    REPO_ROOT
    / "packages"
    / "core"
    / "src"
    / "smart_rag_core"
    / "evaluation"
    / "graph_eval.py"
)
EVAL_SCRIPT = REPO_ROOT / "scripts" / "eval_phase5_graph_freeze.py"
MANIFEST_DOC = REPO_ROOT / "docs" / "graph" / "FROZEN_GRAPH_MANIFEST.md"
EVAL_DOC = REPO_ROOT / "docs" / "evaluation" / "PHASE5_GRAPH_EVAL.md"
HANDOFF_DOC = REPO_ROOT / "docs" / "graph" / "PHASE6_HANDOFF.md"
SCALING_DOC = REPO_ROOT / "docs" / "graph" / "SCALING_OPTIONS.md"


def test_packet8_holds_out_and_does_not_claim_combined() -> None:
    """Packet 8 freeze stays holdout-blind and records the Combined no-claim."""

    report = build_phase5_packet8_report()
    assert report.holdout_opened is False
    assert report.client_decision == "pending_user_acceptance"
    assert report.packet7_pin_commit == PACKET7_PIN_COMMIT
    assert report.pins["code_revision_git_sha"]
    assert report.combined_quality_claim == COMBINED_QUALITY_NO_CLAIM
    assert report.unmapped_returned_relations == 0
    assert report.coverage_gates_passed is True
    assert report.pins["lightrag"] == LIGHTRAG_PINNED_VERSION
    assert report.hashes["lightrag_wheel"] == LIGHTRAG_WHEEL_SHA256
    assert report.pins["graph_field_sep"] == GRAPH_FIELD_SEP
    assert "holdout" not in report.qualification_counts
    assert report.qualification_counts[QueryClass.GRAPH_MAPPING.value] >= 1
    extract = next(gate for gate in report.gates if gate.gate_id == "P8-EXTRACT-LIVE")
    assert extract.status == "unverified"
    combined = next(gate for gate in report.gates if gate.gate_id == "P8-COMBINED")
    assert combined.status == "deferred_phase_6"


def test_mixed_language_is_not_hidden_by_english_totals() -> None:
    """Arabic/mixed floors fail independently of English-heavy aggregates."""

    passed, reason = evaluate_coverage_gates(fixture_coverage_slices())
    assert passed is True
    assert reason == ""
    hidden, hidden_reason = evaluate_coverage_gates(
        failing_mixed_hidden_by_english_slices()
    )
    assert hidden is False
    assert hidden_reason == "language_gate"
    report = build_phase5_packet8_report()
    mixed = [item for item in report.language_metrics if item.language == "mixed"]
    arabic = [item for item in report.language_metrics if item.language == "ar"]
    assert mixed
    assert arabic
    assert all(item.gate_floor == MAPPING_COVERAGE_ARABIC_MIXED_MIN for item in mixed)
    assert all(item.passed for item in mixed)
    assert all(
        item.object_type in {"entity", "relation", "path_edge"} for item in mixed
    )


def test_call_accounting_is_zero_hidden_and_one_mapping_batch() -> None:
    """Query keyword/answer/support searches stay zero; mapping is one plus one."""

    accounting = call_accounting()
    assert accounting.query_keyword_extract == 0
    assert accounting.query_answer_generate == 0
    assert accounting.query_support_searches == 0
    assert accounting.mapping_hybrid_max == MAX_MAPPING_HYBRID_CALLS == 1
    assert accounting.mapping_rerank_max == MAX_MAPPING_RERANK_CALLS == 1
    assert accounting.cited_tests
    report = build_phase5_packet8_report()
    assert report.call_accounting == accounting


def test_envelope_is_reduced_and_reserve_uses_floor() -> None:
    """Unmeasured 2k rebuild reduces the advertised envelope to qualification scale."""

    assert DEADLINE_CAP_DOCUMENTS == (GRAPH_CLEAN_REBUILD_SLA_DAYS * 24 * 3_600) // int(
        DEFAULT_GRAPH_INDEX_DEADLINE_SECONDS
    )
    assert DEADLINE_CAP_DOCUMENTS < PLAN_GRAPH_DOCUMENTS
    report = build_phase5_packet8_report()
    envelope = report.envelope
    assert envelope.supported_documents < PLAN_GRAPH_DOCUMENTS
    assert envelope.supported_chunks is None
    assert envelope.bulk_onboarding_blocked is True
    assert envelope.seven_day_rebuild_of_plan_envelope is False
    assert envelope.measured_full_rebuild_cost_usd is None
    assert envelope.maintenance_reserve_usd == 800.0
    assert maintenance_reserve_usd(measured_full_rebuild_cost_usd=None) == 800.0
    assert maintenance_reserve_usd(measured_full_rebuild_cost_usd=100.0) == 800.0
    assert maintenance_reserve_usd(measured_full_rebuild_cost_usd=300.0) == 1_200.0
    reduced = envelope_decision(supported_documents=4)
    assert reduced.supported_documents == 4
    assert GRAPH_TARGET_CLEANUP_SLA_HOURS == 24
    assert GRAPH_CLEAN_REBUILD_SLA_DAYS == 7
    assert MAPPING_SUPPORT_MIN == 0.80
    assert GRAPH_SURVIVAL_FALLBACK_THRESHOLD == 0.50
    assert ADAPTER_MAX_GRAPH_CANDIDATES == 12
    assert ADAPTER_MAX_HOPS == 3
    assert ADAPTER_MAX_PATHS == 6
    assert INSPECTION_MAX_DEPTH == 3
    assert INSPECTION_MAX_ROWS == 200
    assert INSPECTION_STATEMENT_TIMEOUT == "3s"
    assert INSPECTION_DEADLINE_SECONDS == 10.0


def test_open_split_graph_mapping_count_matches_envelope() -> None:
    """Advertised documents equal open-split graph_mapping labels, not holdout."""

    report = build_phase5_packet8_report()
    qualification = load_qualification_cases()
    development = load_development_cases()
    assert all(case.split.value != "holdout" for case in qualification)
    assert all(case.split.value != "holdout" for case in development)
    open_mapping = sum(
        1
        for case in (*development, *qualification)
        if case.query_class is QueryClass.GRAPH_MAPPING
    )
    assert report.envelope.supported_documents == open_mapping
    assert open_mapping >= report.qualification_counts[QueryClass.GRAPH_MAPPING.value]


def test_fixture_sweep_covers_required_packets_5_to_7_invariants() -> None:
    """Packet 8 reuses Packets 5-7 fixtures instead of inventing Combined tests."""

    ids = {row.fixture_id for row in fixture_sweep()}
    required = {
        "collisions_aliases_do_not_merge",
        "global_steering",
        "mapping_repair",
        "low_survival",
        "partial_readiness",
        "temporal_limitation",
        "acl_blindness_versus_unauthorized_silence",
        "version_overlap",
        "deletion_acl_shared_source",
        "filtered_quarantined_disabled",
        "upgrade_rollback_refuse_same_schema",
        "unfunded_rebuild_quarantine",
        "tombstone_24h_7d",
        "inspection_bounds",
        "adapter_bounds",
    }
    assert required <= ids
    report = build_phase5_packet8_report()
    assert report.fixture_sweep == fixture_sweep()


def test_graph_eval_module_cannot_materialize_sealed_labels() -> None:
    """Freeze sources do not load sealed-split labels."""

    for path in (EVAL_MODULE, EVAL_SCRIPT):
        source = path.read_text(encoding="utf-8")
        dumped = ast.dump(ast.parse(source))
        assert "load_holdout" not in dumped
        assert "DatasetSplit.HOLDOUT" not in dumped
        assert "SMART_RAG_HOLDOUT_ACCESS=true" not in source


def test_graph_eval_refuses_enabled_holdout_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Packet 8 freeze cannot run in the same process as authorized holdout."""

    monkeypatch.setenv("SMART_RAG_HOLDOUT_ACCESS", "true")
    monkeypatch.setenv(
        "SMART_RAG_HOLDOUT_ACCESS_PURPOSE",
        "packet8_immutable_holdout",
    )
    monkeypatch.setenv("SMART_RAG_HOLDOUT_ACCESS_ACTOR", "unit-test")
    with pytest.raises(HoldoutSealedError, match="refuses to run"):
        build_phase5_packet8_report()


def test_rendered_packet8_markdown_matches_committed_docs() -> None:
    """Committed freeze and eval markdown are generated from the report."""

    report = build_phase5_packet8_report()
    manifest = render_frozen_manifest_markdown(report)
    evaluation = render_graph_eval_markdown(report)
    assert MANIFEST_DOC.read_text(encoding="utf-8").replace("\r\n", "\n") == manifest
    assert EVAL_DOC.read_text(encoding="utf-8").replace("\r\n", "\n") == evaluation
    assert "unverified" in evaluation
    assert COMBINED_QUALITY_NO_CLAIM in evaluation


def test_phase6_handoff_and_scaling_docs_are_options_and_no_claim() -> None:
    """Handoff freezes interfaces without Combined quality; scaling is options only."""

    handoff = HANDOFF_DOC.read_text(encoding="utf-8")
    scaling = SCALING_DOC.read_text(encoding="utf-8")
    for token in (
        "GraphRetriever",
        "GraphRetrievalResult",
        "temporal_graph_limitation",
        "graph_survival_below_threshold",
        "graph_acl_blindness",
        "hl_keywords",
        "ll_keywords",
        "Phase 6 owns Combined fusion",
    ):
        assert token in handoff
    assert "options only" in scaling.lower()
    scaling_lower = scaling.lower()
    for option in (
        "domain",
        "dedicated managed",
        "incremental",
        "hybrid-only",
    ):
        assert option in scaling_lower
    assert "query agent" not in handoff.lower()

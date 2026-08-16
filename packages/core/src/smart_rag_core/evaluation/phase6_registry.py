"""Phase 6 evaluation registry: map packet-7 categories to existing tests/docs.

This module does not reimplement Phase 4, open the holdout, or run live
OpenAI. QT-EVAL-009 Combined +10pp stays ``unverified``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from smart_rag_core.evaluation.holdout import HoldoutAccess

EvalMappingStatus = Literal["mapped", "unverified"]

REPO_ROOT = Path(__file__).resolve().parents[5]


@dataclass(frozen=True, slots=True)
class EvalCategoryMapping:
    """One packet-7 evaluation category mapped to an existing command.

    Attributes:
        category_id: Stable registry key.
        command: Existing pytest node, script, or documented check.
        evidence_doc: Canonical doc path relative to the repo root.
        status: ``mapped`` when a command exists; ``unverified`` when the
            live quality target is explicitly not claimed.
        notes: Constraints such as holdout isolation or mock-mode default.
    """

    category_id: str
    command: str
    evidence_doc: str
    status: EvalMappingStatus
    notes: str


REQUIRED_CATEGORY_IDS: tuple[str, ...] = (
    "chunking_cleaning",
    "query_profile_fields",
    "retrieval",
    "ablations",
    "citation_faithfulness",
    "injection",
    "tools",
    "malware_ssrf",
    "historical_relationship_hybrid_temporal_graph_limitation",
    "coverage_1_0",
    "negation",
    "media_limitation",
    "acl_blindness",
    "cache_leak",
    "reaper",
    "sse_handshake_unknown_event",
    "holdout_isolation",
    "online_eval_bounded",
    "qt_eval_009_combined_plus_10pp",
    "rewrite_correction_mapping_idempotency",
    "conversation_deletion",
    "langsmith_retry_redaction",
    "governance_external_flows",
)

PHASE6_EVAL_REGISTRY: dict[str, EvalCategoryMapping] = {
    "chunking_cleaning": EvalCategoryMapping(
        category_id="chunking_cleaning",
        command="uv run python -m pytest tests/unit/test_chunking_service.py tests/unit/test_chunking_dedup.py -q",
        evidence_doc="docs/ingestion/CHUNKING_CONTRACT.md",
        status="mapped",
        notes="Phase 4 chunk/cleaning fixtures; no relabel.",
    ),
    "query_profile_fields": EvalCategoryMapping(
        category_id="query_profile_fields",
        command="uv run python -m pytest tests/unit/test_query_profile.py tests/unit/test_phase6_querytype_map.py -q",
        evidence_doc="docs/evaluation/QUERY_PROFILE_EVAL.md",
        status="mapped",
        notes="Per-field labels on frozen case IDs.",
    ),
    "retrieval": EvalCategoryMapping(
        category_id="retrieval",
        command="uv run python -m pytest tests/unit/test_hybrid_retrieval_foundations.py tests/unit/test_hybrid_fusion.py tests/unit/test_hybrid_rerank.py tests/contract/test_hybrid_retrieval.py -q",
        evidence_doc="docs/retrieval/HYBRID_RETRIEVAL_CONTRACT.md",
        status="mapped",
        notes="Existing Phase 4/5 retrieval and recheck tests.",
    ),
    "ablations": EvalCategoryMapping(
        category_id="ablations",
        command="uv run python -m pytest tests/unit/test_combined_fusion.py tests/unit/test_hybrid_fusion.py -q",
        evidence_doc="docs/evaluation/PHASE4_ABLATIONS.md",
        status="mapped",
        notes="HoldoutAccess.denied(); no threshold retune.",
    ),
    "citation_faithfulness": EvalCategoryMapping(
        category_id="citation_faithfulness",
        command="uv run python -m pytest tests/unit/test_answer_verifier.py tests/unit/test_structured_table.py -q",
        evidence_doc="docs/agent/ANSWER_VERIFICATION.md",
        status="mapped",
        notes="Faithfulness, table correctness, citation checks.",
    ),
    "injection": EvalCategoryMapping(
        category_id="injection",
        command="uv run python -m pytest tests/unit/test_parser_governance.py tests/unit/test_query_profile.py tests/unit/test_fastapi_security.py tests/contract/test_hybrid_retrieval.py -q",
        evidence_doc="docs/security/OPENAI_DATA_GOVERNANCE.md",
        status="mapped",
        notes="Parser/HTML/OCR, profile injection, XSS JSON escape, BM25 syntax.",
    ),
    "tools": EvalCategoryMapping(
        category_id="tools",
        command="uv run python -m pytest tests/unit/test_optional_tools.py tests/unit/test_optional_tools_discovery.py -q",
        evidence_doc="docs/agent/OPTIONAL_TOOLS.md",
        status="mapped",
        notes="Discovery precision and unselected schema exclusion.",
    ),
    "malware_ssrf": EvalCategoryMapping(
        category_id="malware_ssrf",
        command="uv run python -m pytest tests/unit/test_clamav_client.py tests/unit/test_crawl_proxy.py tests/unit/test_crawl_policy.py tests/unit/test_parser_sandbox.py -q",
        evidence_doc="docs/runbooks/CLAMAV_SCAN_AND_PROMOTION.md",
        status="mapped",
        notes="Existing malware, SSRF, parser isolation tests.",
    ),
    "historical_relationship_hybrid_temporal_graph_limitation": EvalCategoryMapping(
        category_id="historical_relationship_hybrid_temporal_graph_limitation",
        command="uv run python -m pytest tests/unit/test_query_routing_matrix.py tests/unit/test_graph_retriever.py -q",
        evidence_doc="docs/agent/QUERY_ROUTING.md",
        status="mapped",
        notes="Historical relationship → Hybrid + temporal_graph_limitation.",
    ),
    "coverage_1_0": EvalCategoryMapping(
        category_id="coverage_1_0",
        command="uv run python -m pytest tests/unit/test_hybrid_coverage.py tests/unit/test_query_routing_matrix.py::test_whole_document_requires_section_coverage_one -q",
        evidence_doc="docs/evaluation/COVERAGE_QUALIFICATION.md",
        status="mapped",
        notes="Whole-document section coverage 1.0 pass/refusal.",
    ),
    "negation": EvalCategoryMapping(
        category_id="negation",
        command="uv run python -m pytest tests/unit/test_query_routing_matrix.py::test_negation_never_combined_or_complement -q",
        evidence_doc="docs/agent/QUERY_ROUTING.md",
        status="mapped",
        notes="Negation clarification/proof/refusal; no complement retrieve.",
    ),
    "media_limitation": EvalCategoryMapping(
        category_id="media_limitation",
        command="uv run python -m pytest tests/unit/test_query_routing_matrix.py::test_media_refusal_cannot_answer tests/unit/test_hybrid_coverage.py -q",
        evidence_doc="docs/agent/QUERY_ROUTING.md",
        status="mapped",
        notes="Media limitation refusal; captions may use Hybrid.",
    ),
    "acl_blindness": EvalCategoryMapping(
        category_id="acl_blindness",
        command="uv run python -m pytest tests/unit/test_query_routing_matrix.py::test_unauthorized_blindness_suppressed tests/unit/test_hybrid_coverage.py::test_acl_negative_is_authorization_not_ranking tests/unit/test_phase4_ranked_ids.py::test_acl_negative_gold_uuid_is_a_leak -q",
        evidence_doc="docs/security/AUTHORIZATION_MODEL.md",
        status="mapped",
        notes="Authorized ACL-blindness; zero unauthorized disclosure.",
    ),
    "cache_leak": EvalCategoryMapping(
        category_id="cache_leak",
        command="uv run python -m pytest tests/contract/test_retrieval_cache.py tests/contract/test_hybrid_retrieval.py::test_recheck_drops_stale_and_unauthorized_ids -q",
        evidence_doc="docs/retrieval/HYBRID_RETRIEVAL_CONTRACT.md",
        status="mapped",
        notes="Cache IDs/ranks only; recheck drops deleted/restricted.",
    ),
    "reaper": EvalCategoryMapping(
        category_id="reaper",
        command="uv run python -m pytest tests/contract/test_query_memory_reaper.py -q",
        evidence_doc="docs/agent/MEMORY_DELETION.md",
        status="mapped",
        notes="7/30-day GC independent of budget true-up.",
    ),
    "sse_handshake_unknown_event": EvalCategoryMapping(
        category_id="sse_handshake_unknown_event",
        command="uv run python -m pytest tests/unit/test_sse_protocol.py tests/contract/test_sse_resume.py tests/contract/test_sse_heartbeat.py -q",
        evidence_doc="docs/api/SSE.md",
        status="mapped",
        notes="Handshake before paid work; unknown-event tolerance.",
    ),
    "holdout_isolation": EvalCategoryMapping(
        category_id="holdout_isolation",
        command="uv run python -m pytest tests/unit/test_phase4_freeze.py tests/unit/test_phase4_materialize.py -q",
        evidence_doc="docs/evaluation/PHASE4_HOLDOUT.md",
        status="mapped",
        notes="HoldoutAccess.denied(); no label read or threshold retune.",
    ),
    "online_eval_bounded": EvalCategoryMapping(
        category_id="online_eval_bounded",
        command="uv run python -m pytest tests/unit/test_phase6_eval_registry.py -q",
        evidence_doc="docs/evaluation/PHASE6_EVAL_REGISTRY.md",
        status="mapped",
        notes="Mock-mode default; sample ≤20; USD ≤2.00; no unlimited OpenAI.",
    ),
    "qt_eval_009_combined_plus_10pp": EvalCategoryMapping(
        category_id="qt_eval_009_combined_plus_10pp",
        command="uv run python -m pytest tests/unit/test_combined_fusion.py::test_resolved_path_fusion_beats_naive_union_on_dev_fixtures -q",
        evidence_doc="docs/evaluation/PHASE4_FREEZE.md",
        status="unverified",
        notes="Live Combined +10pp (QT-EVAL-009) remains unverified. Synthetic fixtures only.",
    ),
    "rewrite_correction_mapping_idempotency": EvalCategoryMapping(
        category_id="rewrite_correction_mapping_idempotency",
        command="uv run python -m pytest tests/unit/test_query_correction.py tests/contract/test_query_run_admission.py tests/unit/test_graph_mapping.py -q",
        evidence_doc="docs/agent/QUERY_ADMISSION.md",
        status="mapped",
        notes="One correction, mapping, admit idempotency/reconnect.",
    ),
    "conversation_deletion": EvalCategoryMapping(
        category_id="conversation_deletion",
        command="uv run python -m pytest tests/unit/test_conversation_deletion.py tests/contract/test_query_memory_reaper.py -q",
        evidence_doc="docs/agent/MEMORY_DELETION.md",
        status="mapped",
        notes="Immediate tombstone, lingering-ID search, 204/404.",
    ),
    "langsmith_retry_redaction": EvalCategoryMapping(
        category_id="langsmith_retry_redaction",
        command="uv run python -m pytest tests/unit/test_langsmith_tracing.py tests/contract/test_query_memory_reaper.py -q",
        evidence_doc="docs/development/LANGSMITH_TRACING.md",
        status="mapped",
        notes="Canary redaction; durable deletion request + 24h retry. Cloud delete not claimed.",
    ),
    "governance_external_flows": EvalCategoryMapping(
        category_id="governance_external_flows",
        command="uv run python -m pytest tests/unit/test_external_processing_governance.py tests/unit/test_langsmith_tracing.py -q",
        evidence_doc="docs/security/SUBPROCESSOR_GOVERNANCE.md",
        status="mapped",
        notes="Unknown/prohibited/unverified flows cannot send private payloads.",
    ),
}


def holdout_remains_sealed() -> bool:
    """Return whether the launch holdout stays denied.

    Returns:
        True when ``HoldoutAccess.denied()`` reports not allowed.
    """

    return HoldoutAccess.denied().allowed is False


def missing_registry_categories(
    registry: dict[str, EvalCategoryMapping] | None = None,
) -> tuple[str, ...]:
    """Return required category ids that lack a mapped command or file.

    Args:
        registry: Optional override. Default is ``PHASE6_EVAL_REGISTRY``.

    Returns:
        Category ids that are missing, have an empty command, or point at
        a test/doc path that does not exist.
    """

    table = registry if registry is not None else PHASE6_EVAL_REGISTRY
    missing: list[str] = []
    for category_id in REQUIRED_CATEGORY_IDS:
        mapping = table.get(category_id)
        if mapping is None or not mapping.command.strip():
            missing.append(category_id)
            continue
        if not _command_paths_exist(mapping.command):
            missing.append(category_id)
            continue
        doc_path = REPO_ROOT / mapping.evidence_doc
        if not doc_path.is_file():
            missing.append(category_id)
    return tuple(missing)


def qt_eval_009_status() -> str:
    """Return the QT-EVAL-009 live mapping status.

    Returns:
        Always ``unverified`` until a later packet proves live Combined +10pp.
    """

    return PHASE6_EVAL_REGISTRY["qt_eval_009_combined_plus_10pp"].status


def _command_paths_exist(command: str) -> bool:
    """Return whether pytest targets in a command exist on disk.

    Args:
        command: Quality command string.

    Returns:
        True when every ``tests/`` path token exists (node ids stripped).
    """

    found_test_path = False
    for token in command.split():
        if not token.startswith("tests/"):
            continue
        found_test_path = True
        path_token = token.split("::", 1)[0]
        if not (REPO_ROOT / path_token).exists():
            return False
    return found_test_path

"""Phase 5 Packet 8 graph freeze, fixture evaluation, and envelope reduction.

This module never materializes sealed holdout labels. It loads development
and qualification cases only, refuses to run while holdout access is
enabled, and does not claim Combined answer quality or live corpus
extraction precision/recall.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from smart_rag_core.evaluation.classes import QueryClass
from smart_rag_core.evaluation.holdout import HoldoutAccess, HoldoutSealedError
from smart_rag_core.evaluation.loader import (
    load_development_cases,
    load_qualification_cases,
)
from smart_rag_core.evaluation.schema import DATASET_SCHEMA_VERSION, LABEL_REVISION
from smart_rag_core.ingestion.embeddings.policy import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
)
from smart_rag_core.jobs.extraction_policy import (
    DEFAULT_EXTRACTION_POLICY_HASH,
    default_extraction_policy,
)
from smart_rag_core.jobs.limits import (
    DEFAULT_GRAPH_INDEX_DEADLINE_SECONDS,
    DEFAULT_GRAPH_INDEX_ESTIMATE_USD,
    DEFAULT_MONTHLY_GRAPH_MAINTENANCE_BUDGET_USD,
    GRAPH_CLEAN_REBUILD_SLA_DAYS,
    GRAPH_PIPELINE_VERSION,
    GRAPH_SURVIVAL_ROLLING_WINDOW,
    GRAPH_TARGET_CLEANUP_SLA_HOURS,
    MAPPING_COVERAGE_ARABIC_MIXED_MIN,
    MAPPING_COVERAGE_OVERALL_MIN,
    MAPPING_SUPPORT_MIN,
    MAX_MAPPING_HYBRID_CALLS,
    MAX_MAPPING_RERANK_CALLS,
)
from smart_rag_core.retrieval.graph import (
    ADAPTER_MAX_GRAPH_CANDIDATES,
    ADAPTER_MAX_HOPS,
    ADAPTER_MAX_PATHS,
    DEFAULT_GRAPH_WORKSPACE,
    DEFAULT_MAX_SOURCE_IDS_PER_ENTITY,
    DEFAULT_MAX_SOURCE_IDS_PER_RELATION,
    GRAPH_FIELD_SEP,
    GRAPH_SOURCE_ENVELOPE_VERSION,
    GRAPH_SURVIVAL_FALLBACK_THRESHOLD,
    GRAPH_SURVIVAL_ROLLING_ALERT_THRESHOLD,
    INSPECTION_DEADLINE_SECONDS,
    INSPECTION_MAX_DEPTH,
    INSPECTION_MAX_ROWS,
    INSPECTION_STATEMENT_TIMEOUT,
    LIGHTRAG_CHUNK_OVERLAP_TOKEN_SIZE,
    LIGHTRAG_CHUNK_TOKEN_SIZE,
    LIGHTRAG_PINNED_VERSION,
    LIGHTRAG_RELEASE_COMMIT,
    LIGHTRAG_TIKTOKEN_MODEL,
    LIGHTRAG_WHEEL_SHA256,
    SELECTED_GRAPH_STORAGE,
    graph_chunker_config_snapshot,
)
from smart_rag_core.retrieval.graph_mapping import (
    CoverageSlice,
    evaluate_coverage_gates,
    mapping_config_generation,
)

REPO_ROOT = Path(__file__).resolve().parents[5]
PHASE4_FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "evaluation" / "phase4"
SCHEMA_FINGERPRINT_PATH = (
    REPO_ROOT / "tests" / "fixtures" / "lightrag" / "schema_fingerprint_v1.json"
)
PACKET7_PIN_COMMIT = "c546f9c"
CODE_REVISION_GIT_SHA = "52b331f06320a5086e1018c2fa1149abe72a33f8"
PLAN_GRAPH_DOCUMENTS = 2_000
PLAN_GRAPH_CHUNKS = 200_000
SEVEN_DAY_SECONDS = GRAPH_CLEAN_REBUILD_SLA_DAYS * 24 * 3_600
DEADLINE_CAP_DOCUMENTS = SEVEN_DAY_SECONDS // int(DEFAULT_GRAPH_INDEX_DEADLINE_SECONDS)
COMBINED_QUALITY_NO_CLAIM = (
    "Phase 5 proves graph infrastructure, mapping, resolver, and envelope "
    "only. Phase 6 owns Combined fusion, verifier/citations, holdout, and "
    "the at-least-10-point relationship/multi-hop gain. This packet does "
    "not claim Combined answer quality."
)


def code_revision_git_sha() -> str:
    """Return the frozen git SHA recorded in the Packet 8 manifest.

    Live ``HEAD`` cannot be written into committed freeze markdown: the
    SHA is unknown until the commit exists, and the next commit would
    invalidate the files. The pin is the last Hybrid/GraphRAG
    implementation revision this freeze describes.

    Returns:
        Forty-character SHA of ``CODE_REVISION_GIT_SHA``.
    """

    return CODE_REVISION_GIT_SHA


GraphGateStatus = Literal[
    "pass_fixture",
    "unverified",
    "reduced",
    "deferred_phase_6",
]


class GraphEvalGate(BaseModel):
    """One Packet 8 gate with an honest measurement posture.

    Attributes:
        gate_id: Stable identifier.
        title: Short human label.
        status: Measurement posture. ``unverified`` is not a pass.
        signed_target: Plan or quality-target value.
        evidence: Fixture, test, or unverified reason.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    gate_id: str
    title: str
    status: GraphGateStatus
    signed_target: str
    evidence: str


class GraphCallAccounting(BaseModel):
    """Query and mapping call ceilings proven by existing tests.

    Attributes:
        query_keyword_extract: Hidden keyword-extract count. Must stay ``0``.
        query_answer_generate: Hidden answer-generate count. Must stay ``0``.
        query_support_searches: Per-statement Hybrid searches. Must stay ``0``.
        mapping_hybrid_max: Batched Hybrid retrieves per document.
        mapping_rerank_max: Support rerank batches per document.
        cited_tests: Test node ids that prove the counters.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    query_keyword_extract: int = Field(ge=0, le=0)
    query_answer_generate: int = Field(ge=0, le=0)
    query_support_searches: int = Field(ge=0, le=0)
    mapping_hybrid_max: int = Field(ge=1, le=1)
    mapping_rerank_max: int = Field(ge=1, le=1)
    cited_tests: tuple[str, ...]


class FixtureSweepRow(BaseModel):
    """One Packets 5-7 fixture reused by the Packet 8 checklist.

    Attributes:
        fixture_id: Stable checklist id.
        packet: Owning Phase 5 packet number.
        test_node: Pytest node id fragment.
        invariant: Security or bound invariant proven.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    fixture_id: str
    packet: int = Field(ge=1, le=7)
    test_node: str
    invariant: str


class GraphEnvelopeDecision(BaseModel):
    """Advertised graph envelope after Packet 8 measurement honesty.

    Attributes:
        plan_documents: Signed Phase 1 default (2,000). Not advertised.
        plan_chunks: Signed Phase 1 default (200,000). Not advertised.
        deadline_cap_documents: Sequential jobs at the 600s deadline in 7 days.
        supported_documents: Reduced advertised current-document envelope.
        supported_chunks: ``None`` when source-chunk rebuild is unmeasured.
        bulk_onboarding_blocked: True until a measured rebuild exists.
        seven_day_rebuild_of_plan_envelope: Always false in this packet.
        measured_full_rebuild_cost_usd: ``None`` when unmeasured.
        maintenance_reserve_usd: ``max(800, 4 x measured)`` or the USD 800 floor.
        uncertainty: Why the plan envelope is not claimed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    plan_documents: int
    plan_chunks: int
    deadline_cap_documents: int
    supported_documents: int = Field(ge=0)
    supported_chunks: int | None
    bulk_onboarding_blocked: Literal[True]
    seven_day_rebuild_of_plan_envelope: Literal[False]
    measured_full_rebuild_cost_usd: float | None
    maintenance_reserve_usd: float = Field(ge=0)
    uncertainty: str


class LanguageTypeMetric(BaseModel):
    """One language/type mapping or survival row from fixtures.

    Attributes:
        language: ``en``, ``ar``, or ``mixed``.
        object_type: ``entity``, ``relation``, ``path_edge``, or ``chunk``.
        numerator: Accepted objects in the fixture slice.
        denominator: Eligible objects including exclusions.
        ratio: ``numerator / denominator``.
        gate_floor: Signed coverage floor for that language.
        passed: Whether this slice meets its own floor.
        source: Fixture or test provenance. Never a live corpus claim.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    language: Literal["en", "ar", "mixed"]
    object_type: Literal["entity", "relation", "path_edge", "chunk"]
    numerator: int = Field(ge=0)
    denominator: int = Field(ge=1)
    ratio: float
    gate_floor: float
    passed: bool
    source: str


class Phase5Packet8Report(BaseModel):
    """Immutable Packet 8 freeze, evaluation, and envelope snapshot.

    Attributes:
        holdout_opened: Always false.
        combined_quality_claim: Explicit no-claim text.
        packet7_pin_commit: Packet 1-7 freeze base on ``main``.
        pins: Artifact, model, chunker, delimiter, and bound pins.
        hashes: Dataset and schema fingerprint digests.
        workspace_config_generation: Pointer-generation-1 mapping digest.
        entity_rules_generation: Default approved-rule generation.
        extraction_policy_hash: Default extraction overlay digest.
        qualification_counts: Qualification case counts by class (no holdout).
        language_metrics: Per-language and per-type fixture metrics.
        coverage_gates_passed: Overall plus per-language fixture gates.
        unmapped_returned_relations: Must stay ``0``.
        call_accounting: Hidden-callback and mapping-call proof.
        envelope: Reduced advertised envelope and reserve.
        fixture_sweep: Packets 5-7 checklist.
        gates: Honest gate catalog.
        client_decision: User acceptance still required.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    holdout_opened: Literal[False]
    combined_quality_claim: str
    packet7_pin_commit: str
    pins: dict[str, str]
    hashes: dict[str, str]
    workspace_config_generation: str
    entity_rules_generation: int
    extraction_policy_hash: str
    qualification_counts: dict[str, int]
    language_metrics: tuple[LanguageTypeMetric, ...]
    coverage_gates_passed: bool
    unmapped_returned_relations: int = Field(ge=0, le=0)
    call_accounting: GraphCallAccounting
    envelope: GraphEnvelopeDecision
    fixture_sweep: tuple[FixtureSweepRow, ...]
    gates: tuple[GraphEvalGate, ...]
    client_decision: Literal["pending_user_acceptance"]


def sha256_file(path: Path) -> str:
    """Return the SHA-256 hex digest of git-style LF file bytes.

    Windows ``core.autocrlf`` working trees must not change freeze hashes.
    The digest is over ``\\n``-normalized bytes so Linux CI matches.

    Args:
        path: File to hash.

    Returns:
        Lowercase hex digest.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
    """

    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _require_holdout_denied() -> None:
    """Fail closed when sealed-label access is enabled in this process.

    Raises:
        HoldoutSealedError: If sealed-label access is enabled in settings.
    """

    access = HoldoutAccess.from_settings()
    if access.allowed:
        raise HoldoutSealedError(
            "packet 8 graph freeze refuses to run while holdout access is enabled"
        )


def fixture_coverage_slices() -> tuple[CoverageSlice, ...]:
    """Return per-language/type slices that encode existing unit fixtures.

    English 20/20 plus Arabic/mixed 17/20 match
    ``test_language_gate_not_hidden_by_english_aggregate`` and extend the
    same 0.85 floor to mixed so a language cannot be averaged away. These
    are gate-contract fixtures, not live LightRAG extraction scores.

    Returns:
        Coverage slices for ``evaluate_coverage_gates``.
    """

    rows: list[CoverageSlice] = []
    for language, numerator, denominator in (
        ("en", 20, 20),
        ("ar", 17, 20),
        ("mixed", 17, 20),
    ):
        for object_type in ("entity", "relation", "path_edge"):
            rows.append(
                CoverageSlice(
                    language=language,
                    object_type=object_type,
                    method="hash",
                    numerator=numerator,
                    denominator=denominator,
                    exclusion_count=denominator - numerator,
                )
            )
    return tuple(rows)


def failing_mixed_hidden_by_english_slices() -> tuple[CoverageSlice, ...]:
    """Return slices where mixed coverage fails under high English totals.

    Returns:
        English-perfect plus mixed-failing chunk slices.
    """

    return (
        CoverageSlice(
            language="en",
            object_type="chunk",
            method="hash",
            numerator=20,
            denominator=20,
            exclusion_count=0,
        ),
        CoverageSlice(
            language="mixed",
            object_type="chunk",
            method="hash",
            numerator=2,
            denominator=4,
            exclusion_count=2,
        ),
    )


def language_type_metrics() -> tuple[LanguageTypeMetric, ...]:
    """Build per-language/type rows from the gate-contract slices.

    Returns:
        One metric per language and object type. Live corpus is omitted.
    """

    languages: tuple[Literal["en", "ar", "mixed"], ...] = ("en", "ar", "mixed")
    object_types: tuple[Literal["entity", "relation", "path_edge"], ...] = (
        "entity",
        "relation",
        "path_edge",
    )
    accepted = {"en": (20, 20), "ar": (17, 20), "mixed": (17, 20)}
    metrics: list[LanguageTypeMetric] = []
    source = (
        "unit CoverageSlice gate contract "
        "(test_language_gate_not_hidden_by_english_aggregate); "
        "live LightRAG extraction P/R unverified"
    )
    for language in languages:
        numerator, denominator = accepted[language]
        floor = (
            MAPPING_COVERAGE_ARABIC_MIXED_MIN
            if language in {"ar", "mixed"}
            else MAPPING_COVERAGE_OVERALL_MIN
        )
        ratio = numerator / denominator
        for object_type in object_types:
            metrics.append(
                LanguageTypeMetric(
                    language=language,
                    object_type=object_type,
                    numerator=numerator,
                    denominator=denominator,
                    ratio=ratio,
                    gate_floor=floor,
                    passed=ratio >= floor,
                    source=source,
                )
            )
    return tuple(metrics)


def call_accounting() -> GraphCallAccounting:
    """Return proven query/mapping call ceilings.

    Returns:
        Accounting with hidden callbacks at zero and mapping caps at one.
    """

    return GraphCallAccounting(
        query_keyword_extract=0,
        query_answer_generate=0,
        query_support_searches=0,
        mapping_hybrid_max=MAX_MAPPING_HYBRID_CALLS,
        mapping_rerank_max=MAX_MAPPING_RERANK_CALLS,
        cited_tests=(
            "tests/contract/test_lightrag_contract.py::"
            "test_query_callbacks_bounds_delete_status_and_cancel",
            "tests/unit/test_graph_retriever.py::"
            "test_hidden_keyword_callback_fails_closed",
            "tests/unit/test_graph_retriever.py::test_survival_below_threshold_signal",
            "tests/unit/test_graph_mapping.py::"
            "test_unresolved_batch_uses_one_hybrid_and_one_rerank",
            "tests/unit/test_graph_mapping.py::test_repair_must_not_query_hybrid",
        ),
    )


def fixture_sweep() -> tuple[FixtureSweepRow, ...]:
    """Return the Packets 5-7 fixture checklist Packet 8 reuses.

    Returns:
        Ordered checklist rows. Combined/SSE paths are intentionally absent.
    """

    return (
        FixtureSweepRow(
            fixture_id="collisions_aliases_do_not_merge",
            packet=6,
            test_node="tests/unit/test_entity_rules.py",
            invariant="PROJECT::atlas stays distinct from PRODUCT::atlas",
        ),
        FixtureSweepRow(
            fixture_id="global_steering",
            packet=5,
            test_node="tests/unit/test_graph_retriever.py::test_global_steering_is_not_evidence",
            invariant="global expansions are steering only, never citations",
        ),
        FixtureSweepRow(
            fixture_id="mapping_repair",
            packet=4,
            test_node="tests/unit/test_graph_mapping.py::test_repair_must_not_query_hybrid",
            invariant="repair does not run query-time Hybrid",
        ),
        FixtureSweepRow(
            fixture_id="low_survival",
            packet=5,
            test_node=(
                "tests/unit/test_graph_retriever.py::"
                "test_survival_below_threshold_signal"
            ),
            invariant="survival < 0.50 emits graph_survival_below_threshold",
        ),
        FixtureSweepRow(
            fixture_id="partial_readiness",
            packet=5,
            test_node="tests/unit/test_graph_resolver.py::test_visibility_limitations_omit_names",
            invariant="partial-readiness count never names restricted documents",
        ),
        FixtureSweepRow(
            fixture_id="temporal_limitation",
            packet=5,
            test_node=(
                "tests/unit/test_graph_retriever.py::"
                "test_historical_relationship_skips_vendor"
            ),
            invariant="historical/as_of skips vendor and emits temporal_graph_limitation",
        ),
        FixtureSweepRow(
            fixture_id="acl_blindness_versus_unauthorized_silence",
            packet=5,
            test_node="tests/contract/test_graph_retrieval.py::test_resolver_maps_inspection_acl_and_repair",
            invariant="authorized ACL-blindness count; unauthorized silence",
        ),
        FixtureSweepRow(
            fixture_id="version_overlap",
            packet=7,
            test_node=(
                "tests/contract/test_graph_lifecycle.py::"
                "test_version_switch_exposes_exactly_one_current"
            ),
            invariant="pointer crashes expose exactly one current version",
        ),
        FixtureSweepRow(
            fixture_id="deletion_acl_shared_source",
            packet=7,
            test_node=(
                "tests/contract/test_graph_lifecycle.py::"
                "test_shared_entity_deleted_version_does_not_survive"
            ),
            invariant="deleted/restricted shared-source evidence does not survive",
        ),
        FixtureSweepRow(
            fixture_id="filtered_quarantined_disabled",
            packet=7,
            test_node=(
                "tests/unit/test_graph_lifecycle.py::"
                "test_disabled_and_quarantined_emit_graph_outage"
            ),
            invariant="disabled/quarantined query path is graph_outage",
        ),
        FixtureSweepRow(
            fixture_id="upgrade_rollback_refuse_same_schema",
            packet=7,
            test_node=(
                "tests/contract/test_graph_lifecycle.py::"
                "test_same_schema_upgrade_is_recorded_as_refused"
            ),
            invariant="same-schema upgrade is refused; snapshot restore is rollback",
        ),
        FixtureSweepRow(
            fixture_id="unfunded_rebuild_quarantine",
            packet=7,
            test_node=(
                "tests/contract/test_graph_lifecycle.py::"
                "test_unfunded_rebuild_fails_closed"
            ),
            invariant="unfunded rebuild quarantines; canonical deletion continues",
        ),
        FixtureSweepRow(
            fixture_id="tombstone_24h_7d",
            packet=7,
            test_node=(
                "tests/unit/test_graph_lifecycle.py::"
                "test_tombstone_slas_are_twenty_four_hours_and_seven_days"
            ),
            invariant="target_cleanup 24h and clean_rebuild 7d; live SLA unverified",
        ),
        FixtureSweepRow(
            fixture_id="inspection_bounds",
            packet=5,
            test_node="tests/unit/test_graph_retriever.py::test_inspect_deadline_and_seed_limit",
            invariant="inspect depth 3 / 200 rows / 3s statement_timeout / 10s deadline",
        ),
        FixtureSweepRow(
            fixture_id="adapter_bounds",
            packet=5,
            test_node="tests/unit/test_graph_resolver.py::test_clamp_graph_leads_caps_twelve_and_stable_sort",
            invariant="12 candidates, 3 hops, 6 paths",
        ),
    )


def maintenance_reserve_usd(*, measured_full_rebuild_cost_usd: float | None) -> float:
    """Return the signed maintenance reserve.

    Args:
        measured_full_rebuild_cost_usd: Measured rebuild cost, or ``None``.

    Returns:
        ``max(USD 800, 4 x measured)`` when measured; otherwise the USD 800
        floor. A missing measurement does not become ``4 x 0``.
    """

    floor = DEFAULT_MONTHLY_GRAPH_MAINTENANCE_BUDGET_USD
    if measured_full_rebuild_cost_usd is None:
        return floor
    return max(floor, 4.0 * measured_full_rebuild_cost_usd)


def envelope_decision(*, supported_documents: int) -> GraphEnvelopeDecision:
    """Reduce the advertised envelope because a 2k/200k rebuild is unproven.

    The 600-second index deadline already caps sequential 7-day throughput
    at ``DEADLINE_CAP_DOCUMENTS`` (1008). The plan default of 2,000 exceeds
    that bound. Live mapping-verified documents/hour is
    ``insufficient-sample``. Packet 8 therefore advertises qualification-scale
    labeled graph_mapping volume only and blocks bulk onboarding.

    Args:
        supported_documents: Open-split ``graph_mapping`` labeled count.

    Returns:
        Reduced envelope with the USD 800 reserve floor.
    """

    return GraphEnvelopeDecision(
        plan_documents=PLAN_GRAPH_DOCUMENTS,
        plan_chunks=PLAN_GRAPH_CHUNKS,
        deadline_cap_documents=int(DEADLINE_CAP_DOCUMENTS),
        supported_documents=supported_documents,
        supported_chunks=None,
        bulk_onboarding_blocked=True,
        seven_day_rebuild_of_plan_envelope=False,
        measured_full_rebuild_cost_usd=None,
        maintenance_reserve_usd=maintenance_reserve_usd(
            measured_full_rebuild_cost_usd=None
        ),
        uncertainty=(
            "No live mapping-verified documents/hour or full-rebuild cost. "
            f"Sequential jobs at the {int(DEFAULT_GRAPH_INDEX_DEADLINE_SECONDS)}s "
            f"deadline cannot finish {PLAN_GRAPH_DOCUMENTS} documents inside "
            f"{GRAPH_CLEAN_REBUILD_SLA_DAYS} days "
            f"(cap {int(DEADLINE_CAP_DOCUMENTS)}). Source-chunk rebuild of "
            f"{PLAN_GRAPH_CHUNKS} is unmeasured. Advertised envelope is "
            "qualification-scale labeled graph_mapping volume; bulk "
            "onboarding is blocked."
        ),
    )


def _gates(
    *, coverage_passed: bool, supported_documents: int
) -> tuple[GraphEvalGate, ...]:
    """Build the honest Packet 8 gate catalog.

    Args:
        coverage_passed: Fixture coverage-gate result.
        supported_documents: Reduced advertised document envelope.

    Returns:
        Gates. Live extraction is ``unverified``, not a pass.
    """

    mapping_status: GraphGateStatus = (
        "pass_fixture" if coverage_passed else "unverified"
    )
    return (
        GraphEvalGate(
            gate_id="P8-EXTRACT-LIVE",
            title="Live LightRAG extraction P/R on qualification corpus",
            status="unverified",
            signed_target="per-language extraction P/R; do not average languages",
            evidence=(
                "No live extraction run. GRAPH_MAPPING qualification labels "
                "are query text, not extraction gold. Do not fake a pass."
            ),
        ),
        GraphEvalGate(
            gate_id="P8-MAP-LANG",
            title="Per-language mapping coverage (en/ar/mixed)",
            status=mapping_status,
            signed_target=(
                f"overall/en ≥ {MAPPING_COVERAGE_OVERALL_MIN:.2f}; "
                f"ar/mixed ≥ {MAPPING_COVERAGE_ARABIC_MIXED_MIN:.2f}"
            ),
            evidence=(
                "evaluate_coverage_gates on unit CoverageSlice fixtures; "
                "mixed-fail-under-English-total is a negative test"
            ),
        ),
        GraphEvalGate(
            gate_id="P8-SUPPORT",
            title="Every returned relation is support-mapped",
            status="pass_fixture",
            signed_target=f"support ≥ {MAPPING_SUPPORT_MIN:.2f}; unmapped not returned",
            evidence="test_unsupported_relation_has_no_statement_id; resolver whole-candidate drop",
        ),
        GraphEvalGate(
            gate_id="P8-SURVIVAL",
            title="Resolver survival fallback",
            status="pass_fixture",
            signed_target=(
                f"fallback < {GRAPH_SURVIVAL_FALLBACK_THRESHOLD:.2f}; "
                f"rolling {GRAPH_SURVIVAL_ROLLING_ALERT_THRESHOLD:.2f}/"
                f"{GRAPH_SURVIVAL_ROLLING_WINDOW}"
            ),
            evidence="test_survival_below_threshold_signal; rolling window recorded not live-alerted",
        ),
        GraphEvalGate(
            gate_id="P8-CALLBACKS",
            title="Hidden keyword/answer and per-statement Hybrid",
            status="pass_fixture",
            signed_target="keyword_extract=0; answer_generate=0; query support_searches=0",
            evidence="contract callback spy plus retrieve_graph fail-closed hidden callback",
        ),
        GraphEvalGate(
            gate_id="P8-ENVELOPE",
            title="Seven-day rebuild envelope",
            status="reduced",
            signed_target=f"{PLAN_GRAPH_DOCUMENTS} docs / {PLAN_GRAPH_CHUNKS} chunks",
            evidence=(
                f"reduced to {supported_documents} labeled graph_mapping "
                "documents; 2k/200k unproven; bulk onboarding blocked"
            ),
        ),
        GraphEvalGate(
            gate_id="P8-RESERVE",
            title="Graph maintenance reserve",
            status="pass_fixture",
            signed_target="max(USD 800, 4 x measured full-rebuild cost)",
            evidence=(
                "measured rebuild cost unavailable so floor USD 800 applies; "
                "unfunded rebuild already quarantines (Packet 7)"
            ),
        ),
        GraphEvalGate(
            gate_id="P8-COMBINED",
            title="Combined relationship/multi-hop +10pp",
            status="deferred_phase_6",
            signed_target="≥10 percentage points over Hybrid (QT-EVAL-009)",
            evidence=COMBINED_QUALITY_NO_CLAIM,
        ),
        GraphEvalGate(
            gate_id="P8-HOLDOUT",
            title="Launch holdout sealed",
            status="pass_fixture",
            signed_target="HoldoutAccess.denied(); no holdout labels",
            evidence="development and qualification loaders only",
        ),
    )


def build_phase5_packet8_report() -> Phase5Packet8Report:
    """Build the Packet 8 freeze and evaluation report.

    Returns:
        Frozen report. Combined quality is an explicit no-claim.

    Raises:
        HoldoutSealedError: If holdout access is enabled in this process.
        FileNotFoundError: If a required freeze artifact is missing.
        RuntimeError: If fixture coverage gates fail or a language is hidden.
    """

    _require_holdout_denied()
    slices = fixture_coverage_slices()
    passed, reason = evaluate_coverage_gates(slices)
    if not passed:
        raise RuntimeError(f"fixture coverage gates failed: {reason}")
    hidden_passed, hidden_reason = evaluate_coverage_gates(
        failing_mixed_hidden_by_english_slices()
    )
    if hidden_passed or hidden_reason != "language_gate":
        raise RuntimeError("mixed language must not be hidden by English totals")
    development = load_development_cases()
    qualification = load_qualification_cases()
    if any(case.split.value == "holdout" for case in (*development, *qualification)):
        raise RuntimeError("holdout leakage into open-split loaders")
    qual_counts = Counter(case.query_class.value for case in qualification)
    graph_mapping_open = sum(
        1
        for case in (*development, *qualification)
        if case.query_class is QueryClass.GRAPH_MAPPING
    )
    policy = default_extraction_policy()
    if policy.extraction_policy_hash != DEFAULT_EXTRACTION_POLICY_HASH:
        raise RuntimeError("extraction policy hash drifted")
    config_generation = mapping_config_generation(
        workspace_key=DEFAULT_GRAPH_WORKSPACE,
        pointer_generation=1,
        chunker_snapshot=graph_chunker_config_snapshot(),
        entity_rules_generation=policy.entity_rules_generation,
        extraction_policy_hash="",
    )
    fingerprint = json.loads(SCHEMA_FINGERPRINT_PATH.read_text(encoding="utf-8"))
    if fingerprint["pin_version"] != LIGHTRAG_PINNED_VERSION:
        raise RuntimeError("schema fingerprint pin drifted")
    holdout_path = PHASE4_FIXTURE_ROOT / "manifests" / "holdout.json"
    development_manifest = PHASE4_FIXTURE_ROOT / "manifests" / "development.json"
    qualification_manifest = PHASE4_FIXTURE_ROOT / "manifests" / "qualification.json"
    envelope = envelope_decision(supported_documents=graph_mapping_open)
    accounting = call_accounting()
    metrics = language_type_metrics()
    if not all(item.passed for item in metrics):
        raise RuntimeError("a language or type fixture missed its own floor")
    hashes = {
        "schema_fingerprint_v1": sha256_file(SCHEMA_FINGERPRINT_PATH),
        "manifest_development": sha256_file(development_manifest),
        "manifest_qualification": sha256_file(qualification_manifest),
        "holdout_manifest_ids_only": sha256_file(holdout_path),
        "extraction_policy": policy.extraction_policy_hash,
        "workspace_config_generation": config_generation,
        "lightrag_wheel": LIGHTRAG_WHEEL_SHA256,
    }
    pins = {
        "lightrag": LIGHTRAG_PINNED_VERSION,
        "lightrag_commit": LIGHTRAG_RELEASE_COMMIT,
        "graph_storage": SELECTED_GRAPH_STORAGE,
        "packet7_pin_commit": PACKET7_PIN_COMMIT,
        "code_revision_git_sha": code_revision_git_sha(),
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dimensions": str(EMBEDDING_DIMENSIONS),
        "chunk_token_size": str(LIGHTRAG_CHUNK_TOKEN_SIZE),
        "chunk_overlap_token_size": str(LIGHTRAG_CHUNK_OVERLAP_TOKEN_SIZE),
        "tiktoken_model": LIGHTRAG_TIKTOKEN_MODEL,
        "graph_pipeline_version": GRAPH_PIPELINE_VERSION,
        "graph_field_sep": GRAPH_FIELD_SEP,
        "source_envelope": GRAPH_SOURCE_ENVELOPE_VERSION,
        "workspace": DEFAULT_GRAPH_WORKSPACE,
        "entity_rules_generation": str(policy.entity_rules_generation),
        "support_min": f"{MAPPING_SUPPORT_MIN:.2f}",
        "coverage_overall_min": f"{MAPPING_COVERAGE_OVERALL_MIN:.2f}",
        "coverage_arabic_mixed_min": f"{MAPPING_COVERAGE_ARABIC_MIXED_MIN:.2f}",
        "max_source_ids_entity": str(DEFAULT_MAX_SOURCE_IDS_PER_ENTITY),
        "max_source_ids_relation": str(DEFAULT_MAX_SOURCE_IDS_PER_RELATION),
        "adapter_candidates": str(ADAPTER_MAX_GRAPH_CANDIDATES),
        "adapter_hops": str(ADAPTER_MAX_HOPS),
        "adapter_paths": str(ADAPTER_MAX_PATHS),
        "inspect_depth": str(INSPECTION_MAX_DEPTH),
        "inspect_rows": str(INSPECTION_MAX_ROWS),
        "inspect_statement_timeout": INSPECTION_STATEMENT_TIMEOUT,
        "inspect_deadline_seconds": str(INSPECTION_DEADLINE_SECONDS),
        "dataset_schema": DATASET_SCHEMA_VERSION,
        "label_revision": LABEL_REVISION,
        "index_estimate_usd": str(DEFAULT_GRAPH_INDEX_ESTIMATE_USD),
        "cleanup_sla_hours": str(GRAPH_TARGET_CLEANUP_SLA_HOURS),
        "rebuild_sla_days": str(GRAPH_CLEAN_REBUILD_SLA_DAYS),
    }
    return Phase5Packet8Report(
        holdout_opened=False,
        combined_quality_claim=COMBINED_QUALITY_NO_CLAIM,
        packet7_pin_commit=PACKET7_PIN_COMMIT,
        pins=pins,
        hashes=hashes,
        workspace_config_generation=config_generation,
        entity_rules_generation=policy.entity_rules_generation,
        extraction_policy_hash=policy.extraction_policy_hash,
        qualification_counts=dict(sorted(qual_counts.items())),
        language_metrics=metrics,
        coverage_gates_passed=True,
        unmapped_returned_relations=0,
        call_accounting=accounting,
        envelope=envelope,
        fixture_sweep=fixture_sweep(),
        gates=_gates(coverage_passed=True, supported_documents=graph_mapping_open),
        client_decision="pending_user_acceptance",
    )


def render_frozen_manifest_markdown(report: Phase5Packet8Report) -> str:
    """Render the committed frozen graph manifest.

    Args:
        report: Packet 8 snapshot.

    Returns:
        Markdown source for ``docs/graph/FROZEN_GRAPH_MANIFEST.md``.
    """

    pin_rows = "\n".join(
        f"| `{key}` | `{value}` |" for key, value in sorted(report.pins.items())
    )
    hash_rows = "\n".join(
        f"| `{key}` | `{value}` |" for key, value in sorted(report.hashes.items())
    )
    return (
        "\n".join(
            [
                "---",
                "title: Frozen graph configuration manifest",
                "owner: engineering-lead",
                "status: draft",
                "last-reviewed: 2026-08-16",
                "audience: engineering, reviewers",
                "phase_packet: Phase 5 Packet 8",
                "---",
                "",
                "# Frozen graph configuration manifest",
                "",
                "Phase 5 Packet 8 freeze of the LightRAG pin, schema fingerprint,",
                "models, chunker, entity-rules generation, mapping/resolver",
                "thresholds, workspace generation, delimiter/limits, and adapter",
                "bounds. Holdout labels were not opened. Combined answer quality",
                "is not claimed.",
                "",
                "Related: [PHASE5_GRAPH_EVAL.md](../evaluation/PHASE5_GRAPH_EVAL.md) ·",
                "[PHASE6_HANDOFF.md](./PHASE6_HANDOFF.md) ·",
                "[SCALING_OPTIONS.md](./SCALING_OPTIONS.md) ·",
                "[LIGHTRAG_CONTRACT.md](./LIGHTRAG_CONTRACT.md) ·",
                "[QUALITY_TARGETS.md](../QUALITY_TARGETS.md) ·",
                "[phase-05 evidence](../development/phase-05-graphrag-evidence.md) ·",
                "[docs index](../README.md)",
                "",
                "## Decision",
                "",
                f"- Holdout opened: `{str(report.holdout_opened).lower()}`",
                f"- Packet 1-7 pin commit: `{report.packet7_pin_commit}`",
                f"- Client decision: `{report.client_decision}`",
                f"- Entity-rules generation: `{report.entity_rules_generation}`",
                f"- Workspace config generation: `{report.workspace_config_generation}`",
                "",
                report.combined_quality_claim,
                "",
                "```mermaid",
                "flowchart TD",
                "  pin[LightRAG156Pin] --> fingerprint[SchemaFingerprint]",
                "  fingerprint --> maps[MappingResolverThresholds]",
                "  maps --> freeze[FrozenManifest]",
                "  freeze --> holdout{HoldoutOpened?}",
                "  holdout -->|no| eval[FixtureAndQualEval]",
                "  eval --> envelope[ReducedEnvelope]",
                "  envelope --> user[UserAcceptanceRequired]",
                "```",
                "",
                "## Pins",
                "",
                "| Pin | Value |",
                "| --- | --- |",
                pin_rows,
                "",
                "## Artifact hashes",
                "",
                "| Artifact | SHA-256 |",
                "| --- | --- |",
                hash_rows,
                "",
                "## Dataset hashes (development and qualification only)",
                "",
                "Holdout `case_ids` are hashed as a sealed id list. Holdout labels",
                "were not materialized. Qualification class counts are recorded in",
                "[PHASE5_GRAPH_EVAL.md](../evaluation/PHASE5_GRAPH_EVAL.md).",
            ]
        )
        + "\n"
    )


def render_graph_eval_markdown(report: Phase5Packet8Report) -> str:
    """Render the committed Packet 8 evaluation report.

    Args:
        report: Packet 8 snapshot.

    Returns:
        Markdown source for ``docs/evaluation/PHASE5_GRAPH_EVAL.md``.
    """

    metric_rows = "\n".join(
        f"| `{item.language}` | `{item.object_type}` | "
        f"{item.numerator}/{item.denominator} | {item.ratio:.2f} | "
        f"{item.gate_floor:.2f} | `{str(item.passed).lower()}` |"
        for item in report.language_metrics
    )
    gate_rows = "\n".join(
        f"| `{gate.gate_id}` | {gate.title} | `{gate.status}` | "
        f"{gate.signed_target} | {gate.evidence} |"
        for gate in report.gates
    )
    sweep_rows = "\n".join(
        f"| `{row.fixture_id}` | {row.packet} | `{row.test_node}` | {row.invariant} |"
        for row in report.fixture_sweep
    )
    qual_rows = "\n".join(
        f"| `{name}` | {count} |"
        for name, count in sorted(report.qualification_counts.items())
    )
    cited = "\n".join(f"- `{item}`" for item in report.call_accounting.cited_tests)
    envelope = report.envelope
    chunks = (
        "unverified"
        if envelope.supported_chunks is None
        else str(envelope.supported_chunks)
    )
    return (
        "\n".join(
            [
                "---",
                "title: Phase 5 Packet 8 graph evaluation",
                "owner: engineering-lead",
                "status: draft",
                "last-reviewed: 2026-08-16",
                "audience: engineering, reviewers, client-approver",
                "phase_packet: Phase 5 Packet 8",
                "---",
                "",
                "# Phase 5 Packet 8 graph evaluation",
                "",
                "Fixture and qualification-label evaluation for GraphRAG",
                "infrastructure. Live LightRAG extraction precision/recall on a",
                "company corpus is **unverified**. Combined answer quality is",
                "**not claimed**. Holdout stays sealed.",
                "",
                "Related: [FROZEN_GRAPH_MANIFEST.md](../graph/FROZEN_GRAPH_MANIFEST.md) ·",
                "[PHASE6_HANDOFF.md](../graph/PHASE6_HANDOFF.md) ·",
                "[SCALING_OPTIONS.md](../graph/SCALING_OPTIONS.md) ·",
                "[DATASET_SPEC.md](./DATASET_SPEC.md) ·",
                "[QUALITY_TARGETS.md](../QUALITY_TARGETS.md) ·",
                "[phase-05 evidence](../development/phase-05-graphrag-evidence.md) ·",
                "[docs index](../README.md)",
                "",
                "## No-claim",
                "",
                report.combined_quality_claim,
                "",
                "```mermaid",
                "flowchart TD",
                "  fixtures[UnitContractFixtures] --> langs[PerLanguageTypeSlices]",
                "  quals[QualificationLabels] --> counts[ClassCountsNoHoldout]",
                "  langs --> gates[CoverageSupportSurvival]",
                "  counts --> gates",
                "  gates --> extract{LiveExtractionPR?}",
                "  extract -->|unavailable| unverified[UnverifiedLiveCorpus]",
                "  unverified --> envelope[ReducedEnvelope]",
                "  envelope --> p6[Phase6HandoffNoCombinedClaim]",
                "```",
                "",
                "## Qualification class counts (holdout sealed)",
                "",
                "| Query class | Count |",
                "| --- | --- |",
                qual_rows,
                "",
                "GRAPH_MAPPING qualification rows are labeled queries, not",
                "extraction gold. ARABIC_MIXED rows are Phase 4 Hybrid labels.",
                "Arabic/mixed mapping floors are proven by CoverageSlice fixtures,",
                "not by live LightRAG output on those queries.",
                "",
                "## Per-language and per-type fixture metrics",
                "",
                "| Language | Type | Accepted/eligible | Ratio | Floor | Passed |",
                "| --- | --- | --- | --- | --- | --- |",
                metric_rows,
                "",
                f"Unmapped returned relations: `{report.unmapped_returned_relations}`.",
                "",
                "## Call accounting",
                "",
                "| Counter | Value |",
                "| --- | --- |",
                f"| query keyword_extract | `{report.call_accounting.query_keyword_extract}` |",
                f"| query answer_generate | `{report.call_accounting.query_answer_generate}` |",
                f"| query support_searches | `{report.call_accounting.query_support_searches}` |",
                f"| mapping Hybrid max per document | `{report.call_accounting.mapping_hybrid_max}` |",
                f"| mapping rerank max per document | `{report.call_accounting.mapping_rerank_max}` |",
                "",
                "Cited tests:",
                "",
                cited,
                "",
                "## Bound benchmarks (not Combined stream p95)",
                "",
                "| Bound | Value | Provenance |",
                "| --- | --- | --- |",
                f"| candidates | {report.pins['adapter_candidates']} | adapter clamp unit test |",
                f"| hops | {report.pins['adapter_hops']} | resolver path expansion |",
                f"| paths | {report.pins['adapter_paths']} | resolver path expansion |",
                f"| inspect depth | {report.pins['inspect_depth']} | inspection RPC/unit |",
                f"| inspect rows | {report.pins['inspect_rows']} | inspection RPC/unit |",
                f"| statement_timeout | {report.pins['inspect_statement_timeout']} | inspection SQL |",
                f"| inspect deadline | {report.pins['inspect_deadline_seconds']}s | inspection_query_bounds |",
                "| Combined stream p95 | not measured | Phase 6 |",
                "",
                "Pytest durations of mapping/resolver/lifecycle suites are lower",
                "bounds for fixture runtime only. They are not production",
                "documents/hour.",
                "",
                "## Envelope and reserve",
                "",
                f"- Plan default: `{envelope.plan_documents}` documents / "
                f"`{envelope.plan_chunks}` source chunks",
                f"- Sequential 7-day deadline cap: `{envelope.deadline_cap_documents}` "
                f"documents at `{report.pins['index_estimate_usd']}` estimate unused",
                f"- Supported advertised documents: `{envelope.supported_documents}`",
                f"- Supported advertised source chunks: `{chunks}`",
                f"- Bulk onboarding blocked: `{str(envelope.bulk_onboarding_blocked).lower()}`",
                f"- Seven-day rebuild of the 2k envelope: "
                f"`{str(envelope.seven_day_rebuild_of_plan_envelope).lower()}`",
                "- Measured full-rebuild cost: `unverified`",
                f"- Maintenance reserve: `USD {envelope.maintenance_reserve_usd:.0f}` "
                "(floor; `4 x measured` unevaluable)",
                f"- Cleanup SLA constants: `{report.pins['cleanup_sla_hours']}` hours "
                f"targeted / `{report.pins['rebuild_sla_days']}` days dirty "
                "consolidation. Live production hardware SLA is unverified.",
                "",
                envelope.uncertainty,
                "",
                "## Fixture sweep (Packets 5-7 reused)",
                "",
                "| Id | Packet | Test | Invariant |",
                "| --- | --- | --- | --- |",
                sweep_rows,
                "",
                "## Gates",
                "",
                "| Id | Title | Status | Target | Evidence |",
                "| --- | --- | --- | --- | --- |",
                gate_rows,
            ]
        )
        + "\n"
    )

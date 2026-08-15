"""Phase 4 Packet 8 freeze: hashes, ablation catalog, and honest launch no-go.

This module never materializes sealed holdout labels. It reads id/hash
manifests and open-split cases only. It refuses to run when holdout access
is enabled so a freeze job cannot coincide with an authorized open.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from smart_rag_core.evaluation.classes import RuntimeOwner
from smart_rag_core.evaluation.holdout import HoldoutAccess, HoldoutSealedError
from smart_rag_core.evaluation.loader import load_open_splits
from smart_rag_core.evaluation.schema import (
    DATASET_SCHEMA_VERSION,
    LABEL_REVISION,
)
from smart_rag_core.query_profile.versions import (
    NORMALIZER_VERSION,
    PROFILE_PROMPT_SHA256,
    PROFILE_PROMPT_VERSION,
)
from smart_rag_core.retrieval.frozen_profile import (
    FROZEN_HYBRID_PROFILE_SHA256,
    FROZEN_PROFILE_PATH,
    load_frozen_profile,
)
from smart_rag_core.retrieval.profiles import (
    BM25_AUTHORIZED_SURVIVOR_CAP,
    CHANNEL_WEIGHT_BM25,
    CHANNEL_WEIGHT_DENSE,
    CHANNEL_WEIGHT_TERM,
    DENSE_CANDIDATE_CAP,
    HYBRID_DEFAULT_PROFILE_ID,
    RRF_K,
    TERM_CANDIDATE_CAP,
)
from smart_rag_core.retrieval.prohibited import (
    ProhibitedMethodError,
    scan_lockfile,
    scan_pyproject_files,
)
from smart_rag_core.retrieval.rerank_versions import (
    RERANK_MODEL_VERSION,
    RERANK_PROMPT_SHA256,
    RERANK_PROMPT_VERSION,
)
from smart_rag_core.tables.limits import DUCKDB_VERSION_PIN, PYARROW_VERSION_PIN

REPO_ROOT = Path(__file__).resolve().parents[5]
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "evaluation" / "phase4"
LOCK_PATH = REPO_ROOT / "uv.lock"
PYPROJECT_CORE = REPO_ROOT / "packages" / "core" / "pyproject.toml"
OPENAI_SDK_PIN = "2.26.0"
LANGSMITH_SDK_PIN = "0.10.18"
EMBEDDING_MODEL_PIN = "text-embedding-3-large"
EMBEDDING_DIMENSIONS_PIN = 1024
LAUNCH_DECISION_NO_GO = "no_go"
INDEPENDENT_SME_STATUS = "independently_sealed"

GateStatus = Literal[
    "pass",
    "pass_open_split",
    "fixture_only",
    "unverified",
    "deferred",
    "blocker",
]
AblationStatus = Literal[
    "fixture_proven",
    "occupancy_proxy",
    "mock_counterfactual",
    "unverified_live",
    "deferred_later_phase",
    "not_selected",
]
REQUIRED_ABLATION_IDS: tuple[str, ...] = (
    "embedding_small_vs_large",
    "structure_aware_vs_fixed_chunks",
    "dense_only",
    "bm25_only",
    "term_only",
    "dense_term_bm25_outage",
    "max_vs_summed_variants",
    "static_vs_query_aware_rrf",
    "metadata_temporal_factors",
    "always_vs_conditional_rerank",
    "mmr_quotas",
    "parents_context",
    "rewrites",
    "arabic_tokenizer_stemmer",
    "selective_ann_exact_oracle",
    "structured_tables",
)


class FreezeGate(BaseModel):
    """One signed quality or latency gate with an honest measurement status.

    Attributes:
        gate_id: Stable ``QUALITY_TARGETS.md`` identifier.
        title: Short human label.
        status: Measurement posture. ``blocker`` prevents a launch claim.
            ``pass_open_split`` is live Packet 9 evidence on unsealed splits
            only; it is not a holdout pass.
        signed_target: Signed numeric or policy target.
        evidence: Where the status was proven or why it is unverified.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    gate_id: str
    title: str
    status: GateStatus
    signed_target: str
    evidence: str


class FreezeAblation(BaseModel):
    """One required simpler-baseline or method ablation.

    Attributes:
        ablation_id: Stable catalog id.
        title: Short human label.
        status: How the ablation was evidenced.
        evidence: Report or fixture pointer.
        live_recall_claimed: Always false until a live ranked-ID run exists.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    ablation_id: str
    title: str
    status: AblationStatus
    evidence: str
    live_recall_claimed: bool = False


class Phase4FreezeReport(BaseModel):
    """Immutable Packet 8 freeze snapshot.

    Attributes:
        launch_decision: ``no_go`` until holdout and live Hybrid gates exist.
        holdout_opened: Always false for this builder.
        holdout_blocked_reason: Why sealed labels were not materialized.
        profile_id: Frozen Hybrid profile id.
        profile_sha256: Canonical JSON digest matching the pin.
        dataset_schema_version: Packet 1 schema id.
        label_revision: Packet 1 label revision.
        open_split_case_count: Development plus qualification count.
        development_case_count: Development n.
        qualification_case_count: Qualification n.
        holdout_manifest_case_count: Sealed id count, not loaded labels.
        deferred_open_split_count: Open-split cases owned by later phases.
        hashes: Artifact and pin digests.
        pins: SDK, model, and channel pins.
        gates: Signed-target statuses.
        ablations: Required ablation catalog.
        sme_approval_status: Packet 1 corpus metadata status.
        client_decision: Continue-versus-pilot remains pending.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    launch_decision: Literal["no_go"]
    holdout_opened: Literal[False]
    holdout_blocked_reason: str
    profile_id: str
    profile_sha256: str
    dataset_schema_version: str
    label_revision: str
    open_split_case_count: int = Field(ge=1)
    development_case_count: int = Field(ge=1)
    qualification_case_count: int = Field(ge=1)
    holdout_manifest_case_count: int = Field(ge=1)
    deferred_open_split_count: int = Field(ge=0)
    hashes: dict[str, str]
    pins: dict[str, str]
    gates: tuple[FreezeGate, ...]
    ablations: tuple[FreezeAblation, ...]
    sme_approval_status: str
    client_decision: Literal["pending_user_acceptance"]


def sha256_file(path: Path) -> str:
    """Return the SHA-256 hex digest of a file's bytes.

    Args:
        path: File to hash.

    Returns:
        Lowercase hex digest.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
    """

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_holdout_denied() -> None:
    """Fail closed when sealed-label access is enabled in this process.

    Raises:
        HoldoutSealedError: If sealed-label access is enabled in settings.
    """

    access = HoldoutAccess.from_settings()
    if access.allowed:
        raise HoldoutSealedError(
            "packet 8 freeze refuses to run while holdout access is enabled"
        )


def _pin_from_pyproject(text: str, name: str) -> str:
    """Extract one ``name==version`` pin from a pyproject dependency list.

    Args:
        text: ``pyproject.toml`` contents.
        name: Distribution name.

    Returns:
        Exact version string.

    Raises:
        ValueError: If the pin is missing.
    """

    needle = f'"{name}=='
    start = text.find(needle)
    if start < 0:
        raise ValueError(f"missing pyproject pin for {name}")
    rest = text[start + len(needle) :]
    end = rest.find('"')
    if end < 0:
        raise ValueError(f"malformed pyproject pin for {name}")
    return rest[:end]


def _ablations() -> tuple[FreezeAblation, ...]:
    """Return the Packet 8 ablation catalog with honest statuses.

    Returns:
        One row per required ablation id. None claims live Recall@K.
    """

    rows = (
        FreezeAblation(
            ablation_id="embedding_small_vs_large",
            title="Embedding small vs large vs reduced-large",
            status="fixture_proven",
            evidence=(
                "ADR-embedding-model-dimension.md; embedding-qual-v1 slice; "
                "text-embedding-3-large @1024"
            ),
        ),
        FreezeAblation(
            ablation_id="structure_aware_vs_fixed_chunks",
            title="Structure-aware versus fixed chunks",
            status="fixture_proven",
            evidence="Phase 3 CHUNKING_CONTRACT.md and chunking unit fixtures",
        ),
        FreezeAblation(
            ablation_id="dense_only",
            title="Dense-only candidates",
            status="fixture_proven",
            evidence="Packet 2 HNSW RPC fixtures; live 405 Recall@10 unverified",
        ),
        FreezeAblation(
            ablation_id="bm25_only",
            title="BM25-only candidates",
            status="fixture_proven",
            evidence="Packet 2 ParadeDB typed query fixtures; live Recall@10 unverified",
        ),
        FreezeAblation(
            ablation_id="term_only",
            title="Populated term-only candidates",
            status="fixture_proven",
            evidence="Packet 2 trigram/exact RPC fixtures; live Recall@10 unverified",
        ),
        FreezeAblation(
            ablation_id="dense_term_bm25_outage",
            title="Dense plus term under BM25 outage",
            status="fixture_proven",
            evidence="Packet 4 BM25_DEGRADED signal; dense+term continue; no uncited snippets",
        ),
        FreezeAblation(
            ablation_id="max_vs_summed_variants",
            title="Max versus summed variant RRF",
            status="fixture_proven",
            evidence="Packet 4 max-across-variant contribution; summed path not selected",
        ),
        FreezeAblation(
            ablation_id="static_vs_query_aware_rrf",
            title="Static versus query-aware RRF weights",
            status="not_selected",
            evidence="Equal 1.0 weights frozen; unequal weights lack ranked-ID evidence",
        ),
        FreezeAblation(
            ablation_id="metadata_temporal_factors",
            title="Metadata and UTC temporal factors",
            status="fixture_proven",
            evidence="Packet 4 clamp [1.0, 1.15], recent=90d UTC; Hijri not authoritative",
        ),
        FreezeAblation(
            ablation_id="always_vs_conditional_rerank",
            title="Always versus conditional rerank",
            status="mock_counterfactual",
            evidence="RERANK_COUNTERFACTUAL.md; mock identity; live OpenAI delta unverified",
        ),
        FreezeAblation(
            ablation_id="mmr_quotas",
            title="MMR and document/section quotas",
            status="fixture_proven",
            evidence="Packet 5 unit fixtures; not retuned on ranked IDs",
        ),
        FreezeAblation(
            ablation_id="parents_context",
            title="Parent expansion and context budget",
            status="fixture_proven",
            evidence="Packet 5 parent fetch without is_search_representative; token cap 3500",
        ),
        FreezeAblation(
            ablation_id="rewrites",
            title="Bounded query rewrites versus HyDE",
            status="not_selected",
            evidence="Packet 4 bounded variants only; HyDE prohibited in v1",
        ),
        FreezeAblation(
            ablation_id="arabic_tokenizer_stemmer",
            title="Arabic tokenizer versus English stemmer",
            status="fixture_proven",
            evidence="arabic_norm_v1 parity; Unicode tokenizer; stemmer not selected",
        ),
        FreezeAblation(
            ablation_id="selective_ann_exact_oracle",
            title="Selective ANN then bounded exact fallback",
            status="fixture_proven",
            evidence="Packet 2/4 HNSW iterative scan plus 10000-row exact cap fixtures",
        ),
        FreezeAblation(
            ablation_id="structured_tables",
            title="Sandboxed DuckDB structured tables",
            status="fixture_proven",
            evidence="Packet 7 unit+contract; p95 table latency unverified",
        ),
    )
    ids = tuple(item.ablation_id for item in rows)
    if ids != REQUIRED_ABLATION_IDS:
        raise RuntimeError("ablation catalog drifted from REQUIRED_ABLATION_IDS")
    if any(item.live_recall_claimed for item in rows):
        raise RuntimeError("freeze catalog must not claim live recall")
    return rows


def _gates() -> tuple[FreezeGate, ...]:
    """Return signed-target statuses, including Packet 9 open-split measurements.

    Returns:
        Gate rows. Blockers force ``no_go``. ``pass_open_split`` is not a
        holdout pass and does not clear launch.
    """

    return (
        FreezeGate(
            gate_id="QT-EVAL-001",
            title="Zero ACL leaks",
            status="pass_open_split",
            signed_target="0 leaks",
            evidence=(
                "Packet 9 live ranked-ID ACL leak count 0 on Phase-4-owned "
                "development/qualification; full 405-case ACL still not a "
                "holdout run"
            ),
        ),
        FreezeGate(
            gate_id="QT-EVAL-002",
            title="Citation correctness",
            status="blocker",
            signed_target=">=98%",
            evidence=(
                "Packet 9 locator correctness **1.00** on returned Hybrid units "
                "(open splits). Answer/citation assembler remains Phase 6"
            ),
        ),
        FreezeGate(
            gate_id="QT-EVAL-003",
            title="Citation completeness",
            status="blocker",
            signed_target=">=90%",
            evidence="No Phase 4 answer/citation assembler run on labeled corpus",
        ),
        FreezeGate(
            gate_id="QT-EVAL-004",
            title="Answer faithfulness",
            status="blocker",
            signed_target=">=90%",
            evidence="No answer/verifier prompts in Phase 4",
        ),
        FreezeGate(
            gate_id="QT-EVAL-006",
            title="Hybrid Recall@10",
            status="pass_open_split",
            signed_target=">=85%",
            evidence=(
                "Packet 9 live ranked-ID development **0.902** / qualification "
                "**0.868** on Phase-4-owned classes; holdout sealed"
            ),
        ),
        FreezeGate(
            gate_id="QT-EVAL-007",
            title="Exact-code Recall@5",
            status="pass_open_split",
            signed_target=">=98%",
            evidence="Packet 9 live **1.00** development and qualification",
        ),
        FreezeGate(
            gate_id="QT-EVAL-008",
            title="Approved-alias Recall@10",
            status="pass_open_split",
            signed_target=">=95%",
            evidence="Packet 9 live **1.00** development and qualification",
        ),
        FreezeGate(
            gate_id="QT-EVAL-009",
            title="Combined vs Hybrid relationship/multi-hop",
            status="deferred",
            signed_target="+10pp without ceiling breach",
            evidence="Phase 5/6; labels must not count as Phase 4 passes",
        ),
        FreezeGate(
            gate_id="QT-QP-001",
            title="Language/configuration accuracy",
            status="pass",
            signed_target=">=95%",
            evidence="scripts/eval_query_profile.py open splits; mock extract",
        ),
        FreezeGate(
            gate_id="QT-QP-002",
            title="Temporal-intent macro-F1",
            status="pass",
            signed_target=">=90%",
            evidence="QUERY_PROFILE_EVAL.md Packet 3 open-split confirm",
        ),
        FreezeGate(
            gate_id="QT-QP-003",
            title="Exact-code/date extraction F1",
            status="pass",
            signed_target=">=98%",
            evidence="QUERY_PROFILE_EVAL.md; codes present in query text",
        ),
        FreezeGate(
            gate_id="QT-QP-004",
            title="Entity/approved-alias macro-F1",
            status="pass",
            signed_target=">=90%",
            evidence="eval_query_profile.py 2026-08-14; development and qualification passed",
        ),
        FreezeGate(
            gate_id="QT-QP-005",
            title="Metadata-filter precision and recall",
            status="pass",
            signed_target=">=95%",
            evidence="eval_query_profile.py 2026-08-14; both splits passed",
        ),
        FreezeGate(
            gate_id="QT-QP-006",
            title="Query-type/relationship/table/decomposition macro-F1",
            status="pass",
            signed_target=">=90%",
            evidence="eval_query_profile.py 2026-08-14; both splits passed",
        ),
        FreezeGate(
            gate_id="QT-LAT-001",
            title="Hybrid first evidence p95",
            status="pass_open_split",
            signed_target="<=2s",
            evidence=(
                "Packet 9 live development **785 ms** / qualification **601 ms** "
                "(retrieve path, not first answer token)"
            ),
        ),
        FreezeGate(
            gate_id="QT-LAT-006",
            title="Structured-table p95",
            status="unverified",
            signed_target="<=5s deterministic",
            evidence="Packet 7 unit deadline 3s; labeled-table p95 not benchmarked",
        ),
        FreezeGate(
            gate_id="QT-HOLD-001",
            title="Immutable holdout run",
            status="blocker",
            signed_target="one sealed end-to-end run",
            evidence="Holdout not independently SME-sealed; access remains denied",
        ),
    )


def build_phase4_freeze_report() -> Phase4FreezeReport:
    """Build the Packet 8 freeze report without opening holdout labels.

    Returns:
        Frozen report with ``launch_decision=no_go``.

    Raises:
        HoldoutSealedError: If holdout access is enabled in this process.
        FrozenProfileMutationError: If the Hybrid profile hash drifted.
        ProhibitedMethodError: If a forbidden retrieval dependency is declared.
        FileNotFoundError: If a required freeze artifact is missing.
        ValueError: If pyproject pins do not match expected SDK versions.
        RuntimeError: If ablation catalog integrity fails.
    """

    _require_holdout_denied()
    profile = load_frozen_profile(HYBRID_DEFAULT_PROFILE_ID)
    pyproject = PYPROJECT_CORE.read_text(encoding="utf-8")
    openai_pin = _pin_from_pyproject(pyproject, "openai")
    langsmith_pin = _pin_from_pyproject(pyproject, "langsmith")
    duckdb_pin = _pin_from_pyproject(pyproject, "duckdb")
    pyarrow_pin = _pin_from_pyproject(pyproject, "pyarrow")
    if openai_pin != OPENAI_SDK_PIN:
        raise ValueError(f"openai pin drifted: {openai_pin}")
    if langsmith_pin != LANGSMITH_SDK_PIN:
        raise ValueError(f"langsmith pin drifted: {langsmith_pin}")
    if duckdb_pin != DUCKDB_VERSION_PIN:
        raise ValueError(f"duckdb pin drifted: {duckdb_pin}")
    if pyarrow_pin != PYARROW_VERSION_PIN:
        raise ValueError(f"pyarrow pin drifted: {pyarrow_pin}")
    lock_hits = scan_lockfile(LOCK_PATH.read_text(encoding="utf-8"))
    pyproject_hits = scan_pyproject_files(REPO_ROOT)
    if lock_hits or pyproject_hits:
        raise ProhibitedMethodError(
            f"prohibited methods present: lock={lock_hits} pyproject={pyproject_hits}"
        )
    meta_path = FIXTURE_ROOT / "corpus_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    typed_meta = cast(dict[str, Any], meta)
    sme = cast(dict[str, Any], typed_meta["sme_approval"])
    sme_status = str(sme["status"])
    holdout_path = FIXTURE_ROOT / "manifests" / "holdout.json"
    holdout_payload = json.loads(holdout_path.read_text(encoding="utf-8"))
    holdout_ids = cast(list[object], holdout_payload["case_ids"])
    open_cases = load_open_splits()
    development_n = sum(1 for case in open_cases if case.split.value == "development")
    qualification_n = sum(
        1 for case in open_cases if case.split.value == "qualification"
    )
    deferred_n = sum(
        1 for case in open_cases if case.runtime_owner is not RuntimeOwner.PHASE_4
    )
    gates = _gates()
    if not any(gate.status == "blocker" for gate in gates):
        raise RuntimeError("freeze must retain launch blockers until holdout exists")
    if sme_status == INDEPENDENT_SME_STATUS:
        raise RuntimeError("synthetic corpus must not claim independent SME seal")
    hashes = {
        "hybrid_default_v1": FROZEN_HYBRID_PROFILE_SHA256,
        "hybrid_default_v1_file": sha256_file(FROZEN_PROFILE_PATH),
        "corpus_meta_file": sha256_file(meta_path),
        "schema": str(typed_meta["schema_hash"]),
        "manifest_development": str(
            cast(dict[str, Any], typed_meta["manifest_hashes"])["manifest_development"]
        ),
        "manifest_qualification": str(
            cast(dict[str, Any], typed_meta["manifest_hashes"])[
                "manifest_qualification"
            ]
        ),
        "manifest_holdout": str(
            cast(dict[str, Any], typed_meta["manifest_hashes"])["manifest_holdout"]
        ),
        "holdout_manifest_file": sha256_file(holdout_path),
        "query_profile_prompt": PROFILE_PROMPT_SHA256,
        "rerank_prompt": RERANK_PROMPT_SHA256,
    }
    pins = {
        "openai": OPENAI_SDK_PIN,
        "langsmith": LANGSMITH_SDK_PIN,
        "duckdb": DUCKDB_VERSION_PIN,
        "pyarrow": PYARROW_VERSION_PIN,
        "embedding_model": EMBEDDING_MODEL_PIN,
        "embedding_dimensions": str(EMBEDDING_DIMENSIONS_PIN),
        "rerank_model": RERANK_MODEL_VERSION,
        "rerank_prompt_version": RERANK_PROMPT_VERSION,
        "query_profile_prompt_version": PROFILE_PROMPT_VERSION,
        "normalizer": NORMALIZER_VERSION,
        "rrf_k": str(RRF_K),
        "channel_weights": (
            f"{CHANNEL_WEIGHT_DENSE}/{CHANNEL_WEIGHT_BM25}/{CHANNEL_WEIGHT_TERM}"
        ),
        "dense_cap": str(DENSE_CANDIDATE_CAP),
        "bm25_survivor_cap": str(BM25_AUTHORIZED_SURVIVOR_CAP),
        "term_cap": str(TERM_CANDIDATE_CAP),
        "coverage_baseline": str(profile.coverage_score_baseline),
        "langsmith_tracing_default": "false",
    }
    reason = (
        "sealed holdout labels were not materialized; corpus SME status is "
        f"{sme_status}, not {INDEPENDENT_SME_STATUS}; Packet 9 measured "
        "Phase-4-owned open-split ranked-ID gates without opening holdout"
    )
    return Phase4FreezeReport(
        launch_decision=LAUNCH_DECISION_NO_GO,
        holdout_opened=False,
        holdout_blocked_reason=reason,
        profile_id=profile.profile_id,
        profile_sha256=FROZEN_HYBRID_PROFILE_SHA256,
        dataset_schema_version=DATASET_SCHEMA_VERSION,
        label_revision=LABEL_REVISION,
        open_split_case_count=len(open_cases),
        development_case_count=development_n,
        qualification_case_count=qualification_n,
        holdout_manifest_case_count=len(holdout_ids),
        deferred_open_split_count=deferred_n,
        hashes=hashes,
        pins=pins,
        gates=gates,
        ablations=_ablations(),
        sme_approval_status=sme_status,
        client_decision="pending_user_acceptance",
    )


def render_freeze_markdown(report: Phase4FreezeReport) -> str:
    """Render the committed Packet 8 freeze document.

    Args:
        report: Freeze snapshot.

    Returns:
        Markdown source for ``docs/evaluation/PHASE4_FREEZE.md``.
    """

    gate_rows = "\n".join(
        f"| `{gate.gate_id}` | {gate.title} | `{gate.status}` | "
        f"{gate.signed_target} | {gate.evidence} |"
        for gate in report.gates
    )
    ablation_rows = "\n".join(
        f"| `{item.ablation_id}` | {item.title} | `{item.status}` | "
        f"{item.evidence} | `{str(item.live_recall_claimed).lower()}` |"
        for item in report.ablations
    )
    hash_rows = "\n".join(
        f"| `{key}` | `{value}` |" for key, value in sorted(report.hashes.items())
    )
    pin_rows = "\n".join(
        f"| `{key}` | `{value}` |" for key, value in sorted(report.pins.items())
    )
    return "\n".join(
        [
            "---",
            "title: Phase 4 Packet 8 freeze",
            "owner: engineering-lead",
            "status: draft",
            "last-reviewed: 2026-08-15",
            "audience: engineering, reviewers, client-approver",
            "---",
            "",
            "# Phase 4 Packet 8 freeze",
            "",
            "Honest freeze of Hybrid code, config, prompts, and dataset manifests.",
            "Launch decision is **no-go**. Sealed holdout labels were not opened.",
            "",
            "Related: [PHASE4_ABLATIONS.md](./PHASE4_ABLATIONS.md) ·",
            "[PHASE4_HOLDOUT.md](./PHASE4_HOLDOUT.md) ·",
            "[QUALITY_TARGETS.md](../QUALITY_TARGETS.md) ·",
            "[HYBRID_RETRIEVAL_CONTRACT.md](../retrieval/HYBRID_RETRIEVAL_CONTRACT.md) ·",
            "[phase-04 evidence](../development/phase-04-hybrid-rag-evidence.md) ·",
            "[docs index](../README.md)",
            "",
            "## Decision",
            "",
            f"- Launch decision: `{report.launch_decision}`",
            f"- Holdout opened: `{str(report.holdout_opened).lower()}`",
            f"- Client continue-versus-pilot: `{report.client_decision}`",
            f"- SME corpus status: `{report.sme_approval_status}`",
            f"- Holdout blocked: {report.holdout_blocked_reason}",
            "",
            "```mermaid",
            "flowchart TD",
            "  packets[Packets1to7] --> freeze[FreezeHashes]",
            "  freeze --> ablations[OpenSplitAblations]",
            "  ablations --> gates[SignedGates]",
            "  gates --> holdout{IndependentlySealedHoldout?}",
            "  holdout -->|no| nogo[NoGoPending]",
            "  nogo --> user[UserAcceptanceRequired]",
            "```",
            "",
            "## Dataset counts",
            "",
            f"- Schema `{report.dataset_schema_version}` revision `{report.label_revision}`",
            f"- Development `{report.development_case_count}`",
            f"- Qualification `{report.qualification_case_count}`",
            f"- Open splits `{report.open_split_case_count}`",
            f"- Holdout ids in sealed manifest `{report.holdout_manifest_case_count}`",
            f"- Deferred later-phase labels on open splits `{report.deferred_open_split_count}`",
            f"- Profile `{report.profile_id}` SHA-256 `{report.profile_sha256}`",
            "",
            "## Artifact hashes",
            "",
            "| Artifact | SHA-256 |",
            "| --- | --- |",
            hash_rows,
            "",
            "## Pins",
            "",
            "| Pin | Value |",
            "| --- | --- |",
            pin_rows,
            "",
            "## Signed gates",
            "",
            "| ID | Title | Status | Target | Evidence |",
            "| --- | --- | --- | --- | --- |",
            gate_rows,
            "",
            "## Ablations",
            "",
            "Full narrative lives in [PHASE4_ABLATIONS.md](./PHASE4_ABLATIONS.md).",
            "Live Recall@K is not claimed.",
            "",
            "| ID | Title | Status | Evidence | Live recall claimed |",
            "| --- | --- | --- | --- | --- |",
            ablation_rows,
            "",
            "## Verification",
            "",
            "```powershell",
            "uv run python scripts/eval_phase4_freeze.py",
            "uv run pytest tests/unit/test_phase4_freeze.py tests/unit/test_langsmith_tracing.py -q",
            "```",
            "",
            "Re-run the freeze script after this packet lands to print the current",
            "git SHA. Do not enable holdout access to force a pass.",
            "",
            "[docs index](../README.md)",
            "",
        ]
    )

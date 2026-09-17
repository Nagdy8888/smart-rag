"""Hybrid retrieval channel bounds, HNSW profiles, RRF, and fallback reasons.

Packet 2 froze channel caps and HNSW. Packet 4 freezes ``rrf_k=60``, equal
channel weights, the 205 pre-fusion union cap, metadata clamp ``[1.0, 1.15]``,
the 90-day ``recent`` window, and the 25-second Hybrid deadline. Packet 5 freezes
the top-20 rerank pool, max five passages per document, MMR lambda 0.7, and
parent/context bounds. Packet 6 freezes per-class ``coverage_score`` thresholds
at ``0.65`` in ``retrieval/frozen/hybrid_default_v1.json``. Packet 9 Wave 1A
freezes ``RETRIEVAL_SLICE_SECONDS`` at the 8s statement-timeout bound and
adds named fallbacks for dense/term/auth/empty retrieve failures.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from smart_rag_core.models.env_pins import ALLOWED_RERANK_MODEL_IDS, RERANK_MODEL_ID

if RERANK_MODEL_ID not in ALLOWED_RERANK_MODEL_IDS:
    raise RuntimeError("pinned rerank model is not allow-listed")

DENSE_CANDIDATE_CAP = 100
DENSE_UNDERFILL_FLOOR = 10
BM25_AUTHORIZED_SURVIVOR_CAP = 75
BM25_SCAN_ID_CAP = 300
TERM_CANDIDATE_CAP = 30
TERM_EXTRA_NEEDLE_CAP = 8
"""Bounded extra exact/acronym/alias needles besides the ranking sentence."""
EXACT_FALLBACK_AUTHORIZED_ROW_CAP = 10_000
RETRIEVAL_STATEMENT_TIMEOUT_MS = 8_000
HNSW_WORK_MEM = "32MB"
HNSW_SCAN_MEM_MULTIPLIER = 2
HNSW_ITERATIVE_SCAN = "strict_order"
TRIGRAM_SIMILARITY_THRESHOLD = 0.3
NORMALIZATION_VERSION = "arabic_norm_v1"
BM25_INDEX_SCHEMA_VERSION = "bm25_v1"
MAX_NORMALIZED_QUERY_CHARS = 512
HYBRID_DEFAULT_PROFILE_ID = "hybrid_default_v1"
ALLOWED_RETRIEVAL_PROFILE_IDS = frozenset({HYBRID_DEFAULT_PROFILE_ID})
RRF_K = 60
PREFUSION_UNION_CAP = 205
METADATA_FACTOR_MIN = 1.0
METADATA_FACTOR_MAX = 1.15
RECENT_WINDOW_DAYS = 90
HYBRID_DEADLINE_SECONDS = 25
RETRIEVAL_SLICE_SECONDS = RETRIEVAL_STATEMENT_TIMEOUT_MS / 1000.0
CHANNEL_WEIGHT_DENSE = 1.0
CHANNEL_WEIGHT_BM25 = 1.0
CHANNEL_WEIGHT_TERM = 1.0
RERANK_POOL_SIZE = 20
RERANK_MAX_PER_DOCUMENT = 5
RERANK_EXCERPT_CHARS = 400
RERANK_PROMPT_VERSION = "rerank_v1"
RERANK_MAX_OUTPUT_TOKENS = 2_048
FINAL_EVIDENCE_MAX = 12
FINAL_TOKEN_BUDGET = 3_500
MMR_LAMBDA = 0.7
MMR_CANDIDATE_DEPTH = 20
DOCUMENT_QUOTA = 2
SECTION_QUOTA = 2


class HnswProfileId(StrEnum):
    """Allow-listed HNSW selectivity profiles."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DenseMode(StrEnum):
    """Dense retrieval execution mode."""

    ANN = "ann"
    EXACT = "exact"
    WEAK_EVIDENCE = "weak_evidence"


class RetrievalFallbackReason(StrEnum):
    """Named Hybrid retrieve fallbacks. Existing Packet 2 values stay stable."""

    NONE = "none"
    BM25_UNAVAILABLE = "bm25_unavailable"
    BM25_VERSION_MISMATCH = "bm25_version_mismatch"
    WEAK_EVIDENCE = "weak_evidence"
    TIMEOUT = "retrieval_timeout"
    DENSE_UNAVAILABLE = "dense_unavailable"
    TERM_UNAVAILABLE = "term_unavailable"
    AUTH_CONTEXT_INVALID = "auth_context_invalid"
    RETRIEVAL_EMPTY = "retrieval_empty"


class Bm25Operator(StrEnum):
    """Allow-listed ParadeDB match operators. Raw ``pdb.parse`` is forbidden."""

    MATCH_DISJUNCTION = "match_disjunction"
    MATCH_CONJUNCTION = "match_conjunction"
    PHRASE = "phrase"


class Bm25Field(StrEnum):
    """Allow-listed BM25 projection fields in title > heading/alias > body order."""

    TITLE = "title_search"
    HEADING = "heading_search"
    ALIAS = "alias_search"
    BODY = "body_search"


@dataclass(frozen=True, slots=True)
class HnswProfileSettings:
    """Transaction-local HNSW settings for one allow-listed profile.

    Attributes:
        profile_id: Allow-listed profile name.
        ef_search: pgvector candidate list size during search.
        max_scan_tuples: Approximate iterative-scan visit bound, not a hard cap.
        scan_mem_multiplier: Multiplier of ``work_mem`` for iterative scans.
        work_mem: Transaction-local work memory.
        statement_timeout_ms: Statement timeout for the retrieval transaction.
        iterative_scan: Must remain ``strict_order``; this does not make HNSW exact.
    """

    profile_id: HnswProfileId
    ef_search: int
    max_scan_tuples: int
    scan_mem_multiplier: int
    work_mem: str
    statement_timeout_ms: int
    iterative_scan: str


HNSW_PROFILES: dict[HnswProfileId, HnswProfileSettings] = {
    HnswProfileId.LOW: HnswProfileSettings(
        profile_id=HnswProfileId.LOW,
        ef_search=40,
        max_scan_tuples=8_000,
        scan_mem_multiplier=HNSW_SCAN_MEM_MULTIPLIER,
        work_mem=HNSW_WORK_MEM,
        statement_timeout_ms=RETRIEVAL_STATEMENT_TIMEOUT_MS,
        iterative_scan=HNSW_ITERATIVE_SCAN,
    ),
    HnswProfileId.MEDIUM: HnswProfileSettings(
        profile_id=HnswProfileId.MEDIUM,
        ef_search=80,
        max_scan_tuples=16_000,
        scan_mem_multiplier=HNSW_SCAN_MEM_MULTIPLIER,
        work_mem=HNSW_WORK_MEM,
        statement_timeout_ms=RETRIEVAL_STATEMENT_TIMEOUT_MS,
        iterative_scan=HNSW_ITERATIVE_SCAN,
    ),
    HnswProfileId.HIGH: HnswProfileSettings(
        profile_id=HnswProfileId.HIGH,
        ef_search=120,
        max_scan_tuples=20_000,
        scan_mem_multiplier=HNSW_SCAN_MEM_MULTIPLIER,
        work_mem=HNSW_WORK_MEM,
        statement_timeout_ms=RETRIEVAL_STATEMENT_TIMEOUT_MS,
        iterative_scan=HNSW_ITERATIVE_SCAN,
    ),
}

BM25_FIELD_PRIORITY: tuple[Bm25Field, ...] = (
    Bm25Field.TITLE,
    Bm25Field.HEADING,
    Bm25Field.ALIAS,
    Bm25Field.BODY,
)

BM25_OPERATOR_SQL: dict[Bm25Operator, str] = {
    Bm25Operator.MATCH_DISJUNCTION: "|||",
    Bm25Operator.MATCH_CONJUNCTION: "&&&",
    Bm25Operator.PHRASE: "###",
}


def admit_exact_fallback(authorized_count: int) -> DenseMode:
    """Admit exact dense scan only at or below the hard authorized-row cap.

    Args:
        authorized_count: ACL-visible retrievable rows for the same filters.

    Returns:
        ``exact`` when the scan is bounded; ``weak_evidence`` otherwise.
        Planner estimates are not consulted.
    """

    if authorized_count > EXACT_FALLBACK_AUTHORIZED_ROW_CAP:
        return DenseMode.WEAK_EVIDENCE
    return DenseMode.EXACT


def resolve_hnsw_profile(profile_id: HnswProfileId | str) -> HnswProfileSettings:
    """Return one allow-listed HNSW profile or fail closed.

    Args:
        profile_id: Profile name from the query path, never a free-form GUC map.

    Returns:
        Frozen profile settings.

    Raises:
        ValueError: If the profile is not allow-listed.
    """

    try:
        resolved = HnswProfileId(profile_id)
    except ValueError as error:
        raise ValueError("unknown_retrieval_profile") from error
    return HNSW_PROFILES[resolved]

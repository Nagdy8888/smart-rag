"""Server-side exam candidate fingerprint. Qualification fails closed if incomplete."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from smart_rag_core.models.env_pins import EMBEDDING_MODEL, RERANK_MODEL_ID
from smart_rag_core.retrieval.frozen_profile import FROZEN_HYBRID_PROFILE_SHA256
from smart_rag_core.retrieval.profiles import (
    BM25_INDEX_SCHEMA_VERSION,
    HYBRID_DEFAULT_PROFILE_ID,
    NORMALIZATION_VERSION,
    RERANK_PROMPT_VERSION,
)

EXAM_METRIC_VERSION = "production_corpus_all_required_gold_at_10_v1"
EXAM_CACHE_MODE = "cold_bypass"


@dataclass(frozen=True, slots=True)
class ExamCandidateFingerprint:
    """Content-free Hybrid identity used as the qualification key.

    Attributes:
        digest: SHA-256 hex of the canonical component map.
        complete: False when any required pin is missing.
        missing: Empty when complete.
    """

    digest: str
    complete: bool
    missing: tuple[str, ...]


def capture_exam_candidate_fingerprint() -> ExamCandidateFingerprint:
    """Capture the production Hybrid identity used by web exams.

    Incomplete fingerprints must not consume qualification. The digest
    never includes questions, answers, gold UUIDs, or DSNs.

    Returns:
        Fingerprint with a 64-character digest when complete.
    """

    components = {
        "metric_version": EXAM_METRIC_VERSION,
        "cache_mode": EXAM_CACHE_MODE,
        "profile_id": HYBRID_DEFAULT_PROFILE_ID,
        "profile_sha256": FROZEN_HYBRID_PROFILE_SHA256,
        "bm25_index_schema_version": BM25_INDEX_SCHEMA_VERSION,
        "normalization_version": NORMALIZATION_VERSION,
        "rerank_prompt_version": RERANK_PROMPT_VERSION,
        "rerank_model_id": RERANK_MODEL_ID,
        "embedding_model": EMBEDDING_MODEL,
    }
    missing = tuple(key for key, value in components.items() if not str(value).strip())
    canonical = json.dumps(components, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return ExamCandidateFingerprint(
        digest=digest,
        complete=not missing,
        missing=missing,
    )

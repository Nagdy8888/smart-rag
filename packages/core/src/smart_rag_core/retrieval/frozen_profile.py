"""Immutable Hybrid retrieval profile load, hash, and unknown-id refusal."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from smart_rag_core.evaluation.classes import QueryClass
from smart_rag_core.retrieval.profiles import HYBRID_DEFAULT_PROFILE_ID

PROFILE_FILENAME = "hybrid_default_v1.json"
PROFILE_DIR = Path(__file__).resolve().parent / "frozen"
FROZEN_PROFILE_PATH = PROFILE_DIR / PROFILE_FILENAME
ROLLBACK_PROFILE_ID = "hybrid_packet5_v1"
LONG_DOCUMENT_PROFILE_ID = "hybrid_long_document_v1"
CANDIDATE_PROFILE_PATH = PROFILE_DIR / f"{LONG_DOCUMENT_PROFILE_ID}.json"
COVERAGE_SCORE_BASELINE = 0.65
FROZEN_HYBRID_PROFILE_SHA256 = (
    "def45b691e64707d07d3c7ea47f45eb1b23b5d2d2546c37a19a514f316c5940c"
)
FROZEN_LONG_DOCUMENT_PROFILE_SHA256 = ""
"""Non-empty after Packet 16 qualification. Empty keeps runtime deny."""


class UnknownRetrievalProfileError(ValueError):
    """Runtime requested a profile id that is not the frozen allow-list."""


class FrozenProfileMutationError(ValueError):
    """On-disk frozen profile bytes no longer match the pinned SHA-256."""


class FrozenHybridProfile(BaseModel):
    """Version-addressed Hybrid tunables selected in Packet 6.

    Attributes:
        profile_id: Runtime allow-listed identifier.
        rollback_profile_id: Packet 5 signal-only rollback identifier.
        schema_version: Frozen artifact schema.
        rrf_k: Reciprocal-rank constant. Not retuned without ranked-ID evidence.
        channel_weights: Equal dense/BM25/term weights.
        unequal_channel_weights_selected: Always false in this freeze.
        coverage_score_baseline: Development baseline ``0.65``.
        false_supported_loss_weight: Loss weight for unsupported answers.
        unnecessary_refusal_loss_weight: Loss weight for extra refusals.
        mmr_lambda: Packet 5 MMR mix.
        document_quota: Packet 5 document quota.
        section_quota: Packet 5 section quota.
        rerank_pool_size: Packet 5 rerank pool.
        final_evidence_max: Packet 5 evidence unit cap.
        final_token_budget: Packet 5 token cap.
        coverage_thresholds: Per-class coverage_score refuse thresholds.
        dense_mode_when_version_scoped: ``exact`` for a resolved version on
            the long-document candidate; default profile stays ``ann``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    profile_id: str
    rollback_profile_id: str
    schema_version: str
    rrf_k: int = Field(ge=1)
    channel_weights: dict[str, float]
    unequal_channel_weights_selected: bool
    coverage_score_baseline: float
    false_supported_loss_weight: float
    unnecessary_refusal_loss_weight: float
    mmr_lambda: float
    document_quota: int
    section_quota: int
    rerank_pool_size: int
    final_evidence_max: int
    final_token_budget: int
    coverage_thresholds: dict[str, float]
    rerank_max_per_document: int = Field(default=5, ge=1)
    excerpt_chars: int = Field(default=400, ge=1)
    mmr_candidate_depth: int = Field(default=20, ge=1)
    excerpt_strategy: Literal["prefix", "query_aware"] = "prefix"
    dense_mode_when_version_scoped: Literal["ann", "exact"] = "ann"


def canonical_profile_digest(payload: dict[str, Any]) -> str:
    """Return SHA-256 of canonical JSON for one profile payload.

    Args:
        payload: Loaded JSON object.

    Returns:
        Hex digest of sorted compact JSON.
    """

    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def long_document_runtime_enabled() -> bool:
    """Return whether the long-document profile is frozen for runtime.

    Returns:
        True when Packet 16 pinned a digest.
    """

    return bool(FROZEN_LONG_DOCUMENT_PROFILE_SHA256)


def load_frozen_profile(profile_id: str) -> FrozenHybridProfile:
    """Load an immutable Hybrid profile or fail closed.

    Args:
        profile_id: Requested runtime profile. ``hybrid_default_v1`` is
            always executable. ``hybrid_long_document_v1`` is executable
            only after Packet 16 pins its digest.
            ``hybrid_packet5_v1`` is documented rollback, not a second
            live default.

    Returns:
        Validated frozen profile.

    Raises:
        UnknownRetrievalProfileError: Unknown or unfrozen id.
        FrozenProfileMutationError: File hash does not match the pin.
        FileNotFoundError: Artifact is missing.
    """

    if profile_id == HYBRID_DEFAULT_PROFILE_ID:
        raw = json.loads(FROZEN_PROFILE_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise FrozenProfileMutationError("frozen profile is not an object")
        payload = cast(dict[str, Any], raw)
        digest = canonical_profile_digest(payload)
        if digest != FROZEN_HYBRID_PROFILE_SHA256:
            raise FrozenProfileMutationError("frozen profile hash mismatch")
        profile = FrozenHybridProfile.model_validate(payload)
        if profile.profile_id != HYBRID_DEFAULT_PROFILE_ID:
            raise FrozenProfileMutationError("profile_id mismatch")
        return profile
    if profile_id == LONG_DOCUMENT_PROFILE_ID:
        pin = FROZEN_LONG_DOCUMENT_PROFILE_SHA256
        if not pin:
            raise UnknownRetrievalProfileError(profile_id)
        raw = json.loads(CANDIDATE_PROFILE_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise FrozenProfileMutationError("frozen profile is not an object")
        payload = cast(dict[str, Any], raw)
        digest = canonical_profile_digest(payload)
        if digest != pin:
            raise FrozenProfileMutationError("frozen profile hash mismatch")
        profile = FrozenHybridProfile.model_validate(payload)
        if profile.profile_id != LONG_DOCUMENT_PROFILE_ID:
            raise FrozenProfileMutationError("profile_id mismatch")
        return profile
    raise UnknownRetrievalProfileError(profile_id)


def load_evaluation_profile(profile_id: str) -> FrozenHybridProfile:
    """Load an evaluation candidate. Runtime retrieve must not call this.

    Args:
        profile_id: ``hybrid_default_v1`` or ``hybrid_long_document_v1``.

    Returns:
        Validated profile. Long-document is not on the runtime allow-list.

    Raises:
        UnknownRetrievalProfileError: Unknown id.
        FrozenProfileMutationError: Default hash mismatch or invalid object.
    """

    if profile_id == HYBRID_DEFAULT_PROFILE_ID:
        return load_frozen_profile(profile_id)
    if profile_id != LONG_DOCUMENT_PROFILE_ID:
        raise UnknownRetrievalProfileError(profile_id)
    raw = json.loads(CANDIDATE_PROFILE_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise FrozenProfileMutationError("candidate profile is not an object")
    payload = cast(dict[str, Any], raw)
    profile = FrozenHybridProfile.model_validate(payload)
    if profile.profile_id != LONG_DOCUMENT_PROFILE_ID:
        raise FrozenProfileMutationError("profile_id mismatch")
    return profile


def coverage_threshold_for(query_class: QueryClass | None) -> float:
    """Return the frozen refuse threshold for one class.

    Args:
        query_class: Evaluation class, or None for the baseline.

    Returns:
        Threshold in ``[0, 1]``. Unknown class uses the baseline.

    Raises:
        FrozenProfileMutationError: If the frozen artifact was mutated.
        UnknownRetrievalProfileError: If the default profile id is invalid.
    """

    profile = load_frozen_profile(HYBRID_DEFAULT_PROFILE_ID)
    if query_class is None:
        return profile.coverage_score_baseline
    return profile.coverage_thresholds.get(
        query_class.value, profile.coverage_score_baseline
    )

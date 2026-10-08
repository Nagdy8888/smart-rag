"""Immutable long-document profile pin and runtime allow-list."""

from __future__ import annotations

import json
from uuid import UUID

import pytest
from smart_rag_core.retrieval.cache_key import hybrid_cache_key
from smart_rag_core.retrieval.frozen_profile import (
    FROZEN_HYBRID_PROFILE_SHA256,
    FROZEN_LONG_DOCUMENT_PROFILE_SHA256,
    FROZEN_PROFILE_PATH,
    LONG_DOCUMENT_PROFILE_ID,
    LONG_DOCUMENT_V4_PROFILE_ID,
    PRIOR_LONG_DOCUMENT_PROFILE_ID,
    PRIOR_LONG_DOCUMENT_PROFILE_PATH,
    UnknownRetrievalProfileError,
    canonical_profile_digest,
    load_frozen_profile,
    runtime_profile_ids,
)
from smart_rag_core.retrieval.profiles import HYBRID_DEFAULT_PROFILE_ID
from smart_rag_core.retrieval.source_scope import (
    SourceResolution,
    select_runtime_profile,
)

_FAILED_V1_DIGEST = "d9e154747a88a94c0c75e87935a1f977e1c1802e2e80f9e12825bd24e1d15d22"
_FORBIDDEN_PROFILE_KEYS = frozenset(
    {"pdf_sha", "question_id", "gold_phrase", "page_number", "isbn"}
)


def test_default_profile_bytes_match_existing_pin() -> None:
    """P06-62 must not rewrite frozen ``hybrid_default_v1``."""

    payload = json.loads(FROZEN_PROFILE_PATH.read_text(encoding="utf-8"))
    assert canonical_profile_digest(payload) == FROZEN_HYBRID_PROFILE_SHA256
    default = load_frozen_profile(HYBRID_DEFAULT_PROFILE_ID)
    assert default.profile_id == HYBRID_DEFAULT_PROFILE_ID
    assert default.document_quota == 2


def test_long_document_v2_pin_is_not_failed_v1() -> None:
    """Runtime pin is a new digest, not the unmeasured v1 file."""

    assert FROZEN_LONG_DOCUMENT_PROFILE_SHA256
    assert FROZEN_LONG_DOCUMENT_PROFILE_SHA256 != _FAILED_V1_DIGEST
    profile = load_frozen_profile(LONG_DOCUMENT_PROFILE_ID)
    assert profile.profile_id == LONG_DOCUMENT_PROFILE_ID
    assert profile.document_quota == 12
    assert profile.excerpt_strategy == "query_aware"
    assert profile.excerpt_chars == 800
    assert profile.rerank_max_per_document == 20
    assert profile.dense_mode_when_version_scoped == "exact"
    payload = json.loads(
        (FROZEN_PROFILE_PATH.parent / f"{LONG_DOCUMENT_PROFILE_ID}.json").read_text(
            encoding="utf-8"
        )
    )
    assert canonical_profile_digest(payload) == FROZEN_LONG_DOCUMENT_PROFILE_SHA256
    assert _FORBIDDEN_PROFILE_KEYS.isdisjoint(payload)


def test_prior_long_document_v1_stays_unfrozen() -> None:
    """Enabling the failed prior file without a pin fails closed."""

    v1 = json.loads(PRIOR_LONG_DOCUMENT_PROFILE_PATH.read_text(encoding="utf-8"))
    assert canonical_profile_digest(v1) == _FAILED_V1_DIGEST
    with pytest.raises(UnknownRetrievalProfileError):
        load_frozen_profile(PRIOR_LONG_DOCUMENT_PROFILE_ID)
    assert PRIOR_LONG_DOCUMENT_PROFILE_ID not in runtime_profile_ids()
    assert LONG_DOCUMENT_PROFILE_ID in runtime_profile_ids()


def test_exact_one_long_document_selects_v3() -> None:
    """Exact-one authorized versions above the passage gate use v3."""

    profile_id, reason = select_runtime_profile(
        resolution=SourceResolution.EXACT_ONE,
        version_id=UUID("00000000-0000-0000-0000-000000000099"),
        representative_count=40,
        query_class="factual_definition",
    )
    assert profile_id == LONG_DOCUMENT_V4_PROFILE_ID
    assert reason == "long_document_eligible"
    key = hybrid_cache_key(
        principal_scope_hash="p",
        query_normalized="q",
        retrieval_profile_id=LONG_DOCUMENT_V4_PROFILE_ID,
        visibility_generation=1,
    )
    assert len(key) == 64


def test_small_corpus_long_document_selects_v3() -> None:
    """Unscoped questions on a small corpus with a long document use v3."""

    profile_id, reason = select_runtime_profile(
        resolution=SourceResolution.UNSCOPED,
        version_id=None,
        representative_count=1015,
        query_class="factual_definition",
        authorized_document_count=4,
    )
    assert profile_id == LONG_DOCUMENT_V4_PROFILE_ID
    assert reason == "small_corpus_long_document"


def test_large_corpus_and_short_documents_stay_default() -> None:
    """Nine documents, or only short documents, keep the default profile."""

    large, large_reason = select_runtime_profile(
        resolution=SourceResolution.UNSCOPED,
        version_id=None,
        representative_count=1015,
        query_class=None,
        authorized_document_count=9,
    )
    short, short_reason = select_runtime_profile(
        resolution=SourceResolution.AMBIGUOUS,
        version_id=None,
        representative_count=5,
        query_class=None,
        authorized_document_count=2,
    )
    unknown, unknown_reason = select_runtime_profile(
        resolution=SourceResolution.UNSCOPED,
        version_id=None,
        representative_count=1015,
        query_class=None,
    )
    assert (large, large_reason) == (
        HYBRID_DEFAULT_PROFILE_ID,
        "default_profile_required",
    )
    assert (short, short_reason) == (
        HYBRID_DEFAULT_PROFILE_ID,
        "default_profile_required",
    )
    assert (unknown, unknown_reason) == (
        HYBRID_DEFAULT_PROFILE_ID,
        "default_profile_required",
    )


def test_small_corpus_trivial_exact_stays_default() -> None:
    """Trivial exact classes stay on the default profile even when eligible."""

    profile_id, reason = select_runtime_profile(
        resolution=SourceResolution.UNSCOPED,
        version_id=None,
        representative_count=1015,
        query_class="exact_code",
        authorized_document_count=4,
    )
    assert profile_id == HYBRID_DEFAULT_PROFILE_ID
    assert reason == "trivial_exact_default_profile"

"""P06-71 deadline admission: exact dense cannot start under a short slice."""

from __future__ import annotations

import json
from uuid import uuid4

from smart_rag_core.retrieval.frozen_profile import (
    FROZEN_HYBRID_PROFILE_SHA256,
    FROZEN_PROFILE_PATH,
    LONG_DOCUMENT_PROFILE_ID,
    canonical_profile_digest,
    load_evaluation_profile,
    load_frozen_profile,
)
from smart_rag_core.retrieval.hybrid_run.channels import (
    collect_dense_lists,
    dense_retrieve_mode,
    exact_dense_admitted,
)
from smart_rag_core.retrieval.profiles import (
    EXACT_START_MIN_SLICE_SECONDS,
    HYBRID_DEADLINE_SECONDS,
    HYBRID_DEFAULT_PROFILE_ID,
    RERANK_RESERVED_SECONDS,
    DenseMode,
)
from smart_rag_core.retrieval.types import DenseRetrievalResult, RetrievalCandidate
from smart_rag_core.security.identity import CallerContext, UserRole
from smart_rag_core.settings.base import SharedSettings


def _caller() -> CallerContext:
    """Build one member caller for dense collect tests.

    Returns:
        Frozen member caller.
    """

    return CallerContext(
        user_id=str(uuid4()),
        role=UserRole.MEMBER,
        authorization_version=1,
    )


def test_exact_dense_admitted_requires_full_hybrid_slice() -> None:
    """Unmeasured and short slices refuse exact; a full envelope admits it."""

    assert EXACT_START_MIN_SLICE_SECONDS == HYBRID_DEADLINE_SECONDS == 25
    assert exact_dense_admitted(None) is False
    assert exact_dense_admitted(8.0) is False
    assert exact_dense_admitted(24.9) is False
    assert exact_dense_admitted(25.0) is True
    assert exact_dense_admitted(30.0) is True


def test_long_document_ask_slice_starts_ann() -> None:
    """Production Ask remaining is below 25s, so version-scoped exact stays off."""

    long_profile = load_evaluation_profile(LONG_DOCUMENT_PROFILE_ID)
    version = uuid4()
    assert (
        dense_retrieve_mode(
            version_id=version,
            profile=long_profile,
            remaining_slice_seconds=8.0,
        )
        is DenseMode.ANN
    )
    assert (
        dense_retrieve_mode(
            version_id=version,
            profile=long_profile,
            remaining_slice_seconds=18.0,
        )
        is DenseMode.ANN
    )
    assert (
        dense_retrieve_mode(
            version_id=version,
            profile=long_profile,
            remaining_slice_seconds=25.0,
        )
        is DenseMode.EXACT
    )


def test_short_slice_skips_exact_underfill_escalate() -> None:
    """A measured short slice does not escalate ANN underfill to exact."""

    modes: list[object] = []
    hit = RetrievalCandidate(
        chunk_id=uuid4(),
        document_id=uuid4(),
        version_id=uuid4(),
        channel_rank=1,
        channel_score=1.0,
    )

    def retrieve(**kwargs: object) -> DenseRetrievalResult:
        """Record mode and return one underfilled ANN list.

        Returns:
            Dense result with a single candidate.
        """

        modes.append(kwargs.get("mode"))
        return DenseRetrievalResult(
            mode=DenseMode.ANN,
            candidates=(hit,),
            authorized_count=20,
        )

    collect_dense_lists(
        retrieve,
        caller=_caller(),
        texts=("policy leave",),
        vectors=((0.1,),),
        version_id=uuid4(),
        dense_mode=DenseMode.ANN,
        remaining_slice_seconds=8.0,
    )
    assert DenseMode.EXACT not in modes


def test_unmeasured_slice_does_not_escalate_exact() -> None:
    """Omitted slice remaining must not start exact by default."""

    modes: list[object] = []
    hit = RetrievalCandidate(
        chunk_id=uuid4(),
        document_id=uuid4(),
        version_id=uuid4(),
        channel_rank=1,
        channel_score=1.0,
    )

    def retrieve(**kwargs: object) -> DenseRetrievalResult:
        """Record mode and return one underfilled ANN list.

        Returns:
            Dense result with a single candidate.
        """

        modes.append(kwargs.get("mode"))
        return DenseRetrievalResult(
            mode=DenseMode.ANN,
            candidates=(hit,),
            authorized_count=20,
        )

    collect_dense_lists(
        retrieve,
        caller=_caller(),
        texts=("policy leave",),
        vectors=((0.1,),),
        version_id=uuid4(),
        dense_mode=DenseMode.ANN,
    )
    assert DenseMode.EXACT not in modes


def test_deadline_repair_does_not_raise_ceilings_or_mutate_default() -> None:
    """ACL-adjacent ceilings and frozen default bytes stay unchanged."""

    settings = SharedSettings()
    assert settings.model_input_max_chars == 16_384
    assert HYBRID_DEADLINE_SECONDS == 25
    assert RERANK_RESERVED_SECONDS == 2.0
    payload = json.loads(FROZEN_PROFILE_PATH.read_text(encoding="utf-8"))
    assert canonical_profile_digest(payload) == FROZEN_HYBRID_PROFILE_SHA256
    default = load_frozen_profile(HYBRID_DEFAULT_PROFILE_ID)
    assert default.dense_mode_when_version_scoped == "ann"

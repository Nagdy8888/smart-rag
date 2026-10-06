"""Query-anchored salvage for autonomy-mode and ADAS confuser answers."""

from __future__ import annotations

from uuid import UUID, uuid4

from smart_rag_core.retrieval.rerank import (
    RerankPassage,
    promote_adas_model_passages,
    promote_expose_mode_passages,
)
from smart_rag_core.retrieval.types import RetrievalCandidate


def _passage(index: int, *, text: str) -> RerankPassage:
    """Build one rerank passage with stable chunk identity.

    Args:
        index: Distinct index for the chunk UUID.
        text: Passage text.

    Returns:
        Rerank passage wrapping a retrieval candidate.
    """

    chunk_id = UUID(f"0000000{index}-0000-4000-8000-000000000000")
    return RerankPassage(
        candidate=RetrievalCandidate(
            chunk_id=chunk_id,
            document_id=uuid4(),
            version_id=uuid4(),
            channel_rank=index,
            channel_score=1.0 / index,
        ),
        raw_text=text,
        excerpt=text,
        token_count=max(1, len(text.split())),
        channels=frozenset({"dense"}),
    )


def test_promote_expose_modes_pins_gold_from_pool() -> None:
    """Expose asks prepend Manual/Assist/Auto prose missing from selection."""

    confuser = _passage(1, text='Figure: "Manual," "Ask," and "Agent."')
    gold = _passage(
        2,
        text='Label these modes such as "Manual," "Assist," and "Auto".',
    )
    promoted = promote_expose_mode_passages(
        (confuser,),
        query="What mode labels should you expose on the autonomy slider?",
        pool=(confuser, gold),
        limit=3,
    )
    assert promoted[0].candidate.chunk_id == gold.candidate.chunk_id


def test_promote_adas_model_pins_dated_defaults() -> None:
    """ADAS asks prepend dated model+temperature prose from the pool."""

    confuser = _passage(1, text='ChatOpenAI(model="gpt-4o", temperature=0.0)')
    gold = _passage(
        2,
        text="model='gpt-4o-2024-05-13', temperature=0.5 for LLMAgentBase",
    )
    promoted = promote_adas_model_passages(
        (confuser,),
        query="What default model and temperature does ADAS LLMAgentBase use?",
        pool=(confuser, gold),
        limit=3,
    )
    assert promoted[0].candidate.chunk_id == gold.candidate.chunk_id

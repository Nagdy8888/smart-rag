"""Shared answer-verifier passages, tables, and prompt digests."""

from __future__ import annotations

import hashlib
from pathlib import Path

from smart_rag_agents.query.state import QueryGraphState
from smart_rag_core.query_fusion import fusion_config_hash
from smart_rag_core.query_fusion.models import (
    FusionAlgorithm,
    FusionResult,
    PassageOrigin,
    ScoredPassage,
)
from smart_rag_core.query_routing.models import (
    TableEvidenceRecord,
)

PROMPTS = (
    Path(__file__).resolve().parents[2]
    / "apps"
    / "agents"
    / "src"
    / "smart_rag_agents"
    / "prompts"
)


def verifier_uid(n: int) -> str:
    """Return a 36-character synthetic UUID.

    Args:
        n: Discriminator.

    Returns:
        Canonical UUID string.
    """

    return f"{n:08x}-0000-4000-8000-000000000000"


def verifier_passage(n: int, *, text: str, rank: int = 1) -> ScoredPassage:
    """Build one canonical scored passage.

    Args:
        n: Chunk discriminator.
        text: Canonical citation text.
        rank: Hybrid rank.

    Returns:
        Scored passage used as answer evidence.
    """

    return ScoredPassage(
        chunk_id=verifier_uid(n),
        document_id=verifier_uid(10_000 + n),
        version_id=verifier_uid(20_000 + n),
        citation_text=text,
        hybrid_rank=rank,
        combined_score=1.0 / (60 + rank),
        origin=PassageOrigin.HYBRID,
        graph_discovered_only=False,
    )


def verifier_fusion(*passages: ScoredPassage) -> FusionResult:
    """Wrap passages in a Hybrid-effective fusion result.

    Args:
        passages: Canonical evidence units.

    Returns:
        Frozen fusion result.
    """

    return FusionResult(
        algorithm=FusionAlgorithm.RESOLVED_PATH_FUSION,
        config_hash=fusion_config_hash(FusionAlgorithm.RESOLVED_PATH_FUSION),
        requested_route="hybrid",
        effective_route="hybrid",
        evidence=passages,
        graph_discovered_only_ratio=0.0,
    )


def verifier_table() -> TableEvidenceRecord:
    """Return one sandbox table snapshot with exact ranges.

    Returns:
        Deterministic table evidence.
    """

    return TableEvidenceRecord(
        table_id=verifier_uid(700),
        version_id=verifier_uid(701),
        document_id=verifier_uid(702),
        source_ranges=("Sheet1!B2:B4", "Sheet1!C2:C4"),
        operation="sum:revenue compare:north-south",
        rows=(
            {"region": "north", "revenue": 10.0},
            {"region": "south", "revenue": 12.0},
        ),
        sheet="Sheet1",
        units="USD",
    )


def verifier_prompt_digest(name: str) -> str:
    """Return the LF-normalized SHA-256 of a prompt file.

    Args:
        name: Prompt filename.

    Returns:
        64-character hex digest.
    """

    payload = (PROMPTS / name).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(payload).hexdigest()


def verified_answer_state() -> QueryGraphState:
    """Build one company answer that passes deterministic citation checks.

    Returns:
        Graph state with fusion and a cited paragraph.
    """

    from smart_rag_agents.query.state import pending_query_state
    from smart_rag_core.query_answer.models import (
        AnswerCitation,
        AnswerParagraph,
        AnswerPayload,
        AtomicLink,
    )

    fusion = verifier_fusion(verifier_passage(1, text="Refund period is 30 days."))
    chunk_id = fusion.evidence[0].chunk_id
    state = pending_query_state(user_query="What is the refund period?")
    state["status"] = "answered"
    state["remaining_model_calls"] = 8
    state["fusion"] = fusion.model_dump(mode="json")
    state["answer"] = AnswerPayload(
        answer_text="Refund period is 30 days.",
        paragraphs=(
            AnswerParagraph(
                paragraph_index=0,
                text="Refund period is 30 days.",
                link_ids=("l1",),
            ),
        ),
        citations=(
            AnswerCitation(
                chunk_id=chunk_id,
                span="Refund period is 30 days.",
                paragraph_index=0,
                atomic_link_id="l1",
            ),
        ),
        atomic_links=(
            AtomicLink(
                link_id="l1",
                claim="Refund period is 30 days.",
                chunk_ids=(chunk_id,),
            ),
        ),
        status="complete",
    ).model_dump(mode="json")
    return state

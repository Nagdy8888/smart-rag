"""Shared answer-verifier passages, tables, and prompt digests."""

from __future__ import annotations

import hashlib
from pathlib import Path

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


def _uid(n: int) -> str:
    """Return a 36-character synthetic UUID.

    Args:
        n: Discriminator.

    Returns:
        Canonical UUID string.
    """

    return f"{n:08x}-0000-4000-8000-000000000000"


def _passage(n: int, *, text: str, rank: int = 1) -> ScoredPassage:
    """Build one canonical scored passage.

    Args:
        n: Chunk discriminator.
        text: Canonical citation text.
        rank: Hybrid rank.

    Returns:
        Scored passage used as answer evidence.
    """

    return ScoredPassage(
        chunk_id=_uid(n),
        document_id=_uid(10_000 + n),
        version_id=_uid(20_000 + n),
        citation_text=text,
        hybrid_rank=rank,
        combined_score=1.0 / (60 + rank),
        origin=PassageOrigin.HYBRID,
        graph_discovered_only=False,
    )


def _fusion(*passages: ScoredPassage) -> FusionResult:
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


def _table() -> TableEvidenceRecord:
    """Return one sandbox table snapshot with exact ranges.

    Returns:
        Deterministic table evidence.
    """

    return TableEvidenceRecord(
        table_id=_uid(700),
        version_id=_uid(701),
        document_id=_uid(702),
        source_ranges=("Sheet1!B2:B4", "Sheet1!C2:C4"),
        operation="sum:revenue compare:north-south",
        rows=(
            {"region": "north", "revenue": 10.0},
            {"region": "south", "revenue": 12.0},
        ),
        sheet="Sheet1",
        units="USD",
    )


def _prompt_digest(name: str) -> str:
    """Return the LF-normalized SHA-256 of a prompt file.

    Args:
        name: Prompt filename.

    Returns:
        64-character hex digest.
    """

    payload = (PROMPTS / name).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(payload).hexdigest()

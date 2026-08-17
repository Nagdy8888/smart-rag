"""Local sizing baseline mapped to the signed envelope without managed claims."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from smart_rag_core.release.constants import (
    REDUCED_GRAPH_VERSION_ENVELOPE,
    SIGNED_CHUNK_ENVELOPE,
    SIGNED_GRAPH_VERSION_ENVELOPE,
    SIGNED_HYBRID_VERSION_ENVELOPE,
    SIZING_SCHEMA_VERSION,
)


class CandidateSizingBaseline(BaseModel):
    """Local hardware and seeded-count mapping. Not managed EC2/Supabase proof.

    Attributes:
        schema_version: Frozen sizing schema.
        docker_ncpu: CPUs reported by ``docker info``.
        docker_mem_bytes: Docker Desktop / engine memory bytes.
        container_limits: Compose service memory limits.
        seeded_document_versions: Local candidate corpus versions.
        seeded_chunks: Local candidate corpus chunks.
        seeded_graph_eligible_versions: Graph-eligible versions in the seed.
        signed_hybrid_version_envelope: QT-CAP-001.
        signed_chunk_envelope: QT-CAP-002.
        signed_graph_version_envelope: QT-CAP-005 aspiration.
        reduced_graph_version_envelope: QT-CAP-005-P8.
        local_candidate_not_full_envelope: Always true for Packet 1.
        managed_claims: Always empty; Phase 10 owns managed proof.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["phase09-candidate-sizing-v1"] = SIZING_SCHEMA_VERSION
    docker_ncpu: int | None = None
    docker_mem_bytes: int | None = None
    container_limits: dict[str, str]
    seeded_document_versions: int = Field(ge=0)
    seeded_chunks: int = Field(ge=0)
    seeded_graph_eligible_versions: int = Field(ge=0)
    signed_hybrid_version_envelope: int = SIGNED_HYBRID_VERSION_ENVELOPE
    signed_chunk_envelope: int = SIGNED_CHUNK_ENVELOPE
    signed_graph_version_envelope: int = SIGNED_GRAPH_VERSION_ENVELOPE
    reduced_graph_version_envelope: int = REDUCED_GRAPH_VERSION_ENVELOPE
    local_candidate_not_full_envelope: Literal[True] = True
    managed_claims: tuple[str, ...] = ()


def default_container_limits() -> dict[str, str]:
    """Return Compose-declared candidate container memory limits.

    Returns:
        Service name to documented ``mem_limit``.
    """

    return {
        "paradedb": "2g",
        "valkey-limits": "128m",
        "valkey-cache": "320m",
        "clamav": "2g",
        "crawl-proxy": "128m",
        "api": "unbounded_in_compose",
        "worker": "unbounded_in_compose",
        "frontend": "unbounded_in_compose",
    }


def build_sizing_baseline(
    *,
    docker_ncpu: int | None,
    docker_mem_bytes: int | None,
    seeded_document_versions: int,
    seeded_chunks: int,
    seeded_graph_eligible_versions: int,
) -> CandidateSizingBaseline:
    """Build the Packet 1 sizing baseline.

    Args:
        docker_ncpu: Engine CPU count when known.
        docker_mem_bytes: Engine memory bytes when known.
        seeded_document_versions: Seeded canonical versions.
        seeded_chunks: Seeded canonical chunks.
        seeded_graph_eligible_versions: Graph-eligible seeded versions.

    Returns:
        Baseline that maps local counts onto the signed envelope.
    """

    return CandidateSizingBaseline(
        docker_ncpu=docker_ncpu,
        docker_mem_bytes=docker_mem_bytes,
        container_limits=default_container_limits(),
        seeded_document_versions=seeded_document_versions,
        seeded_chunks=seeded_chunks,
        seeded_graph_eligible_versions=seeded_graph_eligible_versions,
        managed_claims=(),
    )

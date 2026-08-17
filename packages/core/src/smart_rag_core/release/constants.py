"""Stable identifiers and artifact locations for Phase 9 Packet 1."""

from __future__ import annotations

from smart_rag_core.schema.enums import DocumentStatus

IDENTITY_SCHEMA_VERSION = "phase09-candidate-identity-v1"
IMAGE_MANIFEST_SCHEMA_VERSION = "phase09-candidate-images-v1"
CORPUS_MANIFEST_SCHEMA_VERSION = "phase09-candidate-corpus-v1"
READINESS_SCHEMA_VERSION = "phase09-candidate-readiness-v1"
SIZING_SCHEMA_VERSION = "phase09-candidate-sizing-v1"
SCAN_SCHEMA_VERSION = "phase09-candidate-scan-v1"
HEALTH_SCHEMA_VERSION = "phase09-candidate-health-v1"
MIGRATION_SCHEMA_VERSION = "phase09-candidate-migrations-v1"
PACKET2_MATRIX_SCHEMA_VERSION = "phase09-candidate-packet2-v1"
PACKET3_MATRIX_SCHEMA_VERSION = "phase09-candidate-packet3-v1"
PACKET3_QUALITY_SCHEMA_VERSION = "phase09-candidate-packet3-quality-v1"
PACKET3_LATENCY_SCHEMA_VERSION = "phase09-candidate-packet3-latency-v1"
PACKET3_LEDGER_SCHEMA_VERSION = "phase09-candidate-packet3-ledger-v1"
PACKET3_BM25_SCHEMA_VERSION = "phase09-candidate-packet3-bm25-v1"
PACKET3_GRAPH_SCHEMA_VERSION = "phase09-candidate-packet3-graph-v1"
PACKET4_MATRIX_SCHEMA_VERSION = "phase09-candidate-packet4-v1"
PACKET4_WORKLOAD_SCHEMA_VERSION = "phase09-candidate-packet4-workload-v1"
PACKET4_CONTENTION_SCHEMA_VERSION = "phase09-candidate-packet4-contention-v1"
PACKET4_STREAMS_SCHEMA_VERSION = "phase09-candidate-packet4-streams-v1"
PACKET4_POOLS_SCHEMA_VERSION = "phase09-candidate-packet4-pools-v1"
PACKET4_RESOURCES_SCHEMA_VERSION = "phase09-candidate-packet4-resources-v1"
PACKET4_BM25_SCHEMA_VERSION = "phase09-candidate-packet4-bm25-v1"

ARTIFACT_DIR = "docs/deployment/phase-09"
CANDIDATE_COMPOSE_FILE = "docker-compose.yml"
PACKET8_OVERLAY_FILE = "docker-compose.packet8.yml"
TMP_SCAN_DIR = ".tmp-phase09"

PRIVATE_COMPOSE_SERVICES: tuple[str, ...] = (
    "paradedb",
    "valkey-limits",
    "valkey-cache",
    "crawl-proxy",
)
CANDIDATE_BUILD_SERVICES: tuple[str, ...] = (
    "api",
    "worker",
    "frontend",
    "crawl-proxy",
)
PARSER_SANDBOX_IMAGE = "smart-rag-parser-sandbox:local"
LIGHTRAG_PUBLIC_PORTS: frozenset[int] = frozenset({9621, 9624})
REQUIRED_IMAGE_USER = "10001"

REQUIRED_DOCUMENT_STATES: tuple[str, ...] = (
    DocumentStatus.UPLOADING.value,
    DocumentStatus.UPLOADED.value,
    DocumentStatus.SCANNING.value,
    DocumentStatus.PARSING.value,
    DocumentStatus.HYBRID_READY.value,
    DocumentStatus.GRAPH_PENDING.value,
    DocumentStatus.GRAPH_READY.value,
    DocumentStatus.GRAPH_INELIGIBLE.value,
    DocumentStatus.DELETION_PENDING.value,
    DocumentStatus.FAILED.value,
)

SIGNED_HYBRID_VERSION_ENVELOPE = 10_000
SIGNED_CHUNK_ENVELOPE = 1_000_000
SIGNED_GRAPH_VERSION_ENVELOPE = 2_000
REDUCED_GRAPH_VERSION_ENVELOPE = 15

PROCEED_DECISION = (
    "Phase 8 wrapper remains pending awaiting user acceptance; "
    "the user explicitly ordered Phase 9 implementation on 2026-08-17."
)

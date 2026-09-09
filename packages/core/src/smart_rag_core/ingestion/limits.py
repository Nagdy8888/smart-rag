"""Phase 3 scan, quarantine, promotion, and cleanup operational limits."""

from __future__ import annotations

SCAN_CONFIG_VERSION = "scan_v1"
PROMOTION_CONFIG_VERSION = "promotion_v1"
SIGNATURE_MAX_AGE_HOURS = 24
QUARANTINE_TTL_HOURS_DEFAULT = 24

# ClamAV / scan bounds (see docs/ingestion/INGESTION_LIMITS.md)
SCAN_MAX_BYTES = 104_857_600  # 100 MiB hard max per object stream
SCAN_TIMEOUT_SECONDS = 120
SCAN_MAX_RECURSION = 16
SCAN_MAX_FILES = 10_000
SCAN_MAX_EMBEDDED_PE = 40
SCAN_ARCHIVE_MAX_EXPANSION_RATIO = 250
SCAN_CONCURRENT_STREAMS = 2
SIGNATURE_RELOAD_MEMORY_MB = 512

# Promotion saga
PROMOTION_COPY_TIMEOUT_SECONDS = 300
PROMOTION_VERIFY_TIMEOUT_SECONDS = 120
PROMOTION_CLEANUP_BATCH_LIMIT = 100

# Governance
EXTERNAL_PROCESSING_POLICY_VERSION = "2026-08-13"

# Embedding bounds (Packet 7; see docs/ingestion/INGESTION_LIMITS.md)
DEFAULT_EMBEDDING_BATCH_SIZE = 64
DEFAULT_EMBEDDING_MAX_INPUTS = 2048
DEFAULT_EMBEDDING_REQUEST_TIMEOUT_SECONDS = 120
DEFAULT_EMBEDDING_MAX_RETRIES = 2
DEFAULT_EMBEDDING_CONCURRENCY = 1
# Inline vectors in embedding_operation_ledger.result_ref. Larger batches
# persist vectors only on app.document_chunks (hosted 60s statement_timeout
# cannot store hundreds of 1024-d vectors as one JSONB value).
LEDGER_INLINE_VECTOR_MAX = 64
# Role default app_worker statement_timeout stays 60s. Long-document
# canonical/ledger transactions SET LOCAL these values only.
LONG_DOCUMENT_WRITE_STATEMENT_TIMEOUT = "300s"
LONG_DOCUMENT_IDLE_IN_TXN_TIMEOUT = "180s"

# BM25 projection bounds (Packet 7)
DEFAULT_BM25_UPSERT_BATCH_SIZE = 250
DEFAULT_BM25_VERIFY_SAMPLE_COUNT = 5
DEFAULT_BM25_VERIFY_QUERY_LIMIT = 10
DEFAULT_BM25_REBUILD_BATCH_SIZE = 500

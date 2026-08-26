/**
 * Document, upload, crawl, and ingestion OpenAPI types.
 *
 * Field names match `docs/api/openapi.foundation.json`.
 */

/** `GET /documents` and `GET /documents/{document_id}` item. */
export type DocumentResponse = {
  document_id: string;
  title: string | null;
  visibility: string;
  current_version_id: string | null;
  visibility_generation: number;
  created_at: string | null;
};

/** `POST /documents/uploads/finalize` body. Field names match OpenAPI. */
export type FinalizeUploadHttpRequest = {
  reservation_id: string;
  object_name: string;
  content_hash: string;
  actual_bytes: number;
  media_type?: string | null;
  declared_category: string;
  attestation_policy_version: string;
  idempotency_key: string;
  document_title?: string | null;
};

/** `POST /documents/uploads/finalize` identifiers. */
export type FinalizeUploadHttpResponse = {
  reservation_id: string;
  document_id: string;
  version_id: string;
  job_id: string;
};

/** `POST /ingestion/crawls` body. Defaults match the FastAPI schema. */
export type EnqueueWebsiteCrawlRequest = {
  start_url: string;
  approved_domain: string;
  idempotency_key: string;
  document_title?: string | null;
  max_depth?: number;
  max_pages?: number;
  content_class?: string;
  graph_eligible?: boolean;
  attestation_policy_version?: string | null;
};

/** `POST /ingestion/crawls` identifiers. */
export type EnqueueWebsiteCrawlResponse = {
  document_id: string;
  version_id: string;
  source_id: string;
  approval_id: string;
  job_id: string;
};

/** `POST /ingestion/jobs/{job_id}/retry` body. */
export type RetryIngestionJobResponse = {
  job_id: string;
  status: string;
  detail: string;
};

export type ScanDiagnostics = {
  result: string | null;
  evidence_id: string | null;
  scanned_at: string | null;
  age_seconds: number | null;
  engine_version: string | null;
  signature_version: string | null;
  object_hash: string | null;
};

/** Category attestation and URL-approval diagnostics. */
export type ReviewDiagnostics = {
  declared_category: string | null;
  source_type: string | null;
  approval_status: string | null;
  attestation_policy_version: string | null;
};

/** Page and OCR counts. */
export type OcrDiagnostics = {
  page_count: number;
  ocr_pages: number;
};

/** Safe ingestion job diagnostic row. */
export type IngestionJobSummary = {
  id: string;
  job_kind: string;
  status: string;
  priority: string;
  attempt_count: number;
  max_attempts: number;
  error_category: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
};

/** Public lifecycle statuses from version status. */
export const INGESTION_LIFECYCLE_STATUSES = [
  "uploading",
  "uploaded",
  "scanning",
  "parsing",
  "hybrid_ready",
  "graph_pending",
  "graph_ready",
  "graph_ineligible",
  "deletion_pending",
  "failed",
] as const;

export type IngestionLifecycleStatus =
  (typeof INGESTION_LIFECYCLE_STATUSES)[number];

export type Bm25Diagnostics = {
  active_index_version: number | null;
  index_schema_version: string | null;
  lag_seconds: number | null;
  pending: number;
  processing: number;
  failed: number;
  dead_letter: number;
  retry_attempts: number;
  verified_at: string | null;
};

/** LightRAG handoff counts. Upload never implies graph ready. */
export type GraphHandoffDiagnostics = {
  pending: number;
  processing: number;
  completed: number;
  failed: number;
  dead_letter: number;
};

/** Version lifecycle plus BM25/graph handoff diagnostics. */
export type IngestionStatusVersion = {
  version_id: string;
  document_id: string;
  status: string;
  retrieval_eligible: boolean;
  document_graph_eligible: boolean;
  hybrid_verified_at: string | null;
  bm25_verified_at: string | null;
  graph_handoff_at: string | null;
  retry_allowed: boolean;
  bm25: Bm25Diagnostics;
  graph_handoff: GraphHandoffDiagnostics;
  scan?: ScanDiagnostics;
  review?: ReviewDiagnostics;
  ocr?: OcrDiagnostics;
};

/** Envelope from `GET /ingestion/versions/{id}/status`. */
export type DocumentIngestionStatusResponse = {
  version: IngestionStatusVersion;
  recent_jobs: IngestionJobSummary[];
};

/** `POST /documents/uploads` local reservation. `signed_url` is null until Phase 10. */
export type SignedUploadResponse = {
  reservation_id: string;
  storage_bucket: string;
  storage_path: string;
  expires_at: string;
  signed_url: string | null;
  upload_method: string;
};

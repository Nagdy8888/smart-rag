/**
 * OpenAPI-aligned types for the thin developer UI.
 *
 * Field names match `docs/api/openapi.foundation.json`. This file does not
 * invent endpoints or payload keys.
 */

/** `GET /api/meta` handshake body. */
export type MetaResponse = {
  api_version: string;
  sse_schema_version: string;
  min_client_version: string;
};

/** `POST /invitations/accept` response. Email is not a request field. */
export type AcceptInvitationResponse = {
  invitation_id: string;
};

/** `GET /me` server-derived identity. */
export type CurrentUserResponse = {
  user_id: string;
  role: string;
  authorization_version: number;
  upload_enabled: boolean;
};

/** One named probe from authenticated `GET /ops/ready`. */
export type DependencyStatus = {
  name: string;
  status: string;
};

/** Console readiness: public `/health/ready` plus optional operator probes. */
export type ReadinessResponse = {
  status: string;
  query_ready: boolean;
  detail: string;
  rate_limit_degraded: boolean;
  dependencies: DependencyStatus[];
};

/** `GET|POST /conversations` item. */
export type ConversationResponse = {
  conversation_id: string;
  creator_user_id: string;
  title: string | null;
  created_at: string | null;
};

/** JSON 202 from `POST /conversations/{id}/messages`. */
export type SubmitMessageResponse = {
  run_id: string;
  stream_path: string;
  reconnect: boolean;
  reservation_id: string;
  route_family: string;
  status: string;
};

/** `GET /runs/{run_id}` and `POST /runs/{run_id}/cancel` body. */
export type RunResponse = {
  run_id: string;
  conversation_id: string;
  creator_user_id: string;
  status: string;
  reservation_id: string | null;
  created_at: string | null;
};

/** `POST /runs/{run_id}/feedback` 201 body. */
export type FeedbackResponse = {
  feedback_id: string;
};

/** `GET /runs/{id}/citations` item. */
export type CitationResponse = {
  citation_id: string;
  citation_index: number;
  chunk_id: string | null;
  provenance: Record<string, unknown>;
  source_unavailable: boolean;
};

/** `GET /documents` and `GET /documents/{document_id}` item. */
export type DocumentResponse = {
  document_id: string;
  title: string | null;
  visibility: string;
  current_version_id: string | null;
  visibility_generation: number;
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

/** `GET /graph/entities/search` hit. No vendor prose. */
export type GraphEntityResponse = {
  object_id: string;
  object_type: string;
  chunk_id: string;
  document_id: string;
  version_id: string;
  support: number;
};

/** `POST /graph/inspect` body. Depth is 1–3. */
export type GraphInspectRequest = {
  entity_keys: string[];
  document_id?: string | null;
  depth: number;
};

/** Authorized inspect node. No document title field. */
export type GraphInspectNodeResponse = {
  object_type: string;
  object_id: string;
  chunk_id: string;
  document_id: string;
  version_id: string;
  support: number;
  hop: number;
};

/** Canonical locator coordinates. Never vendor chunk text. */
export type GraphInspectLocator = {
  chunk_id: string;
  document_id: string;
  version_id: string;
  page_number: number | null;
  section_path: string[];
  sheet_name: string | null;
  range_ref: string | null;
  source_url: string | null;
};

/** Typed inspect limitation. ACL blindness must ignore `count`. */
export type GraphInspectLimitation = {
  code: string;
  count: number | null;
};

/** `POST /graph/inspect` payload. At most 200 rows. */
export type GraphInspectResponse = {
  nodes: GraphInspectNodeResponse[];
  locators: GraphInspectLocator[];
  limitations: GraphInspectLimitation[];
  row_count: number;
  depth: number;
};

/** Allow-listed table predicate operators. */
export const TABLE_PREDICATE_OPERATORS = [
  "eq",
  "ne",
  "lt",
  "le",
  "gt",
  "ge",
  "in",
] as const;

export type TablePredicateOperator = (typeof TABLE_PREDICATE_OPERATORS)[number];

/** Allow-listed aggregations. */
export const TABLE_AGGREGATION_OPS = [
  "sum",
  "count",
  "average",
  "min",
  "max",
] as const;

export type TableAggregationOp = (typeof TABLE_AGGREGATION_OPS)[number];

/** Allow-listed sort directions. */
export const TABLE_SORT_DIRECTIONS = ["asc", "desc"] as const;

export type TableSortDirection = (typeof TABLE_SORT_DIRECTIONS)[number];

/** One typed predicate. Extra SQL/path fields are forbidden. */
export type TablePredicate = {
  column: string;
  operator: TablePredicateOperator;
  value: string | number | boolean | null | Array<string | number | boolean | null>;
};

/** One aggregation. COUNT may omit `column`. */
export type TableAggregation = {
  op: TableAggregationOp;
  column?: string | null;
  alias: string;
};

/** One order-by clause. */
export type TableOrder = {
  column: string;
  direction: TableSortDirection;
};

/**
 * Declarative table plan. Matches `TableQueryPlan` extra=forbid.
 * There is no SQL field.
 */
export type TableQueryPlan = {
  table_id: string;
  version_id: string;
  columns?: string[];
  predicates?: TablePredicate[];
  aggregations?: TableAggregation[];
  group_by?: string[];
  order_by?: TableOrder[];
  comparison?: {
    aggregation: TableAggregationOp;
    column: string;
    left: TablePredicate[];
    right: TablePredicate[];
  } | null;
  units?: string | null;
  row_limit?: number;
  output_byte_limit?: number;
};

/** `GET /tables` manifest. No storage paths. */
export type TableManifestResponse = {
  table_id: string;
  document_id: string;
  version_id: string;
  table_name: string;
  sheet_name: string | null;
  row_count: number | null;
  column_count: number | null;
};

/** `POST /tables/analyze` deterministic result. */
export type TableAnalyzeResponse = {
  table_id: string;
  version_id: string;
  document_id: string;
  rows: Array<Record<string, unknown>>;
  source_ranges: string[];
};

/** Nested scan evidence from version status. */
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

/** `GET /usage/me` totals without prompt text. */
export type UsageResponse = {
  scope: string;
  cost_usd: string | number;
  prompt_tokens: number;
  completion_tokens: number;
  usage_rows: number;
};

/** Nested BM25 diagnostics from `GET /ingestion/versions/{id}/status`. */
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

/** Catalog event names from `smart_rag_core.sse.catalog`. */
export const KNOWN_SSE_EVENT_TYPES = [
  "schema",
  "status",
  "heartbeat",
  "route_correction",
  "limitation",
  "deadline",
  "partial",
  "cache",
  "coverage",
  "optional_tool_disclosure",
  "citation_preview",
  "token_delta",
  "usage",
  "completed",
  "cancelled",
  "error",
] as const;

export type KnownSseEventType = (typeof KNOWN_SSE_EVENT_TYPES)[number];

export const TERMINAL_SSE_EVENT_TYPES = [
  "completed",
  "cancelled",
  "error",
  "partial",
] as const;

/** Exact unmerged packet-7 feedback tags. */
export const FEEDBACK_TAGS = [
  "chunk/cleaning loss",
  "profile field wrong",
  "candidate miss",
  "wrong rerank",
  "bad refusal/overconfident answer",
  "missed relationship",
  "wrong route",
  "wrong calculation",
  "bad citation",
  "insufficient graph",
] as const;

export type FeedbackTag = (typeof FEEDBACK_TAGS)[number];

/** Invitation roles from `POST /admin/invitations`. */
export const INVITE_ROLES = ["owner", "admin", "member", "viewer"] as const;

export type InviteRole = (typeof INVITE_ROLES)[number];

/** `POST /admin/invitations` body. Extra fields are forbidden. */
export type CreateInvitationRequest = {
  email: string;
  role: InviteRole;
  upload_enabled: boolean;
};

/** Invitation identifiers. The one-time token is mail-only, not JSON. */
export type CreateInvitationResponse = {
  invitation_id: string;
  email: string;
  role: string;
  upload_enabled: boolean;
  expires_at: string;
};

/** `POST /admin/users/{user_id}/offboard` identifiers. */
export type OffboardResponse = {
  request_id: string;
  subject_user_id: string;
  completed_at: string;
};

/** `GET /tools` card. Unauthorized names are omitted by the server. */
export type ToolCardResponse = {
  tool_key: string;
  version_label: string;
  short_name: string;
  purpose: string;
  required_role: string;
  risk_class: string;
  active: boolean;
};

/** `POST /admin/tools` seed. Extra fields are forbidden. */
export type ToolSeedRequest = {
  tool_key: string;
  display_name: string;
  description?: string;
  active?: boolean;
};

/** Tool permission levels from `set_tool_permission`. */
export const TOOL_PERMISSIONS = ["none", "read", "execute", "admin"] as const;

export type ToolPermission = (typeof TOOL_PERMISSIONS)[number];

/** `POST /admin/tools/{tool_key}/permissions` body. */
export type ToolPermissionRequest = {
  target_role: InviteRole;
  permission: ToolPermission;
};

/** Admin tool/glossary/entity-rule mutation id payload. */
export type ToolMutationResponse = {
  id: string;
};

/** Glossary languages. */
export const GLOSSARY_LANGUAGES = ["en", "ar", "mixed"] as const;

export type GlossaryLanguage = (typeof GLOSSARY_LANGUAGES)[number];

/** Glossary entry types. */
export const GLOSSARY_ENTRY_TYPES = [
  "product_code",
  "project_name",
  "acronym",
  "canonical_term",
  "identifier_rule",
] as const;

export type GlossaryEntryType = (typeof GLOSSARY_ENTRY_TYPES)[number];

/** Glossary scopes. */
export const GLOSSARY_SCOPES = ["company", "synthetic_eval"] as const;

export type GlossaryScope = (typeof GLOSSARY_SCOPES)[number];

/** One alias in a glossary import. */
export type GlossaryAliasRequest = {
  alias: string;
  language: GlossaryLanguage;
};

/** One glossary entry. Extra SQL-like fields are forbidden. */
export type GlossaryEntryRequest = {
  entry_key: string;
  canonical_term: string;
  language: GlossaryLanguage;
  entry_type: GlossaryEntryType;
  effective_scope: GlossaryScope;
  identifier_pattern?: string | null;
  checksum_algorithm?: string | null;
  aliases?: GlossaryAliasRequest[];
};

/** `POST /admin/glossary/imports` body. Extra fields are forbidden. */
export type ImportGlossaryRequest = {
  source_name: string;
  source_version: string;
  idempotency_key: string;
  entries: GlossaryEntryRequest[];
};

/** Glossary import/approve/rollback identifiers. */
export type GlossaryImportResponse = {
  import_id: string;
  status: string;
  entry_count: number;
  alias_count: number;
};

/** Entity-rule lifecycle. */
export const ENTITY_RULE_STATUSES = ["suggested", "approved", "revoked"] as const;

export type EntityRuleStatus = (typeof ENTITY_RULE_STATUSES)[number];

/** Entity-rule provenance. */
export const ENTITY_RULE_SOURCES = ["admin", "feedback", "model"] as const;

export type EntityRuleSource = (typeof ENTITY_RULE_SOURCES)[number];

/** `GET /admin/graph/entity-rules` item. */
export type EntityRuleListItem = {
  id: string;
  entity_type: string;
  canonical_name: string | null;
  display_label: string | null;
  aliases: string[];
  do_not_merge: string[];
  languages: string[];
  alias_scope: string;
  relation_label_policy: string;
  status: EntityRuleStatus;
  active: boolean;
  row_version: number;
  source: EntityRuleSource;
  reason: string;
  confidence: number | null;
  created_at: string | null;
  updated_at: string | null;
};

/** `GET /admin/graph/entity-rules` envelope. */
export type EntityRuleListResponse = {
  rules: EntityRuleListItem[];
};

/** Approve/revoke concurrency body. Extra fields are forbidden. */
export type EntityRuleConcurrencyRequest = {
  row_version: number;
};

/** Entity-rule mutation identifiers. Alias text is omitted. */
export type EntityRuleMutationResponse = {
  rule_id: string;
  status: EntityRuleStatus;
  row_version: number;
  entity_rules_generation: number;
  rebuild_job_id: string | null;
  repair_job_id: string | null;
  invalidated: boolean;
};

/** `POST /admin/graph/entity-rules` upsert. Extra fields are forbidden. */
export type EntityRuleUpsertRequest = {
  entity_type: string;
  canonical_name: string;
  aliases?: string[];
  do_not_merge?: string[];
  display_label?: string | null;
  languages?: string[];
  alias_scope?: "company" | "synthetic_eval";
  relation_label_policy?: "directed" | "symmetric";
  reason?: string;
  source?: EntityRuleSource;
  confidence?: number | null;
  status?: EntityRuleStatus;
  row_version?: number | null;
};

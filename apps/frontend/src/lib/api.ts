/**
 * Authenticated FastAPI client. Authorization is the Bearer JWT; UI role
 * checks are convenience only.
 */

import { CLIENT_VERSION } from "./client-version";
import { apiBaseUrl } from "./env";
import type {
  CitationResponse,
  ConversationResponse,
  CurrentUserResponse,
  AcceptInvitationResponse,
  CreateInvitationRequest,
  CreateInvitationResponse,
  DocumentResponse,
  DocumentIngestionStatusResponse,
  EnqueueWebsiteCrawlRequest,
  EnqueueWebsiteCrawlResponse,
  EntityRuleListItem,
  EntityRuleListResponse,
  EntityRuleMutationResponse,
  EntityRuleSource,
  EntityRuleStatus,
  EntityRuleUpsertRequest,
  FeedbackTag,
  FinalizeUploadHttpRequest,
  FinalizeUploadHttpResponse,
  GlossaryImportResponse,
  GraphEntityResponse,
  GraphInspectRequest,
  GraphInspectResponse,
  ImportGlossaryRequest,
  IngestionJobSummary,
  IngestionStatusVersion,
  MetaResponse,
  OffboardResponse,
  RetryIngestionJobResponse,
  SignedUploadResponse,
  SubmitMessageResponse,
  TableAnalyzeResponse,
  TableManifestResponse,
  TableQueryPlan,
  ToolCardResponse,
  ToolMutationResponse,
  ToolPermissionRequest,
  ToolSeedRequest,
  UsageResponse,
  ReadinessResponse,
} from "./types";
import {
  buildEntityRuleConcurrencyBody,
  buildEntityRuleUpsertBody,
  buildGlossaryImportBody,
  buildInvitationCreateBody,
  buildToolEnableBody,
  buildToolPermissionBody,
  buildToolSeedBody,
} from "./admin-bodies";
import { buildGraphInspectRequest, clampGraphSearchLimit } from "./graph-client";
import { tableAnalyzeBody } from "./table-plan";

/** Headers shared by paid POST bodies. Resume GET omits the version. */
export type ApiAuth = {
  accessToken: string;
};

/**
 * Build JSON headers for a new paid mutation.
 *
 * @param auth - Bearer token.
 * @param idempotencyKey - Optional UUID reused across retry.
 * @returns Header map including `X-Client-Version`.
 */
export function paidMutationHeaders(
  auth: ApiAuth,
  idempotencyKey?: string,
): Record<string, string> {
  const headers: Record<string, string> = {
    Authorization: `Bearer ${auth.accessToken}`,
    "Content-Type": "application/json",
    "X-Client-Version": CLIENT_VERSION,
  };
  if (idempotencyKey) {
    headers["Idempotency-Key"] = idempotencyKey;
  }
  return headers;
}

/**
 * JSON body for `POST /conversations/{id}/messages`. Auto only.
 * There is no client route field (GAP-07-01).
 *
 * @param message - Untrusted user text.
 * @param idempotencyKey - Stable UUID.
 * @returns `{ message, idempotency_key }` only.
 */
export function submitMessageBody(
  message: string,
  idempotencyKey: string,
): { message: string; idempotency_key: string } {
  return { message, idempotency_key: idempotencyKey };
}

/**
 * Build headers for resume/cancel/read paths. No version handshake.
 *
 * @param auth - Bearer token.
 * @param lastEventId - Optional Last-Event-ID for SSE resume.
 * @returns Header map.
 */
export function resumeHeaders(
  auth: ApiAuth,
  lastEventId?: string,
): Record<string, string> {
  const headers: Record<string, string> = {
    Authorization: `Bearer ${auth.accessToken}`,
  };
  if (lastEventId) {
    headers["Last-Event-ID"] = lastEventId;
  }
  return headers;
}

/**
 * Join API origin and a path that may already be absolute-path.
 *
 * @param path - `/conversations` or a `stream_path`.
 * @returns Absolute URL.
 */
export function apiUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  const prefix = path.startsWith("/") ? path : `/${path}`;
  return `${apiBaseUrl()}${prefix}`;
}

export type HandshakeFailure = {
  kind: "upgrade";
  minClientVersion: string;
  sseSchemaVersion: string;
};

export type AuthFailure = {
  kind: "auth";
  status: number;
  detail: string;
};

export type MfaFailure = {
  kind: "mfa";
  detail: string;
};

export type FailClosedFailure = {
  kind: "fail_closed";
  status: number;
  detail: string;
};

export type BudgetFailure = {
  kind: "budget";
  detail: string;
};

export type RateFailure = {
  kind: "rate";
  detail: string;
  retryAfter: string | null;
};

export type DeletedFailure = {
  kind: "deleted";
};

export type ApiFailure =
  | HandshakeFailure
  | AuthFailure
  | MfaFailure
  | FailClosedFailure
  | BudgetFailure
  | RateFailure
  | DeletedFailure;

/**
 * Read a sanitized `detail` string from a FastAPI JSON body.
 *
 * @param body - Parsed object.
 * @param fallback - Used when `detail` is missing or not a string.
 * @returns Code-like detail. Never exception text from unknown shapes.
 */
export function sanitizedDetail(
  body: Record<string, unknown>,
  fallback: string,
): string {
  return typeof body.detail === "string" ? body.detail : fallback;
}

/**
 * Read `Retry-After` from a Fetch Headers map or a plain record.
 *
 * @param headers - Optional response headers.
 * @returns Header value, or null.
 */
export function retryAfterHeader(
  headers?: Headers | Record<string, string>,
): string | null {
  if (headers === undefined) {
    return null;
  }
  if (headers instanceof Headers) {
    return headers.get("Retry-After");
  }
  return headers["Retry-After"] ?? headers["retry-after"] ?? null;
}

/**
 * Parse a FastAPI error body into a typed UI failure.
 *
 * @param status - HTTP status.
 * @param body - JSON-ish object.
 * @param headers - Optional headers for `Retry-After` on 429.
 * @returns Typed failure when the status is an expected gate.
 */
export function classifyApiError(
  status: number,
  body: Record<string, unknown>,
  headers?: Headers | Record<string, string>,
): ApiFailure | null {
  if (status === 426) {
    const min =
      typeof body.min_client_version === "string"
        ? body.min_client_version
        : "0.1.0";
    const schema =
      typeof body.sse_schema_version === "string" ? body.sse_schema_version : "1";
    return {
      kind: "upgrade",
      minClientVersion: min,
      sseSchemaVersion: schema,
    };
  }
  if (status === 403 && body.detail === "MFA required") {
    return { kind: "mfa", detail: "MFA required" };
  }
  if (status === 401 || status === 403) {
    return {
      kind: "auth",
      status,
      detail: sanitizedDetail(body, "unauthorized"),
    };
  }
  if (status === 402) {
    return {
      kind: "budget",
      detail: sanitizedDetail(body, "budget_exhausted"),
    };
  }
  if (status === 429) {
    return {
      kind: "rate",
      detail: sanitizedDetail(body, "rate_limited"),
      retryAfter: retryAfterHeader(headers),
    };
  }
  if (status === 503) {
    return {
      kind: "fail_closed",
      status,
      detail: sanitizedDetail(body, "limiter_unavailable"),
    };
  }
  if (status === 404) {
    return { kind: "deleted" };
  }
  return null;
}

/**
 * JSON headers for AUTH_ADJACENT administration POSTs.
 *
 * Handshake `X-Client-Version` is reserved for paid chat/upload. These
 * mutations send Bearer only. Production never sends `X-Test-*`.
 *
 * @param auth - Access token.
 * @returns Header map.
 */
export function adminMutationHeaders(auth: ApiAuth): Record<string, string> {
  return {
    ...resumeHeaders(auth),
    "Content-Type": "application/json",
  };
}

/**
 * Map a non-OK administration response to a thrown Error code.
 *
 * 404 is not treated as conversation deletion. 403 MFA required stays
 * distinct from forbidden.
 *
 * @param status - HTTP status.
 * @param body - JSON-ish object.
 * @param headers - Optional headers for 429 Retry-After classification.
 * @throws Error with `mfa_required`, `forbidden`, `budget_exhausted`,
 *   `rate_limited`, `stale_row_version`, or a sanitized detail.
 */
export function throwClassifiedAdminError(
  status: number,
  body: Record<string, unknown>,
  headers?: Headers | Record<string, string>,
): never {
  const classified = classifyApiError(status, body, headers);
  if (classified?.kind === "mfa") {
    throw new Error("mfa_required");
  }
  if (classified?.kind === "budget") {
    throw new Error("budget_exhausted");
  }
  if (classified?.kind === "rate") {
    throw new Error("rate_limited");
  }
  if (classified?.kind === "auth") {
    const detail = classified.detail;
    if (detail === "forbidden" || detail === "authorization_rejected") {
      throw new Error("forbidden");
    }
    throw new Error(detail);
  }
  if (status === 409) {
    throw new Error(sanitizedDetail(body, "stale_row_version"));
  }
  throw new Error(sanitizedDetail(body, "request_rejected"));
}

async function readJsonObject(response: Response): Promise<Record<string, unknown>> {
  try {
    const parsed: unknown = await response.json();
    if (parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
  } catch {
    return {};
  }
  return {};
}

/**
 * GET `/health/ready` without authentication.
 *
 * @param fetchImpl - Injected fetch.
 * @returns Readiness payload, or null when the API is unreachable.
 */
export async function fetchReady(
  fetchImpl: typeof fetch = fetch,
): Promise<ReadinessResponse | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 3000);
  try {
    const response = await fetchImpl(apiUrl("/health/ready"), {
      signal: controller.signal,
    });
    const body = await readJsonObject(response);
    if (!response.ok) {
      return null;
    }
    const rawDeps = body.dependencies;
    const dependencies = Array.isArray(rawDeps)
      ? rawDeps
          .filter(
            (item): item is Record<string, unknown> =>
              item !== null && typeof item === "object" && !Array.isArray(item),
          )
          .map((item) => ({
            name: String(item.name ?? ""),
            status: String(item.status ?? ""),
          }))
      : [];
    return {
      status: String(body.status ?? ""),
      query_ready: Boolean(body.query_ready),
      detail: String(body.detail ?? ""),
      rate_limit_degraded: Boolean(body.rate_limit_degraded),
      dependencies,
    };
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * GET `/api/meta` without authentication.
 *
 * @param fetchImpl - Injected fetch.
 * @returns Handshake fields.
 */
export async function fetchMeta(
  fetchImpl: typeof fetch = fetch,
): Promise<MetaResponse> {
  const response = await fetchImpl(apiUrl("/api/meta"));
  const body = await readJsonObject(response);
  if (!response.ok) {
    throw new Error("meta_unreachable");
  }
  const minClientVersion = String(body.min_client_version ?? "");
  if (minClientVersion.trim() === "") {
    throw new Error("meta_unreachable");
  }
  return {
    api_version: String(body.api_version ?? ""),
    sse_schema_version: String(body.sse_schema_version ?? ""),
    min_client_version: minClientVersion,
  };
}

/**
 * GET `/me` with a Bearer token.
 *
 * @param auth - Access token.
 * @param fetchImpl - Injected fetch.
 * @returns Server-derived caller snapshot.
 */
export async function fetchMe(
  auth: ApiAuth,
  fetchImpl: typeof fetch = fetch,
): Promise<CurrentUserResponse> {
  const response = await fetchImpl(apiUrl("/me"), {
    headers: resumeHeaders(auth),
  });
  const body = await readJsonObject(response);
  if (!response.ok) {
    const classified = classifyApiError(response.status, body);
    if (classified?.kind === "mfa") {
      throw new Error("mfa_required");
    }
    if (classified?.kind === "auth" && classified.detail === "session_revoked") {
      throw new Error("session_revoked");
    }
    throw new Error("me_failed");
  }
  return {
    user_id: String(body.user_id ?? ""),
    role: String(body.role ?? ""),
    authorization_version: Number(body.authorization_version ?? 0),
    upload_enabled: Boolean(body.upload_enabled),
    mfa_enrolled: Boolean(body.mfa_enrolled),
  };
}

/**
 * List conversations the caller may read.
 *
 * @param auth - Access token.
 * @param fetchImpl - Injected fetch.
 * @returns Conversation rows.
 */
export async function listConversations(
  auth: ApiAuth,
  fetchImpl: typeof fetch = fetch,
): Promise<ConversationResponse[]> {
  const response = await fetchImpl(apiUrl("/conversations"), {
    headers: resumeHeaders(auth),
  });
  const parsed: unknown = await response.json();
  if (!Array.isArray(parsed)) {
    return [];
  }
  return parsed as ConversationResponse[];
}

/**
 * Create a conversation.
 *
 * @param auth - Access token.
 * @param title - Optional title.
 * @param fetchImpl - Injected fetch.
 * @returns Created conversation.
 */
export async function createConversation(
  auth: ApiAuth,
  title: string | null,
  fetchImpl: typeof fetch = fetch,
): Promise<ConversationResponse> {
  const response = await fetchImpl(apiUrl("/conversations"), {
    method: "POST",
    headers: paidMutationHeaders(auth),
    body: JSON.stringify(title ? { title } : {}),
  });
  return (await response.json()) as ConversationResponse;
}

/**
 * Tombstone and purge one conversation.
 *
 * @param auth - Access token.
 * @param conversationId - Conversation UUID.
 * @param fetchImpl - Injected fetch.
 * @returns True on 204.
 */
export async function deleteConversation(
  auth: ApiAuth,
  conversationId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<boolean> {
  const response = await fetchImpl(apiUrl(`/conversations/${conversationId}`), {
    method: "DELETE",
    headers: resumeHeaders(auth),
  });
  return response.status === 204;
}

/**
 * List visible documents.
 *
 * @param auth - Access token.
 * @param fetchImpl - Injected fetch.
 * @returns Document summaries.
 */
export async function listDocuments(
  auth: ApiAuth,
  fetchImpl: typeof fetch = fetch,
): Promise<DocumentResponse[]> {
  const response = await fetchImpl(apiUrl("/documents"), {
    headers: resumeHeaders(auth),
  });
  const parsed: unknown = await response.json();
  if (!Array.isArray(parsed)) {
    return [];
  }
  return parsed as DocumentResponse[];
}

/**
 * Reserve quarantine upload quota. Local ``signed_url`` is always null.
 *
 * @param auth - Access token.
 * @param declaredBytes - Declared object size.
 * @param idempotencyKey - Upload reservation key.
 * @param fetchImpl - Injected fetch.
 * @returns Reservation payload.
 */
export async function reserveUpload(
  auth: ApiAuth,
  declaredBytes: number,
  idempotencyKey: string,
  fetchImpl: typeof fetch = fetch,
): Promise<SignedUploadResponse> {
  const response = await fetchImpl(apiUrl("/documents/uploads"), {
    method: "POST",
    headers: paidMutationHeaders(auth, idempotencyKey),
    body: JSON.stringify({
      declared_bytes: declaredBytes,
      idempotency_key: idempotencyKey,
    }),
  });
  if (!response.ok) {
    const body = await readJsonObject(response);
    const classified = classifyApiError(response.status, body);
    if (classified?.kind === "mfa") {
      throw new Error("mfa_required");
    }
    throw new Error("upload_reserve_failed");
  }
  return (await response.json()) as SignedUploadResponse;
}

/**
 * Fetch Hybrid/BM25/graph-handoff diagnostics for one version.
 *
 * Graph ready is never inferred from upload alone.
 *
 * @param auth - Access token.
 * @param versionId - Document version UUID.
 * @param fetchImpl - Injected fetch.
 * @returns Envelope, or null on 404. 404 bodies are not parsed for titles.
 */
export async function fetchVersionStatus(
  auth: ApiAuth,
  versionId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<DocumentIngestionStatusResponse | null> {
  const response = await fetchImpl(
    apiUrl(`/ingestion/versions/${versionId}/status`),
    { headers: resumeHeaders(auth) },
  );
  if (response.status === 404) {
    return null;
  }
  const body = (await response.json()) as {
    version?: IngestionStatusVersion;
    recent_jobs?: IngestionJobSummary[];
  };
  const version = body.version;
  if (version === undefined) {
    return null;
  }
  if (version.bm25 === undefined) {
    version.bm25 = {
      active_index_version: null,
      index_schema_version: null,
      lag_seconds: null,
      pending: 0,
      processing: 0,
      failed: 0,
      dead_letter: 0,
      retry_attempts: 0,
      verified_at: null,
    };
  }
  if (version.graph_handoff === undefined) {
    version.graph_handoff = {
      pending: 0,
      processing: 0,
      completed: 0,
      failed: 0,
      dead_letter: 0,
    };
  }
  return {
    version,
    recent_jobs: Array.isArray(body.recent_jobs) ? body.recent_jobs : [],
  };
}

export type DocumentFetchResult =
  | { ok: true; document: DocumentResponse }
  | { ok: false; notFound: true };

/**
 * GET `/documents/{document_id}`. 404 must not leak a title.
 *
 * @param auth - Access token.
 * @param documentId - Document UUID.
 * @param fetchImpl - Injected fetch.
 * @returns Document or `{ notFound: true }` without parsing error titles.
 */
export async function fetchDocument(
  auth: ApiAuth,
  documentId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<DocumentFetchResult> {
  const response = await fetchImpl(apiUrl(`/documents/${documentId}`), {
    headers: resumeHeaders(auth),
  });
  if (response.status === 404) {
    await response.arrayBuffer().catch(() => undefined);
    return { ok: false, notFound: true };
  }
  if (!response.ok) {
    await response.arrayBuffer().catch(() => undefined);
    return { ok: false, notFound: true };
  }
  const body = await readJsonObject(response);
  return {
    ok: true,
    document: {
      document_id: String(body.document_id ?? ""),
      title: typeof body.title === "string" ? body.title : null,
      visibility: String(body.visibility ?? ""),
      current_version_id:
        typeof body.current_version_id === "string"
          ? body.current_version_id
          : null,
      visibility_generation: Number(body.visibility_generation ?? 0),
    },
  };
}

/**
 * Finalize a reserved quarantine upload after Storage write + SHA-256.
 *
 * @param auth - Access token.
 * @param body - Required finalize fields.
 * @param fetchImpl - Injected fetch.
 * @returns Identifiers, or a classified failure.
 */
export async function finalizeUpload(
  auth: ApiAuth,
  body: FinalizeUploadHttpRequest,
  fetchImpl: typeof fetch = fetch,
): Promise<FinalizeUploadHttpResponse> {
  const payload: FinalizeUploadHttpRequest = {
    reservation_id: body.reservation_id,
    object_name: body.object_name,
    content_hash: body.content_hash,
    actual_bytes: body.actual_bytes,
    declared_category: body.declared_category,
    attestation_policy_version: body.attestation_policy_version,
    idempotency_key: body.idempotency_key,
  };
  if (body.media_type) {
    payload.media_type = body.media_type;
  }
  if (body.document_title) {
    payload.document_title = body.document_title;
  }
  const response = await fetchImpl(apiUrl("/documents/uploads/finalize"), {
    method: "POST",
    headers: paidMutationHeaders(auth, body.idempotency_key),
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const errorBody = await readJsonObject(response);
    const classified = classifyApiError(response.status, errorBody);
    if (classified?.kind === "mfa") {
      throw new Error("mfa_required");
    }
    throw new Error(sanitizedDetail(errorBody, "upload_finalize_rejected"));
  }
  const parsed = await readJsonObject(response);
  return {
    reservation_id: String(parsed.reservation_id ?? ""),
    document_id: String(parsed.document_id ?? ""),
    version_id: String(parsed.version_id ?? ""),
    job_id: String(parsed.job_id ?? ""),
  };
}

/**
 * Enqueue an approved website crawl. Owner/admin on the server; members 403.
 *
 * @param auth - Access token.
 * @param body - Crawl request.
 * @param fetchImpl - Injected fetch.
 * @returns Created ids.
 */
export async function enqueueWebsiteCrawl(
  auth: ApiAuth,
  body: EnqueueWebsiteCrawlRequest,
  fetchImpl: typeof fetch = fetch,
): Promise<EnqueueWebsiteCrawlResponse> {
  const payload: EnqueueWebsiteCrawlRequest = {
    start_url: body.start_url,
    approved_domain: body.approved_domain,
    idempotency_key: body.idempotency_key,
    max_depth: body.max_depth ?? 2,
    max_pages: body.max_pages ?? 50,
    content_class: body.content_class ?? "synthetic",
    graph_eligible: body.graph_eligible ?? false,
  };
  if (body.document_title) {
    payload.document_title = body.document_title;
  }
  if (body.attestation_policy_version) {
    payload.attestation_policy_version = body.attestation_policy_version;
  }
  const response = await fetchImpl(apiUrl("/ingestion/crawls"), {
    method: "POST",
    headers: paidMutationHeaders(auth, body.idempotency_key),
    body: JSON.stringify(payload),
  });
  const parsed = await readJsonObject(response);
  if (!response.ok) {
    const classified = classifyApiError(response.status, parsed);
    if (classified?.kind === "auth") {
      throw new Error("forbidden");
    }
    throw new Error(sanitizedDetail(parsed, "crawl_enqueue_rejected"));
  }
  return {
    document_id: String(parsed.document_id ?? ""),
    version_id: String(parsed.version_id ?? ""),
    source_id: String(parsed.source_id ?? ""),
    approval_id: String(parsed.approval_id ?? ""),
    job_id: String(parsed.job_id ?? ""),
  };
}

/**
 * Retry a failed ingestion job. Owner/admin when `retry_allowed`.
 *
 * @param auth - Access token.
 * @param jobId - Job UUID.
 * @param fetchImpl - Injected fetch.
 * @returns Retry result.
 */
export async function retryIngestionJob(
  auth: ApiAuth,
  jobId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<RetryIngestionJobResponse> {
  const response = await fetchImpl(apiUrl(`/ingestion/jobs/${jobId}/retry`), {
    method: "POST",
    headers: paidMutationHeaders(auth),
  });
  const parsed = await readJsonObject(response);
  if (!response.ok) {
    throw new Error(sanitizedDetail(parsed, "retry_not_allowed"));
  }
  return {
    job_id: String(parsed.job_id ?? ""),
    status: String(parsed.status ?? ""),
    detail: String(parsed.detail ?? ""),
  };
}

/**
 * Search authorized graph entities. Limit is clamped to 25.
 *
 * @param auth - Access token.
 * @param query - Bounded search string.
 * @param limit - Requested limit.
 * @param fetchImpl - Injected fetch.
 * @returns Hits without vendor prose.
 */
export async function searchGraphEntities(
  auth: ApiAuth,
  query: string,
  limit: number = 25,
  fetchImpl: typeof fetch = fetch,
): Promise<GraphEntityResponse[]> {
  const capped = clampGraphSearchLimit(limit);
  const url = apiUrl(
    `/graph/entities/search?q=${encodeURIComponent(query)}&limit=${String(capped)}`,
  );
  const response = await fetchImpl(url, { headers: resumeHeaders(auth) });
  const parsed: unknown = await response.json();
  if (!Array.isArray(parsed)) {
    return [];
  }
  return parsed.map((item) => {
    const row = item as Record<string, unknown>;
    return {
      object_id: String(row.object_id ?? ""),
      object_type: String(row.object_type ?? ""),
      chunk_id: String(row.chunk_id ?? ""),
      document_id: String(row.document_id ?? ""),
      version_id: String(row.version_id ?? ""),
      support: Number(row.support ?? 0),
    };
  });
}

/**
 * Inspect authorized graph objects. Depth is clamped to 1–3 on this client.
 *
 * Extra title fields on nodes are ignored.
 *
 * @param auth - Access token.
 * @param request - Seed keys and/or document id.
 * @param fetchImpl - Injected fetch.
 * @returns Inspect payload.
 */
export async function inspectGraph(
  auth: ApiAuth,
  request: GraphInspectRequest,
  fetchImpl: typeof fetch = fetch,
): Promise<GraphInspectResponse> {
  const body = buildGraphInspectRequest(
    request.entity_keys,
    request.document_id ?? null,
    request.depth,
  );
  const payload: {
    entity_keys: string[];
    depth: number;
    document_id?: string;
  } = {
    entity_keys: body.entity_keys,
    depth: body.depth,
  };
  if (body.document_id) {
    payload.document_id = body.document_id;
  }
  const response = await fetchImpl(apiUrl("/graph/inspect"), {
    method: "POST",
    headers: paidMutationHeaders(auth),
    body: JSON.stringify(payload),
  });
  const parsed = await readJsonObject(response);
  if (!response.ok) {
    throw new Error(sanitizedDetail(parsed, "inspect_rejected"));
  }
  const nodesRaw = Array.isArray(parsed.nodes) ? parsed.nodes : [];
  const locatorsRaw = Array.isArray(parsed.locators) ? parsed.locators : [];
  const limitationsRaw = Array.isArray(parsed.limitations)
    ? parsed.limitations
    : [];
  return {
    nodes: nodesRaw.map((item) => {
      const row = item as Record<string, unknown>;
      return {
        object_type: String(row.object_type ?? ""),
        object_id: String(row.object_id ?? ""),
        chunk_id: String(row.chunk_id ?? ""),
        document_id: String(row.document_id ?? ""),
        version_id: String(row.version_id ?? ""),
        support: Number(row.support ?? 0),
        hop: Number(row.hop ?? 0),
      };
    }),
    locators: locatorsRaw.map((item) => {
      const row = item as Record<string, unknown>;
      const section = row.section_path;
      return {
        chunk_id: String(row.chunk_id ?? ""),
        document_id: String(row.document_id ?? ""),
        version_id: String(row.version_id ?? ""),
        page_number: typeof row.page_number === "number" ? row.page_number : null,
        section_path: Array.isArray(section) ? section.map(String) : [],
        sheet_name: typeof row.sheet_name === "string" ? row.sheet_name : null,
        range_ref: typeof row.range_ref === "string" ? row.range_ref : null,
        source_url: typeof row.source_url === "string" ? row.source_url : null,
      };
    }),
    limitations: limitationsRaw.map((item) => {
      const row = item as Record<string, unknown>;
      return {
        code: String(row.code ?? ""),
        count: typeof row.count === "number" ? row.count : null,
      };
    }),
    row_count: Number(parsed.row_count ?? 0),
    depth: Number(parsed.depth ?? body.depth),
  };
}

/**
 * List authorized table manifests. No storage paths.
 *
 * @param auth - Access token.
 * @param fetchImpl - Injected fetch.
 * @returns Manifests.
 */
export async function listTables(
  auth: ApiAuth,
  fetchImpl: typeof fetch = fetch,
): Promise<TableManifestResponse[]> {
  const response = await fetchImpl(apiUrl("/tables"), {
    headers: resumeHeaders(auth),
  });
  const parsed: unknown = await response.json();
  if (!Array.isArray(parsed)) {
    return [];
  }
  return parsed.map((item) => {
    const row = item as Record<string, unknown>;
    return {
      table_id: String(row.table_id ?? ""),
      document_id: String(row.document_id ?? ""),
      version_id: String(row.version_id ?? ""),
      table_name: String(row.table_name ?? ""),
      sheet_name: typeof row.sheet_name === "string" ? row.sheet_name : null,
      row_count: typeof row.row_count === "number" ? row.row_count : null,
      column_count: typeof row.column_count === "number" ? row.column_count : null,
    };
  });
}

/**
 * Execute one extra-forbid TableQueryPlan. Extra SQL-like fields are omitted.
 *
 * @param auth - Access token.
 * @param plan - Declarative plan.
 * @param fetchImpl - Injected fetch.
 * @returns Deterministic rows and source_ranges.
 */
export async function analyzeTable(
  auth: ApiAuth,
  plan: TableQueryPlan,
  fetchImpl: typeof fetch = fetch,
): Promise<TableAnalyzeResponse> {
  const response = await fetchImpl(apiUrl("/tables/analyze"), {
    method: "POST",
    headers: paidMutationHeaders(auth),
    body: JSON.stringify(tableAnalyzeBody(plan)),
  });
  const parsed = await readJsonObject(response);
  if (!response.ok) {
    throw new Error(sanitizedDetail(parsed, "table_plan_rejected"));
  }
  const rowsRaw = Array.isArray(parsed.rows) ? parsed.rows : [];
  const rangesRaw = Array.isArray(parsed.source_ranges)
    ? parsed.source_ranges
    : [];
  return {
    table_id: String(parsed.table_id ?? ""),
    version_id: String(parsed.version_id ?? ""),
    document_id: String(parsed.document_id ?? ""),
    rows: rowsRaw.filter(
      (row): row is Record<string, unknown> =>
        row !== null && typeof row === "object" && !Array.isArray(row),
    ),
    source_ranges: rangesRaw.map(String),
  };
}

/**
 * Fetch citations for an owned run.
 *
 * @param auth - Access token.
 * @param runId - Run UUID.
 * @param fetchImpl - Injected fetch.
 * @returns Citation identifiers. No passage text.
 */
export async function listCitations(
  auth: ApiAuth,
  runId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<CitationResponse[]> {
  const response = await fetchImpl(apiUrl(`/runs/${runId}/citations`), {
    headers: resumeHeaders(auth),
  });
  const parsed: unknown = await response.json();
  if (!Array.isArray(parsed)) {
    return [];
  }
  return parsed as CitationResponse[];
}

/**
 * Submit thumbs feedback with a required unmerged tag.
 *
 * @param auth - Access token.
 * @param runId - Run UUID.
 * @param thumbsUp - Rating 5 when true.
 * @param tag - Exact catalog tag.
 * @param comment - Optional correction text.
 * @param fetchImpl - Injected fetch.
 * @returns True on success.
 */
export async function submitFeedback(
  auth: ApiAuth,
  runId: string,
  thumbsUp: boolean,
  tag: FeedbackTag,
  comment: string | null,
  fetchImpl: typeof fetch = fetch,
): Promise<boolean> {
  const response = await fetchImpl(apiUrl(`/runs/${runId}/feedback`), {
    method: "POST",
    headers: paidMutationHeaders(auth),
    body: JSON.stringify({
      thumbs_up: thumbsUp,
      tag,
      comment,
    }),
  });
  return response.ok;
}

/**
 * Cancel a pending or running owned run.
 *
 * @param auth - Access token.
 * @param runId - Run UUID.
 * @param fetchImpl - Injected fetch.
 * @returns True on success.
 */
export async function cancelRun(
  auth: ApiAuth,
  runId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<boolean> {
  const response = await fetchImpl(apiUrl(`/runs/${runId}/cancel`), {
    method: "POST",
    headers: resumeHeaders(auth),
  });
  return response.ok;
}

/**
 * Parse usage totals. Prompt text fields are omitted even if present.
 *
 * @param body - JSON object.
 * @returns Totals only.
 */
function parseUsageResponse(body: Record<string, unknown>): UsageResponse {
  const cost = body.cost_usd;
  return {
    scope: String(body.scope ?? ""),
    cost_usd:
      typeof cost === "number" || typeof cost === "string" ? cost : String(cost ?? "0"),
    prompt_tokens: Number(body.prompt_tokens ?? 0),
    completion_tokens: Number(body.completion_tokens ?? 0),
    usage_rows: Number(body.usage_rows ?? 0),
  };
}

/**
 * Fetch caller usage totals without prompt text.
 *
 * @param auth - Access token.
 * @param fetchImpl - Injected fetch.
 * @returns Usage summary.
 * @throws Error when FastAPI rejects the call.
 */
export async function fetchUsageMe(
  auth: ApiAuth,
  fetchImpl: typeof fetch = fetch,
): Promise<UsageResponse> {
  const response = await fetchImpl(apiUrl("/usage/me"), {
    headers: resumeHeaders(auth),
  });
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  return parseUsageResponse(body);
}

/**
 * Fetch company usage totals. Owner/admin on the server; members 403.
 *
 * @param auth - Access token.
 * @param fetchImpl - Injected fetch.
 * @returns Company totals. No prompt text.
 * @throws Error `forbidden` for member/viewer 403.
 */
export async function fetchUsageCompany(
  auth: ApiAuth,
  fetchImpl: typeof fetch = fetch,
): Promise<UsageResponse> {
  const response = await fetchImpl(apiUrl("/usage/company"), {
    headers: resumeHeaders(auth),
  });
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  return parseUsageResponse(body);
}

/**
 * Accept a single-use invitation. Body is `{ token }` only. Email comes from
 * the verified JWT on the server, not this payload.
 *
 * @param auth - Access token.
 * @param token - Raw invitation secret.
 * @param fetchImpl - Injected fetch.
 * @returns Accepted invitation id.
 * @throws Error when FastAPI rejects the call. MFA maps to `mfa_required`.
 */
export async function acceptInvitation(
  auth: ApiAuth,
  token: string,
  fetchImpl: typeof fetch = fetch,
): Promise<AcceptInvitationResponse> {
  const response = await fetchImpl(apiUrl("/invitations/accept"), {
    method: "POST",
    headers: {
      ...resumeHeaders(auth),
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ token }),
  });
  const body = await readJsonObject(response);
  if (!response.ok) {
    const classified = classifyApiError(response.status, body, response.headers);
    if (classified?.kind === "mfa") {
      throw new Error("mfa_required");
    }
    if (classified?.kind === "auth" && classified.detail === "session_revoked") {
      throw new Error("session_revoked");
    }
    throw new Error(sanitizedDetail(body, "invitation_rejected"));
  }
  return { invitation_id: String(body.invitation_id ?? "") };
}

/**
 * Create a 24-hour invitation. Owner/admin on the server.
 *
 * Body is `{ email, role, upload_enabled }` only. `raw_token` is returned
 * once. Production never sends `X-Test-*` or a role header.
 *
 * @param auth - Access token.
 * @param input - Invitee email, role, and upload flag.
 * @param fetchImpl - Injected fetch.
 * @returns Invitation identifiers including the one-time token.
 * @throws Error `forbidden`, `mfa_required`, `budget_exhausted`, or `rate_limited`.
 */
export async function createInvitation(
  auth: ApiAuth,
  input: CreateInvitationRequest,
  fetchImpl: typeof fetch = fetch,
): Promise<CreateInvitationResponse> {
  const payload = buildInvitationCreateBody(input);
  const response = await fetchImpl(apiUrl("/admin/invitations"), {
    method: "POST",
    headers: adminMutationHeaders(auth),
    body: JSON.stringify(payload),
  });
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  return {
    invitation_id: String(body.invitation_id ?? ""),
    email: String(body.email ?? ""),
    role: String(body.role ?? ""),
    upload_enabled: Boolean(body.upload_enabled),
    expires_at: String(body.expires_at ?? ""),
    raw_token: String(body.raw_token ?? ""),
  };
}

/**
 * Offboard one subject. Owner/admin AAL2 on the server.
 *
 * @param auth - Access token. No role header.
 * @param userId - Subject user UUID from `GET /me` (no member directory).
 * @param fetchImpl - Injected fetch.
 * @returns Completed identifiers.
 * @throws Error `forbidden` or `mfa_required` on 403.
 */
export async function offboardUser(
  auth: ApiAuth,
  userId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<OffboardResponse> {
  const response = await fetchImpl(apiUrl(`/admin/users/${userId}/offboard`), {
    method: "POST",
    headers: adminMutationHeaders(auth),
  });
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  return {
    request_id: String(body.request_id ?? ""),
    subject_user_id: String(body.subject_user_id ?? ""),
    completed_at: String(body.completed_at ?? ""),
  };
}

/**
 * Parse one tool card. Unknown extra fields are ignored.
 *
 * @param row - JSON object.
 * @returns Card, or null when `tool_key` is empty.
 */
function parseToolCard(row: Record<string, unknown>): ToolCardResponse | null {
  const toolKey = String(row.tool_key ?? "");
  if (toolKey === "") {
    return null;
  }
  return {
    tool_key: toolKey,
    version_label: String(row.version_label ?? ""),
    short_name: String(row.short_name ?? ""),
    purpose: String(row.purpose ?? ""),
    required_role: String(row.required_role ?? ""),
    risk_class: String(row.risk_class ?? ""),
    active: Boolean(row.active),
  };
}

/**
 * List tools the live role may see. Unauthorized names are omitted.
 *
 * This client does not invent redacted titles for omitted tools.
 *
 * @param auth - Access token.
 * @param query - Optional substring filter.
 * @param fetchImpl - Injected fetch.
 * @returns Permission-filtered cards.
 */
export async function listTools(
  auth: ApiAuth,
  query?: string,
  fetchImpl: typeof fetch = fetch,
): Promise<ToolCardResponse[]> {
  const suffix =
    query && query.trim() !== ""
      ? `?q=${encodeURIComponent(query.trim().slice(0, 64))}`
      : "";
  const response = await fetchImpl(apiUrl(`/tools${suffix}`), {
    headers: resumeHeaders(auth),
  });
  const parsed: unknown = await response.json();
  if (!Array.isArray(parsed)) {
    return [];
  }
  return parsed
    .filter(
      (item): item is Record<string, unknown> =>
        item !== null && typeof item === "object" && !Array.isArray(item),
    )
    .map(parseToolCard)
    .filter((card): card is ToolCardResponse => card !== null);
}

/**
 * Seed an allow-listed tool. Owner/admin on the server.
 *
 * @param auth - Access token.
 * @param input - Seed payload.
 * @param fetchImpl - Injected fetch.
 * @returns Catalog row id.
 */
export async function seedTool(
  auth: ApiAuth,
  input: ToolSeedRequest,
  fetchImpl: typeof fetch = fetch,
): Promise<ToolMutationResponse> {
  const payload = buildToolSeedBody(input);
  const response = await fetchImpl(apiUrl("/admin/tools"), {
    method: "POST",
    headers: adminMutationHeaders(auth),
    body: JSON.stringify(payload),
  });
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  return { id: String(body.id ?? "") };
}

/**
 * Enable or disable a catalog tool. Owner/admin on the server.
 *
 * The helper still exists for viewer/member callers; FastAPI returns 403.
 *
 * @param auth - Access token. Bearer only; no role header.
 * @param toolKey - Catalog key.
 * @param active - Desired flag.
 * @param fetchImpl - Injected fetch.
 * @returns Catalog row id.
 */
export async function enableTool(
  auth: ApiAuth,
  toolKey: string,
  active: boolean,
  fetchImpl: typeof fetch = fetch,
): Promise<ToolMutationResponse> {
  const response = await fetchImpl(apiUrl(`/admin/tools/${toolKey}/enable`), {
    method: "POST",
    headers: adminMutationHeaders(auth),
    body: JSON.stringify(buildToolEnableBody(active)),
  });
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  return { id: String(body.id ?? "") };
}

/**
 * Set a role permission seed. Executor still rechecks live role.
 *
 * @param auth - Access token.
 * @param toolKey - Catalog key.
 * @param input - Target role and permission.
 * @param fetchImpl - Injected fetch.
 * @returns Permission row id.
 */
export async function setToolPermission(
  auth: ApiAuth,
  toolKey: string,
  input: ToolPermissionRequest,
  fetchImpl: typeof fetch = fetch,
): Promise<ToolMutationResponse> {
  const payload = buildToolPermissionBody(input);
  const response = await fetchImpl(
    apiUrl(`/admin/tools/${toolKey}/permissions`),
    {
      method: "POST",
      headers: adminMutationHeaders(auth),
      body: JSON.stringify(payload),
    },
  );
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  return { id: String(body.id ?? "") };
}

/**
 * Import a pending glossary batch. Extra SQL-like fields are omitted.
 *
 * @param auth - Access token.
 * @param input - Source, version, idempotency key, and entries.
 * @param fetchImpl - Injected fetch.
 * @returns Import identifiers.
 */
export async function importGlossary(
  auth: ApiAuth,
  input: ImportGlossaryRequest & Record<string, unknown>,
  fetchImpl: typeof fetch = fetch,
): Promise<GlossaryImportResponse> {
  const payload = buildGlossaryImportBody(input);
  const response = await fetchImpl(apiUrl("/admin/glossary/imports"), {
    method: "POST",
    headers: adminMutationHeaders(auth),
    body: JSON.stringify(payload),
  });
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  return {
    import_id: String(body.import_id ?? ""),
    status: String(body.status ?? ""),
    entry_count: Number(body.entry_count ?? 0),
    alias_count: Number(body.alias_count ?? 0),
  };
}

/**
 * Approve a pending glossary import.
 *
 * @param auth - Access token.
 * @param importId - Import UUID.
 * @param fetchImpl - Injected fetch.
 * @returns Updated identifiers.
 */
export async function approveGlossaryImport(
  auth: ApiAuth,
  importId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<GlossaryImportResponse> {
  const response = await fetchImpl(
    apiUrl(`/admin/glossary/imports/${importId}/approve`),
    {
      method: "POST",
      headers: adminMutationHeaders(auth),
    },
  );
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  return {
    import_id: String(body.import_id ?? ""),
    status: String(body.status ?? ""),
    entry_count: Number(body.entry_count ?? 0),
    alias_count: Number(body.alias_count ?? 0),
  };
}

/**
 * Roll back an approved glossary import.
 *
 * @param auth - Access token.
 * @param importId - Import UUID.
 * @param fetchImpl - Injected fetch.
 * @returns Updated identifiers.
 */
export async function rollbackGlossaryImport(
  auth: ApiAuth,
  importId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<GlossaryImportResponse> {
  const response = await fetchImpl(
    apiUrl(`/admin/glossary/imports/${importId}/rollback`),
    {
      method: "POST",
      headers: adminMutationHeaders(auth),
    },
  );
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  return {
    import_id: String(body.import_id ?? ""),
    status: String(body.status ?? ""),
    entry_count: Number(body.entry_count ?? 0),
    alias_count: Number(body.alias_count ?? 0),
  };
}

/**
 * Parse one entity-rule list row.
 *
 * @param row - JSON object.
 * @returns List item.
 */
function parseEntityRuleItem(row: Record<string, unknown>): EntityRuleListItem {
  const aliases = Array.isArray(row.aliases) ? row.aliases.map(String) : [];
  const doNotMerge = Array.isArray(row.do_not_merge)
    ? row.do_not_merge.map(String)
    : [];
  const languages = Array.isArray(row.languages) ? row.languages.map(String) : [];
  return {
    id: String(row.id ?? ""),
    entity_type: String(row.entity_type ?? ""),
    canonical_name: typeof row.canonical_name === "string" ? row.canonical_name : null,
    display_label: typeof row.display_label === "string" ? row.display_label : null,
    aliases,
    do_not_merge: doNotMerge,
    languages,
    alias_scope: String(row.alias_scope ?? ""),
    relation_label_policy: String(row.relation_label_policy ?? ""),
    status: String(row.status ?? "suggested") as EntityRuleStatus,
    active: Boolean(row.active),
    row_version: Number(row.row_version ?? 1),
    source: String(row.source ?? "admin") as EntityRuleSource,
    reason: String(row.reason ?? ""),
    confidence: typeof row.confidence === "number" ? row.confidence : null,
    created_at: typeof row.created_at === "string" ? row.created_at : null,
    updated_at: typeof row.updated_at === "string" ? row.updated_at : null,
  };
}

/**
 * List entity rules. Owner/admin on the server; members 403.
 *
 * @param auth - Access token.
 * @param fetchImpl - Injected fetch.
 * @returns `{ rules }`.
 */
export async function listEntityRules(
  auth: ApiAuth,
  fetchImpl: typeof fetch = fetch,
): Promise<EntityRuleListResponse> {
  const response = await fetchImpl(apiUrl("/admin/graph/entity-rules"), {
    headers: resumeHeaders(auth),
  });
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  const rulesRaw = Array.isArray(body.rules) ? body.rules : [];
  return {
    rules: rulesRaw
      .filter(
        (item): item is Record<string, unknown> =>
          item !== null && typeof item === "object" && !Array.isArray(item),
      )
      .map(parseEntityRuleItem),
  };
}

/**
 * Parse an entity-rule mutation response.
 *
 * @param body - JSON object.
 * @returns Mutation identifiers. Alias text is omitted.
 */
function parseEntityRuleMutation(
  body: Record<string, unknown>,
): EntityRuleMutationResponse {
  return {
    rule_id: String(body.rule_id ?? ""),
    status: String(body.status ?? "suggested") as EntityRuleStatus,
    row_version: Number(body.row_version ?? 1),
    entity_rules_generation: Number(body.entity_rules_generation ?? 0),
    rebuild_job_id:
      typeof body.rebuild_job_id === "string" ? body.rebuild_job_id : null,
    repair_job_id: typeof body.repair_job_id === "string" ? body.repair_job_id : null,
    invalidated: Boolean(body.invalidated),
  };
}

/**
 * Create or replace an entity rule. Extra fields are omitted.
 *
 * @param auth - Access token.
 * @param input - Upsert payload.
 * @param fetchImpl - Injected fetch.
 * @returns Mutation identifiers.
 */
export async function upsertEntityRule(
  auth: ApiAuth,
  input: EntityRuleUpsertRequest & Record<string, unknown>,
  fetchImpl: typeof fetch = fetch,
): Promise<EntityRuleMutationResponse> {
  const payload = buildEntityRuleUpsertBody(input);
  const response = await fetchImpl(apiUrl("/admin/graph/entity-rules"), {
    method: "POST",
    headers: adminMutationHeaders(auth),
    body: JSON.stringify(payload),
  });
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  return parseEntityRuleMutation(body);
}

/**
 * Approve a suggested entity rule. Body is `{ row_version }` only.
 *
 * @param auth - Access token.
 * @param ruleId - Rule UUID.
 * @param rowVersion - Optimistic concurrency token.
 * @param fetchImpl - Injected fetch.
 * @returns Mutation identifiers.
 * @throws Error `stale_row_version` on 409.
 */
export async function approveEntityRule(
  auth: ApiAuth,
  ruleId: string,
  rowVersion: number,
  fetchImpl: typeof fetch = fetch,
): Promise<EntityRuleMutationResponse> {
  const response = await fetchImpl(
    apiUrl(`/admin/graph/entity-rules/${ruleId}/approve`),
    {
      method: "POST",
      headers: adminMutationHeaders(auth),
      body: JSON.stringify(buildEntityRuleConcurrencyBody(rowVersion)),
    },
  );
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  return parseEntityRuleMutation(body);
}

/**
 * Revoke an entity rule. Body is `{ row_version }` only.
 *
 * @param auth - Access token.
 * @param ruleId - Rule UUID.
 * @param rowVersion - Optimistic concurrency token.
 * @param fetchImpl - Injected fetch.
 * @returns Mutation identifiers.
 */
export async function revokeEntityRule(
  auth: ApiAuth,
  ruleId: string,
  rowVersion: number,
  fetchImpl: typeof fetch = fetch,
): Promise<EntityRuleMutationResponse> {
  const response = await fetchImpl(
    apiUrl(`/admin/graph/entity-rules/${ruleId}/revoke`),
    {
      method: "POST",
      headers: adminMutationHeaders(auth),
      body: JSON.stringify(buildEntityRuleConcurrencyBody(rowVersion)),
    },
  );
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  return parseEntityRuleMutation(body);
}

export type StreamStart = {
  response: Response;
  admission: SubmitMessageResponse | null;
  failure: ApiFailure | null;
  /** True when the client skipped POST and used GET resume for an existing run. */
  resumed: boolean;
};

/** Minimal run snapshot used to prefer resume over a second paid POST. */
export type PaidRunPointer = {
  runId: string | null;
  terminal: string | null;
  lastSequence: number;
  idempotencyKey: string;
};

/**
 * Return whether the client must resume GET instead of posting again.
 *
 * @param state - Current chat run.
 * @returns True when `runId` is set and the run is not terminal.
 */
export function shouldResumeExistingRun(state: PaidRunPointer): boolean {
  return state.runId !== null && state.terminal === null;
}

/**
 * POST a chat message with JSON Accept so the 202 body includes `run_id`.
 * Handshake runs before admit. The EventSource body is `GET /runs/{id}/events`.
 *
 * Reconnect uses the same run and never starts a second paid reservation.
 *
 * @param auth - Access token.
 * @param conversationId - Conversation UUID.
 * @param message - Untrusted user text.
 * @param idempotencyKey - Stable UUID reused on retry.
 * @param fetchImpl - Injected fetch.
 * @returns Streaming GET response plus admission JSON, or a typed failure.
 */
export async function startMessageStream(
  auth: ApiAuth,
  conversationId: string,
  message: string,
  idempotencyKey: string,
  fetchImpl: typeof fetch = fetch,
): Promise<StreamStart> {
  const admitHeaders = {
    ...paidMutationHeaders(auth, idempotencyKey),
    Accept: "application/json",
  };
  const admitResponse = await fetchImpl(
    apiUrl(`/conversations/${conversationId}/messages`),
    {
      method: "POST",
      headers: admitHeaders,
      body: JSON.stringify(submitMessageBody(message, idempotencyKey)),
    },
  );
  if (!admitResponse.ok) {
    const body = await readJsonObject(admitResponse);
    return {
      response: admitResponse,
      admission: null,
      failure: classifyApiError(admitResponse.status, body, admitResponse.headers),
      resumed: false,
    };
  }
  const admission = (await admitResponse.json()) as SubmitMessageResponse;
  const stream = await resumeEventStream(auth, admission.run_id, 0, fetchImpl);
  if (!stream.ok) {
    const body = await readJsonObject(stream);
    return {
      response: stream,
      admission,
      failure: classifyApiError(stream.status, body, stream.headers),
      resumed: false,
    };
  }
  return { response: stream, admission, failure: null, resumed: false };
}

/**
 * Resume an in-flight run when `runId` is already known; otherwise admit.
 *
 * Reusing the stored run never sends a second paid POST from this client.
 * If this helper does POST (no `runId` yet), the server still reuses the
 * idempotency key.
 *
 * @param auth - Access token.
 * @param conversationId - Conversation UUID.
 * @param message - Untrusted user text. Ignored on resume.
 * @param state - Current run pointer.
 * @param fetchImpl - Injected fetch.
 * @returns Stream start. `resumed` is true when POST was skipped.
 */
export async function startOrResumeMessageStream(
  auth: ApiAuth,
  conversationId: string,
  message: string,
  state: PaidRunPointer,
  fetchImpl: typeof fetch = fetch,
): Promise<StreamStart> {
  if (shouldResumeExistingRun(state) && state.runId !== null) {
    const stream = await resumeEventStream(
      auth,
      state.runId,
      state.lastSequence,
      fetchImpl,
    );
    if (!stream.ok) {
      const body = await readJsonObject(stream);
      return {
        response: stream,
        admission: null,
        failure: classifyApiError(stream.status, body, stream.headers),
        resumed: true,
      };
    }
    return {
      response: stream,
      admission: null,
      failure: null,
      resumed: true,
    };
  }
  return startMessageStream(
    auth,
    conversationId,
    message,
    state.idempotencyKey,
    fetchImpl,
  );
}

/**
 * Resume an admitted run. Does not send `X-Client-Version`.
 *
 * @param auth - Access token.
 * @param runId - Run UUID.
 * @param after - Last applied sequence.
 * @param fetchImpl - Injected fetch.
 * @returns SSE response.
 */
export async function resumeEventStream(
  auth: ApiAuth,
  runId: string,
  after: number,
  fetchImpl: typeof fetch = fetch,
): Promise<Response> {
  const url = apiUrl(`/runs/${runId}/events?after=${encodeURIComponent(String(after))}`);
  return fetchImpl(url, {
    headers: {
      ...resumeHeaders(auth),
      Accept: "text/event-stream",
    },
  });
}

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
  DocumentResponse,
  FeedbackTag,
  MetaResponse,
  SignedUploadResponse,
  SubmitMessageResponse,
  UsageResponse,
  IngestionStatusVersion,
} from "./types";

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

export type DeletedFailure = {
  kind: "deleted";
};

export type ApiFailure = HandshakeFailure | AuthFailure | DeletedFailure;

/**
 * Parse a FastAPI error body into a typed UI failure.
 *
 * @param status - HTTP status.
 * @param body - JSON-ish object.
 * @returns Typed failure when the status is an expected gate.
 */
export function classifyApiError(
  status: number,
  body: Record<string, unknown>,
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
  if (status === 401 || status === 403) {
    const detail = typeof body.detail === "string" ? body.detail : "unauthorized";
    return { kind: "auth", status, detail };
  }
  if (status === 404) {
    return { kind: "deleted" };
  }
  return null;
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
  return {
    api_version: String(body.api_version ?? ""),
    sse_schema_version: String(body.sse_schema_version ?? ""),
    min_client_version: String(body.min_client_version ?? ""),
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
 * @returns Version diagnostics, or null on 404.
 */
export async function fetchVersionStatus(
  auth: ApiAuth,
  versionId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<IngestionStatusVersion | null> {
  const response = await fetchImpl(
    apiUrl(`/ingestion/versions/${versionId}/status`),
    { headers: resumeHeaders(auth) },
  );
  if (response.status === 404) {
    return null;
  }
  const body = (await response.json()) as { version?: IngestionStatusVersion };
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
  return version;
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
 * Fetch caller usage totals without prompt text.
 *
 * @param auth - Access token.
 * @param fetchImpl - Injected fetch.
 * @returns Usage summary.
 */
export async function fetchUsageMe(
  auth: ApiAuth,
  fetchImpl: typeof fetch = fetch,
): Promise<UsageResponse> {
  const response = await fetchImpl(apiUrl("/usage/me"), {
    headers: resumeHeaders(auth),
  });
  return (await response.json()) as UsageResponse;
}

export type StreamStart = {
  response: Response;
  admission: SubmitMessageResponse | null;
  failure: ApiFailure | null;
};

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
      body: JSON.stringify({ message, idempotency_key: idempotencyKey }),
    },
  );
  if (!admitResponse.ok) {
    const body = await readJsonObject(admitResponse);
    return {
      response: admitResponse,
      admission: null,
      failure: classifyApiError(admitResponse.status, body),
    };
  }
  const admission = (await admitResponse.json()) as SubmitMessageResponse;
  const stream = await resumeEventStream(auth, admission.run_id, 0, fetchImpl);
  if (!stream.ok) {
    const body = await readJsonObject(stream);
    return {
      response: stream,
      admission,
      failure: classifyApiError(stream.status, body),
    };
  }
  return { response: stream, admission, failure: null };
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

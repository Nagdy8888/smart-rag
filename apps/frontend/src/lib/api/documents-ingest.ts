/**
 * Upload reserve/finalize, crawl, and ingestion retry HTTP helpers.
 */

import type {
  EnqueueWebsiteCrawlRequest,
  EnqueueWebsiteCrawlResponse,
  FinalizeUploadHttpRequest,
  FinalizeUploadHttpResponse,
  RetryIngestionJobResponse,
  SignedUploadResponse,
} from "../types";
import { sanitizedDetail, throwIfNotOk } from "./errors";
import type { ApiAuth } from "./headers";
import { paidMutationHeaders } from "./headers";
import { apiUrl, readJsonObject } from "./http";

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
    await readJsonObject(response);
    throw new Error("upload_reserve_failed");
  }
  return (await response.json()) as SignedUploadResponse;
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
    throwIfNotOk(response, parsed);
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

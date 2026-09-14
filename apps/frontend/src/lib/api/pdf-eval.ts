/**
 * Hosted PDF evaluation workspace HTTP helpers. Owner/admin only.
 *
 * Hidden Ask chrome is not authorization. FastAPI still 403s members.
 */

import { throwClassifiedAdminError } from "./admin-errors";
import type { ApiAuth } from "./headers";
import { adminMutationHeaders, paidMutationHeaders, resumeHeaders } from "./headers";
import { apiUrl, readJsonObject } from "./http";
import type {
  PdfEvalCaseCreateRequest,
  PdfEvalCaseDetail,
  PdfEvalCaseList,
  PdfEvalCaseSummary,
  PdfEvalCompareRun,
  PdfEvalEmptyDataset,
  PdfEvalExamAccepted,
  PdfEvalExamCase,
  PdfEvalExamCaseList,
  PdfEvalExamReport,
  PdfEvalExamStatus,
  PdfEvalGoldLocator,
  PdfEvalMutation,
  PdfEvalPassage,
  PdfEvalPassageList,
  PdfEvalStatus,
} from "../types/pdf-eval";

/**
 * Optional keyset filters for case summaries.
 */
export type PdfEvalCaseListQuery = {
  /** Split filter. `holdout` is rejected by the server. */
  split?: string;
  /** Optional `draft`, `approved`, or `rejected`. */
  review_status?: string;
  /** Keyset cursor from the previous page. */
  after?: string | null;
  /** Page size 1–20. */
  limit?: number;
};

/** Keyset filters for current-document passages. */
export type PdfEvalPassageListQuery = {
  /** Required current document. */
  documentId: string;
  /** Keyset cursor from the previous page. */
  after?: string | null;
  /** Page size 1–60. */
  limit?: number;
};

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === "string");
}

function numberList(value: unknown): number[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((item) => Number(item)).filter((item) => Number.isFinite(item));
}

function optionalString(value: unknown): string | null {
  return typeof value === "string" && value !== "" ? value : null;
}

function parseGold(value: unknown): PdfEvalGoldLocator[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((item) => {
    if (item === null || typeof item !== "object" || Array.isArray(item)) {
      return [];
    }
    const row = item as Record<string, unknown>;
    const chunkId = String(row.chunk_id ?? "");
    if (chunkId === "") {
      return [];
    }
    return [
      {
        ordinal: Number(row.ordinal ?? 0),
        chunk_id: chunkId,
        document_id: String(row.document_id ?? ""),
        version_id: String(row.version_id ?? ""),
        page_number:
          typeof row.page_number === "number" ? row.page_number : null,
        page_label: optionalString(row.page_label),
        section_path: stringList(row.section_path),
        stale: Boolean(row.stale),
      },
    ];
  });
}

function parseSummary(row: Record<string, unknown>): PdfEvalCaseSummary | null {
  const caseId = String(row.case_id ?? "");
  if (caseId === "") {
    return null;
  }
  const reviewStatus = String(row.review_status ?? "");
  const humanApproved =
    Boolean(row.human_approved) || reviewStatus === "approved";
  return {
    case_id: caseId,
    split: String(row.split ?? ""),
    query_class: String(row.query_class ?? ""),
    human_approved: humanApproved,
    generated_only: Boolean(row.generated_only),
    reviewer: optionalString(row.reviewer),
    expected_refusal: Boolean(row.expected_refusal),
    gold_chunk_count: Number(row.gold_chunk_count ?? 0),
    review_status: reviewStatus || (humanApproved ? "approved" : "draft"),
    source_family_id: optionalString(row.source_family_id),
    gold_stale: Boolean(row.gold_stale),
    row_version: Number(row.row_version ?? 0),
  };
}

function parseMutation(body: Record<string, unknown>): PdfEvalMutation {
  return {
    case_id: optionalString(body.case_id),
    row_version:
      typeof body.row_version === "number"
        ? body.row_version
        : Number(body.row_version ?? 0) || null,
    replayed: Boolean(body.replayed),
    inserted_count:
      typeof body.inserted_count === "number" ? body.inserted_count : null,
    gold_chunk_count:
      typeof body.gold_chunk_count === "number" ? body.gold_chunk_count : null,
  };
}

function parsePassage(row: Record<string, unknown>): PdfEvalPassage | null {
  const chunkId = String(row.chunk_id ?? "");
  if (chunkId === "") {
    return null;
  }
  return {
    chunk_id: chunkId,
    document_id: String(row.document_id ?? ""),
    version_id: String(row.version_id ?? ""),
    page_number: typeof row.page_number === "number" ? row.page_number : null,
    heading_path: stringList(row.heading_path),
    raw_text: String(row.raw_text ?? ""),
  };
}

/**
 * GET `/admin/pdf-eval/status`.
 *
 * @param auth - Access token.
 * @param fetchImpl - Injected fetch.
 * @returns Status without questions.
 * @throws Error `forbidden` or `request_rejected`.
 */
export async function fetchPdfEvalStatus(
  auth: ApiAuth,
  fetchImpl: typeof fetch = fetch,
): Promise<PdfEvalStatus> {
  const response = await fetchImpl(apiUrl("/admin/pdf-eval/status"), {
    headers: resumeHeaders(auth),
  });
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  return {
    enabled: Boolean(body.enabled),
    case_count: Number(body.case_count ?? body.live_count ?? 0),
    revision: typeof body.revision === "string" ? body.revision : null,
    version_id: typeof body.version_id === "string" ? body.version_id : null,
    document_id: typeof body.document_id === "string" ? body.document_id : null,
    dataset_present: Boolean(body.dataset_present),
    schema_ready: body.schema_ready !== false,
    holdout_opened: Boolean(body.holdout_opened),
    draft_count: Number(body.draft_count ?? 0),
    approved_count: Number(body.approved_count ?? 0),
    rejected_count: Number(body.rejected_count ?? 0),
    stale_gold_count: Number(body.stale_gold_count ?? 0),
    live_count: Number(body.live_count ?? body.case_count ?? 0),
    remaining_capacity: Number(body.remaining_capacity ?? 0),
  };
}

/**
 * GET `/admin/pdf-eval/cases` without bulk question fields.
 *
 * @param auth - Access token.
 * @param fetchImpl - Injected fetch.
 * @param query - Optional split/keyset filters.
 * @returns Summaries and optional next cursor.
 * @throws Error `forbidden` or `request_rejected`.
 */
export async function listPdfEvalCases(
  auth: ApiAuth,
  fetchImpl: typeof fetch = fetch,
  query: PdfEvalCaseListQuery = {},
): Promise<PdfEvalCaseList> {
  const params = new URLSearchParams();
  if (query.split) {
    params.set("split", query.split);
  }
  if (query.review_status) {
    params.set("review_status", query.review_status);
  }
  if (query.after) {
    params.set("after", query.after);
  }
  if (query.limit !== undefined) {
    params.set("limit", String(query.limit));
  }
  const encoded = params.toString();
  const suffix = encoded ? `?${encoded}` : "";
  const response = await fetchImpl(apiUrl(`/admin/pdf-eval/cases${suffix}`), {
    headers: resumeHeaders(auth),
  });
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  const itemsRaw = Array.isArray(body.items) ? body.items : [];
  const items: PdfEvalCaseSummary[] = itemsRaw.flatMap((item) => {
    if (item === null || typeof item !== "object" || Array.isArray(item)) {
      return [];
    }
    const parsed = parseSummary(item as Record<string, unknown>);
    return parsed ? [parsed] : [];
  });
  return {
    revision: String(body.revision ?? ""),
    items,
    next_case_id: typeof body.next_case_id === "string" ? body.next_case_id : null,
  };
}

/**
 * GET `/admin/pdf-eval/cases/{id}`.
 *
 * @param auth - Access token.
 * @param caseId - Case identifier.
 * @param fetchImpl - Injected fetch.
 * @returns Detail including private question fields.
 * @throws Error `forbidden` or `request_rejected`.
 */
export async function fetchPdfEvalCase(
  auth: ApiAuth,
  caseId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<PdfEvalCaseDetail> {
  const response = await fetchImpl(apiUrl(`/admin/pdf-eval/cases/${caseId}`), {
    headers: resumeHeaders(auth),
  });
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  const gold = parseGold(body.gold);
  const chunkIds =
    gold.length > 0 ? gold.map((item) => item.chunk_id) : stringList(body.chunk_ids);
  const pageNumbers =
    gold.length > 0
      ? gold
          .map((item) => item.page_number)
          .filter((item): item is number => item !== null)
      : numberList(body.page_numbers);
  const headingPaths =
    gold.length > 0
      ? gold.map((item) => item.section_path.join(" / ")).filter((item) => item !== "")
      : stringList(body.heading_paths);
  const reviewStatus = String(body.review_status ?? "");
  const humanApproved =
    Boolean(body.human_approved) || reviewStatus === "approved";
  const rowVersion = Number(body.row_version ?? 0);
  const revision =
    typeof body.revision === "string" && body.revision !== ""
      ? body.revision
      : String(rowVersion || "");
  return {
    revision,
    case_id: String(body.case_id ?? caseId),
    split: String(body.split ?? ""),
    query_class: String(body.query_class ?? ""),
    human_approved: humanApproved,
    generated_only: Boolean(body.generated_only),
    reviewer: optionalString(body.reviewer),
    expected_refusal: Boolean(body.expected_refusal),
    expected_scope: String(body.expected_scope ?? ""),
    chunk_ids: chunkIds,
    page_numbers: pageNumbers,
    heading_paths: headingPaths,
    required_terms: stringList(body.required_terms),
    question: String(body.question ?? ""),
    expected_answer: String(body.expected_answer ?? ""),
    atomic_facts: stringList(body.atomic_facts),
    review_status: reviewStatus || (humanApproved ? "approved" : "draft"),
    source_family_id: optionalString(body.source_family_id),
    source_run_id: optionalString(body.source_run_id),
    document_id: optionalString(body.document_id),
    version_id: optionalString(body.version_id),
    gold,
    gold_stale: Boolean(body.gold_stale),
    reviewer_user_id: optionalString(body.reviewer_user_id),
    row_version: rowVersion,
  };
}

/**
 * POST `/admin/pdf-eval/cases`. Browser question text is omitted.
 *
 * @param auth - Access token.
 * @param body - Run id, labels, optional gold IDs, idempotency key.
 * @param fetchImpl - Injected fetch.
 * @returns Case id, row version, and replay flag.
 * @throws Error `forbidden`, `validation_failed`, or `request_rejected`.
 * @remarks
 * Authorization: owner/admin only. Members remain 403. Never sends
 * `question`. Split is always `development` from Ask. Never approves.
 */
export async function createPdfEvalCase(
  auth: ApiAuth,
  body: PdfEvalCaseCreateRequest,
  fetchImpl: typeof fetch = fetch,
): Promise<PdfEvalMutation> {
  const payload: Record<string, unknown> = {
    source_run_id: body.source_run_id,
    query_class: body.query_class,
    split: body.split ?? "development",
    idempotency_key: body.idempotency_key,
    chunk_ids: body.chunk_ids ?? [],
    expected_answer: body.expected_answer ?? "",
    atomic_facts: body.atomic_facts ?? [],
    required_terms: body.required_terms ?? [],
  };
  if (body.source_family_id) {
    payload.source_family_id = body.source_family_id;
  }
  const response = await fetchImpl(apiUrl("/admin/pdf-eval/cases"), {
    method: "POST",
    headers: adminMutationHeaders(auth),
    body: JSON.stringify(payload),
  });
  const responseBody = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, responseBody, response.headers);
  }
  return parseMutation(responseBody);
}

/**
 * PATCH `/admin/pdf-eval/cases/{id}` with compare-and-swap.
 *
 * @param auth - Access token.
 * @param caseId - Case identifier.
 * @param expectedRowVersion - Held `row_version`.
 * @param patch - Editable fields only. Cannot set reviewer or split.
 * @param fetchImpl - Injected fetch.
 * @returns New row version.
 * @throws Error `stale_row_version` on 409.
 */
export async function patchPdfEvalCase(
  auth: ApiAuth,
  caseId: string,
  expectedRowVersion: number,
  patch: {
    question?: string;
    expected_answer?: string;
    atomic_facts?: string[];
    query_class?: string;
    required_terms?: string[];
  },
  fetchImpl: typeof fetch = fetch,
): Promise<PdfEvalMutation> {
  const response = await fetchImpl(apiUrl(`/admin/pdf-eval/cases/${caseId}`), {
    method: "PATCH",
    headers: adminMutationHeaders(auth),
    body: JSON.stringify({ expected_row_version: expectedRowVersion, ...patch }),
  });
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  return parseMutation(body);
}

/**
 * POST approve or reject. Reviewer is server-derived.
 *
 * @param auth - Access token.
 * @param caseId - Case identifier.
 * @param expectedRowVersion - Held `row_version`.
 * @param approved - Approve vs reject.
 * @param fetchImpl - Injected fetch.
 * @returns New row version.
 * @throws Error `stale_row_version` on 409, `gold_stale` when locators are stale.
 */
export async function setPdfEvalApproval(
  auth: ApiAuth,
  caseId: string,
  expectedRowVersion: number,
  approved: boolean,
  fetchImpl: typeof fetch = fetch,
): Promise<PdfEvalMutation> {
  const action = approved ? "approve" : "reject";
  const response = await fetchImpl(
    apiUrl(`/admin/pdf-eval/cases/${caseId}/${action}`),
    {
      method: "POST",
      headers: adminMutationHeaders(auth),
      body: JSON.stringify({ expected_row_version: expectedRowVersion }),
    },
  );
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  return parseMutation(body);
}

/**
 * PUT `/admin/pdf-eval/cases/{id}/gold`. Locators are server-derived.
 *
 * @param auth - Access token.
 * @param caseId - Case identifier.
 * @param expectedRowVersion - Held `row_version`.
 * @param chunkIds - Zero to three current chunk IDs.
 * @param fetchImpl - Injected fetch.
 * @returns New row version. Clears approval.
 * @throws Error `stale_row_version` on 409.
 */
export async function replacePdfEvalGold(
  auth: ApiAuth,
  caseId: string,
  expectedRowVersion: number,
  chunkIds: readonly string[],
  fetchImpl: typeof fetch = fetch,
): Promise<PdfEvalMutation> {
  const response = await fetchImpl(
    apiUrl(`/admin/pdf-eval/cases/${caseId}/gold`),
    {
      method: "PUT",
      headers: adminMutationHeaders(auth),
      body: JSON.stringify({
        expected_row_version: expectedRowVersion,
        chunk_ids: chunkIds,
      }),
    },
  );
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  return parseMutation(body);
}

/**
 * DELETE `/admin/pdf-eval/cases/{id}` with compare-and-swap.
 *
 * @param auth - Access token.
 * @param caseId - Case identifier.
 * @param expectedRowVersion - Held `row_version`.
 * @param fetchImpl - Injected fetch.
 * @returns Deleted case id.
 * @throws Error `stale_row_version` on 409.
 */
export async function deletePdfEvalCase(
  auth: ApiAuth,
  caseId: string,
  expectedRowVersion: number,
  fetchImpl: typeof fetch = fetch,
): Promise<PdfEvalMutation> {
  const response = await fetchImpl(apiUrl(`/admin/pdf-eval/cases/${caseId}`), {
    method: "DELETE",
    headers: adminMutationHeaders(auth),
    body: JSON.stringify({ expected_row_version: expectedRowVersion }),
  });
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  return parseMutation(body);
}

/**
 * POST `/admin/pdf-eval/drafts/regenerate` for one current document.
 *
 * Generated rows remain unapproved.
 *
 * @param auth - Access token.
 * @param documentId - Selected current document.
 * @param fetchImpl - Injected fetch.
 * @returns Inserted draft count.
 * @throws Error `capacity_exceeded` on 409, or `request_rejected`.
 */
export async function regeneratePdfEvalDrafts(
  auth: ApiAuth,
  documentId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<PdfEvalMutation> {
  const response = await fetchImpl(apiUrl("/admin/pdf-eval/drafts/regenerate"), {
    method: "POST",
    headers: adminMutationHeaders(auth),
    body: JSON.stringify({ document_id: documentId }),
  });
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  return parseMutation(body);
}

/**
 * GET `/admin/pdf-eval/passages` for one selected current document.
 *
 * @param auth - Access token.
 * @param query - Required `documentId` plus optional keyset.
 * @param fetchImpl - Injected fetch.
 * @returns Authorized current passages.
 * @throws Error `forbidden` or `request_rejected`.
 */
export async function listPdfEvalPassages(
  auth: ApiAuth,
  query: PdfEvalPassageListQuery,
  fetchImpl: typeof fetch = fetch,
): Promise<PdfEvalPassageList> {
  const params = new URLSearchParams();
  params.set("document_id", query.documentId);
  if (query.after) {
    params.set("after", query.after);
  }
  if (query.limit !== undefined) {
    params.set("limit", String(query.limit));
  }
  const encoded = params.toString();
  const response = await fetchImpl(
    apiUrl(`/admin/pdf-eval/passages?${encoded}`),
    {
      headers: resumeHeaders(auth),
    },
  );
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  const itemsRaw = Array.isArray(body.items) ? body.items : [];
  const items: PdfEvalPassage[] = itemsRaw.flatMap((item) => {
    if (item === null || typeof item !== "object" || Array.isArray(item)) {
      return [];
    }
    const parsed = parsePassage(item as Record<string, unknown>);
    return parsed ? [parsed] : [];
  });
  return {
    items,
    next_chunk_id:
      typeof body.next_chunk_id === "string" ? body.next_chunk_id : null,
  };
}

/**
 * POST `/admin/pdf-eval/cases/{id}/compare-run`.
 *
 * Sends `{ run_id }` only. Expected answers are never included.
 *
 * @param auth - Access token.
 * @param caseId - Case identifier.
 * @param runId - Caller-owned run.
 * @param fetchImpl - Injected fetch.
 * @returns Count-only overlap. `manual_ai_test` is not Recall@10.
 */
export async function comparePdfEvalRun(
  auth: ApiAuth,
  caseId: string,
  runId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<PdfEvalCompareRun> {
  const response = await fetchImpl(
    apiUrl(`/admin/pdf-eval/cases/${caseId}/compare-run`),
    {
      method: "POST",
      headers: adminMutationHeaders(auth),
      body: JSON.stringify({ run_id: runId }),
    },
  );
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  return {
    case_id: String(body.case_id ?? caseId),
    split: String(body.split ?? ""),
    gold_count: Number(body.gold_count ?? 0),
    citation_count: Number(body.citation_count ?? 0),
    intersection: Number(body.intersection ?? 0),
    ranked_hit_at_10: Number(body.ranked_hit_at_10 ?? 0),
    run_id: String(body.run_id ?? runId),
    manual_ai_test: Boolean(body.manual_ai_test),
  };
}

function parseExamStatus(body: Record<string, unknown>, fallbackId: string): PdfEvalExamStatus {
  return {
    exam_run_id: String(body.exam_run_id ?? fallbackId),
    split: String(body.split ?? ""),
    status: String(body.status ?? ""),
    dataset_hash: String(body.dataset_hash ?? ""),
    case_count: Number(body.case_count ?? 0),
    completed_case_count: Number(body.completed_case_count ?? 0),
    holdout_opened: Boolean(body.holdout_opened),
    candidate_fingerprint: optionalString(body.candidate_fingerprint),
  };
}

/**
 * POST `/admin/pdf-eval/exams`. HTTP never scores cases.
 *
 * @param auth - Access token.
 * @param body - Split, idempotency key, optional dataset CAS hash.
 * @param fetchImpl - Injected fetch.
 * @returns 202 accepted or idempotent reconnect.
 * @throws Error `empty_dataset`, `already_running`, `qualification_consumed`,
 *   `forbidden`, or `request_rejected`.
 */
export async function startPdfEvalExam(
  auth: ApiAuth,
  body: {
    split: "development" | "qualification";
    idempotency_key: string;
    expected_dataset_hash?: string | null;
  },
  fetchImpl: typeof fetch = fetch,
): Promise<PdfEvalExamAccepted> {
  const payload: Record<string, unknown> = {
    split: body.split,
    idempotency_key: body.idempotency_key,
  };
  if (body.expected_dataset_hash) {
    payload.expected_dataset_hash = body.expected_dataset_hash;
  }
  const response = await fetchImpl(apiUrl("/admin/pdf-eval/exams"), {
    method: "POST",
    headers: paidMutationHeaders(auth, body.idempotency_key),
    body: JSON.stringify(payload),
  });
  const responseBody = await readJsonObject(response);
  if (response.status === 422 && responseBody.detail === "empty_dataset") {
    const error = new Error("empty_dataset") as Error & PdfEvalEmptyDataset;
    error.detail = "empty_dataset";
    error.draft_count = Number(responseBody.draft_count ?? 0);
    error.approved_count = Number(responseBody.approved_count ?? 0);
    error.rejected_count = Number(responseBody.rejected_count ?? 0);
    error.stale_gold_count = Number(responseBody.stale_gold_count ?? 0);
    error.live_count = Number(responseBody.live_count ?? 0);
    throw error;
  }
  if (!response.ok) {
    throwClassifiedAdminError(response.status, responseBody, response.headers);
  }
  return {
    exam_run_id: String(responseBody.exam_run_id ?? ""),
    status: String(responseBody.status ?? ""),
    dataset_hash: String(responseBody.dataset_hash ?? ""),
    replayed: Boolean(responseBody.replayed),
    holdout_opened: Boolean(responseBody.holdout_opened),
  };
}

/**
 * GET `/admin/pdf-eval/exams/{id}`.
 *
 * @param auth - Access token.
 * @param examRunId - Exam id.
 * @param fetchImpl - Injected fetch.
 * @returns Count-only status.
 */
export async function fetchPdfEvalExam(
  auth: ApiAuth,
  examRunId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<PdfEvalExamStatus> {
  const response = await fetchImpl(apiUrl(`/admin/pdf-eval/exams/${examRunId}`), {
    headers: resumeHeaders(auth),
  });
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  return parseExamStatus(body, examRunId);
}

/**
 * POST `/admin/pdf-eval/exams/{id}/cancel`.
 *
 * @param auth - Access token.
 * @param examRunId - Exam id.
 * @param fetchImpl - Injected fetch.
 * @returns Status after cancel.
 */
export async function cancelPdfEvalExam(
  auth: ApiAuth,
  examRunId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<PdfEvalExamStatus> {
  const response = await fetchImpl(
    apiUrl(`/admin/pdf-eval/exams/${examRunId}/cancel`),
    {
      method: "POST",
      headers: paidMutationHeaders(auth),
    },
  );
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  return parseExamStatus(body, examRunId);
}

/**
 * GET `/admin/pdf-eval/reports/latest`.
 *
 * @param auth - Access token.
 * @param split - `development` or `qualification`.
 * @param fetchImpl - Injected fetch.
 * @returns Count-only official report or `present=false`.
 */
export async function fetchPdfEvalLatestReport(
  auth: ApiAuth,
  split: "development" | "qualification",
  fetchImpl: typeof fetch = fetch,
): Promise<PdfEvalExamReport> {
  const params = new URLSearchParams();
  params.set("split", split);
  const response = await fetchImpl(
    apiUrl(`/admin/pdf-eval/reports/latest?${params.toString()}`),
    { headers: resumeHeaders(auth) },
  );
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  return {
    present: Boolean(body.present),
    holdout_opened: Boolean(body.holdout_opened),
    exam_run_id: optionalString(body.exam_run_id),
    split: optionalString(body.split),
    dataset_hash: optionalString(body.dataset_hash),
    case_count: typeof body.case_count === "number" ? body.case_count : null,
    hit_count: typeof body.hit_count === "number" ? body.hit_count : null,
    hybrid_recall_at_10:
      typeof body.hybrid_recall_at_10 === "number" ? body.hybrid_recall_at_10 : null,
    gates_pass: typeof body.gates_pass === "boolean" ? body.gates_pass : null,
    created_at: optionalString(body.created_at),
  };
}

/**
 * GET `/admin/pdf-eval/reports/{id}/cases`.
 *
 * @param auth - Access token.
 * @param examRunId - Succeeded exam id.
 * @param fetchImpl - Injected fetch.
 * @returns Count-only case rows.
 */
export async function listPdfEvalExamCases(
  auth: ApiAuth,
  examRunId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<PdfEvalExamCaseList> {
  const response = await fetchImpl(
    apiUrl(`/admin/pdf-eval/reports/${examRunId}/cases`),
    { headers: resumeHeaders(auth) },
  );
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  const itemsRaw = Array.isArray(body.items) ? body.items : [];
  const items: PdfEvalExamCase[] = itemsRaw.flatMap((item) => {
    if (item === null || typeof item !== "object" || Array.isArray(item)) {
      return [];
    }
    const row = item as Record<string, unknown>;
    const caseId = String(row.case_id ?? "");
    if (caseId === "") {
      return [];
    }
    return [
      {
        case_id: caseId,
        ordinal: Number(row.ordinal ?? 0),
        hit: Boolean(row.hit),
        gold_count: Number(row.gold_count ?? 0),
        ranked_hit_count: Number(row.ranked_hit_count ?? 0),
        latency_ms: typeof row.latency_ms === "number" ? row.latency_ms : null,
      },
    ];
  });
  return {
    exam_run_id: String(body.exam_run_id ?? examRunId),
    items,
    missed_count: Number(body.missed_count ?? items.filter((item) => !item.hit).length),
  };
}

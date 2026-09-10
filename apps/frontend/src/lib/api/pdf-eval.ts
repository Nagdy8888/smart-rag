/**
 * Local PDF evaluation workspace HTTP helpers. Owner/admin only.
 */

import { throwClassifiedAdminError } from "./admin-errors";
import type { ApiAuth } from "./headers";
import { adminMutationHeaders, resumeHeaders } from "./headers";
import { apiUrl, readJsonObject } from "./http";
import type {
  PdfEvalCaseDetail,
  PdfEvalCaseList,
  PdfEvalCaseSummary,
  PdfEvalCompareRun,
  PdfEvalPassage,
  PdfEvalStatus,
} from "../types/pdf-eval";

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
    case_count: Number(body.case_count ?? 0),
    revision: typeof body.revision === "string" ? body.revision : null,
    version_id: typeof body.version_id === "string" ? body.version_id : null,
    document_id: typeof body.document_id === "string" ? body.document_id : null,
    dataset_present: Boolean(body.dataset_present),
  };
}

/**
 * GET `/admin/pdf-eval/cases` without bulk question fields.
 *
 * @param auth - Access token.
 * @param fetchImpl - Injected fetch.
 * @returns Summaries and revision.
 */
export async function listPdfEvalCases(
  auth: ApiAuth,
  fetchImpl: typeof fetch = fetch,
): Promise<PdfEvalCaseList> {
  const response = await fetchImpl(apiUrl("/admin/pdf-eval/cases"), {
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
    const row = item as Record<string, unknown>;
    const caseId = String(row.case_id ?? "");
    if (caseId === "") {
      return [];
    }
    return [
      {
        case_id: caseId,
        split: String(row.split ?? ""),
        query_class: String(row.query_class ?? ""),
        human_approved: Boolean(row.human_approved),
        generated_only: Boolean(row.generated_only),
        reviewer: typeof row.reviewer === "string" ? row.reviewer : null,
        expected_refusal: Boolean(row.expected_refusal),
        gold_chunk_count: Number(row.gold_chunk_count ?? 0),
      },
    ];
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
  return {
    revision: String(body.revision ?? ""),
    case_id: String(body.case_id ?? caseId),
    split: String(body.split ?? ""),
    query_class: String(body.query_class ?? ""),
    human_approved: Boolean(body.human_approved),
    generated_only: Boolean(body.generated_only),
    reviewer: typeof body.reviewer === "string" ? body.reviewer : null,
    expected_refusal: Boolean(body.expected_refusal),
    expected_scope: String(body.expected_scope ?? ""),
    chunk_ids: stringList(body.chunk_ids),
    page_numbers: numberList(body.page_numbers),
    heading_paths: stringList(body.heading_paths),
    required_terms: stringList(body.required_terms),
    question: String(body.question ?? ""),
    expected_answer: String(body.expected_answer ?? ""),
    atomic_facts: stringList(body.atomic_facts),
  };
}

/**
 * PATCH `/admin/pdf-eval/cases/{id}` with compare-and-swap.
 *
 * @param auth - Access token.
 * @param caseId - Case identifier.
 * @param expectedRevision - SHA-256 held by the editor.
 * @param patch - Editable fields only.
 * @param fetchImpl - Injected fetch.
 * @returns New revision.
 */
export async function patchPdfEvalCase(
  auth: ApiAuth,
  caseId: string,
  expectedRevision: string,
  patch: {
    question?: string;
    expected_answer?: string;
    atomic_facts?: string[];
  },
  fetchImpl: typeof fetch = fetch,
): Promise<string> {
  const response = await fetchImpl(apiUrl(`/admin/pdf-eval/cases/${caseId}`), {
    method: "PATCH",
    headers: adminMutationHeaders(auth),
    body: JSON.stringify({ expected_revision: expectedRevision, ...patch }),
  });
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  return String(body.revision ?? "");
}

/**
 * POST approve or reject. Reviewer is server-derived.
 *
 * @param auth - Access token.
 * @param caseId - Case identifier.
 * @param expectedRevision - SHA-256.
 * @param approved - Approve vs reject.
 * @param fetchImpl - Injected fetch.
 * @returns New revision.
 */
export async function setPdfEvalApproval(
  auth: ApiAuth,
  caseId: string,
  expectedRevision: string,
  approved: boolean,
  fetchImpl: typeof fetch = fetch,
): Promise<string> {
  const action = approved ? "approve" : "reject";
  const response = await fetchImpl(
    apiUrl(`/admin/pdf-eval/cases/${caseId}/${action}`),
    {
      method: "POST",
      headers: adminMutationHeaders(auth),
      body: JSON.stringify({ expected_revision: expectedRevision }),
    },
  );
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  return String(body.revision ?? "");
}

/**
 * GET `/admin/pdf-eval/passages`.
 *
 * @param auth - Access token.
 * @param fetchImpl - Injected fetch.
 * @returns Authorized current passages.
 */
export async function listPdfEvalPassages(
  auth: ApiAuth,
  fetchImpl: typeof fetch = fetch,
): Promise<PdfEvalPassage[]> {
  const response = await fetchImpl(apiUrl("/admin/pdf-eval/passages"), {
    headers: resumeHeaders(auth),
  });
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  const itemsRaw = Array.isArray(body.items) ? body.items : [];
  return itemsRaw.flatMap((item) => {
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
        chunk_id: chunkId,
        document_id: String(row.document_id ?? ""),
        version_id: String(row.version_id ?? ""),
        page_number:
          typeof row.page_number === "number" ? row.page_number : null,
        heading_path: stringList(row.heading_path),
        raw_text: String(row.raw_text ?? ""),
      },
    ];
  });
}

/**
 * POST `/admin/pdf-eval/cases/{id}/compare-run`.
 *
 * @param auth - Access token.
 * @param caseId - Case identifier.
 * @param runId - Caller-owned run.
 * @param fetchImpl - Injected fetch.
 * @returns Count-only overlap.
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

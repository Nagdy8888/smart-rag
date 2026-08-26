/**
 * Glossary import HTTP helpers.
 */

import type { GlossaryImportResponse, ImportGlossaryRequest } from "../types";
import { buildGlossaryImportBody } from "../admin-bodies";
import { throwClassifiedAdminError } from "./admin-errors";
import type { ApiAuth } from "./headers";
import { adminMutationHeaders } from "./headers";
import { apiUrl, readJsonObject } from "./http";

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

/** Canonical governance API; authority labels never grant document access. */
import type { ApiAuth } from "./headers";
import { adminMutationHeaders, resumeHeaders } from "./headers";
import { apiUrl, readJsonObject } from "./http";
import { throwIfNotOk } from "./errors";

export type DocumentGovernance = {
  version_id: string | null;
  version_number?: number | null;
  owner_user_id: string | null;
  owner_display_name?: string | null;
  knowledge_area: string | null;
  review_due_at: string | null;
  authority_status: "unreviewed" | "draft" | "approved" | "superseded";
  effective_at: string | null;
  superseded_by_version_id: string | null;
  governance_generation: number;
  reliability_enabled: boolean;
};

export type GovernanceUpdate = Omit<DocumentGovernance,
  "version_id" | "version_number" | "owner_display_name" | "governance_generation" | "reliability_enabled"> & {
    version_id: string;
    expected_generation: number;
  };

/** Load live metadata or submit an optimistic, server-authorized replacement. */
export async function documentGovernance(
  auth: ApiAuth, documentId: string, body?: GovernanceUpdate,
  fetchImpl: typeof fetch = fetch,
  versionId?: string | null,
): Promise<DocumentGovernance> {
  const suffix = versionId ? `?version_id=${encodeURIComponent(versionId)}` : "";
  const response = await fetchImpl(apiUrl(`/documents/${encodeURIComponent(documentId)}/governance${suffix}`), {
    method: body ? "PATCH" : "GET",
    headers: body ? adminMutationHeaders(auth) : resumeHeaders(auth),
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  const parsed = await readJsonObject(response);
  throwIfNotOk(response, parsed);
  if (!Number.isInteger(parsed.governance_generation) ||
      !["unreviewed", "draft", "approved", "superseded"].includes(String(parsed.authority_status))) {
    throw new Error("Invalid document governance response");
  }
  return parsed as DocumentGovernance;
}

/** Bounded version metadata for explicit approval and replacement management. */
export async function governanceVersions(auth: ApiAuth, documentId: string): Promise<DocumentGovernance[]> {
  const response = await fetch(apiUrl(`/documents/${encodeURIComponent(documentId)}/governance/versions`), { headers: resumeHeaders(auth) });
  if (!response.ok) throwIfNotOk(response, await readJsonObject(response));
  const data: unknown = await response.json();
  if (!Array.isArray(data)) throw new Error("Invalid version response");
  return data as DocumentGovernance[];
}

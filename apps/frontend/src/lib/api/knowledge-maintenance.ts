/** Owner/admin review queue. The server rechecks consent and source access. */
import type { ApiAuth } from "./headers";
import { adminMutationHeaders, resumeHeaders } from "./headers";
import { apiUrl, readJsonObject } from "./http";
import { throwIfNotOk } from "./errors";

export type MaintenanceKind = "missing_owner" | "overdue_review" | "feedback" | "insufficient_evidence" | "conflicting_evidence";
export type MaintenanceItem = {
  kind: MaintenanceKind;
  source_id: string;
  document_id: string | null;
  run_id: string | null;
  title: string | null;
  report: Record<string, string | null>;
  status: "open" | "resolved" | "dismissed";
  assigned_to: string | null;
  reason: string | null;
  revision: number;
};
export type MaintenanceUpdate = Pick<MaintenanceItem, "status" | "assigned_to" | "reason"> & { expected_revision: number };

/** Read a bounded queue page; errors are never displayed as an empty queue. */
export async function listMaintenance(auth: ApiAuth, offset = 0): Promise<MaintenanceItem[]> {
  const response = await fetch(apiUrl(`/admin/knowledge/maintenance?limit=50&offset=${offset}`), { headers: resumeHeaders(auth) });
  if (!response.ok) throwIfNotOk(response, await readJsonObject(response));
  const data: unknown = await response.json();
  if (!Array.isArray(data)) throw new Error("Invalid maintenance response");
  return data as MaintenanceItem[];
}

/** Persist a human assignment or reasoned resolution, never source edits. */
export async function updateMaintenance(auth: ApiAuth, item: MaintenanceItem, body: MaintenanceUpdate) {
  const response = await fetch(apiUrl(`/admin/knowledge/maintenance/${item.kind}/${encodeURIComponent(item.source_id)}`), {
    method: "PATCH", headers: adminMutationHeaders(auth), body: JSON.stringify(body),
  });
  if (!response.ok) throwIfNotOk(response, await readJsonObject(response));
}

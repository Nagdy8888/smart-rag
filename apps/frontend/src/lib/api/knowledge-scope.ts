/** Saved selection is creator-private and snapshotted by the server at admission. */
import type { ApiAuth } from "./headers";
import { adminMutationHeaders, resumeHeaders } from "./headers";
import { apiUrl, readJsonObject } from "./http";
import { throwIfNotOk } from "./errors";

export type KnowledgeScope = { document_id: string | null; title: string | null; unavailable: boolean; enabled: boolean };

/** Omit `documentId` to read; pass null to explicitly clear the selection. */
export async function knowledgeScope(auth: ApiAuth, conversationId: string, documentId?: string | null): Promise<KnowledgeScope> {
  const update = documentId !== undefined;
  const response = await fetch(apiUrl(`/conversations/${encodeURIComponent(conversationId)}/knowledge-scope`), {
    method: update ? "PATCH" : "GET", headers: update ? adminMutationHeaders(auth) : resumeHeaders(auth),
    ...(update ? { body: JSON.stringify({ document_id: documentId }) } : {}),
  });
  const body = await readJsonObject(response);
  throwIfNotOk(response, body);
  return body as KnowledgeScope;
}

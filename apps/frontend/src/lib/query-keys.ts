/**
 * TanStack Query keys. Session-bearing keys include the access token so a
 * sign-out does not reuse another caller's cache. UI role is never a key.
 */

/**
 * Public handshake and readiness keys (no Bearer).
 */
export const publicQueryKeys = {
  meta: ["meta"] as const,
  ready: ["health-ready"] as const,
};

/**
 * Build session-aware FastAPI query keys.
 *
 * @param accessToken - Bearer JWT, or null when signed out.
 * @returns Key factories. Empty token disables the matching queries.
 */
export function sessionQueryKeys(accessToken: string | null) {
  return {
    me: ["me", accessToken] as const,
    conversations: ["conversations", accessToken] as const,
    documents: ["documents", accessToken] as const,
    usage: ["usage", accessToken] as const,
    versionStatus: (versionId: string | null) =>
      ["version-status", accessToken, versionId] as const,
    citations: (runId: string | null) => ["citations", accessToken, runId] as const,
    document: (documentId: string | null) =>
      ["document", accessToken, documentId] as const,
    tables: ["tables", accessToken] as const,
    graphSearch: (query: string) => ["graph-search", accessToken, query] as const,
  };
}

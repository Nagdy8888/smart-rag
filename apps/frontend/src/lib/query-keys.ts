/**
 * TanStack Query keys. Session-bearing keys use Auth `sub` (user id) so a
 * sign-out does not reuse another caller's cache. The raw Bearer JWT is
 * never a query key; it stays on fetch `Authorization` headers only. UI
 * role is never a key.
 */

/**
 * Public handshake and readiness keys (no Bearer).
 */
export const publicQueryKeys = {
  meta: ["meta"] as const,
  ready: ["health-ready"] as const,
};

/**
 * Decode the JWT payload without verifying the signature.
 *
 * Used only to read `sub` for cache isolation. Authorization still uses
 * the Bearer header on each fetch.
 *
 * @param accessToken - Compact JWT, or null when signed out.
 * @returns Payload object, or null when the token is missing or malformed.
 */
export function decodeJwtPayload(
  accessToken: string | null,
): Record<string, unknown> | null {
  if (accessToken === null || accessToken === "") {
    return null;
  }
  const parts = accessToken.split(".");
  if (parts.length < 2) {
    return null;
  }
  const encoded = parts[1];
  if (encoded === undefined || encoded === "") {
    return null;
  }
  try {
    const padded = encoded.replace(/-/g, "+").replace(/_/g, "/");
    const pad =
      padded.length % 4 === 0 ? "" : "=".repeat(4 - (padded.length % 4));
    const json = globalThis.atob(`${padded}${pad}`);
    const parsed: unknown = JSON.parse(json);
    if (parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
  } catch {
    return null;
  }
  return null;
}

/**
 * Return the TanStack Query session scope for a Bearer token.
 *
 * @param accessToken - Bearer JWT, or null when signed out.
 * @returns Auth `sub` when present; `"invalid"` for a malformed token;
 *   `null` when signed out. Never returns the raw JWT.
 */
export function sessionCacheScope(accessToken: string | null): string | null {
  if (accessToken === null || accessToken === "") {
    return null;
  }
  const payload = decodeJwtPayload(accessToken);
  const sub = payload?.sub;
  if (typeof sub === "string" && sub !== "") {
    return sub;
  }
  return "invalid";
}

/**
 * Build session-aware FastAPI query keys.
 *
 * @param accessToken - Bearer JWT, or null when signed out. Only `sub` is
 *   stored in keys; the token itself is not.
 * @returns Key factories. Empty token disables the matching queries.
 */
export function sessionQueryKeys(accessToken: string | null) {
  const scope = sessionCacheScope(accessToken);
  return {
    me: ["me", scope] as const,
    conversations: ["conversations", scope] as const,
    documents: ["documents", scope] as const,
    usage: ["usage", scope] as const,
    versionStatus: (versionId: string | null) =>
      ["version-status", scope, versionId] as const,
    conversationMessages: (conversationId: string | null) =>
      ["conversation-messages", scope, conversationId] as const,
    citations: (runId: string | null) => ["citations", scope, runId] as const,
    document: (documentId: string | null) =>
      ["document", scope, documentId] as const,
    tables: ["tables", scope] as const,
    graphSearch: (query: string) => ["graph-search", scope, query] as const,
    tools: (query = "") => ["tools", scope, query] as const,
    entityRules: ["entity-rules", scope] as const,
    usageCompany: ["usage-company", scope] as const,
    workspaceUsers: ["workspace-users", scope] as const,
    pdfEvalStatus: ["pdf-eval-status", scope] as const,
    pdfEvalCases: ["pdf-eval-cases", scope] as const,
    pdfEvalCaseList: (split: string, review: string) =>
      ["pdf-eval-cases", scope, split, review] as const,
    pdfEvalAskCases: ["pdf-eval-ask-cases", scope] as const,
    pdfEvalCase: (caseId: string | null) =>
      ["pdf-eval-case", scope, caseId] as const,
    pdfEvalPassages: (documentId: string | null) =>
      ["pdf-eval-passages", scope, documentId] as const,
    pdfEvalLatestReport: (split: string) =>
      ["pdf-eval-latest-report", scope, split] as const,
    pdfEvalExam: (examRunId: string | null) =>
      ["pdf-eval-exam", scope, examRunId] as const,
    pdfEvalExamCases: (examRunId: string | null) =>
      ["pdf-eval-exam-cases", scope, examRunId] as const,
    consoleReady: (role: string | null) =>
      ["console-ready", scope, role ?? "pending"] as const,
  };
}

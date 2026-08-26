/**
 * Invitation accept/create and user offboard HTTP helpers.
 */

import type {
  AcceptInvitationResponse,
  CreateInvitationRequest,
  CreateInvitationResponse,
  OffboardResponse,
} from "../types";
import { buildInvitationCreateBody } from "../admin-bodies";
import { throwClassifiedAdminError } from "./admin-errors";
import { classifyApiError, sanitizedDetail } from "./errors";
import type { ApiAuth } from "./headers";
import { adminMutationHeaders, resumeHeaders } from "./headers";
import { apiUrl, readJsonObject } from "./http";

/**
 * Accept a single-use invitation. Body is `{ token }` only. Email comes from
 * the verified JWT on the server, not this payload.
 *
 * @param auth - Access token.
 * @param token - Raw invitation secret.
 * @param fetchImpl - Injected fetch.
 * @returns Accepted invitation id.
 * @throws Error when FastAPI rejects the call.
 */
export async function acceptInvitation(
  auth: ApiAuth,
  token: string,
  fetchImpl: typeof fetch = fetch,
): Promise<AcceptInvitationResponse> {
  const response = await fetchImpl(apiUrl("/invitations/accept"), {
    method: "POST",
    headers: {
      ...resumeHeaders(auth),
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ token }),
  });
  const body = await readJsonObject(response);
  if (!response.ok) {
    const classified = classifyApiError(response.status, body, response.headers);
    if (classified?.kind === "auth" && classified.detail === "session_revoked") {
      throw new Error("session_revoked");
    }
    throw new Error(sanitizedDetail(body, "invitation_rejected"));
  }
  return { invitation_id: String(body.invitation_id ?? "") };
}

/**
 * Create a 24-hour invitation. Owner/admin on the server.
 *
 * Body is `{ email, role, upload_enabled }` only. The one-time token is
 * mail-only; JSON never includes `raw_token`. Production never sends
 * `X-Test-*` or a role header.
 *
 * @param auth - Access token.
 * @param input - Invitee email, role, and upload flag.
 * @param fetchImpl - Injected fetch.
 * @returns Invitation identifiers without the mail token.
 * @throws Error `forbidden`, `budget_exhausted`, or `rate_limited`.
 */
export async function createInvitation(
  auth: ApiAuth,
  input: CreateInvitationRequest,
  fetchImpl: typeof fetch = fetch,
): Promise<CreateInvitationResponse> {
  const payload = buildInvitationCreateBody(input);
  const response = await fetchImpl(apiUrl("/admin/invitations"), {
    method: "POST",
    headers: adminMutationHeaders(auth),
    body: JSON.stringify(payload),
  });
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  return {
    invitation_id: String(body.invitation_id ?? ""),
    email: String(body.email ?? ""),
    role: String(body.role ?? ""),
    upload_enabled: Boolean(body.upload_enabled),
    expires_at: String(body.expires_at ?? ""),
  };
}

/**
 * Offboard one subject. Owner/admin AAL2 on the server.
 *
 * @param auth - Access token. No role header.
 * @param userId - Subject user UUID from `GET /me` (no member directory).
 * @param fetchImpl - Injected fetch.
 * @returns Completed identifiers.
 * @throws Error `forbidden` on 403.
 */
export async function offboardUser(
  auth: ApiAuth,
  userId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<OffboardResponse> {
  const response = await fetchImpl(apiUrl(`/admin/users/${userId}/offboard`), {
    method: "POST",
    headers: adminMutationHeaders(auth),
  });
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  return {
    request_id: String(body.request_id ?? ""),
    subject_user_id: String(body.subject_user_id ?? ""),
    completed_at: String(body.completed_at ?? ""),
  };
}

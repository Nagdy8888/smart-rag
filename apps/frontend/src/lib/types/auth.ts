/**
 * Auth, invitation, and current-user OpenAPI types.
 *
 * Field names match `docs/api/openapi.foundation.json`.
 */

/** `GET /api/meta` handshake body. */
export type MetaResponse = {
  api_version: string;
  sse_schema_version: string;
  min_client_version: string;
};

/** `POST /invitations/accept` response. Email is not a request field. */
export type AcceptInvitationResponse = {
  invitation_id: string;
};

/** `GET /me` server-derived identity. */
export type CurrentUserResponse = {
  user_id: string;
  role: string;
  authorization_version: number;
  upload_enabled: boolean;
};

export const INVITE_ROLES = ["owner", "admin", "member", "viewer"] as const;

export type InviteRole = (typeof INVITE_ROLES)[number];

/** `POST /admin/invitations` body. Extra fields are forbidden. */
export type CreateInvitationRequest = {
  email: string;
  role: InviteRole;
  upload_enabled: boolean;
};

/** Invitation identifiers. The one-time token is mail-only, not JSON. */
export type CreateInvitationResponse = {
  invitation_id: string;
  email: string;
  role: string;
  upload_enabled: boolean;
  expires_at: string;
};

/** `POST /admin/users/{user_id}/offboard` identifiers. */
export type OffboardResponse = {
  request_id: string;
  subject_user_id: string;
  completed_at: string;
};

/**
 * Extra-forbid invitation and tool catalog POST bodies.
 */

import {
  INVITE_ROLES,
  TOOL_PERMISSIONS,
  type CreateInvitationRequest,
  type InviteRole,
  type ToolPermission,
  type ToolPermissionRequest,
  type ToolSeedRequest,
} from "../types";

/**
 * Return whether a role is an invitation target.
 *
 * @param value - Candidate role.
 * @returns True for owner|admin|member|viewer.
 */
export function isInviteRole(value: string): value is InviteRole {
  return (INVITE_ROLES as readonly string[]).includes(value);
}

/**
 * Build `{ email, role, upload_enabled }` only.
 *
 * @param input - Invite form values. Extra keys such as `sql` are dropped.
 * @returns Create-invitation body.
 */
export function buildInvitationCreateBody(
  input: CreateInvitationRequest & Record<string, unknown>,
): CreateInvitationRequest {
  const role = isInviteRole(String(input.role)) ? input.role : "viewer";
  const uploadEnabled = role === "viewer" ? false : Boolean(input.upload_enabled);
  return {
    email: String(input.email ?? ""),
    role,
    upload_enabled: uploadEnabled,
  };
}

/**
 * Build tool seed `{ tool_key, display_name, description?, active? }`.
 *
 * @param input - Seed form. Extra keys are dropped.
 * @returns Seed body.
 */
export function buildToolSeedBody(
  input: ToolSeedRequest & Record<string, unknown>,
): ToolSeedRequest {
  const body: ToolSeedRequest = {
    tool_key: String(input.tool_key ?? ""),
    display_name: String(input.display_name ?? ""),
  };
  if (typeof input.description === "string" && input.description.length > 0) {
    body.description = input.description;
  }
  if (typeof input.active === "boolean") {
    body.active = input.active;
  }
  return body;
}

/**
 * Build `{ active }` for enable/disable.
 *
 * @param active - Desired catalog flag.
 * @returns Enable body.
 */
export function buildToolEnableBody(active: boolean): { active: boolean } {
  return { active };
}

/**
 * Build `{ target_role, permission }` only.
 *
 * @param input - Permission form. Extra keys are dropped.
 * @returns Permission body.
 */
export function buildToolPermissionBody(
  input: ToolPermissionRequest & Record<string, unknown>,
): ToolPermissionRequest {
  const targetRole = isInviteRole(String(input.target_role))
    ? input.target_role
    : "viewer";
  const permission = (TOOL_PERMISSIONS as readonly string[]).includes(
    String(input.permission),
  )
    ? (input.permission as ToolPermission)
    : "none";
  return { target_role: targetRole, permission };
}

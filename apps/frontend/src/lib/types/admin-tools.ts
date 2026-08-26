/**
 * Admin tool-card OpenAPI types.
 *
 * Field names match `docs/api/openapi.foundation.json`.
 */

import type { InviteRole } from "./auth";

export type ToolCardResponse = {
  tool_key: string;
  version_label: string;
  short_name: string;
  purpose: string;
  required_role: string;
  risk_class: string;
  active: boolean;
};

/** `POST /admin/tools` seed. Extra fields are forbidden. */
export type ToolSeedRequest = {
  tool_key: string;
  display_name: string;
  description?: string;
  active?: boolean;
};

/** Tool permission levels from `set_tool_permission`. */
export const TOOL_PERMISSIONS = ["none", "read", "execute", "admin"] as const;

export type ToolPermission = (typeof TOOL_PERMISSIONS)[number];

/** `POST /admin/tools/{tool_key}/permissions` body. */
export type ToolPermissionRequest = {
  target_role: InviteRole;
  permission: ToolPermission;
};

/** Admin tool/glossary/entity-rule mutation id payload. */
export type ToolMutationResponse = {
  id: string;
};

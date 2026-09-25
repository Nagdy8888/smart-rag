/**
 * Honest administration copy. Gaps have no HTTP; do not invent events.
 */

import { OWNER_BOOTSTRAP_UNAVAILABLE } from "./auth/copy";

/** Offboarding cannot be undone from this UI. */
export const OFFBOARD_IRREVERSIBLE_COPY =
  "Offboarding cannot be undone from this console. The person is disabled and their sessions end.";

/** Team listing is owner/admin only. */
export const WORKSPACE_PEOPLE_COPY =
  "People who already have a workspace account, plus invitations that have not been accepted yet.";

/** Frame 14 budget editor / critical-reserve sliders. GAP-07-11 has no HTTP. */
export const BUDGET_EDITOR_UNAVAILABLE =
  "Budget policy and graph-maintenance reserve editors are not available. Spend limits are enforced by the server; this page does not include sliders.";

/** Static 402 copy for the usage hierarchy. Not a fake budget remaining. */
export const BUDGET_EXHAUSTED_COPY =
  "When the workspace budget is exhausted, new questions and uploads pause until capacity is restored.";

/** Rate-limit copy. Live 429 still uses `apiFailureBanner`. */
export const RATE_LIMIT_COPY =
  "If the service is busy, wait a moment and retry. A degraded rate limiter is shown as a warning, not as a healthy status.";

/** GAP-07-12 has no list/export HTTP. Do not invent events or leak passages. */
export const AUDIT_HISTORY_UNAVAILABLE =
  "Restricted read, preview, and download history is not available. This page does not invent audit events or show private passages.";

/** GAP-07-13 has no company-settings CRUD. */
export const COMPANY_SETTINGS_UNAVAILABLE =
  "Company settings cannot be edited here. There is no save control on this page.";

/** GAP-07-19: `GET /me` has no name or locale fields. */
export const PROFILE_EDITOR_UNAVAILABLE =
  "Name and language cannot be edited here. This profile shows the signed-in account fields only.";

/** Invitation create JSON never includes the one-time token. */
export const INVITE_TOKEN_MAIL_ONLY =
  "The invitation token is delivered by mail only. It is not in this JSON response.";

/** Re-export GAP-07-08 copy for the team surface. */
export const TEAM_OWNER_BOOTSTRAP_UNAVAILABLE = OWNER_BOOTSTRAP_UNAVAILABLE;

/** Server denial when a hidden control is still invoked. */
export const FORBIDDEN_MUTATION_COPY =
  "You don’t have permission to do this.";

/** Optimistic concurrency conflict on entity-rule approve/revoke. */
export const STALE_ROW_VERSION_COPY =
  "This rule changed since you loaded it. Reload the list and try again.";

/**
 * Title-case a stored invite role for chrome. Unknown values stay as text.
 *
 * @param role - Server role string.
 * @returns Display label.
 */
export function inviteRoleLabel(role: string): string {
  switch (role) {
    case "owner":
      return "Owner";
    case "admin":
      return "Admin";
    case "member":
      return "Member";
    case "viewer":
      return "Viewer";
    default:
      return role;
  }
}

/**
 * Title-case a stored tool permission for chrome.
 *
 * @param permission - Server permission string.
 * @returns Display label.
 */
export function toolPermissionLabel(permission: string): string {
  switch (permission) {
    case "none":
      return "None";
    case "read":
      return "Read";
    case "execute":
      return "Execute";
    case "admin":
      return "Admin";
    default:
      return permission;
  }
}

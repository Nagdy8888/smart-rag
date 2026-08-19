/**
 * Honest administration copy. Gaps have no HTTP; do not invent events.
 */

import { OWNER_BOOTSTRAP_UNAVAILABLE } from "./auth/copy";

/** No member-list HTTP. Identify users from `GET /me` and audit when available. */
export const NO_MEMBER_DIRECTORY_COPY =
  "No member directory API; identify users from GET /me and audit when available";

/** Offboarding cannot be undone from this UI. */
export const OFFBOARD_IRREVERSIBLE_COPY =
  "Offboarding is irreversible. The subject is disabled and sessions are revoked. There is no undo HTTP.";

/** Frame 14 budget editor / critical-reserve sliders. GAP-07-11 has no HTTP. */
export const BUDGET_EDITOR_UNAVAILABLE =
  "Budget policy and graph-maintenance reserve editors are unavailable (GAP-07-11). There is no /budgets HTTP. FastAPI returns 402 budget_exhausted when spend is exhausted. This page does not ship sliders.";

/** Static 402 copy for the usage hierarchy. Not a fake budget remaining. */
export const BUDGET_EXHAUSTED_COPY =
  "When the durable budget is exhausted, FastAPI returns 402 budget_exhausted. Ordinary chat and ingestion pause. The graph-maintenance reserve is not consumable here.";

/** Rate-limit copy. Live 429 still uses `apiFailureBanner`. */
export const RATE_LIMIT_COPY =
  "FastAPI returns 429 rate_limited or concurrency_limit with Retry-After. GET /health/ready.rate_limit_degraded is informational degradation, not a fake healthy limiter.";

/** GAP-07-12 has no list/export HTTP. Do not invent events or leak passages. */
export const AUDIT_HISTORY_UNAVAILABLE =
  "Restricted read, preview, and download audit history is unavailable (GAP-07-12). There is no audit list or export HTTP. This page does not invent events or show passages.";

/** GAP-07-13 has no company-settings CRUD. */
export const COMPANY_SETTINGS_UNAVAILABLE =
  "Company settings CRUD is unavailable (GAP-07-13). app.company_settings has no public read or write API. This page has no save control.";

/** GAP-07-19: `GET /me` has no name or locale fields. */
export const PROFILE_EDITOR_UNAVAILABLE =
  "Name and locale editors are unavailable (GAP-07-19). GET /me returns five fields only: user_id, role, authorization_version, upload_enabled, mfa_enrolled.";

/** Invitation create JSON never includes the one-time token. */
export const INVITE_TOKEN_MAIL_ONLY =
  "The invitation token is delivered by mail only. It is not in this JSON response.";

/** Re-export GAP-07-08 copy for the team surface. */
export const TEAM_OWNER_BOOTSTRAP_UNAVAILABLE = OWNER_BOOTSTRAP_UNAVAILABLE;

/** Server denial when a hidden control is still invoked. */
export const FORBIDDEN_MUTATION_COPY =
  "Server denied this request (forbidden). UI hiding is convenience only.";

/** Optimistic concurrency conflict on entity-rule approve/revoke. */
export const STALE_ROW_VERSION_COPY =
  "Entity rule update conflict (stale_row_version). Reload the list and retry with the current row_version.";

/**
 * Generic Auth chrome. Never include provider traces or FastAPI limiter claims
 * on browser-direct sign-in (GAP-07-20).
 */

/** Password/OAuth/callback failures shown to the user. */
export const SIGN_IN_FAILED = "Sign in failed";

/** Replayed or missing PKCE `code` after `/auth/callback`. */
export const CALLBACK_FAILED = "Sign-in could not be completed";

/** FastAPI 403 `MFA required` for privileged callers. */
export const MFA_REQUIRED_BANNER =
  "MFA required. Owner, admin, and upload_enabled callers need a verified TOTP session (aal2). Password JWTs stay aal1 until challenge/verify.";

/** Upload 403 MFA. No fake TOTP success. */
export const MFA_UPLOAD_DENIED =
  "MFA required. Verify TOTP so the JWT is aal2, then retry the upload.";

/** 401 `session_revoked`. */
export const SESSION_REVOKED_BANNER =
  "Session rejected (session_revoked). Sign in again. UI state is not authorization.";

/** GAP-07-07 honest copy. No recovery-code HTTP. */
export const MFA_RECOVERY_UNAVAILABLE =
  "Lost-factor MFA recovery is not available. Contact an administrator if you cannot complete authenticator verification.";

/** GAP-07-08 honest copy. No bootstrap wizard. */
export const OWNER_BOOTSTRAP_UNAVAILABLE =
  "Owner bootstrap is not available. Sign in with an invited account, then accept the invitation.";

/** Disabled Google control (GAP-07-04). */
export const GOOGLE_OAUTH_BUTTON_LABEL = "Continue with Google (when enabled)";

/** Helper under the disabled Google button. */
export const GOOGLE_OAUTH_HELPER =
  "Google sign-in is not enabled for this workspace.";

/** Sign-up success. Membership is FastAPI invitation, not a fake dashboard. */
export const SIGN_UP_SUCCESS =
  "Account created. Confirmation may be required. FastAPI membership still needs an accepted invitation. Continue to sign in or invitation accept.";

/** Forgot-password check-inbox copy. Does not reveal whether the email exists. */
export const RESET_EMAIL_SENT =
  "If that address can receive mail, check the inbox for a reset link.";

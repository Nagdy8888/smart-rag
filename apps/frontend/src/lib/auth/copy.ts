/**
 * Generic Auth chrome. Never include provider traces or FastAPI limiter claims
 * on browser-direct sign-in (GAP-07-20).
 */

/** Password/OAuth/callback failures shown to the user. */
export const SIGN_IN_FAILED = "Sign in failed";

/** Replayed or missing PKCE `code` after `/auth/callback`. */
export const CALLBACK_FAILED = "Sign-in could not be completed";

/** 401 `session_revoked`. */
export const SESSION_REVOKED_BANNER =
  "You were signed out. Sign in again.";

/** GAP-07-08 honest copy. No bootstrap wizard. */
export const OWNER_BOOTSTRAP_UNAVAILABLE =
  "Owner bootstrap is not available. Sign in with an invited account, then accept the invitation.";

/** Sign-up success. Membership is FastAPI invitation, not a fake dashboard. */
export const SIGN_UP_SUCCESS =
  "Account created. Confirmation may be required. FastAPI membership still needs an accepted invitation. Continue to sign in or invitation accept.";

/** Forgot-password check-inbox copy. Does not reveal whether the email exists. */
export const RESET_EMAIL_SENT =
  "If that address can receive mail, check the inbox for a reset link.";

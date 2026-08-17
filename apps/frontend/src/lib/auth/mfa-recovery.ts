/**
 * MFA lost-factor recovery is GAP-07-07: `mfa_recovery.py` has no router.
 * Hidden chrome must not invent HTTP.
 */

/** There is no recovery HTTP in this phase. */
export const MFA_RECOVERY_HTTP_ENABLED = false as const;

/**
 * Return a recovery endpoint if one existed.
 *
 * @returns Always `null`. Do not POST recovery codes.
 * @remarks
 * Side effects: none. A visible Unavailable banner is not an HTTP client.
 */
export function mfaRecoveryRequestUrl(): null {
  return null;
}

/**
 * Return whether a recovery-code form may submit.
 *
 * @returns Always `false`.
 */
export function mfaRecoveryFormMaySubmit(): false {
  return false;
}

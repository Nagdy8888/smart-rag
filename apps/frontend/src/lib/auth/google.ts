/**
 * Google OAuth is Auth-direct. Local `supabase/config.toml` has
 * `[auth.external.google] enabled=false` (GAP-07-04).
 */

/** Local and v1 default: do not call `signInWithOAuth`. */
export const GOOGLE_OAUTH_ENABLED = false;

/**
 * Return whether the Google button may invoke Auth OAuth.
 *
 * @param enabled - Provider flag. False in this repository.
 * @returns True only when the provider is enabled.
 * @remarks
 * Side effects: none. Callers must not invoke `signInWithOAuth` when this
 * returns false.
 */
export function shouldInvokeGoogleOAuth(enabled: boolean): boolean {
  return enabled === true;
}

/**
 * Guard around `signInWithOAuth`. Used by tests to prove the disabled button
 * never reaches Auth.
 *
 * @param enabled - Provider flag.
 * @param signInWithOAuth - Injected Auth method. Must not run when disabled.
 * @returns Auth result when enabled; `{ invoked: false }` otherwise.
 */
export async function maybeSignInWithGoogle(
  enabled: boolean,
  signInWithOAuth: () => Promise<unknown>,
): Promise<{ invoked: boolean; result?: unknown }> {
  if (!shouldInvokeGoogleOAuth(enabled)) {
    return { invoked: false };
  }
  const result = await signInWithOAuth();
  return { invoked: true, result };
}

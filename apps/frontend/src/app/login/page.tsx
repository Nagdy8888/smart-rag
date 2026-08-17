/**
 * Canonical sign-in URL. Unauthenticated `/` redirects here via proxy.
 */

import { SignInForm } from "../../components/auth/auth-screens";

/**
 * Render the email/password sign-in surface.
 *
 * @param props - Next.js search params. `error=callback` is generic failure.
 * @returns Sign-in form.
 */
export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string | string[] }>;
}) {
  const params = await searchParams;
  const error = params.error;
  const callbackError = Array.isArray(error)
    ? error.includes("callback")
    : error === "callback";
  return <SignInForm callbackError={callbackError} />;
}

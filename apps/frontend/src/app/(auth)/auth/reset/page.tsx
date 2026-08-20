import { ResetPasswordForm } from "../../../../components/auth/auth-screens";

/**
 * Render recovery update-password after PKCE callback `next=/auth/reset`.
 *
 * @returns Reset form.
 */
export default function ResetPasswordPage() {
  return <ResetPasswordForm />;
}

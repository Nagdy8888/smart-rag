import { MfaChallengeForm } from "../../../../components/auth/auth-screens";

/**
 * Render TOTP challenge plus the MFA-required banner.
 *
 * @returns Challenge form.
 */
export default function MfaChallengePage() {
  return <MfaChallengeForm />;
}

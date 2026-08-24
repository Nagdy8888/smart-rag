/**
 * Supported Account destination. Reuses the existing read-only `/me` profile app.
 */
import { ProfileApp } from "../../../components/profile-app";

/**
 * Render Account details. No MFA, name, or locale editor.
 *
 * @returns Profile surface.
 */
export default function AccountPage() {
  return <ProfileApp />;
}

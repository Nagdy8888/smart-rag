/**
 * Supported Account destination. Read-only `/me` fields.
 */
import { AccountPanel } from "../../../components/admin/account-panel";

/**
 * Render Account details. No name or locale editor.
 *
 * @returns Account surface.
 */
export default function AccountPage() {
  return <AccountPanel />;
}

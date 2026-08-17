import { InvitationAcceptForm } from "../../../components/auth/auth-screens";

/**
 * Render authenticated invitation accept. Body is `{ token }` only.
 *
 * @returns Accept form. Team create/offboard is packet 4.
 */
export default function InvitationAcceptPage() {
  return <InvitationAcceptForm />;
}

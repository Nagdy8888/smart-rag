/**
 * Read-only Account details from `GET /me`. No name, locale, or company editor.
 */

"use client";

import { PageHeader } from "../ui/page-header";
import { Spinner } from "../ui/spinner";
import { CodeText, UserText } from "../ui/user-text";
import { inviteRoleLabel } from "../../lib/admin-copy";
import { useCurrentUser } from "../../lib/hooks/use-current-user";
import shellStyles from "./admin-shell.module.css";
import tableStyles from "./admin-tables.module.css";

const styles = { ...shellStyles, ...tableStyles };

/**
 * Show the signed-in `/me` fields.
 *
 * @returns Account page. Sign out stays in the shell menu.
 */
export function AccountPanel() {
  const { currentUser, currentUserPending } = useCurrentUser();
  const me = currentUser;

  return (
    <div className={styles.page}>
      <PageHeader description="Signed-in identity for this workspace." />
      {currentUserPending ? <Spinner label="Loading account" /> : null}
      <section className={styles.panel} aria-label="Current user" data-testid="profile-fields">
        <dl className={styles.dl}>
          <dt>User ID</dt>
          <dd>
            <CodeText value={me?.user_id ?? ""} />
          </dd>
          <dt>Role</dt>
          <dd>
            <UserText value={me ? inviteRoleLabel(me.role) : ""} />
          </dd>
          <dt>Authorization version</dt>
          <dd>
            <UserText value={me ? String(me.authorization_version) : ""} />
          </dd>
          <dt>Upload access</dt>
          <dd>
            <UserText value={me ? (me.upload_enabled ? "Enabled" : "Disabled") : ""} />
          </dd>
        </dl>
      </section>
    </div>
  );
}

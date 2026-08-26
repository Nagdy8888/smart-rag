/**
 * Read-only Account details from `GET /me`. No name, locale, or company editor.
 */

"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { PageHeader } from "../ui/page-header";
import { CodeText, UserText } from "../ui/user-text";
import { fetchMe, type ApiAuth } from "../../lib/api";
import { useSession } from "../../lib/auth/session-provider";
import { sessionQueryKeys } from "../../lib/query-keys";
import shellStyles from "./admin-shell.module.css";
import tableStyles from "./admin-tables.module.css";

const styles = { ...shellStyles, ...tableStyles };

/**
 * Show the signed-in `/me` fields.
 *
 * @returns Account page. Sign out stays in the shell menu.
 */
export function AccountPanel() {
  const session = useSession();
  const accessToken = session.accessToken;
  const auth = useMemo<ApiAuth | null>(
    () => (accessToken ? { accessToken } : null),
    [accessToken],
  );
  const keys = sessionQueryKeys(accessToken);
  const meQuery = useQuery({
    queryKey: keys.me,
    queryFn: () => fetchMe(auth as ApiAuth),
    enabled: auth !== null,
  });
  const me = meQuery.data;

  return (
    <div className={styles.page}>
      <PageHeader description="Signed-in identity for this workspace." />
      <section className={styles.panel} aria-label="Current user" data-testid="profile-fields">
        <dl className={styles.dl}>
          <dt>user_id</dt>
          <dd>
            <CodeText value={me?.user_id ?? ""} />
          </dd>
          <dt>role</dt>
          <dd>
            <UserText value={me?.role ?? ""} />
          </dd>
          <dt>authorization_version</dt>
          <dd>
            <UserText value={String(me?.authorization_version ?? "")} />
          </dd>
          <dt>upload_enabled</dt>
          <dd>
            <UserText value={String(me?.upload_enabled ?? "")} />
          </dd>
        </dl>
      </section>
    </div>
  );
}

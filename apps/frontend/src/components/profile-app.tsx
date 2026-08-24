/**
 * Read-only `GET /me` profile. No name/locale editor. No company-settings save.
 */

"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { HandshakeBanner } from "./auth/auth-screens";
import { LimitationCallout } from "./ui/limitation-callout";
import { CodeText, UserText } from "./ui/user-text";
import { fetchMe, type ApiAuth } from "../lib/api";
import {
  COMPANY_SETTINGS_UNAVAILABLE,
  PROFILE_EDITOR_UNAVAILABLE,
} from "../lib/admin-copy";
import { useSession } from "../lib/auth/session-provider";
import { sessionQueryKeys } from "../lib/query-keys";
import styles from "./admin/admin.module.css";

/**
 * Show the five `/me` fields and honest Unavailable editors.
 *
 * @returns Profile surface.
 */
export function ProfileApp() {
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
    <div className={styles.shell}>
      <header className={styles.row}>
        <h2>Profile</h2>
        <p className={styles.pageLead}>
          Account details for the signed-in user. Name and language cannot be
          edited here.
        </p>
      </header>
      <HandshakeBanner />
      <section className={styles.panel} aria-label="Current user" data-testid="profile-fields">
        <h2>Current user</h2>
        <dl>
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
      <section
        className={styles.panel}
        data-testid="profile-editor-unavailable"
        aria-label="Profile editor"
      >
        <h2>Name and locale</h2>
        <LimitationCallout tone="warning">{PROFILE_EDITOR_UNAVAILABLE}</LimitationCallout>
      </section>
      <section
        className={styles.panel}
        data-testid="company-settings-unavailable"
        aria-label="Company settings"
      >
        <h2>Company settings</h2>
        <LimitationCallout tone="warning">{COMPANY_SETTINGS_UNAVAILABLE}</LimitationCallout>
      </section>
    </div>
  );
}

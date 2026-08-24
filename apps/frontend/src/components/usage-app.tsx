/**
 * Usage meters for `/usage/me` and company totals. No budget sliders.
 */

"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { HandshakeBanner } from "./auth/auth-screens";
import { LimitationCallout } from "./ui/limitation-callout";
import { StatusBanner } from "./ui/status-banner";
import { UserText } from "./ui/user-text";
import {
  fetchMe,
  loadConsoleReadiness,
  fetchUsageCompany,
  fetchUsageMe,
  type ApiAuth,
} from "../lib/api";
import {
  AUDIT_HISTORY_UNAVAILABLE,
  BUDGET_EDITOR_UNAVAILABLE,
  BUDGET_EXHAUSTED_COPY,
  RATE_LIMIT_COPY,
} from "../lib/admin-copy";
import { useSession } from "../lib/auth/session-provider";
import { mutationFailureBanner } from "../lib/failure-copy";
import { publicQueryKeys, sessionQueryKeys } from "../lib/query-keys";
import { showCompanyUsageConvenience } from "../lib/roles";
import type { UsageResponse } from "../lib/types";
import styles from "./admin/admin.module.css";

/**
 * Render usage totals without prompt text.
 *
 * @param props - Usage payload and heading.
 * @returns Meter list.
 */
function UsageMeters({
  title,
  usage,
  testId,
}: {
  title: string;
  usage: UsageResponse | undefined;
  testId: string;
}) {
  return (
    <section className={styles.panel} aria-label={title} data-testid={testId}>
      <h2>{title}</h2>
      <p className={styles.muted}>scope {usage?.scope ?? "—"}</p>
      <div className={styles.metricGrid}>
        <div className={styles.card}>
          <p className={styles.muted}>Cost (USD)</p>
          <p>
            <UserText value={String(usage?.cost_usd ?? "—")} />
          </p>
        </div>
        <div className={styles.card}>
          <p className={styles.muted}>Prompt tokens</p>
          <p>
            <UserText value={String(usage?.prompt_tokens ?? "—")} />
          </p>
        </div>
        <div className={styles.card}>
          <p className={styles.muted}>Completion tokens</p>
          <p>
            <UserText value={String(usage?.completion_tokens ?? "—")} />
          </p>
        </div>
        <div className={styles.card}>
          <p className={styles.muted}>Usage rows</p>
          <p>
            <UserText value={String(usage?.usage_rows ?? "—")} />
          </p>
        </div>
      </div>
    </section>
  );
}

/**
 * Usage, rate degradation, and honest Unavailable budget/audit sections.
 *
 * @returns Usage surface.
 * @remarks
 * GAP-07-11/12 have no HTTP. This page must not ship sliders, fake events,
 * or prompt text.
 */
export function UsageApp() {
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
  const usageQuery = useQuery({
    queryKey: keys.usage,
    queryFn: () => fetchUsageMe(auth as ApiAuth),
    enabled: auth !== null,
  });
  const showCompany = showCompanyUsageConvenience(meQuery.data?.role);
  const companyQuery = useQuery({
    queryKey: keys.usageCompany,
    queryFn: () => fetchUsageCompany(auth as ApiAuth),
    enabled: auth !== null && showCompany,
  });
  const readyQuery = useQuery({
    queryKey: auth === null ? publicQueryKeys.ready : keys.consoleReady,
    queryFn: () => loadConsoleReadiness(auth),
  });

  const companyError =
    companyQuery.error instanceof Error
      ? mutationFailureBanner(companyQuery.error)
      : null;
  const meError =
    usageQuery.error instanceof Error
      ? mutationFailureBanner(usageQuery.error)
      : null;
  const rateDegraded = readyQuery.data?.rate_limit_degraded === true;

  return (
    <div className={styles.shell}>
      <header className={styles.pageHeader}>
        <div>
          <h2>Usage and budgets</h2>
          <p className={styles.pageLead}>
            Token and cost totals for your account. Budget editors are not
            available.
          </p>
        </div>
      </header>
      <HandshakeBanner />
      {meError ? (
        <StatusBanner kind="error" role="alert">
          {meError}
        </StatusBanner>
      ) : null}
      <UsageMeters
        title="Caller usage"
        usage={usageQuery.data}
        testId="usage-meters"
      />
      {showCompany ? (
        <UsageMeters
          title="Company usage"
          usage={companyQuery.data}
          testId="company-usage-meters"
        />
      ) : (
        <p className={styles.muted}>
          Company totals are hidden for this role. The server still denies the
          request.
        </p>
      )}
      {companyError ? (
        <StatusBanner kind="error" role="alert">
          {companyError}
        </StatusBanner>
      ) : null}
      {rateDegraded ? (
        <StatusBanner kind="warning" role="status">
          Rate limiter is degraded. {RATE_LIMIT_COPY}
        </StatusBanner>
      ) : (
        <LimitationCallout tone="neutral">{RATE_LIMIT_COPY}</LimitationCallout>
      )}
      <LimitationCallout tone="warning">{BUDGET_EXHAUSTED_COPY}</LimitationCallout>
      <section
        className={styles.panel}
        data-testid="budget-editor-unavailable"
        aria-label="Budget policies"
      >
        <h2>Budget policies</h2>
        <p className={styles.muted}>
          Policy sliders from the design are not connected. Spend limits stay
          server-enforced.
        </p>
        <LimitationCallout tone="warning">{BUDGET_EDITOR_UNAVAILABLE}</LimitationCallout>
      </section>
      <section
        className={styles.panel}
        data-testid="audit-unavailable"
        aria-label="Restricted audit"
      >
        <h2>Restricted read and download audit</h2>
        <LimitationCallout tone="warning">{AUDIT_HISTORY_UNAVAILABLE}</LimitationCallout>
      </section>
    </div>
  );
}

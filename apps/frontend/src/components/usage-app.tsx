/**
 * Usage meters for `/usage/me` and company totals. No budget sliders.
 */

"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { HandshakeBanner } from "./auth/auth-screens";
import { ReadinessPanel } from "./readiness-panel";
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
import styles from "./developer-app.module.css";

/**
 * Render one usage total row. This is a meter, not a slider.
 *
 * @param props - Field name and value.
 * @returns Read-only row.
 */
function UsageMeterRow({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.meterRow}>
      <span>{label}</span>
      <span className={styles.meterTrack} aria-hidden="true" />
      <UserText value={value} />
    </div>
  );
}

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
      <div className={styles.meterList}>
        <UsageMeterRow label="cost_usd" value={String(usage?.cost_usd ?? "—")} />
        <UsageMeterRow
          label="prompt_tokens"
          value={String(usage?.prompt_tokens ?? "—")}
        />
        <UsageMeterRow
          label="completion_tokens"
          value={String(usage?.completion_tokens ?? "—")}
        />
        <UsageMeterRow
          label="usage_rows"
          value={String(usage?.usage_rows ?? "—")}
        />
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
      <header className={styles.row}>
        <h1>Usage</h1>
        <p className={styles.muted}>
          Token and cost meters from GET /usage. No budget sliders. Totals
          never include prompt text.
        </p>
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
          Company usage is hidden for this role. `fetchUsageCompany` still
          exists and FastAPI still 403s for members and viewers.
        </p>
      )}
      {companyError ? (
        <StatusBanner kind="error" role="alert">
          {companyError}
        </StatusBanner>
      ) : null}
      {rateDegraded ? (
        <StatusBanner kind="warning" role="status">
          Rate limiter is degraded (`ready.rate_limit_degraded`). {RATE_LIMIT_COPY}
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
        <h2>Budget policies and critical reserve</h2>
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
      <ReadinessPanel ready={readyQuery.data} />
    </div>
  );
}

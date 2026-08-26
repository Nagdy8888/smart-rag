/**
 * Real caller and company usage totals. No budget editor, audit, chart, or progress bar.
 */

"use client";

import { useQuery } from "@tanstack/react-query";
import { StatusBanner } from "../ui/status-banner";
import { UserText } from "../ui/user-text";
import { fetchUsageCompany, fetchUsageMe, type ApiAuth } from "../../lib/api";
import { RATE_LIMIT_COPY } from "../../lib/admin-copy";
import { useApiAuth } from "../../lib/auth/use-api-auth";
import { useSession } from "../../lib/auth/session-provider";
import { mutationFailureBanner } from "../../lib/failure-copy";
import { useConsoleReadiness } from "../../lib/hooks/use-console-readiness";
import { useCurrentUser } from "../../lib/hooks/use-current-user";
import { sessionQueryKeys } from "../../lib/query-keys";
import { showCompanyUsageConvenience } from "../../lib/roles";
import type { UsageResponse } from "../../lib/types";
import shellStyles from "./admin-shell.module.css";
import tableStyles from "./admin-tables.module.css";

const styles = { ...shellStyles, ...tableStyles };

/**
 * One usage metric card.
 *
 * @param props - Title, payload, test id.
 * @returns Tokens and USD only.
 */
function UsageCard({
  title,
  usage,
  testId,
}: {
  title: string;
  usage: UsageResponse | undefined;
  testId: string;
}) {
  const tokens =
    usage === undefined
      ? "—"
      : String(usage.prompt_tokens + usage.completion_tokens);
  const usd = usage === undefined ? "—" : String(usage.cost_usd);
  return (
    <section className={styles.metricCard} aria-label={title} data-testid={testId}>
      <h2>{title}</h2>
      <p className={styles.metricLabel}>Tokens</p>
      <p className={styles.metricValue}>
        <UserText value={tokens} />
      </p>
      <p className={styles.metricLabel}>USD</p>
      <p className={styles.metricValue}>
        <UserText value={usd} />
      </p>
    </section>
  );
}

/**
 * Usage tab.
 *
 * @returns At most two metric cards plus a real rate-degradation banner.
 */
export function UsagePanel() {
  const session = useSession();
  const auth = useApiAuth();
  const keys = sessionQueryKeys(session.accessToken);
  const { currentUser } = useCurrentUser();
  const { ready } = useConsoleReadiness();
  const usageQuery = useQuery({
    queryKey: keys.usage,
    queryFn: () => fetchUsageMe(auth as ApiAuth),
    enabled: auth !== null,
  });
  const showCompany = showCompanyUsageConvenience(currentUser?.role);
  const companyQuery = useQuery({
    queryKey: keys.usageCompany,
    queryFn: () => fetchUsageCompany(auth as ApiAuth),
    enabled: auth !== null && showCompany,
  });
  const companyError =
    companyQuery.error instanceof Error
      ? mutationFailureBanner(companyQuery.error)
      : null;
  const meError =
    usageQuery.error instanceof Error
      ? mutationFailureBanner(usageQuery.error)
      : null;
  const rateDegraded = ready?.rate_limit_degraded === true;

  return (
    <div className={styles.stack}>
      {meError ? (
        <StatusBanner kind="error" role="alert">
          {meError}
        </StatusBanner>
      ) : null}
      {companyError ? (
        <StatusBanner kind="error" role="alert">
          {companyError}
        </StatusBanner>
      ) : null}
      <div className={styles.usageRow}>
        <UsageCard title="Your usage" usage={usageQuery.data} testId="usage-meters" />
        {showCompany ? (
          <UsageCard
            title="Company usage"
            usage={companyQuery.data}
            testId="company-usage-meters"
          />
        ) : null}
      </div>
      {rateDegraded ? (
        <StatusBanner kind="warning" role="status">
          Rate limiter is degraded. {RATE_LIMIT_COPY}
        </StatusBanner>
      ) : null}
    </div>
  );
}

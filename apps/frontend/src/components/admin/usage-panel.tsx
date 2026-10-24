/**
 * Caller and company ledger totals with explicit cost-estimate provenance.
 */

"use client";

import { useQuery } from "@tanstack/react-query";
import { Spinner } from "../ui/spinner";
import { StatusBanner } from "../ui/status-banner";
import { Button } from "../ui/button";
import { formatUsd } from "../../lib/format-usage";
import usageStyles from "./usage-panel.module.css";
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

/** Totals from the authorized usage endpoint; no placeholder figures. */
function UsageCard({ title, usage, testId }: {
  title: string;
  usage: UsageResponse | undefined;
  testId: string;
}) {
  const count = (value: number | undefined) => value === undefined ? "\u2014" : new Intl.NumberFormat("en-US").format(value);
  return (
    <section className={usageStyles.card} aria-label={title} data-testid={testId}>
      <header className={usageStyles.cardHeader}>
        <h2>{title}</h2><span>All time</span>
      </header>
      <p className={usageStyles.costLabel}>Recorded cost estimate</p>
      <p className={usageStyles.cost}>{usage ? formatUsd(usage.cost_usd) : "\u2014"}</p>
      <dl className={usageStyles.metrics}>
        <div><dt>Prompt tokens</dt><dd>{count(usage?.prompt_tokens)}</dd></div>
        <div><dt>Completion tokens</dt><dd>{count(usage?.completion_tokens)}</dd></div>
        <div><dt>Usage records</dt><dd>{count(usage?.usage_rows)}</dd></div>
      </dl>
      {usage?.usage_rows === 0 ? <p className={usageStyles.empty}>No model usage has been recorded yet.</p> : null}
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
    refetchInterval: 30_000,
    staleTime: 0,
  });
  const showCompany = showCompanyUsageConvenience(currentUser?.role);
  const companyQuery = useQuery({
    queryKey: keys.usageCompany,
    queryFn: () => fetchUsageCompany(auth as ApiAuth),
    enabled: auth !== null && showCompany,
    refetchInterval: 30_000,
    staleTime: 0,
  });
  const companyError =
    companyQuery.error instanceof Error
      ? mutationFailureBanner(companyQuery.error)
      : null;
  const meError =
    usageQuery.error instanceof Error
      ? mutationFailureBanner(usageQuery.error)
      : null;
  const loadingMe = usageQuery.isPending && usageQuery.data === undefined;
  const loadingCompany =
    showCompany && companyQuery.isPending && companyQuery.data === undefined;
  const rateDegraded = ready?.rate_limit_degraded === true;

  return (
    <div className={styles.stack}>
      <div className={usageStyles.toolbar}>
        <div>
          <h2 className={usageStyles.heading}>Understand your usage</h2>
          <p className={styles.panelLead}>Recorded model usage for this workspace, across all time.</p>
          <p className={usageStyles.updated}>
            {usageQuery.dataUpdatedAt > 0 ? `Updated ${new Date(usageQuery.dataUpdatedAt).toLocaleTimeString()}` : "Waiting for usage data"}
            {usageQuery.isError && usageQuery.data ? " / Last successful snapshot" : " / Refreshes every 30 seconds"}
          </p>
        </div>
        <Button type="button" variant="secondary" pending={usageQuery.isFetching || (showCompany && companyQuery.isFetching)} pendingLabel="Refreshing" onClick={() => {
          void usageQuery.refetch();
          if (showCompany) void companyQuery.refetch();
        }}>Refresh usage</Button>
      </div>
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
      {loadingMe && !meError ? <Spinner label="Loading usage" /> : null}
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
      {loadingCompany ? <Spinner label="Loading company usage" /> : null}
      <aside className={usageStyles.note}>
        <strong>What these numbers mean</strong>
        <p>Tokens and records come from the application usage ledger. Costs are recorded estimates and can include conservative allowances when provider usage is unavailable. They are not a verified provider invoice.</p>
        <p>Usage records are individual model operations, not the number of questions. Prompt text is never shown here.</p>
      </aside>
      {rateDegraded ? (
        <StatusBanner kind="warning" role="status">
          Rate limiter is degraded. {RATE_LIMIT_COPY}
        </StatusBanner>
      ) : null}
    </div>
  );
}

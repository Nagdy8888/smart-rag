/**
 * Caller and company ledger totals with explicit cost-estimate provenance.
 */

"use client";

import { usageDisplayCost } from "../../lib/checkpoint-usage";
import { useQuery } from "@tanstack/react-query";
import { CostReportingDetails } from "./cost-reporting-details";
import { dashboardCost } from "./overview-charts";
import { Spinner } from "../ui/spinner";
import { StatusBanner } from "../ui/status-banner";
import { Button } from "../ui/button";
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
  const cost = usage ? usageDisplayCost(usage) : null;
  const history = usage?.checkpoint_usage;
  return (
    <section className={usageStyles.card} aria-label={title} data-testid={testId}>
      <header className={usageStyles.cardHeader}>
        <h2>{title}</h2><span>All time</span>
      </header>
      <p className={usageStyles.costLabel}>Estimated usage cost</p>
      <p className={usageStyles.cost}>{cost != null ? dashboardCost(cost) : "Not measured"}</p>
      {usage ? <CostReportingDetails report={usage.cost_reporting} /> : null}
      <dl className={usageStyles.metrics}>
        <div><dt>Recorded input tokens</dt><dd>{usage && (history?.runs || usage.cost_reporting?.measured_prompt_tokens != null) ? count(usage.prompt_tokens) : "Not measured"}</dd></div>
        <div><dt>Recorded output tokens</dt><dd>{usage && (history?.runs || usage.cost_reporting?.measured_completion_tokens != null) ? count(usage.completion_tokens) : "Not measured"}</dd></div>
        <div><dt>Usage records</dt><dd>{count(usage?.usage_rows)}</dd></div>
      </dl>
      {usage?.cost_reporting?.unmeasured_operations ? <p className={usageStyles.empty}>{count(usage.cost_reporting.unmeasured_operations)} ledger operations lack provider measurements.{history?.runs ? " Available checkpoint counters are included in recorded totals." : " Token usage remains unmeasured."}</p> : null}
      {history && history.runs > 0 ? <section className={usageStyles.history} aria-label={`${title} checkpoint history`}>
        <h3>Recovered checkpoint history</h3>
        {history.first_recorded_at && history.last_recorded_at ? <p>{new Date(history.first_recorded_at).toLocaleDateString("en-US",{timeZone:"UTC",year:"numeric",month:"short",day:"numeric"})} to {new Date(history.last_recorded_at).toLocaleDateString("en-US",{timeZone:"UTC",year:"numeric",month:"short",day:"numeric"})} / UTC</p> : null}
        <p>{count(history.runs)} runs recovered. Each run is counted once across checkpoints and the usage ledger.</p>
        <dl className={usageStyles.metrics}>
          <div><dt>Stored input tokens</dt><dd>{count(history.prompt_tokens)}</dd></div>
          <div><dt>Stored output tokens</dt><dd>{count(history.completion_tokens)}</dd></div>
          <div><dt>Stored cost estimate</dt><dd>{history.estimated_cost_usd === null ? "Not recorded" : dashboardCost(history.estimated_cost_usd)}</dd></div>
          <div><dt>Added checkpoint cost</dt><dd>{history.additional_estimated_cost_usd === null ? "None recorded" : dashboardCost(history.additional_estimated_cost_usd)}</dd></div>
        </dl>
        <p>{count(history.overlapping_ledger_runs)} runs already have ledger records; their costs are not added again. {history.unpriced_runs ? `${count(history.unpriced_runs)} runs have missing or allowance-like costs and are excluded from the cost estimate.` : ""}</p>
        <p>Checkpoint counters and costs retain their original recorded values. Provider measurements take precedence when available.</p>
      </section> : null}
      {usage?.usage_rows === 0 && !history?.runs ? <p className={usageStyles.empty}>No model usage has been recorded yet.</p> : null}
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
        <p>Recorded tokens combine provider measurements with recovered checkpoint counters. A run with provider measurements uses those measurements; otherwise its checkpoint total is used once. Usage-cost estimates exclude unresolved safety allowances. Historical reconstructions use Standard uncached token rates. They are not a verified provider invoice.</p>
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

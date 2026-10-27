import type { CostReporting } from "../../lib/cost-reporting";
import { dashboardCost, dashboardNumber } from "./overview-charts";
import styles from "./overview.module.css";

export function CostReportingDetails({ report }: { report?: CostReporting | null }) {
  if (!report) return <p className={styles.footnote}>Cost coverage is unavailable. Budget-accounted usage is not verified spending.</p>;
  return <div className={styles.costCoverage}>
    <p className={styles.footnote}>{report.unresolved_operations ? `Partial estimate: ${dashboardNumber(report.unresolved_operations)} ${report.unresolved_operations === 1 ? "operation has" : "operations have"} unresolved charges.` : "Estimated usage costs are not a verified provider invoice."} {report.reconstructed_operations ? `${dashboardNumber(report.reconstructed_operations)} historical operations were reconstructed at Standard uncached token rates.` : ""}</p>
    {report.unresolved_operations ? <p className={styles.footnote}><strong>{dashboardCost(report.safety_allowance_usd)} safety allowances are excluded from the estimate.</strong> These are budget safeguards, not confirmed charges.</p> : null}
    <details className={styles.dataDetails}><summary>How costs are calculated</summary><dl className={styles.attentionCounts}>
      <div><dt>Operations with cost estimates</dt><dd>{dashboardNumber(report.estimated_operations)}</dd></div>
      <div><dt>Unresolved operations</dt><dd>{dashboardNumber(report.unresolved_operations)}</dd></div>
      <div><dt>Safety allowances (not spending)</dt><dd>{dashboardCost(report.safety_allowance_usd)}</dd></div>
      <div><dt>Original budget-accounted total</dt><dd>{dashboardCost(report.budget_accounted_usd)}</dd></div>
    </dl><p className={styles.footnote}>Historical reconstruction assumes Standard processing without cache discounts. Timeouts and ambiguous token counters remain unresolved. Original ledger and budget records are preserved.</p></details>
  </div>;
}

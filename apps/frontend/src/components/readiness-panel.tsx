/**
 * Shared readiness and signed-outage panels. Public `GET /health/ready` is
 * informational and is not login success.
 */

import { Fragment } from "react";
import { StatusBanner } from "./ui/status-banner";
import { LimitationCallout } from "./ui/limitation-callout";
import { limitationCopy } from "../lib/limitations";
import { displayText } from "../lib/safe-text";
import type { ReadinessResponse } from "../lib/types";
import styles from "./developer-app.module.css";

/**
 * Render public `GET /health/ready`. Owner/admin named probes from
 * `GET /ops/ready` are merged by the caller when the Bearer is allowed.
 *
 * @param props - Readiness payload, or null when FastAPI is unreachable.
 * @returns Readiness panel.
 */
export function ReadinessPanel({
  ready,
}: {
  ready: ReadinessResponse | null | undefined;
}) {
  if (ready === undefined) {
    return (
      <section className={styles.panel} aria-label="API readiness">
        <h2>API readiness</h2>
        <p className={styles.muted}>Checking GET /health/ready.</p>
      </section>
    );
  }
  if (ready === null) {
    return (
      <section className={styles.panel} aria-label="API readiness">
        <h2>API readiness</h2>
        <StatusBanner kind="error" role="status">
          FastAPI GET /health/ready is unreachable. Outage copy below is still
          the signed UI language when those events exist.
        </StatusBanner>
      </section>
    );
  }
  return (
    <section
      className={styles.panel}
      aria-label="API readiness"
      data-testid="api-readiness"
    >
      <h2>API readiness</h2>
      <p className={styles.muted}>{displayText(ready.detail)}</p>
      <dl>
        <dt>query_ready</dt>
        <dd data-testid="query-ready">{String(ready.query_ready)}</dd>
        <dt>status</dt>
        <dd>{displayText(ready.status)}</dd>
        <dt>rate_limit_degraded</dt>
        <dd>{String(ready.rate_limit_degraded)}</dd>
        {ready.dependencies.map((item) => (
          <Fragment key={item.name}>
            <dt>{displayText(item.name)}</dt>
            <dd data-testid={`dep-${item.name}`}>{displayText(item.status)}</dd>
          </Fragment>
        ))}
      </dl>
    </section>
  );
}

/**
 * Signed retrieval-outage sentences. Chat SSE still owns live codes.
 *
 * @returns Outage-copy panel.
 */
export function SignedOutageCopy() {
  return (
    <section className={styles.panel} aria-label="Signed outage copy">
      <h2>Signed outage copy</h2>
      <p className={styles.muted}>
        ParadeDB loss uses bm25_unavailable. LightRAG loss uses graph_outage.
        Valkey mutations fail closed; approved reads may degrade.
      </p>
      <LimitationCallout>{limitationCopy("bm25_unavailable")}</LimitationCallout>
      <LimitationCallout>{limitationCopy("graph_outage")}</LimitationCallout>
    </section>
  );
}

/**
 * Shell readiness chip and popover. Public `/health/ready` plus optional
 * owner/admin `/ops/ready` probes. Not an authorization boundary.
 */

"use client";

import { useConsoleReadiness } from "../../lib/hooks/use-console-readiness";
import {
  readinessBlockingCopy,
  readinessCapabilities,
  readinessHeadline,
} from "../../lib/shell-navigation";
import { Popover } from "./popover";
import { StatusPill } from "./status-pill";
import layoutStyles from "./app-shell.module.css";
import topbarStyles from "./app-topbar.module.css";

const styles = { ...layoutStyles, ...topbarStyles };

const TONE: Record<
  ReturnType<typeof readinessHeadline>,
  "neutral" | "success" | "warning" | "danger"
> = {
  Checking: "neutral",
  Ready: "success",
  Degraded: "warning",
  Unavailable: "danger",
};

/**
 * Render the top-bar readiness control.
 *
 * @returns Popover button. Side effects: health fetches.
 */
export function ReadinessIndicator() {
  const { ready, readyPending } = useConsoleReadiness();
  const resolved = readyPending && ready === null ? undefined : ready;
  const headline = readinessHeadline(resolved);
  const capabilities =
    resolved === null || resolved === undefined ? [] : readinessCapabilities(resolved);

  return (
    <span data-action-id="shell.readiness" data-testid="shell-readiness">
      <Popover
        label="Service readiness"
        actionId="shell.readiness"
        trigger={
          <>
            <StatusPill status={headline} tone={TONE[headline]} />
            <span className={styles.srOnly}>Service readiness: {headline}</span>
          </>
        }
      >
        <div className={styles.readinessPopover}>
          {headline === "Unavailable" ? <p>{readinessBlockingCopy()}</p> : null}
          {headline === "Checking" ? <p>Checking GET /health/ready.</p> : null}
          {capabilities.length > 0 ? (
            <ul>
              {capabilities.map((row) => (
                <li key={row.id}>
                  {row.label}: {row.ok ? "Ready" : "Unavailable"}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </Popover>
    </span>
  );
}

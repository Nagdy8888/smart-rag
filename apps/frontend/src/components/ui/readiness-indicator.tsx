/**
 * Shell readiness chip and popover. Public `/health/ready` plus optional
 * owner/admin `/ops/ready` probes. Not an authorization boundary.
 */

"use client";

import { useQuery } from "@tanstack/react-query";
import { loadConsoleReadiness } from "../../lib/api";
import { useSession } from "../../lib/auth/session-provider";
import { publicQueryKeys, sessionQueryKeys } from "../../lib/query-keys";
import {
  readinessBlockingCopy,
  readinessCapabilities,
  readinessHeadline,
} from "../../lib/shell-navigation";
import { Popover } from "./popover";
import { StatusPill } from "./status-pill";
import styles from "./app-shell.module.css";

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
  const session = useSession();
  const token = session.accessToken;
  const auth = token === null ? null : { accessToken: token };
  const query = useQuery({
    queryKey:
      token === null ? publicQueryKeys.ready : sessionQueryKeys(token).consoleReady,
    queryFn: () => loadConsoleReadiness(auth),
    enabled: session.ready,
  });
  const ready = query.isPending && query.data === undefined ? undefined : query.data ?? null;
  const headline = readinessHeadline(ready);
  const capabilities = ready === null || ready === undefined ? [] : readinessCapabilities(ready);

  return (
    <span data-action-id="shell.readiness" data-testid="shell-readiness">
      <Popover
        label="Service readiness"
        trigger={<StatusPill status={headline} tone={TONE[headline]} />}
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

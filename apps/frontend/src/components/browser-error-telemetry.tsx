/**
 * Optional GlitchTip browser init. Idle when the public DSN is unset.
 */
"use client";

import { useEffect } from "react";
import { scrubBrowserErrorEvent } from "../lib/browser-error-telemetry";

/**
 * Install the browser error client once when a public DSN is configured.
 *
 * @returns Nothing. The effect does not render UI.
 * @remarks
 * The DSN is an ingest key, not a privileged credential. Cookies, request
 * bodies, and passage-like fields are removed before send.
 */
export function BrowserErrorTelemetry() {
  useEffect(() => {
    const dsn = process.env.NEXT_PUBLIC_GLITCHTIP_DSN;
    if (dsn === undefined || dsn.trim() === "") {
      return;
    }
    let cancelled = false;
    void import("@sentry/browser").then((sentry) => {
      if (cancelled) {
        return;
      }
      sentry.init({
        dsn,
        environment: process.env.NEXT_PUBLIC_APP_ENV ?? "local",
        tracesSampleRate: 0,
        dataCollection: {
          userInfo: false,
          cookies: false,
          httpHeaders: false,
          httpBodies: [],
          urlQueryParams: false,
          stackFrameVariables: false,
          frameContextLines: 0,
        },
        beforeSend(event) {
          return scrubBrowserErrorEvent(event);
        },
      });
    });
    return () => {
      cancelled = true;
    };
  }, []);
  return null;
}

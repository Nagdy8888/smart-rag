/**
 * TanStack Query provider for server-state lists.
 */

"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { SessionProvider } from "../lib/auth/session-provider";
import { BrowserErrorTelemetry } from "./browser-error-telemetry";

/**
 * Wrap App Router children with QueryClient and Auth session.
 *
 * @param children - Route content.
 * @returns Provider tree. Browser error export stays idle without a public DSN.
 */
export function AppProviders({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { retry: false, refetchOnWindowFocus: false },
        },
      }),
  );
  return (
    <QueryClientProvider client={client}>
      <BrowserErrorTelemetry />
      <SessionProvider>{children}</SessionProvider>
    </QueryClientProvider>
  );
}

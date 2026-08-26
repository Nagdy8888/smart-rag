/**
 * One console-readiness query per session-role tuple.
 *
 * Readiness is not an authorization boundary.
 */

"use client";

import { useQuery } from "@tanstack/react-query";
import { loadConsoleReadiness } from "../api";
import { useApiAuth } from "../auth/use-api-auth";
import { useSession } from "../auth/session-provider";
import { publicQueryKeys, sessionQueryKeys } from "../query-keys";
import type { ReadinessResponse } from "../types";
import { useCurrentUser } from "./use-current-user";

export type UseConsoleReadinessResult = {
  ready: ReadinessResponse | null;
  readyPending: boolean;
};

/**
 * Load public `/health/ready` plus owner/admin `/ops/ready` probes.
 *
 * Signed-out callers share `publicQueryKeys.ready`. Authenticated callers
 * share `["console-ready", sub, role ?? "pending"]`.
 *
 * @returns Merged readiness, or null when FastAPI is unreachable.
 */
export function useConsoleReadiness(): UseConsoleReadinessResult {
  const session = useSession();
  const auth = useApiAuth();
  const { currentUser, isFetched } = useCurrentUser();
  const role = currentUser?.role ?? null;
  const keys = sessionQueryKeys(session.accessToken);
  const query = useQuery({
    queryKey: auth === null ? publicQueryKeys.ready : keys.consoleReady(role),
    queryFn: () => loadConsoleReadiness(auth, role),
    enabled: session.ready && (auth === null || isFetched),
    staleTime: 30_000,
    refetchInterval: 15_000,
    refetchIntervalInBackground: false,
  });
  return {
    ready: query.isPending && query.data === undefined ? null : query.data ?? null,
    readyPending: query.isPending,
  };
}

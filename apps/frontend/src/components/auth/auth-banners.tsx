/**
 * Shared Auth and console admission banners.
 */

"use client";

import { useQuery } from "@tanstack/react-query";
import { StatusBanner } from "../ui/status-banner";
import { fetchMeta } from "../../lib/api";
import { publicSupabaseConfig } from "../../lib/env";
import { evaluatePaidHandshake, handshakeBelowMinCopy } from "../../lib/handshake";
import { publicQueryKeys } from "../../lib/query-keys";

/**
 * Env-missing banner for Auth screens.
 *
 * @returns Banner, or null when public config is present.
 */
export function EnvMissingBanner() {
  if (publicSupabaseConfig() !== null) {
    return null;
  }
  return (
    <StatusBanner kind="error" role="alert">
      Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.
    </StatusBanner>
  );
}

/**
 * Handshake-before-spend banner on Auth and console surfaces.
 *
 * @returns Banner when the client is below min or meta is unreachable.
 */
export function HandshakeBanner() {
  const metaQuery = useQuery({
    queryKey: publicQueryKeys.meta,
    queryFn: () => fetchMeta(),
    refetchInterval: (query) => (query.state.status === "error" ? 10_000 : false),
  });
  const decision = evaluatePaidHandshake(
    metaQuery.data ?? null,
    metaQuery.isPending ? "loading" : metaQuery.isError ? "error" : "ok",
  );
  if (decision.kind === "below_min") {
    return (
      <StatusBanner kind="error" role="alert">
        {handshakeBelowMinCopy()}
      </StatusBanner>
    );
  }
  if (decision.kind === "unreachable") {
    return (
      <StatusBanner kind="warning" role="status">
        Compatibility could not be confirmed. New questions stay paused until
        the service responds.
      </StatusBanner>
    );
  }
  if (decision.kind === "schema_newer") {
    return (
      <StatusBanner kind="info" role="status">
        This console is slightly behind the API. Unknown stream events are
        ignored.
      </StatusBanner>
    );
  }
  return null;
}

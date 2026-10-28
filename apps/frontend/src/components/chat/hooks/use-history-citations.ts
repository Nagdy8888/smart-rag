"use client";

import { useEffect, useState, type RefObject } from "react";
import { useQueries } from "@tanstack/react-query";
import { listCitations, type ApiAuth } from "../../../lib/api";
import { sessionQueryKeys } from "../../../lib/query-keys";
import type { CitationResponse, ConversationMessage } from "../../../lib/types";

/** Fetch metadata for at most four visible turns; details remain on demand. */
export function useHistoryCitations(auth: ApiAuth | null, accessToken: string | null,
  conversationId: string | null, messages: readonly ConversationMessage[],
  root: RefObject<HTMLDivElement | null>): Record<string, readonly CitationResponse[]> {
  const [visible, setVisible] = useState<{ conversationId: string | null; ids: string[] }>({ conversationId: null, ids: [] });
  useEffect(() => {
    const container = root.current;
    if (!container || typeof IntersectionObserver === "undefined") return;
    const seen = new Set<string>();
    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        const id = (entry.target as HTMLElement).dataset.historyRun;
        if (id) { if (entry.isIntersecting) seen.add(id); else seen.delete(id); }
      }
      setVisible({ conversationId, ids: [...seen].slice(-4) });
    }, { root: container, rootMargin: "100px" });
    container.querySelectorAll("[data-history-run]").forEach((element) => observer.observe(element));
    return () => observer.disconnect();
  }, [conversationId, messages, root]);
  const ids = visible.conversationId === conversationId ? visible.ids : [];
  const keys = sessionQueryKeys(accessToken);
  const results = useQueries({ queries: ids.map((id) => ({
    queryKey: keys.citations(id), queryFn: () => listCitations(auth as ApiAuth, id),
    enabled: auth !== null, staleTime: 60_000, retry: false,
  })) });
  return Object.fromEntries(ids.map((id, index) => [id, results[index]?.data ?? []]));
}

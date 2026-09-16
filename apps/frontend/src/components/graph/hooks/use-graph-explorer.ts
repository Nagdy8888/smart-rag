/**
 * Graph search, 12-chip selection, and inspect mutation.
 */

"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  inspectGraph,
  isClassifiedApiError,
  searchGraphEntities,
  type ApiAuth,
} from "../../../lib/api";
import { useApiAuth } from "../../../lib/auth/use-api-auth";
import { useSession } from "../../../lib/auth/session-provider";
import { apiFailureBanner, GENERIC_PRODUCTION_ERROR } from "../../../lib/failure-copy";
import {
  GRAPH_INSPECT_MAX_ENTITIES,
  GRAPH_INSPECT_MAX_DEPTH,
  buildGraphInspectRequest,
  clampGraphInspectDepth,
  clampGraphSearchQuery,
  graphSearchQueryIsRunnable,
  visibleInspectNodes,
} from "../../../lib/graph-client";
import { sessionQueryKeys } from "../../../lib/query-keys";
import type {
  GraphEntityResponse,
  GraphInspectNodeResponse,
} from "../../../lib/types";

/**
 * Own graph search, chip selection, inspect, and stale-result guards.
 *
 * List and canvas share one `selectNode` callback. Chip count never exceeds
 * `GRAPH_INSPECT_MAX_ENTITIES` (12).
 *
 * @returns Explorer controller. Inspect remains a paid FastAPI mutation
 *   and stays disabled until API auth exists.
 */
export function useGraphExplorer() {
  const session = useSession();
  const searchParams = useSearchParams();
  const seededDocument = searchParams.get("documentId");
  const auth = useApiAuth();
  const keys = sessionQueryKeys(session.accessToken);
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [selectedHits, setSelectedHits] = useState<GraphEntityResponse[]>([]);
  const [depth, setDepth] = useState(GRAPH_INSPECT_MAX_DEPTH);
  const [view, setView] = useState<"list" | "canvas">("list");
  const [selectedNode, setSelectedNode] = useState<GraphInspectNodeResponse | null>(
    null,
  );
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [compactInspector, setCompactInspector] = useState(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return false;
    }
    return window.matchMedia("(max-width: 1279px)").matches;
  });
  const selectReturnRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") {
      return;
    }
    const media = window.matchMedia("(max-width: 1279px)");
    function onChange(): void {
      setCompactInspector(media.matches);
    }
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);

  const searchQuery = useQuery({
    queryKey: keys.graphSearch(submitted),
    queryFn: () => searchGraphEntities(auth as ApiAuth, submitted, 25),
    enabled: auth !== null && graphSearchQueryIsRunnable(submitted),
  });

  const inspectMutation = useMutation({
    mutationFn: async () => {
      if (auth === null) {
        throw new Error("unsigned");
      }
      const body = buildGraphInspectRequest(
        selectedHits.map((hit) => hit.object_id),
        seededDocument,
        clampGraphInspectDepth(depth),
      );
      return inspectGraph(auth, body);
    },
  });

  /**
   * Add a search hit as a chip without inspecting yet.
   *
   * @param hit - Authorized search row.
   */
  function addHit(hit: GraphEntityResponse): void {
    setSelectedHits((current) => {
      if (current.some((item) => item.object_id === hit.object_id)) {
        return current;
      }
      if (current.length >= GRAPH_INSPECT_MAX_ENTITIES) {
        return current;
      }
      return [...current, hit];
    });
  }

  /**
   * Remove one selected chip.
   *
   * @param objectId - Chip entity id.
   */
  function removeHit(objectId: string): void {
    setSelectedHits((current) => current.filter((item) => item.object_id !== objectId));
  }

  /**
   * Select a node and open the evidence drawer on compact layouts.
   *
   * @param node - Inspect row.
   * @param source - Select control used to restore focus when the drawer closes.
   */
  function selectNode(
    node: GraphInspectNodeResponse,
    source?: HTMLButtonElement,
  ): void {
    if (source) {
      selectReturnRef.current = source;
    }
    setSelectedNode(node);
    setDrawerOpen(true);
  }

  const inspect = inspectMutation.data;
  const listError =
    searchQuery.error !== null && searchQuery.error !== undefined
      ? isClassifiedApiError(searchQuery.error)
        ? apiFailureBanner(searchQuery.error.failure)
        : GENERIC_PRODUCTION_ERROR
      : null;
  const inspectError =
    inspectMutation.error !== null && inspectMutation.error !== undefined
      ? isClassifiedApiError(inspectMutation.error)
        ? apiFailureBanner(inspectMutation.error.failure)
        : GENERIC_PRODUCTION_ERROR
      : null;

  return {
    signedIn: session.ready && session.accessToken !== null,
    query,
    setQuery,
    search: () => setSubmitted(clampGraphSearchQuery(query)),
    hits: searchQuery.data ?? [],
    searching: searchQuery.isFetching,
    searched: submitted !== "",
    selectedHits,
    addHit,
    removeHit,
    atEntityLimit: selectedHits.length >= GRAPH_INSPECT_MAX_ENTITIES,
    seededDocument,
    depth,
    setDepth: (value: number) => setDepth(clampGraphInspectDepth(value)),
    canInspect:
      auth !== null &&
      (selectedHits.length > 0 || Boolean(seededDocument?.trim())),
    inspect: () => inspectMutation.mutate(),
    inspectPending: inspectMutation.isPending,
    inspectResult: inspect,
    nodes: visibleInspectNodes(inspect?.nodes ?? []),
    limitations: inspect?.limitations ?? [],
    locators: inspect?.locators ?? [],
    view,
    setView,
    selectedNode,
    selectNode,
    drawerOpen,
    closeDrawer: () => setDrawerOpen(false),
    compactInspector,
    selectReturnRef,
    listError,
    inspectError,
  };
}

/** Controller returned by `useGraphExplorer`. */
export type UseGraphExplorerResult = ReturnType<typeof useGraphExplorer>;

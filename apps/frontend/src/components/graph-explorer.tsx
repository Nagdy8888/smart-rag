/**
 * Graph explorer: search + inspect, list-first, hop cap 3, ≤200 nodes.
 * Graph Pending is distinct from ACL blindness. No unauthorized titles.
 */

"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { EntitySearch } from "./graph/entity-search";
import { GraphListFallback } from "./graph/graph-list-fallback";
import { GraphInspector } from "./graph/graph-inspector";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import {
  inspectGraph,
  searchGraphEntities,
  type ApiAuth,
} from "../lib/api";
import { useSession } from "../lib/auth/session-provider";
import {
  GRAPH_INSPECT_MAX_DEPTH,
  GRAPH_INSPECT_MAX_ROWS,
  buildGraphInspectRequest,
  clampGraphInspectDepth,
} from "../lib/graph-client";
import { sessionQueryKeys } from "../lib/query-keys";
import { displayText } from "../lib/safe-text";
import type { GraphInspectResponse } from "../lib/types";
import styles from "./graph/graph.module.css";

const GraphCanvas = dynamic(
  () => import("./graph/graph-canvas").then((mod) => mod.GraphCanvas),
  { ssr: false, loading: () => <p>Loading canvas</p> },
);

/**
 * Optional bounded SVG of inspect nodes. React elements only, not innerHTML.
 *
 * @param props - Inspect payload.
 * @returns SVG or null when empty.
 */
export function GraphNeighborhoodSvg({
  inspect,
}: {
  inspect: GraphInspectResponse;
}) {
  const nodes = inspect.nodes.slice(0, GRAPH_INSPECT_MAX_ROWS);
  if (nodes.length === 0 || nodes.length > 80) {
    return null;
  }
  const width = 480;
  const height = 320;
  const originX = width / 2;
  const originY = height / 2;
  return (
    <div className={styles.svgWrap}>
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${String(width)} ${String(height)}`}
        role="img"
        aria-label="Bounded graph neighborhood"
      >
        {nodes.map((node, index) => {
          const angle = (index / Math.max(nodes.length, 1)) * Math.PI * 2 - Math.PI / 2;
          const radius = index === 0 ? 0 : 110;
          const x = originX + Math.cos(angle) * radius;
          const y = originY + Math.sin(angle) * radius;
          const hue = 217;
          return (
            <g key={`${node.object_id}-${String(index)}`}>
              {index > 0 ? (
                <line
                  x1={originX}
                  y1={originY}
                  x2={x}
                  y2={y}
                  stroke="var(--color-border)"
                  strokeWidth={1.5}
                />
              ) : null}
              <circle
                cx={x}
                cy={y}
                r={index === 0 ? 18 : 12}
                fill={`hsl(${String(hue)} 84% ${index === 0 ? "54%" : "72%"})`}
              />
              <title>{displayText(node.object_id)}</title>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

/**
 * Graph search and inspect surface.
 *
 * @returns Three-pane explorer.
 */
export function GraphExplorer() {
  const session = useSession();
  const searchParams = useSearchParams();
  const seededDocument = searchParams.get("documentId");
  const accessToken = session.accessToken;
  const auth = useMemo<ApiAuth | null>(
    () => (accessToken ? { accessToken } : null),
    [accessToken],
  );
  const keys = sessionQueryKeys(accessToken);
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [entityKey, setEntityKey] = useState("");
  const [documentId, setDocumentId] = useState(seededDocument ?? "");
  const [depth, setDepth] = useState(GRAPH_INSPECT_MAX_DEPTH);

  const searchQuery = useQuery({
    queryKey: keys.graphSearch(submitted),
    queryFn: () => searchGraphEntities(auth as ApiAuth, submitted, 25),
    enabled: auth !== null && submitted.trim() !== "",
  });

  const inspectMutation = useMutation({
    mutationFn: async (keysOverride?: string) => {
      if (auth === null) {
        throw new Error("unsigned");
      }
      const raw = keysOverride ?? entityKey;
      const keysList = raw
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
      const body = buildGraphInspectRequest(
        keysList,
        documentId.trim() || null,
        clampGraphInspectDepth(depth),
      );
      return inspectGraph(auth, body);
    },
  });

  if (!session.ready || accessToken === null) {
    return (
      <div className={styles.shell}>
        <h2>Graph</h2>
        <p className={styles.muted}>
          <Link href="/login">Sign in</Link>
        </p>
      </div>
    );
  }

  const inspect = inspectMutation.data;
  const limitations = inspect?.limitations ?? [];

  return (
    <div className={styles.shell}>
      <h2>Graph explorer</h2>
      <p className={styles.pageLead}>
        Search first, then inspect a bounded neighborhood. Depth stays at most{" "}
        {String(GRAPH_INSPECT_MAX_DEPTH)}. This is inspection, not an answering
        mode.
      </p>
      <div className={styles.panes}>
        <EntitySearch
          query={query}
          onQuery={setQuery}
          onSearch={() => setSubmitted(query.trim())}
          hits={searchQuery.data ?? []}
          onSelect={(objectId) => {
            setEntityKey(objectId);
            inspectMutation.mutate(objectId);
          }}
          loading={searchQuery.isFetching}
        />
        <section className={styles.panel} aria-label="Inspect">
          <h2>Inspect</h2>
          <Input
            label="Entity keys (comma-separated, max 12)"
            value={entityKey}
            onChange={(event) => setEntityKey(event.target.value)}
          />
          <details className={styles.details}>
            <summary>Advanced inspect</summary>
            <Input
              label="Document id seed"
              value={documentId}
              onChange={(event) => setDocumentId(event.target.value)}
            />
            <Input
              label="Depth (1–3)"
              type="number"
              min={1}
              max={GRAPH_INSPECT_MAX_DEPTH}
              value={String(depth)}
              onChange={(event) =>
                setDepth(clampGraphInspectDepth(Number(event.target.value)))
              }
            />
          </details>
          <Button
            type="button"
            variant="primary"
            onClick={() => inspectMutation.mutate(undefined)}
            disabled={entityKey.trim() === "" && documentId.trim() === ""}
          >
            Inspect
          </Button>
          {inspectMutation.isError ? (
            <p className={styles.muted}>Inspect rejected.</p>
          ) : null}
          <GraphListFallback nodes={inspect?.nodes ?? []} />
          {inspect ? <GraphCanvas nodes={inspect.nodes} /> : null}
          {inspect ? <GraphNeighborhoodSvg inspect={inspect} /> : null}
        </section>
        <GraphInspector
          locators={inspect?.locators ?? []}
          limitations={limitations}
        />
      </div>
    </div>
  );
}

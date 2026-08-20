/**
 * Graph explorer: search + inspect, list-first, hop cap 3, ≤200 nodes.
 * Graph Pending is distinct from ACL blindness. No unauthorized titles.
 */

"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { LimitationCallout } from "./ui/limitation-callout";
import { UserText } from "./ui/user-text";
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
  graphLimitationDisplay,
  isGraphPendingLimitation,
} from "../lib/graph-client";
import { graphNotReadyCopy, limitationCopy, limitationTone } from "../lib/limitations";
import { sessionQueryKeys } from "../lib/query-keys";
import { displayText, formatProvenance } from "../lib/safe-text";
import type { GraphInspectResponse } from "../lib/types";
import styles from "./developer-app.module.css";

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
    mutationFn: async () => {
      if (auth === null) {
        throw new Error("unsigned");
      }
      const keysList = entityKey
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
        <h1>Graph</h1>
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
      <h1>Graph explorer</h1>
      <p className={styles.pageLead}>
        Search first, then inspect a bounded neighborhood. Depth stays at most{" "}
        {String(GRAPH_INSPECT_MAX_DEPTH)}. This is inspection, not an answering
        mode.
      </p>
      <div className={styles.panes}>
        <section className={styles.panel} aria-label="Search">
          <h2>Search</h2>
          <Input
            label="Entity query"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <Button
            type="button"
            onClick={() => setSubmitted(query.trim())}
            disabled={query.trim() === ""}
          >
            Search
          </Button>
          <ul className={styles.list}>
            {(searchQuery.data ?? []).map((hit) => (
              <li key={`${hit.object_id}-${hit.chunk_id}`}>
                <button
                  type="button"
                  onClick={() => setEntityKey(hit.object_id)}
                >
                  <UserText value={hit.object_type} />{" "}
                  <UserText value={hit.object_id} />
                </button>
              </li>
            ))}
          </ul>
        </section>
        <section className={styles.panel} aria-label="Inspect">
          <h2>Inspect</h2>
          <Input
            label="Entity keys (comma-separated, max 12)"
            value={entityKey}
            onChange={(event) => setEntityKey(event.target.value)}
          />
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
          <Button
            type="button"
            variant="primary"
            onClick={() => inspectMutation.mutate()}
            disabled={entityKey.trim() === "" && documentId.trim() === ""}
          >
            Inspect
          </Button>
          {inspectMutation.isError ? (
            <p className={styles.muted}>Inspect rejected.</p>
          ) : null}
          <h3>Nodes</h3>
          <ul className={styles.list}>
            {(inspect?.nodes ?? []).map((node, index) => (
              <li key={`${node.object_id}-${String(index)}`}>
                hop {String(node.hop)}{" "}
                <UserText value={node.object_type} />{" "}
                <UserText value={node.object_id} />
              </li>
            ))}
          </ul>
          {inspect ? <GraphNeighborhoodSvg inspect={inspect} /> : null}
        </section>
        <section className={styles.panel} aria-label="Locators and limitations">
          <h2>Locators</h2>
          <ul className={styles.list}>
            {(inspect?.locators ?? []).map((locator) => (
              <li key={locator.chunk_id}>
                <UserText
                  value={formatProvenance({
                    page_number: locator.page_number,
                    section_path: locator.section_path,
                    sheet_name: locator.sheet_name,
                    range_ref: locator.range_ref,
                    source_url: locator.source_url,
                  })}
                />
              </li>
            ))}
          </ul>
          {limitations.map((item) => (
            <LimitationCallout
              key={item.code}
              tone={limitationTone(item.code)}
            >
              {graphLimitationDisplay(item)}
              {isGraphPendingLimitation(item.code) &&
              item.code !== "graph_acl_blindness"
                ? ` ${graphNotReadyCopy(item.count ?? 0)}`
                : null}
            </LimitationCallout>
          ))}
          {limitations.some((item) => item.code === "graph_acl_blindness") ? (
            <p className={styles.muted}>{limitationCopy("graph_acl_blindness")}</p>
          ) : null}
          <p className={styles.muted}>
            Relationship editing is not available. This explorer is
            inspection-only.
          </p>
        </section>
      </div>
    </div>
  );
}

/**
 * Graph explorer: search → select chips → inspect. List-first plus optional React Flow.
 * No custom SVG neighborhood. No relationship editing.
 */

"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { EntitySearch } from "./entity-search";
import { GraphListFallback } from "./graph-list-fallback";
import { GraphInspector } from "./graph-inspector";
import { Button, PrimaryAction } from "../ui/button";
import { Drawer } from "../ui/drawer";
import { Icon } from "../ui/icon";
import { PageHeader } from "../ui/page-header";
import { Select } from "../ui/select";
import { StatusBanner } from "../ui/status-banner";
import { StatusPill } from "../ui/status-pill";
import { UserText } from "../ui/user-text";
import {
  inspectGraph,
  isClassifiedApiError,
  searchGraphEntities,
  type ApiAuth,
} from "../../lib/api";
import { useSession } from "../../lib/auth/session-provider";
import { apiFailureBanner, GENERIC_PRODUCTION_ERROR } from "../../lib/failure-copy";
import {
  GRAPH_ENTITY_LIMIT_COPY,
  GRAPH_INSPECT_BOUNDS_COPY,
  GRAPH_INSPECT_MAX_DEPTH,
  GRAPH_INSPECT_MAX_ENTITIES,
  GRAPH_INSPECT_MAX_ROWS,
  buildGraphInspectRequest,
  clampGraphInspectDepth,
  clampGraphSearchQuery,
  graphSearchQueryIsRunnable,
  visibleInspectNodes,
} from "../../lib/graph-client";
import { sessionQueryKeys } from "../../lib/query-keys";
import type {
  GraphEntityResponse,
  GraphInspectNodeResponse,
} from "../../lib/types";
import styles from "./graph.module.css";

const GraphCanvas = dynamic(
  () => import("./graph-canvas").then((mod) => mod.GraphCanvas),
  { ssr: false, loading: () => <p>Loading canvas</p> },
);

const DEPTH_OPTIONS = [
  { value: "1", label: "1" },
  { value: "2", label: "2" },
  { value: "3", label: "3" },
];

/**
 * Graph search and inspect surface.
 *
 * @returns Search, results, and evidence inspector.
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

  if (!session.ready || accessToken === null) {
    return (
      <div className={styles.page}>
        <PageHeader title="Graph." />
        <p className={styles.muted}>
          <Link href="/login">Sign in</Link>
        </p>
      </div>
    );
  }

  const inspect = inspectMutation.data;
  const nodes = visibleInspectNodes(inspect?.nodes ?? []);
  const limitations = inspect?.limitations ?? [];
  const atEntityLimit = selectedHits.length >= GRAPH_INSPECT_MAX_ENTITIES;
  const canInspect = selectedHits.length > 0 || Boolean(seededDocument?.trim());
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

  /**
   * Add a search hit as a chip without inspecting yet.
   *
   * @param hit - Authorized search row.
   */
  function addHit(hit: GraphEntityResponse): void {
    if (selectedHits.some((item) => item.object_id === hit.object_id)) {
      return;
    }
    if (selectedHits.length >= GRAPH_INSPECT_MAX_ENTITIES) {
      return;
    }
    setSelectedHits([...selectedHits, hit]);
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

  const inspector = (
    <GraphInspector
      node={selectedNode}
      locators={inspect?.locators ?? []}
      limitations={limitations}
    />
  );

  return (
    <div className={styles.page}>
      <PageHeader
        title="Graph."
        description="Inspect bounded entities and relationships backed by authorized evidence."
      />
      {listError ? (
        <StatusBanner kind="error" role="alert">
          {listError}
        </StatusBanner>
      ) : null}
      {inspectError ? (
        <StatusBanner kind="error" role="alert">
          {inspectError}
        </StatusBanner>
      ) : null}

      <div className={styles.layout}>
        <div className={styles.searchColumn}>
          <EntitySearch
            query={query}
            onQuery={setQuery}
            onSearch={() => setSubmitted(clampGraphSearchQuery(query))}
            hits={searchQuery.data ?? []}
            onSelect={addHit}
            loading={searchQuery.isFetching}
            searched={submitted !== ""}
          />
          {selectedHits.length > 0 ? (
            <ul className={styles.chipList} aria-label="Selected entities">
              {selectedHits.map((hit) => (
                <li key={hit.object_id} className={styles.chip}>
                  <UserText value={hit.object_id} />
                  <Button
                    type="button"
                    size="icon"
                    aria-label={`Remove ${hit.object_id}`}
                    onClick={() =>
                      setSelectedHits(
                        selectedHits.filter((item) => item.object_id !== hit.object_id),
                      )
                    }
                  >
                    <Icon name="close" />
                  </Button>
                </li>
              ))}
            </ul>
          ) : null}
          {atEntityLimit ? (
            <p className={styles.muted}>{GRAPH_ENTITY_LIMIT_COPY}</p>
          ) : null}
          {seededDocument ? (
            <p className={styles.muted}>
              Document seed{" "}
              <span className={styles.mono}>
                <UserText value={seededDocument} />
              </span>
            </p>
          ) : null}
          <Select
            label="Depth"
            value={String(depth)}
            options={DEPTH_OPTIONS}
            onChange={(event) =>
              setDepth(clampGraphInspectDepth(Number(event.target.value)))
            }
          />
          <PrimaryAction
            type="button"
            data-action-id="graph.inspect"
            pending={inspectMutation.isPending}
            pendingLabel="Inspecting…"
            disabled={!canInspect}
            disabledReason={
              canInspect ? undefined : "Select an entity or open a document seed."
            }
            onClick={() => inspectMutation.mutate()}
          >
            Inspect graph
          </PrimaryAction>
        </div>

        <section className={styles.results} aria-label="Graph results">
          <div className={styles.toolbar}>
            <p className={styles.muted}>
              {nodes.length}
              {inspect && inspect.row_count > GRAPH_INSPECT_MAX_ROWS
                ? ` of ${String(inspect.row_count)}`
                : ""}{" "}
              nodes. {GRAPH_INSPECT_BOUNDS_COPY}
            </p>
            {limitations[0] ? (
              <StatusPill status={limitations[0].code} tone="warning" />
            ) : null}
            <div className={styles.toolbarRight}>
              <Button
                type="button"
                aria-pressed={view === "list"}
                onClick={() => setView("list")}
              >
                List
              </Button>
              <Button
                type="button"
                aria-pressed={view === "canvas"}
                onClick={() => setView("canvas")}
              >
                Canvas
              </Button>
            </div>
          </div>
          {inspect ? (
            view === "list" ? (
              <GraphListFallback
                nodes={nodes}
                selectedId={selectedNode?.object_id ?? null}
                onSelect={selectNode}
              />
            ) : (
              <GraphCanvas
                nodes={nodes}
                selectedId={selectedNode?.object_id ?? null}
                onSelect={selectNode}
              />
            )
          ) : (
            <p className={styles.muted}>{GRAPH_INSPECT_BOUNDS_COPY}</p>
          )}
        </section>

        <aside className={styles.inspectorDock} aria-label="Evidence details">
          {inspector}
        </aside>
      </div>

      {drawerOpen && compactInspector ? (
        <Drawer
          title="Evidence details."
          onClose={() => setDrawerOpen(false)}
          returnFocusRef={selectReturnRef}
        >
          {inspector}
        </Drawer>
      ) : null}
    </div>
  );
}

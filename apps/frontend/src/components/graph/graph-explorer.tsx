/**
 * Graph explorer: search → select chips → inspect. List-first plus optional React Flow.
 * No custom SVG neighborhood. No relationship editing.
 */

"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { EntitySearch } from "./entity-search";
import { GraphListFallback } from "./graph-list-fallback";
import { GraphInspector } from "./graph-inspector";
import { useGraphExplorer } from "./hooks/use-graph-explorer";
import { Button, PrimaryAction } from "../ui/button";
import { Drawer } from "../ui/drawer";
import { Icon } from "../ui/icon";
import { PageHeader } from "../ui/page-header";
import { Select } from "../ui/select";
import { StatusBanner } from "../ui/status-banner";
import { StatusPill } from "../ui/status-pill";
import { UserText } from "../ui/user-text";
import {
  GRAPH_ENTITY_LIMIT_COPY,
  GRAPH_INSPECT_BOUNDS_COPY,
  GRAPH_INSPECT_MAX_ROWS,
} from "../../lib/graph-client";
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
  const g = useGraphExplorer();

  if (!g.signedIn) {
    return (
      <div className={styles.page}>
        <PageHeader />
        <p className={styles.muted}>
          <Link href="/login">Sign in</Link>
        </p>
      </div>
    );
  }

  const inspector = (
    <GraphInspector
      node={g.selectedNode}
      locators={g.locators}
      limitations={g.limitations}
    />
  );

  return (
    <div className={styles.page}>
      <PageHeader />
      {g.listError ? (
        <StatusBanner kind="error" role="alert">
          {g.listError}
        </StatusBanner>
      ) : null}
      {g.inspectError ? (
        <StatusBanner kind="error" role="alert">
          {g.inspectError}
        </StatusBanner>
      ) : null}

      <div className={styles.layout}>
        <div className={styles.searchColumn}>
          <EntitySearch
            query={g.query}
            onQuery={g.setQuery}
            onSearch={g.search}
            hits={g.hits}
            onSelect={g.addHit}
            loading={g.searching}
            searched={g.searched}
          />
          {g.selectedHits.length > 0 ? (
            <ul className={styles.chipList} aria-label="Selected entities">
              {g.selectedHits.map((hit) => (
                <li key={hit.object_id} className={styles.chip}>
                  <UserText value={hit.object_id} />
                  <Button
                    type="button"
                    size="icon"
                    aria-label={`Remove ${hit.object_id}`}
                    onClick={() => g.removeHit(hit.object_id)}
                  >
                    <Icon name="close" />
                  </Button>
                </li>
              ))}
            </ul>
          ) : null}
          {g.atEntityLimit ? (
            <p className={styles.muted}>{GRAPH_ENTITY_LIMIT_COPY}</p>
          ) : null}
          {g.seededDocument ? (
            <p className={styles.muted}>
              Document seed{" "}
              <span className={styles.mono}>
                <UserText value={g.seededDocument} />
              </span>
            </p>
          ) : null}
          <Select
            label="Depth"
            value={String(g.depth)}
            options={DEPTH_OPTIONS}
            onChange={(event) => g.setDepth(Number(event.target.value))}
          />
          <PrimaryAction
            type="button"
            data-action-id="graph.inspect"
            pending={g.inspectPending}
            pendingLabel="Inspecting…"
            disabled={!g.canInspect}
            disabledReason={
              g.canInspect ? undefined : "Select an entity or open a document seed."
            }
            onClick={g.inspect}
          >
            Inspect graph
          </PrimaryAction>
        </div>

        <section className={styles.results} aria-label="Graph results">
          <div className={styles.toolbar}>
            <p className={styles.muted}>{GRAPH_INSPECT_BOUNDS_COPY}</p>
            <p className={styles.muted}>
              {g.nodes.length}
              {g.inspectResult && g.inspectResult.row_count > GRAPH_INSPECT_MAX_ROWS
                ? ` of ${String(g.inspectResult.row_count)}`
                : ""}{" "}
              nodes
            </p>
            {g.limitations[0] ? (
              <StatusPill status={g.limitations[0].code} tone="warning" />
            ) : null}
            <div className={styles.toolbarRight}>
              <Button
                type="button"
                aria-pressed={g.view === "list"}
                onClick={() => g.setView("list")}
              >
                List
              </Button>
              <Button
                type="button"
                aria-pressed={g.view === "canvas"}
                onClick={() => g.setView("canvas")}
              >
                Canvas
              </Button>
            </div>
          </div>
          {g.inspectResult ? (
            g.view === "list" ? (
              <GraphListFallback
                nodes={g.nodes}
                selectedId={g.selectedNode?.object_id ?? null}
                onSelect={g.selectNode}
              />
            ) : (
              <GraphCanvas
                nodes={g.nodes}
                selectedId={g.selectedNode?.object_id ?? null}
                onSelect={g.selectNode}
                onOpenAccessibleList={() => g.setView("list")}
              />
            )
          ) : (
            <p className={styles.muted}>Run inspect to load a neighborhood.</p>
          )}
        </section>

        <aside className={styles.inspectorDock} aria-label="Evidence details">
          {inspector}
        </aside>
      </div>

      {g.drawerOpen && g.compactInspector ? (
        <Drawer
          title="Evidence details"
          onClose={g.closeDrawer}
          returnFocusRef={g.selectReturnRef}
        >
          {inspector}
        </Drawer>
      ) : null}
    </div>
  );
}

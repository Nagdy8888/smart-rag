/**
 * Always-available inspect list. Default accessible representation.
 */

import { Button } from "../ui/button";
import { StatusPill } from "../ui/status-pill";
import { UserText } from "../ui/user-text";
import { EMPTY_INSPECT_COPY } from "../../lib/graph-client";
import type { GraphInspectNodeResponse } from "../../lib/types";
import styles from "./graph.module.css";

export type GraphListFallbackProps = {
  /** Inspect nodes already clamped to 200. */
  nodes: GraphInspectNodeResponse[];
  /** Currently inspected object. */
  selectedId: string | null;
  /** Open the evidence inspector. */
  onSelect: (node: GraphInspectNodeResponse, source: HTMLButtonElement) => void;
};

/**
 * Render the semantic node list.
 *
 * @param props - Nodes and selection.
 * @returns List of type, id, hop, support, and Select.
 */
export function GraphListFallback({
  nodes,
  selectedId,
  onSelect,
}: GraphListFallbackProps) {
  return (
    <section aria-label="Graph list">
      {nodes.length === 0 ? (
        <p className={styles.muted}>{EMPTY_INSPECT_COPY}</p>
      ) : (
        <ul className={styles.nodeList}>
          {nodes.map((node, index) => {
            const rowId = `${node.object_id}-${String(index)}`;
            const active = selectedId === node.object_id;
            return (
              <li key={rowId} className={active ? styles.nodeRowActive : styles.nodeRow}>
                <StatusPill status={node.object_type} />
                <span className={styles.mono}>
                  <UserText value={node.object_id} />
                </span>
                <span className={styles.muted}>hop {String(node.hop)}</span>
                <span className={styles.muted}>support {String(node.support)}</span>
                <Button
                  type="button"
                  size="compact"
                  aria-current={active ? "true" : undefined}
                  onClick={(event) => onSelect(node, event.currentTarget)}
                >
                  Select
                </Button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

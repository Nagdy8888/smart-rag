/**
 * Always-available inspect list. Required when the canvas is hidden or fails.
 */

import { UserText } from "../ui/user-text";
import type { GraphInspectNodeResponse } from "../../lib/types";
import styles from "./graph.module.css";

export type GraphListFallbackProps = {
  /** Inspect nodes. */
  nodes: GraphInspectNodeResponse[];
};

/**
 * Render the semantic node list.
 *
 * @param props - Nodes.
 * @returns List of hop, object_type, object_id.
 */
export function GraphListFallback({ nodes }: GraphListFallbackProps) {
  return (
    <section aria-label="Node list">
      <h3>Nodes</h3>
      {nodes.length === 0 ? (
        <p className={styles.muted}>No authorized nodes in this inspect.</p>
      ) : (
        <ul className={styles.list}>
          {nodes.map((node, index) => (
            <li key={`${node.object_id}-${String(index)}`}>
              hop {String(node.hop)}{" "}
              <UserText value={node.object_type} />{" "}
              <UserText value={node.object_id} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

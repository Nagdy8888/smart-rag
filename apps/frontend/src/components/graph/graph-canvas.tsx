/**
 * Lazy React Flow canvas. Nodes show object_type and object_id only.
 */

"use client";

import { useMemo } from "react";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { UserText } from "../ui/user-text";
import type { GraphInspectNodeResponse } from "../../lib/types";
import styles from "./graph.module.css";

export type GraphCanvasProps = {
  /** Inspect nodes. */
  nodes: GraphInspectNodeResponse[];
};

/**
 * Render a non-editable neighborhood canvas.
 *
 * @param props - Inspect nodes.
 * @returns React Flow surface. No connect/delete. Edges unlabeled.
 */
export function GraphCanvas({ nodes }: GraphCanvasProps) {
  const flowNodes = useMemo<Node[]>(() => {
    return nodes.map((node, index) => ({
      id: `${node.object_id}-${String(index)}`,
      position: { x: 40 + (index % 4) * 180, y: 40 + Math.floor(index / 4) * 100 },
      data: { objectType: node.object_type, objectId: node.object_id },
      draggable: false,
      connectable: false,
      selectable: true,
      sourcePosition: undefined,
      targetPosition: undefined,
      style: { width: 160 },
    }));
  }, [nodes]);
  const edges = useMemo<Edge[]>(() => [], []);
  return (
    <div className={styles.canvas} aria-label="Graph canvas">
      <ReactFlow
        nodes={flowNodes}
        edges={edges}
        fitView
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        panOnDrag
        zoomOnScroll
        proOptions={{ hideAttribution: true }}
        nodeTypes={{
          default: ({ data, selected }: { data: { objectType: string; objectId: string }; selected?: boolean }) => (
            <div className={selected ? `${styles.node} ${styles.nodeSelected}` : styles.node}>
              <div>
                <UserText value={data.objectType} />
              </div>
              <div className={styles.mono}>
                <UserText value={data.objectId} />
              </div>
            </div>
          ),
        }}
      >
        <Background />
        <Controls showInteractive={false} aria-label="Graph controls" />
        <MiniMap pannable zoomable aria-label="Graph overview" />
      </ReactFlow>
    </div>
  );
}

/**
 * Optional React Flow canvas. Inspection only; no connect/delete/edit.
 * Inspect payloads have no edge list, so this canvas does not invent edges.
 */

"use client";

import { useMemo, type MouseEvent } from "react";
import {
  Background,
  BackgroundVariant,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Node,
  type NodeMouseHandler,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Button } from "../ui/button";
import { UserText } from "../ui/user-text";
import type { GraphInspectNodeResponse } from "../../lib/types";
import styles from "./graph.module.css";

export type GraphCanvasProps = {
  /** Inspect nodes already clamped to 200. */
  nodes: GraphInspectNodeResponse[];
  /** Selected object id. */
  selectedId: string | null;
  /** Node click selects evidence details. */
  onSelect: (node: GraphInspectNodeResponse) => void;
};

type GraphNodeData = {
  objectType: string;
  objectId: string;
  hop: number;
  support: number;
  source: GraphInspectNodeResponse;
};

/**
 * Bounded node chrome: type, id, hop/support.
 *
 * @param props - React Flow node props.
 * @returns Non-editable node.
 */
function GraphFlowNode({
  data,
  selected,
}: {
  data: GraphNodeData;
  selected?: boolean;
}) {
  return (
    <div className={selected ? `${styles.node} ${styles.nodeSelected}` : styles.node}>
      <p className={styles.nodeCaption}>
        <UserText value={data.objectType} />
      </p>
      <p className={styles.mono}>
        <UserText value={data.objectId} />
      </p>
      <p className={styles.nodeFooter}>
        hop {String(data.hop)} · support {String(data.support)}
      </p>
    </div>
  );
}

const NODE_TYPES = { default: GraphFlowNode };

/**
 * Zoom and fit controls. Labeled; the canvas is not an editor.
 *
 * @returns Control cluster.
 */
function CanvasControls() {
  const { zoomIn, zoomOut, fitView } = useReactFlow();
  return (
    <div className={styles.canvasControls}>
      <Button type="button" size="icon" aria-label="Zoom in" onClick={() => void zoomIn()}>
        +
      </Button>
      <Button type="button" size="icon" aria-label="Zoom out" onClick={() => void zoomOut()}>
        −
      </Button>
      <Button type="button" aria-label="Fit" onClick={() => void fitView()}>
        Fit
      </Button>
    </div>
  );
}

/**
 * Inner canvas that can call `useReactFlow`.
 *
 * @param props - Nodes and selection.
 * @returns React Flow surface.
 */
function GraphCanvasInner({ nodes, selectedId, onSelect }: GraphCanvasProps) {
  const flowNodes = useMemo<Node<GraphNodeData>[]>(() => {
    return nodes.map((node, index) => ({
      id: `${node.object_id}-${String(index)}`,
      position: { x: 40 + (index % 4) * 190, y: 40 + Math.floor(index / 4) * 120 },
      selected: selectedId === node.object_id,
      data: {
        objectType: node.object_type,
        objectId: node.object_id,
        hop: node.hop,
        support: node.support,
        source: node,
      },
      draggable: false,
      connectable: false,
      selectable: true,
    }));
  }, [nodes, selectedId]);

  const handleNodeClick: NodeMouseHandler<Node<GraphNodeData>> = (
    _event: MouseEvent,
    node,
  ) => {
    onSelect(node.data.source);
  };

  return (
    <div className={styles.canvas} aria-label="Graph canvas">
      <ReactFlow
        nodes={flowNodes}
        edges={[]}
        fitView
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        panOnDrag
        zoomOnScroll
        deleteKeyCode={null}
        proOptions={{ hideAttribution: true }}
        nodeTypes={NODE_TYPES}
        onNodeClick={handleNodeClick}
      >
        <Background variant={BackgroundVariant.Dots} gap={16} color="var(--color-border)" />
        <CanvasControls />
      </ReactFlow>
    </div>
  );
}

/**
 * Render a non-editable neighborhood canvas.
 *
 * @param props - Inspect nodes and selection.
 * @returns React Flow surface. No connect/delete. No invented edges.
 */
export function GraphCanvas(props: GraphCanvasProps) {
  return (
    <ReactFlowProvider>
      <GraphCanvasInner {...props} />
    </ReactFlowProvider>
  );
}

/**
 * Optional React Flow canvas. Inspection only; no connect/delete/edit.
 * Inspect payloads have no edge list, so this canvas does not invent edges.
 */

"use client";

import { useMemo, type KeyboardEvent, type MouseEvent } from "react";
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
  /** Node click or Enter/Space on a focused node selects evidence details. */
  onSelect: (node: GraphInspectNodeResponse) => void;
  /** Switch to the canonical accessible list. */
  onOpenAccessibleList: () => void;
};

type GraphNodeData = {
  objectType: string;
  objectId: string;
  hop: number;
  support: number;
  source: GraphInspectNodeResponse;
  onSelect: (node: GraphInspectNodeResponse) => void;
};

/**
 * Activate the same inspect callback used by pointer selection.
 *
 * @param event - Keyboard event on a focused canvas node.
 * @param onSelect - Shared inspect callback.
 * @param source - Inspect row.
 */
export function activateCanvasNode(
  event: Pick<KeyboardEvent, "key" | "preventDefault">,
  onSelect: (node: GraphInspectNodeResponse) => void,
  source: GraphInspectNodeResponse,
): void {
  if (event.key !== "Enter" && event.key !== " ") {
    return;
  }
  event.preventDefault();
  onSelect(source);
}

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
    <div
      className={selected ? `${styles.node} ${styles.nodeSelected}` : styles.node}
      tabIndex={0}
      role="button"
      aria-current={selected ? "true" : undefined}
      aria-label={`${data.objectType} ${data.objectId}`}
      onKeyDown={(event) => activateCanvasNode(event, data.onSelect, data.source)}
    >
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
function GraphCanvasInner({
  nodes,
  selectedId,
  onSelect,
  onOpenAccessibleList,
}: GraphCanvasProps) {
  const flowNodes = useMemo<Node<GraphNodeData>[]>(() => {
    return nodes.map((node, index) => ({
      id: `${node.object_id}-${String(index)}`,
      position: { x: 40 + (index % 4) * 190, y: 40 + Math.floor(index / 4) * 120 },
      selected: selectedId === node.object_id,
      ariaLabel: `${node.object_type} ${node.object_id}`,
      data: {
        objectType: node.object_type,
        objectId: node.object_id,
        hop: node.hop,
        support: node.support,
        source: node,
        onSelect,
      },
      draggable: false,
      connectable: false,
      selectable: true,
      focusable: true,
    }));
  }, [nodes, onSelect, selectedId]);

  const handleNodeClick: NodeMouseHandler<Node<GraphNodeData>> = (
    _event: MouseEvent,
    node,
  ) => {
    onSelect(node.data.source);
  };

  const canvasSupported = typeof ResizeObserver !== "undefined";

  return (
    <div className={styles.canvas} aria-label="Supplementary graph canvas">
      <div className={styles.canvasBanner}>
        <p className={styles.muted}>
          Canvas is a supplementary visualization. The list is the accessible
          representation.
        </p>
        <Button type="button" size="compact" onClick={onOpenAccessibleList}>
          Open accessible list
        </Button>
      </div>
      {canvasSupported ? (
        <ReactFlow
          nodes={flowNodes}
          edges={[]}
          fitView
          nodesDraggable={false}
          nodesConnectable={false}
          nodesFocusable
          edgesFocusable={false}
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
      ) : (
        <p className={styles.muted}>
          Canvas visualization is unavailable here. Use the accessible list.
        </p>
      )}
    </div>
  );
}

/**
 * Render a non-editable neighborhood canvas.
 *
 * @param props - Inspect nodes, selection, and list fallback action.
 * @returns React Flow surface. No connect/delete. No invented edges.
 */
export function GraphCanvas(props: GraphCanvasProps) {
  return (
    <ReactFlowProvider>
      <GraphCanvasInner {...props} />
    </ReactFlowProvider>
  );
}

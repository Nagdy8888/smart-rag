/**
 * Graph explorer route. `useSearchParams` requires a Suspense boundary.
 */
import { Suspense } from "react";
import { GraphExplorer } from "../../../components/graph-explorer";

/**
 * Render graph search and inspect.
 *
 * @returns Explorer wrapped in Suspense.
 */
export default function GraphPage() {
  return (
    <Suspense fallback={<p>Loading graph explorer</p>}>
      <GraphExplorer />
    </Suspense>
  );
}

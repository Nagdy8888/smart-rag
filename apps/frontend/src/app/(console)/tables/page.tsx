/**
 * Structured tables route. `useSearchParams` requires a Suspense boundary.
 */
import { Suspense } from "react";
import { TablesApp } from "../../../components/tables/tables-app";

/**
 * Render table manifests and the typed plan builder.
 *
 * @returns Tables wrapped in Suspense.
 */
export default function TablesPage() {
  return (
    <Suspense fallback={<p>Loading tables</p>}>
      <TablesApp />
    </Suspense>
  );
}

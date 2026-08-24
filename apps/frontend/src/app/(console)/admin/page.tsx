/**
 * Consolidated Admin workspace. Bodies stay the existing Team/Tools/Curation/Usage apps.
 */
import { Suspense } from "react";
import { AdminWorkspace } from "../../../components/admin-workspace";

/**
 * Render Admin tabs. Authorization remains on FastAPI.
 *
 * @returns Suspended Admin workspace.
 */
export default function AdminPage() {
  return (
    <Suspense fallback={null}>
      <AdminWorkspace />
    </Suspense>
  );
}

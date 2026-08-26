/**
 * Consolidated Admin workspace.
 */
import { Suspense } from "react";
import { AdminApp } from "../../../components/admin/admin-app";

/**
 * Render Admin tabs. Authorization remains on FastAPI.
 *
 * @returns Suspended Admin workspace.
 */
export default function AdminPage() {
  return (
    <Suspense fallback={null}>
      <AdminApp />
    </Suspense>
  );
}

/**
 * Tool catalog and owner/admin enable/permissions.
 */
import { ToolsApp } from "../../components/tools-app";

/**
 * Render GET /tools cards. Enable remains server-enforced.
 *
 * @returns Tools surface.
 */
export default function ToolsPage() {
  return <ToolsApp />;
}

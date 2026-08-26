/**
 * Bookmark redirect from `/tools` to `/admin?tab=tools`.
 */
import { redirect } from "next/navigation";

/**
 * Send legacy Tools bookmarks to the P08-14 destination.
 *
 * @returns Never. `redirect` throws.
 */
export default function ToolsRedirectPage() {
  redirect("/admin?tab=tools");
}

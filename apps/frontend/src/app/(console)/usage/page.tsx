/**
 * Bookmark redirect from `/usage` to `/admin?tab=usage`.
 */
import { redirect } from "next/navigation";

/**
 * Send legacy Usage bookmarks to the P08-14 destination.
 *
 * @returns Never. `redirect` throws.
 */
export default function UsageRedirectPage() {
  redirect("/admin?tab=usage");
}

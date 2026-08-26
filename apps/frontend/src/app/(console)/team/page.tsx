/**
 * Bookmark redirect from `/team` to `/admin?tab=team`.
 */
import { redirect } from "next/navigation";

/**
 * Send legacy Team bookmarks to the P08-14 destination.
 *
 * @returns Never. `redirect` throws.
 */
export default function TeamRedirectPage() {
  redirect("/admin?tab=team");
}

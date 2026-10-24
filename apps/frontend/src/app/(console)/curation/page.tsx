/**
 * Bookmark redirect from `/curation` to `/admin?tab=team`.
 */
import { redirect } from "next/navigation";

/**
 * Send legacy Curation bookmarks to the P08-14 destination.
 *
 * @returns Never. `redirect` throws.
 */
export default function CurationRedirectPage() {
  redirect("/admin?tab=team");
}
